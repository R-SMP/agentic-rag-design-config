// Geometry constants for the in-browser front-end geometry (FEG) preview.
//
// Ported verbatim from the standalone propeller-browser reference
// (_shared/params.js CONSTANTS).  These are NOT exposed in the UI — they
// come from the underlying Grasshopper scripts and govern the FEG's
// resolution + ring/hub sizing.  Kept here so the FEG matches the
// reference exactly.  See extra_utilities/web_interface_notes.md.

export const CONSTANTS = {
  countI:               25,    // NACA + camber sample count
  clearance:            1.0,   // ring_height_based_on _outer.cs
  innerRadiusFixed:     4.0,   // inner_profile.cs translates to (4, 0, 0)
  bladeRingSteps:       32,    // loft rings along radial direction
  ringAngularSegments:  96,    // ring sweep resolution around Z
  hub: {                       // interface.cs placeholder
    radius: 8.28,
    baseZ:  -5,
    height: 10,
  },
};
