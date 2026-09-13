#!/usr/bin/env bash
# Deploy the `production` branch to the VPS. Normally run by
# scripts/autodeploy.sh (every minute, via deploy/mnh-autodeploy.timer) after
# CI promotes main; also fine by hand:
#   sudo bash /srv/mnh/app/scripts/deploy.sh            # production branch
#   sudo BRANCH=main bash /srv/mnh/app/scripts/deploy.sh # skip CI, for emergencies only
#
# Order matters: snapshot, fetch + reset to the remote branch, install
# (hash-checked), audit, migrate, restart, health check. A failing step
# aborts before the service restarts, and the snapshot makes a bad migration
# a restore away. A lock stops a manual run colliding with the timer.
set -euo pipefail

APP_HOME=/srv/mnh
APP_DIR=$APP_HOME/app
VENV=$APP_HOME/.venv
DATA_DIR=$APP_HOME/data
BRANCH="${BRANCH:-production}"

exec 9>"$APP_HOME/deploy.lock"
flock -w 600 9 || { echo "another deploy is still running"; exit 1; }

as_mnh() { sudo -u mnh env DISCHARGE_ENV=production DISCHARGE_DATA_DIR="$DATA_DIR" "$@"; }
log() { printf '\n==> %s\n' "$*"; }

log "Pre-deploy backup"
# Skip if an archive was written in the last hour, so a burst of deploys
# does not push the nightly archives out of the 30-file retention window.
if [ -z "$(find "$DATA_DIR/backups" -maxdepth 1 -name 'discharge_backup_*.zip' -mmin -60 2>/dev/null | head -1)" ]; then
    as_mnh "$VENV/bin/python" "$APP_DIR/scripts/backup_now.py"
else
    echo "recent archive exists; skipping"
fi

log "Fetch $BRANCH"
sudo -u mnh git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
# The VPS never has local commits: make the checkout exactly the remote branch.
sudo -u mnh git -C "$APP_DIR" checkout --quiet -B "$BRANCH" "origin/$BRANCH"
sha=$(sudo -u mnh git -C "$APP_DIR" rev-parse HEAD)
sudo -u mnh git -C "$APP_DIR" log -1 --oneline

log "Install locked dependencies (hash-checked)"
sudo -u mnh "$VENV/bin/pip" install -r "$APP_DIR/requirements.lock" --require-hashes -q

log "Vulnerability audit"
sudo -u mnh "$VENV/bin/pip-audit" -r "$APP_DIR/requirements.lock" --require-hashes --progress-spinner off

log "Database migration"
as_mnh "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head

log "Refresh service files"
cp "$APP_DIR/deploy/mnh.service" "$APP_DIR/deploy/mnh-backup.service" \
   "$APP_DIR/deploy/mnh-backup.timer" "$APP_DIR/deploy/mnh-autodeploy.service" \
   "$APP_DIR/deploy/mnh-autodeploy.timer" /etc/systemd/system/
systemctl daemon-reload
# Record the commit for /api/health without needing git inside the sandboxed service.
grep -v '^DISCHARGE_GIT_SHA=' "$APP_HOME/mnh.env" > "$APP_HOME/mnh.env.new" || true
echo "DISCHARGE_GIT_SHA=$sha" >> "$APP_HOME/mnh.env.new"
install -m 600 -o mnh -g mnh "$APP_HOME/mnh.env.new" "$APP_HOME/mnh.env"
rm -f "$APP_HOME/mnh.env.new"

log "Restart"
systemctl restart mnh
sleep 3
systemctl --no-pager --lines=0 status mnh | head -3

log "Health check"
for i in 1 2 3 4 5 6; do
    body=$(curl -fsS http://127.0.0.1:8021/api/health || true)
    if printf '%s' "$body" | grep -q "\"version\":\"$sha\""; then
        echo "healthy, running $sha"; exit 0
    fi
    sleep 3
done
echo "Health check FAILED (got: ${body:-nothing}); recent log:" >&2
journalctl -u mnh --no-pager -n 40 >&2
exit 1
