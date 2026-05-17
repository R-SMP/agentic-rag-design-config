"use strict";

const $ = (id) => document.getElementById(id);
const gate = $("gate");
const gateForm = $("gate-form");
const gateInput = $("gate-input");
const gateError = $("gate-error");
const workspace = $("workspace");
const messages = $("messages");
const composer = $("composer");
const input = $("input");
const sendBtn = $("send-btn");
const endBtn = $("end-btn");

let busy = false;

function showChat() {
  gate.hidden = true;
  workspace.hidden = false;
  endBtn.hidden = false;
  input.focus();
}

function showGate() {
  workspace.hidden = true;
  endBtn.hidden = true;
  gate.hidden = false;
  gateInput.value = "";
  gateInput.focus();
}

function loadMesh(url, name) {
  if (window.modelViewer) window.modelViewer.load(url, name);
}

function addBubble(role, text, opts = {}) {
  const el = document.createElement("div");
  el.className =
    "bubble " + role + (opts.pending ? " pending" : "") +
    (opts.error ? " error-bubble" : "");
  el.textContent = text;
  if (opts.artefacts) {
    for (const a of opts.artefacts) {
      if (a.kind === "image") {
        const img = document.createElement("img");
        img.src = a.url;
        img.alt = a.name;
        el.appendChild(img);
      } else if (a.kind === "mesh") {
        const view = document.createElement("button");
        view.type = "button";
        view.className = "artefact-action";
        view.textContent = "🧊 View " + a.name + " in 3D";
        view.addEventListener("click", () => loadMesh(a.url, a.name));
        el.appendChild(view);
        const dl = document.createElement("a");
        dl.className = "artefact-link";
        dl.href = a.url;
        dl.textContent = "⬇ " + a.name;
        dl.target = "_blank";
        el.appendChild(dl);
      } else {
        const link = document.createElement("a");
        link.className = "artefact-link";
        link.href = a.url;
        link.textContent = "⬇ " + a.name;
        link.target = "_blank";
        el.appendChild(link);
      }
    }
  }
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
  return el;
}

async function init() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    if (cfg.auth_required && !cfg.authed) showGate();
    else showChat();
  } catch (e) {
    showGate();
    gateError.hidden = false;
    gateError.textContent = "Cannot reach the server. Is uvicorn running?";
  }
}

gateForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  gateError.hidden = true;
  try {
    const res = await fetch("/api/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: gateInput.value }),
    });
    if (res.ok) {
      showChat();
    } else {
      const body = await res.json().catch(() => ({}));
      gateError.hidden = false;
      gateError.textContent = body.detail || "Invite code did not match.";
    }
  } catch (e) {
    gateError.hidden = false;
    gateError.textContent = "Network error contacting the server.";
  }
});

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  sendBtn.disabled = true;
  input.disabled = true;

  addBubble("user", text);
  const pending = addBubble(
    "assistant",
    "Thinking — running the multi-agent pipeline… (this can take a while)",
    { pending: true }
  );

  try {
    const res = await fetch("/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    if (res.status === 401) {
      pending.remove();
      showGate();
      return;
    }
    const data = await res.json();
    pending.remove();
    addBubble("assistant", data.reply, {
      artefacts: data.artefacts,
      error:
        data.forwarded === false && /internal error/.test(data.reply || ""),
    });
    // Auto-load the most recent mesh produced this turn into the viewer.
    const meshes = (data.artefacts || []).filter((a) => a.kind === "mesh");
    if (meshes.length) {
      const last = meshes[meshes.length - 1];
      loadMesh(last.url, last.name);
    }
  } catch (e) {
    pending.remove();
    addBubble(
      "assistant",
      "(network error — the request did not complete: " + e + ")",
      { error: true }
    );
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value;
  input.value = "";
  sendMessage(text);
});

// Enter to send, Shift+Enter for newline.
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.requestSubmit();
  }
});

endBtn.addEventListener("click", async () => {
  if (busy) return;
  try {
    await fetch("/api/end", { method: "POST" });
  } catch (e) {
    /* ignore */
  }
  messages.innerHTML = "";
  const cfg = await (await fetch("/api/config")).json().catch(() => ({}));
  if (cfg.auth_required && !cfg.authed) showGate();
  else input.focus();
});

