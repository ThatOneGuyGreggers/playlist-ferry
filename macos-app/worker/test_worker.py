"""Protocol checks that run before installing spotDL's network dependencies."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

WORKER = Path(__file__).with_name("worker.py")


def load_worker_module():
    import importlib.util

    specification = importlib.util.spec_from_file_location("worker_under_test", WORKER)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class WorkerProtocolTests(unittest.TestCase):
    def request(self, payload: object):
        result = subprocess.run(
            [sys.executable, str(WORKER)],
            input=json.dumps(payload) + "\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode, json.loads(result.stdout)

    def test_rejects_non_spotify_host(self):
        code, event = self.request(
            {
                "version": 1,
                "action": "preview",
                "url": "https://evil.example/playlist/30eOhDJsGGMtzE6WHpIpTY",
            }
        )
        self.assertEqual(code, 2)
        self.assertEqual(event["event"], "error")

    def test_rejects_unknown_protocol_version(self):
        code, event = self.request({"version": 2, "action": "preview"})
        self.assertEqual(code, 2)
        self.assertIn("version", event["message"])

    def test_rejects_download_without_destination(self):
        code, event = self.request(
            {
                "version": 1,
                "action": "download",
                "url": "https://open.spotify.com/playlist/30eOhDJsGGMtzE6WHpIpTY",
            }
        )
        self.assertEqual(code, 2)
        self.assertIn("destination", event["message"])

    def test_rejects_unknown_output_preset(self):
        code, event = self.request(
            {
                "version": 1,
                "action": "download",
                "url": "https://open.spotify.com/playlist/30eOhDJsGGMtzE6WHpIpTY",
                "destination": str(WORKER.parent),
                "preset": "unbounded-custom-arguments",
            }
        )
        self.assertEqual(code, 2)
        self.assertIn("preset", event["message"])

    def test_rejects_oversized_request(self):
        code, event = self.request({"padding": "x" * 20_000})
        self.assertEqual(code, 2)
        self.assertIn("too large", event["message"])

    def test_rejects_credentials_ports_and_unicode_ids(self):
        worker = load_worker_module()
        for url in [
            "https://user@open.spotify.com/playlist/30eOhDJsGGMtzE6WHpIpTY",
            "https://open.spotify.com:443/playlist/30eOhDJsGGMtzE6WHpIpTY",
            "https://open.spotify.com/playlist/" + "é" * 22,
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                worker.validate_playlist_url(url)

    def test_dependency_output_does_not_corrupt_protocol(self):
        import contextlib
        import io

        worker = load_worker_module()
        protocol = io.StringIO()
        diagnostics = io.StringIO()
        worker.PROTOCOL_STDOUT = protocol
        with contextlib.redirect_stdout(diagnostics):
            print("dependency progress")
            worker.emit("complete", failed=0)
        self.assertEqual(json.loads(protocol.getvalue())["event"], "complete")
        self.assertIn("dependency progress", diagnostics.getvalue())

    def test_missing_dependency_message_names_the_component(self):
        worker = load_worker_module()
        error = ModuleNotFoundError(
            "No module named 'example_dependency'", name="example_dependency"
        )
        self.assertIn("example_dependency", worker.failure_message(error))


if __name__ == "__main__":
    unittest.main()
