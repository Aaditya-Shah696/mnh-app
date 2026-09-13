# MNH Discharge Records

A discharge record system for Mahavir Nursing Home (Dr. Mitesh Shah,
Pediatrician). It replaces the copy-paste-from-old-Word-files workflow: as
a diagnosis is typed, the closest past cases appear alongside the form and
their medicines can be copied into the current record with one click.

Runs as one Python process with a SQLite database. No cloud AI, no LLM
APIs; the similar-case search uses a small local sentence-embedding model
(fastembed, downloaded once and cached). It can run on a single PC or be
hosted on a small VPS for the whole clinic (see Deployment).

## Features

- Full discharge card form: patient details, admission (ward is a fixed
  choice; weight and height), examination findings (vitals, six yes/no
  signs, per-system notes), diagnosis, history, course, treatment lines,
  discharge medicines, advice, follow-up, investigations.
- Patient registry with name search, plus per-patient profiles: chronic
  conditions and past medical history live on the profile and prefill
  every new discharge. Each profile lists all past visits.
- Similar past cases panel: as you type, past records are ranked by
  semantic similarity of diagnosis + history + treatment. "Copy medicines"
  pulls a past record's discharge medicines (and advice, if empty) into
  the current form.
- Medicine dose, route, and frequency fields are editable dropdown presets.
- Print-ready A4 discharge card PDF that leaves blank space at the top for
  pre-printed letterhead stationery. Draft records get a DRAFT watermark.
- Named users with two roles (staff, admin), server-side sessions, an
  append-only audit log of every view, print and edit, and soft delete
  with restore. See Security.
- Automatic daily encrypted backups (AES-256 zip) of the database and
  clinic config, retention of the newest 30.
- Draft / Final workflow, Ctrl+S to save, unsaved-changes warning.

## Setup (once, on any machine)

```powershell
cd discharge-mnh
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock --require-hashes
.venv\Scripts\alembic upgrade head
.venv\Scripts\python scripts\create_user.py --admin --username mitesh --display-name "Dr. Mitesh Shah"
.venv\Scripts\python scripts\seed_demo_data.py   # optional demo data (refused in production)
```

`create_user.py` prompts for the password twice and never accepts it on
the command line. Passwords are 12 characters or longer.

For a local development copy only, `python scripts\dev_users.py` creates
or resets two fixed accounts and prints their passwords: `mitesh` (admin)
and `reception` (staff). It refuses to run when `DISCHARGE_ENV=production`.

The first record save downloads the embedding model (~130 MB) into the
user cache; after that everything works offline.

## Run locally

```powershell
.venv\Scripts\python -m uvicorn app.main:app --port 8021
```

Open http://localhost:8021, sign in. API docs live at /docs outside
production. The server binds to localhost only.

## Deployment (VPS)

Production runs on an Ubuntu VPS behind Caddy (automatic HTTPS), as a
hardened systemd service, with SSH reachable only over Tailscale. The
whole build is one script, and releases are a push to `main`:

```bash
sudo -E bash scripts/vps_bootstrap.sh        # once
git push origin main                         # every release
```

GitHub Actions runs `pip-audit` and the full test suite, then
fast-forwards the `production` branch. The VPS polls that branch every
minute and deploys it (`scripts/autodeploy.sh` → `scripts/deploy.sh`),
and the workflow finishes only when `https://mnhapp.app/api/health`
reports the pushed commit. GitHub holds no server credentials.

Everything operational (first build, moving the existing records, backups
that the clinic PC pulls nightly, restore drill, incidents) is in
[docs/RUNBOOK.md](docs/RUNBOOK.md). Server-side files are in `deploy/`.

Environment variables (all optional locally, set by the systemd unit in
production):

| Variable | Default | Purpose |
|---|---|---|
| `DISCHARGE_ENV` | `development` | `production` disables /docs and refuses demo seeding |
| `DISCHARGE_DATA_DIR` | `./data` | database, clinic.json, backups |
| `DISCHARGE_PUBLIC_ORIGIN` | unset | `https://host` the app is served from; used by the CSRF check |
| `DISCHARGE_SESSION_IDLE_HOURS` | `12` | sign out after this long without activity |
| `DISCHARGE_SESSION_MAX_DAYS` | `14` | sign out unconditionally after this long |
| `DISCHARGE_COOKIE_SECURE` | `1` | set `0` only for a browser that refuses Secure cookies on localhost |
| `DISCHARGE_BACKUP_DIR` | `data/backups` | where archives are written |
| `DISCHARGE_BACKUP_INTERVAL_HOURS` | `24` | in-app scheduler interval |

## Users and roles

| Action | staff | admin |
|---|---|---|
| Create / edit patients and records, finalize, print PDF, similar cases | yes | yes |
| Delete or restore a patient or record (soft delete) | no | yes |
| Run a backup on demand | no | yes |
| Manage users, reset passwords, unlock accounts | no | yes |
| Read the audit log | no | yes |
| Change own password | yes | yes |

