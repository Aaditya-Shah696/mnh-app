/* MNH Discharge Records - single-page app, no build step.
   All user data is inserted via textContent / DOM APIs, never innerHTML. */
"use strict";

/* ---------- Icons (vendored from Phosphor Icons, MIT license) ---------- */

const ICONS = {
  plus: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 128a8 8 0 0 1-8 8h-80v80a8 8 0 0 1-16 0v-80H40a8 8 0 0 1 0-16h80V40a8 8 0 0 1 16 0v80h80a8 8 0 0 1 8 8Z"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M229.66 218.34l-50.07-50.06a88.11 88.11 0 1 0-11.31 11.31l50.06 50.07a8 8 0 0 0 11.32-11.32ZM40 112a72 72 0 1 1 72 72a72.08 72.08 0 0 1-72-72Z"/></svg>',
  "arrow-left": '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8Z"/></svg>',
  "file-pdf": '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 152a8 8 0 0 1-8 8h-24v16h16a8 8 0 0 1 0 16h-16v16a8 8 0 0 1-16 0v-56a8 8 0 0 1 8-8h32a8 8 0 0 1 8 8ZM92 172a28 28 0 0 1-28 28h-8v8a8 8 0 0 1-16 0v-56a8 8 0 0 1 8-8h16a28 28 0 0 1 28 28Zm-16 0a12 12 0 0 0-12-12h-8v24h8a12 12 0 0 0 12-12Zm88 8a36 36 0 0 1-36 36h-16a8 8 0 0 1-8-8v-56a8 8 0 0 1 8-8h16a36 36 0 0 1 36 36Zm-16 0a20 20 0 0 0-20-20h-8v40h8a20 20 0 0 0 20-20ZM40 112V40a16 16 0 0 1 16-16h96a8 8 0 0 1 5.66 2.34l56 56A8 8 0 0 1 216 88v24a8 8 0 0 1-16 0V96h-48a8 8 0 0 1-8-8V40H56v72a8 8 0 0 1-16 0ZM160 80h28.69L160 51.31Z"/></svg>',
  trash: '<svg width="15" height="15" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M216 48h-40v-8a24 24 0 0 0-24-24h-48a24 24 0 0 0-24 24v8H40a8 8 0 0 0 0 16h8v144a16 16 0 0 0 16 16h128a16 16 0 0 0 16-16V64h8a8 8 0 0 0 0-16ZM96 40a8 8 0 0 1 8-8h48a8 8 0 0 1 8 8v8H96Zm96 168H64V64h128Zm-80-104v64a8 8 0 0 1-16 0v-64a8 8 0 0 1 16 0Zm48 0v64a8 8 0 0 1-16 0v-64a8 8 0 0 1 16 0Z"/></svg>',
  copy: '<svg width="15" height="15" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M216 32H88a8 8 0 0 0-8 8v40H40a8 8 0 0 0-8 8v128a8 8 0 0 0 8 8h128a8 8 0 0 0 8-8v-40h40a8 8 0 0 0 8-8V40a8 8 0 0 0-8-8Zm-56 176H48V96h112Zm48-48h-32V88a8 8 0 0 0-8-8H96V48h112Z"/></svg>',
  user: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M230.92 212c-15.23-26.33-38.7-45.21-66.09-54.16a72 72 0 1 0-73.66 0c-27.39 8.94-50.86 27.82-66.09 54.16a8 8 0 1 0 13.85 8c18.84-32.56 52.14-52 89.07-52s70.23 19.44 89.07 52a8 8 0 1 0 13.85-8ZM72 96a56 56 0 1 1 56 56a56.06 56.06 0 0 1-56-56Z"/></svg>',
  "sign-out": '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M112 216a8 8 0 0 1-8 8H48a16 16 0 0 1-16-16V48a16 16 0 0 1 16-16h56a8 8 0 0 1 0 16H48v160h56a8 8 0 0 1 8 8Zm109.66-93.66l-40-40a8 8 0 0 0-11.32 11.32L196.69 120H104a8 8 0 0 0 0 16h92.69l-26.35 26.34a8 8 0 0 0 11.32 11.32l40-40a8 8 0 0 0 0-11.32Z"/></svg>',
};

function renderIcons(root) {
  (root || document).querySelectorAll("[data-icon]").forEach((span) => {
    const svg = ICONS[span.dataset.icon];
    if (svg) span.innerHTML = svg; // trusted constant strings only
  });
}

/* ---------- Small DOM helpers ---------- */

const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(child);
  }
  return node;
}

