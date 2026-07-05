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
const saveLogBtn = $("save-log-btn");

let busy = false;

// State carried across the End Session lifecycle: the click handler
// kicks off ``/api/end`` (which returns HTTP 202 immediately and runs
// the actual DH save + archive sweep in a background task on the
// server) and stores the in-flight UI state here.  The SSE handler in
// ``startEventStream`` picks the state up when the matching
// ``session_save_done`` event arrives and runs the post-save cleanup
// (clear chat / viewer / images / log view, re-enable the button).
// ``null`` means "no End Session in flight".
let endSessionState = null;
let endSessionTimeoutId = null;
const END_SESSION_HARD_TIMEOUT_MS = 25 * 60 * 1000;   // 25 minutes

function showChat() {
  gate.hidden = true;
  workspace.hidden = false;
  endBtn.hidden = false;
  if (saveLogBtn) saveLogBtn.hidden = false;
  input.focus();
}

function showGate() {
  workspace.hidden = true;
  endBtn.hidden = true;
  if (saveLogBtn) saveLogBtn.hidden = true;
  gate.hidden = false;
  gateInput.value = "";
  gateInput.focus();
}

// Track the most recently loaded mesh so the Download geometry
// button can save it.  Updated by both the in-bubble mesh load and
// the live `visualize` SSE event.
let currentMesh = { url: null, name: null };

function loadMesh(url, name, attempt) {
  // ``attempt`` is the "Attempt NNN" label string (or null/undefined
  // when the mesh sits outside an attempt folder).  Threaded through
  // to window.modelViewer.load so the viewer toolbar shows the
  // attempt badge alongside the filename.
  if (window.modelViewer) window.modelViewer.load(url, name, attempt);
  currentMesh = {
    url,
    name: name || "propeller_mesh.obj",
    attempt: attempt || null,
  };
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
    // Insert an "Attempt NNN" heading before the FIRST artefact of
    // each distinct attempt — keeps multi-attempt bubbles readable
    // and avoids duplicating the label per artefact.  Artefacts
    // without an attempt_label (e.g. input images) reset the
    // running label to null so they don't accidentally inherit the
    // previous group's heading.
    let lastAttemptLabel = null;
    for (const a of opts.artefacts) {
      const thisLabel = a.attempt_label || null;
      if (thisLabel && thisLabel !== lastAttemptLabel) {
        const heading = document.createElement("div");
        heading.className = "artefact-attempt-heading";
        heading.textContent = thisLabel;
        el.appendChild(heading);
      }
      lastAttemptLabel = thisLabel;

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
        view.addEventListener("click", () => loadMesh(a.url, a.name, thisLabel));
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

// Map of in-flight chat turns: turn_id -> { pending: <pending bubble> }.
// Populated when /api/turn returns HTTP 202; drained when the matching
// turn_done event arrives on /api/events.  See
// web_app.py:_run_turn_in_background for the server-side publisher.
const _pendingTurns = new Map();

function _resetComposer() {
  busy = false;
  sendBtn.disabled = false;
  input.disabled = false;
  if (stopBtn) {
    stopBtn.hidden = true;
    stopBtn.disabled = false;
    stopBtn.textContent = "Stop";
  }
  input.focus();
  // A turn just settled → session is now active (build is lazy on
  // /api/turn).  Lock the settings view until the next End Session.
  refreshSessionActive();
}

function finalizeTurn(data) {
  const entry = _pendingTurns.get(data.turn_id);
  if (entry) {
    _pendingTurns.delete(data.turn_id);
    entry.pending.remove();
  } else {
    // SSE event arrived for an unknown turn_id — likely the browser
    // tab was closed and reopened mid-turn, or the server restarted
    // between 202 and turn_done.  Surface the reply anyway so the
    // user isn't left without a response.
    console.warn("[chat] turn_done for unknown turn_id:", data.turn_id);
  }
  addBubble("assistant", data.reply, {
    artefacts: data.artefacts,
    error:
      data.forwarded === false && /internal error/.test(data.reply || ""),
  });
  // Auto-load the most recent mesh produced this turn into the viewer.
  const meshes = (data.artefacts || []).filter((a) => a.kind === "mesh");
  if (meshes.length) {
    const last = meshes[meshes.length - 1];
    loadMesh(last.url, last.name, last.attempt_label || null);
  }
  // Only reset composer state when we owned the pending bubble — a
  // reload-recovery render has no busy state to clear.
  if (entry) _resetComposer();
}

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
    // Step 8: include the user's FIXED parameter dict + RELEASED key
    // list from the Parameters Inputs view if they have changed since
    // the last send.  paramsDiffFixedForSend() returns an object
    // {fixed_params, released_params} where each is either the
    // payload value or null.  Either or both may be null when
    // nothing has changed since the previous send (per locked
    // decision §6.D.B1).
    const fixedDiff =
      typeof paramsDiffFixedForSend === "function"
        ? paramsDiffFixedForSend()
        : { fixed_params: null, released_params: null };
    const reqBody = { message: text };
    if (fixedDiff.fixed_params) reqBody.fixed_params = fixedDiff.fixed_params;
    if (fixedDiff.released_params) reqBody.released_params = fixedDiff.released_params;
    const res = await fetch("/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqBody),
    });
    if (res.status === 401) {
      pending.remove();
      showGate();
      _resetComposer();
      return;
    }
    if (res.status === 409) {
      pending.remove();
      addBubble(
        "assistant",
        "(server says a previous turn is still in flight — please wait for it to finish before sending another)",
        { error: true }
      );
      _resetComposer();
      return;
    }
    // Expected happy path: HTTP 202 Accepted with {ok, status:
    // "started", turn_id}.  The actual reply + artefacts land later
    // as a "turn_done" event on /api/events; see finalizeTurn().
    // We leave busy=true and the pending bubble alive until then.
    if (res.status === 202 || res.status === 200) {
      const data = await res.json();
      const turnId = data && data.turn_id;
      if (!turnId) {
        pending.remove();
        addBubble(
          "assistant",
          "(network error — /api/turn returned HTTP " + res.status +
            " without a turn_id; reply cannot be tracked)",
          { error: true }
        );
        _resetComposer();
        return;
      }
      _pendingTurns.set(turnId, { pending });
      // Do NOT reset busy / pending here — finalizeTurn() does that
      // when the turn_done SSE event arrives.
      return;
    }
    // Any other status (5xx, 400 for empty text, …) — surface as a
    // chat error and clear the in-flight state.  Tries to use the
    // FastAPI {detail: "..."} body when present.
    pending.remove();
    let detail = "HTTP " + res.status;
    try {
      const errBody = await res.json();
      if (errBody && errBody.detail) detail += " — " + errBody.detail;
    } catch (_) {
      /* non-JSON body (e.g. proxy 'upstream error') */
    }
    addBubble(
      "assistant",
      "(server rejected the turn: " + detail + ")",
      { error: true }
    );
    _resetComposer();
  } catch (e) {
    pending.remove();
    addBubble(
      "assistant",
      "(network error — the request did not complete: " + e + ")",
      { error: true }
    );
    _resetComposer();
  }
}

if (stopBtn) {
  stopBtn.addEventListener("click", async () => {
    if (!busy) return;
    // /api/turn was scheduled as a background task — let it finish
    // naturally.  We just tell the server to flag the pipeline for
    // cooperative cancellation; the orchestrator will bail at the
    // next hop boundary and the background task will publish a
    // turn_done event carrying the "(Session interrupted ...)"
    // reply, which finalizeTurn() will render normally.
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

// Run AFTER the server-side End Session work finishes — invoked
// either by the ``session_save_done`` SSE event or by the hard-
// timeout safety net.  Wipes chat / viewer / images / log view and
// re-enables the End Session button.  Idempotent: safe to call
// twice (the second call sees ``endSessionState === null`` and
// returns).
async function finalizeEndSession(evt) {
  if (endSessionState === null) return;
  const { originalEndText, pendingBubble } = endSessionState;
  endSessionState = null;
  if (endSessionTimeoutId !== null) {
    clearTimeout(endSessionTimeoutId);
    endSessionTimeoutId = null;
  }

  endBtn.disabled = false;
  endBtn.textContent = originalEndText || "End Session";
  if (pendingBubble) pendingBubble.remove();

  // Wipe the chat ROOM first; THEN add any error bubble so it
  // survives the wipe.  Existing assistant bubbles belong to the
  // session that just ended and would only confuse the next one.
  messages.innerHTML = "";
  if (evt && evt.ok === false && evt.error) {
    addBubble("assistant", `End Session failed: ${evt.error}`, { error: true });
  } else if (evt && evt.dh && evt.dh.error) {
    addBubble("assistant", `Database Handler error: ${evt.dh.error}`, { error: true });
  }

  // 3D viewer (right of the Chat pane): the mesh belongs to the
  // session that just ended.  Drop it and restore the "No model yet…"
  // placeholder so the next session opens with an empty viewer.
  if (window.modelViewer && window.modelViewer.unload) {
    window.modelViewer.unload();
  }
  currentMesh = { url: null, name: null };
  const dlBtn = document.getElementById("download-mesh");
  if (dlBtn) dlBtn.disabled = true;
  // Parameters Inputs panel: the FIXED / PROPOSED state + the live-
  // preview mesh + the FIXED-dispatch dedup snapshot belong to the
  // session that just ended.  Reset to all-gray VARY at defaults so
  // the next session starts clean; see paramsResetAll() for the full
  // list of state it clears (rows, dedup snapshot, blob URL, viewer
  // mesh, download button, status line).
  if (typeof paramsResetAll === "function") {
    paramsResetAll();
  }
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
  hideAllDynamicArrows();
  const cfg = await (await fetch("/api/config")).json().catch(() => ({}));
  if (cfg.auth_required && !cfg.authed) showGate();
  else input.focus();
  // End Session cleared the in-process session — unlock the settings.
  applySettingsLock(!!cfg.session_active);
}


// --------------------------------------------------------------------
// End Session modal (replaces window.confirm).
// --------------------------------------------------------------------
//
// Step 1: Save? Yes / No / Cancel.
// Step 2 (only on Yes): satisfaction toggle (required) + two optional
// textareas + Submit / Back.
// The Yes-submit path POSTs /api/end with body.feedback populated; the
// No-archive path POSTs with feedback=null.
//
// Internal state is local to the modal — the post-POST locked-UI
// state (button disabled, pendingBubble, hard timeout) is handled by
// performEndSession() below, which is shared between the two paths.

const endModal       = document.getElementById("end-modal");
const endModalStep1  = document.getElementById("end-modal-step1");
const endModalStep2  = document.getElementById("end-modal-step2");
const endModalYes    = document.getElementById("end-modal-yes");
const endModalNo     = document.getElementById("end-modal-no");
const endModalCancel = document.getElementById("end-modal-cancel");
const endModalSubmit = document.getElementById("end-modal-submit");
const endModalBack   = document.getElementById("end-modal-back");
const satBtns        = endModalStep2
  ? endModalStep2.querySelectorAll(".sat-btn")
  : [];
const feedbackWell   = document.getElementById("feedback-well");
const feedbackWrong  = document.getElementById("feedback-wrong");

let selectedSatisfaction = null;   // "yes" | "partially" | "no" | null

function showEndModalStep(which) {
  if (endModalStep1) endModalStep1.hidden = (which !== 1);
  if (endModalStep2) endModalStep2.hidden = (which !== 2);
}
function openEndModal() {
  selectedSatisfaction = null;
  if (feedbackWell)  feedbackWell.value  = "";
  if (feedbackWrong) feedbackWrong.value = "";
  satBtns.forEach((b) => b.classList.remove("selected"));
  if (endModalSubmit) endModalSubmit.disabled = true;
  showEndModalStep(1);
  if (endModal) endModal.hidden = false;
}
function closeEndModal() {
  if (endModal) endModal.hidden = true;
}

// Satisfaction toggle behaviour: clicking a sat-btn picks that value
// and visually marks it; the Submit button is gated until one is
// chosen (the two text fields are intentionally optional).
satBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    selectedSatisfaction = btn.getAttribute("data-value");
    satBtns.forEach((b) => b.classList.toggle(
      "selected", b === btn,
    ));
    if (endModalSubmit) endModalSubmit.disabled = false;
  });
});

if (endModalNo) {
  endModalNo.addEventListener("click", () => {
    closeEndModal();
    performEndSession(false, null);
  });
}
if (endModalCancel) {
  endModalCancel.addEventListener("click", () => {
    closeEndModal();
  });
}
if (endModalYes) {
  endModalYes.addEventListener("click", () => {
    showEndModalStep(2);
  });
}
if (endModalBack) {
  endModalBack.addEventListener("click", () => {
    showEndModalStep(1);
  });
}
if (endModalSubmit) {
  endModalSubmit.addEventListener("click", () => {
    if (!selectedSatisfaction) return;   // belt-and-suspenders
    const feedback = {
      satisfaction:    selectedSatisfaction,
      what_went_well:  (feedbackWell  && feedbackWell.value)  || "",
      what_went_wrong: (feedbackWrong && feedbackWrong.value) || "",
    };
    closeEndModal();
    performEndSession(true, feedback);
  });
}


// --------------------------------------------------------------------
// Shared "actually run /api/end" path — used by both the Yes-with-
// feedback submit and the No-archive button.  Owns the locked-UI
// state (button disabled, pendingBubble, hard timeout, 409/202
// branching, etc.) that was previously inline in the click handler.
// --------------------------------------------------------------------
async function performEndSession(wantSave, feedback) {
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

  // Park the UI state where the SSE handler can pick it up.  Setting
  // this BEFORE awaiting the fetch closes the (tiny) window where a
  // very-fast session_save_done could arrive before the click
  // handler stored its state.
  endSessionState = { originalEndText, pendingBubble };
  // Hard timeout safety net — if the server-side task crashes
  // without publishing session_save_done (or the SSE stream is
  // disconnected for the whole window), we still re-enable the
  // button after 25 minutes so the user is never permanently stuck.
  endSessionTimeoutId = setTimeout(() => {
    console.warn(
      "[End Session] hard timeout (25 min) — no session_save_done " +
      "received; re-enabling button.  The save may still be running " +
      "server-side; check /api/log/stream."
    );
    finalizeEndSession({
      ok: false,
      saved: !!wantSave,
      error: "Timed out waiting for session_save_done after 25 minutes.",
    });
  }, END_SESSION_HARD_TIMEOUT_MS);

  let endResp = null;
  try {
    const reqBody = { save: !!wantSave };
    if (wantSave && feedback) {
      // Only forward feedback when saving — without a DH save it
      // would have nowhere to land for future sessions, and the
      // backend skips the feedback round whenever save=false.
      reqBody.feedback = feedback;
    }
    endResp = await fetch("/api/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqBody),
    });
  } catch (e) {
    /* network error — clear the in-flight state and re-enable the
       button so the user can retry. */
    console.warn("[End Session] network error talking to /api/end:", e);
    if (endSessionTimeoutId !== null) {
      clearTimeout(endSessionTimeoutId);
      endSessionTimeoutId = null;
    }
    endSessionState = null;
    endBtn.disabled = false;
    endBtn.textContent = originalEndText || "End Session";
    if (pendingBubble) pendingBubble.remove();
    return;
  }

  // HTTP 409 — the server already has a save in flight (typically a
  // proxy / browser retry that this call duplicates).  Keep the UI in
  // its locked "Saving…" state: the ORIGINAL /api/end is still
  // running server-side and will publish a session_save_done event
  // when it finishes; the existing SSE handler will run the cleanup.
  // We did NOT register a new in-flight state (endSessionState was
  // already non-null from the original click), so just clear THIS
  // call's pending bubble and leave the locked state alone.
  // See web_app.py:api_end for the backend guard and
  // extra_utilities/TODO_known_issues.md F22 for the diagnosis.
  if (endResp.status === 409) {
    console.warn(
      "[End Session] /api/end returned HTTP 409 — a previous save is " +
      "still in progress; this click was ignored by the server.  " +
      "Leaving the UI in its locked state; the in-flight save will " +
      "complete on its own and trigger cleanup via SSE."
    );
    endBtn.textContent = "Save already in progress…";
    return;
  }

  // HTTP 202 Accepted — the server has kicked off the End Session
  // work in a background task and will publish a session_save_done
  // event on /api/events when it finishes.  The SSE handler in
  // startEventStream() will pick it up and call finalizeEndSession.
  // Until then we leave the locked UI state in place.
  if (endResp.status === 202 || endResp.status === 200) {
    console.log(
      "[End Session] /api/end accepted (HTTP " + endResp.status +
      "); waiting for session_save_done SSE event."
    );
    return;
  }

  // Any other status — treat as failure, clear the in-flight state.
  console.warn(
    "[End Session] unexpected /api/end status " + endResp.status +
    "; falling back to immediate cleanup."
  );
  await finalizeEndSession({
    ok: false,
    saved: !!wantSave,
    error: "Unexpected HTTP status " + endResp.status + " from /api/end.",
  });
}


// The End Session button itself just opens the modal.  All the actual
// "should we save / get feedback / POST /api/end" logic is in the
// modal handlers + performEndSession() above.
endBtn.addEventListener("click", () => {
  if (busy) return;
  // A previous End Session is still waiting on its session_save_done
  // event — ignore clicks while it's in flight.  The button is
  // already disabled by performEndSession but this is belt-and-
  // suspenders for keyboard / scripted activation.
  if (endSessionState !== null) return;
  openEndModal();
});


// Save LOG — snapshot the current session log to R2 without ending
// the session.  Posts to /api/save_log which writes
// <resolved_session_name>/logs/snapshot_<UTC>.log via r2_uploader.
// Brief Saving... / Saved! / Save failed feedback for 1.4 s, same
// pattern as the Copy parameters list button in the chat viewer.
//
// 60 s AbortController timeout so a dead connection (proxy hold,
// network drop mid-response) doesn't leave the button stuck on
// "Saving…" forever — fetch on its own has no built-in timeout.
const _SAVE_LOG_TIMEOUT_MS = 60_000;

if (saveLogBtn) {
  saveLogBtn.addEventListener("click", async () => {
    if (saveLogBtn.disabled) return;
    const originalLabel = saveLogBtn.textContent;
    saveLogBtn.disabled = true;
    saveLogBtn.textContent = "Saving…";
    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(),
      _SAVE_LOG_TIMEOUT_MS,
    );
    try {
      const res = await fetch("/api/save_log", {
        method: "POST",
        signal: controller.signal,
      });
      const body = await res.json().catch(() => ({}));
      if (body.ok) {
        saveLogBtn.textContent = "Saved!";
      } else {
        saveLogBtn.textContent = "Save failed";
        console.warn("[save-log] failed:", body.error || res.statusText);
      }
    } catch (e) {
      saveLogBtn.textContent = (e && e.name === "AbortError")
        ? "Timed out"
        : "Save failed";
    } finally {
      clearTimeout(timeoutId);
      setTimeout(() => {
        saveLogBtn.textContent = originalLabel;
        saveLogBtn.disabled = false;
      }, 1400);
    }
  });
}

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

// Dynamic gray arrows around the Orchestrator and the Tool Caller.
// Each <line> in the SVG represents one specific connection and is
// only visible while that handoff is the most recent agent_active
// event.  Static arrows (always-visible black) cover User ↔
// Receptionist, Receptionist ↔ Orchestrator, UII ↔ Orchestrator,
// DOI ↔ Orchestrator, and the inter-chain backbone — they are not
// touched here.
//
// Keys are the lowercased display names of the two endpoints,
// sorted alphabetically and joined with "|".  Values are the SVG
// <line> element IDs in web/index.html.
const DYNAMIC_ARROW_BY_EDGE = {
  "orchestrator|planner":                    "dyn-orch-planner",
  "dc input creator|orchestrator":           "dyn-orch-dic",
  "dc input inspector|orchestrator":         "dyn-orch-dii",
  "orchestrator|tool caller":                "dyn-orch-tc",
  "propeller configurator|tool caller":      "dyn-tc-propeller",
  "tool caller|visual renderings generator": "dyn-tc-vr",
};
const DYNAMIC_ARROW_IDS = Object.values(DYNAMIC_ARROW_BY_EDGE);

