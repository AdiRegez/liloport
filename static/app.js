/* Liloport – app.js: das Dashboard. Zeigt den Verzeichnisbaum (auch unter file://),
   die Suche, den Ordner auf dem Rechner und – im Editiermodus – Anlegen, Bearbeiten,
   Löschen, Export sowie die dezenten Wartungsbereiche (Backup, Papierkorb, Dateien). */
(function () {
  'use strict';
  var L = window.Liloport;
  var el = L.el, dialog = L.dialog, feld = L.feld;
  var daten = L.daten;
  var edit = L.istEditiermodus;

  function slug(text) {
    var t = (text || '').trim().toLowerCase()
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/-{2,}/g, '-').replace(/^-|-$/g, '')
      .slice(0, 60).replace(/-$/, '');
    return t || 'seite';
  }

  function datumKurz(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
      ' ' + d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
  }

  function neuLaden() {
    if (!edit) { location.reload(); return; }
    L.api('GET', '/api/site').then(function (j) {
      daten = j; L.daten = j; window.LILOPORT = j;
      aufbauen();
    }).catch(fehlerZeigen);
  }

  function fehlerZeigen(e) { alert(e.message || e); }

  // ---------- Baum ----------

  // ---------- Übersicht: Sortierung und eingeklappte Verzeichnisse (pro Browser gemerkt) ----------

  function merkLesen(schluessel, vorgabe) { try { var w = localStorage.getItem(schluessel); return w === null ? vorgabe : JSON.parse(w); } catch (e) { return vorgabe; } }
  function merkSchreiben(schluessel, wert) { try { localStorage.setItem(schluessel, JSON.stringify(wert)); } catch (e) { /* egal */ } }
  var sortierung = merkLesen('liloport-sortierung', 'az');        // 'az' | 'erstellt'
  var zuGemerkt = merkLesen('liloport-verzeichnisse-zu', {});     // Verzeichnis-ID -> true (zu) / false (offen)
  var VIELE = 12;                                                  // ab so vielen Verzeichnissen startet die Übersicht eingeklappt
  function vergleichName(a, b) { return a.localeCompare(b, 'de', { numeric: true, sensitivity: 'base' }); }

  function kinderVon(id) {
    return daten.verzeichnisse.filter(function (v) { return (v.eltern || null) === id; })
      .sort(function (a, b) { return sortierung === 'az' ? vergleichName(a.name, b.name) : ((a.reihenfolge - b.reihenfolge) || vergleichName(a.name, b.name)); });
  }
  function seitenVon(v) {
    var liste = v.seiten.slice();
    if (sortierung === 'az') liste.sort(function (a, b) { return vergleichName(a.titel || '', b.titel || ''); });
    return liste;
  }
  function istZu(v) {
    if (Object.prototype.hasOwnProperty.call(zuGemerkt, v.id)) return !!zuGemerkt[v.id];
    return daten.verzeichnisse.length > VIELE;
  }
  function inhaltZaehlen(v) {
    var seiten = v.seiten.filter(function (s) { return !s.redirect; }).length, unter = kinderVon(v.id).length;
    var teile = [];
    if (seiten) teile.push(seiten + (seiten === 1 ? ' Seite' : ' Seiten'));
    if (unter) teile.push(unter + (unter === 1 ? ' Verzeichnis' : ' Verzeichnisse'));
    return teile.join(' · ') || 'leer';
  }
  function alleSetzen(zu) {
    daten.verzeichnisse.forEach(function (v) { zuGemerkt[v.id] = zu; });
    merkSchreiben('liloport-verzeichnisse-zu', zuGemerkt);
    aufbauen();
  }

  function baumWerkzeuge() {
    var w = document.getElementById('baum-werkzeuge');
    if (!w) return;
    w.innerHTML = '';
    if (!daten.verzeichnisse.length) return;
    var gruppe = el('span', { 'class': 'sortier-schalter', role: 'group', 'aria-label': 'Sortierung' });
    [['az', 'A–Z'], ['erstellt', 'Erstellt']].forEach(function (x) {
      var b = el('button', { type: 'button', 'class': 'klein' + (sortierung === x[0] ? ' aktiv' : ''), text: x[1], title: x[0] === 'az' ? 'Verzeichnisse und Seiten alphabetisch' : 'In der Reihenfolge, in der sie angelegt wurden', 'aria-pressed': sortierung === x[0] ? 'true' : 'false' });
      b.addEventListener('click', function () { sortierung = x[0]; merkSchreiben('liloport-sortierung', sortierung); aufbauen(); });
      gruppe.appendChild(b);
    });
    w.appendChild(el('span', { 'class': 'klein-text', text: 'Sortieren:' }));
    w.appendChild(gruppe);
    w.appendChild(el('span', { 'class': 'abstand' }));
    w.appendChild(el('button', { type: 'button', 'class': 'klein', text: '▾ Alle aufklappen', onclick: function () { alleSetzen(false); } }));
    w.appendChild(el('button', { type: 'button', 'class': 'klein', text: '▸ Alle zuklappen', onclick: function () { alleSetzen(true); } }));
  }

  function verzeichnisKnoten(v) {
    var zu = istZu(v);
    var klapp = el('button', { type: 'button', 'class': 'verz-klapp', text: zu ? '▸' : '▾', title: zu ? 'Aufklappen' : 'Zuklappen', 'aria-expanded': zu ? 'false' : 'true' });
    var name = el('span', { 'class': 'name', text: v.name, title: 'Klicken zum Auf- oder Zuklappen' });
    var zeile = el('div', { 'class': 'verz-zeile' }, [
      klapp,
      el('span', { text: '📁' }),
      name,
      el('span', { 'class': 'verz-anzahl', text: inhaltZaehlen(v) }),
      v.inMenue ? null : el('span', { 'class': 'nicht-im-menue', text: 'nicht im Menü' })
    ]);
    function umschalten() {
      zu = !knoten.classList.contains('zu');
      knoten.classList.toggle('zu', zu);
      klapp.textContent = zu ? '▸' : '▾'; klapp.title = zu ? 'Aufklappen' : 'Zuklappen'; klapp.setAttribute('aria-expanded', zu ? 'false' : 'true');
      zuGemerkt[v.id] = zu; merkSchreiben('liloport-verzeichnisse-zu', zuGemerkt);
    }
    klapp.addEventListener('click', umschalten);
    name.addEventListener('click', umschalten);
    if (edit) {
      zeile.appendChild(el('span', { 'class': 'aktionen' }, [
        el('button', { 'class': 'klein', text: 'Seite', title: 'Neue Seite in diesem Verzeichnis', onclick: function () { dialogSeite(v.id); } }),
        el('button', { 'class': 'klein', text: 'Unterverzeichnis', onclick: function () { dialogVerzeichnis(v.id); } }),
        el('button', { 'class': 'klein', text: 'Bearbeiten', onclick: function () { dialogVerzeichnisAendern(v); } }),
        el('button', { 'class': 'klein', text: 'Exportieren', title: 'Dieses Verzeichnis mit allen Unterverzeichnissen als ZIP für einen Webserver', onclick: function () { L.dialogExport({ verzeichnis: v.id, titel: v.name }); } }),
        el('button', { 'class': 'klein gefahr', text: 'Löschen', onclick: function () { verzeichnisLoeschen(v); } })
      ]));
    }
    var knoten = el('li', { 'class': 'verz' + (zu ? ' zu' : '') }, [zeile]);
    var liste = el('ul');
    seitenVon(v).forEach(function (s) { liste.appendChild(seitenKnoten(s, v)); });
    kinderVon(v.id).forEach(function (k) { liste.appendChild(verzeichnisKnoten(k)); });
    if (!liste.children.length) liste.appendChild(el('li', { 'class': 'leer', text: 'leer' }));
    knoten.appendChild(liste);
    return knoten;
  }

  function seitenKnoten(s, v) {
    var zeile = el('div', { 'class': 'seite-zeile' + (s.redirect ? ' redirect' : '') }, [
      el('span', { text: s.redirect ? '↪' : '📄', title: s.redirect ? 'Weiterleitung auf ' + s.ziel : '' }),
      el('a', { 'class': 'titel', href: s.pfad + '.html', text: s.titel + (s.redirect ? ' (Weiterleitung)' : '') }),
      (s.tags || []).length && !s.redirect ? el('span', { 'class': 'tags' }, s.tags.slice(0, 4).map(function (t) {
        return el('a', { 'class': 'tag', href: '#', text: '#' + t, onclick: function (ev) { ev.preventDefault(); sucheNach('#' + t); } });
      })) : null,
      el('span', { 'class': 'datum', text: s.redirect ? '→ ' + s.ziel : datumKurz(s.geaendert) })
    ]);
    if (edit) {
      var aktionen = el('span', { 'class': 'aktionen' });
      if (s.redirect) {
        aktionen.appendChild(el('button', { 'class': 'klein gefahr', text: 'Entfernen', onclick: function () { redirectEntfernen(v, s); } }));
      } else {
        aktionen.appendChild(el('a', { 'class': 'knopf klein', href: s.pfad + '.html#bearbeiten', text: 'Bearbeiten' }));
        aktionen.appendChild(el('button', { 'class': 'klein', text: 'Verschieben', title: 'In ein anderes Verzeichnis verschieben', onclick: function () { dialogVerschieben(s); } }));
        aktionen.appendChild(el('button', { 'class': 'klein', text: 'Exportieren', title: 'Als ZIP für einen Webserver', onclick: function () { L.dialogExport(s); } }));
        aktionen.appendChild(el('button', { 'class': 'klein gefahr', text: 'Löschen', onclick: function () { seiteLoeschen(s); } }));
      }
      zeile.appendChild(aktionen);
    }
    return el('li', null, [zeile]);
  }

  function aufbauen() {
    var baum = document.getElementById('baum');
    baum.innerHTML = '';
    baumWerkzeuge();
    reiterEinrichten();
    var wurzel = el('ul');
    kinderVon(null).forEach(function (v) { wurzel.appendChild(verzeichnisKnoten(v)); });
    if (!wurzel.children.length) {
      baum.appendChild(el('p', { 'class': 'leer-hinweis', text: edit ? 'Noch keine Verzeichnisse. Mit «Neu» ein erstes Verzeichnis anlegen.' : 'Noch keine Verzeichnisse.' }));
    } else {
      baum.appendChild(wurzel);
    }
    var anzahlSeiten = daten.verzeichnisse.reduce(function (n, v) { return n + v.seiten.filter(function (s) { return !s.redirect; }).length; }, 0);
    document.getElementById('statistik').textContent = daten.verzeichnisse.length + ' Verzeichnisse · ' + anzahlSeiten + ' Seiten';
    ordnerZeile();
    wartung();
    beispielKarte();
    geraetWarnung();
  }

  function beispielKarte() {
    var alt = document.getElementById('beispiel-karte'); if (alt) alt.remove();
    if (!edit || daten.beispielGefragt === undefined || daten.beispielGefragt) return;
    var karte = el('section', { id: 'beispiel-karte', 'class': 'beispiel-karte' }, [
      el('h2', { text: 'Willkommen bei Liloport!' }),
      el('p', { text: 'Möchtest du ein kleines Beispiel-Portfolio anlegen? Es zeigt Seiten, Bilder, Spalten, Tags, Fussnoten und interne Links. Du kannst es jederzeit wieder löschen.' }),
      el('div', { 'class': 'feld-zeile' }, [
        el('button', { 'class': 'primaer', text: 'Beispiel anlegen', onclick: function () {
          L.api('POST', '/api/beispiel', { anlegen: true }).then(function (j) { location.href = j.pfad + '.html'; }).catch(fehlerZeigen);
        } }),
        el('button', { text: 'Nein danke, leer starten', onclick: function () { L.api('POST', '/api/beispiel', { anlegen: false }).then(neuLaden).catch(fehlerZeigen); } })
      ])
    ]);
    var ziel = document.querySelector('.dashboard-inhalt');
    ziel.insertBefore(karte, ziel.firstChild);
  }

  function geraetWarnung() {
    if (!edit) return;
    L.api('GET', '/api/sitzung').then(function (j) {
      var alt = document.getElementById('geraet-warnung'); if (alt) alt.remove();
      if (!j.fremd) return;
      var ziel = document.querySelector('.dashboard-inhalt');
      ziel.insertBefore(el('div', { id: 'geraet-warnung', 'class': 'geraet-warnung', text: '⚠ Liloport läuft gerade auch auf «' + j.fremd.name + '» mit diesem Inhalte-Ordner (Cloud-Ordner?). Arbeite am besten nur auf einem Gerät gleichzeitig, sonst können Änderungen verloren gehen.' }), ziel.firstChild);
    }).catch(function () {});
  }

  function ordnerZeile() {
    var z = document.getElementById('ordner-zeile');
    z.innerHTML = '';
    var pfad = daten.ordner;
    if (!pfad && location.protocol === 'file:') {
      pfad = decodeURIComponent(location.pathname.replace(/\/index\.html$/, '').replace(/^\/([A-Za-z]:)/, '$1'));
    }
    if (!pfad) return;
    z.appendChild(el('span', { text: 'Alles liegt auf diesem Rechner im Ordner' }));
    z.appendChild(el('code', { text: pfad }));
    if (edit) {
      z.appendChild(el('button', { 'class': 'klein', text: '📂 Ordner öffnen', onclick: function () { L.api('POST', '/api/oeffnen', { pfad: '' }).catch(fehlerZeigen); } }));
      if (daten.verzeichnisse.length) z.appendChild(el('button', { 'class': 'klein', text: '📦 Ganzes Portfolio exportieren', onclick: function () { L.dialogExport({ verzeichnis: '', titel: daten.titel || 'Portfolio' }); } }));
    } else {
      z.appendChild(el('a', { 'class': 'knopf klein', href: 'file://' + (pfad.charAt(0) === '/' ? '' : '/') + pfad.replace(/\\/g, '/') + '/', text: '📂 Ordner öffnen' }));
    }
  }

  // ---------- Dialoge ----------

  function verzeichnisAuswahl(vorgabe) {
    var sel = el('select');
    sel.appendChild(el('option', { value: '', text: '– oberste Ebene –' }));
    (function rek(elternId, tiefe) {
      kinderVon(elternId).forEach(function (v) {
        sel.appendChild(el('option', { value: v.id, text: '  '.repeat(tiefe) + v.name }));
        rek(v.id, tiefe + 1);
      });
    })(null, 0);
    if (vorgabe) sel.value = vorgabe;
    return sel;
  }

  function dialogAuswahl() {
    if (!daten.verzeichnisse.length) { dialogVerzeichnis(null); return; }
    var d = dialog('Was soll angelegt werden?', [
      el('div', { 'class': 'feld-zeile' }, [
        el('button', { type: 'button', 'class': 'primaer', text: '📄 Neue Seite', onclick: function () { d.close(); dialogSeite(null); } }),
        el('button', { type: 'button', text: '📁 Neues Verzeichnis', onclick: function () { d.close(); dialogVerzeichnis(null); } }),
        el('button', { type: 'button', text: '📥 Seite aus ZIP importieren', onclick: function () { d.close(); dialogImportZip(); } })
      ])
    ], 'Schliessen', function () {});
    d.querySelector('button[type=submit]').style.display = 'none';
  }

  // ---------- Import einer heruntergeladenen Export-ZIP ----------

  function dialogImportZip() {
    var datei = el('input', { type: 'file', accept: '.zip,application/zip' });
    var info = el('div', { 'class': 'import-info' });
    var titel = el('input', { type: 'text', maxlength: '120' });
    var verz = verzeichnisAuswahl((kinderVon(null)[0] || {}).id); verz.firstChild.remove();
    var schritt2 = el('div', null, [feld('Titel', titel), feld('Verzeichnis', verz)]); schritt2.hidden = true;
    var token = null;
    datei.addEventListener('change', function () {
      var f = datei.files[0]; if (!f) return;
      info.textContent = 'ZIP wird geprüft …'; schritt2.hidden = true; token = null;
      fetch('/api/import/vorschau', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Dateiname': encodeURIComponent(f.name) }, body: f })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.fehler) throw new Error(j.fehler);
          token = j.token; titel.value = j.titel;
          info.innerHTML = '';
          info.appendChild(el('p', null, [el('strong', { text: j.titel }), el('span', { text: ' – ' + (j.seiten > 1 ? j.seiten + ' Seiten, ' : '') + j.bloecke + ' Blöcke, ' + j.anhaenge + ' Anhänge, ' + j.kommentare + ' Kommentare' + (j.css ? ', eigenes CSS' : '') })]));
          if (j.seiten > 1) info.appendChild(el('p', { 'class': 'klein-text', text: 'Die Seiten werden im gewählten Verzeichnis angelegt' + (j.verzeichnisse.length > 1 ? ', Unterverzeichnisse werden nachgebildet: ' + j.verzeichnisse.join(' · ') : '') + '. Interne Links zwischen den Seiten bleiben erhalten.' }));
          if (j.abgabe) info.appendChild(el('p', { 'class': j.abgabe.gueltig ? 'hinweis' : 'fehlermeldung', text: (j.abgabe.gueltig ? '✓ Abgabestempel vom ' : '✗ Abgabestempel vom ') + j.abgabe.zeit.replace('T', ' ') + (j.abgabe.gueltig ? ': Inhalt seit dem Export unverändert.' : ': Der Inhalt wurde seit dem Export verändert.') + ' Prüfsumme ' + j.abgabe.pruefsumme.slice(0, 16) + '…' }));
          titel.parentNode.hidden = j.seiten > 1;
          if (j.html) info.appendChild(el('p', { 'class': 'hinweis', text: 'Die Seite enthält ' + j.html + ' HTML-Block/Blöcke. Zur Sicherheit werden Skripte und Event-Handler beim Import entfernt.' }));
          if (j.fehlend.length) info.appendChild(el('p', { 'class': 'hinweis', text: 'In der ZIP fehlen: ' + j.fehlend.join(', ') + ' – diese Blöcke bleiben leer.' }));
          schritt2.hidden = false;
        })
        .catch(function (e) { info.textContent = e.message; });
    });
    dialog('Seite(n) aus ZIP importieren', [
      el('p', { 'class': 'hinweis', text: 'Eine ZIP, die über «Herunterladen» von einer exportierten Seite stammt (oder die Export-ZIP selbst, auch von einem Verzeichnis oder ganzen Portfolio). Die Seiten werden neu angelegt, Anhänge übernommen, Kommentare erscheinen unter der Seite. Vorlagen von Dozierenden oder der Hochschule lassen sich genauso importieren.' }),
      feld('ZIP-Datei', datei), info, schritt2
    ], 'Importieren', function () {
      if (!token) throw new Error('Bitte zuerst eine gültige ZIP wählen.');
      return L.api('POST', '/api/import', { token: token, verzeichnis: verz.value, titel: titel.value }).then(function (j) { location.href = j.pfad + '.html'; });
    });
  }

  // ---------- Verzeichnisse und Seiten anlegen, ändern, löschen ----------

  function dialogVerzeichnis(elternId) {
    var name = el('input', { type: 'text', required: '', maxlength: '80' });
    var ordnerVorschau = el('span', { html: 'Ordnername: <code>…</code>' });
    name.addEventListener('input', function () { ordnerVorschau.innerHTML = 'Ordnername: <code>' + slug(name.value) + '</code>'; });
    var eltern = verzeichnisAuswahl(elternId);
    var imMenue = L.kreuz('In der Menübar anzeigen', true);
    dialog('Neues Verzeichnis', [feld('Name', name, ordnerVorschau), feld('Übergeordnetes Verzeichnis', eltern), imMenue.el], 'Anlegen', function () {
      return L.api('POST', '/api/verzeichnisse', { name: name.value, eltern: eltern.value || null, inMenue: imMenue.box.checked }).then(neuLaden);
    });
  }

  function dialogVerzeichnisAendern(v) {
    var name = el('input', { type: 'text', required: '', value: v.name, maxlength: '80' });
    var imMenue = L.kreuz('In der Menübar anzeigen', v.inMenue);
    dialog('Verzeichnis bearbeiten', [
      feld('Name', name, el('span', { text: 'Ein neuer Name benennt auch den Ordner um; Links werden neu erzeugt.' })),
      imMenue.el
    ], 'Speichern', function () {
      return L.api('PUT', '/api/verzeichnisse/' + v.id, { name: name.value, inMenue: imMenue.box.checked }).then(neuLaden);
    });
  }

  function verzeichnisLoeschen(v) {
    if (v.seiten.length || kinderVon(v.id).length) {
      alert('«' + v.name + '» enthält noch Seiten oder Unterverzeichnisse. Zuerst diese löschen oder verschieben.');
      return;
    }
    if (!confirm('Verzeichnis «' + v.name + '» und seinen Ordner löschen?')) return;
    L.api('DELETE', '/api/verzeichnisse/' + v.id).then(neuLaden).catch(fehlerZeigen);
  }

  function dialogSeite(vorgabeVerzeichnis) {
    var titel = el('input', { type: 'text', required: '', maxlength: '120' });
    var slugVorschau = el('span', { html: 'Dateiname: <code>…</code>.html' });
    titel.addEventListener('input', function () { slugVorschau.innerHTML = 'Dateiname: <code>' + slug(titel.value) + '</code>.html'; });
    var verz = verzeichnisAuswahl(vorgabeVerzeichnis || (kinderVon(null)[0] || {}).id);
    verz.firstChild.remove();
    var menue = el('select', null, [
      el('option', { value: 'voll', text: 'Menübar ganz anzeigen' }),
      el('option', { value: 'seitenmenue', text: 'Nur als Seitenmenü' }),
      el('option', { value: 'keine', text: 'Kein Menü' })
    ]);
    var text = el('textarea', { rows: '5', placeholder: 'Erster Textblock (optional). Formatierung danach im Editor.' });
    dialog('Neue Seite', [feld('Titel', titel, slugVorschau), feld('Verzeichnis', verz), feld('Menübar', menue), feld('Inhalt', text)], 'Erstellen', function () {
      var bloecke = [];
      if (text.value.trim()) {
        var html = text.value.trim().split(/\n{2,}/).map(function (abs) {
          return '<p>' + abs.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>') + '</p>';
        }).join('');
        bloecke.push({ id: 'b1', typ: 'text', html: html });
      }
      return L.api('POST', '/api/seiten', { titel: titel.value, verzeichnis: verz.value, menue: menue.value, bloecke: bloecke })
        .then(function (j) { location.href = j.pfad + '.html#bearbeiten'; });
    });
  }

  function seiteLoeschen(s) {
    L.api('GET', '/api/loeschvorschau/' + s.pfad).then(function (v) {
      function liste(titel, eintraege, zeile) {
        if (!eintraege.length) return null;
        return el('div', { 'class': 'feld' }, [el('label', { text: titel }), el('ul', { 'class': 'loesch-liste' }, eintraege.map(function (e) { return el('li', { text: zeile(e) }); }))]);
      }
      dialog('Seite «' + s.titel + '» löschen', [
        el('p', { 'class': 'hinweis', text: 'Anhänge gehören zu der Seite, auf der sie hochgeladen wurden. Beim Löschen werden nur Anhänge entfernt, die keine andere Seite mehr verwendet; die übrigen wechseln zu einer Seite, die sie noch nutzt. Die Seite selbst bleibt 30 Tage im Papierkorb.' }),
        liste('Wird mitgelöscht', v.geloescht, function (e) { return e.name; }),
        liste('Bleibt erhalten (wird noch verwendet)', v.bleibt, function (e) { return e.name + ' – verwendet von ' + e.seiten.join(', ') + '; neue Heimat: ' + e.neueHeimat; }),
        liste('Weiterleitungen, die ebenfalls entfernt werden', v.redirects, function (e) { return e.verzeichnis + ' (' + e.ordner + '/)'; }),
        (!v.geloescht.length && !v.bleibt.length && !v.redirects.length) ? el('p', { text: 'Die Seite hat keine Anhänge und keine Weiterleitungen.' }) : null
      ], 'Löschen', function () { return L.api('DELETE', '/api/seiten/' + s.pfad).then(neuLaden); });
    }).catch(fehlerZeigen);
  }

  function dialogVerschieben(s) {
    var ziel = verzeichnisAuswahl(null);
    ziel.firstChild.remove();
    dialog('«' + s.titel + '» verschieben', [
      el('p', { 'class': 'hinweis', text: 'Die Seite wandert samt Datei in den Ordner des gewählten Verzeichnisses. Anhänge, Verlauf, Kommentare und interne Links ziehen mit; alte Lesezeichen auf die Datei gelten danach nicht mehr.' }),
      feld('Neues Verzeichnis', ziel)
    ], 'Verschieben', function () { return L.api('POST', '/api/seiten/' + s.pfad + '/verschieben', { verzeichnis: ziel.value }).then(neuLaden); });
  }

  function redirectEntfernen(v, s) {
    if (!confirm('Weiterleitung auf «' + s.titel + '» aus «' + v.name + '» entfernen? Die Seite selbst bleibt.')) return;
    L.api('DELETE', '/api/verzeichnisse/' + v.id + '/redirect/' + s.ziel).then(neuLaden).catch(fehlerZeigen);
  }


  // ---------- Wartung: Backup, Papierkorb, nicht verwendete Dateien (dezent) ----------

  // ---------- Reiter: Portfolio, Kompetenzen, Verwaltung ----------
  // Backup, Papierkorb usw. rutschen so bei vielen Verzeichnissen nicht aus dem Blick.

  var reiterAktiv = null;
  function reiterZeigen(name, merken) {
    var nav = document.getElementById('dash-reiter');
    if (!nav || nav.hidden) return;
    reiterAktiv = name;
    nav.querySelectorAll('[role=tab]').forEach(function (b) {
      var an = b.dataset.reiter === name;
      b.classList.toggle('aktiv', an); b.setAttribute('aria-selected', an ? 'true' : 'false'); b.tabIndex = an ? 0 : -1;
      var panel = document.getElementById(b.getAttribute('aria-controls')); if (panel) panel.hidden = !an;
    });
    if (merken) merkSchreiben('liloport-dashboard-reiter', name);
  }
  function reiterEinrichten() {
    var nav = document.getElementById('dash-reiter');
    if (!nav || !edit || nav.dataset.bereit) return;
    nav.dataset.bereit = '1';
    nav.hidden = false;
    var tabs = [].slice.call(nav.querySelectorAll('[role=tab]'));
    tabs.forEach(function (b, i) {
      b.addEventListener('click', function () { reiterZeigen(b.dataset.reiter, true); });
      b.addEventListener('keydown', function (ev) {   // Pfeiltasten wie bei Reitern üblich
        var j = ev.key === 'ArrowRight' ? i + 1 : ev.key === 'ArrowLeft' ? i - 1 : null;
        if (j === null) return;
        var ziel = tabs[(j + tabs.length) % tabs.length]; reiterZeigen(ziel.dataset.reiter, true); ziel.focus(); ev.preventDefault();
      });
    });
    var aus = location.hash.replace('#', '');
    reiterZeigen(['portfolio', 'kompetenzen', 'verwaltung'].indexOf(aus) >= 0 ? aus : merkLesen('liloport-dashboard-reiter', 'portfolio'), false);
  }
  function reiterZahl(name, text, warnung) {
    var b = document.getElementById('reiter-' + name); if (!b) return;
    var z = b.querySelector('.reiter-zahl'); z.textContent = text || ''; z.classList.toggle('warnung', !!warnung);
  }

  function abschnitt(symbol, titel, zahl, warnung, inhalt) {
    var d = el('details', null, [
      el('summary', null, [el('span', { 'class': 'symbol', text: symbol }), el('span', { text: titel }), el('span', { 'class': 'zahl' + (warnung ? ' warnung' : ''), text: zahl })]),
      inhalt
    ]);
    return d;
  }

  function wartung() {
    var alt = document.getElementById('wartung'); if (alt) alt.remove();
    var altK = document.getElementById('kompetenzen-bereich'); if (altK) altK.remove();
    if (!edit) return;
    Promise.all([L.api('GET', '/api/backup'), L.api('GET', '/api/papierkorb'), L.api('GET', '/api/assets'), L.api('GET', '/api/export-einstellungen'), L.api('GET', '/api/kompetenzrahmen')]).then(function (r) {
      var backup = r[0], korb = r[1].eintraege, assets = r[2];
      var sek = el('section', { id: 'wartung', 'class': 'wartung' });
      var kompSek = el('section', { id: 'kompetenzen-bereich', 'class': 'wartung kompetenzen-bereich' });

      // Backup
      var bInhalt = el('div', { 'class': 'backup-bereich' });
      var backupAbschnitt = abschnitt('🛟', 'Backup', '', backup.warnung, bInhalt);
      backupZeigen(backupAbschnitt, bInhalt, backup);
      if (backup.warnung || backup.laeuft) backupAbschnitt.open = true;
      sek.appendChild(backupAbschnitt);

      // Papierkorb
      var kInhalt = el('ul');
      if (!korb.length) kInhalt.appendChild(el('li', { 'class': 'hinweis', text: 'Leer. Gelöschte Seiten bleiben hier 30 Tage.' }));
      korb.forEach(function (k) {
        kInhalt.appendChild(el('li', null, [
          el('strong', { text: k.titel }), el('span', { text: k.pfad + ' · gelöscht ' + datumKurz(k.geloescht) }),
          el('button', { 'class': 'klein', text: 'Wiederherstellen', onclick: function () {
            L.api('POST', '/api/papierkorb/' + k.id).then(function (j) { alert('Wiederhergestellt als ' + j.pfad + '.html'); neuLaden(); }).catch(fehlerZeigen);
          } }),
          el('button', { 'class': 'klein gefahr', text: 'Endgültig löschen', onclick: function () {
            if (!confirm('«' + k.titel + '» endgültig aus dem Papierkorb löschen?')) return;
            L.api('DELETE', '/api/papierkorb/' + k.id).then(neuLaden).catch(fehlerZeigen);
          } })
        ]));
      });
      sek.appendChild(abschnitt('🗑', 'Papierkorb', korb.length ? korb.length + ' Seiten' : 'leer', false, kInhalt));

      // Nicht verwendete Dateien
      var ids = assets.verwaist;
      var aInhalt = el('ul');
      if (!ids.length) aInhalt.appendChild(el('li', { 'class': 'hinweis', text: 'Alle hochgeladenen Dateien werden in Seiten verwendet.' }));
      assets.assets.filter(function (a) { return ids.indexOf(a.id) >= 0; }).forEach(function (a) {
        aInhalt.appendChild(el('li', null, [
          el('a', { href: a.datei, target: '_blank', text: a.name }), el('span', { text: a.typ + ' · ' + Math.round(a.groesse / 1024) + ' KB · hochgeladen für ' + a.heimat }),
          el('button', { 'class': 'klein gefahr', text: 'Löschen', onclick: function () {
            if (!confirm('Datei «' + a.name + '» endgültig löschen?')) return;
            L.api('DELETE', '/api/assets/' + a.id).then(neuLaden).catch(fehlerZeigen);
          } })
        ]));
      });
      sek.appendChild(abschnitt('📎', 'Nicht verwendete Dateien', ids.length ? ids.length + ' Dateien' : 'keine', false, aInhalt));

      // Kompetenzen: Rahmen anlegen/importieren, bearbeiten, Abbildung ansehen
      var rahmen = (r[4] || {}).rahmen || [];
      var kInhalt = el('div', { 'class': 'kompetenz-zeile' });
      if (!rahmen.length) kInhalt.appendChild(el('p', { 'class': 'klein-text', text: 'Ein Kompetenzrahmen beschreibt Bereiche, Kompetenzen, Stufen und Punkte. Seiten verweisen mit dem Block «Kompetenzen» darauf; die Abbildung zeigt, was offen, in Bearbeitung oder erarbeitet ist.' }));
      rahmen.forEach(function (k) {
        kInhalt.appendChild(el('div', { 'class': 'kompetenz-rahmen' }, [
          el('strong', { text: k.titel }),
          el('span', { 'class': 'klein-text', text: k.bereiche + ' Bereiche · ' + k.knoten + ' Einträge' + (k.version ? ' · Version ' + k.version : '') }),
          el('a', { 'class': 'knopf klein', href: '_kompetenzen/' + k.id + '.html', text: 'Rahmen bearbeiten' }),
          el('a', { 'class': 'knopf klein primaer', href: '_kompetenzen/' + k.id + '-abbildung.html', text: 'Abbildung ansehen' })
        ]));
      });
      kInhalt.appendChild(el('div', { 'class': 'feld-zeile' }, [
        el('button', { 'class': 'klein', text: '+ Kompetenzrahmen erstellen', onclick: dialogRahmenNeu }),
        el('button', { 'class': 'klein', text: '📥 Kompetenzrahmen importieren', onclick: dialogRahmenImport })
      ]));
      kompSek.appendChild(el('h2', { 'class': 'tab-titel', text: 'Kompetenzrahmen' }));
      kompSek.appendChild(kInhalt);
      reiterZahl('kompetenzen', rahmen.length ? String(rahmen.length) : '');

      // Profil: Anzeigename und ID für Exporte
      var profil = r[3] || {};
      var pName = el('input', { type: 'text', value: profil.autor || '', placeholder: 'Anzeigename, z. B. Vorname Name', maxlength: '120' });
      var pId = el('input', { type: 'text', value: profil.id || '', placeholder: 'ID-Nummer, Matrikelnummer etc.', maxlength: '60' });
      var pStatus = el('span', { 'class': 'klein-text' });
      var pInhalt = el('div', { 'class': 'profil-zeile' }, [
        el('label', null, [el('span', { text: 'Anzeigename' }), pName]),
        el('label', null, [el('span', { text: 'ID-Nummer' }), pId]),
        el('button', { 'class': 'klein', text: 'Speichern', onclick: function () {
          L.api('POST', '/api/profil', { autor: pName.value, id: pId.value }).then(function () { pStatus.textContent = 'gespeichert'; setTimeout(function () { pStatus.textContent = ''; }, 2000); }).catch(fehlerZeigen);
        } }),
        pStatus,
        el('p', { 'class': 'klein-text', text: 'Beide Angaben werden beim Exportieren vorbelegt. Ob sie auf den exportierten Seiten erscheinen, entscheidest du bei jedem Export.' })
      ]);
      sek.appendChild(abschnitt('👤', 'Profil für Exporte', profil.autor ? profil.autor + (profil.id ? ' · ' + profil.id : '') : 'nicht ausgefüllt', false, pInhalt));
      var nochmal = document.getElementById('wartung'); if (nochmal) nochmal.remove();
      var nochmalK = document.getElementById('kompetenzen-bereich'); if (nochmalK) nochmalK.remove();
      var tabV = document.getElementById('tab-verwaltung'), tabK = document.getElementById('tab-kompetenzen');
      if (tabV && tabK) {
        tabV.appendChild(sek); tabK.appendChild(kompSek);
        reiterZahl('verwaltung', backup.warnung ? '⚠' : '', backup.warnung);
      } else {
        sek.appendChild(kompSek);
        document.querySelector('.dashboard-inhalt').appendChild(sek);
      }
    }).catch(function () {});
  }

  function dialogRahmenNeu() {
    var titel = el('input', { type: 'text', required: '', maxlength: '200', placeholder: 'z. B. Kompetenzprofil Lehrberuf' });
    var quelle = el('input', { type: 'text', maxlength: '300', placeholder: 'Hochschule, Studiengang, Jahr (optional)' });
    dialog('Kompetenzrahmen erstellen', [
      el('p', { 'class': 'hinweis', text: 'Danach öffnet sich die Seite des Rahmens. Dort legst du Bereiche, Kompetenzen, Stufen und Punkte an.' }),
      feld('Titel', titel), feld('Quelle', quelle)
    ], 'Erstellen', function () {
      return L.api('POST', '/api/kompetenzrahmen', { titel: titel.value, quelle: quelle.value, bereiche: [] }).then(function (j) { location.href = '_kompetenzen/' + j.id + '.html'; });
    });
  }

  function dialogRahmenImport() {
    var datei = el('input', { type: 'file', accept: '.json,application/json' });
    dialog('Kompetenzrahmen importieren', [
      el('p', { 'class': 'hinweis', text: 'Eine JSON-Datei, die aus einem Liloport über «Als JSON weitergeben» stammt – zum Beispiel der Rahmen einer Hochschule. Der Rahmen wird als eigener Eintrag angelegt; bestehende bleiben unverändert.' }),
      feld('Datei', datei)
    ], 'Importieren', function () {
      var f = datei.files[0]; if (!f) throw new Error('Bitte eine Datei wählen.');
      return fetch('/api/kompetenzrahmen/import', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Dateiname': encodeURIComponent(f.name) }, body: f })
        .then(function (r) { return r.json(); }).then(function (j) { if (j.fehler) throw new Error(j.fehler); location.href = '_kompetenzen/' + j.id + '.html'; });
    });
  }

  // ---------- Backup: Zustand, Fortschritt, Ort ----------

  function groesse(n) {
    if (n === null || n === undefined) return '';
    var e = ['Bytes', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (n >= 1024 && i < e.length - 1) { n /= 1024; i++; }
    return (i < 2 ? Math.round(n) : n.toFixed(1).replace('.', ',')) + ' ' + e[i];
  }

  var backupUhr = null, backupErwartet = null;   // erwartet: Art der Arbeit, deren Ergebnis noch zu melden ist

  function backupZeigen(abschn, box, b) {
    var zahl = abschn.querySelector('summary .zahl');
    var arbeit = b.laeuft;
    zahl.textContent = arbeit ? (arbeit.art === 'backup' ? 'läuft …' : 'stellt wieder her …')
      : b.meldung ? 'Problem' : b.speicher_knapp ? 'Speicher knapp'
      : b.letztes ? (b.tage >= 7 ? 'älter als 7 Tage' : datumKurz(b.letztes)) : 'keines';
    zahl.classList.toggle('warnung', !!b.warnung && !arbeit);
    var reiterV = document.getElementById('reiter-verwaltung');
    if (reiterV) reiterV.title = b.meldung || (b.speicher_knapp ? 'Speicherplatz knapp' : b.warnung ? 'Backup ist älter als 7 Tage' : '');
    box.textContent = '';
    if (b.meldung) box.appendChild(el('p', { 'class': 'backup-meldung', text: '⚠ ' + b.meldung }));
    if (b.speicher_knapp && b.inhalte_speicher) box.appendChild(el('p', { 'class': 'backup-meldung', text: '⚠ Auf dem Laufwerk deiner Inhalte sind nur noch ' + groesse(b.inhalte_speicher.frei) + ' frei. Ist ein Laufwerk voll, können Programme (auch der Browser) nicht mehr richtig speichern oder sich aktualisieren. Bitte Platz schaffen.' }));
    if (arbeit) {
      var anteil = arbeit.gesamt ? Math.min(100, Math.round(100 * arbeit.fertig / arbeit.gesamt)) : 0;
      box.appendChild(el('div', { 'class': 'backup-zeile' }, [
        el('span', { text: (arbeit.art === 'backup' ? 'Backup läuft im Hintergrund' : 'Wiederherstellen läuft') + (arbeit.gesamt ? ': ' + groesse(arbeit.fertig) + ' von ' + groesse(arbeit.gesamt) + '.' : ' …') + ' Du kannst normal weiterarbeiten.' }),
        el('progress', { max: '100', value: String(anteil) })
      ]));
      clearTimeout(backupUhr);
      backupUhr = setTimeout(function () {
        L.api('GET', '/api/backup').then(function (neu) {
          if (document.body.contains(box)) backupZeigen(abschn, box, neu);
        }).catch(function () {});
      }, 1500);
    } else if (backupErwartet && b.zuletzt && b.zuletzt.art === backupErwartet) {
      // Ergebnis der eben gestarteten Arbeit melden (auch wenn sie so schnell war, dass kein Fortschritt erschien)
      var z = b.zuletzt; backupErwartet = null;
      setTimeout(function () {
        if (z.art === 'wiederherstellen') alert(z.ok ? 'Wiederhergestellt nach ' + z.ziel + (z.fehlend && z.fehlend.length ? '\n\n' + z.fehlend.length + ' Datei(en) fehlten im Backup.' : '') : z.fehler);
        else if (!z.ok) alert(z.fehler);
      }, 50);
    }
    var text = b.letztes ? 'Zuletzt ' + datumKurz(b.letztes) + ', ' + b.anzahl + ' vorhanden. Täglich beim ersten Start automatisch.' : 'Noch kein Backup. Beim nächsten Start wird automatisch eines angelegt.';
    box.appendChild(el('div', { 'class': 'backup-zeile' }, [
      el('span', { text: text }),
      el('button', { 'class': 'klein', text: 'Backup jetzt', disabled: arbeit ? '' : null, onclick: function () {
        backupErwartet = 'backup';
        L.api('POST', '/api/backup').then(function () { return L.api('GET', '/api/backup'); }).then(function (neu) { backupZeigen(abschn, box, neu); }).catch(function (e) { backupErwartet = null; fehlerZeigen(e); });
      } }),
      el('button', { 'class': 'klein', text: 'Wiederherstellen …', disabled: arbeit ? '' : null, onclick: function () { dialogBackup(b.backups, function (neu) { backupZeigen(abschn, box, neu); }); } })
    ]));
    var platz = [];
    if (b.inhalte) platz.push('Inhalte ' + groesse(b.inhalte));
    if (b.belegt) platz.push('Backups belegen ' + groesse(b.belegt));
    if (b.speicher) platz.push(groesse(b.speicher.frei) + ' frei');
    box.appendChild(el('div', { 'class': 'backup-zeile backup-ort' }, [
      el('span', { text: 'Backup-Ordner: ' + (b.standard ? 'im Inhalte-Ordner (_wiki/backups)' : b.ordner) + (platz.length ? ' · ' + platz.join(' · ') : '') }),
      el('button', { 'class': 'klein', text: 'Ändern …', disabled: arbeit ? '' : null, onclick: function () { dialogBackupOrt(b, function (neu) { backupZeigen(abschn, box, neu); }); } })
    ]));
    box.appendChild(el('p', { 'class': 'klein-text backup-hinweis', text: 'Jedes Backup ist ein vollständiger Stand. Grosse Dateien (Bilder, Videos, PDFs) speichert Liloport dabei nur einmal; ein weiteres Backup kostet nur, was sich geändert hat. ' +
      (b.standard ? 'Backups im Inhalte-Ordner schützen vor Versehen, nicht vor einem Defekt des Laufwerks – dafür einen Ordner auf einer externen Festplatte wählen.' : '') }));
  }

  function dialogBackupOrt(b, fertig) {
    var ordner = el('input', { type: 'text', value: b.standard ? '' : b.ordner, placeholder: 'leer = im Inhalte-Ordner; z. B. E:\\Liloport-Backups' });
    dialog('Backup-Ordner wählen', [
      el('p', { 'class': 'hinweis', text: 'Zum Beispiel ein Ordner auf einer externen Festplatte. Ist sie beim Start nicht angeschlossen, meldet Liloport das hier und sichert, sobald sie wieder da ist. Liloport legt darin einen eigenen Unterordner an (Liloport-Backups › Name deines Inhalte-Ordners) und räumt nur dort auf. Bisherige Backups bleiben, wo sie sind (im Inhalte-Ordner unter _wiki/backups; dort kannst du sie bei Platzmangel löschen).' }),
      feld('Ordner (vollständiger Pfad)', ordner, el('span', { text: 'Windows: im Explorer den Ordner öffnen, oben in die Adresszeile klicken und den Pfad kopieren. Mac: Ordner mit gedrückter Wahltaste (⌥) rechts anklicken › «… als Pfadname kopieren».' }))
    ], 'Übernehmen', function () {
      return L.api('POST', '/api/backup/ort', { ordner: ordner.value }).then(fertig);
    });
  }

  function dialogBackup(backups, fertig) {
    if (!backups.length) { alert('Noch kein Backup vorhanden.'); return; }
    var sel = el('select', null, backups.filter(function (b) { return !b.defekt; }).map(function (b) { return el('option', { value: b.name, text: datumKurz(b.zeit) + ' · ' + groesse(b.groesse) }); }));
    var ziel = el('input', { type: 'text', placeholder: 'Pfad eines neuen oder leeren Ordners, z. B. C:\\Users\\name\\Liloport-Backup-Stand', required: '' });
    dialog('Backup wiederherstellen', [
      el('p', { 'class': 'hinweis', text: 'Das Backup wird in einen neuen, leeren Ordner entpackt; deine aktuellen Inhalte bleiben unverändert. Um mit dem wiederhergestellten Stand zu arbeiten: Liloport beenden, den bisherigen Inhalte-Ordner umbenennen (z. B. «Liloport-alt») und den wiederhergestellten Ordner an seine Stelle setzen und gleich benennen.' }),
      feld('Backup', sel), feld('Zielordner', ziel)
    ], 'Entpacken', function () {
      return L.api('POST', '/api/backup/wiederherstellen', { name: sel.value, ziel: ziel.value })
        .then(function () { backupErwartet = 'wiederherstellen'; return L.api('GET', '/api/backup'); }).then(function (neu) { if (fertig) fertig(neu); });
    });
  }

  // ---------- Suche (läuft auch unter file://) ----------

  var sucheNach = function () {};

  function suche() {
    var feldEl = document.getElementById('suchfeld'), treffer = document.getElementById('treffer'), info = document.getElementById('suche-info');
    if (!feldEl) return;
    var index = window.LILOPORT_INDEX || [];
    function norm(t) { return (t || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, ''); }
    function ausschnitt(text, woerter) {
      var t = norm(text), pos = -1;
      woerter.forEach(function (w) { var i = t.indexOf(w); if (i >= 0 && (pos < 0 || i < pos)) pos = i; });
      if (pos < 0) return text.slice(0, 160);
      var start = Math.max(0, pos - 60);
      return (start ? '… ' : '') + text.slice(start, start + 200) + (start + 200 < text.length ? ' …' : '');
    }
    function markieren(text, woerter) {
      var frag = document.createDocumentFragment();
      var re = new RegExp('(' + woerter.map(function (w) { return w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|') + ')', 'ig');
      text.split(re).forEach(function (teil, i) { frag.appendChild(i % 2 ? el('mark', { text: teil }) : document.createTextNode(teil)); });
      return frag;
    }
    function laufen() {
      var q = feldEl.value.trim();
      treffer.innerHTML = '';
      if (q.length < 2) { treffer.hidden = true; info.textContent = ''; document.getElementById('baum').hidden = false; document.getElementById('baum-werkzeuge').hidden = false; return; }
      // «#tag» (auch mit Leerzeichen: «#Woche 1») sucht genau diesen Tag; sonst Wörter in Titel, Text, Tags, Anhängen
      var tagSuche = q.charAt(0) === '#' ? norm(q.slice(1).trim()) : null;
      var woerter = tagSuche !== null ? [tagSuche] : norm(q).split(/\s+/).filter(Boolean);
      var liste = index.map(function (e) {
        var tags = (e.tags || []).map(norm);
        if (tagSuche !== null) return tags.indexOf(tagSuche) >= 0 ? { e: e, punkte: 1 } : null;
        var titel = norm(e.titel), text = norm(e.text), anh = norm(e.anhaenge.join(' ')), tagText = tags.join(' ');
        var punkte = 0;
        woerter.forEach(function (w) {
          if (titel.indexOf(w) >= 0) punkte += 10;
          if (tagText.indexOf(w) >= 0) punkte += 6;
          if (text.indexOf(w) >= 0) punkte += 2;
          if (anh.indexOf(w) >= 0) punkte += 3;
        });
        var alle = woerter.every(function (w) { return titel.indexOf(w) >= 0 || text.indexOf(w) >= 0 || anh.indexOf(w) >= 0 || tagText.indexOf(w) >= 0; });
        return alle ? { e: e, punkte: punkte } : null;
      }).filter(Boolean).sort(function (a, b) { return (b.punkte - a.punkte) || String(b.e.datum || '').localeCompare(String(a.e.datum || '')); });
      info.textContent = liste.length + ' Treffer';
      document.getElementById('baum').hidden = true;
      document.getElementById('baum-werkzeuge').hidden = true;
      if (reiterAktiv && reiterAktiv !== 'portfolio') reiterZeigen('portfolio', false);
      treffer.hidden = false;
      if (!liste.length) { treffer.appendChild(el('p', { 'class': 'hinweis', text: 'Nichts gefunden.' })); return; }
      liste.forEach(function (t) {
        var e = t.e;
        var zeile = el('div', { 'class': 'treffer-zeile' }, [
          el('a', { 'class': 'treffer-titel', href: e.pfad + '.html' }, [markieren(e.titel, woerter)]),
          el('span', { 'class': 'klein-text', text: ' ' + e.verzeichnis + (e.datum ? ' · ' + e.datum.split('-').reverse().join('.') : '') }),
          (e.tags || []).length ? el('span', { 'class': 'tags' }, e.tags.map(function (t) {
            return el('a', { 'class': 'tag', href: '#', text: '#' + t, onclick: function (ev) { ev.preventDefault(); sucheNach('#' + t); } });
          })) : null,
          el('p', { 'class': 'treffer-text' }, [markieren(ausschnitt(e.text, woerter), woerter)])
        ]);
        if (e.anhaenge.length) zeile.appendChild(el('p', { 'class': 'klein-text' }, [document.createTextNode('Anhänge: '), markieren(e.anhaenge.join(', '), woerter)]));
        treffer.appendChild(zeile);
      });
    }
    sucheNach = function (q) { feldEl.value = q; laufen(); feldEl.focus(); window.scrollTo(0, 0); };
    var vorgabe = new URLSearchParams(location.search).get('suche');
    if (vorgabe) feldEl.value = vorgabe;
    feldEl.addEventListener('input', laufen);
    document.getElementById('suche').addEventListener('submit', function (ev) { ev.preventDefault(); laufen(); });
    laufen();
  }

  // ---------- Start ----------

  document.getElementById('plus-button').addEventListener('click', function () {
    if (!edit) { alert('Zum Anlegen Liloport starten (python server.py).'); return; }
    dialogAuswahl();
  });
  aufbauen();
  if (edit) neuLaden();
  suche();
  if (edit && location.hash === '#neu') { history.replaceState(null, '', 'index.html'); dialogAuswahl(); }
})();
