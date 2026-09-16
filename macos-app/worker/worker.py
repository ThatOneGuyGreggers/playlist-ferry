"""One-request spotDL worker. Each stdout line is a JSON event for the app."""

import contextlib
import json
import logging
import os
import shlex
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

MAX_REQUEST_BYTES = 16_384
MAX_TRACKS = 1_000
MAX_EVENT_BYTES = 4_194_304
PROTOCOL_STDOUT = sys.stdout
OUTPUT_PRESETS = {
    "apple-universal": {
        "format": "m4a",
        "bitrate": "128k",
        "ffmpeg_args": "-ar 44100 -ac 2 -movflags +faststart",
    },
    "apple-high-quality": {
        "format": "m4a",
        "bitrate": "256k",
        "ffmpeg_args": "-ar 44100 -ac 2 -movflags +faststart",
    },
    "ipod-legacy-aac": {
        "format": "m4a",
        "bitrate": "128k",
        "ffmpeg_args": "-ar 44100 -ac 2 -movflags +faststart",
    },
    "ipod-legacy-mp3": {
        "format": "mp3",
        "bitrate": "128k",
        "ffmpeg_args": "-ar 44100 -ac 2",
    },
}
# Development can use the pinned checkout; packaged Python imports installed wheels.
SOURCE_ROOT = Path(
    os.environ.get(
        "SPOTDL_SOURCE_ROOT", Path(__file__).resolve().parents[2] / "spotify-downloader"
    )
)
if (
    os.environ.get("PLAYLIST_FERRY_BUNDLED") != "1"
    and (SOURCE_ROOT / "spotdl" / "__init__.py").is_file()
):
    sys.path.insert(0, str(SOURCE_ROOT))
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def emit(event: str, **data: object) -> None:
    """Write one complete protocol event and flush it immediately."""
    payload = json.dumps({"event": event, **data})
    if len(payload.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ValueError("Playlist response exceeds the supported size.")
    print(payload, file=PROTOCOL_STDOUT, flush=True)


def validate_playlist_url(value: object) -> str:
    """Return a public Spotify playlist URL or raise a user-facing error."""
    if not isinstance(value, str) or len(value) > 2_048:
        raise ValueError("Enter a Spotify playlist URL under 2,048 characters.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "open.spotify.com":
        raise ValueError("Enter an https://open.spotify.com/playlist/ URL.")
    parts = parsed.path.strip("/").split("/")
    if (
        len(parts) != 2
        or parts[0] != "playlist"
        or len(parts[1]) != 22
        or not parts[1].isascii()
        or not parts[1].isalnum()
    ):
        raise ValueError("Enter a valid Spotify playlist URL.")
    return value


def load_playlist(url: str):
    """Initialize spotDL's public metadata client and fetch playlist tracks."""
    from spotdl.types.playlist import Playlist
    from spotdl.utils.config import SPOTIFY_OPTIONS
    from spotdl.utils.spotify import SpotifyClient

    SpotifyClient.init(**SPOTIFY_OPTIONS)
    metadata, songs = Playlist.get_metadata(url)
    if len(songs) > MAX_TRACKS:
        raise ValueError(
            f"This version supports at most {MAX_TRACKS} tracks per playlist."
        )
    return metadata, songs


def song_data(song) -> dict:
    """Expose only the fields needed by the native interface."""
    return {
        "id": song.song_id,
        "name": song.name,
        "artists": song.artists,
        "duration": song.duration,
        "position": song.list_position,
    }


def output_settings(preset_name: object) -> dict:
    """Return bounded FFmpeg settings for a known device profile."""
    if not isinstance(preset_name, str) or preset_name not in OUTPUT_PRESETS:
        supported = ", ".join(OUTPUT_PRESETS)
        raise ValueError(f"Choose a supported output preset: {supported}.")
    return OUTPUT_PRESETS[preset_name].copy()


def prepare_download_song(song, output_format: str):
    """Avoid passing None to upstream MP3 ISRC tagging; preserve the caller's song."""
    if output_format == "mp3" and song.isrc is None:
        return replace(song, isrc="")
    return song


def download(songs: list, destination: Path, preset_name: str) -> None:
    """Download sequentially so each track has a clear completion event."""
    from spotdl.download.downloader import Downloader

    preset = output_settings(preset_name)
    settings = {
        "output": str(destination / "{artists} - {title}.{output-ext}"),
        "threads": 1,
        **preset,
    }
    bundled_ffmpeg = os.environ.get("SPOTDL_FFMPEG")
    if bundled_ffmpeg:
        settings["ffmpeg"] = bundled_ffmpeg
    tools = Path(__file__).resolve().parent / "tools"
    if os.environ.get("PLAYLIST_FERRY_BUNDLED") == "1":
        for name in ("ffmpeg", "ffprobe", "deno"):
            if not os.access(tools / name, os.X_OK):
                raise RuntimeError(
                    f"The bundled {name} executable is missing. Reinstall Playlist Ferry."
                )
        settings["ffmpeg"] = str(tools / "ffmpeg")
        settings["yt_dlp_args"] = shlex.join(
            [
                "--js-runtimes",
                f"deno:{tools / 'deno'}",
                "--ffmpeg-location",
                str(tools),
                "--socket-timeout",
                "20",
                "--retries",
                "2",
                "--fragment-retries",
                "2",
                "--extractor-retries",
                "2",
                "--no-progress",
            ]
        )
    settings["simple_tui"] = True
    settings["load_config"] = False
    downloader = Downloader(settings=settings)
    failures = 0
    try:
        for index, song in enumerate(songs, start=1):
            song = prepare_download_song(song, preset["format"])
            emit("track_started", id=song.song_id, index=index, total=len(songs))
            try:
                _, output = downloader.search_and_download(song)
                if output is None:
                    raise RuntimeError("No matching YouTube audio was downloaded.")
                emit("track_complete", id=song.song_id, path=str(output))
            except Exception as error:
                failures += 1
                LOGGER.exception("Track failed: %s", song.song_id)
                emit("track_failed", id=song.song_id, message=failure_message(error))
    finally:
        downloader.loop.close()
    emit("complete", total=len(songs), failed=failures)


def handle(request: dict) -> None:
    """Validate the request before loading network and download libraries."""
    if request.get("version") != 1:
        raise ValueError("Unsupported worker protocol version.")
    action = request.get("action")
    if action not in ("preview", "download"):
        raise ValueError("Unknown worker action.")
    url = validate_playlist_url(request.get("url"))
    destination = None
    preset_name: object = "apple-universal"
    if action == "download":
        raw_destination = request.get("destination")
        if not isinstance(raw_destination, str) or not raw_destination:
            raise ValueError("Choose a destination folder.")
        destination = Path(raw_destination).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError("The destination folder is unavailable.")
        preset_name = request.get("preset")
        output_settings(preset_name)

    metadata, songs = load_playlist(url)
    emit("playlist", metadata=metadata, songs=[song_data(song) for song in songs])
    if action == "download":
        assert destination is not None and isinstance(preset_name, str)
        download(songs, destination, preset_name)


def failure_message(error: Exception) -> str:
    """Convert an internal failure into a bounded message useful to the app user."""
    if isinstance(error, ModuleNotFoundError):
        dependency = error.name or "unknown"
        return f"A required download component is missing: {dependency}. Rebuild the app runtime."
    if isinstance(
        error, (ConnectionError, TimeoutError)
    ) or error.__class__.__module__.startswith(("requests", "urllib3")):
        return (
            "Could not connect to Spotify. Check the internet connection and try again."
        )
    message = str(error).strip()
    if not message:
        return "The playlist request failed without an error description."
    return message[:500]


def main() -> int:
    """Read one bounded request and return a terminal event."""
    # Own a process group so cancellation also stops FFmpeg and Deno children.
    if os.getpgrp() != os.getpid():
        os.setsid()
    raw = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        emit("error", message="Worker request is too large.")
        return 2
    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("Worker request must be an object.")
        # Keep dependency progress and diagnostics off the JSON event channel.
        with contextlib.redirect_stdout(sys.stderr):
            handle(request)
        return 0
    except (ValueError, json.JSONDecodeError) as error:
        emit("error", message=failure_message(error))
        return 2
    except Exception as error:
        LOGGER.exception("Worker request failed")
        emit("error", message=failure_message(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