function _edgeKey(fromName, toName) {
  const a = String(fromName || "").trim().toLowerCase();
  const b = String(toName || "").trim().toLowerCase();
  if (!a || !b) return null;
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

// Use setAttribute / removeAttribute rather than the `hidden` IDL
// property: on SVG elements the IDL property does not always
// reflect into the content attribute, which would leave the
// `.orch-dyn-link[hidden]` CSS rule out of sync with reality.
function hideAllDynamicArrows() {
  for (const id of DYNAMIC_ARROW_IDS) {
    const el = document.getElementById(id);
    if (el) el.setAttribute("hidden", "");
  }
}

function applyDynamicArrow(fromName, toName) {
  hideAllDynamicArrows();
  const key = _edgeKey(fromName, toName);
  if (!key) return;
  const arrowId = DYNAMIC_ARROW_BY_EDGE[key];
  if (!arrowId) return;
  const el = document.getElementById(arrowId);
  if (el) el.removeAttribute("hidden");
}

function applyAgentActive(fromName, toName) {
  // Dynamic gray arrows toggle on EVERY handoff (including
  // tool-entry events), so this call runs BEFORE the
  // tool-vs-agent branch so e.g. dyn-tc-propeller shows while
  // Tool Caller is calling the configurator.
  applyDynamicArrow(fromName, toName);

  // Two cases for the box-highlight policy:
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
}

function startEventStream() {
  try {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "visualize" && window.modelViewer) {
          loadMesh(data.url, data.name, data.attempt_label || null);
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
        } else if (data.type === "session_save_done") {
          // The server-side End Session background task has finished
          // (success or failure).  Run the post-save UI cleanup that
          // the click handler deferred when /api/end returned HTTP
          // 202 — clear chat / viewer / images / log view, re-enable
          // the End Session button, and surface any error.
          console.log("[End Session] session_save_done event:", data);
          finalizeEndSession(data);
        } else if (data.type === "params_proposed") {
          // Step 10 of the Parameters Inputs redesign — the
          // Receptionist's propose_attempt tool has fired.  Update
          // the Parameters Inputs view: non-FIXED sliders -> ORANGE
          // at the proposed value; FIXED rows keep their slider but
          // also display "PROPOSED VALUE: X" text (per locked
          // §6.F.C2 / §6.F.C3).  See paramsApplyProposal() for the
          // exact transition rules.
          if (typeof paramsApplyProposal === "function") {
            paramsApplyProposal(data.values || {});
          }
        } else if (data.type === "turn_done") {
          // /api/turn background-task completion signal — see
          // web_app.py:_run_turn_in_background.  finalizeTurn matches
          // the turn_id to the pending bubble captured at /api/turn
          // 202 time, renders the assistant reply, auto-loads any
          // new mesh into the viewer, and clears busy/pending.
          finalizeTurn(data);
        } else if (data.type === "backfill_log") {
          // Live progress line from the chunks_mm backfill (Database
          // options panel) — append to the panel's log box.
          dbOptAppendLog(data.message || "");
        } else if (data.type === "backfill_done") {
          // Terminal backfill signal — re-enable the button + summarise.
          dbOptFinalizeBackfill(data);
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
  // System Prompts view: warn before leaving with unsaved edits
  // (round 4 Q16 — in-app prompt on view-switch).  ``confirm()`` is
  // synchronous; if the user chooses "Cancel" we abort the switch
  // before mutating any nav state.
  if (
    name !== "prompts"
    && typeof promptsState !== "undefined"
    && promptsState.loaded
    && promptsDirtyCount() > 0
  ) {
    const ok = confirm(
      `You have ${promptsDirtyCount()} unsaved system-prompt file(s). `
      + "Switch view and discard them?"
    );
    if (!ok) return;
    promptsDiscardAllBuffers();
  }
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
  if (name === "params" && window.paramsViewer) {
    // The params view starts hidden; the params Viewer was
    // constructed against a 0×0 container.  Force a re-measure each
    // time the user shows the view so the WebGL canvas matches the
    // pane (covers both the first-show case AND any window-resize
    // that happened while the view was hidden — ResizeObserver does
    // not fire for display:none elements in all browsers).
    window.paramsViewer.resize();
    // Auto-build the FEG preview on open so the viewer is never empty
    // and Download geometry is enabled from the start.  Builds the
    // default propeller on first open; reflects the current slider /
    // proposed values on subsequent opens.  Also draws the 2D section
    // cross-sections.
    paramsUpdatePreview();
  }
  if (name === "logstatus") startLogStream();
  else stopLogStream();
  if (name === "questions") {
    loadQuestions();
    refreshSessionActive();
  }
  if (name === "database") {
    // Re-lock the view on every entry — the operator must re-enter
    // the password for any destructive action.  Clears stale status
    // messages from the previous visit too.
    resetDbView();
  }
  if (name === "prompts") {
    if (typeof promptsState !== "undefined") {
      if (!promptsState.loaded) loadPromptsTree();
      else refreshSessionActive();
    }
  }
  if (name === "embed_tests") loadEmbedTests();
  if (name === "db_options") loadDbOptions();
}

for (const b of navItems) {
  b.addEventListener("click", () => switchView(b.dataset.view));
}

// ---------------------------------------------------------------------------
// Database options panel — 3-way DB mode toggle + multimodal chunks_mm
// backfill (architecture doc §6.3).  The mode just RECORDS the choice for
// now; the backfill button streams progress over /api/events
// (backfill_log / backfill_done, handled in startEventStream).
// ---------------------------------------------------------------------------
let dbOptBackfillInFlight = false;

function dbOptEsc(s) {
  return String(s == null ? "" : s).replace(
    /[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function setDbOptStatus(msg, kind) {
  const el = document.getElementById("db-opt-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "db-opt-status" + (kind ? " " + kind : "");
}

function setDbOptBackfillStatus(msg, kind) {
  const el = document.getElementById("db-opt-backfill-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "db-opt-badge" + (kind ? " " + kind : "");
}

function dbOptAppendLog(line) {
  const el = document.getElementById("db-opt-log");
  if (!el) return;
  el.textContent += (el.textContent ? "\n" : "") + line;
  el.scrollTop = el.scrollHeight;
}

function dbOptRow(parent, label, value) {
  const row = document.createElement("div");
  row.className = "db-opt-row";
  const a = document.createElement("span");
  a.className = "db-opt-key";
  a.textContent = label;
  const b = document.createElement("span");
  b.className = "db-opt-val";
  b.textContent = value == null || value === "" ? "—" : String(value);
  row.appendChild(a);
  row.appendChild(b);
  parent.appendChild(row);
}

function dbOptShowMode(mode) {
  // Mark the selected column; the non-selected columns get the dimming
  // veil via CSS (.db-opt-col:not(.selected)::after).  All columns stay
  // fully visible — only the veil changes.
  for (const col of document.querySelectorAll(".db-opt-col")) {
    col.classList.toggle("selected", col.dataset.mode === mode);
  }
}

async function loadDbOptions() {
  try {
    const res = await fetch("/api/db_options");
    const data = await res.json();
    dbOptShowMode(data.mode);

    const t = data.text_only || {};
    const tEl = document.getElementById("db-opt-text-params");
    if (tEl) {
      tEl.innerHTML = "";
      dbOptRow(tEl, "Embedding provider", t.embedding_provider);
      dbOptRow(tEl, "Embedding model", t.embedding_model);
      dbOptRow(tEl, "Vector dimension", t.output_dimension);
      dbOptRow(tEl, "Images embedded", "None (text only)");
    }

    const m = data.multimodal || {};
    const mEl = document.getElementById("db-opt-mm-params");
    if (mEl) {
      mEl.innerHTML = "";
      dbOptRow(mEl, "Embedding model", m.embedding_model);
      dbOptRow(mEl, "Vector dimension", m.output_dimension);
      dbOptRow(mEl, "Max image side (px)", m.max_image_side_px);
      dbOptRow(mEl, "Input type", m.input_type);
      dbOptRow(mEl, "Image + text fusion", m.image_text_fusion ? "On" : "Off");
      dbOptRow(mEl, "Images embedded", m.images_embedded);
      dbOptRow(mEl, "Call mode", m.call_mode);
      dbOptRow(mEl, "embedding_model tag", m.embedding_model_string);
      dbOptRow(mEl, "Visible to agents", m.agents_to);
    }

    const fmEl = document.getElementById("db-opt-mm-fieldmap");
    if (fmEl) {
      fmEl.innerHTML = "";
      for (const f of m.field_mapping || []) {
        const row = document.createElement("div");
        row.className = "db-opt-row";
        row.innerHTML =
          "<span class=\"db-opt-key\">" + dbOptEsc(f.kind) + "</span>" +
          "<span class=\"db-opt-val\">agent_from=<code>" + dbOptEsc(f.agent_from) +
          "</code>, field=<code>" + dbOptEsc(f.field) +
          "</code>, fused with " + dbOptEsc(f.fused_text) + "</span>";
        fmEl.appendChild(row);
      }
    }

    dbOptBackfillInFlight = !!data.backfill_in_flight;
    const btn = document.getElementById("db-opt-backfill-btn");
    if (btn) btn.disabled = dbOptBackfillInFlight;
    setDbOptBackfillStatus(
      dbOptBackfillInFlight ? "Running…" : "",
      dbOptBackfillInFlight ? "busy" : "");
    setDbOptStatus("", "");
  } catch (e) {
    setDbOptStatus("Could not load database options: " + (e.message || e), "err");
  }
}

async function onDbOptModeClick(mode) {
  try {
    const res = await fetch("/api/db_options", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    const data = await res.json();
    if (!res.ok) {
      setDbOptStatus(data.detail || "Could not save the choice.", "err");
      return;
    }
    dbOptShowMode(data.mode);
    setDbOptStatus(
      "Saved — recorded choice: " + data.mode +
      " (no routing change yet; both databases are still written).", "ok");
  } catch (e) {
    setDbOptStatus("Could not save the choice: " + (e.message || e), "err");
  }
}

function dbOptFinalizeBackfill(data) {
  dbOptBackfillInFlight = false;
  const btn = document.getElementById("db-opt-backfill-btn");
  if (btn) btn.disabled = false;
  if (data.ok) {
    const line =
      "Done: " + data.done + " embedded, " + data.skipped + " skipped, " +
      data.errors + " errors, " + data.rows_inserted + " rows (" +
      data.sessions + " sessions).";
    setDbOptBackfillStatus(line, "ok");
    dbOptAppendLog("==== Backfill complete — " + line + " ====");
  } else {
    setDbOptBackfillStatus("Failed: " + (data.error || "unknown error"), "err");
    dbOptAppendLog("==== Backfill FAILED: " + (data.error || "unknown") + " ====");
  }
}

async function onDbOptRunBackfill() {
  if (dbOptBackfillInFlight) return;
  const force = !!(document.getElementById("db-opt-force") || {}).checked;
  const ok = confirm(force
    ? "Force re-embed ALL sessions into the multimodal database? This "
      + "re-embeds everything and can take several minutes."
    : "Run the multimodal backfill? Sessions already embedded at the "
      + "current model are skipped. This can take several minutes.");
  if (!ok) return;

  dbOptBackfillInFlight = true;
  const btn = document.getElementById("db-opt-backfill-btn");
  if (btn) btn.disabled = true;
  const logEl = document.getElementById("db-opt-log");
  if (logEl) logEl.textContent = "";
  setDbOptBackfillStatus("Starting…", "busy");

  try {
    const res = await fetch("/api/db_options/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    if (res.status === 409) {
      setDbOptBackfillStatus("Already running", "busy");
      return;  // leave button disabled; the running task will finalise
    }
    const data = await res.json();
    if (data.ok) {
      setDbOptBackfillStatus("Running…", "busy");
      dbOptAppendLog(
        "Backfill started" + (force ? " (force re-embed all)" : "") +
        " — streaming progress…");
    } else {
      dbOptBackfillInFlight = false;
      if (btn) btn.disabled = false;
      setDbOptBackfillStatus("Could not start: " + (data.error || "unknown"), "err");
    }
  } catch (e) {
    dbOptBackfillInFlight = false;
    if (btn) btn.disabled = false;
    setDbOptBackfillStatus("Could not start: " + (e.message || e), "err");
  }
}

// Delegated wiring — robust whether or not the panel DOM exists at load.
document.addEventListener("click", (ev) => {
  const t = ev.target;
  if (!t || !t.closest) return;
  // Backfill button — run it; don't also treat the click as a select.
  if (t.closest("#db-opt-backfill-btn")) {
    onDbOptRunBackfill();
    return;
  }
  // Leave the column's interactive controls (force checkbox, log box) to
  // their own behaviour — clicking them must not change the selection.
  if (t.closest("#db-opt-force") || t.closest("#db-opt-log")) return;
  // Clicking anywhere else in a selectable column selects that option.
  const col = t.closest(".db-opt-col");
  if (col && !col.classList.contains("db-opt-col-soon")) {
    onDbOptModeClick(col.dataset.mode);
  }
});
// Keyboard a11y: Enter / Space on a focused selectable column selects it.
document.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const t = ev.target;
  if (!t || !t.classList || !t.classList.contains("db-opt-col")) return;
  if (t.classList.contains("db-opt-col-soon")) return;
  ev.preventDefault();
  onDbOptModeClick(t.dataset.mode);
});

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
    // The flag list may include RAG_ENABLED (the master switch for
    // database access).  Re-fetch the DBa state immediately and
    // repaint the chart's banner + button dimming so the visual
    // master-on/master-off state matches what was just saved,
    // without needing the operator to refresh the page.
    await loadDbAccessState();
    paintDbaBanner();
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
    label: "Context Pruner" },
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
// DBa (database access) state — { flags: {agent: bool, ...}, rag_enabled }.
// Loaded by loadDbAccessState() at the same time as lrState; drives the
// per-agent DBa toggle button rendered by renderLrOverlay() and the
// master-off banner painted by paintDbaBanner().
let dbaState = { flags: {}, rag_enabled: false };
let ocrState = { flags: {}, ocr_enabled: false };

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

    // DBa (database access) toggle button.  Only the 8 chain agents
    // are eligible (matches database_access.DEFAULT_AGENTS server-
    // side).  Other roles (e.g. DH if it were on this chart) get no
    // button.
    if (dbaState.flags && Object.prototype.hasOwnProperty.call(dbaState.flags, b.key)) {
      const dbaBtn = document.createElement("button");
      dbaBtn.className = "lr-dba-btn";
      dbaBtn.type = "button";
      dbaBtn.textContent = "DBa";
      dbaBtn.title =
        "DBa = Database access.  Toggle whether this agent gets " +
        "database_search bound + the fragment in its prompt.  " +
        "Takes effect on the next session.";
      const initialOn = !!dbaState.flags[b.key];
      dbaBtn.classList.toggle("dba-on",  initialOn);
      dbaBtn.classList.toggle("dba-off", !initialOn);
      dbaBtn.addEventListener("click", () => onDbaToggle(b.key, dbaBtn));
      div.appendChild(dbaBtn);
    }

    // OCR (per-agent OCR access) toggle button.  Only the 5 image
    // agents are eligible (matches ocr_access.DEFAULT_AGENTS server-
    // side).  Mirrors the DBa button above; distinct blue accent.
    if (ocrState.flags && Object.prototype.hasOwnProperty.call(ocrState.flags, b.key)) {
      const ocrBtn = document.createElement("button");
      ocrBtn.className = "lr-ocr-btn";
      ocrBtn.type = "button";
      ocrBtn.textContent = "OCR";
      ocrBtn.title =
        "OCR = read text on user images.  Toggle whether this agent's " +
        "image tools run OCR (the extract_text flag + the ocr_region " +
        "tool).  Takes effect on the next session.";
      const ocrOn = !!ocrState.flags[b.key];
      ocrBtn.classList.toggle("ocr-on",  ocrOn);
      ocrBtn.classList.toggle("ocr-off", !ocrOn);
      ocrBtn.addEventListener("click", () => onOcrToggle(b.key, ocrBtn));
      div.appendChild(ocrBtn);
    }

    overlay.appendChild(div);
  }
}

// ---- Workflow presets (Proposed OpenAI / Anthropic / …) ------------------

function renderLrPresets() {
  // Rendered into the .lr-global row's #lr-presets container.  One
  // button per entry in lrState.proposed_workflows (sourced from
  // workflow_settings/llm_defaults.py PROPOSED_WORKFLOWS).  Click
  // populates every per-agent override field with the workflow's
  // (provider, model); the user reviews and hits the existing
  // "Save LLM routing" button to commit.  DBa is untouched.
  const host = lrEl("lr-presets");
  if (!host || !lrState) return;
  host.innerHTML = "";
  const workflows = Array.isArray(lrState.proposed_workflows)
    ? lrState.proposed_workflows : [];
  for (const wf of workflows) {
    if (!wf || !wf.id || !wf.provider || !wf.models) continue;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ghost lr-preset-btn";
    btn.textContent = wf.label || wf.id;
    btn.title =
      "Populate every per-agent provider+model in the chart with the " +
      (wf.label || wf.id) + " configuration.  Does NOT save — click " +
      "Save LLM routing to commit.  DBa toggles are not touched.";
    btn.addEventListener("click", () => applyLrPreset(wf));
    host.appendChild(btn);
  }
}

function applyLrPreset(wf) {
  if (!lrState || !wf || !wf.provider || !wf.models) return;
  let touched = 0;
  for (const a of lrState.agents) {
    const proposed = wf.models[a.key];
    if (!proposed) continue;  // workflow doesn't list this agent
    a.override_provider = wf.provider;
    a.override_model = proposed;
    touched += 1;
  }
  // Re-render the per-agent overlay so the input fields show the new
  // values; DBa state + Global LLM dropdown are untouched.
  renderLrOverlay();
  setLrStatus(
    "Populated " + touched + " agent row(s) with " +
    (wf.label || wf.id) + ".  Click Save LLM routing to commit.",
    "ok",
  );
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
    // Also fetch the DBa (database access) state — drives the per-
    // agent toggle button rendered inside each agent box and the
    // master-off banner.  Non-blocking: if it fails, we render the
    // chart anyway with all buttons defaulted to OFF.
    await loadDbAccessState();
    await loadOcrAccessState();
    buildLrChart();
    renderLrGlobal();
    renderLrPresets();
    renderLrOverlay();
    paintDbaBanner();
    const _ocrOv = document.getElementById("lr-overlay");
    if (_ocrOv) _ocrOv.classList.toggle("ocr-master-off", !ocrState.ocr_enabled);
    setLrStatus("", "");
  } catch (e) {
    setLrStatus("Network error: " + e, "err");
  }
}

async function loadDbAccessState() {
  try {
    const res = await fetch("/api/database-access");
    if (!res.ok) return;
    dbaState = await res.json();
  } catch (e) {
    // Non-blocking — leave dbaState as-is (defaults to empty).
  }
}

async function loadOcrAccessState() {
  try {
    const res = await fetch("/api/ocr-access");
    if (!res.ok) return;
    ocrState = await res.json();
  } catch (e) {
    // Non-blocking — leave ocrState as-is (defaults to empty).
  }
}

function paintDbaBanner() {
  const banner = document.getElementById("dba-banner");
  const overlay = document.getElementById("lr-overlay");
  // Toggle the master-off class on the overlay so CSS dims every
  // .lr-dba-btn inside it without us having to touch each button.
  if (overlay) {
    overlay.classList.toggle("dba-master-off", !dbaState.rag_enabled);
  }
  if (!banner) return;
  if (dbaState.rag_enabled) {
    banner.hidden = true;
    banner.textContent = "";
  } else {
    banner.hidden = false;
    banner.textContent =
      "Master switch RAG_ENABLED is OFF — no agent has " +
      "database access this session, regardless of the per-agent " +
      "DBa toggles below.";
  }
}

async function onDbaToggle(agentKey, btn) {
  // Optimistic toggle — flip locally, send to server, revert on
  // error.  Same pattern as several other workflow-settings writes.
  const newState = !btn.classList.contains("dba-on");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/database-access", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ agent: agentKey, enabled: newState }),
    });
    if (res.status === 401) { showGate(); return; }
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      setLrStatus(data.detail || "Locked — session is active.", "err");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setLrStatus(data.detail || "DBa toggle failed.", "err");
      return;
    }
    if (data.flags) dbaState.flags = data.flags;
    btn.classList.toggle("dba-on",  newState);
    btn.classList.toggle("dba-off", !newState);
    setLrStatus(
      "DBa for " + agentKey + " → " + (newState ? "ON" : "OFF") +
      ".  Takes effect on the next session.",
      "ok",
    );
  } catch (e) {
    setLrStatus("Network error: " + e, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function onOcrToggle(agentKey, btn) {
  // Optimistic toggle — mirror of onDbaToggle for the OCR per-agent flag.
  const newState = !btn.classList.contains("ocr-on");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/ocr-access", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ agent: agentKey, enabled: newState }),
    });
    if (res.status === 401) { showGate(); return; }
    if (res.status === 409) {
      const data = await res.json().catch(() => ({}));
      setLrStatus(data.detail || "Locked — session is active.", "err");
      return;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setLrStatus(data.detail || "OCR toggle failed.", "err");
      return;
    }
    if (data.flags) ocrState.flags = data.flags;
    btn.classList.toggle("ocr-on",  newState);
    btn.classList.toggle("ocr-off", !newState);
    setLrStatus(
      "OCR for " + agentKey + " → " + (newState ? "ON" : "OFF") +
      ".  Takes effect on the next session.",
      "ok",
    );
  } catch (e) {
    setLrStatus("Network error: " + e, "err");
  } finally {
    if (btn) btn.disabled = false;
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
const Q_FIXED  = []; // populated by /api/fixed-feedback-questions — rendered
                     // as the LAST rows of the schedule table, read-only.
                     // See architecture doc §3.7 + warnings_developer.md W24.
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

  // Help text: leaving every checkbox unchecked is NOT "no agents
  // can see this Q+A" — the Database Handler interprets an empty
  // to_agents as "all primary agents have access" (the permissive
  // default).  Tick boxes here only to RESTRICT visibility.  Mirror
  // of the rule in extra_utilities/db_design/database_and_RAG_architecture.md
  // §3.6 and W21 in extra_utilities/warnings_developer.md.
  const help = document.createElement("div");
  help.className = "q-popover-help";
  help.textContent =
    "Tick to restrict visibility. Leaving all unchecked means " +
    "all primary agents have access (default).";
  pop.appendChild(help);

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
    // Empty to_agents means the DH inserts the chunk with
    // agents_to = [all primary agents] (architecture doc §3.6 /
    // warnings_developer.md W21).  Text reflects the permissive
    // default rather than the previous misleading "(click to set)".
    empty.textContent = "(all agents — click to restrict)";
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

  // ---- Fixed feedback questions appended at the end -----------------
  // Per architecture doc §3.7, the fixed questions live in code
  // (workflow_settings/fixed_feedback_questions.py) and render as
  // the LAST rows of this table, read-only and visually greyer.
  // Editable rows CANNOT be moved past them — the fixed rows have
  // no DnD listeners, so dropping on them is a no-op.  The
  // "+ New question" button appends to qState.questions, which is
  // rendered BEFORE this block, so a new editable row always lands
  // just above the fixed rows.  See warnings_developer.md W24.
  if (Q_FIXED.length > 0) {
    const dividerTr = document.createElement("tr");
    dividerTr.className = "q-fixed-divider";
    const dividerTd = document.createElement("td");
    dividerTd.colSpan = 9;
    dividerTd.innerHTML =
      "↓ Fixed questions asked to the user — read-only, defined in " +
      "<code>workflow_settings/fixed_feedback_questions.py</code>";
    dividerTr.appendChild(dividerTd);
    tbody.appendChild(dividerTr);
    for (let j = 0; j < Q_FIXED.length; j++) {
      tbody.appendChild(buildFixedRowTr(Q_FIXED[j], "F" + (j + 1)));
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

// Builds a read-only row for Q_FIXED — rendered AT THE END of
// the schedule table, beneath the editable rows.  Visually greyer
// (.q-fixed-row), not draggable, no DnD listeners, no
// insert-above button, no Customize controls.  Uses ``disabled``
// <input>/<select>/<textarea> so the column widths and vertical
// alignment match the editable rows above.  See architecture
// doc §3.7 + warnings_developer.md W24.
function buildFixedRowTr(q, numLabel) {
  const tr = document.createElement("tr");
  tr.className = "q-row q-fixed-row";
  tr.draggable = false;

  // Grip cell — empty (no drag glyph, no insert-above button).
  const grip = document.createElement("td");
  grip.className = "q-grip";
  tr.appendChild(grip);

  // Number — "F1", "F2", … so the label distinguishes the fixed
  // rows from numerically-indexed editable rows above.
  const num = document.createElement("td");
  num.className = "q-num";
  num.textContent = numLabel;
  tr.appendChild(num);

  // Name (the chunks.field value, e.g. "Positive User Comments").
  const tdName = document.createElement("td");
  const inputName = document.createElement("input");
  inputName.type = "text";
  inputName.className = "q-name-input";
  inputName.value = q.field || "";
  inputName.disabled = true;
  tdName.appendChild(inputName);
  tr.appendChild(tdName);

  // Description — the exact question text shown to the user.
  const tdDesc = document.createElement("td");
  const inputDesc = document.createElement("textarea");
  inputDesc.className = "q-desc-input";
  inputDesc.value = q.question || "";
  inputDesc.rows = 2;
  inputDesc.disabled = true;
  tdDesc.appendChild(inputDesc);
  tr.appendChild(tdDesc);

  // From — fixed feedback rows always come FROM the User.
  const tdFrom = document.createElement("td");
  const selFrom = document.createElement("select");
  selFrom.className = "q-from-select";
  selFrom.disabled = true;
  const optFrom = document.createElement("option");
  optFrom.value = "User";
  optFrom.textContent = "User";
  selFrom.appendChild(optFrom);
  tdFrom.appendChild(selFrom);
  tr.appendChild(tdFrom);

  // To — "(all primary agents)" rendered as a disabled text input.
  const tdTo = document.createElement("td");
  const inputTo = document.createElement("input");
  inputTo.type = "text";
  inputTo.className = "q-name-input";
  inputTo.value = "(all primary agents)";
  inputTo.disabled = true;
  tdTo.appendChild(inputTo);
  tr.appendChild(tdTo);

  // Scope — session.
  const tdScope = document.createElement("td");
  const selScope = document.createElement("select");
  selScope.className = "q-scope-select";
  selScope.disabled = true;
  const optScope = document.createElement("option");
  optScope.value = "session";
  optScope.textContent = "session";
  selScope.appendChild(optScope);
  tdScope.appendChild(selScope);
  tr.appendChild(tdScope);

  // Type — Semantic.
  const tdType = document.createElement("td");
  const selType = document.createElement("select");
  selType.className = "q-type-select";
  selType.disabled = true;
  const optType = document.createElement("option");
  optType.value = "Semantic";
  optType.textContent = "Semantic";
  selType.appendChild(optType);
  tdType.appendChild(selType);
  tr.appendChild(tdType);

  // Customize / actions — em dash placeholder.
  const tdActions = document.createElement("td");
  tdActions.className = "q-fixed-actions";
  tdActions.textContent = "—";
  tr.appendChild(tdActions);

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
    // Fetch the editable schedule and the read-only fixed feedback
    // questions in parallel.  The fixed questions render as the
    // LAST rows of the same table (see renderQuestions +
    // buildFixedRowTr), greyer and not editable.  Source of truth:
    // workflow_settings/fixed_feedback_questions.py.  See
    // architecture doc §3.7 + warnings_developer.md W24.
    const [scheduleRes, fixedRes] = await Promise.all([
      fetch("/api/dh-schedule"),
      fetch("/api/fixed-feedback-questions"),
    ]);
    if (scheduleRes.status === 401) { showGate(); return; }
    if (!scheduleRes.ok) {
      const data = await scheduleRes.json().catch(() => ({}));
      qSetStatus(data.detail || "Could not load schedule.", "err");
      return;
    }
    const data = await scheduleRes.json();
    qState = {
      version: data.version || 1,
      questions: data.questions || [],
    };
    Q_AGENTS.length = 0;
    for (const a of (data.agents || [])) Q_AGENTS.push(a);
    // Best-effort: editable schedule still renders if this endpoint
    // fails; the fixed-rows section is just omitted.
    Q_FIXED.length = 0;
    if (fixedRes.ok) {
      try {
        const fdata = await fixedRes.json();
        for (const q of (fdata.questions || [])) Q_FIXED.push(q);
      } catch (e) {
        console.warn("[fixed-feedback-questions] parse failed:", e);
      }
    } else {
      console.warn(
        "[fixed-feedback-questions] HTTP " + fixedRes.status
      );
    }
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

// --- Per-image compression tuning (single preview + compare + lightbox) ---
const cmpSlider = $("cmp-slider");
const cmpNumber = $("cmp-number");
const cmpStats = $("cmp-stats");
const cmpSave = $("cmp-save");
const cmpStatusEl = $("cmp-status");
const cmpCompare = $("cmp-compare");
const cmpLightbox = $("cmp-lightbox");
const cmpLbImg = $("cmp-lb-img");
const cmpLbSlider = $("cmp-lb-slider");
const cmpLbLabel = $("cmp-lb-label");
const cmpLbClose = $("cmp-lb-close");
const cmpLbStage = $("cmp-lb-stage");
const cmpLbCompare = $("cmp-lb-compare");
const cmpLbZoomIn = $("cmp-lb-zoomin");
const cmpLbZoomOut = $("cmp-lb-zoomout");
const cmpLbReset = $("cmp-lb-reset");
const cmpLbZoomLvl = $("cmp-lb-zoomlvl");
let cmpPreviewTimer = null;
let cmpSuggested = 0;
let cmpCurrentSrc = "";   // current compressed-preview src (compare + lightbox)
let cmpOrigUrl = "";      // original-image file URL for the selected image

function setCmpStatus(msg, kind) {
  if (!cmpStatusEl) return;
  cmpStatusEl.textContent = msg || "";
  cmpStatusEl.className = "img-status" + (kind ? " " + kind : "");
}
function cmpKB(n) { return Math.max(1, Math.round(n / 1024)); }

// Keep the panel slider, number box and lightbox slider/label in lockstep.
function applyDegreeUI(v) {
  v = Math.max(0, Math.min(100, v || 0));
  if (cmpSlider) cmpSlider.value = v;
  if (cmpNumber) cmpNumber.value = v;
  if (cmpLbSlider) cmpLbSlider.value = v;
  if (cmpLbLabel) cmpLbLabel.textContent = "Compression: " + v + "%";
}

async function loadCompression(name) {
  if (!cmpSlider) return;
  cmpStats.textContent = "";
  setCmpStatus("", "");
  cmpOrigUrl = "/api/images/file?name=" + encodeURIComponent(name) +
    "&_=" + Date.now();
  try {
    const res = await fetch(
      "/api/images/compression?name=" + encodeURIComponent(name)
    );
    if (!res.ok) return;
    const d = await res.json();
    cmpSuggested = d.suggested || 0;
    const deg = (d.degree === null || d.degree === undefined)
      ? cmpSuggested : d.degree;
    applyDegreeUI(deg);
    updateCompressionPreview();
  } catch (e) { /* non-fatal */ }
}

function cmpSync(el) {
  applyDegreeUI(parseInt(el.value, 10) || 0);
  clearTimeout(cmpPreviewTimer);
  cmpPreviewTimer = setTimeout(updateCompressionPreview, 220);
}

async function updateCompressionPreview() {
  if (!imgSelected || !cmpSlider) return;
  const deg = parseInt(cmpSlider.value, 10) || 0;
  cmpStats.textContent = "…";
  try {
    const res = await fetch(
      "/api/images/compression/preview?name=" +
        encodeURIComponent(imgSelected) + "&degree=" + deg
    );
    if (!res.ok) { cmpStats.textContent = ""; return; }
    const d = await res.json();
    cmpCurrentSrc = d.preview;
    if (imgPreview) imgPreview.src = d.preview;      // the single preview IS the compressed one
    if (cmpLbImg && cmpLightbox && !cmpLightbox.hidden) cmpLbImg.src = d.preview;
    const o = d.orig, c = d.compressed;
    cmpStats.innerHTML =
      "<b>" + o.width + "×" + o.height + "</b> → <b>" +
        c.width + "×" + c.height + "</b> px" +
      " &nbsp;·&nbsp; Anthropic " + o.tokens.anthropic + " → " +
        c.tokens.anthropic + " tok" +
      " &nbsp;·&nbsp; OpenAI " + o.tokens.openai + " → " +
        c.tokens.openai + " tok" +
      " &nbsp;·&nbsp; " + cmpKB(o.bytes) + " → " + cmpKB(c.bytes) + " KB";
  } catch (e) { cmpStats.textContent = ""; }
}

async function saveCompression() {
  if (!imgSelected) return;
  const deg = parseInt(cmpSlider.value, 10) || 0;
  cmpSave.disabled = true;
  try {
    const res = await fetch("/api/images/compression", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: imgSelected, degree: deg }),
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) { setCmpStatus(d.detail || "Save failed.", "err"); return; }
    setCmpStatus("Compression saved (" + deg + "%).", "ok");
  } catch (e) {
    setCmpStatus("Save failed: " + e, "err");
  } finally {
    cmpSave.disabled = false;
  }
}

// Hold-to-compare: show the original while pressed, compressed on release.
function cmpShowOriginal() { if (cmpOrigUrl && imgPreview) imgPreview.src = cmpOrigUrl; }
function cmpShowCompressed() { if (cmpCurrentSrc && imgPreview) imgPreview.src = cmpCurrentSrc; }

// Full-screen enlarge with a live slider at the bottom.
function openLightbox() {
  if (!cmpLightbox || !imgSelected) return;
  cmpLbImg.src = cmpCurrentSrc || cmpOrigUrl;
  applyDegreeUI(parseInt(cmpSlider.value, 10) || 0);
  cmpLightbox.hidden = false;
  lbReset();
}
function closeLightbox() { if (cmpLightbox) cmpLightbox.hidden = true; }

// Zoom + pan for the enlarged image (transform = translate then scale).
const LB_MAX_ZOOM = 100, LB_MIN_ZOOM = 1;
let lbScale = 1, lbTx = 0, lbTy = 0;
let lbDragging = false, lbDragX = 0, lbDragY = 0;

function lbApply() {
  if (!cmpLbImg) return;
  cmpLbImg.style.transform =
    "translate(" + lbTx + "px," + lbTy + "px) scale(" + lbScale + ")";
  cmpLbImg.style.cursor =
    lbScale > 1 ? (lbDragging ? "grabbing" : "grab") : "default";
  if (cmpLbZoomLvl) cmpLbZoomLvl.textContent = lbScale.toFixed(1) + "×";
}
function lbReset() { lbScale = 1; lbTx = 0; lbTy = 0; lbApply(); }
function lbZoomTo(newScale, cx, cy) {
  newScale = Math.max(LB_MIN_ZOOM, Math.min(LB_MAX_ZOOM, newScale));
  if (Math.abs(newScale - lbScale) < 1e-4) return;
  // Keep the point (cx,cy) — relative to stage centre — fixed while scaling.
  lbTx = cx - (newScale / lbScale) * (cx - lbTx);
  lbTy = cy - (newScale / lbScale) * (cy - lbTy);
  lbScale = newScale;
  if (lbScale <= LB_MIN_ZOOM + 1e-6) { lbTx = 0; lbTy = 0; }
  lbApply();
}
// Hold-to-compare keeps the current zoom/position (same element, swap src).
function lbShowOriginal() { if (cmpOrigUrl && cmpLbImg) cmpLbImg.src = cmpOrigUrl; }
function lbShowCompressed() { if (cmpCurrentSrc && cmpLbImg) cmpLbImg.src = cmpCurrentSrc; }

if (cmpSlider) {
  cmpSlider.addEventListener("input", () => cmpSync(cmpSlider));
  cmpNumber.addEventListener("input", () => cmpSync(cmpNumber));
  cmpSave.addEventListener("click", saveCompression);
}
if (cmpCompare) {
  cmpCompare.addEventListener("mousedown", cmpShowOriginal);
  cmpCompare.addEventListener("mouseup", cmpShowCompressed);
  cmpCompare.addEventListener("mouseleave", cmpShowCompressed);
  cmpCompare.addEventListener("touchstart",
    (e) => { e.preventDefault(); cmpShowOriginal(); }, { passive: false });
  cmpCompare.addEventListener("touchend", cmpShowCompressed);
}
if (imgPreview) {
  imgPreview.addEventListener("click", openLightbox);
}
if (cmpLightbox) {
  cmpLbSlider.addEventListener("input", () => cmpSync(cmpLbSlider));
  cmpLbClose.addEventListener("click", closeLightbox);

  // Zoom: on-screen buttons (toward centre) + wheel (toward cursor).
  cmpLbZoomIn.addEventListener("click", () => lbZoomTo(lbScale * 1.4, 0, 0));
  cmpLbZoomOut.addEventListener("click", () => lbZoomTo(lbScale / 1.4, 0, 0));
  cmpLbReset.addEventListener("click", lbReset);
  cmpLbStage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = cmpLbStage.getBoundingClientRect();
    lbZoomTo(lbScale * (e.deltaY < 0 ? 1.18 : 1 / 1.18),
      e.clientX - (r.left + r.width / 2),
      e.clientY - (r.top + r.height / 2));
  }, { passive: false });

  // Pan: click-drag (only when zoomed in).
  cmpLbStage.addEventListener("mousedown", (e) => {
    if (lbScale <= 1) return;
    lbDragging = true; lbDragX = e.clientX; lbDragY = e.clientY;
    lbApply(); e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!lbDragging) return;
    lbTx += e.clientX - lbDragX; lbTy += e.clientY - lbDragY;
    lbDragX = e.clientX; lbDragY = e.clientY; lbApply();
  });
  window.addEventListener("mouseup", () => {
    if (lbDragging) { lbDragging = false; lbApply(); }
  });

  // Compare: hold to show the original at the same zoom/position.
  cmpLbCompare.addEventListener("mousedown", lbShowOriginal);
  cmpLbCompare.addEventListener("mouseup", lbShowCompressed);
  cmpLbCompare.addEventListener("mouseleave", lbShowCompressed);
  cmpLbCompare.addEventListener("touchstart",
    (e) => { e.preventDefault(); lbShowOriginal(); }, { passive: false });
  cmpLbCompare.addEventListener("touchend", lbShowCompressed);

  // Keyboard: arrows pan the zoomed image, Esc closes.
  document.addEventListener("keydown", (e) => {
    if (cmpLightbox.hidden) return;
    if (e.key === "Escape") { closeLightbox(); return; }
    const ae = document.activeElement;
    if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA")) return;
    const step = 48;
    if (e.key === "ArrowRight") lbTx += step;
    else if (e.key === "ArrowLeft") lbTx -= step;
    else if (e.key === "ArrowUp") lbTy -= step;
    else if (e.key === "ArrowDown") lbTy += step;
    else return;
    e.preventDefault(); lbApply();
  });
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
  loadCompression(name);
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


