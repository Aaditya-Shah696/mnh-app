#!/usr/bin/env bash
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: this builds /srv/mnh, /etc/mnh and /var/lib/mnh on a throwaway machine" >&2
    exit 2
fi
for path in /srv/mnh /etc/mnh /var/lib/mnh /usr/local/lib/mnh /srv/mnh-backups; do
    if [ -e "$path" ] && [ ! -e /srv/mnh/.deploy-pipeline-test ]; then
        echo "refusing to run: $path exists and is not from a previous test run" >&2
        exit 2
    fi
done
if (exec 3<>/dev/tcp/127.0.0.1/8021) 2>/dev/null; then
    echo "refusing to run: something already listens on 127.0.0.1:8021" >&2
    exit 2
fi
rm -rf /srv/mnh /etc/mnh /var/lib/mnh /usr/local/lib/mnh /srv/mnh-backups

WORK=$(mktemp -d)
stop_fake_app() {
    if [ -f "$WORK/app.pid" ]; then
        kill "$(cat "$WORK/app.pid")" 2>/dev/null || true
    fi
}
trap stop_fake_app EXIT
STUBS=$WORK/stubs
ORIGIN=$WORK/origin.git
SEED=$WORK/seed
LOGS=$WORK/logs
export PATH="$STUBS:$PATH"
mkdir -p "$STUBS" "$LOGS"

passed=0
failed=0
check() {
    local name=$1
    shift
    if "$@"; then
        printf 'PASS  %s\n' "$name"
        passed=$((passed + 1))
    else
        printf 'FAIL  %s\n' "$name"
        failed=$((failed + 1))
    fi
}

id mnh >/dev/null 2>&1 || useradd --system --user-group --home-dir /srv/mnh --shell /usr/sbin/nologin mnh
install -d -m 750 -o root -g mnh /srv/mnh
touch /srv/mnh/.deploy-pipeline-test
install -d -m 700 -o mnh -g mnh /srv/mnh/data /srv/mnh/.cache
install -d -m 755 -o mnh -g mnh /srv/mnh/.venv /srv/mnh/.venv/bin
install -d -m 700 -o root -g root /etc/mnh /var/lib/mnh
install -d -m 755 -o root -g root /srv/mnh-backups /usr/local/lib/mnh /etc/systemd/system /etc/caddy
install -d -m 750 -o mnh -g mnh /srv/mnh-backups/archives
install -m 600 /dev/null /etc/mnh/deploy_key
printf 'PUBLIC_HOST=test.example\n' > /etc/mnh/deploy.conf
printf 'DISCHARGE_BACKUP_DIR=/srv/mnh-backups/archives\n' > /srv/mnh/mnh.env
chmod 600 /srv/mnh/mnh.env
install -m 644 -o mnh -g mnh /dev/null /srv/mnh/data/discharge.db
printf 'r1\n' > /srv/mnh/data/alembic_rev
chown mnh:mnh /srv/mnh/data/alembic_rev

cat > /srv/mnh/.venv/bin/pip <<'EOF'
#!/bin/bash
printf 'pip %s\n' "$*" >> /srv/mnh/data/calls.log
if grep -qx 'pip=fail' /srv/mnh/app/simulate 2>/dev/null; then echo "simulated pip failure" >&2; exit 1; fi
if grep -qx 'pip=hang' /srv/mnh/app/simulate 2>/dev/null; then exec sleep 600; fi
exit 0
EOF
cat > /srv/mnh/.venv/bin/pip-audit <<'EOF'
#!/bin/bash
exit 0
EOF
cat > /srv/mnh/.venv/bin/alembic <<'EOF'
#!/bin/bash
rev_file=/srv/mnh/data/alembic_rev
args=("$@")
last=${args[-1]}
before=${args[-2]:-}
if [ "$last" = current ]; then
    printf '%s (head)\n' "$(cat "$rev_file")"
