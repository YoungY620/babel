#!/usr/bin/env bash
# 隐私泄漏扫描：跟踪文件内容 + 待推送提交的 author 身份。
# 标准见 PRIVACY.md。本地手动跑、git hook、CI 三处共用。
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
err() { echo "PRIVACY: $1"; fail=1; }

# 1. 禁止入库的路径（模板/样例文件豁免）
for p in $(git ls-files); do
  case "$p" in
    *.example|*.sample|*.template) continue ;;
    secrets/*|*/secrets/*|*.env|*.env.*|config.env|*/config.env|*cookies*.txt)
      err "禁止入库的文件被跟踪: $p" ;;
  esac
done

# 2. 内容扫描（跟踪文件，排除本脚本自身与样例文档里的规则描述）
PATTERNS='(/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|moonshot|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|Netscape HTTP Cookie File)'
while read -r f; do
  case "$f" in
    scripts/privacy_check.sh|PRIVACY.md|.gitignore|*.lock|pnpm-lock.yaml) continue ;;
  esac
  if grep -nEI "$PATTERNS" "$f" >/dev/null 2>&1; then
    err "可疑内容: $f: $(grep -nEI "$PATTERNS" "$f" | head -3 | tr '\n' ' ')"
  fi
  # 邮箱：仅允许 users.noreply.github.com
  if grep -noE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$f" 2>/dev/null \
     | grep -v 'users.noreply.github.com' | grep -qv 'example.com'; then
    hits=$(grep -noE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$f" \
           | grep -v 'users.noreply.github.com' | grep -v 'example.com' | head -3 | tr '\n' ' ')
    [ -n "$hits" ] && err "非 noreply 邮箱: $f: $hits"
  fi
done < <(git ls-files)

# 3. 待推送提交的 author 身份
if git rev-parse @{u} >/dev/null 2>&1; then
  bad=$(git log @{u}..HEAD --format='%ae' 2>/dev/null | sort -u \
        | grep -v 'users.noreply.github.com$' || true)
  [ -n "$bad" ] && err "待推送提交含非 noreply author: $bad"
fi

if [ "$fail" -ne 0 ]; then
  echo "PRIVACY: 检查未通过" >&2
  exit 1
fi
echo "PRIVACY: OK"
