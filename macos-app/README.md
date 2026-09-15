# macOS app prototype

This directory contains a SwiftUI front end and a Python worker for public Spotify playlists. A local debug `.app` can be built, but it is not yet a dependency-free distribution build.

The native interface follows the project-specific [UI design guidance](UI_DESIGN.md), derived from the referenced Apple Human Interface Guidelines summary.

The Python worker uses [spotDL](https://github.com/spotdl/spotify-downloader), distributed under its upstream [MIT license](../spotify-downloader/LICENSE). Interface design draws on [eonist's Apple HIG summary](https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4). See the [project acknowledgments](../README.md#references-and-acknowledgments) for attribution and dependency details. Initialize the dependency with `git submodule update --init --recursive` before following the instructions below.

## Test build

From the project root on a Mac with Swift Command Line Tools:

```sh
swift build --package-path macos-app --scratch-path /tmp/spotify-swift-build -j 1 \
  -Xswiftc -module-cache-path -Xswiftc /tmp/spotify-swift-modules
macos-app/scripts/package-test-app.sh \
  /tmp/spotify-swift-build/x86_64-apple-macosx/debug/SpotifyPlaylistDownloader
open 'macos-app/dist/Spotify Playlist Downloader.app'
```

The resulting bundle is ad hoc signed for local testing. This build is x86_64 because it was compiled on an Intel Mac; an Apple Silicon build needs a build on that target or a universal build process. The bundle includes the Swift UI, worker script, and spotDL source. On this development machine it uses `macos-app/.venv`, and public playlist preview has been verified. It does not yet bundle that Python runtime, FFmpeg, or Deno, so it is not portable and downloads still require those tools. Do not treat this debug build as an installer or a notarized release.

If a worker request fails, the app now shows a bounded description of the actual error. Missing dependencies name the missing component, and connection failures ask the user to check network access. Detailed Python diagnostics remain off the JSON protocol on stderr.

## Run from source

On a Mac with Xcode or Command Line Tools and Python 3.10–3.14:

```sh
cd macos-app
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd ..
swift run --package-path macos-app SpotifyPlaylistDownloader
```

The Swift target uses `macos-app/.venv/bin/python` when run from the project root, then falls back to `/usr/bin/python3`. FFmpeg is also required for downloads; distribution will bundle it and Deno. The UI currently previews a playlist and downloads songs in order, with per-track status and cancellation by stopping the worker process. Packaging, resume, match review, and release signing remain to be built.

## Apple output presets

The app offers bounded output presets instead of exposing raw FFmpeg arguments:

- **Apple Universal:** M4A with AAC at 128 kbps, stereo, and 44.1 kHz. This is the default for iPhone, iPad, and AAC-capable iPod models.
- **iPhone/iPad High Quality:** M4A with AAC at 256 kbps, stereo, and 44.1 kHz. This makes larger files. It cannot restore quality missing from the YouTube source; standard sources are commonly limited to 128 kbps.
- **iPod Legacy AAC:** M4A with AAC at 128 kbps, stereo, and 44.1 kHz, using conservative settings for AAC-capable iPods.
- **Older iPod MP3:** MP3 at 128 kbps, stereo, and 44.1 kHz for broad support in older libraries and devices.

All presets embed spotDL's supported metadata and artwork. ALAC is omitted because converting a lossy YouTube source to lossless audio would increase file size without restoring audio quality.

## Worker protocol

The worker reads one UTF-8 JSON line from stdin and writes newline-delimited JSON events to stdout. Requests have `version: 1`, `action: "preview"` or `"download"`, and a public Spotify playlist `url`. Download requests also need an existing `destination` directory and a supported `preset` identifier. Events include `playlist`, `track_started`, `track_complete`, `track_failed`, `complete`, and `error`. Diagnostics go to stderr. Closing the worker process cancels the active job.
