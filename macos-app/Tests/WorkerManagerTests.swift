import Foundation

@main
struct WorkerManagerTests {
    @MainActor
    static func main() async throws {
        let tests = WorkerManagerTests()
        try await tests.testMalformedProtocolStopsAndReportsFailure()
        try await tests.testMissingDownloadCompletionIsReported()
        try await tests.testCanceledJobCannotOverwriteNewPlaylist()
        try await tests.testWorkerExitStopsChildHoldingProtocolPipe()
        try await tests.testUnpreviewedPlaylistCannotDownload()
        print("All five native worker regression checks passed.")
    }

    private func expect(_ condition: Bool, _ message: String) throws {
        if !condition { throw NSError(domain: "WorkerRegression", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
    }
    @MainActor
    private func manager(_ source: String) throws -> (WorkerManager, URL) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let script = root.appendingPathComponent("worker.py")
        try source.write(to: script, atomically: true, encoding: .utf8)
        return (WorkerManager(python: URL(fileURLWithPath: "/usr/bin/python3"), script: script), root)
    }

    @MainActor
    private func finish(_ worker: WorkerManager) async throws {
        for _ in 0..<200 {
            if !worker.busy { return }
            try await Task.sleep(nanoseconds: 25_000_000)
        }
        worker.cancel()
        try expect(false, "Worker did not stop within five seconds")
    }

    @MainActor
    func testMalformedProtocolStopsAndReportsFailure() async throws {
        let (worker, root) = try manager("print('not json', flush=True)\n")
        defer { try? FileManager.default.removeItem(at: root) }
        worker.preview(url: "fixture")
        try await finish(worker)
        try expect(worker.message?.contains("invalid response") == true, "Malformed output was not reported")
    }

    @MainActor
    func testMissingDownloadCompletionIsReported() async throws {
        let (worker, root) = try manager("print('{\"event\":\"playlist\",\"songs\":[]}', flush=True)\n")
        defer { try? FileManager.default.removeItem(at: root) }
        worker.preview(url: "fixture")
        try await finish(worker)
        worker.download(url: "fixture", destination: root, preset: "apple-universal")
        try await finish(worker)
        try expect(worker.message?.contains("without completing") == true, "Missing completion was not reported")
    }

    @MainActor
    func testCanceledJobCannotOverwriteNewPlaylist() async throws {
        let source = """
        import json, sys, time, signal, os
        if os.getpgrp() != os.getpid():
            os.setsid()
        signal.signal(signal.SIGTERM, lambda *args: None)
        request = json.loads(sys.stdin.readline())
        if request['url'] == 'old':
            time.sleep(0.3)
        print(json.dumps({'event':'playlist','metadata':{'name':request['url'],'author_name':'fixture'},'songs':[]}), flush=True)
        """
        let (worker, root) = try manager(source)
        defer { worker.cancel(); try? FileManager.default.removeItem(at: root) }
        worker.preview(url: "old")
        try await Task.sleep(nanoseconds: 100_000_000)
        worker.cancel()
        worker.preview(url: "new")
        try await finish(worker)
        try await Task.sleep(nanoseconds: 500_000_000)
        try expect(worker.playlist?.name == "new", "Canceled job replaced the new playlist: name=\(worker.playlist?.name ?? "nil") message=\(worker.message ?? "nil")")
        try expect(!worker.busy, "Worker remained busy")
    }
    @MainActor
    func testWorkerExitStopsChildHoldingProtocolPipe() async throws {
        let source = """
        import os, time, json, signal
        if os.fork() == 0:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            time.sleep(30)
            os._exit(0)
        print(json.dumps({'event':'playlist','songs':[]}), flush=True)
        """
        let (worker, root) = try manager(source)
        defer { worker.cancel(); try? FileManager.default.removeItem(at: root) }
        worker.preview(url: "fixture")
        try await finish(worker)
        try expect(!worker.busy, "Child process kept the worker busy")
    }

    @MainActor
    func testUnpreviewedPlaylistCannotDownload() async throws {
        let (worker, root) = try manager("print('should not start', flush=True)\n")
        defer { try? FileManager.default.removeItem(at: root) }
        worker.download(url: "different", destination: root, preset: "apple-universal")
        try expect(!worker.busy, "Unpreviewed playlist started a worker")
        try expect(worker.message?.contains("Preview") == true, "Missing preview instruction")
    }

}
