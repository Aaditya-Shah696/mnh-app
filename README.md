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
- One search box over every record: patient names, any word on the card
  (stemmed, prefix-matched, highlighted in the result) and, below those,
  records related by meaning with no word in common. A section filter
  narrows it to diagnosis, examination, investigations, course or medicines.
  See [Search and the vector store](#search-and-the-vector-store).
- Duplicate-entry warning: saving a new discharge for a patient who already
  has one admitted the same day, or a near-identical one within a week,
  asks before creating a second record.
- ICD-10-CM diagnosis codes: as the diagnosis is typed, likely codes are
  suggested (from the official index wording and synonyms, ranked by
  meaning); the doctor clicks to add them. Codes are stored on the record
  and searchable. See [Diagnosis codes](#diagnosis-codes-icd-10-cm).
- Medicine dose, route, and frequency fields are editable dropdown presets.
- Print-ready A4 discharge card PDF that leaves blank space at the top for
  pre-printed letterhead stationery. Draft records get a DRAFT watermark.
- Named users with two roles (staff, admin), server-side sessions, an
  append-only audit log of every view, print and edit, and soft delete
  with restore. See Security.
- Automatic daily encrypted backups (AES-256 zip) of the database and
  clinic config, retention of the newest 30.
- Draft / Final workflow, Ctrl+S to save, unsaved-changes warning.
- Optional AI drafting of "Course in hospital" (off by default): retrieves
  similar finalised past cases, strips identifiers, and asks Claude for a
  draft built only from the current record's facts, for the doctor to
  review. See [AI drafting](#ai-drafting-optional-off-by-default).

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
minute and deploys it (`scripts/autodeploy.sh` → `scripts/deploy.sh`, run
by root from root-owned copies in `/usr/local/lib/mnh`, never from the
checkout). A deploy that fails at any step is rolled back to the previous
commit, dependencies, schema and service files, and is not retried until
`production` moves again. The workflow finishes only when
`https://mnhapp.org/api/health` reports the pushed commit. GitHub holds no
server credentials.

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
| `DISCHARGE_BACKUP_DIR` | `data/backups` | where archives are written (`/srv/mnh-backups/archives` on the VPS, outside the database directory) |
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

## Search and the vector store

Everything runs inside the one SQLite file and the one app process; there is
no separate search or vector server to secure or back up.

**Vector store.** Each record is embedded by the local model
(bge-small-en-v1.5) once per section into the `record_vectors` table:

| Section | Text embedded | Used by |
|---|---|---|
| `summary` | diagnosis, history, treatment lines | similar cases, AI drafting, search |
| `examination` | general and per-system findings, signs present | search (Examination) |
| `investigations` | investigations | search (Investigations) |
| `course` | course in hospital | search (Course in hospital) |

Each row stores the SHA-256 of the exact text embedded, so saving a record
re-embeds only the sections whose text changed. If the model is down, the
vectors of changed sections are dropped rather than left describing old text,
and a background backfill at startup (and after any model change) fills
them in. Queries run against an in-memory matrix per section that is rebuilt
after any commit touching records or vectors; at clinic scale (tens of
thousands of records) a full scan is milliseconds.

sqlite-vec was considered and rejected: its Linux builds are compiled with
`-mavx -mavx2` whenever the build machine has AVX, and the VPS CPU (QEMU,
SSE3 only) does not, so the published wheels would crash there.

**Keyword index.** An SQLite FTS5 table, `record_search`, holds each record's
name, diagnosis, history, examination, investigations, course, medicines and
advice (Porter stemming, prefix indexes, BM25 weighted towards name and
diagnosis). It is derived data: the app creates it at startup, the record
and patient routes re-index what they change in the same transaction, and a
startup check compares every row's content hash so changes made outside the
API (seed scripts, restores) are caught. User input is reduced to quoted
words, so FTS5 operators typed into the box are inert.

**Ranking.** Records containing every typed word come first, ordered by
reciprocal rank fusion of their keyword rank and their meaning rank. Then
come at most five records related only by meaning, shown under their own
heading. bge-small similarities are compressed (noise ~0.5-0.6, real matches
~0.65-0.8), so a fixed cut-off is unreliable. On 18 test queries over the 19
demo records, a fixed cut-off gave about 0.4 precision. Instead a record must
stand out from the query's scores over all records (z-score >= 1.75) and
reach 0.55 similarity, which gave 0.78 precision at 0.61 recall. Queries use
BGE's retrieval instruction prefix, which lifted ranking quality (MRR) from
0.90 to 0.93. These numbers come from synthetic records: re-tune
`SEARCH_MIN_ZSCORE` / `SEARCH_MIN_SIMILARITY` in `app/config.py` once the old
cards are imported. Soft-deleted records never appear. Each search is audited
as `record.search` with the section and the ids returned, never the query
text.

## Diagnosis codes (ICD-10-CM)

Under the Diagnosis field, the app suggests ICD-10-CM codes for what has been
typed; clicking one adds it to the record (at most 10). A code can also be
typed directly (`J18.9`, `j189`), and the search box finds records by code.

**Source.** `app/data/icd10cm_2027.tsv`, built by `scripts/build_icd10cm.py`
from two public-domain CMS FY2027 files (effective 1 October 2026): the code
descriptions and the "Code Tables, Tabular and Index" release. The script
records both ZIPs' SHA-256 in the file header. It keeps the 36,378 billable
codes, minus external causes (V00-Y99) and non-initial-encounter injury
codes, and adds 56,660 phrases: the Alphabetic Index terms (e.g. "Fever,
enteric" -> A01.00) and the tabular inclusion terms ("Hand, foot and mouth
disease" -> B08.4). Each October, download the new year's two ZIPs, re-run
the script, and commit the new TSV; the app uses the newest one.

**ICD-10-CM is the US clinical modification, not WHO ICD-10.** The two agree
at the category level for most diagnoses but differ in places. For example,
dengue is A90/A91 in ICD-10-CM but A97.x in recent WHO ICD-10. If the clinic
must report in WHO ICD-10 (state returns, insurers), check the codes or ask
for a WHO mapping; WHO's ICD-10 files need a licence and are not used here.

**Ranking.** The diagnosis text is embedded and compared with every code
title and phrase; a code scores by its best phrase, and the matched phrase
is shown. Codes this clinic has already used get a small boost
(`USAGE_BOOST` in `app/services/codes.py`). On 24 demo diagnoses labelled by
the developer (not a clinical coder), the right code was first 16 times
(67%) and in the top five 20 times (83%). With code titles alone it was 11
and 17. Re-measure on real data with
`python scripts/eval_code_suggestions.py labels.tsv` (diagnosis<TAB>codes).
Typical misses: "lower lobe pneumonia" also matches "malignant neoplasm of
lower lobe", and venom codes come back with the wrong intent digit. The
doctor always chooses; nothing is coded automatically.

**Vectors.** The 93k phrase vectors (~70 MB, float16) are derived data,
built once in a background thread and cached in `data/cache/` (not in the
database, not in backups), keyed by model and code-file hash. The first
build took about 8 minutes on the development laptop; on the 2-vCPU VPS it
will take longer, with a short pause between batches so requests are
still served. Until it is ready, typed codes work and the picker shows
progress.

## AI drafting (optional, off by default)

A "Draft with AI" button next to **Course in hospital** writes a first draft
of that section for the doctor to review. It appears only when the server has
drafting switched on and an API key; otherwise the app behaves exactly as
before.

How a draft is made (retrieval-augmented generation):

1. **Retrieve.** The local embedding model finds the most similar
   *finalised* past records that have a course-in-hospital section (soft
   deleted and draft records are never used).
2. **De-identify.** The current record is turned into labelled clinical
   lines with no name, date of birth, IPD number, ward, calendar dates or
   doctor. Free text in it and in each past case is scrubbed of that
   patient's name parts, IPD number, phone numbers and dates. Length of stay
   is sent instead of dates.
3. **Generate.** Claude (`claude-sonnet-5-5` by default) returns structured
   output: the draft plus a list of facts the record does not state (for
   example "SpO2 at discharge?"). The prompt forbids adding facts that are
   not in the current record; past cases are used only for the doctor's
   style.
4. **Review.** The draft is shown in a panel; nothing is saved until the
   doctor presses *Use this draft*, edits as needed and saves the record.

Every request that reaches the model is written to the audit log as
`record.draft` with the outcome, the model, token counts and the ids of the
past cases sent (never any text). Each user is limited to 30 drafts an hour.
Refusals, timeouts and API errors are shown to the user as errors; there is
no canned or template fallback.

For local development the key can live in `data/anthropic_api_key.txt`
(git-ignored, not in backups) instead of the environment; this saves it
without echoing it:

```powershell
$k = Read-Host "Anthropic API key" -AsSecureString; [System.Net.NetworkCredential]::new('', $k).Password | Set-Content -NoNewline -Encoding ascii data\anthropic_api_key.txt
```

To switch it on, set in the environment (on the VPS, in `/srv/mnh/mnh.env`):

```
DISCHARGE_LLM_ENABLED=1
ANTHROPIC_API_KEY=sk-ant-...
# optional
DISCHARGE_LLM_MODEL=claude-sonnet-5-5
DISCHARGE_LLM_EFFORT=medium
DISCHARGE_LLM_HOURLY_LIMIT=30
```

Before switching it on for real patients: Dr. Shah's agreement, Anthropic's
data-retention terms in writing (ask for zero data retention), and an
evaluation on about 60 real past cards, comparing each draft with what the
doctor actually wrote.

## Backups and restore

- While the app runs, an encrypted backup is written to `data/backups/`
  whenever the newest one is older than 24 h. On the VPS a systemd timer
  also runs one at 21:30 IST. Archives are written under a temporary name
  and renamed when complete, and every writer (app, timer, CLI) takes the
  same file lock.
- Manual backup: `python scripts\backup_now.py [--copy-to E:\...]`
  or `POST /api/backup` (admin).
- On the VPS deployment the clinic PC pulls the archives nightly with
  `scripts\pull_backup.ps1` (registered by `scripts\setup_backup_task.ps1`).
- Restore (to a fresh folder, never straight over live data):

  ```powershell
  .venv\Scripts\python scripts\restore_backup.py data\backups\discharge_backup_XXXX.zip C:\restore-here --prompt
  ```

  `--prompt` asks for the password without echoing it; `--password-file`
  reads it from a file. Without either, `data/backup_password.txt` is used.

  Then stop the app, swap the restored folder in place of `data/`, run
  `alembic upgrade head`, and start the app again. Restores are
  integrity-checked automatically. Users and the audit log are inside the
  database, so they come back with it.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

The recommender tests run against the real local embedding model; by
design there is no mocked model anywhere in the suite. AI drafting is tested
the same way: `tests/test_drafting.py` covers de-identification, prompt
building, retrieval and every guard without calling the model, and
`tests/test_drafting_live.py` calls the real Anthropic API. It skips, saying
why, when `ANTHROPIC_API_KEY` is not set, and costs a few cents when it runs. Authentication is
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
  models.py          User, UserSession, LoginFailure, AuditLog, Patient, DischargeRecord, TreatmentItem
  querying.py        LIKE-pattern escaping for name search
  schemas.py         pydantic request/response models
  routers/           auth, users, audit, patients, records, match, search, codes, draft, backups
  services/
    embeddings.py    local model, per-section vector store, in-memory index, backfill
    search.py        FTS5 keyword index, hybrid ranking, highlighted snippets
    codes.py         ICD-10-CM code list, phrase vectors, suggestions
  data/              icd10cm_<year>.tsv (built by scripts/build_icd10cm.py)
    drafting.py      AI course-in-hospital drafting: retrieval, de-identification, Claude call
    pdf_export.py    A4 discharge card renderer (reportlab)
    backup.py        encrypted backup/restore + scheduler
  static/            no-build UI (index.html, css, js)
alembic/             migrations (SQLite batch mode enabled)
deploy/              systemd units, Caddyfile, fail2ban jail + filter, sshd block for the pull user
docs/RUNBOOK.md      build, deploy, backups, restore drill, incidents
scripts/             create_user, seed_demo_data, backup_now, restore_backup,
                     vps_bootstrap.sh, deploy_lib.sh, deploy.sh, autodeploy.sh,
                     lockdown_ssh.sh, pull_backup.ps1, setup_backup_task.ps1
tests/               pytest suite (real embedding model, real auth, no mocks)
```

Data lives in `data/` (SQLite DB, backups, clinic.json), which is
git-ignored. `DISCHARGE_DATA_DIR` relocates it entirely.
