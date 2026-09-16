"""Check protocol, native lifecycle, and every preset against an extracted candidate."""

import argparse
import os
import platform
import runpy
import subprocess
import tempfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, check=True, timeout=300, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="playlist-ferry-check-") as directory:
        root = Path(directory)
        run("ditto", "-x", "-k", str(args.archive.resolve()), str(root))
        app = root / "Playlist Ferry.app"
        resources = app / "Contents/Resources"
        runpy.run_path(str(APP_ROOT / "scripts/package-release.py"))["audit"](
            app, platform.machine()
        )
        python = resources / "python/bin/python3"
        environment = {
            **os.environ,
            "HOME": str(root),
            "PATH": str(resources / "tools") + ":/usr/bin:/bin",
            "PLAYLIST_FERRY_BUNDLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for name in (
            "PYTHONHOME",
            "PYTHONPATH",
            "DYLD_INSERT_LIBRARIES",
            "DYLD_LIBRARY_PATH",
        ):
            environment.pop(name, None)
        run("codesign", "--verify", "--deep", "--strict", str(app))
        run(
            str(python),
            "-I",
            "-B",
            str(APP_ROOT / "worker/test_worker.py"),
            env=environment,
        )
        run(
            str(python),
            "-I",
            "-B",
            str(APP_ROOT / "Tests/test_audio_presets.py"),
            str(resources),
            env=environment,
        )
        binary = root / "WorkerManagerTests"
        run(
            "swiftc",
            "-parse-as-library",
            str(APP_ROOT / "Swift/WorkerManager.swift"),
            str(APP_ROOT / "Tests/WorkerManagerTests.swift"),
            "-module-cache-path",
            str(root / "modules"),
            "-o",
            str(binary),
        )
        run(str(binary))
        run("codesign", "--verify", "--deep", "--strict", str(app))
    print(
        "Extracted candidate passed protocol, native lifecycle, audio, and signature checks."
    )


if __name__ == "__main__":
    main()
