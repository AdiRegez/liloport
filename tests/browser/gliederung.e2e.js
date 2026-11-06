// Gliederung v0.12 (Profi): Hierarchie der Überschriften in drei Designs; Trenner-Vorlagen (Amateur und Profi).
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/gliederung.e2e.js http://127.0.0.1:8787 [bildordner]
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://127.0.0.1:8787';
const BILDER = process.argv[3];
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }

(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1100, height: 1400 } });
  const p = await ctx.newPage(); const fehler = []; p.on('pageerror', e => fehler.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await p.waitForURL(/willkommen/);
  const seite = B + '/beispiel-portfolio/semester-1/projekte/projekt-a.html';
  await p.goto(seite);

  // Amateur: Trenner-Vorlage «Grosse Punkte», keine Gliederungs-Wahl
  await p.click('.kopf .schalter button:has-text("Amateur")'); await p.waitForLoadState('load'); await p.waitForTimeout(300);
  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('.editor-block');
  ok('Amateur: keine Gliederungs-Wahl', (await p.locator('#editor-gliederung').count()) === 0);
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("Trenner")');
  const tr = p.locator('.editor-block.typ-trenner').last();
  ok('Drei Trenner-Vorlagen', (await tr.locator('.trenner-vorlage').count()) === 3);
  await tr.locator('.trenner-vorlage:has-text("Grosse Punkte")').click();
  ok('Felder übernommen', (await tr.locator('.trenner-felder select').inputValue()) === 'gepunktet' && (await tr.locator('.trenner-felder input[type=number]').nth(0).inputValue()) === '8'
    && (await tr.locator('.trenner-felder input[type=number]').nth(1).inputValue()) === '50' && (await tr.locator('.trenner-felder input[type=number]').nth(2).inputValue()) === '50');
  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForLoadState('load'); await p.waitForSelector('.block-trenner');
  const stil = await p.locator('hr.block-trenner').last().getAttribute('style');
  ok('Amateur-Seite mit Standard-Gliederung', (await p.locator('.gliederung.gl-standard').count()) === 1);
  ok('Trenner «Grosse Punkte» gespeichert', /border-top:8px dotted var\(--pg-rand\)/.test(stil) && /margin-top:50px/.test(stil) && /margin-bottom:50px/.test(stil), stil);

  // Profi: Text mit Hierarchie, dann die drei Designs
  await p.click('.kopf .schalter button:has-text("Profi")'); await p.waitForLoadState('load'); await p.waitForTimeout(300);
  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('#editor-gliederung');
  await p.evaluate(() => {
    // vorhandene Blöcke ersetzen wir nicht – neuer Textblock mit Hierarchie oben drauf genügt
  });
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("Text")');
  await p.locator('.editor-block.typ-text .editor-text').last().evaluate(t => {
    t.innerHTML = '<h1>Projektziel</h1><p>Worum es im Projekt geht.</p><h2>Ausgangslage</h2><p>Was vorher war.</p>'
      + '<h3>Beobachtungen</h3><p>Erste Notizen aus der Praxis.</p><h4>Detail</h4><p>Eine Kleinigkeit.</p>'
      + '<h2>Vorgehen</h2><p>Schritte und Methoden.</p><h1>Reflexion</h1><p>Was ich gelernt habe.</p>';
    t.dispatchEvent(new Event('input'));
  });
  for (const [wert, name] of [['linien', 'Leitlinien'], ['flaechen', 'Flächen'], ['nummern', 'Nummeriert']]) {
    if (!(await p.locator('#editor-gliederung').count())) { await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('#editor-gliederung'); }
    await p.selectOption('#editor-gliederung', wert);
    await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForLoadState('load'); await p.waitForSelector('.gliederung');
    ok(name + ': Wrapper', (await p.locator('.gliederung.gl-' + wert).count()) === 1);
    const nr = await p.$$eval('.gl-abschnitt', a => a.map(x => x.dataset.gliederung).join(' '));
    ok(name + ': Abschnitte', /1 1\.1 1\.1\.1 1\.1\.1\.1 1\.2 2$/.test(nr), nr);
    if (wert === 'nummern') ok('Nummern sichtbar', (await p.textContent('.gl-h3 h3')).trim().startsWith('1.1.1'));
    // Alle Überschriften beginnen links auf derselben Höhe (Leitlinien, Nummeriert, Standard)
    if (wert !== 'flaechen') {
      const x = await p.$$eval('.gl-abschnitt > .block-text:first-child > :first-child', hs => hs.map(h => Math.round(h.getBoundingClientRect().left)));
      ok(name + ': Überschriften links bündig', new Set(x).size === 1, x.join(','));
    }
    if (wert === 'linien') {
      const r = await p.$$eval('.gl-h1, .gl-h2, .gl-h3, .gl-h4', a => [...new Set(a.map(e => { const s = getComputedStyle(e); return e.className.match(/gl-h\d/)[0] + ':' + s.borderRightWidth + ' ' + s.borderRightStyle + ' L' + s.borderLeftWidth; }))].sort());
      ok('Leitlinien rechts, gepunktet, Stärke je Ebene', r.join() === 'gl-h1:4px dotted L0px,gl-h2:3px dotted L0px,gl-h3:2px dotted L0px,gl-h4:1px dotted L0px', r.join(' | '));
    }
    if (wert === 'flaechen') {
      const g = await p.$$eval('.gl-abschnitt', a => a.map(e => getComputedStyle(e).backgroundColor));
      ok('Flächen: alle Ebenen als dezent getönte Karten', g.every(c => c !== 'rgba(0, 0, 0, 0)'), g.join(' | '));
    }
    if (BILDER) await p.locator('.gliederung').screenshot({ path: BILDER + '/gl-' + wert + '.png' });
  }
  // wieder aus
  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('#editor-gliederung');
  ok('Wahl bleibt gespeichert', (await p.inputValue('#editor-gliederung')) === 'nummern');
  await p.selectOption('#editor-gliederung', '');
  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForLoadState('load'); await p.waitForSelector('.block-text');
  ok('Zurück auf Standard', (await p.locator('.gliederung.gl-standard').count()) === 1 && (await p.locator('.gl-nr').count()) === 0);
  const xs = await p.$$eval('.gl-abschnitt > .block-text:first-child > :first-child', hs => hs.map(h => Math.round(h.getBoundingClientRect().left)));
  ok('Standard: Überschriften links bündig', new Set(xs).size === 1, xs.join(','));
  if (BILDER) await p.locator('.gliederung').screenshot({ path: BILDER + '/gl-standard.png' });

  ok('Keine JavaScript-Fehler', !fehler.length, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})();
