import AppKit
import SwiftUI

private enum AudioPreset: String, CaseIterable, Identifiable {
    case appleUniversal = "apple-universal"
    case appleHighQuality = "apple-high-quality"
    case iPodLegacyAAC = "ipod-legacy-aac"
    case iPodLegacyMP3 = "ipod-legacy-mp3"

    var id: String { rawValue }

    var name: String {
        switch self {
        case .appleUniversal: return "Apple Universal"
        case .appleHighQuality: return "iPhone & iPad High Quality"
        case .iPodLegacyAAC: return "iPod Legacy AAC"
        case .iPodLegacyMP3: return "Older iPod MP3"
        }
    }

    var specification: String {
        switch self {
        case .appleUniversal: return "AAC · 128 kbps · 44.1 kHz"
        case .appleHighQuality: return "AAC · 256 kbps · 44.1 kHz"
        case .iPodLegacyAAC: return "AAC · 128 kbps · 44.1 kHz"
        case .iPodLegacyMP3: return "MP3 · 128 kbps · 44.1 kHz"
        }
    }

    var detail: String {
        switch self {
        case .appleUniversal:
            return "Recommended for iPhone, iPad, and AAC-capable iPods."
        case .appleHighQuality:
            return "Larger files for modern devices. Source quality may be lower."
        case .iPodLegacyAAC:
            return "Conservative AAC settings for compatible iPod models."
        case .iPodLegacyMP3:
            return "Broad support for early or MP3-focused iPod libraries."
        }
    }
}

struct ContentView: View {
    @StateObject private var worker = WorkerManager()
    @State private var playlistURL = ""
    @State private var destination: URL?
    @State private var preset = AudioPreset.appleUniversal

    var body: some View {
        NavigationSplitView {
            settingsSidebar
                .navigationSplitViewColumnWidth(min: 250, ideal: 280, max: 340)
        } detail: {
            mainContent
                .navigationTitle(worker.playlist?.name ?? "Playlist Downloader")
                .toolbar { toolbarContent }
        }
        .frame(minWidth: 820, minHeight: 560)
    }

    private var settingsSidebar: some View {
        Form {
            Section("Save Location") {
                Button(action: chooseFolder) {
                    Label("Choose Folder…", systemImage: "folder")
                }
                Text(destination?.path ?? "No folder selected")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .accessibilityLabel("Save location")
                    .accessibilityValue(destination?.path ?? "No folder selected")
            }

            Section("Audio for Apple Devices") {
                Picker("Preset", selection: $preset) {
                    ForEach(AudioPreset.allCases) { option in
                        Text(option.name).tag(option)
                    }
                }
                .labelsHidden()
                Text(preset.specification).font(.callout).fontWeight(.medium)
                Text(preset.detail).font(.caption).foregroundStyle(.secondary)
            }

            Section("Source") {
                Label("Track details from Spotify", systemImage: "music.note.list")
                Label("Matched audio from YouTube", systemImage: "play.rectangle")
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .formStyle(.grouped)
        .navigationTitle("Download Settings")
    }

    private var mainContent: some View {
        VStack(alignment: .leading, spacing: 18) {
            playlistInput
            feedback
            if let playlist = worker.playlist {
                playlistView(playlist)
            } else {
                emptyState
            }
        }
        .padding(24)
    }

    private var playlistInput: some View {
        GroupBox {
            HStack(spacing: 10) {
                Image(systemName: "link")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                TextField("Spotify playlist URL", text: $playlistURL)
                    .textFieldStyle(.plain)
                    .onSubmit(previewPlaylist)
                    .accessibilityHint("Enter a public Spotify playlist link")
                Button("Preview", action: previewPlaylist)
                    .buttonStyle(.borderedProminent)
                    .disabled(!canPreview)
                    .keyboardShortcut(.return, modifiers: [.command])
            }
            .padding(6)
        } label: {
            Label("Spotify Playlist", systemImage: "music.note")
        }
    }

    @ViewBuilder
    private var feedback: some View {
        if worker.busy {
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text(worker.tracks.isEmpty ? "Loading playlist…" : "Downloading playlist…")
                Spacer()
                Button("Cancel", role: .cancel) { worker.cancel() }
                    .keyboardShortcut(.cancelAction)
            }
            .accessibilityElement(children: .combine)
        } else if let message = worker.message {
            Label(message, systemImage: "info.circle")
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    private func playlistView(_ playlist: PlaylistMetadata) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(playlist.name).font(.title2).fontWeight(.semibold)
                    Text("By \(playlist.author_name) · \(worker.tracks.count) tracks")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(action: startDownload) {
                    Label("Download Playlist", systemImage: "arrow.down.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!canDownload)
                .keyboardShortcut("d", modifiers: [.command])
            }

            List(worker.tracks) { track in
                TrackRow(track: track, status: worker.statuses[track.id])
            }
            .listStyle(.inset)
            .overlay {
                if worker.tracks.isEmpty {
                    Text("This playlist has no downloadable tracks.")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "music.note.list")
                .font(.system(size: 44, weight: .light))
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text("Add a Spotify playlist").font(.title2).fontWeight(.semibold)
            Text("Paste a public playlist link above to review its tracks before downloading.")
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 390)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup {
            Button(action: previewPlaylist) {
                Label("Refresh Playlist", systemImage: "arrow.clockwise")
            }
            .disabled(!canPreview)
            .help("Reload the playlist from Spotify")

            Button(action: startDownload) {
                Label("Download Playlist", systemImage: "arrow.down.circle")
            }
            .disabled(!canDownload)
            .help("Download all tracks with the selected audio preset")
        }
    }

    private var canPreview: Bool {
        !worker.busy && !playlistURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var canDownload: Bool {
        !worker.busy && destination != nil && !worker.tracks.isEmpty
    }

    private func previewPlaylist() {
        guard canPreview else { return }
        worker.preview(url: playlistURL.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private func startDownload() {
        guard canDownload, let destination else { return }
        worker.download(
            url: playlistURL.trimmingCharacters(in: .whitespacesAndNewlines),
            destination: destination,
            preset: preset.rawValue
        )
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.title = "Choose where to save this playlist"
        panel.prompt = "Choose"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK { destination = panel.url }
    }
}

private struct TrackRow: View {
    let track: Track
    let status: String?

    var body: some View {
        HStack(spacing: 12) {
            Text("\(track.position ?? 0)")
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .frame(width: 28, alignment: .trailing)
            VStack(alignment: .leading, spacing: 2) {
                Text(track.name).lineLimit(1)
                Text(track.artists.joined(separator: ", "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Text(durationText).font(.caption).monospacedDigit().foregroundStyle(.secondary)
            Label(status ?? "Ready", systemImage: statusSymbol)
                .font(.caption)
                .foregroundStyle(statusColor)
                .frame(minWidth: 90, alignment: .leading)
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
    }

    private var durationText: String {
        String(format: "%d:%02d", track.duration / 60, track.duration % 60)
    }

    private var statusSymbol: String {
        guard let status else { return "circle" }
        if status == "Downloading" { return "arrow.down.circle" }
        if status == "Saved" { return "checkmark.circle.fill" }
        if status.hasPrefix("Failed") { return "exclamationmark.triangle.fill" }
        return "circle"
    }

    private var statusColor: Color {
        guard let status else { return .secondary }
        if status == "Saved" { return .green }
        if status.hasPrefix("Failed") { return .red }
        return .secondary
    }
}
