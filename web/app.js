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
    applySettingsLock(!!cfg.session_active);
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
    // A turn just landed → session is now active (build is lazy on
    // /api/turn).  Lock the settings view until the next End Session.
    refreshSessionActive();
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

  // Ask the user whether to save this session to the database before
  // archiving.  Yes  → /api/end runs the Database Handler first
  // (interviews every agent, writes one .txt per field under
  // database/<session>/); the DH highlights its own box in the LOG-
  // and-Status flowchart while it runs.  No / Cancel  → archive only.
  const wantSave = window.confirm(
    "Do you want this session to be saved for the database?\n\n" +
    "Yes — the Database Handler will interview every agent before " +
    "the session is archived.  This can take several minutes; the " +
    "LOG and Status chart lights up the Database Handler box while " +
    "it runs.\n\n" +
    "No (or Cancel) — archive the session without saving."
  );

  // Disable the button + indicate progress in the UI while /api/end
  // is in flight.  The DH save can take a long time, so the user
  // needs to see that the click registered.
  endBtn.disabled = true;
  const originalEndText = endBtn.textContent;
  let pendingBubble = null;
  if (wantSave) {
    endBtn.textContent = "Saving to database…";
    pendingBubble = addBubble(
      "assistant",
      "Saving this session to the database.  The Database Handler is " +
      "interviewing every agent — this can take several minutes.  " +
      "Open the LOG and Status view to watch its progress.",
      { pending: true }
    );
  } else {
    endBtn.textContent = "Ending…";
  }

  let endResp = null;
  try {
    endResp = await fetch("/api/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ save: !!wantSave }),
    });
  } catch (e) {
    /* network error — fall through; the finally block re-enables the
       button so the user can retry. */
    console.warn("[End Session] network error talking to /api/end:", e);
  }

  // HTTP 409 — the server already has a save in flight (typically a
  // proxy / browser retry that this call duplicates).  Keep the UI in
  // its locked "Saving…" state: the ORIGINAL /api/end is still
  // running server-side and will finish on its own; clearing chat /
  // viewer / images here would lie to the user about what state they
  // are in.  See web_app.py:api_end for the backend guard and
  // extra_utilities/TODO_known_issues.md F22 for the diagnosis.
  if (endResp && endResp.status === 409) {
    console.warn(
      "[End Session] /api/end returned HTTP 409 — a previous save is " +
      "still in progress; this click was ignored by the server.  " +
      "Leaving the UI in its locked state; the in-flight save will " +
      "complete on its own."
    );
    endBtn.textContent = "Save already in progress…";
    // Do NOT re-enable the button, remove the pending bubble, or
    // wipe chat / viewer / images — those steps belong to the
    // original /api/end that is still running.
    return;
  }

  endBtn.disabled = false;
  endBtn.textContent = originalEndText || "End Session";
  if (pendingBubble) pendingBubble.remove();

  messages.innerHTML = "";
  // 3D viewer (right of the Chat pane): the mesh belongs to the
  // session that just ended.  Drop it and restore the "No model yet…"
  // placeholder so the next session opens with an empty viewer.
  if (window.modelViewer && window.modelViewer.unload) {
    window.modelViewer.unload();
  }
  currentMesh = { url: null, name: null };
  const dlBtn = document.getElementById("download-mesh");
  if (dlBtn) dlBtn.disabled = true;
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
  // End Session cleared the in-process session — unlock the settings.
  applySettingsLock(!!cfg.session_active);
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
  // Context Pruner is treated as a tool-like overlay: when an agent's
  // history exceeds the configured token threshold its pre-invoke
  // hook lights up the CP box ALONGSIDE the calling agent (multi-
  // active), and the matching exit event clears CP while leaving the
  // caller solo-lit.  Same lifecycle as the two DC tools.
  "Context Pruner",
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
  if (name === "settings") {
    if (!settingsLoaded) loadSettings();
    loadLrRouting();
    // Pick up the latest lock state when the user opens the view;
    // otherwise a session started in another tab/turn could leave the
    // view stale.
    refreshSessionActive();
  }
  if (name === "images") loadImages();
  if (name === "chat" && input) input.focus();
  if (name === "logstatus") startLogStream();
  else stopLogStream();
  if (name === "questions") {
    loadQuestions();
    refreshSessionActive();
  }
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
// LLM routing — duplicate-layout flowchart in Workflow Settings with a
// provider dropdown + model input under each agent box.  Independent of
// the LOG-and-Status chart (no live highlight, no dynamic arrows); only
// shares the visual topology.
// ---------------------------------------------------------------------------

const SVG_NS = "http://www.w3.org/2000/svg";

