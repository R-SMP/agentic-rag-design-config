/* ======================================================================
 * studio.js -- the MAS Studio draft (proof of concept, no engine wiring).
 *
 * Plain ES5 in one IIFE, as the studio UI kit asks.  Every call to the
 * server goes through call()/req(); in the draft they are answered by
 * mock_bridge.js from the REAL propeller pack (draft_data.js), in the real
 * Studio by POST /api/<name>.
 *
 * Screens are hash routes, so each one has an address (and a screenshot):
 *   #/landing                         the three buttons
 *   #/start                           Create your own: example or blank
 *   #/import[?file=1]                 Import a setup (+ the summary card)
 *   #/studio/<section>[?field=..]     the Studio: sections | editor | inspector
 *      sections: identity parameters description outputs tools examples
 *                inputs access settings prompts validate
 *      extra:    &modal=newtool|download  &mode=local  &test=<tool>
 *                &param=<name>  &topo=3|5|7  &agent=<key>
 * ====================================================================== */
(function (root) {
  'use strict';

  var doc = root.document;
  var D = null;                        // the pack, from the bridge
  var R = { page: 'landing', section: 'identity', q: {} };
  var MODE = 'hosted';
  var SAVED_AT = new Date();

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
  function hhmm(d) { return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
  function disp(key) { return (D.roles.display[key] || key).replace(/^The /, ''); }

  function toast(text, kind) {
    var t = h('div', { 'class': 'toast ' + (kind || '') }, text);
    el('toasts').appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 4200);
  }
  function setStatus(text, cls) {
    var n = el('statusMsg');
    if (n) { n.textContent = text; n.className = 'msg ' + (cls || ''); }
  }

  /* ---------------- routing ---------------- */
  function parse() {
    var raw = (root.location.hash || '#/landing').slice(1);
    var i = raw.indexOf('?');
    var path = i < 0 ? raw : raw.slice(0, i);
    var q = {};
    if (i >= 0) raw.slice(i + 1).split('&').forEach(function (kv) {
      if (!kv) return;
      var p = kv.split('=');
      q[decodeURIComponent(p[0])] = p.length > 1 ? decodeURIComponent(p[1]) : '1';
    });
    var parts = path.replace(/^\//, '').split('/');
    R = { page: parts[0] || 'landing', section: parts[1] || 'identity', q: q };
    MODE = q.mode === 'local' ? 'local' : 'hosted';
  }
  function link(page, section, q) {
    q = q || {};
    if (MODE === 'local' && !('mode' in q)) q.mode = 'local';
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
    if (id === 'settings') return Object.keys(D.settings).length;
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
  function f104All() { return D.f104.blade_sections.concat(D.f104.mesh_checks); }
  function unusedSlots() {
    return D.slots.filter(function (s) { return !D.where[s.slot]; }).map(function (s) { return s.slot; });
  }

  /* ======================================================================
   * full-page screens
   * ==================================================================== */
  function renderLanding(app) {
    var p = h('div', { 'class': 'page' });
    add(p, [
      h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Set up a multi-agent system for your own design configurator: describe its parameters, the text its agents read, and its tools. Then download it and run it yourself.'),
      h('div', { 'class': 'cards' }, [
        bigcard('▶', 'Use the Propeller Configurator',
          'Open the ready-made example: the lab’s propeller configurator, ' + D.parameters.parameters.length +
          ' parameters, a team of AI agents that design, render and check propellers. Invite code required.',
          'Opens the propeller app ↗', function () { toast('Would open the propeller deployment (invite code as today).'); }, 'feat'),
        bigcard('✎', 'Create your own',
          'Describe your design configurator: its parameters, the text its agents read, its tools. Start blank or from the propeller example.',
          'Opens the Studio →', function () { go('start'); }),
        bigcard('⇪', 'Import a setup',
          'Continue from a setup file you downloaded earlier. It opens in the Studio for editing; nothing in it is run on this site.',
          'Upload a .zip →', function () { go('import'); })
      ]),
      h('div', { 'class': 'foot' }, [
        h('span', null, 'Nothing is stored on this server: your draft stays in this browser, and the setup file is your save.'),
        h('span', null, ['On your own computer instead: ', h('code', null, 'python -m studio')]),
        h('span', { style: 'margin-left:auto' }, 'engine 0.1 · setup format 1')
      ])
    ]);
    app.appendChild(p);
  }
  function bigcard(icon, title, body, state, onclick, cls) {
    return h('button', { 'class': 'bigcard ' + (cls || ''), onclick: onclick }, [
      h('div', { 'class': 'ic' }, icon), h('div', { 'class': 't' }, title),
      h('div', { 'class': 'b' }, body), h('div', { 'class': 'state' }, state)
    ]);
  }

  function renderStart(app) {
    var nTxt = D.slots.length;
    var p = h('div', { 'class': 'page' });
    add(p, [
      h('span', { 'class': 'back', onclick: function () { go('landing'); } }, '← Back'),
      h('h1', null, 'Create your own'),
      h('p', { 'class': 'sub' }, 'Give your configurator a name, then choose where to start. You can change everything later; the draft is autosaved in this browser.'),
      h('div', { 'class': 'row', style: 'max-width:520px;margin-top:22px' }, [
        h('label', { 'for': 'inName' }, 'Configurator name'),
        h('input', { id: 'inName', type: 'text', placeholder: 'e.g. turbine wheel', value: R.q.name || '' })
      ]),
      h('div', { 'class': 'hint', style: 'margin-left:118px' }, 'Used as $dc_name in the agents’ prompts ("the ___ design configurator").'),
      h('div', { 'class': 'cards', style: 'grid-template-columns:1fr 1fr' }, [
        bigcard('⧉', 'Start from the propeller example',
          'Every field filled with the propeller’s values: ' + D.parameters.parameters.length + ' parameters, ' + nTxt +
          ' text fields, ' + D.tools.length + ' tools. Change what is different in your configurator.',
          'Open the Studio →', function () { go('studio', 'identity'); }, 'feat'),
        bigcard('▢', 'Start blank',
          'Every field empty. The propeller value is shown beside each field as a reference, with a button to copy it.',
          'Open the Studio →', function () { go('studio', 'identity', { blank: '1' }); })
      ]),
      h('div', { 'class': 'foot' }, [h('span', null, 'Tip: you can also continue a setup file with “Import a setup” on the first page.')])
    ]);
    app.appendChild(p);
  }

  function renderImport(app) {
    var done = !!R.q.file;
    var nLinked = D.slots.filter(function (s) { return s.linked; }).length;
    var p = h('div', { 'class': 'page' });
    add(p, [
      h('span', { 'class': 'back', onclick: function () { go('landing'); } }, '← Back'),
      h('h1', null, 'Import a setup'),
      h('p', { 'class': 'sub' }, 'Upload a setup file (.zip) made with the Studio. It opens for editing only: the tools inside it are listed as code and are never run on this site.'),
      h('div', { 'class': 'dropzone' + (done ? ' done' : ''), onclick: function () {
        req('import_setup').then(function () { go('import', null, { file: '1' }); });
      } }, done ? ['✓ ', h('b', null, 'propeller.mas-setup.zip'), ' read in this browser session — nothing was stored on the server'] :
        [h('b', null, 'Drop a setup file here'), ' or click to choose one', h('br'), h('span', { style: 'font-size:11.5px' }, '.zip only · at most 25 MB · text, JSON, YAML, Python and image files inside')])
    ]);
    if (done) {
      var tools = D.tools.map(function (t) { return t.name; });
      add(p, h('div', { 'class': 'card', style: 'margin-top:16px;padding:16px 18px' }, [
        h('h4', null, 'What is in this setup file'),
        h('div', { 'class': 'kv', style: 'margin-top:8px' }, [
          h('div', { 'class': 'k' }, 'Configurator'), h('div', null, [h('b', null, D.pack.name), ' — ' + D.pack.domain]),
          h('div', { 'class': 'k' }, 'Setup format'), h('div', null, '1 (current) · written by engine 0.1'),
          h('div', { 'class': 'k' }, 'Parameters'), h('div', null, D.parameters.parameters.length + ' in ' + D.parameters.groups.length + ' groups'),
          h('div', { 'class': 'k' }, 'Text fields'), h('div', null, D.slots.length + ' (' + nLinked + ' shared by the three topologies, ' + (D.slots.length - nLinked) + ' with a text per topology)'),
          h('div', { 'class': 'k' }, 'Tools'), h('div', null, tools.join(', ')),
          h('div', { 'class': 'k' }, 'Code'), h('div', { 'class': 'codeflag' }, '⚠ ' + tools.length + ' Python files (tools/*/tool.py) — kept in the file, NOT run on this site'),
          h('div', { 'class': 'k' }, 'Secrets'), h('div', null, 'none inside ✓ · after download it needs 2 optional variables (RHINO_COMPUTE_URL, RHINO_COMPUTE_API_KEY)'),
          h('div', { 'class': 'k' }, 'Checks on upload'), h('div', { 'class': 'ok' }, '✓ zip structure  ✓ size (' + Math.round(D.pack_bytes / 1024) + ' KB unpacked)  ✓ file types  ✓ no secret values found')
        ]),
        h('div', { style: 'display:flex;gap:8px;margin-top:14px' }, [
          h('button', { 'class': 'primary', onclick: function () { go('studio', 'identity'); } }, 'Open in the Studio'),
          h('button', { onclick: function () { go('import'); } }, 'Choose another file')
        ])
      ]));
    }
    add(p, h('div', { 'class': 'foot' }, [h('span', null, 'Running an imported setup on this site is planned for later, and only for setups whose tools all run on the user’s own servers (option C).')]));
    app.appendChild(p);
  }

  /* ======================================================================
   * the Studio shell: toolbar / banner / 3 columns / status bar
   * ==================================================================== */
  function renderStudio(app) {
    var local = MODE === 'local';
    var tb = h('div', { 'class': 'toolbar' }, [
      h('span', { 'class': 'title', style: 'cursor:pointer', onclick: function () { go('landing'); } }, 'MAS Studio'),
      h('span', { 'class': 'pack' }, ['setup: ', h('b', null, R.q.blank ? '(untitled)' : D.pack.name), R.q.blank ? ' · blank' : ' · from the propeller example']),
      pill(local ? 'local' : 'hosted', local ? 'mode-local' : 'mode-hosted',
           local ? 'python -m studio on this computer' : 'the Studio website'),
      h('span', { 'class': 'grow' }),
      h('button', { onclick: function () { go('studio', 'validate'); } }, 'Validate'),
      h('button', { onclick: function () { go('studio', R.section, withQ({ modal: 'download' })); } }, 'Download setup file'),
      h('button', { 'class': 'primary', onclick: function () { go('studio', R.section, withQ({ modal: 'download' })); } }, 'Download full package'),
      local ? h('span', { 'class': 'sep' }) : null,
      local ? h('button', { onclick: function () { toast('Prepare for GitHub: tool tests, offline checks, .gitignore, first commit, DEPLOY.md.'); } }, 'Prepare for GitHub') : null
    ]);
    var banner = h('div', { 'class': 'banner ' + (local ? 'info' : 'info') },
      local ? 'Local mode (python -m studio): your setup is saved to dc_pack/ on this computer, tools can be tested, and Prepare for GitHub runs the git steps.'
            : (R.q.blank ? 'Blank setup: every field is empty — the grey text in each box is the propeller’s value, for reference. ' : '') +
              'Draft autosaved in this browser at ' + hhmm(SAVED_AT) + '. Nothing is kept on the server — download the setup file to keep your work.');
    var left = h('div', { 'class': 'col side', id: 'colLeft', style: 'width:250px' }, renderNav());
    var center = h('div', { 'class': 'col center', id: 'center' });
    var right = h('div', { 'class': 'col side', id: 'colRight', style: 'width:380px' });
    var main = h('div', { id: 'main' }, [left, h('div', { 'class': 'splitter', 'data-target': 'colLeft', 'data-side': 'left' }), center,
      h('div', { 'class': 'splitter', 'data-target': 'colRight', 'data-side': 'right' }), right]);
    var sb = h('div', { 'class': 'statusbar' }, [
      pill(local ? 'saved to dc_pack/' : 'autosaved', 'good'),
      h('span', { 'class': 'msg', id: 'statusMsg' }, 'Ready.'),
      h('div', { 'class': 'progress' }, h('div', { id: 'progressBar' }))
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
    add(nav, [h('div', { 'class': 'grp' }, h('h4', null, 'Your setup')),
      h('div', { 'class': 'progressline', title: '9 of 9 sections complete' }, h('div', { style: 'width:100%' }))]);
    SECTIONS.forEach(function (s) {
      add(nav, h('a', { 'class': R.section === s.id ? 'on' : '', href: link('studio', s.id, R.q.blank ? { blank: '1' } : {}) }, [
        h('span', { 'class': 'num' }, s.n), h('span', { 'class': 'lab' }, s.label),
        h('span', { 'class': 'cnt' }, sectionCount(s.id)),
        h('span', { 'class': 'st ' + (R.q.blank && s.id !== 'identity' ? 'muted' : 'ok') }, R.q.blank && s.id !== 'identity' ? '○' : '✓')
      ]));
    });
    add(nav, h('div', { 'class': 'grp', style: 'margin-top:8px' }, h('h4', null, 'Check')));
    CHECK_PAGES.forEach(function (s) {
      add(nav, h('a', { 'class': R.section === s.id ? 'on' : '', href: link('studio', s.id) }, [
        h('span', { 'class': 'num' }, s.id === 'prompts' ? '▤' : '✔'), h('span', { 'class': 'lab' }, s.label),
        s.id === 'validate' ? h('span', { 'class': 'st warn' }, validateSummary().warn + ' ⚠') : null
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
        present.length > 1 ? h('span', { 'class': 'link ' + (unlinked ? 'off' : 'on'), title: unlinked ? 'Click to link: choose which text to keep for all' : 'Click to unlink: give each topology its own text' },
          unlinked ? '⛓ unlinked' : '🔗 linked') : null])
    ]);
    add(r, label);
    [3, 5, 7].forEach(function (t) {
      var v = values[String(t)];
      var c = h('div', { 'class': 'cell' });
      if (agent && !inRoster(agent, t)) c.appendChild(h('div', { 'class': 'na' }, 'no ' + disp(agent) + ' in this topology'));
      else if (v === null || v === undefined) c.appendChild(h('div', { 'class': 'na' }, agent ? 'uses the shared text' : 'no file'));
      else if (v === '' && !landsIn(s.slot, t, agent)) c.appendChild(h('div', { 'class': 'na' }, 'not used'));
      else c.appendChild(editor(s, R.q.blank ? '' : v, R.q.blank ? v : null));
      add(r, c);
    });
    return r;
  }
  function editor(s, v, placeholder) {
    var lines = (v || placeholder || '').split('\n').length;
    if (s.kind === 'block') {
      return h('textarea', { rows: Math.max(2, Math.min(6, lines)), placeholder: placeholder ? 'propeller: ' + placeholder.slice(0, 160) : null,
        spellcheck: 'false' }, v);
    }
    if (s.kind === 'phrase') {
      var len = (v || placeholder || '').length;
      return h('textarea', { 'class': 'phrase', rows: Math.max(1, Math.min(4, Math.ceil(len / 34))), spellcheck: 'false',
        placeholder: placeholder ? 'propeller: ' + placeholder : null }, v);
    }
    return h('input', { type: 'text', value: v, placeholder: placeholder ? 'propeller: ' + placeholder : null, spellcheck: 'false' });
  }

  function hints(s, v) {
    var out = [];
    if (s.kind === 'phrase') out.push('One line: it sits inside a generic sentence and is re-wrapped at 80 columns.');
    if (s.kind === 'word') out.push('A single word or short noun phrase (vocabulary).');
    if (s.kind === 'block') out.push('Multi-line Markdown; it stands on its own line in the prompt.');
    if (/^\(/.test(v)) out.push('Keep the parentheses: the sentence expects "( … )".');
    if (/^,/.test(v)) out.push('Starts with a comma: it continues the sentence before it.');
    if (/^"/.test(v)) out.push('A quoted list: "…", "…".');
    if (/<<BSV_ON>>/.test(v)) out.push('Carries <<BSV_ON>>: shown only while the blade-sections tool is on.');
    if (/<<MESH_ON>>/.test(v)) out.push('Carries <<MESH_ON>>: shown only while mesh checks are on.');
    return out;
  }
  function inspectField(s) {
    var agent = R.q.agent || null, v7 = s.values['7'] || s.values['5'] || s.values['3'] || '';
    if (agent) (s.variants || []).forEach(function (x) { if (x.agent === agent) v7 = x.values['7'] || x.values['5'] || x.values['3'] || ''; });
    var rows = whereRows(s.slot).filter(function (r) { return !agent || r.agents[agent]; });
    var cur = R.q.blank ? '' : v7;          // what the user has typed so far
    var needed = [3, 5, 7].some(function (t) { return landsIn(s.slot, t); });
    var checks = [
      [!/[{}]/.test(cur), 'no { or } (W45)'],
      [s.kind !== 'phrase' || cur.indexOf('\n') < 0, 'one line'],
      [true, 'every $name is a known field'],
      [!!cur || !needed, cur ? 'not empty' : needed ? 'empty — required: ' + rows.length + ' sentence(s) need it' : 'empty — allowed here']
    ];
    var box = h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, s.slot + (agent ? '  @' + agent : '')),
      h('div', { 'class': 'pills' }, [kpill(s.kind), kpill(s.origin === 'tool' ? 'tool text' : 'DC text', s.origin === 'tool' ? 'tool' : 'dc'),
        s.linked ? kpill('linked 3·5·7') : kpill('per topology'), f104All().indexOf(s.slot) >= 0 ? pill('F104', 'warn', 'mentions a feature but has no feature marker') : null]),
      h('p', null, s.description || h('span', { 'class': 'muted' }, 'No description yet (the registry will hold one per field).')),
      h('div', { 'class': 'block' }, [h('h4', null, 'Propeller value'), h('div', { 'class': 'refval' }, v7 || '(empty)'),
        h('div', { style: 'margin-top:5px;display:flex;gap:6px' }, [h('button', { onclick: function () { toast('Copied the propeller value into the field.', 'ok'); } }, 'Copy example')])]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Shape'), h('ul', { 'class': 'checks' }, hints(s, v7).map(function (x) { return h('li', null, ['•', h('span', null, x)]); }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Live checks'), h('ul', { 'class': 'checks' }, checks.map(function (c) {
        return h('li', null, [h('span', { 'class': c[0] ? 'ok' : 'warn' }, c[0] ? '✓' : '⚠'), h('span', null, c[1])]);
      }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Where it lands · ' + rows.length + ' sentence' + (rows.length === 1 ? '' : 's')),
        rows.length ? null : h('p', { 'class': 'muted' }, 'Not in any prompt under the checked settings (base, all features on).')].concat(
        rows.slice(0, 5).map(function (r) { return whereCard(r, s); }),
        rows.length > 5 ? [h('div', { 'class': 'muted', style: 'font-size:11.5px' }, '+ ' + (rows.length - 5) + ' more')] : [])),
      h('div', { 'class': 'block' }, [h('h4', null, 'Stored as'), h('div', { 'class': 'mono', style: 'font-size:11.5px;color:#b9bec8' },
        s.linked ? 'dc_pack/fragments/' + s.slot + '.md' : 'dc_pack/fragments/' + s.slot + '.t3.md · .t5.md · .t7.md')])
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
    add(center, head('Outputs & vocabulary', 'Type two nouns; the other forms are filled in by rule, each still editable. Every form is shown in a real sentence of the prompts.', [legendGrid()]));
    var tbl = h('table', { 'class': 'ptab', style: 'margin:10px 16px 6px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Form', 'Value', 'Rule', 'In a real sentence'].map(function (x) { return h('th', null, x); })))]);
    var tb = h('tbody');
    add(tb, h('tr', { 'class': 'grp' }, h('td', { colspan: 4 }, [
      'Base nouns: model ', h('input', { type: 'text', value: (slotByName('output_model').values['7']), style: 'width:90px;margin:0 10px 0 4px' }),
      'image ', h('input', { type: 'text', value: (slotByName('output_image').values['7']), style: 'width:90px;margin-left:4px' })])));
    VOCAB_RULES.forEach(function (vr) {
      var s = slotByName(vr[0]);
      if (!s) return;
      var w = whereRows(s.slot)[0];
      var sent = w ? '…' + esc(w.before.slice(-70)) + ' <mark>' + esc(w.value) + '</mark> ' + esc(w.after.slice(0, 50)) + '…' : '';
      add(tb, h('tr', { 'class': R.q.field === s.slot ? 'sel' : '', style: 'cursor:pointer', onclick: function () { go('studio', 'outputs', withQ({ field: s.slot })); } }, [
        h('td', null, h('span', { 'class': 'pname' }, s.slot)),
        h('td', { style: 'width:150px' }, h('input', { type: 'text', value: s.values['7'] })),
        h('td', { 'class': 'muted', style: 'font-size:11.5px;width:160px' }, vr[1]),
        h('td', { style: 'font-size:11.5px;color:#b9bec8', html: sent })
      ]));
    });
    tbl.appendChild(tb);
    add(center, tbl);
    var rest = slotsOf('outputs').filter(function (s) { return s.slot.indexOf('output_') !== 0; });
    add(center, h('div', { style: 'padding:14px 16px 4px' }, h('h4', null, 'What the inspector checks in the images')));
    add(center, grid(rest));
    var sel = slotByName(R.q.field || 'output_images');
    add(right, inspectField(sel));
  }

  /* ======================================================================
   * Parameters
   * ==================================================================== */
  function renderParams(center, right) {
    var P = D.parameters.parameters;
    add(center, head('Parameters', 'The one list every part of the system reads: the agents’ prompts, the parameter sliders, the validator and the database. ' +
      P.length + ' parameters in ' + D.parameters.groups.length + ' groups.', [
      h('button', null, 'Import JSON…'), h('button', null, 'Paste CSV…'), h('button', null, '+ Add parameter'), h('button', null, '+ Add group'),
      h('span', { 'class': 'muted', style: 'font-size:11.5px;margin-left:6px' }, 'CSV columns: name, type, min, max, default, unit, description')]));
    var t = h('table', { 'class': 'ptab' }, h('thead', null, h('tr', null,
      ['Name', 'Label', 'Type', 'Min', 'Max', 'Step', 'Default', 'Unit'].map(function (x) { return h('th', null, x); }))));
    var tb = h('tbody');
    D.parameters.groups.forEach(function (g) {
      add(tb, h('tr', { 'class': 'grp' }, h('td', { colspan: 8 }, [g.label,
        h('img', { 'class': 'thumb', src: '../../../web/images/' + g.id + '-profile.png', alt: '' })])));
      P.filter(function (p) { return p.group === g.id; }).forEach(function (p) {
        var bad = unitMismatch(p);
        add(tb, h('tr', { 'class': (R.q.param === p.name ? 'sel ' : '') + (bad ? 'warnrow' : ''), style: 'cursor:pointer',
          onclick: function () { go('studio', 'parameters', withQ({ param: p.name })); } }, [
          h('td', null, h('span', { 'class': 'pname' }, p.name)),
          h('td', null, h('input', { type: 'text', value: p.label })),
          h('td', { style: 'width:80px' }, h('select', null, ['int', 'float'].map(function (o) { return h('option', { selected: o === p.type }, o); }))),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.min })),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.max })),
          h('td', { 'class': 'num', style: 'width:64px' }, h('input', { type: 'text', value: p.step })),
          h('td', { 'class': 'num', style: 'width:70px' }, h('input', { type: 'text', value: p.default })),
          h('td', null, h('input', { type: 'text', value: p.unit, 'class': bad ? 'invalid' : null }))
        ]));
      });
    });
    t.appendChild(tb);
    add(center, h('div', { style: 'padding:0 16px 20px' }, t));
    var p = P.filter(function (x) { return x.name === (R.q.param || 'middlePos'); })[0] || P[0];
    var bad = unitMismatch(p);
    add(right, h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, p.name),
      h('div', { 'class': 'pills' }, [kpill(p.type), kpill('[' + p.min + '; ' + p.max + ']'), kpill('default ' + p.default)]),
      h('p', null, p.description),
      bad ? h('div', { 'class': 'banner warn', style: 'border:1px solid #7a5a1a;border-radius:7px;margin:10px 0' }, [
        h('b', null, 'Two copies disagree on the unit. '), 'The agents’ parameter list says “' + p.unit_prompt + '”; the slider page says “' +
        p.unit + '”. Today these are separate hand-kept copies; with one parameter list (phase P2) they cannot drift.']) : null,
      h('div', { 'class': 'block' }, [h('h4', null, 'Unit'), h('div', { 'class': 'kv', style: 'grid-template-columns:110px 1fr' }, [
        h('div', { 'class': 'k' }, 'slider label'), h('div', null, p.unit || '—'),
        h('div', { 'class': 'k' }, 'agents’ text'), h('div', null, p.unit_prompt || '—')])]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Generated from this one entry'), h('ul', { 'class': 'checks' }, [
        'the parameter list in the agents’ prompts (full / names only, per agent — see Agent access)',
        'the key list and types the validator enforces', 'the slider on the Parameters page of the web app',
        'the in-browser preview’s input check', 'the database’s parameter schema (a new version on any change)'].map(function (x) {
        return h('li', null, ['•', h('span', null, x)]); }))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Prompt notes (optional)'), h('textarea', { rows: 3, style: 'width:100%', placeholder: 'Extra text the agents read about this parameter' })])
    ]));
  }

  /* ======================================================================
   * Tools (+ New tool overlay, + local-mode Test tool)
   * ==================================================================== */
  var TOOL_META = {
    generate_and_render_propeller: { roles: ['tool_runner'], outputs: 'model: .obj · images: isometric, top, side (side off by default) · quality-check numbers',
      settings: 'quality_checks, render_library, backend, views', secrets: 'RHINO_COMPUTE_URL, RHINO_COMPUTE_API_KEY (both optional)',
      deps: 'trimesh, pyrender, pyvista, compute-rhino3d, rhino3dm, DracoPy · apt: libosmesa6, nodejs' },
    render_blade_sections: { roles: ['tool_runner'], outputs: 'model: none · images: blade_sections.png', settings: 'enabled',
      secrets: 'none', deps: 'Pillow' }
  };
  function rolesLine(role) {
    var key = ROLE_ROWS.filter(function (r) { return r.role === role; })[0].key;
    return [3, 5, 7].map(function (t) { var a = holder(key, t); return (a ? disp(a) : '—') + ' (' + t + ')'; }).join(' · ');
  }
  function renderTools(center, right) {
    var local = MODE === 'local';
    add(center, head('Tools', 'The functions your agents call to build and look at a design. Each tool is a plain Python function plus a manifest: what it is, which role may call it, what it produces, and the text the agents read about it.', [
      h('button', { 'class': 'primary', onclick: function () { go('studio', 'tools', withQ({ modal: 'newtool' })); } }, '+ New tool'),
      h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'Templates: RhinoCompute + Grasshopper · Python function · Node script · HTTP endpoint')]));
    var wrap = h('div', { 'class': 'toolcards' });
    D.tools.forEach(function (t) {
      var m = TOOL_META[t.name] || {};
      var first = t.description.split('\n\n')[0].replace(/\s+/g, ' ');
      var card = h('div', { 'class': 'tcard' + (R.q.test === t.name ? ' selected' : '') }, [
        h('div', { 'class': 'head' }, [h('span', { 'class': 'n' }, t.name), pill(t.display), kpill(t.kind === 'generator' ? 'generator · primary' : 'second generator'),
          h('span', { 'class': 'grow' }), h('button', null, 'Edit'),
          h('button', { disabled: !local, title: local ? 'Run it with the default parameters' : 'This site never runs a setup’s Python',
            onclick: function () { go('studio', 'tools', withQ({ test: t.name })); } }, 'Test tool')]),
        h('div', { 'class': 'd' }, first),
        h('div', { 'class': 'grid2' }, [
          h('div', { 'class': 'k' }, 'Called by'), h('div', null, 'tool runner: ' + rolesLine('tool_runner')),
          h('div', { 'class': 'k' }, 'Produces'), h('div', null, m.outputs),
          h('div', { 'class': 'k' }, 'Settings'), h('div', null, m.settings),
          h('div', { 'class': 'k' }, 'Secrets'), h('div', null, m.secrets),
          h('div', { 'class': 'k' }, 'Dependencies'), h('div', null, m.deps),
          h('div', { 'class': 'k' }, 'Code'), h('div', { 'class': 'mono', style: 'font-size:11px' }, 'dc_pack/tools/' + t.name + '/tool.py  (today: ' + t.file + ')')
        ]),
        !local ? h('div', { 'class': 'disabled-note', style: 'margin-top:8px' }, 'Test tool is available after download, on your own computer: python -m studio') : null
      ]);
      add(wrap, card);
      if (local && R.q.test === t.name) add(wrap, testResult(t));
    });
    add(center, wrap);
    add(center, h('div', { style: 'padding:6px 16px 4px' }, [h('h4', null, 'Tool text the agents read · ' + slotsOf('tools').length + ' fields'),
      h('div', { 'class': 'muted', style: 'font-size:11.5px' }, 'Today’s propeller tool text. With the tool contract (phase P3) most of it moves into each tool’s own sections.')]));
    add(center, grid(slotsOf('tools')));
    if (R.q.field) { add(right, inspectField(slotByName(R.q.field))); if (R.q.modal === 'newtool') openNewTool(); return; }
    add(right, h('div', { 'class': 'insp' }, [
      h('h4', null, 'How tools reach the agents'),
      h('p', null, 'A tool is bound to a ROLE, not to an agent. The engine gives it to whichever agent holds that role in the running topology.'),
      h('div', { 'class': 'block' }, [h('h4', null, 'tool runner'), h('div', { 'class': 'kv', style: 'grid-template-columns:70px 1fr' },
        [3, 5, 7].reduce(function (acc, t) { var a = holder('tool_caller', t); return acc.concat([h('div', { 'class': 'k' }, t + '-agent'), h('div', null, a ? disp(a) : '—')]); }, []))]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Text the agents read about tools'), h('p', null, 'Each tool adds its text to fixed sections of the agents that hold its role: “How to use your configurator tools”, “Hard constraints — tools” and “Reporting tool results”. Today’s propeller tool text is in the ' +
        slotsOf('tools').length + ' fields below the cards.')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'On this site'), h('p', null, local ? 'Local mode: tools are imported and run on this computer, in a separate process.' :
        'Hosted: a tool’s Python file is stored in your setup file and checked as text only. It is never imported or run here.')])
    ]));
    if (R.q.modal === 'newtool') openNewTool();
  }
  function testResult(t) {
    var r = D.test_run;
    if (!r || !r.ok) return h('div', { 'class': 'testres' }, 'The test run failed: ' + (r && r.error));
    return h('div', { 'class': 'testres' }, [
      h('div', { style: 'display:flex;gap:8px;align-items:center;margin-bottom:8px' }, [h('b', null, 'Test run — ' + t.name),
        pill('local', 'mode-local'), h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'default parameters, separate process')]),
      h('ul', { 'class': 'checks', style: 'margin-bottom:8px' }, [
        h('li', null, [h('span', { 'class': 'ok' }, '✓'), 'tool.py imported; the function matches its manifest']),
        h('li', null, [h('span', { 'class': 'ok' }, '✓'), 'ran in ' + r.seconds + ' s']),
        h('li', null, [h('span', { 'class': 'ok' }, '✓'), 'produced 1 of 1 declared images: blade_sections.png (' + r.w + ' × ' + r.h + ' px, ' + Math.round(r.bytes / 1024) + ' KB)'])
      ]),
      h('img', { src: r.image, alt: 'blade sections test output', style: 'max-height:260px' }),
      h('div', { 'class': 'muted', style: 'font-size:11px;margin-top:6px' }, 'Parameters used: ' + Object.keys(r.params).map(function (k) { return k + '=' + r.params[k]; }).join(', '))
    ]);
  }
  function openNewTool() {
    var local = MODE === 'local';
    var roles = ROLE_ROWS.filter(function (r) { return r.role !== 'database_handler'; });
    var body = h('div', { 'class': 'frm' }, [
      h('label', null, 'Tool name'), h('input', { type: 'text', value: 'generate_turbine_wheel', 'class': 'mono' }),
      h('label', null, 'Display name'), h('input', { type: 'text', value: 'Turbine Wheel Generator' }),
      h('label', null, 'Kind'), h('select', null, ['generator (primary)', 'second generator', 'helper', 'inspection'].map(function (o, i) { return h('option', { selected: i === 0 }, o); })),
      h('label', null, 'Start from'), h('span', { 'class': 'seg' }, ['RhinoCompute + Grasshopper', 'Python function', 'Node script', 'HTTP endpoint'].map(function (o, i) {
        return h('button', { 'class': i === 1 ? 'on' : '' }, o); })),
      h('label', null, 'Code'), h('div', { 'class': 'dropzone', style: 'margin:0;padding:12px;text-align:left' }, [h('b', null, 'tool.py'), ' — drop the file here · entry point ',
        h('input', { type: 'text', value: 'tool.py:generate', 'class': 'mono', style: 'width:150px' }),
        h('div', { 'class': 'codeflag', style: 'font-size:11px;margin-top:4px' }, local ? 'Local mode: it can be run with “Test tool” below.' : '⚠ Python code: stored in your setup file, never run on this site.')]),
      h('label', null, 'Description (what the AI reads)'), h('textarea', { rows: 3 }, 'Generate the turbine wheel geometry from an attempt’s parameters.json, save it, then render three views.'),
      h('label', null, 'Called by (role)'), h('div', { 'class': 'chks' }, roles.map(function (r) {
        return h('label', { title: [3, 5, 7].map(function (t) { var a = holder(r.key, t); return t + ': ' + (a ? disp(a) : '—'); }).join('  ') }, [
          h('input', { type: 'checkbox', checked: r.role === 'tool_runner' }), r.label]); })),
      h('label', null, ''), h('div', { 'class': 'muted', style: 'font-size:11.5px' }, 'tool runner = ' + rolesLine('tool_runner')),
      h('label', null, 'Text in the prompts'), h('div', null, [
        h('div', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:4px' }, 'Per role, in fixed sections: How to use · Hard constraints — tools · Reporting'),
        h('textarea', { rows: 2, placeholder: 'How to use your configurator tools: when to call it, what to pass' })]),
      h('label', null, 'Produces'), h('div', { 'class': 'row2' }, [h('select', { style: 'width:140px' }, ['model: .obj', 'model: .glb', 'model: .stl', 'model: .step', 'no model'].map(function (o) { return h('option', null, o); })),
        h('span', { 'class': 'muted' }, 'images:'), h('input', { type: 'text', value: 'isometric, top, side', style: 'width:220px' }),
        h('label', { style: 'display:flex;gap:4px;align-items:center;color:var(--txt)' }, [h('input', { type: 'checkbox', checked: true }), 'quality numbers'])]),
      h('label', null, 'Settings'), h('input', { type: 'text', value: 'quality_checks (bool, off) · backend (enum: local | remote)' }),
      h('label', null, 'Secrets it needs'), h('div', null, [h('input', { type: 'text', value: 'TURBINE_API_URL', 'class': 'mono', style: 'width:220px' }),
        h('span', { 'class': 'muted', style: 'font-size:11.5px;margin-left:8px' }, 'names only — values go in your .env after download')]),
      h('label', null, 'Dependencies'), h('input', { type: 'text', value: 'pip: trimesh>=4.0 · apt: —', 'class': 'mono' }),
      h('label', null, 'Timeout'), h('div', { 'class': 'row2' }, [h('input', { type: 'text', value: '180', style: 'width:70px' }), h('span', { 'class': 'muted' }, 'seconds')])
    ]);
    showModal('New tool', body, [
      h('button', { disabled: !local, title: local ? '' : 'Not on this site' }, 'Test tool'),
      !local ? h('span', { 'class': 'disabled-note', style: 'margin-right:auto' }, 'Test tool: available after download (python -m studio)') : h('span', { style: 'margin-right:auto' }),
      h('button', { onclick: closeModal }, 'Cancel'), h('button', { 'class': 'primary', onclick: function () { closeModal(); toast('Saved the tool to dc_pack/tools/generate_turbine_wheel/', 'ok'); } }, 'Save tool')
    ], true);
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
          return h('td', null, h('span', { 'class': 'seg' }, PA.states.filter(function (o) {
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
  var ENV_USE = {
    OPENAI_API_KEY: ['LLM provider', 'at least one LLM key'], ANTHROPIC_API_KEY: ['LLM provider', 'at least one LLM key'],
    GOOGLE_API_KEY: ['LLM provider', 'at least one LLM key'], OPENROUTER_API_KEY: ['LLM provider', 'at least one LLM key'],
    RHINO_COMPUTE_URL: ['generate_and_render_propeller (backend rhino, downloads)', 'optional'],
    RHINO_COMPUTE_API_KEY: ['generate_and_render_propeller (backend rhino, downloads)', 'optional'],
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
        h('span', { 'class': 'seg' }, [h('button', { 'class': value ? 'on' : '' }, 'on'), h('button', { 'class': value ? '' : 'on' }, 'off')]) :
        h('select', null, (choices || [value]).map(function (c) { return h('option', { selected: c === value }, c); }))),
        h('td', { 'class': 'muted', style: 'font-size:11.5px' }, note)]);
    }
    add(center, head('Settings & secrets', 'Default values of the tools’ own settings (users change them later in Workflow Settings), and the list of secrets your setup will need.'));
    var t = h('table', { 'class': 'ptab', style: 'margin:10px 16px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Setting', 'Default', 'Today in settings.py'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, [
        h('tr', { 'class': 'grp' }, h('td', { colspan: 3 }, 'generate_and_render_propeller')),
        srow('quality_checks', !!S.MESH_CHECKS, null, 'MESH_CHECKS'),
        srow('render_library', S.RENDER_LIBRARY, ['trimesh', 'pyvista'], 'RENDER_LIBRARY'),
        srow('backend', S.GEOMETRY_BACKEND, ['feg', 'rhino'], 'GEOMETRY_BACKEND'),
        srow('view_isometric', !!S.ATTEMPT_VIEW_ISOMETRIC, null, 'ATTEMPT_VIEW_ISOMETRIC'),
        srow('view_top', !!S.ATTEMPT_VIEW_TOP, null, 'ATTEMPT_VIEW_TOP'),
        srow('view_side', !!S.ATTEMPT_VIEW_SIDE, null, 'ATTEMPT_VIEW_SIDE'),
        h('tr', { 'class': 'grp' }, h('td', { colspan: 3 }, 'render_blade_sections')),
        srow('enabled', !!S.BLADE_SECTIONS_VISUALIZER_ENABLED, null, 'BLADE_SECTIONS_VISUALIZER_ENABLED'),
        h('tr', { 'class': 'grp' }, h('td', { colspan: 3 }, 'setup')),
        srow('parameter_primer_image', !!S.DC_PARAMS_PRIMER_ENABLED, null, 'DC_PARAMS_PRIMER_ENABLED')
      ])]);
    add(center, t);
    add(center, h('div', { 'class': 'banner info', style: 'margin:6px 16px;border:1px solid #2f4f86;border-radius:7px' },
      'This site never asks for a secret value. These names go into .env.example in the full package, with empty values; you fill them on your own computer or in your hosting provider.'));
    var e = h('table', { 'class': 'ptab', style: 'margin:6px 16px 20px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Variable', 'Needed for', 'Required'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, D.env_vars.map(function (n) {
        var u = ENV_USE[n] || ['', 'optional'];
        return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, n)), h('td', null, u[0]),
          h('td', { 'class': u[1] === 'optional' ? 'muted' : 'warn' }, u[1])]);
      }))]);
    add(center, e);
    add(right, h('div', { 'class': 'insp' }, [h('h4', null, 'Why no secrets here'),
      h('p', null, 'The Studio website holds no keys at all — nothing in it is worth stealing — and it never runs your tools, so it never needs them. Your deployment reads them from its environment.'),
      h('div', { 'class': 'block' }, [h('h4', null, 'Declared by tools'), h('p', null, 'A tool lists the variables it reads in its manifest; they appear here automatically.')])]));
  }

  /* ======================================================================
   * Prompt viewer (inside the main window)
   * ==================================================================== */
  function topoAgents(t) { return Object.keys(D.prompts[String(t)].prompts); }
  function originOf(name) {
    if (RUNTIME[name]) return 'rt';
    var s = slotByName(name);
    return s ? (s.origin === 'tool' ? 'tool' : 'dc') : 'dc';
  }
  function renderPrompts(center, right) {
    var topo = parseInt(R.q.topo || '7', 10);
    var agents = topoAgents(topo);
    var agent = R.q.agent && agents.indexOf(R.q.agent) >= 0 ? R.q.agent : 'receptionist';
    var bar = [h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'Topology'), h('span', { 'class': 'seg' }, [3, 5, 7].map(function (t) {
      return h('button', { 'class': t === topo ? 'on' : '', onclick: function () { go('studio', 'prompts', withQ({ topo: t, agent: null })); } }, String(t)); }))];
    [['RAG', false], ['Blade sections', true], ['Mesh checks', false], ['Planner first', false], ['DC Input Inspector', true]].forEach(function (x) {
      bar.push(h('label', { title: 'Draft: the viewer shows the default settings' }, [h('input', { type: 'checkbox', checked: x[1], disabled: true }), x[0]]));
    });
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
    spans.forEach(function (sp) { if (!RUNTIME[sp[2]]) used[sp[2]] = (used[sp[2]] || 0) + 1; });
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
      out.push(own[i] ? '<span class="o-' + own[i] + '" title="' + esc(nm[i]) + '"' + (own[i] !== 'rt' ? ' data-slot="' + esc(nm[i]) + '"' : '') + '>' + chunk + '</span>' : chunk);
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
   * Validate (hosted: static checks + prompt assembly)
   * ==================================================================== */
  function validateGroups() {
    var V = D.validate, P = D.parameters.parameters, unused = unusedSlots(), f104 = f104All();
    var names = P.map(function (p) { return p.name; });
    var dupes = names.filter(function (n, i) { return names.indexOf(n) !== i; });
    var badRange = P.filter(function (p) { return !(p.min < p.max); });
    var badDef = P.filter(function (p) { return p.default < p.min || p.default > p.max; });
    var units = P.filter(unitMismatch);
    return [
      { title: 'Setup file', rows: [
        ['ok', 'pack.yaml: name, setup format 1, engine 0.1'],
        ['ok', 'parameters.json matches its schema (' + P.length + ' parameters, ' + D.parameters.groups.length + ' groups)'],
        ['ok', D.tools.length + ' tool manifests, exactly one primary generator (' + D.tools[0].name + ')']] },
      { title: 'Text fields', rows: [
        [V.brace_files.length ? 'bad' : 'ok', V.fragment_files + ' text files: no { or } in any of them', V.brace_files.length ? V.brace_files.join(', ') : 'A brace silently strips the routing section of a prompt (W45).'],
        [V.unknown_dollar.length ? 'bad' : 'ok', 'every $name refers to a known field', V.unknown_dollar.join(', ')],
        [V.multiline_phrases.length ? 'bad' : 'ok', 'every one-line field is one line', V.multiline_phrases.join(', ')],
        ['info', V.empty_in_topology7.length + ' fields are empty for the 7-agent topology', 'Used only by the 3-agent topology: ' + V.empty_in_topology7.join(', ')],
        ['warn', unused.length + ' fields are in no prompt (default settings and all features on)', unused.join(', ') + '. Some are kept on purpose (W42); some overlap newer fields (F108).'],
        ['warn', f104.length + ' fields describe the blade-sections tool or the mesh checks but have no feature marker', 'They stay in the prompts with the feature off (F104): ' + f104.join(', ')]] },
      { title: 'Parameters', rows: [
        [dupes.length ? 'bad' : 'ok', P.length + ' unique names'],
        [badRange.length ? 'bad' : 'ok', 'min < max for every parameter'],
        [badDef.length ? 'bad' : 'ok', 'every default lies inside its range'],
        [units.length ? 'warn' : 'ok', units.length ? units.length + ' parameter has two different units in its copies' : 'units agree', units.map(function (p) { return p.name + ': “' + p.unit_prompt + '” vs “' + p.unit + '”'; }).join('; ')]] },
      { title: 'Tools', rows: [
        ['ok', 'every tool’s role exists in all three topologies'],
        ['info', 'tools are not imported or run on this site', 'Their Python files are checked as text. Test tool runs after download: python -m studio']] },
      { title: 'Assembly', rows: [
        ['ok', fmt(D.matrix.prompts) + ' prompts assembled (' + D.matrix.combinations + ' setting combinations × 3 topologies), ' + D.matrix.unformatted + ' left unformatted'],
        ['info', 'largest prompt: ' + disp(D.matrix.largest.agent) + ' (' + D.matrix.largest.where.replace('/', ', topology ') + ') — ' + fmt(D.matrix.largest.chars) + ' characters ≈ ' + fmt(Math.round(D.matrix.largest.chars / 4)) + ' tokens']] }
    ];
  }
  function validateSummary() {
    var w = 0, b = 0;
    validateGroups().forEach(function (g) { g.rows.forEach(function (r) { if (r[0] === 'warn') w++; if (r[0] === 'bad') b++; }); });
    return { warn: w, bad: b };
  }
  function renderValidate(center, right) {
    var sum = validateSummary();
    add(center, head('Validate', 'On this site: static checks of every file and the assembly of every prompt. No tool is imported or run (that happens on your own computer).', [
      h('button', { 'class': 'primary', onclick: function () { req('validate').then(function () { toast('Validated: ' + sum.warn + ' warnings', 'ok'); }); } }, 'Run again')]));
    add(center, h('div', { 'class': 'vsum' }, [pill(sum.bad ? 'Failed' : 'Passed with ' + sum.warn + ' warnings', sum.bad ? 'bad' : 'warn'),
      h('span', { 'class': 'muted', style: 'font-size:11.5px' }, 'checked at ' + hhmm(SAVED_AT) + ' · the downloads are marked with this result')]));
    validateGroups().forEach(function (g) {
      var box = h('div', { 'class': 'vgroup' }, h('div', { 'class': 'vh' }, [g.title, h('span', { 'class': 'grow' }),
        g.rows.some(function (r) { return r[0] === 'bad'; }) ? pill('fail', 'bad') : g.rows.some(function (r) { return r[0] === 'warn'; }) ? pill('warning', 'warn') : pill('pass', 'good')]));
      g.rows.forEach(function (r) {
        var icon = { ok: ['ok', '✓'], warn: ['warn', '⚠'], bad: ['err', '✗'], info: ['muted', 'ⓘ'] }[r[0]];
        add(box, h('div', { 'class': 'vrow' }, [h('span', { 'class': icon[0] }, icon[1]), h('div', null, [r[1], r[2] ? h('div', { 'class': 'detail' }, r[2]) : null])]));
      });
      add(center, box);
    });
    add(right, h('div', { 'class': 'insp' }, [h('h4', null, 'Hosted vs local'),
      h('div', { 'class': 'kv', style: 'grid-template-columns:1fr 60px 60px;font-size:11.5px' }, [
        h('div', { 'class': 'k' }, ''), h('div', { 'class': 'k' }, 'website'), h('div', { 'class': 'k' }, 'local'),
        h('div', null, 'files, fields, parameters'), h('div', { 'class': 'ok' }, '✓'), h('div', { 'class': 'ok' }, '✓'),
        h('div', null, 'every prompt assembled'), h('div', { 'class': 'ok' }, '✓'), h('div', { 'class': 'ok' }, '✓'),
        h('div', null, 'tools imported and test-run'), h('div', { 'class': 'muted' }, '—'), h('div', { 'class': 'ok' }, '✓'),
        h('div', null, 'the 7 offline checks with your tools'), h('div', { 'class': 'muted' }, '—'), h('div', { 'class': 'ok' }, '✓')]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Warnings'), h('p', null, 'Warnings do not block a download. Fails do.')])]));
  }

  /* ======================================================================
   * Downloads (modal)
   * ==================================================================== */
  function openDownload() {
    var sum = validateSummary(), nLinked = D.slots.filter(function (s) { return s.linked; }).length;
    var name = D.pack.name;
    var body = h('div', { 'class': 'dl' }, [
      h('div', { 'class': 'dlcard' }, [h('h3', null, 'Setup file'), h('div', { 'class': 'muted', style: 'font-size:12px' }, 'Your configurator alone — also the Studio’s save file. Import it later to continue.'),
        h('div', { 'class': 'tree' }, name + '.mas-setup.zip\n└─ dc_pack/\n   ├─ pack.yaml          name · setup format 1 · engine 0.1\n' +
          '   ├─ parameters.json    ' + D.parameters.parameters.length + ' parameters, ' + D.parameters.groups.length + ' groups\n' +
          '   ├─ fragments/         ' + D.slots.length + ' fields (' + nLinked + ' shared + per-topology files)\n' +
          '   ├─ tools/\n' + D.tools.map(function (t, i) { return '   │  ' + (i === D.tools.length - 1 ? '└' : '├') + '─ ' + t.name + '/  tool.yaml · tool.py ⚠ code'; }).join('\n') +
          '\n   ├─ assets/            primer image, 4 group diagrams\n   └─ examples/          (optional)\n\nnever inside: secret values, .env, logs'),
        h('button', { 'class': 'primary', onclick: function () { call('download', 'setup').then(function (r) { toast(r.ok ? 'Downloaded' : r.error); }); } }, 'Download setup file')]),
      h('div', { 'class': 'dlcard' }, [h('h3', null, 'Full package'), h('div', { 'class': 'muted', style: 'font-size:12px' }, 'The engine plus your setup, ready for a private GitHub repository and a host such as Railway.'),
        h('div', { 'class': 'tree' }, name + '-mas/\n├─ agents/ tools/ web/ web_app.py …   the engine\n├─ dc_pack/                         your setup\n' +
          '├─ studio/                          python -m studio (local)\n├─ requirements.txt                 engine + tool packages, merged\n' +
          '├─ Dockerfile                       system packages from the tools\n├─ .env.example                     ' + D.env_vars.length + ' variables, all empty\n' +
          '├─ .gitignore\n└─ DEPLOY.md                        every variable + Railway steps'),
        h('div', { style: 'font-size:11.5px;margin-bottom:8px' }, ['Then, on your computer: unzip → fill ', h('code', { 'class': 'mono-inline' }, '.env'), ' → ',
          h('code', { 'class': 'mono-inline' }, 'python -m studio prepare'), ' (tool tests, checks, first commit) → push → deploy']),
        h('button', { 'class': 'primary', onclick: function () { call('download', 'full').then(function (r) { toast(r.ok ? 'Downloaded' : r.error); }); } }, 'Download full package')])
    ]);
    showModal('Download', body, [h('span', { style: 'margin-right:auto', 'class': sum.bad ? 'err' : 'warn' }, 'Last Validate: ' + (sum.bad ? 'failed' : 'passed with ' + sum.warn + ' warnings') + ' (current)'),
      h('button', { onclick: closeModal }, 'Close')], 'x');
  }

  /* ---------------- modal + splitters (kit) ---------------- */
  function showModal(title, body, foot, wide) {
    el('modalTitle').textContent = title;
    var b = el('modalBody'); b.innerHTML = ''; b.className = 'body scroll'; b.appendChild(body);
    var f = el('modalFoot'); f.innerHTML = ''; add(f, foot);
    el('modalBox').className = 'modal' + (wide === 'x' ? ' xwide' : wide ? ' wide' : '');
    el('modal').className = 'modal-back on';
  }
  function closeModal() {
    el('modal').className = 'modal-back';
    var q = withQ({ modal: null });
    go(R.page, R.section, q);
  }
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
    el('modal').className = 'modal-back';
    if (R.page === 'start') renderStart(app);
    else if (R.page === 'import') renderImport(app);
    else if (R.page === 'studio') renderStudio(app);
    else renderLanding(app);
    if (R.q.modal === 'download') openDownload();
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
    req('get_all').then(function (r) {
      D = r.data;
      root.addEventListener('hashchange', render);
      render();
      setStatus('Ready.', 'ok');
    }).catch(function (e) {
      el('app').textContent = 'The Studio could not load its data: ' + (e && e.message ? e.message : e);
    });
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', init);
  else init();

  root.StudioDraft = { render: render, data: function () { return D; } };
}(window));
