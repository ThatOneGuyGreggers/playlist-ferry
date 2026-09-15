#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
APP_ROOT=${SCRIPT_DIR:h}
PROJECT_ROOT=${APP_ROOT:h}
BINARY=${1:-${APP_ROOT}/.build/debug/SpotifyPlaylistDownloader}
APP="${APP_ROOT}/dist/Spotify Playlist Downloader.app"

if [[ ! -x "${BINARY}" ]]; then
    print -u2 "Built executable not found: ${BINARY}"
    exit 1
fi

# Recreate the test bundle so stale resources cannot survive a rebuild.
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources/spotify-downloader"
cp "${BINARY}" "${APP}/Contents/MacOS/SpotifyPlaylistDownloader"
cp "${APP_ROOT}/worker/worker.py" "${APP}/Contents/Resources/worker.py"
cp -R "${PROJECT_ROOT}/spotify-downloader/spotdl" "${APP}/Contents/Resources/spotify-downloader/spotdl"

cat > "${APP}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleDevelopmentRegion</key><string>en</string>
    <key>CFBundleExecutable</key><string>SpotifyPlaylistDownloader</string>
    <key>CFBundleIdentifier</key><string>local.greggers.spotify-playlist-downloader.test</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>Spotify Playlist Downloader</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

plutil -lint "${APP}/Contents/Info.plist"
# Finder can attach metadata after a local launch; remove it before signing a fresh bundle.
xattr -cr "${APP}"
codesign --force --sign - "${APP}"
print "Test app: ${APP}"