// Live model pushes: when an agent calls visualize_3d_model the
// server emits an SSE "visualize" event — load it into the viewer
// immediately, without waiting for the turn to finish.
function startEventStream() {
  try {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "visualize" && window.modelViewer) {
          window.modelViewer.load(data.url, data.name);
        }
      } catch (_) {
        /* ignore malformed event */
      }
    };
    es.onerror = () => {
      /* EventSource reconnects automatically */
    };
  } catch (_) {
    /* SSE unsupported — non-fatal, end-of-turn artefacts still work */
  }
}

// ---------------------------------------------------------------------------
// Left side menu — switch between the interfaces
// ---------------------------------------------------------------------------
const navItems = Array.from(document.querySelectorAll(".nav-item"));
const views = Array.from(document.querySelectorAll(".view"));
let settingsLoaded = false;

function switchView(name) {
  for (const b of navItems) {
    b.classList.toggle("active", b.dataset.view === name);
  }
  for (const v of views) {
    const on = v.dataset.view === name;
    v.classList.toggle("active", on);
    v.hidden = !on;
  }
  if (name === "settings" && !settingsLoaded) loadSettings();
  if (name === "images") loadImages();
  if (name === "chat" && input) input.focus();
}

for (const b of navItems) {
  b.addEventListener("click", () => switchView(b.dataset.view));
}

// ---------------------------------------------------------------------------
// Workflow Settings — live editor over workflow_settings/settings.py
// ---------------------------------------------------------------------------
const settingsRoot = $("settings-root");
const settingsSave = $("settings-save");
const settingsReload = $("settings-reload");
const settingsStatus = $("settings-status");

let settingsState = []; // [{ name, type, control, original, current, readonly, ... }]

function setSettingsStatus(msg, kind) {
  settingsStatus.textContent = msg || "";
  settingsStatus.className =
    "settings-status" + (kind ? " " + kind : "");
}

function renderSettings(schema) {
  settingsState = schema.map((f) => ({ ...f, current: f.value }));
  settingsRoot.innerHTML = "";
  let lastGroup = null;

  for (const f of settingsState) {
    if (f.group && f.group !== lastGroup) {
      lastGroup = f.group;
      const h = document.createElement("div");
      h.className = "settings-group-title";
      h.textContent = f.group;
      settingsRoot.appendChild(h);
    }

    const row = document.createElement("div");
    row.className = "setting-row";

    const main = document.createElement("div");
    main.className = "setting-main";
    const nameEl = document.createElement("div");
    nameEl.className = "setting-name";
    nameEl.textContent = f.name;
    main.appendChild(nameEl);

    const helpText =
      f.help || (f.readonly && f.derived_note ? f.derived_note : "");
    if (helpText) {
      const det = document.createElement("details");
      det.className = "setting-help";
      const sum = document.createElement("summary");
      sum.textContent = "Details";
      const pre = document.createElement("pre");
      pre.textContent = helpText;
      det.appendChild(sum);
      det.appendChild(pre);
      main.appendChild(det);
    }

    const ctrl = document.createElement("div");
    ctrl.className = "setting-control";
    ctrl.appendChild(buildControl(f));

    row.appendChild(main);
    row.appendChild(ctrl);
    settingsRoot.appendChild(row);
  }
}

function buildControl(f) {
  if (f.readonly) {
    const inp = document.createElement("input");
    inp.type = "text";
    inp.disabled = true;
    inp.value = f.present
      ? "•••••••• (set from environment)"
      : "(not set — environment variable is empty)";
    return inp;
  }

  if (f.control === "toggle") {
    const wrap = document.createElement("div");
    wrap.className = "toggle";
    const yes = document.createElement("button");
    yes.type = "button";
    yes.className = "yes";
    yes.textContent = "V";
    const no = document.createElement("button");
    no.type = "button";
    no.className = "no";
    no.textContent = "X";
    const paint = () => {
      yes.classList.toggle("on", f.current === true);
      no.classList.toggle("on", f.current === false);
    };
    yes.addEventListener("click", () => {
      f.current = true;
      paint();
    });
    no.addEventListener("click", () => {
      f.current = false;
      paint();
    });
    paint();
    wrap.appendChild(yes);
    wrap.appendChild(no);
    return wrap;
  }

  if (f.control === "dropdown") {
    const sel = document.createElement("select");
    for (const opt of f.options) {
      const o = document.createElement("option");
      o.value = String(opt);
      o.textContent = String(opt);
      if (opt === f.current) o.selected = true;
      sel.appendChild(o);
    }
    sel.addEventListener("change", () => {
      f.current = f.type === "int" ? Number(sel.value) : sel.value;
    });
    return sel;
  }

  // free text (str / int / float)
  const inp = document.createElement("input");
  inp.type = "text";
  inp.value = f.current == null ? "" : String(f.current);
  inp.addEventListener("input", () => {
    f.current = inp.value;
  });
  return inp;
}

