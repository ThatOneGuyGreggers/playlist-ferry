import Foundation

struct Track: Decodable, Identifiable {
    let id: String
    let name: String
    let artists: [String]
    let duration: Int
    let position: Int?
}

struct PlaylistMetadata: Decodable {
    let name: String
    let author_name: String
    let description: String?
}

private struct WorkerEvent: Decodable {
    let event: String
    let message: String?
    let id: String?
    let path: String?
    let failed: Int?
    let metadata: PlaylistMetadata?
    let songs: [Track]?
}

@MainActor
final class WorkerManager: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var playlist: PlaylistMetadata?
    @Published private(set) var tracks: [Track] = []
    @Published private(set) var statuses: [String: String] = [:]
    @Published private(set) var message: String?

    private var process: Process?

    func preview(url: String) {
        start(["version": 1, "action": "preview", "url": url])
    }

    func download(url: String, destination: URL, preset: String) {
        start([
            "version": 1, "action": "download", "url": url,
            "destination": destination.path, "preset": preset,
        ])
    }

    func cancel() {
        process?.terminate()
        process = nil
        busy = false
        message = "Canceled."
    }

    private func start(_ request: [String: Any]) {
        guard !busy else { return }
        message = nil
        busy = true

        // Development uses the checkout; distribution will resolve bundled resources.
        let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let script = root.appendingPathComponent("macos-app/worker/worker.py")
        let bundledScript = Bundle.main.resourceURL?.appendingPathComponent("worker.py")
        let workerScript = bundledScript.flatMap {
            FileManager.default.fileExists(atPath: $0.path) ? $0 : nil
        } ?? script
        guard FileManager.default.fileExists(atPath: workerScript.path) else {
            message = "Worker script is missing. Run the app from the project root."
            busy = false
            return
        }
        let bundledPython = Bundle.main.resourceURL?.appendingPathComponent("python/bin/python3")
        let developmentPython = root.appendingPathComponent("macos-app/.venv/bin/python")
        let packagedDevelopmentPython = Bundle.main.resourceURL?
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(".venv/bin/python")
        let pythonCandidates = [bundledPython, packagedDevelopmentPython, developmentPython]
            .compactMap { $0 }
        guard let python = pythonCandidates.first(where: {
            FileManager.default.isExecutableFile(atPath: $0.path)
        }) else {
            message = "The app runtime is missing. Rebuild the test app after installing its dependencies."
            busy = false
            return
        }

        do {
            let input = Pipe()
            let output = Pipe()
            let task = Process()
            task.executableURL = python
            task.arguments = [workerScript.path]
            if let resources = Bundle.main.resourceURL,
               FileManager.default.fileExists(
                   atPath: resources.appendingPathComponent("spotify-downloader/spotdl").path
               ) {
                var environment = ProcessInfo.processInfo.environment
                environment["SPOTDL_SOURCE_ROOT"] = resources
                    .appendingPathComponent("spotify-downloader").path
                task.environment = environment
            }
            task.standardInput = input
            task.standardOutput = output
            task.standardError = FileHandle.standardError
            let data = try JSONSerialization.data(withJSONObject: request)
            try task.run()
            process = task
            input.fileHandleForWriting.write(data + Data([0x0A]))
            try? input.fileHandleForWriting.close()

            // Read complete lines off the main thread so the interface remains responsive.
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let handle = output.fileHandleForReading
                var buffer = Data()
                while true {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    buffer.append(chunk)
                    while let newline = buffer.firstIndex(of: 0x0A) {
                        let line = Data(buffer[..<newline])
                        buffer.removeSubrange(...newline)
                        guard let event = try? JSONDecoder().decode(WorkerEvent.self, from: line) else {
                            continue
                        }
                        DispatchQueue.main.async { self?.apply(event) }
                    }
                }
                task.waitUntilExit()
                DispatchQueue.main.async {
                    guard self?.process === task else { return }
                    if task.terminationStatus != 0 && self?.message == nil {
                        self?.message = "Worker stopped unexpectedly. Check its log."
                    }
                    self?.process = nil
                    self?.busy = false
                }
            }
        } catch {
            message = "Could not start the worker: \(error.localizedDescription)"
            busy = false
        }
    }

    private func apply(_ event: WorkerEvent) {
        switch event.event {
        case "playlist":
            playlist = event.metadata
            tracks = event.songs ?? []
            statuses = [:]
        case "track_started":
            if let id = event.id { statuses[id] = "Downloading" }
        case "track_complete":
            if let id = event.id { statuses[id] = "Saved" }
        case "track_failed":
            if let id = event.id { statuses[id] = "Failed: \(event.message ?? "Unknown error")" }
        case "complete":
            message = "Finished with \(event.failed ?? 0) failed tracks."
        case "error":
            message = event.message ?? "The worker reported an error."
        default:
            message = "The worker sent an unknown event."
        }
    }
}
