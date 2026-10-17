/* ======================================================================
 * studio.js -- the MAS Studio, read-only (MAS-blueprint P5a).
 *
 * Plain ES5 in one IIFE, as the studio UI kit asks.  Every call to the
 * server goes through call()/req() and bridge.js (POST /api/<name>); the
 * one call today, get_all, answers the setup as the engine assembles it
 * (studio/engine_view.py).  The screens are the Studio draft's
 * (extra_utilities/docs/studio_draft/), made real and read-only.
 *
 * Screens are hash routes, so each one has an address:
 *   #/studio/<section>[?field=..]     the Studio: sections | fields | inspector
 *      sections: identity parameters description outputs tools examples
 *                inputs access settings prompts validate
 *      extra:    &agent=<key>  &param=<name>  &topo=3|5|7
 *   #/landing  #/start  #/import      later (the hosted Studio, P7b)
 * ====================================================================== */
(function (root) {
  'use strict';

  var doc = root.document;
  var D = null;                        // the setup, from the server
  var R = { page: 'studio', section: 'identity', q: {} };

  var SECTIONS = [
    { id: 'identity', n: 1, label: 'Identity' },
    { id: 'parameters', n: 2, label: 'Parameters' },
    { id: 'description', n: 3, label: 'Configurator description' },
    { id: 'outputs', n: 4, label: 'Outputs & vocabulary' },
    { id: 'tools', n: 5, label: 'Tools' },
    { id: 'examples', n: 6, label: 'Examples' },
    { id: 'inputs', n: 7, label: 'User input types' },
    { id: 'access', n: 8, label: 'Agent access' },
    { id: 'settings', n: 9, label: 'Settings & secrets' }
  ];
  var CHECK_PAGES = [
    { id: 'prompts', label: 'Prompt viewer' },
    { id: 'validate', label: 'Validate' }
  ];
  var INTRO = {
    identity: 'What the configurator is called and how the agents introduce it.',
    description: 'What the configurator builds, how its parameters behave, what it can and cannot do. Long text blocks, mostly read by the agents that write and check parameters.',
    outputs: 'What the generator produces and the words the agents use for it.',
    examples: 'Short examples spliced INTO generic sentences. Each one is a phrase: keep it on one line and keep its shape (parentheses, quotes, a leading comma).',
    inputs: 'How the agents treat a sketch or reference image the user uploads.'
  };
  // The texts of the screens that come later.
  var LATER = {
    editing: 'Editing comes in P6.',
    test: 'Test tool comes in P6.',
    validate: 'Validate comes in P7.',
    downloads: 'Downloads come in P7.',
    prepare: 'Prepare for GitHub comes in P7.',
    landing: 'The landing page and Import come with the hosted Studio (P7b).'
  };
  // the seven-agent roles a tool binds to (brief §5.4)
  var ROLE_ROWS = [
    { role: 'receptionist', label: 'Receptionist', key: 'receptionist' },
    { role: 'hub', label: 'Hub', key: 'orchestrator' },
    { role: 'planner', label: 'Planner', key: 'planner' },
    { role: 'input_extractor', label: 'Input extractor', key: 'user_input_inspector' },
    { role: 'parameter_author', label: 'Parameter author', key: 'dc_input_creator' },
    { role: 'parameter_checker', label: 'Parameter checker', key: 'dc_input_inspector' },
    { role: 'tool_runner', label: 'Tool runner', key: 'tool_caller' },
    { role: 'output_inspector', label: 'Output inspector', key: 'dc_output_inspector' },
    { role: 'database_handler', label: 'Database handler', key: 'database_handler' }
  ];
  var RUNTIME = { routing_instructions: 1, render_check_library_block: 1, image_persistence_block: 1,
                  comparison_mode_block: 1, chain_access_block: 1, user_inputs_dir: 1,
                  input_images_subdir: 1, extraction_output_file: 1 };

  /* ---------------- bridge (kit contract) ---------------- */
  function call(name) {
    var b = root.StudioBridge;
    if (!b) return Promise.reject(new Error('no bridge'));
    return b.call.apply(b, arguments);
  }
  function req(name) {
    return call.apply(null, arguments).then(function (r) {
      if (!r || r.ok === false) throw new Error((r && r.error) || (name + ' failed'));
      return r;
    });
  }

  /* ---------------- tiny DOM helper ---------------- */
  function h(tag, a, kids) {
    var n = doc.createElement(tag);
    if (a) Object.keys(a).forEach(function (k) {
      var v = a[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k === 'html') n.innerHTML = v;
      else if (k === 'style') n.style.cssText = v;
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    });
    add(n, kids);
    return n;
  }
  function add(n, kids) {
    if (kids === null || kids === undefined) return;
    if (!(kids instanceof Array)) kids = [kids];
    kids.forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      n.appendChild(typeof c === 'string' || typeof c === 'number' ? doc.createTextNode(String(c)) : c);
    });
  }
  function el(id) { return doc.getElementById(id); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function pill(text, cls, title) { return h('span', { 'class': 'pill ' + (cls || ''), title: title || null }, text); }
  function kpill(text, cls) { return h('span', { 'class': 'kpill ' + (cls || '') }, text); }
  function disp(key) { return (D.roles.display[key] || key).replace(/^The /, ''); }
  // a button of a screen that comes later: shown, disabled, its phase as the tooltip
  function laterButton(label, why, cls) { return h('button', { 'class': cls || null, disabled: true, title: why }, label); }

  /* ---------------- routing ---------------- */
  function parse() {
    var raw = (root.location.hash || '#/studio/identity').slice(1);
    var i = raw.indexOf('?');
    var path = i < 0 ? raw : raw.slice(0, i);
    var q = {};
    if (i >= 0) raw.slice(i + 1).split('&').forEach(function (kv) {
      if (!kv) return;
      var p = kv.split('=');
      q[decodeURIComponent(p[0])] = p.length > 1 ? decodeURIComponent(p[1]) : '1';
    });
    var parts = path.replace(/^\//, '').split('/');
    R = { page: parts[0] || 'studio', section: parts[1] || 'identity', q: q };
  }
  function link(page, section, q) {
    q = q || {};
    var qs = Object.keys(q).filter(function (k) { return q[k] !== null && q[k] !== undefined; })
      .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(q[k]); }).join('&');
    return '#/' + page + (section ? '/' + section : '') + (qs ? '?' + qs : '');
  }
  function go(page, section, q) { root.location.hash = link(page, section, q); }
  function withQ(extra) {
    var q = {};
    Object.keys(R.q).forEach(function (k) { q[k] = R.q[k]; });
    Object.keys(extra).forEach(function (k) { q[k] = extra[k]; });
    return q;
  }

  /* ---------------- data helpers ---------------- */
  function slotsOf(section) {
    return D.slots.filter(function (s) { return s.section === section; })
      .sort(function (a, b) { return a.order - b.order || (a.slot < b.slot ? -1 : 1); });
  }
  function slotByName(n) {
    for (var i = 0; i < D.slots.length; i++) if (D.slots[i].slot === n) return D.slots[i];
    return null;
  }
  function whereRows(slot) { return D.where[slot] || []; }
  function landsIn(slot, topo, agent) {
    return whereRows(slot).some(function (r) {
      return Object.keys(r.agents).some(function (a) {
        return (!agent || a === agent) && r.agents[a].indexOf(topo) >= 0;
      });
    });
  }
  function inRoster(agent, topo) {
    return agent === 'database_handler' || (D.roles.roster[String(topo)] || []).indexOf(agent) >= 0;
  }
  function holder(roleKey, topo) {
    if (roleKey === 'database_handler') return 'database_handler';
    var hm = D.roles.holder[String(topo)] || {};
    if (hm[roleKey]) return hm[roleKey];
    return inRoster(roleKey, topo) ? roleKey : null;
  }
  function sectionCount(id) {
    if (id === 'parameters') return D.parameters.parameters.length;
    if (id === 'tools') return D.tools.length;
    if (id === 'access') return D.parameter_access.rows.length;
    if (id === 'settings') return D.tool_settings.reduce(function (n, t) { return n + t.settings.length; }, 0) + Object.keys(D.settings).length;
    return slotsOf(id).length;
  }
  function unitMismatch(p) {
    if (!p.unit || !p.unit_prompt) return false;
    var stop = { the: 1, of: 1, a: 1, an: 1, unitless: 1, integer: 1, inner: 1, outer: 1 };
    function toks(s) {
      return s.toLowerCase().replace(/[^a-z%]+/g, ' ').split(' ').filter(function (t) { return t && !stop[t]; });
    }
    var a = toks(p.unit), b = toks(p.unit_prompt);
    return a.length && b.length && !a.some(function (t) { return b.indexOf(t) >= 0; });
  }

  /* ======================================================================
   * screens that come later: the landing page, Create your own, Import
   * ==================================================================== */
  function renderLater(app) {
    var p = h('div', { 'class': 'page' });
    add(p, [
      h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, LATER.landing),
      h('div', { style: 'margin-top:18px' }, h('button', { 'class': 'primary', onclick: function () { go('studio', 'identity'); } }, 'Open the Studio →'))
    ]);
    app.appendChild(p);
  }

  /* ======================================================================
   * the Studio shell: toolbar / banner / 3 columns / status bar
   * ==================================================================== */
  function renderStudio(app) {
    var tb = h('div', { 'class': 'toolbar' }, [
      h('span', { 'class': 'title', style: 'cursor:pointer', onclick: function () { go('landing'); } }, 'MAS Studio'),
      h('span', { 'class': 'pack', title: D.pack_dir }, ['setup: ', h('b', null, D.pack.name), ' · ' + D.pack_dir.split(/[\\/]/).pop() + '/']),
      pill('local', 'mode-local', 'python -m studio on this computer'),
      h('span', { 'class': 'grow' }),
      laterButton('Validate', LATER.validate),
      laterButton('Download setup file', LATER.downloads),
      laterButton('Download full package', LATER.downloads, 'primary'),
      h('span', { 'class': 'sep' }),
      laterButton('Prepare for GitHub', LATER.prepare)
    ]);
    var banner = h('div', { 'class': 'banner info' },
      'Read-only: the setup in ' + D.pack_dir + ', as the engine reads and assembles it. ' + LATER.editing);
    var left = h('div', { 'class': 'col side', id: 'colLeft', style: 'width:250px' }, renderNav());
    var center = h('div', { 'class': 'col center', id: 'center' });
    var right = h('div', { 'class': 'col side', id: 'colRight', style: 'width:380px' });
    var main = h('div', { id: 'main' }, [left, h('div', { 'class': 'splitter', 'data-target': 'colLeft', 'data-side': 'left' }), center,
      h('div', { 'class': 'splitter', 'data-target': 'colRight', 'data-side': 'right' }), right]);
    var sb = h('div', { 'class': 'statusbar' }, [
      pill('read-only', 'good'),
      h('span', { 'class': 'msg', id: 'statusMsg' }, 'Ready.')
    ]);
    add(app, h('div', { id: 'appShell', style: 'display:flex;flex-direction:column;height:100vh' }, [tb, banner, main, sb]));

    var sec = R.section;
    if (sec === 'parameters') renderParams(center, right);
    else if (sec === 'tools') renderTools(center, right);
    else if (sec === 'access') renderAccess(center, right);
    else if (sec === 'settings') renderSettings(center, right);
    else if (sec === 'prompts') renderPrompts(center, right);
    else if (sec === 'validate') renderValidate(center, right);
    else if (sec === 'outputs') renderOutputs(center, right);
    else renderGridSection(center, right, sec);
    initSplitters();
  }

  function renderNav() {
    var nav = h('div', { 'class': 'nav' });
    add(nav, h('div', { 'class': 'grp' }, h('h4', null, 'Your setup')));
    SECTIONS.forEach(function (s) {
      add(nav, h('a', { 'class': R.section === s.id ? 'on' : '', href: link('studio', s.id) }, [
        h('span', { 'class': 'num' }, s.n), h('span', { 'class': 'lab' }, s.label),
        h('span', { 'class': 'cnt' }, sectionCount(s.id))
      ]));
    });
    add(nav, h('div', { 'class': 'grp', style: 'margin-top:8px' }, h('h4', null, 'Check')));
    CHECK_PAGES.forEach(function (s) {
      add(nav, h('a', { 'class': R.section === s.id ? 'on' : '', href: link('studio', s.id) }, [
        h('span', { 'class': 'num' }, s.id === 'prompts' ? '▤' : '✔'), h('span', { 'class': 'lab' }, s.label),
        s.id === 'validate' ? h('span', { 'class': 'later', title: LATER.validate }, 'P7') : null
      ]));
    });
    return nav;
  }

  function head(title, sub, tools) {
    return h('div', { 'class': 'center-head' }, [h('h2', null, title), sub ? h('p', { 'class': 'sub' }, sub) : null,
      tools ? h('div', { 'class': 'tools' }, tools) : null]);
  }

  /* ======================================================================
   * the 3 / 5 / 7 grid (D6) + field inspector
   * ==================================================================== */
  function renderGridSection(center, right, sec) {
    var meta = SECTIONS.filter(function (s) { return s.id === sec; })[0] || { label: sec };
    add(center, head(meta.label, INTRO[sec], [legendGrid()]));
    var list = slotsOf(sec);
    add(center, grid(list));
    var sel = R.q.field ? slotByName(R.q.field) : list[0];
    add(right, sel ? inspectField(sel) : h('div', { 'class': 'insp empty' }, 'Select a field.'));
  }
  function legendGrid() {
    return h('div', { 'class': 'legend' }, [
      h('span', null, [h('span', { 'class': 'link on' }, '🔗 linked'), ' one text for every topology that uses it']),
      h('span', null, [h('span', { 'class': 'link off' }, '⛓ unlinked'), ' one text per topology (orange outline)']),
      h('span', null, [h('span', { 'class': 'na', style: 'font-style:italic;color:#5f6470' }, 'not used'), ' the topology never reads this field'])
    ]);
  }
  function grid(list) {
    var g = h('div', { 'class': 'tgrid' }, [
      h('div', { 'class': 'gh' }, 'Field'),
      h('div', { 'class': 'gh' }, '3-agent · ' + D.roles.roster['3'].length + ' agents'),
      h('div', { 'class': 'gh' }, '5-agent · ' + D.roles.roster['5'].length + ' agents'),
      h('div', { 'class': 'gh' }, '7-agent · ' + D.roles.roster['7'].length + ' agents')
    ]);
    list.forEach(function (s) {
      add(g, row(s, s.values, null));
      (s.variants || []).forEach(function (v) { add(g, row(s, v.values, v.agent)); });
    });
    return g;
  }
  function row(s, values, agent) {
    var present = [3, 5, 7].map(function (t) { return values[String(t)]; }).filter(function (v) { return v !== null && v !== undefined; });
    var same = present.length > 1 && present.every(function (v) { return v === present[0]; });
    var unlinked = !same && present.filter(function (v) { return v; }).length > 1;
    var selected = R.q.field === s.slot && (R.q.agent || null) === agent;
    var r = h('div', { 'class': 'trow' + (agent ? ' sub' : '') + (unlinked ? ' unlinked' : '') + (selected ? ' sel' : '') });
    var label = h('div', { 'class': 'fl', onclick: function () { go('studio', R.section, withQ({ field: s.slot, agent: agent })); } }, [
      h('span', { 'class': 'nm' }, agent ? '↳ ' + disp(agent) : s.slot),
      h('span', { 'class': 'meta' }, agent ? [kpill('own copy for this agent')] : [
        kpill(s.kind), kpill(s.origin === 'tool' ? 'tool' : 'DC', s.origin === 'tool' ? 'tool' : 'dc'),
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null,
        present.length > 1 ? h('span', { 'class': 'link ' + (unlinked ? 'off' : 'on'), title: LATER.editing },
          unlinked ? '⛓ unlinked' : '🔗 linked') : null])
    ]);
    add(r, label);
    [3, 5, 7].forEach(function (t) {
      var v = values[String(t)];
      var c = h('div', { 'class': 'cell' });
      if (agent && !inRoster(agent, t)) c.appendChild(h('div', { 'class': 'na' }, 'no ' + disp(agent) + ' in this topology'));
      else if (v === null || v === undefined) c.appendChild(h('div', { 'class': 'na' }, agent ? 'uses the shared text' : 'no file'));
      else if (v === '' && !landsIn(s.slot, t, agent)) c.appendChild(h('div', { 'class': 'na' }, 'not used'));
      else c.appendChild(field(s, v));
      add(r, c);
    });
    return r;
  }
  // a field's text, read-only (editing comes in P6)
  function field(s, v) {
    var lines = (v || '').split('\n').length;
    if (s.kind === 'block') {
      return h('textarea', { rows: Math.max(2, Math.min(6, lines)), readonly: true, spellcheck: 'false' }, v);
    }
    if (s.kind === 'phrase') {
      return h('textarea', { 'class': 'phrase', rows: Math.max(1, Math.min(4, Math.ceil((v || '').length / 34))),
        readonly: true, spellcheck: 'false' }, v);
    }
    return h('input', { type: 'text', value: v, readonly: true, spellcheck: 'false' });
  }

  function hints(s, v) {
    var out = [];
    if (s.kind === 'phrase') out.push('One line: it sits inside a generic sentence and is re-wrapped at 80 columns.');
    if (s.kind === 'word') out.push('A single word or short noun phrase (vocabulary).');
    if (s.kind === 'block') out.push('Multi-line Markdown; it stands on its own line in the prompt.');
    if (/^\(/.test(v)) out.push('Keep the parentheses: the sentence expects "( … )".');
    if (/^,/.test(v)) out.push('Starts with a comma: it continues the sentence before it.');
    if (/^"/.test(v)) out.push('A quoted list: "…", "…".');
    if (/<<IF(NOT)?:tool:/.test(v)) out.push('Carries an <<IF:tool:…>> region: part of it depends on whether that tool is on.');
    if (/<<IF(NOT)?:setting:/.test(v)) out.push('Carries an <<IF:setting:…>> region: part of it depends on that tool setting.');
    return out;
  }
  function inspectField(s) {
    var agent = R.q.agent || null, v7 = s.values['7'] || s.values['5'] || s.values['3'] || '';
    if (agent) (s.variants || []).forEach(function (x) { if (x.agent === agent) v7 = x.values['7'] || x.values['5'] || x.values['3'] || ''; });
    var rows = whereRows(s.slot).filter(function (r) { return !agent || r.agents[agent]; });
    var files = (D.files[s.slot] || {})[agent || ''] || [];
    var box = h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, s.slot + (agent ? '  @' + agent : '')),
      h('div', { 'class': 'pills' }, [kpill(s.kind), kpill(s.origin === 'tool' ? 'tool text' : 'DC text', s.origin === 'tool' ? 'tool' : 'dc'),
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null,
        s.linked ? kpill('linked 3·5·7') : kpill('per topology')]),
      h('p', null, s.description || h('span', { 'class': 'muted' }, 'No description in the slot registry yet.')),
      h('div', { 'class': 'block' }, [h('h4', null, 'Value'), h('div', { 'class': 'refval' }, v7 || '(empty)')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Shape'), h('ul', { 'class': 'checks' }, hints(s, v7).map(function (x) { return h('li', null, ['•', h('span', null, x)]); }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Where it lands · ' + rows.length + ' sentence' + (rows.length === 1 ? '' : 's')),
        rows.length ? null : h('p', { 'class': 'muted' }, 'Not in any prompt under the checked settings (base, all features on).')].concat(
        rows.slice(0, 5).map(function (r) { return whereCard(r, s); }),
        rows.length > 5 ? [h('div', { 'class': 'muted', style: 'font-size:11.5px' }, '+ ' + (rows.length - 5) + ' more')] : [])),
      h('div', { 'class': 'block' }, [h('h4', null, 'Stored as'), h('div', { 'class': 'mono', style: 'font-size:11.5px;color:#b9bec8;white-space:pre-line' },
        files.length ? files.join('\n') : 'no file: ' + (agent ? 'this agent has no copy' : 'no shared text'))])
    ]);
    return box;
  }
  function whereCard(r, s) {
    var who = Object.keys(r.agents).map(function (a) {
      return h('span', null, [h('b', null, disp(a)), ' ', h('span', { 'class': 'topo' }, r.agents[a].join(' · '))]);
    });
    var before = r.before.length > 150 ? '…' + r.before.slice(-150) : r.before;
    var after = r.after.length > 140 ? r.after.slice(0, 140) + '…' : r.after;
    return h('div', { 'class': 'where' }, [
      h('div', { 'class': 'who' }, who.concat(r.only_with_features ? [pill('only with features on', 'warn')] : [])),
      r.heading ? h('div', { 'class': 'sec' }, '§ ' + r.heading.slice(0, 80)) : null,
      h('div', { 'class': 's', html: esc(before) + ' <mark class="' + (s && s.origin === 'tool' ? 'tool' : '') + '">' + esc(r.value) + '</mark> ' + esc(after) })
    ]);
  }

  /* ======================================================================
   * Outputs & vocabulary
   * ==================================================================== */
  var VOCAB_RULES = [
    ['output_model', 'noun', 'the model the generator builds'], ['output_model_label', 'Model + " file"', 'hand-off label'],
    ['output_image', 'noun', 'one output image'], ['output_images', 'plural', '+s'],
    ['output_image_caps', 'CAPITALS', 'emphasis'], ['output_produced', 'past participle', '+ed'],
    ['output_images_long', 'participle + "images"', 'long form'], ['output_image_files', 'participle + "PNGs"', 'files'],
    ['output_images_label', 'Capitalised + " images"', 'hand-off label'], ['output_action', 'verb', 'produce them'],
    ['output_reaction', '"re-" + verb', 'produce again'], ['output_reactions', '3rd person', '+s'],
    ['output_action_noun', '-ing noun', 'the act']
  ];
  function renderOutputs(center, right) {
    add(center, head('Outputs & vocabulary', 'Two nouns, and the forms made from them by rule. Every form is shown in a real sentence of the prompts.', [legendGrid()]));
    var tbl = h('table', { 'class': 'ptab', style: 'margin:10px 16px 6px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Form', 'Value', 'Rule', 'In a real sentence'].map(function (x) { return h('th', null, x); })))]);
    var tb = h('tbody');
    add(tb, h('tr', { 'class': 'grp' }, h('td', { colspan: 4 }, [
      'Base nouns: model ', h('input', { type: 'text', value: (slotByName('output_model') || { values: {} }).values['7'], readonly: true, style: 'width:90px;margin:0 10px 0 4px' }),
      'image ', h('input', { type: 'text', value: (slotByName('output_image') || { values: {} }).values['7'], readonly: true, style: 'width:90px;margin-left:4px' })])));
    VOCAB_RULES.forEach(function (vr) {
      var s = slotByName(vr[0]);
      if (!s) return;
      var w = whereRows(s.slot)[0];
      var sent = w ? '…' + esc(w.before.slice(-70)) + ' <mark>' + esc(w.value) + '</mark> ' + esc(w.after.slice(0, 50)) + '…' : '';
      add(tb, h('tr', { 'class': R.q.field === s.slot ? 'sel' : '', style: 'cursor:pointer', onclick: function () { go('studio', 'outputs', withQ({ field: s.slot })); } }, [
        h('td', null, h('span', { 'class': 'pname' }, s.slot)),
        h('td', { style: 'width:150px' }, h('input', { type: 'text', value: s.values['7'], readonly: true })),
        h('td', { 'class': 'muted', style: 'font-size:11.5px;width:160px' }, vr[1]),
        h('td', { style: 'font-size:11.5px;color:#b9bec8', html: sent })
      ]));
    });
    tbl.appendChild(tb);
    add(center, tbl);
    var rest = slotsOf('outputs').filter(function (s) { return s.slot.indexOf('output_') !== 0; });
    add(center, h('div', { style: 'padding:14px 16px 4px' }, h('h4', null, 'What the inspector checks in the images')));
    add(center, grid(rest));
    var sel = slotByName(R.q.field || 'output_images') || slotsOf('outputs')[0];
    if (sel) add(right, inspectField(sel));
  }

  /* ======================================================================
   * Parameters
   * ==================================================================== */
  function renderParams(center, right) {
    var P = D.parameters.parameters;
    add(center, head('Parameters', 'The one parameter file (parameters.json): the validator, the parameter sliders, the database and the agents’ parameter count read it; the agents’ own parameter lists are checked against it. ' +
      P.length + ' parameters in ' + D.parameters.groups.length + ' groups.', [
      laterButton('Import JSON…', LATER.editing), laterButton('Paste CSV…', LATER.editing),
      laterButton('+ Add parameter', LATER.editing), laterButton('+ Add group', LATER.editing)]));
    var t = h('table', { 'class': 'ptab' }, h('thead', null, h('tr', null,
      ['Name', 'Label', 'Type', 'Min', 'Max', 'Step', 'Default', 'Unit'].map(function (x) { return h('th', null, x); }))));
    var tb = h('tbody');
    D.parameters.groups.forEach(function (g) {
      var img = D.group_images[g.id];
      add(tb, h('tr', { 'class': 'grp' }, h('td', { colspan: 8 }, [g.label,
        img ? h('img', { 'class': 'thumb', src: img, alt: '' }) : null])));
      P.filter(function (p) { return p.group === g.id; }).forEach(function (p) {
        var bad = unitMismatch(p);
        add(tb, h('tr', { 'class': (R.q.param === p.name ? 'sel ' : '') + (bad ? 'warnrow' : ''), style: 'cursor:pointer',
          onclick: function () { go('studio', 'parameters', withQ({ param: p.name })); } }, [
          h('td', null, h('span', { 'class': 'pname' }, p.name)),
          h('td', null, h('input', { type: 'text', value: p.label, readonly: true })),
          h('td', { style: 'width:80px' }, h('select', { disabled: true }, ['int', 'float'].map(function (o) { return h('option', { selected: o === p.type }, o); }))),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.min, readonly: true })),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.max, readonly: true })),
          h('td', { 'class': 'num', style: 'width:64px' }, h('input', { type: 'text', value: p.step, readonly: true })),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.default, readonly: true })),
          h('td', null, h('input', { type: 'text', value: p.unit, readonly: true, 'class': bad ? 'invalid' : null }))
        ]));
      });
    });
    t.appendChild(tb);
    add(center, h('div', { style: 'padding:0 16px 20px' }, t));
    var p = P.filter(function (x) { return x.name === R.q.param; })[0] || P[0];
    var bad = unitMismatch(p);
    add(right, h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, p.name),
      h('div', { 'class': 'pills' }, [kpill(p.type), kpill('[' + p.min + '; ' + p.max + ']'), kpill('default ' + p.default)]),
      h('p', null, p.description),
      bad ? h('div', { 'class': 'banner warn', style: 'border:1px solid #7a5a1a;border-radius:7px;margin:10px 0' }, [
        h('b', null, 'Two texts disagree on the unit. '), 'The agents’ parameter list says “' + p.unit_prompt + '”; the slider page says “' +
        p.unit + '”. The agents’ list is hand-written text ($parameter_list), checked against parameters.json for names, order and ranges only.']) : null,
      h('div', { 'class': 'block' }, [h('h4', null, 'Unit'), h('div', { 'class': 'kv', style: 'grid-template-columns:110px 1fr' }, [
        h('div', { 'class': 'k' }, 'slider label'), h('div', null, p.unit || '—'),
        h('div', { 'class': 'k' }, 'agents’ text'), h('div', null, p.unit_prompt || '—')])]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Read from this one entry (parameters.json)'), h('ul', { 'class': 'checks' }, [
        'the key list and types the validator enforces', 'the parameter count in the agents’ prompts ($parameter_count)',
        'the slider on the Parameters page of the web app', 'the in-browser preview’s input check',
        'the database’s parameter schema (a new version on each upload)'].map(function (x) {
        return h('li', null, ['•', h('span', null, x)]); }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Checked against it'), h('ul', { 'class': 'checks' }, [
        'the parameter list in the agents’ prompts ($parameter_list and its per-agent copies; full or names only per agent — see Agent access): same names, order and ranges'].map(function (x) {
        return h('li', null, ['•', h('span', null, x)]); }))])
    ]));
  }

  /* ======================================================================
   * Tools
   * ==================================================================== */
  function rolesLine(role) {
    var row = ROLE_ROWS.filter(function (r) { return r.role === role; })[0];
    if (!row) return role;
    return [3, 5, 7].map(function (t) { var a = holder(row.key, t); return (a ? disp(a) : '—') + ' (' + t + ')'; }).join(' · ');
  }
  function roleLabel(role) {
    var row = ROLE_ROWS.filter(function (r) { return r.role === role; })[0];
    return row ? row.label.toLowerCase() : role;
  }
  function produces(info) {
    var parts = [];
    if (info.model_format) parts.push('model: .' + info.model_format);
    if (info.images.length) parts.push('images: ' + info.images.map(function (i) {
      return i.view + (i.default_enabled ? '' : ' (off by default)'); }).join(', '));
    return parts.length ? parts.join(' · ') : 'nothing declared';
  }
  function renderTools(center, right) {
    add(center, head('Tools', 'The functions your agents call to build and look at a design. Each tool is a plain Python function plus a manifest: what it is, which role may call it, what it produces, and the text the agents read about it.', [
      laterButton('+ New tool', LATER.editing, 'primary')]));
    var wrap = h('div', { 'class': 'toolcards' });
    D.tools.forEach(function (t) {
      var info = D.tool_info[t.name] || { roles: [], images: [], settings: [] };
      var first = t.description.split('\n\n')[0].replace(/\s+/g, ' ');
      var settings = info.settings.length ? info.settings.join(', ') : 'none';
      add(wrap, h('div', { 'class': 'tcard' }, [
        h('div', { 'class': 'head' }, [h('span', { 'class': 'n' }, t.name), pill(t.display), kpill(t.kind === 'generator' ? 'generator · primary' : t.kind),
          h('span', { 'class': 'grow' }), laterButton('Edit', LATER.editing), laterButton('Test tool', LATER.test)]),
        h('div', { 'class': 'd' }, first),
        h('div', { 'class': 'grid2' }, [
          h('div', { 'class': 'k' }, 'Called by'), h('div', null, t.kind === 'geometry'
            ? 'the engine, never an agent: the generator’s geometry tool setting, the Download buttons'
            : info.roles.map(function (r) { return roleLabel(r) + ': ' + rolesLine(r); }).join('; ') || 'no role'),
          h('div', { 'class': 'k' }, 'Produces'), h('div', null, produces(info)),
          h('div', { 'class': 'k' }, 'Settings'), h('div', null, (info.switch ? 'an on/off switch · ' : '') + settings),
          h('div', { 'class': 'k' }, 'Prompt text'), h('div', null, t.kind === 'geometry' ? 'none (no agent reads about it)'
            : t.owns.length + ' fields it owns (they leave with it) + its entry in the tool runner’s numbered list, place ' + t.list_order),
          h('div', { 'class': 'k' }, 'Code'), h('div', { 'class': 'mono', style: 'font-size:11px' }, t.file + '  ·  manifest dc_pack/tools/' + t.name + '/tool.yaml')
        ])
      ]));
    });
    add(center, wrap);
    add(center, h('div', { style: 'padding:6px 16px 4px' }, [h('h4', null, 'Tool text the agents read · ' + slotsOf('tools').length + ' fields'),
      h('div', { 'class': 'muted', style: 'font-size:11.5px' }, 'A field owned by a tool lives in that tool’s folder (dc_pack/tools/<tool>/prompts/) and leaves with it; the others are shared by all tools.')]));
    add(center, grid(slotsOf('tools')));
    if (R.q.field && slotByName(R.q.field)) { add(right, inspectField(slotByName(R.q.field))); return; }
    add(right, h('div', { 'class': 'insp' }, [
      h('h4', null, 'How tools reach the agents'),
      h('p', null, 'A tool is bound to a ROLE, not to an agent. The engine gives it to whichever agent holds that role in the running topology.'),
      h('div', { 'class': 'block' }, [h('h4', null, 'tool runner'), h('div', { 'class': 'kv', style: 'grid-template-columns:70px 1fr' },
        [3, 5, 7].reduce(function (acc, t) { var a = holder('tool_caller', t); return acc.concat([h('div', { 'class': 'k' }, t + '-agent'), h('div', null, a ? disp(a) : '—')]); }, []))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Text the agents read about tools'), h('p', null, 'Each tool owns the text about it: ' +
        D.tools.reduce(function (n, t) { return n + t.owns.length; }, 0) + ' fields live in the tools’ own folders, and the tool runner’s numbered tool list is built from each tool’s entry. Removing a tool removes its text; a marked passage about it elsewhere reads as switched off.')])
    ]));
  }

  /* ======================================================================
   * Agent access
   * ==================================================================== */
  function renderAccess(center, right) {
    var PA = D.parameter_access;
    add(center, head('Agent access', 'Who sees the parameter list, and how: one choice per agent and topology (a cell exists only where the agent does). This is the setup’s default; Workflow Settings can change it for the next session.'));
    var t = h('table', { 'class': 'ptab', style: 'margin:10px 16px;width:calc(100% - 32px)' }, h('thead', null, h('tr', null,
      ['Agent', '7-agent', '5-agent', '3-agent'].map(function (x) { return h('th', null, x); }))));
    var tb = h('tbody');
    PA.rows.forEach(function (r) {
      add(tb, h('tr', null, [h('td', null, [h('b', null, r.name), h('div', { 'class': 'muted mono', style: 'font-size:10.5px' }, r.agent)])].concat(
        ['7', '5', '3'].map(function (k) {
          var st = r.cells[k];
          if (!st) return h('td', null, h('span', { 'class': 'na' }, '—'));
          return h('td', null, h('span', { 'class': 'seg ro', title: LATER.editing }, PA.states.filter(function (o) {
            return !(o.id === 'tool' && PA.no_tool.indexOf(r.agent) >= 0); }).map(function (o) {
            return h('button', { 'class': o.id === st ? 'on' : '' }, o.short); })));
        }))));
    });
    t.appendChild(tb);
    add(center, t);
    add(right, h('div', { 'class': 'insp' }, [
      h('h4', null, 'The four choices'),
      h('div', { 'class': 'kv', style: 'grid-template-columns:90px 1fr;margin-top:6px' }, [
        h('div', { 'class': 'k' }, 'full'), h('div', null, 'the parameter list in the prompt, ranges included'),
        h('div', { 'class': 'k' }, 'names'), h('div', null, 'the list in the prompt with every [min; max] range removed'),
        h('div', { 'class': 'k' }, 'tool'), h('div', null, 'nothing in the prompt; the agent calls dc_params_list when it needs the list'),
        h('div', { 'class': 'k' }, 'none'), h('div', null, 'neither')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Stored in'), h('p', null, 'dc_pack/pack.yaml → parameter_access (the default). Workflow Settings › Parameter list access stores changed cells for the next session. The Database Handler cannot take “tool”.')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Later'), h('p', { 'class': 'muted' }, 'Editing the role map itself (which agent holds which role) is TODO F102, not in this version.')])
    ]));
  }

  /* ======================================================================
   * Settings & secrets
   * ==================================================================== */
  // What the engine reads each variable for; a variable not listed here
  // shows its heading in .env.example.
  var ENV_USE = {
    OPENAI_API_KEY: ['LLM provider', 'at least one LLM key'], ANTHROPIC_API_KEY: ['LLM provider', 'at least one LLM key'],
    GOOGLE_API_KEY: ['LLM provider', 'at least one LLM key'], OPENROUTER_API_KEY: ['LLM provider', 'at least one LLM key'],
    DATABASE_URL: ['database (saved sessions, RAG)', 'optional'], DATABASE_PUBLIC_URL: ['database, from outside Railway', 'optional'],
    R2_ACCESS_KEY_ID: ['cloud file storage', 'optional'], R2_ACCOUNT_ID: ['cloud file storage', 'optional'],
    R2_BUCKET_NAME: ['cloud file storage', 'optional'], R2_SECRET_ACCESS_KEY: ['cloud file storage', 'optional'],
    STORAGE_BACKEND: ['where files are stored', 'optional'], INVITE_CODE: ['login gate of your deployment', 'optional'],
    VOYAGE_API_KEY: ['image search in the database', 'optional'], GOOGLE_CLOUD_VISION_API_KEY: ['reading text in images (OCR)', 'optional']
  };
  function renderSettings(center, right) {
    var S = D.settings;
    function srow(name, value, choices, note) {
      return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, name)), h('td', null, typeof value === 'boolean' ?
        h('span', { 'class': 'seg ro', title: LATER.editing }, [h('button', { 'class': value ? 'on' : '' }, 'on'), h('button', { 'class': value ? '' : 'on' }, 'off')]) :
        h('select', { disabled: true, title: LATER.editing }, (choices || [value]).map(function (c) { return h('option', { selected: c === value }, c); }))),
        h('td', { 'class': 'muted', style: 'font-size:11.5px' }, note)]);
    }
    add(center, head('Settings & secrets', 'Default values of the tools’ own settings (users change them later in Workflow Settings), and the list of secrets your setup will need.'));
    var t = h('table', { 'class': 'ptab', style: 'margin:10px 16px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Setting', 'Default', 'What it is'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, D.tool_settings.reduce(function (rows, tool) {
        rows.push(h('tr', { 'class': 'grp' }, h('td', { colspan: 3 }, tool.tool)));
        tool.settings.forEach(function (s) { rows.push(srow(s.name, s.default, s.values, s.label)); });
        return rows;
      }, []).concat([
        h('tr', { 'class': 'grp' }, h('td', { colspan: 3 }, 'setup')),
        srow('parameter_primer_image', !!S.DC_PARAMS_PRIMER_ENABLED, null, 'DC_PARAMS_PRIMER_ENABLED (settings.py)')
      ]))]);
    add(center, t);
    add(center, h('div', { 'class': 'banner info', style: 'margin:6px 16px;border:1px solid #2f4f86;border-radius:7px' },
      'The Studio never asks for a secret value. These names go into .env.example in the full package, with empty values; you fill them on your own computer or in your hosting provider.'));
    var e = h('table', { 'class': 'ptab', style: 'margin:6px 16px 20px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Variable', 'Needed for', 'Required'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, D.env_vars.map(function (n) {
        var u = ENV_USE[n] || [D.env_sections[n] || '', 'optional'];
        return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, n)), h('td', null, u[0]),
          h('td', { 'class': u[1] === 'optional' ? 'muted' : 'warn' }, u[1])]);
      }))]);
    add(center, e);
    add(right, h('div', { 'class': 'insp' }, [h('h4', null, 'Where these come from'),
      h('p', null, 'The settings are each tool’s own (its tool.yaml) and the setup’s (settings.py); the variable names are the engine’s .env.example. No value of a secret is read or shown.')]));
  }

  /* ======================================================================
   * Prompt viewer (inside the main window)
   * ==================================================================== */
  function topoAgents(t) { return Object.keys(D.prompts[String(t)].prompts); }
  function ownerName(tool) { var t = D.tools.filter(function (x) { return x.name === tool; })[0]; return t ? t.display : tool; }
  // Built by the engine from each tool's own entry (the tool runner's list):
  // tool text, but no single field to open.
  var ENGINE_BUILT = { tool_inventory: 1 };
  function originOf(name) {
    if (RUNTIME[name]) return 'rt';
    if (ENGINE_BUILT[name]) return 'tool';
    var s = slotByName(name);
    return s ? (s.origin === 'tool' ? 'tool' : 'dc') : 'dc';
  }
  function renderPrompts(center, right) {
    var topo = parseInt(R.q.topo || '7', 10);
    if ([3, 5, 7].indexOf(topo) < 0) topo = 7;
    var agents = topoAgents(topo);
    var agent = R.q.agent && agents.indexOf(R.q.agent) >= 0 ? R.q.agent : 'receptionist';
    var bar = [h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'Topology'), h('span', { 'class': 'seg' }, [3, 5, 7].map(function (t) {
      return h('button', { 'class': t === topo ? 'on' : '', onclick: function () { go('studio', 'prompts', withQ({ topo: t, agent: null })); } }, String(t)); })),
      h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'Shown with this setup’s default settings; any combination comes in P5b.')];
    add(center, head('Prompt viewer', 'The exact system prompt each agent receives, assembled by the engine from this setup. Click an agent.', bar));
    add(center, h('div', { 'class': 'flow' }, flowchart(topo, agent)));
    add(center, h('div', { style: 'padding:0 16px' }, h('div', { 'class': 'legend' }, [
      h('span', null, [h('span', { 'class': 'sw gen' }), 'engine text (generic)']), h('span', null, [h('span', { 'class': 'sw dc' }), 'your DC text']),
      h('span', null, [h('span', { 'class': 'sw tool' }), 'your tool text']), h('span', null, [h('span', { 'class': 'sw rt' }), 'filled in per session'])])));
    var data = D.prompts[String(topo)];
    var text = data.prompts[agent], spans = data.spans[agent] || [];
    var pre = h('div', { 'class': 'prompt' });
    pre.innerHTML = colourise(text, spans);
    pre.addEventListener('click', function (ev) {
      var t = ev.target;
      if (t && t.getAttribute && t.getAttribute('data-slot')) {
        var s = slotByName(t.getAttribute('data-slot'));
        if (s) go('studio', s.section, { field: s.slot });
      }
    });
    add(center, pre);
    // composition
    var own = new Array(text.length);
    spans.slice().sort(function (a, b) { return a[3] - b[3]; }).forEach(function (sp) { for (var i = sp[0]; i < sp[1]; i++) own[i] = originOf(sp[2]); });
    var cnt = { gen: 0, dc: 0, tool: 0, rt: 0 };
    for (var i = 0; i < text.length; i++) cnt[own[i] || 'gen']++;
    var used = {};
    spans.forEach(function (sp) { if (!RUNTIME[sp[2]] && !ENGINE_BUILT[sp[2]]) used[sp[2]] = (used[sp[2]] || 0) + 1; });
    var col = { gen: '#4a4d57', dc: 'var(--a)', tool: 'var(--b)', rt: 'var(--c)' };
    add(right, h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, disp(agent) + ' · topology ' + topo),
      h('div', { 'class': 'pills' }, [kpill(fmt(text.length) + ' characters'), kpill('≈ ' + fmt(Math.round(text.length / 4)) + ' tokens')]),
      h('h4', null, 'Where the text comes from'),
      h('div', { 'class': 'stack' }, ['gen', 'dc', 'tool', 'rt'].map(function (k) { return h('div', { style: 'width:' + (100 * cnt[k] / text.length) + '%;background:' + col[k] }); })),
      h('div', { 'class': 'kv', style: 'grid-template-columns:120px 1fr;font-size:11.5px' }, [
        h('div', { 'class': 'k' }, 'engine (generic)'), h('div', null, Math.round(100 * cnt.gen / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'your DC text'), h('div', null, Math.round(100 * cnt.dc / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'your tool text'), h('div', null, Math.round(100 * cnt.tool / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'per session'), h('div', null, Math.round(100 * cnt.rt / text.length) + ' %')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Your fields in this prompt · ' + Object.keys(used).length),
        h('div', null, Object.keys(used).sort().map(function (n) {
          return h('a', { href: link('studio', (slotByName(n) || {}).section || 'tools', { field: n }), 'class': 'kpill ' + originOf(n), style: 'display:inline-block;margin:2px;text-decoration:none' }, n + (used[n] > 1 ? ' ×' + used[n] : ''));
        }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Exact'), h('p', { 'class': 'muted', style: 'font-size:11.5px' }, 'Colours come from markers placed while the engine assembled this prompt, then checked against the real prompt (' + D.align[('base/' + topo)][agent] + ').')])
    ]));
  }
  function colourise(text, spans) {
    var own = new Array(text.length), nm = new Array(text.length);
    spans.slice().sort(function (a, b) { return a[3] - b[3]; }).forEach(function (sp) {
      for (var i = sp[0]; i < sp[1]; i++) { own[i] = originOf(sp[2]); nm[i] = sp[2]; }
    });
    var out = [], i = 0;
    while (i < text.length) {
      var j = i;
      while (j < text.length && own[j] === own[i] && nm[j] === nm[i]) j++;
      var chunk = esc(text.slice(i, j));
      out.push(own[i] ? '<span class="o-' + own[i] + '" title="' + esc(nm[i]) + '"' + (own[i] !== 'rt' && !ENGINE_BUILT[nm[i]] ? ' data-slot="' + esc(nm[i]) + '"' : '') + '>' + chunk + '</span>' : chunk);
      i = j;
    }
    return out.join('');
  }
  function flowchart(topo, sel) {
    var agents = topoAgents(topo).filter(function (a) { return a !== 'receptionist' && a !== 'database_handler'; });
    var hub = topo === 7 ? 'orchestrator' : 'planner';
    var ORDER = ['planner', 'user_input_inspector', 'dc_input_creator', 'dc_input_inspector', 'tool_caller',
                 'dc_output_inspector', 'design_engineer', 'requirements_analyst'];
    var spokes = agents.filter(function (a) { return a !== hub; })
      .sort(function (a, b) { return ORDER.indexOf(a) - ORDER.indexOf(b); });
    var W = 1000, ns = 'http://www.w3.org/2000/svg';
    var svg = doc.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' 150');
    function node(key, x, y, w, cls) {
      var g = doc.createElementNS(ns, 'g');
      g.setAttribute('class', 'node ' + (cls || '') + (key === sel ? ' on' : ''));
      g.addEventListener('click', function () { go('studio', 'prompts', withQ({ agent: key })); });
      var r = doc.createElementNS(ns, 'rect');
      r.setAttribute('x', x - w / 2); r.setAttribute('y', y - 17); r.setAttribute('width', w); r.setAttribute('height', 34); r.setAttribute('rx', 8);
      var tx = doc.createElementNS(ns, 'text');
      tx.setAttribute('x', x); tx.setAttribute('y', y + 4); tx.setAttribute('text-anchor', 'middle'); tx.textContent = disp(key);
      var tk = doc.createElementNS(ns, 'text');
      tk.setAttribute('x', x); tk.setAttribute('y', y + 30); tk.setAttribute('text-anchor', 'middle'); tk.setAttribute('class', 'tk');
      tk.textContent = '≈' + fmt(Math.round(D.prompts[String(topo)].prompts[key].length / 4)) + ' tok';
      g.appendChild(r); g.appendChild(tx); g.appendChild(tk);
      return g;
    }
    function line(x1, y1, x2, y2) {
      var l = doc.createElementNS(ns, 'line');
      l.setAttribute('x1', x1); l.setAttribute('y1', y1); l.setAttribute('x2', x2); l.setAttribute('y2', y2); l.setAttribute('class', 'edge');
      svg.appendChild(l);
    }
    var hx = 300, hy = 30;
    line(100, hy, hx, hy);
    var step = (W - 60) / Math.max(1, spokes.length);
    spokes.forEach(function (a, i) { line(hx, hy + 17, 30 + step * (i + 0.5), 112 - 17); });
    svg.appendChild(node('receptionist', 100, hy, 150));
    svg.appendChild(node(hub, hx, hy, 170, 'hub'));
    svg.appendChild(node('database_handler', 860, hy, 170));
    spokes.forEach(function (a, i) { svg.appendChild(node(a, 30 + step * (i + 0.5), 112, Math.min(170, step - 12))); });
    return svg;
  }

  /* ======================================================================
   * Validate (comes in P7)
   * ==================================================================== */
  function renderValidate(center, right) {
    add(center, head('Validate', LATER.validate));
    add(right, h('div', { 'class': 'insp' }, h('p', { 'class': 'muted' }, LATER.validate)));
  }

  /* ---------------- splitters (kit) ---------------- */
  function initSplitters() {
    Array.prototype.forEach.call(doc.querySelectorAll('.splitter'), function (bar) {
      bar.addEventListener('mousedown', function (ev) {
        var target = el(bar.getAttribute('data-target')), side = bar.getAttribute('data-side');
        var startX = ev.clientX, startW = target.getBoundingClientRect().width;
        bar.classList.add('drag');
        function move(e) { var dx = e.clientX - startX; target.style.width = Math.max(180, Math.min(640, side === 'left' ? startW + dx : startW - dx)) + 'px'; }
        function up() { bar.classList.remove('drag'); doc.removeEventListener('mousemove', move); doc.removeEventListener('mouseup', up); }
        doc.addEventListener('mousemove', move); doc.addEventListener('mouseup', up); ev.preventDefault();
      });
    });
  }

  /* ---------------- render loop ---------------- */
  var lastKey = '';
  function render() {
    parse();
    var app = el('app');
    var center = el('center');
    var keep = center && lastKey === R.page + '/' + R.section ? center.scrollTop : 0;
    app.innerHTML = '';
    if (R.page === 'studio') renderStudio(app);
    else renderLater(app);
    lastKey = R.page + '/' + R.section;
    center = el('center');
    if (center && keep) center.scrollTop = keep;
    if (center && R.q.scroll) center.scrollTop = parseInt(R.q.scroll, 10);
    var sel = doc.querySelector('.trow.sel');
    if (sel && !keep && !R.q.scroll && center) {
      var rel = sel.firstChild.getBoundingClientRect().top - center.getBoundingClientRect().top;
      if (rel > center.clientHeight * 0.55) center.scrollTop = Math.max(0, rel + center.scrollTop - 110);
    }
  }

  function init() {
    el('app').appendChild(h('div', { 'class': 'page' }, [h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Assembling every prompt of this setup… (first time only)')]));
    req('get_all').then(function (r) {
      D = r.data;
      root.addEventListener('hashchange', render);
      render();
    }).catch(function (e) {
      el('app').innerHTML = '';
      el('app').appendChild(h('div', { 'class': 'page' }, [h('h1', null, 'MAS Studio'),
        h('p', { 'class': 'sub err', style: 'white-space:pre-wrap' }, 'The Studio could not load its data: ' + (e && e.message ? e.message : e))]));
    });
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
  else init();

  root.Studio = { render: render, data: function () { return D; } };
}(window));
