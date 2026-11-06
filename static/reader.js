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
      if (!liste.length) { box.dataset.leer = '1'; box.hidden = true; return; }
      liste.slice(0, 10).forEach(function (e) {
        box.appendChild(el('div', { 'class': 'klein-text' }, [el('span', { text: String(e.zeit).replace('T', ' ').slice(0, 16) + (e.portfolio ? ' · im Portfolio «' + e.titel + '»' : '') })]));
        box.appendChild(moderationsZeile(e.name, e.moderation));
      });
    }).catch(function () { box.dataset.leer = '1'; box.hidden = true; });
    return box;
  }

  function dialogExport(s) {
    /* s: {pfad, titel} für eine Seite oder {verzeichnis: id|'' , titel} für ein Verzeichnis / das ganze Portfolio.
       Der Dialog fragt zuerst nach dem Zweck (Weitergeben als ZIP oder Webserver) und zeigt nur, was dazu passt:
       der Moderations-Link zum Beispiel nützt nur auf einem Webserver. */
    var mehrere = !s.pfad;
    api('GET', '/api/export-einstellungen').then(function (einst) {

      /* ---- Zweck: Weitergeben oder Webserver ---- */
      var zweck = 'weitergabe';
      try { zweck = localStorage.getItem('liloport-export-zweck') || 'weitergabe'; } catch (e) { /* egal */ }
      if (zweck !== 'webserver') zweck = 'weitergabe';
      function zweckKarte(wert, symbol, titel, text) {
        var radio = el('input', { type: 'radio', name: 'export-zweck', value: wert });
        var karte = el('label', { 'class': 'zweck-karte' }, [
          radio,
          el('span', { 'class': 'zweck-inhalt' }, [
            el('strong', null, [document.createTextNode(symbol + ' ' + titel)]),
            el('span', { 'class': 'zweck-text', text: text })
          ])
        ]);
        radio.addEventListener('change', function () { if (radio.checked) { zweck = wert; try { localStorage.setItem('liloport-export-zweck', wert); } catch (e) { /* egal */ } anpassen(); } });
        return { el: karte, radio: radio };
      }
      var kWeiter = zweckKarte('weitergabe', '📨', 'Weitergeben als ZIP',
        'Per E-Mail, USB-Stick oder Chat. Die andere Person entpackt die ZIP und doppelklickt «Seite öffnen» – lesen und kommentieren geht direkt im Browser, ohne Internet und Zusatzprogramm. Kommentare kommen per «Herunterladen» als ZIP zurück.');
      var kServer = zweckKarte('webserver', '🌐', 'Auf einem Webserver veröffentlichen',
        'Der Ordner «inhalt» aus der ZIP kommt auf den Server (z. B. Webspace der Hochschule). Die Dateinamen sind zufällig: Nur wer den Link kennt, findet die Seite; Suchmaschinen sind ausgeschlossen.');
      (zweck === 'webserver' ? kServer : kWeiter).radio.checked = true;
      var zweckWahl = el('div', { 'class': 'zweck-wahl', role: 'radiogroup', 'aria-label': 'Wofür ist der Export?' }, [kWeiter.el, kServer.el]);

      /* ---- Angaben auf den Seiten ---- */
      var autor = el('input', { type: 'text', value: einst.autor || '', placeholder: 'Name, der angezeigt werden darf', maxlength: '120' });
      var ident = el('input', { type: 'text', value: einst.id || '', placeholder: 'ID-Nummer, Matrikelnummer etc.', maxlength: '60' });
      var autorAn = kreuz('Anzeigename auf den Seiten zeigen', einst.autorAnzeigen !== false && !!einst.autor);
      var idAn = kreuz('ID-Nummer auf den Seiten zeigen', !!einst.idAnzeigen && !!einst.id);
      var profilHinweis = el('div', { 'class': 'nebenbei', text: 'Vorbelegt aus dem Profil im Dashboard. Änderungen hier werden dort übernommen. Autor, Zeitstempel und Bild-Metadaten (EXIF) werden entfernt, sofern hier nicht eingeschaltet.' });
      var datumAn = kreuz('Datum der Seite anzeigen', einst.datumAnzeigen);

      /* ---- Kommentare ---- */
      var kommentare = kreuz('Kommentare erlauben', true, 'Wer die Seite öffnet, kann kommentieren (Name freiwillig).');
      var kommentarHinweis = el('div', { 'class': 'nebenbei' });
      var modAn = kreuz('Moderations-Link erzeugen', true, 'Mit dem Moderations-Link kannst du auf dem Server alle Kommentare bearbeiten und löschen.');
      var modHinweis = el('div', { 'class': 'nebenbei' });

      /* ---- Abgabe und Passwortschutz ---- */
      var abgabe = kreuz('Als Abgabe kennzeichnen (Datum und Prüfsumme)', false, 'Zeigt auf der Seite den Zeitpunkt des Exports und eine Prüfsumme. Liloport erkennt beim Import, ob der Inhalt seither verändert wurde.');
      var abgabeHinweis = el('div', { 'class': 'nebenbei', text: 'Die Prüfsumme belegt, dass der Inhalt seit dem Export unverändert ist. Damit auch der Zeitpunkt belegt ist: die Prüfsumme bei der Abgabe zusätzlich angeben (z. B. im Abgabeformular). Sie steht auch in der Datei ABGABE.txt. Seiten mit Kompetenz-Block werden zugleich zur Bewertung freigegeben: Unter den Kompetenzen erscheint eine Beurteilung mit wählbarer Skala (0–1 bis 0–10) und Kommentar; sie braucht «Kommentare erlauben».' });
      abgabeHinweis.hidden = true;
      abgabe.box.addEventListener('change', function () { abgabeHinweis.hidden = !abgabe.box.checked; });
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
      var pwAn = kreuz('Passwortschutz', false, 'Der Inhalt wird verschlüsselt und erst im Browser nach Eingabe des Passworts entschlüsselt.');
      var pw1 = el('input', { type: 'password', placeholder: 'Passwort', autocomplete: 'new-password' });
      var pw2 = el('input', { type: 'password', placeholder: 'Passwort wiederholen', autocomplete: 'new-password' });
      var pwFelder = el('div', { 'class': 'feld-zeile' }, [pw1, pw2]); pwFelder.style.display = 'none';
      var pwWarnung = el('div', { 'class': 'export-hinweis-pw', role: 'note' }, [
        el('strong', { text: 'Nicht wieder importierbar: ' }),
        el('span', { text: 'Eine passwortgeschützte ZIP lässt sich nicht in Liloport zurückholen – weder die Seite noch die Kommentare. Wer Kommentare oder Beurteilungen zurück in Liloport holen möchte, exportiert ohne Passwort. Auf einem Webserver braucht die Entschlüsselung https://.' })
      ]);
      pwWarnung.hidden = true;
      pwAn.box.addEventListener('change', function () { pwFelder.style.display = pwAn.box.checked ? '' : 'none'; pwWarnung.hidden = !pwAn.box.checked; });

      var ergebnis = el('div', { 'class': 'export-ergebnis' });
      var warnung = el('div', { 'class': 'export-warnung' }, [
        el('strong', { text: 'Vor dem Weitergeben prüfen: Personen und Fallbeispiele' }),
        el('ul', null, [
          el('li', { text: 'Fotos, Namen oder Aussagen von anderen Personen nur mit deren Einverständnis weitergeben.' }),
          el('li', { text: 'Fallbeispiele aus Praktikum oder Praxis (z. B. Schule, Pflege, Soziale Arbeit) nur anonymisiert: keine Namen, Orte, Daten oder Details, die auf eine Person schliessen lassen.' }),
          el('li', { text: 'Im Zweifel den Passwortschutz einschalten.' })
        ])
      ]);
      var umfang = mehrere
        ? (s.verzeichnis ? 'Das Verzeichnis mit allen Unterverzeichnissen' : 'Das ganze Portfolio') + ' wird zu einer kleinen Website mit Inhaltsverzeichnis als Startseite; interne Links zwischen den Seiten funktionieren.'
        : 'Die ZIP enthält die Seite ohne Liloport-Leiste und Menü und nur ihre eigenen Anhänge. Interne Links auf andere Seiten werden zu einfachem Text.';

      function gruppe(titel, kinder) {
        return el('div', { 'class': 'export-gruppe' }, [el('h3', { text: titel })].concat(kinder));
      }
      var frueher = fruehereExporte(s);
      var gruppeKommentare = gruppe('Kommentare', [kommentare.el, kommentarHinweis, modAn.el, modHinweis]);
      var gruppeAngaben = gruppe('Angaben auf den Seiten', [feld('Anzeigename', autor), autorAn.el, feld('ID-Nummer', ident), idAn.el, datumAn.el, profilHinweis]);
      var gruppeSchutz = gruppe('Abgabe und Schutz', [abgabe.el, abgabeHinweis, pwAn.el, pwFelder, pwWarnung,
        el('div', { 'class': 'nebenbei', text: 'Ein vergessenes Passwort kann nicht wiederhergestellt werden.' })]);

      function anpassen() {
        /* Zeigt nur, was zum gewählten Zweck passt. */
        var server = zweck === 'webserver';
        modAn.el.hidden = !server; modHinweis.hidden = !server;
        frueher.hidden = !server || frueher.dataset.leer === '1';
        kommentarHinweis.textContent = server
          ? 'Kann der Server PHP oder Python (comments.php / comments.py liegen in der ZIP), sehen alle Besucher die Kommentare. Sonst bleiben sie im Browser der kommentierenden Person und kommen über «Herunterladen» zurück.'
          : 'Kommentare bleiben im Browser der Person, die kommentiert. Über «Herunterladen» auf der Seite schickt sie dir die ZIP samt Kommentaren zurück; «Dashboard › Neu › Aus ZIP importieren» holt sie nach Liloport.';
      }
      anpassen();

      dialog('«' + s.titel + '» exportieren', [
        el('p', { 'class': 'hinweis', text: umfang }),
        el('p', { 'class': 'zweck-frage', text: 'Wofür ist der Export?' }),
        zweckWahl,
        warnung,
        gruppeKommentare, gruppeAngaben, gruppeSchutz,
        ergebnis,
        frueher
      ], 'ZIP herunterladen', function () {
        var server = zweck === 'webserver';
        var optionen = { autor: autor.value, id: ident.value, autorAnzeigen: autorAn.box.checked, idAnzeigen: idAn.box.checked, datumAnzeigen: datumAn.box.checked, kommentare: kommentare.box.checked, abgabe: abgabe.box.checked,
          moderation: server && modAn.box.checked && !abgabe.box.checked };
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
              ergebnis.appendChild(el('p', null, [el('strong', { text: '✓ ZIP heruntergeladen' + (name ? ': ' : '.') }), name ? el('code', { text: name[1] }) : null]));
              if (!server) {
                ergebnis.appendChild(el('p', { 'class': 'klein-text', text: 'Die ZIP kannst du so weitergeben – per E-Mail, USB-Stick oder Chat. Die andere Person entpackt sie (Windows: Rechtsklick › «Alle extrahieren…») und doppelklickt «Seite öffnen».' }));
                if (kommentare.box.checked) ergebnis.appendChild(el('p', { 'class': 'klein-text', text: 'Kommentare und Beurteilungen kommen über «Herunterladen» (unten auf der Seite) als ZIP zurück und lassen sich im Dashboard über «Neu › Aus ZIP importieren» wieder einlesen.' }));
              } else {
                ergebnis.appendChild(el('p', null, [el('span', { text: 'Entpacken und den Ordner «inhalt» auf den Webserver kopieren (die LIESMICH.txt erklärt die Schritte). ' + (mehrere ? 'Die Startseite' : 'Die Seite') + ' heisst dort: ' }), el('code', { text: zufall + '.html' }),
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
              }
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
  /* Für grosse Portfolios (viele Verzeichnisse, tiefe Verschachtelung, lange Seitenlisten):
     - Brotkrumen über dem Titel zeigen, wo die Seite liegt; ein Klick öffnet das Menü an dieser Stelle
     - Seitensuche (Strg/Cmd+K): alle Seiten nach Titel, Verzeichnis und Tags; ohne Eingabe die zuletzt bearbeiteten
     - Leiste oben: eine Zeile, was nicht passt, liegt unter «Mehr»; ein Klick öffnet ein Panel mit den Seiten in
       Spalten, Unterverzeichnisse aufklappbar, ab vielen Seiten mit Filter
     - Seitenmenü links: Filterfeld, nur der Weg zur aktuellen Seite offen, Führungslinien, lange Listen gekürzt */

  function alleKinderVon(elternId) {   // auch Verzeichnisse, die nicht im Menü stehen (für andere Skripte)
    return daten.verzeichnisse.filter(function (v) { return (v.eltern || null) === elternId; })
      .sort(function (a, b) { return (a.reihenfolge - b.reihenfolge) || a.name.localeCompare(b.name, 'de'); });
  }
  function kinderVon(elternId) {   // nur Verzeichnisse im Menü
    return daten.verzeichnisse.filter(function (v) { return (v.eltern || null) === elternId && v.inMenue !== false; })
      .sort(function (a, b) { return (a.reihenfolge - b.reihenfolge) || a.name.localeCompare(b.name, 'de'); });
  }
  function verzNach(id) { return daten.verzeichnisse.filter(function (v) { return v.id === id; })[0] || null; }
  function vorfahren(v) {   // [Wurzel, …, v]
    var kette = [];
    for (var x = v; x; x = x.eltern ? verzNach(x.eltern) : null) { kette.unshift(x); if (kette.length > 50) break; }
    return kette;
  }
  function istAktuell(s, pfad) { return s.pfad === pfad || s.ziel === pfad; }
  var anzahlCache = {};
  function anzahl(v) {   // Seiten im ganzen Teilbaum
    if (anzahlCache[v.id] === undefined) anzahlCache[v.id] = v.seiten.length + kinderVon(v.id).reduce(function (n, k) { return n + anzahl(k); }, 0);
    return anzahlCache[v.id];
  }
  function enthaeltAktuell(v, pfad) {
    return v.seiten.some(function (s) { return istAktuell(s, pfad); }) || kinderVon(v.id).some(function (k) { return enthaeltAktuell(k, pfad); });
  }
  function aktuellesVerzeichnis(pfad) {
    var treffer = daten.verzeichnisse.filter(function (v) { return v.seiten.some(function (s) { return s.pfad === pfad && !s.redirect; }); });
    if (!treffer.length) treffer = daten.verzeichnisse.filter(function (v) { return v.seiten.some(function (s) { return istAktuell(s, pfad); }); });
    return treffer[0] || null;
  }
  function sichtbarImMenue(v) { return vorfahren(v).every(function (x) { return x.inMenue !== false; }); }
  function seitenLink(s, pfad) {
    var a = el('a', { href: rel + s.pfad + '.html', text: s.titel });
    if (istAktuell(s, pfad)) { a.className = 'aktuell'; a.setAttribute('aria-current', 'page'); }
    return a;
  }

  // Suche über alle Seiten im Menü
  function normal(t) { return String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }
  var eintraegeCache = null;
  function alleEintraege() {
    if (eintraegeCache) return eintraegeCache;
    eintraegeCache = [];
    daten.verzeichnisse.forEach(function (v) {
      if (!sichtbarImMenue(v)) return;
      var ort = vorfahren(v).map(function (x) { return x.name; }).join(' › ');
      v.seiten.forEach(function (s) {
        eintraegeCache.push({ s: s, v: v, ort: ort, titelN: normal(s.titel), allesN: normal(s.titel + ' ' + ort + ' ' + (s.tags || []).join(' ')) });
      });
    });
    return eintraegeCache;
  }
  function suchen(text, imVerz) {
    var woerter = normal(text).split(/\s+/).filter(Boolean);
    var liste = alleEintraege();
    if (imVerz) liste = liste.filter(function (e) { return vorfahren(e.v).indexOf(imVerz) >= 0; });
    if (!woerter.length) {   // ohne Eingabe: zuletzt bearbeitet (ohne Doppelte)
      var gesehen = {};
      return liste.filter(function (e) { var k = e.s.ziel || e.s.pfad; if (gesehen[k] || e.s.redirect) return false; gesehen[k] = 1; return true; })
        .sort(function (a, b) { return String(b.s.geaendert || '').localeCompare(String(a.s.geaendert || '')); }).slice(0, 8);
    }
    return liste.filter(function (e) { return woerter.every(function (w) { return e.allesN.indexOf(w) >= 0; }); })
      .map(function (e) {
        var p = e.titelN.indexOf(woerter[0]);
        return { e: e, rang: p === 0 ? 0 : p > 0 ? 1 : 2 };
      })
      .sort(function (a, b) { return (a.rang - b.rang) || a.e.s.titel.localeCompare(b.e.s.titel, 'de'); })
      .slice(0, 60).map(function (x) { return x.e; });
  }
  function trefferListe(ergebnisse, pfad, leerText) {
    var ul = el('ul', { 'class': 'nav-treffer', role: 'listbox' });
    ergebnisse.forEach(function (e, i) {
      var a = el('a', { href: rel + e.s.pfad + '.html', role: 'option', 'class': (istAktuell(e.s, pfad) ? 'aktuell' : '') + (i === 0 ? ' gewaehlt' : '') }, [
        el('span', { 'class': 'nav-treffer-titel', text: e.s.titel }),
        el('span', { 'class': 'nav-treffer-ort', text: e.ort })
      ]);
      ul.appendChild(el('li', null, [a]));
    });
    if (!ergebnisse.length) ul.appendChild(el('li', { 'class': 'nav-leer', text: leerText || 'Keine Seite gefunden.' }));
    return ul;
  }
  function pfeiltasten(feld, holeListe) {
    /* ↑/↓ wählt einen Treffer, Enter öffnet ihn */
    feld.addEventListener('keydown', function (ev) {
      var liste = holeListe(); if (!liste) return;
      var links = [].slice.call(liste.querySelectorAll('a'));
      if (!links.length) return;
      var i = links.indexOf(liste.querySelector('a.gewaehlt'));
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        ev.preventDefault();
        i = ev.key === 'ArrowDown' ? Math.min(links.length - 1, i + 1) : Math.max(0, i - 1);
        links.forEach(function (a, j) { a.classList.toggle('gewaehlt', j === i); });
        links[i].scrollIntoView({ block: 'nearest' });
      } else if (ev.key === 'Enter') {
        ev.preventDefault();
        location.href = (links[i] || links[0]).href;
      }
    });
  }

  // Seitensuche als Fenster (Leiste oben; Strg/Cmd+K)
  var finder = null;
  function finderOeffnen(pfad) {
    if (!finder) {
      var feld = el('input', { type: 'search', 'class': 'nav-finder-feld', placeholder: 'Seite suchen – Titel, Verzeichnis oder Tag', 'aria-label': 'Seite suchen', autocomplete: 'off', spellcheck: 'false' });
      var titel = el('p', { 'class': 'nav-finder-hinweis' });
      var ergebnis = el('div', { 'class': 'nav-finder-ergebnis' });
      var box = el('div', { 'class': 'nav-finder', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Seite suchen' }, [feld, titel, ergebnis,
        el('p', { 'class': 'nav-finder-fuss', text: '↑ ↓ wählen · Enter öffnen · Esc schliessen' })]);
      var hinter = el('div', { 'class': 'nav-finder-hinter' }, [box]);
      var zeigen = function () {
        titel.textContent = feld.value.trim() ? '' : 'Zuletzt bearbeitet';
        ergebnis.innerHTML = '';
        ergebnis.appendChild(trefferListe(suchen(feld.value), pfad));
      };
      feld.addEventListener('input', zeigen);
      pfeiltasten(feld, function () { return ergebnis.querySelector('.nav-treffer'); });
      hinter.addEventListener('mousedown', function (ev) { if (ev.target === hinter) finderSchliessen(); });
      hinter.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') { ev.preventDefault(); finderSchliessen(); } });
      finder = { hinter: hinter, feld: feld, zeigen: zeigen, vorher: null };
      document.body.appendChild(hinter);
    }
    finder.vorher = document.activeElement;
    finder.hinter.classList.add('offen');
    finder.feld.value = '';
    finder.zeigen();
    finder.feld.focus();
  }
  function finderSchliessen() {
    if (!finder) return;
    finder.hinter.classList.remove('offen');
    if (finder.vorher && finder.vorher.focus) finder.vorher.focus();
  }

  function brotkrumen(pfad, oeffnen) {
    var v = aktuellesVerzeichnis(pfad);
    var titel = document.getElementById('seitentitel');
    if (!v || !titel || !sichtbarImMenue(v)) return;
    var nav = el('nav', { 'class': 'brotkrumen', 'aria-label': 'Ort der Seite' });
    vorfahren(v).forEach(function (x, i) {
      if (i) nav.appendChild(el('span', { 'class': 'brotkrumen-trenner', 'aria-hidden': 'true', text: '›' }));
      nav.appendChild(el('button', { type: 'button', text: x.name, title: 'Im Menü zeigen: ' + x.name, onclick: function (ev) { oeffnen(x, ev.currentTarget); } }));
    });
    titel.parentNode.insertBefore(nav, titel);
  }

  function menueAufbauen() {
    var nav = document.getElementById('menue');
    if (!nav || istDashboard) return;
    var modus = body.dataset.menue || 'voll';
    var pfad = body.dataset.pfad || '';
    if (modus === 'keine' || !kinderVon(null).length) return;
    var oeffnen = modus === 'voll' ? obenMenue(nav, pfad) : seitenmenue(pfad);
    brotkrumen(pfad, oeffnen);
    // Strg/Cmd+K: Seite suchen (nicht beim Schreiben in Feldern oder im Editor)
    document.addEventListener('keydown', function (ev) {
      if (!(ev.ctrlKey || ev.metaKey) || ev.altKey || ev.key.toLowerCase() !== 'k') return;
      var t = ev.target;
      if (t && t.closest && t.closest('input, textarea, select, [contenteditable], .editor-block')) return;
      ev.preventDefault();
      if (modus === 'voll') finderOeffnen(pfad); else oeffnen(null);
    });
  }

  /* Leiste oben */
  function obenMenue(nav, pfad) {
    var oben = kinderVon(null);
    var haupt = el('ul', { 'class': 'menue-haupt' });
    var punkte = [];
    var offen = null;   // { v, knopf, panel }
    var panel = el('div', { 'class': 'menue-panel', hidden: '' });
    var mehrKnopf = el('button', { type: 'button', 'class': 'menue-knopf', 'aria-haspopup': 'true', 'aria-expanded': 'false' }, [el('span', { text: 'Mehr' }), el('span', { 'class': 'pfeil', text: '▾' })]);
    var mehrLi = el('li', { 'class': 'menue-mehr', hidden: '' }, [mehrKnopf]);

    oben.forEach(function (v) {
      var knopf = el('button', { type: 'button', 'class': 'menue-knopf', 'aria-haspopup': 'true', 'aria-expanded': 'false' }, [el('span', { text: v.name }), el('span', { 'class': 'pfeil', text: '▾' })]);
      var li = el('li', { 'class': 'menue-punkt' + (enthaeltAktuell(v, pfad) ? ' im-pfad' : '') }, [knopf]);
      knopf.addEventListener('click', function () { umschalten(v, knopf); });
      punkte.push({ v: v, li: li });
      haupt.appendChild(li);
    });
    haupt.appendChild(mehrLi);
    mehrKnopf.addEventListener('click', function () { umschalten('mehr', mehrKnopf); });
    var finden = el('button', { type: 'button', 'class': 'menue-finden', title: 'Seite suchen (Strg/Cmd+K)', onclick: function () { schliessen(); finderOeffnen(pfad); } }, [
      el('span', { 'class': 'lupe', 'aria-hidden': 'true' }), el('span', { 'class': 'menue-finden-text', text: 'Seite suchen' }), el('kbd', { text: /Mac|iP/.test(navigator.platform) ? '⌘K' : 'Strg K' })
    ]);
    nav.appendChild(el('div', { 'class': 'menue-zeile' }, [haupt, finden]));
    nav.appendChild(panel);

    function anordnen() {
      /* So viele Hauptverzeichnisse wie in eine Zeile passen; der Rest kommt unter «Mehr». */
      punkte.forEach(function (p) { p.li.hidden = false; });
      mehrLi.hidden = true;
      if (haupt.scrollWidth <= haupt.clientWidth + 1) return;
      mehrLi.hidden = false;
      for (var i = punkte.length - 1; i >= 0 && haupt.scrollWidth > haupt.clientWidth + 1; i--) {
        if (punkte[i].li.classList.contains('im-pfad') && i > 0) {   // aktuelles Verzeichnis möglichst sichtbar lassen
          var j = i - 1; while (j >= 0 && punkte[j].li.hidden) j--;
          if (j >= 0) { punkte[j].li.hidden = true; i++; continue; }
        }
        punkte[i].li.hidden = true;
      }
      mehrKnopf.classList.toggle('im-pfad', punkte.some(function (p) { return p.li.hidden && p.li.classList.contains('im-pfad'); }));
    }
    anordnen();
    var zeitgeber = null;
    window.addEventListener('resize', function () { clearTimeout(zeitgeber); zeitgeber = setTimeout(function () { schliessen(); anordnen(); }, 120); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(anordnen);

    function schliessen() {
      if (!offen) return;
      offen.knopf.setAttribute('aria-expanded', 'false');
      offen.knopf.classList.remove('offen');
      panel.hidden = true; panel.innerHTML = '';
      offen = null;
    }
    function umschalten(v, knopf, zielVerz) {
      if (offen && offen.knopf === knopf && offen.v === v && !zielVerz) { schliessen(); return; }
      schliessen();
      panel.innerHTML = '';
      panel.appendChild(v === 'mehr' ? mehrInhalt() : panelInhalt(v, zielVerz));
      panel.hidden = false;
      panel.classList.toggle('schmal', v === 'mehr');
      // «Mehr» als schmales Menü unter dem Knopf, Verzeichnisse über die ganze Breite
      if (v === 'mehr') {
        var r = knopf.getBoundingClientRect(), n = nav.getBoundingClientRect();
        panel.style.left = Math.max(8, Math.min(r.left - n.left, n.width - 300)) + 'px';
      } else panel.style.left = '';
      knopf.setAttribute('aria-expanded', 'true');
      knopf.classList.add('offen');
      offen = { v: v, knopf: knopf };
      var ziel = panel.querySelector('.ziel') || panel.querySelector('a.aktuell');
      if (ziel) ziel.scrollIntoView({ block: 'nearest' });
      var feld = panel.querySelector('input'); if (feld && !zielVerz) feld.focus({ preventScroll: true });
    }
    function mehrInhalt() {
      var ul = el('ul', { 'class': 'menue-mehr-liste' });
      punkte.filter(function (p) { return p.li.hidden; }).forEach(function (p) {
        var b = el('button', { type: 'button', 'class': p.li.classList.contains('im-pfad') ? 'im-pfad' : '' }, [
          el('span', { text: p.v.name }), el('span', { 'class': 'nav-zahl', text: String(anzahl(p.v)) })]);
        b.addEventListener('click', function () { umschalten(p.v, mehrKnopf, null); });
        ul.appendChild(el('li', null, [b]));
      });
      return ul;
    }
    function panelInhalt(v, zielVerz) {
      var gesamt = anzahl(v);
      var kopf = el('div', { 'class': 'menue-panel-kopf' }, [
        el('span', { 'class': 'menue-panel-titel', text: v.name }),
        el('span', { 'class': 'nav-zahl', text: gesamt === 1 ? '1 Seite' : gesamt + ' Seiten' })
      ]);
      var rumpfEl = el('div', { 'class': 'menue-panel-rumpf' });
      var baumEl = abschnitt(v, 0, zielVerz);
      rumpfEl.appendChild(baumEl);
      if (gesamt > 10) {
        var feld = el('input', { type: 'search', 'class': 'menue-filter', placeholder: 'In «' + v.name + '» suchen', 'aria-label': 'In ' + v.name + ' suchen', autocomplete: 'off' });
        var treffer = el('div', { 'class': 'menue-filter-treffer', hidden: '' });
        feld.addEventListener('input', function () {
          var q = feld.value.trim();
          baumEl.hidden = !!q; treffer.hidden = !q;
          treffer.innerHTML = '';
          if (q) treffer.appendChild(trefferListe(suchen(q, v), pfad));
        });
        pfeiltasten(feld, function () { return treffer.hidden ? null : treffer.querySelector('.nav-treffer'); });
        kopf.appendChild(feld);
        rumpfEl.appendChild(treffer);
      }
      return el('div', null, [kopf, rumpfEl]);
    }
    function abschnitt(v, tiefe, zielVerz) {
      var box = el('div', { 'class': 'menue-abschnitt' });
      if (v.seiten.length) {
        var ul = el('ul', { 'class': 'menue-seiten' });
        v.seiten.forEach(function (s) { ul.appendChild(el('li', null, [seitenLink(s, pfad)])); });
        box.appendChild(ul);
      }
      kinderVon(v.id).forEach(function (k) {
        var mitZiel = zielVerz && vorfahren(zielVerz).indexOf(k) >= 0;
        var d = el('details', { 'class': 'menue-unterverz tiefe-' + Math.min(tiefe + 1, 4) + (zielVerz === k ? ' ziel' : '') });
        if (enthaeltAktuell(k, pfad) || mitZiel || (tiefe === 0 && anzahl(v) <= 40)) d.open = true;
        d.appendChild(el('summary', null, [el('span', { text: k.name }), el('span', { 'class': 'nav-zahl', text: String(anzahl(k)) })]));
        d.appendChild(abschnitt(k, tiefe + 1, zielVerz));
        box.appendChild(d);
      });
      if (!box.children.length) box.appendChild(el('p', { 'class': 'nav-leer', text: 'keine Seiten' }));
      return box;
    }

    document.addEventListener('mousedown', function (ev) { if (offen && !nav.contains(ev.target) && !(ev.target.closest && ev.target.closest('.brotkrumen'))) schliessen(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && offen) { var k = offen.knopf; schliessen(); k.focus(); } });

    // Brotkrumen: Panel des Hauptverzeichnisses öffnen, das gewählte Unterverzeichnis aufgeklappt
    return function (x) {
      if (!x) { finderOeffnen(pfad); return; }
      var wurzel = vorfahren(x)[0];
      var p = punkte.filter(function (q) { return q.v === wurzel; })[0];
      if (!p) return;
      var knopf = p.li.hidden ? mehrKnopf : p.li.querySelector('button');
      umschalten(wurzel, knopf, x === wurzel ? null : x);
      nav.scrollIntoView({ block: 'nearest' });
    };
  }

  /* Seitenmenü: Seitenleiste links mit Verzeichnisgruppen; auf breiten Bildschirmen offen,
     einklappbar zu einer schmalen Leiste; Zustand wird gemerkt. */
  function seitenmenue(pfad) {
    var LANG = 12, KURZ = 8;   // ab LANG Seiten zuerst nur KURZ zeigen (plus die aktuelle)
    var leiste = el('aside', { 'class': 'seitenmenue', id: 'seitenmenue' });
    var zuAlle = el('button', { 'class': 'seitenmenue-werkzeug', type: 'button', title: 'Alle Verzeichnisse zuklappen', 'aria-label': 'Alle Verzeichnisse zuklappen', text: '⊟' });
    var kopf = el('div', { 'class': 'seitenmenue-kopf' }, [
      el('span', { 'class': 'seitenmenue-titel', text: daten.titel || 'Inhalt' }),
      zuAlle,
      el('button', { 'class': 'seitenmenue-schliessen', type: 'button', title: 'Menü einklappen', 'aria-label': 'Menü einklappen', text: '‹' })
    ]);
    var feld = el('input', { type: 'search', 'class': 'seitenmenue-feld', placeholder: 'Seite suchen …', 'aria-label': 'Seite suchen', autocomplete: 'off', spellcheck: 'false', title: 'Seite suchen (Strg/Cmd+K)' });
    var treffer = el('div', { 'class': 'seitenmenue-treffer', hidden: '' });
    var suche = el('div', { 'class': 'seitenmenue-suche' }, [feld]);
    var griff = el('button', { 'class': 'seitenmenue-griff', type: 'button', title: 'Menü aufklappen', 'aria-label': 'Menü aufklappen' }, [el('span', { text: '☰' }), el('span', { 'class': 'seitenmenue-griff-text', text: 'Menü' })]);
    var baumEl = el('nav', { 'class': 'seitenmenue-baum', 'aria-label': 'Verzeichnisse' });
    var gruppeVon = {};
    function gemerkt(v) { try { return localStorage.getItem('liloport-sm-' + v.id); } catch (e) { return null; } }
    function merken(v, zu) { try { localStorage.setItem('liloport-sm-' + v.id, zu ? 'zu' : 'auf'); } catch (e) { /* egal */ } }
    function setzeZu(sek, titel, zu) { sek.classList.toggle('zu', zu); titel.setAttribute('aria-expanded', zu ? 'false' : 'true'); }
    function gruppen(elternId, tiefe) {
      return kinderVon(elternId).map(function (v) {
        var sek = el('section', { 'class': 'seitenmenue-gruppe tiefe-' + Math.min(tiefe, 4) });
        var titel = el('button', { 'class': 'seitenmenue-gruppe-titel', type: 'button' }, [
          el('span', { 'class': 'pfeil', text: '▾' }), el('span', { 'class': 'seitenmenue-gruppe-name', text: v.name }), el('span', { 'class': 'nav-zahl', text: String(anzahl(v)) })]);
        var liste = el('ul');
        var hatAktuell = enthaeltAktuell(v, pfad);
        var aktIndex = -1;
        v.seiten.forEach(function (s, i) { if (istAktuell(s, pfad)) aktIndex = i; });
        v.seiten.forEach(function (s, i) {
          var li = el('li', null, [seitenLink(s, pfad)]);
          if (v.seiten.length > LANG && i >= KURZ && i !== aktIndex) li.className = 'mehr-versteckt';
          liste.appendChild(li);
        });
        if (v.seiten.length > LANG) {
          var rest = liste.querySelectorAll('.mehr-versteckt').length;
          var mehr = el('button', { type: 'button', 'class': 'seitenmenue-mehr', text: 'Alle ' + v.seiten.length + ' Seiten zeigen' });
          mehr.addEventListener('click', function () {
            var auf = liste.classList.toggle('alle');
            mehr.textContent = auf ? 'Weniger zeigen' : 'Alle ' + v.seiten.length + ' Seiten zeigen';
          });
          if (rest) liste.appendChild(el('li', { 'class': 'seitenmenue-mehr-zeile' }, [mehr]));
        }
        var unter = el('div', { 'class': 'seitenmenue-unter' });
        gruppen(v.id, tiefe + 1).forEach(function (u) { unter.appendChild(u); });
        if (!liste.children.length && !unter.children.length) liste.appendChild(el('li', { 'class': 'leer', text: 'keine Seiten' }));
        // Standard: nur der Weg zur aktuellen Seite ist offen; was man selbst auf- oder zuklappt, bleibt gemerkt
        var g = gemerkt(v);
        setzeZu(sek, titel, hatAktuell ? false : g ? g === 'zu' : true);
        titel.addEventListener('click', function () {
          var jetztZu = !sek.classList.contains('zu');
          setzeZu(sek, titel, jetztZu); merken(v, jetztZu);
        });
        sek.appendChild(titel); sek.appendChild(liste); sek.appendChild(unter);
        gruppeVon[v.id] = { sek: sek, titel: titel };
        return sek;
      });
    }
    gruppen(null, 0).forEach(function (g) { baumEl.appendChild(g); });
    leiste.appendChild(kopf); leiste.appendChild(suche); leiste.appendChild(treffer); leiste.appendChild(baumEl);

    feld.addEventListener('input', function () {
      var q = feld.value.trim();
      baumEl.hidden = !!q; treffer.hidden = !q;
      treffer.innerHTML = '';
      if (q) treffer.appendChild(trefferListe(suchen(q), pfad));
    });
    feld.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && feld.value) { ev.preventDefault(); feld.value = ''; feld.dispatchEvent(new Event('input')); } });
    pfeiltasten(feld, function () { return treffer.hidden ? null : treffer.querySelector('.nav-treffer'); });
    zuAlle.addEventListener('click', function () {
      Object.keys(gruppeVon).forEach(function (id) { var g = gruppeVon[id]; setzeZu(g.sek, g.titel, true); merken({ id: id }, true); });
    });

    function setzen(eingeklappt, merkenZustand) {
      body.classList.toggle('seitenmenue-zu', eingeklappt);
      if (merkenZustand) { try { localStorage.setItem('liloport-seitenmenue', eingeklappt ? 'zu' : 'auf'); } catch (e) { /* egal */ } }
    }
    var zustand = null;
    try { zustand = localStorage.getItem('liloport-seitenmenue'); } catch (e) { /* egal */ }
    var schmal = window.matchMedia && window.matchMedia('(max-width: 900px)').matches;
    setzen(zustand ? zustand === 'zu' : schmal, false);
    kopf.querySelector('.seitenmenue-schliessen').addEventListener('click', function () { setzen(true, true); });
    griff.addEventListener('click', function () { setzen(false, true); });
    var rumpf = document.querySelector('.rumpf');
    rumpf.insertBefore(leiste, rumpf.firstChild);
    rumpf.insertBefore(griff, leiste);
    // Aktuelle Seite in der Leiste sichtbar machen
    var akt = baumEl.querySelector('a.aktuell');
    if (akt && leiste.scrollHeight > leiste.clientHeight) leiste.scrollTop = Math.max(0, akt.offsetTop - leiste.clientHeight / 3);

    // Brotkrumen und Strg/Cmd+K
    return function (x) {
      setzen(false, false);
      if (!x) { feld.focus(); feld.select(); return; }
      vorfahren(x).forEach(function (y) { var g = gruppeVon[y.id]; if (g) setzeZu(g.sek, g.titel, false); });
      var g = gruppeVon[x.id];
      if (g) {
        if (schmal) leiste.scrollIntoView({ block: 'start' });
        g.sek.scrollIntoView({ block: 'nearest' });
        g.titel.focus({ preventScroll: true });
        g.sek.classList.add('aufgeleuchtet');
        setTimeout(function () { g.sek.classList.remove('aufgeleuchtet'); }, 1200);
      }
    };
  }

  /* ---------- Seiten-Werkzeugleiste ---------- */

  function werkzeuge() {
    var w = document.getElementById('seiten-werkzeuge');
    if (!w || istDashboard || !istLokalerServer || body.dataset.vorschau) return;
    var pfad = body.dataset.pfad, titel = (document.getElementById('seitentitel') || {}).textContent || pfad;
    var drucker = el('button', { type: 'button', 'class': 'druck-knopf', title: 'Seite drucken (A4)', 'aria-label': 'Seite drucken', onclick: drucken });
    drucker.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
      + '<path d="M7 9V3.5h10V9"/><rect x="3.5" y="9" width="17" height="8" rx="2"/><path d="M7 14.5h10V20.5H7z"/><path d="M17.5 12h.01"/></svg>';
    w.appendChild(drucker);
    w.appendChild(el('button', { type: 'button', text: 'Exportieren', title: 'Diese Seite als ZIP weitergeben oder auf einen Webserver stellen', onclick: function () { dialogExport({ pfad: pfad, titel: titel }); } }));
    w.appendChild(el('button', { type: 'button', 'class': 'primaer', text: 'Bearbeiten', id: 'bearbeiten-knopf', onclick: editorLaden }));
  }

  /* ---------- Drucken ---------- */
  /* Vor dem Druck: Eingeklapptes öffnen und alle Bilder laden (lazy); danach wieder zuklappen.
     Gilt auch für Strg/Cmd+P. Das Layout für A4 steht in style.css (@media print). */
  var druckGeoeffnet = [];
  function druckAufbereiten() {
    [].slice.call(document.querySelectorAll('details:not([open])')).forEach(function (d) { d.open = true; druckGeoeffnet.push(d); });
    [].slice.call(document.querySelectorAll('img[loading="lazy"]')).forEach(function (i) { i.loading = 'eager'; });
  }
  window.addEventListener('beforeprint', druckAufbereiten);
  window.addEventListener('afterprint', function () { druckGeoeffnet.forEach(function (d) { d.open = false; }); druckGeoeffnet = []; });
  function drucken() {
    druckAufbereiten();
    var bilder = [].slice.call(document.images).filter(function (i) { return !i.complete; });
    var los = function () { los = function () {}; window.print(); };
    if (!bilder.length) return los();
    var offen = bilder.length;
    bilder.forEach(function (i) { var fertig = function () { if (--offen <= 0) los(); }; i.addEventListener('load', fertig, { once: true }); i.addEventListener('error', fertig, { once: true }); });
    setTimeout(function () { los(); }, 4000);   // nicht ewig auf langsame Bilder warten
  }

  /* ---------- Nach-oben- und Nach-unten-Knopf ---------- */

  function nachObenKnopf() {
    /* Zwei runde Knöpfe unten rechts: «Nach oben» erscheint, sobald man gescrollt hat, und bringt einen
       zurück zu «Bearbeiten» und «Exportieren»; «Nach unten» erscheint, solange die Seite noch weiter
       nach unten reicht, und springt ans Ende (z. B. zu Fussnoten, «Verlinkt von», Kommentaren). */
    var pfeil = function (d) {
      return '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">'
        + '<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    };
    var oben = el('button', { 'class': 'nach-oben', type: 'button', title: 'Nach oben', 'aria-label': 'Nach oben scrollen', hidden: '' });
    var unten = el('button', { 'class': 'nach-unten', type: 'button', title: 'Nach unten', 'aria-label': 'Nach unten scrollen', hidden: '' });
    oben.innerHTML = pfeil('M5 14.5 12 7.5l7 7');
    unten.innerHTML = pfeil('M5 9.5 12 16.5l7-7');
    function scrollen(y) { try { window.scrollTo({ top: y, behavior: 'smooth' }); } catch (e) { window.scrollTo(0, y); } }
    function ende() { return Math.max(document.documentElement.scrollHeight, document.body.scrollHeight); }
    oben.addEventListener('click', function () { scrollen(0); });
    unten.addEventListener('click', function () { scrollen(ende()); });
    document.body.appendChild(el('div', { 'class': 'scroll-knoepfe' }, [oben, unten]));
    var zustand = '';
    function pruefen() {
      var y = window.scrollY || document.documentElement.scrollTop || 0;
      var rest = ende() - y - window.innerHeight;
      var zeigeOben = y > 400, zeigeUnten = rest > 400;
      var neu = (zeigeOben ? 'o' : '') + (zeigeUnten ? 'u' : '');
      if (neu !== zustand) { zustand = neu; oben.hidden = !zeigeOben; unten.hidden = !zeigeUnten; }
    }
    window.addEventListener('scroll', pruefen, { passive: true });
    window.addEventListener('resize', pruefen);
    // Die Seitenlänge ändert sich auch ohne Scrollen (Bilder laden, Editor, Ein-/Ausklappen)
    if (window.ResizeObserver) { try { new ResizeObserver(pruefen).observe(document.body); } catch (e) { /* egal */ } }
    window.addEventListener('load', pruefen);
    pruefen();
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

  /* ---------- Vollbild für Bilder (Galerie und Bild-Blöcke) ----------
     Ein Klick auf ein Bild öffnet es in voller Grösse; in Galerien lässt sich mit ‹ › und den
     Pfeiltasten blättern. Schliessen mit ✕, Escape oder Klick auf den Hintergrund. */

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
      body.classList.remove('vollbild-offen');
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
    body.classList.add('vollbild-offen');
    body.appendChild(huelle);
    huelle.focus();
  }

  function vollbild() {
    document.addEventListener('click', function (ev) {
      if (body.classList.contains('bearbeiten')) return;   // im Editor nicht
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
    istEditiermodus: istLokalerServer, kinderVon: alleKinderVon, editorLaden: editorLaden
  };

  leiste();
  menueAufbauen();
  werkzeuge();
  nachObenKnopf();
  vollbild();
  ordnerLinks();
  kompetenzSchalter();
  if (istLokalerServer && location.hash === '#bearbeiten' && !istDashboard) editorLaden();
  window.addEventListener('hashchange', function () {
    if (istLokalerServer && location.hash === '#bearbeiten' && !istDashboard) editorLaden();
  });
})();
