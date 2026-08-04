#!/usr/bin/env node
/**
 * verify_prompt_shrink.cjs — check that the cuts in PROMPT_SHRINK_PROPOSAL_7agent.md
 * still apply cleanly to the working tree.
 *
 *   node extra_utilities/prompt_efficiency/verify_prompt_shrink.cjs
 *   node extra_utilities/prompt_efficiency/verify_prompt_shrink.cjs --agent Planner
 *   node extra_utilities/prompt_efficiency/verify_prompt_shrink.cjs --pending
 *
 * Run it after applying a batch. A cut whose anchors no longer resolve has either
 * been applied already or been invalidated by an overlapping edit — `--pending`
 * lists the ones still outstanding so you can see what is left without re-reading
 * the 1.4 MB document.
 *
 * Four checks:
 *   1. ANCHORS   — do quote_start and quote_end still appear in the named file?
 *                  Exact match first, then a dash/whitespace-normalised match.
 *   2. OVERLAP   — do two cuts in the same file claim intersecting spans? Only one
 *                  of an overlapping pair can be applied as written.
 *   3. TEMPLATE  — does a replacement introduce a `$slot` that prompts.py does not
 *                  register, or a `{key}` no agent passes to .format()? Either
 *                  leaves a literal token in the assembled prompt or raises at
 *                  build time. This is the brace-escape trap that has bitten before.
 *   4. ARITHMETIC— does the declared chars_removed match the measured span?
 *                  Note the convention differs per auditor: eight report net
 *                  (span minus replacement), the Orchestrator reports gross.
 *
 * Exit code is 1 if any check fails, so it can gate a commit.
 */
'use strict';
const fs = require('fs');
const path = require('path');

const HERE = __dirname;
const ROOT = path.resolve(HERE, '..', '..');
const CUTS = path.join(HERE, 'prompt_shrink_cuts.json');

const argv = process.argv.slice(2);
const arg = n => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : null; };
const has = n => argv.includes(n);
const onlyAgent = arg('--agent');
const pendingOnly = has('--pending');

if (!fs.existsSync(CUTS)) {
  console.error(`missing ${CUTS}`);
  process.exit(1);
}
let cuts = JSON.parse(fs.readFileSync(CUTS, 'utf8'));
if (onlyAgent) {
  cuts = cuts.filter(c => c.agent.toLowerCase().includes(onlyAgent.toLowerCase()));
  if (!cuts.length) { console.error(`no cuts for agent matching "${onlyAgent}"`); process.exit(1); }
}

