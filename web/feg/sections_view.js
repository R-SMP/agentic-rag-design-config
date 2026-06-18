// "Blade sections" 2D view for the params-inputs left pane.
//
// Draws all three blade-section airfoils stacked vertically (Inner top,
// Middle, Outer bottom) on a light-gray 1 mm grid, at a single shared scale
// chosen to fit the pane, plus a bottom-right protractor showing each
// section's angle of attack as a colour-matched ray.
//
// Reuses the airfoil point math from ./curves.js (buildSectionPoints — the
// morphed NACA section, rotated by its angle of attack, in mm).  The grid +
// protractor are NOT in the reference example; they are v9-specific.

import { buildSectionPoints } from './curves.js';

// Top-to-bottom order + per-section colour (shape fill/stroke AND protractor
// ray share the colour so a ray maps obviously to its shape).
const SECTIONS = [
  { kind: 'inner',  label: 'Inner',  angleKey: 'innerAngle',  color: '#2563eb' }, // blue
  { kind: 'middle', label: 'Middle', angleKey: 'middleAngle', color: '#16a34a' }, // green
  { kind: 'outer',  label: 'Outer',  angleKey: 'outerAngle',  color: '#dc2626' }, // red
];

const BG_COLOR        = '#f7f7f7';   // near-white, matches the 3D viewer
const GRID_MINOR      = '#dcdcdc';   // 1 mm lines
const GRID_MAJOR      = '#c4c4c4';   // every 5 mm
const MAJOR_EVERY_MM  = 5;
const PROTRACTOR_MAX_DEG = 25;       // angle-of-attack range top

function bbox(pts) {
  let xmin = Infinity, xmax = -Infinity, zmin = Infinity, zmax = -Infinity;
  for (const p of pts) {
    if (p.x < xmin) xmin = p.x;
    if (p.x > xmax) xmax = p.x;
    if (p.z < zmin) zmin = p.z;
    if (p.z > zmax) zmax = p.z;
  }
  return { w: xmax - xmin, h: zmax - zmin, cx: (xmin + xmax) / 2, cz: (zmin + zmax) / 2 };
}

// '#rrggbb' + alpha -> 'rgba(r,g,b,a)'.
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawGrid(ctx, w, h, pxPerMm) {
  // 1 mm minor lines (skipped if they'd be denser than ~3 px to avoid moiré).
  if (pxPerMm >= 3) {
    ctx.strokeStyle = GRID_MINOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = 0; x <= w; x += pxPerMm) {
      const px = Math.round(x) + 0.5;
      ctx.moveTo(px, 0); ctx.lineTo(px, h);
    }
    for (let y = 0; y <= h; y += pxPerMm) {
      const py = Math.round(y) + 0.5;
      ctx.moveTo(0, py); ctx.lineTo(w, py);
    }
    ctx.stroke();
  }
  // 5 mm major lines.
  const step = pxPerMm * MAJOR_EVERY_MM;
  ctx.strokeStyle = GRID_MAJOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0; x <= w; x += step) {
    const px = Math.round(x) + 0.5;
    ctx.moveTo(px, 0); ctx.lineTo(px, h);
  }
  for (let y = 0; y <= h; y += step) {
    const py = Math.round(y) + 0.5;
    ctx.moveTo(0, py); ctx.lineTo(w, py);
  }
  ctx.stroke();
}

