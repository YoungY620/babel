#!/usr/bin/env bash
# Repository identity and public publishing metadata for a fresh checkout.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
repository=${1:-${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY to owner/repo}}
[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
data_dir=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0,"apps/pipeline/pipeline"); from paths import data_root; print(data_root(Path("apps/pipeline").resolve()))')
mkdir -p "$data_dir/episodes"
owner=${repository%/*}
repo=${repository#*/}
git config user.name "$owner"
git config user.email "$owner@users.noreply.github.com"
if [ ! -f "$data_dir/config.env" ]; then
  if [ -f apps/pipeline/config.env ]; then
    echo "Move the existing publishing config into BABEL_DATA_DIR/config.env before bootstrap." >&2
    exit 1
  fi
  cat > "$data_dir/config.env" <<ENV
GITHUB_USER=$owner
GITHUB_REPO=$repo
SHOW_TITLE="巴别塔 Babel"
SHOW_AUTHOR="巴别塔 Babel"
SHOW_EMAIL=$owner@users.noreply.github.com
SUPPORT_LINKS=""
ENV
  chmod 600 "$data_dir/config.env"
fi
