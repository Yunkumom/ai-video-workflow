#!/bin/bash
set -euo pipefail
TASK_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TASK_PROJECT=${1:---launcher}
if [[ "$TASK_PROJECT" == "--launcher" ]]; then
  TASK_PROJECT=""
  TASK_APP="$TASK_ROOT/2_processing/desktop_launcher_codex/影片編輯器.app"
  TASK_CACHE="$TASK_ROOT/2_processing/desktop_launcher_codex/swift-cache"
else
  if [[ ! "$TASK_PROJECT" =~ ^[[:alnum:]_-]+$ || ${#TASK_PROJECT} -gt 80 ]]; then exit 2; fi
  TASK_APP="$TASK_ROOT/3_output/$TASK_PROJECT/開啟編輯器.app"
  TASK_CACHE="$TASK_ROOT/2_processing/$TASK_PROJECT/desktop-editor/swift-cache"
fi
TASK_PYTHON=$(command -v python3)
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
mkdir -p "$TASK_APP/Contents/MacOS" "$TASK_APP/Contents/Resources" "$TASK_CACHE"
if [[ ! -x "$TASK_APP/Contents/MacOS/Editor" || "$TASK_ROOT/system/desktop/EditorApp.swift" -nt "$TASK_APP/Contents/MacOS/Editor" ]]; then
  CLANG_MODULE_CACHE_PATH="$TASK_CACHE" swiftc "$TASK_ROOT/system/desktop/EditorApp.swift" -o "$TASK_APP/Contents/MacOS/Editor"
fi
cp "$TASK_ROOT/system/desktop/Info.plist" "$TASK_APP/Contents/Info.plist"
"$TASK_PYTHON" - "$TASK_ROOT" "$TASK_PROJECT" "$TASK_PYTHON" "$TASK_APP/Contents/Resources/project.json" <<'PY'
import json, sys, plistlib
from pathlib import Path
Path(sys.argv[4]).write_text(json.dumps(dict(root=sys.argv[1], project=sys.argv[2], python=sys.argv[3])))
plist_path = Path(sys.argv[4]).parents[1] / 'Info.plist'
info = plistlib.loads(plist_path.read_bytes())
if not sys.argv[2]: info['CFBundleIdentifier'] = 'local.video-editor.desktop.launcher'
info['CFBundleShortVersionString'] = '7.0'
info['CFBundleVersion'] = '7'
plist_path.write_bytes(plistlib.dumps(info))
PY
codesign --force --sign - "$TASK_APP"
printf '%s\n' "$TASK_APP"
