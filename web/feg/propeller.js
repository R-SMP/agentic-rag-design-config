// Assemble the full front-end-geometry (FEG) propeller from a 17-parameter
// dict and return it as a THREE.Group (blade InstancedMesh ×bladeCount +
// swept-ellipse ring + placeholder hub).
//
// This is the geometry half of the reference's core.js (buildAllSections() +
// rebuild3D()), refactored to return a self-contained Group instead of
// mutating a shared scene.  The 2D section overlays / slider-graying from the
// reference are intentionally NOT ported here — those belong to the deferred
// blade-section views (see extra_utilities/web_interface_notes.md).
//
// Built in the GH/Rhino coordinate convention (Z = propeller axis).  The
// caller (web/viewer.js) applies the same -90° X-rotation it already uses for
// loaded RhinoCompute OBJs, so the FEG preview and the RCG share an
// orientation.

import * as THREE from 'three';
import { CONSTANTS } from './constants.js';
import { buildPlacedSection, buildBladeGeometry } from './blade.js';
import { interpolateMiddleParams } from './profiles.js';
import { computeRingDimensions, buildRingGeometry } from './ring.js';
import { buildHubGeometry } from './hub.js';

// Mirrors core.js:buildAllSections — the three placed cross-sections.
function buildAllSections(params) {
  const innerSection = buildPlacedSection({
    thickness: params.innerThickness,
    highPt:    params.innerMaxPos,
    camber:    params.innerCamber,
    chord:     params.innerChord,
    angle:     params.innerAngle,
    radius:    CONSTANTS.innerRadiusFixed,
    countI:    CONSTANTS.countI,
    project:   false,
  });

  const midP = interpolateMiddleParams(
    params.middlePos,
    { thickness: params.innerThickness, highPt: params.innerMaxPos, camber: params.innerCamber },
    { thickness: params.outerThickness, highPt: params.outerMaxPos, camber: params.outerCamber },
    params.impellerRadius,
  );
  const middleSection = buildPlacedSection({
    thickness: midP.thickness,
    highPt:    midP.highPt,
    camber:    midP.camber,
    chord:     params.middleChord,
    angle:     params.middleAngle,
    radius:    midP.radius,
    countI:    CONSTANTS.countI,
    project:   false,
  });

  const outerSection = buildPlacedSection({
    thickness:        params.outerThickness,
    highPt:           params.outerMaxPos,
    camber:           params.outerCamber,
    chord:            params.outerChord,
    angle:            params.outerAngle,
    radius:           params.impellerRadius,
    countI:           CONSTANTS.countI,
    project:          true,
    projectionRadius: params.impellerRadius,
  });

  return { innerSection, middleSection, outerSection };
}

// Build the three section outline curves (Inner/Middle/Outer) as closed
// THREE.Line loops over the same placed section points the blade lofts
// through.  Default blue; the Viewer recolors the tab-active section green
// (see Viewer.setActiveProfile).  Drawn over the mesh (depthTest:false,
// renderOrder 2) so they read on top of the blade.  Mirrors the reference's
// core.js:rebuildProfileLines.
function buildProfileLines({ innerSection, middleSection, outerSection }) {
  const sections = {
    InnerProfile:  innerSection,
    MiddleProfile: middleSection,
    OuterProfile:  outerSection,
  };
  const lines = [];
  for (const name of Object.keys(sections)) {
    const pts = sections[name];
    const positions = new Float32Array((pts.length + 1) * 3);
    for (let i = 0; i < pts.length; i++) {
      positions[i * 3]     = pts[i].x;
      positions[i * 3 + 1] = pts[i].y;
      positions[i * 3 + 2] = pts[i].z;
    }
    // Close the loop back to the first point.
    positions[pts.length * 3]     = pts[0].x;
    positions[pts.length * 3 + 1] = pts[0].y;
    positions[pts.length * 3 + 2] = pts[0].z;

    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.LineBasicMaterial({
      color: 0x2196f3,          // blue (default); active tab -> green
      transparent: true,
      opacity: 1.0,
      depthTest: false,
      depthWrite: false,
    });
    const line = new THREE.Line(geom, mat);
    line.name = name;
    line.userData.isProfileLine = true;
    line.renderOrder = 2;
    lines.push(line);
  }
  return lines;
}

/**
 * Build the FEG propeller for `params` using the supplied `material` for
 * every surface (blade, ring, hub share one material so they read as one
 * body).  Returns a THREE.Group; the caller owns disposal of its child
 * geometries.
 *
 * @param {object} params  the 17 canonical parameters (raw geom units).
 * @param {THREE.Material} material  shared surface material.
 * @returns {THREE.Group}
 */
export function buildPropellerGroup(params, material) {
  const group = new THREE.Group();
  const { innerSection, middleSection, outerSection } = buildAllSections(params);

  // Blade loft, instanced bladeCount times around Z.
  const bladeGeom = buildBladeGeometry({
    innerSection, middleSection, outerSection,
    middlePos: params.middlePos,
    ringSteps: CONSTANTS.bladeRingSteps,
  });
  const count = Math.max(1, Math.floor(params.bladeCount));
  const bladeMesh = new THREE.InstancedMesh(bladeGeom, material, count);
  const dummy = new THREE.Object3D();
  for (let i = 0; i < count; i++) {
    dummy.rotation.set(0, 0, 2 * Math.PI * i / count);
    dummy.updateMatrix();
    bladeMesh.setMatrixAt(i, dummy.matrix);
  }
  bladeMesh.instanceMatrix.needsUpdate = true;
  group.add(bladeMesh);

  // Outer ring sized from the projected outer section.
  const ringDims = computeRingDimensions(
    outerSection, params.impellerHeight,
    CONSTANTS.clearance, CONSTANTS.safetyMargin,
  );
  const ringGeom = buildRingGeometry(
    params.impellerRadius, params.impellerThickness,
    ringDims.finalHeight, ringDims.centerZ,
    Math.max(24, CONSTANTS.countI * 2), CONSTANTS.ringAngularSegments,
  );
  group.add(new THREE.Mesh(ringGeom, material));

  // Hub placeholder (geometry is invariant).
  group.add(new THREE.Mesh(buildHubGeometry(), material));

  // Section outline curves (recolored per active tab by the Viewer).
  for (const line of buildProfileLines({ innerSection, middleSection, outerSection })) {
    group.add(line);
  }

  return group;
}
