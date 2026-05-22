#!/usr/bin/env bash
# Pseudokrat — macOS-Build-Skript.
#
# Baut Pseudokrat.app via PyInstaller, optional signiert + notarisiert.
# Voraussetzungen siehe INSTALLER.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SIGN=0
NOTARIZE=0
DMG=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sign) SIGN=1 ;;
        --notarize) NOTARIZE=1 ;;
        --dmg) DMG=1 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^#\s\?//'
            exit 0
            ;;
        *)
            echo "Unbekanntes Argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

echo "==> Pseudokrat-macOS-Build"
echo "    Repo: $REPO_ROOT"

# Cleanup
rm -rf build dist

# Bauwerkzeuge
echo "==> Installiere pyinstaller"
python -m pip install --upgrade pip pyinstaller >/dev/null

# PyInstaller
echo "==> PyInstaller-Bundle"
python -m PyInstaller packaging/pseudokrat.spec --noconfirm --clean
APP_PATH="dist/Pseudokrat.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "Erwartete App nicht gefunden: $APP_PATH" >&2
    exit 2
fi
echo "    OK: $APP_PATH"

# Signing
if [[ "$SIGN" -eq 1 ]]; then
    echo "==> Code-Signing"
    "$REPO_ROOT/packaging/sign_macos.sh" "$APP_PATH"
fi

# Notarization (setzt Signing voraus)
if [[ "$NOTARIZE" -eq 1 ]]; then
    if [[ "$SIGN" -ne 1 ]]; then
        echo "FEHLER: --notarize erfordert --sign." >&2
        exit 2
    fi
    echo "==> Notarization bei Apple"
    : "${PSEUDOKRAT_APPLE_ID:?PSEUDOKRAT_APPLE_ID nicht gesetzt}"
    : "${PSEUDOKRAT_APPLE_PASSWORD:?PSEUDOKRAT_APPLE_PASSWORD nicht gesetzt}"
    : "${PSEUDOKRAT_APPLE_TEAM_ID:?PSEUDOKRAT_APPLE_TEAM_ID nicht gesetzt}"

    ZIP="dist/Pseudokrat.zip"
    /usr/bin/ditto -c -k --keepParent "$APP_PATH" "$ZIP"
    xcrun notarytool submit "$ZIP" \
        --apple-id "$PSEUDOKRAT_APPLE_ID" \
        --password "$PSEUDOKRAT_APPLE_PASSWORD" \
        --team-id "$PSEUDOKRAT_APPLE_TEAM_ID" \
        --wait
    xcrun stapler staple "$APP_PATH"
fi

# DMG (optional)
if [[ "$DMG" -eq 1 ]]; then
    echo "==> DMG"
    DMG_OUT="dist/Pseudokrat-0.1.0.dmg"
    hdiutil create -volname "Pseudokrat" -srcfolder "$APP_PATH" \
        -ov -format UDZO "$DMG_OUT"
    if [[ "$SIGN" -eq 1 ]]; then
        codesign --sign "$PSEUDOKRAT_APPLE_IDENTITY" "$DMG_OUT"
    fi
    echo "    OK: $DMG_OUT"
fi

echo ""
echo "Fertig."
