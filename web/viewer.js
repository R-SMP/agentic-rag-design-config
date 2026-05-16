// Interactive 3D model viewer for the generated propeller mesh.
// Loaded as an ES module; exposes `window.modelViewer = { load, reset }`
// so the classic app.js can drive it. Three.js comes from the CDN
// import map declared in index.html (needs internet).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";

const container = document.getElementById("viewer");
const placeholder = document.getElementById("viewer-placeholder");
const nameLabel = document.getElementById("viewer-name");
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

function load(url, name) {
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

resetBtn && resetBtn.addEventListener("click", reset);

(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();

window.modelViewer = { load, reset };
