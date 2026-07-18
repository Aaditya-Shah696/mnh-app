# MNH Discharge Records

A local, offline-first discharge record system for a small nursing home.
It replaces the copy-paste-from-old-Word-files workflow: as a diagnosis is
typed, the closest past cases appear alongside the form and their medicines
can be copied into the current record with one click.

Everything runs on one machine. No cloud, no external services, no LLM
APIs; the similar-case search uses a small local sentence-embedding model
(fastembed, downloaded once and cached).

## Features

- Full discharge card form: patient details, admission, vitals, diagnosis,
  history, investigations, course, treatment lines, discharge medicines,
  advice, follow-up, attachments (lab reports, scans).
- Patient registry with search by name or phone; repeat visits reuse the
  same patient.
- Similar past cases panel: as you type, past records are ranked by
  semantic similarity of diagnosis + complaints + history + treatment.
  "Copy medicines" pulls a past record's discharge medicines (and advice,
  if empty) into the current form.
- Print-ready A4 discharge card PDF with the clinic letterhead; draft
  records get a DRAFT watermark.
- Automatic daily encrypted backups (AES-256 zip) of the database,
  attachments, and clinic config, with retention of the newest 30.
- Draft / Final workflow, Ctrl+S to save, unsaved-changes warning.

## Setup (once)

```powershell
cd discharge-mnh
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\alembic upgrade head
.venv\Scripts\python scripts\seed_demo_data.py   # optional demo data
```

The first record save downloads the embedding model (~130 MB) into the
user cache; after that everything works offline.

## Run

```powershell
.venv\Scripts\python -m uvicorn app.main:app --port 8021
```

Open http://localhost:8021 in a browser. API docs live at /docs.
The server binds to localhost only; nothing is reachable from the network.

## Clinic letterhead

Edit `data/clinic.json` (clinic name, address, phone, doctor name,
qualifications, registration number). It feeds the app header and the
PDF letterhead. No restart needed for the PDF; reload the page for the
header.

## Backups and restore

- While the app runs, an encrypted backup is written to `data/backups/`
  whenever the newest one is older than 24 h (configurable via
  `DISCHARGE_BACKUP_INTERVAL_HOURS`).
- The backup password is generated once into `data/backup_password.txt`.
  **Write it down somewhere outside this computer** - a backup cannot be
  opened without it.
- Point backups at an external or synced drive with
  `DISCHARGE_BACKUP_DIR=E:\clinic-backups`, or register a nightly
  Task Scheduler job that also copies to another drive:

  ```powershell
  .\scripts\setup_backup_task.ps1 -CopyTo "E:\clinic-backups"
  ```

- Manual backup: `python scripts\backup_now.py [--copy-to E:\...]`
  or `POST /api/backup`.
- Restore (to a fresh folder, never straight over live data):

  ```powershell
  .venv\Scripts\python scripts\restore_backup.py data\backups\discharge_backup_XXXX.zip C:\restore-here
  ```

  Then stop the app, swap the restored folder in place of `data/`, and
  start the app again. Restores are integrity-checked automatically.

## Security notes

- The server listens on 127.0.0.1 only; responses carry a strict
  Content-Security-Policy and the UI never renders user input as HTML.
- Attachments are stored under random names, size-limited (25 MB default)
  and type-limited (PDF, images, Word).
- Backups are AES-256 encrypted.
- For at-rest protection of the live database, enable BitLocker device
  encryption on the machine (Settings > Privacy and security > Device
  encryption). SQLCipher was deliberately avoided: it complicates every
  future upgrade, and OS-level encryption protects the same threat
  (stolen or discarded hardware) more robustly.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

The recommender tests run against the real local embedding model - by
design there is no mocked model anywhere in the suite.

## Project layout

```
app/
  main.py            FastAPI app, static serving, security headers
  config.py          paths, env overrides, clinic.json loader
  database.py        engine, session, SQLite pragmas (WAL, FKs)
  models.py          Patient, DischargeRecord, TreatmentItem, Attachment
  schemas.py         pydantic request/response models
  routers/           patients, records, attachments, match, backups
  services/
    embeddings.py    local fastembed model, record text, backfill
    pdf_export.py    A4 discharge card renderer (reportlab)
    backup.py        encrypted backup/restore + scheduler
  static/            no-build UI (index.html, css, js)
alembic/             migrations (SQLite batch mode enabled)
scripts/             seed_demo_data, backup_now, restore_backup,
                     setup_backup_task.ps1
tests/               pytest suite (real embedding model, no mocks)
```

Data lives in `data/` (SQLite DB, attachments, backups, clinic.json),
which is git-ignored. `DISCHARGE_DATA_DIR` relocates it entirely.
