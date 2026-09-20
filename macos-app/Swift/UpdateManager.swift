import AppKit
import Combine
import CryptoKit
import Foundation

struct AvailableUpdate: Identifiable {
    let version: String
    let archiveURL: URL
    let checksumURL: URL

    var id: String { version }
}

private struct GitHubRelease: Decodable {
    struct Asset: Decodable {
        let name: String
        let browser_download_url: URL
    }

    let tag_name: String
    let assets: [Asset]
}

@MainActor
final class UpdateManager: ObservableObject {
    @Published var availableUpdate: AvailableUpdate?
    @Published private(set) var status = ""
    @Published private(set) var busy = false

    private let repository = "ThatOneGuyGreggers/playlist-ferry"

    func checkForUpdates(showCurrentStatus: Bool = false) async {
        guard !busy else { return }
        busy = true
        if showCurrentStatus { status = "Checking for updates…" }
        defer { busy = false }
        do {
            let update = try await fetchAvailableUpdate()
            availableUpdate = update
            if update == nil && showCurrentStatus {
                status = "Playlist Ferry is up to date."
            } else if let update {
                status = "Version \(update.version) is available."
            }
        } catch {
            if showCurrentStatus {
                status = "Update check failed: \(error.localizedDescription)"
            }
        }
    }

    func install(_ update: AvailableUpdate) async {
        guard !busy else { return }
        busy = true
        status = "Downloading Playlist Ferry \(update.version)…"
        do {
            let prepared = try await prepare(update)
            status = "Installing Playlist Ferry \(update.version)…"
            try launchInstaller(stagedApp: prepared.app, workDirectory: prepared.root)
            NSApp.terminate(nil)
        } catch {
            status = "Update failed: \(error.localizedDescription)"
            busy = false
        }
    }

    private func fetchAvailableUpdate() async throws -> AvailableUpdate? {
        let endpoint = URL(string: "https://api.github.com/repos/\(repository)/releases/latest")!
        var request = URLRequest(url: endpoint)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("Playlist-Ferry-Updater", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 20
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw UpdateError.releaseUnavailable
        }
        let release = try JSONDecoder().decode(GitHubRelease.self, from: data)
        let version = release.tag_name.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
        guard Self.isNewer(version, than: currentVersion) else { return nil }
        let archiveName = "Playlist-Ferry-\(version)-macos-\(Self.architecture).zip"
        guard
            let archive = release.assets.first(where: { $0.name == archiveName }),
            let checksum = release.assets.first(where: { $0.name == archiveName + ".sha256" })
        else {
            throw UpdateError.assetsMissing
        }
        try Self.requireGitHubURL(archive.browser_download_url)
        try Self.requireGitHubURL(checksum.browser_download_url)
        return AvailableUpdate(
            version: version,
            archiveURL: archive.browser_download_url,
            checksumURL: checksum.browser_download_url
        )
    }

