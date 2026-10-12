#!/usr/bin/env bash
# Deploy the `production` branch to the VPS. Normally run by
# autodeploy.sh (every minute, via deploy/mnh-autodeploy.timer) after CI
# promotes main; also fine by hand, always from the root-owned copy:
#   sudo /usr/local/lib/mnh/deploy.sh                # production branch
#   sudo BRANCH=main /usr/local/lib/mnh/deploy.sh    # skip CI, for emergencies only
set -euo pipefail
umask 027

. "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/deploy_lib.sh"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

BRANCH="${BRANCH:-production}"
TARGET="${TARGET:-}"

if ! layout_is_current; then
    echo "This server predates the root-owned deploy layout; re-run scripts/vps_bootstrap.sh first." >&2
    exit 1
fi

install -d -m 700 -o root -g root "$STATE_DIR"
if [ "${MNH_DEPLOY_LOCK_HELD:-0}" != 1 ]; then
    exec 9>"$STATE_DIR/deploy.lock"
    flock -w 600 9 || { echo "another deploy is still running" >&2; exit 1; }
fi

cd "$APP_DIR"
work=$(mktemp -d)
sha=""
prev=""
prev_db=""
changing=""
migrated=""
system_files=""
restarted=""

rollback() {
    local back
    echo "deploy of $sha FAILED; rolling back to ${prev:-nothing}" >&2
    if [ -n "$migrated" ]; then
        if [ -n "$prev_db" ]; then
            as_mnh "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" downgrade "$prev_db" \
                || echo "database downgrade to $prev_db FAILED; restore the pre-deploy archive" >&2
        else
            echo "previous database revision unknown; check it with alembic current" >&2
        fi
    fi
    if [ -n "$prev" ]; then
        git_app checkout --quiet --force -B "$BRANCH" "$prev"
        git_app clean -ffdq
        fix_checkout_permissions
        as_mnh "$VENV/bin/pip" install -r "$APP_DIR/requirements.lock" --require-hashes -q
        if [ -n "$system_files" ]; then
            back=$(mktemp -d)
            render_system_files "$APP_DIR" "$back" && install_system_files "$back"
            rm -rf "$back"
        fi
        set_env_var DISCHARGE_GIT_SHA "$prev"
        if [ -n "$restarted" ]; then
            systemctl restart mnh
            wait_healthy "$prev" || echo "the previous version is not healthy either" >&2
        fi
    fi
    journalctl -u mnh --no-pager -n 40 >&2
}

finish() {
    local status=$?
    trap - EXIT INT TERM
    set +e
    if [ "$status" -ne 0 ] && [ -n "$changing" ]; then
        rollback
    fi
    rm -rf "$work"
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log "Fetch $BRANCH"
git_app fetch --quiet origin "$BRANCH"
sha=$(git_app rev-parse "${TARGET:-origin/$BRANCH}^{commit}")
if ! git_app merge-base --is-ancestor "$sha" "origin/$BRANCH"; then
    echo "$sha is not on origin/$BRANCH; refusing to deploy it" >&2
    exit 1
fi
verify_commit "$sha"
git_app log -1 --oneline "$sha"
prev=$(cat "$STATE_DIR/deployed" 2>/dev/null || git_app rev-parse HEAD)
prev_db=$(current_db_revision || true)

log "Validate service files from $sha"
mkdir -p "$work/src" "$work/staged"
git_app archive "$sha" deploy | tar -x -C "$work/src"
render_system_files "$work/src" "$work/staged"
validate_caddyfile "$work/staged/Caddyfile"

log "Pre-deploy backup"
if [ -z "$(find "$(backup_dir)" -maxdepth 1 -name 'discharge_backup_*.zip' -mmin -60 -print -quit 2>/dev/null)" ]; then
    systemctl start mnh-backup.service
else
    echo "recent archive exists; skipping"
fi

changing=1

log "Check out $sha"
git_app checkout --quiet --force -B "$BRANCH" "$sha"
git_app clean -ffdq
fix_checkout_permissions

log "Install locked dependencies (hash-checked)"
as_mnh "$VENV/bin/pip" install -r "$APP_DIR/requirements.lock" --require-hashes -q

log "Vulnerability audit"
as_mnh "$VENV/bin/pip-audit" -r "$APP_DIR/requirements.lock" --require-hashes --progress-spinner off

log "Database migration"
migrated=1
as_mnh "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
lock_down_data

log "Service files"
system_files=1
install_system_files "$work/staged"
set_env_var DISCHARGE_GIT_SHA "$sha"

log "Restart"
restarted=1
systemctl restart mnh

log "Health check"
wait_healthy "$sha"

printf '%s\n' "$sha" > "$STATE_DIR/deployed"
changing=""
install_deploy_scripts "$APP_DIR"
echo "deployed $sha"
