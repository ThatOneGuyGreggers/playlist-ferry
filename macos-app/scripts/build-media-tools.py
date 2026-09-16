"""Build audio-only FFmpeg and LAME, retaining source archives and rebuild inputs."""

import argparse
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

SOURCES = {
    "ffmpeg-9.0.1.tar.xz": (
        "https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz",
        "cf38e0e28c7e5605942c4a77755349b0145804a397af37eb1fb4c77cb237f635",
    ),
    "lame-3.100.tar.gz": (
        "https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz",
        "ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e",
    ),
}


def run(args: list[str], directory: Path, log: Path) -> None:
    with log.open("ab") as output:
        result = subprocess.run(
            args,
            cwd=directory,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=1800,
            env={**os.environ, "MACOSX_DEPLOYMENT_TARGET": "13.0"},
        )
    if result.returncode:
        raise RuntimeError(f"Media build failed: {args}; see {log}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = output / "sources"
    sources.mkdir(exist_ok=True)
    for name, (url, digest) in SOURCES.items():
        archive = sources / name
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=60) as response, archive.open(
                "wb"
            ) as target:
                total = 0
                while chunk := response.read(1_048_576):
                    total += len(chunk)
                    if total > 52_428_800:
                        raise ValueError(f"Source exceeds 50 MiB: {name}")
                    target.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source checksum mismatch: {name}")
    shutil.copy2(Path(__file__), sources / "build-media-tools.py")
    notices = output / "licenses"
    notices.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="playlist-ferry-media-") as directory:
        root = Path(directory)
        for name in SOURCES:
            with tarfile.open(sources / name) as archive:
                archive.extractall(root, filter="data")
        lame = root / "lame-3.100"
        ffmpeg = root / "ffmpeg-9.0.1"
        prefix = root / "lame-install"
        log = sources / "build.log"
        log.write_text("Native macOS 13+ audio-only toolchain build\n")
        run(
            [
                "./configure",
                f"--prefix={prefix}",
                "--disable-shared",
                "--enable-static",
                "--disable-frontend",
                "CFLAGS=-mmacosx-version-min=13.0",
            ],
            lame,
            log,
        )
        run(["make", "-j", "2"], lame, log)
        run(["make", "install"], lame, log)
        flags = [
            "--disable-doc",
            "--disable-debug",
            "--disable-shared",
            "--enable-static",
            "--disable-autodetect",
            "--disable-everything",
            "--enable-ffmpeg",
            "--enable-ffprobe",
            "--disable-x86asm",
            "--enable-libmp3lame",
            "--enable-encoder=aac,libmp3lame",
            "--enable-decoder=aac,aac_fixed,mp3,mp3float,opus,vorbis,flac,pcm_s16le,pcm_s24le,pcm_f32le",
            "--enable-parser=aac,mpegaudio,opus,vorbis,flac",
            "--enable-demuxer=mov,matroska,mp3,ogg,wav,flac,aac",
            "--enable-muxer=mp4,ipod,mp3,wav",
            "--enable-protocol=file,pipe",
            "--enable-filter=aresample,aformat,anull,atrim,asetpts",
            "--enable-bsf=aac_adtstoasc",
            "--disable-network",
            f"--extra-cflags=-mmacosx-version-min=13.0 -I{prefix}/include",
            f"--extra-ldflags=-mmacosx-version-min=13.0 -L{prefix}/lib",
        ]
        (sources / "configure-options.txt").write_text("\n".join(flags) + "\n")
        run(["./configure", *flags], ffmpeg, log)
        run(["make", "-j", "2"], ffmpeg, log)
        for name in ("ffmpeg", "ffprobe"):
            shutil.copy2(ffmpeg / name, output / name)
        shutil.copy2(ffmpeg / "COPYING.LGPLv2.1", notices / "FFmpeg-LGPL-2.1.txt")
        shutil.copy2(ffmpeg / "LICENSE.md", notices / "FFmpeg-LICENSE.txt")
        shutil.copy2(lame / "COPYING", notices / "LAME-LICENSE.txt")
    print(f"Audio-only FFmpeg and matching source artifacts: {output}")


if __name__ == "__main__":
    main()
