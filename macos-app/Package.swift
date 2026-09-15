// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "SpotifyPlaylistDownloader",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "SpotifyPlaylistDownloader", targets: ["SpotifyPlaylistDownloader"])],
    targets: [
        .executableTarget(name: "SpotifyPlaylistDownloader", path: "Swift"),
    ]
)
