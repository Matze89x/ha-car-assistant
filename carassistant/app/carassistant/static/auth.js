// Passkeys (WebAuthn) for the login page and the account card. Failures never break the page (try/catch).
(function () {
  function toBuf(s) { s = s.replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "="; var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a.buffer; }
  function toB64(buf) { var a = new Uint8Array(buf), s = ""; for (var i = 0; i < a.length; i++) s += String.fromCharCode(a[i]); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
  function supported() { return !!(window.PublicKeyCredential && navigator.credentials && window.isSecureContext); }
  function post(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined }).then(function (r) { return r.json(); });
  }
  function label() { var u = navigator.userAgent; return /iPhone/.test(u) ? "iPhone" : /iPad/.test(u) ? "iPad" : /Macintosh/.test(u) ? "Mac" : /Android/.test(u) ? "Android" : /Windows/.test(u) ? "Windows" : "Device"; }

  // login page
  try {
    var rec = document.getElementById("recToggle"), recForm = document.getElementById("rec");
    if (rec && recForm) rec.addEventListener("click", function () { recForm.hidden = !recForm.hidden; });
    var box = document.getElementById("pk"), btn = document.getElementById("pkBtn"), err = document.getElementById("pkErr");
    if (box && btn && supported()) {
      var base = document.querySelector("[data-base]").getAttribute("data-base"), next = box.getAttribute("data-next") || "/";
      box.hidden = false;
      var fail = function (t) { err.textContent = t; err.hidden = false; btn.disabled = false; };
      btn.addEventListener("click", async function () {
        err.hidden = true; btn.disabled = true;
        try {
          var j = await post(base + "/login/passkey/options");
          if (!j.ok) return fail(j.error);
          var o = j.options; o.challenge = toBuf(o.challenge); (o.allowCredentials || []).forEach(function (c) { c.id = toBuf(c.id); });
          var c = await navigator.credentials.get({ publicKey: o }), rs = c.response;
          var cred = { id: c.id, rawId: toB64(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
            response: { clientDataJSON: toB64(rs.clientDataJSON), authenticatorData: toB64(rs.authenticatorData), signature: toB64(rs.signature) } };
          if (rs.userHandle) cred.response.userHandle = toB64(rs.userHandle);
          var j2 = await post(base + "/login/passkey/verify", { token: j.token, credential: cred, next: next });
          if (!j2.ok) return fail(j2.error);
          location.href = j2.next || "/";
        } catch (e) { fail(box.getAttribute(e && e.name === "NotAllowedError" ? "data-cancelled" : "data-unsupported")); }
      });
    }
  } catch (e) { /* ignore */ }

  // account card: add a passkey
  try {
    var holder = document.getElementById("pk-add-box"), add = document.getElementById("pk-add"), msg = document.getElementById("pk-msg");
    if (holder && add) {
      var b = holder.getAttribute("data-base");
      var say = function (t) { msg.textContent = t; msg.hidden = false; };
      if (!supported()) { say(holder.getAttribute("data-unsupported")); return; }
      add.hidden = false;
      add.addEventListener("click", async function () {
        add.disabled = true; msg.hidden = true;
        try {
          var j = await post(b + "/account/passkey/options");
          if (!j.ok) throw { soft: j.error };
          var o = j.options; o.challenge = toBuf(o.challenge); o.user.id = toBuf(o.user.id); (o.excludeCredentials || []).forEach(function (c) { c.id = toBuf(c.id); });
          var c = await navigator.credentials.create({ publicKey: o }), rs = c.response;
          var cred = { id: c.id, rawId: toB64(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
            response: { clientDataJSON: toB64(rs.clientDataJSON), attestationObject: toB64(rs.attestationObject) } };
          if (c.authenticatorAttachment) cred.authenticatorAttachment = c.authenticatorAttachment;
          var j2 = await post(b + "/account/passkey/register", { token: j.token, credential: cred, label: label() });
          if (!j2.ok) throw { soft: j2.error };
          location.href = b + "/settings#account"; location.reload();
        } catch (e) {
          say(e && e.soft ? e.soft : holder.getAttribute(e && e.name === "InvalidStateError" ? "data-exists" : e && e.name === "NotAllowedError" ? "data-cancelled" : "data-unsupported"));
          add.disabled = false;
        }
      });
    }
  } catch (e) { /* ignore */ }
})();
