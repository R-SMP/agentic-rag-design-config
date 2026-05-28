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
const stopBtn = $("stop-btn");

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

// Track the most recently loaded mesh so the Download geometry
// button can save it.  Updated by both the in-bubble mesh load and
// the live `visualize` SSE event.
let currentMesh = { url: null, name: null };

function loadMesh(url, name) {
  if (window.modelViewer) window.modelViewer.load(url, name);
  currentMesh = { url, name: name || "propeller_mesh.obj" };
  const dlBtn = document.getElementById("download-mesh");
  if (dlBtn) dlBtn.disabled = !url;
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
  if (stopBtn) {
    stopBtn.hidden = false;
    stopBtn.disabled = false;
    stopBtn.textContent = "Stop";
  }

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
    if (stopBtn) {
      stopBtn.hidden = true;
      stopBtn.disabled = false;
      stopBtn.textContent = "Stop";
    }
    input.focus();
  }
}

if (stopBtn) {
  stopBtn.addEventListener("click", async () => {
    if (!busy) return;
    // Don't replace the in-flight /api/turn request — let it finish
    // naturally.  Just tell the server to flag the pipeline for
    // cooperative cancellation; the orchestrator will bail at the
    // next hop boundary and /api/turn will resolve with the
    // "(Session interrupted ...)" reply.
    stopBtn.disabled = true;
    stopBtn.textContent = "Stopping…";
    try {
      await fetch("/api/stop", { method: "POST" });
    } catch (_) {
      // Network error reaching /api/stop is unlikely (same origin) —
      // re-enable so the user can retry.
      stopBtn.disabled = false;
      stopBtn.textContent = "Stop";
    }
  });
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
  // Image Inputs: server-side _archive_previous_session has just moved
  // input_images/ into the archived session folder, so the new
  // session's list is empty.  Reset the UI to match — otherwise the
  // last-selected image stays visible in the detail pane and a stale
  // "Deleted ..." status lingers below it.
  clearImgDetail();
  setImgStatus("", "");
  loadImages();
  // LOG and Status: the archived session's log file just moved off
  // the active log path; the flowchart's active highlight and the
  // per-agent "last tool used" labels belong to a session that no
  // longer exists.  Wipe them all so the view starts clean for the
  // next session.
  clearLogView();
  _clearActiveBoxes();
  clearAllToolLabels();
  hideOrchCallerLink();
  hideOrchCalleeLink();
  const cfg = await (await fetch("/api/config")).json().catch(() => ({}));
  if (cfg.auth_required && !cfg.authed) showGate();
  else input.focus();
});

// Live agent / model events.  Two kinds of SSE message arrive on
// /api/events: "visualize" pushes a freshly-generated 3D model into
// the viewer; "agent_active" pushes a handoff so the LOG and Status
// flowchart can light up the currently-active box.  The stream is
// opened once at app start (independent of which view is shown) so
// the chart is already up-to-date when the user opens it.
const FLOW_BOX_BY_NAME = {
  // User box — lit when it is the user's turn to type.
  "User":                  "agent-user",
  // AGENT_DISPLAY entries from agents/shared/routing_tools.py
  "Receptionist":          "agent-receptionist",
  "Orchestrator":          "agent-orchestrator",
  "User Input Inspector":  "agent-user-input-inspector",
  "Planner":               "agent-planner",
  "DC Input Creator":      "agent-dc-input-creator",
  "DC Input Inspector":    "agent-dc-input-inspector",
  "Tool Caller":           "agent-tool-caller",
  "DC Output Inspector":   "agent-dc-output-inspector",
  // Tool boxes (published from tools/*.py via the @tool_active
  // decorator).  Also listed in TOOL_NAMES below so that "<agent> →
  // <tool>" transitions keep BOTH the calling agent and the tool
  // highlighted — the agent is still semantically in flight, waiting
  // for the tool's return.  The matching tool→agent exit event then
  // clears the tool box and leaves the caller solo-lit.
  "Propeller Configurator":      "agent-propeller-configurator",
  "Visual Renderings Generator": "agent-visual-renderings-generator",
  // Extra agents — not yet wired into trace(); reserved so they'll
  // light up automatically once instrumentation lands.
  "Database Handler":      "agent-database-handler",
  "Context Pruner":        "agent-context-pruner",
};

const TOOL_NAMES = new Set([
  "Propeller Configurator",
  "Visual Renderings Generator",
]);

