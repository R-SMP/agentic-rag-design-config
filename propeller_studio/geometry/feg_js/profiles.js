// Helpers for the middle-section parameter interpolation (mid_profile_1.cs)
// and the outer-section radial projection onto the impeller cylinder
// (outer_profile.cs:137-176).
//
// Ported verbatim from the propeller-browser reference (geom/profiles.js)
// for the in-browser FEG preview.

import * as THREE from 'three';

// Linear interpolation of inner -> outer NACA shape parameters plus radius.
// Inner radius is fixed at 4.0 (inner_profile.cs:133); outer radius is the
// impeller radius. middlePos in [0, 1] is the slider value.
export function interpolateMiddleParams(middlePos, innerParams, outerParams, impellerRadius) {
  const t = Math.max(0, Math.min(1, middlePos));
  return {
    thickness: innerParams.thickness + (outerParams.thickness - innerParams.thickness) * t,
    highPt:    innerParams.highPt    + (outerParams.highPt    - innerParams.highPt)    * t,
    camber:    innerParams.camber    + (outerParams.camber    - innerParams.camber)    * t,
    radius:    4.0                   + (impellerRadius        - 4.0)                   * t,
  };
}

// Project an array of points radially onto a cylinder of given radius whose
// axis coincides with the world Z axis. For each point, keep Z, then scale
// (X, Y) so that sqrt(X² + Y²) equals the cylinder radius.
export function projectOntoCylinder(pts3D, cylinderRadius) {
  return pts3D.map(p => {
    const radial = Math.sqrt(p.x * p.x + p.y * p.y);
    if (radial < 1e-9) return p.clone();
    const k = cylinderRadius / radial;
    return new THREE.Vector3(p.x * k, p.y * k, p.z);
  });
}
