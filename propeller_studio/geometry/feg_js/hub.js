// Placeholder hub mirroring interface.cs:
//   Circle(center=(0, 0, baseZ), radius), extruded along +Z by `height`.
// The cylinder spans Z = baseZ .. baseZ + height. Three.js CylinderGeometry's
// default axis is Y; rotate around X by +π/2 to align it with Z.
//
// Ported from the propeller-browser reference (geom/hub.js) for the
// in-browser FEG preview.  Only the CONSTANTS import path differs from the
// reference (./constants.js instead of the standalone's _shared/params.js).

import * as THREE from 'three';
import { CONSTANTS } from './constants.js';

export function buildHubGeometry() {
  const { radius, baseZ, height } = CONSTANTS.hub;
  const geom = new THREE.CylinderGeometry(radius, radius, height, 64);
  geom.rotateX(Math.PI / 2);                     // Y-axis -> Z-axis
  geom.translate(0, 0, baseZ + height * 0.5);    // base at z = baseZ, top at z = baseZ + height
  return geom;
}
