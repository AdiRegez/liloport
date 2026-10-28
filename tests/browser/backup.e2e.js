// Backup im Dashboard: läuft im Hintergrund mit Fortschritt, eigener Backup-Ordner, Wiederherstellen in einen
// leeren Ordner (grosse Dateien kommen aus dem gemeinsamen Dateispeicher zurück).
// Aufruf mit leerem Inhalte-Ordner: node tests/browser/backup.e2e.js http://127.0.0.1:8787
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path'); const os = require('os');
const B = process.argv[2] || 'http://127.0.0.1:8787';
const T = fs.mkdtempSync(path.join(os.tmpdir(), 'liloport-backup-'));
let fehlerZahl = 0;
function ok(name, wahr, info) { console.log((wahr ? 'OK    ' : 'FEHLER') + ' ' + name + (info !== undefined ? ' – ' + info : '')); if (!wahr) fehlerZahl++; }
(async () => {
  const browser = await chromium.launch(); const p = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  const fehler = []; p.on('pageerror', e => fehler.push(e.message));
  const meldungen = []; p.on('dialog', d => { meldungen.push(d.message()); d.accept(); });
  await p.goto(B + '/'); await p.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await p.waitForURL(/willkommen/);
  // Ein grosses Video, damit der gemeinsame Dateispeicher zum Zug kommt
  const film = path.join(T, 'film.mp4'); const kopf = Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 109, 112, 52, 50, 0, 0, 0, 0, 109, 112, 52, 50, 105, 115, 111, 109]);
  fs.writeFileSync(film, Buffer.concat([kopf, Buffer.alloc(3 * 1024 * 1024, 7)]));
  const site = await (await p.request.get(B + '/api/site')).json();
  const seite = site.verzeichnisse.find(v => v.seiten.length).seiten[0].pfad;
  const up = await p.request.post(B + '/api/upload/' + seite, { headers: { 'X-Dateiname': 'film.mp4', 'Content-Type': 'application/octet-stream', Origin: B }, data: fs.readFileSync(film) });
  ok('Video hochgeladen', up.ok(), up.status());

  await p.goto(B + '/'); await p.click('#reiter-verwaltung'); await p.waitForTimeout(1200);
  await p.locator('#tab-verwaltung details:has(.backup-bereich)').evaluate(d => { d.open = true; });
  ok('Hinweis auf externe Festplatte', /externen Festplatte/.test(await p.textContent('#tab-verwaltung .backup-bereich')));

  // Eigener Backup-Ordner
  const extern = path.join(T, 'Festplatte', 'Liloport-Backups');
  await p.click('#tab-verwaltung .backup-ort button');
  await p.fill('dialog input[type=text]', 'relativ/ordner'); await p.click('dialog button:has-text("Übernehmen")'); await p.waitForTimeout(400);
  ok('Relativer Pfad abgelehnt', /vollständigen Pfad/.test(await p.textContent('dialog .fehlermeldung')));
  await p.fill('dialog input[type=text]', extern); await p.click('dialog button:has-text("Übernehmen")'); await p.waitForTimeout(500);
  ok('Ordner übernommen', (await p.textContent('#tab-verwaltung .backup-ort')).includes('Liloport-Backups'));

  // Backup jetzt: läuft im Hintergrund, Knopf gesperrt, danach fertig
  await p.click('#tab-verwaltung .backup-bereich button:has-text("Backup jetzt")');
  await p.waitForFunction(() => /Zuletzt/.test(document.querySelector('#tab-verwaltung .backup-bereich').textContent) && !document.querySelector('#tab-verwaltung progress'), null, { timeout: 60000 });
  const ordnerEcht = (await (await p.request.get(B + '/api/backup')).json()).ordner;
  ok('Eigener Unterordner pro Portfolio', ordnerEcht.startsWith(extern) && ordnerEcht !== extern, ordnerEcht);
  const zips = fs.readdirSync(ordnerEcht).filter(n => n.endsWith('.zip'));
  ok('Backup im eigenen Ordner', zips.length === 1, zips.join());
  ok('Video im Dateispeicher', fs.existsSync(path.join(ordnerEcht, 'dateien')) && fs.readdirSync(path.join(ordnerEcht, 'dateien')).length >= 1);
  ok('Keine Fehlermeldung', meldungen.length === 0, meldungen.join(' | '));

  // Wiederherstellen
  const ziel = path.join(T, 'zurueck');
  await p.click('#tab-verwaltung .backup-bereich button:has-text("Wiederherstellen")');
  await p.fill('dialog input[type=text]', ziel); await p.click('dialog button:has-text("Entpacken")');
  await p.waitForFunction(() => !document.querySelector('dialog') && !document.querySelector('#tab-verwaltung progress'), null, { timeout: 60000 });
  await p.waitForTimeout(2500);
  ok('Meldung «Wiederhergestellt»', meldungen.some(m => /Wiederhergestellt nach/.test(m)), meldungen.join(' | '));
  const filme = fs.readdirSync(ziel, { recursive: true }).filter(n => String(n).endsWith('.mp4'));
  ok('Video wiederhergestellt', filme.length === 1 && fs.statSync(path.join(ziel, filme[0])).size === fs.statSync(film).size, filme.join());
  ok('Seiten wiederhergestellt', fs.existsSync(path.join(ziel, 'site.json')));

  // Zurück zum Standard
  await p.click('#tab-verwaltung .backup-ort button');
  await p.fill('dialog input[type=text]', ''); await p.click('dialog button:has-text("Übernehmen")'); await p.waitForTimeout(500);
  ok('Wieder im Inhalte-Ordner', /im Inhalte-Ordner/.test(await p.textContent('#tab-verwaltung .backup-ort')));

  ok('Keine Skriptfehler', fehler.length === 0, fehler.join(' | '));
  await browser.close();
  console.log(fehlerZahl ? fehlerZahl + ' Fehler' : 'Alles OK');
  process.exit(fehlerZahl ? 1 : 0);
})().catch(e => { console.log('TESTFEHLER', e.message); process.exit(1); });
