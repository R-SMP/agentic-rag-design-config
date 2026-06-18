// Place a 2D morphed airfoil into 3D world space, faithful to the GH chain
// scale -> mirror across y=chord/4 -> rotate around X axis -> translate by (radius, 0, 0).
//
// Coordinate convention (GH propeller_V3):
//   X = radial (out from rotation axis)
//   Y = chordwise (after mirror: LE at +Y, TE at -Y)
//   Z = axial / propeller rotation axis (thrust direction)
//
// Note: the rotation pivot is the X axis through the WORLD origin, not the
// quarter-chord. After mirror, the quarter-chord sits at Y=chord/4, so the
// airfoil's quarter-chord swings around X by chord/4 as the angle changes.
// This is what the GH definition does — preserve it.
//
// Ported verbatim from the propeller-browser reference (geom/placement.js)
// for the in-browser FEG preview.

import * as THREE from 'three';

export function placeProfile(pts2D, chord, angleDeg, radius) {
  const angle = angleDeg * Math.PI / 180;
  const ca = Math.cos(angle);
  const sa = Math.sin(angle);
  const half = chord * 0.5;

  return pts2D.map(p => {
    const yS = p.y * chord;
    const zS = p.z * chord;
    const yM = half - yS;            // mirror across plane Y = chord/4 (y' = chord/2 - y)
    const zM = zS;
    const yR = yM * ca - zM * sa;    // rotate around X axis at origin
    const zR = yM * sa + zM * ca;
    return new THREE.Vector3(radius, yR, zR);
  });
}
