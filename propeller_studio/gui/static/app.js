// Propeller Studio -- local GUI.
//
// The page holds no schema of its own: parameter names, ranges, view names,
// lighting rigs and the settings defaults all arrive from /api/schema.  That
// keeps one source of truth in settings.py; a hard-coded copy here would drift
// the first time a toggle is added and silently send stale settings.

const $ = (id) => document.getElementById(id);
let SCHEMA = null;
let POLL = null;

const ANNOTATIONS = [
  ["chord", "Chord length"],
  ["angle", "Angle of attack"],
  ["thickness", "Max thickness"],
  ["camber", "Max camber + crest"],
  ["radial_station", "Radial station r"],
  ["span_position", "Span position"],
  ["chord_line", "Chord line"],
  ["camber_line", "Camber mean line"],
  ["le_te", "LE / TE markers"],
  ["le_radius", "Leading-edge radius"],
  ["bbox", "Bounding box"],
  ["value_table", "Value table"],
];

async function boot() {
  SCHEMA = await (await fetch("/api/schema")).json();
  buildParams();
  buildChips("render-views", Object.keys(SCHEMA.named_views), ["iso", "top", "front"]);
  buildChips("draw-views", Object.keys(SCHEMA.named_views), ["top", "front", "iso"]);
  buildChips("sec-which", ["inner", "middle", "outer"], ["inner", "middle", "outer"]);
  buildSelect("projection", SCHEMA.projections, "perspective");
  buildSelect("lighting", SCHEMA.lighting_presets, "studio");
  buildSelect("bg-mode", SCHEMA.background_modes, "gradient");
  buildSelect("sheet-size", SCHEMA.sheet_sizes, "A3");
  buildSelect("layout", SCHEMA.layouts, "stacked");
  buildSelect("scale-mode", SCHEMA.scale_modes, "fill");
  buildAnnotations();
  buildPartMaterials();
  for (const p of SCHEMA.presets) {
    const o = document.createElement("option");
    o.value = o.textContent = p;
    $("preset").appendChild(o);
  }
  document.querySelectorAll("input[name=matmode]").forEach((r) =>
    r.addEventListener("change", () => {
      const perPart = document.querySelector("input[name=matmode]:checked").value === "per_part";
      $("mat-parts").hidden = !perPart;
      $("mat-uniform").hidden = perPart;
    }));
  document.querySelectorAll("input[type=range]").forEach(syncRange);
  $("render").addEventListener("click", startRender);
  $("apply-preset").addEventListener("click", applyPreset);
  $("save-preset").addEventListener("click", savePreset);
  loadHistory();
}

function syncRange(el) {
  const span = el.parentElement.querySelector(".val");
  if (!span) return;
  const show = () => { span.textContent = Number(el.value).toFixed(2); };
  el.addEventListener("input", show);
  show();
}

function buildParams() {
  const host = $("params");
  let group = null, box = null;
  for (const spec of SCHEMA.params) {
    if (spec.group !== group) {
      group = spec.group;
      const h = document.createElement("div");
      h.className = "field-label";
      h.textContent = group;
      host.appendChild(h);
      box = document.createElement("div");
      box.className = "param-grid";
      host.appendChild(box);
    }
    const wrap = document.createElement("label");
    wrap.className = "param";
    wrap.innerHTML =
      `<span class="pname">${spec.name}</span>` +
      `<input type="number" id="p_${spec.name}" step="${spec.integer ? 1 : 0.1}" ` +
      `value="${SCHEMA.defaults_params[spec.name]}">` +
      `<span class="prange">${spec.lo}–${spec.hi}${spec.unit ? " " + spec.unit : ""}</span>`;
    box.appendChild(wrap);
  }
}

function buildChips(hostId, names, checked) {
  const host = $(hostId);
  host.innerHTML = "";
  for (const n of names) {
    const id = `${hostId}_${n}`;
    const l = document.createElement("label");
    l.className = "chip";
    l.innerHTML = `<input type="checkbox" id="${id}" value="${n}"` +
      `${checked.includes(n) ? " checked" : ""}><span>${n}</span>`;
    host.appendChild(l);
  }
}

function buildSelect(id, values, selected) {
  const el = $(id);
  el.innerHTML = "";
  for (const v of values) {
    const o = document.createElement("option");
    o.value = o.textContent = v;
    if (v === selected) o.selected = true;
    el.appendChild(o);
  }
}

function buildAnnotations() {
  const host = $("annotations");
  const defs = SCHEMA.defaults.drawing.sections.annotations;
  for (const [key, label] of ANNOTATIONS) {
    const l = document.createElement("label");
    l.className = "check";
    l.innerHTML = `<input type="checkbox" id="an_${key}"${defs[key] ? " checked" : ""}> ${label}`;
    host.appendChild(l);
  }
}

