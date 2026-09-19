# Playlist Ferry for macOS

A SwiftUI app and Python worker for previewing public Spotify playlists, YouTube playlists, and individual YouTube videos. Spotify tracks are matched to audio through spotDL; YouTube sources download their exact linked videos. It offers Apple device audio presets, track status, destination selection, and cancellation.

Version 2.0.0 adds direct YouTube videos and playlists, Apple Music-compatible playlist exports, configurable concurrent downloads, and per-track manual YouTube repair. Release bundles include Python, FFmpeg, FFprobe, and Deno and are tested on Intel and Apple Silicon. They are ad hoc signed, so macOS may require manual approval in Privacy & Security.

Project documentation lives in the [Wiki](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki), including [build instructions](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/BUILDING), the [development plan](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/MACOS_APP_PLAN), [changelog](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/CHANGELOG), and [code review](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/CODE_REVIEW).

## References and acknowledgments

- [spotDL / spotify-downloader](https://github.com/spotdl/spotify-downloader), by the spotDL developers, provides playlist metadata, audio matching, downloading, and metadata embedding. The `spotify-downloader` submodule pins commit `cd4a4203f5b12bd6dbbdf22d7674807858d35e05`. Its source retains the upstream [MIT license and copyright notice](spotify-downloader/LICENSE). This app is an independent project and is not an official spotDL release.
- [Apple Human Interface Guidelines summary](https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4), by eonist, informed the native interface design. It is a community summary; [Apple's Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines) are the primary design reference. The [UI design guidance](https://github.com/ThatOneGuyGreggers/playlist-ferry/wiki/UI_DESIGN) records how these principles apply to this app.

These references credit the software dependency and design guidance; they do not imply endorsement. This project's original app code uses the [MIT license](LICENSE). Third-party software retains its own license and copyright notices.