There is no self-registration. Admins add users on the Users page or with
`create_user.py`. Deactivating a user signs them out everywhere at once.

## Security notes

- Passwords are hashed with Argon2id. Sessions are opaque random tokens
  in an `HttpOnly; Secure; SameSite=Strict` cookie, stored server-side
  (only a hash) so they can be revoked. Idle timeout 12 h, absolute 14 days.
- Five failed sign-ins lock the account for 15 minutes, doubling each
  further failure up to 24 hours; an admin can unlock. Thirty attempts
  from one address in ten minutes returns 429. On the VPS, fail2ban also
  bans repeat offenders at the firewall.
- Cross-site writes are refused by an Origin / `Sec-Fetch-Site` check.
  API responses carry `Cache-Control: no-store`; a strict
  Content-Security-Policy applies everywhere and the UI never renders
  user input as HTML.
- Every sign-in, view, print, edit, delete, restore, backup and user
  change is written to an append-only `audit_log` table (SQLite triggers
  refuse UPDATE and DELETE on it). Admins read it on the Audit page.
  Details record which fields changed, never the clinical values.
- Records and patients are never hard-deleted through the API: deletion
  sets `deleted_at`, hides the row from lists and the matcher, and an
  admin can restore it.
- Backups are AES-256 encrypted with the password in
  `data/backup_password.txt`. **Write it down somewhere outside the
  computer**; a backup cannot be opened without it.
- Dependencies are pinned with hashes in `requirements.lock` (regenerate
  with `uv pip compile requirements.txt --universal --python-version 3.12
  --generate-hashes -o requirements.lock`) and `pip-audit` runs on every
  deploy.
- For the machine running it locally, enable BitLocker for at-rest
  protection. SQLCipher was deliberately avoided.

## Clinic details and warning signs

Edit `data/clinic.json` (clinic name, doctor name, qualifications,
warning-signs text, ...). The clinic and doctor names feed the app header,
the login page and the PDF signature; the printed card deliberately has
**no letterhead**. `warning_signs` is the paragraph printed at the end of
every card. No restart needed for the PDF; reload the page for the header.

## Backups and restore

- While the app runs, an encrypted backup is written to `data/backups/`
  whenever the newest one is older than 24 h. On the VPS a systemd timer
  also runs one at 21:30.
- Manual backup: `python scripts\backup_now.py [--copy-to E:\...]`
  or `POST /api/backup` (admin).
- On the VPS deployment the clinic PC pulls the archives nightly with
  `scripts\pull_backup.ps1` (registered by `scripts\setup_backup_task.ps1`).
- Restore (to a fresh folder, never straight over live data):

  ```powershell
  .venv\Scripts\python scripts\restore_backup.py data\backups\discharge_backup_XXXX.zip C:\restore-here
  ```

  Then stop the app, swap the restored folder in place of `data/`, run
  `alembic upgrade head`, and start the app again. Restores are
  integrity-checked automatically. Users and the audit log are inside the
  database, so they come back with it.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

The recommender tests run against the real local embedding model; by
design there is no mocked model anywhere in the suite. Authentication is
exercised for real too: fixtures sign in through the API, and a
route-walk test asserts that every `/api` route except health, clinic and
login refuses anonymous requests and that every admin route refuses staff.

## Project layout

```
app/
  main.py            FastAPI app, routers, static serving
  middleware.py      security headers, no-store, CSRF Origin check
  auth.py            argon2 hashing, sessions, lockout, throttle, dependencies
  audit.py           audit() helper (rows join the caller's transaction)
  config.py          paths, env overrides, clinic.json loader
  database.py        engine, session, SQLite pragmas (WAL, FKs)
  models.py          User, UserSession, AuditLog, Patient, DischargeRecord, TreatmentItem
  schemas.py         pydantic request/response models
  routers/           auth, users, audit, patients, records, match, backups
  services/
    embeddings.py    local fastembed model, record text, backfill
    pdf_export.py    A4 discharge card renderer (reportlab)
    backup.py        encrypted backup/restore + scheduler
  static/            no-build UI (index.html, css, js)
alembic/             migrations (SQLite batch mode enabled)
deploy/              systemd units, Caddyfile, fail2ban jail + filter
docs/RUNBOOK.md      build, deploy, backups, restore drill, incidents
scripts/             create_user, seed_demo_data, backup_now, restore_backup,
                     vps_bootstrap.sh, deploy.sh, pull_backup.ps1, setup_backup_task.ps1
tests/               pytest suite (real embedding model, real auth, no mocks)
```

Data lives in `data/` (SQLite DB, backups, clinic.json), which is
git-ignored. `DISCHARGE_DATA_DIR` relocates it entirely.
