/* ======================================================================
 * studio.js -- the MAS Studio (MAS-blueprint P5a-P5b, P6a-P6c).
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
 * P6b edits the parameters (parameters.json, its groups and pictures; the
 * server keeps the agents' parameter lists in step) and the agent-access
 * grid (pack.yaml).
 * P6c edits the tools: their manifests (a form, or the text), their files,
 * their tool-list entries, their settings' defaults and secrets; removes
 * them and puts them back; makes new ones (a template per kind, or a copy)
 * and test-runs them (engine/tool_test.py) (studio/tools_edit.py).
 * P7 adds Validate: every check of the setup (studio/validate.py), run on
 * the server while the page polls its progress; the two downloads -- the
 * setup file and the full package -- and Open setup file
 * (studio/package.py); and Prepare for GitHub (studio/prepare.py), which
 * never runs git: it shows the commands.
 * P7b-lite: online (python -m studio --online) the page asks for the access
 * code first, opens on the landing page, and the setup is one shared one.
 * The guide is a page of its own (web/guide.html), linked from the toolbar
 * and the landing page.
 *
 * Screens are hash routes, so each one has an address:
 *   #/studio/<section>[?field=..]     the Studio: sections | fields | inspector
 *      sections: identity parameters description outputs tools examples
 *                inputs access settings prompts validate
 *      extra:    &agent=<key>  &param=<name>  &topo=3|5|7
 *   #/landing                         the landing page (online: the start)
 * ====================================================================== */
