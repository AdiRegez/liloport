/* Liloport – comment-editor.js: Formatierbare Kommentare auf exportierten Seiten.
   Werkzeugleiste + contenteditable, umschaltbar auf HTML-Quelltext. Vor dem Senden und vor dem
   Anzeigen wird HTML gegen eine Whitelist gefiltert (Server filtert zusätzlich). */
(function () {
  'use strict';

  var ERLAUBT = {
    p: [], br: [], h2: [], h3: [], h4: [], strong: [], b: [], em: [], i: [], u: [], s: [], sub: [], sup: [],
    ul: [], ol: [], li: [], blockquote: [], code: [], pre: [], hr: [], span: ['style'],
    a: ['href', 'title'], img: ['src', 'alt', 'width', 'height'],
    table: [], thead: [], tbody: [], tr: [], th: [], td: []
  };
  var UMBENENNEN = { b: 'strong', i: 'em', strike: 's', div: 'p' };
  var STIL_OK = /^(color|background-color|text-align)\s*:\s*[#a-zA-Z0-9 ,.()%-]+$/;

  function hrefSicher(w) {
    w = (w || '').trim().toLowerCase();
    return /^(https?:|mailto:|#|\/|\.\/|\.\.\/)/.test(w) || (w.indexOf(':') < 0);
  }
  function srcSicher(w) { return /^(https?:\/\/|\.\/|\.\.\/|assets\/)/i.test((w || '').trim()); }

  function filtern(html) {
    /* Baut den Baum neu auf: nur erlaubte Tags und Attribute bleiben. */
    var doc = new DOMParser().parseFromString('<div>' + (html || '') + '</div>', 'text/html');
    var wurzel = doc.body.firstChild;
    function kopieren(knoten, ziel) {
      Array.prototype.forEach.call(knoten.childNodes, function (k) {
        if (k.nodeType === 3) { ziel.appendChild(document.createTextNode(k.nodeValue)); return; }
        if (k.nodeType !== 1) return;
        var tag = k.tagName.toLowerCase();
        tag = UMBENENNEN[tag] || tag;
        if (!ERLAUBT.hasOwnProperty(tag)) { kopieren(k, ziel); return; }  // unbekanntes Tag: nur Inhalt behalten
        if (tag === 'p' && k.querySelector('ul,ol,h2,h3,h4,blockquote,pre,table,p,div')) { kopieren(k, ziel); return; }  // Blöcke nicht in Absätze packen
        var neu = document.createElement(tag);
        ERLAUBT[tag].forEach(function (attr) {
          var w = k.getAttribute(attr);
          if (w === null) return;
          if (attr === 'href' && !hrefSicher(w)) return;
          if (attr === 'src' && !srcSicher(w)) return;
          if (attr === 'style') { w = w.split(';').map(function (d) { return d.trim(); }).filter(function (d) { return STIL_OK.test(d) && d.toLowerCase().indexOf('url') < 0; }).join('; '); if (!w) return; }
          neu.setAttribute(attr, w);
        });
        if (tag === 'a') { neu.setAttribute('rel', 'noopener nofollow'); neu.setAttribute('target', '_blank'); }
        kopieren(k, neu);
        ziel.appendChild(neu);
      });
    }
    var out = document.createElement('div');
    kopieren(wurzel, out);
    return out.innerHTML;
  }

  function textLaenge(html) { var d = document.createElement('div'); d.innerHTML = html; return (d.textContent || '').replace(/\u00a0/g, ' ').trim().length + d.querySelectorAll('img').length; }

  function editor(form) {
    /* Ersetzt das <textarea name="text"> durch Werkzeugleiste + Editorfeld; das textarea bleibt als Träger. */
    var ta = form.querySelector('textarea[name=text]');
    if (!ta || ta.dataset.editor) return;
    ta.dataset.editor = '1';
    var feld = document.createElement('div');
    feld.className = 'kommentar-editor'; feld.contentEditable = 'true'; feld.setAttribute('data-platzhalter', 'Kommentar schreiben …');
    feld.innerHTML = '<p><br></p>';
    feld.addEventListener('focus', function () { if (!feld.innerHTML.trim()) feld.innerHTML = '<p><br></p>'; });
    var quelle = document.createElement('textarea'); quelle.className = 'kommentar-quelle'; quelle.rows = 8; quelle.hidden = true; quelle.spellcheck = false;
    var leiste = document.createElement('div'); leiste.className = 'werkzeuge kommentar-werkzeuge';
    var imQuelltext = false;
    var werkzeuge = [
      ['bold', 'F', 'Fett', 'font-weight:700'], ['italic', 'K', 'Kursiv', 'font-style:italic'], ['underline', 'U', 'Unterstrichen', 'text-decoration:underline'],
      ['h2', 'H2', 'Überschrift'], ['h3', 'H3', 'Zwischenüberschrift'], ['p', '¶', 'Absatz'],
      ['insertUnorderedList', '• Liste', 'Aufzählung'], ['insertOrderedList', '1. Liste', 'Nummerierte Liste'],
      ['blockquote', '❝', 'Zitat'], ['pre', '</>', 'Code'], ['link', 'Link', 'Link einfügen'], ['removeFormat', '⌫', 'Formatierung entfernen'], ['html', 'HTML', 'HTML-Quelltext bearbeiten']
    ];
    werkzeuge.forEach(function (w) {
      var b = document.createElement('button'); b.type = 'button'; b.textContent = w[1]; b.title = w[2]; b.tabIndex = -1;
      if (w[3]) b.setAttribute('style', w[3]);
      b.addEventListener('mousedown', function (ev) { ev.preventDefault(); });
      b.addEventListener('click', function () {
        if (w[0] === 'html') { umschalten(); return; }
        if (imQuelltext) return;
        feld.focus();
        if (['h2', 'h3', 'p', 'blockquote', 'pre'].indexOf(w[0]) >= 0) document.execCommand('formatBlock', false, w[0]);
        else if (w[0] === 'link') {
          var sel = window.getSelection();
          if (!sel || sel.isCollapsed) { alert('Zuerst den Text markieren, der zum Link werden soll.'); return; }
          var ziel = prompt('Link-Adresse:', 'https://');
          if (ziel && hrefSicher(ziel)) document.execCommand('createLink', false, ziel.trim());
        } else document.execCommand(w[0], false, null);
      });
      leiste.appendChild(b);
    });
    function umschalten() {
      imQuelltext = !imQuelltext;
      if (imQuelltext) { quelle.value = feld.innerHTML; feld.hidden = true; quelle.hidden = false; quelle.focus(); }
      else { feld.innerHTML = filtern(quelle.value); quelle.hidden = true; feld.hidden = false; feld.focus(); }
      leiste.lastChild.classList.toggle('aktiv', imQuelltext);
    }
    feld.addEventListener('paste', function (ev) {
      ev.preventDefault();
      var html = ev.clipboardData.getData('text/html'), text = ev.clipboardData.getData('text/plain');
      if (html) document.execCommand('insertHTML', false, filtern(html)); else document.execCommand('insertText', false, text);
    });
    try { document.execCommand('styleWithCSS', false, false); } catch (e) { /* egal */ }  // echte <b>/<i>/<u>-Tags statt style-Spans
    ta.hidden = true; ta.required = false;
    // Editor ausserhalb des <label> einhängen: ein Klick ins Label würde sonst das versteckte textarea aktivieren
    var label = ta.closest('label') || ta;
    var huelle = document.createElement('div'); huelle.className = 'kommentar-editor-huelle';
    label.parentNode.insertBefore(huelle, label.nextSibling);
    huelle.appendChild(leiste); huelle.appendChild(feld); huelle.appendChild(quelle);
    form.addEventListener('submit', function () {
      var html = filtern(imQuelltext ? quelle.value : feld.innerHTML);
      ta.value = textLaenge(html) ? html : '';
    }, true);
    return {
      leeren: function () { feld.innerHTML = '<p><br></p>'; quelle.value = ''; if (imQuelltext) umschalten(); },
      setzen: function (html) { feld.innerHTML = /<[a-z][\s\S]*>/i.test(html) ? filtern(html) : '<p></p>'; if (!/<[a-z][\s\S]*>/i.test(html)) feld.firstChild.textContent = html; },
      wert: function () { return filtern(imQuelltext ? quelle.value : feld.innerHTML); },
      leer: function () { return !textLaenge(imQuelltext ? quelle.value : feld.innerHTML); }
    };
  }

  window.LiloportKommentarEditor = { filtern: filtern, editor: editor, textLaenge: textLaenge };
})();
