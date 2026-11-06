// Formatierung v0.12: Fett/Kursiv/Unterstrichen überstehen das Speichern, Schriftfarbe (Palette, HEX, RGB),
// Textmarker mit angepasster Schriftfarbe, «zuletzt bearbeitet», Nach-oben/Nach-unten-Knopf.
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/formatierung.e2e.js http://127.0.0.1:8787
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://127.0.0.1:8787';
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }

(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage(); const fehler = []; p.on('pageerror', e => fehler.push(e.message)); p.on('dialog', d => d.accept());

  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await p.waitForURL(/willkommen/);
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html');
  await p.click('.kopf .schalter button:has-text("Profi")'); await p.waitForLoadState('load'); await p.waitForTimeout(300);
  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('.editor-block');

  // Neuer Textblock mit Wörtern, die einzeln formatiert werden
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("Text")');
  const text = p.locator('.editor-block.typ-text .editor-text').last();
  await text.click();
  await p.keyboard.type('Fett Kursiv Unter Palette Hexwert Gelbmarker Dunkelmarker Wegmarker Ende');
  const block = p.locator('.editor-block.typ-text').last();
  async function waehle(wort) {
    await p.evaluate((w) => {
      const t = [...document.querySelectorAll('.editor-block.typ-text .editor-text')].pop();
      t.focus();
      const gang = document.createTreeWalker(t, NodeFilter.SHOW_TEXT); let n;
      while ((n = gang.nextNode())) {
        const i = n.data.indexOf(w);
        if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + w.length); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return; }
      }
      throw new Error('nicht gefunden: ' + w);
    }, wort);
  }
  const knopf = (titel) => block.locator('.werkzeuge button[title^="' + titel + '"]');

  await waehle('Fett'); await knopf('Fett').click();
  await waehle('Kursiv'); await p.keyboard.press('Control+i');
  await waehle('Unter'); await knopf('Unterstrichen').click();

  await waehle('Palette'); await knopf('Schriftfarbe').click();
  ok('Palette Schriftfarbe offen', await block.locator('.farb-palette').isVisible());
  ok('Palette mit HEX-Feld und RGB-Farbwähler', (await block.locator('.farb-palette .farb-hex').count()) === 1 && (await block.locator('.farb-palette button:has-text("RGB")').count()) === 1);
  await block.locator('.farb-palette .farb-muster[data-farbe="#2a7f78"]').click();
  ok('Palette schliesst nach Wahl', (await block.locator('.farb-palette').count()) === 0);

  await waehle('Hexwert'); await knopf('Schriftfarbe').click();
  await block.locator('.farb-hex').fill('c25');
  await block.locator('.farb-hex').press('Enter');

  await waehle('Gelbmarker'); await knopf('Text farbig').click();
  await block.locator('.farb-palette .farb-muster[data-farbe="#fdf0a6"]').click();
  await waehle('Dunkelmarker'); await knopf('Text farbig').click();
  await block.locator('.farb-palette .farb-muster[data-farbe="#3a2e4a"]').click();
  await waehle('Wegmarker'); await knopf('Text farbig').click();
  await block.locator('.farb-palette .farb-muster[data-farbe="#bde0fe"]').click();
  await waehle('Wegmarker'); await knopf('Text farbig').click();
  await block.locator('.farb-palette button:has-text("Markierung entfernen")').click();

  // Escape schliesst die Palette
  await waehle('Ende'); await knopf('Schriftfarbe').click(); await p.keyboard.press('Escape');
  ok('Escape schliesst die Palette', (await block.locator('.farb-palette').count()) === 0);

  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForLoadState('load'); await p.waitForSelector('.block-text');
  const html = await p.evaluate(() => [...document.querySelectorAll('.block-text')].map(e => e.innerHTML).join('\n'));
  const sicht = await p.evaluate(() => {
    const info = (w) => { const t = [...document.querySelectorAll('.block-text *')].filter(e => e.childNodes.length === 1 && e.textContent === w).pop() || null;
      if (!t) return null; const s = getComputedStyle(t); return { tag: t.tagName, farbe: s.color, grund: s.backgroundColor, gewicht: s.fontWeight, stil: s.fontStyle, linie: s.textDecorationLine }; };
    return { fett: info('Fett'), kursiv: info('Kursiv'), unter: info('Unter'), palette: info('Palette'), hex: info('Hexwert'), gelb: info('Gelbmarker'), dunkel: info('Dunkelmarker'), weg: info('Wegmarker') };
  });
  ok('Fett gespeichert', sicht.fett && Number(sicht.fett.gewicht) >= 600, JSON.stringify(sicht.fett));
  ok('Kursiv gespeichert (Ctrl+I)', sicht.kursiv && sicht.kursiv.stil === 'italic', JSON.stringify(sicht.kursiv));
  ok('Unterstrichen gespeichert', sicht.unter && /underline/.test(sicht.unter.linie), JSON.stringify(sicht.unter));
  ok('Schriftfarbe aus Palette', sicht.palette && sicht.palette.farbe === 'rgb(42, 127, 120)', JSON.stringify(sicht.palette));
  ok('Schriftfarbe per HEX (#c25)', sicht.hex && sicht.hex.farbe === 'rgb(204, 34, 85)', JSON.stringify(sicht.hex));
  ok('Heller Marker mit dunkler Schrift', sicht.gelb && sicht.gelb.grund === 'rgb(253, 240, 166)' && sicht.gelb.farbe === 'rgb(42, 42, 40)', JSON.stringify(sicht.gelb));
  ok('Dunkler Marker mit weisser Schrift', sicht.dunkel && sicht.dunkel.grund === 'rgb(58, 46, 74)' && sicht.dunkel.farbe === 'rgb(255, 255, 255)', JSON.stringify(sicht.dunkel));
  ok('Markierung entfernt', !/Wegmarker<\/span>/.test(html) || !/background-color[^>]*>Wegmarker/.test(html), html.match(/.{0,80}Wegmarker/)[0]);
  ok('Kein <font>, kein font-weight im gespeicherten HTML', !/<font|font-weight|font-style/.test(html));

  // «zuletzt bearbeitet» mit Datum und Uhrzeit
  const zuletzt = await p.textContent('.seiten-meta .zuletzt-bearbeitet').catch(() => '');
  ok('«zuletzt bearbeitet» mit Zeit', /zuletzt bearbeitet \d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}/.test(zuletzt), zuletzt);

  // Nach-oben / Nach-unten
  await p.evaluate(() => { document.body.style.minHeight = '5000px'; window.scrollTo(0, 0); });
  await p.waitForTimeout(300);
  ok('Oben: nur «Nach unten» sichtbar', await p.locator('.nach-unten').isVisible() && !(await p.locator('.nach-oben').isVisible()));
  await p.click('.nach-unten'); await p.waitForTimeout(1200);
  const rest = await p.evaluate(() => document.documentElement.scrollHeight - scrollY - innerHeight);
  ok('«Nach unten» scrollt ans Ende', rest < 5, rest);
  ok('Unten: nur «Nach oben» sichtbar', await p.locator('.nach-oben').isVisible() && !(await p.locator('.nach-unten').isVisible()));
  await p.click('.nach-oben'); await p.waitForTimeout(1200);
  ok('«Nach oben» scrollt an den Anfang', (await p.evaluate(() => scrollY)) < 5);

  ok('Keine JavaScript-Fehler', !fehler.length, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})();
