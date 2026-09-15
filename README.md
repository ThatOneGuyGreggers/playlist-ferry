# Spotify Playlist Downloader for macOS

A SwiftUI app and Python worker for previewing public Spotify playlists and downloading matching audio through spotDL. It offers Apple device audio presets, track status, destination selection, and cancellation.

This is a development prototype. The local test app is ad hoc signed and still needs a Python environment, FFmpeg, and Deno. It is not a portable installer or a notarized release.

## Get started

Clone this repository with its pinned spotDL dependency:

```sh
git clone --recurse-submodules https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader.git
cd Spotify-PlayList-YouTube-downloader
```

For an existing clone, run `git submodule update --init --recursive`.

Follow the [app setup and build instructions](macos-app/README.md) to run from source or create a local test bundle. See the [development plan](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/MACOS_APP_PLAN) for remaining work and the [changelog](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/CHANGELOG) for changes.

Project documentation lives in the [Wiki](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki). Development work follows the [project instructions](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/AGENTS) and [coding guidelines](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/CODING_GUIDELINES). The Wiki also contains the [code review](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/CODE_REVIEW).

## References and acknowledgments

- [spotDL / spotify-downloader](https://github.com/spotdl/spotify-downloader), by the spotDL developers, provides playlist metadata, audio matching, downloading, and metadata embedding. The `spotify-downloader` submodule pins commit `cd4a4203f5b12bd6dbbdf22d7674807858d35e05`. Its source retains the upstream [MIT license and copyright notice](spotify-downloader/LICENSE). This app is an independent project and is not an official spotDL release.
- [Apple Human Interface Guidelines summary](https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4), by eonist, informed the native interface design. It is a community summary; [Apple's Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines) are the primary design reference. The [UI design guidance](https://github.com/ThatOneGuyGreggers/Spotify-PlayList-YouTube-downloader/wiki/UI_DESIGN) records how these principles apply to this app.

These references credit the software dependency and design guidance; they do not imply endorsement. This project's original app code uses the [MIT license](LICENSE). Third-party software retains its own license and copyright notices.
