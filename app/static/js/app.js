/* MNH Discharge Records - single-page app, no build step.
   All user data is inserted via textContent / DOM APIs, never innerHTML. */
"use strict";

/* ---------- Icons (vendored from Phosphor Icons, MIT license) ---------- */

const ICONS = {
  plus: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 128a8 8 0 0 1-8 8h-80v80a8 8 0 0 1-16 0v-80H40a8 8 0 0 1 0-16h80V40a8 8 0 0 1 16 0v80h80a8 8 0 0 1 8 8Z"/></svg>',
  search: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M229.66 218.34l-50.07-50.06a88.11 88.11 0 1 0-11.31 11.31l50.06 50.07a8 8 0 0 0 11.32-11.32ZM40 112a72 72 0 1 1 72 72a72.08 72.08 0 0 1-72-72Z"/></svg>',
  "arrow-left": '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8Z"/></svg>',
  "file-pdf": '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 152a8 8 0 0 1-8 8h-24v16h16a8 8 0 0 1 0 16h-16v16a8 8 0 0 1-16 0v-56a8 8 0 0 1 8-8h32a8 8 0 0 1 8 8ZM92 172a28 28 0 0 1-28 28h-8v8a8 8 0 0 1-16 0v-56a8 8 0 0 1 8-8h16a28 28 0 0 1 28 28Zm-16 0a12 12 0 0 0-12-12h-8v24h8a12 12 0 0 0 12-12Zm88 8a36 36 0 0 1-36 36h-16a8 8 0 0 1-8-8v-56a8 8 0 0 1 8-8h16a36 36 0 0 1 36 36Zm-16 0a20 20 0 0 0-20-20h-8v40h8a20 20 0 0 0 20-20ZM40 112V40a16 16 0 0 1 16-16h96a8 8 0 0 1 5.66 2.34l56 56A8 8 0 0 1 216 88v24a8 8 0 0 1-16 0V96h-48a8 8 0 0 1-8-8V40H56v72a8 8 0 0 1-16 0ZM160 80h28.69L160 51.31Z"/></svg>',
  paperclip: '<svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M209.66 122.34a8 8 0 0 1 0 11.32l-82.05 82a56 56 0 0 1-79.2-79.21L147.67 35.73a40 40 0 1 1 56.61 56.55L105 193a24 24 0 0 1-33.94-33.94l83.32-84.66a8 8 0 0 1 11.4 11.22l-83.31 84.66a8 8 0 0 0 11.32 11.32l99.32-100.66a24 24 0 1 0-33.89-34L59.76 147.68a40 40 0 1 0 56.53 56.62l82.06-82a8 8 0 0 1 11.31 0Z"/></svg>',
  trash: '<svg width="15" height="15" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M216 48h-40v-8a24 24 0 0 0-24-24h-48a24 24 0 0 0-24 24v8H40a8 8 0 0 0 0 16h8v144a16 16 0 0 0 16 16h128a16 16 0 0 0 16-16V64h8a8 8 0 0 0 0-16ZM96 40a8 8 0 0 1 8-8h48a8 8 0 0 1 8 8v8H96Zm96 168H64V64h128Zm-80-104v64a8 8 0 0 1-16 0v-64a8 8 0 0 1 16 0Zm48 0v64a8 8 0 0 1-16 0v-64a8 8 0 0 1 16 0Z"/></svg>',
  copy: '<svg width="15" height="15" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M216 32H88a8 8 0 0 0-8 8v40H40a8 8 0 0 0-8 8v128a8 8 0 0 0 8 8h128a8 8 0 0 0 8-8v-40h40a8 8 0 0 0 8-8V40a8 8 0 0 0-8-8Zm-56 176H48V96h112Zm48-48h-32V88a8 8 0 0 0-8-8H96V48h112Z"/></svg>',
  download: '<svg width="15" height="15" viewBox="0 0 256 256" fill="currentColor" aria-hidden="true"><path d="M224 152v56a16 16 0 0 1-16 16H48a16 16 0 0 1-16-16v-56a8 8 0 0 1 16 0v56h160v-56a8 8 0 0 1 16 0Zm-101.66 5.66a8 8 0 0 0 11.32 0l40-40a8 8 0 0 0-11.32-11.32L136 132.69V40a8 8 0 0 0-16 0v92.69l-26.34-26.35a8 8 0 0 0-11.32 11.32Z"/></svg>',
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

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
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
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ---------- App state ---------- */

const state = {
  recordId: null,       // saved record id, null = unsaved new record
  patient: null,        // locked patient object, null = creating a new patient
  attachments: [],
  dirty: false,
  saving: false,
  matchAvailable: true, // set false when /api/match reports the model is down
  lastMatchKey: "",
  matchRequestSeq: 0,    // guards against out-of-order responses overwriting newer ones
};

const SCALAR_FIELDS = [
  "ipd_number", "ward_bed", "age_at_admission", "weight",
  "diagnosis", "presenting_complaints", "history", "allergies",
  "examination_findings", "temperature", "pulse", "bp", "resp_rate",
  "spo2", "investigations", "course_in_hospital", "condition_at_discharge",
  "advice", "follow_up_notes", "doctor_name",
];
const DATE_FIELDS = ["admission_date", "discharge_date", "follow_up_date"];

/* ---------- Routing ---------- */

function route() {
  const hash = location.hash.replace(/^#\/?/, "");
  if (hash === "record/new") showEditor(null);
  else if (/^record\/\d+$/.test(hash)) showEditor(Number(hash.split("/")[1]));
  else showHome();
}

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

/* ---------- Home view ---------- */

async function showHome() {
  $("view-editor").classList.add("hidden");
  $("view-home").classList.remove("hidden");
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

async function loadRecordList(query) {
  const list = $("home-list");
  list.replaceChildren(
    ...Array.from({ length: 4 }, () => el("div", { class: "skeleton-row" }))
  );
  let records;
  try {
    const params = query ? "?q=" + encodeURIComponent(query) : "";
    records = await api("/api/records" + params);
  } catch (err) {
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: "Could not load records" }),
      el("div", { text: err.message })));
    return;
  }
  if (!records.length) {
    const title = query ? "No records match “" + query + "”" : "No discharge records yet";
    const hint = query
      ? "Check the spelling, or search by phone number."
      : "Use the New discharge button above to create the first one.";
    list.replaceChildren(el("div", { class: "empty-state" },
      el("div", { class: "e-title", text: title }),
      el("div", { text: hint })));
    return;
  }
  list.replaceChildren(...records.map((r) =>
    el("button", {
      class: "record-row", type: "button",
      onclick: () => navigate("#/record/" + r.id),
    },
      el("span", { class: "r-name", text: r.patient_name }),
      el("span", { class: "r-dx", text: r.diagnosis || "No diagnosis recorded" }),
      el("span", { class: "chip " + (r.status === "final" ? "chip-final" : "chip-draft"), text: r.status === "final" ? "Final" : "Draft" }),
      el("span", { class: "r-date", text: fmtDate(r.discharge_date || r.admission_date || r.updated_at) }),
    )
  ));
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
  for (const [key, label] of TX_COLUMNS) {
    row.append(el("input", {
      type: "text", "data-tx": key, "aria-label": label,
      value: (values && values[key]) || "",
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
  if (patient.phone) bits.push(patient.phone);
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
        text: [p.sex, p.dob ? fmtDate(p.dob) : "", p.phone].filter(Boolean).join(", "),
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
  if (!state.dirty) {
    state.dirty = true;
    setSaveStatus("Unsaved changes");
  }
  scheduleMatch();
}

function clearForm() {
  for (const key of SCALAR_FIELDS) $("f-" + key).value = "";
  for (const key of DATE_FIELDS) $("f-" + key).value = "";
  $("f-status").value = "draft";
  ["p-name", "p-dob", "p-phone", "p-address"].forEach((id) => { $(id).value = ""; });
  $("p-sex").value = "";
  fillTxTable("tx-hospital", []);
  fillTxTable("tx-discharge", []);
  addTxRow("tx-hospital");
  addTxRow("tx-discharge");
  state.attachments = [];
  renderAttachments();
  $("match-list").replaceChildren();
  $("match-panel-wrap").classList.add("hidden");
  $("editor-layout").classList.remove("has-panel");
  state.lastMatchKey = "";
  $("err-p-name").classList.add("hidden");
  $("p-name").classList.remove("input-invalid");
}

async function showEditor(recordId) {
  $("view-home").classList.add("hidden");
  $("view-editor").classList.remove("hidden");
  clearForm();
  state.recordId = recordId;
  state.dirty = false;
  setSaveStatus("");

  if (recordId === null) {
    $("editor-title").textContent = "New discharge";
    $("editor-status-chip").replaceChildren();
    unlockPatient();
    state.dirty = false;
    setSaveStatus("");
    setSavedControlsEnabled(false);
    prefillDoctor();
    return;
  }

  setSaveStatus("Loading…");
  let record;
  try {
    record = await api("/api/records/" + recordId);
  } catch (err) {
    toast("Could not open record: " + err.message, true);
    navigate("#/");
    return;
  }
  $("editor-title").textContent = "Discharge · " + record.patient.name;
  lockPatient(record.patient);
  for (const key of SCALAR_FIELDS) $("f-" + key).value = record[key] || "";
  $("f-admission_date").value = (record.admission_date || "").slice(0, 16);
  $("f-discharge_date").value = (record.discharge_date || "").slice(0, 16);
  $("f-follow_up_date").value = record.follow_up_date || "";
  $("f-status").value = record.status;
  fillTxTable("tx-hospital", record.treatment_items.filter((t) => t.category === "hospital"));
  fillTxTable("tx-discharge", record.treatment_items.filter((t) => t.category === "discharge"));
  if (!$("tx-hospital").children.length) addTxRow("tx-hospital");
  if (!$("tx-discharge").children.length) addTxRow("tx-discharge");
  state.attachments = record.attachments;
  renderAttachments();
  updateStatusChip();
  setSavedControlsEnabled(true);
  state.dirty = false;
  setSaveStatus("All changes saved");
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
  const isFinal = $("f-status").value === "final";
  $("editor-status-chip").replaceChildren(
    el("span", { class: "chip " + (isFinal ? "chip-final" : "chip-draft"), text: isFinal ? "Final" : "Draft" })
  );
}

function setSavedControlsEnabled(enabled) {
  $("btn-export-pdf").disabled = !enabled;
  $("btn-export-pdf").title = enabled ? "" : "Save the record first";
  $("btn-add-attachment").disabled = !enabled;
  $("btn-add-attachment").title = enabled ? "" : "Save the record first";
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
      phone: $("p-phone").value.trim() || null,
      address: $("p-address").value.trim() || null,
    },
  });
  lockPatient(patient);
  return patient;
}

