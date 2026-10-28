// Dashboard-Übersicht und Speichern: A–Z-Sortierung, einklappbare Verzeichnisse, Reiter, kein falscher
// Konflikt, wenn «Fertig» während eines langsamen automatischen Speicherns geklickt wird.
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/uebersicht.e2e.js http://127.0.0.1:8787
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://127.0.0.1:8787';
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }
(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage(); const fehler = []; p.on('pageerror', e => fehler.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Nein danke")'); await p.waitForTimeout(400);
  const api = (m, u, d) => p.evaluate(([m, u, d]) => fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: d ? JSON.stringify(d) : undefined }).then(r => r.json()), [m, u, d]);
  // In absichtlich «falscher» Reihenfolge anlegen, dazu Unterverzeichnisse: insgesamt 16 Verzeichnisse
  const namen = ['Zoologie', 'Mathematik', 'Biologie', 'Ästhetik', 'Chemie', 'Kunst', 'Sport', 'Deutsch', 'Englisch', 'Geschichte', 'Physik', 'Musik'];
  const ids = {};
  for (const n of namen) ids[n] = (await api('POST', '/api/verzeichnisse', { name: n, eltern: null, inMenue: true })).verzeichnis.id;
  for (const n of ['Woche 10', 'Woche 2', 'Woche 1']) await api('POST', '/api/verzeichnisse', { name: n, eltern: ids['Mathematik'], inMenue: true });
  await api('POST', '/api/verzeichnisse', { name: 'Projekte', eltern: ids['Biologie'], inMenue: true });
  await p.evaluate(() => localStorage.clear());
  await p.goto(B + '/'); await p.waitForSelector('.baum .verz');

  const oben = await p.$$eval('.baum > ul > li.verz > .verz-zeile .name', e => e.map(x => x.textContent));
  ok('A–Z ist Standard (mit Umlauten)', oben.join(',') === 'Ästhetik,Biologie,Chemie,Deutsch,Englisch,Geschichte,Kunst,Mathematik,Musik,Physik,Sport,Zoologie', oben.join(','));
  ok('Viele Verzeichnisse: zu Beginn eingeklappt', (await p.locator('.baum li.verz.zu').count()) === 16);
  ok('Eingeklappt zeigt den Inhalt als Zahl', /3 Verzeichnisse/.test(await p.textContent('.verz-zeile:has-text("Mathematik") .verz-anzahl')));
  await p.click('.verz-zeile:has-text("Mathematik") .verz-klapp');
  const wochen = await p.$$eval('.verz-zeile:has-text("Mathematik") + ul > li.verz > .verz-zeile .name', e => e.map(x => x.textContent));
  ok('Aufklappen; Zahlen natürlich sortiert', wochen.join(',') === 'Woche 1,Woche 2,Woche 10', wochen.join(','));
  await p.reload(); await p.waitForSelector('.baum .verz');
  ok('Auf-/Zugeklappt wird gemerkt', !(await p.locator('.verz-zeile:has-text("Mathematik")').evaluate(e => e.parentElement.classList.contains('zu'))));
  await p.click('.baum-werkzeuge button:has-text("Erstellt")');
  const erstellt = await p.$$eval('.baum > ul > li.verz > .verz-zeile .name', e => e.map(x => x.textContent));
  ok('Sortierung «Erstellt»', erstellt[0] === 'Zoologie' && erstellt[1] === 'Mathematik', erstellt.slice(0, 3).join(','));
  await p.click('.baum-werkzeuge button:has-text("A–Z")');
  await p.click('.baum-werkzeuge button:has-text("Alle aufklappen")');
  ok('Alle aufklappen', (await p.locator('.baum li.verz.zu').count()) === 0);
  await p.click('.baum-werkzeuge button:has-text("Alle zuklappen")');
  ok('Alle zuklappen', (await p.locator('.baum li.verz.zu').count()) === 16);

  // Reiter
  ok('Reiter sichtbar', await p.isVisible('#dash-reiter'));
  await p.click('#reiter-verwaltung');
  ok('Verwaltung: Backup, Papierkorb, Dateien, Profil', (await p.locator('#tab-verwaltung summary').allTextContents()).join('|').match(/Backup.*Papierkorb.*Dateien.*Profil/) !== null);
  ok('Portfolio-Baum ausgeblendet', !(await p.isVisible('#baum')));
  await p.reload(); await p.waitForTimeout(500);
  ok('Reiter wird gemerkt', await p.isVisible('#tab-verwaltung') && !(await p.isVisible('#baum')));
  await p.click('#reiter-kompetenzen');
  ok('Kompetenzen-Reiter', await p.isVisible('#tab-kompetenzen button:has-text("Kompetenzrahmen erstellen")'));
  await p.fill('#suchfeld', 'Mathe').catch(() => {});   // Suchfeld liegt im Portfolio-Reiter
  await p.click('#reiter-portfolio');
  if (process.env.SCREENSHOT) await p.screenshot({ path: process.env.SCREENSHOT });

  // Kein falscher Konflikt: Speichern dauert lange (künstlich verzögert), «Fertig» kommt dazwischen
  const neu = await api('POST', '/api/seiten', { titel: 'Konflikttest', verzeichnis: ids['Kunst'], menue: 'voll', bloecke: [] });
  await p.route('**/api/seiten/**', async route => { if (route.request().method() === 'PUT') await new Promise(r => setTimeout(r, 1500)); await route.continue(); });
  await p.goto(B + '/' + neu.pfad + '.html#bearbeiten'); await p.waitForSelector('#editor-titel');
  await p.fill('#editor-titel', 'Konflikttest neu'); await p.waitForTimeout(3100);   // Autosave (0,6 s + 2 s) ist unterwegs
  await p.click('.editor-leiste button:has-text("Fertig")');
  await p.waitForTimeout(4500);
  ok('Kein Konfliktdialog', (await p.locator('dialog h2:has-text("anderswo geändert")').count()) === 0);
  const seite = await api('GET', '/api/seiten/' + neu.pfad);
  ok('Gespeichert', seite.seite.titel === 'Konflikttest neu', seite.seite.titel);

  ok('Keine Skriptfehler', fehler.length === 0, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})().catch(e => { console.log('TESTFEHLER', e.message); process.exit(1); });
