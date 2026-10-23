// The propeller's browser preview for the web app's Parameters page: the
// pack's side of the contract the page reads (MAS-blueprint P4c).
//
// The page imports this module when the pack has one (served at
// /pack/preview/preview.js) and calls what it exports.  Only buildModel is
// required; without this file the page offers a Preview button instead: the
// server builds the model of the values and the 3D view shows it.
//
//   buildModel(params, material)   -> THREE.Object3D: the live 3D preview,
//                                     in the model's own axes (the
//                                     generator's tool.yaml up_axis; the
//                                     page turns it upright).
//   highlightGroup(model, groupId) -> colour the part the parameter group
//                                     being edited shapes (null: none).
//   views                          -> more left-pane views beside "3D view":
//                                     [{id, label, title, draw(canvas, params)}].
//   groupFigures + drawGroupFigure(canvas, groupId, params)
//                                  -> a live drawing beside those groups'
//                                     pictures (setups/propeller/parameters.json groups).
//   modelTitle                     -> the "3D view" button's tooltip.
//
// The propeller's is FEG -- the front-end geometry in ./feg/, also run by
// Node for the agents (setups/propeller/tools/feg_geometry/feg_export.mjs).

import { buildPropellerGroup } from "./feg/propeller.js";
import { drawProfile2D } from "./feg/curves.js";
import { drawBladeSections } from "./feg/sections_view.js";

export const modelTitle =
  "Fast in-browser preview (FEG). Use Download geometry for the precise RhinoCompute mesh.";

export function buildModel(params, material) {
  return buildPropellerGroup(params, material);
}

// The blade section each parameter group shapes: its outline line in the
// model (feg/propeller.js names them) turns green while the group's tab is
// open; the others stay blue.  The general group shapes none.
const PROFILE_OF_GROUP = {
  inner: "InnerProfile",
  middle: "MiddleProfile",
  outer: "OuterProfile",
};

export function highlightGroup(model, groupId) {
  const active = PROFILE_OF_GROUP[groupId] || null;
  model.traverse((child) => {
    if (child.userData && child.userData.isProfileLine && child.material) {
      child.material.color.set(child.name === active ? 0x42a832 : 0x2196f3);
      child.material.needsUpdate = true;
    }
  });
}

export const views = [
  {
    id: "sections",
    label: "Blade sections",
    title: "Show the three blade-section airfoils (Inner/Middle/Outer) on a 1 mm grid",
    draw: drawBladeSections,
  },
];

// The three airfoil sections get a live cross-section drawing beside their
// picture (drawn "active", green, matching the 3D outline); General gets
// the picture only.
export const groupFigures = ["inner", "middle", "outer"];

export function drawGroupFigure(canvas, groupId, params) {
  drawProfile2D(canvas, groupId, params, { active: true });
}