// Box geometry for the routing chart.  Agent boxes are taller than the
// LOG chart (h=95 vs h=50) to fit the provider + model controls in
// their lower half.  Tool boxes stay short (no controls).
const LR_VIEW = { w: 820, h: 720 };
const LR_BOXES = [
  // User — display only, no controls.
  { key: "user",                  role: "user",  x: 230, y: 10,  w: 140, h: 40,
    label: "User" },
  // Chain agents — single label line each; controls overlay placed in
  // the lower half by the HTML overlay (see renderLrOverlay).
  { key: "receptionist",          role: "agent", x: 230, y: 75,  w: 140, h: 95,
    label: "Receptionist" },
  { key: "user_input_inspector",  role: "agent", x: 40,  y: 200, w: 140, h: 95,
    label: "User Input Inspector" },
  { key: "orchestrator",          role: "agent", x: 230, y: 200, w: 140, h: 95,
    label: "Orchestrator" },
  { key: "dc_output_inspector",   role: "agent", x: 420, y: 200, w: 140, h: 95,
    label: "Output Inspector" },
  { key: "planner",               role: "agent", x: 40,  y: 325, w: 140, h: 95,
    label: "Planner" },
  { key: "dc_input_creator",      role: "agent", x: 40,  y: 450, w: 140, h: 95,
    label: "Input Creator" },
  { key: "dc_input_inspector",    role: "agent", x: 230, y: 450, w: 140, h: 95,
    label: "Input Inspector" },
  { key: "tool_caller",           role: "agent", x: 420, y: 450, w: 140, h: 95,
    label: "Tool Caller" },
  // Tools — display only.  Propeller Configurator sits just below
  // the EXTRA AGENTS panel (frame ends at y=255).
  { key: "propeller_configurator",   role: "tool", x: 610, y: 275, w: 180, h: 60,
    label: "Propeller Configurator", toolPrefix: true },
  { key: "visual_renderings_generator", role: "tool", x: 610, y: 480, w: 180, h: 60,
    label: "Visual Renderings", toolPrefix: true },
  // Extra agents panel + boxes.  Boxes are full-height (h=95) so their
  // provider+model controls fit on the same scale as the chain agents.
  { key: "__extra_frame__",       role: "extra-frame", x: 600, y: 10, w: 200, h: 245,
    label: "EXTRA AGENTS" },
  { key: "database_handler",      role: "agent", x: 615, y: 45,  w: 170, h: 95,
    label: "Database Handler" },
  { key: "context_pruner",        role: "agent", x: 615, y: 150, w: 170, h: 95,
    label: "Context Pruner", notWired: true },
];
const LR_AGENT_KEYS = LR_BOXES
  .filter((b) => b.role === "agent")
  .map((b) => b.key);

// Static black arrows between boxes (drawn first so they sit behind).
// Coords match the box centre-edges; arrowheads at both ends to mirror
// the LOG-and-Status chart's visual convention.
const LR_ARROWS = [
  // User ↔ Receptionist
  { x1: 300, y1: 54,  x2: 300, y2: 71  },
  // Receptionist ↔ Orchestrator
  { x1: 300, y1: 174, x2: 300, y2: 196 },
  // UII ↔ Planner
  { x1: 110, y1: 299, x2: 110, y2: 321 },
  // Planner ↔ Input Creator
  { x1: 110, y1: 424, x2: 110, y2: 446 },
  // Input Creator ↔ Input Inspector
  { x1: 184, y1: 498, x2: 226, y2: 498 },
  // Input Inspector ↔ Tool Caller
  { x1: 374, y1: 498, x2: 416, y2: 498 },
  // Tool Caller ↔ Output Inspector (vertical, x≈490)
  { x1: 490, y1: 446, x2: 490, y2: 299 },
  // Tool Caller ↔ Propeller Configurator (diagonal)
  { x1: 564, y1: 470, x2: 606, y2: 305 },
  // Tool Caller ↔ Visual Renderings generator (diagonal)
  { x1: 564, y1: 530, x2: 606, y2: 510 },
];

function lrEl(id) { return document.getElementById(id); }

// State carried across renders.  Populated by loadLrRouting().
let lrState = null;  // { mode, providers, shared, agents:[...] }

// ---- chart build ---------------------------------------------------------

function _svg(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}

