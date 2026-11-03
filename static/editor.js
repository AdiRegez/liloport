/* Liloport – editor.js: Bearbeiten einer Seite direkt in der Seite (nur im Editiermodus).
   Blöcke: Text, Bild, Video, PDF, Trenner; Profi zusätzlich Spalten, HTML, Seiten-CSS.
   Amateur: nur vertikales Drag und Drop, Profi-Blöcke gesperrt. */
(function () {
  'use strict';
  var L = window.Liloport;
  var el = L.el;
  var pfad = document.body.dataset.pfad;
  var rel = L.rel;
  var profi = false;   // wird beim Start frisch vom Server gelesen
  var seite = null;
  var bloecke = [];     // Baumstruktur (Spalten enthalten Unterlisten)
  var zaehler = 0;
  var gestartet = false;
  var assetCache = {};  // id -> Registry-Eintrag
  var objekte = {};     // id -> Blockobjekt, alles was je gezeichnet wurde
  var hinweisSchonGezeigt = false;
  var undoStack = [], redoStack = [];   // JSON-Schnappschüsse von {titel, menue, css, bloecke}
  var autosaveTimer = null, gespeichertStand = '', speichertGerade = false, statusEl = null, menueEl = null;

  var WERKZEUGE_AMATEUR = [
    { cmd: 'bold', text: 'F', title: 'Fett (Ctrl+B)', stil: 'font-weight:700' },
    { cmd: 'italic', text: 'K', title: 'Kursiv (Ctrl+I)', stil: 'font-style:italic' },
    { cmd: 'underline', text: 'U', title: 'Unterstrichen (Ctrl+U)', stil: 'text-decoration:underline' },
    { block: 'h1', text: 'H1', title: 'Überschrift 1' },
    { block: 'h2', text: 'H2', title: 'Überschrift 2' },
    { block: 'h3', text: 'H3', title: 'Überschrift 3' },
    { block: 'p', text: '¶', title: 'Normaler Absatz' },
    { cmd: 'insertUnorderedList', text: '• Liste', title: 'Aufzählung' },
    { cmd: 'insertOrderedList', text: '1. Liste', title: 'Nummerierte Liste' },
    { block: 'blockquote', text: '❝ Zitat', title: 'Zitat' },
    { cmd: 'justifyLeft', text: '⇤', title: 'Linksbündig' },
    { cmd: 'justifyCenter', text: '↔', title: 'Zentriert' },
    { cmd: 'justifyRight', text: '⇥', title: 'Rechtsbündig' },
    { link: true, text: 'Link', title: 'Link auf eine Seite in Liloport oder eine Webadresse' },
    { fussnote: true, text: 'Fussnote', title: 'Fussnote an der Cursorposition einfügen' },
    { cmd: 'removeFormat', text: '⌫ Format', title: 'Formatierung entfernen' }
  ];
  var WERKZEUGE_PROFI = [
    { block: 'h4', text: 'H4', title: 'Überschrift 4' },
    { block: 'pre', text: '</> Code', title: 'Codeblock' },
    { farbe: true, text: 'Farbe', title: 'Textfarbe' },
    { tabelle: true, text: 'Tabelle', title: 'Tabelle 2×2 einfügen' }
  ];

  function neueId() {
    zaehler += 1;
    var id = 'b' + zaehler;
    while (objekte[id]) { zaehler += 1; id = 'b' + zaehler; }
    return id;
  }

  function alleBloecke() {
    var liste = [];
    (function rek(bl) { bl.forEach(function (b) { liste.push(b); if (b.typ === 'spalten') b.spalten.forEach(rek); }); })(bloecke);
    return liste;
  }

  function blockVonId(id) { return objekte[id]; }

  function typName(typ) {
    return { text: 'Text', bild: 'Bild', galerie: 'Galerie', video: 'Video', audio: 'Audio', pdf: 'PDF', datei: 'ZIP-Datei', button: 'Button', trenner: 'Trenner', spalten: 'Spalten', html: 'HTML', kr: 'Kompetenzen' }[typ] || typ;
  }
  var AUSRICHTUNGEN = [['links', 'links'], ['mitte', 'zentriert'], ['rechts', 'rechts']];
  function ausrichtungSelect(b) {
    var sel = el('select', null, AUSRICHTUNGEN.map(function (a) { return el('option', { value: a[0], text: 'Ausrichtung: ' + a[1] }); }));
    sel.value = b.ausrichtung || 'links';
    sel.addEventListener('change', function () { b.ausrichtung = sel.value; geaendert(); });
    return sel;
  }

  // ---------- Start ----------

  function starten() {
    if (gestartet) return;
    gestartet = true;
    document.body.classList.add('bearbeiten');
    var werkzeuge = document.getElementById('seiten-werkzeuge');
    if (werkzeuge) werkzeuge.innerHTML = '';
    Promise.all([L.api('GET', '/api/seiten/' + pfad), L.api('GET', '/api/assets'), L.api('GET', '/api/site'), L.api('GET', '/api/kompetenzrahmen')]).then(function (r) {
      seite = r[0].seite;
      profi = (r[2].niveau === 'profi');
      rahmenListe = r[3].rahmen || [];
      r[1].assets.forEach(function (a) { assetCache[a.id] = a; });
      bloecke = JSON.parse(JSON.stringify(seite.bloecke || []));
      alleBloecke().forEach(function (b) { objekte[b.id] = b; });
      zaehler = alleBloecke().length;
      geraetPruefen(); setInterval(geraetPruefen, 60000);
      try { document.execCommand('styleWithCSS', false, true); } catch (e) { /* egal */ }
      aufbauen();
    }).catch(function (e) { alert(e.message); });
  }

  function geraetPruefen() {
    L.api('GET', '/api/sitzung').then(function (j) {
      var alt = document.getElementById('geraet-warnung'); if (alt) alt.remove();
      if (!j.fremd) return;
      var main = document.getElementById('inhalt');
      main.insertBefore(el('div', { id: 'geraet-warnung', 'class': 'geraet-warnung', text: '⚠ Liloport läuft gerade auch auf «' + j.fremd.name + '» mit diesem Inhalte-Ordner. Wenn dort dieselbe Seite bearbeitet wird, können Änderungen verloren gehen. Am besten nur auf einem Gerät gleichzeitig arbeiten.' }), main.firstChild);
    }).catch(function () {});
  }

  function aufbauen() {
    var main = document.getElementById('inhalt');
    main.innerHTML = '';

    var status = el('span', { 'class': 'status', text: '' });
    var menue = el('select', null, [
      el('option', { value: 'voll', text: 'Menübar ganz' }),
      el('option', { value: 'seitenmenue', text: 'Seitenmenü' }),
      el('option', { value: 'keine', text: 'Kein Menü' })
    ]);
    menue.value = seite.menue || 'voll';
    statusEl = status; menueEl = menue;
    menue.addEventListener('change', geaendert);
    var leiste = el('div', { 'class': 'editor-leiste' }, [
      el('button', { 'class': 'primaer', text: 'Fertig', title: 'Speichern und Bearbeitung beenden', onclick: function () { speichern(true); } }),
      el('button', { text: '↶', title: 'Rückgängig (Ctrl+Z)', id: 'undo-knopf', onclick: undo }),
      el('button', { text: '↷', title: 'Wiederherstellen (Ctrl+Y)', id: 'redo-knopf', onclick: redo }),
      el('button', { text: 'Verlauf', title: 'Frühere Fassungen dieser Seite', onclick: verlaufDialog }),
      el('span', { text: 'Menübar:' }), menue,
      profi ? el('button', { text: 'Seiten-CSS', title: 'Eigenes CSS nur für diese Seite', onclick: cssDialog }) : null,
      profi ? verweiseSchalter() : null,
      el('span', { 'class': 'hinweis', text: profi ? 'Niveau: Profi' : 'Niveau: Amateur' }),
      status
    ]);
    main.appendChild(leiste);
    var titelFeld = el('input', { 'class': 'editor-titel', type: 'text', value: seite.titel, id: 'editor-titel', maxlength: '120' });
    titelFeld.addEventListener('input', geaendertVerzoegert);
    main.appendChild(titelFeld);
    main.appendChild(metaZeile());

    var liste = el('div', { id: 'block-liste', 'class': 'block-liste' });
    main.appendChild(liste);
    liste.appendChild(einfuegenAnfang(liste));
    bloecke.forEach(function (b) { liste.appendChild(blockElement(b)); });
    if (!bloecke.length) liste.appendChild(leerHinweis());
    ablageZone(liste);
    main.appendChild(hinzufuegenLeiste(null));
    if (!gespeichertStand) {
      document.addEventListener('keydown', tastatur);
      window.addEventListener('beforeunload', beimVerlassen);
      gespeichertStand = schnappschuss();
      undoStack = [gespeichertStand];
    }
    status.textContent = schnappschuss() === gespeichertStand ? 'gespeichert' : 'ungespeichert';
    undoKnoepfe();
  }

  function metaZeile() {
    /* Datum und Tags der Seite; Tags werden von der Suche gefunden. */
    var datum = el('input', { type: 'date', id: 'editor-datum', value: seite.datum || '', title: 'Datum der Seite (erscheint unter dem Titel)' });
    var tags = el('input', { type: 'text', id: 'editor-tags', list: 'tag-vorschlaege', value: (seite.tags || []).join(', '), placeholder: 'Tags, mit Komma getrennt, z. B. Reflexion, Woche 3', maxlength: '600' });
    var bekannt = {};
    alleSeiten().forEach(function (s) { s.tags.forEach(function (t) { bekannt[t] = 1; }); });
    var vorschlaege = el('datalist', { id: 'tag-vorschlaege' }, Object.keys(bekannt).sort().map(function (t) { return el('option', { value: t }); }));
    datum.addEventListener('change', geaendert);
    tags.addEventListener('input', geaendertVerzoegert);
    return el('div', { 'class': 'editor-meta' }, [
      el('label', null, [el('span', { text: 'Datum' }), datum]),
      el('label', { 'class': 'tags-feld' }, [el('span', { text: 'Tags' }), tags]),
      vorschlaege
    ]);
  }

  function tagsLesen() {
    var f = document.getElementById('editor-tags');
    if (!f) return seite.tags || [];
    var gesehen = {};
    return f.value.split(',').map(function (t) { return t.replace(/^\s*#/, '').trim(); }).filter(function (t) {
      var k = t.toLowerCase(); if (!t || gesehen[k]) return false; gesehen[k] = 1; return true;
    });
  }

  // ---------- Undo / Redo / Autosave ----------

  function zustand() {
    strukturAusDom();
    document.querySelectorAll('.editor-block').forEach(function (e) {
      var t = e.querySelector(':scope > .editor-text'); var b = objekte[e.dataset.id];
      if (t && b) b.html = t.innerHTML;
    });
    var titelFeld = document.getElementById('editor-titel');
    var datumFeld = document.getElementById('editor-datum');
    return { titel: titelFeld ? titelFeld.value : seite.titel, menue: menueEl ? menueEl.value : seite.menue, css: seite.css || '',
      datum: datumFeld ? datumFeld.value : (seite.datum || ''), tags: tagsLesen(), verweise: seite.verweise !== false, bloecke: bloecke };
  }

  function schnappschuss() { return JSON.stringify(zustand()); }

  function geaendert() {
    /* Nach jeder Änderung: Schnappschuss auf den Undo-Stack, Redo verwerfen, Autosave anstossen. */
    var jetzt = schnappschuss();
    if (undoStack.length && undoStack[undoStack.length - 1] === jetzt) return;
    undoStack.push(jetzt);
    if (undoStack.length > 100) undoStack.shift();
    redoStack = [];
    undoKnoepfe();
    if (statusEl) statusEl.textContent = 'ungespeichert';
    autosavePlanen();
  }

  var geaendertTimer = null;
  function geaendertVerzoegert() {
    /* Tippen erzeugt erst nach einer Pause einen Undo-Schritt. */
    clearTimeout(geaendertTimer);
    geaendertTimer = setTimeout(geaendert, 600);
    if (statusEl) statusEl.textContent = 'ungespeichert';
    autosavePlanen();
  }

  function undoKnoepfe() {
    var u = document.getElementById('undo-knopf'), r = document.getElementById('redo-knopf');
    if (u) u.disabled = undoStack.length < 2;
    if (r) r.disabled = !redoStack.length;
  }

  function anwenden(json) {
    var z = JSON.parse(json);
    seite.titel = z.titel; seite.menue = z.menue; seite.css = z.css; seite.datum = z.datum; seite.tags = z.tags; seite.verweise = z.verweise; bloecke = z.bloecke;
    objekte = {};
    aufbauen();
    undoStack.push(json); // aufbauen() hat den Stand übernommen; Stack-Spitze = aktueller Stand
    undoKnoepfe();
    autosavePlanen();
  }

  function undo() {
    clearTimeout(geaendertTimer);
    var jetzt = schnappschuss();
    if (undoStack[undoStack.length - 1] !== jetzt) { undoStack.push(jetzt); }
    if (undoStack.length < 2) return;
    redoStack.push(undoStack.pop());
    var ziel = undoStack.pop();
    anwenden(ziel);
  }

  function redo() {
    if (!redoStack.length) return;
    anwenden(redoStack.pop());
  }

  function autosavePlanen() {
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(function () { speichern(false); }, 2000);
  }

  function beimVerlassen(ev) {
    if (schnappschuss() !== gespeichertStand) {
      speichern(false, true);
      ev.preventDefault(); ev.returnValue = '';
    }
  }

  function leerHinweis() {
    return el('p', { 'class': 'leer-hinweis', text: 'Noch keine Blöcke. Unten einen Block hinzufügen.' });
  }

  function blockTypen(inSpalte) {
    /* Welche Blocktypen gerade zur Wahl stehen (Niveau, Spalten-Kontext, Kompetenzrahmen). */
    var typen = ['text', 'bild', 'video', 'audio', 'pdf', 'datei', 'button', 'trenner'];
    if (profi) typen.splice(2, 0, 'galerie');   // Galerie (Masonry) nur im Profi-Niveau
    if (rahmenListe.length) typen.push('kr');
    if (!inSpalte) typen.push('spalten');
    if (profi) typen.push('html');
    return typen;
  }

  function hinzufuegenLeiste(spaltenListe) {
    var leiste = el('div', { 'class': 'block-hinzufuegen' }, [el('span', { text: spaltenListe ? '+' : 'Block hinzufügen:' })]);
    blockTypen(!!spaltenListe).forEach(function (t) {
      leiste.appendChild(el('button', { 'class': 'klein', text: (spaltenListe ? '' : '+ ') + typName(t), onclick: function () { blockHinzufuegen(t, spaltenListe); } }));
    });
    return leiste;
  }

  function neuerBlock(typ) {
    var b = { id: neueId(), typ: typ };
    if (typ === 'text') b.html = '<p><br></p>';
    if (typ === 'bild') { b.asset = ''; b.bildtext = ''; b.breite = 'voll'; b.ausrichtung = 'links'; }
    if (typ === 'galerie') { b.bilder = []; b.spalten = 3; }
    if (typ === 'video' || typ === 'audio' || typ === 'pdf' || typ === 'datei') b.asset = '';
    if (typ === 'button') { b.text = ''; b.ziel = ''; b.stil = 'voll'; b.ausrichtung = 'links'; }
    if (typ === 'pdf') b.hoehe = 600;
    if (typ === 'html') b.html = '';
    if (typ === 'spalten') b.spalten = [[], []];
    if (typ === 'kr') { b.rahmen = rahmenListe.length === 1 ? rahmenListe[0].id : ''; b.knoten = {}; }
    return b;
  }

  function blockHinzufuegen(typ, spaltenListe) {
    var zielListe = spaltenListe || document.getElementById('block-liste');
    var leer = zielListe.querySelector(':scope > .leer-hinweis'); if (leer) leer.remove();
    var e = blockElement(neuerBlock(typ));
    zielListe.appendChild(e);
    geaendert();
    var t = e.querySelector('.editor-text, textarea');
    if (t) t.focus();
  }

  function blockTypDialog(inSpalte, beiWahl) {
    /* Kleine Auswahl aller Blocktypen – für die «+»-Knöpfe zwischen den Blöcken. */
    var d = L.dialog('Welcher Block soll eingefügt werden?', [
      el('div', { 'class': 'typ-wahl' }, blockTypen(inSpalte).map(function (t) {
        return el('button', { type: 'button', text: typName(t), onclick: function () { d.close(); beiWahl(t); } });
      }))
    ], 'Schliessen', function () {});
    d.querySelector('button[type=submit]').style.display = 'none';
  }

  function blockEinfuegenNach(box) {
    /* Fügt direkt nach diesem Block einen neuen ein – ohne den Umweg über die Leiste ganz unten. */
    blockTypDialog(box.parentNode.classList.contains('spalte'), function (typ) {
      var e = blockElement(neuerBlock(typ));
      box.parentNode.insertBefore(e, box.nextSibling);
      geaendert();
      try { e.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (ex) { /* egal */ }
      var t = e.querySelector('.editor-text, textarea');
      if (t) t.focus();
    });
  }

  function einfuegenAnfang(liste) {
    /* Einfügepunkt ganz oben: Neuer Inhalt zuoberst, ohne einen Block nach oben schieben zu müssen. */
    return el('div', { 'class': 'block-einfuegen block-einfuegen-anfang' }, [
      el('button', { type: 'button', text: '+', title: 'Neuen Block ganz oben einfügen', 'aria-label': 'Neuen Block ganz oben einfügen', onclick: function () {
        blockTypDialog(false, function (typ) {
          var leer = liste.querySelector(':scope > .leer-hinweis'); if (leer) leer.remove();
          var e = blockElement(neuerBlock(typ));
          liste.insertBefore(e, liste.querySelector(':scope > .editor-block'));
          geaendert();
          var t = e.querySelector('.editor-text, textarea');
          if (t) t.focus();
        });
      } })
    ]);
  }

  // ---------- Block-Element ----------

  function blockElement(b) {
    objekte[b.id] = b;
    var gesperrt = !profi && (b.typ === 'html' || b.typ === 'galerie');
    var zuKnopf = el('button', { 'class': 'klapp', text: '▾', title: 'Block einklappen', 'aria-expanded': 'true' });
    var zusammenfassung = el('span', { 'class': 'zusammenfassung' });
    // Aktionen in einer eigenen Gruppe: In schmalen Blöcken (Spalten) klappt sie hinter «⋯» und erscheint
    // dann als eigene Zeile im Kopf, statt über den Rand zu ragen (siehe @container in style.css).
    var aktionen = el('span', { 'class': 'block-aktionen' }, [
      el('button', { text: '▲', title: 'Nach oben', onclick: function () { verschieben(b.id, -1); } }),
      el('button', { text: '▼', title: 'Nach unten', onclick: function () { verschieben(b.id, 1); } }),
      klappEinstellung(b),
      el('button', { text: '⧉', title: 'Duplizieren', onclick: function () { blockDuplizieren(b.id); } }),
      el('button', { 'class': 'gefahr', text: 'Löschen', onclick: function () { blockLoeschen(b.id); } })
    ]);
    var mehr = el('button', { 'class': 'mehr', type: 'button', text: '⋯', title: 'Weitere Aktionen: verschieben, einklappbar, duplizieren, löschen', 'aria-expanded': 'false' });
    var kopf = el('div', { 'class': 'block-kopf' }, [
      el('span', { 'class': 'griff', title: 'Ziehen zum Verschieben', text: '⋮⋮' }),
      zuKnopf,
      el('span', { 'class': 'typ', text: typName(b.typ) + (gesperrt ? ' – für diesen Block auf Profi wechseln' : '') }),
      zusammenfassung,
      mehr,
      aktionen
    ]);
    mehr.addEventListener('click', function () {
      var offen = !kopf.classList.contains('aktionen-offen');
      kopf.classList.toggle('aktionen-offen', offen);
      mehr.setAttribute('aria-expanded', offen ? 'true' : 'false');
    });
    var box = el('div', { 'class': 'editor-block typ-' + b.typ + (gesperrt ? ' gesperrt' : '') + (eingeklappt[b.id] ? ' zu' : ''), 'data-id': b.id, 'data-typ': b.typ, draggable: 'true' }, [kopf]);
    if (eingeklappt[b.id]) { zuKnopf.textContent = '▸'; zuKnopf.title = 'Block ausklappen'; zuKnopf.setAttribute('aria-expanded', 'false'); zusammenfassung.textContent = blockZusammenfassung(b); }
    zuKnopf.addEventListener('click', function () {
      var zu = !box.classList.contains('zu');
      box.classList.toggle('zu', zu);
      eingeklappt[b.id] = zu;
      zuKnopf.textContent = zu ? '▸' : '▾'; zuKnopf.title = zu ? 'Block ausklappen' : 'Block einklappen'; zuKnopf.setAttribute('aria-expanded', zu ? 'false' : 'true');
      zusammenfassung.textContent = zu ? blockZusammenfassung(b) : '';
    });
    if (gesperrt) {
      box.appendChild(el('div', { 'class': 'gesperrt-vorschau', html: vorschauHtml(b) }));
    } else if (b.typ === 'text') {
      box.appendChild(werkzeugLeiste(box));
      var text = el('div', { 'class': 'editor-text', contenteditable: 'true', html: b.html || '' });
      text.addEventListener('input', function () { b.html = text.innerHTML; geaendertVerzoegert(); });
      text.addEventListener('paste', einfuegenAlsText);
      box.appendChild(text);
    } else if (b.typ === 'trenner') {
      box.appendChild(trennerBereich(b));
    } else if (b.typ === 'galerie') {
      box.appendChild(galerieBereich(b));
    } else if (b.typ === 'bild' || b.typ === 'video' || b.typ === 'audio' || b.typ === 'pdf' || b.typ === 'datei') {
      box.appendChild(medienBereich(b, box));
    } else if (b.typ === 'button') {
      box.appendChild(buttonBereich(b));
    } else if (b.typ === 'html') {
      var ta = el('textarea', { 'class': 'editor-code', rows: '8', spellcheck: 'false', placeholder: '<div class="eigen">…</div>' });
      ta.value = b.html || '';
      ta.addEventListener('input', function () { b.html = ta.value; geaendertVerzoegert(); });
      box.appendChild(ta);
      box.appendChild(el('p', { 'class': 'hinweis klein-text', text: 'Rohes HTML, wird ungefiltert eingefügt. Dateien per Pfad assets/… einbinden; der Pfad wird für die Löschlogik erkannt.' }));
    } else if (b.typ === 'spalten') {
      box.appendChild(spaltenBereich(b));
    } else if (b.typ === 'kr') {
      box.appendChild(krBereich(b));
    }
    // «+» am unteren Rand: fügt direkt nach diesem Block einen neuen ein (erscheint beim Überfahren)
    box.appendChild(el('div', { 'class': 'block-einfuegen' }, [
      el('button', { type: 'button', text: '+', title: 'Neuen Block direkt danach einfügen', 'aria-label': 'Neuen Block direkt danach einfügen', onclick: function () { blockEinfuegenNach(box); } })
    ]));
    dragUndDrop(box);
    return box;
  }

  var eingeklappt = {};   // Block-ID -> eingeklappt (nur Editor-Zustand, standardmässig ausgeklappt)
  var rahmenListe = [];   // Kompetenzrahmen (id, titel) aus dem Dashboard
  var rahmenCache = {};   // id -> {rahmen, index}

  // ---------- Kompetenz-Block: Rahmen wählen, Knoten des Baums ankreuzen ----------

  var KR_EBENEN = ['bereich', 'kompetenz', 'stufe', 'punkt'], KR_KINDER = { bereich: 'kompetenzen', kompetenz: 'stufen', stufe: 'punkte' };
  var KR_NAMEN = { bereich: 'Bereich', kompetenz: 'Kompetenz', stufe: 'Stufe', punkt: 'Punkt' };
  var KR_STATUS = [['weiss', 'noch nicht bearbeitet'], ['orange', 'in Bearbeitung'], ['gruen', 'erarbeitet']];

  function rahmenLaden(id) {
    if (rahmenCache[id]) return Promise.resolve(rahmenCache[id]);
    return L.api('GET', '/api/kompetenzrahmen/' + id).then(function (j) { rahmenCache[id] = j; return j; });
  }

  function krBereich(b) {
    var bereich = el('div', { 'class': 'medien-bereich kr-bereich' });
    var wahl = el('select', null, [el('option', { value: '', text: 'Kompetenzrahmen wählen …' })].concat(rahmenListe.map(function (r) { return el('option', { value: r.id, text: r.titel }); })));
    wahl.value = b.rahmen || '';
    var baum = el('div', { 'class': 'kr-wahl' });
    var info = el('span', { 'class': 'klein-text' });
    function zeichnen() {
      baum.innerHTML = '';
      if (!b.rahmen) { info.textContent = 'Kompetenzrahmen anlegen oder importieren im Dashboard unter «Kompetenzen».'; return; }
      info.textContent = 'lädt …';
      rahmenLaden(b.rahmen).then(function (j) {
        info.textContent = 'Ankreuzen, woran diese Seite arbeitet. Den Stand setzt du hier oder später direkt auf der Seite.';
        function knoten(obj, ebene, tiefe) {
          var gewaehlt = Object.prototype.hasOwnProperty.call(b.knoten, obj.id);
          var box = el('input', { type: 'checkbox' }); box.checked = gewaehlt;
          var st = el('select', { 'class': 'kr-status-wahl' }, KR_STATUS.map(function (x) { return el('option', { value: x[0], text: x[1] }); }));
          st.value = b.knoten[obj.id] || 'weiss'; st.hidden = !gewaehlt;
          st.addEventListener('change', function () { b.knoten[obj.id] = st.value; geaendert(); });
          box.addEventListener('change', function () { if (box.checked) b.knoten[obj.id] = st.value; else delete b.knoten[obj.id]; st.hidden = !box.checked; geaendert(); });
          var zeile = el('label', { 'class': 'kr-wahl-zeile kr-wahl-' + ebene, style: 'padding-left:' + (tiefe * 18) + 'px' }, [
            box, el('span', { 'class': 'ka-punkt st-' + ((j.status || {})[obj.id] || 'offen'), title: 'aktueller Stand in der Abbildung' }),
            el('span', { 'class': 'kr-wahl-ebene', text: KR_NAMEN[ebene] }), el('span', { text: obj.titel || '(ohne Titel)' }), st
          ]);
          baum.appendChild(zeile);
          (obj[KR_KINDER[ebene]] || []).forEach(function (k) { knoten(k, KR_EBENEN[KR_EBENEN.indexOf(ebene) + 1], tiefe + 1); });
        }
        (j.rahmen.bereiche || []).forEach(function (br) { knoten(br, 'bereich', 0); });
        if (!(j.rahmen.bereiche || []).length) baum.appendChild(el('p', { 'class': 'hinweis', text: 'Dieser Rahmen hat noch keine Bereiche.' }));
      }).catch(function (e) { info.textContent = 'Fehler: ' + e.message; });
    }
    wahl.addEventListener('change', function () { b.rahmen = wahl.value; b.knoten = {}; geaendert(); zeichnen(); });
    bereich.appendChild(el('div', { 'class': 'medien-felder' }, [wahl, info]));
    bereich.appendChild(baum);
    zeichnen();
    return bereich;
  }

  function blockZusammenfassung(b) {
    /* Kurztext für eingeklappte Blöcke. */
    var t = '';
    if (b.typ === 'text' || b.typ === 'html') { var d = document.createElement('div'); d.innerHTML = b.html || ''; t = (d.textContent || '').trim(); }
    else if (b.typ === 'button') t = b.text || '';
    else if (b.typ === 'bild') t = b.bildtext || (assetCache[b.asset] || {}).name || '';
    else if (b.typ === 'galerie') t = (b.bilder || []).length + ' Bilder';
    else if (b.typ === 'video' || b.typ === 'audio' || b.typ === 'pdf' || b.typ === 'datei') t = (assetCache[b.asset] || {}).name || '';
    else if (b.typ === 'spalten') t = b.spalten.length + ' Spalten, ' + b.spalten.reduce(function (n, s) { return n + s.length; }, 0) + ' Blöcke';
    else if (b.typ === 'kr') t = Object.keys(b.knoten || {}).length + ' Kompetenzen gewählt';
    return t.length > 70 ? t.slice(0, 70) + '…' : t;
  }

  function klappEinstellung(b) {
    /* Auf der fertigen Seite einklappbar? normal | offen | zu, dazu ein Titel. */
    var sel = el('select', { 'class': 'klapp-wahl', title: 'Auf der Seite ein-/ausklappbar' }, [
      el('option', { value: '', text: 'Seite: normal' }),
      el('option', { value: 'offen', text: 'Seite: einklappbar, offen' }),
      el('option', { value: 'zu', text: 'Seite: einklappbar, zu' })
    ]);
    sel.value = b.klapp || '';
    var titel = el('input', { type: 'text', 'class': 'klapp-titel', placeholder: 'Titel des Abschnitts', maxlength: '120', value: b.klappTitel || '' });
    titel.hidden = !b.klapp;
    sel.addEventListener('change', function () { b.klapp = sel.value || undefined; if (!sel.value) delete b.klapp; titel.hidden = !sel.value; if (sel.value && !titel.value) titel.focus(); geaendert(); });
    titel.addEventListener('input', function () { b.klappTitel = titel.value; geaendertVerzoegert(); });
    titel.addEventListener('mousedown', function (ev) { ev.stopPropagation(); });
    return el('span', { 'class': 'klapp-einstellung' }, [sel, titel]);
  }

  function blockDuplizieren(id) {
    var b = blockVonId(id);
    if (!b) return;
    var kopie = JSON.parse(JSON.stringify(b));
    (function neueIds(x) { x.id = neueId(); objekte[x.id] = x; if (x.typ === 'spalten') x.spalten.forEach(function (sp) { sp.forEach(neueIds); }); })(kopie);
    var e = document.querySelector('.editor-block[data-id="' + id + '"]');
    e.parentNode.insertBefore(blockElement(kopie), e.nextSibling);
    geaendert();
  }

  function vorschauHtml(b) {
    if (b.typ === 'html') return '<pre class="code-vorschau">' + (b.html || '').replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</pre>';
    if (b.typ === 'galerie') return '<p class="hinweis">Galerie (Masonry) mit ' + (b.bilder || []).length + ' Bildern.</p>';
    if (b.typ === 'spalten') return '<p class="hinweis">' + b.spalten.length + ' Spalten mit ' + b.spalten.reduce(function (n, s) { return n + s.length; }, 0) + ' Blöcken.</p>';
    return '';
  }

  // ---------- Werkzeuge ----------

  function werkzeugLeiste(box) {
    var leiste = el('div', { 'class': 'werkzeuge' });
    WERKZEUGE_AMATEUR.concat(profi ? WERKZEUGE_PROFI : []).forEach(function (w) {
      var btn = el('button', { type: 'button', text: w.text, title: w.title, tabindex: '-1' });
      if (w.stil) btn.setAttribute('style', w.stil);
      btn.addEventListener('mousedown', function (ev) { ev.preventDefault(); }); // Auswahl behalten
      btn.addEventListener('click', function () {
        var text = box.querySelector('.editor-text');
        text.focus();
        if (w.cmd) document.execCommand(w.cmd, false, null);
        else if (w.block) document.execCommand('formatBlock', false, w.block);
        else if (w.link) { linkDialog(text); return; }
        else if (w.fussnote) { fussnoteDialog(text); return; }
        else if (w.farbe) farbeWaehlen(text);
        else if (w.tabelle) document.execCommand('insertHTML', false, '<table><tbody><tr><td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>&nbsp;</td><td>&nbsp;</td></tr></tbody></table><p></p>');
        text.dispatchEvent(new Event('input'));
        clearTimeout(geaendertTimer); geaendert();
      });
      leiste.appendChild(btn);
    });
    return leiste;
  }

  function farbeWaehlen(text) {
    var eingabe = el('input', { type: 'color', value: '#1f5f8b' });
    eingabe.style.position = 'fixed'; eingabe.style.opacity = '0';
    document.body.appendChild(eingabe);
    eingabe.addEventListener('input', function () { text.focus(); document.execCommand('foreColor', false, eingabe.value); text.dispatchEvent(new Event('input')); });
    eingabe.addEventListener('change', function () { eingabe.remove(); });
    eingabe.click();
  }

  /* ---------- Interne Links, Fussnoten ---------- */

  function alleSeiten() {
    /* Alle echten Seiten (ohne Weiterleitungen) aus menu.js, mit Verzeichnispfad für die Anzeige. */
    var namen = {}, liste = [];
    (L.daten.verzeichnisse || []).forEach(function (v) { namen[v.id] = v; });
    function weg(v) { var t = []; while (v) { t.unshift(v.name); v = namen[v.eltern]; } return t.join(' › '); }
    (L.daten.verzeichnisse || []).forEach(function (v) {
      v.seiten.forEach(function (s) { if (!s.redirect) liste.push({ pfad: s.pfad, titel: s.titel, ort: weg(v), tags: s.tags || [] }); });
    });
    return liste;
  }

  function seitenWahl(beiWahl) {
    /* Suchfeld + Liste aller Seiten; ruft beiWahl(seite) beim Klick. */
    var suche = el('input', { type: 'search', placeholder: 'Seite suchen (Titel, Verzeichnis, Tag) …' });
    var liste = el('div', { 'class': 'seiten-wahl' });
    function zeichnen() {
      var q = suche.value.trim().toLowerCase();
      liste.innerHTML = '';
      var treffer = alleSeiten().filter(function (s) {
        return s.pfad !== pfad && (!q || (s.titel + ' ' + s.ort + ' ' + s.tags.join(' ')).toLowerCase().indexOf(q) >= 0);
      });
      if (!treffer.length) liste.appendChild(el('p', { 'class': 'hinweis', text: 'Keine passende Seite.' }));
      treffer.slice(0, 200).forEach(function (s) {
        liste.appendChild(el('button', { type: 'button', 'class': 'seiten-wahl-eintrag', onclick: function () { beiWahl(s); } }, [
          el('strong', { text: s.titel }), el('span', { 'class': 'klein-text', text: s.ort })
        ]));
      });
    }
    suche.addEventListener('input', zeichnen);
    zeichnen();
    return el('div', null, [suche, liste]);
  }

  function seitenTitel(lp) {
    var p = (lp || '').replace(/^lp:/, '').split('#')[0];
    var s = alleSeiten().filter(function (x) { return x.pfad === p; })[0];
    return s ? s.titel : null;
  }

  function auswahlMerken(text) {
    var sel = window.getSelection();
    if (sel && sel.rangeCount && text.contains(sel.anchorNode)) return sel.getRangeAt(0).cloneRange();
    var r = document.createRange(); r.selectNodeContents(text); r.collapse(false); return r;
  }
  function auswahlZurueck(text, bereich) {
    text.focus();
    var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(bereich);
  }
  function htmlEsc(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function linkDialog(text) {
    var bereich = auswahlMerken(text);
    var markiert = !bereich.collapsed;
    var adresse = el('input', { type: 'url', placeholder: 'https://…' });
    var fertig = function (href, titel) {
      d.close();
      auswahlZurueck(text, bereich);
      if (markiert) document.execCommand('createLink', false, href);
      else document.execCommand('insertHTML', false, '<a href="' + htmlEsc(href) + '">' + htmlEsc(titel || href) + '</a>&nbsp;');
      text.dispatchEvent(new Event('input')); clearTimeout(geaendertTimer); geaendert();
    };
    var d = L.dialog('Link einfügen', [
      el('p', { 'class': 'hinweis', text: markiert ? 'Der markierte Text wird zum Link.' : 'Es wird ein Link mit dem Seitentitel eingefügt. Tipp: Zuerst Text markieren, dann wird dieser zum Link.' }),
      el('h3', { text: 'Seite in Liloport' }),
      seitenWahl(function (s) { fertig('lp:' + s.pfad, s.titel); }),
      el('p', { 'class': 'klein-text', text: 'Interne Links bleiben gültig, wenn Verzeichnisse umbenannt werden. Die Zielseite zeigt unten «Verlinkt von».' }),
      el('h3', { text: 'oder Webadresse' }),
      L.feld('Adresse', adresse)
    ], 'Webadresse verlinken', function () {
      var ziel = adresse.value.trim();
      if (!ziel || ziel === 'https://') throw new Error('Bitte eine Seite wählen oder eine Adresse eingeben.');
      if (/^\s*(javascript|data|vbscript):/i.test(ziel)) throw new Error('Diese Adresse ist nicht erlaubt.');
      fertig(ziel, ziel);
      throw { bleiben: true };
    });
  }

  function fussnoteDialog(text) {
    var bereich = auswahlMerken(text);
    bereich.collapse(false);
    var eingabe = el('textarea', { rows: '3', maxlength: '1000', placeholder: 'z. B. Müller, A. (2024). Lernen mit Portfolios. S. 12.' });
    var d = L.dialog('Fussnote einfügen', [
      el('p', { 'class': 'hinweis', text: 'Die Fussnote erscheint im Text als hochgestellte Zahl und unten auf der Seite als nummerierte Liste. Nummeriert wird automatisch.' }),
      L.feld('Text der Fussnote', eingabe)
    ], 'Einfügen', function () {
      var t = eingabe.value.trim();
      if (!t) throw new Error('Bitte einen Text eingeben.');
      d.close();   // erst schliessen: solange der modale Dialog offen ist, nimmt der Text keinen Fokus an
      // nicht in eine bestehende Fussnote oder einen Link hinein einfügen
      var drin = bereich.startContainer.nodeType === 1 ? bereich.startContainer : bereich.startContainer.parentNode;
      var huelle = drin && drin.closest && drin.closest('.fussnote, a');
      if (huelle && text.contains(huelle)) { bereich.setStartAfter(huelle); bereich.collapse(true); }
      auswahlZurueck(text, bereich);
      document.execCommand('insertHTML', false, '<span class="fussnote">' + htmlEsc(t) + '</span>&#8203;');
      text.dispatchEvent(new Event('input')); clearTimeout(geaendertTimer); geaendert();
    });
  }

  function einfuegenAlsText(ev) {
    ev.preventDefault();
    var text = (ev.clipboardData || window.clipboardData).getData('text/plain');
    document.execCommand('insertText', false, text);
  }

  function tastatur(ev) {
    if (!(ev.ctrlKey || ev.metaKey)) return;
    if (ev.key === 's') { ev.preventDefault(); speichern(false); return; }
    var imText = ev.target.closest && ev.target.closest('.editor-text, textarea, input');
    if (imText) return; // Im Text übernimmt der Browser Undo/Redo der Tastatur
    if (ev.key === 'z' && !ev.shiftKey) { ev.preventDefault(); undo(); }
    if (ev.key === 'y' || (ev.key === 'z' && ev.shiftKey)) { ev.preventDefault(); redo(); }
  }

  function verweiseSchalter() {
    /* Profi: Abschnitt «Verlinkt von» unten auf der Seite ein- oder ausblenden. */
    var box = el('input', { type: 'checkbox', id: 'editor-verweise' });
    box.checked = seite.verweise !== false;
    box.addEventListener('change', function () { seite.verweise = box.checked; geaendert(); });
    return el('label', { 'class': 'editor-schalter', title: 'Zeigt unten auf der Seite, welche anderen Seiten hierher verlinken' }, [box, el('span', { text: '«Verlinkt von» zeigen' })]);
  }

  function cssDialog() {
    var ta = el('textarea', { rows: '14', spellcheck: 'false', placeholder: 'h2 { color: #1f5f8b }\n.eigen { padding: 1em }' });
    ta.value = seite.css || '';
    var fehler = el('div', { 'class': 'fehlermeldung' });
    var form = el('form', { method: 'dialog' }, [
      el('h2', { text: 'Seiten-CSS' }),
      el('p', { 'class': 'hinweis', text: 'Gilt nur für diese Seite. Jeder Selektor wird automatisch mit .seite-' + document.body.dataset.slug + ' eingegrenzt; !important ist nicht nötig.' }),
      el('div', { 'class': 'feld' }, [ta]), fehler,
      el('div', { 'class': 'dialog-fuss' }, [
        el('button', { type: 'button', text: 'Abbrechen', onclick: function () { d.close(); } }),
        el('button', { type: 'submit', 'class': 'primaer', text: 'Übernehmen' })
      ])
    ]);
    var d = el('dialog', null, [form]);
    form.addEventListener('submit', function (ev) { ev.preventDefault(); seite.css = ta.value; d.close(); geaendert(); });
    d.addEventListener('close', function () { d.remove(); });
    document.body.appendChild(d); d.showModal(); ta.focus();
  }

  // ---------- Medien ----------

  function medienBereich(b, box) {
    var bereich = el('div', { 'class': 'medien-bereich' });
    function neuZeichnen() {
      bereich.innerHTML = '';
      var a = assetCache[b.asset];
      if (!a) { bereich.appendChild(auswahlBereich(b, neuZeichnen)); return; }
      var vorschau;
      if (b.typ === 'bild') vorschau = el('img', { src: rel + a.datei, alt: '' });
      else if (b.typ === 'video') vorschau = el('video', { src: rel + a.datei, controls: '' });
      else if (b.typ === 'audio') vorschau = el('audio', { src: rel + a.datei, controls: '', preload: 'metadata' });
      else if (b.typ === 'datei') vorschau = el('div', { 'class': 'datei-vorschau', text: '🗜 ' + a.name + ' (' + groesse(a.groesse) + ') – auf der Seite öffnet ein Klick den Ordner der Datei' });
      else vorschau = el('div', { 'class': 'pdf-vorschau', text: '📄 ' + a.name + ' (' + groesse(a.groesse) + ')' });
      var felder = el('div', { 'class': 'medien-felder' });
      felder.appendChild(el('span', { 'class': 'klein-text', text: a.name + ' · Heimat: ' + a.heimat + (a.heimat !== pfad ? ' (eingebettet)' : '') }));
      if (b.typ === 'bild') {
        var bt = el('input', { type: 'text', placeholder: 'Bildtext (Beschriftung)', value: b.bildtext || '', maxlength: '300' });
        bt.addEventListener('input', function () { b.bildtext = bt.value; geaendertVerzoegert(); });
        var br = el('select', null, [
          el('option', { value: 'voll', text: 'Breite: voll' }), el('option', { value: 'halb', text: 'Breite: halb' }), el('option', { value: 'klein', text: 'Breite: klein' })
        ]);
        if (profi) br.appendChild(el('option', { value: 'frei', text: 'Breite: frei (px oder %)' }));
        var frei = el('input', { type: 'text', placeholder: 'z. B. 320px oder 40%', size: '14' });
        var istFrei = ['voll', 'halb', 'klein'].indexOf(b.breite || 'voll') < 0;
        br.value = istFrei ? (profi ? 'frei' : 'voll') : (b.breite || 'voll');
        frei.value = istFrei ? b.breite : '';
        frei.style.display = (br.value === 'frei') ? '' : 'none';
        br.addEventListener('change', function () { frei.style.display = br.value === 'frei' ? '' : 'none'; b.breite = br.value === 'frei' ? (frei.value || 'voll') : br.value; geaendert(); });
        frei.addEventListener('input', function () { if (/^\d{1,4}(px|%)$/.test(frei.value.trim())) { b.breite = frei.value.trim(); geaendertVerzoegert(); } });
        felder.appendChild(bt); felder.appendChild(br); felder.appendChild(frei);
        felder.appendChild(ausrichtungSelect(b));
      }
      if (b.typ === 'pdf') {
        var h = el('input', { type: 'number', min: '200', max: '2000', step: '50', value: b.hoehe || 600, title: 'Höhe in Pixel' });
        h.addEventListener('input', function () { b.hoehe = parseInt(h.value, 10) || 600; geaendertVerzoegert(); });
        felder.appendChild(el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Höhe:' }), h, el('span', { text: 'px' })]));
        var sNr = el('input', { type: 'number', min: '1', max: '99999', step: '1', value: b.seite || 1, title: 'Auf welcher Seite das PDF beim Öffnen steht' });
        sNr.addEventListener('input', function () { var n = parseInt(sNr.value, 10); b.seite = n > 1 ? n : undefined; geaendertVerzoegert(); });
        felder.appendChild(el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Öffnen auf Seite:' }), sNr]));
        felder.appendChild(el('p', { 'class': 'klein-text pdf-hinweis', text: 'Der Text des PDFs ist gleich nach dem Hochladen in der Suche des Dashboards (auch bei mehreren hundert Seiten nach wenigen Sekunden). Gescannte PDFs ohne Textebene findet die Suche nur über den Dateinamen. Die Startseite beachten Chrome, Edge und Firefox; Safari zeigt das PDF unter Umständen ab Seite 1.' }));
      }
      felder.appendChild(el('button', { 'class': 'klein', text: 'Andere Datei', onclick: function () { b.asset = ''; neuZeichnen(); geaendert(); } }));
      bereich.appendChild(el('div', { 'class': 'medien-vorschau' }, [vorschau]));
      bereich.appendChild(felder);
    }
    neuZeichnen();
    return bereich;
  }

  function buttonBereich(b) {
    var text = el('input', { type: 'text', placeholder: 'Beschriftung, z. B. «Zum Projekt»', value: b.text || '', maxlength: '120' });
    text.addEventListener('input', function () { b.text = text.value; geaendertVerzoegert(); });
    var ziel = el('input', { type: 'url', placeholder: 'Webadresse https://… oder «Seite wählen»', value: (b.ziel || '').indexOf('lp:') === 0 ? '' : (b.ziel || '') });
    var intern = el('span', { 'class': 'klein-text intern-ziel' });
    function internZeigen() {
      var istIntern = (b.ziel || '').indexOf('lp:') === 0;
      intern.textContent = istIntern ? '→ Seite: ' + (seitenTitel(b.ziel) || b.ziel.slice(3) + ' (nicht gefunden)') : '';
      ziel.hidden = istIntern;
    }
    ziel.addEventListener('input', function () { b.ziel = ziel.value; geaendertVerzoegert(); });
    var wahl = el('button', { type: 'button', 'class': 'klein', text: 'Seite wählen', onclick: function () {
      var d = L.dialog('Ziel des Buttons', [seitenWahl(function (s) { b.ziel = 'lp:' + s.pfad; if (!b.text) { b.text = s.titel; text.value = s.titel; } internZeigen(); d.close(); geaendert(); })], 'Schliessen', function () {});
    } });
    var webadresse = el('button', { type: 'button', 'class': 'klein', text: 'Webadresse', onclick: function () { b.ziel = ''; ziel.value = ''; internZeigen(); ziel.focus(); geaendert(); } });
    internZeigen();
    var stil = el('select', null, [el('option', { value: 'voll', text: 'Stil: gefüllt' }), el('option', { value: 'umrandet', text: 'Stil: umrandet' })]);
    stil.value = b.stil || 'voll';
    stil.addEventListener('change', function () { b.stil = stil.value; geaendert(); });
    return el('div', { 'class': 'medien-bereich' }, [
      el('div', { 'class': 'medien-felder' }, [text, ziel, intern, wahl, webadresse]),
      el('div', { 'class': 'medien-felder' }, [stil, ausrichtungSelect(b)])
    ]);
  }

  function groesse(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB'; }

  function auswahlBereich(b, fertig) {
    var akzeptiert = { bild: 'image/*', video: 'video/mp4,video/webm',
      audio: 'audio/mpeg,audio/mp4,audio/x-m4a,audio/ogg,audio/wav,audio/flac,.mp3,.m4a,.ogg,.oga,.wav,.flac',
      pdf: 'application/pdf', datei: '.zip,application/zip' }[b.typ];
    var datei = el('input', { type: 'file', accept: akzeptiert });
    var status = el('span', { 'class': 'klein-text' });
    var zone = el('div', { 'class': 'ablage-zone' }, [
      el('p', { text: typName(b.typ) + ' hierher ziehen oder' }),
      el('button', { 'class': 'klein', text: 'Datei wählen', onclick: function () { datei.click(); } }),
      status
    ]);
    datei.style.display = 'none';
    zone.appendChild(datei);
    function hochladen(f) {
      if (!f) return;
      status.textContent = 'lädt hoch … 0 %';
      new Promise(function (ok, nein) {
        // XMLHttpRequest statt fetch: zeigt den Fortschritt, wichtig bei grossen Videos (kein Grössenlimit)
        var x = new XMLHttpRequest();
        x.open('POST', '/api/upload/' + pfad);
        x.setRequestHeader('Content-Type', 'application/octet-stream');
        x.setRequestHeader('X-Dateiname', encodeURIComponent(f.name));
        x.upload.onprogress = function (ev) {
          if (ev.lengthComputable) status.textContent = 'lädt hoch … ' + Math.floor(ev.loaded * 100 / ev.total) + ' % von ' + groesse(ev.total);
        };
        x.onload = function () { try { ok(JSON.parse(x.responseText)); } catch (e) { nein(new Error('Antwort unlesbar')); } };
        x.onerror = function () { nein(new Error('Verbindung unterbrochen')); };
        x.send(f);
      })
        .then(function (j) {
          if (j.fehler) throw new Error(j.fehler);
          assetCache[j.asset.id] = j.asset;
          if (j.asset.typ !== b.typ) { status.textContent = 'Die Datei ist ein ' + typName(j.asset.typ) + ', kein ' + typName(b.typ) + '. Sie liegt unter «Nicht verwendete Dateien» im Dashboard.'; return; }
          b.asset = j.asset.id;
          geaendert();
          if (j.asset.hinweis && !hinweisSchonGezeigt) { hinweisSchonGezeigt = true; alert('Hinweis: Die Datei ist grösser als 50 MB. Das geht, aber grosse Dateien machen Backups und Exporte langsamer, und beim Export auf einen Webserver gelten dessen Grenzen.'); }
          fertig();
        })
        .catch(function (e) { status.textContent = 'Fehler: ' + e.message; });
    }
    datei.addEventListener('change', function () { hochladen(datei.files[0]); });
    zone.addEventListener('dragover', function (ev) { if (ev.dataTransfer.types.indexOf('Files') >= 0) { ev.preventDefault(); ev.stopPropagation(); zone.classList.add('aktiv'); } });
    zone.addEventListener('dragleave', function () { zone.classList.remove('aktiv'); });
    zone.addEventListener('drop', function (ev) { if (ev.dataTransfer.files.length) { ev.preventDefault(); ev.stopPropagation(); zone.classList.remove('aktiv'); hochladen(ev.dataTransfer.files[0]); } });

    var tabs = el('div', { 'class': 'tabs' });
    var inhalt = el('div');
    var vorhanden = vorhandeneDateien(b, fertig);
    var tabNeu = el('button', { 'class': 'klein aktiv', text: 'Hochladen' });
    var tabAlt = el('button', { 'class': 'klein', text: 'Vorhandene Datei' });
    tabNeu.addEventListener('click', function () { tabNeu.classList.add('aktiv'); tabAlt.classList.remove('aktiv'); inhalt.innerHTML = ''; inhalt.appendChild(zone); });
    tabAlt.addEventListener('click', function () { tabAlt.classList.add('aktiv'); tabNeu.classList.remove('aktiv'); inhalt.innerHTML = ''; inhalt.appendChild(vorhanden); });
    tabs.appendChild(tabNeu); tabs.appendChild(tabAlt);
    inhalt.appendChild(zone);
    return el('div', null, [tabs, inhalt]);
  }

  function vorhandeneDateien(b, fertig) {
    var liste = el('div', { 'class': 'asset-liste' });
    var passend = Object.keys(assetCache).map(function (k) { return assetCache[k]; }).filter(function (a) { return a.typ === b.typ; });
    if (!passend.length) return el('p', { 'class': 'hinweis', text: 'Noch keine passende Datei vorhanden.' });
    passend.forEach(function (a) {
      var eintrag = el('button', { 'class': 'asset-eintrag', type: 'button' }, [
        a.typ === 'bild' ? el('img', { src: rel + a.datei, alt: '' }) : el('span', { 'class': 'asset-symbol', text: a.typ === 'pdf' ? '📄' : a.typ === 'audio' ? '🎵' : '🎞' }),
        el('span', { 'class': 'asset-name', text: a.name }),
        el('span', { 'class': 'klein-text', text: 'Heimat: ' + a.heimat })
      ]);
      eintrag.addEventListener('click', function () { b.asset = a.id; fertig(); geaendert(); });
      liste.appendChild(eintrag);
    });
    return liste;
  }

  // ---------- Trenner: Farbe, Dicke, Linienart, Abstand ----------

  var TRENNER_ARTEN = [['', 'durchgezogen'], ['gestrichelt', 'gestrichelt'], ['gepunktet', 'gepunktet'], ['doppelt', 'doppelt']];
  var TRENNER_CSS = { gestrichelt: 'dashed', gepunktet: 'dotted', doppelt: 'double' };
  var TRENNER_STANDARDFARBE = '#e3dccf';   // var(--pg-rand) hell; nur als Vorbelegung des Farbwählers

  function trennerBereich(b) {
    var hr = el('hr');
    function vorschau() {
      var art = TRENNER_CSS[b.stil] || 'solid';
      var dicke = parseInt(b.dicke, 10) || 1;
      if (art === 'double' && dicke < 3) dicke = 3;
      hr.style.border = '0';
      hr.style.borderTop = dicke + 'px ' + art + ' ' + (b.farbe || 'var(--pg-rand)');
      hr.style.marginTop = b.abstandOben === undefined ? '' : b.abstandOben + 'px';
      hr.style.marginBottom = b.abstandUnten === undefined ? '' : b.abstandUnten + 'px';
    }
    var farbe = el('input', { type: 'color', value: /^#[0-9a-fA-F]{6}$/.test(b.farbe || '') ? b.farbe : TRENNER_STANDARDFARBE, title: 'Farbe der Linie' });
    farbe.addEventListener('input', function () { b.farbe = farbe.value; vorschau(); geaendertVerzoegert(); });
    var farbeWeg = el('button', { 'class': 'klein', type: 'button', text: 'Standardfarbe', title: 'Zurück zur Standardfarbe der Seite', onclick: function () {
      delete b.farbe; farbe.value = TRENNER_STANDARDFARBE; vorschau(); geaendert();
    } });
    var art = el('select', null, TRENNER_ARTEN.map(function (x) { return el('option', { value: x[0], text: x[1] }); }));
    art.value = TRENNER_CSS[b.stil] ? b.stil : '';
    art.addEventListener('change', function () { if (art.value) b.stil = art.value; else delete b.stil; vorschau(); geaendert(); });
    var dicke = el('input', { type: 'number', min: '1', max: '20', step: '1', value: b.dicke || 1, title: 'Dicke der Linie in Pixel' });
    dicke.addEventListener('input', function () {
      var n = parseInt(dicke.value, 10);
      if (n > 1 && n <= 20) b.dicke = n; else delete b.dicke;
      vorschau(); geaendertVerzoegert();
    });
    function abstandFeld(schluessel, titel) {
      var feldEl = el('input', { type: 'number', min: '0', max: '200', step: '2', placeholder: 'Standard', title: titel });
      if (b[schluessel] !== undefined) feldEl.value = b[schluessel];
      feldEl.addEventListener('input', function () {
        var n = parseInt(feldEl.value, 10);
        if (feldEl.value !== '' && n >= 0 && n <= 200) b[schluessel] = n; else delete b[schluessel];
        vorschau(); geaendertVerzoegert();
      });
      return feldEl;
    }
    var oben = abstandFeld('abstandOben', 'Abstand zum Block davor in Pixel (leer = Standard)');
    var unten = abstandFeld('abstandUnten', 'Abstand zum Block danach in Pixel (leer = Standard)');
    vorschau();
    return el('div', { 'class': 'editor-trenner' }, [
      hr,
      el('div', { 'class': 'medien-felder trenner-felder' }, [
        el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Farbe:' }), farbe, farbeWeg]),
        el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Linienart:' }), art]),
        el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Dicke:' }), dicke, el('span', { text: 'px' })]),
        el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Abstand oben:' }), oben, el('span', { text: 'px' })]),
        el('label', { 'class': 'feld-zeile' }, [el('span', { text: 'Abstand unten:' }), unten, el('span', { text: 'px' })])
      ]),
      el('p', { 'class': 'klein-text', text: 'Abstand oben/unten vergrössert oder verkleinert die Distanz zum vorherigen bzw. nächsten Block. Leer = Standardabstand.' })
    ]);
  }

  // ---------- Galerie (Masonry, Profi) ----------

  function dateiHochladen(f, status) {
    /* Lädt eine Datei hoch (XMLHttpRequest mit Fortschritt, kein Grössenlimit); gibt Promise mit dem Asset. */
    return new Promise(function (ok, nein) {
      var x = new XMLHttpRequest();
      x.open('POST', '/api/upload/' + pfad);
      x.setRequestHeader('Content-Type', 'application/octet-stream');
      x.setRequestHeader('X-Dateiname', encodeURIComponent(f.name));
      x.upload.onprogress = function (ev) {
        if (ev.lengthComputable && status) status.textContent = f.name + ' lädt hoch … ' + Math.floor(ev.loaded * 100 / ev.total) + ' %';
      };
      x.onload = function () {
        try {
          var j = JSON.parse(x.responseText);
          if (j.fehler) return nein(new Error(j.fehler));
          assetCache[j.asset.id] = j.asset;
          ok(j.asset);
        } catch (e) { nein(new Error('Antwort unlesbar')); }
      };
      x.onerror = function () { nein(new Error('Verbindung unterbrochen')); };
      x.send(f);
    });
  }

  function galerieBereich(b) {
    var bereich = el('div', { 'class': 'medien-bereich galerie-bereich' });
    b.bilder = b.bilder || [];
    var spaltenWahl = el('select', null, [2, 3, 4].map(function (n) { return el('option', { value: String(n), text: n + ' Spalten' }); }));
    spaltenWahl.value = String(b.spalten >= 2 && b.spalten <= 4 ? b.spalten : 3);
    spaltenWahl.addEventListener('change', function () { b.spalten = parseInt(spaltenWahl.value, 10); geaendert(); });
    var status = el('span', { 'class': 'klein-text' });
    var raster = el('div', { 'class': 'galerie-editor' });
    function zeichnen() {
      raster.innerHTML = '';
      b.bilder.forEach(function (bild, i) {
        var a = assetCache[bild.asset];
        var bt = el('input', { type: 'text', placeholder: 'Bildtext (optional)', value: bild.bildtext || '', maxlength: '300' });
        bt.addEventListener('input', function () { bild.bildtext = bt.value; geaendertVerzoegert(); });
        raster.appendChild(el('div', { 'class': 'galerie-eintrag' }, [
          a ? el('img', { src: rel + a.datei, alt: '' }) : el('span', { 'class': 'asset-symbol', text: '🖼' }),
          bt,
          el('span', { 'class': 'galerie-aktionen' }, [
            el('button', { type: 'button', text: '◀', title: 'Nach vorne', onclick: function () { if (i > 0) { b.bilder.splice(i - 1, 0, b.bilder.splice(i, 1)[0]); zeichnen(); geaendert(); } } }),
            el('button', { type: 'button', text: '▶', title: 'Nach hinten', onclick: function () { if (i < b.bilder.length - 1) { b.bilder.splice(i + 1, 0, b.bilder.splice(i, 1)[0]); zeichnen(); geaendert(); } } }),
            el('button', { type: 'button', 'class': 'gefahr', text: '✕', title: 'Aus der Galerie entfernen (die Datei bleibt erhalten)', onclick: function () { b.bilder.splice(i, 1); zeichnen(); geaendert(); } })
          ])
        ]));
      });
      if (!b.bilder.length) raster.appendChild(el('p', { 'class': 'hinweis', text: 'Noch keine Bilder. Die Galerie zeigt Bilder im Masonry-Layout: in Spalten, jedes Bild in seiner Originalproportion.' }));
    }
    var datei = el('input', { type: 'file', accept: 'image/*', multiple: '' });
    datei.style.display = 'none';
    datei.addEventListener('change', function () {
      var dateien = [].slice.call(datei.files);
      datei.value = '';
      dateien.reduce(function (kette, f) {
        return kette.then(function () { return dateiHochladen(f, status); }).then(function (a) {
          if (a.typ !== 'bild') { status.textContent = f.name + ' ist kein Bild und wurde nicht aufgenommen (liegt unter «Nicht verwendete Dateien»).'; return; }
          b.bilder.push({ asset: a.id, bildtext: '' });
          zeichnen(); geaendert();
          status.textContent = '';
        });
      }, Promise.resolve()).catch(function (e) { status.textContent = 'Fehler: ' + e.message; });
    });
    var hochladen = el('button', { type: 'button', 'class': 'klein', text: '+ Bilder hochladen', title: 'Eine oder mehrere Bilddateien wählen', onclick: function () { datei.click(); } });
    var vorhandene = el('button', { type: 'button', 'class': 'klein', text: '+ Vorhandenes Bild', onclick: function () {
      var passend = Object.keys(assetCache).map(function (k) { return assetCache[k]; }).filter(function (a) { return a.typ === 'bild'; });
      if (!passend.length) { alert('Noch keine Bilder hochgeladen.'); return; }
      var liste = el('div', { 'class': 'asset-liste' });
      passend.forEach(function (a) {
        var eintrag = el('button', { 'class': 'asset-eintrag', type: 'button' }, [
          el('img', { src: rel + a.datei, alt: '' }),
          el('span', { 'class': 'asset-name', text: a.name })
        ]);
        eintrag.addEventListener('click', function () { b.bilder.push({ asset: a.id, bildtext: '' }); zeichnen(); geaendert(); d.close(); });
        liste.appendChild(eintrag);
      });
      var d = L.dialog('Bild für die Galerie wählen', [liste], 'Schliessen', function () {});
    } });
    zeichnen();
    bereich.appendChild(el('div', { 'class': 'medien-felder' }, [spaltenWahl, hochladen, vorhandene, status, datei]));
    bereich.appendChild(raster);
    return bereich;
  }

  // ---------- Spalten ----------

  function spaltenBereich(b) {
    var bereich = el('div', { 'class': 'spalten-bereich' });
    var kopf = el('div', { 'class': 'spalten-kopf' }, [el('span', { text: 'Anzahl Spalten:' })]);
    var anzahl = el('select', null, [2, 3, 4].map(function (n) { return el('option', { value: String(n), text: String(n) }); }));
    anzahl.value = String(b.spalten.length);
    anzahl.addEventListener('change', function () {
      var n = parseInt(anzahl.value, 10);
      strukturAusDom();
      while (b.spalten.length < n) b.spalten.push([]);
      if (b.spalten.length > n) {
        var rest = b.spalten.slice(n).reduce(function (acc, s) { return acc.concat(s); }, []);
        b.spalten = b.spalten.slice(0, n);
        b.spalten[n - 1] = b.spalten[n - 1].concat(rest);
      }
      raster.innerHTML = ''; spaltenZeichnen();
      geaendert();
    });
    kopf.appendChild(anzahl);
    var raster = el('div', { 'class': 'spalten-raster' });
    function spaltenZeichnen() {
      raster.className = 'spalten-raster spalten-' + b.spalten.length;
      b.spalten.forEach(function (sp, i) {
        var liste = el('div', { 'class': 'spalte block-liste', 'data-spalte': String(i) });
        sp.forEach(function (x) { liste.appendChild(blockElement(x)); });
        ablageZone(liste);
        var huelle = el('div', { 'class': 'spalte-huelle' }, [liste, hinzufuegenLeiste(liste)]);
        raster.appendChild(huelle);
      });
    }
    spaltenZeichnen();
    bereich.appendChild(kopf); bereich.appendChild(raster);
    return bereich;
  }

  // ---------- Reihenfolge / Struktur ----------

  function strukturAusDom() {
    /* Baut `bloecke` aus der DOM-Reihenfolge neu auf (inkl. Spalten); Blockobjekte bleiben dieselben. */
    function lesen(liste) {
      return Array.prototype.filter.call(liste.children, function (e) { return e.classList.contains('editor-block'); }).map(function (e) {
        var b = objekte[e.dataset.id];
        if (b.typ === 'spalten' && !e.classList.contains('gesperrt')) {
          b.spalten = Array.prototype.map.call(e.querySelectorAll(':scope > .spalten-bereich > .spalten-raster > .spalte-huelle > .spalte'), lesen);
        }
        return b;
      });
    }
    bloecke = lesen(document.getElementById('block-liste'));
  }

  function verschieben(id, richtung) {
    var e = document.querySelector('.editor-block[data-id="' + id + '"]');
    if (!e) return;
    var liste = e.parentNode;
    var geschwister = Array.prototype.filter.call(liste.children, function (x) { return x.classList.contains('editor-block'); });
    var i = geschwister.indexOf(e);
    if (richtung < 0 && i > 0) liste.insertBefore(e, geschwister[i - 1]);
    if (richtung > 0 && i < geschwister.length - 1) liste.insertBefore(geschwister[i + 1], e);
    geaendert();
  }

  function blockLoeschen(id) {
    var b = blockVonId(id);
    if (!b) return;
    var hatInhalt = (b.typ === 'text' && (b.html || '').replace(/<[^>]+>/g, '').trim()) || b.asset || b.typ === 'spalten' || (b.typ === 'html' && b.html) || (b.typ === 'button' && (b.text || b.ziel));
    if (hatInhalt && !confirm('Diesen ' + typName(b.typ) + '-Block löschen?' + (b.asset ? ' Die Datei bleibt erhalten, solange eine Seite sie nutzt.' : ''))) return;
    var e = document.querySelector('.editor-block[data-id="' + id + '"]');
    var liste = e.parentNode;
    e.remove();
    geaendert();
    if (!liste.querySelector(':scope > .editor-block') && liste.id === 'block-liste') liste.appendChild(leerHinweis());
  }

  var gezogen = null;
  function dragUndDrop(box) {
    box.addEventListener('dragstart', function (ev) {
      if (ev.target !== box && ev.target.closest('.editor-block') !== box) return;
      if (ev.target.closest('.editor-text, textarea, input')) { ev.preventDefault(); return; }
      ev.stopPropagation();
      gezogen = box; box.classList.add('ziehen');
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('text/plain', box.dataset.id);
    });
    box.addEventListener('dragend', function () {
      box.classList.remove('ziehen'); gezogen = null;
      document.querySelectorAll('.ablage-oben, .ablage-unten, .ablage-leer').forEach(function (e) { e.classList.remove('ablage-oben', 'ablage-unten', 'ablage-leer'); });
    });
    box.addEventListener('dragover', function (ev) {
      if (!gezogen || gezogen === box || gezogen.contains(box)) return;
      if (!zielErlaubt(box.parentNode)) return;
      ev.preventDefault(); ev.stopPropagation();
      ev.dataTransfer.dropEffect = 'move';
      var r = box.getBoundingClientRect();
      var oben = ev.clientY < r.top + r.height / 2; // Entscheidung nur vertikal
      box.classList.toggle('ablage-oben', oben);
      box.classList.toggle('ablage-unten', !oben);
    });
    box.addEventListener('dragleave', function () { box.classList.remove('ablage-oben', 'ablage-unten'); });
    box.addEventListener('drop', function (ev) {
      if (!gezogen || gezogen === box || gezogen.contains(box)) return;
      ev.preventDefault(); ev.stopPropagation();
      var oben = box.classList.contains('ablage-oben');
      box.classList.remove('ablage-oben', 'ablage-unten');
      box.parentNode.insertBefore(gezogen, oben ? box : box.nextSibling);
      geaendert();
    });
  }

  function zielErlaubt(liste) {
    /* Blöcke dürfen in jede Liste, auch in Spalten; nur ein Spalten-Block nie in eine Spalte. */
    if (!gezogen) return false;
    if (gezogen.dataset.typ === 'spalten' && liste.classList.contains('spalte')) return false;
    return true;
  }

  function ablageZone(liste) {
    /* Ablegen in eine leere Liste oder unter den letzten Block. */
    liste.addEventListener('dragover', function (ev) {
      if (!gezogen || !zielErlaubt(liste)) return;
      if (ev.target !== liste && ev.target.closest('.editor-block')) return;
      ev.preventDefault(); ev.stopPropagation(); liste.classList.add('ablage-leer');
    });
    liste.addEventListener('dragleave', function () { liste.classList.remove('ablage-leer'); });
    liste.addEventListener('drop', function (ev) {
      if (!gezogen || !zielErlaubt(liste)) return;
      if (ev.target !== liste && ev.target.closest('.editor-block')) return;
      ev.preventDefault(); ev.stopPropagation(); liste.classList.remove('ablage-leer');
      var leer = liste.querySelector(':scope > .leer-hinweis'); if (leer) leer.remove();
      liste.appendChild(gezogen);
      geaendert();
    });
  }

  /* ---------- Automatisches Scrollen beim Ziehen ----------
     Nähert sich der gezogene Block dem oberen oder unteren Fensterrand, scrollt die Seite von selbst –
     so lässt sich ein Block auch auf einer langen Seite von ganz unten nach ganz oben ziehen. */

  var autoScrollY = null, autoScrollRaf = null;

  function autoScrollSchritt() {
    autoScrollRaf = null;
    if (autoScrollY === null) return;
    var oben = 150, unten = 110, max = 28, h = window.innerHeight, dy = 0;
    if (autoScrollY < oben) dy = -Math.ceil((oben - autoScrollY) / oben * max);
    else if (autoScrollY > h - unten) dy = Math.ceil((autoScrollY - (h - unten)) / unten * max);
    if (dy) {
      window.scrollBy(0, dy);
      autoScrollRaf = requestAnimationFrame(autoScrollSchritt);
    }
  }

  document.addEventListener('dragover', function (ev) {
    if (!gezogen) return;
    autoScrollY = ev.clientY;
    if (!autoScrollRaf) autoScrollRaf = requestAnimationFrame(autoScrollSchritt);
  });
  ['drop', 'dragend'].forEach(function (name) {
    document.addEventListener(name, function () { autoScrollY = null; });
  });

  // ---------- Speichern ----------

  var konfliktOffen = false;
  function konfliktDialog(j, schliessen) {
    if (konfliktOffen) return;
    konfliktOffen = true;
    var d = L.dialog('Seite wurde anderswo geändert', [
      el('p', { text: 'Diese Seite wurde gespeichert, während du sie bearbeitet hast – vermutlich auf einem anderen Gerät oder durch die Synchronisation eines Cloud-Ordners (Stand ' + String(j.geaendert || '').replace('T', ' ') + ').' }),
      el('p', { 'class': 'hinweis', text: '«Meine Fassung speichern» überschreibt die andere Fassung; sie bleibt im Verlauf erhalten. «Andere Fassung laden» verwirft deine ungespeicherten Änderungen.' }),
      el('button', { type: 'button', text: 'Andere Fassung laden', onclick: function () { window.removeEventListener('beforeunload', beimVerlassen); location.reload(); } })
    ], 'Meine Fassung speichern', function () {
      konfliktOffen = false; erzwingen = true; speichern(schliessen);
    });
    d.addEventListener('close', function () { konfliktOffen = false; });
  }
  var erzwingen = false;
  // Kennung dieses Editors: Der Server erkennt daran eigene frühere Speicherungen (kein falscher Konflikt)
  var editorKennung = Math.random().toString(36).slice(2) + Date.now().toString(36);
  var nachholen = null;   // während ein Speichern läuft, angefordertes weiteres Speichern (z. B. «Fertig»)

  function weiterNachSpeichern() {
    speichertGerade = false;
    if (nachholen) { var n = nachholen; nachholen = null; speichern(n.schliessen); }
  }

  function speichern(schliessen, keepalive) {
    clearTimeout(autosaveTimer);
    if (konfliktOffen) return;
    var z = zustand();
    var json = JSON.stringify(z);
    if (!schliessen && json === gespeichertStand) { if (statusEl) statusEl.textContent = 'gespeichert'; return; }
    var titel = (z.titel || '').trim();
    if (!titel) { statusEl.textContent = 'Der Titel darf nicht leer sein.'; return; }
    // Nie zwei Speichervorgänge gleichzeitig: Der zweite würde mit dem alten Stand als Basis gesendet und
    // als «anderswo geändert» abgewiesen. Stattdessen nach dem laufenden nachholen (mit «Fertig» gemerkt).
    if (speichertGerade && !keepalive) { nachholen = { schliessen: schliessen || (nachholen && nachholen.schliessen) }; return; }
    speichertGerade = true;
    statusEl.textContent = 'speichert …';
    fetch('/api/seiten/' + pfad, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, keepalive: !!keepalive,
      body: JSON.stringify({ titel: titel, menue: z.menue, bloecke: z.bloecke, css: z.css, datum: z.datum, tags: z.tags, verweise: z.verweise,
        basis: seite.geaendert, erzwingen: erzwingen, editor: editorKennung }) })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.konflikt) { speichertGerade = false; nachholen = null; statusEl.textContent = 'nicht gespeichert: Konflikt'; konfliktDialog(j, schliessen); return; }
        if (j.fehler) throw new Error(j.fehler);
        erzwingen = false;
        seite.geaendert = j.seite.geaendert;
        gespeichertStand = json;
        statusEl.textContent = 'gespeichert';
        if (schliessen) { speichertGerade = false; window.removeEventListener('beforeunload', beimVerlassen); location.hash = ''; location.reload(); return; }
        weiterNachSpeichern();
      })
      .catch(function (e) { statusEl.textContent = 'Fehler: ' + e.message; weiterNachSpeichern(); });
  }

  // ---------- Verlauf ----------

  function verlaufDialog() {
    speichern(false);
    L.api('GET', '/api/verlauf/' + pfad).then(function (j) {
      var liste = el('div', { 'class': 'verlauf-liste' });
      if (!j.versionen.length) liste.appendChild(el('p', { 'class': 'hinweis', text: 'Noch keine früheren Fassungen. Jede Speicherung legt eine an.' }));
      j.versionen.forEach(function (v) {
        var zeile = el('div', { 'class': 'verlauf-zeile' }, [
          el('span', { 'class': 'verlauf-zeit', text: v.zeit.replace('T', ' ') }),
          el('span', { 'class': 'klein-text', text: v.bloecke + ' Blöcke · ' + (v.geaendert ? v.geaendert + ' Unterschiede zur aktuellen Fassung' : 'wie aktuell') }),
          el('a', { 'class': 'knopf klein', href: '/_vorschau/' + pfad + '?v=' + encodeURIComponent(v.id), target: '_blank', text: 'Vorschau' }),
          el('button', { 'class': 'klein', type: 'button', text: 'Wiederherstellen', onclick: function () {
            if (!confirm('Diese Fassung vom ' + v.zeit.replace('T', ' ') + ' wiederherstellen? Die aktuelle Fassung bleibt im Verlauf.')) return;
            L.api('POST', '/api/verlauf/' + pfad, { v: v.id }).then(function () { window.removeEventListener('beforeunload', beimVerlassen); location.reload(); }).catch(function (e) { alert(e.message); });
          } })
        ]);
        if (profi && v.geaendert) {
          var d = v.diff;
          var teile = [];
          if (d.geaendert.length) teile.push('geändert: ' + d.geaendert.join(', '));
          if (d.neu.length) teile.push('seither neu: ' + d.neu.join(', '));
          if (d.entfernt.length) teile.push('seither entfernt: ' + d.entfernt.join(', '));
          if (d.titel) teile.push('Titel'); if (d.css) teile.push('CSS');
          zeile.appendChild(el('span', { 'class': 'klein-text verlauf-diff', text: teile.join(' · ') }));
        }
        liste.appendChild(zeile);
      });
      var form = el('form', { method: 'dialog' }, [
        el('h2', { text: 'Verlauf' }),
        el('p', { 'class': 'hinweis', text: 'Die letzten 50 Fassungen bis 90 Tage zurück. Vorschau öffnet die Fassung in einem neuen Tab.' }),
        liste,
        el('div', { 'class': 'dialog-fuss' }, [el('button', { type: 'submit', text: 'Schliessen' })])
      ]);
      var dlg = el('dialog', { 'class': 'breit' }, [form]);
      dlg.addEventListener('close', function () { dlg.remove(); });
      document.body.appendChild(dlg); dlg.showModal();
    }).catch(function (e) { alert(e.message); });
  }

  window.LiloportEditor = { starten: starten };
})();