// ---------------------------------------------------------------------------
// Parameters Inputs view  (Step 2 of the redesign — see
// extra_utilities/web_interface_notes.md §§1-7)
// ---------------------------------------------------------------------------
// Split-pane layout: 3D viewer LEFT (wired in Step 4), scrolling
// parameter column RIGHT.  All 17 propeller parameters rendered
// in order, grouped by section (General / Inner / Middle / Outer)
// with the matching profile image shown inline above each section.
// No tabs, no Next/Back navigation.
//
// Each slider row carries a left-side state button that will cycle
// through VARY (gray, unpressed) / FIXED (green, pressed) / PROPOSED
// (orange, from system).  Step 2 ships the visual shell only: the
// button renders gray "VARY" but is not yet interactive
// (Step 3 wires VARY ↔ FIXED on slider modification; Step 10 wires
// PROPOSED from the propose_attempt SSE event).
//
// Slider ranges are sourced from DC_prompt_fragments/dc_config/parameters.md
// (the SAME ranges agents validate against).  Defaults are the
// reference's pragmatic mid-of-range values.  Units (from
// parameters.md) appear in the min / current / max display and
// (Step 8) in the auto-appended FIXED block sent to the agents.

const PARAM_GROUPS = [
  {
    key: "general",
    label: "General Parameters",
    image: "/static/images/general-profile.png",
    imageAlt: "General profile diagram",
    params: [
      { key: "impellerRadius",    label: "Propeller Radius",     unit: "mm",                 min: 60,  max: 80,  step: 1,    value: 71 },
      { key: "impellerHeight",    label: "Propeller Height",     unit: "mm",                 min: 4,   max: 10,  step: 1,    value: 8  },
      { key: "impellerThickness", label: "Propeller Thickness",  unit: "mm",                 min: 1,   max: 5,   step: 1,    value: 2  },
      { key: "bladeCount",        label: "Blade Count",          unit: "",                   min: 3,   max: 6,   step: 1,    value: 3  },
    ],
  },
  {
    key: "inner",
    label: "Inner Profile",
    image: "/static/images/inner-profile.png",
    imageAlt: "Inner profile diagram",
    params: [
      { key: "innerThickness",    label: "Thickness",            unit: "% of chord",         min: 3,   max: 24,  step: 1,    value: 6  },
      { key: "innerMaxPos",       label: "Max Position",         unit: "tenths of chord",    min: 2,   max: 8,   step: 1,    value: 4  },
      { key: "innerCamber",       label: "Camber",               unit: "% of chord",         min: 0,   max: 9,   step: 1,    value: 4  },
      { key: "innerChord",        label: "Chord Length",         unit: "mm",                 min: 3,   max: 11,  step: 1,    value: 11 },
      { key: "innerAngle",        label: "Angle of Attack",      unit: "degrees",            min: 2,   max: 25,  step: 1,    value: 25 },
    ],
  },
  {
    key: "middle",
    label: "Middle Profile",
    image: "/static/images/middle-profile.png",
    imageAlt: "Middle profile diagram",
    params: [
      { key: "middlePos",         label: "Radial Position",      unit: "× impellerRadius",   min: 0.3, max: 0.7, step: 0.05, value: 0.3 },
      { key: "middleChord",       label: "Chord Length",         unit: "mm",                 min: 10,  max: 30,  step: 1,    value: 20 },
      { key: "middleAngle",       label: "Angle of Attack",      unit: "degrees",            min: 2,   max: 25,  step: 1,    value: 15 },
    ],
  },
  {
    key: "outer",
    label: "Outer Profile",
    image: "/static/images/outer-profile.png",
    imageAlt: "Outer profile diagram",
    params: [
      { key: "outerThickness",    label: "Thickness",            unit: "% of chord",         min: 3,   max: 24,  step: 1,    value: 6  },
      { key: "outerMaxPos",       label: "Max Position",         unit: "tenths of chord",    min: 2,   max: 8,   step: 1,    value: 4  },
      { key: "outerCamber",       label: "Camber",               unit: "% of chord",         min: 0,   max: 9,   step: 1,    value: 4  },
      { key: "outerChord",        label: "Chord Length",         unit: "mm",                 min: 10,  max: 30,  step: 1,    value: 15 },
      { key: "outerAngle",        label: "Angle of Attack",      unit: "degrees",            min: 2,   max: 25,  step: 1,    value: 10 },
    ],
  },
];