function buildLrChart() {
  const svg = lrEl("lr-chart");
  if (!svg) return;
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${LR_VIEW.w} ${LR_VIEW.h}`);

  // Arrow marker (single, reused by every static line).
  const defs = _svg("defs");
  const marker = _svg("marker", {
    id: "lr-arrow", viewBox: "0 0 10 10", refX: "9", refY: "5",
    markerWidth: "6", markerHeight: "6",
    orient: "auto-start-reverse",
  });
  marker.appendChild(_svg("path", { d: "M0,0 L10,5 L0,10 z", fill: "#e6e8eb" }));
  defs.appendChild(marker);
  svg.appendChild(defs);

  // Arrows (drawn before boxes so they sit behind).
  for (const a of LR_ARROWS) {
    svg.appendChild(_svg("line", {
      x1: a.x1, y1: a.y1, x2: a.x2, y2: a.y2,
      stroke: "#e6e8eb", "stroke-width": "2",
      "marker-start": "url(#lr-arrow)",
      "marker-end": "url(#lr-arrow)",
    }));
  }

  // Boxes.
  for (const b of LR_BOXES) {
    if (b.role === "extra-frame") {
      svg.appendChild(_svg("rect", {
        x: b.x, y: b.y, width: b.w, height: b.h, rx: 4, ry: 4,
        class: "lr-extra-frame",
      }));
      const t = _svg("text", {
        x: b.x + b.w / 2, y: b.y + 22, "text-anchor": "middle",
        class: "lr-extra-title",
      });
      t.textContent = b.label;
      svg.appendChild(t);
      continue;
    }
    const g = _svg("g", {
      id: `lr-box-${b.key}`,
      class: "lr-box" +
        (b.role === "tool" ? " lr-box-tool"
        : b.role === "user" ? " lr-box-user"
        : " lr-box-agent") +
        (b.notWired ? " lr-not-wired" : ""),
    });
    g.appendChild(_svg("rect", {
      x: b.x, y: b.y, width: b.w, height: b.h, rx: 3, ry: 3,
    }));
    if (b.toolPrefix) {
      const p = _svg("text", {
        x: b.x + b.w / 2, y: b.y + 22, "text-anchor": "middle",
        class: "lr-tool-prefix",
      });
      p.textContent = "TOOL:";
      g.appendChild(p);
      const t = _svg("text", {
        x: b.x + b.w / 2, y: b.y + 42, "text-anchor": "middle",
      });
      t.textContent = b.label;
      g.appendChild(t);
    } else {
      const t = _svg("text", {
        x: b.x + b.w / 2,
        // Title at the top quarter of the box; controls (HTML overlay)
        // occupy the lower 2/3.
        y: b.y + (b.role === "agent" ? 22 : b.h / 2 + 5),
        "text-anchor": "middle",
      });
      t.textContent = b.label;
      g.appendChild(t);
      if (b.notWired) {
        const r = _svg("text", {
          x: b.x + b.w / 2, y: b.y + b.h - 5, "text-anchor": "middle",
          class: "lr-not-wired-label",
        });
        r.textContent = "(not yet wired)";
        g.appendChild(r);
      }
    }
    svg.appendChild(g);
  }
}

// ---- HTML overlay (provider + model controls per agent box) --------------

function _toPercent(x, total) { return (x / total) * 100 + "%"; }

function _providerOptionsHtml(providers, selected, allowBlank) {
  const opts = [];
  if (allowBlank) {
    opts.push(`<option value=""${selected ? "" : " selected"}>—</option>`);
  }
  for (const p of providers) {
    const badge = p.key_present ? "✓" : "✗";
    const sel = p.key === selected ? " selected" : "";
    opts.push(
      `<option value="${p.key}"${sel}>${p.label} ${badge}</option>`
    );
  }
  return opts.join("");
}

function renderLrOverlay() {
  const overlay = lrEl("lr-overlay");
  if (!overlay || !lrState) return;
  overlay.innerHTML = "";

  for (const b of LR_BOXES) {
    if (b.role !== "agent") continue;
    const a = lrState.agents.find((x) => x.key === b.key);
    if (!a) continue;

    const div = document.createElement("div");
    div.className = "lr-agent-controls";
    div.dataset.agentKey = b.key;
    // Position the controls in the lower 2/3 of the box, with a small
    // inset so the rectangle border stays visible.
    const inset = 4;
    const controlsTop = b.y + 32;  // below the title line
    const controlsH = b.h - 32 - inset;
    div.style.left   = _toPercent(b.x + inset,  LR_VIEW.w);
    div.style.top    = _toPercent(controlsTop,  LR_VIEW.h);
    div.style.width  = _toPercent(b.w - 2 * inset, LR_VIEW.w);
    div.style.height = _toPercent(controlsH, LR_VIEW.h);

    // Provider select (allow blank = "inherit from shared default").
    const sel = document.createElement("select");
    sel.className = "lr-provider-select";
    sel.innerHTML = _providerOptionsHtml(
      lrState.providers, a.override_provider, true,
    );
    sel.addEventListener("change", () => {
      a.override_provider = sel.value;
      // If the user picks a provider, prefill the model with the
      // placeholder for that provider so the row doesn't sit empty
      // with the wrong placeholder.  Empty selection clears the model.
      if (sel.value) {
        const p = lrState.providers.find((x) => x.key === sel.value);
        if (p && !a.override_model) {
          a.override_model = p.model_placeholder || "";
          inp.value = a.override_model;
        }
      } else {
        a.override_model = "";
        inp.value = "";
      }
    });

    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "lr-model-input";
    inp.value = a.override_model || "";
    inp.placeholder = "model (inherits from shared)";
    inp.addEventListener("input", () => {
      a.override_model = inp.value;
    });

    div.appendChild(sel);
    div.appendChild(inp);
    overlay.appendChild(div);
  }
}

// ---- Global LLM controls + banner ----------------------------------------

function renderLrGlobal() {
  const provSel = lrEl("lr-global-provider");
  const modelInp = lrEl("lr-global-model");
  const banner = lrEl("lr-banner");
  if (!provSel || !modelInp || !banner || !lrState) return;

  // Provider dropdown: 4 options.  ``individual`` is the "no-override"
  // mode; the three real providers force a global override.
  const opts = [];
  opts.push(
    `<option value="individual"${lrState.mode === "individual" ? " selected" : ""}>`
    + "Use individual LLMs"
    + "</option>"
  );
  for (const p of lrState.providers) {
    const badge = p.key_present ? "✓" : "✗";
    const sel = lrState.mode === p.key ? " selected" : "";
    opts.push(
      `<option value="${p.key}"${sel}>${p.label} ${badge} (global override)</option>`
    );
  }
  provSel.innerHTML = opts.join("");

  // The model input always edits ``shared.model`` (it's the value used
  // when the chart is in "individual" mode AND no per-agent override is
  // set; AND it's the value used as the global model when a provider
  // override is active).
  modelInp.value = lrState.shared.model || "";

  paintLrBanner();
  paintLrChartGlobalState();
}

function paintLrBanner() {
  const banner = lrEl("lr-banner");
  if (!banner || !lrState) return;
  if (lrState.mode === "individual") {
    banner.hidden = true;
    banner.textContent = "";
    banner.classList.remove("lr-banner-warn");
    return;
  }
  const p = lrState.providers.find((x) => x.key === lrState.mode);
  const provLabel = p ? p.label : lrState.mode;
  const keyPresent = p ? p.key_present : false;
  const model = lrState.shared.model || "(empty)";
  banner.hidden = false;
  banner.textContent =
    `Global override active: ${provLabel} · ${model}` +
    (keyPresent
      ? ""
      : `  —  ${p ? p.env_var : "API key"} is not set; sessions will fail to start until it is set in agents/.env or the process environment.`);
  banner.classList.toggle("lr-banner-warn", !keyPresent);
}

function paintLrChartGlobalState() {
  const wrap = lrEl("lr-chart-wrap");
  if (!wrap) return;
  const overrideActive = lrState && lrState.mode !== "individual";
  wrap.classList.toggle("lr-global-active", !!overrideActive);
}

// ---- Provider change handler --------------------------------------------

function _onLrGlobalProviderChange() {
  const provSel = lrEl("lr-global-provider");
  const modelInp = lrEl("lr-global-model");
  if (!provSel || !lrState) return;
  lrState.mode = provSel.value;
  // If switching to a global provider override, pre-fill the model
  // placeholder for convenience (user can still edit it).
  if (lrState.mode !== "individual") {
    const p = lrState.providers.find((x) => x.key === lrState.mode);
    if (p && (!lrState.shared.model || lrState.shared.model === "")) {
      lrState.shared.model = p.model_placeholder || "";
      modelInp.value = lrState.shared.model;
    }
  }
  paintLrBanner();
  paintLrChartGlobalState();
}

function _onLrGlobalModelInput() {
  const modelInp = lrEl("lr-global-model");
  if (!modelInp || !lrState) return;
  lrState.shared.model = modelInp.value;
  paintLrBanner();
}

// ---- Load + save ---------------------------------------------------------

function setLrStatus(msg, kind) {
  const el = lrEl("lr-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "lr-status" + (kind ? " " + kind : "");
}

async function loadLrRouting() {
  setLrStatus("Loading…", "");
  try {
    const res = await fetch("/api/llm-routing");
    if (res.status === 401) { showGate(); return; }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      setLrStatus(data.detail || "Could not load LLM routing.", "err");
      return;
    }
    lrState = await res.json();
    // Ensure shared.provider has a value the dropdown can match; if
    // missing, the dropdown still falls through to "individual".
    if (!lrState.shared) lrState.shared = { provider: "openai", model: "" };
    buildLrChart();
    renderLrGlobal();
    renderLrOverlay();
    setLrStatus("", "");
  } catch (e) {
    setLrStatus("Network error: " + e, "err");
  }
}

async function saveLrRouting() {
  if (!lrState) return;
  const saveBtn = lrEl("lr-save");
  if (saveBtn) saveBtn.disabled = true;
  setLrStatus("Saving…", "");

  // shared.provider is fixed to whatever shared currently says (mode is
  // distinct).  We send what was loaded; the backend may keep it or
  // overlay it with the user's pick — for now we trust the loaded value
  // (set by the previous save) and only let the UI mutate
  // shared.model + mode + per-agent overrides.
  const payload = {
    mode: lrState.mode || "individual",
    shared: {
      provider: lrState.shared.provider || "openai",
      model: lrState.shared.model || "",
    },
    agents: lrState.agents.map((a) => ({
      key: a.key,
      override_provider: a.override_provider || "",
      override_model: a.override_model || "",
    })),
  };

  try {
    const res = await fetch("/api/llm-routing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) { showGate(); return; }
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      setLrStatus(data.detail || "Locked — session is active.", "err");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setLrStatus(data.detail || "Save failed.", "err");
      return;
    }
    lrState = data.state || lrState;
    buildLrChart();
    renderLrGlobal();
    renderLrOverlay();
    setLrStatus("Saved — applies to the next session.", "ok");
  } catch (e) {
    setLrStatus("Network error: " + e, "err");
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

// ---- Wiring --------------------------------------------------------------

(function _wireLr() {
  const provSel = lrEl("lr-global-provider");
  const modelInp = lrEl("lr-global-model");
  const saveBtn = lrEl("lr-save");
  const reloadBtn = lrEl("lr-reload");
  if (provSel) provSel.addEventListener("change", _onLrGlobalProviderChange);
  if (modelInp) modelInp.addEventListener("input", _onLrGlobalModelInput);
  if (saveBtn) saveBtn.addEventListener("click", saveLrRouting);
  if (reloadBtn) reloadBtn.addEventListener("click", () => {
    setLrStatus("", "");
    loadLrRouting();
  });
})();

// ---------------------------------------------------------------------------
// Questions for Saved Sessions — developer-facing editor for the DH's
// question schedule.  Reads /api/dh-schedule, lets the user edit a
// table of (Name / Description / From / To / Scope / Type) rows with
// support for attempt-specific Q(N).x sub-rows, then writes back via
// the same endpoint.  Download/Upload buttons export/import the JSON.
// Locked while a session is active (shared lock; see applySettingsLock).
// ---------------------------------------------------------------------------

const Q_AGENTS = []; // populated by /api/dh-schedule.agents
const Q_SCOPES = ["session", "attempt"];
const Q_TYPES = ["Semantic", "Quantitative"];

// In-memory table state — flat list of row objects in display order.
// Persisted to the server on Save.
let qState = {
  version: 1,
  questions: [],
};

function qEl(id) { return document.getElementById(id); }
function qNewId() {
  // RFC4122-ish v4; the backend assigns its own UUIDs if absent, so
  // collision odds here are immaterial.
  return ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)
  );
}

function qSetStatus(msg, kind) {
  const el = qEl("q-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "settings-status" + (kind ? " " + kind : "");
}

// ---- Q-number rendering -------------------------------------------------
// Q-numbers are computed from the row's position and parent_id, not
// stored.  Numbering rule:
//   * Top-level rows get sequential integers Q1, Q2, Q3, …
//   * Child rows get Q<parent_number>.<sub_index>
//   * sub_index restarts at 1 for each parent block.
function computeQNumbers() {
  const rows = qState.questions;
  let topCounter = 0;
  const topNumByParentId = new Map(); // id -> "Q4"
  const subCounters = new Map();      // parent_id -> next sub_index
  const numbers = new Array(rows.length).fill("");
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (!r.parent_id) {
      topCounter += 1;
      const label = `Q${topCounter}`;
      topNumByParentId.set(r.id, label);
      numbers[i] = label;
    } else {
      const parentLabel = topNumByParentId.get(r.parent_id);
      if (!parentLabel) {
        // Orphan — show "?" so the user notices.  Validation rejects
        // orphans on Save.
        numbers[i] = "?";
      } else {
        const nextSub = (subCounters.get(r.parent_id) || 0) + 1;
        subCounters.set(r.parent_id, nextSub);
        numbers[i] = `${parentLabel}.${nextSub}`;
      }
    }
  }
  return numbers;
}

// ---- "To" popover -------------------------------------------------------
let qPopoverAnchor = null;
let qPopoverRowId = null;

function closeQPopover() {
  const pop = qEl("q-to-popover");
  if (!pop) return;
  pop.hidden = true;
  pop.innerHTML = "";
  qPopoverAnchor = null;
  qPopoverRowId = null;
}

function openQPopover(row, anchorCell) {
  closeQPopover();
  if (sessionActive) return; // locked

  const pop = qEl("q-to-popover");
  if (!pop) return;

  pop.innerHTML = "";
  const list = document.createElement("ul");
  list.className = "q-popover-list";
  for (const a of Q_AGENTS) {
    const li = document.createElement("li");
    const lbl = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = a.key;
    cb.checked = (row.to_agents || []).indexOf(a.key) !== -1;
    cb.addEventListener("change", () => {
      const set = new Set(row.to_agents || []);
      if (cb.checked) set.add(a.key);
      else set.delete(a.key);
      row.to_agents = Q_AGENTS
        .map((x) => x.key)
        .filter((k) => set.has(k));
      // Repaint the chips in the originating cell.
      const cell = document.querySelector(
        `.q-to-cell[data-row-id="${row.id}"]`
      );
      if (cell) renderToCellChips(cell, row);
    });
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(" " + a.label));
    li.appendChild(lbl);
    list.appendChild(li);
  }
  pop.appendChild(list);

  // Position next to the anchor cell (use viewport coords, fall back
  // to under-cell if it would clip off-screen).
  const rect = anchorCell.getBoundingClientRect();
  pop.style.top = `${rect.bottom + window.scrollY + 4}px`;
  pop.style.left = `${rect.left + window.scrollX}px`;
  pop.hidden = false;
  qPopoverAnchor = anchorCell;
  qPopoverRowId = row.id;
}

document.addEventListener("click", (ev) => {
  const pop = qEl("q-to-popover");
  if (!pop || pop.hidden) return;
  // Click on a "To" cell that's already open re-opens for that cell;
  // click anywhere else closes.
  if (qPopoverAnchor && qPopoverAnchor.contains(ev.target)) return;
  if (pop.contains(ev.target)) return;
  closeQPopover();
});

function renderToCellChips(cell, row) {
  cell.innerHTML = "";
  const inner = document.createElement("div");
  inner.className = "q-to-chips";
  const ks = row.to_agents || [];
  if (!ks.length) {
    const empty = document.createElement("span");
    empty.className = "q-to-empty";
    empty.textContent = "(click to set)";
    inner.appendChild(empty);
  } else {
    for (const k of ks) {
      const a = Q_AGENTS.find((x) => x.key === k);
      const chip = document.createElement("span");
      chip.className = "q-chip";
      chip.textContent = a ? a.label : k;
      inner.appendChild(chip);
    }
  }
  cell.appendChild(inner);
}

// ---- Row factory --------------------------------------------------------
function qBlankRow(opts) {
  opts = opts || {};
  return {
    id: qNewId(),
    name: "",
    description: "",
    from_agent: Q_AGENTS.length ? Q_AGENTS[0].key : "",
    to_agents: [],
    scope: opts.scope || "session",
    type: "Semantic",
    parent_id: opts.parent_id || null,
    sub_index: null, // recomputed at render
    requires_dcii_enabled: false,
  };
}

// ---- Render -------------------------------------------------------------
function renderQuestions() {
  const tbody = qEl("q-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  const numbers = computeQNumbers();

  // Group children under their parent so we can render an "+Q(N).x"
  // button at the end of each attempt block.
  for (let i = 0; i < qState.questions.length; i++) {
    const r = qState.questions[i];
    const tr = buildRowTr(r, numbers[i]);
    tbody.appendChild(tr);

    // After the LAST child of an attempt block (or after the
    // identifying Q(N) when no children exist), insert a tiny row
    // with a "+Q(N).x" button.
    const nextRow = qState.questions[i + 1];
    const isLastInBlock =
      r.scope === "attempt" &&
      (!r.parent_id || (r.parent_id && (!nextRow || nextRow.parent_id !== r.parent_id))) &&
      // The block ends when the next row is not a child of the same parent.
      (!nextRow ||
        (nextRow.parent_id !== r.id && nextRow.parent_id !== r.parent_id));
    if (isLastInBlock) {
      const parentId = r.parent_id || r.id;
      const parentNumber = r.parent_id
        ? numbers[i].split(".")[0]
        : numbers[i];
      tbody.appendChild(buildAddSubRowTr(parentId, parentNumber));
    }
  }
}

function buildAddSubRowTr(parentId, parentLabel) {
  const tr = document.createElement("tr");
  tr.className = "q-row-addsub";
  const td = document.createElement("td");
  td.colSpan = 9;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "ghost q-add-sub-btn";
  btn.textContent = `+ ${parentLabel}.x`;
  btn.title = `Add a follow-up question for ${parentLabel}`;
  btn.addEventListener("click", () => {
    if (sessionActive) return;
    addSubRow(parentId);
  });
  td.appendChild(btn);
  tr.appendChild(td);
  return tr;
}

function buildRowTr(row, qNumberLabel) {
  const tr = document.createElement("tr");
  tr.className = "q-row" + (row.parent_id ? " q-row-sub" : "");
  tr.dataset.rowId = row.id;
  tr.draggable = !sessionActive;

  // Drag handle + hover-only "insert above" affordance.  The button
  // is a child of the grip cell so it can be positioned absolutely
  // against the cell (which has position: relative).
  const grip = document.createElement("td");
  grip.className = "q-grip";
  const gripGlyph = document.createElement("span");
  gripGlyph.className = "q-grip-glyph";
  gripGlyph.textContent = "⋮⋮";
  gripGlyph.title = "Drag to reorder";
  grip.appendChild(gripGlyph);
  const insertAbove = document.createElement("button");
  insertAbove.type = "button";
  insertAbove.className = "q-row-insert-above";
  insertAbove.textContent = "+";
  insertAbove.title = "Insert a new row above this one";
  insertAbove.addEventListener("click", (ev) => {
    ev.stopPropagation();
    insertRowAbove(row.id);
  });
  grip.appendChild(insertAbove);
  tr.appendChild(grip);

  // Number
  const num = document.createElement("td");
  num.className = "q-num";
  num.textContent = qNumberLabel;
  tr.appendChild(num);

  // Name
  const nameCell = document.createElement("td");
  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = row.name || "";
  nameInput.className = "q-name-input";
  nameInput.placeholder = "e.g. Planner Problem";
  nameInput.addEventListener("input", () => { row.name = nameInput.value; });
  nameCell.appendChild(nameInput);
  const fileHint = document.createElement("div");
  fileHint.className = "q-file-hint";
  const updateFileHint = () => {
    const slug = (row.name || "")
      .trim()
      .replace(/[^\w]+/g, "_")
      .replace(/^_+|_+$/g, "");
    fileHint.textContent = slug
      ? `→ ${slug}.txt`
      : "→ (enter a name)";
  };
  nameInput.addEventListener("input", updateFileHint);
  updateFileHint();
  nameCell.appendChild(fileHint);
  tr.appendChild(nameCell);

  // Description
  const descCell = document.createElement("td");
  const descArea = document.createElement("textarea");
  descArea.rows = 3;
  descArea.value = row.description || "";
  descArea.placeholder = "Describe what the DH should ask the agent…";
  descArea.className = "q-desc-input";
  descArea.addEventListener("input", () => { row.description = descArea.value; });
  descCell.appendChild(descArea);
  tr.appendChild(descCell);

  // From
  const fromCell = document.createElement("td");
  const fromSel = document.createElement("select");
  fromSel.className = "q-from-select";
  for (const a of Q_AGENTS) {
    const opt = document.createElement("option");
    opt.value = a.key;
    opt.textContent = a.label;
    if (a.key === row.from_agent) opt.selected = true;
    fromSel.appendChild(opt);
  }
  fromSel.addEventListener("change", () => { row.from_agent = fromSel.value; });
  fromCell.appendChild(fromSel);
  tr.appendChild(fromCell);

  // To
  const toCell = document.createElement("td");
  toCell.className = "q-to-cell";
  toCell.dataset.rowId = row.id;
  renderToCellChips(toCell, row);
  toCell.addEventListener("click", () => openQPopover(row, toCell));
  tr.appendChild(toCell);

  // Scope
  const scopeCell = document.createElement("td");
  const scopeSel = document.createElement("select");
  scopeSel.className = "q-scope-select";
  if (row.parent_id) {
    // Sub-rows are forced attempt-scoped.
    const opt = document.createElement("option");
    opt.value = "attempt";
    opt.textContent = "attempt (sub)";
    opt.selected = true;
    scopeSel.appendChild(opt);
    scopeSel.disabled = true;
  } else {
    for (const s of Q_SCOPES) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      if (s === row.scope) opt.selected = true;
      scopeSel.appendChild(opt);
    }
    scopeSel.addEventListener("change", () => {
      const before = row.scope;
      row.scope = scopeSel.value;
      handleScopeChange(row, before);
    });
  }
  scopeCell.appendChild(scopeSel);
  tr.appendChild(scopeCell);

  // Type
  const typeCell = document.createElement("td");
  const typeSel = document.createElement("select");
  typeSel.className = "q-type-select";
  for (const t of Q_TYPES) {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    if (t === row.type) opt.selected = true;
    typeSel.appendChild(opt);
  }
  typeSel.addEventListener("change", () => { row.type = typeSel.value; });
  typeCell.appendChild(typeSel);
  tr.appendChild(typeCell);

  // Actions
  const actCell = document.createElement("td");
  actCell.className = "q-actions";
  const dup = document.createElement("button");
  dup.type = "button";
  dup.className = "q-act-dup";
  dup.title = "Duplicate this row";
  dup.textContent = "❐";
  dup.addEventListener("click", () => duplicateRow(row.id));
  const del = document.createElement("button");
  del.type = "button";
  del.className = "q-act-del";
  del.title = "Delete this row";
  del.textContent = "🗑";
  del.addEventListener("click", () => deleteRow(row.id));
  actCell.appendChild(dup);
  actCell.appendChild(del);
  tr.appendChild(actCell);

  // Drag-and-drop wiring (HTML5)
  tr.addEventListener("dragstart", (ev) => {
    if (sessionActive) { ev.preventDefault(); return; }
    ev.dataTransfer.setData("text/plain", row.id);
    ev.dataTransfer.effectAllowed = "move";
    tr.classList.add("q-row-dragging");
  });
  tr.addEventListener("dragend", () => tr.classList.remove("q-row-dragging"));
  tr.addEventListener("dragover", (ev) => {
    if (sessionActive) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    tr.classList.add("q-row-dragover");
  });
  tr.addEventListener("dragleave", () => tr.classList.remove("q-row-dragover"));
  tr.addEventListener("drop", (ev) => {
    ev.preventDefault();
    tr.classList.remove("q-row-dragover");
    const srcId = ev.dataTransfer.getData("text/plain");
    if (srcId && srcId !== row.id) moveRow(srcId, row.id);
  });

  return tr;
}

// ---- Scope change side effects ------------------------------------------
function handleScopeChange(row, prevScope) {
  if (row.scope === "attempt" && prevScope !== "attempt") {
    // Auto-spawn the mandatory Q(N).1 child so the user is never in
    // an invalid state (an attempt-scoped parent with no children).
    const sub = qBlankRow({ scope: "attempt", parent_id: row.id });
    const parentIdx = qState.questions.findIndex((q) => q.id === row.id);
    qState.questions.splice(parentIdx + 1, 0, sub);
    renderQuestions();
  } else if (row.scope !== "attempt" && prevScope === "attempt") {
    // Switching attempt → session must drop any children (they would
    // otherwise be orphaned).  Confirm before destroying.
    const kids = qState.questions.filter((q) => q.parent_id === row.id);
    if (kids.length) {
      const ok = window.confirm(
        `Switching this row to 'session' will delete its ${kids.length} ` +
        `attempt-specific sub-row(s).  Proceed?`
      );
      if (!ok) {
        row.scope = "attempt";
        renderQuestions();
        return;
      }
      qState.questions = qState.questions.filter(
        (q) => q.parent_id !== row.id
      );
    }
    renderQuestions();
  }
}

// ---- Row operations -----------------------------------------------------
function addTopLevelRow() {
  if (sessionActive) return;
  qState.questions.push(qBlankRow({ scope: "session" }));
  renderQuestions();
}

function insertRowAbove(targetId) {
  if (sessionActive) return;
  const idx = qState.questions.findIndex((q) => q.id === targetId);
  if (idx < 0) return;
  const target = qState.questions[idx];

  // Mirror the target's hierarchical level so the inserted row never
  // creates an invalid state:
  //   * Target is a sub-row (parent_id set)  → new row is also a
  //     sub-row of the SAME parent.  Scope is forced to 'attempt'.
  //   * Target is top-level                  → new row is top-level,
  //     defaulting to 'session' scope.  The user can switch to
  //     'attempt' afterwards (which auto-spawns a Q(N).1 child).
  let blank;
  if (target.parent_id) {
    blank = qBlankRow({ scope: "attempt", parent_id: target.parent_id });
  } else {
    blank = qBlankRow({ scope: "session" });
  }
  qState.questions.splice(idx, 0, blank);
  renderQuestions();
  qSetStatus("", "");
}

function addSubRow(parentId) {
  if (sessionActive) return;
  // Find the index of the last existing child of this parent (or the
  // parent itself if none yet) and insert the new child right after.
  let insertAt = qState.questions.findIndex((q) => q.id === parentId);
  if (insertAt < 0) return;
  for (let i = insertAt + 1; i < qState.questions.length; i++) {
    if (qState.questions[i].parent_id === parentId) insertAt = i;
    else break;
  }
  qState.questions.splice(
    insertAt + 1, 0,
    qBlankRow({ scope: "attempt", parent_id: parentId }),
  );
  renderQuestions();
}

function duplicateRow(rowId) {
  if (sessionActive) return;
  const idx = qState.questions.findIndex((q) => q.id === rowId);
  if (idx < 0) return;
  const src = qState.questions[idx];
  const copy = JSON.parse(JSON.stringify(src));
  copy.id = qNewId();
  copy.name = (src.name || "") + " (copy)";
  // Duplicating an identifying Q(N) without its children doesn't make
  // sense (the new Q(N) would have no kids → invalid).  Duplicate the
  // whole block instead.
  if (!src.parent_id && src.scope === "attempt") {
    const block = [copy];
    for (let i = idx + 1; i < qState.questions.length; i++) {
      const k = qState.questions[i];
      if (k.parent_id !== src.id) break;
      const ck = JSON.parse(JSON.stringify(k));
      ck.id = qNewId();
      ck.parent_id = copy.id;
      block.push(ck);
    }
    qState.questions.splice(idx + block.length /* skip src and its kids */, 0, ...block);
    // Recompute the splice location: insert AFTER the original block.
    // Simpler: re-find the last index of the original block, then insert.
    qState.questions.splice(
      qState.questions.indexOf(copy), 1,  // remove the temporary placement
    );
    let lastOrigKid = idx;
    for (let i = idx + 1; i < qState.questions.length; i++) {
      if (qState.questions[i].parent_id === src.id) lastOrigKid = i;
      else break;
    }
    qState.questions.splice(lastOrigKid + 1, 0, ...block);
  } else {
    qState.questions.splice(idx + 1, 0, copy);
  }
  renderQuestions();
}

function deleteRow(rowId) {
  if (sessionActive) return;
  const idx = qState.questions.findIndex((q) => q.id === rowId);
  if (idx < 0) return;
  const r = qState.questions[idx];

  // Deleting the only Q(N).1 child of an attempt parent is rejected —
  // the parent would become orphaned.  User must delete the parent
  // (which deletes the block) or duplicate then delete.
  if (r.parent_id) {
    const siblings = qState.questions.filter(
      (q) => q.parent_id === r.parent_id
    );
    if (siblings.length === 1) {
      qSetStatus(
        "Cannot delete the only sub-row of an attempt-specific Q(N). " +
        "Delete the parent row (Q(N)) instead — that removes the " +
        "whole block.",
        "err",
      );
      return;
    }
  }
  if (!r.parent_id && r.scope === "attempt") {
    // Deleting the parent also deletes its children.
    qState.questions = qState.questions.filter(
      (q) => q.id !== r.id && q.parent_id !== r.id
    );
  } else {
    qState.questions.splice(idx, 1);
  }
  renderQuestions();
}

function moveRow(srcId, targetId) {
  if (sessionActive) return;
  const srcIdx = qState.questions.findIndex((q) => q.id === srcId);
  const tgtIdx = qState.questions.findIndex((q) => q.id === targetId);
  if (srcIdx < 0 || tgtIdx < 0 || srcIdx === tgtIdx) return;
  const src = qState.questions[srcIdx];
  const tgt = qState.questions[tgtIdx];

  // Constraint: top-level rows reorder freely with other top-level
  // rows; sub-rows reorder freely within their parent's block.  No
  // cross-block drags.
  if ((src.parent_id || null) !== (tgt.parent_id || null)) {
    qSetStatus(
      "Cross-block moves are not allowed — drop the row within the " +
      "same block (top-level rows, or within the same Q(N) parent).",
      "err",
    );
    return;
  }

  // Splice out and re-insert at the target's position.  For top-level
  // rows that own children, also drag the children along so the block
  // stays contiguous.
  if (!src.parent_id && src.scope === "attempt") {
    // Block-aware move: pick up src + all its consecutive kids.
    let endIdx = srcIdx;
    for (let i = srcIdx + 1; i < qState.questions.length; i++) {
      if (qState.questions[i].parent_id === src.id) endIdx = i;
      else break;
    }
    const block = qState.questions.splice(srcIdx, endIdx - srcIdx + 1);
    // Find the new target index after splice (may have shifted).
    let newTgt = qState.questions.findIndex((q) => q.id === targetId);
    if (newTgt < 0) newTgt = qState.questions.length;
    // If target itself is part of another block, jump to that block's end.
    const tgtRow = qState.questions[newTgt];
    if (tgtRow && tgtRow.scope === "attempt" && !tgtRow.parent_id) {
      for (let i = newTgt + 1; i < qState.questions.length; i++) {
        if (qState.questions[i].parent_id === tgtRow.id) newTgt = i;
        else break;
      }
    }
    qState.questions.splice(newTgt + 1, 0, ...block);
  } else {
    // Single-row move (top-level non-attempt, or sub-row).
    qState.questions.splice(srcIdx, 1);
    let newTgt = qState.questions.findIndex((q) => q.id === targetId);
    if (newTgt < 0) newTgt = qState.questions.length;
    qState.questions.splice(newTgt + 1, 0, src);
  }
  renderQuestions();
  qSetStatus("", "");
}

// ---- Load / save / download / upload ------------------------------------
async function loadQuestions() {
  qSetStatus("Loading…", "");
  try {
    const res = await fetch("/api/dh-schedule");
    if (res.status === 401) { showGate(); return; }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      qSetStatus(data.detail || "Could not load schedule.", "err");
      return;
    }
    const data = await res.json();
    qState = {
      version: data.version || 1,
      questions: data.questions || [],
    };
    Q_AGENTS.length = 0;
    for (const a of (data.agents || [])) Q_AGENTS.push(a);
    renderQuestions();
    qSetStatus("", "");
  } catch (e) {
    qSetStatus("Network error: " + e, "err");
  }
}

async function saveQuestions() {
  const saveBtn = qEl("q-save");
  if (saveBtn) saveBtn.disabled = true;
  qSetStatus("Saving…", "");
  try {
    const res = await fetch("/api/dh-schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version: qState.version || 1,
        questions: qState.questions,
      }),
    });
    if (res.status === 401) { showGate(); return; }
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      qSetStatus(data.detail || "Locked — session is active.", "err");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      qSetStatus(data.detail || "Save failed.", "err");
      return;
    }
    qState = {
      version: data.state.version || 1,
      questions: data.state.questions || [],
    };
    renderQuestions();
    qSetStatus("Saved — applies to the next save.", "ok");
  } catch (e) {
    qSetStatus("Network error: " + e, "err");
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function downloadQuestions() {
  try {
    const res = await fetch("/api/dh-schedule/download");
    if (!res.ok) {
      qSetStatus("Download failed.", "err");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dh_schedule.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    qSetStatus("Downloaded.", "ok");
  } catch (e) {
    qSetStatus("Download error: " + e, "err");
  }
}

async function uploadQuestionsFile(file) {
  if (!file) return;
  const ok = window.confirm(
    `Replace the current schedule with the contents of "${file.name}"?\n\n` +
    "The current table will be replaced in memory.  Click Save to " +
    "persist; close the view to discard."
  );
  if (!ok) return;
  qSetStatus("Uploading…", "");
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch("/api/dh-schedule/upload", {
      method: "POST",
      body: form,
    });
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      qSetStatus(data.detail || "Locked — session is active.", "err");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      qSetStatus(data.detail || "Upload failed.", "err");
      return;
    }
    qState = {
      version: data.payload.version || 1,
      questions: data.payload.questions || [],
    };
    renderQuestions();
    qSetStatus("Uploaded — click Save to persist.", "ok");
  } catch (e) {
    qSetStatus("Upload error: " + e, "err");
  }
}

// ---- Wiring -------------------------------------------------------------
(function _wireQuestions() {
  const saveBtn = qEl("q-save");
  const reloadBtn = qEl("q-reload");
  const downloadBtn = qEl("q-download");
  const uploadPickBtn = qEl("q-upload-pick");
  const uploadFileInp = qEl("q-upload-file");
  const addTopBtn = qEl("q-add-toplevel");

  if (saveBtn) saveBtn.addEventListener("click", saveQuestions);
  if (reloadBtn) reloadBtn.addEventListener("click", () => {
    qSetStatus("", "");
    loadQuestions();
  });
  if (downloadBtn) downloadBtn.addEventListener("click", downloadQuestions);
  if (uploadPickBtn && uploadFileInp) {
    uploadPickBtn.addEventListener("click", () => uploadFileInp.click());
    uploadFileInp.addEventListener("change", () => {
      const f = uploadFileInp.files && uploadFileInp.files[0];
      uploadFileInp.value = ""; // allow re-pick of same file
      if (f) uploadQuestionsFile(f);
    });
  }
  if (addTopBtn) addTopBtn.addEventListener("click", addTopLevelRow);
})();

// ---------------------------------------------------------------------------
// Session-active lock for the whole Workflow Settings view (chart +
// flag list).  Driven by /api/config.session_active; the backend is the
// safety net (HTTP 409 on writes while a session is active).
// ---------------------------------------------------------------------------

let sessionActive = false;

function applySettingsLock(active) {
  sessionActive = !!active;
  const scroll = document.getElementById("settings-scroll");
  const banner = document.getElementById("settings-lock-banner");
  if (scroll) scroll.classList.toggle("locked", sessionActive);
  if (banner) banner.hidden = !sessionActive;
  // Questions-for-Saved-Sessions view shares the same lock.
  const qScroll = document.getElementById("questions-scroll");
  const qBanner = document.getElementById("questions-lock-banner");
  if (qScroll) qScroll.classList.toggle("locked", sessionActive);
  if (qBanner) qBanner.hidden = !sessionActive;
}

async function refreshSessionActive() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    applySettingsLock(!!cfg.session_active);
  } catch (_) {
    // Network error — leave the previous lock state in place; the
    // backend 409 is still the source of truth on writes.
  }
}

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