function _clearActiveBoxes() {
  document.querySelectorAll(".flow-box.active").forEach((el) =>
    el.classList.remove("active")
  );
}

function _activateById(id) {
  if (!id) return;
  const node = document.getElementById(id);
  if (node) node.classList.add("active");
}

// "Last used tool" label inside each agent box — set when the agent
// invokes a generic helper (read inputs, list attempts, calculate,
// ...) and PERSISTS until the agent runs another tool or the
// session ends.  Because generic tools complete in milliseconds the
// "currently running" model flashed too fast to read; this is a
// historical-status display instead, gray-italic below the agent
// name.  The agent's own highlight (yellow border on .active) is
// orthogonal — driven by agent_active events from real handoffs.
function recordToolUsedByActiveAgent(name) {
  // Find the agent box currently lit (Strict-transitions policy:
  // exactly one agent box has .active during a turn).  Skip tool
  // boxes (TOOL: Propeller Configurator etc.) and the User box —
  // they don't call generic helpers.
  const active = document.querySelectorAll(
    ".flow-box.active:not(.flow-box-tool):not(.flow-box-user)"
  );
  for (const box of active) {
    const label = box.querySelector(".agent-tool-label");
    if (label) label.textContent = name;
  }
}

function clearAllToolLabels() {
  // Used on End Session to wipe every "last tool" annotation.
  document.querySelectorAll(".agent-tool-label").forEach((el) => {
    el.textContent = "";
  });
}

// Dynamic gray arrow from the last non-Receptionist caller of the
// Orchestrator.  Agents in this set:
const ORCH_CALLERS = new Set([
  "User Input Inspector",
  "Planner",
  "DC Input Creator",
  "DC Input Inspector",
  "Tool Caller",
  "DC Output Inspector",
]);

function _readRectAttrs(rectEl) {
  return {
    x: parseFloat(rectEl.getAttribute("x")),
    y: parseFloat(rectEl.getAttribute("y")),
    w: parseFloat(rectEl.getAttribute("width")),
    h: parseFloat(rectEl.getAttribute("height")),
  };
}

// Closest point on a rectangle's perimeter to an external target,
// pushed outward by `gap` so the arrow visually doesn't touch the
// box.  `target` is in SVG user-space coords.
function _edgePointOutward(rect, target, gap) {
  let px = Math.max(rect.x, Math.min(target.x, rect.x + rect.w));
  let py = Math.max(rect.y, Math.min(target.y, rect.y + rect.h));
  let dx = 0, dy = 0;
  if (target.x < rect.x)            { px = rect.x;          dx = -1; }
  else if (target.x > rect.x + rect.w) { px = rect.x + rect.w; dx = 1; }
  if (target.y < rect.y)            { py = rect.y;          dy = -1; }
  else if (target.y > rect.y + rect.h) { py = rect.y + rect.h; dy = 1; }
  return { x: px + dx * gap, y: py + dy * gap };
}

// Show / hide helpers for SVG <line> elements.  We CANNOT use
// `link.hidden = true/false` here: the `hidden` IDL property comes
// from the HTMLOrSVGElement mixin and in some browsers does not
// reliably reflect into the `hidden` content attribute on SVG
// elements — which would leave our `.orch-dyn-link[hidden]` CSS
// rule out of sync with reality.  setAttribute / removeAttribute
// is the portable, attribute-true path.
function _showSvgLine(link) { link.removeAttribute("hidden"); }
function _hideSvgLine(link) { link.setAttribute("hidden", ""); }

// Internal helper: compute "10px outside the box edge closest to
// `target`" for both rects, and write the endpoints + arrowhead
// into the given <line>.  Direction is determined by which rect
// is `src` (line start) vs `dst` (line end / arrowhead end).
function _drawOrchDynLink(link, srcRect, dstRect) {
  const s = _readRectAttrs(srcRect);
  const d = _readRectAttrs(dstRect);
  const sCenter = { x: s.x + s.w / 2, y: s.y + s.h / 2 };
  const dCenter = { x: d.x + d.w / 2, y: d.y + d.h / 2 };
  const sEdge = _edgePointOutward(s, dCenter, 10);
  const dEdge = _edgePointOutward(d, sCenter, 10);
  link.setAttribute("x1", String(sEdge.x));
  link.setAttribute("y1", String(sEdge.y));
  link.setAttribute("x2", String(dEdge.x));
  link.setAttribute("y2", String(dEdge.y));
  link.setAttribute("marker-end", "url(#arrow-gray)");
  link.removeAttribute("marker-start");
  _showSvgLine(link);
}

