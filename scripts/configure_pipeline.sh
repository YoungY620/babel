#!/usr/bin/env bash
# Repository identity and public publishing metadata for a fresh checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
repository=${1:-${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY to owner/repo}}
[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
owner=${repository%/*}
repo=${repository#*/}
git config user.name "$owner"
git config user.email "$owner@users.noreply.github.com"
if [ ! -f apps/pipeline/config.env ]; then
  cat > apps/pipeline/config.env <<ENV
GITHUB_USER=$owner
GITHUB_REPO=$repo
SHOW_TITLE="巴别塔 Babel"
SHOW_AUTHOR="巴别塔 Babel"
SHOW_EMAIL=$owner@users.noreply.github.com
SUPPORT_LINKS=""
ENV
  chmod 600 apps/pipeline/config.env
fi
