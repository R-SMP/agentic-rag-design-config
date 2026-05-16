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

init();
startEventStream();
