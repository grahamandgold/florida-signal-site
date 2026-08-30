#!/bin/bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
app_path="$HOME/Desktop/Florida Signal Data Wire.app"
expected_bundle="com.floridasignal.datawire.local"
site_repo="${FL_SIGNAL_SITE_REPO:-$HOME/Documents/FL SIGNAL SITE BUILD}"
source_root="${FL_SIGNAL_SOURCE_ROOT:-$site_repo/_source_copies/florida-signal}"
project_state_source="$source_root/data/reference/florida_signal_project_state.json"
pdmr_db_source="$source_root/data/pdmr/florida_signal_v1.sqlite"
pdmr_candidate_source="$source_root/scripts/nominate_pdmr_candidates.py"

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
/bin/cp "$repo_dir/cms/server.py" "$repo_dir/cms/home.html" "$repo_dir/cms/agenda.html" \
  "$repo_dir/cms/index.html" \
  "$repo_dir/cms/data.html" "$repo_dir/cms/review.html" "$repo_dir/cms/desk-shell.css" \
  "$repo_dir/cms/desk-shell.js" "$staged_app/Contents/Resources/cms/"
/bin/cp -L "$repo_dir/cms/mark-full-color.png" "$staged_app/Contents/Resources/cms/mark-full-color.png"

# Bundle local-only research lanes so the Finder app does not need Documents access.
# Re-running this updater refreshes the read-only snapshot.
for source_file in "$project_state_source" "$pdmr_db_source" "$pdmr_candidate_source"; do
  if [[ ! -s "$source_file" ]]; then
    echo "Desktop source snapshot is missing: $source_file" >&2
    exit 1
  fi
done
/usr/bin/python3 -m json.tool "$project_state_source" >/dev/null
if [[ "$(/usr/bin/sqlite3 "$pdmr_db_source" 'pragma quick_check;')" != "ok" ]]; then
  echo "PDMR evidence database failed SQLite quick_check" >&2
  exit 1
fi
snapshot_root="$staged_app/Contents/Resources/florida-signal"
/bin/mkdir -p "$snapshot_root/data/reference" "$snapshot_root/data/pdmr" "$snapshot_root/scripts"
/bin/cp "$project_state_source" "$snapshot_root/data/reference/florida_signal_project_state.json"
/bin/cp "$pdmr_db_source" "$snapshot_root/data/pdmr/florida_signal_v1.sqlite"
/bin/cp "$pdmr_candidate_source" "$snapshot_root/scripts/nominate_pdmr_candidates.py"

for required_page in home.html agenda.html index.html data.html review.html; do
  if [[ ! -s "$staged_app/Contents/Resources/cms/$required_page" ]]; then
    echo "Staged desktop app is missing required Newsroom page: $required_page" >&2
    exit 1
  fi
done
for required_snapshot in \
  data/reference/florida_signal_project_state.json \
  data/pdmr/florida_signal_v1.sqlite \
  scripts/nominate_pdmr_candidates.py; do
  if [[ ! -s "$snapshot_root/$required_snapshot" ]]; then
    echo "Staged desktop app is missing source snapshot: $required_snapshot" >&2
    exit 1
  fi
done
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
  # Python loads server.py into memory. Replacing the bundle updates static pages immediately,
  # but an already-running process would keep the old route map until restart. Restart only this
  # app's loopback server when it was already open; never kill another service on the port.
  app_was_running=0
  while IFS= read -r process_id; do
    [[ -n "$process_id" ]] || continue
    app_was_running=1
    /bin/kill "$process_id" 2>/dev/null || true
  done < <(/usr/bin/pgrep -f 'Florida Signal Data Wire\.app/.*/cms/server\.py --port 8788' || true)
  if [[ "$app_was_running" == 1 ]]; then
    /usr/bin/open "$app_path"
  fi
else
  [[ -d "$app_path" ]] && /bin/mv "$app_path" "$stage_dir/failed-new.app"
  /bin/mv "$previous_app" "$app_path"
  /usr/bin/xattr -d com.apple.FinderInfo "$app_path" 2>/dev/null || true
  echo "Update failed; the previous desktop app was restored." >&2
  exit 1
fi