// Per-key live state.  Mirrors slider values in JS so we can read them
// at submit / copy time without re-querying the DOM.
const paramState = {};

// Lookup table {key -> spec} so formatters / submit-message builder
// can look up metadata without nested for-loops.
const paramSpecByKey = {};
for (const group of PARAM_GROUPS) {
  for (const p of group.params) paramSpecByKey[p.key] = p;
}

function paramsFormatValue(spec, value) {
  // Render with a precision matching the step (so 0.05-stepped sliders
  // don't render as "0.30000000000004").
  const decimals = spec.step < 1 ? 2 : 0;
  return Number(value).toFixed(decimals);
}

function paramsFormatValueWithUnit(spec, value) {
  const formatted = paramsFormatValue(spec, value);
  return spec.unit ? `${formatted} ${spec.unit}` : formatted;
}

// Per-key live state machine: "vary" (default) | "fixed" | "proposed".
// Keys are param keys.  Updated in lockstep with the DOM via
// paramsSetState() so JS callers (paramsSubmit, future propose_attempt
// handler) and CSS data-state attributes never drift apart.
const paramRowState = {};


// ---------------------------------------------------------------------------
// Live 3D preview pipeline — front-end geometry (FEG).
//
// On every slider input we rebuild the propeller IN THE BROWSER (three.js,
// web/feg/*) and show it in the params-view Viewer instance — no server
// round-trip.  The precise RhinoCompute geometry (RCG) is fetched only when
// the user clicks Download geometry (see paramsDownloadMesh).
//
// Rebuilds are coalesced with requestAnimationFrame so a fast drag rebuilds
// at most once per frame (the FEG geometry is small, so this feels instant).
// ---------------------------------------------------------------------------

let paramsFegRafId = null;          // pending rAF handle (null = none queued)

function paramsBuildPreviewBody() {
  // Snapshot the current 17-param values into a plain dict.  Reads
  // paramState (kept in sync by the slider input handler).  Used by both
  // the FEG build and the RCG download (/api/preview_mesh body).
  const out = {};
  for (const key of Object.keys(paramSpecByKey)) {
    out[key] = paramState[key];
  }
  return out;
}

function paramsRenderFEG() {
  // Build + show the FEG from the current paramState.  Synchronous —
  // delegates to Viewer.loadFromParams (web/feg/*).  No-op if the params
  // viewer isn't available.
  if (!window.paramsViewer || !window.paramsViewer.loadFromParams) return;
  const ok = window.paramsViewer.loadFromParams(paramsBuildPreviewBody(), "");
  if (!ok) return;
  // There is now a parameter set worth sending to RhinoCompute, so the
  // Download geometry (RCG) button becomes meaningful.
  const dlBtn = document.getElementById("params-download-mesh");
  if (dlBtn) dlBtn.disabled = false;
}

// Redraw the per-section 2D cross-section canvases (Inner/Middle/Outer) from
// the current paramState.  Independent of the 3D viewer — needs only
// window.fegDrawProfile2D (set by viewer.js) and the canvases.  Each tab
// shows only its own section, so all are drawn "active" (green), matching the
// 3D active outline.
function paramsRedrawSections() {
  if (!window.fegDrawProfile2D) return;
  const params = paramsBuildPreviewBody();
  document
    .querySelectorAll(".param-section-canvas[data-section]")
    .forEach((canvas) => {
      const kind = canvas.getAttribute("data-section");
      try {
        window.fegDrawProfile2D(canvas, kind, params, { active: true });
      } catch (e) {
        // Degenerate params can throw in the morph math; skip this canvas.
      }
    });
}

// Left-pane preview mode: "3d" (FEG WebGL) or "sections" (2D blade-sections).
let paramsViewMode = "3d";

// Redraw the Blade-sections 2D view (Inner/Middle/Outer airfoils on a 1mm
// grid + a corner angle-of-attack protractor) from the current paramState.
function paramsRedrawBladeSections() {
  const canvas = document.getElementById("params-sections-canvas");
  if (!canvas || !window.fegDrawBladeSections) return;
  window.fegDrawBladeSections(canvas, paramsBuildPreviewBody());
}

// Refresh the previews from the current paramState.  The left pane shows
// either the 3D FEG or the 2D blade-sections (whichever mode is active); the
// per-tab section cross-sections in the right column always redraw.
function paramsUpdatePreview() {
  if (paramsViewMode === "sections") {
    paramsRedrawBladeSections();
  } else {
    paramsRenderFEG();
  }
  paramsRedrawSections();
}

// Switch the left pane between the 3D FEG preview and the 2D Blade-sections
// view.  refresh=false only sets the UI/visibility (used by End-Session reset,
// which must NOT rebuild into the just-unloaded viewer).
function paramsSetViewMode(mode, { refresh = true } = {}) {
  paramsViewMode = mode === "sections" ? "sections" : "3d";
  const showSections = paramsViewMode === "sections";
  document.querySelectorAll(".params-viewmode-toggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.pmode === paramsViewMode);
  });
  const viewer3d = document.getElementById("params-viewer");
  const sections = document.getElementById("params-sections");
  const resetBtn = document.getElementById("params-viewer-reset");
  if (viewer3d) viewer3d.hidden = showSections;
  if (sections) sections.hidden = !showSections;
  if (resetBtn) resetBtn.disabled = showSections;   // Reset view is 3D-only
  if (!refresh) return;
  if (showSections) {
    paramsRedrawBladeSections();
  } else {
    // The WebGL canvas was display:none; re-measure for the now-visible
    // container, then rebuild (frame-once keeps the camera).
    if (window.paramsViewer && window.paramsViewer.resize) {
      window.paramsViewer.resize();
    }
    paramsRenderFEG();
  }
}

function paramsRequestFEG() {
  // Coalesce rapid slider input into at most one rebuild per frame.
  // paramsUpdatePreview() reads paramState fresh, so the frame always uses
  // the latest slider positions.
  if (paramsFegRafId !== null) return;
  paramsFegRafId = requestAnimationFrame(() => {
    paramsFegRafId = null;
    paramsUpdatePreview();
  });
}

async function paramsDownloadMesh() {
  // Download the PRECISE RhinoCompute geometry (RCG) for the current
  // parameter set.  Unlike the live preview (FEG, built in-browser), this
  // does a server round-trip to /api/preview_mesh — the same mesh the agent
  // pipeline would generate — and saves it as propeller.obj.  Fetch-on-click
  // with a brief "Generating…" status (the round-trip is ~1-2 s).
  const status = document.getElementById("params-status");
  const dlBtn = document.getElementById("params-download-mesh");
  if (status) {
    status.classList.remove("error");
    status.textContent = "Generating geometry…";
  }
  if (dlBtn) dlBtn.disabled = true;
  try {
    const res = await fetch("/api/preview_mesh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: paramsBuildPreviewBody() }),
    });
    if (res.status === 401) {
      showGate();
      return;
    }
    if (!res.ok) {
      let detail = "";
      try {
        const data = await res.json();
        detail = data.detail || JSON.stringify(data);
      } catch {
        detail = await res.text();
      }
      if (status) {
        status.classList.add("error");
        status.textContent =
          "Download failed (" + res.status + "): " + String(detail).slice(0, 200);
      }
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "propeller.obj";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    if (status) status.textContent = "Geometry downloaded.";
  } catch (e) {
    if (status) {
      status.classList.add("error");
      status.textContent =
        "Download network error: " + (e && e.message ? e.message : e);
    }
  } finally {
    if (dlBtn) dlBtn.disabled = false;
  }
}

function paramsSetState(key, newState) {
  // Idempotent.  Updates the row's data-state attribute (which CSS
  // hooks on to swap colours), updates the button label, and keeps
  // paramRowState in sync.  Slider VALUE is never touched here —
  // per locked decision §6.C, FIXED → VARY release preserves the
  // current slider position.
  const row = document.querySelector(`.param-row[data-param-key="${key}"]`);
  if (!row) return;
  paramRowState[key] = newState;
  row.dataset.state = newState;
  const btn = row.querySelector(".param-state-btn");
  if (btn) {
    if (newState === "fixed") btn.textContent = "FIXED";
    else if (newState === "proposed") btn.textContent = "PROPOSED";
    else btn.textContent = "VARY";
  }
}

function paramsBuildRow(spec) {
  paramState[spec.key] = spec.value;
  paramRowState[spec.key] = "vary";

  const row = document.createElement("div");
  row.className = "param-row";
  row.dataset.paramKey = spec.key;
  row.dataset.state = "vary";

  // LEFT: state button (VARY / FIXED).  Click toggles between the
  // two; the PROPOSED visual is system-driven (Step 10).
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "param-state-btn";
  btn.dataset.paramKey = spec.key;
  btn.textContent = "VARY";
  btn.title = "Click to FIX this parameter (or move the slider).";
  row.appendChild(btn);

  // RIGHT: label + slider + min/current/max values.
  const body = document.createElement("div");
  body.className = "param-body";

  const labelRow = document.createElement("div");
  labelRow.className = "param-label-row";
  const lbl = document.createElement("label");
  lbl.className = "param-label";
  lbl.setAttribute("for", `param-${spec.key}`);
  lbl.textContent = spec.label;
  labelRow.appendChild(lbl);
  // PROPOSED-VALUE text — populated by the SSE handler when the
  // Receptionist's propose_attempt tool fires (Step 10).  Hidden
  // until then via the .param-row[data-has-proposal="true"] CSS
  // rule.  Persists even after the user re-overrides the slider
  // (locked §6.F.C2) — the user always sees the system's latest
  // proposal as a reference point.
  const proposedSpan = document.createElement("span");
  proposedSpan.className = "param-proposed-text";
  proposedSpan.id = `param-proposed-${spec.key}`;
  labelRow.appendChild(proposedSpan);
  body.appendChild(labelRow);

  const range = document.createElement("input");
  range.type = "range";
  range.id = `param-${spec.key}`;
  range.className = "param-slider";
  range.dataset.paramKey = spec.key;
  range.min = String(spec.min);
  range.max = String(spec.max);
  range.step = String(spec.step);
  range.value = String(spec.value);
  body.appendChild(range);

  const valuesRow = document.createElement("div");
  valuesRow.className = "param-values";

  const minSpan = document.createElement("span");
  minSpan.className = "param-min";
  minSpan.textContent = spec.unit
    ? `min ${spec.min} ${spec.unit}`
    : `min ${spec.min}`;
  valuesRow.appendChild(minSpan);

  const curSpan = document.createElement("span");
  curSpan.className = "param-current";
  curSpan.id = `param-cur-${spec.key}`;
  curSpan.textContent = paramsFormatValueWithUnit(spec, spec.value);
  valuesRow.appendChild(curSpan);

  const maxSpan = document.createElement("span");
  maxSpan.className = "param-max";
  maxSpan.textContent = spec.unit
    ? `max ${spec.max} ${spec.unit}`
    : `max ${spec.max}`;
  valuesRow.appendChild(maxSpan);

  body.appendChild(valuesRow);
  row.appendChild(body);

  // Slider input: live-update visible value AND transition row to
  // FIXED (per locked design — moving a slider is the user's intent
  // signal that this value is now user-imposed).  The first input
  // event of a session takes the row from VARY → FIXED; subsequent
  // inputs while already FIXED just update the visible value.  Also
  // schedules a live FEG rebuild so the 3D viewer on the left
  // regenerates the propeller for the new parameter set.
  range.addEventListener("input", () => {
    const v = parseFloat(range.value);
    paramState[spec.key] = v;
    curSpan.textContent = paramsFormatValueWithUnit(spec, v);
    if (paramRowState[spec.key] !== "fixed") {
      paramsSetState(spec.key, "fixed");
    }
    paramsRequestFEG();
  });

  // Button click: toggle VARY ↔ FIXED.  Slider value is preserved
  // in both directions per §6.C.
  btn.addEventListener("click", () => {
    const cur = paramRowState[spec.key];
    // PROPOSED rows clicked also collapse to FIXED (the user is
    // taking ownership of the proposed value).  Same effect as the
    // user moving the slider to commit to the proposed value.
    if (cur === "fixed") {
      paramsSetState(spec.key, "vary");
    } else {
      paramsSetState(spec.key, "fixed");
    }
  });

  return row;
}

function paramsBuildSectionHeader(group) {
  // Per-pane header: a media row (parameter image + live 2D cross-section
  // for the airfoil sections) above the section title.
  const header = document.createElement("div");
  header.className = "param-section-header";

  const media = document.createElement("div");
  media.className = "param-section-media";

  const img = document.createElement("img");
  img.className = "param-section-img";
  img.src = group.image;
  img.alt = group.imageAlt;
  media.appendChild(img);

  // The three airfoil sections get a live 2D cross-section canvas alongside
  // the parameter image; General (ring/impeller params) gets the image only.
  const kind = group.key === "general" ? null : group.key;  // inner|middle|outer
  if (kind) {
    const canvas = document.createElement("canvas");
    canvas.className = "param-section-canvas";
    canvas.dataset.section = kind;
    canvas.width = 360;     // drawing buffer (CSS scales the display size)
    canvas.height = 180;
    media.appendChild(canvas);
    header.classList.add("has-canvas");
  }

  header.appendChild(media);

  const title = document.createElement("h3");
  title.className = "param-section-title";
  title.textContent = group.label;
  header.appendChild(title);

  return header;
}

function paramsBuildAll() {
  // One pane per group (4 total).  Each pane is its own DOM container
  // and gets the section image + slider rows for that group only.
  // The .active pane is toggled by paramsSwitchTab().
  for (const group of PARAM_GROUPS) {
    const pane = document.getElementById(`params-pane-${group.key}`);
    if (!pane) continue;
    pane.innerHTML = "";
    pane.appendChild(paramsBuildSectionHeader(group));
    for (const spec of group.params) {
      pane.appendChild(paramsBuildRow(spec));
    }
  }
}

// Maps a parameter tab to the FEG section outline highlighted green in the
// params viewer (general tab → none, so all three stay blue).  See
// Viewer.setActiveProfile().
const TAB_TO_PROFILE = {
  general: null,
  inner: "InnerProfile",
  middle: "MiddleProfile",
  outer: "OuterProfile",
};

function paramsSwitchTab(tabKey) {
  document.querySelectorAll(".params-tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.paramtab === tabKey);
  });
  document.querySelectorAll(".params-pane").forEach((p) => {
    p.classList.toggle("active", p.dataset.paramtab === tabKey);
  });
  // Recolour the matching 3D section outline green (instant; no rebuild).
  if (window.paramsViewer && window.paramsViewer.setActiveProfile) {
    window.paramsViewer.setActiveProfile(TAB_TO_PROFILE[tabKey] || null);
  }
}

