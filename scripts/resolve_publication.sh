#!/usr/bin/env bash
# Resolve an immutable data revision. Missing branch is the bootstrap state; network errors fail.
set -euo pipefail
requested=${REQUESTED_PUBLICATION:-}
if [ -n "$requested" ]; then
  [[ "$requested" =~ ^[0-9a-f]{40}$ ]] || { echo 'Publication revision must be a complete lowercase commit SHA.' >&2; exit 1; }
  printf '%s\n' "$requested"
  exit 0
fi
repository=${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY}
[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || exit 1
set +e
result=$(git -c http.lowSpeedLimit=1 -c http.lowSpeedTime=30 ls-remote --exit-code --heads "https://github.com/$repository.git" refs/heads/publication)
status=$?
set -e
case "$status" in
  0)
    [[ "$result" =~ ^([0-9a-f]{40})[[:space:]]refs/heads/publication$ ]] || exit 1
    printf '%s\n' "${BASH_REMATCH[1]}"
    ;;
  2) exit 0 ;;
  *) echo 'Could not resolve publication branch; refusing a bootstrap fallback.' >&2; exit "$status" ;;
esac