async function saveRecord() {
  if (state.saving) return;
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
    state.dirty = false;
    setSaveStatus("All changes saved");
    toast("Record saved");
  } catch (err) {
    setSaveStatus("Not saved");
    toast("Save failed: " + err.message, true);
  } finally {
    state.saving = false;
    $("btn-save").disabled = false;
  }
}

/* ---------- Attachments ---------- */

function renderAttachments() {
  const list = $("attachment-list");
  if (!state.attachments.length) {
    list.replaceChildren(el("div", { class: "muted", text: "No files attached." }));
    return;
  }
  list.replaceChildren(...state.attachments.map((a) =>
    el("div", { class: "attachment-row" },
      iconEl("paperclip"),
      el("span", { class: "a-name", text: a.original_name }),
      el("span", { class: "a-size", text: fmtSize(a.size_bytes) }),
      el("a", {
        class: "btn-ghost btn-icon", href: "/api/attachments/" + a.id + "/download",
        title: "Download", "aria-label": "Download " + a.original_name,
      }, iconEl("download")),
      el("button", {
        class: "btn-danger-ghost btn-icon", type: "button",
        title: "Delete", "aria-label": "Delete " + a.original_name,
        onclick: () => deleteAttachment(a),
      }, iconEl("trash")),
    )
  ));
  renderIcons(list);
}

