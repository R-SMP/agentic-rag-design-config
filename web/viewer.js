// Interactive 3D model viewer for the generated propeller mesh.
// Loaded as an ES module; exposes `window.modelViewer = { load, reset,
// unload }` so the classic app.js can drive it. Three.js comes from
// the CDN import map declared in index.html (needs internet).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";

const container = document.getElementById("viewer");
const placeholder = document.getElementById("viewer-placeholder");
const nameLabel = document.getElementById("viewer-name");
const attemptLabel = document.getElementById("viewer-attempt");
const resetBtn = document.getElementById("viewer-reset");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0f1117);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100000);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
container.appendChild(renderer.domElement);

// Lighting: a hemisphere for soft fill + a key directional light so
// surface curvature reads clearly while orbiting.
scene.add(new THREE.HemisphereLight(0xffffff, 0x444455, 1.0));
const key = new THREE.DirectionalLight(0xffffff, 1.4);
key.position.set(1, 1.5, 1);
scene.add(key);
scene.add(new THREE.AmbientLight(0xffffff, 0.25));

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enableZoom = true;          // scroll to zoom
controls.enablePan = false;          // keep rotation strictly about centre
controls.target.set(0, 0, 0);

let currentModel = null;
let homeCamPos = new THREE.Vector3(1, 1, 1);

// Snapshot the placeholder's initial HTML so unload() can restore the
// original "No model yet — generate a propeller…" copy even after a
// failed load() overwrote it with an error message.
const PLACEHOLDER_HTML = placeholder ? placeholder.innerHTML : "";

function sizeToContainer() {
  const w = container.clientWidth || 1;
  const h = container.clientHeight || 1;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(sizeToContainer).observe(container);
sizeToContainer();

function frameObject(obj) {
  // Recentre the model on the world origin so OrbitControls rotates
  // about its centre, then pull the camera back to fit it in view.
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  obj.position.sub(center);

  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z, 1e-3) * 0.5;
  const fov = (camera.fov * Math.PI) / 180;
  const dist = (radius / Math.sin(fov / 2)) * 1.6;

  const dir = new THREE.Vector3(1, 0.7, 1).normalize();
  homeCamPos = dir.multiplyScalar(dist);
  camera.position.copy(homeCamPos);
  camera.near = radius / 100;
  camera.far = radius * 100;
  camera.updateProjectionMatrix();

  controls.target.set(0, 0, 0);
  controls.minDistance = radius * 0.15;
  controls.maxDistance = radius * 25;
  controls.update();
}

function setAttemptLabel(text) {
  if (!attemptLabel) return;
  const trimmed = (text || "").trim();
  attemptLabel.textContent = trimmed;
  // The CSS rule defaults the badge to display:none; the
  // .has-attempt class flips it to display:inline-block.  This
  // avoids reserving toolbar space for an empty badge.
  if (trimmed) {
    attemptLabel.classList.add("has-attempt");
  } else {
    attemptLabel.classList.remove("has-attempt");
  }
}

function load(url, name, attempt) {
  const loader = new OBJLoader();
  loader.load(
    url,
    (obj) => {
      if (currentModel) scene.remove(currentModel);
      obj.traverse((child) => {
        if (child.isMesh) {
          if (!child.geometry.attributes.normal) {
            child.geometry.computeVertexNormals();
          }
          child.material = new THREE.MeshStandardMaterial({
            color: 0x9aa7b5,
            metalness: 0.15,
            roughness: 0.65,
            side: THREE.DoubleSide,
          });
        }
      });
      // Rhino is Z-up; the viewer is Y-up. Rotate so the propeller's
      // axis of rotation points up instead of lying horizontal.
      obj.rotation.x = -Math.PI / 2;
      currentModel = obj;
      scene.add(obj);
      frameObject(obj);
      if (placeholder) placeholder.style.display = "none";
      if (nameLabel) nameLabel.textContent = name || "";
      setAttemptLabel(attempt);
    },
    undefined,
    (err) => {
      console.error("OBJ load failed:", err);
      if (placeholder) {
        placeholder.style.display = "flex";
        placeholder.textContent =
          "Could not load the 3D model (" + (name || "mesh") + ").";
      }
    }
  );
}

function reset() {
  camera.position.copy(homeCamPos);
  controls.target.set(0, 0, 0);
  controls.update();
}

function unload() {
  // Drop the current mesh from the scene, free its GPU resources, and
  // bring the "No model yet…" placeholder back.  Called on End Session
  // so the viewer starts the next session as if nothing had been
  // generated.
  if (currentModel) {
    scene.remove(currentModel);
    currentModel.traverse((child) => {
      if (child.isMesh) {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((m) => m && m.dispose && m.dispose());
          } else if (child.material.dispose) {
            child.material.dispose();
          }
        }
      }
    });
    currentModel = null;
  }
  if (placeholder) {
    placeholder.innerHTML = PLACEHOLDER_HTML;
    placeholder.style.display = "";  // revert to stylesheet default
  }
  if (nameLabel) nameLabel.textContent = "";
  setAttemptLabel("");
  homeCamPos = new THREE.Vector3(1, 1, 1);
  camera.position.copy(homeCamPos);
  controls.target.set(0, 0, 0);
  controls.update();
}

resetBtn && resetBtn.addEventListener("click", reset);

(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();

window.modelViewer = { load, reset, unload };