function paramsBuildSubmitMessage() {
  // Long-form clipboard text — full 17-parameter list with units,
  // grouped by section.  Used by the Copy parameters button so the
  // clipboard payload is self-contained (no auto-append context
  // since clipboard ≠ chat).
  const lines = [
    "I want to generate a propeller with the following parameters:",
    "",
  ];
  for (const group of PARAM_GROUPS) {
    lines.push(`${group.label}:`);
    for (const p of group.params) {
      const v = paramsFormatValueWithUnit(p, paramState[p.key]);
      lines.push(`  - ${p.key}: ${v}`);
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}


// ---------------------------------------------------------------------------
// Step 8 — FIXED-block dispatch (see web_interface_notes.md §6.D).
// sendMessage() reads paramsDiffFixedForSend() to decide whether to
// include the user's FIXED parameter dict in the /api/turn body for
// this turn.  Backend (web_app.TurnIn + dispatch.save_user_input)
// appends a "The user has fixed the following values..." block to
// user_query.txt when fixed_params is present and non-empty.
// ---------------------------------------------------------------------------

let _lastSentFixedFingerprint = null;

function paramsBuildFixedParamsDict() {
  // Build the dict of FIXED parameters with values formatted as
  // display strings (e.g. "72 mm", "5 % of chord") — the backend
  // writes them verbatim into the FIXED block of user_query.txt,
  // so frontend formatting authority means no unit table is needed
  // in dispatch.py.
  const out = {};
  for (const group of PARAM_GROUPS) {
    for (const spec of group.params) {
      if (paramRowState[spec.key] === "fixed") {
        out[spec.key] = paramsFormatValueWithUnit(spec, paramState[spec.key]);
      }
    }
  }
  return out;
}

function _paramsFingerprintFixed(dict) {
  // Deterministic fingerprint independent of dict insertion order.
  const keys = Object.keys(dict).sort();
  return keys.map((k) => `${k}=${dict[k]}`).join("|");
}

// Snapshot of the FIXED dict at the time of the previous send.
// Needed (in addition to the fingerprint) so paramsDiffFixedForSend()
// can compute the SET of parameter keys released since then — the
// list goes into the "released_params" payload of /api/turn (Step 8
// follow-up after 2026-06-01 test feedback).
let _lastSentFixedDict = null;

function paramsDiffFixedForSend() {
  // Returns { fixed_params, released_params }:
  //   - fixed_params: the current FIXED dict when it has CHANGED
  //     since the previous send AND is non-empty; null otherwise.
  //   - released_params: list of param keys that WERE in the previous
  //     send's FIXED dict but are NOT in the current FIXED set;
  //     null when no releases happened.
  // Both fields together get included in the /api/turn body (Step 8)
  // so the backend appends the FIXED block AND the "no longer
  // constraining ..." block to user_query.txt.
  //
  // The dedup is by full fingerprint (names + values per §6.D.B1):
  // if neither set membership nor values changed, we send null/null.
  // Returns the same shape in both cases so callers don't have to
  // null-check the function result.
  const currentDict = paramsBuildFixedParamsDict();
  const currentFp = _paramsFingerprintFixed(currentDict);
  const changed = currentFp !== _lastSentFixedFingerprint;
  if (!changed) {
    return { fixed_params: null, released_params: null };
  }
  // Compute the released set: keys that were FIXED last send but
  // aren't FIXED now.  Includes the "lastSent was null" first-turn
  // case (no releases possible before any send).
  let released = null;
  if (_lastSentFixedDict) {
    const list = [];
    for (const key of Object.keys(_lastSentFixedDict)) {
      if (!(key in currentDict)) list.push(key);
    }
    if (list.length > 0) released = list;
  }
  // Update the snapshot regardless of whether fixed/released are
  // non-empty — the fingerprint changed, so next-send needs to
  // diff against THIS state.
  _lastSentFixedDict = { ...currentDict };
  _lastSentFixedFingerprint = currentFp;
  const fixed =
    Object.keys(currentDict).length > 0 ? currentDict : null;
  return { fixed_params: fixed, released_params: released };
}


// ---------------------------------------------------------------------------
// Step 10 — Apply a PROPOSED parameter set from the Receptionist's
// propose_attempt tool.  Called by the SSE handler when a
// params_proposed event arrives.
//
// Rules (web_interface_notes.md §§6.A.A2 / 6.A.A3 / 6.F.C2 / 6.F.C3):
//   - For each parameter in the proposed dict:
//       * Always update the "PROPOSED VALUE: X" text alongside the
//         label (even on FIXED rows — the user always sees the latest
//         proposal as a reference point, even after over-riding it).
//       * If the row's state is FIXED, do NOT touch its slider value.
//         The user's FIX wins (§6.F.C3).
//       * Otherwise (VARY or already PROPOSED): set state to
//         PROPOSED (orange), move the slider to the proposed value,
//         update paramState.
//   - The proposed-text persists.  Subsequent slider moves by the
//     user transition the row to FIXED (per the existing input
//     handler) but the proposed-text stays — provides the
//     "remember-what-was-proposed" affordance §6.F.C2 requires.
// ---------------------------------------------------------------------------

function paramsApplyProposal(values) {
  if (!values || typeof values !== "object") return;
  for (const key of Object.keys(values)) {
    const spec = paramSpecByKey[key];
    if (!spec) continue;       // unknown key — silently skip
    const proposedValue = Number(values[key]);
    if (Number.isNaN(proposedValue)) continue;

    // Always update the proposed-text (visible on every row that has
    // ever received a proposal, regardless of current state).
    const row = document.querySelector(
      `.param-row[data-param-key="${key}"]`
    );
    if (!row) continue;
    row.dataset.hasProposal = "true";
    const proposedSpan = document.getElementById(`param-proposed-${key}`);
    if (proposedSpan) {
      proposedSpan.textContent =
        "PROPOSED VALUE: " + paramsFormatValueWithUnit(spec, proposedValue);
    }

    // FIXED rows: keep slider value untouched (§6.F.C3).
    if (paramRowState[key] === "fixed") continue;

    // Otherwise: switch to PROPOSED state, move the slider, update
    // paramState + visible current value.
    const range = document.getElementById(`param-${key}`);
    const curSpan = document.getElementById(`param-cur-${key}`);
    if (range) {
      range.value = String(proposedValue);
    }
    paramState[key] = proposedValue;
    if (curSpan) {
      curSpan.textContent = paramsFormatValueWithUnit(spec, proposedValue);
    }
    paramsSetState(key, "proposed");
  }

  // Rebuild the FEG preview so it reflects the proposed propeller the user
  // is now looking at (non-FIXED sliders moved to their proposed values).
  paramsRequestFEG();
}

async function paramsSubmit() {
  // PERMANENT submit path (locked 2026-06-01).  Click semantics
  // (web_interface_notes.md §6.C):
  //   1. Transform ALL parameter rows to FIXED — including ones the
  //      user never touched.  This makes the user's intent explicit
  //      ("I am committing to ALL of these values, not just the ones
  //      I tweaked") and lines up with Step 8's auto-append flow.
  //   2. Switch to the Chat view and call sendMessage() with a SHORT
  //      message.  The actual parameter values reach the agents via
  //      the auto-appended FIXED block on user_query.txt (Step 8) —
  //      no need to inline the parameter list in the message body,
  //      which would duplicate the FIXED block.
  const status = document.getElementById("params-status");
  if (status) {
    status.classList.remove("error");
    status.textContent = "Submitting parameters to the chat pipeline…";
  }
  // Step 1: lock every row to FIXED (visible BEFORE the view switch
  // so the user sees the transformation).
  for (const key of Object.keys(paramState)) {
    paramsSetState(key, "fixed");
  }
  // Step 2: short prompt — the FIXED auto-append from Step 8 carries
  // the actual values into user_query.txt.
  const message =
    "I am committing to the parameter values shown in the Parameters " +
    "Inputs panel — please use them.";
  try {
    switchView("chat");
    if (typeof sendMessage === "function") {
      await sendMessage(message);
    } else {
      throw new Error("sendMessage() is not defined");
    }
    if (status) status.textContent = "Sent. Switched to the Chat view.";
  } catch (e) {
    if (status) {
      status.classList.add("error");
      status.textContent = "Submit failed: " + (e && e.message ? e.message : e);
    }
  }
}

async function paramsCopy() {
  const status = document.getElementById("params-status");
  const text = paramsBuildSubmitMessage();
  try {
    await navigator.clipboard.writeText(text);
    if (status) {
      status.classList.remove("error");
      status.textContent = "Parameters copied to clipboard.";
    }
  } catch (e) {
    if (status) {
      status.classList.add("error");
      status.textContent = "Copy failed: " + (e && e.message ? e.message : e);
    }
  }
}

// ---------------------------------------------------------------------------
// End-Session reset for the Parameters Inputs view.  Called from the
// chat-side End Session handler (app.js finalizeEndSession around
// line 309) so the panel starts the NEXT session clean: all-gray
// VARY at mid-of-range defaults, no PROPOSED text, no live-preview
// mesh, dedup snapshot cleared.  Without this, FIXED / PROPOSED
// state from the previous session would leak into the next one and
// the FIXED-dispatch dedup would suppress the first send's auto-
// append block.
// ---------------------------------------------------------------------------
function paramsResetAll() {
  // Walk PARAM_GROUPS rather than the DOM so the reset works even
  // when the params view hasn't been opened yet this page-load.
  for (const group of PARAM_GROUPS) {
    for (const spec of group.params) {
      paramState[spec.key] = spec.value;
      paramRowState[spec.key] = "vary";
      const row = document.querySelector(
        `.param-row[data-param-key="${spec.key}"]`
      );
      if (row) {
        row.dataset.state = "vary";
        delete row.dataset.hasProposal;
        const btn = row.querySelector(".param-state-btn");
        if (btn) btn.textContent = "VARY";
        const range = document.getElementById(`param-${spec.key}`);
        if (range) range.value = String(spec.value);
        const curSpan = document.getElementById(`param-cur-${spec.key}`);
        if (curSpan) {
          curSpan.textContent = paramsFormatValueWithUnit(spec, spec.value);
        }
        const proposedSpan = document.getElementById(
          `param-proposed-${spec.key}`
        );
        if (proposedSpan) proposedSpan.textContent = "";
      }
    }
  }
  // Reset FIXED-dispatch dedup snapshot so the next session's first
  // chat send doesn't inherit the previous session's fingerprint.
  // (An empty FIXED list comparing equal to a prior empty list would
  // cause the very first auto-append of the new session to be
  // dropped as a no-op.)
  _lastSentFixedDict = null;
  _lastSentFixedFingerprint = null;
  // Live-preview cleanup: cancel any pending FEG rebuild, unload the
  // params viewer, disable Download.  The default propeller re-builds
  // automatically the next time the user opens the Parameters Inputs view
  // (switchView → paramsRenderFEG).
  if (paramsFegRafId !== null) {
    cancelAnimationFrame(paramsFegRafId);
    paramsFegRafId = null;
  }
  if (window.paramsViewer && window.paramsViewer.unload) {
    window.paramsViewer.unload();
  }
  const paramsDlBtn = document.getElementById("params-download-mesh");
  if (paramsDlBtn) paramsDlBtn.disabled = true;
  // Reset the active tab to General so the next session starts there with
  // all section outlines blue.
  paramsSwitchTab("general");
  // Return the left pane to 3D mode (refresh:false — don't rebuild into the
  // just-unloaded viewer; the next view-open auto-builds).
  paramsSetViewMode("3d", { refresh: false });
  const status = document.getElementById("params-status");
  if (status) {
    status.classList.remove("error");
    status.textContent = "";
  }
}


function paramsInit() {
  paramsBuildAll();
  // Wire tab buttons.
  document.querySelectorAll(".params-tab-btn").forEach((b) => {
    b.addEventListener("click", () => paramsSwitchTab(b.dataset.paramtab));
  });
  const submitBtn = document.getElementById("params-submit");
  if (submitBtn) submitBtn.addEventListener("click", paramsSubmit);
  const copyBtn = document.getElementById("params-copy");
  if (copyBtn) copyBtn.addEventListener("click", paramsCopy);
  // Step 7: Download geometry button (mirrors the chat's
  // download-mesh handler around line 2670 — same anchor-click
  // pattern but sourced from the in-memory blob URL of the latest
  // preview).
  const dlBtn = document.getElementById("params-download-mesh");
  if (dlBtn) dlBtn.addEventListener("click", paramsDownloadMesh);
  // Wire the "3D view / Blade sections" left-pane toggle.
  document.querySelectorAll(".params-viewmode-toggle button").forEach((b) => {
    b.addEventListener("click", () => paramsSetViewMode(b.dataset.pmode));
  });
  // Refit the Blade-sections canvas when its pane resizes (fit-to-pane scale).
  const sectionsEl = document.getElementById("params-sections");
  if (sectionsEl && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => {
      if (paramsViewMode === "sections") paramsRedrawBladeSections();
    }).observe(sectionsEl);
  }
  // Default to General Parameters on first render.
  paramsSwitchTab("general");
}

paramsInit();


// ---------------------------------------------------------------------------
// Database view — password-gated developer console
// (POST /api/db_admin/auth + POST /api/db_admin/reset)
// ---------------------------------------------------------------------------
//
// State machine:
//   * Locked   — password input + Unlock button.
//   * Unlocked — reset-phrase input + Send + Lock again.
//   * After a successful reset → re-lock automatically after 4s so a
//     subsequent destructive action requires re-authentication.
//
// The password is held in dbPassword (module-local) ONLY.  We never
// stash it in localStorage / sessionStorage — refreshing the page
// requires re-entering it.  Switching to any other view + back also
// re-locks (see the "database" branch of switchView above).

let dbPassword = "";

const dbLocked       = $("db-locked");
const dbUnlocked     = $("db-unlocked");
const dbPasswordIn   = $("db-password");
const dbUnlockBtn    = $("db-unlock");
const dbLockedStat   = $("db-locked-status");
const dbResetPhrase  = $("db-reset-phrase");
const dbResetSendBtn = $("db-reset-send");
const dbUnlockedStat = $("db-unlocked-status");
const dbRelockBtn    = $("db-relock");

// State 2c — clear previous_sessions folder (blue card, sits beside
// the red reset card inside .db-action-row).  Same dbPassword unlock
// as the red card.
const dbClearCard    = $("db-clear-sessions");
const dbClearPhrase  = $("db-clear-phrase");
const dbClearSendBtn = $("db-clear-send");
const dbClearStat    = $("db-clear-status");


function _dbSetStatus(el, text, kind) {
  if (!el) return;
  el.textContent = text || "";
  el.classList.remove("error", "success");
  if (kind === "error")   el.classList.add("error");
  if (kind === "success") el.classList.add("success");
}


function resetDbView() {
  if (!dbLocked || !dbUnlocked) return;
  dbPassword = "";
  if (dbPasswordIn)  dbPasswordIn.value  = "";
  if (dbResetPhrase) dbResetPhrase.value = "";
  if (dbClearPhrase) dbClearPhrase.value = "";
  _dbSetStatus(dbLockedStat,   "");
  _dbSetStatus(dbUnlockedStat, "");
  _dbSetStatus(dbClearStat,    "");
  dbLocked.hidden   = false;
  dbUnlocked.hidden = true;
  if (dbClearCard) dbClearCard.hidden = true;
  // Hide + clear the ignore-list card too (re-revealed on next unlock).
  const ignoreCard = $("db-ignore-card");
  if (ignoreCard) ignoreCard.hidden = true;
  dbIgnoreState = [];
  _dbSetStatus($("db-ignore-status"), "");
}


async function dbUnlock() {
  if (!dbPasswordIn) return;
  const pw = dbPasswordIn.value;
  if (!pw) {
    _dbSetStatus(dbLockedStat, "Please enter a password.", "error");
    return;
  }
  _dbSetStatus(dbLockedStat, "Checking…");
  if (dbUnlockBtn) dbUnlockBtn.disabled = true;
  try {
    const res = await fetch("/api/db_admin/auth", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ password: pw }),
    });
    const body = await res.json().catch(() => ({}));
    if (body.ok) {
      dbPassword = pw;
      dbLocked.hidden   = true;
      dbUnlocked.hidden = false;
      // Reveal the blue clear_previous_sessions card alongside the red one.
      if (dbClearCard) dbClearCard.hidden = false;
      _dbSetStatus(dbUnlockedStat, "");
      _dbSetStatus(dbClearStat,    "");
      // Reveal the session-ignore-list card too and load its current state.
      const ignoreCard = $("db-ignore-card");
      if (ignoreCard) ignoreCard.hidden = false;
      loadDbIgnoreList();
      setTimeout(() => { if (dbResetPhrase) dbResetPhrase.focus(); }, 0);
    } else {
      _dbSetStatus(dbLockedStat,
        body.error || "Password rejected.", "error");
    }
  } catch (e) {
    _dbSetStatus(dbLockedStat,
      "Network error contacting the server.", "error");
  } finally {
    if (dbUnlockBtn) dbUnlockBtn.disabled = false;
  }
}


async function dbResetSend() {
  if (!dbResetPhrase) return;
  const phrase = dbResetPhrase.value;
  if (phrase !== "reset_database") {
    _dbSetStatus(dbUnlockedStat,
      "Phrase must be exactly \"reset_database\".  Nothing was deleted.",
      "error");
    return;
  }
  if (!window.confirm(
        "This will TRUNCATE every data table except " +
        "dc_parameter_schemas.  This action is IRREVERSIBLE.  " +
        "Continue?")) {
    _dbSetStatus(dbUnlockedStat, "Cancelled.");
    return;
  }
  _dbSetStatus(dbUnlockedStat, "Sending…");
  if (dbResetSendBtn) dbResetSendBtn.disabled = true;
  try {
    const res = await fetch("/api/db_admin/reset", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ password: dbPassword, phrase }),
    });
    const body = await res.json().catch(() => ({}));
    if (body.ok) {
      const counts = Object.entries(body.before_counts || {})
        .map(([k, v]) => `${k}=${v}`)
        .join(", ");
      _dbSetStatus(dbUnlockedStat,
        "Database reset successfully.  Deleted: " + counts +
        ".  Re-locking in 4 s…",
        "success");
      setTimeout(resetDbView, 4000);
    } else {
      _dbSetStatus(dbUnlockedStat,
        body.error || "Reset failed.", "error");
    }
  } catch (e) {
    _dbSetStatus(dbUnlockedStat,
      "Network error contacting the server.", "error");
  } finally {
    if (dbResetSendBtn) dbResetSendBtn.disabled = false;
  }
}


async function dbClearSend() {
  if (!dbClearPhrase) return;
  const phrase = dbClearPhrase.value;
  if (phrase !== "clear_previous_sessions") {
    _dbSetStatus(dbClearStat,
      "Phrase must be exactly \"clear_previous_sessions\".  Nothing was deleted.",
      "error");
    return;
  }
  if (!window.confirm(
        "This will permanently delete every subdirectory inside " +
        "previous_sessions/ on the current container.  The R2 archive " +
        "and the Postgres database are NOT affected.  This action is " +
        "IRREVERSIBLE on the local volume.  Continue?")) {
    _dbSetStatus(dbClearStat, "Cancelled.");
    return;
  }
  _dbSetStatus(dbClearStat, "Sending…");
  if (dbClearSendBtn) dbClearSendBtn.disabled = true;
  try {
    const res = await fetch("/api/db_admin/clear_previous_sessions", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ password: dbPassword, phrase }),
    });
    const body = await res.json().catch(() => ({}));
    if (body.ok) {
      const n     = body.entries_removed;
      const bytes = body.bytes_freed;
      const summary = (n != null && bytes != null)
        ? `Removed ${n} entr${n === 1 ? "y" : "ies"}, freed ${bytes} byte(s).`
        : "previous_sessions/ cleared.";
      const note = body.note ? "  " + body.note : "";
      _dbSetStatus(dbClearStat,
        summary + note + "  Re-locking in 4 s…",
        "success");
      setTimeout(resetDbView, 4000);
    } else {
      _dbSetStatus(dbClearStat,
        body.error || "Clear failed.", "error");
    }
  } catch (e) {
    _dbSetStatus(dbClearStat,
      "Network error contacting the server.", "error");
  } finally {
    if (dbClearSendBtn) dbClearSendBtn.disabled = false;
  }
}


if (dbUnlockBtn)   dbUnlockBtn.addEventListener("click", dbUnlock);
if (dbResetSendBtn) dbResetSendBtn.addEventListener("click", dbResetSend);
if (dbClearSendBtn) dbClearSendBtn.addEventListener("click", dbClearSend);
if (dbRelockBtn)   dbRelockBtn.addEventListener("click", resetDbView);

if (dbPasswordIn) dbPasswordIn.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); dbUnlock(); }
});
if (dbResetPhrase) dbResetPhrase.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); dbResetSend(); }
});
if (dbClearPhrase) dbClearPhrase.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); dbClearSend(); }
});


// ---------------------------------------------------------------------------
// Database admin — session ignore list editor (co-resides with the
// reset card in State 2 of the database view).  Backed by
// POST /api/db_admin/ignore_list/{read,write}.  Uses dbPassword (the
// same in-memory password that the rest of the db_admin endpoints
// use).
// ---------------------------------------------------------------------------

const _SESSION_ID_RE = /^ID\d+_\d{8}_\d{6}$/;

// In-memory mirror of the persisted ignore list (string[]).  Loaded
// from /api/db_admin/ignore_list/read on unlock; mutated by add /
// remove; flushed back to the server by Save.
let dbIgnoreState = [];


async function loadDbIgnoreList() {
  const statusEl = $("db-ignore-status");
  _dbSetStatus(statusEl, "Loading…");
  try {
    const res = await fetch("/api/db_admin/ignore_list/read", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ password: dbPassword }),
    });
    const body = await res.json().catch(() => ({}));
    if (body.ok) {
      dbIgnoreState = Array.isArray(body.sessions) ? body.sessions.slice() : [];
      renderDbIgnoreList();
      _dbSetStatus(statusEl,
        `Loaded ${dbIgnoreState.length} session(s).`, "success");
    } else {
      _dbSetStatus(statusEl,
        body.error || "Could not load ignore list.", "error");
    }
  } catch (e) {
    _dbSetStatus(statusEl,
      "Network error contacting the server.", "error");
  }
}


function renderDbIgnoreList() {
  const ul = $("db-ignore-list");
  if (!ul) return;
  ul.innerHTML = "";
  if (!dbIgnoreState.length) {
    const li = document.createElement("li");
    li.className = "db-ignore-empty";
    li.innerHTML = "<em>(empty — no sessions ignored)</em>";
    ul.appendChild(li);
    return;
  }
  for (const sid of dbIgnoreState) {
    const li = document.createElement("li");
    li.className = "db-ignore-row";
    const code = document.createElement("code");
    code.textContent = sid;
    const del = document.createElement("button");
    del.type = "button";
    del.className = "ghost db-ignore-del";
    del.textContent = "Remove";
    del.addEventListener("click", () => removeDbIgnoreId(sid));
    li.appendChild(code);
    li.appendChild(del);
    ul.appendChild(li);
  }
}


function addDbIgnoreId() {
  const inp = $("db-ignore-input");
  const statusEl = $("db-ignore-status");
  if (!inp) return;
  const raw = (inp.value || "").trim();
  if (!raw) {
    _dbSetStatus(statusEl, "Enter a session_id first.", "error");
    return;
  }
  if (!_SESSION_ID_RE.test(raw)) {
    _dbSetStatus(statusEl,
      `"${raw}" does not match ^ID\\d+_\\d{8}_\\d{6}$ — example: ID042_20260602_140000.`,
      "error");
    return;
  }
  if (dbIgnoreState.includes(raw)) {
    _dbSetStatus(statusEl, `${raw} is already on the list.`, "error");
    return;
  }
  dbIgnoreState.push(raw);
  dbIgnoreState.sort();
  renderDbIgnoreList();
  inp.value = "";
  _dbSetStatus(statusEl,
    `Added ${raw}.  Click Save to persist.`, "success");
}


function removeDbIgnoreId(sid) {
  const statusEl = $("db-ignore-status");
  const idx = dbIgnoreState.indexOf(sid);
  if (idx < 0) return;
  dbIgnoreState.splice(idx, 1);
  renderDbIgnoreList();
  _dbSetStatus(statusEl,
    `Removed ${sid}.  Click Save to persist.`, "success");
}