function buildPartMaterials() {
  const host = $("mat-parts");
  const parts = SCHEMA.defaults.render.material.parts;
  for (const name of Object.keys(parts)) {
    const m = parts[name];
    const div = document.createElement("div");
    div.className = "partrow";
    div.innerHTML =
      `<span class="pname">${name}</span>` +
      `<input type="color" id="pc_${name}" value="${m.color}">` +
      `<label>metal <input type="number" step="0.05" min="0" max="1" id="pm_${name}" value="${m.metallic}"></label>` +
      `<label>rough <input type="number" step="0.05" min="0" max="1" id="pr_${name}" value="${m.roughness}"></label>` +
      `<label>opacity <input type="number" step="0.05" min="0.05" max="1" id="po_${name}" value="${m.opacity}"></label>`;
    host.appendChild(div);
  }
}

function chipValues(hostId) {
  return [...$(hostId).querySelectorAll("input:checked")].map((i) => i.value);
}

function customViews() {
  const raw = $("render-custom").value.trim();
  if (!raw) return [];
  const out = [];
  for (const tok of raw.split(",")) {
    const m = tok.trim().match(/^(-?[\d.]+)\s*[/ ]\s*(-?[\d.]+)$/);
    if (m) out.push({ name: `az${m[1]}_el${m[2]}`, az: +m[1], el: +m[2] });
  }
  return out;
}

function collectParams() {
  const out = {};
  for (const spec of SCHEMA.params) out[spec.name] = Number($(`p_${spec.name}`).value);
  return out;
}

function collectSettings() {
  const parts = {};
  for (const name of Object.keys(SCHEMA.defaults.render.material.parts)) {
    parts[name] = {
      color: $(`pc_${name}`).value,
      metallic: Number($(`pm_${name}`).value),
      roughness: Number($(`pr_${name}`).value),
      opacity: Number($(`po_${name}`).value),
    };
  }
  const annotations = {};
  for (const [key] of ANNOTATIONS) annotations[key] = $(`an_${key}`).checked;

  return {
    backend: document.querySelector("input[name=backend]:checked").value,
    render: {
      enabled: $("render-enabled").checked,
      views: [...chipValues("render-views"), ...customViews()],
      turntable: {
        enabled: Number($("turntable").value) > 0,
        count: Number($("turntable").value) || 12,
        elevation: Number($("turntable-el").value),
      },
      width: Number($("width").value),
      height: Number($("height").value),
      zoom: Number($("zoom").value),
      projection: $("projection").value,
      background: {
        mode: $("bg-mode").value,
        color: $("bg-color").value,
        color2: $("bg-color2").value,
        floor_color: $("bg-floor").value,
        shadow: $("bg-shadow").checked,
      },
      material: {
        mode: document.querySelector("input[name=matmode]:checked").value,
        uniform: {
          color: $("uni-color").value,
          metallic: Number($("uni-metallic").value),
          roughness: Number($("uni-roughness").value),
          opacity: Number($("uni-opacity").value),
        },
        parts,
      },
      lighting: { preset: $("lighting").value, intensity: Number($("intensity").value), custom: [] },
      overlays: {
        silhouette: $("ov-silhouette").checked,
        feature_edges: $("ov-feature").checked,
        feature_angle: Number($("ov-feature-angle").value),
        section_curves: $("ov-sections").checked,
        section_curves_on_top: $("ov-sections-top").checked,
        wireframe: $("ov-wire").checked,
      },
    },
    drawing: {
      enabled: $("draw-enabled").checked,
      sheet: {
        size: $("sheet-size").value,
        orientation: $("sheet-orient").value,
        margin_mm: SCHEMA.defaults.drawing.sheet.margin_mm,
        frame: $("sheet-frame").checked,
        title_block: $("sheet-tb").checked,
      },
      layout: $("layout").value,
      scale_mode: $("scale-mode").value,
      font_scale: Number($("font-scale").value),
      sections_column_fraction: Number($("sections-width").value),
      views: chipValues("draw-views"),
      view_style: {
        shaded: $("vs-shaded").checked,
        silhouette: $("vs-silhouette").checked,
        feature_edges: $("vs-feature").checked,
        section_curves: $("vs-sections").checked,
        wireframe: $("vs-wire").checked,
        labels: $("vs-labels").checked,
        shading_strength: Number($("vs-strength").value),
      },
      sections: {
        enabled: $("sec-enabled").checked,
        which: chipValues("sec-which"),
        common_scale: $("sec-common").checked,
        scale: $("sec-scale").value.trim() || null,
        grid: $("sec-grid").checked,
        annotations,
      },
      param_table: $("param-table").checked,
      title: $("title").value,
      drawn_by: $("drawn-by").value,
      notes: $("notes").value,
      formats: { png: $("fmt-png").checked, pdf: $("fmt-pdf").checked, svg: $("fmt-svg").checked },
      dpi: Number($("dpi").value),
    },
  };
}

