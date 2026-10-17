/* bridge.js -- the page's calls to the Studio server.
 *
 * StudioBridge.call('<name>', args...) -> POST /api/<name> with
 * {"args": [...]}; the answer is the studio UI kit's {ok: true, ...} /
 * {ok: false, error: "<sentence>"}.  The Studio draft's mock_bridge.js
 * answered the same calls from a file.
 */
(function (root) {
  'use strict';

  root.StudioBridge = {
    call: function (name) {
      var args = Array.prototype.slice.call(arguments, 1);
      return root.fetch('/api/' + encodeURIComponent(name), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ args: args })
      }).then(function (r) {
        return r.json().catch(function () {
          return { ok: false, error: 'The Studio server answered ' + r.status + ' without data.' };
        });
      });
    }
  };
}(window));