function iconEl(name) {
  const span = el("span");
  span.innerHTML = ICONS[name] || "";
  span.style.lineHeight = "0";
  return span;
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function toast(message, isError) {
  const host = $("toast-host");
  const node = el("div", { class: "toast" + (isError ? " toast-error" : ""), text: message });
  host.append(node);
  setTimeout(() => node.remove(), isError ? 5200 : 2600);
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

// Server timestamps are naive UTC ("2026-09-13T10:22:01"); mark them so the
// browser shows local time.
function fmtDateTime(iso) {
  if (!iso) return "";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) +
    " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function showError(id, message) {
  const node = $(id);
  node.textContent = message || "";
  node.classList.toggle("hidden", !message);
}

/* ---------- API ---------- */

async function api(path, options) {
  const opts = options || {};
  if (opts.json !== undefined) {
    opts.method = opts.method || "POST";
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers);
    opts.body = JSON.stringify(opts.json);
    delete opts.json;
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail) && data.detail[0]) {
        const d0 = data.detail[0];
        detail = (d0.loc ? d0.loc.join(".") + ": " : "") + d0.msg;
      }
    } catch (_) { /* keep statusText */ }
    if (res.status === 401 && !path.startsWith("/api/auth/login")) {
      handleUnauthenticated();
      detail = "Signed out. Sign in and try again.";
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- App state ---------- */

const state = {
  user: null,           // logged-in user from /api/auth/me
  booted: false,        // app views wired up (once, after first login)
  recordId: null,       // saved record id, null = unsaved new record
  recordDeleted: false, // editor is showing a soft-deleted record (read-only)
  patient: null,        // locked patient object, null = creating a new patient
  profilePatient: null, // patient shown on the profile view
  dirty: false,
  saving: false,
  matchAvailable: true, // set false when /api/match reports the model is down
  lastMatchKey: "",
  matchRequestSeq: 0,    // guards against out-of-order responses overwriting newer ones
  matchPanelCollapsed: localStorage.getItem("mnh:matchPanelCollapsed") === "1",
  audit: { offset: 0, total: 0, params: {} },
};

const isAdmin = () => Boolean(state.user && state.user.role === "admin");

const SCALAR_FIELDS = [
  "ipd_number", "ward", "age_at_admission", "weight", "height",
  "diagnosis", "history",
  "examination_findings", "temperature", "pulse", "bp", "resp_rate",
  "spo2", "throat_findings", "respiratory_system", "cvs_system",
  "abdominal_exam", "cns_system", "investigations", "course_in_hospital",
  "advice", "follow_up_notes", "doctor_name",
];
const DATE_FIELDS = ["admission_date", "discharge_date", "follow_up_date"];
// Checkbox signs: ticked saves "yes", unticked saves "no".
const SIGN_FIELDS = [
  "pallor", "icterus", "rash", "cyanosis", "meningeal_signs", "dehydration_signs",
];

/* ---------- Authentication ---------- */

function setUser(user) {
  state.user = user;
  const admin = isAdmin();
  if (user) {
    $("user-name").textContent = user.display_name;
    $("user-role").textContent = user.role === "admin" ? "Admin" : "Staff";
    $("user-role").classList.toggle("is-admin", admin);
  }
  document.querySelectorAll(".admin-only").forEach((node) => node.classList.toggle("hidden", !admin));
}

function showLogin(resume) {
  $("login-resume").classList.toggle("hidden", !resume);
  showError("login-error", "");
  $("login-password").value = "";
  if (!resume) {
    $("appbar").classList.add("hidden");
    $("page").classList.add("hidden");
    $("login-username").value = "";
  }
  $("login-overlay").classList.remove("hidden");
  ($("login-username").value ? $("login-password") : $("login-username")).focus();
}

function hideLogin() {
  $("login-overlay").classList.add("hidden");
  $("appbar").classList.remove("hidden");
  $("page").classList.remove("hidden");
}

function handleUnauthenticated() {
  const wasSignedIn = Boolean(state.user);
  if (wasSignedIn) {
    state.user = null;
    showLogin(true);
  } else if ($("login-overlay").classList.contains("hidden")) {
    showLogin(false);
  }
}

async function submitLogin(event) {
  event.preventDefault();
  const username = $("login-username").value.trim();
  const password = $("login-password").value;
  if (!username || !password) {
    showError("login-error", "Enter your username and password.");
    return;
  }
  $("login-submit").disabled = true;
  showError("login-error", "");
  let user;
  try {
    user = await api("/api/auth/login", { json: { username, password } });
  } catch (err) {
    showError("login-error", err.status === 429
      ? "Too many attempts from this device. Wait ten minutes and try again."
      : err.message);
    $("login-password").value = "";
    $("login-password").focus();
    return;
  } finally {
    $("login-submit").disabled = false;
  }
  const resuming = !$("login-resume").classList.contains("hidden");
  setUser(user);
  hideLogin();
  if (!state.booted) {
    startApp();
  } else if (resuming) {
    const editing = !$("view-editor").classList.contains("hidden");
    if (editing && state.dirty) toast("Signed in again. Press Save to keep your changes.");
    else route();
  }
}

async function logout() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* cookie cleared anyway */ }
  state.user = null;
  state.dirty = false;
  location.hash = "";
  showLogin(false);
}

async function submitPasswordChange(event) {
  event.preventDefault();
  const current = $("pw-current").value;
  const fresh = $("pw-new").value;
  if (fresh.length < 12) { showError("pw-error", "New password must be at least 12 characters."); return; }
  if (fresh !== $("pw-repeat").value) { showError("pw-error", "The new passwords do not match."); return; }
  try {
    await api("/api/auth/password", { json: { current_password: current, new_password: fresh } });
  } catch (err) {
    showError("pw-error", err.message);
    return;
  }
  $("dlg-password").close();
  toast("Password changed. Other devices were signed out.");
}

/* ---------- Dialog helpers ---------- */

function openDialog(id, onOpen) {
  const dlg = $(id);
  dlg.querySelectorAll(".field-error").forEach((n) => n.classList.add("hidden"));
  dlg.querySelectorAll("input").forEach((i) => { i.value = ""; });
  if (onOpen) onOpen(dlg);
  dlg.showModal();
  const first = dlg.querySelector("input, select");
  if (first) first.focus();
}

let confirmResolver = null;

function confirmDialog(title, message, okLabel, danger) {
  $("confirm-title").textContent = title;
  $("confirm-message").textContent = message;
  const ok = $("confirm-ok");
  ok.textContent = okLabel || "Confirm";
  ok.className = danger ? "btn-danger" : "btn-primary";
  return new Promise((resolve) => {
    confirmResolver = resolve;
    $("dlg-confirm").showModal();
    ok.focus();
  });
}

function wireDialogs() {
  document.querySelectorAll("dialog.dialog").forEach((dlg) => {
    dlg.querySelectorAll("[data-close]").forEach((btn) => btn.addEventListener("click", () => dlg.close()));
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  });
  $("form-confirm").addEventListener("submit", (e) => {
    e.preventDefault();
    $("dlg-confirm").close();
    if (confirmResolver) { confirmResolver(true); confirmResolver = null; }
  });
  $("dlg-confirm").addEventListener("close", () => {
    if (confirmResolver) { confirmResolver(false); confirmResolver = null; }
  });
  $("form-password").addEventListener("submit", submitPasswordChange);
  $("form-user").addEventListener("submit", submitNewUser);
  $("form-reset").addEventListener("submit", submitResetPassword);
}

/* ---------- Routing ---------- */

const VIEWS = ["view-home", "view-editor", "view-patients", "view-patient", "view-users", "view-audit"];

function showView(id) {
  for (const view of VIEWS) $(view).classList.toggle("hidden", view !== id);
}

