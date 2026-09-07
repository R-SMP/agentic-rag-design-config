// Headless Node exporter for propeller_studio -- the FEG (.js) geometry backend.
//
// Differs from tools/generate_mesh/feg_export.mjs in two ways that the studio
// needs and that one cannot provide:
//
//   1. Parts stay TAGGED (blade / ring / hub) instead of being flattened into
//      one anonymous soup, so each can take its own colour and material.
//   2. The three section outline curves are KEPT.  feg_export.mjs skips them
//      as "display-only"; here they are the curves the technical drawing puts
//      on top of the 3D geometry.
//
// Usage:  node feg_export_parts.mjs '<params-json>'
//         JSON -> stdout, one-line stats -> stderr.
//
// Reads the VENDORED ./feg_js/ copy of web/feg, so this package can be lifted
// into its own repository as-is.  dev/drift_check.py diffs that copy against
// web/feg.

import * as THREE from 'three';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const propellerUrl = pathToFileURL(
  resolve(__dirname, 'feg_js', 'propeller.js'),
).href;
const { buildPropellerGroup } = await import(propellerUrl);

const params = JSON.parse(process.argv[2] || '{}');
const material = new THREE.MeshStandardMaterial();
const group = buildPropellerGroup(params, material);
group.updateMatrixWorld(true);

const parts = {};
const sections = {};
const v = new THREE.Vector3();
const instMat = new THREE.Matrix4();
const full = new THREE.Matrix4();

// Section outline curves are named InnerProfile / MiddleProfile / OuterProfile
// by propeller.js:buildProfileLines.
const SECTION_BY_LINE_NAME = {
  InnerProfile: 'inner',
  MiddleProfile: 'middle',
  OuterProfile: 'outer',
};

function emptyPart() {
  return { positions: [], indices: [], instances: 0 };
}

// Bake one mesh (or every instance of an InstancedMesh) into explicit
// world-space triangles appended to `part`.
function bake(part, obj) {
  const geom = obj.geometry;
  const pos = geom.attributes.position;
  const idx = geom.index;
  const n = obj.isInstancedMesh ? obj.count : 1;
  for (let k = 0; k < n; k += 1) {
    if (obj.isInstancedMesh) {
      obj.getMatrixAt(k, instMat);
      full.multiplyMatrices(obj.matrixWorld, instMat);
    } else {
      full.copy(obj.matrixWorld);
    }
    const base = part.positions.length / 3;
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(full);
      part.positions.push(v.x, v.y, v.z);
    }
    if (idx) {
      for (let i = 0; i < idx.count; i += 1) {
        part.indices.push(base + idx.getX(i));
      }
    } else {
      for (let i = 0; i < pos.count; i += 1) part.indices.push(base + i);
    }
    part.instances += 1;
  }
}

// Classify by INTRINSIC properties, never by traversal order: the hub is the
// only CylinderGeometry, the blade the only InstancedMesh, the ring whatever
// plain mesh is left.  Order-based classification would silently swap ring and
// hub the moment propeller.js reorders its group -- and a swap is invisible in
// a render until you wonder why the ring is hub-coloured.
const plainMeshes = [];
group.traverse((obj) => {
  if (obj.isLine) {
    const key = SECTION_BY_LINE_NAME[obj.name];
    if (!key) return;
    const pos = obj.geometry.attributes.position;
    const pts = [];
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(obj.matrixWorld);
      pts.push([v.x, v.y, v.z]);
    }
    sections[key] = pts;
    return;
  }
  if (!obj.isMesh) return;
  if (obj.isInstancedMesh) {
    parts.blade = parts.blade || emptyPart();
    bake(parts.blade, obj);
    return;
  }
  plainMeshes.push(obj);
});

for (const obj of plainMeshes) {
  const isHub = obj.geometry.type === 'CylinderGeometry';
  const key = isHub ? 'hub' : 'ring';
  parts[key] = parts[key] || emptyPart();
  bake(parts[key], obj);
}

const missing = ['blade', 'ring', 'hub'].filter((k) => !parts[k]);
if (missing.length) {
  process.stderr.write(
    `[feg_export_parts] FATAL: no geometry classified as ${missing.join(', ')}. `
    + 'web/feg/propeller.js has changed shape -- update the classifier rather '
    + 'than shipping a mislabelled part.\n',
  );
  process.exit(2);
}

const stats = Object.entries(parts)
  .map(([k, p]) => `${k}=${p.positions.length / 3}v/${p.indices.length / 3}f`)
  .join(' ');
process.stderr.write(
  `[feg_export_parts] ${stats} sections=${Object.keys(sections).length}\n`,
);

process.stdout.write(JSON.stringify({
  backend: 'feg',
  parts,
  sections,
  meta: { bladeCount: parts.blade.instances },
}));
