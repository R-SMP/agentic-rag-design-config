// Blade construction:
//   1) Build the three placed 3D sections (inner, middle, outer) via
//      buildPlacedSection — NACA + camber morph + scale + mirror + rotate +
//      translate, plus cylinder projection for the outer section.
//   2) Loft across the three sections in placed-3D space using Lagrange
//      interpolation with knots at (0, middlePos, 1) — visually similar to
//      the GH 2-rail sweep through 3 cross-sections (blades.cs), per the
//      "visually faithful" decision.
//
// Ported verbatim from the propeller-browser reference (geom/blade.js) for
// the in-browser FEG preview.

import * as THREE from 'three';
import { buildSymmetricProfile, buildCamberCurve, morphProfileOntoCamber } from './naca.js';
import { placeProfile } from './placement.js';
import { projectOntoCylinder } from './profiles.js';

// Build one placed section as an array of THREE.Vector3 in world coords.
// All three sections share the same M = 2·countI + 1 point indexing so the
// loft can interpolate corresponding points across sections.
export function buildPlacedSection({ thickness, highPt, camber, chord, angle, radius, countI, project = false, projectionRadius = 0 }) {
  const sym = buildSymmetricProfile(countI, thickness);
  const cam = buildCamberCurve(highPt, camber);
  const morphed = morphProfileOntoCamber(sym, cam);
  const placed  = placeProfile(morphed, chord, angle, radius);
  return project ? projectOntoCylinder(placed, projectionRadius) : placed;
}

// Loft the blade as a triangulated mesh.
//   innerSection, middleSection, outerSection: parallel arrays of THREE.Vector3 (length M).
//   middlePos: parametric position of the middle section in [0, 1].
//   ringSteps: number of segments along the radial loft direction.
//
// At each row t ∈ [0, 1], the row position is a Lagrange interpolation of
// the three sections' i-th points. The side wall is triangulated as quads;
// root and tip caps are triangle fans to a centroid.
export function buildBladeGeometry({ innerSection, middleSection, outerSection, middlePos, ringSteps }) {
  const M = innerSection.length;
  const R = Math.max(2, ringSteps | 0);

  // Clamp middlePos away from the endpoints to keep the Lagrange basis well-conditioned.
  const mPar = Math.min(0.95, Math.max(0.05, middlePos));
  const basis = (t) => {
    const L0 = (t - mPar) * (t - 1)    / ((0    - mPar) * (0    - 1));
    const L1 =  t         * (t - 1)    / ((mPar - 0)    * (mPar - 1));
    const L2 =  t         * (t - mPar) / ((1    - 0)    * (1    - mPar));
    return [L0, L1, L2];
  };

  const sideVerts  = (R + 1) * M;
  const totalVerts = sideVerts + 2;        // + 2 cap centroids
  const positions  = new Float32Array(totalVerts * 3);

  for (let row = 0; row <= R; row++) {
    const t = row / R;
    const [L0, L1, L2] = basis(t);
    for (let i = 0; i < M; i++) {
      const pIn  = innerSection[i];
      const pMid = middleSection[i];
      const pOut = outerSection[i];
      const idx = (row * M + i) * 3;
      positions[idx]     = L0 * pIn.x  + L1 * pMid.x  + L2 * pOut.x;
      positions[idx + 1] = L0 * pIn.y  + L1 * pMid.y  + L2 * pOut.y;
      positions[idx + 2] = L0 * pIn.z  + L1 * pMid.z  + L2 * pOut.z;
    }
  }

  // Cap centroids
  let cInX = 0, cInY = 0, cInZ = 0;
  let cOutX = 0, cOutY = 0, cOutZ = 0;
  for (let i = 0; i < M; i++) {
    const a = i * 3;
    cInX  += positions[a];     cInY  += positions[a + 1]; cInZ  += positions[a + 2];
    const b = (R * M + i) * 3;
    cOutX += positions[b];     cOutY += positions[b + 1]; cOutZ += positions[b + 2];
  }
  cInX /= M; cInY /= M; cInZ /= M;
  cOutX /= M; cOutY /= M; cOutZ /= M;
  const inCi  = sideVerts;
  const outCi = sideVerts + 1;
  positions[inCi  * 3]     = cInX;
  positions[inCi  * 3 + 1] = cInY;
  positions[inCi  * 3 + 2] = cInZ;
  positions[outCi * 3]     = cOutX;
  positions[outCi * 3 + 1] = cOutY;
  positions[outCi * 3 + 2] = cOutZ;

  // Indices: side wall + 2 fan caps.
  const sideTris = R * M * 2;
  const capTris  = M * 2;
  const indices = new Uint32Array((sideTris + capTris) * 3);
  let k = 0;
  for (let row = 0; row < R; row++) {
    for (let i = 0; i < M; i++) {
      const i2 = (i + 1) % M;
      const a = row * M + i;
      const b = row * M + i2;
      const c = (row + 1) * M + i2;
      const d = (row + 1) * M + i;
      indices[k++] = a; indices[k++] = b; indices[k++] = c;
      indices[k++] = a; indices[k++] = c; indices[k++] = d;
    }
  }
  // Root cap (inner end, opposite winding to tip).
  for (let i = 0; i < M; i++) {
    const i2 = (i + 1) % M;
    indices[k++] = inCi;
    indices[k++] = i2;
    indices[k++] = i;
  }
  // Tip cap (outer end).
  for (let i = 0; i < M; i++) {
    const i2 = (i + 1) % M;
    indices[k++] = outCi;
    indices[k++] = R * M + i;
    indices[k++] = R * M + i2;
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geom.setIndex(new THREE.BufferAttribute(indices, 1));
  geom.computeVertexNormals();
  return geom;
}
