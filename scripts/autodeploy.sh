#!/usr/bin/env bash
# Pull-based continuous deployment. Run by deploy/mnh-autodeploy.timer every
# minute as root. Fetches the `production` branch (which CI fast-forwards
# only after the tests pass) and runs scripts/deploy.sh when it moved.
#
# A commit whose deploy failed is not retried every minute: its SHA is
# remembered in $STATE and skipped until production moves again. Fix
# forward by pushing a new commit, or run deploy.sh by hand.
set -euo pipefail

APP_HOME=/srv/mnh
APP_DIR=$APP_HOME/app
STATE=$APP_HOME/autodeploy.state
BRANCH="${BRANCH:-production}"

git_mnh() { sudo -u mnh git -C "$APP_DIR" "$@"; }

if ! git_mnh fetch --quiet origin "$BRANCH" 2>/tmp/autodeploy.fetch.err; then
    echo "fetch failed: $(tail -1 /tmp/autodeploy.fetch.err)" >&2
    exit 0   # transient network trouble; the timer tries again in a minute
fi

want=$(git_mnh rev-parse "origin/$BRANCH")
have=$(git_mnh rev-parse HEAD)

if [ "$want" = "$have" ]; then
    exit 0
fi

last_failed=$(cat "$STATE" 2>/dev/null || true)
if [ "$want" = "$last_failed" ]; then
    echo "skipping $want: its last deploy failed; push a new commit or run deploy.sh manually" >&2
    exit 0
fi

echo "production moved $have -> $want; deploying"
if BRANCH="$BRANCH" bash "$APP_DIR/scripts/deploy.sh"; then
    rm -f "$STATE"
    echo "deployed $want"
else
    echo "$want" > "$STATE"
    echo "deploy of $want FAILED; recorded in $STATE" >&2
    exit 1
fi
