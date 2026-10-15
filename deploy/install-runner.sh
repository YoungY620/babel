#!/usr/bin/env bash
# Root on Ubuntu 26.04 x86_64. Prepare first; then register with a fresh token on stdin.
set -euo pipefail
[ "$(id -u)" = 0 ]
[ "$(uname -m)" = x86_64 ]
. /etc/os-release
[ "$ID" = ubuntu ]
[ "$VERSION_ID" = 26.04 ] # Match the shared production host; no older-release compatibility.
MODE="${1:?Usage: install-runner.sh prepare|register [owner/repo]}"
[[ "$MODE" = prepare || "$MODE" = register ]]
REPOSITORY="${2:-YoungY620/babel-runner}"
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]
# A persistent runner must never accept workflows from a public repository.
[ "$REPOSITORY" = YoungY620/babel-runner ]
RUNNER_USER=babel-runner
RUNNER_HOME=/srv/babel
VERSION=2.338.0
SHA256=af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32
[ ! -L "$RUNNER_HOME" ]
[ ! -L "$RUNNER_HOME/runner" ]

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  [ "$MODE" = prepare ]
  useradd --system --user-group --create-home --home-dir "$RUNNER_HOME" --shell /bin/bash "$RUNNER_USER"
fi
# Reject inherited host privileges instead of silently modifying an existing account.
[ "$(id -u "$RUNNER_USER")" != 0 ]
[ "$(id -Gn "$RUNNER_USER")" = "$RUNNER_USER" ]
[ "$(getent passwd "$RUNNER_USER" | cut -d: -f6)" = "$RUNNER_HOME" ]
if command -v sudo >/dev/null; then
  sudo_listing=$(LC_ALL=C sudo -n -l -U "$RUNNER_USER" 2>&1 || true)
  if [[ "$sudo_listing" != *"is not allowed to run sudo"* ]]; then
    echo 'Refusing a runner account whose lack of sudo privileges cannot be verified.' >&2
    exit 1
  fi
fi
if [ -f "$RUNNER_HOME/runner/.runner" ]; then
  echo 'Runner already registered; refusing to replace its identity.' >&2
  exit 1
fi

if [ "$MODE" = prepare ]; then
  apt-get update
  apt-get install -y ca-certificates curl ffmpeg gh git python3 libicu-dev liblttng-ust1t64 libkrb5-3 zlib1g libssl3t64
  owner=${REPOSITORY%/*}
  runuser -u "$RUNNER_USER" -- git config --global user.name "$owner"
  runuser -u "$RUNNER_USER" -- git config --global user.email "$owner@users.noreply.github.com"
  install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_HOME/runner" "$RUNNER_HOME/tools"
  archive=$(mktemp)
  trap 'rm -f "$archive"' EXIT
  curl --fail --location --retry 3 \
    "https://github.com/actions/runner/releases/download/v$VERSION/actions-runner-linux-x64-$VERSION.tar.gz" \
    -o "$archive"
  printf '%s  %s\n' "$SHA256" "$archive" | sha256sum --check --status
  chmod 644 "$archive"
  runuser -u "$RUNNER_USER" -- tar -xzf "$archive" -C "$RUNNER_HOME/runner"
  echo 'Prepared. Generate a fresh repository registration token, then run register.'
  exit 0
fi

# GitHub deliberately returns 404 to anonymous callers for private repositories.
# Refuse public repositories and unexpected API failures before registration.
visibility=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  "https://api.github.com/repos/$REPOSITORY")
[ "$visibility" = 404 ]
cd "$RUNNER_HOME/runner"
read -r TOKEN
trap 'unset TOKEN ACTIONS_RUNNER_INPUT_TOKEN' EXIT
export ACTIONS_RUNNER_INPUT_TOKEN="$TOKEN"
runuser -u "$RUNNER_USER" -- ./config.sh --unattended \
  --url "https://github.com/$REPOSITORY" \
  --name babel-ubuntu --labels babel --work _work
unset TOKEN ACTIONS_RUNNER_INPUT_TOKEN
runuser -u "$RUNNER_USER" -- tee .env >/dev/null <<ENV
RUNNER_TOOL_CACHE=$RUNNER_HOME/tools
AGENT_TOOLSDIRECTORY=$RUNNER_HOME/tools
ENV
# Never execute files writable by the runner as root.
service=actions.runner.babel-ubuntu.service
cat > "/etc/systemd/system/$service" <<ENV
[Unit]
Description=Babel GitHub Actions runner
After=network-online.target
Wants=network-online.target

[Service]
User=$RUNNER_USER
Group=$RUNNER_USER
WorkingDirectory=$RUNNER_HOME/runner
ExecStart=$RUNNER_HOME/runner/runsvc.sh
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
ENV
printf '%s\n' "$service" | runuser -u "$RUNNER_USER" -- tee .service >/dev/null
mkdir -p "/etc/systemd/system/$service.d"
cat > "/etc/systemd/system/$service.d/resources.conf" <<ENV
[Service]
# At most half of this four-vCPU machine; at least 22 GiB remain for other work.
CPUQuota=200%
CPUWeight=10
MemoryHigh=6G
MemoryMax=8G
MemorySwapMax=0
IOWeight=10
Nice=10
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
UMask=0077
ENV
systemctl daemon-reload
systemctl enable --now "$service"
systemctl is-active "$service"