function route() {
  if (!state.user) return;
  const hash = location.hash.replace(/^#\/?/, "");
  if (hash === "record/new") showEditor(null, null);
  else if (/^record\/new\/\d+$/.test(hash)) showEditor(null, Number(hash.split("/")[2]));
  else if (/^record\/\d+$/.test(hash)) showEditor(Number(hash.split("/")[1]), null);
  else if (hash === "patients") showPatients();
  else if (/^patient\/\d+$/.test(hash)) showPatientProfile(Number(hash.split("/")[1]));
  else if (hash === "users" && isAdmin()) showUsers();
  else if (hash === "audit" && isAdmin()) showAudit();
  else showHome();
}

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

/* ---------- Home view ---------- */

async function showHome() {
  showView("view-home");
  loadBackupStatus();
  await loadRecordList($("home-search").value.trim());
}

async function loadBackupStatus() {
  try {
    const status = await api("/api/backup/status");
    $("backup-status").textContent = status.last_backup
      ? "Last automatic backup: " + fmtDate(status.last_backup) + ", " +
        new Date(status.last_backup).toLocaleTimeString(undefined,
          { hour: "2-digit", minute: "2-digit" }) +
        " (" + status.backup_count + " kept)"
      : "No backup yet. The first automatic backup runs shortly after the app starts.";
  } catch (_) {
    $("backup-status").textContent = "";
  }
}

function restoreButton(label, onclick) {
  return el("span", { class: "r-actions" },
    el("button", {
      class: "btn-secondary", type: "button",
      onclick: (e) => { e.stopPropagation(); onclick(); },
    }, label));
}

async function loadRecordList(query) {
  const list = $("home-list");
  const showDeleted = isAdmin() && $("home-show-deleted").checked;
  list.replaceChildren(
    ...Array.from({ length: 4 }, () => el("div", { class: "skeleton-row" }))
  );
  let records;
  try {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (showDeleted) params.set("deleted", "true");
    const qs = params.toString();
    records = await api("/api/records" + (qs ? "?" + qs : ""));
  } catch (err) {
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: "Could not load records" }),
      el("div", { text: err.message })));
    return;
  }
  if (!records.length) {
    const title = showDeleted ? "No deleted records"
      : query ? "No records match “" + query + "”" : "No discharge records yet";
    const hint = showDeleted ? "Deleted records can be restored from this list."
      : query ? "Check the spelling of the patient's name."
      : "Use the New discharge button above to create the first one.";
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: title }),
      el("div", { text: hint })));
    return;
  }
  list.replaceChildren(...records.map((r) =>
    el("button", {
      class: "record-row" + (r.deleted_at ? " is-deleted" : ""), type: "button",
      onclick: () => navigate("#/record/" + r.id),
    },
      el("span", { class: "r-name", text: r.patient_name }),
      el("span", { class: "r-dx", text: r.diagnosis || "No diagnosis recorded" }),
      r.deleted_at
        ? restoreButton("Restore", () => restoreRecord(r.id))
        : (r.status === "draft" ? el("span", { class: "chip chip-draft", text: "Draft" }) : null),
      el("span", { class: "r-date", text: fmtDate(r.discharge_date || r.admission_date || r.updated_at) }),
    )
  ));
}

/* ---------- Patients list + profile ---------- */

async function showPatients() {
  showView("view-patients");
  await loadPatientList($("patients-search").value.trim());
}

async function loadPatientList(query) {
  const list = $("patients-list");
  const showDeleted = isAdmin() && $("patients-show-deleted").checked;
  list.replaceChildren(
    ...Array.from({ length: 4 }, () => el("div", { class: "skeleton-row" }))
  );
  let patients;
  try {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (showDeleted) params.set("deleted", "true");
    const qs = params.toString();
    patients = await api("/api/patients" + (qs ? "?" + qs : ""));
  } catch (err) {
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: "Could not load patients" }),
      el("div", { text: err.message })));
    return;
  }
  if (!patients.length) {
    const title = showDeleted ? "No deleted patients"
      : query ? "No patients match “" + query + "”" : "No patients yet";
    const hint = showDeleted ? "Deleted patients can be restored from this list."
      : query ? "Check the spelling of the patient's name."
      : "Patients are created with their first discharge record.";
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: title }),
      el("div", { text: hint })));
    return;
  }
  list.replaceChildren(...patients.map((p) =>
    el("button", {
      class: "record-row" + (p.deleted_at ? " is-deleted" : ""), type: "button",
      onclick: () => navigate("#/patient/" + p.id),
    },
      el("span", { class: "r-name", text: p.name }),
      el("span", {
        class: "r-dx",
        text: [p.sex, p.dob ? "b. " + fmtDate(p.dob) : "", p.chronic_conditions]
          .filter(Boolean).join(" · ") || "No details on file",
      }),
      p.deleted_at ? restoreButton("Restore", () => restorePatient(p.id)) : el("span"),
      el("span", { class: "r-date", text: fmtDate(p.updated_at) }),
    )
  ));
}

function demographicItem(label, value) {
  return el("div", {},
    el("div", { class: "pm-label", text: label }),
    el("div", { class: "pm-value", text: value || "—" }),
  );
}

async function fetchPossiblyDeleted(path) {
  // Normal fetch first; an admin retries with include_deleted to open a
  // soft-deleted item read-only.
  try {
    return await api(path);
  } catch (err) {
    if (err.status === 404 && isAdmin()) {
      return api(path + (path.includes("?") ? "&" : "?") + "include_deleted=true");
    }
    throw err;
  }
}

async function showPatientProfile(patientId) {
  showView("view-patient");
  $("patient-title").textContent = "Patient";
  $("patient-save-status").textContent = "";
  $("patient-deleted-banner").classList.add("hidden");
  $("btn-delete-patient").classList.add("hidden");
  $("btn-restore-patient").classList.add("hidden");
  let patient, records;
  try {
    patient = await fetchPossiblyDeleted("/api/patients/" + patientId);
    const deleted = Boolean(patient.deleted_at);
    records = await api("/api/patients/" + patientId + "/records" + (deleted ? "?include_deleted=true" : ""));
  } catch (err) {
    toast("Could not open patient: " + err.message, true);
    navigate("#/patients");
    return;
  }
  state.profilePatient = patient;
  const deleted = Boolean(patient.deleted_at);
  $("patient-title").textContent = patient.name;
  $("patient-demographics").replaceChildren(
    demographicItem("Sex", patient.sex),
    demographicItem("Date of birth", patient.dob ? fmtDate(patient.dob) : ""),
    demographicItem("On file since", fmtDate(patient.created_at)),
  );
  $("pp-chronic_conditions").value = patient.chronic_conditions || "";
  $("pp-past_history").value = patient.past_history || "";
  $("pp-chronic_conditions").disabled = deleted;
  $("pp-past_history").disabled = deleted;
  $("btn-save-patient").disabled = deleted;
  $("btn-new-for-patient").disabled = deleted;
  if (deleted) {
    $("patient-deleted-banner").textContent =
      "This patient was deleted on " + fmtDateTime(patient.deleted_at) + ". The profile is read-only until restored.";
    $("patient-deleted-banner").classList.remove("hidden");
    $("btn-restore-patient").classList.toggle("hidden", !isAdmin());
  } else {
    $("btn-delete-patient").classList.toggle("hidden", !isAdmin());
  }

  const visits = $("patient-visits");
  if (!records.length) {
    visits.replaceChildren(el("div", { class: "muted", text: "No discharge records yet." }));
    return;
  }
  visits.replaceChildren(...records.map((r) =>
    el("button", {
      class: "record-row" + (r.deleted_at ? " is-deleted" : ""), type: "button",
      onclick: () => navigate("#/record/" + r.id),
    },
      el("span", { class: "r-name", text: fmtDate(r.discharge_date || r.admission_date || r.updated_at) }),
      el("span", { class: "r-dx", text: r.diagnosis || "No diagnosis recorded" }),
      r.deleted_at ? el("span", { class: "chip chip-deleted", text: "Deleted" })
        : r.status === "draft" ? el("span", { class: "chip chip-draft", text: "Draft" }) : null,
    )
  ));
}