function collectChanges() {
  const values = {};
  for (const f of settingsState) {
    if (f.readonly) continue;
    let cur = f.current;
    if (f.type === "int" || f.type === "float") {
      if (cur === "" || cur == null || isNaN(Number(cur))) {
        return { error: `${f.name} must be a number.` };
      }
      cur = Number(cur);
    }
    if (cur !== f.value) values[f.name] = cur;
  }
  return { values };
}

async function loadSettings() {
  setSettingsStatus("Loading…", "");
  try {
    const res = await fetch("/api/settings");
    if (res.status === 401) {
      showGate();
      return;
    }
    const data = await res.json();
    renderSettings(data.settings || []);
    settingsLoaded = true;
    setSettingsStatus("", "");
  } catch (e) {
    setSettingsStatus("Could not load settings: " + e, "err");
  }
}

async function saveSettings() {
  const { values, error } = collectChanges();
  if (error) {
    setSettingsStatus(error, "err");
    return;
  }
  if (Object.keys(values).length === 0) {
    setSettingsStatus("No changes to save.", "");
    return;
  }
  settingsSave.disabled = true;
  setSettingsStatus("Saving…", "");
  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    if (res.status === 401) {
      showGate();
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setSettingsStatus(data.detail || "Save failed.", "err");
      return;
    }
    renderSettings(data.settings || []);
    setSettingsStatus(
      "Saved — applies to the next session.",
      "ok"
    );
  } catch (e) {
    setSettingsStatus("Network error: " + e, "err");
  } finally {
    settingsSave.disabled = false;
  }
}

settingsSave && settingsSave.addEventListener("click", saveSettings);
settingsReload &&
  settingsReload.addEventListener("click", () => {
    setSettingsStatus("", "");
    loadSettings();
  });

// ---------------------------------------------------------------------------
// Image Inputs — upload reference images and edit their _note.txt
// ---------------------------------------------------------------------------
const imgDrop = $("img-drop");
const imgFile = $("img-file");
const imgPick = $("img-pick");
const imgListEl = $("img-list");
const imgDetailEmpty = $("img-detail-empty");
const imgDetailBody = $("img-detail-body");
const imgPreview = $("img-preview");
const imgNote = $("img-note");
const imgSave = $("img-save");
const imgReset = $("img-reset");
const imgDelete = $("img-delete");
const imgStatusEl = $("img-status");

let imgSelected = null;

function setImgStatus(msg, kind) {
  imgStatusEl.textContent = msg || "";
  imgStatusEl.className = "img-status" + (kind ? " " + kind : "");
}

function clearImgDetail() {
  imgSelected = null;
  imgDetailBody.hidden = true;
  imgDetailEmpty.hidden = false;
}

function renderImageList(images) {
  imgListEl.innerHTML = "";
  if (!images.length) {
    const p = document.createElement("p");
    p.className = "img-empty";
    p.textContent = "No images yet.";
    imgListEl.appendChild(p);
    if (imgSelected) clearImgDetail();
    return;
  }
  let stillThere = false;
  for (const im of images) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "img-card" + (im.name === imgSelected ? " selected" : "");
    if (im.name === imgSelected) stillThere = true;

    const thumb = document.createElement("img");
    thumb.src = im.url;
    thumb.alt = im.name;
    const nm = document.createElement("span");
    nm.className = "img-card-name";
    nm.textContent = im.name;
    const badge = document.createElement("span");
    if (!im.has_note || im.note_empty) {
      badge.className = "img-card-badge empty";
      badge.textContent = "no description";
    } else {
      badge.className = "img-card-badge";
      badge.textContent = "✓";
    }
    card.appendChild(thumb);
    card.appendChild(nm);
    card.appendChild(badge);
    card.addEventListener("click", () => selectImage(im.name, im.url));
    imgListEl.appendChild(card);
  }
  if (imgSelected && !stillThere) clearImgDetail();
}

