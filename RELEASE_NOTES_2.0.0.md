# Playlist Ferry 2.0.0

Playlist Ferry 2.0.0 expands the app beyond Spotify playlist matching and adds a complete playlist-repair workflow.

## What's new

- Preview and download public YouTube playlists, individual videos, Shorts, and Live links.
- Download exact YouTube sources without rematching them by title.
- Export ordered, UTF-8 Apple Music-compatible `.m3u8` playlists.
- Enable or disable Apple Music playlist generation before downloading.
- Choose between 1 and 8 concurrent downloads; the default is 3.
- See per-track download progress and isolated failures during concurrent jobs.
- When automatic Spotify matching fails, provide a direct YouTube link and re-download only that track.
- Automatically repair the existing Apple Music playlist after a successful manual track retry.

## Reliability and safety

- Strict Spotify and YouTube URL validation rejects lookalike domains, credentials, ports, playlists used as manual track matches, and unknown track IDs.
- Manual retry paths are restricted to the selected destination folder.
- Apple Music playlist repairs are atomic and preserve original track order.
- The local debug launcher now handles virtual-environment Python symlinks and explicitly discovers Homebrew FFmpeg, FFprobe, and Node installations.
- Worker responses, request sizes, playlist sizes, concurrency, and error messages remain bounded.

## Compatibility

- macOS 13 or newer.
- Native Intel and Apple Silicon release artifacts are produced separately.
- Release builds bundle Python, FFmpeg, FFprobe, and Deno.
- Builds are ad hoc signed and are not notarized; macOS may require manual approval in Privacy & Security.
