#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
APP_ROOT=${SCRIPT_DIR:h}
PROJECT_ROOT=${APP_ROOT:h}
BINARY=${1:-${APP_ROOT}/.build/debug/PlaylistFerry}
APP="${APP_ROOT}/dist/Playlist Ferry.app"

if [[ ! -x "${BINARY}" ]]; then
    print -u2 "Built executable not found: ${BINARY}"
    exit 1
fi

# Recreate the test bundle so stale resources cannot survive a rebuild.
rm -rf "${APP}"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources/spotify-downloader"
cp "${BINARY}" "${APP}/Contents/MacOS/PlaylistFerry"
cp "${APP_ROOT}/Assets/playlist-ferry.icns" "${APP}/Contents/Resources/PlaylistFerry.icns"
cp "${APP_ROOT}/worker/worker.py" "${APP}/Contents/Resources/worker.py"
cp -R "${PROJECT_ROOT}/spotify-downloader/spotdl" "${APP}/Contents/Resources/spotify-downloader/spotdl"
if [[ ! -x "${APP_ROOT}/.venv/bin/python" ]]; then
    print -u2 "Development Python runtime not found: ${APP_ROOT}/.venv/bin/python"
    exit 1
fi
cat > "${APP}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleDevelopmentRegion</key><string>en</string>
    <key>CFBundleExecutable</key><string>PlaylistFerry</string>
    <key>CFBundleIdentifier</key><string>local.greggers.playlist-ferry.test</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>Playlist Ferry</string>
    <key>CFBundleDisplayName</key><string>Playlist Ferry</string>
    <key>CFBundleIconFile</key><string>PlaylistFerry</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>2.0.3</string>
    <key>CFBundleVersion</key><string>4</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

plutil -lint "${APP}/Contents/Info.plist"
# Codex and Finder can attach protected provenance metadata inside the workspace.
# Stage a metadata-free copy so codesign never sees those extended attributes.
SIGNING_STAGE=$(mktemp -d /tmp/playlist-ferry-sign.XXXXXX)
trap 'rm -rf "${SIGNING_STAGE}"' EXIT
ditto --norsrc --noextattr "${APP}" "${SIGNING_STAGE}/Playlist Ferry.app"
codesign --force --deep --sign - "${SIGNING_STAGE}/Playlist Ferry.app"
codesign --verify --deep "${SIGNING_STAGE}/Playlist Ferry.app"
rm -rf "${APP}"
ditto --norsrc --noextattr "${SIGNING_STAGE}/Playlist Ferry.app" "${APP}"
codesign --verify --deep "${APP}"
print "Test app: ${APP}"
