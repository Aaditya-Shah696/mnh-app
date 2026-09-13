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
#   PUBLIC_HOST     the hostname Caddy will serve (default: mnhapp.app)
#
# The repository is private, so the `mnh` user clones it with a read-only
# GitHub deploy key. On the first run the script generates that key, prints
# it, and stops; add it at https://github.com/Aaditya-Shah696/mnh-app/settings/keys
# (read-only is enough) and re-run the script. Every later run is quiet.
#
# After it finishes:
#   1. Point the DNS A record for PUBLIC_HOST at this server.
#   2. `sudo tailscale up` and approve the machine in the Tailscale admin.
#   3. Confirm you can SSH in over the tailnet as ADMIN_USER, THEN close the
#      console session: public SSH is closed by the firewall from this point on.
#   4. Create the first admin:  sudo -u mnh /srv/mnh/.venv/bin/python /srv/mnh/app/scripts/create_user.py --admin --username <name> --display-name "<Name>"
set -euo pipefail

ADMIN_USER="${ADMIN_USER:-aaditya}"
ADMIN_SSH_KEY="${ADMIN_SSH_KEY:?set ADMIN_SSH_KEY to the admin public key line}"
REPO_URL="${REPO_URL:-git@github.com:Aaditya-Shah696/mnh-app.git}"
PUBLIC_HOST="${PUBLIC_HOST:-mnhapp.app}"

APP_HOME=/srv/mnh
APP_DIR=$APP_HOME/app
VENV=$APP_HOME/.venv
DATA_DIR=$APP_HOME/data

log() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

log "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git ufw fail2ban \
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

log "SSH hardening: no root, no passwords"
cat > /etc/ssh/sshd_config.d/90-mnh.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
MaxAuthTries 3
EOF
systemctl restart ssh

log "Application user and directories"
if ! id mnh >/dev/null 2>&1; then
    adduser --system --group --home "$APP_HOME" --shell /usr/sbin/nologin mnh
fi
install -d -m 750 -o mnh -g mnh "$APP_HOME"
install -d -m 700 -o mnh -g mnh "$DATA_DIR" "$APP_HOME/.cache"

log "Deploy key for the private repository"
install -d -m 700 -o mnh -g mnh "$APP_HOME/.ssh"
if [ ! -f "$APP_HOME/.ssh/id_ed25519" ]; then
    sudo -u mnh ssh-keygen -q -t ed25519 -N "" -C "mnh-vps deploy key" -f "$APP_HOME/.ssh/id_ed25519"
fi
sudo -u mnh sh -c "ssh-keyscan -t ed25519 github.com 2>/dev/null >> $APP_HOME/.ssh/known_hosts"
sort -u -o "$APP_HOME/.ssh/known_hosts" "$APP_HOME/.ssh/known_hosts"

log "Code checkout"
if [ ! -d "$APP_DIR/.git" ]; then
    if ! sudo -u mnh git clone --quiet "$REPO_URL" "$APP_DIR" 2>/tmp/clone.err; then
        echo
        echo "Clone of $REPO_URL failed: $(tail -1 /tmp/clone.err)"
        echo "Add this READ-ONLY deploy key to the repository, then re-run this script:"
        echo "  https://github.com/Aaditya-Shah696/mnh-app/settings/keys"
        echo
        cat "$APP_HOME/.ssh/id_ed25519.pub"
        echo
        exit 1
    fi
fi
# Serve the CI-promoted `production` branch when it exists; until the first
# green CI run on main it does not, and main is used for the initial build.
sudo -u mnh git -C "$APP_DIR" fetch --quiet origin
if sudo -u mnh git -C "$APP_DIR" rev-parse --verify --quiet origin/production >/dev/null; then
    sudo -u mnh git -C "$APP_DIR" checkout --quiet -B production origin/production
else
    sudo -u mnh git -C "$APP_DIR" checkout --quiet -B main origin/main
fi

log "Python virtualenv + locked dependencies (hash-checked)"
[ -d "$VENV" ] || sudo -u mnh python3 -m venv "$VENV"
sudo -u mnh "$VENV/bin/pip" install --upgrade pip -q
sudo -u mnh "$VENV/bin/pip" install -r "$APP_DIR/requirements.lock" --require-hashes -q

log "Environment file"
if [ ! -f "$APP_HOME/mnh.env" ]; then
    cat > "$APP_HOME/mnh.env" <<EOF
DISCHARGE_PUBLIC_ORIGIN=https://$PUBLIC_HOST
EOF
    chown mnh:mnh "$APP_HOME/mnh.env"
    chmod 600 "$APP_HOME/mnh.env"
fi

log "Swap (the embedding model load spikes memory on a 2 GB box)"
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "Database schema"
sudo -u mnh env DISCHARGE_ENV=production DISCHARGE_DATA_DIR="$DATA_DIR" \
    "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head

log "systemd units"
cp "$APP_DIR/deploy/mnh.service" "$APP_DIR/deploy/mnh-backup.service" \
   "$APP_DIR/deploy/mnh-backup.timer" "$APP_DIR/deploy/mnh-autodeploy.service" \
   "$APP_DIR/deploy/mnh-autodeploy.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mnh mnh-backup.timer mnh-autodeploy.timer

log "Caddy"
sed "s/mnhapp.app/$PUBLIC_HOST/" "$APP_DIR/deploy/Caddyfile" > /etc/caddy/Caddyfile
install -d -o caddy -g caddy /var/log/caddy
systemctl enable caddy
systemctl reload caddy || systemctl restart caddy

log "fail2ban"
cp "$APP_DIR/deploy/fail2ban/jail.d/mnh.conf" /etc/fail2ban/jail.d/
cp "$APP_DIR/deploy/fail2ban/filter.d/caddy-login.conf" /etc/fail2ban/filter.d/
systemctl enable --now fail2ban
systemctl restart fail2ban

log "Firewall: 80/443 public, SSH over the tailnet only"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow in on tailscale0 to any port 22 proto tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat <<EOF

Done. Next:
  1. DNS: A record  $PUBLIC_HOST -> $(curl -fsS https://api.ipify.org || echo '<this server IP>')
  2. sudo tailscale up            (approve the machine, then test SSH over the tailnet as $ADMIN_USER)
  3. First admin:
     sudo -u mnh env DISCHARGE_DATA_DIR=$DATA_DIR $VENV/bin/python $APP_DIR/scripts/create_user.py --admin --username <name> --display-name "<Name>"
  4. curl -fsS http://127.0.0.1:8021/api/health   -> {"status":"ok"}
  5. https://$PUBLIC_HOST  from a phone: login page with a padlock.
EOF
