// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PlaylistFerry",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "PlaylistFerry", targets: ["PlaylistFerry"])],
    targets: [
        .executableTarget(name: "PlaylistFerry", path: "Swift"),
    ]
)