elif [ "$before" = upgrade ]; then
    target=$(sed -n 's/^migration=//p' /srv/mnh/app/simulate)
    [ -n "$target" ] && printf '%s\n' "$target" > "$rev_file"
    printf 'upgrade to %s\n' "${target:-unchanged}" >> /srv/mnh/data/calls.log
elif [ "$before" = downgrade ]; then
    printf '%s\n' "$last" > "$rev_file"
    printf 'downgrade to %s\n' "$last" >> /srv/mnh/data/calls.log
fi
EOF
chmod 755 /srv/mnh/.venv/bin/*

cat > "$WORK/fake_app.py" <<'EOF'
import http.server
import json
import sys

VERSION = sys.argv[1]


class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "ok", "version": VERSION}, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


http.server.HTTPServer(("127.0.0.1", 8021), Health).serve_forever()
EOF

cat > "$STUBS/systemctl" <<EOF
#!/bin/bash
printf '%s\n' "\$*" >> "$LOGS/systemctl.log"
case "\$1 \${2:-}" in
    "restart mnh")
        if [ -f "$WORK/app.pid" ]; then kill "\$(cat "$WORK/app.pid")" 2>/dev/null || true; sleep 0.3; fi
        version=\$(sed -n 's/^DISCHARGE_GIT_SHA=//p' /srv/mnh/mnh.env | tail -n 1)
        if grep -qx 'health=fail' /srv/mnh/app/simulate 2>/dev/null; then version=broken; fi
        nohup python3 "$WORK/fake_app.py" "\$version" >/dev/null 2>&1 8>&- 9>&- &
        echo \$! > "$WORK/app.pid"
        for _ in \$(seq 1 50); do curl -fsS http://127.0.0.1:8021/ >/dev/null 2>&1 && break; sleep 0.1; done
        ;;
    "start mnh-backup.service")
        sudo -u mnh sh -c 'umask 077 && : > /srv/mnh-backups/archives/discharge_backup_\$(date +%Y%m%d_%H%M%S).zip'
        ;;
esac
exit 0
EOF
cat > "$STUBS/journalctl" <<'EOF'
#!/bin/bash
echo "(journal)"
EOF
chmod 755 "$STUBS/systemctl" "$STUBS/journalctl"

git init --quiet --bare --initial-branch=main "$ORIGIN"
git init --quiet --initial-branch=main "$SEED"
git -C "$SEED" config user.name "Deploy Test"
git -C "$SEED" config user.email "deploy-test@example.com"
cp -r "$REPO/scripts" "$REPO/deploy" "$REPO/requirements.lock" "$REPO/alembic.ini" "$SEED/"
find "$SEED" -type f \( -name '*.sh' -o -name '*.service' -o -name '*.timer' -o -name '*.conf' -o -name Caddyfile \) \
    -exec sed -i 's/\r$//' {} +
git -C "$SEED" remote add origin "$ORIGIN"

commit() {
    local message=$1 simulate=$2
    shift 2
    printf '%b' "$simulate" > "$SEED/simulate"
    git -C "$SEED" add -A
    git -C "$SEED" commit --quiet --allow-empty "$@" -m "$message"
    git -C "$SEED" rev-parse HEAD
}
publish() {
    git -C "$SEED" push --quiet --force origin "HEAD:refs/heads/$1"
}

v1=$(commit "v1" 'migration=r1\n')
publish main
publish production
git clone --quiet --branch production "$ORIGIN" /srv/mnh/app
. /srv/mnh/app/scripts/deploy_lib.sh
fix_checkout_permissions
install_deploy_scripts /srv/mnh/app
set_env_var DISCHARGE_GIT_SHA "$v1"
printf '%s\n' "$v1" > /var/lib/mnh/deployed
systemctl restart mnh

health() { curl -fsS http://127.0.0.1:8021/api/health; }
head_is() { [ "$(git -C /srv/mnh/app rev-parse HEAD)" = "$1" ]; }
health_is() { health | grep -q "\"version\":\"$1\""; }
state_is() { [ "$(cat "/var/lib/mnh/$1" 2>/dev/null)" = "$2" ]; }
rev_is() { [ "$(cat /srv/mnh/data/alembic_rev)" = "$1" ]; }
env_sha_is() { grep -qx "DISCHARGE_GIT_SHA=$1" /srv/mnh/mnh.env; }
called() { grep -qx "$1" /srv/mnh/data/calls.log; }
mnh_cannot() { ! sudo -u mnh "$@" >/dev/null 2>&1; }
restarts() { grep -cx 'restart mnh' "$LOGS/systemctl.log" || true; }
autodeploy() { /usr/local/lib/mnh/autodeploy.sh > "$LOGS/autodeploy.out" 2>&1; }

echo "== good release"
v2=$(commit "v2" 'migration=r2\n')
publish production
check "autodeploy succeeds" autodeploy
check "checkout is v2" head_is "$v2"
check "app reports v2" health_is "$v2"
check "deployed state is v2" state_is deployed "$v2"
check "production.seen is v2" state_is production.seen "$v2"
check "schema migrated to r2" rev_is r2
check "env file carries v2" env_sha_is "$v2"
check "pre-deploy backup written" test -n "$(ls /srv/mnh-backups/archives)"
check "database file is owner-only" test "$(stat -c %a /srv/mnh/data/discharge.db)" = 600
check "checkout owned by root:mnh" test "$(stat -c %U:%G /srv/mnh/app/scripts/deploy.sh)" = root:mnh
check "app user cannot modify the checkout" mnh_cannot touch /srv/mnh/app/scripts/deploy.sh
check "app user cannot read the deploy key" mnh_cannot cat /etc/mnh/deploy_key
check "root runs refreshed copies of the scripts" cmp -s /usr/local/lib/mnh/deploy.sh /srv/mnh/app/scripts/deploy.sh
check "Caddyfile rendered for PUBLIC_HOST" grep -q '^test.example {' /etc/caddy/Caddyfile

echo "== dependency install fails before migration"
before=$(restarts)
v3=$(commit "v3" 'migration=r3\npip=fail\n')
publish production
check "autodeploy reports failure" bash -c '! /usr/local/lib/mnh/autodeploy.sh >/dev/null 2>&1'
check "failed state is v3" state_is failed "$v3"
check "deployed state still v2" state_is deployed "$v2"
check "checkout rolled back to v2" head_is "$v2"
check "app still reports v2" health_is "$v2"
check "schema untouched" rev_is r2
check "service was not restarted" test "$(restarts)" = "$before"
check "a failed commit is not retried" autodeploy
check "retry made no attempt" bash -c "! grep -q deploying '$LOGS/autodeploy.out'"

echo "== health check fails after migration"
v4=$(commit "v4" 'migration=r4\nhealth=fail\n')
publish production
check "autodeploy reports failure" bash -c '! /usr/local/lib/mnh/autodeploy.sh >/dev/null 2>&1'
check "schema downgraded back to r2" called "downgrade to r2"
check "schema is r2" rev_is r2
check "checkout rolled back to v2" head_is "$v2"
check "env file back to v2" env_sha_is "$v2"
check "app restarted on v2 and healthy" health_is "$v2"
check "failed state is v4" state_is failed "$v4"
check "deployed state still v2" state_is deployed "$v2"

echo "== invalid Caddyfile is refused before anything changes"
before=$(restarts)
sed -i 's/^    encode zstd gzip$/    encode zstd gzip\n    bogus_directive on/' "$SEED/deploy/Caddyfile"
grep -q bogus_directive "$SEED/deploy/Caddyfile"
v5=$(commit "v5" 'migration=r5\n')
git -C "$SEED" checkout --quiet HEAD~1 -- deploy/Caddyfile
publish production
check "autodeploy reports failure" bash -c '! /usr/local/lib/mnh/autodeploy.sh >/dev/null 2>&1'
check "checkout never left v2" head_is "$v2"
check "installed Caddyfile unchanged" bash -c "! grep -q bogus_directive /etc/caddy/Caddyfile"
check "no restart" test "$(restarts)" = "$before"
check "failed state is v5" state_is failed "$v5"

echo "== the next good release deploys"
v6=$(commit "v6" 'migration=r6\n')
publish production
check "autodeploy succeeds" autodeploy
check "app reports v6" health_is "$v6"
check "failed state cleared" test ! -e /var/lib/mnh/failed

echo "== emergency deploy of main is not reverted"
v7=$(commit "v7" 'migration=r7\n')
publish main
check "manual BRANCH=main deploy succeeds" env BRANCH=main /usr/local/lib/mnh/deploy.sh
check "app reports v7" health_is "$v7"
before=$(restarts)
check "autodeploy run succeeds" autodeploy
check "still running v7" health_is "$v7"
check "autodeploy did not redeploy" test "$(restarts)" = "$before"
publish production
check "production catches up" autodeploy
check "no redeploy of the already-running commit" test "$(restarts)" = "$before"
check "production.seen is v7" state_is production.seen "$v7"

echo "== a deploy running too long is interrupted and rolled back"
v8=$(commit "v8" 'migration=r8\npip=hang\n')
publish production
check "deploy is stopped" bash -c "! MNH_DEPLOY_LOCK_HELD=0 TARGET=$v8 timeout -k 20 5 /usr/local/lib/mnh/deploy.sh >/dev/null 2>&1"
check "checkout rolled back to v7" head_is "$v7"
check "deployed state still v7" state_is deployed "$v7"
check "app still reports v7" health_is "$v7"

echo "== a running deploy holds off autodeploy"
exec 8>/var/lib/mnh/deploy.lock
flock 8
check "autodeploy backs off" autodeploy
check "and says why" grep -q "already running" "$LOGS/autodeploy.out"
flock -u 8
exec 8>&-
printf '%s\n' "$v8" > /var/lib/mnh/failed

echo "== signed commits only, once allowed_signers exists"
ssh-keygen -q -t ed25519 -N "" -C trusted -f "$WORK/trusted"
ssh-keygen -q -t ed25519 -N "" -C stranger -f "$WORK/stranger"
printf 'deploy-test@example.com namespaces="git" %s\n' "$(cat "$WORK/trusted.pub")" > /etc/mnh/allowed_signers
v9=$(commit "v9 unsigned" 'migration=r9\n')
publish production
check "unsigned commit refused" bash -c '! /usr/local/lib/mnh/autodeploy.sh >/dev/null 2>&1'
check "unsigned commit recorded as failed" state_is failed "$v9"
check "still running v7" health_is "$v7"
signed_commit() {
    local message=$1 simulate=$2 key=$3
    printf '%b' "$simulate" > "$SEED/simulate"
    git -C "$SEED" add -A
    git -C "$SEED" -c gpg.format=ssh -c user.signingkey="$key" commit --quiet --allow-empty -S -m "$message"
    git -C "$SEED" rev-parse HEAD
}
signed_commit "v10 stranger" 'migration=r10\n' "$WORK/stranger" >/dev/null
publish production
check "commit signed by an unknown key refused" bash -c '! /usr/local/lib/mnh/autodeploy.sh >/dev/null 2>&1'
check "still running v7" health_is "$v7"
v11=$(signed_commit "v11 trusted" 'migration=r11\n' "$WORK/trusted")
publish production
check "commit signed by the trusted key deploys" autodeploy
check "app reports v11" health_is "$v11"
rm -f /etc/mnh/allowed_signers

echo "== an old-layout server is refused until bootstrap is re-run"
chown mnh /srv/mnh/app
check "deploy refuses" bash -c '! /usr/local/lib/mnh/deploy.sh >/dev/null 2>&1'
check "and says what to do" bash -c '/usr/local/lib/mnh/deploy.sh 2>&1 | grep -q vps_bootstrap.sh'
chown root /srv/mnh/app

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
