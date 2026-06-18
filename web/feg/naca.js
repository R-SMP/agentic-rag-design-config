// NACA airfoil construction faithful to the GH scripts:
//   inner_profile.cs (symmetric thickness with cos-clustered sampling)
//   mid_profile_2.cs (camber polyline using piecewise NACA mean-line)
//
// Output convention: 2D points { y, z } where y is the chordwise position
// in [0, 1] before scaling, and z is the thickness offset. The full
// section is an open contour traced lower-TE -> LE -> upper-TE; the loft
// downstream closes it by wrapping index M-1 back to index 0.
//
// Ported verbatim from the propeller-browser reference (geom/naca.js) for
// the in-browser FEG preview.

// Build the symmetric thickness contour.
// Mirrors inner_profile.cs:50-77. Uses the GH-specific LE-clustering:
// sample i/(N-1) for i in [0, N], take cos(...), remap [cos(0), cos(1)] to [0, 1].
// This clusters densely at the LE (cos derivative is 0 at 0) and lightly at TE.
export function buildSymmetricProfile(countI, thicknessPct) {
  const N = countI + 1;
  const samples = new Array(N);
  for (let i = 0; i < N; i++) samples[i] = i / (N - 1);

  const cosVals = samples.map(Math.cos);
  const cs = cosVals[0];           // cos(0) = 1
  const ce = cosVals[N - 1];       // cos(1) ≈ 0.5403
  const remapped = cosVals.map(v => (v - cs) / (ce - cs));

  const tN = thicknessPct * 0.01;
  const z = remapped.map(y => {
    const sy = y <= 0 ? 0 : Math.sqrt(y);
    return (tN / 0.2) * (
        0.2969 * sy
      - 0.1260 * y
      - 0.3516 * y * y
      + 0.2843 * y * y * y
      - 0.1015 * y * y * y * y
    );
  });

  // Open contour: lower surface from TE (y=1) to LE (y=0), then upper from
  // just past LE back to TE. Matches the combinedY / combinedZ ordering in
  // inner_profile.cs:58-67.
  const pts = [];
  for (let i = N - 1; i >= 0; i--) pts.push({ y: remapped[i], z: -z[i] });
  for (let i = 1;     i < N;  i++) pts.push({ y: remapped[i], z:  z[i] });
  return pts;
}

// Build the NACA mean-line (camber) as 21 uniform samples in y ∈ [0, 1].
// Mirrors mid_profile_2.cs:117-145 (the cleaner of the two GH camber builders;
// inner_profile.cs uses Convert.ToInt16 on highPointI which rounds away precision).
export function buildCamberCurve(highPointDec, camberPct) {
  const p = Math.max(0.001, Math.min(0.999, highPointDec * 0.1));
  const m = camberPct * 0.01;
  const N = 21;
  const pts = new Array(N);
  for (let i = 0; i < N; i++) {
    const x = i / (N - 1);
    let z;
    if (x <= p) {
      z = (m / (p * p)) * (2 * p * x - x * x);
    } else {
      const denom = (1 - p) * (1 - p);
      z = (m / denom) * ((1 - 2 * p) + 2 * p * x - x * x);
    }
    pts[i] = { y: x, z };
  }
  return pts;
}

// Morph the symmetric thickness contour onto the camber polyline.
// Rhino's FlowSpaceMorph is arc-length preserving; we use the standard airfoil
// construction (camber + perpendicular thickness offset) which is equivalent
// for the small-curvature regime NACA mean-lines live in.
//
// For each profile point (y_chord, z_thick): find the camber segment containing
// y_chord, compute the camber position and the unit normal of the segment
// (90° CCW from tangent in the YZ plane), and offset by z_thick along the normal.
export function morphProfileOntoCamber(profilePts, camberPts) {
  const N = camberPts.length;
  return profilePts.map(p => {
    const fIdx = p.y * (N - 1);
    const segIdx = Math.min(N - 2, Math.max(0, Math.floor(fIdx)));
    const u = Math.min(1, Math.max(0, fIdx - segIdx));

    const c0 = camberPts[segIdx];
    const c1 = camberPts[segIdx + 1];
    const cY = c0.y + (c1.y - c0.y) * u;
    const cZ = c0.z + (c1.z - c0.z) * u;

    const tY = c1.y - c0.y;
    const tZ = c1.z - c0.z;
    const tLen = Math.sqrt(tY * tY + tZ * tZ) || 1;
    const nY = -tZ / tLen;
    const nZ =  tY / tLen;

    return { y: cY + p.z * nY, z: cZ + p.z * nZ };
  });
}
