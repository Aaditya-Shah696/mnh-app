# Runbook — MNH Discharge Records on the VPS

Operational reference for the Namecheap VPS deployment. Design rationale
lives in the (uncommitted) plan; this file is what you open at 9 pm when
something is wrong.

Placeholders: `mnhapp.app` is the public hostname, `mnh-vps` is the
Tailscale machine name, `aaditya` is the sudo user.

## Layout on the server

| Path | What | Owner / mode |
|---|---|---|
| `/srv/mnh/app` | git checkout | `mnh` |
| `/srv/mnh/.venv` | Python venv, installed from `requirements.lock` with `--require-hashes` | `mnh` |
| `/srv/mnh/data` | `discharge.db`, `clinic.json`, `backup_password.txt`, `backups/` | `mnh`, 700 |
| `/srv/mnh/.cache` | fastembed model (downloaded once) | `mnh` |
| `/srv/mnh/mnh.env` | `DISCHARGE_PUBLIC_ORIGIN=https://mnhapp.app` | `mnh`, 600 |
| `/etc/systemd/system/mnh.service` | uvicorn, `127.0.0.1:8021`, one worker | root |
| `/etc/systemd/system/mnh-backup.{service,timer}` | nightly 21:30 encrypted backup | root |
| `/etc/caddy/Caddyfile` | HTTPS on 443, Let's Encrypt, proxy to 8021 | root |
| `/var/log/caddy/access.log` | JSON access log, read by fail2ban | caddy |
| `/etc/fail2ban/jail.d/mnh.conf` | sshd + caddy-login jails | root |

Network: ufw allows 80 and 443 from anywhere, 22 only on `tailscale0`.
Nothing else listens publicly. `nmap` from outside must show exactly 80 and 443.

## First build

Before touching the server:

- Push `main` to GitHub. The bootstrap clones from
  `git@github.com:Aaditya-Shah696/mnh-app.git`.
- Have an SSH key on your laptop (`ssh-keygen -t ed25519` in PowerShell if
  `~/.ssh/id_ed25519.pub` does not exist). Its `.pub` line is `ADMIN_SSH_KEY`.
- In the Namecheap VPS panel: confirm the OS is Ubuntu 24.04 (reimage if it
  came with cPanel or AlmaLinux) and note the public IPv4 address.

On the server, from the Namecheap console or the initial root SSH:

```bash
export ADMIN_SSH_KEY="ssh-ed25519 AAAA... aaditya"
curl -fsSL https://raw.githubusercontent.com/Aaditya-Shah696/mnh-app/main/scripts/vps_bootstrap.sh -o vps_bootstrap.sh
sudo -E bash vps_bootstrap.sh
```

(The raw URL needs a GitHub token for a private repo; pasting the script
over the console or `scp`-ing it as root works just as well.)

The first run stops after generating a deploy key and prints it. Add it
as a **read-only deploy key** at
https://github.com/Aaditya-Shah696/mnh-app/settings/keys, then re-run the
same command; it continues from the clone.

Then, in this order:

1. DNS in Namecheap → Domain List → `mnhapp.app` → Advanced DNS:
   `A Record`, host `@`, value = server IP, TTL automatic; optionally
   `CNAME`, host `www`, value `mnhapp.app.` (Caddy redirects it). Remove any
   parking records Namecheap added. `.app` is HSTS-preloaded in every
   browser, so the site only works over HTTPS; Caddy fetches the
   certificate within a minute of the record resolving:
   `sudo journalctl -u caddy -n 30`.
2. `sudo tailscale up`, approve the machine, then from your laptop:
   `ssh aaditya@mnh-vps`. Only after that works, log out of the Namecheap
   console. Public SSH is closed.
3. First admin (password is prompted, never on the command line):
   ```bash
   sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/python \
       /srv/mnh/app/scripts/create_user.py --admin --username mitesh --display-name "Dr. Mitesh Shah"
   ```
4. Clinic details: `sudo -u mnh nano /srv/mnh/data/clinic.json` (see README).
5. Open `https://mnhapp.app` on a phone. Padlock, login page, sign in.
6. Add staff users from the Users page, or with `create_user.py` without `--admin`.

### Moving the existing records from the laptop

On the laptop: `python scripts/backup_now.py`, copy the newest
`data/backups/discharge_backup_*.zip` and `data/backup_password.txt` to the
server (over the tailnet with `scp`). On the server:

