/* Fuel receipt: a photo fills in the form of a new refuel (the server reads it, see receipt.py). Nothing is saved before the person presses save. */
(function () {
  var FIELDS = ['date', 'amount', 'price_per_unit', 'price_total', 'station', 'notes', 'odometer', 'fuel_kind'];

  function shrink(file, done) { /* longest side 2000 px, as JPEG: a small upload; the server cleans it up again */
    var url = URL.createObjectURL(file), img = new Image();
    img.onload = function () {
      var k = Math.min(1, 2000 / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob(function (b) { done(b || file); }, 'image/jpeg', 0.88);
    };
    img.onerror = function () { URL.revokeObjectURL(url); done(file); }; /* a format the browser cannot draw: send it as it is */
    img.src = url;
  }

  function show(box, text, tone) {
    var note = box.querySelector('[data-scan-note]');
    if (!note) return;
    note.textContent = text || '';
    note.hidden = !text;
    note.className = 'hint scan-note' + (tone ? ' ' + tone : '');
  }

  document.addEventListener('change', function (e) {
    var input = e.target;
    if (!input || !input.matches || !input.matches('[data-scan-file]') || !input.files || !input.files[0]) return;
    var box = input.closest('[data-scan]'), form = input.closest('form'), file = input.files[0];
    if (!box || !form) return;
    var btn = box.querySelector('[data-scan-btn]');
    function t(k) { return box.getAttribute('data-t-' + k) || ''; }
    show(box, t('busy'), 'busy');
    if (btn) btn.disabled = true;
    shrink(file, function (blob) {
      fetch(box.getAttribute('data-scan'), { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'application/octet-stream' }, credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then(function (d) {
          var hits = 0;
          FIELDS.forEach(function (name) {
            var el = form.elements[name], v = d[name];
            if (!el || !v) return;
            if (name === 'notes' && el.value) return; /* never overwrite what somebody typed */
            el.value = v;
            el.classList.add('scan-hit');
            el.addEventListener('input', function () { el.classList.remove('scan-hit'); }, { once: true });
            hits++;
          });
          if (!hits) { show(box, t('none'), 'warn'); return; }
          if ('plausible' in d) { /* the odometer: always to be checked; a warning when it is below the last reading or far above it */
            show(box, d.plausible ? t('ok') : t('odd').replace('{n}', d.last === null ? '' : String(d.last)), d.plausible ? 'ok' : 'warn');
            return;
          }
          show(box, t('ok') + ' ' + (d.amount && d.price_per_unit && d.price_total ? (d.derived && d.derived.length ? t('derived') : (d.checked ? t('fit') : t('nofit'))) : ''), d.checked && !(d.derived && d.derived.length) ? 'ok' : 'warn');
        })
        .catch(function () { show(box, t('err'), 'warn'); })
        .then(function () { if (btn) btn.disabled = false; input.value = ''; });
    });
  });

  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest && e.target.closest('[data-scan-btn]');
    if (!b) return;
    var f = (b.parentNode && b.parentNode.querySelector('[data-scan-file]')) || b.closest('[data-scan]').querySelector('[data-scan-file]');
    if (f) f.click();
  });
})();
