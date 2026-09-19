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

private enum YouTubeArtworkChoice: String {
    case video
    case both
    case none
}

struct ContentView: View {
    @StateObject private var worker = WorkerManager()
    @State private var playlistURL = ""
    @State private var destination: URL?
    @State private var preset = AudioPreset.appleUniversal
    @State private var createAppleMusicPlaylist = true
    @State private var concurrentDownloads = 3
    @State private var youtubeArtwork = YouTubeArtworkChoice.video
    @State private var showYouTubeThumbnailPrompt = false
    @State private var youtubeURLIsPlaylist = false

    var body: some View {
        NavigationSplitView {
            settingsSidebar
                .navigationSplitViewColumnWidth(min: 250, ideal: 280, max: 340)
        } detail: {
            mainContent
                .navigationTitle(worker.playlist?.name ?? "Playlist Ferry")
                .toolbar { toolbarContent }
        }
        .frame(minWidth: 820, minHeight: 560)
        .alert("Choose YouTube artwork", isPresented: $showYouTubeThumbnailPrompt) {
            Button(youtubeURLIsPlaylist ? "Include Track + Playlist Artwork" : "Include Thumbnail") {
                youtubeArtwork = youtubeURLIsPlaylist ? .both : .video
                previewSelectedURL()
            }
            Button("Skip Artwork") {
                youtubeArtwork = .none
                previewSelectedURL()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(youtubeURLIsPlaylist
                 ? "Embed each video's thumbnail and save the playlist thumbnail as a separate JPEG, or leave artwork unset."
                 : "Choose whether to embed the video's thumbnail as audio artwork.")
        }
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
                Stepper("Concurrent downloads: \(concurrentDownloads)", value: $concurrentDownloads, in: 1...8)
                Text("Higher values finish sooner but use more bandwidth and processing power.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Toggle("Create Apple Music playlist", isOn: $createAppleMusicPlaylist)
                Text("Creates an importable .m3u8 playlist beside the downloaded tracks.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Source") {
                Label("Spotify playlists", systemImage: "music.note.list")
                Label("YouTube playlists and videos", systemImage: "play.rectangle")
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
                TextField("Spotify or YouTube URL", text: $playlistURL)
                    .textFieldStyle(.plain)
                    .onSubmit(previewPlaylist)
                    .accessibilityHint("Enter a public Spotify playlist, YouTube playlist, or YouTube video link")
                Button("Preview", action: previewPlaylist)
                    .buttonStyle(.borderedProminent)
                    .disabled(!canPreview)
                    .keyboardShortcut(.return, modifiers: [.command])
            }
            .padding(6)
        } label: {
            Label("Playlist or Video", systemImage: "music.note")
        }
    }

    @ViewBuilder
    private var feedback: some View {
        if worker.busy {
            HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text(worker.tracks.isEmpty ? "Loading source…" : "Downloading…")
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
                    Label("Download", systemImage: "arrow.down.circle.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!canDownload)
                .keyboardShortcut("d", modifiers: [.command])
            }

            List(worker.tracks) { track in
                TrackRow(
                    track: track,
                    status: worker.statuses[track.id],
                    manualURL: Binding(
                        get: { worker.manualURL(for: track.id) },
                        set: { worker.setManualURL($0, for: track.id) }
                    ),
                    canRetry: destination != nil && !worker.busy,
                    retry: { retryTrack(track) }
                )
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
            Text("Add a playlist or video").font(.title2).fontWeight(.semibold)
            Text("Paste a public Spotify playlist or YouTube link above to review it before downloading.")
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
            .help("Reload the playlist or video")

            Button(action: startDownload) {
                Label("Download", systemImage: "arrow.down.circle")
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
            && worker.previewedURL == playlistURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func previewPlaylist() {
        guard canPreview else { return }
        let url = playlistURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if isYouTubeURL(url) {
            youtubeURLIsPlaylist = isYouTubePlaylistURL(url)
            showYouTubeThumbnailPrompt = true
        } else {
            youtubeArtwork = .video
            worker.preview(url: url)
        }
    }

    private func previewSelectedURL() {
        guard canPreview else { return }
        worker.preview(url: playlistURL.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private func isYouTubeURL(_ value: String) -> Bool {
        guard let host = URLComponents(string: value)?.host?.lowercased() else {
            return false
        }
        return [
            "youtu.be", "youtube.com", "www.youtube.com",
            "m.youtube.com", "music.youtube.com",
        ].contains(host)
    }

    private func isYouTubePlaylistURL(_ value: String) -> Bool {
        guard let components = URLComponents(string: value) else { return false }
        return components.path == "/playlist"
            || components.queryItems?.contains(where: { $0.name == "list" && !($0.value ?? "").isEmpty }) == true
    }

    private func startDownload() {
        guard canDownload, let destination else { return }
        worker.download(
            url: playlistURL.trimmingCharacters(in: .whitespacesAndNewlines),
            destination: destination,
            preset: preset.rawValue,
            createPlaylist: createAppleMusicPlaylist,
            concurrentDownloads: concurrentDownloads,
            youtubeArtwork: youtubeArtwork.rawValue,
            manualURLs: worker.manualURLs
        )
    }

    private func retryTrack(_ track: Track) {
        guard let destination else { return }
        let url = worker.manualURL(for: track.id)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty else { return }
        worker.retryTrack(
            track.id,
            url: url,
            destination: destination,
            preset: preset.rawValue
        )
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.title = "Choose where to save these tracks"
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
    @Binding var manualURL: String
    let canRetry: Bool
    let retry: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Text("\(track.position ?? 0)")
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .frame(width: 28, alignment: .trailing)
            VStack(alignment: .leading, spacing: 5) {
                Text(track.name).lineLimit(1)
                Text(track.artists.joined(separator: ", "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                if status?.hasPrefix("Failed") == true {
                    HStack {
                        TextField("Direct YouTube URL", text: $manualURL)
                            .textFieldStyle(.roundedBorder)
                            .font(.caption)
                            .accessibilityLabel("Manual YouTube match for \(track.name)")
                        Button("Re-download", action: retry)
                            .disabled(
                                !canRetry
                                    || manualURL.trimmingCharacters(
                                        in: .whitespacesAndNewlines
                                    ).isEmpty
                            )
                    }
                }
            }
            Spacer()
            Text(durationText).font(.caption).monospacedDigit().foregroundStyle(.secondary)
            Label(status ?? "Ready", systemImage: statusSymbol)
                .font(.caption)
                .foregroundStyle(statusColor)
                .frame(minWidth: 90, alignment: .leading)
        }
        .padding(.vertical, 3)
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
