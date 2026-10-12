# Runbook — MNH Discharge Records on the VPS

Operational reference for the Namecheap VPS deployment. Design rationale
lives in the (uncommitted) plan; this file is what you open at 9 pm when
something is wrong.

Placeholders: `mnhapp.org` is the public hostname, `mnh-vps` is the
Tailscale machine name, `aaditya` is the sudo user.

## Layout on the server

| Path | What | Owner / mode |
|---|---|---|
| `/srv/mnh` | application home | `root:mnh`, 750 |
| `/srv/mnh/app` | git checkout; the app reads it, only root writes it | `root:mnh`, 2750, files 640 |
| `/srv/mnh/.venv` | Python venv, installed from `requirements.lock` with `--require-hashes` | `mnh` |
| `/srv/mnh/data` | `discharge.db`, `clinic.json`, `backup_password.txt` | `mnh`, 700, files 600 |
| `/srv/mnh/.cache` | fastembed model (downloaded once) | `mnh` |
| `/srv/mnh/mnh.env` | `DISCHARGE_PUBLIC_ORIGIN`, `DISCHARGE_BACKUP_DIR`, `DISCHARGE_GIT_SHA` | `root`, 600 |
| `/srv/mnh-backups` | SFTP chroot of the pull user | `root`, 755 |
| `/srv/mnh-backups/archives` | encrypted backup archives, nothing else | `mnh`, 750, ACL `mnhpull:r-x` |
| `/etc/mnh` | `deploy_key` (read-only GitHub key), `known_hosts` (GitHub's pinned key), `deploy.conf`, `allowed_signers` | `root`, 700 |
| `/usr/local/lib/mnh` | `deploy.sh`, `autodeploy.sh`, `deploy_lib.sh`: the copies root actually runs | `root`, 755 |
| `/var/lib/mnh` | deploy state: `deployed`, `production.seen`, `failed`, `deploy.lock` | `root`, 700 |
| `/etc/systemd/system/mnh.service` | uvicorn, `127.0.0.1:8021`, one worker | root |
| `/etc/systemd/system/mnh-backup.{service,timer}` | nightly 21:30 IST encrypted backup | root |
| `/etc/caddy/Caddyfile` | HTTPS on 443, Let's Encrypt, proxy to 8021, admin API off | root |
| `/var/log/caddy/access.log` | JSON access log | caddy |
| `/etc/fail2ban/jail.d/mnh.conf` | sshd + mnh-login jails (both read the journal) | root |
| `/etc/ssh/sshd_config.d/00-mnh.conf` | no root login, no passwords (sorts before cloud-init's file, so it wins) | root |
| end of `/etc/ssh/sshd_config` | `Match User mnhpull` block: SFTP only, read-only, chrooted | root |

The `mnh` user can read the code but not change it, and cannot read the
deploy key. Root never executes anything from the checkout: the deploy
scripts it runs are the copies in `/usr/local/lib/mnh`, refreshed only at
the end of a successful deploy.

Network: ufw allows 80 and 443 from anywhere, 22 only on `tailscale0`.
Nothing else listens publicly. `nmap` from outside must show exactly 80 and 443.

## GitHub settings (once)

1. **Protect `production`.** Settings → Rules → Rulesets → New branch
   ruleset, target `production`, enable *Restrict updates*, *Restrict
   deletions* and *Block force pushes*, and add **GitHub Actions** as the
   only bypass actor. Nobody, including you, can push to it directly; only
   the CI promote job moves it.
2. **Protect `main`** the same way if anyone else ever gets write access:
   require the `Test (real embedding model)` check before merging.
3. **Sign your commits** so the VPS can refuse anything you did not sign.
   On your laptop:

   ```bash
   git config --global gpg.format ssh
   git config --global user.signingkey ~/.ssh/id_ed25519.pub
   git config --global commit.gpgsign true
   ```

   Add the same `.pub` on GitHub as a *Signing key*. Then give the VPS the
   matching `allowed_signers` line (next section, `DEPLOY_SIGNERS`). From
   then on `deploy.sh` runs `git verify-commit` on the exact commit before
   touching anything and refuses unsigned or foreign commits. Until the
   file exists every deploy logs a warning that the check was skipped.
   Merge locally rather than with GitHub's merge button: GitHub signs web
   merges with its own key, which is not in `allowed_signers`.

## First build

Before touching the server:

- Push `main` to GitHub. The bootstrap clones from
  `git@github.com:Aaditya-Shah696/mnh-app.git`.
- Have an SSH key on your laptop (`ssh-keygen -t ed25519` in PowerShell if
  `~/.ssh/id_ed25519.pub` does not exist). Its `.pub` line is `ADMIN_SSH_KEY`.
- On the clinic PC create the pull key now (see "Restricted pull key"); its
  `.pub` line is `PULL_SSH_KEY`.
- In the Namecheap VPS panel: confirm the OS is Ubuntu 24.04 (reimage if it
  came with cPanel or AlmaLinux) and note the public IPv4 address.

On the server, from the Namecheap console or the initial root SSH:

```bash
export ADMIN_SSH_KEY="ssh-ed25519 AAAA... aaditya"
export PULL_SSH_KEY="ssh-ed25519 AAAA... clinic-pc"
export DEPLOY_SIGNERS='you@example.com namespaces="git" ssh-ed25519 AAAA...'
curl -fsSL https://raw.githubusercontent.com/Aaditya-Shah696/mnh-app/main/scripts/vps_bootstrap.sh -o vps_bootstrap.sh
sudo -E bash vps_bootstrap.sh
```

`PULL_SSH_KEY` and `DEPLOY_SIGNERS` are optional; re-run with them set
whenever you have them. The email in `DEPLOY_SIGNERS` is the one in
`git config user.email`.

(The raw URL needs a GitHub token for a private repo; pasting the script
over the console or `scp`-ing it as root works just as well.)

The script applies the firewall and the SSH hardening before it does
anything that could fail on a fresh box, so an interrupted run never leaves
password SSH or an open firewall behind. It is safe to run from the
Namecheap web console (no `SSH_CLIENT`) or over SSH.

The first run stops after generating a deploy key and prints it. Add it
as a **read-only deploy key** at
https://github.com/Aaditya-Shah696/mnh-app/settings/keys, then re-run the
same command; it continues from the clone.

Then, in this order:

1. DNS in Namecheap → Domain List → `mnhapp.org` → Advanced DNS:
   `A Record`, host `@`, value = server IP, TTL automatic; optionally
   `CNAME`, host `www`, value `mnhapp.org.` (Caddy redirects it). Namecheap
   parks a new domain on its own IP (`162.255.119.x`) with `A` and
   `URL Redirect` records; delete those or the app's A record will not
   win. Caddy fetches the certificate within a minute of the record
   resolving to the VPS: `sudo journalctl -u caddy -n 30`.
2. `sudo tailscale up --hostname mnh-vps`, open the printed login URL and
   approve the machine, then from your laptop: `ssh aaditya@mnh-vps`. Only
   after that works, close public SSH:
   `sudo bash /srv/mnh/app/scripts/lockdown_ssh.sh` (it refuses to run
   unless the tailnet is joined, and refuses to cut the session you are
   running it from). Until then SSH stays public but key-only, watched by
   fail2ban.

   **DNS note.** Namecheap's resolvers are at 100.100.100.17/18, inside the
   100.64.0.0/10 range that Tailscale routes into the tailnet. With Tailscale
   up they vanish and every name lookup fails (git fetch, apt, Let's Encrypt
   renewals). The image sets them statically in `/etc/network/interfaces`
   (`dns-nameservers`) and writes a plain `/etc/resolv.conf`. The bootstrap
   rewrites both to 1.1.1.1/8.8.8.8, points `/etc/resolv.conf` at the
   systemd-resolved stub with the same servers, and runs
   `tailscale set --accept-dns=false`.
   Symptom if it regresses: `journalctl -u mnh-autodeploy` shows
   "fetch failed" and `dig github.com` returns nothing.

   **CPU note.** Namecheap's KVM guests present a "QEMU Virtual CPU 2.5+"
   with only SSE2/SSE3. NumPy 2.3+ wheels require x86-64-v2 and crash at
   import, so `requirements.txt` pins `numpy<2.3`. fastembed + onnxruntime
   run fine on it (an embedding takes well under a second). Do not lift the
   pin unless the CPU model changes (`lscpu | grep Flags` shows `sse4_2`
   and `popcnt`).
3. First admin (password is prompted, never on the command line):
   ```bash
   cd /srv/mnh/app
   sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/python \
       scripts/create_user.py --admin --username mitesh --display-name "Dr. Mitesh Shah"
   ```
4. Clinic details: `sudo -u mnh nano /srv/mnh/data/clinic.json` (see README).
5. Open `https://mnhapp.org` on a phone. Padlock, login page, sign in.
6. Add staff users from the Users page, or with `create_user.py` without `--admin`.

### Upgrading a server built before October 2026

Servers built with the earlier bootstrap keep the checkout and deploy key
owned by `mnh`, keep archives next to the database, and run the deploy
scripts from the checkout. The old autodeploy must not ship the change that
introduces the new layout, so upgrade in this order:

1. On the VPS: `sudo systemctl stop mnh-autodeploy.timer`.
2. Push to `main` and wait for CI to promote it to `production`.
3. Copy the new `scripts/vps_bootstrap.sh` to the VPS and run it as in the
   first build (`ADMIN_SSH_KEY` is still required; add `PULL_SSH_KEY` and
   `DEPLOY_SIGNERS` when you have them). It checks out the new
   `production`, migrates the database, and re-enables the timer.

The bootstrap converts everything in place: it moves the existing deploy
key to `/etc/mnh` (no new GitHub key needed), hands the checkout to root,
moves the archives to `/srv/mnh-backups/archives`, removes the old
`mnhpull` ACLs on `/srv/mnh` and `/srv/mnh/data`, sets every file in
`data/` to owner-only, installs the SFTP-only `Match` block and the new
fail2ban jail, restarts Caddy with its admin API off, and installs the
scripts in `/usr/local/lib/mnh`. Until it has run, the new `deploy.sh`
refuses to deploy and says so in `journalctl -u mnh-autodeploy`.

Check afterwards, from the clinic PC: `ssh -i $env:USERPROFILE\.ssh\mnh_pull mnhpull@mnh-vps cat /srv/mnh/data/discharge.db`
must fail with "This service allows sftp connections only", and the
scheduled pull must still succeed.

### Moving the existing records from the laptop

On the laptop: `python scripts/backup_now.py`, copy the newest
`data/backups/discharge_backup_*.zip` and `data/backup_password.txt` to
the server's `/tmp` (over the tailnet with `scp`). On the server:

```bash
sudo systemctl stop mnh
sudo install -o mnh -g mnh -m 600 /tmp/backup_password.txt /srv/mnh/data/backup_password.txt
sudo install -o mnh -g mnh -m 600 /tmp/discharge_backup_XXXX.zip /srv/mnh/data/restore.zip
cd /srv/mnh/app
sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/python \
    scripts/restore_backup.py /srv/mnh/data/restore.zip /srv/mnh/data/restore
sudo -u mnh rm -f /srv/mnh/data/discharge.db-wal /srv/mnh/data/discharge.db-shm
sudo -u mnh cp /srv/mnh/data/restore/discharge.db /srv/mnh/data/restore/clinic.json /srv/mnh/data/
sudo -u mnh rm -rf /srv/mnh/data/restore /srv/mnh/data/restore.zip
sudo chmod 600 /srv/mnh/data/discharge.db /srv/mnh/data/clinic.json
sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data DISCHARGE_BACKUP_DIR=/srv/mnh-backups/archives \
    /srv/mnh/.venv/bin/alembic -c alembic.ini upgrade head
sudo systemctl start mnh
shred -u /tmp/backup_password.txt && rm -f /tmp/discharge_backup_XXXX.zip
```

The restore reads the password from `data/backup_password.txt`, so it never
appears on a command line or in `ps`. Keeping the laptop's backup password
means every archive ever made stays openable with the one password written
down in the clinic.

## Deploying a change (CI/CD)

Push to `main`. That is the whole procedure. What happens:

1. GitHub Actions (`.github/workflows/ci.yml`) lints the shell scripts,
   validates the Caddyfile, the fail2ban filter and the sshd block, installs
   the hashed lock, runs `pip-audit`, and runs the full test suite against
   the real embedding model.
2. If green, the workflow fast-forwards the `production` branch to that
   commit. Nothing on the VPS is contacted; the VPS has no public SSH and
   GitHub holds no server credentials.
3. On the VPS, `mnh-autodeploy.timer` runs `/usr/local/lib/mnh/autodeploy.sh`
   every minute. When `origin/production` moves it runs `deploy.sh`, which:
   - verifies the commit's signature (when `allowed_signers` exists),
   - renders and validates the new unit files and Caddyfile before
     changing anything,
   - snapshots the database (skipped if an archive is under an hour old),
   - checks out the commit, installs with hash checking, runs `pip-audit`,
     `alembic upgrade head`, installs changed unit files and Caddyfile,
     restarts, and waits for `/api/health` to report the new commit,
   - records the commit in `/var/lib/mnh/deployed` only after all of that
     succeeded, then refreshes the root-owned deploy scripts.

   If any step fails, or the deploy runs over 40 minutes, it rolls back:
   `alembic downgrade` to the previous revision, previous checkout and
   dependencies, previous unit files and Caddyfile, restart, health check.
   The commit is written to `/var/lib/mnh/failed` and not retried until
   `production` moves again.
4. The workflow's last job polls `https://mnhapp.org/api/health` until
   its `version` equals the pushed commit (up to 10 minutes). Green check
   on the commit means it is live; red means open the VPS log. While the
   hostname does not resolve at all (server not built, no DNS record) the
   job passes with a warning instead, because there is nothing to verify.

| Need | Command (on the VPS) |
|---|---|
| Watch a deploy | `journalctl -u mnh-autodeploy -f` |
| Which commit is deployed | `cat /var/lib/mnh/deployed` or `curl -s https://mnhapp.org/api/health` |
| Why did it not deploy | `cat /var/lib/mnh/failed` (that commit failed and was rolled back; push a fix or deploy by hand) |
| Pause deploys (e.g. during clinic hours) | `sudo systemctl stop mnh-autodeploy.timer`; resume with `start` |
| Deploy by hand | `sudo /usr/local/lib/mnh/deploy.sh` |
| Emergency deploy of main without CI | `sudo BRANCH=main /usr/local/lib/mnh/deploy.sh` |

An emergency deploy stays live: autodeploy only acts when `production`
itself moves, so it does not put the older production commit back. Once
CI promotes a commit that contains the fix, the normal flow carries on
from there. Changes to the deploy scripts themselves take effect from the
deploy after the one that ships them.

Rollback of a bad release that deployed fine: `git revert` the commit on
`main` and push; CI redeploys the revert in a few minutes. If it had a
migration, revert it with the same downgrade the automatic rollback uses:

```bash
cd /srv/mnh/app
sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data DISCHARGE_BACKUP_DIR=/srv/mnh-backups/archives \
    /srv/mnh/.venv/bin/alembic -c alembic.ini downgrade <rev>
```

The pre-deploy archive is in `/srv/mnh-backups/archives`.

Deploys restart the service, which drops in-flight requests for about
three seconds. Merge during quiet hours or pause the timer for the day.

## Daily operation

| Task | Command |
|---|---|
| Is it up | `curl -fsS https://mnhapp.org/api/health` |
| Service state | `systemctl status mnh caddy fail2ban mnh-backup.timer mnh-autodeploy.timer` |
| App log | `journalctl -u mnh -n 100 -f` |
| Who is hammering login | `sudo fail2ban-client status mnh-login`, `journalctl -u mnh -g 'login rejected'`, and the Audit page filtered to `login.failure` |
| Backups on disk | `ls -lh /srv/mnh-backups/archives` (newest 30 kept) |
| Manual backup | `sudo systemctl start mnh-backup.service` |
| Unlock / reset a user | Users page, or `create_user.py --reset-password --username <name>` |
| List users | `create_user.py --list` |

Run `create_user.py` from `/srv/mnh/app` as
`sudo -u mnh env DISCHARGE_DATA_DIR=/srv/mnh/data /srv/mnh/.venv/bin/python scripts/create_user.py ...`.

Caddy's admin API is off, so `systemctl reload caddy` does not work; use
`sudo systemctl restart caddy` (deploys do this automatically when the
Caddyfile changes, after validating it).

Uptime monitoring: register `https://mnhapp.org/api/health` with a free
checker (UptimeRobot or similar), 5-minute interval, alert to Aaditya's
email. Without this, the first person to notice an outage is a receptionist.

## Backups: the clinic PC pulls

The VPS writes an AES-256 archive nightly at 21:30 IST (systemd timer) and
the in-app scheduler adds one whenever the newest is over a day old. Both
take the same file lock, and archives appear under their final name only
once complete. The clinic PC fetches them over the tailnet so a copy is
always inside the building.

### Restricted pull key (once)

The clinic PC signs in as a dedicated `mnhpull` user. sshd forces it into
read-only SFTP, chrooted to `/srv/mnh-backups`, where the only directory is
`archives`. It cannot run commands, open a shell or a tunnel, or see
anything outside that directory, and the archives are ciphertext without
the password, so a stolen pull key exposes nothing.

On the clinic PC (PowerShell), press Enter twice when asked for a
passphrase so the scheduled task can use the key unattended:

```powershell
ssh-keygen -t ed25519 -C clinic-pc -f $env:USERPROFILE\.ssh\mnh_pull
Get-Content $env:USERPROFILE\.ssh\mnh_pull.pub
```

Do not pass `-N '""'`: PowerShell 7 hands ssh-keygen two literal quote
characters, which become the passphrase, and the nightly pull then fails
with "Permission denied (publickey)".

Put that line in `PULL_SSH_KEY` and re-run the bootstrap; it creates the
user, the chroot, the ACLs and the `authorized_keys` entry (prefixed with
`restrict`). Test from the clinic PC:

```powershell
sftp -i $env:USERPROFILE\.ssh\mnh_pull mnhpull@mnh-vps
sftp> ls /archives
```

### Schedule it

Elevated PowerShell on the clinic PC, from the repo folder, signed in as
the Windows user that owns the pull key:

```powershell
.\scripts\setup_backup_task.ps1 -Remote mnhpull@mnh-vps -Dest "E:\clinic-backups" -At "22:00"
```

The task runs as that user whether or not anyone is signed in, wakes the
PC if it is asleep, and catches up at the next start if the PC was off.
Run it once from Task Scheduler and check `E:\clinic-backups\pull_backup.log`.
Every run writes one line; failures (Tailscale down, key missing, newest
archive older than 36 hours) are written as `ERROR` lines and the task
reports a non-zero result.

### Optional second copy: Backblaze B2

`sudo apt install rclone`, configure a B2 remote as `mnh`, then add to the
timer's service a second `ExecStart=` line
`/usr/bin/rclone copy /srv/mnh-backups/archives mnh:mnh-backups --include "discharge_backup_*.zip"`.
The archives are already encrypted; B2 only ever sees ciphertext.

### The password

`/srv/mnh/data/backup_password.txt` (mode 600) is the only copy on the
server. It is also written on paper in the clinic and stored in Aaditya's
password manager. Without it no archive can be opened. Never put it in the
repo, an environment variable, a command line, or B2.

## Restore drill (every quarter, 10 minutes)

On the clinic PC or laptop, from the repo folder with the venv active:

```powershell
python scripts\restore_backup.py E:\clinic-backups\discharge_backup_<newest>.zip C:\mnh-drill --prompt
$env:DISCHARGE_DATA_DIR = "C:\mnh-drill"
python -m uvicorn app.main:app --port 8021
```

`--prompt` asks for the password from paper without echoing it.
Open `http://localhost:8021`, sign in with your own username (users are in
the database, so the archive carries them), open a record, print a PDF.
Then stop the server and delete `C:\mnh-drill`. Record the date below.

| Drill date | Archive | Who | Result |
|---|---|---|---|
| | | | |

## Incidents

**"Too many failed sign-in attempts from this device."** After 5 wrong
passwords for one username from one address, that address is locked out
of that username for 15 minutes, doubling with each further failure up to
24 hours. Other devices and other addresses are not affected, so a
stranger guessing Dr. Shah's password cannot lock him out at the clinic.
An admin clears every lock for the account with Unlock on the Users page;
`create_user.py --reset-password` does too. Wrong current passwords on the
change-password form count the same way.

**429 "Too many sign-in attempts from this network."** The clinic's public
IP hit 30 login attempts in 10 minutes (everyone in the building shares one
IP). Wait 10 minutes. fail2ban bans an address after 20 rejected logins in
10 minutes for an hour: `sudo fail2ban-client set mnh-login unbanip <ip>`.

**Certificate error in the browser.** `sudo journalctl -u caddy -n 50`.
Usually DNS: `dig +short mnhapp.org` must return the server IP, and
port 80 must be reachable (ACME challenge).

**Deploys stopped.** `journalctl -u mnh-autodeploy -n 100`. "re-run
scripts/vps_bootstrap.sh" means the server still has the old layout (see
"Upgrading a server"). "not signed by a key in allowed_signers" means the
commit is unsigned or signed with another key. A SHA in
`/var/lib/mnh/failed` means that commit failed and was rolled back.

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
users or IPs (similar-case results are logged as `record.view` with
`via=similar_cases`); rebuild the VPS from scratch before bringing it back.

## Weekly five-minute check

1. `https://mnhapp.org/api/health` responds.
2. Audit page: filter `login.failure`, last 7 days. A handful is normal;
   hundreds from one IP means fail2ban is doing its job, thousands means
   raise `maxretry` scrutiny.
3. `E:\clinic-backups\pull_backup.log` has last night's line with no
   `ERROR`, and `age_hours` under a day.
4. `sudo apt list --upgradable` is empty or only non-security packages.