async function saveDbIgnoreList() {
  const statusEl = $("db-ignore-status");
  const saveBtn = $("db-ignore-save");
  if (saveBtn) saveBtn.disabled = true;
  _dbSetStatus(statusEl, "Saving…");
  try {
    const res = await fetch("/api/db_admin/ignore_list/write", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        password: dbPassword,
        sessions: dbIgnoreState,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (body.ok) {
      dbIgnoreState = Array.isArray(body.sessions)
        ? body.sessions.slice() : [];
      renderDbIgnoreList();
      _dbSetStatus(statusEl,
        `Saved.  ${dbIgnoreState.length} session(s) on the ignore list.`,
        "success");
    } else {
      _dbSetStatus(statusEl,
        body.error || "Save failed.", "error");
    }
  } catch (e) {
    _dbSetStatus(statusEl,
      "Network error contacting the server.", "error");
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}


const dbIgnoreAddBtn    = $("db-ignore-add");
const dbIgnoreSaveBtn   = $("db-ignore-save");
const dbIgnoreReloadBtn = $("db-ignore-reload");
const dbIgnoreInput     = $("db-ignore-input");

if (dbIgnoreAddBtn)    dbIgnoreAddBtn.addEventListener("click", addDbIgnoreId);
if (dbIgnoreSaveBtn)   dbIgnoreSaveBtn.addEventListener("click", saveDbIgnoreList);
if (dbIgnoreReloadBtn) dbIgnoreReloadBtn.addEventListener("click", loadDbIgnoreList);
if (dbIgnoreInput) dbIgnoreInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); addDbIgnoreId(); }
});


// ===========================================================
// System Prompts editor — read / write the .md fragment sources
// =============================================================

const promptsState = {
  groups:         [],
  buffers:        {},          // {path: {original, current, hasMarkers}}
  selected:       null,
  password:       null,
  knownSlots:     new Set(),
  markerPairs:    [],
  runtimeSlots:   {},
  loaded:         false,
  sessionLocked:  false,
};

const promptsRoot              = document.querySelector(".prompts-view");
const promptsLockBanner        = $("prompts-lock-banner");
const promptsSearch            = $("prompts-search");
const promptsTree              = $("prompts-tree");
const promptsEditorHeader      = $("prompts-editor-header");
const promptsEditorPath        = $("prompts-editor-path");
const promptsEditorUsedby      = $("prompts-editor-usedby");
const promptsEditorFlags       = $("prompts-editor-flags");
const promptsEditorContainer   = $("prompts-editor-container");
const promptsEditorOverlay     = $("prompts-editor-overlay");
const promptsEditor            = $("prompts-editor");
const promptsEditorPlaceholder = $("prompts-editor-placeholder");
const promptsSave              = $("prompts-save");
const promptsDiscard           = $("prompts-discard");
const promptsAuthRow           = $("prompts-auth-row");
const promptsPassword          = $("prompts-password");
const promptsUnlock            = $("prompts-unlock");
const promptsAuthCancel        = $("prompts-auth-cancel");
const promptsStatus            = $("prompts-status");
const promptsWarningModal      = $("prompts-warning-modal");
const promptsWarningList       = $("prompts-warning-list");
const promptsWarningSave       = $("prompts-warning-save");
const promptsWarningCancel     = $("prompts-warning-cancel");
const promptsDiscardModal      = $("prompts-discard-modal");
const promptsDiscardCount      = $("prompts-discard-count");
const promptsDiscardConfirm    = $("prompts-discard-confirm");
const promptsDiscardCancel     = $("prompts-discard-cancel");

// ----- Helpers --------------------------------------------------

function promptsEscapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
}

function promptsCountSubstring(haystack, needle) {
  if (!needle) return 0;
  let n = 0, i = 0;
  while ((i = haystack.indexOf(needle, i)) !== -1) { n++; i += needle.length; }
  return n;
}

function promptsDirtyEntries() {
  return Object.entries(promptsState.buffers)
    .filter(([, b]) => b.current !== b.original);
}

function promptsDirtyCount() { return promptsDirtyEntries().length; }

function promptsDirtyFiles() {
  return promptsDirtyEntries().map(([path, b]) => ({ path, content: b.current }));
}

function promptsDiscardAllBuffers() {
  for (const [path, buf] of Object.entries(promptsState.buffers)) {
    if (buf.current !== buf.original) {
      buf.current = buf.original;
      promptsMarkFileDirty(path, false);
    }
  }
  // Refresh editor if a dirty file is currently visible
  if (promptsState.selected) {
    const buf = promptsState.buffers[promptsState.selected];
    if (buf) {
      promptsEditor.value = buf.current;
      promptsUpdateOverlay(buf);
    }
  }
  promptsRefreshActionButtons();
}

function promptsSetStatus(msg, kind) {
  if (!promptsStatus) return;
  promptsStatus.textContent = msg;
  promptsStatus.classList.remove("ok", "err");
  if (kind === "ok")  promptsStatus.classList.add("ok");
  if (kind === "err") promptsStatus.classList.add("err");
}

function promptsApplyLockState() {
  if (!promptsRoot || !promptsLockBanner) return;
  promptsLockBanner.hidden = !promptsState.sessionLocked;
  promptsRoot.classList.toggle("locked", promptsState.sessionLocked);
  promptsRefreshActionButtons();
}

function promptsRefreshActionButtons() {
  const anyDirty = promptsDirtyCount() > 0;
  const locked   = promptsState.sessionLocked;
  if (promptsSave)    promptsSave.disabled    = !anyDirty || locked;
  if (promptsDiscard) promptsDiscard.disabled = !anyDirty || locked;
}

// ----- Tree load & render ---------------------------------------

async function loadPromptsTree() {
  if (!promptsTree) return;
  try {
    const res = await fetch("/api/prompts/tree");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    promptsState.groups        = body.groups || [];
    promptsState.sessionLocked = !!body.session_locked;
    promptsState.knownSlots    = new Set(body.known_slots || []);
    promptsState.markerPairs   = body.marker_pairs || [];
    promptsState.runtimeSlots  = body.runtime_slots || {};
    promptsState.loaded        = true;
    promptsApplyLockState();
    promptsRenderTree();
  } catch (e) {
    promptsTree.innerHTML =
      `<p class="prompts-tree-loading">Failed to load: ` +
      `${promptsEscapeHtml(e.message)}</p>`;
  }
}

function promptsRenderTree() {
  promptsTree.innerHTML = "";
  for (const group of promptsState.groups) {
    promptsTree.appendChild(promptsRenderGroup(group));
  }
  promptsApplySearchFilter();
  promptsHighlightSelected();
}

function promptsMakeDisclosure(children) {
  const wrap = document.createElement("span");
  wrap.className = "prompts-tree-disclosure";
  wrap.textContent = "▸";
  const handler = () => {
    const collapsed = !children.hidden;
    children.hidden = collapsed;
    wrap.textContent = collapsed ? "▸" : "▾";
  };
  return { wrap, handler };
}

function promptsRenderGroup(group) {
  const root = document.createElement("div");
  root.className = "prompts-tree-group";
  root.dataset.groupId = group.id;

  const children = document.createElement("div");
  children.className = "prompts-tree-group-children";
  children.hidden = true;
  for (const child of group.children) children.appendChild(promptsRenderNode(child));

  const { wrap: disc, handler } = promptsMakeDisclosure(children);
  const header = document.createElement("div");
  header.className = "prompts-tree-group-header";
  header.appendChild(disc);
  const label = document.createElement("span");
  label.className = "prompts-tree-group-label";
  label.textContent = group.label;
  header.appendChild(label);
  header.addEventListener("click", handler);

  const subtitle = document.createElement("div");
  subtitle.className = "prompts-tree-group-subtitle";
  subtitle.textContent = group.path_subtitle || "";

  root.appendChild(header);
  root.appendChild(subtitle);
  root.appendChild(children);
  return root;
}

function promptsRenderNode(node) {
  if (node.kind === "folder") return promptsRenderFolder(node);
  if (node.kind === "file")   return promptsRenderFile(node);
  return document.createElement("span");
}

function promptsRenderFolder(folder) {
  const root = document.createElement("div");
  root.className = "prompts-tree-folder";

  const children = document.createElement("div");
  children.className = "prompts-tree-folder-children";
  children.hidden = true;
  for (const child of folder.children) children.appendChild(promptsRenderNode(child));

  const { wrap: disc, handler } = promptsMakeDisclosure(children);
  const header = document.createElement("div");
  header.className = "prompts-tree-folder-header";
  header.appendChild(disc);
  const name = document.createElement("span");
  name.textContent = folder.display;
  header.appendChild(name);
  header.addEventListener("click", handler);

  root.appendChild(header);
  root.appendChild(children);
  return root;
}

function promptsRenderFile(file) {
  const root = document.createElement("div");
  root.className = "prompts-tree-file";
  root.dataset.path = file.path;
  root.dataset.display = file.display;
  root.dataset.usedBy  = JSON.stringify(file.used_by || []);

  const dirty = document.createElement("span");
  dirty.className = "prompts-tree-file-dirty";
  dirty.textContent = "";
  const name = document.createElement("span");
  name.className = "prompts-tree-file-name";
  name.textContent = file.display;
  root.appendChild(dirty);
  root.appendChild(name);

  if (file.used_by && file.used_by.length) {
    const badge = document.createElement("span");
    badge.className = "prompts-tree-file-badge";
    badge.textContent = `· ${file.used_by.length}`;
    badge.title = `used by: ${file.used_by.join(", ")}`;
    root.appendChild(badge);
  }

  root.addEventListener("click", () => promptsSelectFile(file.path));
  return root;
}

function promptsFindFileNode(path) {
  // Plain attribute selector — our paths only contain `/`, dots,
  // letters, digits, underscores, all safe in CSS attribute values.
  return promptsTree.querySelector(`[data-path="${path}"]`);
}

function promptsMarkFileDirty(path, dirty) {
  const node = promptsFindFileNode(path);
  if (!node) return;
  const marker = node.querySelector(".prompts-tree-file-dirty");
  if (marker) marker.textContent = dirty ? "*" : "";
}

function promptsHighlightSelected() {
  promptsTree.querySelectorAll(".prompts-tree-file").forEach((el) => {
    el.classList.toggle("selected", el.dataset.path === promptsState.selected);
  });
}

// ----- Search filter --------------------------------------------

function promptsApplySearchFilter() {
  const q = (promptsSearch?.value || "").toLowerCase().trim();
  promptsTree.querySelectorAll(".prompts-tree-file").forEach((el) => {
    const name = (el.dataset.display || "").toLowerCase();
    el.dataset.filtered = !q || name.includes(q) ? "" : "hidden";
  });
  promptsTree.querySelectorAll(".prompts-tree-folder").forEach((el) => {
    const anyVisible = Array.from(el.querySelectorAll(".prompts-tree-file"))
      .some((f) => f.dataset.filtered !== "hidden");
    el.dataset.filtered = !q || anyVisible ? "" : "hidden";
  });
  promptsTree.querySelectorAll(".prompts-tree-group").forEach((el) => {
    const anyVisible = Array.from(el.querySelectorAll(".prompts-tree-file"))
      .some((f) => f.dataset.filtered !== "hidden");
    el.dataset.filtered = !q || anyVisible ? "" : "hidden";
  });
}

// ----- File select / show ---------------------------------------

async function promptsSelectFile(path) {
  if (promptsState.selected === path && promptsState.buffers[path]) return;
  promptsState.selected = path;
  promptsHighlightSelected();

  let buf = promptsState.buffers[path];
  if (!buf) {
    try {
      const res = await fetch(`/api/prompts/file?path=${encodeURIComponent(path)}`);
      if (!res.ok) {
        const detail = (await res.json().catch(() => null))?.detail || res.statusText;
        promptsSetStatus(`Failed to load ${path}: ${detail}`, "err");
        return;
      }
      const body = await res.json();
      buf = {
        original:   body.content,
        current:    body.content,
        hasMarkers: !!body.has_conditional_regions,
      };
      promptsState.buffers[path] = buf;
    } catch (e) {
      promptsSetStatus(`Network error: ${e.message}`, "err");
      return;
    }
  }
  promptsShowFileInEditor(path, buf);
}

function promptsShowFileInEditor(path, buf) {
  promptsEditorPlaceholder.hidden = true;
  promptsEditorContainer.hidden   = false;
  promptsEditorHeader.hidden      = false;

  promptsEditorPath.textContent = path;
  const node = promptsFindFileNode(path);
  const usedBy = node ? JSON.parse(node.dataset.usedBy || "[]") : [];
  promptsEditorUsedby.textContent = usedBy.length
    ? `Used by: ${usedBy.join(", ")}`
    : "Used by: (doc / README — not consumed by any agent)";

  if (buf.hasMarkers) {
    promptsEditorFlags.hidden = false;
    promptsEditorFlags.textContent =
      "Contains <<…>> conditional regions — resolved per current "
      + "PLANNER_FIRST / DC_INSPECTOR_ENABLED / RAG_ENABLED + per-agent "
      + "DBa flags (see Workflow Settings + Database views).";
  } else {
    promptsEditorFlags.hidden = true;
    promptsEditorFlags.textContent = "";
  }

  promptsEditor.value = buf.current;
  promptsUpdateOverlay(buf);
  promptsEditor.scrollTop = 0;
  promptsEditorOverlay.scrollTop = 0;
}

function promptsUpdateOverlay(buf) {
  if (!buf.hasMarkers) {
    promptsEditorOverlay.innerHTML = "";
    promptsEditor.style.color = "var(--fg)";
    return;
  }
  promptsEditor.style.color = "transparent";
  promptsEditorOverlay.innerHTML = promptsRenderOverlay(buf.current);
}

function promptsRegexEscape(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function promptsRenderOverlay(content) {
  let html = promptsEscapeHtml(content);
  for (const [open_, close_] of promptsState.markerPairs) {
    const re = new RegExp(
      promptsRegexEscape(promptsEscapeHtml(open_))
      + "([\\s\\S]*?)"
      + promptsRegexEscape(promptsEscapeHtml(close_)),
      "g"
    );
    html = html.replace(re, (full) =>
      `<span class="prompts-cond-region">${full}</span>`);
  }
  // Trailing newline so a final `\n` in the textarea doesn't get
  // clipped by the overlay's last line.
  return html + "\n";
}

// ----- Editor input / scroll ------------------------------------

function promptsOnEditorInput() {
  const path = promptsState.selected;
  if (!path) return;
  const buf = promptsState.buffers[path];
  if (!buf) return;
  buf.current = promptsEditor.value;
  if (buf.hasMarkers) promptsUpdateOverlay(buf);
  promptsMarkFileDirty(path, buf.current !== buf.original);
  promptsRefreshActionButtons();
}

function promptsOnEditorScroll() {
  promptsEditorOverlay.scrollTop  = promptsEditor.scrollTop;
  promptsEditorOverlay.scrollLeft = promptsEditor.scrollLeft;
}

// ----- Client-side validation (mirrors prompts_admin.validate_one) -----

function promptsValidateAll(files) {
  const out = [];
  for (const f of files) out.push(...promptsValidateOne(f.path, f.content));
  return out;
}

function promptsValidateOne(path, content) {
  const out = [];
  const lines = content.split("\n");

  // Rule (a) — unknown $slot
  for (let i = 0; i < lines.length; i++) {
    const re = /\$([a-z_][a-z0-9_]*)/g;
    let m;
    while ((m = re.exec(lines[i])) !== null) {
      const name = m[1];
      if (!promptsState.knownSlots.has(name)
          && name !== "database_search_per_agent") {
        out.push({
          path, line: i + 1, kind: "unknown_slot",
          detail: `$${name} — not in known $-slot list.`,
        });
      }
    }
  }

  // Rule (b) — unbalanced <<…>> markers
  for (const [open_, close_] of promptsState.markerPairs) {
    const nOpen  = promptsCountSubstring(content, open_);
    const nClose = promptsCountSubstring(content, close_);
    if (nOpen !== nClose) {
      let row = 1;
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes(open_) || lines[i].includes(close_)) {
          row = i + 1; break;
        }
      }
      out.push({
        path, line: row, kind: "unbalanced_marker",
        detail: `${open_} opens=${nOpen}, closes=${nClose} — region mismatch will swallow content.`,
      });
    }
  }

  // Rule (c) — unescaped {x} in a prompt.md
  const agentMatch = path.match(/^agents\/([^/]+)\/prompt\.md$/);
  if (agentMatch) {
    const agent   = agentMatch[1];
    const allowed = new Set(promptsState.runtimeSlots[agent] || []);
    const braceRe = /(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})/g;
    for (let i = 0; i < lines.length; i++) {
      let m;
      braceRe.lastIndex = 0;
      while ((m = braceRe.exec(lines[i])) !== null) {
        const name = m[1];
        if (!allowed.has(name)) {
          const list = Array.from(allowed).sort().join(", ") || "(none)";
          out.push({
            path, line: i + 1, kind: "brace_escape",
            detail: `{${name}} would crash .format() at runtime.  Allowed for ${agent}: ${list}.`,
          });
        }
      }
    }
  }

  // Empty file
  if (!content.trim()) {
    out.push({
      path, line: 1, kind: "empty_file",
      detail: "File is empty after edits.",
    });
  }
  return out;
}

// ----- Save flow ------------------------------------------------

let promptsPendingSave = null;   // callback held while warning modal is open

async function promptsSaveClicked() {
  const files = promptsDirtyFiles();
  if (!files.length) { promptsSetStatus("Nothing to save.", "ok"); return; }
  const warnings = promptsValidateAll(files);
  if (warnings.length) {
    promptsShowWarningModal(warnings, () => promptsActuallySave(files));
    return;
  }
  await promptsActuallySave(files);
}

async function promptsActuallySave(files) {
  if (!promptsState.password) {
    promptsAuthRow.hidden = false;
    promptsPassword.focus();
    return;
  }
  promptsSetStatus("Saving…", "");
  try {
    const res = await fetch("/api/prompts/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: promptsState.password, files }),
    });
    if (res.status === 401) {
      promptsState.password = null;
      promptsSetStatus("Password rejected.  Re-enter and try again.", "err");
      promptsAuthRow.hidden = false;
      promptsPassword.focus();
      return;
    }
    if (res.status === 409) {
      promptsSetStatus(
        "Save rejected — a session is active.  End the session and try again.",
        "err");
      return;
    }
    if (!res.ok) {
      const detail = (await res.json().catch(() => null))?.detail || res.statusText;
      promptsSetStatus(`Save failed: ${detail}`, "err");
      return;
    }
    const body = await res.json();
    for (const entry of body.files_written || []) {
      const buf = promptsState.buffers[entry.path];
      if (buf) buf.original = buf.current;
      promptsMarkFileDirty(entry.path, false);
    }
    promptsRefreshActionButtons();
    promptsSetStatus(promptsFormatSaveStatus(body), "ok");
  } catch (e) {
    promptsSetStatus(`Network error: ${e.message}`, "err");
  }
}

function promptsFormatSaveStatus(body) {
  const written  = body.files_written || [];
  const warnings = body.warnings || [];
  const affected = new Set();
  for (const w of written) (w.affected_agents || []).forEach((a) => affected.add(a));
  const lines = [];
  lines.push(`Saved ${written.length} file(s).`);
  for (const w of written) {
    const ag = (w.affected_agents || []);
    lines.push(`  ${w.path}  →  ${ag.length ? ag.join(", ") : "(doc only — no live consumer)"}`);
  }
  if (affected.size) {
    lines.push(
      `${affected.size} agent(s) will rebuild fresh on next session: `
      + Array.from(affected).sort().join(", "));
  }
  if (warnings.length) {
    lines.push(`${warnings.length} warning(s):`);
    for (const w of warnings) {
      lines.push(`  • [${w.kind}] ${w.path}:${w.line} — ${w.detail}`);
    }
  }
  return lines.join("\n");
}

// ----- Inline auth row ------------------------------------------

async function promptsOnUnlock() {
  const pwd = promptsPassword.value;
  if (!pwd) return;
  promptsState.password = pwd;
  promptsAuthRow.hidden = true;
  promptsPassword.value = "";
  const files = promptsDirtyFiles();
  if (!files.length) return;
  const warnings = promptsValidateAll(files);
  if (warnings.length) {
    promptsShowWarningModal(warnings, () => promptsActuallySave(files));
  } else {
    promptsActuallySave(files);
  }
}

function promptsOnAuthCancel() {
  promptsAuthRow.hidden = true;
  promptsPassword.value = "";
}

// ----- Discard modal --------------------------------------------

function promptsDiscardClicked() {
  const n = promptsDirtyCount();
  if (!n) return;
  promptsDiscardCount.innerHTML =
    `Discard <strong>${n}</strong> unsaved file(s)?  This cannot be undone.`;
  promptsDiscardModal.hidden = false;
}

function promptsDiscardConfirmed() {
  promptsDiscardAllBuffers();
  promptsDiscardModal.hidden = true;
  promptsSetStatus("Discarded all unsaved changes.", "ok");
}

