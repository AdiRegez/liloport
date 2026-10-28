const { chromium } = require('playwright'); const fs = require('fs'); const { execSync, spawn } = require('child_process');
const S=require('fs').mkdtempSync(require('path').join(require('os').tmpdir(),'liloport-')), B=process.argv[2]||'http://127.0.0.1:8783';
function entpacken(zip, ziel) { fs.rmSync(ziel,{recursive:true,force:true}); fs.mkdirSync(ziel); execSync(`cd ${ziel} && unzip -qo ${zip}`); const o = ziel+'/'+fs.readdirSync(ziel)[0]; return o; }
(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({acceptDownloads:true, locale:'de-CH'}); const page = await ctx.newPage();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message)); page.on('dialog', d=>{ console.log('DIALOG', d.message().slice(0,90)); d.accept(); });
  await page.goto(B+'/'); await page.waitForSelector('#beispiel-karte'); await page.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await page.waitForURL(/willkommen/);
  console.log('Schrift Titel:', await page.evaluate(()=>getComputedStyle(document.querySelector('.seitentitel')).fontFamily.slice(0,40)), '| geladen:', await page.evaluate(async()=>{await document.fonts.ready; return document.fonts.check('800 20px "Bricolage Grotesque"') && document.fonts.check('16px "Atkinson Hyperlegible"');}));
  await page.goto(B+'/'); await page.waitForSelector('.verz-zeile'); const z = page.locator('.verz-zeile').filter({hasText:'Semester 1'}).first(); await z.hover(); await z.locator('button:has-text("Exportieren")').click();
  await page.waitForSelector('dialog .export-warnung');
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('dialog button[type=submit]')]); await dl.saveAs(S+'/x1.zip');
  const o1 = entpacken(S+'/x1.zip', S+'/x1'); console.log('Oben:', fs.readdirSync(o1));
  // Person A: Doppelklick auf «Seite öffnen.html»
  await page.goto('file://'+o1+'/Seite öffnen.html'); await page.waitForURL(/inhalt\//); await page.waitForSelector('.portfolio-inhalt');
  console.log('Startseite file://, Schrift ok:', await page.evaluate(async()=>{await document.fonts.ready; return document.fonts.check('800 20px "Bricolage Grotesque"');}));
  await page.click('.portfolio-inhalt a:has-text("Lernjournal")'); await page.waitForSelector('.kommentar-editor');
  console.log('Hinweis:', (await page.textContent('.kommentar-hinweis')).slice(0,60));
  await page.fill('#kommentar-form input[name=name]','Lea'); await page.click('.kommentar-editor'); await page.keyboard.type('Erster Kommentar'); await page.click('#kommentar-form button[type=submit]'); await page.waitForSelector('.kommentar');
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.click('.export-leiste button:has-text("Herunterladen")')]); await dl2.saveAs(S+'/x2.zip');
  const o2 = entpacken(S+'/x2.zip', S+'/x2'); console.log('Download 1 oben:', fs.readdirSync(o2), '| inhalt:', fs.readdirSync(o2+'/inhalt').length, 'Dateien, assets', fs.readdirSync(o2+'/inhalt/assets').length);
  console.log('comments.json:', JSON.parse(fs.readFileSync(o2+'/inhalt/comments.json','utf8')).map(k=>k.text));
  // Person B (anderer Browser-Speicher)
  const ctx2 = await browser.newContext({acceptDownloads:true}); const p2 = await ctx2.newPage(); p2.on('pageerror', e=>errors.push('B: '+e.message));
  await p2.goto('file://'+o2+'/Seite öffnen.html'); await p2.waitForURL(/inhalt\//); await p2.click('.portfolio-inhalt a:has-text("Lernjournal")'); await p2.waitForSelector('.kommentar');
  console.log('B sieht Kommentare:', await p2.locator('.kommentar').count(), '| Bild geladen:', await p2.evaluate(()=>{const i=document.querySelector('.block-bild img');return i&&i.complete&&i.naturalWidth>0;}));
  await p2.click('.kommentar-editor'); await p2.keyboard.type('Zweiter von B'); await p2.click('#kommentar-form button[type=submit]'); await p2.waitForFunction(()=>document.querySelectorAll('.kommentar').length===2);
  const [dl3] = await Promise.all([p2.waitForEvent('download'), p2.click('.export-leiste button:has-text("Herunterladen")')]); await dl3.saveAs(S+'/x3.zip');
  const o3 = entpacken(S+'/x3.zip', S+'/x3'); console.log('Download 2 Ordnername:', o3.split('/').pop(), '| oben:', fs.readdirSync(o3), '| comments:', JSON.parse(fs.readFileSync(o3+'/inhalt/comments.json','utf8')).map(k=>k.text));
  // Webserver (PHP) mit dem Ordner «inhalt»
  fs.rmSync(S+'/srvroot',{recursive:true,force:true}); fs.mkdirSync(S+'/srvroot'); execSync(`cp -r ${o3}/inhalt ${S}/srvroot/abgabe`);
  const php = spawn('php', ['-S','127.0.0.1:8793','-t',S+'/srvroot']); await new Promise(r=>setTimeout(r,800));
  const start = JSON.parse(fs.readFileSync(o3+'/inhalt/manifest.json')).start;
  await p2.goto('http://127.0.0.1:8793/abgabe/'+start); await p2.click('.portfolio-inhalt a:has-text("Lernjournal")'); await p2.waitForSelector('.kommentar'); await p2.waitForTimeout(400);
  console.log('Server: Kommentare', await p2.locator('.kommentar').count());
  await p2.click('.kommentar-editor'); await p2.keyboard.type('Dritter auf dem Server'); await p2.click('#kommentar-form button[type=submit]'); await p2.waitForFunction(()=>document.querySelectorAll('.kommentar').length===3);
  const [dl4] = await Promise.all([p2.waitForEvent('download'), p2.click('.export-leiste button:has-text("Herunterladen")')]); await dl4.saveAs(S+'/x4.zip'); php.kill();
  const o4 = entpacken(S+'/x4.zip', S+'/x4'); console.log('Server-Download Ordner:', o4.split('/').pop(), '| oben:', fs.readdirSync(o4), '| comments:', JSON.parse(fs.readFileSync(o4+'/inhalt/comments.json','utf8')).length, '| php-Quelltext dabei:', fs.existsSync(o4+'/inhalt/comments.php'));
  // Import in Liloport
  await page.goto(B+'/'); await page.click('#plus-button'); await page.click('dialog button:has-text("importieren")'); await page.waitForSelector('dialog input[type=file]');
  await page.setInputFiles('dialog input[type=file]', S+'/x4.zip'); await page.waitForSelector('dialog .import-info strong'); console.log('Import:', (await page.textContent('dialog .import-info')).replace(/\s+/g,' ').slice(0,90));
  await page.click('dialog button[type=submit]'); await page.waitForTimeout(800);
  console.log('Importiert nach', page.url().replace(B,''), '| Kommentare auf Lernjournal-Kopie:', await (async()=>{ const s = await page.evaluate(()=>fetch('/api/site').then(r=>r.json())); const lj = s.verzeichnisse.flatMap(v=>v.seiten).filter(x=>x.titel==='Lernjournal' && !x.redirect).map(x=>x.pfad); const r=[]; for (const p of lj) { const k = await page.evaluate(p=>fetch('/api/kommentare/'+p).then(r=>r.json()), p); r.push(p+':'+k.kommentare.length);} return r.join(', '); })());
  console.log('Fehler:', errors); await browser.close();
})().catch(e=>{console.log('TESTFEHLER', e.message); process.exit(1);});
