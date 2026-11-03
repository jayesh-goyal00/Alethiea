// All communication with the backend lives in this file.
// See README.md for the response format the backend must return.
(function () {
  var base = (window.ALETHEIA_CONFIG || {}).API_BASE || '';

  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) {
      return ('0' + b.toString(16)).slice(-2);
    }).join('');
  }

  // Demo mode: fixed sample result, real SHA-256 for uploaded files.
  function demo(input) {
    var name = input.file ? input.file.name : input.url;
    var result = {
      fileName: name, sha256: null, fps: '29.97', duration: '0:42', score: 88,
      checks: [
        { label: 'Pulse wave', text: 'Unclear or weak pulse pattern.', ok: false },
        { label: 'Face life signs', text: 'Skin color changes are inconsistent.', ok: false },
        { label: 'Heart rate signal', text: 'No steady heart rate found.', ok: false }
      ]
    };
    var wait = new Promise(function (res) { setTimeout(res, 3000); });
    var src = input.original || input.file;
    var hash = (src && window.crypto && crypto.subtle && src.arrayBuffer)
      ? src.arrayBuffer().then(function (b) { return crypto.subtle.digest('SHA-256', b); })
          .then(function (h) { result.sha256 = hex(h); }, function () {})
      : Promise.resolve();
    return Promise.all([wait, hash]).then(function () { return result; });
  }

  // POST /api/analyze
  //   file upload: multipart/form-data, field "video"
  //   link:        application/json  {"url": "https://..."}
  function analyze(input) {
    if (!base) return demo(input);
    var opts;
    if (input.file) {
      var fd = new FormData();
      fd.append('video', input.file);
      opts = { method: 'POST', body: fd };
    } else {
      opts = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: input.url })
      };
    }
    return fetch(base + '/api/analyze', opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (b) {
          throw new Error(b.error || ('Server returned ' + r.status + '.'));
        });
      }
      return r.json().then(function (data) {
        if (data && data.reportUrl && base && !data.reportUrl.startsWith('http')) {
          data.reportUrl = base + data.reportUrl;
        }
        return data;
      });
    });
  }

  window.AletheiaAPI = { analyze: analyze };
})();
