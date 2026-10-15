#!/usr/bin/env bash
# Publish: upload zh.mp3 files to a rolling GitHub Release "audio",
# then push docs/ (feed.xml + player) to GitHub Pages.
# Prereq: gh auth login; config.env filled in.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; source config.env; set +a

# 2. upload audio to rolling release（文件名带内容哈希，重渲染即新 URL）
if ! gh release view audio --repo "$GITHUB_USER/$GITHUB_REPO" >/dev/null 2>&1; then
  gh release create audio --repo "$GITHUB_USER/$GITHUB_REPO" \
     --title "Audio assets" --notes "Rolling release hosting zh.mp3 files"
fi
# Only remove this episode's known content-hash asset names.
prune_assets() {
  gh release view audio --repo "$GITHUB_USER/$GITHUB_REPO" --json assets |
    .venv/bin/python -c '
import json,re,sys
pattern = re.compile(re.escape(sys.argv[1]) + r"-zh-(?:[0-9a-f]{8}|[0-9a-f]{12})\.mp3")
for asset in json.load(sys.stdin)["assets"]:
    name = asset["name"]
    if pattern.fullmatch(name) and name != sys.argv[2]: print(name)
' "$1" "$2" | while IFS= read -r obsolete; do
      gh release delete-asset audio "$obsolete" --repo "$GITHUB_USER/$GITHUB_REPO" --yes
    done
}
for f in episodes/*/zh.mp3; do
  [ -e "$f" ] || continue
  slug=$(basename "$(dirname "$f")")
  if ! .venv/bin/python pipeline/tts.py "$slug" --check; then
    prune_assets "$slug" ""
    echo "skip unverified audio: $slug"
    continue
  fi
  hash=$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1]))["audio_sha256"][:12])' "episodes/$slug/speech.json")
  name="${slug}-zh-${hash}.mp3"
  if gh release view audio --repo "$GITHUB_USER/$GITHUB_REPO" --json assets \
       --jq ".assets[].name" | grep -qx "$name"; then
    echo "skip (exists) $name"
  else
    echo "upload $name"
    tmp=$(mktemp -d)
    ln "$f" "$tmp/$name"   # gh release upload 用文件名做资产名，先硬链接改名
    gh release upload audio "$tmp/$name" --repo "$GITHUB_USER/$GITHUB_REPO"
    rm -rf "$tmp"
  fi
  prune_assets "$slug" "$name"
done

# 3. pages content
.venv/bin/python pipeline/build_feed.py
git add docs
[ -f state.json ] && git add state.json
git commit -m "publish: $(date +%F)" || echo "nothing to commit"
git pull --rebase origin main   # 其他发布（如手动提交）先行时不至于推不上去
git push

# 4. enable Pages (main /docs) on first run
gh api "repos/$GITHUB_USER/$GITHUB_REPO/pages" -X POST \
   -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null || true

echo
echo "Feed:   https://$GITHUB_USER.github.io/$GITHUB_REPO/feed.xml"
echo "Player: https://$GITHUB_USER.github.io/$GITHUB_REPO/"
