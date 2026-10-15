#!/usr/bin/env bash
# Run as root on Ubuntu x86_64; read a short-lived registration token from stdin.
set -euo pipefail
[ "$(id -u)" = 0 ]
[ "$(uname -m)" = x86_64 ]
. /etc/os-release
[ "$ID" = ubuntu ]
REPOSITORY="${1:-YoungY620/babel}"
RUNNER_USER=babel-runner
RUNNER_HOME=/srv/babel
VERSION=2.338.0
SHA256=af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32
read -r TOKEN
trap 'unset TOKEN' EXIT

if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$RUNNER_HOME" --shell /bin/bash "$RUNNER_USER"
fi
install -d -o "$RUNNER_USER" -g "$RUNNER_USER" "$RUNNER_HOME/runner" "$RUNNER_HOME/tools"
cd "$RUNNER_HOME/runner"
if [ -f .runner ]; then
  echo 'Runner already registered; refusing to replace its identity.' >&2
  exit 1
fi
apt-get update
apt-get install -y ca-certificates curl ffmpeg gh git libicu-dev
archive=$(mktemp)
trap 'rm -f "$archive"; unset TOKEN' EXIT
curl --fail --location --retry 3 \
  "https://github.com/actions/runner/releases/download/v$VERSION/actions-runner-linux-x64-$VERSION.tar.gz" \
  -o "$archive"
printf '%s  %s\n' "$SHA256" "$archive" | sha256sum --check --status
tar -xzf "$archive"
chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME"
runuser -u "$RUNNER_USER" -- ./config.sh --unattended \
  --url "https://github.com/$REPOSITORY" --token "$TOKEN" \
  --name babel-ubuntu --labels babel --work _work
unset TOKEN
cat > .env <<ENV
RUNNER_TOOL_CACHE=$RUNNER_HOME/tools
AGENT_TOOLSDIRECTORY=$RUNNER_HOME/tools
ENV
chown "$RUNNER_USER:$RUNNER_USER" .env
./svc.sh install "$RUNNER_USER"
service=$(cat .service)
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
./svc.sh start
systemctl is-active "$service"
