// Rundreise wie bei Windows-Nutzern: Export mit allen Optionen (inkl. Passwort) -> lokal per Doppelklick öffnen
// (file://) -> Kommentar + Beurteilung -> «Herunterladen» -> neue ZIP entpacken und in frischem Browser öffnen.
// Aufruf: node tests/browser/rundreise.e2e.js [http://127.0.0.1:8787] [mitPasswort=1]
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path'); const { execSync } = require('child_process');
const S = fs.mkdtempSync(path.join(require('os').tmpdir(), 'liloport-rr-')), B = process.argv[2] || 'http://127.0.0.1:8787';
const PW = (process.argv[3] || '1') === '1';
function entpacken(zip, ziel) { fs.rmSync(ziel, { recursive: true, force: true }); fs.mkdirSync(ziel); execSync(`cd ${ziel} && unzip -q ${zip}`); return ziel + '/' + fs.readdirSync(ziel)[0]; }
(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ acceptDownloads: true, locale: 'de-CH' }); const page = await ctx.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('dialog', d => d.accept());
  await page.goto(B + '/'); const bsp = await page.$('#beispiel-karte button:has-text("Beispiel anlegen")'); if (bsp) { await bsp.click(); await page.waitForURL(/willkommen/); }
  await page.goto(B + '/beispiel-portfolio/semester-1/lernjournal.html'); await page.click('#seiten-werkzeuge button:has-text("Exportieren")'); await page.waitForSelector('dialog .export-warnung');
  for (const t of ['Datum der Seite', 'Als Abgabe']) await page.click(`dialog label:has-text("${t}")`);
  if (PW) { await page.click('dialog label:has-text("Passwortschutz")'); await page.fill('dialog input[type=password] >> nth=0', 'geheim123'); const p2 = await page.$$('dialog input[type=password]'); if (p2[1]) await p2[1].fill('geheim123'); }
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('dialog button[type=submit]')]); await dl.saveAs(S + '/r1.zip');
  const o1 = entpacken(S + '/r1.zip', S + '/r1');
  // Runde 1 lokal (file://), wie Doppelklick auf «Seite öffnen.html»
  const p1 = await ctx.newPage(); p1.on('pageerror', e => errors.push('r1: ' + e.message)); p1.on('dialog', d => d.accept());
  await p1.goto('file://' + o1 + '/Seite öffnen.html'); await p1.waitForLoadState('load'); await p1.waitForTimeout(800);
  if (PW) { await p1.fill('#passwort-form input[type=password]', 'geheim123'); await p1.click('#passwort-form button'); await p1.waitForTimeout(800); }
  await p1.waitForSelector('#kommentar-form');
  await p1.fill('#kommentar-form input[name=name]', 'Lea'); await p1.click('#kommentar-form .kommentar-editor'); await p1.keyboard.type('Normaler Kommentar in der Box'); await p1.click('#kommentar-form button[type=submit]'); await p1.waitForTimeout(400);
  await p1.click('.kr-b-zeile >> nth=0 >> .kr-b-neu'); await p1.fill('.kr-b-zeile >> nth=0 >> input[name=name]', 'Dr. Meier');
  await p1.click('.kr-b-zeile >> nth=0 >> button.kr-b-stufe:has-text("3")'); await p1.fill('.kr-b-zeile >> nth=0 >> textarea', 'Beurteilungstext'); await p1.click('.kr-b-zeile >> nth=0 >> button:has-text("Beurteilung speichern")'); await p1.waitForTimeout(400);
  console.log('Runde 1: Box-Kommentare', await p1.locator('#kommentar-liste .kommentar').count(), '| Beurteilungen', await p1.locator('.kr-b-eintrag').count());
  const [dl2] = await Promise.all([p1.waitForEvent('download'), p1.click('.export-leiste button:has-text("Herunterladen")')]); await dl2.saveAs(S + '/r2.zip');
  console.log('ZIP-Test:', execSync(`unzip -tq ${S}/r2.zip 2>&1 || true`).toString().trim());
  console.log('Python zipfile:', execSync(`python3 -c "import zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);print(z.testzip(), len(z.namelist()), [i.filename for i in z.infolist() if i.filename.endswith(('.js','.css'))])" ${S}/r2.zip`).toString().trim());
  const o2 = entpacken(S + '/r2.zip', S + '/r2');
  console.log('JS-Dateien in Runde-2-ZIP:', execSync(`unzip -Z1 ${S}/r2.zip`).toString().split('\n').filter(n => /\.js$/i.test(n)));
  for (const f of ['style.css']) {
    const a = fs.readFileSync(o1 + '/inhalt/' + f), b = fs.existsSync(o2 + '/inhalt/' + f) ? fs.readFileSync(o2 + '/inhalt/' + f) : null;
    console.log(f, b ? (a.equals(b) ? 'identisch' : 'VERÄNDERT ' + a.length + '→' + b.length) : 'FEHLT');
  }
  // Runde 2 in neuem Browserprofil (kein localStorage aus Runde 1)
  const ctx2 = await browser.newContext({ locale: 'de-CH' }); const p2 = await ctx2.newPage(); p2.on('pageerror', e => errors.push('r2: ' + e.message)); p2.on('dialog', d => d.accept());
  await p2.goto('file://' + o2 + '/Seite öffnen.html'); await p2.waitForLoadState('load'); await p2.waitForTimeout(800);
  if (await p2.$('#passwort-form')) { console.log('Runde 2 verlangt Passwort'); await p2.fill('#passwort-form input[type=password]', 'geheim123'); await p2.click('#passwort-form button'); await p2.waitForTimeout(800); }
  const css = await p2.evaluate(() => [...document.styleSheets].map(s => { try { return s.href + ':' + s.cssRules.length; } catch (e) { return s.href + ':?'; } }));
  console.log('Runde 2: Stylesheets', css, '| URL', p2.url().replace(S, ''));
  console.log('Runde 2: Box-Kommentare', await p2.locator('#kommentar-liste .kommentar').count(), '| Beurteilungen', await p2.locator('.kr-b-eintrag').count());
  // Runde 2 «direkt aus der ZIP»: nur die HTML-Datei, ohne style.css und ohne Skripte
  const einzeln = S + '/einzeln'; fs.mkdirSync(einzeln); const datei = p2.url().split('/').pop(); fs.copyFileSync(o2 + '/inhalt/' + decodeURIComponent(datei), einzeln + '/seite.html');
  const ctx3 = await browser.newContext({ javaScriptEnabled: false }); const p3 = await ctx3.newPage(); await p3.goto('file://' + einzeln + '/seite.html');
  console.log('Ohne Gestaltung: Hinweis sichtbar', await p3.isVisible('.ohne-gestaltung'), '| Kommentartext lesbar', (await p3.textContent('body')).includes(PW ? 'Normaler Kommentar' : 'Normaler Kommentar'));
  console.log('Fehler', errors); await browser.close();
  console.log('Ordner', S);
})().catch(e => { console.log('TESTFEHLER', e.message); process.exit(1); });