async function startRender() {
  $("render").disabled = true;
  setStatus("running", "Rendering…");
  $("log").hidden = false;
  $("log").textContent = "";
  $("gallery").innerHTML = "";

  const body = {
    params: collectParams(),
    settings: collectSettings(),
    title: $("title").value,
    allow_out_of_range: $("allow-oor").checked,
    rhino: { url: $("rhino-url").value || null },
  };
  const res = await fetch("/api/render", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const { job } = await res.json();
  POLL = setInterval(() => pollJob(job), 700);
}

async function pollJob(job) {
  const j = await (await fetch(`/api/job/${job}`)).json();
  $("log").textContent = (j.log || []).join("\n");
  $("log").scrollTop = $("log").scrollHeight;
  if (j.status === "running") return;
  clearInterval(POLL);
  $("render").disabled = false;
  if (j.status === "error") {
    setStatus("error", j.error || "Failed.");
    return;
  }
  setStatus("ok", `Done in ${j.manifest.total_seconds}s — ${j.manifest.run}`);
  showResults(j.manifest);
  loadHistory();
}

function setStatus(kind, text) {
  const el = $("status");
  el.className = `status ${kind}`;
  el.textContent = text;
}

function showResults(m) {
  const g = $("gallery");
  g.innerHTML = "";
  const base = m.run_url_base;
  if (m.drawing && m.drawing.files) {
    const card = document.createElement("div");
    card.className = "card wide";
    const links = Object.keys(m.drawing.files)
      .map((f) => `<a href="${base}/drawing.${f}" target="_blank">${f.toUpperCase()}</a>`)
      .join(" · ");
    const img = m.drawing.files.png ? `<img src="${base}/drawing.png?t=${Date.now()}">` : "";
    card.innerHTML = `<h3>Technical drawing <small>views ${m.drawing.view_scale || "—"},
      sections ${m.drawing.section_scale || "—"}</small></h3>${img}<p>${links}</p>`;
    g.appendChild(card);
  }
  for (const r of m.renders) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>${r.name}</h3>
      <a href="${base}/renders/${r.file}" target="_blank">
      <img src="${base}/renders/${r.file}?t=${Date.now()}"></a>`;
    g.appendChild(card);
  }
}

async function loadHistory() {
  const runs = await (await fetch("/api/runs")).json();
  $("history").innerHTML = runs.map((r) =>
    `<div class="hist"><code>${r.run}</code> <span>${r.backend}</span>
     ${r.drawing ? `<a href="/api/file/${r.run}/drawing.png" target="_blank">drawing</a>` : ""}
     <span class="dim">${r.renders.length} render(s)</span></div>`).join("");
}

async function applyPreset() {
  const name = $("preset").value;
  if (!name) return;
  const preset = await (await fetch(`/api/preset/${name}`)).json();
  applySettings(preset);
  setStatus("idle", `Loaded preset "${name}".`);
}

// A preset is a PARTIAL settings tree, so only the keys it actually carries are
// applied -- everything else keeps whatever the form already shows.
function applySettings(s) {
  const r = s.render || {}, d = s.drawing || {};
  if (s.backend) {
    const el = document.querySelector(`input[name=backend][value="${s.backend}"]`);
    if (el) el.checked = true;
  }
  if (r.projection) $("projection").value = r.projection;
  if (r.width) $("width").value = r.width;
  if (r.height) $("height").value = r.height;
  if (r.zoom) $("zoom").value = r.zoom;
  if (r.enabled !== undefined) $("render-enabled").checked = r.enabled;
  if (r.background) {
    const b = r.background;
    if (b.mode) $("bg-mode").value = b.mode;
    if (b.color) $("bg-color").value = b.color;
    if (b.color2) $("bg-color2").value = b.color2;
    if (b.floor_color) $("bg-floor").value = b.floor_color;
    if (b.shadow !== undefined) $("bg-shadow").checked = b.shadow;
  }
  if (r.lighting) {
    if (r.lighting.preset) $("lighting").value = r.lighting.preset;
    if (r.lighting.intensity) $("intensity").value = r.lighting.intensity;
  }
  if (r.material) {
    if (r.material.mode) {
      const el = document.querySelector(`input[name=matmode][value="${r.material.mode}"]`);
      if (el) { el.checked = true; el.dispatchEvent(new Event("change")); }
    }
    const u = r.material.uniform || {};
    if (u.color) $("uni-color").value = u.color;
    if (u.metallic !== undefined) $("uni-metallic").value = u.metallic;
    if (u.roughness !== undefined) $("uni-roughness").value = u.roughness;
    if (u.opacity !== undefined) $("uni-opacity").value = u.opacity;
    for (const [name, m] of Object.entries(r.material.parts || {})) {
      if ($(`pc_${name}`)) {
        if (m.color) $(`pc_${name}`).value = m.color;
        if (m.metallic !== undefined) $(`pm_${name}`).value = m.metallic;
        if (m.roughness !== undefined) $(`pr_${name}`).value = m.roughness;
        if (m.opacity !== undefined) $(`po_${name}`).value = m.opacity;
      }
    }
  }
  if (r.overlays) {
    const o = r.overlays;
    if (o.silhouette !== undefined) $("ov-silhouette").checked = o.silhouette;
    if (o.feature_edges !== undefined) $("ov-feature").checked = o.feature_edges;
    if (o.feature_angle !== undefined) $("ov-feature-angle").value = o.feature_angle;
    if (o.section_curves !== undefined) $("ov-sections").checked = o.section_curves;
    if (o.section_curves_on_top !== undefined) $("ov-sections-top").checked = o.section_curves_on_top;
    if (o.wireframe !== undefined) $("ov-wire").checked = o.wireframe;
  }
  if (d.enabled !== undefined) $("draw-enabled").checked = d.enabled;
  if (d.layout) $("layout").value = d.layout;
  if (d.scale_mode) $("scale-mode").value = d.scale_mode;
  if (d.font_scale) $("font-scale").value = d.font_scale;
  if (d.sections_column_fraction) $("sections-width").value = d.sections_column_fraction;
  if (d.param_table !== undefined) $("param-table").checked = d.param_table;
  if (d.dpi) $("dpi").value = d.dpi;
  if (d.sheet) {
    if (d.sheet.size) $("sheet-size").value = d.sheet.size;
    if (d.sheet.orientation) $("sheet-orient").value = d.sheet.orientation;
    if (d.sheet.frame !== undefined) $("sheet-frame").checked = d.sheet.frame;
    if (d.sheet.title_block !== undefined) $("sheet-tb").checked = d.sheet.title_block;
  }
  if (d.view_style) {
    const v = d.view_style;
    if (v.shaded !== undefined) $("vs-shaded").checked = v.shaded;
    if (v.silhouette !== undefined) $("vs-silhouette").checked = v.silhouette;
    if (v.feature_edges !== undefined) $("vs-feature").checked = v.feature_edges;
    if (v.section_curves !== undefined) $("vs-sections").checked = v.section_curves;
    if (v.wireframe !== undefined) $("vs-wire").checked = v.wireframe;
    if (v.labels !== undefined) $("vs-labels").checked = v.labels;
    if (v.shading_strength !== undefined) $("vs-strength").value = v.shading_strength;
  }
  if (d.sections) {
    const sc = d.sections;
    if (sc.enabled !== undefined) $("sec-enabled").checked = sc.enabled;
    if (sc.common_scale !== undefined) $("sec-common").checked = sc.common_scale;
    if (sc.scale !== undefined) $("sec-scale").value = sc.scale === null ? "" : sc.scale;
    if (sc.grid !== undefined) $("sec-grid").checked = sc.grid;
    if (sc.which) {
      for (const k of ["inner", "middle", "outer"]) {
        const el = $(`sec-which_${k}`);
        if (el) el.checked = sc.which.includes(k);
      }
    }
    for (const [k, v] of Object.entries(sc.annotations || {})) {
      if ($(`an_${k}`)) $(`an_${k}`).checked = v;
    }
  }
  if (d.formats) {
    if (d.formats.png !== undefined) $("fmt-png").checked = d.formats.png;
    if (d.formats.pdf !== undefined) $("fmt-pdf").checked = d.formats.pdf;
    if (d.formats.svg !== undefined) $("fmt-svg").checked = d.formats.svg;
  }
  if (d.views) {
    for (const k of Object.keys(SCHEMA.named_views)) {
      const el = $(`draw-views_${k}`);
      if (el) el.checked = d.views.includes(k);
    }
  }
  if (r.views) {
    for (const k of Object.keys(SCHEMA.named_views)) {
      const el = $(`render-views_${k}`);
      if (el) el.checked = r.views.includes(k);
    }
  }
  document.querySelectorAll("input[type=range]").forEach((el) =>
    el.dispatchEvent(new Event("input")));
}

async function savePreset() {
  const name = prompt("Save these settings as a preset named:");
  if (!name) return;
  const res = await fetch(`/api/preset/${encodeURIComponent(name)}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectSettings()),
  });
  const j = await res.json();
  if (![...$("preset").options].some((o) => o.value === j.saved)) {
    const o = document.createElement("option");
    o.value = o.textContent = j.saved;
    $("preset").appendChild(o);
  }
  $("preset").value = j.saved;
  setStatus("ok", `Saved preset "${j.saved}".`);
}

boot();
