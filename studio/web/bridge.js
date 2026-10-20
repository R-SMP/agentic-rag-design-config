/* bridge.js -- the page's calls to the Studio server.
 *
 * StudioBridge.call('<name>', args...) -> POST api/<name> (relative: the
 * Studio is at / on its own, at /studio/ inside the configurator) with
 * {"args": [...]}; the answer is the studio UI kit's {ok: true, ...} /
 * {ok: false, error: "<sentence>"}.  The Studio draft's mock_bridge.js
 * answered the same calls from a file.  Online, an answer 401 with
 * {auth: true} calls StudioBridge.onAuth (the page asks for the code).
 */
(function (root) {
  'use strict';

  root.StudioBridge = {
    call: function (name) {
      var args = Array.prototype.slice.call(arguments, 1);
      return root.fetch('api/' + encodeURIComponent(name), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ args: args })
      }).then(function (r) {
        return r.json().catch(function () {
          return { ok: false, error: 'The Studio server answered ' + r.status + ' without data.' };
        }).then(function (d) {
          // Online, an answer that asks for the access code (P7b-lite).
          if (r.status === 401 && d && d.auth && name !== 'auth' && root.StudioBridge.onAuth) root.StudioBridge.onAuth();
          return d;
        });
      });
    }
  };
}(window));
