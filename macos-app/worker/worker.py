"""One-request spotDL worker. Each stdout line is a JSON event for the app."""

import contextlib
import asyncio
import json
import logging
import os
import re
import shlex
import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

MAX_REQUEST_BYTES = 16_384
MAX_TRACKS = 1_000
MAX_CONCURRENT_DOWNLOADS = 8
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
# Development uses the pinned checkout. A local test bundle places the checkout
# beside this script, while a release imports the installed wheel.
WORKER_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_SOURCE_ROOT = (
    WORKER_DIRECTORY / "spotify-downloader"
    if (WORKER_DIRECTORY / "spotify-downloader" / "spotdl" / "__init__.py").is_file()
    else Path(__file__).resolve().parents[2] / "spotify-downloader"
)
SOURCE_ROOT = Path(os.environ.get("SPOTDL_SOURCE_ROOT", DEFAULT_SOURCE_ROOT))
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


def validate_source_url(value: object) -> tuple[str, str]:
    """Return the source type and a supported public playlist/video URL."""
    if not isinstance(value, str) or len(value) > 2_048:
        raise ValueError("Enter a Spotify or YouTube URL under 2,048 characters.")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Enter a public HTTPS Spotify or YouTube URL.")
    host = (parsed.hostname or "").lower()
    if host == "open.spotify.com":
        parts = parsed.path.strip("/").split("/")
        if (
            len(parts) != 2
            or parts[0] != "playlist"
            or len(parts[1]) != 22
            or not parts[1].isascii()
            or not parts[1].isalnum()
        ):
            raise ValueError("Enter a valid Spotify playlist URL.")
        return "spotify", value

    youtube_hosts = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }
    query = parse_qs(parsed.query)
    parts = parsed.path.strip("/").split("/")
    valid_youtube = False
    normalized_url = value
    if host == "youtu.be":
        valid_youtube = len(parts) == 1 and bool(parts[0])
    elif host in youtube_hosts:
        valid_youtube = (
            (parsed.path == "/watch" and bool(query.get("v")))
            or (parsed.path == "/playlist" and bool(query.get("list")))
            or (len(parts) == 2 and parts[0] in {"shorts", "live"} and bool(parts[1]))
        )
        # YouTube share links for playlist items use /watch with both v and list.
        # Give the playlist identifier precedence so yt-dlp cannot interpret the
        # same input as only the selected video.
        if parsed.path == "/watch" and query.get("v") and query.get("list"):
            playlist_id = query["list"][0]
            if (
                not playlist_id
                or len(playlist_id) > 150
                or not playlist_id.isascii()
                or any(
                    character
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for character in playlist_id
                )
            ):
                raise ValueError("Enter a valid YouTube playlist URL.")
            normalized_url = (
                "https://www.youtube.com/playlist?list=" + playlist_id
            )
    if not valid_youtube:
        raise ValueError("Enter a valid YouTube video or playlist URL.")
    return "youtube", normalized_url


def validate_playlist_url(value: object) -> str:
    """Backward-compatible validator used by protocol tests and integrations."""
    return validate_source_url(value)[1]


def validate_youtube_video_url(value: object) -> str:
    """Return a canonical direct YouTube video URL, never a playlist URL."""
    source, url = validate_source_url(value)
    if source != "youtube":
        raise ValueError("Manual matches must be direct YouTube video URLs.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if host == "youtu.be":
        video_id = parts[0] if len(parts) == 1 else ""
    elif parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live"}:
        video_id = parts[1]
    else:
        video_id = ""
    if (
        len(video_id) != 11
        or not video_id.isascii()
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in video_id
        )
    ):
        raise ValueError("Manual matches must be direct YouTube video URLs.")
    return f"https://www.youtube.com/watch?v={video_id}"


def validate_manual_urls(value: object, song_ids: set[str]) -> dict[str, str]:
    """Validate bounded per-track direct-video overrides."""
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > MAX_TRACKS:
        raise ValueError("Manual YouTube matches must be a track-to-URL object.")
    validated = {}
    for song_id, url in value.items():
        if not isinstance(song_id, str) or song_id not in song_ids:
            raise ValueError("A manual YouTube match refers to an unknown track.")
        validated[song_id] = validate_youtube_video_url(url)
    return validated


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