```bash
sudo systemctl stop mnh
sudo -u mnh /srv/mnh/.venv/bin/python /srv/mnh/app/scripts/restore_backup.py \
    /tmp/discharge_backup_XXXX.zip /tmp/restore --password "$(cat /tmp/backup_password.txt)"
sudo -u mnh cp /tmp/restore/discharge.db /tmp/restore/clinic.json /srv/mnh/data/
sudo -u mnh cp /tmp/backup_password.txt /srv/mnh/data/backup_password.txt
sudo chmod 600 /srv/mnh/data/backup_password.txt
sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/alembic -c /srv/mnh/app/alembic.ini upgrade head
sudo systemctl start mnh
rm -rf /tmp/restore /tmp/discharge_backup_XXXX.zip /tmp/backup_password.txt
```

Keeping the laptop's backup password means every archive ever made stays
openable with the one password written down in the clinic.

## Deploying a change (CI/CD)

Push to `main`. That is the whole procedure. What happens:

1. GitHub Actions (`.github/workflows/ci.yml`) installs the hashed lock,
   runs `pip-audit`, and runs the full test suite against the real
   embedding model.
2. If green, the workflow fast-forwards the `production` branch to that
   commit. Nothing on the VPS is contacted; the VPS has no public SSH and
   GitHub holds no server credentials.
3. On the VPS, `mnh-autodeploy.timer` runs `scripts/autodeploy.sh` every
   minute. When `origin/production` moves it runs `scripts/deploy.sh`:
   snapshot (skipped if an archive is under an hour old), reset the
   checkout to `production`, install with hash checking, `pip-audit`,
   `alembic upgrade head`, refresh unit files, restart, health check.
4. The workflow's last job polls `https://mnhapp.app/api/health` until
   its `version` equals the pushed commit (up to 10 minutes). Green check
   on the commit means it is live; red means open the VPS log. While the
   hostname does not resolve at all (server not built, no DNS record) the
   job passes with a warning instead, because there is nothing to verify.

