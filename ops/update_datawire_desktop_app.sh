#!/bin/bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
app_path="$HOME/Desktop/Florida Signal Data Wire.app"
expected_bundle="com.floridasignal.datawire.local"

if [[ ! -d "$app_path" ]]; then
  echo "Desktop app not found: $app_path" >&2
  exit 1
fi
actual_bundle="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app_path/Contents/Info.plist")"
if [[ "$actual_bundle" != "$expected_bundle" ]]; then
  echo "Refusing to replace an unexpected app bundle: $actual_bundle" >&2
  exit 1
fi

stage_dir="$(mktemp -d /tmp/fl-datawire-app.XXXXXX)"
staged_app="$stage_dir/Florida Signal Data Wire.app"
previous_app="$stage_dir/previous.app"
trap '/bin/rm -rf "$stage_dir"' EXIT

/usr/bin/ditto --norsrc "$app_path" "$staged_app"
/bin/cp "$repo_dir/cms/server.py" "$repo_dir/cms/home.html" "$repo_dir/cms/index.html" \
  "$repo_dir/cms/data.html" "$repo_dir/cms/review.html" "$repo_dir/cms/desk-shell.css" \
  "$repo_dir/cms/desk-shell.js" "$staged_app/Contents/Resources/cms/"
/bin/cp -L "$repo_dir/cms/mark-full-color.png" "$staged_app/Contents/Resources/cms/mark-full-color.png"
/bin/cp "$repo_dir/ops/datawire-app-launcher.zsh" "$staged_app/Contents/MacOS/Florida Signal Data Wire"
/bin/chmod 755 "$staged_app/Contents/MacOS/Florida Signal Data Wire"
/usr/bin/xattr -cr "$staged_app"
/usr/bin/codesign --force --deep --sign - "$staged_app"
/usr/bin/codesign --verify --deep --strict "$staged_app"

/bin/mv "$app_path" "$previous_app"
if /bin/mv "$staged_app" "$app_path"; then
  # Finder can add an empty com.apple.FinderInfo xattr as soon as a bundle lands on Desktop.
  # That metadata is not part of the app and makes strict verification report "detritus."
  /usr/bin/xattr -d com.apple.FinderInfo "$app_path" 2>/dev/null || true
fi
if [[ -d "$app_path" ]] && /usr/bin/codesign --verify --deep "$app_path"; then
  echo "Florida Signal Data Wire desktop app updated and verified."
else
  [[ -d "$app_path" ]] && /bin/mv "$app_path" "$stage_dir/failed-new.app"
  /bin/mv "$previous_app" "$app_path"
  /usr/bin/xattr -d com.apple.FinderInfo "$app_path" 2>/dev/null || true
  echo "Update failed; the previous desktop app was restored." >&2
  exit 1
fi