def youtube_options() -> dict:
    """Use bounded, quiet yt-dlp extraction with the packaged media tools."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": MAX_TRACKS + 1,
        "socket_timeout": 20,
        "retries": 2,
        "extractor_retries": 2,
    }
    tools = Path(__file__).resolve().parent / "tools"
    if os.environ.get("PLAYLIST_FERRY_BUNDLED") == "1":
        options["js_runtimes"] = {"deno": {"path": str(tools / "deno")}}
        options["ffmpeg_location"] = str(tools)
    else:
        node = os.environ.get("PLAYLIST_FERRY_NODE")
        if node:
            options["js_runtimes"] = {"node": {"path": node}}
    return options


def stable_youtube_thumbnail_url(url: str) -> str:
    """Prefer query-free JPEG artwork when a ytimg video ID is available."""
    parsed = urlparse(url)
    match = re.fullmatch(r"/vi/([A-Za-z0-9_-]{11})/[^/]+", parsed.path)
    if parsed.hostname in {"i.ytimg.com", "img.youtube.com"} and match:
        return f"https://i.ytimg.com/vi/{match.group(1)}/hqdefault.jpg"
    return url


def youtube_thumbnail_url(entry: dict, video_id: str | None = None) -> str | None:
    """Return the best HTTP(S) thumbnail from full or flat yt-dlp metadata."""
    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    thumbnail = entry.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail.startswith(("https://", "http://")):
        return stable_youtube_thumbnail_url(thumbnail)
    thumbnails = entry.get("thumbnails")
    if not isinstance(thumbnails, list):
        return None
    candidates = [
        item
        for item in thumbnails
        if isinstance(item, dict)
        and isinstance(item.get("url"), str)
        and item["url"].startswith(("https://", "http://"))
    ]
    if not candidates:
        return None

    def dimension(value: object) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0

    best = max(
        candidates,
        key=lambda item: (
            dimension(item.get("width")) * dimension(item.get("height")),
            dimension(item.get("width")),
        ),
    )
    return stable_youtube_thumbnail_url(best["url"])


def youtube_song(entry: dict, position: int, count: int, list_name: str):
    """Translate yt-dlp metadata into the song shape used by the downloader."""
    from spotdl.types.song import Song

    video_id = str(entry.get("id") or "").strip()
    title = str(entry.get("title") or "").strip()
    if not video_id or not title:
        raise ValueError("YouTube returned an unavailable video in this playlist.")
    channel = str(
        entry.get("artist")
        or entry.get("channel")
        or entry.get("uploader")
        or "YouTube"
    ).strip()
    webpage_url = entry.get("webpage_url") or entry.get("url")
    if not isinstance(webpage_url, str) or not webpage_url.startswith("http"):
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"
    upload_date = str(entry.get("upload_date") or "")
    thumbnail = youtube_thumbnail_url(entry, video_id)
    return Song(
        name=title,
        artists=[channel],
        artist=channel,
        genres=[],
        disc_number=1,
        disc_count=1,
        album_name=list_name,
        album_artist=channel,
        duration=int(entry.get("duration") or 0),
        year=int(upload_date[:4]) if upload_date[:4].isdigit() else 0,
        date=upload_date,
        track_number=position,
        tracks_count=count,
        # A playlist can contain the same video more than once; SwiftUI IDs and
        # per-row progress still need to be unique.
        song_id=f"youtube:{video_id}:{position}",
        explicit=False,
        publisher=channel,
        url=webpage_url,
        isrc="",
        cover_url=thumbnail,
        copyright_text=None,
        download_url=webpage_url,
        list_name=list_name,
        list_url=webpage_url,
        list_position=position,
        list_length=count,
        album_id="",
        artist_id="",
        album_type="playlist",
    )


def load_youtube(url: str):
    """Fetch a YouTube playlist or a single video's public metadata."""
    from yt_dlp import YoutubeDL

    with YoutubeDL(youtube_options()) as client:
        info = client.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise ValueError("YouTube did not return video information.")
    raw_entries = info.get("entries")
    entries = [entry for entry in raw_entries or [] if isinstance(entry, dict)]
    if raw_entries is None:
        entries = [info]
    if len(entries) > MAX_TRACKS:
        raise ValueError(
            f"This version supports at most {MAX_TRACKS} tracks per playlist."
        )
    if not entries:
        raise ValueError("This YouTube playlist has no downloadable videos.")
    name = str(info.get("title") or entries[0].get("title") or "YouTube")
    author = str(info.get("channel") or info.get("uploader") or "YouTube")
    songs = [
        youtube_song(entry, index, len(entries), name)
        for index, entry in enumerate(entries, 1)
    ]
    metadata = {
        "name": name,
        "author_name": author,
        "description": info.get("description"),
        "cover_url": youtube_thumbnail_url(info),
    }
    return metadata, songs


