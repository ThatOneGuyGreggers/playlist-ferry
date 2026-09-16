"""Prepare an isolated, version-pinned native runtime; never alter system Python."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
WORK = APP_ROOT / ".release-work"
PYTHON_VERSION = "3.13.15"


def run(*args: str) -> None:
    subprocess.run(
        args,
        check=True,
        timeout=3600,
        env={**os.environ, "UV_CACHE_DIR": str(WORK / "uv-cache")},
    )


def download(url: str, destination: Path) -> None:
    """Fetch at most 200 MiB over verified HTTPS, with a per-read timeout."""
    with urllib.request.urlopen(url, timeout=60) as response, destination.open(
        "wb"
    ) as output:
        size = 0
        while chunk := response.read(1_048_576):
            size += len(chunk)
            if size > 209_715_200:
                raise ValueError(f"Download exceeds 200 MiB: {url}")
            output.write(chunk)


def main() -> None:
    if platform.system() != "Darwin" or platform.machine() not in ("x86_64", "arm64"):
        raise SystemExit(
            "Build on a native Intel or Apple Silicon Mac; cross-compilation is not supported."
        )
    if not shutil.which("uv"):
        raise SystemExit("Install uv to prepare the pinned standalone Python runtime.")
    WORK.mkdir(exist_ok=True)
    architecture = platform.machine()
    python_architecture = "aarch64" if architecture == "arm64" else "x86_64"
    run(
        "uv",
        "python",
        "install",
        PYTHON_VERSION,
        "--no-bin",
        "--install-dir",
        str(WORK / "python"),
    )
    runtime = (
        WORK / "python" / f"cpython-{PYTHON_VERSION}-macos-{python_architecture}-none"
    )
    python = runtime / "bin" / "python3.13"
    packages = runtime / "lib" / "python3.13" / "site-packages"
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--target",
        str(packages),
        "--require-hashes",
        "-r",
        str(APP_ROOT / "requirements-release.lock"),
    )
    run(
        "uv",
        "pip",
        "install",
        "--python",
        str(python),
        "--target",
        str(packages),
        "--no-deps",
        str(PROJECT_ROOT / "spotify-downloader"),
    )
    tools = WORK / "tools"
    tools.mkdir(exist_ok=True)
    for item in json.loads((APP_ROOT / f"tools-{architecture}.json").read_text()):
        archive = tools / (item["name"] + ".download")
        download(item["url"], archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != item["sha256"]:
            archive.unlink()
            raise ValueError(f"Checksum mismatch for {item['name']}")
        target = tools / item["name"]
        if "zip_member" in item:
            with zipfile.ZipFile(archive) as bundle, bundle.open(
                item["zip_member"]
            ) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        else:
            shutil.copyfile(archive, target)
        target.chmod(0o755)
        archive.unlink()
    notices = tools / "licenses"
    notices.mkdir(exist_ok=True)
    run(
        str(python),
        str(APP_ROOT / "scripts/build-media-tools.py"),
        "--output",
        str(tools),
    )
    for name, url in {
        "Deno-LICENSE.txt": "https://raw.githubusercontent.com/denoland/deno/v2.9.6/LICENSE.md",
    }.items():
        download(url, notices / name)
    print(f"Runtime: {runtime}\nTools: {tools}")


if __name__ == "__main__":
    main()
