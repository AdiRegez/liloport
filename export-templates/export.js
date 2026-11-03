/* Liloport – export.js: läuft nur in exportierten Seiten auf dem Webserver.
   Kommentare in drei Stufen: comments.php (PHP) → comments.py (Python-CGI) → Browser-Speicher
   der kommentierenden Person (reiner Datei-Server, lokale Kopie). «Herunterladen» packt den ganzen Ordner
   als ZIP inklusive aller Kommentare – auch aus einer per Doppelklick geöffneten Kopie (über dateien.html). */
(function () {
  'use strict';
  var kommentare = [];
  var backend = null;          // 'comments.php' | 'comments.py' | null (Browser-Speicher)
  var backendArt = '';         // 'php' | 'python' (CGI)
  var lokaleKommentare = [];   // nur im Browser gespeicherte Kommentare (ohne Server-Backend)
  var meta = (function () { try { return JSON.parse(document.getElementById('liloport-meta').textContent) || {}; } catch (e) { return {}; } })();
  var exportId = meta.export || 'x';
  var startId = meta.start || exportId;   // bei Portfolio-Exporten: die Startseite (gemeinsamer Moderationsschlüssel)
  var speicherSchluessel = 'liloport-kommentare-' + exportId;
  var bearbeitenMoeglich = false;   // Backend kann bearbeiten/löschen
  var moderation = '';              // Moderationsschlüssel (nur für die Autorin/den Autor der Seite)
  // Passwortgeschützte Seite: Formular und Titel vor dem Entschlüsseln merken, damit «Herunterladen» die Kopie
  // wieder verschlüsselt speichert (statt den entschlüsselten Inhalt offen in die ZIP zu legen)
  var geschuetzt = document.getElementById('passwort-form')
    ? { form: document.getElementById('inhalt').innerHTML, titel: document.title, klasse: document.body.className } : null;

  /* Eigene Kommentare: Schlüssel, den der Server beim Speichern nur an die kommentierende Person gibt. */
  function meineSchluessel() { try { return JSON.parse(localStorage.getItem('liloport-schluessel') || '{}') || {}; } catch (e) { return {}; } }
  function schluesselMerken(id, s) { var m = meineSchluessel(); m[id] = s; try { localStorage.setItem('liloport-schluessel', JSON.stringify(m)); } catch (e) { /* egal */ } }
  function schluesselFuer(k) { return meineSchluessel()[k.id] || moderation; }

  function moderationLesen() {
    var m = /[#&]moderation=([A-Za-z0-9_-]{16,})/.exec(location.hash);
    if (m) {
      try { sessionStorage.setItem('liloport-moderation-' + startId, m[1]); } catch (e) { /* egal */ }
      history.replaceState(null, '', location.pathname + location.search);   // Schlüssel nicht in der Adresszeile lassen
    }
    try { moderation = sessionStorage.getItem('liloport-moderation-' + startId) || (m ? m[1] : ''); } catch (e) { moderation = m ? m[1] : ''; }
    // Abgabe (oder Export ohne Moderation): kein Moderationsschlüssel, auch kein mitgebrachter
    if (meta.moderation === false) { moderation = ''; try { sessionStorage.removeItem('liloport-moderation-' + startId); } catch (e) { /* egal */ } }
  }

  function lokalLaden() {
    try { lokaleKommentare = JSON.parse(localStorage.getItem(speicherSchluessel) || '[]') || []; } catch (e) { lokaleKommentare = []; }
  }
  function lokalSpeichern() {
    try { localStorage.setItem(speicherSchluessel, JSON.stringify(lokaleKommentare)); return true; } catch (e) { return false; }
  }
  function zusammenfuehren(a, b) {
    var ids = {}; var alle = [];
    a.concat(b).forEach(function (k) { if (k && k.id && !ids[k.id]) { ids[k.id] = 1; alle.push(k); } });
    alle.sort(function (x, y) { return zeitwert(x.zeit) - zeitwert(y.zeit); });
    return alle;
  }

  function el(tag, attrs, kinder) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === 'text') e.textContent = attrs[k];
      else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    (kinder || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }

  function isoLokal(d) {
    /* ISO 8601 mit lokaler Zeitzone, wie comments.php/comments.py (z. B. 2026-10-24T20:44:08+02:00). */
    var p = function (n) { return (n < 10 ? '0' : '') + n; }, o = -d.getTimezoneOffset(), v = o >= 0 ? '+' : '-';
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) + v + p(Math.floor(Math.abs(o) / 60)) + ':' + p(Math.abs(o) % 60);
  }
  function zeitwert(iso) { var t = Date.parse(iso || ''); return isNaN(t) ? 0 : t; }

  function datum(iso) {
    var d = new Date(iso);
    return isNaN(d) ? (iso || '') : d.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit', year: 'numeric' }) + ' ' + d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
  }

  function kommentarElement(k) {
    var inhalt = el('div', { 'class': 'kommentar-inhalt' });
    var text = k.text || '';
    if (/<[a-z][\s\S]*>/i.test(text) && window.LiloportKommentarEditor) inhalt.innerHTML = window.LiloportKommentarEditor.filtern(text);
    else inhalt.appendChild(el('p', { text: text }));
    var darf = k.lokal || (backend && bearbeitenMoeglich && (meineSchluessel()[k.id] || moderation));
    var artikel = el('article', { 'class': 'kommentar' + (k.lokal ? ' lokal' : ''), 'data-id': k.id }, [
      el('header', null, [el('strong', { text: k.name || 'Anonym' }), el('time', { datetime: k.zeit || '', text: ' · ' + datum(k.zeit) }),
        k.bearbeitet ? el('span', { 'class': 'klein-text bearbeitet', text: ' · bearbeitet' }) : null,
        k.lokal ? el('span', { 'class': 'klein-text', text: ' · nur in diesem Browser' }) : null,
        darf ? el('span', { 'class': 'kommentar-aktionen' }, [
          el('button', { type: 'button', text: 'Bearbeiten', onclick: function () { bearbeiten(k, artikel, inhalt); } }),
          el('button', { type: 'button', text: 'Löschen', onclick: function () { loeschen(k); } })
        ]) : null]),
      inhalt
    ]);
    return artikel;
  }

  function aktion(daten) {
    var f = new FormData();
    Object.keys(daten).forEach(function (n) { f.append(n, daten[n]); });
    return fetch(backend, { method: 'POST', body: f }).then(function (r) { return r.json(); })
      .then(function (j) { if (j.fehler) throw new Error(j.fehler); return j; });
  }

  function loeschen(k) {
    if (!confirm('Diesen Kommentar löschen?')) return;
    if (k.lokal) {
      lokaleKommentare = lokaleKommentare.filter(function (x) { return x.id !== k.id; });
      lokalSpeichern();
      kommentare = kommentare.filter(function (x) { return x.id !== k.id; });
      zeichnen(); return;
    }
    aktion({ aktion: 'loeschen', id: k.id, schluessel: schluesselFuer(k) })
      .then(function () { kommentare = kommentare.filter(function (x) { return x.id !== k.id; }); zeichnen(); })
      .catch(function (e) { alert('Löschen nicht möglich: ' + e.message); });
  }

  function bearbeiten(k, artikel, inhalt) {
    if (artikel.querySelector('.kommentar-bearbeiten')) return;
    var form = el('form', { 'class': 'kommentar-bearbeiten kommentar-form' }, [
      el('label', null, [el('textarea', { name: 'text', rows: '4' })]),
      el('div', { 'class': 'feld-zeile' }, [
        el('button', { type: 'submit', 'class': 'knopf primaer', text: 'Speichern' }),
        el('button', { type: 'button', 'class': 'knopf', text: 'Abbrechen', onclick: function () { form.remove(); inhalt.hidden = false; } })
      ])
    ]);
    inhalt.hidden = true;
    artikel.appendChild(form);
    var ed = window.LiloportKommentarEditor ? window.LiloportKommentarEditor.editor(form) : null;
    if (ed) ed.setzen(k.text || ''); else form.querySelector('textarea').value = k.text || '';
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var text = ed ? ed.wert() : form.querySelector('textarea').value.trim();
      if (ed ? ed.leer() : !text) return;
      if (k.lokal) {
        k.text = text; k.bearbeitet = isoLokal(new Date());
        lokaleKommentare.forEach(function (x) { if (x.id === k.id) { x.text = k.text; x.bearbeitet = k.bearbeitet; } });
        lokalSpeichern(); zeichnen(); return;
      }
      aktion({ aktion: 'bearbeiten', id: k.id, text: text, schluessel: schluesselFuer(k) })
        .then(function (j) { kommentare = kommentare.map(function (x) { return x.id === k.id ? j.kommentar : x; }); zeichnen(); })
        .catch(function (e) { alert('Speichern nicht möglich: ' + e.message); });
    });
  }

  function moderationsBand() {
    var liste = document.getElementById('kommentar-liste');
    var alt = document.getElementById('moderation-band'); if (alt) alt.remove();
    if (!moderation || !liste) return;
    var band = el('div', { id: 'moderation-band', 'class': 'moderation-band' }, [
      el('span', { text: backend && bearbeitenMoeglich ? 'Moderation aktiv: Du kannst alle Kommentare bearbeiten und löschen. ' : 'Moderations-Link erkannt, aber dieser Server speichert keine Kommentare – Moderation ist nur mit PHP oder Python möglich. ' }),
      el('button', { type: 'button', 'class': 'knopf', text: 'Moderation beenden', onclick: function () {
        moderation = ''; try { sessionStorage.removeItem('liloport-moderation-' + startId); } catch (e) { /* egal */ }
        moderationsBand(); zeichnen();
      } })
    ]);
    liste.parentNode.insertBefore(band, liste);
  }

  function zeichnen() {
    var liste = document.getElementById('kommentar-liste');
    if (liste) {
      liste.innerHTML = '';
      var normale = kommentare.filter(function (k) { return k.art !== 'beurteilung'; });
      if (!normale.length) liste.appendChild(el('p', { 'class': 'hinweis', text: 'Noch keine Kommentare.' }));
      normale.forEach(function (k) { liste.appendChild(kommentarElement(k)); });
    }
    beurteilungenZeichnen();
  }

  /* ---------- Beurteilung der Kompetenzen (nur bei Exporten «als Abgabe») ---------- */

  function beurteilungenZeichnen() {
    document.querySelectorAll('.kr-beurteilung').forEach(function (sek) {
      var block = sek.dataset.block;
      sek.querySelectorAll('.kr-b-zeile').forEach(function (zeile) {
        var nid = zeile.dataset.knoten, titel = zeile.dataset.titel, inhalt = zeile.querySelector('.kr-b-inhalt');
        inhalt.innerHTML = '';
        var eigene = kommentare.filter(function (k) { return k.art === 'beurteilung' && k.block === block && k.knoten === nid; });
        eigene.forEach(function (k) { inhalt.appendChild(beurteilungElement(k)); });
        inhalt.appendChild(beurteilungFormular(block, nid, titel));
      });
    });
  }

  function skalaAnzeige(k) {
    var leiste = el('span', { 'class': 'kr-b-skala', role: 'img', 'aria-label': k.wert + ' von ' + k.skala });
    for (var i = 0; i <= k.skala; i++) leiste.appendChild(el('span', { 'class': 'kr-b-stufe' + (i === k.wert ? ' gewaehlt' : '') + (i <= k.wert ? ' erreicht' : ''), text: String(i) }));
    return leiste;
  }

  function beurteilungElement(k) {
    var darf = k.lokal || (backend && bearbeitenMoeglich && (meineSchluessel()[k.id] || moderation));
    var inhalt = el('div', { 'class': 'kommentar-inhalt' });
    if (k.text) { if (/<[a-z][\s\S]*>/i.test(k.text) && window.LiloportKommentarEditor) inhalt.innerHTML = window.LiloportKommentarEditor.filtern(k.text); else inhalt.appendChild(el('p', { text: k.text })); }
    var artikel = el('article', { 'class': 'kr-b-eintrag' + (k.lokal ? ' lokal' : ''), 'data-id': k.id }, [
      el('header', null, [el('strong', { text: k.name || 'Anonym' }), el('time', { datetime: k.zeit || '', text: ' · ' + datum(k.zeit) }),
        k.bearbeitet ? el('span', { 'class': 'klein-text bearbeitet', text: ' · bearbeitet' }) : null,
        k.lokal ? el('span', { 'class': 'klein-text', text: ' · nur in diesem Browser' }) : null,
        darf ? el('span', { 'class': 'kommentar-aktionen' }, [
          el('button', { type: 'button', text: 'Bearbeiten', onclick: function () { beurteilungBearbeiten(k, artikel); } }),
          el('button', { type: 'button', text: 'Löschen', onclick: function () { loeschen(k); } })
        ]) : null]),
      el('div', { 'class': 'kr-b-ergebnis' }, [skalaAnzeige(k), el('strong', { text: k.wert + ' von ' + k.skala })]),
      inhalt
    ]);
    return artikel;
  }

  function skalaWahl(skala, wert, beiWahl) {
    /* Skala (0 bis N, N = 1…10) und Wert als Knöpfe */
    var zustand = { skala: skala || 10, wert: (wert === undefined || wert === null) ? null : wert };
    var sel = el('select', { 'class': 'kr-b-skala-wahl', title: 'Skala' });
    for (var n = 1; n <= 10; n++) sel.appendChild(el('option', { value: String(n), text: '0 bis ' + n }));
    sel.value = String(zustand.skala);
    var leiste = el('div', { 'class': 'kr-b-skala wahl' });
    function knoepfe() {
      leiste.innerHTML = '';
      for (var i = 0; i <= zustand.skala; i++) (function (i) {
        var b = el('button', { type: 'button', 'class': 'kr-b-stufe' + (zustand.wert === i ? ' gewaehlt' : '') + (zustand.wert !== null && i <= zustand.wert ? ' erreicht' : ''), text: String(i), 'aria-pressed': zustand.wert === i ? 'true' : 'false' });
        b.addEventListener('click', function () { zustand.wert = i; knoepfe(); if (beiWahl) beiWahl(zustand); });
        leiste.appendChild(b);
      })(i);
    }
    sel.addEventListener('change', function () { zustand.skala = parseInt(sel.value, 10); if (zustand.wert !== null && zustand.wert > zustand.skala) zustand.wert = zustand.skala; knoepfe(); });
    knoepfe();
    return { el: el('div', { 'class': 'kr-b-wahl' }, [el('label', null, [el('span', { text: 'Skala' }), sel]), leiste]), zustand: zustand };
  }

  function beurteilungFormular(block, nid, titel) {
    var form = el('form', { 'class': 'kr-b-form', autocomplete: 'off' });
    var auf = el('button', { type: 'button', 'class': 'knopf klein kr-b-neu', text: '+ Beurteilung' });
    var name = el('input', { type: 'text', name: 'name', maxlength: '80', placeholder: 'Name (freiwillig)' });
    try { name.value = localStorage.getItem('liloport-name') || ''; } catch (e) { /* egal */ }
    var wahl = skalaWahl(10, null);
    var text = el('textarea', { name: 'text', rows: '3', maxlength: '20000', placeholder: 'Kommentar zur Beurteilung (optional)' });
    var status = el('span', { 'class': 'kommentar-status klein-text' });
    var felder = el('div', { 'class': 'kr-b-felder' }, [name, wahl.el, text, el('div', { 'class': 'feld-zeile' }, [
      el('button', { type: 'submit', 'class': 'knopf primaer', text: 'Beurteilung speichern' }),
      el('button', { type: 'button', 'class': 'knopf', text: 'Abbrechen', onclick: function () { felder.hidden = true; auf.hidden = false; } }), status]) ]);
    felder.hidden = true;
    auf.addEventListener('click', function () { felder.hidden = false; auf.hidden = true; name.focus(); });
    form.appendChild(auf); form.appendChild(felder);
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (wahl.zustand.wert === null) { status.textContent = 'Bitte einen Wert auf der Skala wählen.'; return; }
      try { localStorage.setItem('liloport-name', name.value); } catch (e) { /* egal */ }
      var daten = { name: name.value.trim(), text: text.value.trim(), seite: exportId, art: 'beurteilung', block: block, knoten: nid, knotenTitel: titel, skala: wahl.zustand.skala, wert: wahl.zustand.wert };
      if (!backend) {
        var k = { id: 'lokal-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), zeit: isoLokal(new Date()), lokal: true };
        Object.keys(daten).forEach(function (n) { k[n] = daten[n]; });
        lokaleKommentare.push(k); lokalSpeichern(); kommentare = zusammenfuehren(kommentare, lokaleKommentare); zeichnen(); return;
      }
      status.textContent = 'sendet …';
      aktion(daten).then(function (j) {
        if (j.schluessel) schluesselMerken(j.kommentar.id, j.schluessel);
        kommentare.push(j.kommentar); zeichnen();
      }).catch(function (e) { status.textContent = 'Fehler: ' + e.message; });
    });
    return form;
  }

  function beurteilungBearbeiten(k, artikel) {
    if (artikel.querySelector('.kr-b-form')) return;
    var wahl = skalaWahl(k.skala, k.wert);
    var text = el('textarea', { rows: '3', maxlength: '20000' }); text.value = k.text || '';
    var form = el('form', { 'class': 'kr-b-form' }, [wahl.el, text, el('div', { 'class': 'feld-zeile' }, [
      el('button', { type: 'submit', 'class': 'knopf primaer', text: 'Speichern' }),
      el('button', { type: 'button', 'class': 'knopf', text: 'Abbrechen', onclick: function () { form.remove(); } })])]);
    artikel.appendChild(form);
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (wahl.zustand.wert === null) return;
      if (k.lokal) {
        k.skala = wahl.zustand.skala; k.wert = wahl.zustand.wert; k.text = text.value.trim(); k.bearbeitet = isoLokal(new Date());
        lokaleKommentare.forEach(function (x) { if (x.id === k.id) { x.skala = k.skala; x.wert = k.wert; x.text = k.text; x.bearbeitet = k.bearbeitet; } });
        lokalSpeichern(); zeichnen(); return;
      }
      aktion({ aktion: 'bearbeiten', id: k.id, text: text.value.trim(), skala: wahl.zustand.skala, wert: wahl.zustand.wert, block: k.block, knoten: k.knoten, knotenTitel: k.knotenTitel, schluessel: schluesselFuer(k) })
        .then(function (j) { kommentare = kommentare.map(function (x) { return x.id === k.id ? j.kommentar : x; }); zeichnen(); })
        .catch(function (e) { alert('Speichern nicht möglich: ' + e.message); });
    });
  }

  function ping(name) {
    return fetch(name + '?ping=1', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { if (j && j.ok) { backendArt = j.backend || (name === 'comments.php' ? 'php' : 'python'); bearbeitenMoeglich = !!j.bearbeiten; return name; } return Promise.reject(); });
  }

  function fuerDieseSeite(liste) {
    return (liste || []).filter(function (k) { return k && (!k.seite || k.seite === exportId); });
  }

  function kommentareLaden() {
    var eingebettet = document.getElementById('liloport-kommentare');
    if (eingebettet) { try { kommentare = fuerDieseSeite(JSON.parse(eingebettet.textContent)); } catch (e) { kommentare = []; } }
    lokalLaden();
    moderationLesen();
    if (location.protocol === 'file:') { backend = null; kommentare = zusammenfuehren(kommentare, lokaleKommentare); zeichnen(); moderationsBand(); return Promise.resolve(); }
    return ping('comments.php').catch(function () { return ping('comments.py'); })
      .then(function (name) { backend = name; }, function () { backend = null; })
      .then(function () { return fetch(backend ? backend + '?liste=1&seite=' + encodeURIComponent(exportId) : 'comments.json', { cache: 'no-store' }); })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (liste) { liste = fuerDieseSeite(liste); if (Array.isArray(liste) && (liste.length || backend)) kommentare = liste; })
      .catch(function () {})
      .then(function () { kommentare = zusammenfuehren(kommentare, lokaleKommentare); zeichnen(); moderationsBand(); });
  }

  function formular() {
    var form = document.getElementById('kommentar-form');
    if (!form) return;
    var status = form.querySelector('.kommentar-status');
    var editor = window.LiloportKommentarEditor ? window.LiloportKommentarEditor.editor(form) : null;
    if (!backend) {
      form.insertBefore(el('p', { 'class': 'hinweis kommentar-hinweis', text: location.protocol === 'file:'
        ? 'Lokale Kopie: Dein Kommentar wird in diesem Browser gespeichert. Mit «Herunterladen» unten gibst du die Seite samt allen Kommentaren als ZIP weiter – zum Beispiel per E-Mail.'
        : 'Dieser Server speichert keine Kommentare (kein PHP, kein Python). Dein Kommentar bleibt in diesem Browser; mit «Herunterladen» gibst du die Seite samt deinen Kommentaren als ZIP weiter – zum Beispiel per E-Mail an die Autorin oder den Autor.' }), form.firstChild);
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var daten = new FormData(form);
      var name = (daten.get('name') || '').toString().trim();
      var text = editor ? editor.wert() : (daten.get('text') || '').toString().trim();
      if (editor ? editor.leer() : !text) { status.textContent = 'Bitte einen Kommentar eingeben.'; return; }
      daten.set('text', text);
      if (!backend) {
        if (daten.get('website')) { form.reset(); return; }
        var k = { id: 'lokal-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), zeit: isoLokal(new Date()), name: name.slice(0, 80), text: text.slice(0, 20000), lokal: true, seite: exportId };
        lokaleKommentare.push(k);
        var ok = lokalSpeichern();
        kommentare = zusammenfuehren(kommentare, lokaleKommentare);
        zeichnen(); form.reset(); if (editor) editor.leeren();
        status.textContent = ok ? 'In diesem Browser gespeichert. Mit «Herunterladen» kommt der Kommentar in die ZIP.' : 'Gespeichert bis zum Schliessen der Seite (Browser-Speicher nicht verfügbar).';
        return;
      }
      status.textContent = 'sendet …';
      daten.set('seite', exportId);
      fetch(backend, { method: 'POST', body: daten })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.fehler) throw new Error(j.fehler);
          if (j.schluessel) schluesselMerken(j.kommentar.id, j.schluessel);
          kommentare.push(j.kommentar);
          zeichnen();
          form.reset(); if (editor) editor.leeren();
          status.textContent = 'Danke, der Kommentar ist gespeichert.' + (j.schluessel ? ' Du kannst ihn in diesem Browser bearbeiten oder löschen.' : '');
        })
        .catch(function (e) { status.textContent = 'Fehler: ' + e.message; });
    });
  }

  /* ---------- ZIP ohne Bibliothek (Speichern ohne Kompression) ---------- */

  var crcTabelle = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[n] = c >>> 0; }
    return t;
  })();
  function crc32(buf) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < buf.length; i++) c = crcTabelle[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function zipBauen(eintraege) {
    /* eintraege: [{name, daten: Uint8Array}] -> Blob */
    var teile = [], zentral = [], offset = 0, enc = new TextEncoder();
    function u16(n) { return [n & 255, (n >> 8) & 255]; }
    function u32(n) { return [n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255]; }
    var d = new Date(), dosZeit = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1), dosDatum = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
    eintraege.forEach(function (e) {
      var name = enc.encode(e.name), crc = crc32(e.daten), n = e.daten.length;
      var kopf = new Uint8Array([].concat([0x50, 0x4b, 3, 4], u16(20), u16(0x0800), u16(0), u16(dosZeit), u16(dosDatum), u32(crc), u32(n), u32(n), u16(name.length), u16(0)));
      teile.push(kopf, name, e.daten);
      zentral.push(new Uint8Array([].concat([0x50, 0x4b, 1, 2], u16(20), u16(20), u16(0x0800), u16(0), u16(dosZeit), u16(dosDatum), u32(crc), u32(n), u32(n), u16(name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset))), name);
      offset += kopf.length + name.length + n;
    });
    var zentralGroesse = zentral.reduce(function (s, z) { return s + z.length; }, 0);
    var ende = new Uint8Array([].concat([0x50, 0x4b, 5, 6], u16(0), u16(0), u16(eintraege.length), u16(eintraege.length), u32(zentralGroesse), u32(offset), u16(0)));
    return new Blob(teile.concat(zentral, [ende]), { type: 'application/zip' });
  }

  /* ---------- dateien.html: macht «Herunterladen» auch aus einer per Doppelklick geöffneten Kopie möglich ----------
     Ein Browser darf aus einer lokalen Datei die Nachbardateien nicht lesen, sie aber in einem unsichtbaren Rahmen
     öffnen. dateien.html enthält alle Dateien des Exports (base64) und schickt sie per postMessage an diese Seite;
     geladen wird sie erst beim Klick auf «Herunterladen». Bewusst keine .js-Datei: Windows blockiert .js-Dateien
     beim Entpacken einer heruntergeladenen ZIP. */

  var EINBETTEN_MAX = 60 * 1024 * 1024;
  var STARTDATEI = 'Seite öffnen.html';

  function b64codieren(bytes) {
    var s = ''; for (var i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function b64decodieren(s) { var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a; }

  var DATEIEN_HTML = 'dateien.html';
  var geladeneDateien = null;

  function dateienLaden() {
    /* -> Promise({dateien: {name: Uint8Array}, fehlend: [...]}) oder null, wenn dateien.html fehlt */
    function auswerten(roh) {
      if (!roh || !roh.dateien) return null;
      var out = {}; Object.keys(roh.dateien).forEach(function (n) { out[n] = b64decodieren(roh.dateien[n]); });
      return { dateien: out, fehlend: roh.fehlend || [] };
    }
    if (geladeneDateien) return Promise.resolve(auswerten(geladeneDateien));
    return new Promise(function (ok) {
      var rahmen = document.createElement('iframe'), erledigt = false, uhr = null;
      rahmen.id = 'liloport-dateien-rahmen'; rahmen.hidden = true; rahmen.setAttribute('aria-hidden', 'true');
      function ende(roh) {
        if (erledigt) return; erledigt = true; clearTimeout(uhr);
        window.removeEventListener('message', empfang); rahmen.remove();
        if (roh) geladeneDateien = roh;
        ok(auswerten(roh));
      }
      function empfang(ev) {
        if (ev.source !== rahmen.contentWindow || !ev.data || !ev.data.liloportDateien) return;
        ende(ev.data.liloportDateien);
      }
      window.addEventListener('message', empfang);
      // Fehlt die Datei, kommt keine Nachricht: nach dem Laden noch kurz warten, dann aufgeben
      rahmen.onload = function () { uhr = setTimeout(function () { ende(null); }, 3000); };
      rahmen.onerror = function () { ende(null); };
      rahmen.src = DATEIEN_HTML;
      document.body.appendChild(rahmen);
    });
  }

  function dateienHtml(sammlung) {
    /* Gegenstück zu dateien_html() in Liloport: kleinste Dateien zuerst, bis zur Grenze. */
    var dateien = {}, fehlend = [], gesamt = 0;
    Object.keys(sammlung).filter(function (n) { return n !== DATEIEN_HTML && n !== 'dateien.js'; })
      .sort(function (a, b) { return sammlung[a].length - sammlung[b].length; })
      .forEach(function (n) { if (gesamt + sammlung[n].length <= EINBETTEN_MAX) { dateien[n] = b64codieren(sammlung[n]); gesamt += sammlung[n].length; } else fehlend.push(n); });
    var nutzlast = JSON.stringify({ dateien: dateien, fehlend: fehlend }).replace(/<\//g, '<\\/');
    var text = '<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8"><meta name="robots" content="noindex">' +
      '<title>Liloport – Hilfsdatei</title></head><body style="font-family:system-ui,sans-serif;margin:3em">' +
      '<p>Hilfsdatei von Liloport für «Herunterladen». Bitte nicht löschen; zum Ansehen «Seite öffnen» verwenden.</p>' +
      '<script>(function(){var d=' + nutzlast + ';if(window.parent===window)return;' +
      'var ziel=location.protocol==="file:"?"*":location.origin;' +
      'window.parent.postMessage({liloportDateien:d},ziel);})();</' + 'script></body></html>\n';
    return { text: text, fehlend: fehlend };
  }

  function startdateiHtml(start) {
    var ziel = 'inhalt/' + start + '.html';
    return '<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8"><title>Seite öffnen</title><meta http-equiv="refresh" content="0; url=' + ziel + '"></head>' +
      '<body style="font-family:system-ui,sans-serif;margin:3em;max-width:40em"><p><a href="' + ziel + '">Seite öffnen</a></p>' +
      '<p>Öffnet sich die Seite nicht oder ohne Gestaltung, wurde die ZIP-Datei vermutlich nicht entpackt. ' +
      'Windows: Rechtsklick auf die ZIP-Datei › «Alle extrahieren…»; Mac: Doppelklick. Danach im entpackten Ordner «Seite öffnen» doppelklicken.</p></body></html>\n';
  }

  function seiteMitKommentaren() {
    /* Die aktuelle Seite als HTML mit den Kommentaren eingebettet (ohne Editor-Zustand). Die Kommentare stehen
       zusätzlich als fertiges HTML in der Seite: So sind sie auch zu lesen, wenn die Skripte nicht laufen
       (z. B. Seite direkt aus der ZIP geöffnet); export.js zeichnet sie beim Laden neu. */
    var kopie = document.documentElement.cloneNode(true);
    kopie.querySelectorAll('#passwort-form, #liloport-dateien, #liloport-dateien-rahmen, script[src="dateien.js"]').forEach(function (e) { e.remove(); });
    kopie.querySelectorAll('#moderation-band').forEach(function (e) { e.remove(); });
    // Bedienelemente der Kommentare entfernen, die Texte bleiben
    kopie.querySelectorAll('#kommentar-liste form, .kr-beurteilung form, .kommentar-aktionen, .kr-b-neu').forEach(function (e) { e.remove(); });
    kopie.querySelectorAll('#kommentar-liste [hidden], .kr-beurteilung [hidden]').forEach(function (e) { e.hidden = false; });
    var alt = kopie.querySelector('#liloport-kommentare');
    if (alt) alt.remove();
    var leiste = kopie.querySelector('.export-leiste');
    if (leiste) { leiste.innerHTML = ''; delete leiste.dataset.bereit; }
    var form = kopie.querySelector('#kommentar-form');
    if (form) {
      kopie.querySelectorAll('.kommentar-editor-huelle').forEach(function (e) { e.remove(); });  // Editor wird beim Laden neu aufgebaut
      var ta = form.querySelector('textarea[name=text]');
      if (ta) { ta.removeAttribute('data-editor'); ta.hidden = false; ta.required = true; ta.value = ''; ta.textContent = ''; }
      form.querySelectorAll('input[type=text]').forEach(function (i) { i.setAttribute('value', ''); });
      form.querySelectorAll('.kommentar-hinweis').forEach(function (e) { e.remove(); });
      var st = form.querySelector('.kommentar-status'); if (st) st.textContent = '';
    }
    if (document.getElementById('kommentare') || document.querySelector('.kr-beurteilung')) {
      var daten = document.createElement('script');
      daten.type = 'application/json'; daten.id = 'liloport-kommentare';
      daten.textContent = JSON.stringify(kommentare.map(sauberKommentar)).replace(/</g, '\\u003c');
      // Bei Passwortschutz gehören die Kommentare in den verschlüsselten Teil
      (geschuetzt ? kopie.querySelector('#inhalt') : kopie.querySelector('body')).appendChild(daten);
    }
    return kopie;
  }

  function seiteHtml() {
    /* -> Promise(HTML-Text der Seite mit Kommentaren); passwortgeschützte Seiten bleiben verschlüsselt. */
    var kopie = seiteMitKommentaren();
    if (!geschuetzt) return Promise.resolve('<!DOCTYPE html>\n' + kopie.outerHTML);
    var pw = window.LiloportGeschuetzt;
    if (!pw || !window.crypto || !crypto.subtle) return Promise.reject(new Error('Die Seite ist geschützt, lässt sich in diesem Browser aber nicht neu verschlüsseln.'));
    var inhalt = kopie.querySelector('#inhalt');
    var klartext = inhalt.innerHTML;
    var salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    var iterationen = pw.iterationen || 310000;
    return crypto.subtle.importKey('raw', new TextEncoder().encode(pw.passwort), 'PBKDF2', false, ['deriveKey']).then(function (basis) {
      return crypto.subtle.deriveKey({ name: 'PBKDF2', salt: salt, iterations: iterationen, hash: 'SHA-256' }, basis, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
    }).then(function (key) {
      return crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, key, new TextEncoder().encode(klartext));
    }).then(function (verschluesselt) {
      var alteDaten = {};
      var skript = kopie.querySelector('#liloport-entschluesseln');
      if (!skript) throw new Error('Entschlüsselungsteil der Seite fehlt.');
      var m = /var geheim = (.*);\n/.exec(skript.textContent);
      try { alteDaten = JSON.parse(m[1].replace(/<\\\//g, '</')); } catch (e) { alteDaten = {}; }
      var nutzlast = { salt: b64codieren(salt), iv: b64codieren(iv), daten: b64codieren(new Uint8Array(verschluesselt)),
                       iterationen: iterationen, titel: alteDaten.titel || document.title, slug: alteDaten.slug || '' };
      skript.textContent = skript.textContent.replace(/var geheim = .*;\n/, function () {
        return 'var geheim = ' + JSON.stringify(nutzlast).replace(/<\//g, '<\\/') + ';\n';
      });
      inhalt.innerHTML = geschuetzt.form;
      kopie.querySelector('body').className = geschuetzt.klasse;
      var t = kopie.querySelector('title'); if (t) t.textContent = geschuetzt.titel;
      return '<!DOCTYPE html>\n' + kopie.outerHTML;
    });
  }

  function sauberKommentar(k) {
    var x = { id: k.id, zeit: k.zeit, name: k.name, text: k.text };
    if (k.art === 'beurteilung') { x.art = 'beurteilung'; x.skala = k.skala; x.wert = k.wert; x.block = k.block; x.knoten = k.knoten; x.knotenTitel = k.knotenTitel; }
    if (k.seite) x.seite = k.seite;
    if (k.bearbeitet) x.bearbeitet = k.bearbeitet;
    if (k.sh) x.sh = k.sh;
    return x;
  }

  var alleKommentare = null;   // beim Herunterladen: Kommentare aller Seiten des Exports (Portfolio)
  function kommentareJson() {
    return JSON.stringify((alleKommentare || kommentare).map(sauberKommentar), null, 2);
  }

  function lokaleAllerSeiten(dateinamen) {
    /* Im Browser gespeicherte Kommentare zu allen Seiten dieses Exports. */
    var alle = [];
    (dateinamen || []).forEach(function (n) {
      var id = n.replace(/\.html$/, '');
      if (!/^[a-z0-9]{32}$/.test(id)) return;
      try { (JSON.parse(localStorage.getItem('liloport-kommentare-' + id) || '[]') || []).forEach(function (k) { k.seite = k.seite || id; alle.push(k); }); } catch (e) { /* egal */ }
    });
    return alle;
  }

  function paketBauen(sammlung, ordner, seitenDatei, mitKommentaren, seitenText) {
    /* Gleicher Aufbau wie der Export aus Liloport: «Seite öffnen.html» und der Ordner «inhalt». */
    var enc = new TextEncoder();
    sammlung[seitenDatei] = enc.encode(seitenText);
    if (mitKommentaren) sammlung['comments.json'] = enc.encode(kommentareJson());
    delete sammlung['dateien.js']; delete sammlung['export.js']; delete sammlung['comment-editor.js'];   // ältere Exporte: Skripte stehen jetzt in der Seite
    var namen = Object.keys(sammlung).filter(function (n) { return n !== 'manifest.json' && n !== 'dateien.js' && n !== DATEIEN_HTML; }).sort();
    sammlung['manifest.json'] = enc.encode(JSON.stringify({ dateien: namen.concat([DATEIEN_HTML, 'manifest.json']), start: startId + '.html' }));
    var js = dateienHtml(sammlung);
    sammlung[DATEIEN_HTML] = enc.encode(js.text);
    var eintraege = [{ name: ordner + '/' + STARTDATEI, daten: enc.encode(startdateiHtml(startId)) }];
    Object.keys(sammlung).sort().forEach(function (n) { eintraege.push({ name: ordner + '/inhalt/' + n, daten: sammlung[n] }); });
    return { blob: zipBauen(eintraege), fehlend: js.fehlend };
  }

  function speichern(blob, name) {
    var a = el('a', { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); a.remove();
  }

  function herunterladen(knopf) {
    var teile = location.pathname.split('/').map(function (t) { try { return decodeURIComponent(t); } catch (e) { return t; } });
    var seitenDatei = teile.pop() || 'seite.html';
    var ordner = teile.pop() || 'liloport-export';
    if (ordner === 'inhalt') ordner = teile.pop() || 'liloport-export';   // lokale Kopie: …/export-…/inhalt/seite.html
    var mitKommentaren = !!document.getElementById('kommentare');
    knopf.disabled = true; knopf.textContent = 'bereitet vor …';
    function fertig(paket) {
      knopf.disabled = false; knopf.textContent = 'Herunterladen';
      alleKommentare = null;
      if (paket && paket.fehlend.length) alert('Hinweis: ' + paket.fehlend.length + ' sehr grosse Datei(en) sind in der ZIP, lassen sich aber aus einer per Doppelklick geöffneten Kopie nicht erneut herunterladen: ' + paket.fehlend.join(', '));
    }

    if (location.protocol === 'file:') {
      dateienLaden().then(function (d) {
        if (!d) {
          return seiteHtml().then(function (text) {
            speichern(new Blob([text], { type: 'text/html;charset=utf-8' }), seitenDatei);
            fertig();
            alert('In diesem Ordner fehlt die Datei dateien.html. Gespeichert wurde darum nur die Seite mit den Kommentaren.');
          });
        }
        var basis = [];
        try { basis = JSON.parse(new TextDecoder().decode(d.dateien['comments.json'] || new Uint8Array())) || []; } catch (e) { basis = []; }
        alleKommentare = zusammenfuehren(zusammenfuehren(basis, kommentare), lokaleAllerSeiten(Object.keys(d.dateien).concat([seitenDatei])));
        var sammlung = {};
        Object.keys(d.dateien).forEach(function (n) { if (n !== seitenDatei) sammlung[n] = d.dateien[n]; });
        return seiteHtml().then(function (text) {
          var paket = paketBauen(sammlung, ordner, seitenDatei, mitKommentaren || 'comments.json' in d.dateien, text);
          speichern(paket.blob, ordner + '.zip');
          paket.fehlend = paket.fehlend.concat(d.fehlend.filter(function (n) { return paket.fehlend.indexOf(n) < 0; }));
          fertig(paket);
        });
      }).catch(function (e) { fertig(); alert('Herunterladen fehlgeschlagen: ' + e.message); });
      return;
    }

    var manifest = { dateien: [] };
    fetch('manifest.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : { dateien: [] }; })
      .catch(function () { return { dateien: [] }; })
      .then(function (m) {
        manifest = m;
        // comments.php/.py nur ausschliessen, wenn der Server sie ausführt (dann käme nicht der Quelltext zurück)
        var namen = (m.dateien || []).filter(function (n) { return n !== seitenDatei && n !== 'comments.json' && n !== 'manifest.json' && n !== 'dateien.js' && n !== DATEIEN_HTML && !(n === 'comments.php' && backendArt === 'php') && !(n === 'comments.py' && backendArt === 'python'); });
        // Kommentare aller Seiten (bei Portfolio-Exporten liegen alle in einer comments.json)
        var listeUrl = backend ? backend + '?liste=1' : 'comments.json';
        var mitListe = fetch(listeUrl, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; })
          .then(function (liste) { alleKommentare = zusammenfuehren(zusammenfuehren(Array.isArray(liste) ? liste : [], kommentare), lokaleAllerSeiten(m.dateien)); });
        return mitListe.then(function () { return Promise.all(namen.map(function (name) {
          return fetch(name, { cache: 'no-store' }).then(function (r) { return r.ok ? r.arrayBuffer() : null; })
            .then(function (buf) { return buf ? [name, new Uint8Array(buf)] : null; })
            .catch(function () { return null; });
        })); });
      })
      .then(function (paare) {
        var sammlung = {};
        paare.filter(Boolean).forEach(function (p) { sammlung[p[0]] = p[1]; });
        // Ein Server mit PHP/Python liefert comments.php/.py nicht als Quelltext aus: die Kopie aus dateien.html nehmen
        if (!backendArt || backendArt === 'lokal' || ('comments.php' in sammlung && 'comments.py' in sammlung)) return sammlung;
        return dateienLaden().then(function (d) {
          ['comments.php', 'comments.py'].forEach(function (n) { if (!(n in sammlung) && d && d.dateien[n]) sammlung[n] = d.dateien[n]; });
          return sammlung;
        });
      })
      .then(function (sammlung) {
        return seiteHtml().then(function (text) {
          var paket = paketBauen(sammlung, ordner, seitenDatei, mitKommentaren || (manifest.dateien || []).indexOf('comments.json') >= 0, text);
          speichern(paket.blob, ordner + '.zip');
          fertig(paket);
        });
      })
      .catch(function (e) { fertig(); alert('Herunterladen fehlgeschlagen: ' + e.message); });
  }

  /* ---------- Vollbild für Bilder (Galerie und Bild-Blöcke); gleiche Bedienung wie in Liloport ---------- */

  function vollbildAnzeigen(liste, start) {
    var i = start;
    var bild = el('img', { 'class': 'vollbild-bild', alt: '' });
    var text = el('div', { 'class': 'vollbild-text' });
    var mehrere = liste.length > 1;
    var zu = el('button', { 'class': 'vollbild-knopf vollbild-zu', type: 'button', title: 'Schliessen (Esc)', 'aria-label': 'Vollbild schliessen', text: '✕' });
    var vor = el('button', { 'class': 'vollbild-knopf vollbild-vor', type: 'button', title: 'Vorheriges Bild (←)', 'aria-label': 'Vorheriges Bild', text: '‹' });
    var nach = el('button', { 'class': 'vollbild-knopf vollbild-nach', type: 'button', title: 'Nächstes Bild (→)', 'aria-label': 'Nächstes Bild', text: '›' });
    var rahmen = el('figure', { 'class': 'vollbild-rahmen' }, [bild, text]);
    var huelle = el('div', { 'class': 'vollbild', role: 'dialog', 'aria-label': 'Bild in Vollansicht', tabindex: '-1' },
      [zu, mehrere ? vor : null, rahmen, mehrere ? nach : null]);
    bild.addEventListener('load', function () {
      // Kleine Bilder moderat vergrössern (höchstens aufs Doppelte); grosse begrenzt das CSS
      if (!bild.naturalWidth) return;
      var maxB = Math.max(200, window.innerWidth - 150), maxH = Math.max(200, window.innerHeight - 130);
      var faktor = Math.min(2, maxB / bild.naturalWidth, maxH / bild.naturalHeight);
      bild.style.width = faktor > 1 ? Math.round(bild.naturalWidth * faktor) + 'px' : '';
    });
    function zeigen(n) {
      i = (n + liste.length) % liste.length;
      bild.style.width = '';
      bild.src = liste[i].src;
      var b = liste[i].beschriftung || '';
      text.textContent = mehrere ? b + (b ? ' · ' : '') + (i + 1) + ' / ' + liste.length : b;
    }
    function schliessen() {
      document.removeEventListener('keydown', tasten);
      document.body.classList.remove('vollbild-offen');
      huelle.remove();
    }
    function tasten(ev) {
      if (ev.key === 'Escape') schliessen();
      else if (ev.key === 'ArrowLeft' && mehrere) zeigen(i - 1);
      else if (ev.key === 'ArrowRight' && mehrere) zeigen(i + 1);
      else return;
      ev.preventDefault();
    }
    zu.addEventListener('click', schliessen);
    vor.addEventListener('click', function (ev) { ev.stopPropagation(); zeigen(i - 1); });
    nach.addEventListener('click', function (ev) { ev.stopPropagation(); zeigen(i + 1); });
    huelle.addEventListener('click', function (ev) { if (ev.target === huelle || ev.target === rahmen) schliessen(); });
    document.addEventListener('keydown', tasten);
    zeigen(i);
    document.body.classList.add('vollbild-offen');
    document.body.appendChild(huelle);
    huelle.focus();
  }

  function vollbild() {
    document.addEventListener('click', function (ev) {
      var img = ev.target.closest && ev.target.closest('.block-galerie .galerie-bild img, .block-bild img');
      if (!img || img.closest('a')) return;
      ev.preventDefault();
      var galerie = img.closest('.block-galerie');
      var alle = galerie ? [].slice.call(galerie.querySelectorAll('.galerie-bild img')) : [img];
      var liste = alle.map(function (x) {
        var fig = x.closest('figure'), cap = fig && fig.querySelector('figcaption');
        return { src: x.currentSrc || x.src, beschriftung: (cap ? cap.textContent : x.alt) || '' };
      });
      vollbildAnzeigen(liste, Math.max(0, alle.indexOf(img)));
    });
  }

  function init() {
    var leiste = document.querySelector('.export-leiste');
    if (leiste && !leiste.dataset.bereit) {
      leiste.dataset.bereit = '1';
      var knopf = el('button', { 'class': 'knopf', type: 'button', text: 'Herunterladen', title: 'Diese Seite mit allen Dateien und Kommentaren als ZIP speichern; nach dem Entpacken lokal per Doppelklick nutzbar und in Liloport importierbar' });
      knopf.addEventListener('click', function () { herunterladen(knopf); });
      leiste.appendChild(knopf);
    }
    moderationLesen();   // auch auf der Startseite eines Portfolios (dort gibt es keine Kommentare)
    if (!document.body.dataset.vollbildBereit) { document.body.dataset.vollbildBereit = '1'; vollbild(); }
    if (document.getElementById('kommentare') || document.querySelector('.kr-beurteilung')) kommentareLaden().then(formular);
    else if (moderation && !document.getElementById('moderation-band')) {
      var inhalt = document.getElementById('inhalt');
      if (inhalt) inhalt.insertBefore(el('div', { id: 'moderation-band', 'class': 'moderation-band', text: 'Moderation aktiv: Öffne eine Seite, um deren Kommentare zu bearbeiten oder zu löschen. Gilt bis zum Schliessen dieses Tabs.' }), inhalt.firstChild);
    }
  }

  window.LiloportExport = { init: init };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