def load_source(source: str, url: str):
    if source == "youtube":
        return load_youtube(url)
    return load_playlist(url)


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


def validate_concurrent_downloads(value: object) -> int:
    """Return a safe worker count for parallel network and FFmpeg work."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_CONCURRENT_DOWNLOADS
    ):
        raise ValueError(
            f"Concurrent downloads must be between 1 and {MAX_CONCURRENT_DOWNLOADS}."
        )
    return value


def prepare_download_song(song, output_format: str):
    """Avoid passing None to upstream MP3 ISRC tagging; preserve the caller's song."""
    if output_format == "mp3" and song.isrc is None:
        return replace(song, isrc="")
    return song


def apply_youtube_artwork_choice(
    songs: list, artwork: str, playlist_cover_url: object
) -> list:
    """Keep per-video artwork unless the user declines all artwork."""
    if artwork in {"video", "both"}:
        return songs
    if artwork == "none":
        return [replace(song, cover_url=None) for song in songs]
    raise ValueError("Choose YouTube artwork or no artwork.")


def playlist_filename(name: str) -> str:
    """Return a safe, readable filename for an exported Apple Music playlist."""
    cleaned = re.sub(r"[/:\x00-\x1f]", "-", name).strip(" .")
    return (cleaned or "Playlist Ferry")[:180]


def write_youtube_playlist_artwork(
    destination: Path, name: str, artwork_url: str
) -> Path:
    """Download a bounded JPEG copy of the YouTube playlist thumbnail."""
    output = destination / f"{playlist_filename(name)} artwork.jpg"
    suffix = 2
    while output.exists():
        output = destination / f"{playlist_filename(name)} artwork {suffix}.jpg"
        suffix += 1
    with urlopen(artwork_url, timeout=20) as response:
        artwork = response.read(10_485_761)
    if len(artwork) > 10_485_760 or not artwork.startswith(b"\xff\xd8\xff"):
        raise ValueError("YouTube did not return valid JPEG playlist artwork.")
    temporary = output.with_suffix(".jpg.tmp")
    temporary.write_bytes(artwork)
    temporary.replace(output)
    return output


def song_position(song) -> int:
    """Return the source-list position while tolerating minimal test metadata."""
    return int(
        getattr(song, "list_position", None)
        or getattr(song, "track_number", 0)
        or 0
    )


def apple_music_track_path(path: Path) -> str:
    """Return an absolute macOS path Apple Music can resolve during import."""
    return str(path.expanduser().resolve()).replace("\n", " ")


