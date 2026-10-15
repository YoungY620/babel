#!/usr/bin/env bash
# 把浏览器里的 YouTube cookies 导出为长期使用的 secrets/cookies.txt。
# 首次前置：在浏览器里登录一次 YouTube（chrome/firefox/edge/brave 任一）。
# YouTube cookies 会过期，fetch 报 403/bot 时重跑本脚本即可。
# 用法: scripts/cookies_refresh.sh [chrome|firefox|edge|brave]
set -euo pipefail
cd "$(dirname "$0")/.."

BROWSER="${1:-chrome}"
YTDLP="apps/pipeline/.venv/bin/yt-dlp"
[ -x "$YTDLP" ] || YTDLP="yt-dlp"

"$YTDLP" --cookies-from-browser "$BROWSER" --cookies secrets/cookies.txt \
  --skip-download --print "verify: %(id)s %(title)s" \
  "https://www.youtube.com/watch?v=jNQXAC9IVRw"

echo "OK saved -> secrets/cookies.txt (已 gitignore，切勿提交)"