// Incoming arrow: shown from <callerName> to Orchestrator.
function showOrchCallerLink(callerName) {
  const link = document.getElementById("orch-caller-link");
  if (!link) return;
  const callerBoxId = FLOW_BOX_BY_NAME[callerName];
  if (!callerBoxId) { _hideSvgLine(link); return; }
  const callerBox = document.getElementById(callerBoxId);
  const orchBox = document.getElementById("agent-orchestrator");
  if (!callerBox || !orchBox) { _hideSvgLine(link); return; }
  const callerRectEl = callerBox.querySelector("rect");
  const orchRectEl = orchBox.querySelector("rect");
  if (!callerRectEl || !orchRectEl) { _hideSvgLine(link); return; }
  _drawOrchDynLink(link, callerRectEl, orchRectEl);
}

function hideOrchCallerLink() {
  const link = document.getElementById("orch-caller-link");
  if (link) _hideSvgLine(link);
}

// Outgoing arrow: shown from Orchestrator to <calleeName>.
function showOrchCalleeLink(calleeName) {
  const link = document.getElementById("orch-callee-link");
  if (!link) return;
  const calleeBoxId = FLOW_BOX_BY_NAME[calleeName];
  if (!calleeBoxId) { _hideSvgLine(link); return; }
  const calleeBox = document.getElementById(calleeBoxId);
  const orchBox = document.getElementById("agent-orchestrator");
  if (!calleeBox || !orchBox) { _hideSvgLine(link); return; }
  const calleeRectEl = calleeBox.querySelector("rect");
  const orchRectEl = orchBox.querySelector("rect");
  if (!calleeRectEl || !orchRectEl) { _hideSvgLine(link); return; }
  _drawOrchDynLink(link, orchRectEl, calleeRectEl);
}

function hideOrchCalleeLink() {
  const link = document.getElementById("orch-callee-link");
  if (link) _hideSvgLine(link);
}

function applyAgentActive(fromName, toName) {
  // Two cases:
  //   * Tool entry (to == one of TOOL_NAMES): keep the calling
  //     agent lit AND light the tool box.  The matching "tool
  //     returned" event will fire on tool exit and bring us back
  //     into the single-active branch below.
  //   * Anything else (agent → agent, anyone → User, tool → agent):
  //     single-active.  Clear everything and light just `to`.
  if (TOOL_NAMES.has(toName)) {
    _clearActiveBoxes();
    _activateById(FLOW_BOX_BY_NAME[fromName]);
    _activateById(FLOW_BOX_BY_NAME[toName]);
    return;
  }
  _clearActiveBoxes();
  _activateById(FLOW_BOX_BY_NAME[toName]);

  // Dynamic gray arrows around the Orchestrator.  They visualise
  // which agent most recently called Orch (incoming) and which
  // agent Orch most recently called (outgoing).  Symmetric show/
  // hide rules so at most one of each is visible at a time:
  //
  //   * to == Orchestrator and from ∈ ORCH_CALLERS  →  show incoming
  //     (the static black arrow handles Receptionist → Orch, so we
  //     skip it here).  Also hide the outgoing arrow — Orch is
  //     receiving a call, the previous outgoing transaction is done.
  //   * from == Orchestrator and to ∈ ORCH_CALLERS  →  show outgoing.
  //     Also hide the incoming arrow — Orch is now the source.
  //   * from == Orchestrator and to == Receptionist  →  hide outgoing
  //     (the static black arrow handles Orch → Receptionist too).
  if (toName === "Orchestrator" && ORCH_CALLERS.has(fromName)) {
    showOrchCallerLink(fromName);
    hideOrchCalleeLink();
  } else if (fromName === "Orchestrator") {
    hideOrchCallerLink();
    if (ORCH_CALLERS.has(toName)) {
      showOrchCalleeLink(toName);
    } else {
      // Orchestrator → Receptionist (or any non-callee).  The static
      // arrow handles it; no dynamic outgoing arrow needed.
      hideOrchCalleeLink();
    }
  }
}

