// Interactive 3D model viewer for generated propeller meshes.
//
// Loaded as an ES module.  The chat view uses the legacy global
// ``window.modelViewer`` API (load / reset / unload) — preserved via
// the compat shim at the bottom of this file.
//
// The Parameters Inputs view (added in Step 4 of the redesign — see
// extra_utilities/web_interface_notes.md §7) instantiates a SECOND
// independent viewer against its own container:
//
//   import { Viewer } from "./viewer.js";
//   const paramsViewer = new Viewer(document.getElementById("param-viewer"));
//
// Each instance owns its own scene, camera, renderer, controls,
// ResizeObserver, and requestAnimationFrame loop — no shared state.
//
// Three.js comes from the CDN import map declared in index.html
// (needs internet).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { buildPropellerGroup } from "./feg/propeller.js";
import { drawProfile2D } from "./feg/curves.js";
import { drawBladeSections } from "./feg/sections_view.js";

// Expose the 2D drawers to the classic (non-module) app.js, which renders the
// per-section cross-section canvases and the Blade-sections view in the
// Parameters Inputs view.  app.js only calls these from event handlers (after
// this module has evaluated), so the globals are always set by the time
// they're used.
window.fegDrawProfile2D = drawProfile2D;
window.fegDrawBladeSections = drawBladeSections;


export class Viewer {
  /**
   * Create an interactive 3D viewer bound to a container element.
   *
   * @param {HTMLElement} container  DIV the WebGL canvas is appended into.
   * @param {object} [opts]
   * @param {HTMLElement|null} [opts.placeholderEl] Empty-state element
   *     hidden on load() and restored on unload().  Optional — the
   *     params viewer (Step 4) may use a simpler placeholder.
   * @param {HTMLElement|null} [opts.nameEl] Text element receiving
   *     the model's display name.  Optional.
   * @param {HTMLElement|null} [opts.attemptEl] Badge element showing
   *     the attempt label (e.g. "001").  Optional.
   * @param {HTMLElement|null} [opts.resetBtnEl] Button that triggers
   *     reset() on click.  Optional.
   */
  constructor(container, opts = {}) {
    if (!container) {
      throw new Error("Viewer: container element is required");
    }
    this.container = container;
    this.placeholderEl = opts.placeholderEl || null;
    this.nameEl = opts.nameEl || null;
    this.attemptEl = opts.attemptEl || null;
    this.resetBtnEl = opts.resetBtnEl || null;

    // Snapshot placeholder markup so unload() can restore the
    // original copy even after a failed load() overwrote it with
    // an error message.
    this._placeholderHtml = this.placeholderEl
      ? this.placeholderEl.innerHTML
      : "";

    // ---- Scene -----------------------------------------------------
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf5f5f5);   // near-white