    private var currentVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.0.0"
    }

    private static var architecture: String {
#if arch(arm64)
        return "arm64"
#else
        return "x86_64"
#endif
    }

    static func isNewer(_ candidate: String, than current: String) -> Bool {
        func parts(_ value: String) -> [Int]? {
            let components = value.split(separator: ".", omittingEmptySubsequences: false)
            guard !components.isEmpty, components.count <= 3 else { return nil }
            var result: [Int] = []
            for component in components {
                guard !component.isEmpty, component.allSatisfy(\.isNumber), let number = Int(component) else {
                    return nil
                }
                result.append(number)
            }
            return result
        }
        guard let candidateParts = parts(candidate), let currentParts = parts(current) else { return false }
        for index in 0..<max(candidateParts.count, currentParts.count) {
            let left = index < candidateParts.count ? candidateParts[index] : 0
            let right = index < currentParts.count ? currentParts[index] : 0
            if left != right { return left > right }
        }
        return false
    }

    static func supportsArchitecture(_ architecture: String, lipoOutput: String) -> Bool {
        lipoOutput.split(whereSeparator: { $0.isWhitespace }).contains(Substring(architecture))
    }

    private func prepare(_ update: AvailableUpdate) async throws -> (root: URL, app: URL) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("playlist-ferry-update-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        do {
            async let archiveDownload = URLSession.shared.download(from: update.archiveURL)
            async let checksumDownload = URLSession.shared.data(from: update.checksumURL)
            let ((temporaryArchive, archiveResponse), (checksumData, checksumResponse)) =
                try await (archiveDownload, checksumDownload)
            try Self.requireSuccessfulDownload(archiveResponse)
            try Self.requireSuccessfulDownload(checksumResponse)
            let archive = root.appendingPathComponent("update.zip")
            try FileManager.default.moveItem(at: temporaryArchive, to: archive)
            let expected = try Self.parseChecksum(checksumData)
            guard try Self.sha256(archive) == expected else {
                throw UpdateError.checksumMismatch
            }
            let extracted = root.appendingPathComponent("extracted", isDirectory: true)
            try FileManager.default.createDirectory(at: extracted, withIntermediateDirectories: false)
            try Self.run("/usr/bin/ditto", ["-x", "-k", archive.path, extracted.path])
            let app = extracted.appendingPathComponent("Playlist Ferry.app", isDirectory: true)
            try Self.validate(app)
            return (root, app)
        } catch {
            try? FileManager.default.removeItem(at: root)
            throw error
        }
    }

    private func launchInstaller(stagedApp: URL, workDirectory: URL) throws {
        let installedApp = Bundle.main.bundleURL.standardizedFileURL
        guard installedApp.pathExtension == "app" else { throw UpdateError.notInstalledApp }
        guard FileManager.default.isWritableFile(atPath: installedApp.deletingLastPathComponent().path)
        else { throw UpdateError.installLocationNotWritable }
        let backup = installedApp.deletingLastPathComponent().appendingPathComponent(
            ".Playlist Ferry backup \(UUID().uuidString).app", isDirectory: true
        )
        let script = workDirectory.appendingPathComponent("install-update.sh")
        let contents = """
        #!/bin/sh
        set -u
        staged="$1"
        installed="$2"
        parent_pid="$3"
        backup="$4"
        work="$5"
        while /bin/kill -0 "$parent_pid" 2>/dev/null; do /bin/sleep 0.2; done
        if /bin/mv "$installed" "$backup" && /usr/bin/ditto --noextattr "$staged" "$installed" && /usr/bin/codesign --verify --deep --strict "$installed"; then
            /usr/bin/open "$installed"
            /bin/rm -rf "$backup" "$work"
            exit 0
        fi
        /bin/rm -rf "$installed"
        if [ -e "$backup" ]; then /bin/mv "$backup" "$installed"; /usr/bin/open "$installed"; fi
        exit 1
        """
        try contents.write(to: script, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: script.path)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sh")
        process.arguments = [
            script.path, stagedApp.path, installedApp.path,
            String(ProcessInfo.processInfo.processIdentifier), backup.path, workDirectory.path,
        ]
        try process.run()
    }

    private static func validate(_ app: URL) throws {
        let info = app.appendingPathComponent("Contents/Info.plist")
        guard
            let data = try? Data(contentsOf: info),
            let plist = try? PropertyListSerialization.propertyList(from: data, format: nil),
            let dictionary = plist as? [String: Any],
            dictionary["CFBundleIdentifier"] as? String == "dev.greggers.playlist-ferry"
        else { throw UpdateError.invalidBundle }
        try run("/usr/bin/codesign", ["--verify", "--deep", "--strict", app.path])
        let executable = app.appendingPathComponent("Contents/MacOS/PlaylistFerry")
        let architectures = try output("/usr/bin/lipo", ["-archs", executable.path])
        guard supportsArchitecture(architecture, lipoOutput: architectures) else {
            throw UpdateError.wrongArchitecture
        }
    }

    private static func requireGitHubURL(_ url: URL) throws {
        guard url.scheme == "https", url.host?.lowercased() == "github.com" else {
            throw UpdateError.untrustedURL
        }
    }

    private static func requireSuccessfulDownload(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode)
        else { throw UpdateError.downloadFailed }
    }

    private static func parseChecksum(_ data: Data) throws -> String {
        let text = String(decoding: data, as: UTF8.self)
        guard let value = text.split(whereSeparator: { $0.isWhitespace }).first,
              value.count == 64,
              value.allSatisfy({ $0.isHexDigit })
        else { throw UpdateError.invalidChecksum }
        return value.lowercased()
    }

    private static func sha256(_ file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private static func run(_ executable: String, _ arguments: [String]) throws {
        _ = try output(executable, arguments)
    }

    private static func output(_ executable: String, _ arguments: [String]) throws -> String {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        process.waitUntilExit()
        let output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        guard process.terminationStatus == 0 else {
            throw UpdateError.commandFailed(output.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return output
    }
}

private enum UpdateError: LocalizedError {
    case releaseUnavailable, assetsMissing, untrustedURL, downloadFailed
    case invalidChecksum, checksumMismatch, invalidBundle, wrongArchitecture
    case notInstalledApp, installLocationNotWritable, commandFailed(String)

    var errorDescription: String? {
        switch self {
        case .releaseUnavailable: return "GitHub did not return the latest release."
        case .assetsMissing: return "The release does not contain this Mac's update files."
        case .untrustedURL: return "The release contains an untrusted download URL."
        case .downloadFailed: return "The update download failed."
        case .invalidChecksum: return "The published update checksum is invalid."
        case .checksumMismatch: return "The update failed SHA-256 verification."
        case .invalidBundle: return "The downloaded app has the wrong bundle identity."
        case .wrongArchitecture: return "The downloaded app does not support this Mac."
        case .notInstalledApp: return "Run Playlist Ferry from an installed app bundle to update it."
        case .installLocationNotWritable: return "Move Playlist Ferry to a writable Applications folder, then try again."
        case .commandFailed(let detail): return detail.isEmpty ? "Update validation failed." : detail
        }
    }
}