// ---- registries -------------------------------------------------------------
function slotRegistry() {
  const p = path.join(ROOT, 'agents', 'shared', 'prompts.py');
  const m = fs.readFileSync(p, 'utf8').match(/"[a-z_]+":/g) || [];
  return new Set(m.map(s => s.slice(1, -2)));
}
function formatKeys() {
  const keys = new Set(['hub', 'routing_instructions']);
  (function walk(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (!/__pycache__|node_modules|\.git/.test(e.name)) walk(p); }
      else if (e.name.endsWith('.py')) {
        const t = fs.readFileSync(p, 'utf8');
        for (const mm of t.matchAll(/^\s*([a-z_][a-z0-9_]*)\s*=\s*[A-Za-z_][\w.()\[\]'"]*,?\s*$/gm)) keys.add(mm[1]);
        for (const mm of t.matchAll(/\b([a-z_][a-z0-9_]*)\s*:\s*str\b/g)) keys.add(mm[1]);
      }
    }
  })(path.join(ROOT, 'agents'));
  return keys;
}
const VALID_SLOTS = slotRegistry();
const VALID_KEYS = formatKeys();

// ---- helpers ----------------------------------------------------------------
const cache = new Map();
function read(rel) {
  if (cache.has(rel)) return cache.get(rel);
  let p = String(rel).replace(/\\/g, '/');
  const abs = path.isAbsolute(p) ? p : path.join(ROOT, p);
  let t = null;
  try { t = fs.readFileSync(abs, 'utf8'); } catch (_) { /* missing */ }
  cache.set(rel, t);
  return t;
}
const norm = s => String(s)
  .replace(/[‐-―−]/g, '-')
  .replace(/[‘’]/g, "'")
  .replace(/[“”]/g, '"');

/** Locate quote_start..quote_end, returning [start, end, mode] or null. */
function locate(txt, qs, qe) {
  let i = txt.indexOf(qs);
  if (i >= 0) { const j = txt.indexOf(qe, i); if (j >= 0) return [i, j + qe.length, 'exact']; }
  const map = []; let flat = '';
  for (let k = 0; k < txt.length; k++) {
    let c = norm(txt[k]);
    if (/\s/.test(c)) { if (flat.endsWith(' ')) continue; c = ' '; }
    flat += c.toLowerCase(); map.push(k);
  }
  const f = s => norm(s).replace(/\s+/g, ' ').trim().toLowerCase();
  const a = flat.indexOf(f(qs)); if (a < 0) return null;
  const b = flat.indexOf(f(qe), a); if (b < 0) return null;
  return [map[a], map[Math.min(b + f(qe).length - 1, map.length - 1)] + 1, 'loose'];
}

// ---- 1. anchors -------------------------------------------------------------
const resolved = [], unresolved = [];
for (const c of cuts) {
  const t = read(c.file);
  if (t == null) { unresolved.push({ ...c, why: 'file not found' }); continue; }
  const loc = locate(t, c.quote_start, c.quote_end);
  if (!loc) { unresolved.push({ ...c, why: 'anchors not found (already applied, or superseded)' }); continue; }
  resolved.push({ ...c, s: loc[0], e: loc[1], mode: loc[2] });
}

if (pendingOnly) {
  console.log(`${resolved.length} cuts still pending (of ${cuts.length}${onlyAgent ? ` for ${onlyAgent}` : ''}):\n`);
  const by = {};
  for (const c of resolved) (by[c.agent] ||= []).push(c);
  for (const [a, list] of Object.entries(by)) {
    console.log(`  ${a} — ${list.length}`);
    for (const c of list.sort((x, y) => (y.chars_removed || 0) - (x.chars_removed || 0))) {
      console.log(`     ${c.id.padEnd(8)} ${String(c.action).padEnd(22)} ${String(c.chars_removed).padStart(6)}ch  ${c.section}`);
    }
  }
  process.exit(0);
}

console.log('1. ANCHORS');
console.log(`   resolved  : ${resolved.length}  (${resolved.filter(c => c.mode === 'exact').length} exact, ${resolved.filter(c => c.mode === 'loose').length} normalised)`);
console.log(`   unresolved: ${unresolved.length}`);
for (const c of unresolved) console.log(`      ${c.id}  ${c.file}  — ${c.why}`);

// ---- 2. overlaps ------------------------------------------------------------
// Two kinds, and only one is a defect:
//   COMPETING — different agents' auditors each rewrote the same region of a
//               SHARED fragment. Expected: each looked at the copy its own agent
//               carries. Pick ONE rewrite per fragment; they are alternatives.
//   CONFLICT  — two cuts for the SAME agent overlap. That is a mistake: applying
//               both is impossible and the auditor should have merged them.
const competing = [], conflicts = [];
const byFile = {};
for (const c of resolved) (byFile[c.file] ||= []).push(c);
// All pairs, not just adjacent ones: when many spans overlap on the same file,
// two cuts for the SAME agent can be separated by another agent's cut in the
// sorted order, and an adjacent-only scan silently misses them.
for (const [file, list] of Object.entries(byFile)) {
  list.sort((a, b) => a.s - b.s);
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      if (list[j].s >= list[i].e) break;   // sorted by start: no later span can overlap either
      const pair = [list[i].id, list[j].id, file];
      (list[i].agent === list[j].agent ? conflicts : competing).push(pair);
    }
  }
}
console.log('\n2. SPAN OVERLAPS');
console.log(`   CONFLICTS  (same agent, cannot both apply): ${conflicts.length}`);
for (const [a, b, f] of conflicts) console.log(`      ${a} <-> ${b}   ${f}`);
console.log(`   COMPETING  (different agents, same shared fragment — pick one): ${competing.length}`);
{
  const grouped = {};
  for (const [a, b, f] of competing) (grouped[f] ||= new Set()).add(a).add(b);
  for (const [f, ids] of Object.entries(grouped)) {
    console.log(`      ${f}`);
    console.log(`         ${[...ids].join(', ')}`);
  }
}

// ---- 3. template safety -----------------------------------------------------
const tmpl = [];
for (const c of cuts) {
  const r = c.replacement || ''; if (!r) continue;
  for (const m of r.match(/\$[a-zA-Z_][a-zA-Z0-9_]*/g) || []) {
    if (!VALID_SLOTS.has(m.slice(1))) tmpl.push([c.id, c.file, m, 'unknown $slot — would stay literal in the assembled prompt']);
  }
  for (const m of r.match(/\{[a-zA-Z_][a-zA-Z0-9_]*\}/g) || []) {
    if (!VALID_KEYS.has(m.slice(1, -1))) tmpl.push([c.id, c.file, m, 'unknown {format key} — .format() would raise KeyError']);
  }
}
console.log('\n3. TEMPLATE SAFETY');
console.log(`   ${tmpl.length} suspect token(s) across ${cuts.length} replacements`);
for (const [id, f, tok, why] of tmpl) console.log(`      ${id}  ${tok}  — ${why}\n         ${f}`);

// ---- 4. arithmetic ----------------------------------------------------------
let grossErr = 0, netErr = 0, n = 0;
for (const c of resolved) {
  if (!/prompt\.md$/.test(c.file)) continue;   // fragment/scope cuts remove text living elsewhere
  n++;
  const span = c.e - c.s, repl = (c.replacement || '').length;
  grossErr += Math.abs((c.chars_removed || 0) - span);
  netErr += Math.abs((c.chars_removed || 0) - (span - repl));
}
console.log('\n4. chars_removed CONVENTION');
console.log(`   measurable cuts: ${n}   error if gross: ${grossErr}   error if net: ${netErr}`);
console.log(`   -> this set reports ${netErr < grossErr ? 'NET (span minus replacement)' : 'GROSS (whole span)'}`);

// Only same-agent conflicts and template errors block; competing proposals for a
// shared fragment are a choice to make, not a fault, and unresolved anchors just
// mean the cut has already been applied.
const hard = conflicts.length + tmpl.length;
console.log(`\n${hard === 0
  ? `OK — no blocking problems. (${competing.length} competing shared-fragment proposals to choose between.)`
  : `${hard} blocking problem(s): ${conflicts.length} same-agent conflict(s), ${tmpl.length} template error(s).`}`);
process.exit(hard === 0 ? 0 : 1);
