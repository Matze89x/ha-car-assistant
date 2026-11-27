/* Receipt and odometer photos: a photo or a file fills in the form it was chosen in (the server reads it, see receipt.py / odometer_scan.py). Nothing is saved
   before the person presses save.
   - A form of a refuel has two buttons: [data-scan-btn="camera"] (the camera at once) and [data-scan-btn="file"] (a photo from the library or a PDF), each with
     its hidden input [data-scan-file="camera|file"] beside it. The address and the words come from the nearest ancestor with [data-scan].
   - The odometer box has one button [data-scan-btn] and one input [data-scan-file] (the phone offers camera or library). */
(function () {
  var FIELDS = ['date', 'amount', 'price_per_unit', 'price_total', 'station', 'notes', 'odometer', 'odometer_km', 'fuel_kind'];

  function shrink(file, done) { /* longest side 2000 px, as JPEG: a small upload; the server cleans it up again. A PDF goes as it is. */
    if (file.type === 'application/pdf') { done(file); return; }
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

  function show(note, text, tone) {
    if (!note) return;
    note.textContent = text || '';
    note.hidden = !text;
    note.className = 'hint scan-note' + (tone ? ' ' + tone : '');
  }

  document.addEventListener('change', function (e) {
    var input = e.target;
    if (!input || !input.matches || !input.matches('[data-scan-file]') || !input.files || !input.files[0]) return;
    var root = input.closest('[data-scan]'), form = input.closest('form'), file = input.files[0];
    if (!root || !form) return;
    var note = (input.parentNode && input.parentNode.querySelector('[data-scan-note]')) || form.querySelector('[data-scan-note]');
    var buttons = form.querySelectorAll('[data-scan-btn]');
    function t(k) { return root.getAttribute('data-t-' + k) || ''; }
    function busy(on) { buttons.forEach(function (b) { b.disabled = on; }); }
    show(note, t('busy'), 'busy');
    busy(true);
    shrink(file, function (blob) {
      fetch(root.getAttribute('data-scan'), { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'application/octet-stream' }, credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then(function (d) {
          var hits = 0;
          FIELDS.forEach(function (name) {
            var el = form.elements[name], v = d[name];
            if (!el || !v) return;
            if ((name === 'notes' || name === 'odometer_km') && el.value) return; /* never overwrite what somebody typed - or what the car's own reading gave */
            el.value = v;
            el.classList.add('scan-hit');
            el.addEventListener('input', function () { el.classList.remove('scan-hit'); }, { once: true });
            hits++;
          });
          if (!hits) { show(note, t('none'), 'warn'); return; }
          if ('plausible' in d) { /* the odometer: always to be checked; a warning when it is below the last reading or far above it */
            show(note, d.plausible ? t('ok') : t('odd').replace('{n}', d.last === null ? '' : String(d.last)), d.plausible ? 'ok' : 'warn');
            return;
          }
          show(note, t('ok') + ' ' + (d.amount && d.price_per_unit && d.price_total ? (d.derived && d.derived.length ? (t('derived_' + d.derived[0]) || t('derived')) : (d.checked ? t('fit') : t('nofit'))) : ''), d.checked && !(d.derived && d.derived.length) ? 'ok' : 'warn');
        })
        .catch(function () { show(note, t('err'), 'warn'); })
        .then(function () { busy(false); input.value = ''; });
    });
  });

  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest && e.target.closest('[data-scan-btn]');
    if (!b) return;
    var kind = b.getAttribute('data-scan-btn'), scope = b.parentNode;
    var f = (kind && scope && scope.querySelector('[data-scan-file="' + kind + '"]')) || (scope && scope.querySelector('[data-scan-file]')) || (b.closest('[data-scan]') && b.closest('[data-scan]').querySelector('[data-scan-file]'));
    if (f) f.click();
  });
})();