(function (root) {
  'use strict';

  var doc = root.document;
  var D = null;                        // the setup, from the server
  var SESSION = { online: false, authed: true };   // online mode and the access code (session)
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
    settings: 'DC_PARAMS_PRIMER_ENABLED lives in workflow_settings/settings.py, outside the setup: read-only here.',
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
  // A picture of the setup (parameters.json writes "/pack/assets/..."), from
  // this Studio's own copy: relative, as the Studio may be at /studio/.
  function own(url) { return String(url).charAt(0) === '/' ? String(url).slice(1) : url; }
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
   * the landing page (P7b-lite) and the access code
   * ==================================================================== */
  function renderLanding(app) {
    var p = h('div', { 'class': 'page landing' });
    add(p, [
      h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Build a multi-agent system for your own design configurator: start from the ' + D.pack.name +
        ' example, change its parameters, texts and tools, check it with Validate, and download it to deploy.'),
      h('div', { 'class': 'actions' }, [
        h('button', { 'class': 'primary', onclick: function () { go('studio', 'identity'); } }, 'Open the Studio →'),
        h('button', { onclick: askOpen }, 'Import a setup…'),
        D.can_reset ? h('button', { onclick: askReset }, 'Start again from the ' + D.pack.name + ' example…') : null,
        configuratorLink(),
        h('a', { 'class': 'btn', href: 'static/guide.html', target: '_blank', rel: 'noopener' }, 'Getting started (the guide) ↗')
      ]),
      SESSION.online ? h('p', { 'class': 'note' }, 'This is one shared setup: everyone with the access code sees and changes the same one. ' +
        'It is not kept when the Studio restarts or is deployed again — use Download setup file to keep your work, and Import a setup to bring it back.') : null
    ]);
    app.appendChild(p);
  }
  // The configurator the Studio is deployed beside (CONFIGURATOR_URL): its
  // link on the landing page and on the access-code page.
  function configuratorLink() {
    var c = SESSION.configurator || (D && D.configurator);
    if (!c || !c.url) return null;
    return h('a', { 'class': 'btn', href: c.url, target: '_blank', rel: 'noopener' },
      'Use the ' + (c.name ? c.name + ' ' : '') + 'configurator ↗');
  }
  function renderLogin(app, msg) {
    var input = h('input', { type: 'password', autocomplete: 'current-password', placeholder: 'access code' });
    var out = h('p', { 'class': 'err' }, msg || '');
    function send() {
      out.textContent = '';
      call('auth', input.value).then(function (r) {
        if (r && r.ok) { root.location.reload(); return; }
        out.textContent = (r && r.error) || 'The access code did not match.';
        input.select();
      });
    }
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
    app.innerHTML = '';
    app.appendChild(h('div', { 'class': 'page landing' }, [
      h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Type the access code to open the online Studio. This browser remembers it.'),
      h('div', { 'class': 'actions row' }, [input, h('button', { 'class': 'primary', onclick: send }, 'Open')]),
      out,
      configuratorLink() ? h('div', { 'class': 'actions' }, [h('span', { 'class': 'muted' }, 'Or, without the Studio:'), configuratorLink()]) : null]));
    input.focus();
  }
  function askReset() {
    if (BUSY) return;
    var word = h('input', { type: 'text', spellcheck: 'false', placeholder: 'replace' });
    var msg = h('div');
    var go_ = h('button', { 'class': 'primary', disabled: true }, 'Start again');
    word.addEventListener('input', function () { go_.disabled = word.value !== 'replace'; });
    go_.addEventListener('click', function () {
      msg.innerHTML = '';
      add(msg, h('p', { 'class': 'muted' }, 'Checking it with the engine…'));
      call('reset_to_example', word.value).then(function (r) {
        msg.innerHTML = '';
        if (!r || r.ok === false) { add(msg, h('div', { 'class': 'banner bad boxed' }, (r && r.error) || 'It could not start again.')); return; }
        closeModal();
        BUSY = true; EDITS = {}; PEDITS = {}; GEDITS = {}; TEDITS = {}; FEDITS = {}; TESTS = {}; FIELD_ERRORS = {};
        status('Starting again from the example. Re-assembling every prompt…', 'busy');
        reload().then(function () {
          BUSY = false;
          status('The setup is the ' + D.pack.name + ' example again: Undo now goes back to it.', 'ok');
          go('studio', 'identity');
          render();
        }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
      });
    });
    showModal('Start again from the example', h('div', null, [
      h('div', { 'class': 'banner warn boxed' }, 'This replaces the setup for everyone who uses this Studio: every text, parameter and tool goes back to the example.'),
      h('p', { style: 'margin:8px 0' }, h('a', { href: 'download/setup', download: '' }, 'Download the current setup first')),
      h('p', null, 'Type replace to confirm:'),
      h('div', { style: 'margin:6px 0' }, word), msg]),
      [h('button', { onclick: closeModal }, 'Cancel'), go_]);
    word.focus();
  }

  /* ======================================================================
   * the Studio shell: toolbar / banner / 3 columns / status bar
   * ==================================================================== */
  function renderStudio(app) {
    var tb = h('div', { 'class': 'toolbar' }, [
      h('span', { 'class': 'title', style: 'cursor:pointer', onclick: function () { go('landing'); } }, 'MAS Studio'),
      h('span', { 'class': 'pack', title: D.pack_dir }, ['setup: ', h('b', null, D.pack.name), ' · ' + D.pack_dir.split(/[\\/]/).pop() + '/']),
      SESSION.online ? pill('online', 'mode-hosted', 'The online Studio: one shared setup for everyone with the access code')
        : pill('local', 'mode-local', 'python -m studio on this computer'),
      h('span', { 'class': 'grow' }),
      h('a', { 'class': 'btn', href: 'static/guide.html', target: '_blank', rel: 'noopener', title: 'How to make the setup yours, check it and deploy it.' }, 'Guide'),
      h('button', { title: 'Run every check of the setup.', onclick: function () { go('studio', 'validate'); startValidate(); } },
        ['Validate ', h('span', { id: 'valTop' }, valBadge())]),
      h('button', { title: 'Open a setup file made with the Studio: it replaces this setup.', onclick: askOpen }, 'Open setup file…'),
      h('button', { title: 'The setup alone, to open again later.', onclick: function () { askDownload('setup'); } }, 'Download setup file'),
      h('button', { 'class': 'primary', title: 'The engine and this setup, ready to deploy.', onclick: function () { askDownload('package'); } }, 'Download full package'),
      h('span', { 'class': 'sep' }),
      h('button', { disabled: !(D.prepare && D.prepare.available), onclick: askPrepare,
        title: D.prepare && D.prepare.available ? 'Check this folder and get the commands that put it on GitHub. Nothing is committed.' : (D.prepare && D.prepare.why) || '' },
        'Prepare for GitHub')
    ]);
    var banner = h('div', { 'class': 'banner info' }, SESSION.online
      ? 'Editing the shared online setup: everyone with the access code sees the same one. Each change saves on its own, and Undo puts it back as it was when the Studio started. ' +
        'It is not kept when the Studio restarts: use Download setup file to keep your work.'
      : 'Editing the setup in ' + D.pack_dir + ': each text field, parameter, group, access cell, tool and setting saves on its own, straight to its files, and Undo puts it back as it was when the Studio opened. ' +
        'Test tool runs a tool on a throw-away folder: nothing in the setup changes.');
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
        s.id === 'validate' ? h('span', { 'class': 'cnt', id: 'valNav' }, valBadge()) : null
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
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null, s.runtime ? kpill('read by the app') : null]),
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
        s.owner ? kpill('owned by ' + ownerName(s.owner)) : null, s.runtime ? kpill('read by the app') : null,
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
      s.runtime ? h('div', { 'class': 'block' }, [h('h4', null, 'Where it is read'),
        h('p', { 'class': 'muted' }, 'By the app’s code, not by a $name in a prompt text: in a tool’s description or answer, the tool runner’s list, the parameter primer or the web page — the description above says which.  So the sentences it lands in are not traced here.')]) :
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
      return h('span', null, [h('b', null, disp(a)), ' ', h('span', { 'class': 'topo' },
        r.agents[a].slice().sort(function (x, y) { return x - y; }).join(' · '))]);
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
  function unsavedKeys() {
    return Object.keys(EDITS).map(function (k) { return k.replace('|', ' @').replace(/ @$/, ''); })
      .concat(Object.keys(PEDITS).map(function (k) { return 'parameter ' + (PEDITS[k].name || k); }))
      .concat(Object.keys(GEDITS).map(function (k) { return 'group ' + (GEDITS[k].label || k); }))
      .concat(Object.keys(TEDITS).map(function (k) { return 'manifest of ' + k; }))
      .concat(Object.keys(FEDITS).map(function (k) { return 'file ' + k; }));
  }
  function unsavedPill() {
    var keys = unsavedKeys();
    return keys.length ? pill(keys.length + ' unsaved', 'warn', keys.join('\n')) : null;
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
      FILES = {}; FILE_LOADING = {};
      VIEWS = {}; VIEW_ERRORS = {}; VIEW_PENDING = {}; DIFFS = {}; DIFF_ERRORS = {}; DIFF_PENDING = {};
      if (VAL.state && VAL.state.report) readValidate();     // is the last run still current?
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
    var keys = ['3', '5', '7'].filter(function (t) { return st.values[t] !== null && st.values[t] !== undefined && (!agent || inRoster(agent, t)); });
    var choice = keys[keys.length - 1];
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
   * Parameters (P6b): parameters.json, its groups and pictures; the
   * agents' parameter lists are kept in step by the server
   * (studio/params_edit.py).  A row's unsaved fields live in PEDITS, a
   * group's in GEDITS, until its Save; every change is previewed by the
   * server (preview_parameters) and saved whole (save_parameters).
   * ==================================================================== */
  var PEDITS = {};         // unsaved parameter rows: saved name or 'new:N' -> fields
  var GEDITS = {};         // unsaved groups: id or 'new:N' -> fields
  var NEWSEQ = 0;
  var NUMERIC = { min: 1, max: 1, step: 1, 'default': 1 };
  var P_KEYS = ['name', 'type', 'min', 'max', 'step', 'default', 'group', 'label', 'unit', 'db_unit', 'db_description'];
  var G_KEYS = ['id', 'label', 'image', 'image_alt', 'order'];
  function PE() { return D.params_edit; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function savedParam(name) { return PE().spec.parameters.filter(function (p) { return p.name === name; })[0] || null; }
  function openedParam(name) { return PE().opened.parameters.filter(function (p) { return p.name === name; })[0] || null; }
  function savedGroup(id) { return PE().spec.groups.filter(function (g) { return g.id === id; })[0] || null; }
  function openedGroup(id) { return PE().opened.groups.filter(function (g) { return g.id === id; })[0] || null; }
  // the opened name of the parameter now called *name* (null: added since opening)
  function openedNameOf(name) {
    var s = PE().since_opened || {};
    for (var o in s) if (s[o] === name) return o;
    return openedParam(name) && !s[name] ? name : null;
  }
  function paramChanged(name) {
    var o = openedNameOf(name);
    return !o || JSON.stringify(savedParam(name)) !== JSON.stringify(openedParam(o));
  }
  function groupChanged(id) { var o = openedGroup(id); return !o || JSON.stringify(savedGroup(id)) !== JSON.stringify(o); }
  // parameters of the setup as opened that are gone now (not renamed)
  function removedParams() {
    var s = PE().since_opened || {}, now = PE().spec.parameters.map(function (p) { return p.name; });
    return PE().opened.parameters.filter(function (p) { return now.indexOf(s[p.name] || p.name) < 0; });
  }
  function removedGroups() {
    var now = PE().spec.groups.map(function (g) { return g.id; });
    return PE().opened.groups.filter(function (g) { return now.indexOf(g.id) < 0; });
  }
  function paramsChanged() {
    return (D.changed || []).some(function (c) { return c === 'parameters.json' || c.indexOf('assets/') === 0; });
  }
  function rowFields(key) {
    if (PEDITS[key]) return PEDITS[key];
    return clone(savedParam(key));
  }
  function parseNum(v) {
    if (typeof v === 'number') return v;
    var s = String(v).trim();
    return s !== '' && isFinite(Number(s)) ? Number(s) : s;
  }
  function entryOf(f) {
    // a number's fields, or a choice's / an on/off parameter's (TYPE_KEYS),
    // then its "only when" (MAS-blueprint P6d)
    var e = {}, typed = typedType(f.type);
    (typed ? TYPE_KEYS[f.type] : P_KEYS).forEach(function (k) {
      e[k] = !typed && NUMERIC[k] ? parseNum(f[k]) : f[k];
      // a range an import proposed, until min or max is edited (P6f)
      if (k === 'step' && !typed && f.range !== undefined) e.range = f.range;
    });
    if (f.used_when !== undefined) e.used_when = f.used_when;
    return e;
  }
  // -- choice and on/off parameters (MAS-blueprint P6d) --
  var TYPE_CHOICES = [['int', 'int'], ['float', 'float'], ['choice', 'choice'], ['bool', 'on/off']];
  function typedType(t) { return t === 'choice' || t === 'bool'; }
  // A row switched between a number and a choice / on/off parameter: the
  // fields of its new type (its saved ones when it goes back to them).
  function retype(key, f, to) {
    var saved = key.indexOf('new:') === 0 ? null : savedParam(key);
    ['min', 'max', 'step', 'range', 'choices'].forEach(function (k) { delete f[k]; });
    if (saved && saved.type === to) {
      ['min', 'max', 'step', 'range', 'choices', 'default'].forEach(function (k) { if (k in saved) f[k] = clone(saved[k]); });
    } else if (to === 'choice') {
      f.choices = [{ value: 'option_1', label: 'Option 1' }, { value: 'option_2', label: 'Option 2' }];
      f['default'] = 'option_1';
    } else if (to === 'bool') {
      f['default'] = false;
    } else {
      f.min = '0'; f.max = '1'; f.step = '1'; f['default'] = '0';
    }
  }
  function typeSummary(f) { return f.type === 'choice' ? (f.choices || []).length + ' choices (inspector)' : 'true / false'; }
  // A choice's or an on/off parameter's default: a dropdown of its values.
  function defaultPick(key, f) {
    var choice = f.type === 'choice', ch = f.choices || [];
    var cur = choice ? String(ch.findIndex(function (c) { return same(c.value, f['default']); })) : String(f['default'] === true);
    var opts = choice ? ch.map(function (c, i) { return [String(i), c.label]; }) : [['false', 'false'], ['true', 'true']];
    return h('select', { 'data-fk': 'param|' + key, 'data-t': 'default', onfocus: function () { selectParam(key); },
      onchange: function (e) { onParamInput(key, 'default', choice ? ch[Number(e.target.value)].value : e.target.value === 'true'); } },
      opts.map(function (o) { return h('option', { value: o[0], selected: o[0] === cur }, o[1]); }));
  }
  // The inspector's Choices: value and label of each, in order.
  function choicesBlock(key, f) {
    var ch = f.choices || [];
    function set(list) {
      var d = f['default'];
      onParamInput(key, 'choices', list);
      if (list.length && !list.some(function (c) { return same(c.value, d); })) onParamInput(key, 'default', list[0].value);
    }
    function upd(i, k, text) {
      var list = clone(ch);
      list[i][k] = k === 'value' && /^-?\d+(\.\d+)?$/.test(text) ? Number(text) : text;
      if (k === 'value' && same(ch[i].value, f['default'])) {
        onParamInput(key, 'choices', list);        // the default follows its choice
        onParamInput(key, 'default', list[i].value);
        return;
      }
      set(list);
    }
    function move(i, d) { var list = clone(ch), a = list[i]; list[i] = list[i + d]; list[i + d] = a; set(list); }
    function box(c, i, k) {
      return h('input', { type: 'text', value: String(c[k]), spellcheck: 'false', 'data-fk': 'param|' + key, 'data-t': 'choice:' + i + ':' + k,
        oninput: function (e) { upd(i, k, e.target.value); } });
    }
    return h('div', { 'class': 'block' }, [h('h4', null, 'Choices · ' + ch.length),
      h('table', { 'class': 'ptab pedit chs' }, [h('thead', null, h('tr', null, ['Value', 'Label', ''].map(function (x) { return h('th', null, x); }))),
        h('tbody', null, ch.map(function (c, i) {
          return h('tr', null, [h('td', null, box(c, i, 'value')), h('td', null, box(c, i, 'label')), h('td', { 'class': 'mv' }, [
            h('button', { 'class': 'mini', disabled: i === 0, title: 'Move up', onclick: function () { move(i, -1); } }, '↑'),
            h('button', { 'class': 'mini', disabled: i === ch.length - 1, title: 'Move down', onclick: function () { move(i, 1); } }, '↓'),
            h('button', { 'class': 'mini danger', title: 'Remove this choice', onclick: function () { set(ch.filter(function (_c, j) { return j !== i; })); } }, '×')])]);
        }))]),
      h('div', { style: 'margin-top:6px' }, h('button', { 'class': 'mini', onclick: function () {
        var list = clone(ch), n = list.length + 1;
        list.push({ value: 'option_' + n, label: 'Option ' + n });
        set(list);
      } }, '+ Add a choice')),
      h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-top:4px' }, 'The agents and the database use the values; the slider page shows the labels. ' +
        'A value is text or a number. The database stores a choice as its place in this order: changing the order needs a new parameter schema.')]);
  }
  // The inspector's Only when: each condition names a choice or on/off
  // parameter and the values it must have (engine/parameters.py used_when).
  function whenBlock(key, f) {
    var uw = f.used_when || {}, names = Object.keys(uw);
    var others = PE().spec.parameters.filter(function (p) { return typedType(p.type) && p.name !== f.name && names.indexOf(p.name) < 0; });
    function valuesOf(q) { return !q ? [] : q.type === 'bool' ? [true, false] : (q.choices || []).map(function (c) { return c.value; }); }
    function set(next) { onParamInput(key, 'used_when', Object.keys(next).length ? next : undefined); }
    function toggle(other, v, on) {
      var next = clone(uw), cur = next[other] instanceof Array ? next[other] : [next[other]];
      cur = cur.filter(function (w) { return !same(w, v); });
      if (on) cur.push(v);
      next[other] = cur.length === 1 ? cur[0] : cur;
      set(next);
    }
    var rows = names.map(function (other) {
      var wants = uw[other] instanceof Array ? uw[other] : [uw[other]];
      return h('div', { 'class': 'whenrow' }, [h('span', { 'class': 'mono' }, other + ' is'),
        h('span', null, valuesOf(savedParam(other)).map(function (v) {
          return h('label', { style: 'margin-right:8px;white-space:nowrap' }, [h('input', { type: 'checkbox',
            checked: wants.some(function (w) { return same(w, v); }), onchange: function (e) { toggle(other, v, e.target.checked); } }), ' ' + String(v)]);
        })),
        h('button', { 'class': 'mini', title: 'Remove this condition', onclick: function () { var next = clone(uw); delete next[other]; set(next); } }, '×')]);
    });
    var pick = others.length ? h('select', { onchange: function (e) {
      var q = savedParam(e.target.value);
      if (!q) return;
      var next = clone(uw);
      next[q.name] = valuesOf(q)[0];
      set(next);
    } }, [h('option', { value: '' }, '+ Add a condition…')].concat(others.map(function (p) { return h('option', { value: p.name }, p.name); }))) : null;
    return h('div', { 'class': 'block' }, [h('h4', null, 'Only when'),
      names.length ? h('div', null, rows) : h('p', { 'class': 'muted' }, 'Always used.'),
      pick ? h('div', { style: 'margin-top:6px' }, pick) : names.length ? null
        : h('p', { 'class': 'muted', style: 'font-size:11.5px' }, 'A condition names a choice or on/off parameter; the setup has none yet.'),
      h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-top:4px' },
        'While a condition does not hold, the slider page hides the parameter and the agents read “(only when …)” in their lists.')]);
  }
  function removeFromOrders(spec, name) {
    spec.groups.forEach(function (g) { g.order = (g.order || []).filter(function (n) { return n !== name; }); });
  }
  function groupOf(spec, id) { return spec.groups.filter(function (g) { return g.id === id; })[0] || null; }
  // The saved parameters with one row's unsaved fields: {spec, renames}.
  function specWithRow(key) {
    var spec = clone(PE().spec), e = entryOf(rowFields(key)), renames = {};
    if (key.indexOf('new:') === 0) {
      var last = -1;
      spec.parameters.forEach(function (p, i) { if (p.group === e.group) last = i; });
      spec.parameters.splice(last < 0 ? spec.parameters.length : last + 1, 0, e);
      var g = groupOf(spec, e.group);
      if (g) g.order.push(e.name);
      return { spec: spec, renames: renames };
    }
    var i = spec.parameters.map(function (p) { return p.name; }).indexOf(key), old = spec.parameters[i];
    spec.parameters[i] = e;
    if (e.name !== old.name) {
      renames[old.name] = e.name;
      spec.groups.forEach(function (g) { g.order = g.order.map(function (n) { return n === old.name ? e.name : n; }); });
      // the conditions that name it follow (MAS-blueprint P6d)
      spec.parameters.forEach(function (p) {
        if (p.used_when && old.name in p.used_when) {
          var uw = {};
          Object.keys(p.used_when).forEach(function (o) { uw[o === old.name ? e.name : o] = p.used_when[o]; });
          p.used_when = uw;
        }
      });
    }
    if (e.group !== old.group) {
      removeFromOrders(spec, e.name);
      var ng = groupOf(spec, e.group);
      if (ng) ng.order.push(e.name);
    }
    return { spec: spec, renames: renames };
  }
  function specWithGroup(key) {
    var spec = clone(PE().spec), f = GEDITS[key];
    if (key.indexOf('new:') === 0) {
      spec.groups.push({ id: f.id, label: f.label, image: f.image, image_alt: f.image_alt, order: [] });
    } else {
      var g = groupOf(spec, key);
      g.label = f.label; g.image = f.image; g.image_alt = f.image_alt; g.order = f.order.slice();
    }
    return spec;
  }
  function rowProblems(key) { return validateSpec(specWithRow(key).spec); }
  function groupProblems(key) { return validateSpec(specWithGroup(key)); }

  // -- engine/parameters.py validate, word for word (the server repeats it with the engine's own)
  // a choice's and an on/off parameter's fields (engine/parameters.py _KEYS)
  var TYPE_KEYS = {
    'int': P_KEYS, 'float': P_KEYS,
    choice: ['name', 'type', 'choices', 'default', 'group', 'label', 'unit', 'db_unit', 'db_description'],
    bool: ['name', 'type', 'default', 'group', 'label', 'unit', 'db_unit', 'db_description']
  };
  function pyRepr(v) {
    if (v === null || v === undefined) return 'None';
    if (typeof v === 'boolean') return v ? 'True' : 'False';
    if (typeof v === 'string') return v.indexOf("'") >= 0 && v.indexOf('"') < 0 ? '"' + v + '"' : "'" + v.replace(/'/g, "\\'") + "'";
    return String(v);
  }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }
  function symDiff(a, b) {
    return a.filter(function (k) { return b.indexOf(k) < 0; }).concat(b.filter(function (k) { return a.indexOf(k) < 0; })).sort();
  }
  // equal values, true / false never equal to 1 / 0 (engine _same)
  function same(a, b) { return (typeof a === 'boolean') === (typeof b === 'boolean') && a === b; }
  var CHOICE_TEXT_BAD = /[|\n\r]| = /;
  function choiceValues(p) {
    return p.choices instanceof Array ? p.choices.filter(function (c) {
      return c !== null && typeof c === 'object' && !(c instanceof Array) && 'value' in c;
    }).map(function (c) { return c.value; }) : [];
  }
  function checkValue(p, v) {
    if (p.type === 'bool') return typeof v === 'boolean' ? null : 'must be true or false';
    if (p.type === 'choice') {
      var values = choiceValues(p);
      if (values.some(function (x) { return same(v, x); })) return null;
      return 'must be one of: ' + values.map(function (x) { return typeof x === 'string' ? x : JSON.stringify(x); }).join(', ');
    }
    return isNum(v) ? null : 'must be a number';
  }
  function checkChoices(name, p, problems) {
    var ch = p.choices;
    var isObj = function (o) { return o !== null && typeof o === 'object' && !(o instanceof Array); };
    if (!(ch instanceof Array) || ch.length < 2 || !ch.every(isObj)) {
      problems.push(name + ': choices must be a list of at least two {value, label}');
      return;
    }
    var seen = [];
    ch.forEach(function (c) {
      var v = c.value;
      symDiff(['value', 'label'], Object.keys(c)).forEach(function (k) {
        problems.push(name + ': a choice has ' + (k in c ? 'an unknown field' : 'no') + ' "' + k + '"');
      });
      if (!((typeof v === 'string' && v.trim() && !CHOICE_TEXT_BAD.test(v)) || isNum(v))) {
        problems.push(name + ': a choice\'s value must be a number or text without "|", " = " or a line break (got ' + pyRepr(v) + ')');
      } else if (seen.some(function (s) { return same(v, s); })) {
        problems.push(name + ': the choice ' + pyRepr(v) + ' is listed twice');
      } else {
        seen.push(v);
      }
      if ('label' in c && (typeof c.label !== 'string' || CHOICE_TEXT_BAD.test(c.label))) {
        problems.push(name + ': the label of the choice ' + pyRepr(v) + ' must be text without "|", " = " or a line break');
      }
    });
    if (!seen.some(function (s) { return same(p['default'], s); })) {
      problems.push(name + ': default ' + pyRepr(p['default']) + ' is not one of its choices');
    }
  }
  function checkUsedWhen(params, problems) {
    var isObj = function (o) { return o !== null && typeof o === 'object' && !(o instanceof Array); };
    var by = new Map(), edges = new Map();
    params.forEach(function (p) { if (isObj(p) && typeof p.name === 'string') by.set(p.name, p); });
    by.forEach(function (p, name) {
      if (!('used_when' in p)) return;
      var uw = p.used_when;
      if (!isObj(uw) || !Object.keys(uw).length) {
        problems.push(name + ': used_when must name at least one choice or on/off parameter and its value(s)');
        return;
      }
      edges.set(name, []);
      Object.keys(uw).forEach(function (other) {
        var q = by.get(other), want = uw[other];
        if (other === name) problems.push(name + ': used_when names the parameter itself');
        else if (q === undefined) problems.push(name + ': used_when names ' + pyRepr(other) + ', which is not a parameter');
        else if (q.type !== 'choice' && q.type !== 'bool') {
          problems.push(name + ': used_when names ' + pyRepr(other) + ', which is not a choice or on/off parameter');
        } else {
          edges.get(name).push(other);
          var wants = want instanceof Array ? want : [want];
          if (!wants.length) problems.push(name + ': used_when gives ' + other + ' no value');
          wants.forEach(function (w) {
            if (checkValue(q, w) !== null) problems.push(name + ': used_when: ' + other + ' has no value ' + pyRepr(w));
          });
        }
      });
    });
    // a condition may not go round in a circle (A only when B, B only when A)
    var state = new Map();
    function visit(n, path) {
      state.set(n, 1);
      (edges.get(n) || []).forEach(function (m) {
        if (state.get(m) === 1) {
          var loop = path.indexOf(m) >= 0 ? path.slice(path.indexOf(m)).concat([m]) : [n, m];
          problems.push(loop[0] + ': used_when goes round in a circle (' + loop.join(' -> ') + ')');
        } else if (!state.has(m)) {
          visit(m, path.concat([m]));
        }
      });
      state.set(n, 2);
    }
    edges.forEach(function (_e, n) { if (!state.has(n)) visit(n, [n]); });
  }
  function validateSpec(spec) {
    var NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
    var isObj = function (o) { return o !== null && typeof o === 'object' && !(o instanceof Array); };
    if (!isObj(spec) || !('groups' in spec) || !('parameters' in spec) ||
        Object.keys(spec).some(function (k) { return ['groups', 'parameters', 'retired'].indexOf(k) < 0; })) {
      return ['the file must be an object with "groups" and "parameters" (and, optionally, "retired")'];
    }
    var problems = [], groups = spec.groups, params = spec.parameters;
    if (!(groups instanceof Array) || !(params instanceof Array) || !params.length) {
      return ['"groups" and "parameters" must be lists, "parameters" not empty'];
    }
    var names = [];
    params.forEach(function (p, i) {
      var where = 'parameter #' + (i + 1);
      if (!isObj(p)) { problems.push(where + ': must be an object'); return; }
      var name = p.name;
      if (typeof name === 'string') where = name;
      var keys = (TYPE_KEYS.hasOwnProperty(p.type) ? TYPE_KEYS[p.type] : P_KEYS)
        .concat('used_when' in p ? ['used_when'] : []).concat('range' in p ? ['range'] : []);
      symDiff(keys, Object.keys(p)).forEach(function (k) {
        problems.push(where + ': ' + (k in p ? 'unknown' : 'missing') + ' field "' + k + '"');
      });
      if (typeof name !== 'string' || !NAME.test(name)) { problems.push(where + ': name must be a plain identifier (letters, digits, _)'); return; }
      if (names.indexOf(name) >= 0) problems.push(name + ': duplicate name');
      names.push(name);
      if (!TYPE_KEYS.hasOwnProperty(p.type)) problems.push(name + ': type must be "int", "float", "choice" or "bool"');
      if (p.type === 'choice' || p.type === 'bool') {
        if (p.type === 'choice') checkChoices(name, p, problems);
        else if (typeof p['default'] !== 'boolean') problems.push(name + ': default must be true or false');
        ['label', 'unit', 'db_unit', 'db_description', 'group'].forEach(function (k) {
          if (k in p && typeof p[k] !== 'string') problems.push(name + ': ' + k + ' must be text');
        });
        if ('range' in p) problems.push(name + ': only a number has a range ("range": "proposed")');
        return;
      }
      if ('range' in p && p.range !== 'proposed') {
        problems.push(name + ': range is "proposed" (a range an import proposed, to review) or absent');
      }
      var lo = p.min, hi = p.max, step = p.step, def = p['default'];
      if (![lo, hi, step, def].every(isNum)) { problems.push(name + ': min, max, step and default must be numbers'); return; }
      if (!(lo < hi)) problems.push(name + ': min (' + lo + ') must be smaller than max (' + hi + ')');
      if (step <= 0) problems.push(name + ': step must be positive');
      if (!(lo <= def && def <= hi)) problems.push(name + ': default ' + def + ' is outside [' + lo + '; ' + hi + ']');
      if (p.type === 'int' && ![lo, hi, step, def].every(function (v) { return Math.floor(v) === v; })) {
        problems.push(name + ': an int parameter needs whole-number min, max, step and default');
      }
      ['label', 'unit', 'db_unit', 'db_description', 'group'].forEach(function (k) {
        if (k in p && typeof p[k] !== 'string') problems.push(name + ': ' + k + ' must be text');
      });
    });
    var gids = [], placed = {};
    groups.forEach(function (g, i) {
      if (!isObj(g)) { problems.push('group #' + (i + 1) + ': must be an object'); return; }
      var gid = typeof g.id === 'string' ? g.id : 'group #' + (i + 1);
      symDiff(G_KEYS, Object.keys(g)).forEach(function (k) {
        problems.push('group ' + gid + ': ' + (k in g ? 'unknown' : 'missing') + ' field "' + k + '"');
      });
      if (gids.indexOf(gid) >= 0) problems.push('group ' + gid + ': duplicate id');
      gids.push(gid);
      (g.order || []).forEach(function (n) {
        if (names.indexOf(n) < 0) problems.push('group ' + gid + ': lists ' + pyRepr(n) + ', which is not a parameter');
        else if (placed[n] !== undefined) problems.push(n + ': listed in two groups (' + placed[n] + ', ' + gid + ')');
        else placed[n] = gid;
      });
    });
    var retired = 'retired' in spec ? spec.retired : [];
    if (!(retired instanceof Array)) problems.push('"retired" must be a list of names');
    else retired.forEach(function (n, i) {
      if (typeof n !== 'string' || !NAME.test(n)) problems.push('retired name ' + pyRepr(n) + ': must be a plain identifier');
      else if (names.indexOf(n) >= 0) problems.push(n + ': listed as retired but still a parameter');
      else if (retired.filter(function (x) { return x === n; }).length > 1) problems.push(n + ': listed as retired twice');
    });
    checkUsedWhen(params, problems);
    params.forEach(function (p) {
      if (!isObj(p) || names.indexOf(p.name) < 0) return;
      var gid = p.group;
      if (gids.indexOf(gid) < 0) problems.push(p.name + ': group ' + pyRepr(gid) + ' does not exist');
      else if (placed[p.name] !== gid) problems.push(p.name + ': not listed in the order of its group ' + pyRepr(gid));
    });
    return problems;
  }
  // -- end validate

  // where a name is mentioned in the setup's text fields (not the parameter lists)
  function textMentions(name) {
    var re = new RegExp('\\b' + name + '\\b'), out = [];
    D.slots.forEach(function (s) {
      if (s.slot === 'parameter_list') return;
      [{ agent: null, values: s.values }].concat(s.variants || []).forEach(function (v) {
        if (['7', '5', '3'].some(function (t) { return v.values[t] && re.test(v.values[t]); })) out.push(s.slot + (v.agent ? '@' + v.agent : ''));
      });
    });
    return out;
  }
  // this parameter's entry in each of the agents' lists
  function listEntries(name) {
    var s = slotByName('parameter_list'), out = [];
    if (!s) return out;
    var re = new RegExp('^\\s*\\d+\\.\\s+' + name + '\\b');
    [{ agent: null, values: s.values }].concat(s.variants || []).forEach(function (v) {
      var seen = {};
      ['3', '5', '7'].forEach(function (t) {
        var txt = v.values[t];
        if (txt === null || txt === undefined) return;
        var line = txt.split('\n').filter(function (l) { return re.test(l); })[0] || '';
        (seen[line] = seen[line] || []).push(t);
      });
      Object.keys(seen).forEach(function (line) {
        out.push({ who: (v.agent ? disp(v.agent) : 'shared') + ' · ' + seen[line].join('·'), line: line });
      });
    });
    return out;
  }

  function renderParams(center, right) {
    var spec = PE().spec;
    var fileIn = h('input', { type: 'file', accept: '.json,application/json', style: 'display:none', onchange: function (e) { importJson(e.target.files[0]); e.target.value = ''; } });
    add(center, head('Parameters', 'The one parameter file (parameters.json): the validator, the parameter sliders, the database and the agents’ parameter count read it, and the agents’ parameter lists are kept in step with it. ' +
      spec.parameters.length + ' parameters in ' + spec.groups.length + ' groups.', [
      fileIn,
      h('button', { disabled: BUSY, onclick: function () { fileIn.click(); } }, 'Import JSON…'),
      h('button', { disabled: BUSY, onclick: askCsv }, 'Paste CSV…'),
      h('button', { disabled: BUSY, onclick: addParam }, '+ Add parameter'),
      h('button', { disabled: BUSY, onclick: addGroup }, '+ Add group'),
      rangesToggle(),
      h('span', { 'class': 'grow' }),
      h('button', { disabled: BUSY || !paramsChanged() || !!D.scad_import,
        title: D.scad_import ? 'An import put these parameters in: Undo the import (above) puts them back with its tools.'
          : paramsChanged() ? null : 'Nothing has changed since the Studio opened.', onclick: askUndoAll }, 'Undo all parameter changes')]));
    add(center, importBanner());
    if (databaseChanged()) {
      add(center, h('div', { 'class': 'banner info', style: 'margin:8px 16px 0;border:1px solid #2f4f86;border-radius:7px' },
        'Names, types or ranges differ from the setup as opened: once it is deployed, the database needs a new parameter schema (Workflow Settings › Upload).'));
    }
    var t = h('table', { 'class': 'ptab pedit' }, h('thead', null, h('tr', null,
      ['', 'Name', 'Label', 'Type', 'Min', 'Max', 'Step', 'Default', 'Unit', 'Group', ''].map(function (x) { return h('th', null, x); }))));
    var tb = h('tbody');
    var groups = spec.groups.slice();
    Object.keys(GEDITS).filter(function (k) { return k.indexOf('new:') === 0; }).forEach(function (k) {
      groups.push({ id: k, label: GEDITS[k].label, image: GEDITS[k].image, order: [], unsaved: true });
    });
    // Only ranges to review: the groups and parameters with a proposed range (P6f)
    var only = onlyRanges();
    if (R.q.ranges && !only) add(center, h('div', { 'class': 'banner info boxed', style: 'margin:8px 16px 0' },
      'No range is left to review: every range is your own.'));
    groups.forEach(function (g, gi) {
      if (only && !proposedOf(g.id).length) return;
      add(tb, groupRow(g, gi, groups.length));
      paramRows(tb, g, only);
    });
    if (!only) removedGroups().forEach(function (g) {
      add(tb, h('tr', { 'class': 'grp gone' }, h('td', { colspan: 11 }, [h('s', null, g.label), ' · group removed since the Studio opened ',
        h('button', { 'class': 'mini', disabled: BUSY, onclick: function () { undoGroup(g.id); } }, 'Undo')])));
    });
    t.appendChild(tb);
    add(center, h('div', { style: 'padding:0 16px 20px' }, t));
    if (R.q.group) add(right, inspectGroup(R.q.group));
    else add(right, inspectParam(R.q.param && (savedParam(R.q.param) || PEDITS[R.q.param]) ? R.q.param : (spec.parameters[0] || {}).name));
  }
  function databaseChanged() {
    var key = function (s) {
      return JSON.stringify(s.parameters.map(function (p) {
        return [p.name, p.type, p.min, p.max, (p.choices || []).map(function (c) { return c.value; })];
      }));
    };
    return key(PE().spec) !== key(PE().opened);
  }
  function groupRow(g, gi, n) {
    var img = g.image ? h('img', { 'class': 'thumb', src: own(g.image), alt: '' }) : null;
    var sel = R.q.group === g.id;
    return h('tr', { 'class': 'grp' + (sel ? ' sel' : '') + (GEDITS[g.id] ? ' dirty' : ''), 'data-gk': g.id, style: 'cursor:pointer',
      onclick: function () { pgo({ group: g.id }); } }, h('td', { colspan: 11 }, [
      h('span', { 'class': 'mv' }, [
        h('button', { 'class': 'mini', disabled: BUSY || g.unsaved || gi === 0, title: 'Move the group up (the slider page’s order)', onclick: stopped(function () { moveGroup(g.id, -1); }) }, '↑'),
        h('button', { 'class': 'mini', disabled: BUSY || g.unsaved || gi === n - 1, title: 'Move the group down', onclick: stopped(function () { moveGroup(g.id, 1); }) }, '↓')]),
      (GEDITS[g.id] || g).label, img, g.unsaved ? pill('unsaved', 'warn') : null,
      !g.unsaved && groupChanged(g.id) ? pill('changed', 'warn', 'Changed since the Studio opened.') : null,
      keepGroupButton(g)]));
  }
  function stopped(fn) { return function (ev) { ev.stopPropagation(); fn(); }; }
  function paramRows(tb, g, only) {
    var spec = PE().spec;
    var keys = spec.parameters.filter(function (p) { return p.group === g.id && (!only || p.range === 'proposed'); })
      .map(function (p) { return p.name; });
    if (!only) Object.keys(PEDITS).filter(function (k) { return k.indexOf('new:') === 0 && PEDITS[k].group === g.id; }).forEach(function (k) { keys.push(k); });
    // a saved row whose unsaved group is another shows under its saved group
    keys.forEach(function (key, i) { add(tb, paramRow(key, i, keys)); });
    if (!only) removedParams().filter(function (p) { return p.group === g.id; }).forEach(function (p) {
      add(tb, h('tr', { 'class': 'gone' }, [h('td'), h('td', { colspan: 9 }, [h('s', { 'class': 'pname' }, p.name), ' · removed since the Studio opened']),
        h('td', null, h('button', { 'class': 'mini', disabled: BUSY, onclick: function () { undoRemoved(p.name); } }, 'Undo'))]));
    });
  }
  function paramRow(key, i, keys) {
    var isNew = key.indexOf('new:') === 0, f = rowFields(key), dirty = !!PEDITS[key];
    var p = isNew ? null : savedParam(key), info = isNew ? null : (D.parameters.parameters.filter(function (x) { return x.name === key; })[0] || null);
    var bad = info && unitMismatch(info);
    var sel = R.q.param === key && !R.q.group;
    // min and max of a range an import proposed: amber until reviewed (P6f)
    var proposed = f.range === 'proposed' && !typedType(f.type);
    function cell(k, style) {
      var amber = proposed && (k === 'min' || k === 'max');
      return h('td', { 'class': (NUMERIC[k] ? 'num' : '') + (amber ? ' proposed' : '') || null, style: style || null,
        title: amber ? PROPOSED_TIP : null }, h('input', {
        type: 'text', value: f[k] === undefined || f[k] === null ? '' : String(f[k]), spellcheck: 'false', 'data-fk': 'param|' + key, 'data-t': k,
        'class': k === 'unit' && bad ? 'invalid' : null,
        oninput: function (e) { onParamInput(key, k, e.target.value); }, onfocus: function () { selectParam(key); } }));
    }
    var groups = PE().spec.groups;
    var same = keys.filter(function (k) { return k.indexOf('new:') < 0; });
    var pos = same.indexOf(key);
    return h('tr', { 'class': (sel ? 'sel ' : '') + (dirty ? 'dirty ' : '') + (bad ? 'warnrow' : ''), 'data-pk': key }, [
      h('td', { 'class': 'mv' }, isNew ? null : [
        h('button', { 'class': 'mini', disabled: BUSY || dirty || pos <= 0, title: 'Move up (the order of the agents’ lists and the database)', onclick: function () { moveParam(key, -1); } }, '↑'),
        h('button', { 'class': 'mini', disabled: BUSY || dirty || pos < 0 || pos >= same.length - 1, title: 'Move down', onclick: function () { moveParam(key, 1); } }, '↓')]),
      cell('name', 'width:150px'), cell('label'),
      h('td', { style: 'width:72px' }, h('select', { 'data-fk': 'param|' + key, 'data-t': 'type', onchange: function (e) { onParamInput(key, 'type', e.target.value); },
        onfocus: function () { selectParam(key); } }, TYPE_CHOICES.map(function (o) { return h('option', { value: o[0], selected: o[0] === f.type }, o[1]); })))]
      .concat(typedType(f.type) ? [h('td', { colspan: 3, 'class': 'muted typesum', style: 'font-size:12px;padding-left:8px' }, typeSummary(f)),
        h('td', { style: 'width:64px' }, defaultPick(key, f))]
        : [cell('min', 'width:64px'), cell('max', 'width:64px'), cell('step', 'width:58px'), cell('default', 'width:64px')])
      .concat([cell('unit'),
      h('td', { style: 'width:120px' }, h('select', { 'data-fk': 'param|' + key, 'data-t': 'group', onchange: function (e) { onParamInput(key, 'group', e.target.value); },
        onfocus: function () { selectParam(key); } }, groups.map(function (g) { return h('option', { value: g.id, selected: g.id === f.group }, g.label); }))),
      h('td', { 'class': 'racts', 'data-pacts': key }, paramActions(key))
    ]));
  }
  function paramActions(key) {
    var isNew = key.indexOf('new:') === 0;
    if (PEDITS[key]) {
      var problems = rowProblems(key);
      return [problems.length ? pill(problems.length + (problems.length === 1 ? ' problem' : ' problems'), 'bad', problems.join('\n')) : null,
        h('button', { 'class': 'primary mini', disabled: BUSY || problems.length > 0, title: problems.length ? 'Fix the problems first (see the inspector).' : null,
          onclick: function () { saveParamRow(key); } }, 'Save'),
        h('button', { 'class': 'mini', onclick: function () { delete PEDITS[key]; render(); } }, 'Discard')];
    }
    return [paramChanged(key) ? h('button', { 'class': 'mini', disabled: BUSY, title: openedNameOf(key) ? 'Put this parameter back as it was when the Studio opened.' : 'Remove this parameter, added since the Studio opened.',
        onclick: function () { undoParam(key); } }, 'Undo') : null,
      isNew ? null : h('button', { 'class': 'mini danger', disabled: BUSY, title: 'Remove this parameter', onclick: function () { removeParam(key); } }, '×')];
  }
  function onParamInput(key, k, value) {
    if (!PEDITS[key]) PEDITS[key] = rowFields(key);
    var was = PEDITS[key].type;
    PEDITS[key] = withInput(PEDITS[key], k, value);
    if (k === 'type' && value !== was && (typedType(was) || typedType(value))) {
      // another kind of row: its cells change (MAS-blueprint P6d)
      retype(key, PEDITS[key], value);
      if (key.indexOf('new:') < 0 && JSON.stringify(entryOf(PEDITS[key])) === JSON.stringify(entryOf(rowFields2(key)))) delete PEDITS[key];
      render();
      return;
    }
    if (key.indexOf('new:') < 0 && JSON.stringify(entryOf(PEDITS[key])) === JSON.stringify(entryOf(rowFields2(key)))) delete PEDITS[key];
    var a = doc.querySelector('[data-pacts="' + key + '"]');
    if (a) { a.innerHTML = ''; add(a, paramActions(key)); }
    var tr = doc.querySelector('tr[data-pk="' + key + '"]');
    if (tr) tr.classList.toggle('dirty', !!PEDITS[key]);
    if (tr && !(PEDITS[key] || rowFields(key)).range) {
      Array.prototype.forEach.call(tr.querySelectorAll('td.proposed'), function (td) { td.classList.remove('proposed'); td.removeAttribute('title'); });
    }
    var u = el('unsavedCount');
    if (u) { u.innerHTML = ''; add(u, unsavedPill()); }
    if (k === 'choices' || k === 'default') {
      // the row's default and its choices' count follow the inspector
      var f = PEDITS[key] || rowFields(key), pick = doc.querySelector('tr[data-pk="' + key + '"] select[data-t="default"]');
      if (pick) pick.parentNode.replaceChild(defaultPick(key, f), pick);
      var sum = doc.querySelector('tr[data-pk="' + key + '"] td.typesum');
      if (sum) sum.textContent = typeSummary(f);
    }
    if (R.q.param === key) {
      // the inspector drawn again, the box being typed in keeping the cursor
      var act = doc.activeElement, ft = act && act.getAttribute ? act.getAttribute('data-t') : null;
      var caret = ft ? [act.selectionStart, act.selectionEnd] : null;
      var right = el('colRight');
      right.innerHTML = '';
      add(right, inspectParam(key));
      var back = ft && !doc.body.contains(act) ? right.querySelector('[data-t="' + ft + '"]') : null;
      if (back) {
        back.focus();
        try { back.setSelectionRange(caret[0], caret[1]); } catch (e) { /* not a text box */ }
      }
    }
  }
  function rowFields2(key) { return clone(savedParam(key)); }
  // A row's fields after one input (a copy): min or max typed makes the range
  // the owner's, not the one an import proposed (P6f).
  function withInput(f, k, value) {
    var out = clone(f);
    out[k] = value;
    if (k === 'min' || k === 'max') delete out.range;
    return out;
  }
  function selectParam(key) {
    if (R.q.param === key && !R.q.group) return;
    root.history.replaceState(null, '', plink({ param: key }));
    parse();
    Array.prototype.forEach.call(doc.querySelectorAll('tr.sel'), function (x) { x.classList.remove('sel'); });
    var tr = doc.querySelector('tr[data-pk="' + key + '"]');
    if (tr) tr.classList.add('sel');
    var right = el('colRight');
    if (right) { right.innerHTML = ''; add(right, inspectParam(key)); }
  }

  /* -- the changes ------------------------------------------------------------ */
  // Every change: the server's preview first; a change that touches the
  // agents' lists, removes or renames a parameter is shown before it is saved.
  function applyParams(spec, renames, title, after) {
    if (BUSY) return;
    BUSY = true;
    status('Checking the parameters…', 'busy');
    call('preview_parameters', spec, PE().sha, renames).then(function (r) {
      BUSY = false;
      if (!r || r.ok === false) {
        status((r && r.error) || 'The check failed.', 'err');
        render();
        showModal(r && r.conflict ? 'The parameters changed on disk' : 'The parameters cannot be saved',
          h('div', null, [h('p', { style: 'margin:0 0 8px' }, (r && r.error) || '')].concat((r && r.problems || []).map(function (p) { return h('div', { 'class': 'probline' }, '✗ ' + p); }))),
          [r && r.conflict ? h('button', { 'class': 'primary', onclick: function () { closeModal(); reloadParams(); } }, 'Reload') : null,
           h('button', { onclick: closeModal }, 'Close')]);
        return;
      }
      if (r.same) { status('Nothing to save: the parameters are already so.', ''); render(); if (after) after(); return; }
      var c = r.changes, quiet = !title && !r.lists.length && !c.removed.length && !Object.keys(c.renamed).length;
      if (quiet) { saveParams(spec, renames, after); return; }
      render();
      showModal(title || 'Save the parameters', previewBody(r), [
        h('button', { onclick: closeModal }, 'Cancel'),
        h('button', { 'class': 'primary', onclick: function () { closeModal(); saveParams(spec, renames, after); } }, title ? 'Apply' : 'Save')]);
    }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
  }
  function saveParams(spec, renames, after) {
    change('save_parameters', [spec, PE().sha, renames], 'params', 'Saved the parameters' + (Object.keys(renames).length ? ' (renamed: ' +
      Object.keys(renames).map(function (k) { return k + ' → ' + renames[k]; }).join(', ') + ')' : '') + '.', after);
  }
  function reloadParams() {
    BUSY = true; status('Reading the setup again…', 'busy'); render();
    reload().then(function () { BUSY = false; status('The parameters show what is on disk now.', 'ok'); render(); },
      function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
  }
  function previewBody(r) {
    var c = r.changes, items = [];
    if (c.added.length) items.push('Added: ' + c.added.join(', '));
    c.removed.forEach(function (n) { items.push('Removed: ' + n + ' (its name joins “retired”: an old record that carries it is read without it)'); });
    Object.keys(c.renamed).forEach(function (o) { items.push('Renamed: ' + o + ' → ' + c.renamed[o] + ' (the old name joins “retired”)'); });
    Object.keys(c.fields).forEach(function (n) {
      items.push(n + ': ' + Object.keys(c.fields[n]).map(function (k) { return k + ' ' + JSON.stringify(c.fields[n][k][0]) + ' → ' + JSON.stringify(c.fields[n][k][1]); }).join(', '));
    });
    if (c.order) items.push('The order of the parameters changes (the agents’ lists and the database follow it).');
    c.groups.added.forEach(function (g) { items.push('Group added: ' + g); });
    c.groups.removed.forEach(function (g) { items.push('Group removed: ' + g); });
    Object.keys(c.groups.changed).forEach(function (g) {
      items.push('Group ' + g + ': ' + Object.keys(c.groups.changed[g]).map(function (k) { return k + ' ' + JSON.stringify(c.groups.changed[g][k][0]) + ' → ' + JSON.stringify(c.groups.changed[g][k][1]); }).join(', '));
    });
    if (c.groups.order) items.push('The order of the groups changes (the slider page follows it).');
    var gone = c.removed.concat(Object.keys(c.renamed));
    var warn = gone.map(function (n) {
      var code = r.code_uses[n] || [], text = textMentions(n);
      if (!code.length && !text.length) return null;
      return h('div', null, [h('b', null, n), ' is still named in ' + [code.length ? code.map(function (u) { return u[0] + (u[1] > 1 ? ' (' + u[1] + '×)' : ''); }).join(', ') : null,
        text.length ? 'the text fields ' + text.join(', ') : null].filter(function (x) { return x; }).join('; and in ') + '.']);
    }).filter(function (x) { return x; });
    var body = h('div', { 'class': 'pprev' }, [
      h('ul', { 'class': 'checks' }, items.map(function (x) { return h('li', null, ['•', h('span', null, x)]); })),
      warn.length ? h('div', { 'class': 'banner warn boxed' }, warn.concat([h('div', { style: 'margin-top:4px' }, 'The Studio does not change code or other texts: update them yourself (tools come in P6c).')])) : null,
      r.database ? h('div', { 'class': 'banner info boxed' }, 'Names, types or ranges change: once the setup is deployed, the database needs a new parameter schema (Workflow Settings › Upload).') : null,
      h('h4', null, r.lists.length ? 'The agents’ parameter lists · ' + r.lists.length + ' of ' + PE().lists.length + ' change' : 'The agents’ parameter lists do not change')
    ].concat(r.lists.map(function (l) {
      return h('details', { 'class': 'vtool' }, [h('summary', null, h('span', { 'class': 'mono' }, l.file)),
        h('div', { 'class': 'diff' }, l.lines.map(function (x) {
          return h('div', { 'class': x[0] === '+' ? 'd-add' : x[0] === '-' ? 'd-del' : x[0] === '…' ? 'd-fold' : 'd-eq' }, (x[0] === '=' ? '  ' : x[0] === '…' ? '⋯' : x[0] + ' ') + x[1]);
        }))]);
    })));
    return body;
  }
  function saveParamRow(key) {
    var r = specWithRow(key), f = entryOf(rowFields(key));
    applyParams(r.spec, r.renames, null, function () {
      delete PEDITS[key];
      root.history.replaceState(null, '', plink({ param: f.name }));
    });
  }
  function addParam() {
    var g = R.q.group && savedGroup(R.q.group) ? R.q.group : (PE().spec.groups[0] || {}).id;
    var key = 'new:' + (++NEWSEQ);
    PEDITS[key] = { name: '', type: 'float', min: '0', max: '1', step: '1', 'default': '0', group: g, label: '', unit: '', db_unit: '', db_description: '' };
    root.history.replaceState(null, '', plink({ param: key }));
    render();
    var n = doc.querySelector('[data-fk="param|' + key + '"][data-t="name"]');
    if (n) n.focus();
  }
  function moveParam(key, dir) {
    var spec = clone(PE().spec), ps = spec.parameters, i = ps.map(function (p) { return p.name; }).indexOf(key), j = i + dir;
    while (j >= 0 && j < ps.length && ps[j].group !== ps[i].group) j += dir;
    if (j < 0 || j >= ps.length) return;
    var a = ps[i]; ps[i] = ps[j]; ps[j] = a;
    applyParams(spec, {}, null);
  }
  function removeParam(key) {
    var spec = clone(PE().spec);
    spec.parameters = spec.parameters.filter(function (p) { return p.name !== key; });
    removeFromOrders(spec, key);
    applyParams(spec, {}, null, function () { root.history.replaceState(null, '', plink({})); });
  }
  function undoParam(key) {
    var o = openedNameOf(key), spec = clone(PE().spec), renames = {};
    if (!o) { removeParam(key); return; }
    var op = clone(openedParam(o)), i = spec.parameters.map(function (p) { return p.name; }).indexOf(key), cur = spec.parameters[i];
    spec.parameters[i] = op;
    if (key !== o) {
      renames[key] = o;
      spec.groups.forEach(function (g) { g.order = g.order.map(function (n) { return n === key ? o : n; }); });
    }
    if (cur.group !== op.group) {
      var og = groupOf(spec, op.group);
      if (!og) { status('Its group ' + op.group + ' is gone: put the group back first, or use Undo all parameter changes.', 'err'); return; }
      removeFromOrders(spec, o);
      var at = (openedGroup(op.group).order || []).indexOf(o);
      og.order.splice(Math.min(at < 0 ? og.order.length : at, og.order.length), 0, o);
    }
    applyParams(spec, renames, null, function () { root.history.replaceState(null, '', plink({ param: o })); });
  }
  function undoRemoved(name) {
    var spec = clone(PE().spec), op = clone(openedParam(name)), g = groupOf(spec, op.group);
    if (!g) { status('Its group ' + op.group + ' is gone: put the group back first.', 'err'); return; }
    var at = PE().opened.parameters.map(function (p) { return p.name; }).indexOf(name);
    spec.parameters.splice(Math.min(at, spec.parameters.length), 0, op);
    var gat = (openedGroup(op.group).order || []).indexOf(name);
    g.order.splice(Math.min(gat < 0 ? g.order.length : gat, g.order.length), 0, name);
    if (spec.retired) spec.retired = spec.retired.filter(function (n) { return n !== name; });
    applyParams(spec, {}, null);
  }
  /* -- ranges an import proposed (P6f) ------------------------------------------ */
  // A number may carry "range": "proposed": the import of a CAD model made its
  // min and max from the model's default (studio/scad_import.py).  Its cells
  // are amber until it is reviewed: min or max edited, or kept as it is (Keep,
  // for a parameter or a group: a save without the marker).
  var PROPOSED_TIP = 'Proposed by the import from the model’s default: review it (edit min or max, or keep it in the inspector).';
  function proposedOf(group) {
    return PE().spec.parameters.filter(function (p) { return p.range === 'proposed' && (!group || p.group === group); })
      .map(function (p) { return p.name; });
  }
  function onlyRanges() { return !!R.q.ranges && proposedOf().length > 0; }
  // An address in Parameters that keeps Only ranges to review as it is.
  function plink(q) { return link('studio', 'parameters', Object.assign({ ranges: R.q.ranges || null }, q)); }
  function pgo(q) { root.location.hash = plink(q); }
  // *spec* (a copy) without the marker on the parameters *names*
  function withoutRanges(spec, names) {
    var out = clone(spec);
    out.parameters.forEach(function (p) { if (names.indexOf(p.name) >= 0) delete p.range; });
    return out;
  }
  function keepRanges(names) {
    applyParams(withoutRanges(PE().spec, names), {}, null, function () {
      names.forEach(function (n) { if (PEDITS[n]) delete PEDITS[n].range; });
    });
  }
  function rangesToggle() {
    var n = proposedOf().length;
    if (!n && !R.q.ranges) return null;
    return h('button', { 'class': R.q.ranges ? 'on' : null, title: 'Show only the parameters whose range an import proposed.',
      onclick: function () { go('studio', 'parameters', withQ({ ranges: R.q.ranges ? null : '1' })); } },
      (R.q.ranges ? '✓ ' : '') + 'Only ranges to review (' + n + ')');
  }
  function keepGroupButton(g) {
    var names = g.unsaved ? [] : proposedOf(g.id);
    if (!names.length) return null;
    return h('span', { 'class': 'keepg' }, [pill(names.length + ' to review', 'warn', 'Ranges the import proposed in this group.'),
      h('button', { 'class': 'mini', disabled: BUSY, title: 'Keep the proposed ranges of this group as they are.',
        onclick: stopped(function () { keepRanges(names); }) },
        'Keep all ' + names.length + (names.length === 1 ? ' range' : ' ranges') + ' in this group')]);
  }
  function rangeBlock(key, f, dirty, isNew) {
    if (f.range !== 'proposed' || typedType(f.type)) return null;
    return h('div', { 'class': 'block proposed' }, [h('h4', null, 'Range to review'),
      h('p', null, 'The import proposed [' + f.min + '; ' + f.max + '] from the model’s default (' + f['default'] +
        '). Check it against what the model can make: edit min or max, or keep it as it is.'),
      h('button', { disabled: BUSY || dirty || isNew, title: dirty ? 'Save or discard this parameter’s changes first.' : null,
        onclick: function () { keepRanges([key]); } }, 'Keep this range')]);
  }

  function askUndoAll() {
    showModal('Undo all parameter changes', h('p', { style: 'margin:0;font-size:12.5px;line-height:1.5' },
      'parameters.json and the agents’ parameter lists go back to exactly how they were when the Studio opened; a picture uploaded since then that no group uses is removed. The agent-access grid is not touched.'), [
      h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'danger', onclick: function () {
        closeModal(); PEDITS = {}; GEDITS = {};
        change('undo_parameters', [], 'params', 'The parameters and their lists are back as they were when the Studio opened.');
      } }, 'Undo all')]);
  }

  /* -- groups ---------------------------------------------------------------- */
  function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'group'; }
  function addGroup() {
    var key = 'new:' + (++NEWSEQ);
    GEDITS[key] = { id: '', label: 'New group', image: '', image_alt: '', order: [] };
    pgo({ group: key });
  }
  function groupFields(key) {
    if (GEDITS[key]) return GEDITS[key];
    var g = savedGroup(key);
    return g ? { id: g.id, label: g.label, image: g.image, image_alt: g.image_alt, order: g.order.slice() } : null;
  }
  function onGroupInput(key, k, value) {
    var f = clone(groupFields(key));
    f[k] = value;
    if (key.indexOf('new:') === 0 && k === 'label') {
      var id = slug(value), ids = PE().spec.groups.map(function (g) { return g.id; }), n = 2, base = id;
      while (ids.indexOf(id) >= 0) id = base + '_' + (n++);
      f.id = id;
    }
    GEDITS[key] = f;
    var g = savedGroup(key);
    if (g && JSON.stringify({ id: g.id, label: g.label, image: g.image, image_alt: g.image_alt, order: g.order }) === JSON.stringify(f)) delete GEDITS[key];
    var right = el('colRight');
    if (right) {
      var a = right.querySelector('[data-gacts]');
      if (a) { a.innerHTML = ''; add(a, groupActions(key)); }
    }
    var row = doc.querySelector('tr[data-gk="' + key + '"]');
    if (row) row.classList.toggle('dirty', !!GEDITS[key]);
  }
  function groupActions(key) {
    var isNew = key.indexOf('new:') === 0;
    if (GEDITS[key]) {
      var problems = groupProblems(key);
      return [problems.length ? h('div', { 'class': 'checks bad', style: 'margin-bottom:6px' }, problems.map(function (p) { return h('div', null, '✗ ' + p); })) : null,
        h('button', { 'class': 'primary', disabled: BUSY || problems.length > 0, onclick: function () {
          var spec = specWithGroup(key), id = GEDITS[key].id;
          applyParams(spec, {}, null, function () { delete GEDITS[key]; root.history.replaceState(null, '', plink({ group: id })); });
        } }, isNew ? 'Add the group' : 'Save'),
        h('button', { onclick: function () { delete GEDITS[key]; if (isNew) pgo({}); else render(); } }, 'Discard')];
    }
    if (isNew) return [];
    var g = savedGroup(key), empty = g && !g.order.length && !PE().spec.parameters.some(function (p) { return p.group === key; });
    return [groupChanged(key) ? h('button', { disabled: BUSY, onclick: function () { undoGroup(key); } }, 'Undo') : null,
      h('button', { 'class': 'danger', disabled: BUSY || !empty, title: empty ? null : 'Only an empty group can be deleted: move its parameters first.',
        onclick: function () { deleteGroup(key); } }, 'Delete the group')];
  }
  function inspectGroup(key) {
    var f = groupFields(key);
    if (!f) return h('div', { 'class': 'insp muted' }, 'This group is gone.');
    var assets = PE().assets.slice();
    var cur = (f.image || '').split('/').pop();
    if (cur && assets.indexOf(cur) < 0) assets.push(cur);
    var picIn = h('input', { type: 'file', accept: 'image/png', style: 'display:none', onchange: function (e) { uploadPicture(key, e.target.files[0]); e.target.value = ''; } });
    var orderBox = h('div', { 'class': 'order' }, f.order.map(function (n, i) {
      return h('div', { 'class': 'orow' }, [h('span', { 'class': 'pname' }, n), h('span', { 'class': 'grow' }),
        h('button', { 'class': 'mini', disabled: i === 0, onclick: function () { var o = f.order.slice(); o.splice(i - 1, 0, o.splice(i, 1)[0]); onGroupInput(key, 'order', o); render(); } }, '↑'),
        h('button', { 'class': 'mini', disabled: i === f.order.length - 1, onclick: function () { var o = f.order.slice(); o.splice(i + 1, 0, o.splice(i, 1)[0]); onGroupInput(key, 'order', o); render(); } }, '↓')]);
    }));
    return h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, key.indexOf('new:') === 0 ? 'New group' + (f.id ? ' · ' + f.id : '') : 'Group · ' + key),
      h('div', { 'class': 'kv', style: 'grid-template-columns:90px 1fr;align-items:center' }, [
        h('div', { 'class': 'k' }, 'Label'), h('input', { type: 'text', value: f.label, 'data-fk': 'group|' + key, 'data-t': 'label', oninput: function (e) { onGroupInput(key, 'label', e.target.value); } }),
        h('div', { 'class': 'k' }, 'Picture'), h('div', { 'class': 'row2' }, [
          h('select', { onchange: function (e) { onGroupInput(key, 'image', e.target.value ? '/pack/assets/' + e.target.value : ''); render(); } },
            [h('option', { value: '', selected: !cur }, '(none)')].concat(assets.map(function (a) { return h('option', { value: a, selected: a === cur }, a); }))),
          picIn, h('button', { 'class': 'mini', disabled: BUSY, onclick: function () { picIn.click(); } }, 'Upload PNG…')]),
        h('div', { 'class': 'k' }, 'Picture text'), h('input', { type: 'text', value: f.image_alt, 'data-fk': 'group|' + key, 'data-t': 'image_alt', oninput: function (e) { onGroupInput(key, 'image_alt', e.target.value); } })]),
      f.image ? h('img', { 'class': 'gpic', src: own(f.image), alt: f.image_alt }) : null,
      h('div', { 'class': 'block' }, [h('h4', null, 'Slider order · ' + f.order.length),
        h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-bottom:6px' }, 'The order of this group’s sliders on the Parameters page of the web app. The agents’ lists and the database follow the table’s order instead.'),
        f.order.length ? orderBox : h('p', { 'class': 'muted' }, 'No parameter in this group yet.')]),
      h('div', { 'class': 'block', 'data-gacts': '1' }, groupActions(key))
    ]);
  }
  function uploadPicture(key, file) {
    if (!file) return;
    var fr = new root.FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1] || '';
      BUSY = true; status('Uploading ' + file.name + '…', 'busy'); render();
      call('upload_picture', file.name, b64).then(function (r) {
        BUSY = false;
        if (!r || r.ok === false) { status((r && r.error) || 'The upload failed.', 'err'); render(); return; }
        PE().assets.push(r.file);
        onGroupInput(key, 'image', r.path);
        status('Uploaded assets/' + r.file + ': save the group to use it.', 'ok');
        render();
      }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
    };
    fr.readAsDataURL(file);
  }
  function moveGroup(id, dir) {
    var spec = clone(PE().spec), i = spec.groups.map(function (g) { return g.id; }).indexOf(id), j = i + dir;
    if (j < 0 || j >= spec.groups.length) return;
    var a = spec.groups[i]; spec.groups[i] = spec.groups[j]; spec.groups[j] = a;
    applyParams(spec, {}, null);
  }
  function deleteGroup(id) {
    var spec = clone(PE().spec);
    spec.groups = spec.groups.filter(function (g) { return g.id !== id; });
    applyParams(spec, {}, null, function () { root.history.replaceState(null, '', plink({})); });
  }
  function undoGroup(id) {
    var spec = clone(PE().spec), og = clone(openedGroup(id));
    if (!og) {
      spec.groups = spec.groups.filter(function (g) { return g.id !== id; });
      applyParams(spec, {}, null, function () { root.history.replaceState(null, '', plink({})); call('drop_pictures'); });
      return;
    }
    var g = groupOf(spec, id), mine = spec.parameters.filter(function (p) { return p.group === id; }).map(function (p) { return p.name; });
    var order = og.order.filter(function (n) { return mine.indexOf(n) >= 0; });
    mine.forEach(function (n) { if (order.indexOf(n) < 0) order.push(n); });
    og.order = order;
    if (g) spec.groups[spec.groups.indexOf(g)] = og;
    else spec.groups.splice(Math.min(PE().opened.groups.map(function (x) { return x.id; }).indexOf(id), spec.groups.length), 0, og);
    applyParams(spec, {}, null, function () { call('drop_pictures'); });
  }

  /* -- Import JSON / Paste CSV -------------------------------------------------- */
  function importJson(file) {
    if (!file) return;
    var fr = new root.FileReader();
    fr.onload = function () {
      var spec;
      try { spec = JSON.parse(String(fr.result)); } catch (e) { status(file.name + ' is not valid JSON: ' + e.message, 'err'); return; }
      applyParams(spec, {}, 'Import ' + file.name);
    };
    fr.readAsText(file);
  }
  function askCsv() {
    // the example rows come from the setup: its first parameter, and a new one in its first group
    var p0 = PE().spec.parameters[0], g0 = PE().spec.groups[0];
    var ta = h('textarea', { rows: 10, spellcheck: 'false', style: 'width:100%;font-family:var(--mono);font-size:11.5px',
      placeholder: 'name,min,max,unit,group\n' + (p0 ? p0.name + ',' + p0.min + ',' + p0.max + ',' + p0.unit + ',\n' : '') +
        'newParameter,0,10,,' + (g0 ? g0.label : '') });
    var msg = h('div');
    showModal('Paste CSV', h('div', null, [
      h('p', { style: 'margin:0 0 8px;font-size:12.5px;line-height:1.5' }, 'One row per parameter, matched by name; the first row names the columns: name, type, min, max, step, default, unit, label, group, description. Only the columns you give change; a new name is added (it needs a group, min and max); parameters the CSV does not name stay. Commas, semicolons or tabs.'),
      ta, msg]), [
      h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'primary', onclick: function () {
        call('csv_parameters', ta.value).then(function (r) {
          if (!r || r.ok === false || (r.problems || []).length) {
            msg.innerHTML = '';
            add(msg, [h('div', { 'class': 'probline' }, (r && r.error) || '')].concat(((r && r.problems) || []).map(function (p) { return h('div', { 'class': 'probline' }, '✗ ' + p); })));
            return;
          }
          closeModal();
          applyParams(r.spec, {}, 'Paste CSV');
        });
      } }, 'Preview')]);
  }

  function inspectParam(key) {
    if (!key) return h('div', { 'class': 'insp empty' }, 'Select a parameter.');
    var f = rowFields(key), isNew = key.indexOf('new:') === 0, dirty = !!PEDITS[key];
    var info = isNew ? null : D.parameters.parameters.filter(function (x) { return x.name === key; })[0];
    var bad = info && unitMismatch(info), problems = dirty ? rowProblems(key) : [];
    var code = isNew ? [] : (PE().code_uses[key] || []), text = isNew ? [] : textMentions(key), lines = isNew ? [] : listEntries(key);
    var o = isNew ? null : openedNameOf(key);
    function input(k) {
      return h('input', { type: 'text', value: f[k] || '', spellcheck: 'false', 'data-fk': 'param|' + key, 'data-t': k,
        oninput: function (e) { onParamInput(key, k, e.target.value); } });
    }
    return h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, isNew ? (f.name || 'New parameter') : key),
      h('div', { 'class': 'pills' }, [kpill(f.type === 'bool' ? 'on/off' : f.type),
        kpill(f.type === 'choice' ? (f.choices || []).length + ' choices' : f.type === 'bool' ? 'true / false' : '[' + f.min + '; ' + f.max + ']'),
        kpill('default ' + f['default']),
        dirty ? pill('unsaved', 'warn') : null, !isNew && paramChanged(key) ? pill(o ? 'changed since opened' : 'added since opened', 'warn') : null,
        o && o !== key ? kpill('was ' + o) : null]),
      h('div', { 'class': 'block' }, [h('h4', null, 'Checks')].concat(
        !dirty ? [h('p', { 'class': 'muted' }, 'No unsaved change.')] :
          problems.length ? [h('ul', { 'class': 'checks bad' }, problems.map(function (p) { return h('li', null, ['✗', h('span', null, p)]); }))] :
          [h('ul', { 'class': 'checks good' }, [h('li', null, ['✓', h('span', null, 'No problems: it can be saved.')])])])),
      rangeBlock(key, f, dirty, isNew),
      f.type === 'choice' ? choicesBlock(key, f) : null,
      whenBlock(key, f),
      h('div', { 'class': 'block' }, [h('h4', null, 'The database’s words'), h('div', { 'class': 'kv', style: 'grid-template-columns:90px 1fr;align-items:center' }, [
        h('div', { 'class': 'k' }, 'unit'), input('db_unit'), h('div', { 'class': 'k' }, 'description'), input('db_description')])]),
      bad ? h('div', { 'class': 'banner warn boxed' }, [h('b', null, 'Two texts disagree on the unit. '), 'The agents’ parameter list says “' + info.unit_prompt + '”; the slider page says “' +
        info.unit + '”. The agents’ lists are hand-written text ($parameter_list); the Studio keeps their names, order and ranges in step, not their units.']) : null,
      lines.length ? h('div', { 'class': 'block' }, [h('h4', null, 'In the agents’ parameter lists · ' + lines.length),
        h('div', { 'class': 'lentries' }, lines.map(function (x) { return h('div', null, [h('span', { 'class': 'muted' }, x.who), h('div', { 'class': 'mono' }, x.line || '(no entry)')]); })),
        h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-top:4px' }, 'A Save changes its name and [min; max] — or its values — and its “(only when …)” in every list, or adds / removes its entry; the rest of each line is yours (Configurator description › parameter_list).')]) : null,
      h('div', { 'class': 'block' }, [h('h4', null, 'Named in code · ' + code.length),
        code.length ? h('ul', { 'class': 'checks' }, code.map(function (u) { return h('li', null, ['•', h('span', { 'class': 'mono' }, u[0] + (u[1] > 1 ? '  ×' + u[1] : ''))]); }))
          : h('p', { 'class': 'muted' }, 'No code or configuration file of the setup names it.'),
        code.length ? h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-top:4px' }, 'Renaming or removing it leaves these files naming the old name: update them yourself (tools come in P6c).') : null]),
      text.length ? h('div', { 'class': 'block' }, [h('h4', null, 'Mentioned in text fields · ' + text.length),
        h('div', null, text.map(function (n) {
          var parts = n.split('@'), s = slotByName(parts[0]);
          return h('a', { 'class': 'kpill', style: 'display:inline-block;margin:2px;text-decoration:none', href: link('studio', s ? s.section : 'description', { field: parts[0], agent: parts[1] || null }) }, n);
        }))]) : null
    ]);
  }

  /* ======================================================================
   * Tools (P6c): each tool of the setup edited -- its manifest (a form, or
   * the tool.yaml text), its files, its tool-list entry -- removed, and put
   * back as the Studio opened it (studio/tools_edit.py).  A form's unsaved
   * manifest lives in TEDITS, a file's unsaved text in FEDITS.
   * ==================================================================== */
  var TEDITS = {};          // unsaved manifests from the form: tool -> manifest
  var FEDITS = {};          // unsaved file texts: tool/path -> text
  var FILES = {}, FILE_LOADING = {};   // files read from the server: tool/path -> {text, sha, size}
  var TOOL_TABS = [['form', 'Manifest'], ['yaml', 'tool.yaml'], ['files', 'Files'], ['texts', 'Prompt texts'], ['test', 'Test']];
  function TE() { return D.tools_edit; }
  function toolState(name) { return (TE().tools || {})[name] || null; }
  function manifestOf(name) { return TEDITS[name] || toolState(name).manifest; }
  function toolRoles() { return ROLE_ROWS.filter(function (r) { return r.role !== 'database_handler'; }); }
  function geometryTools() {
    return Object.keys(TE().tools).filter(function (n) { return (TE().tools[n].manifest || {}).kind === 'geometry'; });
  }
  function setPath(o, path, value) {
    for (var i = 0; i < path.length - 1; i++) o = o[path[i]];
    o[path[path.length - 1]] = value;
  }
  function getPath(o, path) {
    for (var i = 0; i < path.length; i++) { if (o === null || o === undefined) return undefined; o = o[path[i]]; }
    return o;
  }
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
    if (R.q.tool && toolState(R.q.tool)) { renderToolEditor(center, right, R.q.tool); return; }
    add(center, head('Tools', 'The functions your agents call to build and look at a design. Each tool is a plain Python function, or an OpenSCAD model the engine runs, plus a manifest: what it is, which role may call it, what it produces, and the text the agents read about it.', [
      h('a', { 'class': 'btn', href: 'static/write-a-tool.html', target: '_blank', rel: 'noopener',
        title: 'How a tool is made: its kinds, its manifest, its code, its pictures and texts.' }, 'Write a tool ↗'),
      h('button', { 'class': 'primary', disabled: BUSY, onclick: askNewTool }, '+ New tool')]));
    add(center, importBanner());
    add(center, scadDrop());
    scadDragTarget(center);
    var wrap = h('div', { 'class': 'toolcards' });
    D.tools.forEach(function (t) {
      var info = D.tool_info[t.name] || { roles: [], images: [], settings: [] }, st = toolState(t.name) || {};
      var first = t.description.split('\n\n')[0].replace(/\s+/g, ' ');
      var settings = info.settings.length ? info.settings.join(', ') : 'none';
      add(wrap, h('div', { 'class': 'tcard' }, [
        h('div', { 'class': 'head' }, [h('span', { 'class': 'n' }, t.name), pill(t.display), kpill(t.kind === 'generator' ? 'generator · primary' : t.kind),
          st.changed ? pill(st.opened ? 'changed' : 'added', 'warn', 'Changed since the Studio opened.') : null,
          h('span', { 'class': 'grow' }),
          st.changed ? h('button', { disabled: BUSY, title: st.opened ? 'Put this tool back as it was when the Studio opened.' : 'Remove this tool, made since the Studio opened.',
            onclick: function () { undoTool(t.name); } }, 'Undo') : null,
          h('button', { 'class': 'primary', onclick: function () { go('studio', 'tools', { tool: t.name }); } }, 'Edit'),
          h('button', { onclick: function () { go('studio', 'tools', { tool: t.name, tab: 'test' }); } }, 'Test tool'),
          h('button', { 'class': 'danger', disabled: BUSY, onclick: function () { askRemoveTool(t.name); } }, 'Remove…')]),
        h('div', { 'class': 'd' }, first),
        h('div', { 'class': 'grid2' }, [
          h('div', { 'class': 'k' }, 'Called by'), h('div', null, t.kind === 'geometry'
            ? 'the engine, never an agent: the generator’s geometry tool setting, the Download buttons'
            : info.roles.map(function (r) { return roleLabel(r) + ': ' + rolesLine(r); }).join('; ') || 'no role'),
          h('div', { 'class': 'k' }, 'Produces'), h('div', null, produces(info)),
          h('div', { 'class': 'k' }, 'Settings'), h('div', null, (info['switch'] ? 'an on/off switch · ' : '') + settings),
          h('div', { 'class': 'k' }, 'Secrets'), h('div', null, (t.secrets || []).length ? t.secrets.map(function (s) { return s.env + (s.required ? ' (required)' : ''); }).join(', ') : 'none'),
          h('div', { 'class': 'k' }, 'Prompt text'), h('div', null, t.kind === 'geometry' ? 'none (no agent reads about it)'
            : t.owns.length + ' fields it owns (they leave with it) + its entry in the tool runner’s numbered list, place ' + t.list_order),
          h('div', { 'class': 'k' }, 'Code'), h('div', { 'class': 'mono', style: 'font-size:11px' }, t.file + '  ·  manifest dc_pack/tools/' + t.name + '/tool.yaml')
        ])
      ]));
    });
    (TE().removed || []).forEach(function (name) {
      add(wrap, h('div', { 'class': 'tcard gone' }, h('div', { 'class': 'head' }, [h('s', { 'class': 'n' }, name), h('span', { 'class': 'muted' }, ' · removed since the Studio opened'),
        h('span', { 'class': 'grow' }), h('button', { disabled: BUSY, onclick: function () { undoTool(name); } }, 'Undo')])));
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

  /* -- one tool --------------------------------------------------------------- */
  function renderToolEditor(center, right, name) {
    var st = toolState(name), m = st.manifest || {}, tab = R.q.tab || 'form';
    add(center, head('Tool · ' + (m.display_name || name), name + ' · ' + (m.kind || '?') + (st.opened ? '' : ' · added since the Studio opened'), [
      h('button', { onclick: function () { go('studio', 'tools', {}); } }, '← All tools'),
      h('span', { 'class': 'seg' }, TOOL_TABS.map(function (tb) {
        return h('button', { 'class': tb[0] === tab ? 'on' : '', onclick: function () { go('studio', 'tools', { tool: name, tab: tb[0] }); } }, tb[1]);
      }))]));
    var body = h('div', { 'class': 'teditor' });
    if (tab === 'yaml') add(body, fileEditor(name, 'tool.yaml', 28,
      'The whole manifest as text. A Save is checked by the engine first: a manifest it would refuse is not written.'));
    else if (tab === 'files') add(body, filesTab(name));
    else if (tab === 'texts') add(body, textsTab(name));
    else if (tab === 'test') add(body, testTab(name));
    else add(body, manifestForm(name));
    add(center, body);
    add(right, toolInspector(name));
  }
  function toolInspector(name) {
    var st = toolState(name), m = st.manifest || {};
    var changed = st.files.filter(function (f) { return f.changed && !f.prompts; });
    return h('div', { 'class': 'insp' }, [
      h('div', { 'class': 'title' }, name),
      h('div', { 'class': 'pills' }, [kpill(m.kind || '?'), st.changed ? pill(st.opened ? 'changed since opened' : 'added since opened', 'warn') : null]),
      m.kind !== 'geometry' ? h('div', { 'class': 'block' }, [h('h4', null, 'Called by'), h('p', null,
        (m.roles || []).map(function (r) { return roleLabel(r) + ': ' + rolesLine(r); }).join('; ') || 'no role')]) : null,
      h('div', { 'class': 'block' }, [h('h4', null, 'Changed since the Studio opened · ' + (changed.length + st.gone_files.length)),
        changed.length || st.gone_files.length ? h('ul', { 'class': 'checks' }, changed.map(function (f) {
          return h('li', null, ['•', h('span', { 'class': 'mono' }, f.path + (f.added ? '  (added)' : ''))]); }).concat(
          st.gone_files.map(function (f) { return h('li', null, ['•', h('s', { 'class': 'mono' }, f)]); })))
          : h('p', { 'class': 'muted' }, 'Nothing.'),
        h('p', { 'class': 'muted', style: 'font-size:11.5px;margin-top:4px' }, 'Its texts (prompts/) are text fields: their changes show in their own sections.')]),
      h('div', { 'class': 'block' }, [
        st.changed ? h('button', { disabled: BUSY, onclick: function () { undoTool(name); } }, 'Undo all changes to this tool') : null,
        ' ', h('button', { 'class': 'danger', disabled: BUSY, onclick: function () { askRemoveTool(name); } }, 'Remove this tool…')])
    ]);
  }

  /* -- the manifest form ------------------------------------------------------ */
  function manifestForm(name) {
    var st = toolState(name), m = manifestOf(name), key = 'tool|' + name;
    if (!m) return h('div', { 'class': 'banner bad boxed', style: 'margin:12px 16px' },
      'tool.yaml does not read as YAML (' + (st.manifest_error || '?') + '): fix it in the tool.yaml tab.');
    var saved = st.manifest, err = FIELD_ERRORS[key];
    function setv(path, value) {
      var w = clone(manifestOf(name));
      setPath(w, path, value);
      // no secret left: the key goes when the manifest as opened had none
      if (path[0] === 'secrets' && !(w.secrets || []).length && !('secrets' in (st.opened_manifest || {}))) delete w.secrets;
      TEDITS[name] = w;
      if (JSON.stringify(w) === JSON.stringify(saved)) delete TEDITS[name];
      delete FIELD_ERRORS[key];
      var a = el('toolActs');
      if (a) { a.innerHTML = ''; add(a, formActions(name)); }
      var u = el('unsavedCount');
      if (u) { u.innerHTML = ''; add(u, unsavedPill()); }
    }
    function field(label, path, kind, help) {
      var v = getPath(m, path), fk = key, ft = path.join('.');
      var input;
      if (kind === 'text') input = h('textarea', { rows: Math.max(3, Math.min(14, String(v || '').split('\n').length + 1)), spellcheck: 'false', 'data-fk': fk, 'data-t': ft,
        oninput: function (e) { setv(path, e.target.value); } }, v || '');
      else if (kind === 'bool') input = h('input', { type: 'checkbox', checked: !!v, 'data-fk': fk, 'data-t': ft, onchange: function (e) { setv(path, e.target.checked); } });
      else if (kind === 'int') input = h('input', { type: 'text', value: v === undefined ? '' : String(v), 'data-fk': fk, 'data-t': ft, style: 'width:90px',
        oninput: function (e) { var s = e.target.value.trim(); setv(path, /^-?\d+$/.test(s) ? parseInt(s, 10) : s); } });
      else input = h('input', { type: 'text', value: v || '', spellcheck: 'false', 'data-fk': fk, 'data-t': ft, oninput: function (e) { setv(path, e.target.value); } });
      return [h('div', { 'class': 'k' }, label), h('div', null, [input, help ? h('div', { 'class': 'muted hint' }, help) : null])];
    }
    var rows = [];
    rows = rows.concat([h('div', { 'class': 'k' }, 'Name'), h('div', { 'class': 'mono' }, name + '  (the folder’s name)'),
      h('div', { 'class': 'k' }, 'Kind'), h('div', null, m.kind)]);
    rows = rows.concat(field('Display name', ['display_name'], 'line', 'The flowchart’s and the log’s label.'));
    rows = rows.concat(field('Description', ['description'], 'text', 'What the LLM reads about the tool (its schema description).'));
    Object.keys(m.args || {}).forEach(function (a) { rows = rows.concat(field('Argument · ' + a, ['args', a], 'text')); });
    var parts = [h('div', { 'class': 'kv mform' }, rows)];
    if (m.kind !== 'geometry') {
      var roles = m.roles || [];
      parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'Roles that may call it'),
        h('div', { 'class': 'rolechecks' }, toolRoles().map(function (r) {
          var on = roles.indexOf(r.role) >= 0;
          return h('label', { 'class': 'vchk' }, [h('input', { type: 'checkbox', checked: on, 'data-fk': key, 'data-t': 'roles.' + r.role, onchange: function (e) {
            var cur = (manifestOf(name).roles || []).slice();
            if (e.target.checked && cur.indexOf(r.role) < 0) cur.push(r.role);
            if (!e.target.checked) cur = cur.filter(function (x) { return x !== r.role; });
            setv(['roles'], cur);
          } }), h('span', null, [h('b', null, r.label), h('span', { 'class': 'muted' }, ' · ' + rolesLine(r.role))])]);
        }))]));
    }
    if (m['switch']) {
      parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'On / off switch'), h('div', { 'class': 'kv mform' },
        field('On by default', ['switch', 'default'], 'bool').concat(field('Label', ['switch', 'label'], 'line'), field('Description', ['switch', 'description'], 'text')))]));
    }
    (m.settings || []).forEach(function (s, i) {
      var ctl;
      if (s.type === 'bool') ctl = field('Default', ['settings', i, 'default'], 'bool');
      else {
        var opts = s.type === 'tool' ? geometryTools().concat(s.none ? ['none'] : []) : (s.values || []);
        ctl = [h('div', { 'class': 'k' }, 'Default'), h('div', null, h('select', { 'data-fk': key, 'data-t': 'settings.' + i + '.default', onchange: function (e) { setv(['settings', i, 'default'], e.target.value); } },
          opts.map(function (o) { return h('option', { value: o, selected: o === s['default'] }, String(o)); })))];
      }
      parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'Setting · ' + s.name + ' (' + s.type + ')'), h('div', { 'class': 'kv mform' },
        ctl.concat(field('Label', ['settings', i, 'label'], 'line'), field('Description', ['settings', i, 'description'], 'text')))]));
    });
    ((m.outputs || {}).images || []).forEach(function (im, i) {
      parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'Picture · ' + im.view + ' (' + im.file + ')'), h('div', { 'class': 'kv mform' },
        field('Label', ['outputs', 'images', i, 'label'], 'line').concat(field('Order', ['outputs', 'images', i, 'order'], 'int'),
          field('On by default', ['outputs', 'images', i, 'default_enabled'], 'bool')))]));
    });
    if ((m.roles || []).indexOf('tool_runner') >= 0) {
      parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'Place in the tool runner’s list'),
        h('div', { 'class': 'kv mform' }, field('List order', ['list_order'], 'int', 'Tools are listed by this number, lowest first.'))]));
    }
    var secrets = m.secrets || [];
    parts.push(h('div', { 'class': 'block' }, [h('h4', null, 'Secrets · ' + secrets.length),
      h('p', { 'class': 'muted hint' }, 'The environment variables the tool reads: names only. Their values go into .env or the hosting provider, never into the setup.'),
      h('table', { 'class': 'ptab secrets' }, [h('thead', null, h('tr', null, ['Variable', 'Required', 'What it is', ''].map(function (x) { return h('th', null, x); }))),
        h('tbody', null, secrets.map(function (s, i) {
          return h('tr', null, [
            h('td', { style: 'width:220px' }, h('input', { type: 'text', value: s.env || '', 'data-fk': key, 'data-t': 'secrets.' + i + '.env', oninput: function (e) { setv(['secrets', i, 'env'], e.target.value); } })),
            h('td', { style: 'width:70px;text-align:center' }, h('input', { type: 'checkbox', checked: !!s.required, onchange: function (e) { setv(['secrets', i, 'required'], e.target.checked); } })),
            h('td', null, h('input', { type: 'text', value: s.description || '', 'data-fk': key, 'data-t': 'secrets.' + i + '.description', oninput: function (e) { setv(['secrets', i, 'description'], e.target.value); } })),
            h('td', { style: 'width:30px' }, h('button', { 'class': 'mini danger', onclick: function () {
              setv(['secrets'], (manifestOf(name).secrets || []).filter(function (x, j) { return j !== i; })); render(); } }, '×'))]);
        }))]),
      h('button', { 'class': 'mini', onclick: function () {
        setv(['secrets'], (manifestOf(name).secrets || []).concat([{ env: '', required: false, description: '' }])); render(); } }, '+ Add a secret')]));
    parts.push(h('p', { 'class': 'muted hint', style: 'margin:10px 0' }, 'Everything else (the code it runs, outputs, prompt slots, the fields revision 2 adds) is edited in the tool.yaml tab.'));
    if (err) parts.push(h('div', { 'class': 'banner bad boxed' }, [h('div', null, err.error)].concat(err.problems.map(function (p) { return h('div', null, '• ' + p); }))));
    parts.push(h('div', { 'class': 'tacts', id: 'toolActs' }, formActions(name)));
    return h('div', { 'class': 'mformwrap' }, parts);
  }
  function formActions(name) {
    if (!TEDITS[name]) return [h('span', { 'class': 'muted' }, 'No unsaved change.')];
    return [h('button', { 'class': 'primary', disabled: BUSY, onclick: function () {
        var desired = TEDITS[name];
        change('save_manifest', [name, desired, toolState(name).sha], 'tool|' + name, 'Saved ' + name + '’s manifest.', function () {
          if (JSON.stringify(TEDITS[name]) === JSON.stringify(desired)) delete TEDITS[name];
        });
      } }, 'Save'),
      h('button', { onclick: function () { delete TEDITS[name]; delete FIELD_ERRORS['tool|' + name]; render(); } }, 'Discard')];
  }

  /* -- files ------------------------------------------------------------------- */
  function loadFile(name, rel) {
    var key = name + '/' + rel;
    if (FILE_LOADING[key]) return;
    FILE_LOADING[key] = true;
    var gen = GEN;
    call('tool_file', name, rel).then(function (r) {
      delete FILE_LOADING[key];
      if (gen !== GEN) return;
      FILES[key] = r && r.ok ? r : { text: null, error: (r && r.error) || 'The file could not be read.' };
      if (R.section === 'tools' && R.q.tool === name) render();
    });
  }
  function fileEditor(name, rel, rows, intro) {
    var key = name + '/' + rel, f = FILES[key], st = toolState(name);
    var info = st.files.filter(function (x) { return x.path === rel; })[0];
    if (!f || (info && f.sha !== info.sha && !FEDITS[key])) { loadFile(name, rel); return h('div', { 'class': 'insp muted' }, 'Reading ' + rel + '…'); }
    if (f.error) return h('div', { 'class': 'banner bad boxed' }, f.error);
    var err = FIELD_ERRORS['file|' + key];
    var picker = h('input', { type: 'file', style: 'display:none', onchange: function (e) { uploadToolFile(name, rel, e.target.files[0], f.sha); e.target.value = ''; } });
    var head2 = h('div', { 'class': 'fhead' }, [h('span', { 'class': 'mono' }, rel), h('span', { 'class': 'muted' }, ' · ' + fmt(f.size) + ' bytes' + (f.eol ? ' · ' + f.eol : '')),
      info && info.changed ? pill(info.added ? 'added' : 'changed', 'warn') : null, h('span', { 'class': 'grow' }), picker,
      h('button', { 'class': 'mini', disabled: BUSY, onclick: function () { picker.click(); } }, 'Replace by upload…'),
      info && info.changed ? h('button', { 'class': 'mini', disabled: BUSY, title: info.added ? 'Remove this file, added since the Studio opened.' : 'Put this file back as it was when the Studio opened.',
        onclick: function () { delete FEDITS[key]; change('undo_tool_file', [name, rel], 'file|' + key, rel + ' is back as it was when the Studio opened.'); } }, 'Undo') : null]);
    if (f.text === null) return h('div', { 'class': 'fedit' }, [head2, h('p', { 'class': 'muted' }, 'Not a text file (or over 1 MB): it can only be replaced by upload.')]);
    var cur = FEDITS[key] !== undefined ? FEDITS[key] : f.text;
    var ta = h('textarea', { 'class': 'code', rows: rows || 22, spellcheck: 'false', 'data-fk': 'file|' + key, 'data-t': 'text',
      oninput: function (e) {
        if (e.target.value === f.text) delete FEDITS[key]; else FEDITS[key] = e.target.value;
        delete FIELD_ERRORS['file|' + key];
        var a = doc.querySelector('[data-facts="' + key + '"]');
        if (a) { a.innerHTML = ''; add(a, fileActions(name, rel)); }
        var u = el('unsavedCount');
        if (u) { u.innerHTML = ''; add(u, unsavedPill()); }
      } }, cur);
    return h('div', { 'class': 'fedit' }, [head2, intro ? h('p', { 'class': 'muted hint' }, intro) : null, ta,
      err ? h('div', { 'class': 'banner bad boxed' }, [h('div', null, err.error)].concat(err.problems.map(function (p) { return h('div', null, '• ' + p); }))) : null,
      h('div', { 'class': 'tacts', 'data-facts': key }, fileActions(name, rel))]);
  }
  function fileActions(name, rel) {
    var key = name + '/' + rel;
    if (FEDITS[key] === undefined) return [h('span', { 'class': 'muted' }, 'No unsaved change.')];
    return [h('button', { 'class': 'primary', disabled: BUSY, onclick: function () {
        var text = FEDITS[key];
        change('save_tool_file', [name, rel, text, FILES[key].sha], 'file|' + key, 'Saved ' + name + '/' + rel + '.', function () {
          if (FEDITS[key] === text) delete FEDITS[key];
        });
      } }, 'Save'),
      h('button', { onclick: function () { delete FEDITS[key]; delete FIELD_ERRORS['file|' + key]; render(); } }, 'Discard')];
  }
  function uploadToolFile(name, rel, file, base) {
    if (!file) return;
    var fr = new root.FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1] || '';
      delete FEDITS[name + '/' + rel];
      change('upload_tool_file', [name, rel, b64, base], 'file|' + name + '/' + rel,
        (base ? 'Replaced ' : 'Added ') + name + '/' + rel + ' (' + fmt(file.size) + ' bytes).');
    };
    fr.readAsDataURL(file);
  }
  function filesTab(name) {
    var st = toolState(name);
    var list = st.files.filter(function (f) { return !f.prompts && !f.entry && f.path !== 'tool.yaml'; });
    var sel = R.q.file && list.some(function (f) { return f.path === R.q.file; }) ? R.q.file : (list[0] || {}).path;
    var adder = h('input', { type: 'file', style: 'display:none', onchange: function (e) {
      var f = e.target.files[0]; e.target.value = '';
      if (f) uploadToolFile(name, f.name.replace(/[^A-Za-z0-9._-]+/g, '_'), f, null);
    } });
    var table = h('table', { 'class': 'ptab files' }, [h('thead', null, h('tr', null, ['File', 'Size', 'Kind', ''].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, list.map(function (f) {
        return h('tr', { 'class': f.path === sel ? 'sel' : '', style: 'cursor:pointer', onclick: function () { go('studio', 'tools', { tool: name, tab: 'files', file: f.path }); } }, [
          h('td', null, h('span', { 'class': 'mono' }, f.path)), h('td', { 'class': 'num' }, fmt(f.size)), h('td', null, f.text ? 'text' : 'binary'),
          h('td', null, f.changed ? pill(f.added ? 'added' : 'changed', 'warn') : null)]);
      }).concat(st.gone_files.filter(function (p) { return p.indexOf('prompts/') !== 0; }).map(function (p) {
        return h('tr', { 'class': 'gone' }, [h('td', null, h('s', { 'class': 'mono' }, p)), h('td', { colspan: 2 }, 'gone since the Studio opened'),
          h('td', null, h('button', { 'class': 'mini', disabled: BUSY, onclick: function (ev) { ev.stopPropagation(); change('undo_tool_file', [name, p], 'file|' + name + '/' + p, p + ' is back.'); } }, 'Undo'))]);
      })))]);
    return h('div', null, [h('div', { 'class': 'fhead' }, [h('span', { 'class': 'muted' }, list.length + ' files · nothing runs when a file is saved'), h('span', { 'class': 'grow' }), adder,
      h('button', { 'class': 'mini', disabled: BUSY, onclick: function () { adder.click(); } }, 'Add a file…')]), table,
      sel ? fileEditor(name, sel, 24) : null]);
  }
  function textsTab(name) {
    var st = toolState(name), m = st.manifest || {};
    var entries = st.files.filter(function (f) { return f.entry; });
    var owned = (m.prompt_slots || []).filter(function (s) { return slotByName(s); });
    return h('div', null, [
      h('div', { 'class': 'block', style: 'padding:0 16px' }, [h('h4', null, 'Its entry in the tool runner’s numbered tool list'),
        entries.length ? null : h('p', { 'class': 'muted' }, m.kind === 'geometry' ? 'None: no agent is given a geometry tool.' : 'None: only a tool the tool runner calls has one.')]),
    ].concat(entries.map(function (f) { return fileEditor(name, f.path, 6, 'Checked like a text field: no braces, only $names the engine knows, closed <<markers>>.'); }), [
      h('div', { 'class': 'block', style: 'padding:0 16px' }, [h('h4', null, 'The text fields it owns · ' + owned.length),
        h('p', { 'class': 'muted hint' }, 'They live in its prompts/ folder and leave with it; each is edited in its section, like every text field.'),
        h('div', null, owned.map(function (s) { var f = slotByName(s);
          return h('a', { 'class': 'kpill tool', style: 'display:inline-block;margin:2px;text-decoration:none', href: link('studio', f.section, { field: s }) }, s); }))])]));
  }

  /* -- New tool (P6c-2) ---------------------------------------------------------- */
  var NEW_KINDS = [
    ['helper', 'Helper', 'one function the tool runner calls with an attempt’s parameters.json; its answer is a text for the agent.'],
    ['generator', 'Generator', 'builds the model from an attempt’s parameters.json, then makes its pictures.'],
    ['geometry', 'Geometry tool', 'builds the model from the parameters, for a generator and the Download buttons; no agent calls it.']];
  function askNewTool() {
    if (BUSY) return;
    var tools = Object.keys(TE().tools), mode = 'template', kind = 'helper', src = tools[0];
    var nameIn = h('input', { type: 'text', spellcheck: 'false', placeholder: 'my_tool' });
    var dispIn = h('input', { type: 'text', placeholder: 'My tool' });
    var msg = h('div');
    var scadPicker = h('input', { type: 'file', accept: '.scad', style: 'display:none', onchange: function (e) {
      var f = e.target.files[0]; e.target.value = '';
      if (f) readScad(f, { name: nameIn.value.trim(), display: dispIn.value.trim() });
    } });
    function radio(value, label, disabled, extra) {
      return h('label', { 'class': 'pick' + (disabled ? ' off' : '') }, [
        h('input', { type: 'radio', name: 'newfrom', value: value, checked: value === mode, disabled: !!disabled,
          onchange: function () { mode = value; } }),
        h('span', null, [h('b', null, label)].concat(extra || []))]);
    }
    var body = h('div', null, [
      h('div', { 'class': 'kv mform' }, [
        h('div', { 'class': 'k' }, 'Name'), h('div', null, [nameIn, h('div', { 'class': 'muted hint' }, 'Lower case: letters, digits and _. It is the folder’s name and the agents’ tool name.')]),
        h('div', { 'class': 'k' }, 'Display name'), h('div', null, [dispIn, h('div', { 'class': 'muted hint' }, 'The flowchart’s and the log’s label.')])]),
      h('h4', { style: 'margin:12px 0 6px' }, 'Start from'),
      radio('template', 'A template', false, [h('div', null, h('select', { onchange: function (e) { kind = e.target.value; } },
        NEW_KINDS.map(function (k) { return h('option', { value: k[0] }, k[1]); }))),
        h('div', { 'class': 'muted hint' }, NEW_KINDS.map(function (k) { return k[1] + ': ' + k[2]; }).join(' '))]),
      radio('copy', 'A copy of a tool', !tools.length, [h('div', null, h('select', { onchange: function (e) { src = e.target.value; } },
        tools.map(function (t) { return h('option', { value: t }, t); }))),
        h('div', { 'class': 'muted hint' }, 'Its manifest and code under the new name. Its texts stay with the original, its pictures and model file get names of their own, a helper’s function is renamed after the copy.')]),
      radio('adapter', 'An adapter (a Grasshopper definition on a compute server, a Node script, an HTTP endpoint)', true, [h('div', { 'class': 'muted hint' }, 'Not yet: a later step (TODO F124).')]),
      radio('cad', 'A CAD file (an OpenSCAD model, .scad)', false, [h('div', { 'class': 'muted hint' }, 'Choose the file next: the Studio reads its settings and shows what each one becomes, and how to import it, before anything is written.  You can also drop a .scad file on the Tools page.')]),
      msg, scadPicker]);
    showModal('New tool', body, [h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'primary', onclick: function () {
        var name = nameIn.value.trim();
        if (mode === 'cad') { scadPicker.click(); return; }
        msg.innerHTML = '';
        add(msg, h('p', { 'class': 'muted' }, 'Checking with the engine…'));
        call('new_tool', name, dispIn.value, mode === 'template' ? kind : null, mode === 'copy' ? src : null).then(function (r) {
          msg.innerHTML = '';
          if (!r || r.ok === false) {
            add(msg, h('div', { 'class': 'banner bad boxed' }, [h('div', null, (r && r.error) || 'The tool could not be made.')].concat(
              ((r && r.problems) || []).map(function (p) { return h('div', null, '• ' + p); }))));
            return;
          }
          closeModal();
          BUSY = true;
          status('Made ' + name + '. Re-assembling every prompt…', 'busy');
          root.history.replaceState(null, '', link('studio', 'tools', { tool: name }));
          reload().then(function () {
            BUSY = false;
            status('Made ' + name + '.' + ((r.warnings || []).length ? '  ' + r.warnings.join(' ') : ''), (r.warnings || []).length ? 'warn' : 'ok');
            render();
          }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
        });
      } }, 'Make the tool')]);
  }

  /* -- A tool from an OpenSCAD model (P6f) ---------------------------------------
   * A .scad file dropped on the Tools page (or picked: Import a .scad file, or
   * New tool › A CAD file) is read by the server (scad_read: the settings its
   * Customizer shows, and what each is proposed as); the dialog shows them by
   * tab with the way to import it -- a new configurator, or one more tool --
   * and scad_import makes it (studio/scad_import.py).  Undo the import
   * (scad_undo) puts back every file it touched. */
  var SCAD = null;              // the import being prepared
  var IMPORT_WARNINGS = null;   // the last import's warnings, for its banner
  var PICK_WORDS = { parameter: 'Parameter', detail: 'Detail', model: 'Left to the model' };
  var PICK_ALL = { parameter: 'All: parameters', detail: 'All: detail', model: 'All: left to the model' };
  // The rows with the owner's picks laid over (the server's apply_picks, for
  // what the dialog shows): each row's pick, its "only when" while it and the
  // choice it names are parameters (on unless unticked), and the counts.
  function scadView(rows, picks, when) {
    var pickOf = {};
    rows.forEach(function (r) { pickOf[r.setting] = picks[r.setting] || r.pick; });
    var out = rows.map(function (r) {
      var ctrl = r.when ? Object.keys(r.when)[0] : null;
      var live = !!ctrl && pickOf[r.setting] === 'parameter' && pickOf[ctrl] === 'parameter';
      return { row: r, pick: pickOf[r.setting], whenLive: live, whenOn: live && when[r.setting] !== false };
    });
    var made = [], when = 0;
    out.forEach(function (v) {
      if (v.pick !== 'parameter') return;
      made = made.concat(v.row.parameters);
      if (v.whenOn) when += v.row.parameters.length;
    });
    return { rows: out, parameters: made.length, names: made.map(function (p) { return p.name; }),
             proposed: made.filter(function (p) { return p.range === 'proposed'; }).length, when: when };
  }
  // A pick for one row, or for every row of a tab that can take it (only the
  // picks that differ from the proposal are kept).
  function scadSetPick(picks, rows, pick) {
    rows.forEach(function (r) {
      if (r.picks.indexOf(pick) < 0) return;
      if (r.pick === pick) delete picks[r.setting]; else picks[r.setting] = pick;
    });
  }
  function andList(xs) { return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]; }
  function importDid(s) {
    return (s.mode === 'new' ? 'as a new configurator: added ' + andList(s.added) +
      (s.removed.length ? '; removed ' + andList(s.removed) : '') + '; ' + s.parameters + ' parameters'
      : 'as one more tool: added ' + andList(s.added) + ' and its ' + s.parameters + ' parameters') + '.';
  }
  function scadShown(v) { return typeof v === 'string' || v instanceof Array ? JSON.stringify(v) : String(v); }
  function scadParamText(p) {
    if (p.type === 'choice') return p.name + ' · choice (' + p.choices.length + ')';
    if (p.type === 'bool') return p.name + ' · on/off';
    return p.name + ' · ' + p.type + ' [' + p.min + '; ' + p.max + ']';
  }
  function scadWhenText(when) {
    return 'only when ' + Object.keys(when).map(function (k) { return k + ' = ' + String(when[k]); }).join(', and ');
  }
  function hasFiles(e) { return !!e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0; }
  function scadDrop() {
    var picker = h('input', { type: 'file', accept: '.scad', style: 'display:none', onchange: function (e) {
      var f = e.target.files[0]; e.target.value = '';
      if (f) readScad(f);
    } });
    return h('div', { 'class': 'dropzone slim', id: 'scadDrop' }, [picker,
      h('span', null, ['Drop an OpenSCAD model (', h('b', null, '.scad'), ') here to import it as a tool, or']),
      h('button', { disabled: BUSY, onclick: function () { picker.click(); } }, 'Import a .scad file…')]);
  }
  // A file dragged over the Tools page lights the drop area; dropped there, it is read.
  function scadDragTarget(center) {
    function zone(on) { var z = el('scadDrop'); if (z) z.classList.toggle('over', on); }
    center.addEventListener('dragover', function (e) { if (!hasFiles(e)) return; e.preventDefault(); zone(true); });
    center.addEventListener('dragleave', function (e) { if (!center.contains(e.relatedTarget)) zone(false); });
    center.addEventListener('drop', function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      zone(false);
      if (e.dataTransfer.files.length) readScad(e.dataTransfer.files[0]);
    });
  }
  function readScad(file, preset) {
    if (!file) return;
    if (BUSY) { status('Wait for the change being written, then drop the file again.', 'warn'); return; }
    if (!/\.scad$/i.test(file.name)) { status(file.name + ' is not an OpenSCAD model: import a .scad file.', 'err'); return; }
    status('Reading ' + file.name + '…', 'busy');
    var fr = new root.FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1] || '';
      call('scad_read', b64, file.name).then(function (r) {
        if (!r || r.ok === false) {
          status((r && r.error) || 'The file could not be read.', 'err');
          showModal('The model cannot be imported', h('div', null, [h('p', { style: 'margin:0 0 8px' }, (r && r.error) || '')].concat(
            ((r && r.problems) || []).map(function (p) { return h('div', { 'class': 'probline' }, '✗ ' + p); }))),
            [h('button', { onclick: closeModal }, 'Close')]);
          return;
        }
        status('Read ' + file.name + ': ' + r.counts.settings + ' settings.', 'ok');
        SCAD = { file: file.name, b64: b64, found: r, mode: null, picks: {}, when: {}, open: {}, error: null,
                 name: (preset && preset.name) || r.name, display: (preset && preset.display) || r.display };
        SCAD.open[r.groups[0]] = true;
        showModal('Import ' + file.name, h('div'), []);
        el('modalBox').className = 'modal xwide';
        drawScad();
      }, function (e) { status(String(e && e.message ? e.message : e), 'err'); });
    };
    fr.readAsDataURL(file);
  }
  function drawScad() {
    var S = SCAD;
    if (!S) return;
    var f = S.found, su = f.setup, v = scadView(f.rows, S.picks, S.when);
    var gone = su.generators.concat(su.geometry);
    var clash = S.mode === 'add' ? v.names.filter(function (n) { return su.parameters.indexOf(n) >= 0; }) : [];
    var unsaved = Object.keys(PEDITS).length + Object.keys(GEDITS).length + Object.keys(TEDITS).length + Object.keys(FEDITS).length;
    function radio(mode, label, hint) {
      return h('label', { 'class': 'pick' }, [h('input', { type: 'radio', name: 'scadmode', checked: S.mode === mode,
        onchange: function () { S.mode = mode; drawScad(); } }), h('span', null, [h('b', null, label), h('div', { 'class': 'muted hint' }, hint)])]);
    }
    var body = h('div', { 'class': 'scad' }, [
      S.error,
      h('p', { 'class': 'scadsum' }, [h('b', null, f.model), ' · ' + f.counts.settings + ' settings in ' + f.groups.length + ' tabs → ' +
        v.parameters + ' parameters, ' + v.proposed + ' of them with a proposed range, ' + v.when + ' used only when a choice has a value.']),
      f.notes.length || f.includes.length ? h('div', { 'class': 'banner warn boxed' }, (f.includes.length ? [h('div', null,
        'The model uses other files (' + f.includes.join(', ') + '): only the model file is copied; add them to the tool’s folder afterwards (Files).')] : [])
        .concat(f.notes.map(function (n) { return h('div', null, n); }))) : null,
      h('h4', null, 'How to import it'),
      radio('new', 'Start a new configurator', 'The model becomes the setup’s generator and its geometry tool for the Download buttons, each with a copy of the file.  Its parameters replace today’s ' +
        su.parameters.length + ', the agents’ parameter lists are written new, and the picture samples become one, the defaults.' +
        (gone.length ? '  These tools go: ' + gone.join(', ') + '.' : '') + (su.helpers.length ? '  These stay: ' + su.helpers.join(', ') + '.' : '') +
        '  The texts stay as they are, for you to adapt.'),
      radio('add', 'Add it as one more tool', (su.add_as === 'generator' ? 'It becomes the setup’s generator (the setup has none).'
        : 'It becomes a geometry tool beside ' + su.generators.join(', ') + ': a generator’s geometry tool setting, or the Download buttons, can use it.') +
        '  Its parameters join today’s ' + su.parameters.length + ', the agents’ lists and the picture samples get them too.'),
      clash.length ? h('div', { 'class': 'banner bad boxed' }, 'The setup has parameters of these names already: ' + clash.join(', ') +
        '.  Leave those settings to the model, or start a new configurator.') : null,
      unsaved ? h('div', { 'class': 'banner warn boxed' }, 'Your ' + unsaved + ' unsaved change(s) to parameters, groups and tools are dropped.') : null,
      h('div', { 'class': 'kv mform', style: 'margin-top:10px' }, [
        h('div', { 'class': 'k' }, 'Tool name'), h('div', null, [h('input', { type: 'text', value: S.name, spellcheck: 'false',
          oninput: function (e) { S.name = e.target.value; } }),
          h('div', { 'class': 'muted hint' }, 'Lower case: letters, digits and _.  A new configurator also makes <name>_geometry.')]),
        h('div', { 'class': 'k' }, 'Display name'), h('div', null, h('input', { type: 'text', value: S.display,
          oninput: function (e) { S.display = e.target.value; } }))]),
      h('h4', null, 'The model’s settings'),
      h('p', { 'class': 'muted hint' }, 'Each setting becomes a parameter the agents set, the model’s detail (its own for the Download buttons, coarser for the agents’ runs), or is left to the model (its own value).  A range in amber was proposed from the model’s default: review it under Parameters after the import.'),
      h('div', { 'class': 'scadfold' }, [
        h('button', { 'class': 'mini', onclick: function () { f.groups.forEach(function (g) { S.open[g] = true; }); drawScad(); } }, 'Unfold every tab'),
        h('button', { 'class': 'mini', onclick: function () { S.open = {}; drawScad(); } }, 'Fold every tab')]),
      scadTable(v)]);
    var b = el('modalBody'), top = b.scrollTop;
    b.innerHTML = '';
    b.appendChild(body);
    b.scrollTop = top;
    var why = !S.mode ? 'Choose how to import it first.' : !v.parameters ? 'Pick at least one setting as a parameter.'
      : clash.length ? 'Some parameter names exist already (see above).' : null;
    var foot = el('modalFoot');
    foot.innerHTML = '';
    add(foot, [h('button', { onclick: function () { SCAD = null; closeModal(); } }, 'Cancel'),
      h('button', { 'class': 'primary', disabled: !!why || BUSY, title: why, onclick: runScad },
        S.mode === 'new' ? 'Start the new configurator' : 'Import')]);
  }
  function scadTable(v) {
    var tabs = [], by = {};
    v.rows.forEach(function (x) {
      var g = x.row.group;
      if (!by[g]) { by[g] = []; tabs.push(g); }
      by[g].push(x);
    });
    var tb = h('tbody');
    tabs.forEach(function (g) {
      var xs = by[g], open = !!SCAD.open[g];
      var n = xs.reduce(function (a, x) { return a + (x.pick === 'parameter' ? x.row.parameters.length : 0); }, 0);
      var picks = ['parameter', 'detail', 'model'].filter(function (p) { return xs.some(function (x) { return x.row.picks.indexOf(p) >= 0; }); });
      add(tb, h('tr', { 'class': 'grp', style: 'cursor:pointer', onclick: function () { SCAD.open[g] = !open; drawScad(); } },
        h('td', { colspan: 5 }, h('div', { 'class': 'scadg' }, [h('span', null, (open ? '▾ ' : '▸ ')), h('b', null, g),
          h('span', { 'class': 'muted' }, xs.length + (xs.length === 1 ? ' setting · ' : ' settings · ') + n + (n === 1 ? ' parameter' : ' parameters')),
          h('span', { 'class': 'grow' }),
          picks.length > 1 ? h('select', { onclick: function (e) { e.stopPropagation(); }, onchange: function (e) {
            if (e.target.value) { scadSetPick(SCAD.picks, xs.map(function (x) { return x.row; }), e.target.value); drawScad(); } } },
            [h('option', { value: '' }, 'All: …')].concat(picks.map(function (p) { return h('option', { value: p }, PICK_ALL[p]); }))) : null]))));
      if (open) xs.forEach(function (x) { add(tb, scadRow(x)); });
    });
    return h('table', { 'class': 'ptab scadtab' }, [h('thead', null, h('tr', null, ['Setting', 'Default', 'Becomes', 'Parameters', 'Only when']
      .map(function (x) { return h('th', null, x); }))), tb]);
  }
  function scadRow(x) {
    var r = x.row;
    var made = x.pick === 'parameter' ? r.parameters.map(function (p) {
      return h('div', { 'class': p.range === 'proposed' ? 'proposed' : null, title: p.range === 'proposed' ? 'A proposed range: review it under Parameters after the import.' : null },
        scadParamText(p));
    }) : h('span', { 'class': 'muted' }, x.pick === 'detail' ? 'the model’s detail: ' + scadShown(r['default']) + ' for downloads, coarser for the agents’ runs' : '—');
    return h('tr', { 'class': x.pick === 'parameter' ? null : 'off' }, [
      h('td', null, [h('div', { 'class': 'mono' }, r.setting), h('div', { 'class': 'muted' }, [r.kind, r.control].filter(function (s) { return s; }).join(' · ')),
        r.description ? h('div', { 'class': 'muted' }, r.description) : null, r.note ? h('div', { 'class': 'warn' }, r.note) : null]),
      h('td', { 'class': 'mono' }, scadShown(r['default'])),
      h('td', null, r.picks.length > 1 ? h('select', { onchange: function (e) { scadSetPick(SCAD.picks, [r], e.target.value); drawScad(); } },
        r.picks.map(function (p) { return h('option', { value: p, selected: p === x.pick }, PICK_WORDS[p]); })) : h('span', { 'class': 'muted' }, PICK_WORDS[r.picks[0]])),
      h('td', null, made),
      h('td', null, x.whenLive ? h('label', null, [h('input', { type: 'checkbox', checked: x.whenOn, onchange: function (e) {
        if (e.target.checked) delete SCAD.when[r.setting]; else SCAD.when[r.setting] = false;
        drawScad(); } }), ' ' + scadWhenText(r.when)]) : null)]);
  }
  function runScad() {
    var S = SCAD;
    if (!S || !S.mode || BUSY) return;
    var when = {};
    Object.keys(S.when).forEach(function (k) { when[k] = false; });
    S.error = h('p', { 'class': 'muted' }, 'Checking it with the engine…');
    BUSY = true;
    drawScad();
    status('Importing ' + S.file + '…', 'busy');
    call('scad_import', S.b64, S.file, S.mode, S.picks, when, S.name.trim(), S.display.trim()).then(function (r) {
      if (!r || r.ok === false) {
        BUSY = false;
        S.error = h('div', { 'class': 'banner bad boxed' }, [h('div', null, (r && r.error) || 'The model could not be imported.')].concat(
          ((r && r.problems) || []).map(function (p) { return h('div', null, '• ' + p); })));
        status((r && r.error) || 'The import failed.', 'err');
        drawScad();
        el('modalBody').scrollTop = 0;
        return;
      }
      SCAD = null;
      closeModal();
      PEDITS = {}; GEDITS = {}; TEDITS = {}; FEDITS = {}; TESTS = {};
      IMPORT_WARNINGS = r.warnings || [];
      var done = 'Imported ' + S.file + ' ' + importDid(r);
      status(done + ' Re-assembling every prompt…', 'busy');
      root.history.replaceState(null, '', link('studio', 'tools', {}));
      parse();
      reload().then(function () {
        BUSY = false;
        status(done + (IMPORT_WARNINGS.length ? '  See its notes above the tools.' : ''), IMPORT_WARNINGS.length ? 'warn' : 'ok');
        render();
      }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
    }, function (e) { BUSY = false; S.error = null; status(String(e && e.message ? e.message : e), 'err'); drawScad(); });
  }
  // While an import can be undone: what it did, and its Undo.
  function importBanner() {
    var s = D.scad_import;
    if (!s) return null;
    return h('div', { 'class': 'banner warn boxed importban' }, [
      h('div', { 'class': 'row' }, [h('div', { 'class': 'grow' }, [h('b', null, 'Imported ' + s.model), ' ' + importDid(s) +
        '  Undo the import puts back every file it touched.']),
        h('button', { disabled: BUSY, onclick: function () { undoImport(false); } }, 'Undo the import')]),
      (IMPORT_WARNINGS || []).length ? h('ul', { 'class': 'checks warn' }, IMPORT_WARNINGS.map(function (w) {
        return h('li', null, ['!', h('span', null, w)]); })) : null]);
  }
  function undoImport(force) {
    if (BUSY) return;
    BUSY = true;
    status('Undoing the import…', 'busy');
    render();
    call('scad_undo', force === true).then(function (r) {
      if (!r || r.ok === false) {
        BUSY = false;
        status((r && r.error) || 'The import could not be undone.', 'err');
        render();
        if (r && (r.problems || []).length) {
          showModal('Undo the import', h('div', null, [h('p', { style: 'margin:0 0 8px' }, r.error)].concat(
            r.problems.map(function (p) { return h('div', { 'class': 'probline' }, '• ' + p); }))), [
            h('button', { onclick: closeModal }, 'Cancel'),
            h('button', { 'class': 'danger', onclick: function () { closeModal(); undoImport(true); } }, 'Undo anyway')]);
        }
        return;
      }
      PEDITS = {}; GEDITS = {}; TEDITS = {}; FEDITS = {}; TESTS = {};
      IMPORT_WARNINGS = null;
      var done = 'Undid the import of ' + r.undone.model + ': every file it touched is back as it was.';
      status(done + ' Re-assembling every prompt…', 'busy');
      reload().then(function () { BUSY = false; status(done, 'ok'); render(); },
        function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
    }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
  }

  /* -- Test tool (P6c-2) --------------------------------------------------------- */
  var TESTS = {};     // tool -> {source, values, settings, report, running}
  function testValues(source) {
    if (source === 'defaults') {
      var out = {};
      PE().spec.parameters.forEach(function (p) { out[p.name] = p['default']; });
      return out;
    }
    return clone((TE().samples || {})[source] || {});
  }
  function testTab(name) {
    var st = toolState(name), m = st.manifest || {};
    var T = TESTS[name] || (TESTS[name] = { source: 'defaults', values: null, settings: {}, report: null, running: false });
    if (!T.values) T.values = testValues(T.source);
    var sources = ['defaults'].concat(Object.keys(TE().samples || {}));
    var srcSel = h('select', { onchange: function (e) {
      T.source = e.target.value;
      if (T.source !== 'typed') T.values = testValues(T.source);
      render();
    } }, sources.map(function (s) { return h('option', { value: s, selected: s === T.source }, s === 'defaults' ? 'the parameters’ defaults' : 'sample: ' + s); })
      .concat([h('option', { value: 'typed', selected: T.source === 'typed' }, 'typed values')]));
    var table = h('table', { 'class': 'ptab tvals' }, [h('thead', null, h('tr', null, ['Parameter', 'Value'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, PE().spec.parameters.map(function (p) {
        return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, p.name)),
          h('td', { 'class': 'num' }, h('input', { type: 'text', value: T.values[p.name] === undefined ? '' : String(T.values[p.name]),
            oninput: function (e) { T.values[p.name] = parseNum(e.target.value); T.source = 'typed'; srcSel.value = 'typed'; } }))]);
      }))]);
    var settings = (m.settings || []).map(function (s) {
      var v = T.settings[s.name] !== undefined ? T.settings[s.name] : s['default'];
      function set(val) { if (val === s['default']) delete T.settings[s.name]; else T.settings[s.name] = val; render(); }
      var ctl = s.type === 'bool'
        ? h('span', { 'class': 'seg' }, [h('button', { 'class': v ? 'on' : '', onclick: function () { set(true); } }, 'on'),
            h('button', { 'class': v ? '' : 'on', onclick: function () { set(false); } }, 'off')])
        : h('select', { onchange: function (e) { set(e.target.value); } },
            (s.type === 'tool' ? geometryTools().concat(s.none ? ['none'] : []) : (s.values || [])).map(function (o) {
              return h('option', { value: o, selected: o === v }, String(o)); }));
      return [h('div', { 'class': 'k' }, s.label || s.name), h('div', null, [ctl, T.settings[s.name] !== undefined ? pill('changed for this run', 'warn') : null])];
    });
    var parts = [
      h('p', { 'class': 'muted hint' }, 'Runs the tool the way the system calls it — ' + (m.kind === 'geometry' ? 'as the engine builds a model' : 'as the tool runner calls it, with an attempt’s parameters.json') +
        ' — in a process of its own, on a throw-away attempt folder. Nothing in the setup changes. It stops after 180 s.'),
      h('div', { 'class': 'kv mform' }, [h('div', { 'class': 'k' }, 'Parameter values'), h('div', null, srcSel)]),
      h('details', { 'class': 'vtool' }, [h('summary', null, 'The values (' + Object.keys(T.values).length + ')'), table]),
      settings.length ? h('div', { 'class': 'block' }, [h('h4', null, 'Its settings for this run'), h('div', { 'class': 'kv mform' }, [].concat.apply([], settings))]) : null,
      h('div', { 'class': 'tacts' }, [h('button', { 'class': 'primary', disabled: T.running, onclick: function () { runTest(name); } }, T.running ? 'Running…' : 'Run the test'),
        T.report ? h('span', { 'class': 'muted' }, 'The last run is shown below.') : null])];
    if (T.report) parts.push(testReport(T.report));
    return h('div', { 'class': 'mformwrap' }, parts);
  }
  function runTest(name) {
    var T = TESTS[name];
    if (!T || T.running) return;
    T.running = true;
    status('Running ' + name + '…', 'busy');
    render();
    call('test_tool', name, T.values, T.settings).then(function (r) {
      T.running = false;
      T.report = r && r.ok ? r.report : { failed: true, error: (r && r.error) || 'The run could not start.', pictures: [], files: [], mismatches: [], output: [] };
      status(T.report.failed ? name + ': the run failed (see the report).' : name + ' ran in ' + T.report.seconds + ' s.', T.report.failed ? 'err' : 'ok');
      if (R.section === 'tools' && R.q.tool === name) render();
    }, function (e) { T.running = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
  }
  function testReport(rep) {
    var pics = rep.pictures || [], files = rep.files || [], mism = rep.mismatches || [], out = rep.output || [];
    return h('div', { 'class': 'treport' }, [
      h('div', { 'class': 'pills' }, [rep.failed ? pill('failed', 'bad') : pill('ran', 'good'),
        rep.seconds !== null && rep.seconds !== undefined ? kpill(rep.seconds + ' s') : null,
        mism.length ? pill(mism.length + (mism.length === 1 ? ' mismatch' : ' mismatches'), 'warn') : null]),
      rep.answer ? h('div', { 'class': 'block' }, [h('h4', null, rep.kind === 'geometry' ? 'What it made' : 'What the agent gets'), h('pre', { 'class': 'log' }, rep.answer)]) : null,
      rep.error ? h('div', { 'class': 'block' }, [h('h4', null, 'Error'), h('pre', { 'class': 'log err' }, rep.error)]) : null,
      mism.length ? h('div', { 'class': 'block' }, [h('h4', null, 'Mismatches with the manifest · ' + mism.length),
        h('ul', { 'class': 'checks warn' }, mism.map(function (x) { return h('li', null, ['!', h('span', null, x)]); }))]) : null,
      pics.length ? h('div', { 'class': 'block' }, [h('h4', null, 'Pictures · ' + pics.length), h('div', { 'class': 'tpics' }, pics.map(function (p) {
        return h('figure', null, [p.png ? h('img', { src: 'data:image/png;base64,' + p.png, alt: p.label }) : h('div', { 'class': 'muted' }, 'too large to show'),
          h('figcaption', null, (p.declared ? '' : 'not declared · ') + p.file + (p.width ? ' · ' + p.width + '×' + p.height : '') + ' · ' + fmt(p.bytes) + ' bytes')]);
      }))]) : null,
      rep.model ? h('div', { 'class': 'block' }, [h('h4', null, 'Model'), h('p', { 'class': 'mono' },
        rep.model.file + ' · ' + fmt(rep.model.bytes) + ' bytes' + (rep.model.vertices !== null ? ' · ' + fmt(rep.model.vertices) + ' vertices' : ''))]) : null,
      files.length ? h('div', { 'class': 'block' }, [h('h4', null, 'Files it wrote · ' + files.length),
        h('p', { 'class': 'mono', style: 'font-size:11px' }, files.map(function (f) { return f.file + ' (' + fmt(f.bytes) + ')'; }).join(', '))]) : null,
      rep.settings ? h('div', { 'class': 'block' }, [h('h4', null, 'Its settings in this run'),
        h('p', { 'class': 'mono', style: 'font-size:11px' }, Object.keys(rep.settings).map(function (k) { return k + ' = ' + rep.settings[k]; }).join(' · '))]) : null,
      h('details', { 'class': 'vtool' }, [h('summary', null, 'Its own output · ' + out.length + ' lines' + (rep.output_cut ? ' (the first ' + rep.output_cut + ' cut)' : '')),
        h('pre', { 'class': 'log' }, out.join('\n') || '(nothing)')])
    ]);
  }

  /* -- the whole tool -------------------------------------------------------- */
  function undoTool(name) {
    Object.keys(FEDITS).forEach(function (k) { if (k.indexOf(name + '/') === 0) delete FEDITS[k]; });
    delete TEDITS[name];
    var st = toolState(name);
    change('undo_tool', [name], 'tool|' + name, st && !st.opened ? 'Removed ' + name + ', made since the Studio opened.'
      : name + ' is back as it was when the Studio opened.');
  }
  function askRemoveTool(name) {
    if (BUSY) return;
    status('Checking what refers to ' + name + '…', 'busy');
    call('remove_tool_preview', name).then(function (r) {
      status('', '');
      if (!r || r.ok === false) { status((r && r.error) || 'The check failed.', 'err'); return; }
      var stop = r.blockers.concat(r.problems);
      var body = h('div', { 'class': 'pprev' }, [
        stop.length ? h('div', { 'class': 'banner bad boxed' }, [h('b', null, 'It cannot be removed yet:')].concat(stop.map(function (p) { return h('div', null, '• ' + p); }))) : null,
        r.warnings.length ? h('div', { 'class': 'banner warn boxed' }, r.warnings.map(function (p) { return h('div', null, '• ' + p); })) : null,
        h('h4', null, 'Its texts leave with it · ' + r.texts.length),
        h('p', { 'class': 'mono', style: 'font-size:11px;line-height:1.5' }, r.texts.join(', ') || 'none'),
        r.marked.length ? h('h4', null, 'Texts with a part about it, read as switched off from now on · ' + r.marked.length) : null,
        r.marked.length ? h('p', { 'class': 'mono', style: 'font-size:11px;line-height:1.5' }, r.marked.join(', ')) : null,
        h('p', { 'class': 'muted', style: 'margin-top:8px' }, 'Undo puts the whole folder back as it was when the Studio opened. The Prompt viewer’s “Changes since opened” shows what the agents lose.')]);
      showModal('Remove ' + name, body, [h('button', { onclick: closeModal }, 'Cancel'),
        h('button', { 'class': 'danger', disabled: stop.length > 0, onclick: function () {
          closeModal();
          root.history.replaceState(null, '', link('studio', 'tools', {}));
          change('remove_tool', [name], 'tool|' + name, 'Removed ' + name + '.');
        } }, 'Remove')]);
    });
  }

  /* ======================================================================
   * Agent access
   * ==================================================================== */
  function renderAccess(center, right) {
    var PA = D.parameter_access, opened = PE().access_opened || {};
    add(center, head('Agent access', 'Who sees the parameter list, and how: one choice per agent and topology (a cell exists only where the agent does). Click a choice to save it: this is the setup’s default (pack.yaml); Workflow Settings can still change it for the next session.'));
    var t = h('table', { 'class': 'ptab', style: 'margin:10px 16px;width:calc(100% - 32px)' }, h('thead', null, h('tr', null,
      ['Agent', '3-agent', '5-agent', '7-agent', ''].map(function (x) { return h('th', null, x); }))));
    var tb = h('tbody');
    PA.rows.forEach(function (r) {
      var then = opened[r.agent] || {};
      var rowChanged = Object.keys(r.cells).some(function (k) { return then[k] !== r.cells[k]; });
      add(tb, h('tr', null, [h('td', null, [h('b', null, r.name), h('div', { 'class': 'muted mono', style: 'font-size:10.5px' }, r.agent)])].concat(
        ['3', '5', '7'].map(function (k) {
          var st = r.cells[k];
          if (!st) return h('td', null, h('span', { 'class': 'na' }, '—'));
          var chg = then[k] !== undefined && then[k] !== st;
          return h('td', { 'class': chg ? 'chg' : null, title: chg ? 'Was “' + then[k] + '” when the Studio opened.' : null },
            h('span', { 'class': 'seg' }, PA.states.filter(function (o) {
              return !(o.id === 'tool' && PA.no_tool.indexOf(r.agent) >= 0); }).map(function (o) {
              return h('button', { 'class': o.id === st ? 'on' : '', disabled: BUSY, title: o.label, onclick: function () {
                if (o.id === st) return;
                change('set_access', [r.agent, k, o.id, PE().pack_yaml_sha], 'access',
                  r.name + ', ' + k + '-agent: ' + o.label.toLowerCase() + ' (saved to pack.yaml).');
              } }, o.short); })));
        }), [h('td', { 'class': 'racts' }, rowChanged ? h('button', { 'class': 'mini', disabled: BUSY, title: 'Put this row back as it was when the Studio opened.',
          onclick: function () { change('undo_access', [r.agent], 'access', r.name + '’s row is back as it was when the Studio opened.'); } }, 'Undo') : null)])));
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
      h('div', { 'class': 'block' }, [h('h4', null, 'See the effect'), h('p', null, 'The Prompt viewer’s “Changes since opened” shows each agent’s prompt against the setup as the Studio opened it.')]),
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
    var S = D.settings, rows = [];
    add(center, head('Settings & secrets', 'Default values of the tools’ own settings, saved into each tool’s tool.yaml (users change them later in Workflow Settings), and the secrets your setup will need.'));
    Object.keys(TE().tools).forEach(function (name) {
      var st = toolState(name), m = st.manifest;
      if (!m) return;
      var om = st.opened_manifest || {}, items = [];
      if (m['switch']) items.push({ path: ['switch', 'default'], name: 'enabled', label: (m['switch'].label || 'On / off') + ' — the tool itself',
        type: 'bool', value: m['switch']['default'], opened: getPath(om, ['switch', 'default']) });
      (m.settings || []).forEach(function (s, i) {
        var o = (om.settings || [])[i];
        items.push({ path: ['settings', i, 'default'], name: s.name, label: s.label || s.name, type: s.type, value: s['default'],
          values: s.type === 'tool' ? geometryTools().concat(s.none ? ['none'] : []) : (s.values || []),
          opened: o && o.name === s.name ? o['default'] : undefined });
      });
      if (!items.length) return;
      rows.push(h('tr', { 'class': 'grp' }, h('td', { colspan: 4 }, (m.display_name || name) + ' · ' + name)));
      items.forEach(function (it) {
        var changed = it.opened !== undefined && it.opened !== it.value;
        function set(v) {
          if (v === it.value || BUSY) return;
          if (TEDITS[name]) { status('Save or discard the unsaved changes in ' + name + '’s manifest form first.', 'err'); return; }
          var w = clone(st.manifest);
          setPath(w, it.path, v);
          change('save_manifest', [name, w, st.sha], 'tool|' + name, name + ': ' + it.name + ' now defaults to ' + String(v) + ' (saved to its tool.yaml).');
        }
        var ctl = it.type === 'bool'
          ? h('span', { 'class': 'seg' }, [h('button', { 'class': it.value ? 'on' : '', disabled: BUSY, onclick: function () { set(true); } }, 'on'),
              h('button', { 'class': it.value ? '' : 'on', disabled: BUSY, onclick: function () { set(false); } }, 'off')])
          : h('select', { disabled: BUSY, onchange: function (e) { set(e.target.value); } },
              it.values.map(function (c) { return h('option', { value: c, selected: c === it.value }, String(c)); }));
        rows.push(h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, it.name)),
          h('td', { 'class': changed ? 'chg' : null, title: changed ? 'Was “' + it.opened + '” when the Studio opened.' : null }, ctl),
          h('td', { 'class': 'muted', style: 'font-size:11.5px' }, it.label),
          h('td', { 'class': 'racts' }, changed ? h('button', { 'class': 'mini', disabled: BUSY, title: 'Back to the default it had when the Studio opened.',
            onclick: function () { set(it.opened); } }, 'Undo') : null)]));
      });
    });
    rows.push(h('tr', { 'class': 'grp' }, h('td', { colspan: 4 }, 'setup')));
    rows.push(h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, 'parameter_primer_image')),
      h('td', null, h('span', { 'class': 'seg ro', title: LATER.settings }, [h('button', { 'class': S.DC_PARAMS_PRIMER_ENABLED ? 'on' : '' }, 'on'),
        h('button', { 'class': S.DC_PARAMS_PRIMER_ENABLED ? '' : 'on' }, 'off')])),
      h('td', { 'class': 'muted', style: 'font-size:11.5px' }, 'DC_PARAMS_PRIMER_ENABLED (workflow_settings/settings.py, outside the setup: read-only here)'), h('td')]));
    add(center, h('table', { 'class': 'ptab', style: 'margin:10px 16px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Setting', 'Default', 'What it is', ''].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, rows)]));
    add(center, h('div', { 'class': 'banner info', style: 'margin:6px 16px;border:1px solid #2f4f86;border-radius:7px' },
      'The Studio never asks for a secret value. These names go into .env.example in the full package, with empty values; you fill them on your own computer or in your hosting provider.'));
    var toolSecrets = [];
    D.tools.forEach(function (t) { (t.secrets || []).forEach(function (s) { toolSecrets.push({ tool: t.name, s: s }); }); });
    add(center, h('div', { style: 'padding:8px 16px 0' }, h('h4', null, 'Declared by the tools · ' + toolSecrets.length)));
    add(center, h('table', { 'class': 'ptab', style: 'margin:6px 16px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Variable', 'Tool', 'What it is', 'Required'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, toolSecrets.length ? toolSecrets.map(function (x) {
        return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, x.s.env)),
          h('td', null, h('a', { href: link('studio', 'tools', { tool: x.tool }) }, x.tool)), h('td', null, x.s.description),
          h('td', { 'class': x.s.required ? 'warn' : 'muted' }, x.s.required ? 'required' : 'optional')]);
      }) : [h('tr', null, h('td', { colspan: 4, 'class': 'muted' }, 'None: a tool declares the variables it reads in its manifest (Tools › Edit › Secrets).'))])]));
    add(center, h('div', { style: 'padding:8px 16px 0' }, h('h4', null, 'Read by the engine · ' + D.env_vars.length)));
    add(center, h('table', { 'class': 'ptab', style: 'margin:6px 16px 20px;width:calc(100% - 32px)' }, [
      h('thead', null, h('tr', null, ['Variable', 'Needed for', 'Required'].map(function (x) { return h('th', null, x); }))),
      h('tbody', null, D.env_vars.map(function (n) {
        var u = ENV_USE[n] || [D.env_sections[n] || '', 'optional'];
        return h('tr', null, [h('td', null, h('span', { 'class': 'pname' }, n)), h('td', null, u[0]),
          h('td', { 'class': u[1] === 'optional' ? 'muted' : 'warn' }, u[1])]);
      }))]));
    add(right, h('div', { 'class': 'insp' }, [h('h4', null, 'Where these come from'),
      h('p', null, 'Each tool’s settings and secrets are its own (its tool.yaml): a change here is saved there, checked by the engine first, and Undo puts the default back as the Studio opened it. The variables in the last table are the engine’s (.env.example). No value of a secret is read or shown.')]));
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
   * the downloads and Open setup file (P7-2, studio/package.py)
   * ==================================================================== */
  var DL_WHAT = {
    setup: ['The setup alone: its parameters, texts, tools and pictures (dc_pack/), and setup_info.json. Open it again here with Open setup file.'],
    package: ['The engine and this setup, ready to put on GitHub and deploy:',
      'the app (agents/, engine/, tools/, web/, workflow_settings/, web_app.py, the Dockerfile), the Studio and the checks Validate runs;',
      'this setup as dc_pack/;',
      'DEPLOY.md (how to put it on Railway), README.md, .env.example with the variables its tools declare, setup_info.json.',
      'Not in it: .env, logs, attempts, past sessions, the Workflow Settings saved on this computer.']
  };
  function dlValidate(v) {
    if (v.status === 'not run') return pill('Validate has not run since the Studio started', 'warn');
    if (v.status === 'out of date') return pill('Validate ran before the last change', 'warn');
    return pill('Validate: ' + (v.counts.fail ? v.counts.fail + ' failed' : 'no failures') + (v.counts.warn ? ', ' + v.counts.warn + (v.counts.warn === 1 ? ' warning' : ' warnings') : ''),
      v.status === 'fail' ? 'bad' : v.status === 'warn' ? 'warn' : 'good');
  }
  function askDownload(kind) {
    var title = kind === 'setup' ? 'Download setup file' : 'Download full package';
    var body = h('div', null, h('p', { 'class': 'muted' }, 'Checking what goes in…'));
    showModal(title, body, [h('button', { onclick: closeModal }, 'Cancel')]);
    call('download_preview', kind).then(function (r) {
      body.innerHTML = '';
      if (!r || r.ok === false) { add(body, h('div', { 'class': 'banner bad boxed' }, (r && r.error) || 'The download could not be prepared.')); return; }
      var found = r.findings || [], notes = r.notes || [];
      add(body, [
        h('p', null, [h('b', { 'class': 'mono' }, r.file), ' · ' + fmt(r.files) + ' files · ' + fmt(Math.round(r.bytes / 1024)) + ' KB before packing']),
        h('ul', { 'class': 'checks', style: 'margin:8px 0' }, DL_WHAT[kind].map(function (x) { return h('li', null, x); })),
        h('div', { 'class': 'pills', style: 'margin:8px 0' }, [dlValidate(r.validate), kpill('engine ' + r.engine)]),
        r.validate.status !== 'pass' && r.validate.status !== 'warn' ? h('p', { 'class': 'muted' }, 'setup_info.json records this. Validate checks the setup before you deploy it.') : null,
        found.length ? h('div', { 'class': 'banner warn boxed' }, [
          h('div', null, h('b', null, 'Something here looks like a key (' + found.length + '). Keys belong in .env or in the deployment’s variables, never in the setup.')),
          h('ul', { 'class': 'checks warn', style: 'margin-top:4px' }, found.map(function (f) {
            return h('li', null, h('span', { 'class': 'mono' }, f.file + ':' + f.line + ' — ' + f.what + ': ' + f.shown));
          }))]) : null,
        notes.length ? h('div', { 'class': 'block' }, [h('h4', null, 'The tools’ own dependencies'),
          h('ul', { 'class': 'checks warn' }, notes.map(function (n) { return h('li', null, n); }))]) : null
      ]);
      var foot = el('modalFoot'); foot.innerHTML = '';
      add(foot, [h('button', { onclick: closeModal }, 'Cancel'),
        h('a', { 'class': 'btn ' + (found.length ? 'warnbtn' : 'primary'), href: 'download/' + kind, download: r.file,
          onclick: function () { closeModal(); status('Downloading ' + r.file + '…', 'busy'); setTimeout(function () { status('Downloaded ' + r.file + '.', 'ok'); }, 2500); } },
          found.length ? 'Download anyway' : 'Download')]);
    });
  }
  function askOpen() {
    if (BUSY) return;
    var file = null;
    var msg = h('div');
    var pick = h('input', { type: 'file', accept: '.zip', onchange: function (e) { file = e.target.files[0] || null; } });
    var body = h('div', null, [
      h('div', { 'class': 'banner warn boxed' }, 'Opening a setup file replaces the setup in ' + D.pack_dir + ': every file of it. Download it first to keep it.' +
        (unsavedKeys().length ? '  Your ' + unsavedKeys().length + ' unsaved change(s) are dropped too.' : '')),
      h('p', { style: 'margin:8px 0' }, h('a', { href: 'download/setup', download: '' }, 'Download the current setup first')),
      h('p', { 'class': 'muted' }, 'A setup file made with Download setup file — or a full package, whose dc_pack/ is taken. The engine checks it before anything is replaced; afterwards Undo and the prompt viewer’s changes start from it.'),
      h('div', { style: 'margin:10px 0' }, pick), msg]);
    showModal('Open setup file', body, [h('button', { onclick: closeModal }, 'Cancel'),
      h('button', { 'class': 'primary', onclick: function () {
        msg.innerHTML = '';
        if (!file) { add(msg, h('p', { 'class': 'err' }, 'Choose a file first.')); return; }
        add(msg, h('p', { 'class': 'muted' }, 'Checking it with the engine…'));
        var fr = new root.FileReader();
        fr.onload = function () {
          var b64 = String(fr.result).split(',')[1] || '';
          call('open_setup', b64, file.name).then(function (r) {
            msg.innerHTML = '';
            if (!r || r.ok === false) {
              add(msg, h('div', { 'class': 'banner bad boxed' }, [h('div', null, (r && r.error) || 'The file could not be opened.')].concat(
                ((r && r.problems) || []).map(function (p) { return h('div', null, '• ' + p); }))));
              return;
            }
            closeModal();
            BUSY = true; EDITS = {}; PEDITS = {}; GEDITS = {}; TEDITS = {}; FEDITS = {}; TESTS = {}; FIELD_ERRORS = {};
            status('Opened ' + file.name + '. Re-assembling every prompt…', 'busy');
            reload().then(function () {
              BUSY = false;
              status('Opened ' + file.name + ' (' + r.files + ' files): Undo now goes back to it.' + ((r.warnings || []).length ? '  ' + r.warnings.join(' ') : ''),
                (r.warnings || []).length ? 'warn' : 'ok');
              go('studio', 'identity');
              render();
            }, function (e) { BUSY = false; status(String(e && e.message ? e.message : e), 'err'); render(); });
          });
        };
        fr.readAsDataURL(file);
      } }, 'Open')]);
  }

  /* ======================================================================
   * Prepare for GitHub (P7-3, studio/prepare.py): it never runs git
   * ==================================================================== */
  function copyButton(text) {
    return h('button', { 'class': 'mini', onclick: function (e) {
      var b = e.target;
      (root.navigator.clipboard ? root.navigator.clipboard.writeText(text) : Promise.reject()).then(
        function () { b.textContent = 'Copied'; }, function () { b.textContent = 'Select and copy it'; });
    } }, 'Copy');
  }
  function askPrepare() {
    if (BUSY) return;
    var body = h('div', null, h('p', { 'class': 'muted' }, 'Checking this folder…'));
    showModal('Prepare for GitHub', body, [h('button', { onclick: closeModal }, 'Close')]);
    call('prepare_run').then(function (r) {
      body.innerHTML = '';
      if (!r || r.ok === false) { add(body, h('div', { 'class': 'banner bad boxed' }, (r && r.error) || 'Prepare could not run.')); return; }
      if (r.needs_validate) {
        add(body, [h('p', null, 'Prepare needs Validate on the setup as it is now, with no failure.'),
          h('button', { 'class': 'primary', style: 'margin-top:8px', onclick: function () { closeModal(); go('studio', 'validate'); startValidate(); } }, 'Run Validate')]);
        return;
      }
      var out = r.result, c = out.validate.counts;
      add(body, h('div', { 'class': 'pills', style: 'margin-bottom:8px' }, [
        pill('Validate: ' + (c.fail ? c.fail + ' failed' : 'no failures') + (c.warn ? ', ' + c.warn + (c.warn === 1 ? ' warning' : ' warnings') : ''),
          out.validate.status === 'fail' ? 'bad' : out.validate.status === 'warn' ? 'warn' : 'good')]));
      if (!out.ok) {
        add(body, [h('div', { 'class': 'banner bad boxed' }, 'Validate found failures: fix them first. Nothing was changed.'),
          h('ul', { 'class': 'checks bad' }, out.failed.map(function (f) { return h('li', null, f.title + (f.lines.length ? ': ' + f.lines[0] : '')); }))]);
        return;
      }
      add(body, h('div', { 'class': 'block' }, [h('h4', null, out.changes.length ? 'What prepare changed' : 'Nothing needed changing'),
        out.changes.length ? h('ul', { 'class': 'checks' }, out.changes.map(function (x) { return h('li', null, x); })) : null]));
      if (out.notes.length) add(body, h('div', { 'class': 'block' }, [h('h4', null, 'The tools’ own dependencies'),
        h('ul', { 'class': 'checks warn' }, out.notes.map(function (n) { return h('li', null, n); }))]));
      if (out.findings.length) add(body, h('div', { 'class': 'banner warn boxed' }, [
        h('div', null, h('b', null, 'Something here looks like a key (' + out.findings.length + '): remove it before you commit. Keys belong in .env (which git ignores) or in the deployment’s variables.')),
        h('ul', { 'class': 'checks warn', style: 'margin-top:4px' }, out.findings.map(function (f) {
          return h('li', null, h('span', { 'class': 'mono' }, f.file + ':' + f.line + ' — ' + f.what + ': ' + f.shown));
        }))]));
      var cmd = out.commands;
      add(body, h('div', { 'class': 'block' }, [
        h('h4', null, cmd.case === 'update' ? 'To commit and push (Railway then deploys it)' : 'To commit and create the private GitHub repository'),
        h('p', { 'class': 'muted' }, 'Nothing was committed: prepare never runs git. In a terminal, in ' + D.pack_dir.replace(/[\\/]dc_pack$/, '') + ':'),
        h('div', { 'class': 'cmds' }, cmd.steps.map(function (s) {
          return h('div', { 'class': 'cmd' }, [h('div', { 'class': 'muted' }, s[0]), h('div', { 'class': 'row2' }, [h('code', null, s[1]), copyButton(s[1])])]);
        })),
        cmd.manual.length ? h('p', { 'class': 'muted', style: 'margin-top:8px;white-space:pre-wrap' }, cmd.manual.join('\n')) : null]));
      status('Prepared: ' + (out.changes.length ? out.changes.length + ' change(s)' : 'nothing to change') + '; nothing was committed.', out.findings.length ? 'warn' : 'ok');
    });
  }

  /* ======================================================================
   * Validate (P7): every check of the setup (studio/validate.py)
   * ==================================================================== */
  var VAL = { state: null, polling: false };
  var VAL_PARTS = [['A', 'The setup loads', 'parameters.json, pack.yaml, every tool.yaml and every text, as the engine reads them'],
    ['B', 'The prompts', 'every agent of topologies 3, 5 and 7, with the setup’s defaults and with every feature on'],
    ['C', 'The parameter lists', 'each agent’s list names the parameters in order, with their ranges'],
    ['D', 'The tools', 'each one run on the parameters’ defaults, as Test tool runs it'],
    ['E', 'A scripted turn', 'one turn per topology with a fake model: no API cost'],
    ['X', 'Developer checks', 'the repository’s own checks that hold for any setup']];
  var VAL_WORD = { pass: 'passed', warn: 'warning', fail: 'failed' };
  var VAL_CLS = { pass: 'good', warn: 'warn', fail: 'bad' };

  function valSummary(rep) {
    var c = rep.counts, parts = [];
    if (c.fail) parts.push(c.fail + ' failed');
    if (c.warn) parts.push(c.warn + (c.warn === 1 ? ' warning' : ' warnings'));
    parts.push(c.pass + ' passed');
    return parts.join(', ');
  }
  function valBadge() {
    var st = VAL.state;
    if (!st) return null;
    if (st.running) return pill(st.done + '/' + (st.total || '…'), 'warn', 'Validate is running.');
    var rep = st.report;
    if (!rep) return null;
    if (!st.current) return pill('out of date', '', 'The setup changed since Validate ran.');
    return pill(rep.status === 'pass' ? '✓' : rep.counts.fail ? rep.counts.fail + ' ✗' : rep.counts.warn + ' !',
      VAL_CLS[rep.status], valSummary(rep));
  }
  function paintValidate() {
    if (R.page === 'studio' && R.section === 'validate') { render(); return; }
    ['valNav', 'valTop'].forEach(function (id) { var e = el(id); if (e) { e.innerHTML = ''; add(e, valBadge()); } });
  }
  function readValidate() {
    VAL.readAt = Date.now();
    return call('validate_state').then(function (r) {
      if (r && r.ok) VAL.state = r.data;
      if (VAL.state && VAL.state.running) pollValidate();
      paintValidate();
    });
  }
  function startValidate() {
    call('validate_start').then(function (r) {
      if (!r || !r.ok) { status((r && r.error) || 'Validate could not start.', 'err'); return; }
      VAL.state = r.data;
      status('Validate is running…', 'busy');
      paintValidate();
      pollValidate();
    });
  }
  function pollValidate() {
    if (VAL.polling) return;
    VAL.polling = true;
    (function tick() {
      call('validate_state').then(function (r) {
        if (r && r.ok) VAL.state = r.data;
        if (VAL.state && VAL.state.running) { paintValidate(); setTimeout(tick, 1200); return; }
        VAL.polling = false;
        var rep = VAL.state && VAL.state.report;
        if (VAL.state && VAL.state.error) status(VAL.state.error, 'err');
        else if (rep) status('Validate: ' + (rep.counts.fail ? '' : 'no failures — ') + valSummary(rep) + '.',
          rep.status === 'fail' ? 'err' : rep.status === 'warn' ? 'warn' : 'ok');
        paintValidate();
      }, function () { VAL.polling = false; });
    }());
  }
  // A file a check names -> the field or tool it belongs to.
  function pathTarget(path) {
    var t = /(?:^|\/)([^\/]+)\.md$/.exec(path);
    if (t && (/(^|\/)fragments\//.test(path) || /\/prompts\//.test(path))) {
      var base = t[1].replace(/\.t\d+$/, ''), agent = null, at = base.indexOf('@');
      if (at >= 0) { agent = base.slice(at + 1); base = base.slice(0, at); }
      var s = slotByName(base);
      if (s) return function () { go('studio', s.section, { field: base, agent: agent }); };
    }
    var m = /(?:^|\/)tools\/([a-z][a-z0-9_]*)\//.exec(path);
    if (m) return function () { go('studio', 'tools', { tool: m[1] }); };
    return null;
  }
  function valLine(ln) {
    var out = [], last = 0, rx = /[\w.-]*\/?(?:fragments\/[\w\/@.-]+\.md|tools\/[a-z][a-z0-9_]*\/[\w\/@.-]*)/g, m;
    while ((m = rx.exec(ln))) {
      var target = pathTarget(m[0]);
      if (!target) continue;
      out.push(ln.slice(last, m.index));
      out.push(h('span', { 'class': 'vlink', title: 'Open it', onclick: target }, m[0]));
      last = m.index + m[0].length;
    }
    out.push(ln.slice(last));
    return out;
  }
  function valGo(lk) {
    if (lk.section === 'prompts') go('studio', 'prompts', { topo: lk.topology || null });
    else if (lk.section === 'tools') go('studio', 'tools', { tool: lk.tool || null });
    else if (lk.section === 'parameters' && lk.filter === 'ranges') pgo({ ranges: '1' });
    else go('studio', lk.section);
  }
  function valItem(i) {
    var kids = [h('div', { 'class': 'vhead' }, [pill(VAL_WORD[i.status], VAL_CLS[i.status]), h('b', null, i.title),
      i.about ? h('span', { 'class': 'muted' }, i.about) : null,
      h('span', { 'class': 'grow' }),
      i.seconds !== undefined && i.seconds !== null ? h('span', { 'class': 'muted vsec' }, i.seconds + ' s') : null,
      i.link ? h('button', { 'class': 'mini', onclick: function () { valGo(i.link); } }, 'Open') : null])];
    if (i.note) kids.push(h('p', { 'class': 'muted vnote' }, i.note));
    if (i.lines.length) kids.push(h('ul', { 'class': 'checks vlines ' + VAL_CLS[i.status] },
      i.lines.map(function (ln) { return h('li', null, valLine(ln)); })));
    if (i.tokens && Object.keys(i.tokens).length) kids.push(h('p', { 'class': 'muted vtok' },
      'Tokens with the setup’s defaults: ' + Object.keys(i.tokens).map(function (a) { return a + ' ' + fmt(i.tokens[a]); }).join(' · ')));
    return h('div', { 'class': 'vitem ' + i.status }, kids);
  }
  function renderValidate(center, right) {
    // is the last run still current? (asked again on each visit)
    if (!VAL.polling && (!VAL.readAt || Date.now() - VAL.readAt > 5000)) readValidate();
    var st = VAL.state || {}, rep = st.report, running = !!st.running;
    add(center, head('Validate', 'Every check of the setup: does it load, do the prompts build, do the parameter lists match, does each tool run, does a turn go through — then the repository’s own checks that hold for any setup. ' +
      'It runs on a copy of the setup taken when it starts (the tools on the setup itself, writing only into a throw-away folder), takes about a minute, and you can keep working meanwhile.',
      [h('button', { 'class': 'primary', disabled: running, onclick: startValidate },
        running ? 'Running… ' + st.done + ' of ' + (st.total || '…') + ' checks' : rep ? 'Run again' : 'Run Validate')]));
    if (running) add(center, h('div', { 'class': 'progressline' }, h('div', { style: 'width:' + (st.total ? Math.round(100 * st.done / st.total) : 2) + '%' })));
    if (st.error) add(center, h('div', { 'class': 'vbanner banner bad boxed' }, st.error));
    if (!running && rep) {
      add(center, h('div', { 'class': 'vbanner banner boxed ' + VAL_CLS[rep.status] },
        (rep.status === 'fail' ? 'The setup has problems: ' : rep.status === 'warn' ? 'The setup works; look at the warnings: ' : 'Every check passed: ') + valSummary(rep) + '.'));
      if (!st.current) add(center, h('div', { 'class': 'vbanner banner warn boxed' }, 'The setup changed after this run started: run Validate again.'));
    }
    var items = running ? st.items || [] : rep ? rep.items : [];
    if (!running && !rep && !st.error) add(center, h('p', { 'class': 'muted', style: 'margin:14px 16px' }, 'Validate has not run since the Studio started.'));
    VAL_PARTS.forEach(function (p) {
      var mine = items.filter(function (i) { return i.part === p[0]; });
      if (!mine.length) return;
      add(center, h('h3', { 'class': 'vpart' }, [p[0] + '. ' + p[1], h('span', { 'class': 'muted' }, ' — ' + p[2])]));
      mine.forEach(function (i) { add(center, valItem(i)); });
    });
    var ins = h('div', { 'class': 'insp' });
    if (rep) {
      add(ins, [h('div', { 'class': 'title' }, 'The last run'),
        h('div', { 'class': 'pills' }, [pill(rep.counts.pass + ' passed', 'good'), rep.counts.warn ? pill(rep.counts.warn + (rep.counts.warn === 1 ? ' warning' : ' warnings'), 'warn') : null,
          rep.counts.fail ? pill(rep.counts.fail + ' failed', 'bad') : null, kpill(rep.seconds + ' s')]),
        h('p', null, 'Started ' + rep.started.replace('T', ' at ') + (st.current ? ', on the setup as it is now.' : '; the setup has changed since.'))]);
    }
    add(ins, h('div', { 'class': 'block' }, [h('h4', null, 'What counts'),
      h('p', null, 'A failure is a problem in the setup: fix it before you download or deploy it.'),
      h('p', { style: 'margin-top:6px' }, 'A warning does not stop the setup working: text left about a tool the setup no longer has (it reads as switched off), or something this computer lacks — a package, a program, a service, a secret. Where the setup is deployed (its Docker image), what the image installs is there.')]));
    add(ins, h('div', { 'class': 'block' }, [h('h4', null, 'The checks'),
      h('ul', { 'class': 'checks' }, VAL_PARTS.map(function (p) { return h('li', null, [h('b', null, p[0]), h('span', null, p[1] + ': ' + p[2] + '.')]); }))]));
    add(right, ins);
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
    else renderLanding(app);
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
    var shown = R.section === 'parameters' ? (R.q.group ? 'group|' + R.q.group : 'param|' + (R.q.param || ''))
      : fkey(R.q.field || '', R.q.agent || null);
    if (fk && R.section === 'tools' && R.q.tool && (fk === 'tool|' + R.q.tool || fk.indexOf('file|' + R.q.tool + '/') === 0)) shown = fk;
    if (fk && fk === shown) {
      var back = doc.querySelector('[data-fk="' + fk + '"][data-t="' + ft + '"]');
      if (back) {
        back.focus();
        try { back.setSelectionRange(caret[0], caret[1]); } catch (e) { /* not a text input */ }
      }
    }
  }

  function init() {
    // An answer that asks for the access code (it ran out): the login again.
    root.StudioBridge.onAuth = function () { renderLogin(el('app'), 'Type the access code again.'); };
    call('session').then(function (s) {
      SESSION = s && s.ok ? s : SESSION;
      if (SESSION.online && !SESSION.authed) { renderLogin(el('app')); return; }
      if (SESSION.online && !root.location.hash) root.location.hash = '#/landing';
      start();
    }, start);
  }
  function start() {
    el('app').innerHTML = '';
    el('app').appendChild(h('div', { 'class': 'page' }, [h('h1', null, 'MAS Studio'),
      h('p', { 'class': 'sub' }, 'Assembling every prompt of this setup… (first time only)')]));
    req('get_all').then(function (r) {
      D = r.data;
      root.addEventListener('hashchange', render);
      // an unsaved change is lost with the page: ask first
      root.addEventListener('beforeunload', function (e) {
        if (unsavedKeys().length) { e.preventDefault(); e.returnValue = ''; }
      });
      render();
      readValidate();
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
