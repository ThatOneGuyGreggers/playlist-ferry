# Native macOS Spotify playlist downloader plan

All implementation and documentation in this workspace must follow [CODING_GUIDELINES.md](CODING_GUIDELINES.md). The root [AGENTS.md](AGENTS.md) makes this an instruction for future coding work.

## Goal

Build a signed, notarized macOS app that accepts a Spotify playlist URL, finds matching YouTube audio through spotDL, and saves tagged audio files to a folder the user chooses. Installing the app must not require Homebrew, Python, FFmpeg, Deno, or command-line setup.

## Starting point

- Upstream source is cloned in [`spotify-downloader`](spotify-downloader/) at commit `cd4a420` (spotDL 4.5.2). This is a shallow clone; fetch more history if development needs it.
- spotDL already implements Spotify playlist/track resolution, YouTube matching through its audio providers, downloading through yt-dlp, metadata and artwork embedding, and playlist sync. The relevant code is in `spotdl/types/playlist.py`, `spotdl/download/downloader.py`, `spotdl/console/download.py`, and `spotdl/console/sync.py`.
- Its Python package requires Python 3.10–3.14 and includes `spotipy`, `spotipyFree`, `ytmusicapi`, `yt-dlp`, and other dependencies in `pyproject.toml`. FFmpeg is required; upstream also strongly recommends Deno for yt-dlp's YouTube support.
- The upstream web UI is limited to individual songs, so it does not meet the playlist-focused native UI goal.

## Proposed architecture

Create a separate SwiftUI macOS target beside the upstream checkout. Keep spotDL as an independently versioned engine rather than rewriting its matching and metadata logic. A small Python worker should expose a stable, newline-delimited JSON protocol over stdin/stdout. Swift launches that worker as a child process, sends playlist/download/cancel requests, and receives structured track and progress events. Keep diagnostics on stderr so they cannot corrupt the protocol.

Use spotDL's Python API inside the worker for playlist resolution and downloading. Avoid parsing its human-oriented console output. Pin spotDL and Python dependency versions; make the worker's protocol the boundary that lets the app update its UI or engine separately. Start with one active playlist job and bounded song concurrency. Persist a job manifest with Spotify track ID, selected YouTube URL, output path, status, and error so interrupted downloads can resume safely.

Bundle an arm64 and x86_64 build (or a tested universal build) of the Python runtime, installed Python packages, FFmpeg/ffprobe, and Deno inside the `.app`. Use build-time downloads with pinned versions and checksums; the installed app must not download dependencies on first launch. Set explicit paths for bundled executables and worker data. Sign nested binaries, enable hardened runtime, notarize the final app, and verify it on clean macOS installations. Check each dependency's distribution license before release and include required notices, including spotDL's MIT notice.

## User flow

1. Paste a public Spotify playlist URL and choose a destination through the macOS folder picker. The app remembers the folder using a security-scoped bookmark where needed.
2. Preview playlist title, artwork, track count, and track list. Show unavailable or unmatched tracks before download when possible.
3. Choose audio format and file naming pattern, then start. Show per-track matching, downloading, conversion, tagging, completed, and failed states, plus total progress and a cancel control.
4. Let the user inspect or change a low-confidence YouTube match before downloading it. Offer retry and "reveal in Finder" for failures and completed files.
5. Save the playlist as a library entry. A later "check for new tracks" action uses spotDL's sync data, with deletion disabled by default and any destructive sync action requiring a clear user choice.

## Spotify access and constraints

Validate public-playlist access through spotDL's current client options. Private playlists or saved-library access require Spotify OAuth and user consent; treat that as a later milestone. Do not embed a reusable Spotify client secret in the app bundle. If official API credentials are needed for a feature, design an appropriate OAuth flow and secure token storage in Keychain before shipping it. Test behavior when Spotify changes API limits or a playlist is unavailable.

Downloading must be limited to material the user is authorized to save and must respect applicable service terms. The app should explain that Spotify supplies track metadata while audio comes from a matched YouTube source, and should never imply the audio was downloaded from Spotify. Match quality and YouTube availability can vary; show the source and make failures actionable.

## Implementation milestones

1. **Engine spike:** Prove playlist URL ingestion, track enumeration, candidate match, one download, tagging, cancellation, and structured progress in a standalone Python worker. Confirm how spotDL locates bundled FFmpeg and Deno.
2. **Native shell:** Add SwiftUI URL input, destination picker, playlist preview, queue, per-track status, settings, and error presentation. Define and version the worker protocol.
3. **Resilience:** Add persisted jobs, restart/resume, duplicate-file handling, retries with backoff, network-loss behavior, conservative sync, and logs with tokens or personal data redacted.
4. **Distribution:** Build both Mac architectures, bundle and sign all dependencies, include license notices, notarize, produce a DMG, and test drag-to-Applications installation on clean machines without developer tools.

## Release acceptance checks

- On a clean supported Mac, installing the DMG and opening the app requires no terminal commands or separate dependency installs.
- A public playlist can be previewed and downloaded to a chosen folder, with artwork and track metadata in the resulting files.
- Unmatched, unavailable, age-restricted, rate-limited, and failed tracks have clear states and retry options; one failure does not stop the entire playlist.
- Cancel stops active work promptly, and relaunch resumes without redownloading completed tracks.
- The app works on supported Apple Silicon and Intel Macs, passes Gatekeeper, and its nested executables are signed and notarized.

## First development decisions

Choose the minimum macOS version and output formats, then prototype the Python worker against the cloned revision. For the first release, use public playlist URLs, MP3 and M4A output, manual sync, and no account login. Expand scope only after the packaged end-to-end path works reliably.

## Current prototype status

The source prototype lives in [`macos-app`](macos-app/) and targets macOS 13 or later. It has a SwiftUI playlist screen and a versioned Python worker for preview and sequential downloads. Apple-focused presets cover modern iPhone and iPad use, AAC-capable iPods, and older MP3-focused iPods with bounded codec, bitrate, channel, and sample-rate settings. The worker reports per-track success or failure. A local x86_64 debug `.app` has been built and launched; see its README for build steps. Live Spotify and YouTube integration, bundled dependencies, resume, match review, release signing, and notarization remain unverified or unfinished.