function drawProtractor(ctx, w, h, secs) {
  const pad = 10;
  const R = Math.max(64, Math.min(140, Math.min(w, h) * 0.26));
  const vx = w - pad;            // vertex at the bottom-right corner
  const vy = h - pad;

  // Faint backdrop panel so the protractor reads over the grid / shapes.
  ctx.fillStyle = 'rgba(255, 255, 255, 0.80)';
  ctx.strokeStyle = '#d0d0d0';
  ctx.lineWidth = 1;
  roundRect(ctx, vx - R - pad - 6, vy - R - pad - 14, R + pad + 6, R + pad + 14, 8);
  ctx.fill();
  ctx.stroke();

  // Title.
  ctx.fillStyle = '#666';
  ctx.font = '600 11px system-ui, sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'top';
  ctx.fillText('Angle of attack', vx - 4, vy - R - pad - 12);

  // Arc baseline (0°, horizontal) + the 0..MAX arc.
  ctx.strokeStyle = '#9a9a9a';
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.moveTo(vx, vy);
  ctx.lineTo(vx - R, vy);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(vx, vy, R, Math.PI, Math.PI + (PROTRACTOR_MAX_DEG * Math.PI) / 180, false);
  ctx.stroke();

  // 5° ticks.
  ctx.strokeStyle = '#b0b0b0';
  ctx.fillStyle = '#888';
  ctx.lineWidth = 1;
  ctx.font = '10px system-ui, sans-serif';
  for (let d = 0; d <= PROTRACTOR_MAX_DEG; d += 5) {
    const a = (d * Math.PI) / 180;
    const c = Math.cos(a), s = Math.sin(a);
    ctx.beginPath();
    ctx.moveTo(vx - (R - 5) * c, vy - (R - 5) * s);
    ctx.lineTo(vx - R * c, vy - R * s);
    ctx.stroke();
  }

  // One ray per section at its angle of attack, in the section colour.
  for (const sec of secs) {
    const a = (Math.max(0, Math.min(PROTRACTOR_MAX_DEG, sec.angle)) * Math.PI) / 180;
    const c = Math.cos(a), s = Math.sin(a);
    const ex = vx - R * c, ey = vy - R * s;
    ctx.strokeStyle = sec.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(vx, vy);
    ctx.lineTo(ex, ey);
    ctx.stroke();
    // degree label just past the ray tip
    ctx.fillStyle = sec.color;
    ctx.font = '600 11px system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${Math.round(sec.angle)}°`, ex - 4, ey - 4);
  }
}

/**
 * Draw the stacked blade-section view into `canvas` from the current 17-param
 * dict.  Self-sizing: backs the canvas buffer with its displayed (CSS) size ×
 * devicePixelRatio for crisp lines.  No-op while the canvas is hidden (0 size).
 */
export function drawBladeSections(canvas, params) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return;

  const bw = Math.round(w * dpr), bh = Math.round(h * dpr);
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  ctx.fillStyle = BG_COLOR;
  ctx.fillRect(0, 0, w, h);

  // Section points + bounding boxes + angle of attack.
  const secs = SECTIONS.map((s) => {
    let pts = [];
    try { pts = buildSectionPoints(s.kind, params); } catch (e) { pts = []; }
    return {
      ...s,
      pts,
      box: pts.length ? bbox(pts) : null,
      angle: Number(params[s.angleKey]) || 0,
    };
  });

  // Shared scale (px per mm) so the worst-case section fits one third of the
  // pane both ways — all sections share it, so their real sizes are
  // comparable on the grid.
  const valid = secs.filter((s) => s.box);
  const maxW = Math.max(1e-3, ...valid.map((s) => s.box.w));
  const maxH = Math.max(1e-3, ...valid.map((s) => s.box.h));
  const bandH = h / 3;
  let pxPerMm = Math.min((w * 0.82) / maxW, (bandH * 0.72) / maxH);
  if (!isFinite(pxPerMm) || pxPerMm <= 0) pxPerMm = 4;

  drawGrid(ctx, w, h, pxPerMm);

  // Airfoils, centred in their band, plus a section-name label.
  const cx = w / 2;
  secs.forEach((s, k) => {
    if (!s.box) return;
    const cy = bandH * (k + 0.5);
    ctx.beginPath();
    for (let i = 0; i < s.pts.length; i++) {
      const px = cx + (s.pts[i].x - s.box.cx) * pxPerMm;
      const py = cy - (s.pts[i].z - s.box.cz) * pxPerMm;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = hexA(s.color, 0.16);
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.6;
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = s.color;
    ctx.font = '600 13px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(s.label, 8, bandH * k + 6);
  });

  drawProtractor(ctx, w, h, secs);
}