    // ---- Camera ----------------------------------------------------
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100000);

    // ---- Renderer --------------------------------------------------
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio || 1);
    this.container.appendChild(this.renderer.domElement);

    // ---- Lights ----------------------------------------------------
    // Tuned for the near-white background: a softer hemisphere fill (light
    // ground so undersides don't go muddy on white), a moderate directional
    // key for form, and a faint ambient lift.  Pairs with the light matte
    // surface material from _makeSurfaceMaterial().
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x9a9a9a, 0.65));
    const key = new THREE.DirectionalLight(0xffffff, 0.85);
    key.position.set(1, 1.5, 1);
    this.scene.add(key);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.30));

    // ---- Controls --------------------------------------------------
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.enableZoom = true;     // scroll to zoom
    this.controls.enablePan = false;     // keep rotation about centre
    this.controls.target.set(0, 0, 0);

    // ---- Mutable state --------------------------------------------
    this.currentModel = null;
    this.homeCamPos = new THREE.Vector3(1, 1, 1);
    this._running = true;
    // FEG-preview state (params view only; the chat view never sets these).
    this._activeProfile = null;   // section name shown green, or null = all blue
    this._fegFramed = false;      // true once loadFromParams() has framed (then locked)

    // ---- Reference axis -------------------------------------------
    // RGB axis indicator aligned to the propeller's frame (the model is
    // built Z-up and rotated −90° X into this Y-up viewer, so the helper
    // gets the same rotation: blue Z = spin axis, red X = radial).  Always
    // visible and drawn IN FRONT of the geometry (depthTest off + a high
    // renderOrder) so it's never hidden by the propeller.
    this._axes = new THREE.AxesHelper(50);
    this._axes.rotation.x = -Math.PI / 2;
    this._axes.renderOrder = 999;
    this._axes.material.depthTest = false;
    this._axes.material.depthWrite = false;
    this._axes.material.transparent = true;
    this.scene.add(this._axes);

    // ---- Resize observer (per-container) --------------------------
    this._resizeObserver = new ResizeObserver(() => this._sizeToContainer());
    this._resizeObserver.observe(this.container);
    this._sizeToContainer();

    // ---- Reset button ---------------------------------------------
    if (this.resetBtnEl) {
      // Stored so destroy() can remove the listener cleanly.
      this._onResetClick = () => this.reset();
      this.resetBtnEl.addEventListener("click", this._onResetClick);
    }

    // ---- Render loop (per-instance) -------------------------------
    this._animate();
  }

  _sizeToContainer() {
    const w = this.container.clientWidth || 1;
    const h = this.container.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  _animate() {
    if (!this._running) return;
    requestAnimationFrame(() => this._animate());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  _frameObject(obj) {
    // Recentre the model on the world origin so OrbitControls rotates
    // about its centre, then pull the camera back to fit it in view.
    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    obj.position.sub(center);

    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 1e-3) * 0.5;
    const fov = (this.camera.fov * Math.PI) / 180;
    const dist = (radius / Math.sin(fov / 2)) * 1.6;

    const dir = new THREE.Vector3(1, 0.7, 1).normalize();
    this.homeCamPos = dir.multiplyScalar(dist);
    this.camera.position.copy(this.homeCamPos);
    this.camera.near = radius / 100;
    this.camera.far = radius * 100;
    this.camera.updateProjectionMatrix();

    this.controls.target.set(0, 0, 0);
    this.controls.minDistance = radius * 0.15;
    this.controls.maxDistance = radius * 25;
    this.controls.update();
  }

  _setAttemptLabel(text) {
    if (!this.attemptEl) return;
    const trimmed = (text || "").trim();
    this.attemptEl.textContent = trimmed;
    // The CSS rule defaults the badge to display:none; the
    // .has-attempt class flips it to display:inline-block.  This
    // avoids reserving toolbar space for an empty badge.
    if (trimmed) {
      this.attemptEl.classList.add("has-attempt");
    } else {
      this.attemptEl.classList.remove("has-attempt");
    }
  }

  /**
   * Light matte surface material for the propeller, tuned to read on the
   * near-white background (a slightly cool light gray, low metalness, high
   * roughness — matte 3D-print-stock look).  Shared by load() and
   * loadFromParams() so both surfaces match.
   */
  _makeSurfaceMaterial() {
    return new THREE.MeshStandardMaterial({
      color: 0xb9c0c8,
      metalness: 0.05,
      roughness: 0.72,
      side: THREE.DoubleSide,
    });
  }

  /**
   * Load an OBJ mesh from ``url`` into the viewer, replacing any
   * current model.  Updates the name / attempt label widgets and
   * hides the placeholder on success.  On failure the placeholder is
   * restored with a short error message.
   */
  load(url, name, attempt) {
    const loader = new OBJLoader();
    loader.load(
      url,
      (obj) => {
        if (this.currentModel) this.scene.remove(this.currentModel);
        obj.traverse((child) => {
          if (child.isMesh) {
            if (!child.geometry.attributes.normal) {
              child.geometry.computeVertexNormals();
            }
            child.material = this._makeSurfaceMaterial();
          }
        });
        // Rhino is Z-up; the viewer is Y-up. Rotate so the propeller's
        // axis of rotation points up instead of lying horizontal.
        obj.rotation.x = -Math.PI / 2;
        this.currentModel = obj;
        this.scene.add(obj);
        this._frameObject(obj);
        if (this.placeholderEl) this.placeholderEl.style.display = "none";
        if (this.nameEl) this.nameEl.textContent = name || "";
        this._setAttemptLabel(attempt);
      },
      undefined,
      (err) => {
        console.error("OBJ load failed:", err);
        if (this.placeholderEl) {
          this.placeholderEl.style.display = "flex";
          this.placeholderEl.textContent =
            "Could not load the 3D model (" + (name || "mesh") + ").";
        }
      }
    );
  }

  /**
   * Build the in-browser front-end geometry (FEG) propeller from a
   * 17-parameter dict and show it, replacing any current model.
   *
   * Synchronous — unlike load(), there is NO server round-trip.  Used by
   * the Parameters Inputs view's live-preview pipeline: the FEG is a fast,
   * disposable approximation of the propeller; the precise RhinoCompute
   * geometry (RCG) is fetched separately by the Download geometry button.
   *
   * The propeller is anchored at the origin (NOT re-centred) and the camera
   * is framed only ONCE — on the first build after the view opens — then
   * left alone, so changing the radius (or any parameter) shows the
   * propeller visibly grow/shrink about the fixed spin axis instead of the
   * view re-normalising every rebuild.  `unload()` resets the frame latch so
   * each new session re-frames once.
   *
   * @param {object} params  the 17 canonical parameters (raw geom units).
   * @param {string} [name]  optional label for the viewer toolbar.
   * @returns {boolean} true if a model was built and shown, false on error.
   */
  loadFromParams(params, name) {
    let group;
    try {
      // A fresh material per build so it disposes cleanly alongside the
      // group on the next swap / unload (matches load()'s per-load
      // material pattern).  Blade, ring and hub share this one instance.
      const material = this._makeSurfaceMaterial();
      group = buildPropellerGroup(params, material);
    } catch (err) {
      // Degenerate parameter combos can throw inside the loft/morph math.
      // Keep the previous model on screen rather than blanking the viewer.
      console.error("FEG build failed:", err);
      return false;
    }

    // Dispose the previous model first so rapid slider dragging doesn't
    // leak GPU buffers (a new group is built on every rebuild).
    if (this.currentModel) {
      this.scene.remove(this.currentModel);
      this._disposeObject(this.currentModel);
      this.currentModel = null;
    }

    // FEG is built Z-up (Rhino convention); the viewer is Y-up.  Match the
    // load() path's rotation so the FEG preview and the RCG look identical.
    // NO re-centring: the propeller's spin axis stays on the origin so a
    // radius change grows/shrinks the ring symmetrically about it.
    group.rotation.x = -Math.PI / 2;
    this.currentModel = group;
    this.scene.add(group);

    // Frame ONCE, then hold the camera still across rebuilds.
    if (!this._fegFramed) {
      this._frameForPreview(group);
      this._fegFramed = true;
    }

    // Colour the tab-active section outline (green) per the stored state.
    this._applyActiveProfile();

    if (this.placeholderEl) this.placeholderEl.style.display = "none";
    if (this.nameEl) this.nameEl.textContent = name || "";
    this._setAttemptLabel("");
    return true;
  }

  /**
   * Frame the camera to fit `obj` and lock that as the home position,
   * WITHOUT moving the object (it stays anchored at the origin).  Targets
   * the origin so the propeller's spin axis is the orbit pivot.  Used by the
   * params-view FEG preview (called once); the chat view uses _frameObject
   * (which re-centres + re-fits on every load).
   */
  _frameForPreview(obj) {
    const box = new THREE.Box3().setFromObject(obj);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 1e-3) * 0.5;
    const fov = (this.camera.fov * Math.PI) / 180;
    const dist = (radius / Math.sin(fov / 2)) * 1.6;

    const dir = new THREE.Vector3(1, 0.7, 1).normalize();
    this.homeCamPos = dir.multiplyScalar(dist);
    this.camera.position.copy(this.homeCamPos);
    this.camera.near = radius / 100;
    this.camera.far = radius * 100;
    this.camera.updateProjectionMatrix();

    this.controls.target.set(0, 0, 0);
    this.controls.minDistance = radius * 0.15;
    this.controls.maxDistance = radius * 25;
    this.controls.update();
  }

  /**
   * Set which blade section's outline is highlighted (green) in the params
   * preview; the others stay blue.  `null` / unknown → all blue.  Persists
   * across rebuilds (loadFromParams re-applies it) and recolours in place
   * without rebuilding, so tab switches are instant.
   *
   * @param {string|null} profileName  "InnerProfile" | "MiddleProfile" |
   *   "OuterProfile" | null.
   */
  setActiveProfile(profileName) {
    this._activeProfile = profileName || null;
    this._applyActiveProfile();
  }

  /** Recolour the section outline lines from the stored active profile. */
  _applyActiveProfile() {
    if (!this.currentModel) return;
    this.currentModel.traverse((child) => {
      if (child.userData && child.userData.isProfileLine && child.material) {
        const isActive = child.name === this._activeProfile;
        child.material.color.set(isActive ? 0x42a832 : 0x2196f3);
        child.material.needsUpdate = true;
      }
    });
  }

  /** Dispose every geometry + material under an object3D (meshes + lines). */
  _disposeObject(obj) {
    obj.traverse((child) => {
      if (child.geometry) child.geometry.dispose();
      const mat = child.material;
      if (mat) {
        if (Array.isArray(mat)) {
          mat.forEach((m) => m && m.dispose && m.dispose());
        } else if (mat.dispose) {
          mat.dispose();
        }
      }
    });
  }

  /** Return the camera to the auto-framed home position. */
  reset() {
    this.camera.position.copy(this.homeCamPos);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Force a re-measure of the container + WebGL canvas.  Needed when
   * the container was display:none at viewer-construction time (the
   * ResizeObserver records 0×0 in that case and may not re-fire when
   * display flips to block/flex on some browsers).  Public so callers
   * like switchView() in app.js can call it on first-show.
   */
  resize() {
    this._sizeToContainer();
  }

  /**
   * Drop the current mesh from the scene, free its GPU resources, and
   * bring the placeholder back.  Called on End Session so the viewer
   * starts the next session as if nothing had been generated.
   */
  unload() {
    if (this.currentModel) {
      this.scene.remove(this.currentModel);
      this._disposeObject(this.currentModel);   // meshes AND outline lines
      this.currentModel = null;
    }
    // Reset FEG-preview latches so the next session re-frames once and
    // starts with all-blue section outlines.  (The reference axis stays
    // visible — it is always shown.)
    this._fegFramed = false;
    this._activeProfile = null;
    if (this.placeholderEl) {
      this.placeholderEl.innerHTML = this._placeholderHtml;
      this.placeholderEl.style.display = "";   // revert to stylesheet default
    }
    if (this.nameEl) this.nameEl.textContent = "";
    this._setAttemptLabel("");
    this.homeCamPos = new THREE.Vector3(1, 1, 1);
    this.camera.position.copy(this.homeCamPos);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  /**
   * Tear down the viewer completely: stop the render loop, disconnect
   * the ResizeObserver, remove event listeners, free GPU resources,
   * and detach the canvas from the DOM.  Idempotent.
   *
   * Not used by the chat view's compat shim (its viewer lives for the
   * page lifetime), but available for tests and for any future code
   * that needs to swap viewers in / out.
   */
  destroy() {
    if (!this._running) return;
    this._running = false;
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
    if (this.resetBtnEl && this._onResetClick) {
      this.resetBtnEl.removeEventListener("click", this._onResetClick);
      this._onResetClick = null;
    }
    this.unload();
    if (this.renderer) {
      this.renderer.dispose();
      if (this.renderer.domElement && this.renderer.domElement.parentNode) {
        this.renderer.domElement.parentNode.removeChild(
          this.renderer.domElement
        );
      }
    }
  }
}


// ---------------------------------------------------------------------------
// Compat shim — preserve the existing window.modelViewer global so
// chat-view callers in app.js (loadMesh wrapper, End-Session handler,
// SSE visualize handler, attempt-thumbnail click handler) work
// unchanged.
//
// MUST run at module-eval time: app.js is loaded AFTER viewer.js in
// index.html and reads window.modelViewer.load(...) at the top level
// inside loadMesh().  Setting it inside a DOMContentLoaded handler or
// any deferred callback would race with that read.
//
// If the chat view's container (#viewer) is somehow missing, skip
// silently — the page that loaded this module evidently isn't the
// chat view, and callers will get a clear "modelViewer is undefined"
// error rather than a misleading instantiation crash from viewer.js.
// ---------------------------------------------------------------------------
const chatContainer = document.getElementById("viewer");
if (chatContainer) {
  window.modelViewer = new Viewer(chatContainer, {
    placeholderEl: document.getElementById("viewer-placeholder"),
    nameEl: document.getElementById("viewer-name"),
    attemptEl: document.getElementById("viewer-attempt"),
    resetBtnEl: document.getElementById("viewer-reset"),
  });
}


// ---------------------------------------------------------------------------
// Second Viewer for the Parameters Inputs view  (Step 4 of redesign,
// see extra_utilities/web_interface_notes.md §7).
//
// Fully independent of window.modelViewer: its own scene, camera,
// renderer, controls, ResizeObserver, and requestAnimationFrame loop.
// No mesh is loaded into this viewer yet — Step 7 wires the live-
// preview pipeline (slider → /api/preview_mesh → load()).
//
// The params view starts hidden (display:none) so the ResizeObserver
// records 0×0 on construction.  app.js's switchView() calls
// window.paramsViewer.resize() the first time the user navigates to
// the Parameters Inputs view, which re-measures the now-visible
// container.
// ---------------------------------------------------------------------------
const paramsContainer = document.getElementById("params-viewer");
if (paramsContainer) {
  window.paramsViewer = new Viewer(paramsContainer, {
    placeholderEl: document.getElementById("params-viewer-placeholder"),
    nameEl: document.getElementById("params-viewer-name"),
    attemptEl: document.getElementById("params-viewer-attempt"),
    resetBtnEl: document.getElementById("params-viewer-reset"),
  });
}