async function uploadAttachment(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    const attachment = await api("/api/records/" + state.recordId + "/attachments", {
      method: "POST", body: form,
    });
    state.attachments.push(attachment);
    renderAttachments();
    toast("Attached " + attachment.original_name);
  } catch (err) {
    toast("Upload failed: " + err.message, true);
  }
}

async function deleteAttachment(attachment) {
  if (!confirm("Delete attachment “" + attachment.original_name + "”?")) return;
  try {
    await api("/api/attachments/" + attachment.id, { method: "DELETE" });
    state.attachments = state.attachments.filter((a) => a.id !== attachment.id);
    renderAttachments();
  } catch (err) {
    toast("Delete failed: " + err.message, true);
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
    $("f-presenting_complaints").value,
    $("f-history").value,
    treatment,
  ].map((s) => s.trim()).filter(Boolean).join("\n");
}

const scheduleMatch = debounce(runMatch, 500);

async function runMatch() {
  if (!state.matchAvailable) return;
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

/* ---------- Wire-up ---------- */

function init() {
  renderIcons();

  api("/api/clinic").then((clinic) => {
    if (clinic.clinic_name) $("clinic-name").textContent = clinic.clinic_name;
    const sub = [clinic.doctor_name, clinic.doctor_qualifications].filter(Boolean).join(", ");
    $("clinic-sub").textContent = sub;
    document.title = (clinic.clinic_name || "Discharge Records") + " · Discharge Records";
  }).catch(() => { /* header falls back to defaults */ });

  $("btn-new-record").addEventListener("click", () => navigate("#/record/new"));
  $("btn-back").addEventListener("click", () => {
    navigate("#/");
  });
  $("btn-save").addEventListener("click", saveRecord);
  $("home-search").addEventListener("input", debounce(() => {
    loadRecordList($("home-search").value.trim());
  }, 300));

  $("btn-add-hospital").addEventListener("click", () => { addTxRow("tx-hospital").querySelector("input").focus(); markDirty(); });
  $("btn-add-discharge").addEventListener("click", () => { addTxRow("tx-discharge").querySelector("input").focus(); markDirty(); });

  $("p-name").addEventListener("input", () => { suggestPatients(); markDirty(); });
  $("p-name").addEventListener("blur", () => setTimeout(hideSuggestions, 200));
  ["p-sex", "p-dob", "p-phone", "p-address"].forEach((id) =>
    $(id).addEventListener("input", markDirty));
  $("btn-change-patient").addEventListener("click", unlockPatient);

  $("record-form").addEventListener("input", markDirty);
  $("f-status").addEventListener("change", updateStatusChip);

  $("btn-add-attachment").addEventListener("click", () => $("attachment-input").click());
  $("attachment-input").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file && state.recordId !== null) uploadAttachment(file);
    e.target.value = "";
  });

  $("btn-export-pdf").addEventListener("click", () => {
    if (state.recordId !== null) window.open("/api/records/" + state.recordId + "/pdf", "_blank");
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s" && !$("view-editor").classList.contains("hidden")) {
      e.preventDefault();
      saveRecord();
    }
  });

  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) e.preventDefault();
  });

  window.addEventListener("hashchange", route);
  route();
}

document.addEventListener("DOMContentLoaded", init);
