import Foundation
import Combine
import Darwin

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

// Retain only a bounded diagnostic tail while continuously draining stderr.
private final class WorkerDiagnostics: @unchecked Sendable {
    private let lock = NSLock()
    private var tail = Data()

    func append(_ data: Data) {
        lock.lock()
        defer { lock.unlock() }
        tail.append(data)
        if tail.count > 8_192 { tail = Data(tail.suffix(8_192)) }
    }

    var summary: String {
        lock.lock()
        defer { lock.unlock() }
        return String(decoding: tail.suffix(500), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

@MainActor
final class WorkerManager: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var playlist: PlaylistMetadata?
    @Published private(set) var previewedURL: String?
    @Published private(set) var tracks: [Track] = []
    @Published private(set) var statuses: [String: String] = [:]
    @Published private(set) var message: String?

    private var process: Process?
    private var deadline: DispatchWorkItem?
    private let testRuntime: (URL, URL)?

    init(python: URL? = nil, script: URL? = nil) {
        if let python, let script { testRuntime = (python, script) }
        else { testRuntime = nil }
    }

    func preview(url: String) {
        guard !busy else { return }
        playlist = nil
        previewedURL = nil
        tracks = []
        statuses = [:]
        start(["version": 1, "action": "preview", "url": url])
    }

    func download(url: String, destination: URL, preset: String) {
        guard !busy else { return }
        guard previewedURL == url else {
            message = "Preview this playlist before downloading."
            return
        }
        statuses = [:]
        start(["version": 1, "action": "download", "url": url,
               "destination": destination.path, "preset": preset])
    }

    func cancel() {
        deadline?.cancel()
        if let task = process { Self.stop(task) }
        process = nil
        busy = false
        message = "Canceled."
    }

    nonisolated private static func stop(_ task: Process) {
        guard task.isRunning else { return }
        let pid = task.processIdentifier
        // The Python worker creates its own group; handle the startup race too.
        if kill(-pid, SIGTERM) != 0 { task.terminate() }
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + 2) {
            if task.isRunning {
                _ = kill(-pid, SIGKILL)
                _ = kill(pid, SIGKILL)
            }
        }
    }

    private func start(_ request: [String: Any]) {
        guard !busy else { return }
        message = nil
        do {
            if let (python, script) = testRuntime {
                try launch(request, python: python, script: script, bundled: false)
                return
            }
            let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            let resources = Bundle.main.resourceURL
            let bundledScript = resources?.appendingPathComponent("worker.py")
            let isBundled = bundledScript.map { FileManager.default.fileExists(atPath: $0.path) } ?? false
            let script = isBundled ? bundledScript! : root.appendingPathComponent("macos-app/worker/worker.py")
            let bundledPython = resources?.appendingPathComponent("python/bin/python3")
            let developmentPython = root.appendingPathComponent("macos-app/.venv/bin/python")
            let testPython = resources?.deletingLastPathComponent().deletingLastPathComponent()
                .deletingLastPathComponent().appendingPathComponent(".venv/bin/python")
            let isTestBundle = Bundle.main.bundleIdentifier?.hasSuffix(".test") == true
            let candidates = isBundled && !isTestBundle ? [bundledPython] : [bundledPython, testPython, developmentPython]
            guard FileManager.default.fileExists(atPath: script.path),
                  let python = candidates.compactMap({ $0 }).first(where: {
                      FileManager.default.isExecutableFile(atPath: $0.path)
                  }) else {
                message = "The app runtime is missing. Reinstall Playlist Ferry or set up the development environment."
                return
            }
            try launch(request, python: python, script: script, bundled: isBundled && !isTestBundle)
        } catch {
            message = "Could not start the worker: \(error.localizedDescription)"
            process = nil
            busy = false
        }
    }

    private func launch(_ request: [String: Any], python: URL, script: URL, bundled: Bool) throws {
        let data = try JSONSerialization.data(withJSONObject: request)
        guard data.count <= 16_384 else {
            message = "The playlist request is too large."
            return
        }
        let input = Pipe(), output = Pipe(), errors = Pipe()
        let task = Process()
        let diagnostics = WorkerDiagnostics()
        task.executableURL = python
        task.arguments = ["-I", "-B", script.path]
        var environment = ProcessInfo.processInfo.environment
        for name in ["PYTHONPATH", "PYTHONHOME", "DYLD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "SPOTDL_SOURCE_ROOT", "SPOTDL_FFMPEG", "PLAYLIST_FERRY_BUNDLED"] {
            environment.removeValue(forKey: name)
        }
        if bundled {
            environment["PLAYLIST_FERRY_BUNDLED"] = "1"
            environment["PATH"] = script.deletingLastPathComponent().appendingPathComponent("tools").path + ":/usr/bin:/bin"
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        task.environment = environment
        task.standardInput = input
        task.standardOutput = output
        task.standardError = errors
        // Children must not keep protocol pipes open after their worker exits.
        task.terminationHandler = { finished in
            _ = kill(-finished.processIdentifier, SIGKILL)
        }
        try task.run()
        process = task
        busy = true
        DispatchQueue.global(qos: .utility).async {
            let handle = errors.fileHandleForReading
            defer { try? handle.close() }
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty { break }
                diagnostics.append(chunk)
            }
        }
        do {
            try input.fileHandleForWriting.write(contentsOf: data + Data([0x0A]))
            try input.fileHandleForWriting.close()
        } catch {
            Self.stop(task)
            try? input.fileHandleForWriting.close()
            throw error
        }
        let timeout = DispatchWorkItem { [weak self, weak task] in
            guard let task, self?.process === task else { return }
            Self.stop(task)
            self?.message = "The operation timed out. Check your connection and try a smaller playlist."
        }
        deadline = timeout
        DispatchQueue.main.asyncAfter(deadline: .now() + (request["action"] as? String == "preview" ? 120 : 14_400), execute: timeout)
        readEvents(output, task: task, diagnostics: diagnostics, expectsDownload: request["action"] as? String == "download", requestURL: request["url"] as? String ?? "")
    }

    private func readEvents(_ output: Pipe, task: Process, diagnostics: WorkerDiagnostics, expectsDownload: Bool, requestURL: String) {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let handle = output.fileHandleForReading
            defer { try? handle.close() }
            var buffer = Data()
            var failure: String?
            var sawTerminal = false
            while failure == nil {
                let chunk = handle.availableData
                if chunk.isEmpty { break }
                buffer.append(chunk)
                while let newline = buffer.firstIndex(of: 0x0A) {
                    let line = Data(buffer[..<newline])
                    buffer.removeSubrange(...newline)
                    guard line.count <= 4_194_304,
                          let event = try? JSONDecoder().decode(WorkerEvent.self, from: line) else {
                        failure = "The worker returned an invalid response."
                        break
                    }
                    sawTerminal = sawTerminal || (event.event == "error" || event.event == (expectsDownload ? "complete" : "playlist"))
                    DispatchQueue.main.async {
                        guard self?.process === task else { return }
                        self?.apply(event)
                        if event.event == "playlist" { self?.previewedURL = requestURL }
                    }
                }
                if buffer.count > 4_194_304 { failure = "The worker response exceeded the supported size." }
            }
            if failure != nil { Self.stop(task) }
            task.waitUntilExit()
            if !buffer.isEmpty && failure == nil { failure = "The worker returned an incomplete response." }
            let result = failure
            let completed = sawTerminal
            DispatchQueue.main.async {
                guard let self, self.process === task else { return }
                self.deadline?.cancel()
                self.deadline = nil
                if let result { self.message = result }
                else if (task.terminationStatus != 0 || !completed) && self.message == nil {
                    let detail = diagnostics.summary
                    self.message = detail.isEmpty ? "The worker stopped without completing the operation." : "Worker failed: \(detail)"
                }
                self.process = nil
                self.busy = false
            }
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
