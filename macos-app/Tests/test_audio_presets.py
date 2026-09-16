"""Exercise every preset with generated audio and artwork, without network access."""

import io
import json
import math
import runpy
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mutagen import File
from PIL import Image
from spotdl.types.song import Song
from spotdl.utils.ffmpeg import convert
from spotdl.utils.metadata import embed_metadata


def main() -> None:
    resources = Path(sys.argv[1]).resolve()
    worker = runpy.run_path(str(resources / "worker.py"))
    artwork = io.BytesIO()
    Image.new("RGB", (32, 32), (40, 180, 150)).save(artwork, format="JPEG")
    song = Song(
        name="Playlist Ferry test tone",
        artists=["Playlist Ferry"],
        artist="Playlist Ferry",
        genres=[],
        disc_number=1,
        disc_count=1,
        album_name="Portable runtime test",
        album_artist="Playlist Ferry",
        duration=5,
        year=2026,
        date="2026-09-15",
        track_number=1,
        tracks_count=1,
        song_id="0000000000000000000000",
        explicit=False,
        publisher="Playlist Ferry",
        url="https://fixture.invalid/tone",
        isrc=None,
        cover_url="https://fixture.invalid/art.jpg",
        copyright_text="Test fixture generated locally",
    )
    with tempfile.TemporaryDirectory(prefix="playlist-ferry-audio-") as directory:
        root = Path(directory)
        source = root / "tone.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(48_000)
            audio.writeframes(
                b"".join(
                    struct.pack(
                        "<h", int(12_000 * math.sin(2 * math.pi * 440 * i / 48_000))
                    )
                    for i in range(240_000)
                )
            )
        for preset in worker["OUTPUT_PRESETS"]:
            settings = worker["output_settings"](preset)
            output = root / (preset + "." + settings["format"])
            success, error = convert(
                source,
                output,
                str(resources / "tools/ffmpeg"),
                settings["format"],
                settings["bitrate"],
                settings["ffmpeg_args"],
            )
            if not success:
                raise RuntimeError(f"{preset} conversion failed: {error}")
            with patch(
                "spotdl.utils.metadata.requests.get",
                return_value=SimpleNamespace(content=artwork.getvalue()),
            ):
                embed_metadata(
                    output, worker["prepare_download_song"](song, settings["format"])
                )
            probe = json.loads(
                subprocess.check_output(
                    [
                        str(resources / "tools/ffprobe"),
                        "-v",
                        "error",
                        "-show_streams",
                        "-of",
                        "json",
                        str(output),
                    ],
                    text=True,
                    timeout=15,
                )
            )
            stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            assert stream["channels"] == 2 and stream["sample_rate"] == "44100", (
                preset,
                stream,
            )
            assert stream["codec_name"] == (
                "mp3" if settings["format"] == "mp3" else "aac"
            ), (preset, stream)
            media = File(output)
            assert media is not None and media.tags, preset
            if settings["format"] == "mp3":
                assert media.tags["TIT2"].text == [song.name]
                assert media.tags["TPE1"].text == song.artists
                assert media.tags.getall("APIC"), "Missing MP3 artwork"
            else:
                assert media.tags["\xa9nam"] == [song.name]
                assert media.tags["\xa9ART"] == song.artists
                assert media.tags["covr"], "Missing M4A artwork"
            print(f"{preset}: correct codec, stereo, 44.1 kHz, title, and artwork")


if __name__ == "__main__":
    main()