async function savePatientProfile() {
  const patient = state.profilePatient;
  if (!patient) return;
  $("btn-save-patient").disabled = true;
  $("patient-save-status").textContent = "Saving…";
  try {
    const updated = await api("/api/patients/" + patient.id, {
      method: "PUT",
      json: {
        name: patient.name,
        sex: patient.sex,
        dob: patient.dob,
        chronic_conditions: $("pp-chronic_conditions").value.trim() || null,
        past_history: $("pp-past_history").value.trim() || null,
      },
    });
    state.profilePatient = updated;
    $("patient-save-status").textContent = "Saved";
    toast("Profile saved");
  } catch (err) {
    $("patient-save-status").textContent = "Not saved";
    toast("Save failed: " + err.message, true);
  } finally {
    $("btn-save-patient").disabled = false;
  }
}

async function deletePatient() {
  const patient = state.profilePatient;
  if (!patient) return;
  const ok = await confirmDialog(
    "Delete " + patient.name + "?",
    "The patient and all their discharge records are hidden everywhere, including the similar-cases panel. Nothing is erased: an administrator can restore them from the Patients list.",
    "Delete patient", true,
  );
  if (!ok) return;
  try {
    await api("/api/patients/" + patient.id, { method: "DELETE" });
    toast("Patient deleted");
    navigate("#/patients");
  } catch (err) {
    toast("Delete failed: " + err.message, true);
  }
}

async function restorePatient(patientId) {
  try {
    await api("/api/patients/" + patientId + "/restore", { method: "POST" });
    toast("Patient restored");
    route();
  } catch (err) {
    toast("Restore failed: " + err.message, true);
  }
}

/* ---------- Treatment tables ---------- */

const TX_COLUMNS = [
  ["drug", "Medicine"],
  ["dose", "Dose"],
  ["route", "Route"],
  ["frequency", "Frequency"],
  ["duration", "Duration"],
  ["instructions", "Instructions"],
];

function txHeaderRow() {
  const row = el("div", { class: "tx-row tx-header-row" });
  for (const [, label] of TX_COLUMNS) row.append(el("span", { class: "tx-head", text: label }));
  row.append(el("span"));
  return row;
}

function addTxRow(containerId, values) {
  const container = $(containerId);
  if (!container.querySelector(".tx-header-row")) container.append(txHeaderRow());
  const row = el("div", { class: "tx-row" });
  const TX_PRESET_LISTS = {
    route: "route-presets", frequency: "freq-presets", instructions: "instructions-presets",
  };
  for (const [key, label] of TX_COLUMNS) {
    row.append(el("input", {
      type: "text", "data-tx": key, "aria-label": label,
      value: (values && values[key]) || "",
      list: TX_PRESET_LISTS[key] || null,
      oninput: markDirty,
    }));
  }
  row.append(el("button", {
    class: "btn-danger-ghost btn-icon", type: "button", title: "Remove line",
    "aria-label": "Remove line",
    onclick: () => { row.remove(); markDirty(); },
  }, iconEl("trash")));
  container.append(row);
  return row;
}

function readTxTable(containerId, category) {
  const items = [];
  $(containerId).querySelectorAll(".tx-row:not(.tx-header-row)").forEach((row) => {
    const item = { category };
    let hasDrug = false;
    row.querySelectorAll("input[data-tx]").forEach((input) => {
      const v = input.value.trim();
      item[input.dataset.tx] = v || null;
      if (input.dataset.tx === "drug" && v) hasDrug = true;
    });
    if (hasDrug) items.push(item);
  });
  return items;
}

function fillTxTable(containerId, items) {
  $(containerId).replaceChildren();
  for (const item of items) addTxRow(containerId, item);
}

/* ---------- Patient picker ---------- */

function lockPatient(patient) {
  state.patient = patient;
  $("pl-name").textContent = patient.name;
  const bits = [];
  if (patient.sex) bits.push(patient.sex);
  if (patient.dob) bits.push("b. " + fmtDate(patient.dob));
  $("pl-meta").textContent = bits.join(", ") || "No details on file";
  $("patient-locked").classList.remove("hidden");
  $("patient-editor").classList.add("hidden");
  hideSuggestions();
}

function unlockPatient() {
  state.patient = null;
  $("patient-locked").classList.add("hidden");
  $("patient-editor").classList.remove("hidden");
  $("p-name").focus();
  markDirty();
}

function hideSuggestions() {
  $("patient-suggestions").classList.add("hidden");
}

const suggestPatients = debounce(async () => {
  const q = $("p-name").value.trim();
  const box = $("patient-suggestions");
  if (q.length < 2) { hideSuggestions(); return; }
  let patients;
  try {
    patients = await api("/api/patients?q=" + encodeURIComponent(q));
  } catch (_) { hideSuggestions(); return; }
  if (!patients.length) { hideSuggestions(); return; }
  box.replaceChildren(...patients.slice(0, 8).map((p) =>
    el("button", { type: "button", onclick: () => { lockPatient(p); markDirty(); } },
      el("span", { text: p.name }),
      el("span", {
        class: "ps-meta",
        text: [p.sex, p.dob ? fmtDate(p.dob) : ""].filter(Boolean).join(", "),
      }),
    )
  ));
  box.classList.remove("hidden");
}, 250);

/* ---------- Editor ---------- */

function setSaveStatus(text) {
  $("save-status").textContent = text;
}

