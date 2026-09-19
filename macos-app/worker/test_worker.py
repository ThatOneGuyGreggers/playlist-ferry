"""Protocol checks that run before installing spotDL's network dependencies."""

import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_rejects_non_boolean_playlist_setting(self):
        code, event = self.request(
            {
                "version": 1,
                "action": "download",
                "url": "https://open.spotify.com/playlist/30eOhDJsGGMtzE6WHpIpTY",
                "destination": str(WORKER.parent),
                "preset": "apple-universal",
                "create_playlist": "yes",
            }
        )
        self.assertEqual(code, 2)
        self.assertIn("true or false", event["message"])

    def test_applies_youtube_thumbnail_choice(self):
        worker = load_worker_module()

        @dataclass
        class Song:
            cover_url: str | None

        song = Song("https://i.ytimg.com/example.jpg")
        self.assertEqual(
            worker.apply_youtube_thumbnail_choice([song], True)[0].cover_url,
            song.cover_url,
        )
        self.assertIsNone(
            worker.apply_youtube_thumbnail_choice([song], False)[0].cover_url
        )

    def test_rejects_non_boolean_youtube_thumbnail_setting(self):
        code, event = self.request(
            {
                "version": 1,
                "action": "download",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "destination": str(WORKER.parent),
                "preset": "apple-universal",
                "youtube_thumbnail": "yes",
            }
        )
        self.assertEqual(code, 2)
        self.assertIn("thumbnail setting", event["message"])

    def test_validates_concurrent_download_count(self):
        worker = load_worker_module()
        for value in [1, 3, 8]:
            with self.subTest(value=value):
                self.assertEqual(worker.validate_concurrent_downloads(value), value)
        for value in [0, 9, True, 2.5, "3"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_concurrent_downloads(value)

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

    def test_accepts_youtube_video_and_playlist_urls(self):
        worker = load_worker_module()
        fixtures = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://music.youtube.com/playlist?list=PL123456789",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
        ]
        for url in fixtures:
            with self.subTest(url=url):
                source, validated = worker.validate_source_url(url)
                self.assertEqual(source, "youtube")
                self.assertEqual(validated, url)

    def test_watch_link_with_playlist_resolves_the_playlist(self):
        worker = load_worker_module()
        source, validated = worker.validate_source_url(
            "https://www.youtube.com/watch?v=artPgvlOtVU"
            "&list=PLyxgmM4B5YzTSFAzp4wUGiIVyxxpWCfOz"
        )

        self.assertEqual(source, "youtube")
        self.assertEqual(
            validated,
            "https://www.youtube.com/playlist?list="
            "PLyxgmM4B5YzTSFAzp4wUGiIVyxxpWCfOz",
        )

    def test_rejects_lookalike_and_malformed_youtube_urls(self):
        worker = load_worker_module()
        fixtures = [
            "https://youtube.example/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch",
            "https://www.youtube.com/playlist",
            "https://user@www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be:443/dQw4w9WgXcQ",
        ]
        for url in fixtures:
            with self.subTest(url=url), self.assertRaises(ValueError):
                worker.validate_source_url(url)

    def test_validates_manual_youtube_video_matches(self):
        worker = load_worker_module()
        song_ids = {"spotify-track"}
        for url in [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ]:
            with self.subTest(url=url):
                self.assertEqual(
                    worker.validate_manual_urls({"spotify-track": url}, song_ids),
                    {
                        "spotify-track":
                            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                    },
                )
        for overrides in [
            {"unknown": "https://youtu.be/dQw4w9WgXcQ"},
            {"spotify-track": "https://www.youtube.com/playlist?list=PL123"},
            {"spotify-track": "https://evil.example/watch?v=dQw4w9WgXcQ"},
        ]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                worker.validate_manual_urls(overrides, song_ids)

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

    def test_writes_ordered_apple_music_playlist_without_overwriting(self):
        worker = load_worker_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "First.m4a"
            second = root / "Second.m4a"
            first.touch()
            second.touch()
            songs = [
                (
                    SimpleNamespace(
                        artists=["Artist A"], name="First", duration=61,
                        list_position=1,
                    ),
                    first,
                ),
                (
                    SimpleNamespace(
                        artists=["Artist B"], name="Second", duration=122,
                        list_position=2,
                    ),
                    second,
                ),
            ]
            playlist = worker.write_apple_music_playlist(
                root, "My/Test: Playlist", songs
            )
            duplicate = worker.write_apple_music_playlist(
                root, "My/Test: Playlist", songs
            )

            self.assertEqual(playlist.name, "My-Test- Playlist.m3u8")
            self.assertEqual(duplicate.name, "My-Test- Playlist 2.m3u8")
            self.assertEqual(
                playlist.read_text(encoding="utf-8").splitlines(),
                [
                    "#EXTM3U",
                    "#PLAYLIST-FERRY-POSITION:1",
                    "#EXTINF:61,Artist A - First",
                    str(first.resolve()),
                    "#PLAYLIST-FERRY-POSITION:2",
                    "#EXTINF:122,Artist B - Second",
                    str(second.resolve()),
                ],
            )
            repaired = root / "Second repaired.m4a"
            repaired.touch()
            worker.update_apple_music_playlist(
                playlist, root, songs[1][0], repaired
            )
            repaired_lines = playlist.read_text(encoding="utf-8").splitlines()
            self.assertIn(str(repaired.resolve()), repaired_lines)
            self.assertNotIn(str(second.resolve()), repaired_lines)
            self.assertLess(
                repaired_lines.index(str(first.resolve())),
                repaired_lines.index(str(repaired.resolve())),
            )

    def test_apple_music_playlist_uses_absolute_paths_with_spaces(self):
        worker = load_worker_module()
        with tempfile.TemporaryDirectory(prefix="Playlist Ferry ") as directory:
            root = Path(directory)
            track = root / "Artist - Track name.m4a"
            track.touch()
            song = SimpleNamespace(
                artists=["Artist"], name="Track name", duration=90,
                list_position=1,
            )

            playlist = worker.write_apple_music_playlist(
                root, "Path Test", [(song, track)]
            )

            lines = playlist.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[-1], str(track.resolve()))
            self.assertTrue(lines[-1].startswith("/"))

    def test_retry_downloads_only_the_selected_track(self):
        import io

        worker = load_worker_module()
        selected = SimpleNamespace(song_id="selected", list_name="My Playlist")
        other = SimpleNamespace(song_id="other", list_name="My Playlist")
        protocol = io.StringIO()
        worker.PROTOCOL_STDOUT = protocol
        with tempfile.TemporaryDirectory() as directory, patch.object(
            worker, "load_source", return_value=({"name": "My Playlist"}, [selected, other])
        ), patch.object(worker, "download") as download:
            worker.handle(
                {
                    "version": 1,
                    "action": "retry_track",
                    "url": "https://open.spotify.com/playlist/30eOhDJsGGMtzE6WHpIpTY",
                    "track_id": "selected",
                    "manual_url": "https://youtu.be/dQw4w9WgXcQ",
                    "destination": directory,
                    "preset": "apple-universal",
                }
            )

        download.assert_called_once()
        arguments = download.call_args.args
        self.assertEqual(arguments[0], [selected])
        self.assertEqual(
            arguments[-2],
            {"selected": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        self.assertEqual(protocol.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
