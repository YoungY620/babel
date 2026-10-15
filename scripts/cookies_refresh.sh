#!/usr/bin/env bash
# 把浏览器里的 YouTube cookies 导出为长期使用的 BABEL_DATA_DIR/private/cookies.txt。
# 首次前置：在浏览器里登录一次 YouTube（chrome/firefox/edge/brave 任一）。
# YouTube cookies 会过期，fetch 报 403/bot 时重跑本脚本即可。
# 用法: scripts/cookies_refresh.sh [chrome|firefox|edge|brave]
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."

data_dir=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0,"apps/pipeline/pipeline"); from paths import data_root; print(data_root(Path("apps/pipeline").resolve()))')
mkdir -p "$data_dir/private"
BROWSER="${1:-chrome}"
YTDLP="apps/pipeline/.venv/bin/yt-dlp"
[ -x "$YTDLP" ] || YTDLP="yt-dlp"

"$YTDLP" --cookies-from-browser "$BROWSER" --cookies "$data_dir/private/cookies.txt" \
  --skip-download --print "verify: %(id)s %(title)s" \
  "https://www.youtube.com/watch?v=jNQXAC9IVRw"

echo "OK saved private cookie file; never commit it."
