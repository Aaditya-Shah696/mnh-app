#!/usr/bin/env bash
# Pull-based continuous deployment. Run by deploy/mnh-autodeploy.timer every
# minute as root, from the root-owned copy in /usr/local/lib/mnh. Fetches the
# `production` branch (which CI fast-forwards only after the tests pass) and
# runs deploy.sh when it moved.
set -euo pipefail
umask 027

. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/deploy_lib.sh"

BRANCH=production

install -d -m 700 -o root -g root "$STATE_DIR"
exec 9>"$STATE_DIR/deploy.lock"
if ! flock -n 9; then
    echo "a deploy is already running; checking again next minute"
    exit 0
fi

if ! out=$(git_app fetch --quiet origin "$BRANCH" 2>&1); then
    echo "fetch failed: ${out##*$'\n'}" >&2
    exit 0
fi

want=$(git_app rev-parse "origin/$BRANCH^{commit}")
seen=$(cat "$STATE_DIR/production.seen" 2>/dev/null || true)
if [ "$want" = "$seen" ]; then
    exit 0
fi

deployed=$(cat "$STATE_DIR/deployed" 2>/dev/null || true)
if [ "$want" = "$deployed" ]; then
    printf '%s\n' "$want" > "$STATE_DIR/production.seen"
    exit 0
fi

failed=$(cat "$STATE_DIR/failed" 2>/dev/null || true)
if [ "$want" = "$failed" ]; then
    exit 0
fi

echo "production moved to $want; deploying"
if MNH_DEPLOY_LOCK_HELD=1 BRANCH="$BRANCH" TARGET="$want" \
    timeout -k 5m 40m "$LIB_DIR/deploy.sh"; then
    printf '%s\n' "$want" > "$STATE_DIR/production.seen"
    rm -f "$STATE_DIR/failed"
    echo "deployed $want"
else
    printf '%s\n' "$want" > "$STATE_DIR/failed"
    echo "deploy of $want FAILED and was rolled back; it is not retried until production moves." >&2
    exit 1
fi