function markDirty() {
  if (state.recordDeleted) return;
  if (!state.dirty) {
    state.dirty = true;
    setSaveStatus("Unsaved changes");
  }
  scheduleMatch();
}

function setFormReadOnly(readOnly) {
  $("record-form").querySelectorAll("input, select, textarea, button").forEach((node) => {
    node.disabled = readOnly;
  });
  $("btn-save").disabled = readOnly;
  $("btn-toggle-match").disabled = readOnly;
}

function updateEditorAdminButtons() {
  const saved = state.recordId !== null;
  $("btn-delete-record").classList.toggle("hidden", !(isAdmin() && saved && !state.recordDeleted));
  $("btn-restore-record").classList.toggle("hidden", !(isAdmin() && saved && state.recordDeleted));
}

function clearForm() {
  setFormReadOnly(false);
  state.recordDeleted = false;
  $("record-deleted-banner").classList.add("hidden");
  for (const key of SCALAR_FIELDS) $("f-" + key).value = "";
  for (const key of DATE_FIELDS) $("f-" + key).value = "";
  for (const key of SIGN_FIELDS) $("f-" + key).checked = false;
  $("f-status").value = "draft";
  ["p-name", "p-dob"].forEach((id) => { $(id).value = ""; });
  $("p-sex").value = "";
  fillTxTable("tx-hospital", []);
  fillTxTable("tx-discharge", []);
  addTxRow("tx-hospital");
  addTxRow("tx-discharge");
  $("match-list").replaceChildren();
  $("match-panel-wrap").classList.add("hidden");
  $("editor-layout").classList.remove("has-panel");
  state.lastMatchKey = "";
  $("err-p-name").classList.add("hidden");
  $("p-name").classList.remove("input-invalid");
}

async function showEditor(recordId, patientId) {
  showView("view-editor");
  clearForm();
  state.recordId = recordId;
  state.dirty = false;
  setSaveStatus("");
  updateEditorAdminButtons();

  if (recordId === null) {
    $("editor-title").textContent = "New discharge";
    $("editor-status-chip").replaceChildren();
    unlockPatient();
    if (patientId) {
      // "New discharge for this patient": lock and prefill from the profile.
      try {
        const patient = await api("/api/patients/" + patientId);
        lockPatient(patient);
        $("editor-title").textContent = "New discharge · " + patient.name;
      } catch (err) {
        toast("Could not load patient: " + err.message, true);
      }
    }
    state.dirty = false;
    setSaveStatus("");
    setSavedControlsEnabled(false);
    prefillDoctor();
    return;
  }

  setSaveStatus("Loading…");
  let record;
  try {
    record = await fetchPossiblyDeleted("/api/records/" + recordId);
  } catch (err) {
    toast("Could not open record: " + err.message, true);
    navigate("#/");
    return;
  }
  $("editor-title").textContent = "Discharge · " + record.patient.name;
  lockPatient(record.patient);
  for (const key of SCALAR_FIELDS) $("f-" + key).value = record[key] || "";
  for (const key of SIGN_FIELDS) $("f-" + key).checked = record[key] === "yes";
  $("f-admission_date").value = (record.admission_date || "").slice(0, 16);
  $("f-discharge_date").value = (record.discharge_date || "").slice(0, 16);
  $("f-follow_up_date").value = record.follow_up_date || "";
  $("f-status").value = record.status;
  fillTxTable("tx-hospital", record.treatment_items.filter((t) => t.category === "hospital"));
  fillTxTable("tx-discharge", record.treatment_items.filter((t) => t.category === "discharge"));
  if (!$("tx-hospital").children.length) addTxRow("tx-hospital");
  if (!$("tx-discharge").children.length) addTxRow("tx-discharge");
  updateStatusChip();
  state.dirty = false;
  if (record.deleted_at) {
    state.recordDeleted = true;
    $("record-deleted-banner").textContent =
      "This record was deleted on " + fmtDateTime(record.deleted_at) + ". It is read-only until restored.";
    $("record-deleted-banner").classList.remove("hidden");
    setFormReadOnly(true);
    setSavedControlsEnabled(false);
    setSaveStatus("Deleted");
    updateEditorAdminButtons();
    return;
  }
  setSavedControlsEnabled(true);
  setSaveStatus("All changes saved");
  updateEditorAdminButtons();
  scheduleMatch();
}

async function prefillDoctor() {
  try {
    const clinic = await api("/api/clinic");
    if (clinic.doctor_name && !$("f-doctor_name").value) {
      $("f-doctor_name").value = clinic.doctor_name;
    }
  } catch (_) { /* optional prefill only */ }
}

function updateStatusChip() {
  const isDraft = $("f-status").value === "draft";
  $("editor-status-chip").replaceChildren(
    ...(isDraft ? [el("span", { class: "chip chip-draft", text: "Draft" })] : [])
  );
}

function setSavedControlsEnabled(enabled) {
  $("btn-export-pdf").disabled = !enabled;
  $("btn-export-pdf").title = enabled ? "" : "Save the record first";
}

function collectRecordPayload() {
  const payload = {};
  for (const key of SCALAR_FIELDS) {
    const v = $("f-" + key).value.trim();
    payload[key] = v || null;
  }
  for (const key of DATE_FIELDS) {
    payload[key] = $("f-" + key).value || null;
  }
  for (const key of SIGN_FIELDS) {
    payload[key] = $("f-" + key).checked ? "yes" : "no";
  }
  payload.status = $("f-status").value;
  payload.treatment_items = [
    ...readTxTable("tx-hospital", "hospital"),
    ...readTxTable("tx-discharge", "discharge"),
  ];
  return payload;
}

async function ensurePatient() {
  if (state.patient) return state.patient;
  const name = $("p-name").value.trim();
  if (!name) {
    $("err-p-name").textContent = "Enter the patient's name before saving.";
    $("err-p-name").classList.remove("hidden");
    $("p-name").classList.add("input-invalid");
    $("p-name").focus();
    throw new Error("Patient name is required");
  }
  $("err-p-name").classList.add("hidden");
  $("p-name").classList.remove("input-invalid");
  const patient = await api("/api/patients", {
    json: {
      name,
      sex: $("p-sex").value || null,
      dob: $("p-dob").value || null,
    },
  });
  lockPatient(patient);
  return patient;
}