def write_apple_music_playlist(
    destination: Path, name: str, completed: list[tuple[object, Path]]
) -> Path:
    """Write an ordered UTF-8 extended M3U file importable by Apple Music."""
    stem = playlist_filename(name)
    output = destination / f"{stem}.m3u8"
    suffix = 2
    while output.exists():
        output = destination / f"{stem} {suffix}.m3u8"
        suffix += 1

    lines = ["#EXTM3U"]
    for song, path in completed:
        position = song_position(song)
        lines.append(f"#PLAYLIST-FERRY-POSITION:{position}")
        label = f"{', '.join(song.artists)} - {song.name}".replace("\n", " ")
        lines.append(f"#EXTINF:{max(0, int(song.duration))},{label}")
        lines.append(apple_music_track_path(path))
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def update_apple_music_playlist(
    playlist: Path, destination: Path, song, track_path: Path
) -> Path:
    """Insert or replace one downloaded track in its original playlist order."""
    playlist = playlist.resolve()
    destination = destination.resolve()
    if (
        playlist.parent != destination
        or playlist.suffix.lower() != ".m3u8"
        or not playlist.is_file()
    ):
        raise ValueError("The Apple Music playlist is unavailable for this retry.")

    lines = playlist.read_text(encoding="utf-8").splitlines()
    blocks: list[tuple[int, list[str]]] = []
    index = 1 if lines[:1] == ["#EXTM3U"] else 0
    fallback_position = MAX_TRACKS + 1
    while index < len(lines):
        if lines[index].startswith("#PLAYLIST-FERRY-POSITION:"):
            try:
                position = int(lines[index].split(":", 1)[1])
            except ValueError:
                position = fallback_position
            block = lines[index : min(index + 3, len(lines))]
            index += len(block)
        else:
            position = fallback_position
            block = lines[index : min(index + 2, len(lines))]
            index += len(block)
        blocks.append((position, block))
        fallback_position += 1

    position = song_position(song)
    label = f"{', '.join(song.artists)} - {song.name}".replace("\n", " ")
    replacement = [
        f"#PLAYLIST-FERRY-POSITION:{position}",
        f"#EXTINF:{max(0, int(song.duration))},{label}",
        apple_music_track_path(track_path),
    ]
    blocks = [(item_position, block) for item_position, block in blocks if item_position != position]
    blocks.append((position, replacement))
    output_lines = ["#EXTM3U"]
    for _, block in sorted(blocks, key=lambda item: item[0]):
        output_lines.extend(block)
    temporary = playlist.with_suffix(".m3u8.tmp")
    temporary.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    temporary.replace(playlist)
    return playlist


def download(
    songs: list,
    destination: Path,
    preset_name: str,
    playlist_name: str,
    create_playlist: bool,
    concurrent_downloads: int,
    manual_urls: dict[str, str],
    playlist_to_update: Path | None = None,
    playlist_artwork_url: str | None = None,
) -> None:
    """Download tracks concurrently with isolated progress and failures."""
    from spotdl.download.downloader import Downloader

    preset = output_settings(preset_name)
    settings = {
        "output": str(destination / "{artists} - {title}.{output-ext}"),
        "threads": concurrent_downloads,
        **preset,
    }
    bundled_ffmpeg = os.environ.get("SPOTDL_FFMPEG")
    if bundled_ffmpeg:
        settings["ffmpeg"] = bundled_ffmpeg
    node = os.environ.get("PLAYLIST_FERRY_NODE")
    if node:
        settings["yt_dlp_args"] = shlex.join(["--js-runtimes", f"node:{node}"])
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
    completed: list[tuple[int, object, Path]] = []

    async def download_all() -> None:
        nonlocal failures
        gate = asyncio.Semaphore(concurrent_downloads)

        async def download_one(index: int, original_song) -> None:
            nonlocal failures
            async with gate:
                override = manual_urls.get(original_song.song_id)
                song = replace(original_song, download_url=override) if override else original_song
                song = prepare_download_song(song, preset["format"])
                emit("track_started", id=song.song_id, index=index, total=len(songs))
                try:
                    _, output = await downloader.async_search_and_download(song)
                    if output is None:
                        raise RuntimeError("No matching YouTube audio was downloaded.")
                    completed.append((index, song, Path(output)))
                    emit("track_complete", id=song.song_id, path=str(output))
                except Exception as error:
                    failures += 1
                    LOGGER.exception("Track failed: %s", song.song_id)
                    emit(
                        "track_failed",
                        id=song.song_id,
                        message=failure_message(error),
                    )

        await asyncio.gather(
            *(download_one(index, song) for index, song in enumerate(songs, start=1))
        )

    try:
        downloader.loop.run_until_complete(download_all())
    finally:
        downloader.loop.close()
    playlist_path = None
    artwork_path = None
    if create_playlist and completed:
        playlist_path = write_apple_music_playlist(
            destination,
            playlist_name,
            [(song, path) for _, song, path in sorted(completed)],
        )
    elif playlist_to_update is not None and completed:
        _, repaired_song, repaired_path = completed[0]
        playlist_path = update_apple_music_playlist(
            playlist_to_update, destination, repaired_song, repaired_path
        )
    if playlist_artwork_url is not None and completed:
        artwork_path = write_youtube_playlist_artwork(
            destination, playlist_name, playlist_artwork_url
        )
    emit(
        "complete",
        total=len(songs),
        failed=failures,
        playlist_path=str(playlist_path) if playlist_path else None,
        artwork_path=str(artwork_path) if artwork_path else None,
    )