function startEventStream() {
  try {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "visualize" && window.modelViewer) {
          loadMesh(data.url, data.name);
        } else if (data.type === "agent_active") {
          // Real agent handoff — switch which box is highlighted.
          // We INTENTIONALLY do NOT clear any "last tool" labels
          // here: those persist across handoffs so each agent box
          // keeps showing the most recent tool it ran.  The labels
          // are wiped only on End Session.
          applyAgentActive(data.from, data.to);
        } else if (data.type === "generic_tool") {
          // Generic tools complete in milliseconds, so showing the
          // "currently running" tool flashed too fast to read.
          // Instead we record it as the LAST tool used by the
          // currently-active agent (gray italic under its name).
          // The `end` event is intentionally ignored — the label
          // sticks until a newer tool overwrites it.
          if (data.state === "start") {
            recordToolUsedByActiveAgent(data.name);
          }
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
// LOG and Status: tail the current session log over SSE while the view
// is open, close the stream on leaving so the server isn't pushing
// bytes to a hidden pane.
// ---------------------------------------------------------------------------
let logStreamEs = null;
let logStickToBottom = true;

function logStreamEl() {
  return document.getElementById("log-stream");
}

function appendLogText(text) {
  const el = logStreamEl();
  if (!el) return;
  const empty = el.querySelector(".log-empty");
  if (empty) empty.remove();
  el.appendChild(document.createTextNode(text));
  if (logStickToBottom) el.scrollTop = el.scrollHeight;
}

function attachLogScrollWatcher() {
  const el = logStreamEl();
  if (!el || el.dataset.scrollWatcher === "1") return;
  el.dataset.scrollWatcher = "1";
  el.addEventListener("scroll", () => {
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    logStickToBottom = nearBottom;
  });
}

function clearLogView() {
  const el = logStreamEl();
  if (!el) return;
  el.textContent = "";
  const span = document.createElement("span");
  span.className = "log-empty";
  span.textContent = "(view cleared — new lines will appear here)";
  el.appendChild(span);
  logStickToBottom = true;
}

function startLogStream() {
  if (logStreamEs) return;
  attachLogScrollWatcher();
  logStickToBottom = true;
  try {
    logStreamEs = new EventSource("/api/log/stream");
    logStreamEs.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "log" && typeof data.text === "string") {
          appendLogText(data.text);
        }
      } catch (_) {
        /* ignore */
      }
    };
    logStreamEs.onerror = () => {
      /* EventSource reconnects automatically */
    };
  } catch (_) {
    /* SSE unsupported — leave the pane in its empty state */
  }
}

function stopLogStream() {
  if (logStreamEs) {
    try { logStreamEs.close(); } catch (_) { /* ignore */ }
    logStreamEs = null;
  }
}

const logClearBtn = document.getElementById("log-clear");
if (logClearBtn) logClearBtn.addEventListener("click", clearLogView);

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
  if (name === "logstatus") startLogStream();
  else stopLogStream();
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

// ---------------------------------------------------------------------------
// Viewer footer — Download geometry + Copy parameters list
// ---------------------------------------------------------------------------
const downloadMeshBtn = document.getElementById("download-mesh");
const copyParametersBtn = document.getElementById("copy-parameters");

if (downloadMeshBtn) {
  downloadMeshBtn.addEventListener("click", () => {
    if (!currentMesh.url) return;
    // Programmatic-link trick: GET the asset URL with a `download`
    // attribute so the browser saves rather than navigates.  Works
    // for cross-origin URLs only because /api/artefact serves the
    // .obj from the same origin as the app.
    const a = document.createElement("a");
    a.href = currentMesh.url;
    a.download = currentMesh.name || "propeller_mesh.obj";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}

if (copyParametersBtn) {
  copyParametersBtn.addEventListener("click", async () => {
    const originalLabel = copyParametersBtn.textContent;
    copyParametersBtn.disabled = true;
    try {
      const res = await fetch("/api/parameters");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const { text } = await res.json();
      // Modern Clipboard API needs a secure context (HTTPS or
      // localhost).  Fall back to a hidden textarea + execCommand
      // for the http:// Railway URL until TLS is in front of it.
      let ok = false;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          ok = true;
        } catch (_) { /* fall through to legacy path */ }
      }
      if (!ok) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
        ta.remove();
      }
      copyParametersBtn.textContent = ok ? "Copied!" : "Copy failed";
    } catch (_) {
      copyParametersBtn.textContent = "Copy failed";
    } finally {
      setTimeout(() => {
        copyParametersBtn.textContent = originalLabel;
        copyParametersBtn.disabled = false;
      }, 1400);
    }
  });
}

init();
startEventStream();
