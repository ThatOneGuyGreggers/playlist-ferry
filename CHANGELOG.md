# Changelog

## 2026-09-14

- Preserved the MIT license selected in the GitHub repository and updated the README to distinguish the app license from upstream notices. LLM: Model not disclosed.

- Added the GitHub destination to the clone instructions and prepared the source for upload to the private repository. LLM: Model not disclosed.

- Prepared GitHub publication with a project README, explicit spotDL and eonist HIG references, a pinned upstream submodule, and exclusions for local environments and build output. LLM: Model not disclosed.

## 2025-01-15

# Changelog

## 2026-09-14

- Updated the test-app packaging script to clear Finder metadata before code signing, preventing local launches from leaving a bundle that fails strict signature verification. LLM: GPT-5 (Codex).
- Confirmed the repaired worker uses spotDL 4.5.2 from the cloned checkout, loads current public Spotify playlist metadata, and reports actionable failures in the native interface. LLM: GPT-5 (Codex).
- Recorded the latest UI, audio-preset, runtime, playlist-preview, testing, and packaging work in this changelog so the current prototype state is documented. LLM: GPT-5 (Codex).

- Fixed public playlist preview by installing the checkout's dependencies in `macos-app/.venv` and making the packaged test app prefer that known runtime instead of an unrelated system spotDL installation. LLM: GPT-5 (Codex).
- Replaced the generic worker-log failure with bounded dependency, connection, and upstream error details in the UI, then verified a 50-track public Spotify playlist loads through the worker. LLM: GPT-5 (Codex).

- Redesigned the SwiftUI interface around the referenced Apple HIG principles with a standard settings sidebar, focused playlist detail view, system controls and symbols, clear loading and track states, keyboard shortcuts, and accessibility labels. LLM: GPT-5 (Codex).
- Added UI design guidance that records how clarity, deference, depth, navigation, interaction, feedback, and accessibility apply to this app. LLM: GPT-5 (Codex).

- Added Apple Universal, iPhone/iPad high-quality, iPod legacy AAC, and older-iPod MP3 output presets with explicit format, bitrate, stereo, and 44.1 kHz settings so users can target Apple device compatibility without entering FFmpeg arguments. LLM: GPT-5 (Codex).
- Rebuilt and validated the ad hoc signed x86_64 test app after adding Apple output controls, and expanded worker tests to reject unknown presets. LLM: GPT-5 (Codex).

- Built and launched an x86_64 macOS debug app, fixed unsupported macOS 13 window modifiers, and added a repeatable local bundle script so the native shell can be tested in Finder. LLM: GPT-5 (Codex).
- Documented that the test bundle still lacks packaged Python, Python packages, FFmpeg, and Deno so its current limits are clear. LLM: GPT-5 (Codex).

- Replaced Gemma-4's mock playlist display with a SwiftUI view connected to a one-request Python worker; added playlist preview, destination selection, MP3/M4A download, track status, and cancellation to establish a working end-to-end development slice. LLM: GPT-5 (Codex).
- Added a Swift package manifest, worker setup requirements, and prototype run instructions so the app can be built and its remaining packaging work is explicit. LLM: GPT-5 (Codex).
- Added worker protocol tests for invalid requests and marked prototype progress in the plan to keep implementation status clear. LLM: GPT-5 (Codex).

- Cloned spotDL and wrote the native macOS app plan to define the first implementation milestones. LLM: GPT-5 (Codex).
- Added the supplied coding guidelines to the workspace and linked them from `AGENTS.md` and the app plan so future work follows them. LLM: GPT-5 (Codex).
- Required dated changelog entries that record meaningful changes, their reason, and the LLM used. LLM: GPT-5 (Codex).
- Created the macOS app directory structure, including a Swift target directory and a Python worker directory. LLM: gemma-4-12b-it-qat
- Initialized a Python worker script to handle communication with the Swift frontend via a newline-delimited JSON protocol over stdin/stdout. LLM: gemma-4-12b-it-qat
- Created a basic SwiftUI project structure with a `ContentView` and a `WorkerManager` to handle worker communication. LLM: gemma-4-12b-it-qat
- Defined a `requirements.txt` for the Python worker dependencies. LLM: gemma-4-12b-it-qat
