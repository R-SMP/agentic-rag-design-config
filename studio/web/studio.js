/* ======================================================================
 * studio.js -- the MAS Studio (MAS-blueprint P5a-P5b, P6a).
 *
 * Plain ES5 in one IIFE, as the studio UI kit asks.  Every call to the
 * server goes through call()/req() and bridge.js (POST /api/<name>):
 * get_all answers the setup as the engine assembles it
 * (studio/engine_view.py), view one prompt-viewer combination (P5b).  The
 * screens are the Studio draft's (extra_utilities/docs/studio_draft/),
 * made real.
 *
 * P6a edits the text fields: a field's unsaved text lives in EDITS until
 * its Save (save_field); the link icon, own copies and Undo are calls of
 * their own (studio/editing.py), and each change re-reads the setup.  The
 * prompt viewer compares with the setup as the Studio opened it (diff).
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
    params: 'Editing the parameters comes in P6b.',
    access: 'Editing agent access comes in P6b.',
    tools: 'New tool and Edit come in P6c.',
    test: 'Test tool comes in P6c.',
    settings: 'Editing the settings comes in P6c.',
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
      'Editing the setup in ' + D.pack_dir + ': each text field saves on its own, straight to its files, and Undo puts a field back as it was when the Studio opened. ' +
      'Parameters and agent access come in P6b, tools and settings in P6c.');
    var left = h('div', { 'class': 'col side', id: 'colLeft', style: 'width:250px' }, renderNav());
    var center = h('div', { 'class': 'col center', id: 'center' });
    var right = h('div', { 'class': 'col side', id: 'colRight', style: 'width:380px' });
    var main = h('div', { id: 'main' }, [left, h('div', { 'class': 'splitter', 'data-target': 'colLeft', 'data-side': 'left' }), center,
      h('div', { 'class': 'splitter', 'data-target': 'colRight', 'data-side': 'right' }), right]);
    var sb = h('div', { 'class': 'statusbar' }, [
      pill('editing', 'good', 'Changes are written to the setup’s own files.'),
      h('span', { 'class': 'msg ' + STATUS.cls, id: 'statusMsg', title: STATUS.text }, STATUS.text),
      h('span', { id: 'unsavedCount' }, unsavedPill())
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
      add(g, row(s, null));
      (s.variants || []).forEach(function (v) { add(g, row(s, v.agent)); });
    });
    return g;
  }
  // One field's row: the shared text (agent null) or an agent's own copy.
  function row(s, agent) {
    var st = stored(s, agent), key = fkey(s.slot, agent);
    var multi = topoKeys(agent).length > 1;
    var unlinked = st.exists && !st.linked && multi;
    var selected = R.q.field === s.slot && (R.q.agent || null) === agent;
    var r = h('div', { 'class': 'trow' + (agent ? ' sub' : '') + (unlinked ? ' unlinked' : '') + (selected ? ' sel' : '') +
      (EDITS[key] ? ' dirty' : ''), 'data-fk': key });
    var label = h('div', { 'class': 'fl', onclick: function () { go('studio', R.section, withQ({ field: s.slot, agent: agent })); } }, [
      h('span', { 'class': 'nm' }, agent ? '↳ ' + disp(agent) : s.slot),
      h('span', { 'class': 'meta' }, agent ? [kpill('own copy for this agent')] : [
        kpill(s.kind), kpill(s.origin === 'tool' ? 'tool' : 'DC', s.origin === 'tool' ? 'tool' : 'dc'),
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null]),
      h('span', { 'class': 'meta' }, [st.exists && multi ? linkButton(s, agent) : null]),
      h('div', { 'class': 'racts', 'data-racts': key }, rowActions(s, agent))
    ]);
    add(r, label);
    ['3', '5', '7'].forEach(function (t) {
      var c = h('div', { 'class': 'cell' });
      if (agent && !inRoster(agent, t)) c.appendChild(h('div', { 'class': 'na' }, 'no ' + disp(agent) + ' in this topology'));
      else if (!st.exists) c.appendChild(h('div', { 'class': 'na' }, 'no shared text: an agent reads its own copy, or nothing'));
      else {
        var v = cellText(s, agent, t);
        if (v === null || v === undefined) c.appendChild(inheritedCell(s, agent, t));
        else c.appendChild(field(s, agent, st.linked ? 'all' : t, t, v));
      }
      add(r, c);
    });
    return r;
  }
  function linkButton(s, agent) {
    var st = stored(s, agent), dirty = !!EDITS[fkey(s.slot, agent)];
    return h('button', { 'class': 'link ' + (st.linked ? 'on' : 'off'), disabled: dirty || BUSY,
      title: dirty ? 'Save or discard the change first.' : st.linked
        ? 'Linked: one file for every topology. Click to unlink: each topology gets a file of its own, holding this text (no prompt changes).'
        : 'Unlinked: one file per topology. Click to link: you choose which text every topology keeps.',
      onclick: function (ev) { ev.stopPropagation(); if (st.linked) unlinkField(s, agent); else askLink(s, agent); } },
      st.linked ? '🔗 linked' : '⛓ unlinked');
  }
  // Save / Discard while the field has an unsaved change; Undo once it differs from the opened setup.
  function rowActions(s, agent) {
    var key = fkey(s.slot, agent);
    function stop(fn) { return function (ev) { ev.stopPropagation(); fn(); }; }
    if (EDITS[key]) {
      var problems = problemsOf(s, agent);
      return [problems.length ? pill(problems.length + (problems.length === 1 ? ' problem' : ' problems'), 'bad', problems.join('\n')) : null,
        h('button', { 'class': 'primary mini', disabled: BUSY || problems.length > 0,
          title: problems.length ? 'Fix the problems first (see the inspector).' : 'Write this field to its files.',
          onclick: stop(function () { saveField(s, agent); }) }, 'Save'),
        h('button', { 'class': 'mini', title: 'Forget the unsaved change.', onclick: stop(function () { discardField(s, agent); }) }, 'Discard')];
    }
    if (isChanged(s.slot, agent)) {
      return [pill('changed', 'warn', 'Changed since the Studio opened.'),
        h('button', { 'class': 'mini', disabled: BUSY, title: 'Put this field back as it was when the Studio opened.',
          onclick: stop(function () { undoField(s, agent); }) }, 'Undo')];
    }
    return [];
  }
  // A topology without a file of its own for this field: what it reads instead.
  function inheritedCell(s, agent, t) {
    var from = readsFrom(s, agent, t);
    return h('div', { 'class': 'inh' }, [
      h('div', { 'class': 'na' }, from.label),
      h('button', { 'class': 'mini', disabled: BUSY,
        title: 'Give the ' + t + '-agent topology a file of its own, starting from the text it reads now.',
        onclick: function (ev) { ev.stopPropagation(); giveOwnText(s, agent, t, from.text); } }, 'Give it its own text')]);
  }
  // a field's text, editable
  function field(s, agent, k, t, v) {
    var key = fkey(s.slot, agent), lines = (v || '').split('\n').length;
    var a = { spellcheck: 'false', 'data-fk': key, 'data-k': k, 'data-t': t,
      placeholder: v === '' && !landsIn(s.slot, +t, agent) ? 'not used: this topology never reads this field' : null,
      oninput: function (e) { onEdit(s, agent, k, e.target.value, e.target); },
      onfocus: function () { selectField(s, agent); } };
    if (s.kind !== 'block') a.onkeydown = function (e) { if (e.key === 'Enter') e.preventDefault(); };
    if (s.kind === 'block') { a.rows = Math.max(2, Math.min(6, lines)); return h('textarea', a, v); }
    if (s.kind === 'phrase') {
      a['class'] = 'phrase';
      a.rows = Math.max(1, Math.min(4, Math.ceil((v || '').length / 34)));
      return h('textarea', a, v);
    }
    a.type = 'text'; a.value = v;
    return h('input', a);
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
    var agent = R.q.agent && variantOf(s, R.q.agent) ? R.q.agent : null;
    var st = stored(s, agent), key = fkey(s.slot, agent), dirty = !!EDITS[key];
    var cur = ['7', '5', '3'].map(function (t) { return cellText(s, agent, t); }).filter(function (x) { return x !== null && x !== undefined; })[0] || '';
    var rows = whereRows(s.slot).filter(function (r) { return agent ? r.agents[agent] : sharedReaders(s.slot, r).length; });
    var files = (D.files[s.slot] || {})[agent || ''] || [];
    var err = FIELD_ERRORS[key];
    var problems = dirty ? problemsOf(s, agent) : [];
    var empty = dirty && editTexts(s, agent).some(function (x) { return cleanText(s.slot, x) === ''; });
    var box = h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, s.slot + (agent ? '  @' + agent : '')),
      h('div', { 'class': 'pills' }, [kpill(s.kind), kpill(s.origin === 'tool' ? 'tool text' : 'DC text', s.origin === 'tool' ? 'tool' : 'dc'),
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null,
        !st.exists ? kpill('no shared text') : st.linked ? kpill('linked 3·5·7') : kpill('per topology'),
        dirty ? pill('unsaved', 'warn') : null, isChanged(s.slot, agent) ? pill('changed since opened', 'warn') : null]),
      h('p', null, s.description || h('span', { 'class': 'muted' }, 'No description in the slot registry yet.')),
      h('div', { 'class': 'block' }, [h('h4', null, 'Checks')].concat(
        err ? [h('div', { 'class': 'banner bad boxed' }, [h('div', null, err.error)].concat(
          err.problems.map(function (p) { return h('div', null, '• ' + p); }),
          err.conflict ? [h('div', { style: 'margin-top:6px' }, h('button', { 'class': 'mini', disabled: BUSY,
            onclick: function () { reloadField(s, agent); } }, 'Reload this field'))] : []))] : [],
        !dirty ? [h('p', { 'class': 'muted' }, 'No unsaved change.')] :
          problems.length ? [h('ul', { 'class': 'checks bad' }, problems.map(function (p) { return h('li', null, ['✗', h('span', null, p)]); }))] :
          [h('ul', { 'class': 'checks good' }, [h('li', null, ['✓', h('span', null, 'No problems: it can be saved.')])])],
        empty ? [h('ul', { 'class': 'checks warn' }, [h('li', null, ['!', h('span', null, 'The text is empty: the agents that read this field get nothing here.')])])] : [])),
      h('div', { 'class': 'block' }, [h('h4', null, 'Shape'), h('ul', { 'class': 'checks' }, hints(s, cur).map(function (x) { return h('li', null, ['•', h('span', null, x)]); }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Where it lands · ' + rows.length + ' sentence' + (rows.length === 1 ? '' : 's')),
        dirty ? h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:6px' }, 'The unsaved text is shown as typed; after Save the engine assembles the exact sentences.') : null,
        rows.length ? null : h('p', { 'class': 'muted' }, 'Not in any prompt under the checked settings (base, all features on).')].concat(
        rows.slice(0, 5).map(function (r) { return whereCard(r, s, liveValue(s, agent, r)); }),
        rows.length > 5 ? [h('div', { 'class': 'muted', style: 'font-size:11.5px' }, '+ ' + (rows.length - 5) + ' more')] : [])),
      h('div', { 'class': 'block' }, [h('h4', null, 'Stored as'), h('div', { 'class': 'mono', style: 'font-size:11.5px;color:#b9bec8;white-space:pre-line' },
        files.length ? files.join('\n') : 'no file: ' + (agent ? 'this agent has no copy' : 'no shared text'))]),
      ownCopies(s, agent),
      isChanged(s.slot, agent) && !dirty ? h('div', { 'class': 'block' }, [h('h4', null, 'Undo'),
        h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:6px' }, 'Puts this field’s files back exactly as they were when the Studio opened.'),
        h('button', { disabled: BUSY, onclick: function () { undoField(s, agent); } }, 'Undo: back to as opened')]) : null
    ]);
    return box;
  }
  // Own copies: from the shared text, give an agent one; from a copy, remove it.
  function ownCopies(s, agent) {
    if (agent) {
      return h('div', { 'class': 'block' }, [h('h4', null, 'Own copy'),
        h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:6px' }, disp(agent) + ' reads this copy instead of the shared text. Remove it and it reads the shared text again.'),
        h('button', { 'class': 'danger', disabled: BUSY || !!EDITS[fkey(s.slot, agent)],
          title: EDITS[fkey(s.slot, agent)] ? 'Save or discard the change first.' : null,
          onclick: function () { askRemoveCopy(s, agent); } }, 'Remove own copy')]);
    }
    var have = (s.variants || []).map(function (v) { return v.agent; });
    var readers = {};
    whereRows(s.slot).forEach(function (r) { Object.keys(r.agents).forEach(function (a) { readers[a] = 1; }); });
    var all = {};
    Object.keys(D.roles.roster).forEach(function (t) { D.roles.roster[t].forEach(function (a) { all[a] = 1; }); });
    all.database_handler = 1;
    var free = Object.keys(all).filter(function (a) { return have.indexOf(a) < 0; })
      .sort(function (a, b) { return (readers[b] || 0) - (readers[a] || 0) || (disp(a) < disp(b) ? -1 : 1); });
    var btn = h('button', { disabled: BUSY || !free.length, onclick: function () { giveCopy(s, sel.value); } },
      free.length ? 'Give ' + disp(free[0]) + ' its own copy' : 'Every agent has its own copy');
    var sel = h('select', { disabled: BUSY || !free.length, onchange: function () { btn.textContent = 'Give ' + disp(sel.value) + ' its own copy'; } },
      free.map(function (a) { return h('option', { value: a }, disp(a) + (readers[a] ? '' : ' · does not read it now')); }));
    return h('div', { 'class': 'block' }, [h('h4', null, 'Own copies · ' + have.length),
      have.length ? h('div', { style: 'margin-bottom:6px' }, have.map(function (a) {
        return h('a', { 'class': 'kpill', style: 'display:inline-block;margin:2px;text-decoration:none', href: link('studio', R.section, withQ({ field: s.slot, agent: a })) }, disp(a));
      })) : null,
      h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:6px' }, isOverlay(s)
        ? 'This field has no shared text: an agent without a copy gets nothing here. A new copy starts empty.'
        : 'An agent with its own copy reads it instead of the shared text. A new copy starts from the text the agent reads now, so no prompt changes until you edit it.'),
      h('div', { 'class': 'row2' }, [sel, btn])]);
  }
  function whereCard(r, s, live) {
    var who = Object.keys(r.agents).map(function (a) {
      return h('span', null, [h('b', null, disp(a)), ' ', h('span', { 'class': 'topo' }, r.agents[a].join(' · '))]);
    });
    var before = r.before.length > 150 ? '…' + r.before.slice(-150) : r.before;
    var after = r.after.length > 140 ? r.after.slice(0, 140) + '…' : r.after;
    var value = r.value, cls = s && s.origin === 'tool' ? 'tool' : '';
    if (live !== null && live !== undefined) {
      value = live.split(/\s+/).filter(function (x) { return x; }).join(' ');
      if (value.length > 260) value = value.slice(0, 240) + ' …';
      cls += ' unsaved';
    }
    return h('div', { 'class': 'where' }, [
      h('div', { 'class': 'who' }, who.concat(r.only_with_features ? [pill('only with features on', 'warn')] : [],
        live !== null && live !== undefined ? [pill('unsaved', 'warn')] : [])),
      r.heading ? h('div', { 'class': 'sec' }, '§ ' + r.heading.slice(0, 80)) : null,
      h('div', { 'class': 's', html: esc(before) + ' <mark class="' + cls + '">' + esc(value) + '</mark> ' + esc(after) })
    ]);
  }

  /* ======================================================================
   * editing the text fields (P6a)
   * ==================================================================== */
  var EDITS = {};          // unsaved texts: fkey -> { all | '7' | '5' | '3': text }
  var FIELD_ERRORS = {};   // fkey -> the last refused change { error, problems, conflict }
  var BUSY = false;        // a change is being written, or the setup re-read
  var STATUS = { text: 'Ready.', cls: '' };
  var GEN = 0;             // bumped each time the setup is re-read

  function fkey(slot, agent) { return slot + '|' + (agent || ''); }
  function specOf(slot) { return D.slot_specs[slot] || {}; }
  function isOverlay(s) { return specOf(s.slot).missing === 'empty'; }
  function variantOf(s, agent) { return (s.variants || []).filter(function (v) { return v.agent === agent; })[0] || null; }
  // the stored texts of the shared text (agent null) or of an agent's copy
  function stored(s, agent) {
    if (!agent) return { values: s.values, linked: s.linked && !isOverlay(s), exists: !isOverlay(s) };
    var v = variantOf(s, agent);
    return v ? { values: v.values, linked: v.linked, exists: true } : { values: { 7: null, 5: null, 3: null }, linked: false, exists: false };
  }
  // the topologies a field has files for: all three for a shared text, the agent's for a copy
  function topoKeys(agent) { return ['7', '5', '3'].filter(function (t) { return !agent || inRoster(agent, t); }); }
  function firstVal(values) {
    return ['7', '5', '3'].map(function (t) { return values[t]; }).filter(function (x) { return x !== null && x !== undefined; })[0];
  }
  // the text as the engine reads it (engine/pack.py _clean)
  function cleanText(slot, t) {
    t = String(t).replace(/\r\n/g, '\n').replace(/\s+$/, '');
    return specOf(slot).strip === 'both' ? t.replace(/^\s+/, '') : t;
  }
  function cellText(s, agent, t) {
    var st = stored(s, agent), e = EDITS[fkey(s.slot, agent)];
    if (!st.exists) return null;
    if (st.linked) return e && e.all !== undefined ? e.all : st.values[t];
    return e && e[t] !== undefined ? e[t] : st.values[t];
  }
  function editTexts(s, agent) {
    var e = EDITS[fkey(s.slot, agent)] || {};
    return Object.keys(e).map(function (k) { return e[k]; });
  }
  function isChanged(slot, agent) { return (D.changed || []).indexOf(slot + (agent ? '@' + agent : '')) >= 0; }
  function setEdit(s, agent, k, text) {
    var key = fkey(s.slot, agent), st = stored(s, agent), e = EDITS[key] || {};
    var saved = k === 'all' ? firstVal(st.values) : st.values[k];
    if (saved !== null && saved !== undefined && cleanText(s.slot, text) === saved) delete e[k];
    else e[k] = text;
    if (Object.keys(e).length) EDITS[key] = e; else delete EDITS[key];
  }

  // The checks a text must pass before it is saved -- studio/editing.py
  // check_text, word for word (the server repeats them).
  var NAME_RE = /\$([a-z_][a-z0-9_]*)/g;
  var OPEN_RE = /<<(?!\/)([A-Za-z][A-Za-z0-9_]*(?::[a-z0-9_.]+)?)>>/g;
  var CLOSE_RE = /<<\/([A-Za-z][A-Za-z0-9_]*(?::[a-z0-9_.]+)?)>>/g;
  var FLAG_TOOL_RE = /^(?:tool:([a-z][a-z0-9_]*)|setting:([a-z][a-z0-9_]*)\.[a-z0-9_]+)$/;
  function allMatches(re, text) {
    var out = [], m;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) out.push(m[1]);
    return out;
  }
  function checkText(kind, text) {
    var problems = [];
    if (/[{}]/.test(text)) problems.push("It contains { or }: the engine would silently drop an agent's routing section (W45).  Write the text without braces.");
    if ((kind === 'phrase' || kind === 'word') && text.indexOf('\n') >= 0) problems.push('It is a one-line field: remove the line breaks.');
    var unknown = allMatches(NAME_RE, text).filter(function (n, i, a) { return D.text_names.indexOf(n) < 0 && a.indexOf(n) === i; }).sort();
    if (unknown.length) problems.push('Unknown $name: ' + unknown.map(function (n) { return '$' + n; }).join(', ') + '.');
    var opens = allMatches(OPEN_RE, text), closes = allMatches(CLOSE_RE, text);
    if (opens.slice().sort().join('\n') !== closes.slice().sort().join('\n')) problems.push('A <<marker>> is not closed by its <</marker>> (or the other way round).');
    opens.filter(function (t, i, a) { return a.indexOf(t) === i; }).sort().forEach(function (tag) {
      if (tag.indexOf('IF:') !== 0 && tag.indexOf('IFNOT:') !== 0) return;
      var flag = tag.slice(tag.indexOf(':') + 1), m = FLAG_TOOL_RE.exec(flag);
      if (D.text_flags.indexOf(flag) < 0 && !(m && D.pack_tools.indexOf(m[1] || m[2]) < 0)) problems.push('<<' + tag + '>> names an unknown flag.');
    });
    return problems;
  }
  function problemsOf(s, agent) {
    var out = [];
    editTexts(s, agent).forEach(function (t) {
      checkText(s.kind, cleanText(s.slot, t)).forEach(function (p) { if (out.indexOf(p) < 0) out.push(p); });
    });
    return out;
  }

  // What topology t reads when this field has no file of its own there
  // (the engine's rule, from D.resolve): label and text.
  function readsFrom(s, agent, t) {
    var path = (((D.resolve[s.slot] || {})[agent || '']) || {})[t];
    if (!path) return { label: 'no text: this topology reads nothing here', text: '' };
    var m = /^(.*?)(?:@([a-z0-9_]+))?(?:\.t(\d+))?\.md$/.exec(path.split('/').pop());
    var who = m[2] || null, n = m[3] || null;
    if (who === agent) return { label: 'uses the ' + (n ? n + '-agent' : 'linked') + ' text', text: stored(s, agent).values[n || t] || '' };
    return { label: 'uses the shared text' + (n ? ' (its ' + n + '-agent file)' : ''), text: s.values[n || t] || '' };
  }
  // the agents (with their topologies) of a where-row that read the SHARED text there
  function sharedReaders(slot, r) {
    if (specOf(slot).missing === 'empty') return [];
    return Object.keys(r.agents).filter(function (a) {
      return r.agents[a].some(function (t) {
        var p = (((D.resolve[slot] || {})[a]) || {})[String(t)];
        return !p || p.indexOf('@') < 0;
      });
    });
  }
  // the unsaved text topology t would read from this field (null: unchanged)
  function effective(s, agent, t) {
    var st = stored(s, agent), e = EDITS[fkey(s.slot, agent)];
    if (!e || !st.exists) return null;
    if (st.linked) return e.all !== undefined ? e.all : null;
    if (e[t] !== undefined) return e[t];
    if (st.values[t] === null || st.values[t] === undefined) {
      var p = (((D.resolve[s.slot] || {})[agent || '']) || {})[t], m = p && /\.t(\d+)\.md$/.exec(p);
      var own = p && (agent ? p.indexOf('@' + agent + '.') >= 0 : p.indexOf('@') < 0);
      if (m && own && e[m[1]] !== undefined) return e[m[1]];
    }
    return null;
  }
  // a where-row's sentence with the unsaved text in it (null: unchanged)
  function liveValue(s, agent, r) {
    if (!EDITS[fkey(s.slot, agent)]) return null;
    var as = agent ? [agent] : sharedReaders(s.slot, r);
    for (var i = 0; i < as.length; i++) {
      var ts = r.agents[as[i]] || [];
      for (var j = 0; j < ts.length; j++) {
        var v = effective(s, agent, String(ts[j]));
        if (v !== null) return cleanText(s.slot, v);
      }
    }
    return null;
  }

  /* -- typing ---------------------------------------------------------------- */
  function onEdit(s, agent, k, text, src) {
    var key = fkey(s.slot, agent);
    setEdit(s, agent, k, text);
    delete FIELD_ERRORS[key];
    // a linked field: every place that shows it shows the one text
    if (k === 'all') Array.prototype.forEach.call(doc.querySelectorAll('[data-fk="' + key + '"][data-k="all"]'), function (x) { if (x !== src) x.value = text; });
    refreshField(s, agent);
  }
  // redraw what depends on a field's unsaved text without touching the inputs
  function refreshField(s, agent) {
    var key = fkey(s.slot, agent);
    Array.prototype.forEach.call(doc.querySelectorAll('[data-racts="' + key + '"]'), function (x) {
      x.innerHTML = ''; add(x, rowActions(s, agent));
    });
    Array.prototype.forEach.call(doc.querySelectorAll('.trow[data-fk="' + key + '"], tr[data-fk="' + key + '"]'), function (x) {
      x.classList.toggle('dirty', !!EDITS[key]);
    });
    var lb = doc.querySelector('.trow[data-fk="' + key + '"] .link');
    if (lb) lb.parentNode.replaceChild(linkButton(s, agent), lb);
    var u = el('unsavedCount');
    if (u) { u.innerHTML = ''; add(u, unsavedPill()); }
    if (R.q.field === s.slot && (R.q.agent || null) === agent) refreshInspector(s);
  }
  function refreshInspector(s) {
    var right = el('colRight');
    if (!right || !right.querySelector('.insp')) return;
    right.innerHTML = '';
    add(right, inspectField(s));
  }
  // focusing a field selects it (the address changes without a redraw)
  function selectField(s, agent) {
    if (R.q.field === s.slot && (R.q.agent || null) === agent) return;
    root.history.replaceState(null, '', link(R.page, R.section, withQ({ field: s.slot, agent: agent })));
    parse();
    Array.prototype.forEach.call(doc.querySelectorAll('.trow.sel, tr.sel'), function (x) { x.classList.remove('sel'); });
    Array.prototype.forEach.call(doc.querySelectorAll('.trow[data-fk="' + fkey(s.slot, agent) + '"], tr[data-fk="' + fkey(s.slot, agent) + '"]'),
      function (x) { x.classList.add('sel'); });
    var right = el('colRight');
    if (right) { right.innerHTML = ''; add(right, inspectField(s)); }
  }
  function unsavedPill() {
    var n = Object.keys(EDITS).length;
    return n ? pill(n + ' unsaved', 'warn', Object.keys(EDITS).map(function (k) { return k.replace('|', ' @').replace(/ @$/, ''); }).join('\n')) : null;
  }
  function status(text, cls) {
    STATUS = { text: text, cls: cls || '' };
    var m = el('statusMsg');
    if (m) { m.textContent = text; m.title = text; m.className = 'msg ' + (cls || ''); }
  }
  function label(s, agent) { return '$' + s.slot + (agent ? ' (' + disp(agent) + '’s copy)' : ''); }

  /* -- the changes -------------------------------------------------------------- */
  // Re-read the setup (the engine re-assembles every prompt) and redraw.
  function reload() {
    return req('get_all').then(function (r) {
      D = r.data; GEN++;
      VIEWS = {}; VIEW_ERRORS = {}; VIEW_PENDING = {}; DIFFS = {}; DIFF_ERRORS = {}; DIFF_PENDING = {};
    });
  }
  // One change: the call, then the setup re-read.  The inputs stay
  // editable meanwhile (unsaved texts live in EDITS); the buttons that
  // change files wait.  *onOk* runs once the call succeeded.
  function change(name, args, key, done, onOk) {
    if (BUSY) return;
    BUSY = true;
    delete FIELD_ERRORS[key];
    status('Writing…', 'busy');
    render();
    call.apply(null, [name].concat(args)).then(function (r) {
      if (!r || r.ok === false) {
        FIELD_ERRORS[key] = { error: (r && r.error) || 'The change failed.', problems: (r && r.problems) || [], conflict: !!(r && r.conflict) };
        BUSY = false;
        status(FIELD_ERRORS[key].error, 'err');
        render();
        return null;
      }
      var warn = (r.warnings || []).join(' ');
      if (onOk) onOk();
      status(done + ' Re-assembling every prompt…', 'busy');
      return reload().then(function () {
        BUSY = false;
        status(done + (warn ? '  ' + warn : ''), warn ? 'warn' : 'ok');
        render();
      });
    }).catch(function (e) {
      BUSY = false;
      status('The Studio could not finish: ' + (e && e.message ? e.message : e), 'err');
      render();
    });
  }
  function saveField(s, agent) {
    var key = fkey(s.slot, agent), e = EDITS[key], st = stored(s, agent);
    if (!e || problemsOf(s, agent).length) return;
    var values = {}, base = {};
    Object.keys(e).forEach(function (k) {
      values[k] = e[k];
      var b = k === 'all' ? firstVal(st.values) : st.values[k];
      base[k] = b === undefined ? null : b;
    });
    var sent = JSON.stringify(values);
    // once written, the unsaved text is the saved one (unless typed on meanwhile)
    change('save_field', [s.slot, agent, values, base], key, 'Saved ' + label(s, agent) + '.', function () {
      if (JSON.stringify(EDITS[key] || {}) === sent) delete EDITS[key];
    });
  }
  function discardField(s, agent) {
    delete EDITS[fkey(s.slot, agent)];
    delete FIELD_ERRORS[fkey(s.slot, agent)];
    render();
  }
  function reloadField(s, agent) {
    delete EDITS[fkey(s.slot, agent)];
    BUSY = true;
    status('Reading the setup again…', 'busy');
    render();
    reload().then(function () {
      delete FIELD_ERRORS[fkey(s.slot, agent)];
      BUSY = false; status('The field shows what is on disk now.', 'ok'); render();
    }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
  }
  function undoField(s, agent) {
    delete EDITS[fkey(s.slot, agent)];
    change('undo_field', [s.slot, agent], fkey(s.slot, agent), label(s, agent) + ' is back as it was when the Studio opened.');
  }
  function unlinkField(s, agent) {
    change('unlink_field', [s.slot, agent], fkey(s.slot, agent),
      'Unlinked ' + label(s, agent) + ': each topology has a file of its own now, holding the same text (no prompt changed).');
  }
  function askLink(s, agent) {
    var st = stored(s, agent);
    var keys = ['7', '5', '3'].filter(function (t) { return st.values[t] !== null && st.values[t] !== undefined && (!agent || inRoster(agent, t)); });
    var choice = keys[0];
    var body = h('div', null, [
      h('p', { style: 'margin:0 0 10px;font-size:12.5px;line-height:1.5' }, 'Every topology will read ONE text. Which one do they keep? The other files are removed (Undo brings them back).'),
      h('div', null, keys.map(function (t) {
        return h('label', { 'class': 'pick' }, [
          h('input', { type: 'radio', name: 'keep', value: t, checked: t === choice, onchange: function () { choice = t; } }),
          h('span', null, [h('b', null, 'the ' + t + '-agent text'), h('div', { 'class': 'refval', style: 'margin-top:4px' }, st.values[t] || '(empty)')])]);
      }))]);
    showModal('Link ' + label(s, agent), body, [
      h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'primary', onclick: function () {
        closeModal();
        change('link_field', [s.slot, agent, choice], fkey(s.slot, agent),
          'Linked ' + label(s, agent) + ': every topology reads the ' + choice + '-agent text.');
      } }, 'Link')]);
  }
  function giveOwnText(s, agent, t, text) {
    var key = fkey(s.slot, agent), e = EDITS[key] || {};
    e[t] = text;
    EDITS[key] = e;
    root.history.replaceState(null, '', link(R.page, R.section, withQ({ field: s.slot, agent: agent })));
    render();
    var n = doc.querySelector('[data-fk="' + key + '"][data-t="' + t + '"]');
    if (n) n.focus();
    status('The ' + t + '-agent topology gets a file of its own when you save ' + label(s, agent) + '.', '');
  }
  function giveCopy(s, agent) {
    change('own_copy', [s.slot, agent], fkey(s.slot, agent), 'Gave ' + disp(agent) + ' its own copy of $' + s.slot + '.');
    root.history.replaceState(null, '', link(R.page, R.section, withQ({ field: s.slot, agent: agent })));
  }
  function askRemoveCopy(s, agent) {
    showModal('Remove ' + disp(agent) + '’s own copy', h('p', { style: 'margin:0;font-size:12.5px;line-height:1.5' },
      'Its file' + (((D.files[s.slot] || {})[agent] || []).length > 1 ? 's go' : ' goes') + ' and ' + disp(agent) +
      (isOverlay(s) ? ' gets nothing here again.' : ' reads the shared text $' + s.slot + ' again.') + ' Undo puts the field back as it was when the Studio opened.'), [
      h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'danger', onclick: function () {
        closeModal();
        root.history.replaceState(null, '', link(R.page, R.section, withQ({ field: s.slot, agent: null })));
        change('remove_copy', [s.slot, agent], fkey(s.slot, agent), 'Removed ' + disp(agent) + '’s own copy of $' + s.slot + '.');
      } }, 'Remove')]);
  }

  /* -- the dialog (kit) ----------------------------------------------------------- */
  function showModal(title, body, foot) {
    el('modalTitle').textContent = title;
    var b = el('modalBody'); b.innerHTML = ''; b.className = 'body scroll'; b.appendChild(body);
    var f = el('modalFoot'); f.innerHTML = ''; add(f, foot);
    el('modalBox').className = 'modal wide';
    el('modal').className = 'modal-back on';
  }
  function closeModal() { el('modal').className = 'modal-back'; }

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
      'Base nouns: model ', vocabInput('output_model', 'n', 'width:90px;margin:0 10px 0 4px'),
      'image ', vocabInput('output_image', 'n', 'width:90px;margin-left:4px')])));
    VOCAB_RULES.forEach(function (vr) {
      var s = slotByName(vr[0]);
      if (!s) return;
      var w = whereRows(s.slot)[0];
      var sent = w ? '…' + esc(w.before.slice(-70)) + ' <mark>' + esc(w.value) + '</mark> ' + esc(w.after.slice(0, 50)) + '…' : '';
      var key = fkey(s.slot, null);
      add(tb, h('tr', { 'class': (R.q.field === s.slot && !R.q.agent ? 'sel' : '') + (EDITS[key] ? ' dirty' : ''), 'data-fk': key, style: 'cursor:pointer',
        onclick: function () { go('studio', 'outputs', withQ({ field: s.slot, agent: null })); } }, [
        h('td', null, h('span', { 'class': 'pname' }, s.slot)),
        h('td', { style: 'width:190px' }, [vocabInput(s.slot, 'v'), h('div', { 'class': 'racts', 'data-racts': key }, rowActions(s, null))]),
        h('td', { 'class': 'muted', style: 'font-size:11.5px;width:160px' }, vr[1]),
        h('td', { style: 'font-size:11.5px;color:#b9bec8', html: sent })
      ]));
    });
    tbl.appendChild(tb);
    add(center, tbl);
    // the other fields of the section, and any vocabulary word with one text
    // per topology or an agent's own copy (the table edits one linked text)
    var inTable = {};
    VOCAB_RULES.forEach(function (vr) { inTable[vr[0]] = 1; });
    var rest = slotsOf('outputs').filter(function (s) { return !inTable[s.slot] || !stored(s, null).linked || (s.variants || []).length; });
    add(center, h('div', { style: 'padding:14px 16px 4px' }, h('h4', null, 'What the inspector checks in the images')));
    add(center, grid(rest));
    var sel = slotByName(R.q.field || 'output_images') || slotsOf('outputs')[0];
    if (sel) add(right, inspectField(sel));
  }
  // a vocabulary word, editable where it is one linked text
  function vocabInput(slot, where, style) {
    var s = slotByName(slot);
    if (!s) return null;
    var st = stored(s, null);
    if (!st.linked) return h('input', { type: 'text', value: firstVal(st.values) || '', readonly: true, style: style || null,
      title: 'One text per topology: edit it in the grid below.' });
    return h('input', { type: 'text', value: cellText(s, null, '7'), spellcheck: 'false', style: style || null,
      'data-fk': fkey(slot, null), 'data-k': 'all', 'data-t': where,
      onclick: function (e) { e.stopPropagation(); },
      onkeydown: function (e) { if (e.key === 'Enter') e.preventDefault(); },
      oninput: function (e) { onEdit(s, null, 'all', e.target.value, e.target); },
      onfocus: function () { selectField(s, null); } });
  }

  /* ======================================================================
   * Parameters
   * ==================================================================== */
  function renderParams(center, right) {
    var P = D.parameters.parameters;
    add(center, head('Parameters', 'The one parameter file (parameters.json): the validator, the parameter sliders, the database and the agents’ parameter count read it; the agents’ own parameter lists are checked against it. ' +
      P.length + ' parameters in ' + D.parameters.groups.length + ' groups.', [
      laterButton('Import JSON…', LATER.params), laterButton('Paste CSV…', LATER.params),
      laterButton('+ Add parameter', LATER.params), laterButton('+ Add group', LATER.params)]));
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
          h('td', null, h('input', { type: 'text', value: p.label, readonly: true, title: LATER.params })),
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
      laterButton('+ New tool', LATER.tools, 'primary')]));
    var wrap = h('div', { 'class': 'toolcards' });
    D.tools.forEach(function (t) {
      var info = D.tool_info[t.name] || { roles: [], images: [], settings: [] };
      var first = t.description.split('\n\n')[0].replace(/\s+/g, ' ');
      var settings = info.settings.length ? info.settings.join(', ') : 'none';
      add(wrap, h('div', { 'class': 'tcard' }, [
        h('div', { 'class': 'head' }, [h('span', { 'class': 'n' }, t.name), pill(t.display), kpill(t.kind === 'generator' ? 'generator · primary' : t.kind),
          h('span', { 'class': 'grow' }), laterButton('Edit', LATER.tools), laterButton('Test tool', LATER.test)]),
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
          return h('td', null, h('span', { 'class': 'seg ro', title: LATER.access }, PA.states.filter(function (o) {
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
        h('span', { 'class': 'seg ro', title: LATER.settings }, [h('button', { 'class': value ? 'on' : '' }, 'on'), h('button', { 'class': value ? '' : 'on' }, 'off')]) :
        h('select', { disabled: true, title: LATER.settings }, (choices || [value]).map(function (c) { return h('option', { selected: c === value }, c); }))),
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
   * Prompt viewer (inside the main window): every agent's prompt and tools
   * under any choice of the settings that change them (P5b), assembled by
   * the engine (POST /api/view)
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
  // The bar's names for the engine settings it offers (studio/engine_view.py
  // VIEWER_SETTINGS); each one's help text in settings.py is its tooltip.
  var SETTING_LABELS = { DC_INSPECTOR_ENABLED: 'DC Input Inspector', DCOI_COMPARISON_MODE: 'Comparison mode',
                         KEEP_IMAGES_IN_CONTEXT: 'Keep images in context', CHAIN_ACCESS: 'Chain access', OCR_ENABLED: 'OCR' };
  var RAG_LABELS = { off: 'off', on: 'on', all: 'on, every database tool' };
  var TOKENS_NOTE = 'Counted with tiktoken cl100k_base, the engine’s own counter; other providers’ tokenizers differ by a few percent.';
  var VIEWS = {}, VIEW_ERRORS = {}, VIEW_PENDING = {};   // by choice
  // the same choice compared with the setup as the Studio opened it: by choice + agent
  var DIFFS = {}, DIFF_ERRORS = {}, DIFF_PENDING = {};
  function viewTopo() { var t = parseInt(R.q.topo || '7', 10); return [3, 5, 7].indexOf(t) < 0 ? 7 : t; }
  function fromQuery(s, q) {
    if (s.type === 'bool') return q === '1';
    return s.values.filter(function (x) { return String(x) === q; })[0];
  }
  // The choice in the address: rag=, s.<SETTING>=, t.<tool>.<setting>=,
  // a.<agent>= (its parameter-list access); a missing key is the default.
  function viewChoice() {
    var V = D.viewer;
    var c = { topology: viewTopo(), rag: R.q.rag || V.rag_default, settings: {}, tools: {}, access: {} };
    V.settings.forEach(function (s) {
      if (R.q['s.' + s.name] !== undefined) c.settings[s.name] = fromQuery(s, R.q['s.' + s.name]);
    });
    V.tools.forEach(function (t) {
      var specs = t.settings.concat(t['switch'] ? [{ name: 'enabled', type: 'bool' }] : []), vals = {};
      specs.forEach(function (s) {
        var q = R.q['t.' + t.tool + '.' + s.name];
        if (q !== undefined) vals[s.name] = fromQuery(s, q);
      });
      if (Object.keys(vals).length) c.tools[t.tool] = vals;
    });
    Object.keys(R.q).forEach(function (k) { if (k.indexOf('a.') === 0) c.access[k.slice(2)] = R.q[k]; });
    return c;
  }
  function setChoice(key, value, dflt) {
    var q = {};
    q[key] = value === dflt ? null : (typeof value === 'boolean' ? (value ? '1' : '0') : String(value));
    go('studio', 'prompts', withQ(q));
  }
  function vcheck(label, value, onchange, disabled, title) {
    return h('label', { 'class': 'vchk' + (disabled ? ' off' : ''), title: title || null }, [
      h('input', { type: 'checkbox', checked: !!value, disabled: !!disabled,
        onchange: function (e) { onchange(e.target.checked); } }), label]);
  }
  function vselect(label, values, value, onchange, disabled, title) {
    return h('label', { 'class': 'vchk' + (disabled ? ' off' : ''), title: title || null }, [label,
      h('select', { disabled: !!disabled, onchange: function (e) {
        onchange(values.filter(function (x) { return String(x) === e.target.value; })[0]); } },
        values.map(function (x) { return h('option', { value: String(x), selected: x === value }, String(x)); }))]);
  }
  function viewerBar(topo, agent) {
    var V = D.viewer, c = viewChoice(), bar = [];
    function group(label, kids, title) {
      return h('span', { 'class': 'vgrp', title: title || null }, [h('span', { 'class': 'vlab' }, label)].concat(kids));
    }
    bar.push(group('Topology', h('span', { 'class': 'seg' }, [3, 5, 7].map(function (t) {
      return h('button', { 'class': t === topo ? 'on' : '', onclick: function () { go('studio', 'prompts', withQ({ topo: t, agent: null })); } }, String(t)); }))));
    bar.push(group('RAG', h('span', { 'class': 'seg' }, ['off', 'on', 'all'].map(function (r) {
      return h('button', { 'class': c.rag === r ? 'on' : '', onclick: function () { setChoice('rag', r, V.rag_default); } }, RAG_LABELS[r]); })), V.rag_help));
    V.tools.forEach(function (t) {
      var vals = c.tools[t.tool] || {}, kids = [];
      function val(s) { return vals[s.name] !== undefined ? vals[s.name] : s['default']; }
      var on = t['switch'] ? (vals.enabled !== undefined ? vals.enabled : t['switch']['default']) : true;
      if (t['switch']) kids.push(vcheck(t['switch'].label, on, function (v) { setChoice('t.' + t.tool + '.enabled', v, t['switch']['default']); }));
      t.settings.forEach(function (s) {
        var gate = s.only_with ? t.settings.filter(function (x) { return x.name === s.only_with; })[0] : null;
        var gateOn = !gate || !!val(gate);
        var title = !on ? 'The tool is off.' : !gateOn ? 'Read only while “' + gate.label + '” is on.' : null;
        var set = function (v) { setChoice('t.' + t.tool + '.' + s.name, v, s['default']); };
        kids.push(s.type === 'bool' ? vcheck(s.label, val(s), set, !on || !gateOn, title)
                                    : vselect(s.label, s.values, val(s), set, !on || !gateOn, title));
      });
      bar.push(group(t.display, kids));
    });
    bar.push(group('Settings', V.settings.map(function (s) {
      var value = c.settings[s.name] !== undefined ? c.settings[s.name] : s['default'];
      var inert = s.topologies.indexOf(topo) < 0;
      var title = (inert ? 'Does nothing in the ' + topo + '-agent topology. ' : '') + s.help;
      var set = function (v) { setChoice('s.' + s.name, v, s['default']); };
      return s.type === 'bool' ? vcheck(SETTING_LABELS[s.name] || s.name, value, set, inert, title)
                               : vselect(SETTING_LABELS[s.name] || s.name, s.values, value, set, inert, title);
    })));
    var PA = D.parameter_access, row = PA.rows.filter(function (r) { return r.agent === agent; })[0];
    var cell = row && row.cells[String(topo)];
    if (cell) {
      var state = c.access[agent] || cell;
      bar.push(group('Parameter list · ' + disp(agent), h('span', { 'class': 'seg' }, PA.states.filter(function (o) {
        return !(o.id === 'tool' && PA.no_tool.indexOf(agent) >= 0); }).map(function (o) {
        return h('button', { 'class': o.id === state ? 'on' : '', title: o.label,
          onclick: function () { setChoice('a.' + agent, o.id, cell); } }, o.short); })), 'Agent access: who sees the parameter list, and how.'));
    }
    bar.push(h('button', { onclick: function () { go('studio', 'prompts', { topo: R.q.topo || null, agent: R.q.agent || null, diff: R.q.diff || null }); } }, 'Defaults'));
    var any = (D.changed || []).length > 0;
    bar.push(group('Compare', vcheck('Changes since opened', R.q.diff === '1' && any, function (v) { go('studio', 'prompts', withQ({ diff: v ? '1' : null })); },
      !any, any ? 'Show this agent’s prompt as a line diff against the setup as the Studio opened it, under the same settings.' : 'Nothing has changed since the Studio opened.')));
    return bar;
  }
  function renderPrompts(center, right) {
    var topo = viewTopo(), choice = viewChoice(), key = JSON.stringify(choice);
    var view = VIEWS[key];
    var agents = view ? Object.keys(view.prompts) : topoAgents(topo);
    var agent = R.q.agent && agents.indexOf(R.q.agent) >= 0 ? R.q.agent : 'receptionist';
    add(center, head('Prompt viewer', 'The exact system prompt and tools each agent receives, assembled by the engine from this setup under the settings above. Click an agent.', viewerBar(topo, agent)));
    if (!view) {
      if (VIEW_ERRORS[key]) {
        add(center, h('div', { 'class': 'banner warn', style: 'margin:10px 16px;white-space:pre-wrap' }, VIEW_ERRORS[key]));
        return;
      }
      add(center, h('div', { 'class': 'insp muted' }, 'Assembling this combination…'));
      if (!VIEW_PENDING[key]) {
        VIEW_PENDING[key] = true;
        var gen = GEN;
        call('view', choice).then(function (r) {
          if (gen !== GEN) return;                  // the setup was re-read meanwhile
          if (r && r.ok) VIEWS[key] = r.data; else VIEW_ERRORS[key] = (r && r.error) || 'The view failed.';
        }, function (e) { if (gen === GEN) VIEW_ERRORS[key] = String(e && e.message ? e.message : e); }).then(function () {
          if (gen !== GEN) return;
          delete VIEW_PENDING[key];
          if (R.page === 'studio' && R.section === 'prompts' && JSON.stringify(viewChoice()) === key) render();
        });
      }
      return;
    }
    var diff = diffOf(choice, key, agent);
    add(center, h('div', { 'class': 'flow' }, flowchart(topo, agent, view, diff ? diff.changed_agents : [])));
    add(center, h('div', { style: 'padding:0 16px' }, h('div', { 'class': 'legend' }, [
      h('span', null, [h('span', { 'class': 'sw gen' }), 'engine text (generic)']), h('span', null, [h('span', { 'class': 'sw dc' }), 'your DC text']),
      h('span', null, [h('span', { 'class': 'sw tool' }), 'your tool text']), h('span', null, [h('span', { 'class': 'sw rt' }), 'filled in per session']),
      diff && diff.changed_agents.length ? h('span', null, [h('span', { 'class': 'sw chg' }), 'prompt changed since the Studio opened']) : null])));
    var text = view.prompts[agent], spans = view.spans[agent] || [], tools = view.tools[agent] || [];
    var pre = h('div', { 'class': 'prompt' });
    if (R.q.diff === '1' && (D.changed || []).length) {
      var dk = key + '|' + agent;
      if (DIFF_ERRORS[dk]) pre = h('div', { 'class': 'banner warn', style: 'margin:10px 16px;white-space:pre-wrap' }, DIFF_ERRORS[dk]);
      else if (!diff) pre = h('div', { 'class': 'insp muted' }, 'Assembling this combination as the Studio opened it…');
      else pre.appendChild(diffView(diff.lines));
    } else pre.innerHTML = colourise(text, spans);
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
    var toolTokens = tools.reduce(function (n, t) { return n + t.tokens; }, 0);
    add(right, h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, disp(agent) + ' · topology ' + topo),
      h('div', { 'class': 'pills', title: TOKENS_NOTE }, [kpill(fmt(text.length) + ' characters'), kpill(fmt(view.tokens[agent]) + ' tokens (cl100k)'),
        kpill(tools.length + ' tools · ' + fmt(toolTokens) + ' tokens')]),
      h('h4', null, 'Where the text comes from'),
      h('div', { 'class': 'stack' }, ['gen', 'dc', 'tool', 'rt'].map(function (k) { return h('div', { style: 'width:' + (100 * cnt[k] / text.length) + '%;background:' + col[k] }); })),
      h('div', { 'class': 'kv', style: 'grid-template-columns:120px 1fr;font-size:11.5px' }, [
        h('div', { 'class': 'k' }, 'engine (generic)'), h('div', null, Math.round(100 * cnt.gen / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'your DC text'), h('div', null, Math.round(100 * cnt.dc / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'your tool text'), h('div', null, Math.round(100 * cnt.tool / text.length) + ' %'),
        h('div', { 'class': 'k' }, 'per session'), h('div', null, Math.round(100 * cnt.rt / text.length) + ' %')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Tools this agent is given · ' + tools.length),
        tools.length ? null : h('p', { 'class': 'muted' }, 'None when the team is built.')].concat(tools.map(function (t) {
          return h('details', { 'class': 'vtool' }, [
            h('summary', null, [h('span', { 'class': 'mono' }, t.name), h('span', { 'class': 'muted' }, ' · ' + fmt(t.tokens) + ' tokens')]),
            h('div', { 'class': 'd' }, t.description),
            h('pre', { 'class': 'args' }, JSON.stringify(t.args, null, 1))]);
        }))),
      h('div', { 'class': 'block' }, [h('h4', null, 'Your fields in this prompt · ' + Object.keys(used).length),
        h('div', null, Object.keys(used).sort().map(function (n) {
          return h('a', { href: link('studio', (slotByName(n) || {}).section || 'tools', { field: n }), 'class': 'kpill ' + originOf(n), style: 'display:inline-block;margin:2px;text-decoration:none' }, n + (used[n] > 1 ? ' ×' + used[n] : ''));
        }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Exact'), h('p', { 'class': 'muted', style: 'font-size:11.5px' }, 'Colours come from markers placed while the engine assembled this prompt, then checked against the real prompt (' + view.align[agent] + ').')])
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
  // The view compared with the setup as the Studio opened it (POST
  // /api/diff): asked only once something has changed; null until it answers.
  function diffOf(choice, key, agent) {
    if (!(D.changed || []).length) return { changed_agents: [], lines: [] };
    var dk = key + '|' + agent;
    if (DIFFS[dk]) return DIFFS[dk];
    if (!DIFF_PENDING[dk] && !DIFF_ERRORS[dk]) {
      DIFF_PENDING[dk] = true;
      var gen = GEN;
      call('diff', choice, agent).then(function (r) {
        if (gen !== GEN) return;
        if (r && r.ok) DIFFS[dk] = r.data; else DIFF_ERRORS[dk] = (r && r.error) || 'The comparison failed.';
      }, function (e) { if (gen === GEN) DIFF_ERRORS[dk] = String(e && e.message ? e.message : e); }).then(function () {
        if (gen !== GEN) return;
        delete DIFF_PENDING[dk];
        if (R.page === 'studio' && R.section === 'prompts' && JSON.stringify(viewChoice()) === key) render();
      });
    }
    return null;
  }
  // a line diff: changed lines with three lines around them, the rest folded
  function diffView(lines) {
    var box = h('div', { 'class': 'diff' });
    if (!lines.some(function (l) { return l[0] !== '='; })) {
      box.appendChild(h('div', { 'class': 'muted' }, 'This agent’s prompt is the same as when the Studio opened.'));
      return box;
    }
    var keep = lines.map(function () { return false; });
    lines.forEach(function (l, i) {
      if (l[0] === '=') return;
      for (var j = Math.max(0, i - 3); j <= Math.min(lines.length - 1, i + 3); j++) keep[j] = true;
    });
    var skipped = 0;
    function fold() {
      if (skipped) box.appendChild(h('div', { 'class': 'd-fold' }, '⋯ ' + skipped + ' unchanged line' + (skipped === 1 ? '' : 's')));
      skipped = 0;
    }
    lines.forEach(function (l, i) {
      if (!keep[i]) { skipped++; return; }
      fold();
      box.appendChild(h('div', { 'class': l[0] === '+' ? 'd-add' : l[0] === '-' ? 'd-del' : 'd-eq' }, (l[0] === '=' ? '  ' : l[0] + ' ') + l[1]));
    });
    fold();
    return box;
  }
  function flowchart(topo, sel, view, changed) {
    var agents = Object.keys(view.prompts).filter(function (a) { return a !== 'receptionist' && a !== 'database_handler'; });
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
      var chg = (changed || []).indexOf(key) >= 0;
      g.setAttribute('class', 'node ' + (cls || '') + (key === sel ? ' on' : '') + (chg ? ' chg' : ''));
      g.addEventListener('click', function () { go('studio', 'prompts', withQ({ agent: key })); });
      var r = doc.createElementNS(ns, 'rect');
      r.setAttribute('x', x - w / 2); r.setAttribute('y', y - 17); r.setAttribute('width', w); r.setAttribute('height', 34); r.setAttribute('rx', 8);
      var tx = doc.createElementNS(ns, 'text');
      tx.setAttribute('x', x); tx.setAttribute('y', y + 4); tx.setAttribute('text-anchor', 'middle'); tx.textContent = disp(key);
      var tk = doc.createElementNS(ns, 'text');
      tk.setAttribute('x', x); tk.setAttribute('y', y + 30); tk.setAttribute('text-anchor', 'middle'); tk.setAttribute('class', 'tk');
      tk.textContent = fmt(view.tokens[key]) + ' tok';
      g.appendChild(r); g.appendChild(tx); g.appendChild(tk);
      if (chg) {
        var dot = doc.createElementNS(ns, 'circle');
        dot.setAttribute('cx', x + w / 2 - 7); dot.setAttribute('cy', y - 10); dot.setAttribute('r', 4); dot.setAttribute('class', 'chgdot');
        var tt = doc.createElementNS(ns, 'title');
        tt.textContent = 'Prompt changed since the Studio opened';
        g.appendChild(dot); g.appendChild(tt);
      }
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
    var act = doc.activeElement, fk = act && act.getAttribute ? act.getAttribute('data-fk') : null;
    var ft = fk ? act.getAttribute('data-t') : null, caret = fk ? [act.selectionStart, act.selectionEnd] : null;
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
    // the field being typed in keeps the cursor (focusing another one would select it)
    if (fk && fk === fkey(R.q.field || '', R.q.agent || null)) {
      var back = doc.querySelector('[data-fk="' + fk + '"][data-t="' + ft + '"]');
      if (back) {
        back.focus();
        try { back.setSelectionRange(caret[0], caret[1]); } catch (e) { /* not a text input */ }
      }
    }
  }

  function init() {
    el('app').appendChild(h('div', { 'class': 'page' }, [h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Assembling every prompt of this setup… (first time only)')]));
    req('get_all').then(function (r) {
      D = r.data;
      root.addEventListener('hashchange', render);
      // an unsaved change is lost with the page: ask first
      root.addEventListener('beforeunload', function (e) {
        if (Object.keys(EDITS).length) { e.preventDefault(); e.returnValue = ''; }
      });
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