async function saveRecord() {
  if (state.saving || state.recordDeleted) return;
  state.saving = true;
  $("btn-save").disabled = true;
  setSaveStatus("Saving…");
  try {
    const patient = await ensurePatient();
    const payload = collectRecordPayload();
    let record;
    if (state.recordId === null) {
      payload.patient_id = patient.id;
      record = await api("/api/records", { json: payload });
      state.recordId = record.id;
      history.replaceState(null, "", "#/record/" + record.id);
    } else {
      record = await api("/api/records/" + state.recordId, { method: "PUT", json: payload });
    }
    $("editor-title").textContent = "Discharge · " + record.patient.name;
    updateStatusChip();
    setSavedControlsEnabled(true);
    updateEditorAdminButtons();
    state.dirty = false;
    setSaveStatus("All changes saved");
    toast("Record saved");
  } catch (err) {
    setSaveStatus(err.status === 401 ? "Sign in to save" : "Not saved");
    toast("Save failed: " + err.message, true);
  } finally {
    state.saving = false;
    $("btn-save").disabled = false;
  }
}

async function deleteRecord() {
  if (state.recordId === null) return;
  const ok = await confirmDialog(
    "Delete this discharge record?",
    "It is hidden from lists, the patient's visits and the similar-cases panel. Nothing is erased: an administrator can restore it from the Records list with “Show deleted”.",
    "Delete record", true,
  );
  if (!ok) return;
  try {
    await api("/api/records/" + state.recordId, { method: "DELETE" });
    state.dirty = false;
    toast("Record deleted");
    navigate("#/");
  } catch (err) {
    toast("Delete failed: " + err.message, true);
  }
}

async function restoreRecord(recordId) {
  try {
    await api("/api/records/" + recordId + "/restore", { method: "POST" });
    toast("Record restored");
    route();
  } catch (err) {
    toast("Restore failed: " + err.message, true);
  }
}

/* ---------- Similar cases (match panel) ---------- */

function matchQueryText() {
  const treatment = [
    ...readTxTable("tx-hospital", "hospital"),
    ...readTxTable("tx-discharge", "discharge"),
  ].map((t) => [t.drug, t.dose, t.frequency, t.duration].filter(Boolean).join(" ")).join("; ");
  return [
    $("f-diagnosis").value,
    $("f-history").value,
    treatment,
  ].map((s) => s.trim()).filter(Boolean).join("\n");
}

const scheduleMatch = debounce(runMatch, 500);

function updateMatchToggleButton() {
  $("btn-toggle-match").textContent =
    state.matchPanelCollapsed ? "Show similar cases" : "Hide similar cases";
}

function toggleMatchPanel() {
  state.matchPanelCollapsed = !state.matchPanelCollapsed;
  localStorage.setItem("mnh:matchPanelCollapsed", state.matchPanelCollapsed ? "1" : "0");
  updateMatchToggleButton();
  if (state.matchPanelCollapsed) {
    $("match-panel-wrap").classList.add("hidden");
    $("editor-layout").classList.remove("has-panel");
  } else {
    state.lastMatchKey = ""; // force a re-fetch now that it's visible again
    runMatch();
  }
}

async function runMatch() {
  if (!state.matchAvailable) return;
  if (state.matchPanelCollapsed) return;
  if (state.recordDeleted) return;
  if ($("view-editor").classList.contains("hidden")) return;
  const text = matchQueryText();
  const wrap = $("match-panel-wrap");
  const list = $("match-list");
  if (text.length < 8) {
    wrap.classList.add("hidden");
    $("editor-layout").classList.remove("has-panel");
    state.lastMatchKey = "";
    return;
  }
  if (text === state.lastMatchKey) return;
  state.lastMatchKey = text;

  // A request fired while the embedding model is still cold-loading (seen
  // ~3.5s in practice, vs ~50ms once warm) can resolve AFTER a later,
  // faster request for newer text. Without this guard the stale response
  // wins the race and overwrites the fresher results on screen.
  const requestId = ++state.matchRequestSeq;

  let results;
  try {
    results = await api("/api/match", {
      json: { text, limit: 5, exclude_record_id: state.recordId },
    });
  } catch (err) {
    if (requestId !== state.matchRequestSeq) return; // superseded by a newer request
    if (err.status === 503) {
      state.matchAvailable = false;
      wrap.classList.remove("hidden");
      $("editor-layout").classList.add("has-panel");
      list.replaceChildren(el("div", { class: "muted", text: "Similar-case search is unavailable: " + err.message }));
    }
    return;
  }
  if (requestId !== state.matchRequestSeq) return; // superseded by a newer request
  wrap.classList.remove("hidden");
  $("editor-layout").classList.add("has-panel");
  if (!results.length) {
    list.replaceChildren(el("div", { class: "muted", text: "No similar past cases yet. Matches appear here as records build up." }));
    return;
  }
  list.replaceChildren(...results.map(renderMatchItem));
}

function renderMatchItem(result) {
  const record = result.record;
  const discharge = record.treatment_items.filter((t) => t.category === "discharge");
  const txText = discharge
    .map((t) => [t.drug, t.dose, t.frequency, t.duration].filter(Boolean).join(" "))
    .join("; ");
  const when = fmtDate(record.discharge_date || record.admission_date);
  return el("div", { class: "match-item" },
    el("div", { class: "m-head" },
      el("span", { class: "m-name", text: record.patient.name + (when ? " · " + when : "") }),
      el("span", { class: "m-score", text: Math.round(result.score * 100) + "%" }),
    ),
    el("div", { class: "m-dx", text: record.diagnosis || "No diagnosis recorded" }),
    txText ? el("div", { class: "m-tx", text: "Rx: " + txText }) : null,
    el("div", { class: "m-actions" },
      discharge.length
        ? el("button", {
            class: "btn-secondary", type: "button",
            onclick: () => copyTreatment(record),
          }, iconEl("copy"), "Copy medicines")
        : null,
      el("button", {
        class: "btn-ghost", type: "button",
        onclick: () => window.open("#/record/" + record.id, "_blank"),
      }, "Open record"),
    ),
  );
}

function copyTreatment(record) {
  const discharge = record.treatment_items.filter((t) => t.category === "discharge");
  const existing = new Set(
    readTxTable("tx-discharge", "discharge").map((t) => (t.drug || "").toLowerCase())
  );
  // Drop the single empty starter row if it is the only one
  const container = $("tx-discharge");
  const rows = container.querySelectorAll(".tx-row:not(.tx-header-row)");
  if (rows.length === 1) {
    const drug = rows[0].querySelector('input[data-tx="drug"]');
    if (drug && !drug.value.trim()) rows[0].remove();
  }
  let added = 0;
  for (const item of discharge) {
    if (existing.has(item.drug.toLowerCase())) continue;
    addTxRow("tx-discharge", item);
    added += 1;
  }
  if (!$("f-advice").value.trim() && record.advice) {
    $("f-advice").value = record.advice;
  }
  markDirty();
  toast(added ? "Copied " + added + " medicine" + (added === 1 ? "" : "s") : "Medicines already on the list");
}

