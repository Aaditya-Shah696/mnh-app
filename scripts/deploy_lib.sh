#!/usr/bin/env bash

APP_HOME=/srv/mnh
APP_DIR=$APP_HOME/app
VENV=$APP_HOME/.venv
DATA_DIR=$APP_HOME/data
ENV_FILE=$APP_HOME/mnh.env
CONF_DIR=/etc/mnh
STATE_DIR=/var/lib/mnh
LIB_DIR=/usr/local/lib/mnh
BACKUP_ROOT=/srv/mnh-backups
BACKUP_DIR=$BACKUP_ROOT/archives
DEPLOY_KEY=$CONF_DIR/deploy_key
KNOWN_HOSTS=$CONF_DIR/known_hosts
ALLOWED_SIGNERS=$CONF_DIR/allowed_signers
UNITS=(mnh.service mnh-backup.service mnh-backup.timer mnh-autodeploy.service mnh-autodeploy.timer)
TIMERS=(mnh-backup.timer mnh-autodeploy.timer)
DEPLOY_SCRIPTS=(deploy_lib.sh deploy.sh autodeploy.sh)

log() { printf '\n==> %s\n' "$*"; }

git_app() {
    GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes -o BatchMode=yes" \
        git -C "$APP_DIR" "$@"
}

env_value() {
    local key=$1
    if [ -f "$ENV_FILE" ]; then
        sed -n "s/^$key=//p" "$ENV_FILE" | tail -n 1
    fi
}

set_env_var() {
    local key=$1 value=$2 tmp
    tmp=$(mktemp "$APP_HOME/.mnh.env.XXXXXX")
    if [ -f "$ENV_FILE" ]; then
        grep -v "^$key=" "$ENV_FILE" > "$tmp" || true
    fi
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
    chown root:root "$tmp"
    chmod 600 "$tmp"
    mv -f "$tmp" "$ENV_FILE"
}

backup_dir() {
    local dir
    dir=$(env_value DISCHARGE_BACKUP_DIR)
    printf '%s\n' "${dir:-$DATA_DIR/backups}"
}

as_mnh() {
    local backups
    backups=$(backup_dir)
    sudo -u mnh env DISCHARGE_ENV=production DISCHARGE_DATA_DIR="$DATA_DIR" \
        DISCHARGE_BACKUP_DIR="$backups" sh -c 'umask 077 && exec "$@"' as_mnh "$@"
}

public_host() {
    local host=""
    if [ -f "$CONF_DIR/deploy.conf" ]; then
        host=$(sed -n 's/^PUBLIC_HOST=//p' "$CONF_DIR/deploy.conf" | tail -n 1)
    fi
    host=${host:-mnhapp.org}
    if ! [[ $host =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
        echo "invalid PUBLIC_HOST '$host' in $CONF_DIR/deploy.conf" >&2
        return 1
    fi
    printf '%s\n' "$host"
}

layout_is_current() {
    [ -f "$DEPLOY_KEY" ] && [ -d "$LIB_DIR" ] && [ "$(stat -c %U "$APP_DIR")" = root ]
}

fix_checkout_permissions() {
    chown -R root:mnh "$APP_DIR"
    chmod -R u+rwX,g+rX,g-w,o-rwx "$APP_DIR"
    find "$APP_DIR" -type d -exec chmod g+s {} +
}

lock_down_data() {
    chmod 700 "$DATA_DIR"
    find "$DATA_DIR" -xdev -mindepth 1 \( -type f -o -type d \) -exec chmod go-rwx {} +
}

verify_commit() {
    local sha=$1
    if [ -s "$ALLOWED_SIGNERS" ]; then
        if ! git_app -c gpg.ssh.allowedSignersFile="$ALLOWED_SIGNERS" verify-commit "$sha" >/dev/null 2>&1; then
            echo "commit $sha is not signed by a key in $ALLOWED_SIGNERS; refusing to deploy it" >&2
            return 1
        fi
        echo "signature on $sha verified"
    else
        echo "WARNING: $ALLOWED_SIGNERS is missing, so $sha is deployed without a signature check" >&2
    fi
}

current_db_revision() {
    as_mnh "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" current 2>/dev/null | awk 'NR == 1 { print $1 }'
}

render_system_files() {
    local src=$1 out=$2 host unit
    host=$(public_host)
    for unit in "${UNITS[@]}"; do
        sed 's/\r$//' "$src/deploy/$unit" > "$out/$unit"
    done
    sed "s/mnhapp\.org/$host/g; s/\r$//" "$src/deploy/Caddyfile" > "$out/Caddyfile"
}

validate_caddyfile() {
    local candidate=$1 copy out status=0
    install -d -m 755 -o caddy -g caddy /var/log/caddy
    copy=$(mktemp)
    install -m 640 -o root -g caddy "$candidate" "$copy"
    out=$(runuser -u caddy -- env HOME=/var/lib/caddy XDG_DATA_HOME= XDG_CONFIG_HOME= \
        caddy validate --config "$copy" --adapter caddyfile 2>&1) || status=$?
    rm -f "$copy"
    if [ "$status" -ne 0 ]; then
        printf '%s\n' "$out" | tail -n 20 >&2
        echo "the Caddyfile does not validate; nothing was installed" >&2
        return 1
    fi
}

install_system_files() {
    local staged=$1 unit units_changed=0 timers_changed=0 caddy_changed=0
    for unit in "${UNITS[@]}"; do
        if ! cmp -s "$staged/$unit" "/etc/systemd/system/$unit"; then
            install -m 644 -o root -g root "$staged/$unit" "/etc/systemd/system/$unit"
            units_changed=1
            case $unit in *.timer) timers_changed=1 ;; esac
        fi
    done
    if ! cmp -s "$staged/Caddyfile" /etc/caddy/Caddyfile; then
        install -m 644 -o root -g root "$staged/Caddyfile" /etc/caddy/Caddyfile
        caddy_changed=1
    fi
    if [ "$units_changed" -eq 1 ]; then
        systemctl daemon-reload
    fi
    if [ "$timers_changed" -eq 1 ]; then
        systemctl restart "${TIMERS[@]}"
    fi
    if [ "$caddy_changed" -eq 1 ]; then
        systemctl restart caddy
    fi
}

install_deploy_scripts() {
    local src=$1 script
    install -d -m 755 -o root -g root "$LIB_DIR"
    for script in "${DEPLOY_SCRIPTS[@]}"; do
        sed 's/\r$//' "$src/scripts/$script" > "$LIB_DIR/.$script.new"
        chown root:root "$LIB_DIR/.$script.new"
        chmod 755 "$LIB_DIR/.$script.new"
        mv -f "$LIB_DIR/.$script.new" "$LIB_DIR/$script"
    done
}

wait_healthy() {
    local sha=$1 body="" attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        body=$(curl -fsS --max-time 5 http://127.0.0.1:8021/api/health 2>/dev/null || true)
        if printf '%s' "$body" | grep -q "\"version\":\"$sha\""; then
            echo "healthy, running $sha"
            return 0
        fi
        sleep 3
    done
    echo "health check failed after $attempt attempts (got: ${body:-nothing})" >&2
    return 1
}
