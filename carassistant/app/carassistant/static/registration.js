/* The registration certificate ("Fahrzeugschein") in the form of the vehicle pass: a photo or a PDF is read on the server (registration.py), and what it says
   goes into the fields that are still EMPTY - marked, so the person sees what came from the certificate. What is written already is never overwritten: where the
   certificate says something else, the fields are only named, and one button takes the values over. Nothing is saved before the person presses Save.
   The card: [data-regscan] (the address of the scan, the words in data-t-*), the buttons [data-reg-btn="camera|file"] with their hidden inputs
   [data-reg-file="camera|file"], the line [data-reg-note], the button [data-reg-apply] and the switch [data-reg-insp] (the next inspection as an appointment). */
(function () {
  var root = document.querySelector('[data-regscan]'), form = document.getElementById('vform');
  if (!root || !form) return;
  var note = root.querySelector('[data-reg-note]'), apply = root.querySelector('[data-reg-apply]'), insp = root.querySelector('[data-reg-insp]');
  var buttons = root.querySelectorAll('[data-reg-btn]'), pending = [], touched = {}, unsure = [];

  function t(k) { return root.getAttribute('data-t-' + k) || ''; }
  function field(name) { return form.elements[name] || null; }
  function isGroup(el) { return !el.tagName; } /* a RadioNodeList (the radio buttons of one name) has no tag */
  function span(radio) { return radio.nextElementSibling; } /* the tile of a radio button: <input><span> */

  function shrink(file, done) { /* longest side 3000 px, as JPEG: the server needs the small print legible; a PDF goes as it is */
    if (file.type === 'application/pdf') { done(file); return; }
    var url = URL.createObjectURL(file), img = new Image();
    img.onload = function () {
      var k = Math.min(1, 3000 / Math.max(img.naturalWidth, img.naturalHeight)), c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob(function (b) { done(b || file); }, 'image/jpeg', 0.9);
    };
    img.onerror = function () { URL.revokeObjectURL(url); done(file); }; /* a format the browser cannot draw: send it as it is */
    img.src = url;
  }

  function show(text, tone) {
    note.textContent = text || '';
    note.hidden = !text;
    note.className = 'hint scan-note' + (tone ? ' ' + tone : '');
  }

  function norm(x) { return String(x == null ? '' : x).toUpperCase().replace(/[\s.\-]/g, ''); }

  /* does the field have nothing of its own yet? The fuel type of a new car always has a choice - the preset one counts as empty until somebody chooses */
  function empty(name) {
    var el = field(name);
    if (!el) return false;
    if (name === 'fuel_type') return root.getAttribute('data-new') === '1' && !touched.fuel_type;
    return String(el.value || '').trim() === '';
  }

  function labelOf(name) {
    var el = field(name), box = el && (isGroup(el) ? el[0].closest('.tf-field') : el.closest('label'));
    var text = box && (box.querySelector('.tf-l') ? box.querySelector('.tf-l').textContent : (box.childNodes[0] && box.childNodes[0].textContent));
    return (text || name).replace(/\*/g, '').trim();
  }

  function clearMark(el) { el.classList.remove('scan-hit', 'scan-unsure'); }
  function markOf(el, name) { el.classList.add('scan-hit'); if (unsure.indexOf(name) >= 0) el.classList.add('scan-unsure'); } /* yellow: only one reading found it */

  function put(name, value) { /* sets the field and marks it; false when the field has no such choice */
    var el = field(name);
    if (!el || !value) return false;
    if (isGroup(el)) {
      var hit = Array.prototype.filter.call(el, function (r) { return r.value === value; })[0];
      if (!hit) return false;
      Array.prototype.forEach.call(el, function (r) { if (span(r)) clearMark(span(r)); });
      hit.checked = true;
      hit.dispatchEvent(new Event('change', { bubbles: true }));
      if (span(hit)) {
        markOf(span(hit), name);
        Array.prototype.forEach.call(el, function (r) { r.addEventListener('change', function () { if (span(hit)) clearMark(span(hit)); }, { once: true }); });
      }
      return true;
    }
    el.value = value;
    if (String(el.value) !== String(value)) return false; /* a choice the list does not have */
    markOf(el, name);
    el.addEventListener('input', function () { clearMark(el); }, { once: true });
    el.addEventListener('change', function () { clearMark(el); }, { once: true });
    var group = el.closest('details');
    if (group) group.open = true; /* the group with the filled field opens: the person sees it */
    return true;
  }

  document.addEventListener('change', function (e) { if (e.target && e.target.name === 'fuel_type') touched.fuel_type = true; });

  function offerInspection(month, text) { /* "2027-06": an appointment, when the car has none yet */
    if (!month || !insp) return text;
    var shown = month.slice(5) + '/' + month.slice(0, 4);
    if (root.getAttribute('data-has-inspection') === '1') return text + ' ' + t('inspection_have').replace('{month}', shown);
    var box = insp.querySelector('input'), sure = unsure.indexOf('inspection') < 0;
    box.value = month;
    box.checked = sure; /* a month that was read only once is offered, but the person has to switch it on */
    insp.querySelector('.nm-t').textContent = t(sure ? 'inspection' : 'inspection_unsure').replace('{month}', shown);
    insp.hidden = false;
    return text;
  }

  function opened(name) {
    var el = field(name), box = el && (isGroup(el) ? el[0] : el), group = box && box.closest('details');
    if (group) group.open = true;
  }

  document.addEventListener('change', function (e) {
    var input = e.target;
    if (!input || !input.matches || !input.matches('[data-reg-file]') || !input.files || !input.files[0]) return;
    var file = input.files[0];
    function busy(on) { buttons.forEach(function (b) { b.disabled = on; }); }
    show(t('busy'), 'busy');
    apply.hidden = true;
    if (insp) insp.hidden = true; /* what the last scan offered is not offered any more: the next answer says what is */
    busy(true);
    shrink(file, function (blob) {
      fetch(root.getAttribute('data-regscan'), { method: 'POST', body: blob, headers: { 'Content-Type': blob.type || 'application/octet-stream' }, credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then(function (d) {
          var filled = [], differs = [];
          pending = [];
          unsure = d.unsure || [];
          (d.found || []).forEach(function (name) {
            var value = d.fields[name];
            if (!value || !field(name)) return;
            if (empty(name)) {
              if (put(name, value)) { filled.push(name); opened(name); }
            } else if (norm(field(name).value) !== norm(value)) {
              differs.push(name);
              pending.push([name, value]);
            }
          });
          if (!(d.found || []).length && !d.inspection) { show(t('none'), 'warn'); return; }
          var text = filled.length ? t('ok').replace('{n}', String(filled.length)) : (differs.length ? '' : t('same'));
          if (differs.length) text += (text ? ' ' : '') + t('diff').replace('{list}', differs.map(labelOf).join(', '));
          var doubtful = filled.some(function (name) { return unsure.indexOf(name) >= 0; });
          if (doubtful) text += ' ' + t('unsure');
          show(offerInspection(d.inspection, text), differs.length || doubtful ? 'warn' : 'ok');
          apply.hidden = !differs.length;
        })
        .catch(function () { show(t('err'), 'warn'); })
        .then(function () { busy(false); input.value = ''; });
    });
  });

  apply.addEventListener('click', function () { /* the person wants the values of the certificate where something else is written */
    pending.forEach(function (p) { if (put(p[0], p[1])) opened(p[0]); });
    pending = [];
    apply.hidden = true;
    show(t('applied'), 'ok');
  });

  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest && e.target.closest('[data-reg-btn]');
    if (!b) return;
    var f = root.querySelector('[data-reg-file="' + b.getAttribute('data-reg-btn') + '"]');
    if (f) f.click();
  });
})();