// ----- Warning modal --------------------------------------------

function promptsShowWarningModal(warnings, onContinue) {
  promptsWarningList.innerHTML = "";
  for (const w of warnings) {
    const li = document.createElement("li");
    const kind  = document.createElement("span");
    kind.className = "pw-kind";
    kind.textContent = w.kind;
    const path  = document.createElement("span");
    path.className = "pw-path";
    path.textContent = w.path;
    const line  = document.createElement("span");
    line.className = "pw-line";
    line.textContent = `line ${w.line}`;
    const det   = document.createElement("span");
    det.className = "pw-detail";
    det.textContent = w.detail;
    li.appendChild(kind);
    li.appendChild(path);
    li.appendChild(line);
    li.appendChild(det);
    promptsWarningList.appendChild(li);
  }
  promptsPendingSave = onContinue;
  promptsWarningModal.hidden = false;
}

function promptsOnWarningSaveAnyway() {
  promptsWarningModal.hidden = true;
  const fn = promptsPendingSave;
  promptsPendingSave = null;
  if (fn) fn();
}

function promptsOnWarningCancel() {
  promptsWarningModal.hidden = true;
  promptsPendingSave = null;
}

// ----- Wire up --------------------------------------------------

if (promptsSearch)         promptsSearch.addEventListener("input", promptsApplySearchFilter);
if (promptsEditor)         promptsEditor.addEventListener("input", promptsOnEditorInput);
if (promptsEditor)         promptsEditor.addEventListener("scroll", promptsOnEditorScroll);
if (promptsSave)           promptsSave.addEventListener("click", promptsSaveClicked);
if (promptsDiscard)        promptsDiscard.addEventListener("click", promptsDiscardClicked);
if (promptsUnlock)         promptsUnlock.addEventListener("click", promptsOnUnlock);
if (promptsPassword)       promptsPassword.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); promptsOnUnlock(); }
});
if (promptsAuthCancel)     promptsAuthCancel.addEventListener("click", promptsOnAuthCancel);
if (promptsWarningSave)    promptsWarningSave.addEventListener("click", promptsOnWarningSaveAnyway);
if (promptsWarningCancel)  promptsWarningCancel.addEventListener("click", promptsOnWarningCancel);
if (promptsDiscardConfirm) promptsDiscardConfirm.addEventListener("click", promptsDiscardConfirmed);
if (promptsDiscardCancel)  promptsDiscardCancel.addEventListener("click", () => {
  promptsDiscardModal.hidden = true;
});

// Browser-native warning on page close/refresh with dirty buffers
// (round 4 Q16).  The view-switch in-app prompt is in switchView above.
window.addEventListener("beforeunload", (e) => {
  if (typeof promptsState !== "undefined" && promptsDirtyCount() > 0) {
    e.preventDefault();
    e.returnValue = "";
  }
});
// =============================================================================
// Embedding tests — complete rebuild
// -----------------------------------------------------------------------------
// Layout: top toolbar (status + view-mode toggle + rebuild), compact search row
// (text + image), single results panel (3x3 grid + captions, last-query wins),
// scroll-bounded reference table (Compact / Full / Grid), wider Recent-searches
// rail with rich 3x3 mini-grid entries (click to re-run).
// =============================================================================

let embLoaded = false;
let embManifest = null;
let embCurrentUpload = null;
let embRebuildInFlight = false;
let embImageSearchInFlight = false;
let embTableMode = "compact";
let embSelectedSketchName = null;
const EMB_LS_MODE_KEY = "emb-tests:table-mode";

const EMB_METHODS = [
  { key: "voyage",           title: "Voyage",           sub: "joint multimodal" },
  { key: "caption_visual",   title: "Caption visual",   sub: "VLM + OpenAI text-emb" },
  { key: "caption_semantic", title: "Caption semantic", sub: "VLM + OpenAI text-emb" },
];
const EMB_METHOD_LABEL = {
  voyage: "V", caption_visual: "CV", caption_semantic: "CS",
};
// Word -> integer for the blade-count parser.
const EMB_NUM = {
  one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8,
  nine:9, ten:10, eleven:11, twelve:12,
};

function embEsc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function embFmtScore(s) {
  return typeof s === "number" ? s.toFixed(3) : String(s);
}
function embImgUrl(name)   { return "/api/embedding_tests/image/"  + encodeURIComponent(name); }
function embThumbUrl(name, w) { return embImgUrl(name) + "?w=" + encodeURIComponent(w); }
function embUploadUrl(name){ return "/api/embedding_tests/upload/" + encodeURIComponent(name); }

// Parse blade count from a semantic description ("Blade count: 3",
// "5 blades", "Blade count = 4", "six blades", etc.).  Returns null
// if no count is identifiable.
function embExtractBladeCount(text) {
  if (!text) return null;
  const patterns = [
    /[Bb]lade\s*count[:\s=]+(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)/,
    /(\d+|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+blades?/i,
  ];
  for (const p of patterns) {
    const m = text.match(p);
    if (m) {
      const raw = String(m[1]).toLowerCase();
      const n = EMB_NUM[raw] || parseInt(raw, 10);
      if (!isNaN(n) && n > 0 && n < 50) return n;
    }
  }
  return null;
}

// ----- Lightbox (dialog with focus trap + return) -----

let _embLightboxOpener = null;   // element that had focus when we opened

function embOpenLightbox(src, caption) {
  const overlay = document.getElementById("emb-lightbox");
  const img     = document.getElementById("emb-lightbox-img");
  const cap     = document.getElementById("emb-lightbox-caption");
  const close   = document.getElementById("emb-lightbox-close");
  if (!overlay || !img) return;
  _embLightboxOpener = document.activeElement;
  img.src = src;
  // Fall back to a generic phrase so screen readers always get
  // SOMETHING when alt is rendered, even if caption is empty.
  img.alt = caption || "Enlarged sketch preview";
  if (cap) cap.textContent = caption || "";
  overlay.hidden = false;
  // Move keyboard focus into the modal so Tab is trapped here.
  if (close) {
    try { close.focus(); } catch (_) { /* ignore */ }
  }
}

function embCloseLightbox() {
  const overlay = document.getElementById("emb-lightbox");
  const img     = document.getElementById("emb-lightbox-img");
  if (!overlay) return;
  overlay.hidden = true;
  if (img) img.src = "";
  // Restore focus to whatever opened the lightbox.
  if (_embLightboxOpener && typeof _embLightboxOpener.focus === "function") {
    try { _embLightboxOpener.focus(); } catch (_) { /* ignore */ }
  }
  _embLightboxOpener = null;
}

// Keyboard handling for the lightbox: Esc closes; Tab and Shift+Tab
// are trapped inside the modal (only the close button is focusable,
// so we just keep focus on it).
document.addEventListener("keydown", (e) => {
  const overlay = document.getElementById("emb-lightbox");
  if (!overlay || overlay.hidden) return;
  if (e.key === "Escape") {
    embCloseLightbox();
    return;
  }
  if (e.key === "Tab") {
    const close = document.getElementById("emb-lightbox-close");
    if (close) {
      e.preventDefault();
      close.focus();
    }
  }
});

// ----- Status badge (top toolbar) -----

let _embStatusWarnTimer = null;   // auto-clear handle

function embSetStatusBadge(text, kind) {
  const el = document.getElementById("emb-status-badge");
  if (!el) return;
  el.textContent = text;
  el.classList.remove("warn", "busy", "ok");
  if (kind) el.classList.add(kind);
  el.title = text;
  // Auto-clear warn states so a stale "Cannot re-run upload" message
  // can't sit there forever.  Cleared by the next badge update too.
  if (_embStatusWarnTimer) {
    clearTimeout(_embStatusWarnTimer);
    _embStatusWarnTimer = null;
  }
  if (kind === "warn") {
    _embStatusWarnTimer = setTimeout(() => {
      // Refetch the manifest to re-paint the proper "vectors ready /
      // not ready" message rather than just blanking the badge.
      _embStatusWarnTimer = null;
      try { fetchEmbManifest(); } catch (_) { /* ignore */ }
    }, 6000);
  }
}

// ----- Reference-table view modes (Compact / Full / Grid) -----

function setEmbTableMode(mode) {
  if (!["compact", "full", "grid"].includes(mode)) mode = "compact";
  embTableMode = mode;
  try { localStorage.setItem(EMB_LS_MODE_KEY, mode); } catch (_) { /* ignore */ }
  const table = document.getElementById("emb-ref-table");
  const grid  = document.getElementById("emb-ref-grid");
  if (table) table.dataset.viewMode = mode;
  if (grid) {
    grid.dataset.active = (mode === "grid") ? "1" : "0";
    // Keep the `hidden` attribute in sync with CSS so any UA / a11y
    // tool that consults the attribute sees consistent state.
    grid.hidden = (mode !== "grid");
  }
  for (const b of document.querySelectorAll(".emb-mode-btn")) {
    const on = b.dataset.mode === mode;
    b.classList.toggle("active", on);
    // role="group" + aria-pressed is the correct pattern for a
    // mutually-exclusive group of toggle buttons (we dropped the
    // tablist role since we don't implement arrow-key navigation).
    b.setAttribute("aria-pressed", on ? "true" : "false");
  }
}

for (const b of document.querySelectorAll(".emb-mode-btn")) {
  b.addEventListener("click", () => setEmbTableMode(b.dataset.mode));
}

// ----- Manifest + reference table -----

async function loadEmbedTests() {
  // Apply persisted view mode (default: compact).
  let savedMode = "compact";
  try {
    const s = localStorage.getItem(EMB_LS_MODE_KEY);
    if (["compact", "full", "grid"].includes(s)) savedMode = s;
  } catch (_) { /* ignore */ }
  setEmbTableMode(savedMode);

  if (embLoaded) {
    refreshEmbLog();
    return;
  }
  const [manifestOk] = await Promise.all([
    fetchEmbManifest(),
    refreshEmbLog(),
  ]);
  if (manifestOk) embLoaded = true;
}

// Build a reference-table description cell: 4-line clamp by default,
// with [Copy] / [→ Search] / [Show more] action buttons.  Clamping
// keeps each row to ~150 px tall instead of ~1500 px; the action row
// turns "copy + paste into the search box" into one click.
function buildEmbDescCell(text, kind, sketchName) {
  const wrap = document.createElement("div");
  wrap.className = "emb-desc-wrap";

  const txt = (text || "").trim();

  const textEl = document.createElement("div");
  textEl.className = "emb-desc-text";
  textEl.textContent = txt || "(empty)";
  wrap.appendChild(textEl);

  if (!txt) return wrap;

  const actions = document.createElement("div");
  actions.className = "emb-desc-actions";

  // Copy to clipboard.  e.stopPropagation so the description-cell
  // buttons don't also fire the row-click selectRefRow handler.
  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.textContent = "Copy";
  copyBtn.title = "Copy this " + kind + " description to clipboard";
  copyBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(txt);
      copyBtn.textContent = "✓ Copied";
      copyBtn.classList.add("success");
    } catch (_) {
      copyBtn.textContent = "Copy failed";
    }
    setTimeout(() => {
      copyBtn.textContent = "Copy";
      copyBtn.classList.remove("success");
    }, 1400);
  });
  actions.appendChild(copyBtn);

  // → Search: paste into the Text → Images box and submit.
  const searchBtn = document.createElement("button");
  searchBtn.type = "button";
  searchBtn.className = "primary";
  searchBtn.textContent = "→ Search";
  searchBtn.title = "Paste this " + kind + " description into the search box and run it";
  searchBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const input = document.getElementById("emb-text-input");
    const form  = document.getElementById("emb-text-form");
    if (!input || !form) return;
    input.value = txt;
    input.scrollIntoView({ behavior: "smooth", block: "center" });
    input.focus();
    if (typeof form.requestSubmit === "function") form.requestSubmit();
    else form.dispatchEvent(new Event("submit", { cancelable: true }));
  });
  actions.appendChild(searchBtn);

  // Show more / less — toggles the 4-line clamp.
  const moreBtn = document.createElement("button");
  moreBtn.type = "button";
  moreBtn.textContent = "Show more";
  moreBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const expanded = textEl.classList.toggle("expanded");
    moreBtn.textContent = expanded ? "Show less" : "Show more";
  });
  actions.appendChild(moreBtn);

  wrap.appendChild(actions);
  return wrap;
}


async function fetchEmbManifest() {
  const tbody  = document.getElementById("emb-ref-tbody");
  const meta   = document.getElementById("emb-meta");
  const select = document.getElementById("emb-image-select");
  const grid   = document.getElementById("emb-ref-grid");
  try {
    const res = await fetch("/api/embedding_tests/manifest");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    embManifest = data;

    if (tbody) {
      tbody.innerHTML = "";
      for (const r of (data.images || [])) tbody.appendChild(buildRefTableRow(r));
    }
    if (grid) {
      grid.innerHTML = "";
      for (const r of (data.images || [])) grid.appendChild(buildRefGridCard(r));
    }
    if (select) {
      while (select.options.length > 1) select.remove(1);
      for (const r of (data.images || [])) {
        const opt = document.createElement("option");
        opt.value = r.name;
        opt.textContent = r.index + ". " + r.name;
        select.appendChild(opt);
      }
    }

    const mv  = data.model_versions || {};
    const gen = data.generated_at;
    const hasVecs = (data.images || []).some(r =>
      r.has_voyage_vector || r.has_visual_caption_vector ||
      r.has_semantic_caption_vector);
    if (meta) {
      meta.innerHTML =
        "voyage=" + embEsc(mv.voyage || "—") +
        " · cap_vlm=" + embEsc(mv.caption_vlm || "—") +
        " · text-emb=" + embEsc(mv.caption_text_embedder || "—") +
        " · generated " + embEsc(gen || "—");
      if (!hasVecs) {
        meta.innerHTML =
          "<span class=\"emb-warn\">⚠ no vectors — click Rebuild</span> · " +
          meta.innerHTML;
      }
    }
    embSetStatusBadge(
      hasVecs ? ("Vectors ready · " + (gen || "—"))
              : "⚠ No vectors — click Rebuild index",
      hasVecs ? "ok" : "warn"
    );
    return true;
  } catch (e) {
    if (tbody) tbody.innerHTML =
      "<tr class=\"emb-error\"><td colspan=\"6\">" +
      "Failed to load manifest: " + embEsc(e.message || e) + "</td></tr>";
    if (grid) grid.innerHTML = "";
    if (select) { while (select.options.length > 1) select.remove(1); }
    if (meta) meta.innerHTML =
      "<span class=\"emb-warn\">Manifest load failed: " +
      embEsc(e.message || e) + "</span>";
    embSetStatusBadge("Manifest load failed", "warn");
    embManifest = null;
    return false;
  }
}

// Build one <tr> for the reference table (works for both Compact and
// Full modes; the Full-only description cells get the
// .emb-mode-full-only class so CSS hides them in Compact).
function buildRefTableRow(r) {
  const tr = document.createElement("tr");
  tr.dataset.name = r.name;
  // Keyboard reachability: the row IS a button (it selects the sketch
  // for image-query use).  Tab to focus, Enter / Space to activate.
  tr.tabIndex = 0;
  tr.setAttribute("role", "button");
  tr.setAttribute(
    "aria-label",
    "Sketch " + r.name + " — press Enter to select as image query");

  const tdIdx = document.createElement("td");
  tdIdx.textContent = r.index;
  tdIdx.style.textAlign = "center";

  const tdName = document.createElement("td");
  tdName.className = "emb-td-name";
  tdName.textContent = r.name;

  const tdThumb = document.createElement("td");
  tdThumb.style.textAlign = "center";
  const img = document.createElement("img");
  img.src = embThumbUrl(r.name, 140);
  img.alt = r.name;
  img.className = "emb-thumb-ref";
  img.addEventListener("click", (e) => {
    e.stopPropagation();
    embOpenLightbox(embImgUrl(r.name), r.name);
  });
  tdThumb.appendChild(img);

  const tdBlades = document.createElement("td");
  tdBlades.className = "emb-td-blades";
  tdBlades.appendChild(buildBladeBadge(r.semantic_description));

  const tdVis = document.createElement("td");
  tdVis.className = "emb-td-desc emb-mode-full-only";
  tdVis.appendChild(buildEmbDescCell(r.visual_description, "visual", r.name));

  const tdSem = document.createElement("td");
  tdSem.className = "emb-td-desc emb-mode-full-only";
  tdSem.appendChild(buildEmbDescCell(r.semantic_description, "semantic", r.name));

  tr.appendChild(tdIdx);
  tr.appendChild(tdName);
  tr.appendChild(tdThumb);
  tr.appendChild(tdBlades);
  tr.appendChild(tdVis);
  tr.appendChild(tdSem);

  tr.addEventListener("click", () => {
    // Description-cell buttons + image thumbnail call e.stopPropagation
    // — this fires only for "background" row clicks.
    selectRefRow(r.name);
  });
  tr.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selectRefRow(r.name);
    }
  });
  return tr;
}

function buildRefGridCard(r) {
  const card = document.createElement("div");
  card.className = "emb-ref-grid-card";
  card.dataset.name = r.name;
  // Same keyboard reachability as the table-row equivalent above.
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.setAttribute(
    "aria-label",
    "Sketch " + r.name + " — press Enter to select as image query");

  const img = document.createElement("img");
  img.src = embThumbUrl(r.name, 300);
  img.alt = r.name;
  img.addEventListener("click", (e) => {
    e.stopPropagation();
    embOpenLightbox(embImgUrl(r.name), r.name);
  });
  card.appendChild(img);

  const meta = document.createElement("div");
  meta.className = "emb-ref-grid-card-meta";
  const name = document.createElement("span");
  name.className = "emb-ref-grid-card-name";
  name.textContent = r.name;
  meta.appendChild(name);
  meta.appendChild(buildBladeBadge(r.semantic_description));
  card.appendChild(meta);

  card.addEventListener("click", () => selectRefRow(r.name));
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selectRefRow(r.name);
    }
  });
  return card;
}

function buildBladeBadge(text) {
  const n = embExtractBladeCount(text);
  const b = document.createElement("span");
  if (n) {
    b.className = "emb-blade-badge";
    b.textContent = n + (n === 1 ? " blade" : " blades");
  } else {
    b.className = "emb-blade-badge empty";
    b.textContent = "—";
  }
  return b;
}

// Row / card selection: highlights + exposes "→ image query" affordance
// next to the selected sketch's name.
function selectRefRow(name) {
  embSelectedSketchName = name;
  for (const tr of document.querySelectorAll(".emb-ref-table tbody tr")) {
    tr.classList.toggle("selected", tr.dataset.name === name);
  }
  for (const c of document.querySelectorAll(".emb-ref-grid-card")) {
    c.classList.toggle("selected", c.dataset.name === name);
  }
  // Sync the image-search dropdown so picked-search uses this sketch.
  const sel = document.getElementById("emb-image-select");
  if (sel) {
    sel.value = name;
    sel.dispatchEvent(new Event("change"));
  }
  attachRowActionButton(name);
}

function attachRowActionButton(name) {
  for (const b of document.querySelectorAll(".emb-row-action-btn")) b.remove();
  if (!name) return;
  const make = () => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "emb-row-action-btn";
    btn.textContent = "→ image query";
    btn.title = "Use this sketch as the image query and search";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const picked = document.getElementById("emb-image-search-picked");
      if (picked && !picked.disabled) picked.click();
    });
    return btn;
  };
  const tr = document.querySelector(
    ".emb-ref-table tbody tr[data-name=\"" + CSS.escape(name) + "\"]");
  if (tr) {
    const cell = tr.querySelector(".emb-td-name");
    if (cell) cell.appendChild(make());
  }
  const card = document.querySelector(
    ".emb-ref-grid-card[data-name=\"" + CSS.escape(name) + "\"]");
  if (card) {
    const btn = make();
    btn.style.marginLeft = "0";
    card.appendChild(btn);
  }
}

// Scroll-highlight a sketch in the reference table when a result tile
// is clicked.  Flashes the row briefly so the eye finds it.
function scrollHighlightInTable(name) {
  if (!name) return;
  const tr = document.querySelector(
    ".emb-ref-table tbody tr[data-name=\"" + CSS.escape(name) + "\"]");
  if (tr && tr.offsetParent !== null) {
    tr.scrollIntoView({ behavior: "smooth", block: "center" });
    tr.classList.remove("flash");
    void tr.offsetWidth;          // restart the animation
    tr.classList.add("flash");
    return;
  }
  const card = document.querySelector(
    ".emb-ref-grid-card[data-name=\"" + CSS.escape(name) + "\"]");
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("selected");
    setTimeout(() => card.classList.remove("selected"), 1500);
  }
}

