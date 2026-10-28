/* Liloport – kr.js: Seite eines Kompetenzrahmens (_kompetenzen/<id>.html).
   Zeigt den Baum Bereich › Kompetenz › Stufe › Punkt mit dem aktuellen Stand; mit laufendem Liloport
   lässt er sich bearbeiten (Texte, Reihenfolge, neue und gelöschte Einträge) und als JSON weitergeben. */
(function () {
  'use strict';
  var L = window.Liloport, el = L.edit ? L.el : L.el;
  var edit = L.istEditiermodus;
  var daten = JSON.parse(document.getElementById('kr-daten').textContent);
  var kr = daten.rahmen, status = daten.status || {};
  var krid = document.body.dataset.krid;
  var EBENEN = ['bereich', 'kompetenz', 'stufe', 'punkt'];
  var KINDER = { bereich: 'kompetenzen', kompetenz: 'stufen', stufe: 'punkte' };
  var NAMEN = { bereich: 'Bereich', kompetenz: 'Kompetenz', stufe: 'Kompetenzstufe', punkt: 'Kompetenzpunkt' };
  var STATUS_NAMEN = { offen: 'offen (keiner Seite zugeordnet)', weiss: 'noch nicht bearbeitet', orange: 'in Bearbeitung', gruen: 'erarbeitet' };
  var wurzel = document.getElementById('kr-editor');
  var geaendertSeit = false, speicherTimer = null, statusEl = null;

  function neueId() { var s = ''; for (var i = 0; i < 6; i++) s += '0123456789abcdef'[Math.floor(Math.random() * 16)]; return s; }

  function punkt(nid) {
    var st = status[nid] || 'offen';
    return el('span', { 'class': 'ka-punkt st-' + st, title: STATUS_NAMEN[st] });
  }

  function textfeld(obj, feld, klasse, platzhalter, mehrzeilig) {
    if (!edit) {
      if (!obj[feld]) return null;
      return el(mehrzeilig ? 'p' : 'span', { 'class': klasse, text: obj[feld] });
    }
    var e = el(mehrzeilig ? 'textarea' : 'input', { 'class': klasse, placeholder: platzhalter });
    if (mehrzeilig) { e.rows = 2; e.value = obj[feld] || ''; } else { e.type = 'text'; e.value = obj[feld] || ''; e.maxLength = 200; }
    e.addEventListener('input', function () { obj[feld] = e.value; geaendert(); if (mehrzeilig) { e.style.height = 'auto'; e.style.height = e.scrollHeight + 'px'; } });
    if (mehrzeilig) setTimeout(function () { e.style.height = 'auto'; e.style.height = e.scrollHeight + 'px'; }, 0);
    return e;
  }

  function knoten(obj, ebene, liste, index) {
    var kinderName = KINDER[ebene];
    var box = el('div', { 'class': 'kr-knoten kr-' + ebene + ' st-' + (status[obj.id] || 'offen'), 'data-id': obj.id });
    var kopf = el('div', { 'class': 'kr-knoten-kopf' }, [
      punkt(obj.id),
      el('span', { 'class': 'kr-ebene', text: NAMEN[ebene] + (ebene === 'stufe' ? ' ' + (index + 1) : '') }),
      textfeld(obj, 'titel', 'kr-knoten-titel', 'Titel'),
    ]);
    if (edit) {
      kopf.appendChild(el('span', { 'class': 'kr-knoten-aktionen' }, [
        el('button', { type: 'button', 'class': 'klein', text: '▲', title: 'Nach oben', onclick: function () { bewegen(liste, index, -1); } }),
        el('button', { type: 'button', 'class': 'klein', text: '▼', title: 'Nach unten', onclick: function () { bewegen(liste, index, 1); } }),
        el('button', { type: 'button', 'class': 'klein gefahr', text: 'Löschen', onclick: function () {
          var n = zaehlen(obj, ebene);
          if (n > 1 && !confirm('«' + (obj.titel || NAMEN[ebene]) + '» mit ' + (n - 1) + ' Unterpunkten löschen? Seiten, die darauf verweisen, verlieren den Bezug.')) return;
          liste.splice(index, 1); geaendert(); zeichnen();
        } })
      ]));
    }
    box.appendChild(kopf);
    var beschr = textfeld(obj, 'beschreibung', 'kr-knoten-beschreibung', 'Beschreibung (optional)', true);
    if (beschr) box.appendChild(beschr);
    if (kinderName) {
      obj[kinderName] = obj[kinderName] || [];
      var unter = el('div', { 'class': 'kr-kinder' });
      var naechste = EBENEN[EBENEN.indexOf(ebene) + 1];
      obj[kinderName].forEach(function (k, i) { unter.appendChild(knoten(k, naechste, obj[kinderName], i)); });
      if (edit) unter.appendChild(el('button', { type: 'button', 'class': 'klein kr-hinzufuegen', text: '+ ' + NAMEN[naechste], onclick: function () {
        obj[kinderName].push(neu(naechste)); geaendert(); zeichnen();
        var felder = wurzel.querySelectorAll('.kr-knoten[data-id="' + obj[kinderName][obj[kinderName].length - 1].id + '"] input'); if (felder[0]) felder[0].focus();
      } }));
      if (!edit && !obj[kinderName].length) unter.remove();
      else box.appendChild(unter);
    }
    return box;
  }

  function neu(ebene) {
    var k = { id: neueId(), titel: '', beschreibung: '' };
    if (KINDER[ebene]) k[KINDER[ebene]] = [];
    return k;
  }
  function zaehlen(obj, ebene) { var n = 1; (obj[KINDER[ebene]] || []).forEach(function (k) { n += zaehlen(k, EBENEN[EBENEN.indexOf(ebene) + 1]); }); return n; }
  function bewegen(liste, i, richtung) {
    var j = i + richtung; if (j < 0 || j >= liste.length) return;
    var t = liste[i]; liste[i] = liste[j]; liste[j] = t; geaendert(); zeichnen();
  }

  function zeichnen() {
    wurzel.innerHTML = '';
    var kopf = el('header', { 'class': 'kr-titelbereich' });
    if (edit) {
      var t = el('input', { type: 'text', 'class': 'kr-titel-feld seitentitel', value: kr.titel || '', placeholder: 'Titel des Kompetenzrahmens', maxlength: '200' });
      t.addEventListener('input', function () { kr.titel = t.value; document.title = t.value + ' – Kompetenzrahmen – Liloport'; geaendert(); });
      kopf.appendChild(t);
      var q = el('input', { type: 'text', 'class': 'kr-meta-feld', value: kr.quelle || '', placeholder: 'Quelle, z. B. Hochschule, Studiengang', maxlength: '300' });
      q.addEventListener('input', function () { kr.quelle = q.value; geaendert(); });
      var v = el('input', { type: 'text', 'class': 'kr-meta-feld kurz', value: kr.version || '', placeholder: 'Version', maxlength: '60' });
      v.addEventListener('input', function () { kr.version = v.value; geaendert(); });
      kopf.appendChild(el('div', { 'class': 'kr-meta-zeile' }, [q, el('label', { 'class': 'kr-version-label' }, [el('span', { text: 'Version' }), v])]));
      var b = el('textarea', { 'class': 'kr-beschreibung-feld', rows: '2', placeholder: 'Wozu dieser Rahmen dient (optional)' }); b.value = kr.beschreibung || '';
      b.addEventListener('input', function () { kr.beschreibung = b.value; geaendert(); });
      kopf.appendChild(b);
      statusEl = el('span', { 'class': 'klein-text', text: 'gespeichert' });
      kopf.appendChild(el('div', { 'class': 'kr-werkzeuge' }, [
        el('button', { type: 'button', 'class': 'primaer', text: 'Speichern', onclick: function () { speichern(); } }),
        el('button', { type: 'button', text: 'Als JSON weitergeben', title: 'Datei zum Importieren in ein anderes Liloport', onclick: herunterladen }),
        el('button', { type: 'button', 'class': 'gefahr', text: 'Rahmen löschen', onclick: loeschen }),
        statusEl
      ]));
    } else {
      kopf.appendChild(el('h1', { 'class': 'seitentitel', text: kr.titel || 'Kompetenzrahmen' }));
      var meta = [kr.quelle, kr.version ? 'Version ' + kr.version : ''].filter(Boolean).join(' · ');
      if (meta) kopf.appendChild(el('p', { 'class': 'seiten-meta', text: meta }));
      if (kr.beschreibung) kopf.appendChild(el('p', { 'class': 'kr-beschreibung', text: kr.beschreibung }));
      kopf.appendChild(el('p', { 'class': 'hinweis', text: 'Zum Bearbeiten Liloport starten. Den Stand (Farben) setzen die Seiten mit Kompetenz-Block; die Übersicht steht in der Kompetenzabbildung.' }));
    }
    wurzel.appendChild(kopf);
    var baum = el('div', { 'class': 'kr-baum' });
    kr.bereiche = kr.bereiche || [];
    kr.bereiche.forEach(function (b, i) { baum.appendChild(knoten(b, 'bereich', kr.bereiche, i)); });
    if (!kr.bereiche.length && !edit) baum.appendChild(el('p', { 'class': 'hinweis', text: 'Dieser Rahmen hat noch keine Bereiche.' }));
    if (edit) baum.appendChild(el('button', { type: 'button', 'class': 'kr-hinzufuegen gross', text: '+ Bereich hinzufügen', onclick: function () { kr.bereiche.push(neu('bereich')); geaendert(); zeichnen(); } }));
    wurzel.appendChild(baum);
  }

  var stand = 0;   // zählt Änderungen; so gehen Eingaben während eines laufenden Speicherns nicht verloren

  function geaendert() {
    stand++;
    geaendertSeit = true;
    if (statusEl) statusEl.textContent = 'ungespeichert';
    clearTimeout(speicherTimer); speicherTimer = setTimeout(speichern, 1500);
  }

  function speichern() {
    clearTimeout(speicherTimer);
    if (!edit || !geaendertSeit) return Promise.resolve();
    if (statusEl) statusEl.textContent = 'speichert …';
    var gesendet = stand;
    return L.api('PUT', '/api/kompetenzrahmen/' + krid, kr).then(function (j) {
      // Das lokale Objekt bleibt bestehen: Die Eingabefelder auf der Seite zeigen direkt darauf. Würde es durch
      // die Antwort des Servers ersetzt, landeten spätere Eingaben und «+ Kompetenz» im alten, nicht mehr
      // gespeicherten Objekt (das war der Fehler beim Erweitern des Beispielrahmens).
      status = j.status || status;
      if (stand === gesendet) {
        geaendertSeit = false;
        if (statusEl) statusEl.textContent = 'gespeichert';
      } else {
        clearTimeout(speicherTimer); speicherTimer = setTimeout(speichern, 800);
      }
    }).catch(function (e) { if (statusEl) statusEl.textContent = 'Fehler: ' + e.message; });
  }

  function herunterladen() {
    speichern().then(function () {
      var blob = new Blob([JSON.stringify(kr, null, 2)], { type: 'application/json' });
      var a = el('a', { href: URL.createObjectURL(blob), download: 'kompetenzrahmen-' + krid + '.json' });
      document.body.appendChild(a); a.click(); a.remove();
    });
  }

  function loeschen() {
    if (!confirm('Den Kompetenzrahmen «' + (kr.titel || krid) + '» löschen? Die Kompetenz-Blöcke auf den Seiten verlieren damit ihren Bezug.')) return;
    L.api('DELETE', '/api/kompetenzrahmen/' + krid).then(function () { location.href = '../index.html'; }).catch(function (e) { alert(e.message); });
  }

  window.addEventListener('beforeunload', function (ev) { if (geaendertSeit) { speichern(); ev.preventDefault(); ev.returnValue = ''; } });
  zeichnen();
})();