/* ---------- Users (admin) ---------- */

function userStatus(u) {
  if (!u.is_active) return el("span", { class: "chip chip-deleted", text: "Inactive" });
  if (u.locked_until && new Date(u.locked_until + "Z") > new Date()) {
    return el("span", { class: "chip chip-draft", text: "Locked until " + fmtDateTime(u.locked_until) });
  }
  return el("span", { class: "chip chip-ok", text: "Active" });
}

async function showUsers() {
  showView("view-users");
  const host = $("users-table");
  host.replaceChildren(el("div", { class: "skeleton-row" }), el("div", { class: "skeleton-row" }));
  let users;
  try {
    users = await api("/api/users");
  } catch (err) {
    host.replaceChildren(el("div", { class: "empty-state", text: "Could not load users: " + err.message }));
    return;
  }
  const me = state.user;
  const table = el("table", { class: "data" },
    el("thead", {}, el("tr", {},
      ...["Username", "Name", "Role", "Status", "Last sign-in", "Actions"].map((h) => el("th", { text: h })))),
    el("tbody", {}, ...users.map((u) => {
      const self = me && u.id === me.id;
      const actions = el("div", { class: "row-actions" },
        el("button", { class: "btn-secondary", type: "button", onclick: () => openResetDialog(u) }, "Reset password"),
        u.locked_until ? el("button", {
          class: "btn-secondary", type: "button", onclick: () => patchUser(u, { unlock: true }, "Account unlocked"),
        }, "Unlock") : null,
        self ? null : el("button", {
          class: "btn-secondary", type: "button",
          onclick: () => patchUser(u, { role: u.role === "admin" ? "staff" : "admin" },
            u.role === "admin" ? "Now staff" : "Now an administrator"),
        }, u.role === "admin" ? "Make staff" : "Make admin"),
        self ? null : el("button", {
          class: u.is_active ? "btn-danger-ghost" : "btn-secondary", type: "button",
          onclick: async () => {
            if (u.is_active) {
              const ok = await confirmDialog("Deactivate " + u.display_name + "?",
                "They are signed out everywhere immediately and cannot sign in again until reactivated. Their name stays on every record and audit entry.",
                "Deactivate", true);
              if (!ok) return;
            }
            patchUser(u, { is_active: !u.is_active }, u.is_active ? "User deactivated" : "User reactivated");
          },
        }, u.is_active ? "Deactivate" : "Reactivate"),
      );
      return el("tr", {},
        el("td", { class: "mono", text: u.username + (self ? " (you)" : "") }),
        el("td", { class: "wrap", text: u.display_name }),
        el("td", {}, el("span", { class: "chip chip-role" + (u.role === "admin" ? " is-admin" : ""),
          text: u.role === "admin" ? "Admin" : "Staff" })),
        el("td", {}, userStatus(u)),
        el("td", { text: u.last_login_at ? fmtDateTime(u.last_login_at) : "Never" }),
        el("td", {}, actions),
      );
    })),
  );
  host.replaceChildren(table);
}

async function patchUser(user, patch, successMessage) {
  try {
    await api("/api/users/" + user.id, { method: "PATCH", json: patch });
    toast(successMessage);
    showUsers();
  } catch (err) {
    toast(err.message, true);
  }
}

async function submitNewUser(event) {
  event.preventDefault();
  const payload = {
    username: $("u-username").value.trim().toLowerCase(),
    display_name: $("u-display").value.trim(),
    role: $("u-role").value,
    password: $("u-password").value,
  };
  if (payload.password.length < 12) { showError("u-error", "Temporary password must be at least 12 characters."); return; }
  try {
    await api("/api/users", { json: payload });
  } catch (err) {
    showError("u-error", err.message);
    return;
  }
  $("dlg-user").close();
  toast("User " + payload.username + " created");
  showUsers();
}

let resetTarget = null;

function openResetDialog(user) {
  resetTarget = user;
  openDialog("dlg-reset", () => {
    $("reset-title").textContent = "Reset password for " + user.display_name;
  });
}

async function submitResetPassword(event) {
  event.preventDefault();
  if (!resetTarget) return;
  const pw = $("reset-password").value;
  if (pw.length < 12) { showError("reset-error", "Password must be at least 12 characters."); return; }
  try {
    await api("/api/users/" + resetTarget.id + "/reset-password", { json: { new_password: pw } });
  } catch (err) {
    showError("reset-error", err.message);
    return;
  }
  $("dlg-reset").close();
  toast("Password reset for " + resetTarget.username);
  showUsers();
}

/* ---------- Audit log (admin) ---------- */

async function showAudit() {
  showView("view-audit");
  const select = $("audit-action");
  if (select.options.length <= 1) {
    try {
      const meta = await api("/api/audit/actions");
      const groups = new Map();
      for (const a of meta.actions) {
        const prefix = a.split(".")[0];
        if (!groups.has(prefix)) groups.set(prefix, []);
        groups.get(prefix).push(a);
      }
      for (const [prefix, actions] of groups) {
        select.append(el("option", { value: prefix + ".", text: "All " + prefix + " events" }));
        for (const a of actions) select.append(el("option", { value: a, text: a }));
      }
    } catch (_) { /* filter stays free-form */ }
  }
  await loadAudit(true);
}

function auditParams() {
  const p = {};
  const username = $("audit-username").value.trim().toLowerCase();
  const action = $("audit-action").value;
  const entityId = $("audit-entity-id").value.trim();
  const since = $("audit-since").value;
  const until = $("audit-until").value;
  if (username) p.username = username;
  if (action) p.action = action;
  if (entityId && /^\d+$/.test(entityId)) p.entity_id = entityId;
  if (since) p.since = since + "T00:00:00";
  if (until) p.until = until + "T23:59:59";
  return p;
}

function describeDetail(detail) {
  if (!detail) return "";
  return Object.entries(detail).map(([k, v]) =>
    k + "=" + (Array.isArray(v) ? v.join(",") : String(v))).join("  ");
}

