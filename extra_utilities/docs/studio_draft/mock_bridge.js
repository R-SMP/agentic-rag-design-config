/* mock_bridge.js -- stands in for the Studio server in the draft.
 *
 * The real Studio answers the same calls over HTTP (POST /api/<name>, the
 * studio UI kit's {ok: true, ...} / {ok: false, error: "<sentence>"}
 * contract).  Here every answer comes from window.DRAFT_DATA, the real
 * propeller pack written by build_draft_data.py.  Nothing is executed and
 * nothing leaves the page.
 */
(function (root) {
  'use strict';
  var D = root.DRAFT_DATA;

  function ok(x) { x = x || {}; x.ok = true; return Promise.resolve(x); }
  function fail(msg) { return Promise.resolve({ ok: false, error: msg }); }

  var api = {
    get_all: function () { return D ? ok({ data: D }) : fail('draft_data.js is missing: run build_draft_data.py.'); },
    validate: function () { return ok({ started: true }); },
    import_setup: function (name) {
      return ok({ file: name || 'propeller.mas-setup.zip' });
    },
    download: function (kind) {
      return fail('Draft: no file is produced. The hosted Studio would build the ' +
                  (kind === 'full' ? 'full package' : 'setup file') + ' in memory and send it to the browser.');
    },
    test_tool: function (name, mode) {
      if (mode !== 'local') return fail('Test tool runs only on your own computer (python -m studio): this site never runs a setup\'s Python.');
      return ok({ started: true, tool: name });
    }
  };

  root.StudioBridge = {
    call: function (name) {
      var args = Array.prototype.slice.call(arguments, 1);
      if (typeof api[name] !== 'function') return Promise.reject(new Error('the bridge has no ' + name + '()'));
      try { return Promise.resolve(api[name].apply(api, args)); }
      catch (e) { return Promise.reject(e); }
    }
  };
}(window));
