// 2D foil-section preview drawn on a <canvas>.
//
// Ported from the propeller-browser reference (curves.js) for the params
// view's per-section cross-section shapes.  Only the import paths differ
// from the reference (./naca.js / ./profiles.js / ./constants.js instead of
// ./geom/* and ../_shared/params.js).
//
// All canvases share PX_PER_UNIT so sections stay proportional to each other
// (an inner section at max settings is visibly smaller than an outer section
// at max settings).
//
// Coordinate mapping (TE faces left):
//   world x = (0.5 - y_chord) * chord    (so y=1 → x = -chord/2 = TE on the left)
//   world z =  z_morphed     * chord
//   rotate (x, z) around the world origin by `angle` radians
//   canvas px = (centerX + x*scale, centerY - z*scale)

import { buildSymmetricProfile, buildCamberCurve, morphProfileOntoCamber } from './naca.js';
import { interpolateMiddleParams } from './profiles.js';
import { CONSTANTS } from './constants.js';

// Shared scale (px per world-unit). 7 px/unit means a canvas of 360x180 shows
// ~51 x 26 units; the worst-case rotated bbox (chord 30, angle 25°, thick 24%,
// camber 9%) has y-extent ≈ 22 units, fitting with margin.
export const PX_PER_UNIT = 7;

// Default canvas dimensions (HTML can override via width/height attributes).
export const CANVAS_W = 360;
export const CANVAS_H = 180;

const ACTIVE_FILL  = 'rgba(66, 168, 50, 0.18)';
const ACTIVE_LINE  = '#42a832'; // matches the 3D active section outline (green)
const DIM_FILL     = 'rgba(150, 180, 210, 0.18)';
const DIM_LINE     = '#3d7ad1';

function sectionParams(kind, params) {
  if (kind === 'inner') {
    return {
      thickness: params.innerThickness,
      highPt:    params.innerMaxPos,
      camber:    params.innerCamber,
      chord:     params.innerChord,
      angleDeg:  params.innerAngle,
    };
  }
  if (kind === 'outer') {
    return {
      thickness: params.outerThickness,
      highPt:    params.outerMaxPos,
      camber:    params.outerCamber,
      chord:     params.outerChord,
      angleDeg:  params.outerAngle,
    };
  }
  // middle: thickness/highPt/camber come from inner→outer interpolation
  const m = interpolateMiddleParams(
    params.middlePos,
    { thickness: params.innerThickness, highPt: params.innerMaxPos, camber: params.innerCamber },
    { thickness: params.outerThickness, highPt: params.outerMaxPos, camber: params.outerCamber },
    params.impellerRadius,
  );
  return {
    thickness: m.thickness,
    highPt:    m.highPt,
    camber:    m.camber,
    chord:     params.middleChord,
    angleDeg:  params.middleAngle,
  };
}

// Build the 2D world-space points (TE-on-left coord, then rotated by angle).
function buildSectionPoints(kind, params) {
  const { thickness, highPt, camber, chord, angleDeg } = sectionParams(kind, params);

  const sym = buildSymmetricProfile(CONSTANTS.countI, thickness);
  const cam = buildCamberCurve(highPt, camber);
  const morphed = morphProfileOntoCamber(sym, cam);

  const angle = angleDeg * Math.PI / 180;
  const ca = Math.cos(angle);
  const sa = Math.sin(angle);

  return morphed.map(p => {
    const xw = (0.5 - p.y) * chord;
    const zw = p.z * chord;
    return {
      x: xw * ca - zw * sa,
      z: xw * sa + zw * ca,
    };
  });
}

export function drawProfile2D(canvas, kind, params, { active = true } = {}) {
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;

  ctx.clearRect(0, 0, w, h);

  // Cross-hair through origin (chord-line reference).
  ctx.strokeStyle = '#eaeaea';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, cy); ctx.lineTo(w, cy);
  ctx.moveTo(cx, 0); ctx.lineTo(cx, h);
  ctx.stroke();

  const pts = buildSectionPoints(kind, params);
  if (!pts.length) return;

  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    const px = cx + pts[i].x * PX_PER_UNIT;
    const py = cy - pts[i].z * PX_PER_UNIT;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();

  ctx.fillStyle   = active ? ACTIVE_FILL : DIM_FILL;
  ctx.strokeStyle = active ? ACTIVE_LINE : DIM_LINE;
  ctx.lineWidth   = 1.5;
  ctx.fill();
  ctx.stroke();
}