async function loadImages() {
  try {
    const res = await fetch("/api/images");
    if (res.status === 401) {
      showGate();
      return;
    }
    const data = await res.json();
    renderImageList(data.images || []);
  } catch (e) {
    setImgStatus("Could not load images: " + e, "err");
  }
}

async function selectImage(name, url) {
  imgSelected = name;
  for (const c of imgListEl.querySelectorAll(".img-card")) {
    c.classList.toggle(
      "selected",
      c.querySelector(".img-card-name")?.textContent === name
    );
  }
  imgDetailEmpty.hidden = true;
  imgDetailBody.hidden = false;
  imgPreview.src = (url || "/api/images/file?name=" + encodeURIComponent(name)) +
    "&_=" + Date.now();
  imgPreview.alt = name;
  imgNote.value = "";
  setImgStatus("", "");
  try {
    const res = await fetch(
      "/api/images/note?name=" + encodeURIComponent(name)
    );
    if (res.ok) {
      const data = await res.json();
      imgNote.value = data.description || "";
    }
  } catch (e) {
    setImgStatus("Could not load description: " + e, "err");
  }
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  setImgStatus("Uploading…", "");
  try {
    const res = await fetch("/api/images", { method: "POST", body: fd });
    if (res.status === 401) {
      showGate();
      return;
    }
    const data = await res.json();
    renderImageList(data.images || []);
    const saved = data.saved || [];
    const errs = data.errors || [];
    if (saved.length) {
      setImgStatus(
        "Uploaded " + saved.length + " image(s)." +
          (errs.length ? " " + errs.length + " skipped." : ""),
        errs.length ? "err" : "ok"
      );
      selectImage(saved[0]);
    } else {
      setImgStatus(errs.join(" · ") || "Nothing uploaded.", "err");
    }
  } catch (e) {
    setImgStatus("Upload failed: " + e, "err");
  }
}

async function saveNote() {
  if (!imgSelected) return;
  imgSave.disabled = true;
  try {
    const res = await fetch("/api/images/note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: imgSelected, description: imgNote.value }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setImgStatus(data.detail || "Save failed.", "err");
      return;
    }
    setImgStatus("Description saved.", "ok");
    loadImages();
  } catch (e) {
    setImgStatus("Network error: " + e, "err");
  } finally {
    imgSave.disabled = false;
  }
}

async function resetNote() {
  if (!imgSelected) return;
  try {
    const res = await fetch("/api/images/note/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: imgSelected }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setImgStatus(data.detail || "Reset failed.", "err");
      return;
    }
    imgNote.value = "";
    setImgStatus("Description cleared.", "ok");
    loadImages();
  } catch (e) {
    setImgStatus("Network error: " + e, "err");
  }
}

async function deleteImage() {
  if (!imgSelected) return;
  if (!confirm('Delete "' + imgSelected + '" and its description?')) return;
  const name = imgSelected;
  try {
    const res = await fetch(
      "/api/images?name=" + encodeURIComponent(name),
      { method: "DELETE" }
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setImgStatus(data.detail || "Delete failed.", "err");
      return;
    }
    clearImgDetail();
    renderImageList(data.images || []);
    setImgStatus('Deleted "' + name + '".', "ok");
  } catch (e) {
    setImgStatus("Network error: " + e, "err");
  }
}

if (imgPick) imgPick.addEventListener("click", () => imgFile.click());
if (imgFile)
  imgFile.addEventListener("change", () => {
    uploadFiles(imgFile.files);
    imgFile.value = "";
  });
if (imgDrop) {
  ["dragenter", "dragover"].forEach((ev) =>
    imgDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      imgDrop.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    imgDrop.addEventListener(ev, (e) => {
      e.preventDefault();
      imgDrop.classList.remove("dragover");
    })
  );
  imgDrop.addEventListener("drop", (e) => {
    if (e.dataTransfer && e.dataTransfer.files) uploadFiles(e.dataTransfer.files);
  });
}
if (imgSave) imgSave.addEventListener("click", saveNote);
if (imgReset) imgReset.addEventListener("click", resetNote);
if (imgDelete) imgDelete.addEventListener("click", deleteImage);

init();
startEventStream();
