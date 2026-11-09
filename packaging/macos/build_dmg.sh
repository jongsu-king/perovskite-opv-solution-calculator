#!/usr/bin/env bash
# Package dist/<App>.app into dist/<slug>-<version>-macos-<arch>.dmg (drag-to-Applications).
# Usage: packaging/macos/build_dmg.sh "Solution Calculator.app" Solution-Calculator 1.1.0
set -euo pipefail
APP="$1"; SLUG="$2"; VERSION="$3"
ARCH=$(uname -m); [ "$ARCH" = "arm64" ] || ARCH=x86_64
STAGE=$(mktemp -d)
cp -R "dist/$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
OUT="dist/${SLUG}-${VERSION}-macos-${ARCH}.dmg"
for attempt in 1 2 3 4; do   # hdiutil occasionally reports "Resource busy" on CI runners
  if hdiutil create -volname "${APP%.app}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"; then break; fi
  sleep $((attempt * 5))
done
test -s "$OUT"
# Check the image: mount it, run the self-test from inside, detach.
MP=$(mktemp -d)
hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MP" "$OUT"
"$MP/$APP/Contents/MacOS/$(defaults read "$MP/$APP/Contents/Info.plist" CFBundleExecutable)" --selftest --out "dist/selftest-macos-${ARCH}-dmg.json"
for attempt in 1 2 3 4; do hdiutil detach "$MP" -quiet && break; sleep 3; done
ls -la dist