| Need | Command (on the VPS) |
|---|---|
| Watch a deploy | `journalctl -u mnh-autodeploy -f` |
| Why did it not deploy | `cat /srv/mnh/autodeploy.state` (a SHA there means that commit's deploy failed and is skipped; push a fix or run deploy.sh) |
| Pause deploys (e.g. during clinic hours) | `sudo systemctl stop mnh-autodeploy.timer`; resume with `start` |
| Deploy by hand | `sudo bash /srv/mnh/app/scripts/deploy.sh` |
| Emergency deploy of main without CI | `sudo BRANCH=main bash /srv/mnh/app/scripts/deploy.sh` (the next autodeploy moves it back to production once CI passes) |
| Which commit is live | `curl -s https://mnhapp.app/api/health` |

Rollback: `git revert` the bad commit on `main` and push; CI redeploys the
revert in a few minutes. If the bad commit had a migration, run
`alembic downgrade <rev>` on the VPS first, as `mnh` with
`DISCHARGE_DATA_DIR=/srv/mnh/data`. The pre-deploy archive is in
`/srv/mnh/data/backups`.

Deploys restart the service, which drops in-flight requests for about
three seconds. Merge during quiet hours or pause the timer for the day.

## Daily operation

| Task | Command |
|---|---|
| Is it up | `curl -fsS https://mnhapp.app/api/health` |
| Service state | `systemctl status mnh caddy fail2ban mnh-backup.timer` |
| App log | `journalctl -u mnh -n 100 -f` |
| Who is hammering login | `sudo fail2ban-client status caddy-login` and the Audit page filtered to `login.failure` |
| Backups on disk | `ls -lh /srv/mnh/data/backups` (newest 30 kept) |
| Manual backup | `sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/python /srv/mnh/app/scripts/backup_now.py` |
| Unlock / reset a user | Users page, or `create_user.py --reset-password --username <name>` |
| List users | `create_user.py --list` |

Uptime monitoring: register `https://mnhapp.app/api/health` with a free
checker (UptimeRobot or similar), 5-minute interval, alert to Aaditya's
email. Without this, the first person to notice an outage is a receptionist.

## Backups: the clinic PC pulls

The VPS writes an AES-256 archive nightly (in-app scheduler plus the
systemd timer; both take the same lock). The clinic PC fetches them over
the tailnet so a copy is always inside the building.

### Restricted pull key (once)

The clinic PC signs in as a dedicated `mnhpull` user that can read the
archives and nothing else. The archives are ciphertext without the
password, so a stolen pull key exposes nothing.

On the VPS (once):

```bash
sudo adduser --disabled-password --gecos "" mnhpull
sudo apt install -y acl
sudo setfacl -m u:mnhpull:x /srv/mnh /srv/mnh/data          # traverse only
sudo setfacl -m u:mnhpull:rx /srv/mnh/data/backups          # list + read
sudo setfacl -d -m u:mnhpull:r /srv/mnh/data/backups        # future archives too
```

On the clinic PC (PowerShell): `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\mnh_pull -N '""'`
and paste the contents of `mnh_pull.pub` into
`/home/mnhpull/.ssh/authorized_keys` on the VPS, prefixed with `restrict,`
(no forwarding, no pty). `ls` and `scp` are all the key can do, and only
over the tailnet because ufw blocks public SSH. Use `-Remote mnhpull@mnh-vps`
in the scripts below.

### Schedule it

Elevated PowerShell on the clinic PC, from the repo folder:

```powershell
.\scripts\setup_backup_task.ps1 -Remote mnhpull@mnh-vps -Dest "E:\clinic-backups" -At "22:00"
```

Run the task once from Task Scheduler and check `E:\clinic-backups\pull_backup.log`.

### Optional second copy: Backblaze B2

`sudo apt install rclone`, configure a B2 remote as `mnh`, then add to the
timer's service a second `ExecStart=` line
`/usr/bin/rclone copy /srv/mnh/data/backups mnh:mnh-backups --include "discharge_backup_*.zip"`.
The archives are already encrypted; B2 only ever sees ciphertext.

### The password

`/srv/mnh/data/backup_password.txt` (mode 600) is the only copy on the
server. It is also written on paper in the clinic and stored in Aaditya's
password manager. Without it no archive can be opened. Never put it in the
repo, an environment variable, or B2.

## Restore drill (every quarter, 10 minutes)

On the clinic PC or laptop, from the repo folder with the venv active:

```powershell
python scripts\restore_backup.py E:\clinic-backups\discharge_backup_<newest>.zip C:\mnh-drill --password "<from paper>"
$env:DISCHARGE_DATA_DIR = "C:\mnh-drill"
python -m uvicorn app.main:app --port 8021
```

Open `http://localhost:8021`, sign in with your own username (users are in
the database, so the archive carries them), open a record, print a PDF.
Then stop the server and delete `C:\mnh-drill`. Record the date below.

| Drill date | Archive | Who | Result |
|---|---|---|---|
| | | | |

## Incidents

**Cannot sign in, "Incorrect username or password" but it is correct.**
The account is locked after 5 failures (15 min, doubling). An admin
unlocks it on the Users page; or `create_user.py --reset-password`.

**429 Too many attempts.** The clinic's public IP hit 30 login attempts in
10 minutes (everyone in the building shares one IP). Wait 10 minutes.
fail2ban bans at 20 failed logins in 10 minutes for an hour:
`sudo fail2ban-client set caddy-login unbanip <ip>`.

**Certificate error in the browser.** `sudo journalctl -u caddy -n 50`.
Usually DNS: `dig +short mnhapp.app` must return the server IP, and
port 80 must be reachable (ACME challenge).

**"database is locked" in the log.** Should not happen with one worker. If
it does, check that only one `uvicorn` process exists: `pgrep -af uvicorn`.

**VPS gone (suspended, wiped).** Provision a new one with
`vps_bootstrap.sh`, then follow "Moving the existing records" using the
newest archive from `E:\clinic-backups`. Update the DNS A record. Total
time is under an hour; the data loss window is at most one night.

**Suspected compromise.** `sudo systemctl stop mnh caddy`; take a copy of
`/srv/mnh/data` and `/var/log/caddy`; rotate every user's password from
the CLI (`create_user.py --reset-password`, which revokes all sessions);
review the Audit page for `record.view` and `record.pdf` by unexpected
users or IPs; rebuild the VPS from scratch before bringing it back.

## Weekly five-minute check

1. `https://mnhapp.app/api/health` responds.
2. Audit page: filter `login.failure`, last 7 days. A handful is normal;
   hundreds from one IP means fail2ban is doing its job, thousands means
   raise `maxretry` scrutiny.
3. `E:\clinic-backups\pull_backup.log` has last night's line.
4. `sudo apt list --upgradable` is empty or only non-security packages.
