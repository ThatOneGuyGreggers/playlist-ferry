"""Create and audit a relocatable release candidate, then verify its extracted ZIP."""

import argparse
import hashlib
import json
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
MACHO_MAGIC = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}


def run(*args: str) -> str:
    try:
        return subprocess.check_output(
            args, text=True, stderr=subprocess.STDOUT, timeout=300
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Command failed: {args}: {error.output}") from error


def native_files(app: Path) -> list[Path]:
    files = []
    for path in app.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as source:
                if source.read(4) in MACHO_MAGIC:
                    files.append(path)
    return files


def audit(app: Path, architecture: str) -> list[Path]:
    """Reject non-system absolute library dependencies and external symlinks."""
    for path in app.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(app.resolve()):
            raise ValueError(f"External bundle symlink: {path}")
    files = native_files(app)
    for path in files:
        if architecture not in run("lipo", "-archs", str(path)).split():
            raise ValueError(f"Requested architecture missing: {path}")
        commands = run("otool", "-arch", architecture, "-l", str(path))
        minimums = re.findall(
            r"cmd LC_BUILD_VERSION\n(?:(?!Load command).)*?\n\s+minos ([\d.]+)",
            commands,
            re.DOTALL,
        )
        minimums += re.findall(
            r"cmd LC_VERSION_MIN_MACOSX\n(?:(?!Load command).)*?\n\s+version ([\d.]+)",
            commands,
            re.DOTALL,
        )
        for minimum in minimums:
            parts = tuple(int(part) for part in minimum.split("."))
            if parts > (13, 0, 0):
                raise ValueError(
                    f"Native dependency needs macOS {minimum}, above 13.0: {path}"
                )
        for line in run("otool", "-arch", architecture, "-L", str(path)).splitlines()[
            1:
        ]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith("/") and not dependency.startswith(
                ("/usr/lib/", "/System/Library/")
            ):
                raise ValueError(f"Nonportable dependency in {path}: {dependency}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--identity", default="-")
    parser.add_argument(
        "--notary-profile",
        help="Existing notarytool keychain profile for Apple submission",
    )
    parser.add_argument(
        "--arch", choices=["x86_64", "arm64"], default=platform.machine()
    )
    args = parser.parse_args()
    if args.notary_profile and args.identity == "-":
        parser.error(
            "Notarization requires a Developer ID identity; ad hoc signatures are insufficient."
        )
    for required in (
        args.binary,
        args.runtime / "bin/python3.13",
        *(args.tools / name for name in ("ffmpeg", "ffprobe", "deno")),
        args.tools / "licenses",
    ):
        if not required.exists():
            raise SystemExit(f"Missing release input: {required}")
    output = APP_ROOT / "dist" / "release-candidate"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="playlist-ferry-build-") as directory:
        package(args, Path(directory) / "Playlist Ferry.app", output)


