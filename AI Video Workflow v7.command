#!/bin/zsh
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
WORKFLOW_DIR=${0:A:h}
cd "$WORKFLOW_DIR"
# Editor v7; the legacy batch editor remains an explicit option.
if [[ "${1:-}" == "--legacy-batch" ]]; then exec python3 -m system.app; fi
for required in python3 swiftc ffmpeg ffprobe; do
  if ! command -v "$required" >/dev/null; then
    print "缺少 $required，請先設定既有工具，再重新開啟。"
    read "?按 Enter 關閉。"
    exit 1
  fi
done
if ! EDITOR_APP=$(bash system/desktop/build_app.sh --launcher); then
  print "編輯器建置失敗，未修改專案；請查看上方錯誤。"
  read "?按 Enter 關閉。"
  exit 1
fi
open "$EDITOR_APP"
