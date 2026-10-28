// Neuerungen v3.6: ⏻ mittig, Amateur/Profi nur auf Seiten, Passwort-Hinweis, KR-Editor nach Autosave,
// vier Zustände in der Abbildung, «Verlinkt von» ausblenden, PDF-Startseite und Volltextsuche, Blockkopf in Spalten.
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/neuerungen.e2e.js http://127.0.0.1:8787
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const B = process.argv[2] || 'http://127.0.0.1:8787';
const S = fs.mkdtempSync(path.join(require('os').tmpdir(), 'liloport-neu-'));
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }
(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage(); const fehler = []; p.on('pageerror', e => fehler.push(e.message)); p.on('dialog', d => d.accept());

  // Grosses PDF (300 Seiten) für Startseite und Suche
  const pdfSeite = await ctx.newPage(); let h = '<style>.s{page-break-after:always}</style>';
  for (let i = 1; i <= 300; i++) h += '<div class=s><h1>Seite ' + i + '</h1><p>Abschnitt Zebrafink' + i + ' im langen Dokument.</p></div>';
  await pdfSeite.setContent(h); await pdfSeite.pdf({ path: S + '/buch.pdf' }); await pdfSeite.close();

  // 1. Dashboard: Beispiel, kein Niveau-Schalter, ⏻ mittig
  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await p.waitForURL(/willkommen/);
  await p.goto(B + '/');
  ok('Dashboard ohne Amateur/Profi', (await p.locator('.kopf .schalter').count()) === 0);
  const mitte = await p.evaluate(() => { const k = document.querySelector('.kopf-beenden').getBoundingClientRect(), s = document.querySelector('.kopf-beenden svg').getBoundingClientRect();
    return [Math.abs((k.left + k.width / 2) - (s.left + s.width / 2)), Math.abs((k.top + k.height / 2) - (s.top + s.height / 2))]; });
  ok('⏻ mittig im Kreis', mitte[0] < 1 && mitte[1] < 1, mitte.map(x => x.toFixed(2)).join(' / '));

  // 2. Kompetenzrahmen: Bereich + Kompetenz nach dem automatischen Speichern
  await p.goto(B + '/_kompetenzen/beispiel-kompetenzrahmen.html'); await p.waitForSelector('.kr-baum');
  ok('Rahmenseite ohne Amateur/Profi', (await p.locator('.kopf .schalter').count()) === 0);
  const vorher = await p.locator('.kr-bereich').count();
  await p.click('button:has-text("+ Bereich hinzufügen")');
  await p.locator('.kr-bereich').nth(vorher).locator('input.kr-knoten-titel').first().fill('Kommunizieren');
  await p.waitForTimeout(2600);   // Autosave ist gelaufen
  await p.locator('.kr-bereich').nth(vorher).locator('button:has-text("+ Kompetenz")').click();
  await p.locator('.kr-bereich').nth(vorher).locator('.kr-kompetenz input.kr-knoten-titel').first().fill('Präsentieren');
  await p.waitForTimeout(2600);
  const kr = await (await p.request.get(B + '/api/kompetenzrahmen/beispiel-kompetenzrahmen')).json();
  const br = kr.rahmen.bereiche[kr.rahmen.bereiche.length - 1];
  ok('Neuer Bereich mit Kompetenz gespeichert', br.titel === 'Kommunizieren' && (br.kompetenzen || []).map(k => k.titel).join() === 'Präsentieren', br.titel + ' / ' + (br.kompetenzen || []).map(k => k.titel));

  // 3. Abbildung: «noch nicht bearbeitet» und «offen» getrennt
  await p.goto(B + '/_kompetenzen/beispiel-kompetenzrahmen-abbildung.html');
  const bewertet = await p.locator('.ka-stufe:has-text("bewertet")').getAttribute('class');
  const weiter = await p.locator('.ka-stufe:has-text("entwickelt weiter")').getAttribute('class');
  ok('Stufe mit Seite «noch nicht bearbeitet»', /st-weiss/.test(bewertet), bewertet);
  ok('Stufe ohne Seite «offen»', /st-offen/.test(weiter), weiter);
  const kopf = (await p.textContent('.ka-tabelle thead')).replace(/\s+/g, ' ');
  ok('Zahlen pro Ebene mit vier Spalten', /erarbeitet.*in Bearbeitung.*noch nicht bearbeitet.*offen.*gesamt/.test(kopf), kopf.trim());
  ok('Gesamtzeile nennt offen', /offen/.test(await p.textContent('.ka-gesamt')));
  ok('Abbildung ohne Amateur/Profi', (await p.locator('.kopf .schalter').count()) === 0);

  // 4. Seite: Schalter da, Profi, «Verlinkt von» aus
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html');
  ok('Seite mit Amateur/Profi', (await p.locator('.kopf .schalter').count()) === 1);
  ok('«Verlinkt von» sichtbar', (await p.locator('.rueckverweise').count()) === 1);
  await p.click('.kopf .schalter button:has-text("Profi")'); await p.waitForLoadState('load'); await p.waitForTimeout(300);
  await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('#editor-verweise');
  await p.uncheck('#editor-verweise');

  // 5. PDF-Block mit Startseite
  await p.click('.block-hinzufuegen >> nth=-1 >> button:has-text("PDF")');
  await p.setInputFiles('.editor-block[data-typ=pdf] input[type=file]', S + '/buch.pdf');
  await p.waitForSelector('.editor-block[data-typ=pdf] label:has-text("Öffnen auf Seite") input', { timeout: 20000 });
  await p.fill('.editor-block[data-typ=pdf] label:has-text("Öffnen auf Seite") input', '250');
  await p.waitForTimeout(800);
  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForTimeout(1500);
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html');
  ok('«Verlinkt von» ausgeblendet', (await p.locator('.rueckverweise').count()) === 0);
  const src = await p.getAttribute('.block-pdf iframe', 'src');
  ok('PDF öffnet auf Seite 250', /#page=250$/.test(src || ''), src);

  // Suche findet Text von Seite 250 des PDFs
  await p.goto(B + '/'); await p.fill('#suchfeld', 'Zebrafink250'); await p.waitForTimeout(600);
  const treffer = await p.textContent('#treffer');
  ok('Suche findet Text tief im PDF', /Lernjournal/.test(treffer || ''), (treffer || '').replace(/\s+/g, ' ').slice(0, 80));

  // 6. Export-Dialog: Hinweis bei Passwortschutz
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html'); await p.click('#seiten-werkzeuge button:has-text("Exportieren")'); await p.waitForSelector('dialog .export-warnung');
  ok('Passwort-Hinweis zuerst verborgen', !(await p.isVisible('dialog .export-hinweis-pw')));
  await p.click('dialog label:has-text("Passwortschutz")');
  ok('Passwort-Hinweis sichtbar', await p.isVisible('dialog .export-hinweis-pw'), (await p.textContent('dialog .export-hinweis-pw')).slice(0, 40));
  await p.click('dialog button:has-text("Abbrechen")');

  // 7. Blockkopf in Spalten ragt nicht über den Rand
  await p.goto(B + '/beispiel-portfolio/semester-1/projekte/projekt-a.html'); await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")'); await p.waitForSelector('.spalten-raster');
  const spalten = p.locator('.spalten-kopf select').first();
  await spalten.selectOption('4'); await p.waitForTimeout(300);
  const ueber = await p.evaluate(() => [...document.querySelectorAll('.spalte .editor-block')].filter(e => { const r = e.getBoundingClientRect();
    return [...e.querySelectorAll('.block-kopf *')].some(k => { const q = k.getBoundingClientRect(); return q.width && q.right > r.right + 1; }); }).length);
  ok('Kein Blockkopf ragt über den Rand (4 Spalten)', ueber === 0, ueber);
  await p.locator('.spalte .editor-block .block-kopf .mehr').first().click();
  ok('«⋯» zeigt die Aktionen', await p.locator('.spalte .editor-block .block-aktionen').first().isVisible());
  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForTimeout(800);

  // 8. Abbildung sofort aktuell: Stand im Editor ändern, dann direkt auf der Seite umschalten
  const stufe = async () => (await p.locator('.ka-stufe:has-text("bewertet")').getAttribute('class')).match(/st-\w+/)[0];
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html'); await p.click('#seiten-werkzeuge button:has-text("Bearbeiten")');
  await p.waitForSelector('.kr-wahl-zeile:has-text("bewertet") select');
  await p.selectOption('.kr-wahl-zeile:has-text("bewertet") select', 'orange'); await p.waitForTimeout(600);
  await p.click('.editor-leiste button:has-text("Fertig")'); await p.waitForTimeout(1200);
  await p.goto(B + '/_kompetenzen/beispiel-kompetenzrahmen-abbildung.html');
  ok('Abbildung nach Speichern im Editor aktuell', (await stufe()) === 'st-orange', await stufe());
  await p.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html');
  await p.click('.kr-zeile[data-knoten="s1b2c3"] button.kr-status[data-status="gruen"]'); await p.waitForTimeout(800);
  await p.goto(B + '/_kompetenzen/beispiel-kompetenzrahmen-abbildung.html');
  ok('Abbildung nach Umschalten auf der Seite aktuell', (await stufe()) === 'st-gruen', await stufe());

  ok('Keine Skriptfehler', fehler.length === 0, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})().catch(e => { console.log('TESTFEHLER', e.message); process.exit(1); });
