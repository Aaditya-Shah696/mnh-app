#!/usr/bin/env bash
# One-time build of the MNH Discharge Records VPS (Ubuntu 24.04, Namecheap).
#
# Run ONCE as root from the fresh server, then never use root again:
#   curl -fsSL <raw url of this file> -o vps_bootstrap.sh
#   sudo bash vps_bootstrap.sh
#
# Idempotent: safe to re-run. Every step prints what it is doing.
#
# Required environment (export before running, or edit the defaults):
#   ADMIN_USER      sudo user for Aaditya (default: aaditya)
#   ADMIN_SSH_KEY   the public key line for ADMIN_USER (REQUIRED)
#   REPO_URL        git URL of this repository (default: git@github.com:Aaditya-Shah696/mnh-app.git)
#   PUBLIC_HOST     the hostname Caddy will serve (default: mnhapp.org)
#
# The repository is private, so root clones it with a read-only GitHub deploy
# key. On the first run the script generates that key, prints it, and stops;
# add it at https://github.com/Aaditya-Shah696/mnh-app/settings/keys
# (read-only is enough) and re-run the script. Every later run is quiet.
#
# After it finishes:
#   1. Point the DNS A record for PUBLIC_HOST at this server.
#   2. `sudo tailscale up` and approve the machine in the Tailscale admin.
#   3. Confirm you can SSH in over the tailnet as ADMIN_USER, THEN run
#      scripts/lockdown_ssh.sh to close public SSH.
#   4. Create the first admin (see docs/RUNBOOK.md).
set -euo pipefail
umask 022

ADMIN_USER="${ADMIN_USER:-aaditya}"
ADMIN_SSH_KEY="${ADMIN_SSH_KEY:?set ADMIN_SSH_KEY to the admin public key line}"
REPO_URL="${REPO_URL:-git@github.com:Aaditya-Shah696/mnh-app.git}"
PUBLIC_HOST="${PUBLIC_HOST:-mnhapp.org}"
PULL_SSH_KEY="${PULL_SSH_KEY:-}"
DEPLOY_SIGNERS="${DEPLOY_SIGNERS:-}"

APP_HOME=/srv/mnh
APP_DIR=$APP_HOME/app
CONF_DIR=/etc/mnh
DEPLOY_KEY=$CONF_DIR/deploy_key
KNOWN_HOSTS=$CONF_DIR/known_hosts
GITHUB_HOST_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"

log() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
if ! [[ $PUBLIC_HOST =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
    echo "PUBLIC_HOST '$PUBLIC_HOST' is not a hostname"; exit 1
fi

log "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git ufw fail2ban python3-systemd acl \
    unattended-upgrades apt-listchanges curl ca-certificates gnupg \
    debian-keyring debian-archive-keyring apt-transport-https

log "Caddy (official repo)"
if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q && apt-get install -y -q caddy
fi

log "Tailscale (admin SSH plane)"
if ! command -v tailscale >/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

log "DNS: public resolvers (provider resolvers collide with the Tailscale range)"
# Namecheap's image configures eth0 statically in /etc/network/interfaces with
# resolvers at 100.100.100.x, inside 100.64.0.0/10 which Tailscale routes into
# the tailnet; once Tailscale is up they are unreachable and git/apt/ACME fail
# with "Temporary failure in name resolution". Use public resolvers everywhere
# the image could pick DNS up from, and hand /etc/resolv.conf to systemd-resolved.
if [ -f /etc/network/interfaces ]; then
    sed -i 's/^\(\s*\)dns-nameservers .*/\1dns-nameservers 1.1.1.1 8.8.8.8/' /etc/network/interfaces
fi
if [ -f /etc/dhcp/dhclient.conf ] && ! grep -q '^supersede domain-name-servers' /etc/dhcp/dhclient.conf; then
    echo 'supersede domain-name-servers 1.1.1.1, 8.8.8.8;' >> /etc/dhcp/dhclient.conf
fi
install -d /etc/systemd/resolved.conf.d
cat > /etc/systemd/resolved.conf.d/10-public-dns.conf <<'EOF'
[Resolve]
DNS=1.1.1.1 8.8.8.8
FallbackDNS=9.9.9.9
Domains=~.
EOF
systemctl enable --now systemd-resolved >/dev/null 2>&1 || true
systemctl restart systemd-resolved
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
resolvectl flush-caches || true
# And never let Tailscale replace the system resolver on this box.
command -v tailscale >/dev/null && tailscale set --accept-dns=false >/dev/null 2>&1 || true
getent hosts github.com >/dev/null || { echo "DNS still broken after fix; aborting" >&2; exit 1; }

log "Automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

log "Admin user $ADMIN_USER (sudo, key-only)"
if ! id "$ADMIN_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$ADMIN_USER"
fi
usermod -aG sudo "$ADMIN_USER"
install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "/home/$ADMIN_USER/.ssh"
grep -qxF "$ADMIN_SSH_KEY" "/home/$ADMIN_USER/.ssh/authorized_keys" 2>/dev/null \
    || echo "$ADMIN_SSH_KEY" >> "/home/$ADMIN_USER/.ssh/authorized_keys"
chmod 600 "/home/$ADMIN_USER/.ssh/authorized_keys"
chown "$ADMIN_USER:$ADMIN_USER" "/home/$ADMIN_USER/.ssh/authorized_keys"
# The admin has no password (key-only login), so sudo must not ask for one.
echo "$ADMIN_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$ADMIN_USER"
chmod 440 "/etc/sudoers.d/90-$ADMIN_USER"
visudo -cf "/etc/sudoers.d/90-$ADMIN_USER" >/dev/null

log "Firewall: 80/443 public, SSH over the tailnet only"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0 to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
# Only close public SSH once the tailnet is actually joined; otherwise this
# script would lock out the person running it. Until then SSH stays public
# but key-only, watched by fail2ban. scripts/lockdown_ssh.sh finishes the job.
if tailscale ip -4 >/dev/null 2>&1 && [ -n "$(tailscale ip -4 2>/dev/null)" ]; then
    echo "tailnet joined: SSH restricted to tailscale0"
else
    ufw allow 22/tcp comment 'TEMPORARY public SSH until tailscale up; remove with scripts/lockdown_ssh.sh'
    echo "tailnet NOT joined yet: public SSH left open (key-only). After 'sudo tailscale up' works, run: sudo bash $APP_DIR/scripts/lockdown_ssh.sh"
fi
ufw --force enable

log "SSH hardening: no root login, no passwords"
sudo -u "$ADMIN_USER" sudo -n true || { echo "admin user cannot sudo; refusing to disable root login"; exit 1; }
rm -f /etc/ssh/sshd_config.d/90-mnh.conf
cat > /etc/ssh/sshd_config.d/00-mnh.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
chmod 644 /etc/ssh/sshd_config.d/00-mnh.conf
install -d -m 755 /run/sshd
sshd -t
effective=$(sshd -T)
for want in "permitrootlogin no" "passwordauthentication no" "kbdinteractiveauthentication no" "pubkeyauthentication yes"; do
    if ! grep -qx "$want" <<<"$effective"; then
        echo "sshd's effective config does not have '$want'; another file in /etc/ssh overrides it" >&2
        exit 1
    fi
done
systemctl restart ssh

log "Application user and directories"
if ! id mnh >/dev/null 2>&1; then
    adduser --system --group --home "$APP_HOME" --shell /usr/sbin/nologin mnh
fi
install -d -m 750 -o root -g mnh "$APP_HOME"
install -d -m 700 -o mnh -g mnh "$APP_HOME/data" "$APP_HOME/.cache"
install -d -m 750 -o mnh -g mnh "$APP_HOME/.venv"
install -d -m 700 -o root -g root "$CONF_DIR" /var/lib/mnh
printf 'PUBLIC_HOST=%s\n' "$PUBLIC_HOST" > "$CONF_DIR/deploy.conf"
chmod 600 "$CONF_DIR/deploy.conf"
if [ -n "$DEPLOY_SIGNERS" ]; then
    printf '%s\n' "$DEPLOY_SIGNERS" > "$CONF_DIR/allowed_signers"
    chmod 644 "$CONF_DIR/allowed_signers"
fi

log "Deploy key for the private repository (root-only; the app user has no repository access)"
if [ ! -f "$DEPLOY_KEY" ]; then
    if [ -f "$APP_HOME/.ssh/id_ed25519" ]; then
        install -m 600 -o root -g root "$APP_HOME/.ssh/id_ed25519" "$DEPLOY_KEY"
        install -m 644 -o root -g root "$APP_HOME/.ssh/id_ed25519.pub" "$DEPLOY_KEY.pub"
    else
        ssh-keygen -q -t ed25519 -N "" -C "mnh-vps deploy key" -f "$DEPLOY_KEY"
    fi
fi
rm -f "$APP_HOME/.ssh/id_ed25519" "$APP_HOME/.ssh/id_ed25519.pub" "$APP_HOME/.ssh/known_hosts" \
    "$APP_HOME/deploy.lock" "$APP_HOME/autodeploy.state"
rmdir "$APP_HOME/.ssh" 2>/dev/null || true
printf 'github.com %s\n' "$GITHUB_HOST_KEY" > "$KNOWN_HOSTS"
chmod 644 "$KNOWN_HOSTS"

log "Code checkout (root-owned, readable by the app user)"
export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes -o BatchMode=yes"
if [ ! -d "$APP_DIR/.git" ]; then
    if ! clone_output=$(git clone --quiet "$REPO_URL" "$APP_DIR" 2>&1); then
        echo
        echo "Clone of $REPO_URL failed: ${clone_output##*$'\n'}"
        echo "Add this READ-ONLY deploy key to the repository, then re-run this script:"
        echo "  https://github.com/Aaditya-Shah696/mnh-app/settings/keys"
        echo
        cat "$DEPLOY_KEY.pub"
        echo
        exit 1
    fi
fi
chown -R root:mnh "$APP_DIR"
git -C "$APP_DIR" remote set-url origin "$REPO_URL"
# Serve the CI-promoted `production` branch when it exists; until the first
# green CI run on main it does not, and main is used for the initial build.
git -C "$APP_DIR" fetch --quiet origin
if git -C "$APP_DIR" rev-parse --verify --quiet origin/production >/dev/null; then
    git -C "$APP_DIR" checkout --quiet --force -B production origin/production
else
    git -C "$APP_DIR" checkout --quiet --force -B main origin/main
fi
unset GIT_SSH_COMMAND

. "$APP_DIR/scripts/deploy_lib.sh"
fix_checkout_permissions
cd "$APP_DIR"

log "Python virtualenv + locked dependencies (hash-checked)"
[ -x "$VENV/bin/python" ] || as_mnh python3 -m venv "$VENV"
as_mnh "$VENV/bin/pip" install --upgrade pip -q
as_mnh "$VENV/bin/pip" install -r "$APP_DIR/requirements.lock" --require-hashes -q

log "Backup archives (separate from the database) and the SFTP-only pull user"
if ! id mnhpull >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" --shell /usr/sbin/nologin mnhpull
fi
if [ "$(getent passwd mnhpull | cut -d: -f7)" != /usr/sbin/nologin ]; then
    usermod --shell /usr/sbin/nologin mnhpull
fi
install -d -m 755 -o root -g root "$BACKUP_ROOT"
install -d -m 750 -o mnh -g mnh "$BACKUP_DIR"
if [ -d "$DATA_DIR/backups" ]; then
    find "$DATA_DIR/backups" -maxdepth 1 -type f -name 'discharge_backup_*.zip' \
        -exec mv -n -t "$BACKUP_DIR" {} +
    rm -f "$DATA_DIR/backups/.db_snapshot.tmp"
    rmdir "$DATA_DIR/backups" 2>/dev/null || echo "left $DATA_DIR/backups in place: it still holds other files"
fi
setfacl -b "$APP_HOME"
setfacl -R -b "$DATA_DIR"
setfacl -m u:mnhpull:rx "$BACKUP_DIR"
setfacl -d -m u:mnhpull:r "$BACKUP_DIR"
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'discharge_backup_*.zip' -exec setfacl -m u:mnhpull:r {} +
install -d -m 700 -o mnhpull -g mnhpull /home/mnhpull/.ssh
PULL_KEYS=/home/mnhpull/.ssh/authorized_keys
if [ -n "$PULL_SSH_KEY" ] && ! grep -qF "$PULL_SSH_KEY" "$PULL_KEYS" 2>/dev/null; then
    printf 'restrict %s\n' "$PULL_SSH_KEY" >> "$PULL_KEYS"
fi
if [ -f "$PULL_KEYS" ]; then
    chown mnhpull:mnhpull "$PULL_KEYS"
    chmod 600 "$PULL_KEYS"
else
    echo "No pull key installed yet: re-run with PULL_SSH_KEY set to the clinic PC's mnh_pull.pub line."
fi
sed -i '/^Match User mnhpull$/,$d' /etc/ssh/sshd_config
if [ -n "$(tail -c 1 /etc/ssh/sshd_config)" ]; then
    echo >> /etc/ssh/sshd_config
fi
sed 's/\r$//' "$APP_DIR/deploy/sshd/mnhpull.conf" >> /etc/ssh/sshd_config
sshd -t
pull_config=$(sshd -T -C user=mnhpull,host=clinic-pc,addr=100.64.0.1)
for want in "chrootdirectory $BACKUP_ROOT" "forcecommand internal-sftp -R -d /archives" \
    "passwordauthentication no" "allowtcpforwarding no" "permittty no"; do
    if ! grep -qx "$want" <<<"$pull_config"; then
        echo "sshd's effective config for mnhpull does not have '$want'" >&2
        exit 1
    fi
done
systemctl restart ssh

log "Environment file"
if [ -z "$(env_value DISCHARGE_PUBLIC_ORIGIN)" ]; then
    set_env_var DISCHARGE_PUBLIC_ORIGIN "https://$PUBLIC_HOST"
fi
set_env_var DISCHARGE_BACKUP_DIR "$BACKUP_DIR"

log "Swap (the embedding model load spikes memory on a 2 GB box)"
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "Database schema (owner-only files)"
as_mnh "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
lock_down_data

log "systemd units, Caddy, deploy scripts"
staged=$(mktemp -d)
render_system_files "$APP_DIR" "$staged"
validate_caddyfile "$staged/Caddyfile"
install_system_files "$staged"
rm -rf "$staged"
install_deploy_scripts "$APP_DIR"
systemctl daemon-reload
systemctl enable --now caddy mnh mnh-backup.timer mnh-autodeploy.timer
systemctl restart caddy mnh

log "fail2ban"
# The stock sshd jail bans the address running this script after a few key
# refusals during setup; whitelist it and lift any ban already in place.
ADMIN_IP="${SSH_CLIENT:-}"
ADMIN_IP="${ADMIN_IP%% *}"
if [ -n "$ADMIN_IP" ]; then
    printf '[DEFAULT]\nignoreip = 127.0.0.1/8 ::1 %s\n' "$ADMIN_IP" > /etc/fail2ban/jail.d/00-ignore-admin.conf
fi
sed 's/\r$//' "$APP_DIR/deploy/fail2ban/jail.d/mnh.conf" > /etc/fail2ban/jail.d/mnh.conf
sed 's/\r$//' "$APP_DIR/deploy/fail2ban/filter.d/mnh-login.conf" > /etc/fail2ban/filter.d/mnh-login.conf
rm -f /etc/fail2ban/filter.d/caddy-login.conf
fail2ban-client --test >/dev/null
systemctl enable fail2ban
systemctl restart fail2ban

cat <<EOF

Done. Next:
  1. DNS: A record  $PUBLIC_HOST -> $(curl -fsS https://api.ipify.org || echo '<this server IP>')
  2. sudo tailscale up            (approve the machine, then test SSH over the tailnet as $ADMIN_USER)
  3. First admin:
     cd $APP_DIR && sudo -u mnh env DISCHARGE_DATA_DIR=$DATA_DIR $VENV/bin/python scripts/create_user.py --admin --username <name> --display-name "<Name>"
  4. curl -fsS http://127.0.0.1:8021/api/health   -> {"status":"ok"}
  5. https://$PUBLIC_HOST  from a phone: login page with a padlock.
EOF