// ----- Results panel (3x3 grid: methods × rank) -----

function renderResultsPanel(opts) {
  const { query_kind, query_text, query_image, methods, errors, captions } = opts;
  const badgeEl = document.getElementById("emb-results-badge");
  const grid    = document.getElementById("emb-results-grid");
  const capWrap = document.getElementById("emb-image-captions");
  const capVis  = document.getElementById("emb-image-caption-visual");
  const capSem  = document.getElementById("emb-image-caption-semantic");
  if (!grid) return;

  // Header badge: "Text query: 'foo'" or "Image query: [thumb] name"
  if (badgeEl) {
    badgeEl.innerHTML = "";
    const kind = document.createElement("span");
    kind.className = "emb-results-badge-kind";
    kind.textContent = query_kind === "text" ? "Text query" : "Image query";
    badgeEl.appendChild(kind);
    if (query_kind === "text") {
      const t = document.createElement("span");
      const s = (query_text || "");
      t.textContent = "“" + (s.length > 110 ? s.slice(0, 110) + "…" : s) + "”";
      badgeEl.appendChild(t);
    } else if (query_image) {
      if (query_image.thumb) {
        const img = document.createElement("img");
        img.src = query_image.thumb;
        img.className = "emb-results-badge-thumb";
        img.alt = query_image.label || "";
        badgeEl.appendChild(img);
      }
      const lbl = document.createElement("span");
      lbl.textContent = query_image.label || query_image.name || "";
      badgeEl.appendChild(lbl);
    }
  }

  // 3x3 grid: row 0 = rank headers; rows 1..3 = methods.
  grid.classList.remove("emb-results-empty");
  grid.innerHTML = "";

  const spacer = document.createElement("div");
  spacer.className = "emb-grid-row-label";
  grid.appendChild(spacer);
  for (let i = 1; i <= 3; i++) {
    const h = document.createElement("div");
    h.className = "emb-grid-rank-header";
    h.textContent = "# " + i;
    grid.appendChild(h);
  }

  for (const m of EMB_METHODS) {
    const lbl = document.createElement("div");
    lbl.className = "emb-grid-row-label " + m.key;
    const main = document.createElement("span");
    main.textContent = m.title;
    lbl.appendChild(main);
    const sub = document.createElement("span");
    sub.className = "emb-grid-row-sub";
    sub.textContent = m.sub;
    lbl.appendChild(sub);
    grid.appendChild(lbl);

    const list = (methods || {})[m.key] || [];
    const err  = (errors  || {})[m.key];
    if (err) {
      const errRow = document.createElement("div");
      errRow.className = "emb-method-error-row";
      errRow.textContent = err;
      grid.appendChild(errRow);
    } else {
      for (let i = 0; i < 3; i++) {
        if (list[i]) {
          grid.appendChild(buildResultTile(m.key, list[i]));
        } else {
          const ph = document.createElement("div");
          ph.className = "emb-result-tile " + m.key;
          ph.style.opacity = "0.25";
          const e = document.createElement("em");
          e.className = "emb-empty";
          e.textContent = "(empty)";
          ph.appendChild(e);
          grid.appendChild(ph);
        }
      }
    }
  }

  if (capWrap && capVis && capSem) {
    if (captions && (captions.visual || captions.semantic)) {
      capVis.textContent = captions.visual   || "(empty)";
      capSem.textContent = captions.semantic || "(empty)";
      capWrap.hidden = false;
    } else {
      capWrap.hidden = true;
    }
  }
}

function buildResultTile(methodKey, r) {
  const methodTitle = (EMB_METHODS.find(m => m.key === methodKey) || {}).title
                      || methodKey;
  const tile = document.createElement("div");
  tile.className = "emb-result-tile " + methodKey;
  tile.dataset.name = r.name;
  tile.title = methodTitle + " — " + r.name + " · score " + embFmtScore(r.score);
  // Keyboard reachability: each result tile is effectively a button
  // that opens the lightbox and scroll-highlights the reference row.
  tile.tabIndex = 0;
  tile.setAttribute("role", "button");
  tile.setAttribute(
    "aria-label",
    methodTitle + " result — " + r.name +
    ", score " + embFmtScore(r.score) +
    ", press Enter to preview");

  const img = document.createElement("img");
  img.src = embThumbUrl(r.name, 240);
  img.alt = r.name;
  img.className = "emb-result-thumb";
  tile.appendChild(img);

  const name = document.createElement("div");
  name.className = "emb-result-name";
  name.textContent = r.name;
  tile.appendChild(name);

  const scoreRow = document.createElement("div");
  scoreRow.className = "emb-result-score-row";
  const score = document.createElement("span");
  score.className = "emb-result-score";
  score.textContent = embFmtScore(r.score);
  const bar = document.createElement("div");
  bar.className = "emb-result-bar";
  const fill = document.createElement("div");
  fill.className = "emb-result-bar-fill";
  const pct = Math.max(0, Math.min(1, +r.score || 0)) * 100;
  fill.style.width = pct.toFixed(1) + "%";
  bar.appendChild(fill);
  scoreRow.appendChild(score);
  scoreRow.appendChild(bar);
  tile.appendChild(scoreRow);

  // Click tile (anywhere) → lightbox + scroll-highlight in reference table.
  tile.addEventListener("click", () => {
    embOpenLightbox(embImgUrl(r.name), r.name);
    scrollHighlightInTable(r.name);
  });
  tile.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      embOpenLightbox(embImgUrl(r.name), r.name);
      scrollHighlightInTable(r.name);
    }
  });
  return tile;
}

function _embErrorTriple(msg) {
  return { voyage: msg, caption_visual: msg, caption_semantic: msg };
}

// ----- Text search -----

const embTextForm  = document.getElementById("emb-text-form");
const embTextInput = document.getElementById("emb-text-input");
const embTextBtn   = document.getElementById("emb-text-btn");

if (embTextForm) embTextForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = (embTextInput && embTextInput.value || "").trim();
  if (!text) return;
  if (embTextBtn) embTextBtn.disabled = true;
  try {
    const res = await fetch("/api/embedding_tests/search_text", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!data.ok) {
      renderResultsPanel({
        query_kind: "text", query_text: text,
        methods: {}, errors: _embErrorTriple(data.error || "Search failed."),
      });
    } else {
      renderResultsPanel({
        query_kind: "text", query_text: text,
        methods: data.methods, errors: data.errors,
      });
      if (data.log_entry) prependEmbLogEntry(data.log_entry);
    }
  } catch (err) {
    renderResultsPanel({
      query_kind: "text", query_text: text,
      methods: {}, errors: _embErrorTriple(String(err)),
    });
  } finally {
    if (embTextBtn) embTextBtn.disabled = false;
  }
});

// ----- Image search (picked from set) -----

const embImageSelect       = document.getElementById("emb-image-select");
const embImageSearchPicked = document.getElementById("emb-image-search-picked");

if (embImageSelect) embImageSelect.addEventListener("change", () => {
  // Don't re-enable the button mid-flight — selectRefRow and
  // rerunEmbLogEntry both dispatch a synthetic change event that
  // would otherwise overwrite the disabled-by-_embStartImageSearch
  // state and produce a UI flicker on the button.
  if (embImageSearchPicked && !embImageSearchInFlight)
    embImageSearchPicked.disabled = !embImageSelect.value;
});

function _embStartImageSearch() {
  embImageSearchInFlight = true;
  if (embImageSearchPicked) embImageSearchPicked.disabled = true;
  if (embImageSearchUpload) embImageSearchUpload.disabled = true;
}

function _embEndImageSearch() {
  embImageSearchInFlight = false;
  if (embImageSearchPicked)
    embImageSearchPicked.disabled = !(embImageSelect && embImageSelect.value);
  if (embImageSearchUpload)
    embImageSearchUpload.disabled = !embCurrentUpload;
}

if (embImageSearchPicked) embImageSearchPicked.addEventListener("click",
  async () => {
    if (embImageSearchInFlight) return;
    if (!embImageSelect || !embImageSelect.value) return;
    const name = embImageSelect.value;
    const qmeta = { name, label: "picked: " + name, thumb: embThumbUrl(name, 80) };
    _embStartImageSearch();
    try {
      const res = await fetch("/api/embedding_tests/search_image_picked", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ image_name: name }),
      });
      const data = await res.json();
      handleEmbImageResponse(data, "image_picked", qmeta);
    } catch (err) {
      renderResultsPanel({
        query_kind: "image_picked", query_image: qmeta,
        methods: {}, errors: _embErrorTriple(String(err)),
      });
    } finally {
      _embEndImageSearch();
    }
  });

// ----- Image search (uploaded) -----

const embImageFile         = document.getElementById("emb-image-file");
const embImagePickFile     = document.getElementById("emb-image-pick-file");
const embImageFilename     = document.getElementById("emb-image-filename");
const embImageSearchUpload = document.getElementById("emb-image-search-upload");

if (embImagePickFile) embImagePickFile.addEventListener("click", () => {
  if (embImageFile) embImageFile.click();
});

if (embImageFile) embImageFile.addEventListener("change", () => {
  const f = embImageFile.files && embImageFile.files[0];
  embCurrentUpload = f || null;
  if (embImageFilename) {
    embImageFilename.textContent = f ? f.name : "";
  }
  // Same in-flight guard as the picked-dropdown change handler so
  // picking a new file mid-flight doesn't flicker the upload button.
  if (embImageSearchUpload && !embImageSearchInFlight)
    embImageSearchUpload.disabled = !f;
});

if (embImageSearchUpload) embImageSearchUpload.addEventListener("click",
  async () => {
    if (embImageSearchInFlight) return;
    if (!embCurrentUpload) return;
    const uploadName = embCurrentUpload.name || "uploaded image";
    _embStartImageSearch();
    try {
      const fd = new FormData();
      fd.append("file", embCurrentUpload);
      const res = await fetch("/api/embedding_tests/search_image_upload", {
        method: "POST", body: fd,
      });
      const data = await res.json();
      const qmeta = {
        label: "upload: " + uploadName,
        thumb: data.upload_ref ? embUploadUrl(data.upload_ref) : undefined,
        name:  data.upload_ref || "",
      };
      handleEmbImageResponse(data, "image_upload", qmeta);
    } catch (err) {
      renderResultsPanel({
        query_kind: "image_upload",
        query_image: { label: "upload: " + uploadName },
        methods: {}, errors: _embErrorTriple(String(err)),
      });
    } finally {
      _embEndImageSearch();
    }
  });

function handleEmbImageResponse(data, kind, qmeta) {
  if (!data.ok) {
    renderResultsPanel({
      query_kind: kind, query_image: qmeta,
      methods: {}, errors: _embErrorTriple(data.error || "Search failed."),
    });
    return;
  }
  renderResultsPanel({
    query_kind: kind, query_image: qmeta,
    methods: data.methods, errors: data.errors,
    captions: data.captions_used,
  });
  if (data.log_entry) prependEmbLogEntry(data.log_entry);
}

// ----- Rebuild (status feedback flows through the top-bar badge) -----

const embRebuildBtn = document.getElementById("emb-rebuild-btn");

if (embRebuildBtn) embRebuildBtn.addEventListener("click", async () => {
  if (embRebuildInFlight) return;
  const msg =
    "Rebuild the embedding index?\n\n" +
    "Re-embeds every sketch via Voyage multimodal-3 AND " +
    "re-embeds the two caption-based vectors via OpenAI text-embedding-3-large.\n\n" +
    "Existing baked-in descriptions are PRESERVED.\n\n" +
    "Takes 1-3 minutes. Do not close the tab while it runs.";
  if (!window.confirm(msg)) return;

  embRebuildInFlight = true;
  embRebuildBtn.disabled = true;
  const t0 = Date.now();
  let tick = null;
  embSetStatusBadge("Rebuilding… 0 s", "busy");
  try {
    tick = setInterval(() => {
      const sec = Math.floor((Date.now() - t0) / 1000);
      embSetStatusBadge("Rebuilding… " + sec + " s", "busy");
    }, 1000);
    const res = await fetch("/api/embedding_tests/rebuild_index", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ preserve_descriptions: true }),
    });
    if (res.status === 409) {
      embSetStatusBadge("Rebuild already in progress", "warn");
      return;
    }
    const data = await res.json();
    if (data.ok) {
      const dur = data.duration_seconds != null
        ? " in " + data.duration_seconds + " s" : "";
      const errLine = (data.errors && data.errors.length)
        ? " (" + data.errors.length + " step errors)" : "";
      embSetStatusBadge(
        "Rebuilt " + data.n_images + " images" + dur + errLine,
        "ok"
      );
      // Refetch the manifest after a successful rebuild.  If THAT
      // call fails (transient HTTP / JSON), embLoaded must stay false
      // so the next view-open retries the manifest — otherwise the
      // table/dropdown/grid would stay empty until a hard reload.
      embLoaded = false;
      const refetched = await fetchEmbManifest();
      embLoaded = !!refetched;
    } else {
      embSetStatusBadge(
        "Rebuild failed: " + (data.error || "unknown error"),
        "warn"
      );
    }
  } catch (err) {
    embSetStatusBadge("Rebuild failed: " + (err.message || err), "warn");
  } finally {
    if (tick) clearInterval(tick);
    embRebuildInFlight = false;
    embRebuildBtn.disabled = false;
  }
});

// ----- Log panel -----

const embLogRefresh = document.getElementById("emb-log-refresh");
if (embLogRefresh) embLogRefresh.addEventListener("click", refreshEmbLog);

async function refreshEmbLog() {
  try {
    const res = await fetch("/api/embedding_tests/log?limit=50");
    if (!res.ok) return;
    const data = await res.json();
    renderEmbLog(data.entries || []);
  } catch (_) { /* ignore */ }
}

function renderEmbLog(entries) {
  const stream = document.getElementById("emb-log-stream");
  if (!stream) return;
  stream.innerHTML = "";
  if (!entries.length) {
    const em = document.createElement("em");
    em.className = "emb-empty";
    em.textContent = "(no searches yet)";
    stream.appendChild(em);
    return;
  }
  // Newest at top.
  for (const e of entries.slice().reverse()) {
    stream.appendChild(buildEmbLogEntry(e));
  }
}

function prependEmbLogEntry(entry) {
  const stream = document.getElementById("emb-log-stream");
  if (!stream) return;
  const placeholder = stream.querySelector(".emb-empty");
  if (placeholder) placeholder.remove();
  stream.insertBefore(buildEmbLogEntry(entry), stream.firstChild);
}

function buildEmbLogEntry(e) {
  const card = document.createElement("div");
  card.className = "emb-log-entry";
  card.tabIndex = 0;
  card.title = "Click to re-run this search";

  // Head: timestamp + kind tag
  const head = document.createElement("div");
  head.className = "emb-log-entry-head";
  const ts = document.createElement("span");
  ts.className = "emb-log-ts";
  ts.textContent = (e.ts || "").replace("T", " ").replace("Z", "");
  head.appendChild(ts);
  const kind = document.createElement("span");
  kind.className = "emb-log-kind-tag" + (e.query_type === "text" ? "" : " image");
  kind.textContent = e.query_type === "text" ? "TEXT" :
                     e.query_type === "image_upload" ? "UPL" : "PICK";
  head.appendChild(kind);
  card.appendChild(head);

  // Query area
  const q = document.createElement("div");
  q.className = "emb-log-query";
  if (e.query_type === "text") {
    const t = document.createElement("div");
    t.className = "emb-log-q-text";
    const text = e.query || "";
    t.textContent = "“" +
      (text.length > 130 ? text.slice(0, 130) + "…" : text) + "”";
    q.appendChild(t);
  } else if (e.query_type === "image_picked" || e.query_type === "image_upload") {
    const qrow = document.createElement("div");
    qrow.className = "emb-log-qrow";
    const qimg = document.createElement("img");
    qimg.className = "emb-log-q-thumb";
    qimg.src = e.query_type === "image_upload"
      ? embUploadUrl(e.query_image || "")
      : embThumbUrl(e.query_image || "", 100);
    qimg.alt = e.query_image || "";
    qimg.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const src = e.query_type === "image_upload"
        ? embUploadUrl(e.query_image || "")
        : embImgUrl(e.query_image || "");
      embOpenLightbox(src, e.filename || e.query_image);
    });
    qrow.appendChild(qimg);
    const qname = document.createElement("div");
    qname.className = "emb-log-q-name";
    qname.textContent = e.query_type === "image_upload"
      ? (e.filename || e.query_image || "")
      : (e.query_image || "");
    qrow.appendChild(qname);
    q.appendChild(qrow);
  }
  card.appendChild(q);

  // Mini 3x3 grid: rows = methods, cols = #1/#2/#3
  const grid = document.createElement("div");
  grid.className = "emb-log-mini-grid";
  const spacer = document.createElement("div");
  spacer.className = "emb-log-mini-row-label";
  grid.appendChild(spacer);
  for (let i = 1; i <= 3; i++) {
    const h = document.createElement("div");
    h.className = "emb-log-mini-row-label";
    h.style.textAlign = "center";
    h.style.color = "var(--muted)";
    h.style.fontSize = "9px";
    h.textContent = "#" + i;
    grid.appendChild(h);
  }
  for (const m of EMB_METHODS) {
    const lbl = document.createElement("div");
    lbl.className = "emb-log-mini-row-label " + m.key;
    lbl.textContent = EMB_METHOD_LABEL[m.key];
    // Color alone is not enough to identify the method for a
    // color-blind user; the full method name is exposed via title
    // (mouse) and aria-label (screen reader).
    lbl.title = m.title;
    lbl.setAttribute("aria-label", m.title);
    grid.appendChild(lbl);
    const list = ((e.results || {})[m.key]) || [];
    const err  = ((e.errors  || {})[m.key]);
    if (err) {
      const errBox = document.createElement("div");
      errBox.className = "emb-log-mini-err";
      errBox.textContent = String(err).slice(0, 80);
      errBox.title = m.title + " error: " + String(err);
      grid.appendChild(errBox);
      continue;
    }
    for (let i = 0; i < 3; i++) {
      const tile = document.createElement("div");
      tile.className = "emb-log-mini-tile " + m.key;
      if (list[i]) {
        const img = document.createElement("img");
        img.src = embThumbUrl(list[i].name, 80);
        // Alt text is the method + image name so the row's method is
        // discoverable from the image itself (color is duplicated).
        img.alt = m.title + " · " + list[i].name;
        img.className = "emb-log-mini-thumb";
        img.title = m.title + " — " + list[i].name +
                    " · score " + embFmtScore(list[i].score);
        tile.appendChild(img);
        const bar = document.createElement("div");
        bar.className = "emb-log-mini-bar";
        const fill = document.createElement("div");
        fill.className = "emb-log-mini-bar-fill";
        fill.style.width =
          (Math.max(0, Math.min(1, +list[i].score || 0)) * 100).toFixed(1) + "%";
        bar.appendChild(fill);
        tile.appendChild(bar);
      } else {
        tile.style.opacity = "0.25";
      }
      grid.appendChild(tile);
    }
  }
  card.appendChild(grid);

  // Click anywhere on the card → re-run.  Use stopPropagation on the
  // child query-thumbnail click so the lightbox-click isn't taken as
  // an entry click.
  const fire = () => rerunEmbLogEntry(e);
  card.addEventListener("click", fire);
  card.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fire(); }
  });

  return card;
}

// Click-to-re-run: text and picked queries reload deterministically;
// upload queries cannot be re-run (the original file is no longer in
// the browser).  We surface a warn-tone status badge in that case.
function rerunEmbLogEntry(e) {
  if (e.query_type === "text") {
    const input = document.getElementById("emb-text-input");
    const form  = document.getElementById("emb-text-form");
    if (input && form) {
      input.value = e.query || "";
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  } else if (e.query_type === "image_picked") {
    const sel = document.getElementById("emb-image-select");
    if (sel) {
      sel.value = e.query_image || "";
      sel.dispatchEvent(new Event("change"));
      const btn = document.getElementById("emb-image-search-picked");
      if (btn) btn.click();
    }
  } else if (e.query_type === "image_upload") {
    embSetStatusBadge(
      "Cannot re-run upload (file expired). Upload it again to retry.",
      "warn");
  }
}

// Lightbox close button + overlay click
const embLightboxClose = document.getElementById("emb-lightbox-close");
if (embLightboxClose) embLightboxClose.addEventListener("click", embCloseLightbox);
const embLightboxOverlay = document.getElementById("emb-lightbox");
if (embLightboxOverlay) embLightboxOverlay.addEventListener("click", (e) => {
  if (e.target === embLightboxOverlay) embCloseLightbox();
});
