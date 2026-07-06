// Headless Node runner for the browser FEG geometry (web/feg/*).
//
// Reuses the EXACT web/feg modules the browser 3D preview uses, so the
// agent-facing geometry matches the preview with zero port-drift.  Outputs an
// OBJ that the existing Python render pipeline (tools/render_mesh) renders the
// same way it renders a RhinoCompute OBJ.
//
// Usage:  node tools/generate_mesh/feg_export.mjs '<params-json>'
//         (17 canonical params) — OBJ text -> stdout, one-line stats -> stderr.
//
// The blade is an InstancedMesh (blade x bladeCount around Z); each instance is
// baked into explicit world-space triangles.  Ring + hub are plain meshes.  The
// section-outline Lines are display-only and skipped.

import * as THREE from 'three';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const propellerUrl = pathToFileURL(
  resolve(__dirname, '..', '..', 'web', 'feg', 'propeller.js'),
).href;
const { buildPropellerGroup } = await import(propellerUrl);

const params = JSON.parse(process.argv[2] || '{}');
const material = new THREE.MeshStandardMaterial();
const group = buildPropellerGroup(params, material);
group.updateMatrixWorld(true);

const vLines = [];
const fLines = [];
let off = 0;
let meshCount = 0;
const instMat = new THREE.Matrix4();
const full = new THREE.Matrix4();
const v = new THREE.Vector3();

group.traverse((obj) => {
  if (!obj.isMesh || obj.isLine) return; // skip Lines (display-only outlines)
  meshCount += 1;
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
    const base = off;
    for (let i = 0; i < pos.count; i += 1) {
      v.fromBufferAttribute(pos, i).applyMatrix4(full);
      vLines.push(`v ${v.x.toFixed(6)} ${v.y.toFixed(6)} ${v.z.toFixed(6)}`);
    }
    if (idx) {
      for (let i = 0; i < idx.count; i += 3) {
        const a = base + idx.getX(i) + 1;
        const b = base + idx.getX(i + 1) + 1;
        const c = base + idx.getX(i + 2) + 1;
        fLines.push(`f ${a} ${b} ${c}`);
      }
    }
    off += pos.count;
  }
});

process.stderr.write(
  `[feg_export] meshes=${meshCount} vertices=${vLines.length} faces=${fLines.length}\n`,
);
process.stdout.write('# FEG propeller - headless Node/Three export of web/feg\n');
process.stdout.write(`${vLines.join('\n')}\n${fLines.join('\n')}\n`);
