// Outer ring construction faithful to
//   ring_height_based_on _outer.cs  (Z-bounds from the cylinder-projected outer profile)
//   ring.cs                          (ellipse swept around impeller circle)
//
// Geometry: a meridional ellipse with semi-axes (impellerThickness/2, finalHeight/2)
// centered at (impellerRadius, 0, centerZ), revolved around the Z axis.
//
// Ported verbatim from the propeller-browser reference (geom/ring.js) for
// the in-browser FEG preview.

import * as THREE from 'three';

// Compute ring height and Z-center from the outer profile's Z extent.
//   ringBottomZ = zMin - clearance
//   ringTopZ    = zMax + clearance
//   fittedHeight = (zMax - zMin) + 2·clearance
// finalHeight uses the input impellerHeight only if it exceeds fittedHeight
// by at least safetyMargin; otherwise fall back to fittedHeight.
export function computeRingDimensions(outerProfilePts3D, impellerHeight, clearance, safetyMargin) {
  let zMin = Infinity, zMax = -Infinity;
  for (const p of outerProfilePts3D) {
    if (p.z < zMin) zMin = p.z;
    if (p.z > zMax) zMax = p.z;
  }
  const ringBottomZ = zMin - clearance;
  const ringTopZ    = zMax + clearance;
  const fittedHeight = (zMax - zMin) + 2 * clearance;

  const useInput = impellerHeight >= fittedHeight + safetyMargin;
  const finalHeight = useInput ? impellerHeight : fittedHeight;
  const centerZ = 0.5 * (ringTopZ + ringBottomZ);

  return {
    ringBottomZ, ringTopZ,
    fittedHeight, finalHeight, centerZ,
    usedInputHeight: useInput,
  };
}

// Build the swept-ellipse ring as a BufferGeometry.
//   M = points around the meridional ellipse
//   N = angular subdivisions around Z
export function buildRingGeometry(impellerRadius, impellerThickness, finalHeight, centerZ, M, N) {
  const aRad = impellerThickness * 0.5;   // radial semi-axis (X)
  const bAxi = finalHeight       * 0.5;   // axial semi-axis  (Z)

  // Meridional ellipse in the XZ plane at azimuth 0.
  const cross = new Array(M);
  for (let i = 0; i < M; i++) {
    const phi = 2 * Math.PI * i / M;
    cross[i] = {
      x: impellerRadius + aRad * Math.cos(phi),
      z: centerZ        + bAxi * Math.sin(phi),
    };
  }

  // Revolve around Z. At azimuth theta, meridional (Xm, Zm) maps to
  // (Xm·cosθ, Xm·sinθ, Zm).
  const positions = new Float32Array(M * N * 3);
  for (let j = 0; j < N; j++) {
    const theta = 2 * Math.PI * j / N;
    const ct = Math.cos(theta);
    const st = Math.sin(theta);
    for (let i = 0; i < M; i++) {
      const Xm = cross[i].x;
      const Zm = cross[i].z;
      const idx = (j * M + i) * 3;
      positions[idx]     = Xm * ct;
      positions[idx + 1] = Xm * st;
      positions[idx + 2] = Zm;
    }
  }

  const indices = new Uint32Array(M * N * 6);
  let k = 0;
  for (let j = 0; j < N; j++) {
    const j2 = (j + 1) % N;
    for (let i = 0; i < M; i++) {
      const i2 = (i + 1) % M;
      const v0 = j  * M + i;
      const v1 = j  * M + i2;
      const v2 = j2 * M + i2;
      const v3 = j2 * M + i;
      // Wound so computeVertexNormals() yields OUTWARD normals (matches blade +
      // hub). Inward winding renders fine in the DoubleSide browser preview but
      // shades dull/inverted in the single-normal render_mesh (pyrender) pass.
      indices[k++] = v0; indices[k++] = v2; indices[k++] = v1;
      indices[k++] = v0; indices[k++] = v3; indices[k++] = v2;
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geom.setIndex(new THREE.BufferAttribute(indices, 1));
  geom.computeVertexNormals();
  return geom;
}
