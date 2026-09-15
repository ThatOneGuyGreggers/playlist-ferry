# UI design guidance

The app's interface follows the Apple Human Interface Guidelines summary in [eonist's HIG reference](https://gist.github.com/eonist/f4ba31012815731284d867232f6c70e4) and treats Apple's current Human Interface Guidelines as the primary source when the two differ.

## Applied principles

- **Clarity:** Use native type styles, plain labels, system symbols, visible units, and concise device-preset descriptions. Put the playlist URL and primary action at the start of the content area.
- **Deference:** Use system colors and controls. Keep settings in a sidebar and leave the main area for the playlist and its tracks.
- **Depth:** Use the split-view hierarchy, grouped form sections, and a grouped playlist input instead of decorative layers.
- **Navigation:** Keep this single-task workflow in a standard `NavigationSplitView`. The sidebar holds persistent download choices; the detail area holds the current playlist.
- **Interaction:** Disable actions until their inputs are ready. Support Return to submit a playlist, Command-Return to preview, Command-D to download, and Escape to cancel.
- **Feedback:** Show an indeterminate progress indicator while loading or downloading, a visible cancel action, per-track state symbols, and completion or error text.
- **Accessibility:** Pair symbols with text, hide decorative symbols from assistive technology, combine each track row into one readable element, support system colors, and avoid color as the only status cue.

## UI structure

The settings sidebar contains the destination, Apple audio preset, and a short source explanation. The detail area contains the Spotify URL, operation feedback, playlist identity, primary download action, and track list. Empty content uses a quiet instructional state rather than disabled controls or sample data.

Future UI changes should preserve this hierarchy unless usability testing supports a change. Test keyboard navigation, VoiceOver labels, light and dark appearances, reduced motion, long playlist and artist names, and the minimum supported window size before release.
