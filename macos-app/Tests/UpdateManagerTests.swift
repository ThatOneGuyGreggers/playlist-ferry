import Foundation

@main
struct UpdateManagerTests {
    @MainActor
    static func main() throws {
        try expect(UpdateManager.isNewer("2.0.2", than: "2.0.1"), "Updater test release was not detected")
        try expect(UpdateManager.isNewer("2.0.1", than: "2.0.0"), "Patch update was not detected")
        try expect(UpdateManager.isNewer("2.1.0", than: "2.0.99"), "Minor update was not detected")
        try expect(UpdateManager.isNewer("3.0.0", than: "2.99.99"), "Major update was not detected")
        try expect(!UpdateManager.isNewer("2.0.0", than: "2.0.0"), "Equal versions were treated as newer")
        try expect(!UpdateManager.isNewer("1.9.9", than: "2.0.0"), "Older version was treated as newer")
        try expect(!UpdateManager.isNewer("release", than: "2.0.0"), "Malformed version was accepted")
        print("All seven update-version checks passed.")
    }

    private static func expect(_ condition: Bool, _ message: String) throws {
        if !condition {
            throw NSError(domain: "UpdateManagerTests", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
        }
    }
}