def handle(request: dict) -> None:
    """Validate the request before loading network and download libraries."""
    if request.get("version") != 1:
        raise ValueError("Unsupported worker protocol version.")
    action = request.get("action")
    if action not in ("preview", "download", "retry_track"):
        raise ValueError("Unknown worker action.")
    source, url = validate_source_url(request.get("url"))
    destination = None
    preset_name: object = "apple-universal"
    create_playlist = True
    concurrent_downloads = 3
    youtube_artwork = "video"
    raw_manual_urls: object = {}
    if action in ("download", "retry_track"):
        raw_destination = request.get("destination")
        if not isinstance(raw_destination, str) or not raw_destination:
            raise ValueError("Choose a destination folder.")
        destination = Path(raw_destination).expanduser().resolve()
        if not destination.is_dir():
            raise ValueError("The destination folder is unavailable.")
        preset_name = request.get("preset")
        output_settings(preset_name)
        if action == "download":
            create_playlist = request.get("create_playlist", True)
            if not isinstance(create_playlist, bool):
                raise ValueError(
                    "The Apple Music playlist setting must be true or false."
                )
            concurrent_downloads = validate_concurrent_downloads(
                request.get("concurrent_downloads", 3)
            )
            youtube_artwork = request.get("youtube_artwork")
            if youtube_artwork is None:
                include_thumbnail = request.get("youtube_thumbnail", True)
                if not isinstance(include_thumbnail, bool):
                    raise ValueError(
                        "The YouTube thumbnail setting must be true or false."
                    )
                youtube_artwork = "video" if include_thumbnail else "none"
            if youtube_artwork not in {"video", "both", "none"}:
                raise ValueError("Choose YouTube artwork or no artwork.")
            raw_manual_urls = request.get("manual_urls", {})

    metadata, songs = load_source(source, url)
    if action == "download" and source == "youtube":
        playlist_cover_url = (
            metadata.get("cover_url") if isinstance(metadata, dict) else None
        )
        songs = apply_youtube_artwork_choice(
            songs, youtube_artwork, playlist_cover_url
        )
    if action != "retry_track":
        emit("playlist", metadata=metadata, songs=[song_data(song) for song in songs])
    if action == "retry_track":
        track_id = request.get("track_id")
        if not isinstance(track_id, str):
            raise ValueError("Choose a track to retry.")
        song = next((item for item in songs if item.song_id == track_id), None)
        if song is None:
            raise ValueError("The track to retry is not in this playlist.")
        manual_url = validate_youtube_video_url(request.get("manual_url"))
        raw_playlist_path = request.get("playlist_path")
        playlist_to_update = (
            Path(raw_playlist_path).expanduser()
            if isinstance(raw_playlist_path, str) and raw_playlist_path
            else None
        )
        assert destination is not None and isinstance(preset_name, str)
        download(
            [song],
            destination,
            preset_name,
            getattr(song, "list_name", None) or "Playlist Ferry",
            False,
            1,
            {track_id: manual_url},
            playlist_to_update,
        )
        return
    if action == "download":
        assert destination is not None and isinstance(preset_name, str)
        playlist_name = (
            metadata.get("name", "Playlist Ferry")
            if isinstance(metadata, dict)
            else getattr(metadata, "name", "Playlist Ferry")
        )
        manual_urls = validate_manual_urls(
            raw_manual_urls, {song.song_id for song in songs}
        )
        download(
            songs,
            destination,
            preset_name,
            playlist_name,
            create_playlist,
            concurrent_downloads,
            manual_urls,
            playlist_artwork_url=(
                playlist_cover_url
                if youtube_artwork == "both"
                and isinstance(playlist_cover_url, str)
                else None
            ),
        )


def failure_message(error: Exception) -> str:
    """Convert an internal failure into a bounded message useful to the app user."""
    if isinstance(error, ModuleNotFoundError):
        dependency = error.name or "unknown"
        return f"A required download component is missing: {dependency}. Rebuild the app runtime."
    if isinstance(
        error, (ConnectionError, TimeoutError)
    ) or error.__class__.__module__.startswith(("requests", "urllib3")):
        return "Could not connect to the media service. Check your connection and try again."
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
