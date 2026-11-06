// v0.12: Tabellen-Editor (Profi), Umbruch langer Links, Drucken (A4) mit Hinweisen und ausgeklappten Blöcken.
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/tabellen-druck.e2e.js http://127.0.0.1:8787 [ordner für PDF/Bilder]
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://127.0.0.1:8787';
const AUS = process.argv[3];
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }

(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  const p = await ctx.newPage(); const fehler = []; p.on('pageerror', e => fehler.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await p.waitForURL(/willkommen/);
  const seite = B + '/beispiel-portfolio/semester-1/lernjournal.html';
  await p.goto(seite);
  await p.click('.kopf .schalter button:has-text("Profi")'); await p.waitForLoadState('load'); await p.waitForTimeout(300);

  // Druckknopf: dezent, links neben «Exportieren»
  const knoepfe = await p.$$eval('#seiten-werkzeuge > button', bs => bs.map(b => b.className || b.textContent.trim()));
  ok('Druckknopf links neben Exportieren', knoepfe[0] === 'druck-knopf' && /Exportieren/.test(knoepfe[1] || ''), knoepfe.join(' | '));
  ok('Druckknopf dezent', Number(await p.$eval('.druck-knopf', b => getComputedStyle(b).opacity)) < 0.8);

  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('.editor-block');
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("Text")');
  const block = p.locator('.editor-block.typ-text').last();
  const text = block.locator('.editor-text');
  await text.click(); await p.keyboard.type('Übersicht der Wochen');
  await p.keyboard.press('Enter');

  // Tabelle einfügen: 4×3, Kopfzeile, Design Teal
  await block.locator('.werkzeuge button[title^="Tabelle einfügen"]').click();
  const pop = block.locator('.tab-popover');
  ok('Einfügen-Dialog mit 7 Designs', (await pop.locator('.tab-design').count()) === 7);
  await pop.locator('input[aria-label="Zeilen"]').fill('4');
  await pop.locator('input[aria-label="Spalten"]').fill('3');
  await pop.locator('.tab-design[data-design="tab-teal"]').click();
  await pop.locator('button:has-text("Einfügen")').click();
  const t = text.locator('table');
  ok('Tabelle eingefügt', (await t.count()) === 1 && (await t.locator('thead th').count()) === 3 && (await t.locator('tbody tr').count()) === 3, await t.evaluate(x => x.outerHTML.slice(0, 120)));
  ok('Design Teal', await t.evaluate(x => x.classList.contains('tab-teal')));
  ok('Tabellen-Leiste sichtbar', await block.locator('.tabellen-leiste').isVisible());

  // In die erste Körperzelle, tippen, Tab weiter
  await t.locator('tbody td').first().click();
  await p.keyboard.type('Woche 1'); await p.keyboard.press('Tab'); await p.keyboard.type('Ziel');
  ok('Tab springt in die nächste Zelle', (await t.locator('tbody tr').first().locator('td').nth(1).textContent()).includes('Ziel'));
  const leiste = block.locator('.tabellen-leiste');
  await leiste.locator('button[title="Spalte rechts einfügen"]').click();
  ok('Spalte eingefügt', (await t.locator('thead th').count()) === 4);
  await leiste.locator('button[title="Spalte löschen"]').click();
  ok('Spalte gelöscht', (await t.locator('thead th').count()) === 3);
  await leiste.locator('button[title="Zeile unterhalb einfügen"]').click();
  ok('Zeile eingefügt', (await t.locator('tbody tr').count()) === 4);
  // Erste Körperzeile gelb hinterlegen (Bereich: Zeile)
  await t.locator('tbody td').first().click();
  await leiste.locator('.tab-bereich button:has-text("Zeile")').click();
  await leiste.locator('button:has-text("Farbe")').click();
  await leiste.locator('.farb-palette .farb-muster[data-farbe="#fdf0a6"]').click();
  const farben = await t.locator('tbody tr').first().locator('td').evaluateAll(cs => cs.map(c => c.style.backgroundColor));
  ok('Ganze Zeile gefärbt', farben.length === 3 && farben.every(f => f === 'rgb(253, 240, 166)'), farben.join());
  // Spalte 3 rechtsbündig
  await t.locator('tbody tr').nth(1).locator('td').nth(2).click();
  await leiste.locator('.tab-bereich button:has-text("Spalte")').click();
  await leiste.locator('button[title="Rechtsbündig"]').click();
  const ausr = await t.locator('tr').evaluateAll(rs => rs.map(r => r.cells[2].style.textAlign));
  ok('Ganze Spalte rechtsbündig', ausr.every(a => a === 'right'), ausr.join());
  for (const s of ['Summenzeile', 'Volle Breite', 'Beschriftung']) await leiste.locator('.tab-schalt:has-text("' + s + '")').click();
  await p.keyboard.type('Wochenplan');
  ok('Beschriftung gesetzt', (await t.locator('caption').textContent()).trim() === 'Wochenplan');
  await t.locator('tbody td').first().click();
  await leiste.locator('button:has-text("Design …")').click();
  await leiste.locator('.tab-design[data-design="tab-gestreift"]').click();
  ok('Design gewechselt', await t.evaluate(x => x.classList.contains('tab-gestreift') && !x.classList.contains('tab-teal')));
  // Kopfzeile aus und wieder an
  await leiste.locator('.tab-schalt:has-text("Kopfzeile")').click();
  ok('Kopfzeile aus', (await t.locator('thead').count()) === 0 && (await t.locator('th').count()) === 0);
  await leiste.locator('.tab-schalt:has-text("Kopfzeile")').click();
  ok('Kopfzeile wieder an', (await t.locator('thead th').count()) === 3);

  // Sehr langer Link
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("Text")');
  const lang = 'https://example.org/' + 'sehr-langer-pfad-'.repeat(23) + 'ende';
  await p.locator('.editor-block.typ-text .editor-text').last().evaluate((e, u) => { e.innerHTML = '<p>Quelle: <a href="' + u + '">' + u + '</a></p>'; e.dispatchEvent(new Event('input')); }, lang);

  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForLoadState('load'); await p.waitForSelector('.tabelle-rahmen');
  const gespeichert = await p.$eval('.tabelle-rahmen table', x => ({ k: x.className, cap: x.caption && x.caption.textContent, th: x.querySelectorAll('thead th').length, bg: x.tBodies[0].rows[0].cells[0].style.backgroundColor, breite: x.getBoundingClientRect().width, rahmen: x.parentNode.getBoundingClientRect().width }));
  ok('Tabelle gespeichert mit Design und Zusätzen', /tab-gestreift/.test(gespeichert.k) && /tab-breit/.test(gespeichert.k) && /tab-summe/.test(gespeichert.k) && gespeichert.cap === 'Wochenplan' && gespeichert.th === 3 && gespeichert.bg === 'rgb(253, 240, 166)', JSON.stringify(gespeichert));
  ok('Volle Breite', Math.abs(gespeichert.breite - gespeichert.rahmen) < 2);
  const ueber = await p.evaluate(() => ({ seite: document.documentElement.scrollWidth, fenster: innerWidth, link: Math.max(...[...document.querySelectorAll('.inhalt a')].map(a => a.getBoundingClientRect().right)), inhalt: document.querySelector('.inhalt').getBoundingClientRect().right }));
  ok('Langer Link bricht um (kein Überlauf)', ueber.seite <= ueber.fenster && ueber.link <= ueber.inhalt + 1, JSON.stringify(ueber));

  // Druckansicht
  await p.emulateMedia({ media: 'print' });
  await p.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  const druck = await p.evaluate(() => ({
    kopf: getComputedStyle(document.querySelector('.kopf')).display,
    werkzeuge: getComputedStyle(document.getElementById('seiten-werkzeuge')).display,
    klappOffen: [...document.querySelectorAll('details.klapp')].every(d => d.open),
    klappSichtbar: [...document.querySelectorAll('details.klapp .klapp-inhalt')].every(k => k.getBoundingClientRect().height > 0),
    buttonInfo: [...document.querySelectorAll('.druck-button-info')].map(e => getComputedStyle(e).display),
    hintergrund: getComputedStyle(document.body).backgroundColor
  }));
  ok('Druck: Kopf und Werkzeuge ausgeblendet', druck.kopf === 'none' && druck.werkzeuge === 'none', JSON.stringify(druck));
  ok('Druck: Eingeklapptes ausgeklappt', druck.klappOffen && druck.klappSichtbar);
  ok('Druck: weisser Hintergrund', druck.hintergrund === 'rgb(255, 255, 255)', druck.hintergrund);
  if (AUS) await p.pdf({ path: AUS + '/druck-lernjournal.pdf', format: 'A4', preferCSSPageSize: true, printBackground: true });
  await p.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  await p.emulateMedia({ media: 'screen' });
  ok('Nach dem Druck wieder eingeklappt', await p.evaluate(() => [...document.querySelectorAll('details.klapp')].some(d => !d.open)));

  // Projekt A: ZIP-Datei → Hinweis im Druck
  await p.goto(B + '/beispiel-portfolio/semester-1/projekte/projekt-a.html');
  await p.emulateMedia({ media: 'print' });
  const zip = await p.evaluate(() => { const h = document.querySelector('.block-datei .druck-hinweis'); return h ? getComputedStyle(h).display + ' | ' + h.textContent : ''; });
  const knopfInfo = await p.$$eval('.druck-button-info', es => es.map(e => getComputedStyle(e).display + ' ' + e.textContent));
  ok('Druck: Hinweis unter Schaltflächen', knopfInfo.length > 0 && knopfInfo.every(d => /^block Schaltfläche/.test(d)), knopfInfo.join(' | '));
  ok('Druck: Hinweis statt ZIP-Karte', /^flex \| ZIP-Archiv.*heruntergeladen/.test(zip) && await p.$eval('.block-datei .datei-karte', e => getComputedStyle(e).display === 'none'), zip);
  if (AUS) await p.pdf({ path: AUS + '/druck-projekt-a.pdf', format: 'A4', preferCSSPageSize: true, printBackground: true });

  ok('Keine JavaScript-Fehler', !fehler.length, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})();
