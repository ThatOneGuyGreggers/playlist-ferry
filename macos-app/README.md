# Playlist Ferry macOS app

This directory contains a SwiftUI front end and a Python worker for public Spotify playlists, YouTube playlists, and direct YouTube video links. YouTube `watch` links that include a `list` parameter resolve the complete playlist. Release 2.0.1 includes its Python runtime and media tools; the debug build uses local development dependencies.

The native interface follows the project-specific [UI design guidance](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/UI_DESIGN), derived from the referenced Apple Human Interface Guidelines summary.

The Python worker uses [spotDL](https://github.com/spotdl/spotify-downloader), distributed under its upstream [MIT license](../spotify-downloader/LICENSE). Interface design draws on [eonist's Apple HIG summary](https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4). See the [project acknowledgments](../README.md#references-and-acknowledgments) for attribution and dependency details.

## Building

Source setup, local test-bundle, portable-release, validation, and signing procedures are maintained in the [Wiki build instructions](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/BUILDING).

## Apple output presets

The app offers bounded output presets instead of exposing raw FFmpeg arguments:

- **Apple Universal:** M4A with AAC at 128 kbps, stereo, and 44.1 kHz. This is the default for iPhone, iPad, and AAC-capable iPod models.
- **iPhone/iPad High Quality:** M4A with AAC at 256 kbps, stereo, and 44.1 kHz. This makes larger files. It cannot restore quality missing from the YouTube source; standard sources are commonly limited to 128 kbps.
- **iPod Legacy AAC:** M4A with AAC at 128 kbps, stereo, and 44.1 kHz, using conservative settings for AAC-capable iPods.
- **Older iPod MP3:** MP3 at 128 kbps, stereo, and 44.1 kHz for broad support in older libraries and devices.

All presets embed spotDL's supported metadata and artwork. ALAC is omitted because converting a lossy YouTube source to lossless audio would increase file size without restoring audio quality.

The **Create Apple Music playlist** option writes an ordered UTF-8 extended M3U (`.m3u8`) file in the destination folder. Its entries use absolute macOS paths so Apple Music can locate and import the downloaded tracks. Existing playlist files are preserved; repeated downloads receive a numbered filename.

The concurrent-download control allows 1–8 tracks to download and convert at once; the default is 3. Higher values can finish large playlists sooner, but consume more network bandwidth, CPU, memory, and temporary disk space.

When automatic matching fails, that track reveals a direct YouTube URL field and a **Re-download** button. Paste a YouTube video, Shorts, or Live URL to retry only that track without processing the full list again. The worker validates and canonicalizes the override, rejects playlists and unknown track IDs, and downloads the exact supplied video instead of searching again.

Before previewing a YouTube playlist or video, the app asks whether to include artwork. For a playlist, accepting embeds each video's individual thumbnail in its audio file and saves the playlist-level thumbnail as a separate JPEG beside the downloads. For a direct video, accepting embeds that video's thumbnail. Declining clears YouTube artwork for the download; Spotify artwork remains unchanged.

The app checks the repository's latest GitHub release when it opens and provides a manual **Check for Updates** control. For a newer semantic version, it selects the matching Intel or Apple Silicon ZIP and offers to download and install it. Installation requires a writable `.app` location and proceeds only after the ZIP's published SHA-256 checksum, bundle identifier, ad hoc code-signature integrity, and executable architecture pass validation. The current app is moved to a temporary backup and restored if replacement validation fails. Because 2.0.0 predates this code, users must install the first updater-enabled release manually; subsequent compatible releases can update in-app.

## Worker protocol

The worker reads one UTF-8 JSON line from stdin and writes newline-delimited JSON events to stdout. Requests have `version: 1`, an `action`, and a public Spotify playlist, YouTube playlist, or direct YouTube video `url`. Full downloads may include the Boolean `create_playlist` option (default `true`), a `youtube_artwork` choice of `video`, `both`, or `none` (default `video`), an integer `concurrent_downloads` from 1–8 (default `3`), and a `manual_urls` object mapping track IDs to direct YouTube videos. The legacy Boolean `youtube_thumbnail` option remains accepted. The `retry_track` action accepts one `track_id` and `manual_url`, downloads only that track, and does not generate another playlist file. Events include `playlist`, `track_started`, `track_complete`, `track_failed`, `complete`, and `error`. A successful full-download `complete` event includes `playlist_path` when a playlist was created and `artwork_path` when playlist artwork was saved. Diagnostics go to stderr. Closing the worker process cancels the active job.
