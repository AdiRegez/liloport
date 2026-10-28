/* Liloport – reader.js: läuft in jeder Seite und im Dashboard, auch unter file://.
   Liloport-Leiste (einklappbar, Niveau-Schalter, Lesemodus), Verzeichnismenü der Seite,
   Seiten-Werkzeugleiste (Bearbeiten, Exportieren), Dialog-Helfer, Export-Dialog. */
(function () {
  'use strict';
  var daten = window.LILOPORT || { titel: 'Liloport', niveau: 'amateur', verzeichnisse: [] };
  var body = document.body;
  var rel = body.dataset.rel || '';
  var istDashboard = body.classList.contains('dashboard');
  var istLokalerServer = location.protocol === 'http:' &&
    (location.hostname === '127.0.0.1' || location.hostname === 'localhost');

  function el(tag, attrs, kinder) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (attrs[k] === null || attrs[k] === undefined) return;   // z. B. disabled: null = nicht gesperrt
      if (k === 'text') e.textContent = attrs[k];
      else if (k === 'html') e.innerHTML = attrs[k];
      else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    (kinder || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }

  function api(methode, pfad, daten) {
    return fetch(pfad, {
      method: methode,
      headers: { 'Content-Type': 'application/json' },
      body: daten ? JSON.stringify(daten) : undefined
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || j.fehler) throw new Error(j.fehler || ('Fehler ' + r.status));
        return j;
      });
    });
  }

  /* ---------- Dialog-Helfer (Liloport-Design) ---------- */

  function dialog(titel, felder, aktionText, beiOk) {
    var fehler = el('div', { 'class': 'fehlermeldung' });
    var form = el('form', { method: 'dialog' }, [el('h2', { text: titel })].concat(felder).concat([
      fehler,
      el('div', { 'class': 'dialog-fuss' }, [
        el('button', { type: 'button', text: 'Abbrechen', onclick: function () { d.close(); } }),
        el('button', { type: 'submit', 'class': 'primaer', text: aktionText })
      ])
    ]));
    var d = el('dialog', null, [form]);
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      fehler.textContent = '';
      Promise.resolve().then(beiOk).then(function () { d.close(); }).catch(function (e) { if (e && e.bleiben) return; fehler.textContent = e.message || e; });
    });
    d.addEventListener('close', function () { d.remove(); });
    document.body.appendChild(d);
    d.showModal();
    var erstes = form.querySelector('input:not([type=checkbox]), select, textarea');
    if (erstes) erstes.focus();
    return d;
  }

  function feld(label, eingabe, nebenbei) {
    return el('div', { 'class': 'feld' }, [el('label', { text: label }), eingabe, nebenbei ? el('div', { 'class': 'nebenbei' }, [nebenbei]) : null]);
  }

  function kreuz(label, vorgabe, titel) {
    var box = el('input', { type: 'checkbox' });
    if (vorgabe) box.checked = true;
    return { box: box, el: el('div', { 'class': 'feld' }, [el('label', { 'class': 'feld-zeile', title: titel || '' }, [box, el('span', { text: label })])]) };
  }

  /* ---------- Export-Dialog (Dashboard und Seite) ---------- */

  function moderationsZeile(name, schluessel) {
    var link = name + '.html#moderation=' + schluessel;
    return el('div', { 'class': 'moderation-link' }, [
      el('span', { text: 'Moderations-Link:' }), el('code', { text: link }),
      el('button', { 'class': 'klein', type: 'button', text: 'Kopieren', onclick: function () { if (navigator.clipboard) navigator.clipboard.writeText(link); } })
    ]);
  }

  function fruehereExporte(s) {
    /* Frühere Exporte dieser Seite bzw. dieses Portfolios mit ihren Moderations-Links. */
    var box = el('details', { 'class': 'fruehere-exporte' }, [el('summary', { text: 'Frühere Exporte und Moderations-Links' })]);
    api('GET', '/api/exporte').then(function (j) {
      var gesehen = {}, liste = [];
      Object.keys(j.exporte || {}).forEach(function (k) {
        var e = j.exporte[k];
        var passt = s.pfad ? (e.pfad === s.pfad && !e.portfolio) || (e.pfad === s.pfad && e.portfolio) : (e.portfolio && e.titel === s.titel);
        var start = e.start || k;
        if (!passt || !e.moderation || gesehen[start]) return;
        gesehen[start] = 1;
        liste.push({ name: s.pfad && !e.portfolio ? k : start, zeit: e.zeit, moderation: e.moderation, portfolio: e.portfolio, titel: e.titel });
      });
      liste.sort(function (a, b) { return String(b.zeit).localeCompare(String(a.zeit)); });
      if (!liste.length) { box.hidden = true; return; }
      liste.slice(0, 10).forEach(function (e) {
        box.appendChild(el('div', { 'class': 'klein-text' }, [el('span', { text: String(e.zeit).replace('T', ' ').slice(0, 16) + (e.portfolio ? ' · im Portfolio «' + e.titel + '»' : '') })]));
        box.appendChild(moderationsZeile(e.name, e.moderation));
      });
    }).catch(function () { box.hidden = true; });
    return box;
  }

  function dialogExport(s) {
    /* s: {pfad, titel} für eine Seite oder {verzeichnis: id|'' , titel} für ein Verzeichnis / das ganze Portfolio */
    var mehrere = !s.pfad;
    api('GET', '/api/export-einstellungen').then(function (einst) {
      var autor = el('input', { type: 'text', value: einst.autor || '', placeholder: 'Name, der angezeigt werden darf', maxlength: '120' });
      var ident = el('input', { type: 'text', value: einst.id || '', placeholder: 'ID-Nummer, Matrikelnummer etc.', maxlength: '60' });
      var autorAn = kreuz('Anzeigename auf den Seiten zeigen', einst.autorAnzeigen !== false && !!einst.autor);
      var idAn = kreuz('ID-Nummer auf den Seiten zeigen', !!einst.idAnzeigen && !!einst.id);
      var profilHinweis = el('div', { 'class': 'nebenbei', text: 'Vorbelegt aus dem Profil im Dashboard. Änderungen hier werden dort übernommen.' });
      var datumAn = kreuz('Datum der Seite anzeigen', einst.datumAnzeigen);
      var kommentare = kreuz('Kommentare erlauben', true, 'Besucher können auf der Seite kommentieren. Gespeichert wird auf dem Server über PHP oder Python; ohne beides bleiben Kommentare im Browser der kommentierenden Person und kommen über «Herunterladen» zurück.');
      var abgabe = kreuz('Als Abgabe kennzeichnen (Datum und Prüfsumme)', false, 'Zeigt auf der Seite den Zeitpunkt des Exports und eine Prüfsumme. Liloport erkennt beim Import, ob der Inhalt seither verändert wurde.');
      var abgabeHinweis = el('div', { 'class': 'nebenbei', text: 'Die Prüfsumme belegt, dass der Inhalt seit dem Export unverändert ist. Damit auch der Zeitpunkt belegt ist: die Prüfsumme bei der Abgabe zusätzlich angeben (z. B. im Abgabeformular). Sie steht auch in der Datei ABGABE.txt. Seiten mit Kompetenz-Block werden zugleich zur Bewertung freigegeben: Unter den Kompetenzen erscheint eine Beurteilung mit wählbarer Skala (0–1 bis 0–10) und Kommentar; sie braucht «Kommentare erlauben».' });
      abgabeHinweis.hidden = true;
      abgabe.box.addEventListener('change', function () { abgabeHinweis.hidden = !abgabe.box.checked; });
      var modAn = kreuz('Moderations-Link erzeugen', true, 'Mit dem Moderations-Link kannst du auf dem Server alle Kommentare bearbeiten und löschen.');
      var modHinweis = el('div', { 'class': 'nebenbei' });
      function modAbgleichen() {
        var ab = abgabe.box.checked;
        modAn.box.disabled = ab || !kommentare.box.checked;
        if (ab) modAn.box.checked = false;
        modAn.el.classList.toggle('gesperrt', modAn.box.disabled);
        modHinweis.textContent = ab
          ? 'Bei einer Abgabe ausgeschaltet: Kommentare und Beurteilungen kann nur ändern oder löschen, wer sie geschrieben hat – auch du nicht. Auf der Seite steht das beim Abgabestempel.'
          : 'Ohne Moderations-Link kann jede Person nur ihre eigenen Kommentare bearbeiten oder löschen.';
      }
      var modVorher = true;
      abgabe.box.addEventListener('change', function () { if (abgabe.box.checked) modVorher = modAn.box.checked; else modAn.box.checked = modVorher; modAbgleichen(); });
      kommentare.box.addEventListener('change', modAbgleichen);
      modAbgleichen();
      var pwAn = kreuz('Passwortschutz', false, 'Inhalt wird im Browser entschlüsselt; braucht https:// auf dem Server');
      var pw1 = el('input', { type: 'password', placeholder: 'Passwort', autocomplete: 'new-password' });
      var pw2 = el('input', { type: 'password', placeholder: 'Passwort wiederholen', autocomplete: 'new-password' });
      var pwFelder = el('div', { 'class': 'feld-zeile' }, [pw1, pw2]); pwFelder.style.display = 'none';
      var pwWarnung = el('div', { 'class': 'export-hinweis-pw', role: 'note' }, [
        el('strong', { text: 'Nicht wieder importierbar: ' }),
        el('span', { text: 'Eine passwortgeschützte ZIP lässt sich nicht in Liloport zurückholen – weder die Seite noch die Kommentare. Wer Kommentare oder Beurteilungen zurück in Liloport holen möchte, exportiert ohne Passwort.' })
      ]);
      pwWarnung.hidden = true;
      pwAn.box.addEventListener('change', function () { pwFelder.style.display = pwAn.box.checked ? '' : 'none'; pwWarnung.hidden = !pwAn.box.checked; });
      var ergebnis = el('div', { 'class': 'export-ergebnis' });
      var warnung = el('div', { 'class': 'export-warnung' }, [
        el('strong', { text: 'Vor dem Veröffentlichen prüfen: Personen und Fallbeispiele' }),
        el('ul', null, [
          el('li', { text: 'Fotos, Namen oder Aussagen von anderen Personen nur mit deren Einverständnis veröffentlichen.' }),
          el('li', { text: 'Fallbeispiele aus Praktikum oder Praxis (z. B. Schule, Pflege, Soziale Arbeit) nur anonymisiert: keine Namen, Orte, Daten oder Details, die auf eine Person schliessen lassen.' }),
          el('li', { text: 'Im Zweifel den Passwortschutz einschalten.' })
        ])
      ]);
      var umfang = mehrere
        ? (s.verzeichnis ? 'Das Verzeichnis mit allen Unterverzeichnissen' : 'Das ganze Portfolio') + ' wird zu einer Website mit Inhaltsverzeichnis als Startseite; interne Links zwischen den Seiten funktionieren.'
        : 'Die ZIP enthält die Seite ohne Liloport-Leiste und Menü und nur ihre eigenen Anhänge. Interne Links auf andere Seiten werden zu einfachem Text.';
      dialog('«' + s.titel + '» exportieren', [
        el('p', { 'class': 'hinweis', text: umfang + ' Die Dateinamen sind zufällig: Nur wer die Adresse kennt, findet die Seite. Suchmaschinen werden ausgeschlossen. Autor, Zeitstempel und Bild-Metadaten werden entfernt, sofern nicht eingeschaltet.' }),
        warnung,
        kommentare.el, modAn.el, modHinweis,
        feld('Anzeigename', autor), autorAn.el, feld('ID-Nummer', ident), idAn.el, profilHinweis, datumAn.el,
        abgabe.el, abgabeHinweis,
        pwAn.el, pwFelder, pwWarnung, el('div', { 'class': 'nebenbei', text: 'Ein vergessenes Passwort kann nicht wiederhergestellt werden.' }),
        ergebnis,
        fruehereExporte(s)
      ], 'ZIP herunterladen', function () {
        var optionen = { autor: autor.value, id: ident.value, autorAnzeigen: autorAn.box.checked, idAnzeigen: idAn.box.checked, datumAnzeigen: datumAn.box.checked, kommentare: kommentare.box.checked, abgabe: abgabe.box.checked, moderation: modAn.box.checked && !abgabe.box.checked };
        if (pwAn.box.checked) {
          if (pw1.value.length < 4) throw new Error('Das Passwort braucht mindestens 4 Zeichen.');
          if (pw1.value !== pw2.value) throw new Error('Die Passwörter stimmen nicht überein.');
          optionen.passwort = pw1.value;
        }
        var url = '/api/export/' + s.pfad;
        if (mehrere) { url = '/api/export-mehrere'; optionen.verzeichnis = s.verzeichnis || ''; }
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(optionen) })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (j) { throw new Error(j.fehler || 'Export fehlgeschlagen'); });
            var name = (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
            var zufall = r.headers.get('X-Zufallsname') || '';
            var moderation = r.headers.get('X-Moderation') || '';
            return r.blob().then(function (blob) {
              var a = el('a', { href: URL.createObjectURL(blob), download: name ? name[1] : 'export.zip' });
              document.body.appendChild(a); a.click(); a.remove();
              ergebnis.innerHTML = '';
              ergebnis.appendChild(el('p', null, [el('strong', { text: 'Heruntergeladen. ' }), el('span', { text: (mehrere ? 'Die Startseite' : 'Die Seite') + ' heisst auf dem Server: ' }), el('code', { text: zufall + '.html' }),
                el('button', { 'class': 'klein', type: 'button', text: 'Kopieren', onclick: function () { navigator.clipboard && navigator.clipboard.writeText(zufall + '.html'); } })]));
              if (!moderation && kommentare.box.checked) {
                ergebnis.appendChild(el('p', { 'class': 'klein-text', text: abgabe.box.checked
                  ? 'Moderation ausgeschaltet (Abgabe): Kommentare und Beurteilungen kann nur ändern oder löschen, wer sie geschrieben hat.'
                  : 'Ohne Moderations-Link exportiert.' }));
              }
              if (moderation) {
                ergebnis.appendChild(moderationsZeile(zufall, moderation));
                ergebnis.appendChild(el('p', { 'class': 'klein-text', text: 'Mit diesem Link kannst du auf dem Server alle Kommentare bearbeiten und löschen: an die Adresse des Ordners anhängen, z. B. https://dein-server/ordner/' + zufall + '.html#moderation=… Nicht weitergeben. Liloport merkt ihn sich unter «Frühere Exporte».' }));
              }
              ergebnis.appendChild(el('p', { 'class': 'klein-text', text: 'Entpacken, den Ordner auf den Webserver kopieren – die LIESMICH.txt im Ordner erklärt die Schritte.' }));
              throw { bleiben: true };
            });
          });
      });
    }).catch(function (e) { alert(e.message || e); });
  }

  /* ---------- Liloport-Leiste ---------- */

  function leiste() {
    var kopf = document.getElementById('kopf'), griff = document.getElementById('kopf-griff'), zu = document.getElementById('kopf-zu');
    if (!kopf) return;
    function setzen(eingeklappt, merken) {
      kopf.classList.toggle('zu', eingeklappt);
      body.classList.toggle('leiste-zu', eingeklappt);
      griff.hidden = !eingeklappt;
      if (merken) { try { localStorage.setItem('liloport-leiste', eingeklappt ? 'zu' : 'auf'); } catch (e) { /* egal */ } }
    }
    var gemerkt = null;
    try { gemerkt = localStorage.getItem('liloport-leiste'); } catch (e) { /* egal */ }
    setzen(gemerkt === 'zu', false);
    zu.addEventListener('click', function () { setzen(true, true); });
    griff.addEventListener('click', function () { setzen(false, true); });

    var rechts = document.getElementById('kopf-rechts');
    // Niveau-Schalter: immer sichtbar; umschaltbar nur mit laufendem Server
    var schalter = el('span', { 'class': 'schalter' + (istLokalerServer ? '' : ' gesperrt'), title: istLokalerServer ? 'Niveau: bestimmt, welche Werkzeuge angezeigt werden' : 'Niveau (nur mit laufendem Liloport umschaltbar)' });
    ['amateur', 'profi'].forEach(function (n) {
      var b = el('button', { type: 'button', text: n === 'profi' ? 'Profi' : 'Amateur', 'class': daten.niveau === n ? 'aktiv' : '' });
      if (!istLokalerServer) b.disabled = true;
      b.addEventListener('click', function () {
        if (daten.niveau === n) return;
        api('POST', '/api/niveau', { niveau: n }).then(function () { location.reload(); }).catch(function (e) { alert(e.message); });
      });
      schalter.appendChild(b);
    });
    // Amateur/Profi bestimmt nur, welche Werkzeuge der Seiten-Editor anbietet: darum nur auf Seiten zeigen,
    // nicht im Dashboard, bei Kompetenzrahmen, Abbildung, Impressum usw.
    if (document.body.dataset.pfad) rechts.appendChild(schalter);
    if (istLokalerServer) {
      var aus = el('button', { type: 'button', 'class': 'kopf-beenden', title: 'Liloport beenden', 'aria-label': 'Liloport beenden' });
      // Symbol als SVG statt Schriftzeichen ⏻: liegt in jeder Schrift genau in der Mitte des Kreises
      aus.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><path d="M12 3.5v8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M7.05 6.6a7.5 7.5 0 1 0 9.9 0" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>';
      aus.addEventListener('click', function () {
        if (!confirm('Liloport beenden? Danach lassen sich die Seiten nur noch lesen. Zum Weiterarbeiten Liloport wieder starten (Desktop-Symbol).')) return;
        api('POST', '/api/beenden', {}).then(function () {
          document.body.innerHTML = '';
          document.body.className = 'beendet-seite';
          document.body.appendChild(el('main', { 'class': 'beendet-hinweis' }, [
            el('h1', { text: 'Liloport wurde beendet.' }),
            el('p', { text: 'Deine Inhalte sind gespeichert. Dieses Browserfenster kannst du schliessen. Zum Weiterarbeiten Liloport wieder starten, zum Beispiel über das Desktop-Symbol.' })
          ]));
        }).catch(function (e) { alert(e.message); });
      });
      rechts.appendChild(aus);
    }
    if (!istLokalerServer) {
      rechts.appendChild(el('span', { 'class': 'lesemodus', text: 'Lesemodus' }));
      var band = document.getElementById('modus-band');
      if (band) {
        band.hidden = false;
        band.textContent = 'Lesemodus: Alles wird angezeigt. Zum Bearbeiten Liloport starten (Desktop-Symbol oder python server.py) und das Dashboard im Browser öffnen.';
      }
    }
  }

  /* ---------- Verzeichnismenü der Seite ---------- */

  function kinderVon(elternId) {
    return daten.verzeichnisse.filter(function (v) { return (v.eltern || null) === elternId; })
      .sort(function (a, b) { return (a.reihenfolge - b.reihenfolge) || a.name.localeCompare(b.name, 'de'); });
  }

  function seitenLink(s, aktuellerPfad) {
    var a = el('a', { href: rel + s.pfad + '.html', text: s.titel });
    if (s.pfad === aktuellerPfad || s.ziel === aktuellerPfad) a.className = 'aktuell';
    return a;
  }

  function baum(elternId, nurImMenue, aktuellerPfad) {
    var liste = kinderVon(elternId).filter(function (v) { return !nurImMenue || v.inMenue; });
    if (!liste.length) return null;
    var ul = el('ul');
    liste.forEach(function (v) {
      var li = el('li', { 'class': 'verzeichnis' }, [el('span', { text: v.name, tabindex: '0' })]);
      var inner = el('ul');
      v.seiten.forEach(function (s) { inner.appendChild(el('li', null, [seitenLink(s, aktuellerPfad)])); });
      var unter = baum(v.id, nurImMenue, aktuellerPfad);
      if (unter) Array.prototype.slice.call(unter.children).forEach(function (c) { inner.appendChild(c); });
      if (!inner.children.length) inner.appendChild(el('li', null, [el('span', { 'class': 'hinweis', text: 'keine Seiten' })]));
      li.appendChild(inner);
      ul.appendChild(li);
    });
    return ul;
  }

  function menueAufbauen() {
    var nav = document.getElementById('menue');
    if (!nav || istDashboard) return;
    var modus = body.dataset.menue || 'voll';
    var pfad = body.dataset.pfad || '';
    if (modus === 'keine') return;
    var tree = baum(null, true, pfad);
    if (!tree) return;
    if (modus === 'voll') { nav.appendChild(tree); return; }
    seitenmenue(pfad);
  }

  /* Seitenmenü: Seitenleiste links mit Verzeichnisgruppen; auf breiten Bildschirmen offen,
     einklappbar zu einer schmalen Leiste; Zustand wird gemerkt. */
  function seitenmenue(pfad) {
    var leiste = el('aside', { 'class': 'seitenmenue', id: 'seitenmenue' });
    var kopf = el('div', { 'class': 'seitenmenue-kopf' }, [
      el('span', { 'class': 'seitenmenue-titel', text: daten.titel || 'Inhalt' }),
      el('button', { 'class': 'seitenmenue-schliessen', type: 'button', title: 'Menü einklappen', 'aria-label': 'Menü einklappen', text: '‹' })
    ]);
    var griff = el('button', { 'class': 'seitenmenue-griff', type: 'button', title: 'Menü aufklappen', 'aria-label': 'Menü aufklappen' }, [el('span', { text: '☰' }), el('span', { 'class': 'seitenmenue-griff-text', text: 'Menü' })]);
    var baumEl = el('nav', { 'class': 'seitenmenue-baum', 'aria-label': 'Verzeichnisse' });
    function gruppen(elternId, tiefe) {
      var ergebnis = [];
      kinderVon(elternId).filter(function (v) { return v.inMenue; }).forEach(function (v) {
        var sek = el('section', { 'class': 'seitenmenue-gruppe tiefe-' + Math.min(tiefe, 3) });
        var zu = false;
        try { zu = localStorage.getItem('liloport-sm-' + v.id) === 'zu'; } catch (e) { /* egal */ }
        var titel = el('button', { 'class': 'seitenmenue-gruppe-titel', type: 'button' }, [el('span', { 'class': 'pfeil', text: '▾' }), el('span', { text: v.name })]);
        var liste = el('ul');
        v.seiten.forEach(function (s) {
          var a = el('a', { href: rel + s.pfad + '.html', text: s.titel });
          if (s.pfad === pfad || s.ziel === pfad) { a.className = 'aktuell'; a.setAttribute('aria-current', 'page'); zu = false; }
          liste.appendChild(el('li', null, [a]));
        });
        var unter = el('div', { 'class': 'seitenmenue-unter' });
        gruppen(v.id, tiefe + 1).forEach(function (u) { unter.appendChild(u); });
        if (unter.querySelector('.aktuell')) zu = false;
        if (!liste.children.length && !unter.children.length) liste.appendChild(el('li', { 'class': 'leer', text: 'keine Seiten' }));
        sek.classList.toggle('zu', zu);
        titel.setAttribute('aria-expanded', zu ? 'false' : 'true');
        titel.addEventListener('click', function () {
          var jetztZu = !sek.classList.contains('zu');
          sek.classList.toggle('zu', jetztZu);
          titel.setAttribute('aria-expanded', jetztZu ? 'false' : 'true');
          try { localStorage.setItem('liloport-sm-' + v.id, jetztZu ? 'zu' : 'auf'); } catch (e) { /* egal */ }
        });
        sek.appendChild(titel); sek.appendChild(liste); sek.appendChild(unter);
        ergebnis.push(sek);
      });
      return ergebnis;
    }
    gruppen(null, 0).forEach(function (g) { baumEl.appendChild(g); });
    leiste.appendChild(kopf); leiste.appendChild(baumEl);
    function setzen(eingeklappt, merken) {
      body.classList.toggle('seitenmenue-zu', eingeklappt);
      if (merken) { try { localStorage.setItem('liloport-seitenmenue', eingeklappt ? 'zu' : 'auf'); } catch (e) { /* egal */ } }
    }
    var gemerkt = null;
    try { gemerkt = localStorage.getItem('liloport-seitenmenue'); } catch (e) { /* egal */ }
    var schmal = window.matchMedia && window.matchMedia('(max-width: 900px)').matches;
    setzen(gemerkt ? gemerkt === 'zu' : schmal, false);
    kopf.querySelector('.seitenmenue-schliessen').addEventListener('click', function () { setzen(true, true); });
    griff.addEventListener('click', function () { setzen(false, true); });
    var rumpf = document.querySelector('.rumpf');
    rumpf.insertBefore(leiste, rumpf.firstChild);
    rumpf.insertBefore(griff, leiste);
  }

  /* ---------- Seiten-Werkzeugleiste ---------- */

  function werkzeuge() {
    var w = document.getElementById('seiten-werkzeuge');
    if (!w || istDashboard || !istLokalerServer || body.dataset.vorschau) return;
    var pfad = body.dataset.pfad, titel = (document.getElementById('seitentitel') || {}).textContent || pfad;
    w.appendChild(el('button', { type: 'button', text: 'Exportieren', title: 'Diese Seite als ZIP für einen Webserver', onclick: function () { dialogExport({ pfad: pfad, titel: titel }); } }));
    w.appendChild(el('button', { type: 'button', 'class': 'primaer', text: 'Bearbeiten', id: 'bearbeiten-knopf', onclick: editorLaden }));
  }

  function editorLaden() {
    if (window.LiloportEditor) { window.LiloportEditor.starten(); return; }
    var s = el('script', { src: rel + '_wiki/editor.js' });
    s.onload = function () { if (window.LiloportEditor) window.LiloportEditor.starten(); };
    document.body.appendChild(s);
  }

  /* ---------- Kompetenz-Blöcke: Status direkt auf der Seite umschalten (nur mit laufendem Liloport) ---------- */

  function kompetenzSchalter() {
    var bloecke = document.querySelectorAll('.block-kr[data-rahmen]');
    if (!bloecke.length) return;
    if (!istLokalerServer) {
      // Lesemodus: Schalter als blossen Stand anzeigen
      bloecke.forEach(function (b) {
        b.querySelectorAll('.kr-schalter').forEach(function (s) {
          var aktiv = s.querySelector('.aktiv');
          var st = aktiv ? aktiv.dataset.status : 'weiss';
          var stand = el('span', { 'class': 'kr-stand st-' + st }, [el('span', { 'class': 'ka-punkt st-' + st }), document.createTextNode(aktiv ? aktiv.textContent : 'noch nicht bearbeitet')]);
          s.replaceWith(stand);
        });
      });
      return;
    }
    document.addEventListener('click', function (ev) {
      var knopf = ev.target.closest && ev.target.closest('.kr-schalter .kr-status');
      if (!knopf || body.classList.contains('bearbeiten')) return;
      var block = knopf.closest('.block-kr'), zeile = knopf.closest('.kr-zeile'), schalter = knopf.closest('.kr-schalter');
      var st = knopf.dataset.status;
      api('POST', '/api/kr-status/' + (block.dataset.pfad || body.dataset.pfad), { block: block.dataset.id, knoten: schalter.dataset.knoten, status: st }).then(function () {
        schalter.querySelectorAll('.kr-status').forEach(function (k) { var an = k === knopf; k.classList.toggle('aktiv', an); k.setAttribute('aria-pressed', an ? 'true' : 'false'); });
        zeile.className = 'kr-zeile st-' + st;
      }).catch(function (e) { alert('Status konnte nicht gespeichert werden: ' + e.message); });
    });
  }

  /* ---------- Ordner-Links (PDF, ZIP-Dateien) ---------- */

  function ordnerLinks() {
    document.addEventListener('click', function (ev) {
      var a = ev.target.closest && ev.target.closest('.ordner-link');
      if (!a) return;
      if (istLokalerServer) {
        ev.preventDefault();
        api('POST', '/api/oeffnen', { pfad: a.dataset.ordner }).catch(function (e) { alert('Ordner konnte nicht geöffnet werden: ' + e.message); });
      } else if (location.protocol !== 'file:') {
        ev.preventDefault();
        alert('Der Ordner lässt sich nur lokal öffnen: ' + a.dataset.ordner);
      }
      // unter file:// öffnet der Link den Ordner direkt
    });
  }

  window.Liloport = {
    daten: daten, rel: rel, el: el, api: api, dialog: dialog, feld: feld, kreuz: kreuz, dialogExport: dialogExport,
    istEditiermodus: istLokalerServer, kinderVon: kinderVon, editorLaden: editorLaden
  };

  leiste();
  menueAufbauen();
  werkzeuge();
  ordnerLinks();
  kompetenzSchalter();
  if (istLokalerServer && location.hash === '#bearbeiten' && !istDashboard) editorLaden();
  window.addEventListener('hashchange', function () {
    if (istLokalerServer && location.hash === '#bearbeiten' && !istDashboard) editorLaden();
  });
})();