async function loadAudit(reset) {
  const host = $("audit-table");
  if (reset) {
    state.audit.offset = 0;
    state.audit.params = auditParams();
    host.replaceChildren(el("div", { class: "skeleton-row" }), el("div", { class: "skeleton-row" }));
  }
  const params = new URLSearchParams(state.audit.params);
  params.set("limit", "100");
  params.set("offset", String(state.audit.offset));
  let page;
  try {
    page = await api("/api/audit?" + params.toString());
  } catch (err) {
    host.replaceChildren(el("div", { class: "empty-state", text: "Could not load audit log: " + err.message }));
    return;
  }
  state.audit.total = page.total;
  const rows = page.items.map((r) => el("tr", {},
    el("td", { text: fmtDateTime(r.ts) }),
    el("td", { class: "mono", text: r.username || "—" }),
    el("td", { class: "mono", text: r.action }),
    el("td", { text: r.entity_type ? r.entity_type + (r.entity_id != null ? " #" + r.entity_id : "") : "" }),
    el("td", { class: "mono", text: r.ip || "" }),
    el("td", { class: "wrap mono", text: describeDetail(r.detail) }),
  ));
  let tbody = host.querySelector("tbody");
  if (reset || !tbody) {
    if (!page.items.length) {
      host.replaceChildren(el("div", { class: "empty-state" },
        el("div", { class: "e-title", text: "No audit entries match" })));
      $("audit-count").textContent = "";
      $("btn-audit-more").classList.add("hidden");
      return;
    }
    const table = el("table", { class: "data" },
      el("thead", {}, el("tr", {},
        ...["Time", "User", "Action", "Entity", "IP", "Detail"].map((h) => el("th", { text: h })))),
      el("tbody", {}, ...rows),
    );
    host.replaceChildren(table);
  } else {
    tbody.append(...rows);
  }
  state.audit.offset += page.items.length;
  $("audit-count").textContent = state.audit.offset + " of " + page.total + " entries";
  $("btn-audit-more").classList.toggle("hidden", state.audit.offset >= page.total);
}

/* ---------- Wire-up ---------- */

function startApp() {
  if (state.booted) { route(); return; }
  state.booted = true;
  updateMatchToggleButton();
  $("btn-toggle-match").addEventListener("click", toggleMatchPanel);

  $("btn-new-record").addEventListener("click", () => navigate("#/record/new"));
  $("nav-records").addEventListener("click", () => navigate("#/"));
  $("nav-patients").addEventListener("click", () => navigate("#/patients"));
  $("nav-users").addEventListener("click", () => navigate("#/users"));
  $("nav-audit").addEventListener("click", () => navigate("#/audit"));
  $("btn-back").addEventListener("click", () => {
    navigate("#/");
  });
  $("btn-save").addEventListener("click", saveRecord);
  $("btn-delete-record").addEventListener("click", deleteRecord);
  $("btn-restore-record").addEventListener("click", () => {
    if (state.recordId !== null) restoreRecord(state.recordId);
  });
  $("home-search").addEventListener("input", debounce(() => {
    loadRecordList($("home-search").value.trim());
  }, 300));
  $("home-show-deleted").addEventListener("change", () => loadRecordList($("home-search").value.trim()));
  $("patients-search").addEventListener("input", debounce(() => {
    loadPatientList($("patients-search").value.trim());
  }, 300));
  $("patients-show-deleted").addEventListener("change", () => loadPatientList($("patients-search").value.trim()));
  $("btn-patient-back").addEventListener("click", () => navigate("#/patients"));
  $("btn-new-for-patient").addEventListener("click", () => {
    if (state.profilePatient) navigate("#/record/new/" + state.profilePatient.id);
  });
  $("btn-save-patient").addEventListener("click", savePatientProfile);
  $("btn-delete-patient").addEventListener("click", deletePatient);
  $("btn-restore-patient").addEventListener("click", () => {
    if (state.profilePatient) restorePatient(state.profilePatient.id);
  });

  $("btn-add-hospital").addEventListener("click", () => { addTxRow("tx-hospital").querySelector("input").focus(); markDirty(); });
  $("btn-add-discharge").addEventListener("click", () => { addTxRow("tx-discharge").querySelector("input").focus(); markDirty(); });

  $("p-name").addEventListener("input", () => { suggestPatients(); markDirty(); });
  $("p-name").addEventListener("blur", () => setTimeout(hideSuggestions, 200));
  ["p-sex", "p-dob"].forEach((id) => $(id).addEventListener("input", markDirty));
  $("btn-change-patient").addEventListener("click", unlockPatient);

  $("record-form").addEventListener("input", markDirty);
  $("f-status").addEventListener("change", updateStatusChip);

  $("btn-export-pdf").addEventListener("click", () => {
    if (state.recordId !== null) window.open("/api/records/" + state.recordId + "/pdf", "_blank");
  });

  $("btn-add-user").addEventListener("click", () => openDialog("dlg-user", () => { $("u-role").value = "staff"; }));
  $("btn-audit-apply").addEventListener("click", () => loadAudit(true));
  $("btn-audit-clear").addEventListener("click", () => {
    ["audit-username", "audit-entity-id", "audit-since", "audit-until"].forEach((id) => { $(id).value = ""; });
    $("audit-action").value = "";
    loadAudit(true);
  });
  $("btn-audit-more").addEventListener("click", () => loadAudit(false));

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s" && !$("view-editor").classList.contains("hidden")) {
      e.preventDefault();
      if ($("login-overlay").classList.contains("hidden")) saveRecord();
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) e.preventDefault();
  });

  window.addEventListener("hashchange", route);
  route();
}

async function init() {
  renderIcons();
  wireDialogs();
  $("login-form").addEventListener("submit", submitLogin);
  $("btn-logout").addEventListener("click", logout);
  $("btn-account").addEventListener("click", () => openDialog("dlg-password"));

  api("/api/clinic").then((clinic) => {
    const name = clinic.clinic_name || "Discharge Records";
    const sub = [clinic.doctor_name, clinic.doctor_qualifications].filter(Boolean).join(", ");
    $("clinic-name").textContent = name;
    $("clinic-sub").textContent = sub;
    $("login-clinic").textContent = name;
    $("login-sub").textContent = sub;
    document.title = name + " · Discharge Records";
  }).catch(() => { /* header falls back to defaults */ });

  let user = null;
  try {
    user = await api("/api/auth/me");
  } catch (_) { /* 401: handleUnauthenticated already showed the login */ }
  if (user) {
    setUser(user);
    hideLogin();
    startApp();
  } else {
    showLogin(false);
  }
}

document.addEventListener("DOMContentLoaded", init);