def package(args: argparse.Namespace, app: Path, output: Path) -> None:
    contents = app / "Contents"
    resources = contents / "Resources"
    (contents / "MacOS").mkdir(parents=True)
    resources.mkdir()
    shutil.copy2(args.binary, contents / "MacOS" / "PlaylistFerry")
    shutil.copy2(
        APP_ROOT / "Assets/playlist-ferry.icns", resources / "PlaylistFerry.icns"
    )
    shutil.copy2(APP_ROOT / "worker/worker.py", resources / "worker.py")
    shutil.copytree(args.runtime, resources / "python", symlinks=True)
    shutil.copytree(
        args.tools,
        resources / "tools",
        symlinks=True,
        ignore=shutil.ignore_patterns("*.zip", "*.download"),
    )
    # Console entry points have installation-specific shebangs; only Python is launched.
    for path in (resources / "python/bin").iterdir():
        if not path.name.startswith("python"):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    python_alias = resources / "python/bin/python3"
    if not python_alias.exists():
        python_alias.symlink_to("python3.13")
    for path in resources.rglob("__pycache__"):
        shutil.rmtree(path)
    licenses = resources / "Licenses"
    licenses.mkdir()
    shutil.copy2(PROJECT_ROOT / "LICENSE", licenses / "Playlist-Ferry.txt")
    shutil.copy2(PROJECT_ROOT / "spotify-downloader/LICENSE", licenses / "spotDL.txt")
    shutil.copy2(
        APP_ROOT / "requirements-release.lock", licenses / "Python-dependencies.lock"
    )
    shutil.copy2(APP_ROOT / f"tools-{args.arch}.json", licenses / "Tool-manifest.json")
    (licenses / "NOTICE.txt").write_text(
        "Playlist Ferry release candidate (native architecture, macOS 13+).\nPython and Python-package licenses are retained in the python directory.\nFFmpeg and Deno notices are retained in tools/licenses.\nspotDL: https://github.com/spotdl/spotify-downloader\nDesign reference: https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4\nFFmpeg and LAME corresponding sources and build instructions are in tools/sources.\nDeno source: https://github.com/denoland/deno/tree/v2.9.6\nStandalone Python: https://github.com/astral-sh/python-build-standalone\nRedistribution requires reviewing all dependency licenses and corresponding source obligations.\n"
    )
    info = {
        "CFBundleExecutable": "PlaylistFerry",
        "CFBundleIdentifier": "dev.greggers.playlist-ferry",
        "CFBundleName": "Playlist Ferry",
        "CFBundleDisplayName": "Playlist Ferry",
        "CFBundleIconFile": "PlaylistFerry",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.9.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "CFBundleDevelopmentRegion": "en",
        "CFBundleInfoDictionaryVersion": "6.0",
    }
    with (contents / "Info.plist").open("wb") as destination:
        plistlib.dump(info, destination)
    run("xattr", "-cr", str(app))
    # uv rewrites libpython's ID at installation; remove that builder-specific ID.
    for path in native_files(app):
        identifiers = [
            line.strip()
            for line in run("otool", "-arch", args.arch, "-D", str(path)).splitlines()[
                1:
            ]
            if line.strip() and not line.rstrip().endswith(":")
        ]
        if identifiers and identifiers[0].startswith("/"):
            run("install_name_tool", "-id", "@rpath/" + path.name, str(path))
    files = audit(app, args.arch)
    run("xattr", "-cr", str(app))
    signing = ["codesign", "--force", "--sign", args.identity]
    if args.identity != "-":
        signing += ["--options", "runtime", "--timestamp"]
    entitlements = app.parent / "runtime-entitlements.plist"
    with entitlements.open("wb") as destination:
        plistlib.dump(
            {
                "com.apple.security.cs.allow-jit": True,
                "com.apple.security.cs.allow-unsigned-executable-memory": True,
            },
            destination,
        )
    # Sign nested code before sealing the outer application bundle.
    for path in sorted(files, key=lambda p: len(p.parts), reverse=True):
        if path == contents / "MacOS" / "PlaylistFerry":
            continue
        run("xattr", "-c", str(path))
        executable_options = []
        if args.identity != "-" and (
            path.name.startswith("python") or path.name == "deno"
        ):
            executable_options = ["--entitlements", str(entitlements)]
        run(*signing, *executable_options, str(path))
    run("xattr", "-cr", str(app))
    run(*signing, str(app))
    run("codesign", "--verify", "--deep", "--strict", str(app))
    archive = output / f"Playlist-Ferry-0.9.0-rc.1-macos-{args.arch}.zip"
    if archive.exists():
        archive.unlink()
    run(
        "ditto",
        "-c",
        "-k",
        "--keepParent",
        "--norsrc",
        "--noextattr",
        str(app),
        str(archive),
    )
    if args.notary_profile:
        submission = subprocess.run(
            [
                "xcrun",
                "notarytool",
                "submit",
                str(archive),
                "--keychain-profile",
                args.notary_profile,
                "--wait",
                "--output-format",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        response = json.loads(submission.stdout)
        if response.get("status") != "Accepted":
            raise RuntimeError(f"Apple notarization was not accepted: {response}")
        print(f"Apple accepted notarization: {response.get('id')}")
        run("xcrun", "stapler", "staple", str(app))
        run("xcrun", "stapler", "validate", str(app))
        run("spctl", "--assess", "--type", "execute", "--verbose", str(app))
        archive.unlink()
        run(
            "ditto",
            "-c",
            "-k",
            "--keepParent",
            "--norsrc",
            "--noextattr",
            str(app),
            str(archive),
        )
    with tempfile.TemporaryDirectory(prefix="playlist-ferry-extracted-") as directory:
        run("ditto", "-x", "-k", str(archive), directory)
        extracted = Path(directory) / app.name
        audit(extracted, args.arch)
        run("codesign", "--verify", "--deep", "--strict", str(extracted))
        python = extracted / "Contents/Resources/python/bin/python3"
        result = run(
            str(python),
            "-I",
            "-B",
            "-c",
            'import spotdl, yt_dlp, mutagen, ssl; print("Bundled imports passed")',
        )
        print(result.strip())
    archive.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(archive.read_bytes()).hexdigest() + "  " + archive.name + "\n"
    )
    print(f"Verified candidate: {archive}")


if __name__ == "__main__":
    main()
