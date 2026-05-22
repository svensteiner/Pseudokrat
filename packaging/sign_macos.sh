#!/usr/bin/env bash
# Pseudokrat — macOS-Code-Signing.
#
# Signiert eine .app, ein .dmg oder ein .pkg-Installer-Bundle mit einer
# Apple Developer ID. Verwendet codesign + (für Notarization) notarytool.
#
# Geheimnisse aus Env:
#   PSEUDOKRAT_APPLE_IDENTITY   — "Developer ID Application: Foo Bar (TEAMID)"
#   PSEUDOKRAT_APPLE_ID         — Apple ID (für Notarization)
#   PSEUDOKRAT_APPLE_PASSWORD   — App-spezifisches Passwort (NICHT iCloud-PW)
#   PSEUDOKRAT_APPLE_TEAM_ID    — 10-stellige Apple-Team-ID
#
# Bei fehlenden Vars wird klar abgelehnt, statt halb-signiert weiterzulaufen.
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <path/to/Pseudokrat.app|...dmg|...pkg>" >&2
    exit 2
fi
TARGET="$1"

if [[ ! -e "$TARGET" ]]; then
    echo "Zu signierendes Artefakt nicht gefunden: $TARGET" >&2
    exit 2
fi

: "${PSEUDOKRAT_APPLE_IDENTITY:?Env PSEUDOKRAT_APPLE_IDENTITY fehlt (Developer ID Application)}"

echo "==> Signiere $TARGET"
echo "    Identität: $PSEUDOKRAT_APPLE_IDENTITY"

# Entitlements optional aus Datei nehmen; sonst Minimal-Set.
ENTITLEMENTS_FILE="$(dirname "$0")/macos-entitlements.plist"
ENTITLEMENTS_ARG=()
if [[ -f "$ENTITLEMENTS_FILE" ]]; then
    ENTITLEMENTS_ARG=(--entitlements "$ENTITLEMENTS_FILE")
fi

codesign --force --deep --options runtime --timestamp \
    --sign "$PSEUDOKRAT_APPLE_IDENTITY" \
    "${ENTITLEMENTS_ARG[@]}" \
    "$TARGET"

codesign --verify --deep --strict --verbose=2 "$TARGET"

echo "OK: Signatur gültig."

# Notarization (optional)
if [[ "${NOTARIZE:-0}" == "1" ]]; then
    : "${PSEUDOKRAT_APPLE_ID:?Env PSEUDOKRAT_APPLE_ID fehlt}"
    : "${PSEUDOKRAT_APPLE_PASSWORD:?Env PSEUDOKRAT_APPLE_PASSWORD fehlt}"
    : "${PSEUDOKRAT_APPLE_TEAM_ID:?Env PSEUDOKRAT_APPLE_TEAM_ID fehlt}"
    echo "==> Notarization"
    case "$TARGET" in
        *.app)
            ZIP="$(dirname "$TARGET")/$(basename "$TARGET" .app)-for-notary.zip"
            /usr/bin/ditto -c -k --keepParent "$TARGET" "$ZIP"
            xcrun notarytool submit "$ZIP" \
                --apple-id "$PSEUDOKRAT_APPLE_ID" \
                --password "$PSEUDOKRAT_APPLE_PASSWORD" \
                --team-id "$PSEUDOKRAT_APPLE_TEAM_ID" \
                --wait
            rm -f "$ZIP"
            xcrun stapler staple "$TARGET"
            ;;
        *.dmg|*.pkg)
            xcrun notarytool submit "$TARGET" \
                --apple-id "$PSEUDOKRAT_APPLE_ID" \
                --password "$PSEUDOKRAT_APPLE_PASSWORD" \
                --team-id "$PSEUDOKRAT_APPLE_TEAM_ID" \
                --wait
            xcrun stapler staple "$TARGET"
            ;;
        *)
            echo "Unbekannter Artefakt-Typ für Notarization: $TARGET" >&2
            exit 3
            ;;
    esac
    echo "OK: Notarisiert + Stapled."
fi
