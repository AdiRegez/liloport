const { chromium } = require('playwright'); const fs = require('fs'); const { execSync, spawn } = require('child_process');
const S=require('fs').mkdtempSync(require('path').join(require('os').tmpdir(),'liloport-')), B=process.argv[2]||'http://127.0.0.1:8787';
(async () => {
  const browser = await chromium.launch(); const ctx = await browser.newContext({acceptDownloads:true, locale:'de-CH', viewport:{width:1200,height:900}}); const page = await ctx.newPage();
  const errors=[]; page.on('pageerror', e=>errors.push(e.message)); page.on('dialog', d=>d.accept());
  await page.goto(B+'/'); await page.waitForSelector('#beispiel-karte'); await page.click('#beispiel-karte button:has-text("Beispiel anlegen")'); await page.waitForURL(/willkommen/);
  await page.goto(B+'/beispiel-portfolio/semester-1/lernjournal.html'); await page.click('#seiten-werkzeuge button:has-text("Exportieren")'); await page.waitForSelector('dialog .export-warnung');
  await page.check('dialog .zweck-karte input[value="webserver"]');   // Moderations-Link gibt es nur beim Zweck Webserver
  await page.click('dialog label:has-text("Als Abgabe")');
  console.log('Dialog: Moderation bei Abgabe gesperrt', await page.isDisabled('dialog label:has-text("Moderations-Link") input'), '| angehakt', await page.isChecked('dialog label:has-text("Moderations-Link") input'));
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('dialog button[type=submit]')]); await dl.saveAs(S+'/b1.zip');
  fs.rmSync(S+'/b1',{recursive:true,force:true}); fs.mkdirSync(S+'/b1'); execSync(`cd ${S}/b1 && unzip -qo ${S}/b1.zip`); const o=S+'/b1/'+fs.readdirSync(S+'/b1')[0];
  fs.rmSync(S+'/srvB',{recursive:true,force:true}); fs.mkdirSync(S+'/srvB'); execSync(`cp -r ${o}/inhalt ${S}/srvB/abgabe`);
  const php = spawn('php', ['-S','127.0.0.1:8797','-t',S+'/srvB']); await new Promise(r=>setTimeout(r,800));
  const start = JSON.parse(fs.readFileSync(o+'/inhalt/manifest.json')).start;
  await page.goto('http://127.0.0.1:8797/abgabe/'+start); await page.waitForSelector('.kr-b-neu'); await page.waitForTimeout(300);
  console.log('Beurteilungszeilen:', await page.locator('.kr-b-zeile').count(), '| KR-Zeilen (Stand):', await page.locator('.kr-zeile').count());
  await page.click('.kr-b-zeile >> nth=0 >> .kr-b-neu'); await page.fill('.kr-b-zeile >> nth=0 >> input[name=name]', 'Dr. Meier');
  await page.selectOption('.kr-b-zeile >> nth=0 >> select', '6'); await page.click('.kr-b-zeile >> nth=0 >> button.kr-b-stufe:has-text("5")');
  await page.fill('.kr-b-zeile >> nth=0 >> textarea', 'Gut dokumentiert, Begründung fehlt.'); await page.click('.kr-b-zeile >> nth=0 >> button:has-text("Beurteilung speichern")');
  await page.waitForSelector('.kr-b-eintrag'); await page.evaluate(()=>document.querySelector('.kr-beurteilung').scrollIntoView()); await page.screenshot({path:S+'/beurteilung.png'});
  console.log('Eintrag:', await page.textContent('.kr-b-eintrag .kr-b-ergebnis strong'), '| comments.json:', JSON.parse(fs.readFileSync(S+'/srvB/abgabe/comments.json','utf8')).map(k=>k.art+':'+k.wert+'/'+k.skala));
  await page.click('.kr-b-eintrag .kommentar-aktionen button:has-text("Bearbeiten")'); await page.click('.kr-b-eintrag form button.kr-b-stufe:has-text("6")'); await page.click('.kr-b-eintrag form button:has-text("Speichern")'); await page.waitForTimeout(400);
  console.log('Nach Bearbeiten:', await page.textContent('.kr-b-eintrag .kr-b-ergebnis strong'), '| normale Kommentare sichtbar:', await page.locator('#kommentar-liste .kommentar').count());
  // Abgebende Person mit erfundenem Moderations-Link in einem anderen Browser: keine Knöpfe, kein Band
  const ctxS = await browser.newContext(); const ps = await ctxS.newPage();
  await ps.goto('http://127.0.0.1:8797/abgabe/' + start + '#moderation=abcdefghijklmnopqrstuvwx'); await ps.waitForSelector('.kr-b-eintrag'); await ps.waitForTimeout(300);
  console.log('Stempel:', (await ps.textContent('.abgabe-moderation')).trim().slice(0, 40), '| Knöpfe für fremde Beurteilung:', await ps.locator('.kr-b-eintrag .kommentar-aktionen').count(), '| Moderationsband:', await ps.locator('#moderation-band').count());
  const pr = await ps.evaluate(() => { const f = new FormData(); f.append('aktion', 'pruefen'); f.append('schluessel', 'abcdefghijklmnopqrstuvwx'); return fetch('comments.php', { method: 'POST', body: f }).then(r => r.json()); });
  console.log('Server prüft erfundenen Schlüssel:', JSON.stringify(pr)); await ctxS.close();
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.click('.export-leiste button:has-text("Herunterladen")')]); await dl2.saveAs(S+'/b2.zip'); php.kill();
  await page.goto(B+'/'); await page.click('#plus-button'); await page.click('dialog button:has-text("importieren")'); await page.setInputFiles('dialog input[type=file]', S+'/b2.zip'); await page.waitForSelector('dialog .import-info strong');
  console.log('Import:', (await page.textContent('dialog .import-info')).replace(/\s+/g,' ').slice(0,120));
  const vid = await page.evaluate(()=>[...document.querySelectorAll('dialog select option')].find(o=>o.textContent.includes('Private')).value); await page.selectOption('dialog select', vid); await page.click('dialog button[type=submit]'); await page.waitForTimeout(800);
  console.log('Lokal:', await page.locator('.kommentar.beurteilung').count(), 'Beurteilung(en) –', (await page.textContent('.kommentar.beurteilung .kr-b-ergebnis')).trim());
  await page.evaluate(()=>document.querySelector('#kommentare').scrollIntoView()); await page.screenshot({path:S+'/beurteilung-lokal.png'});
  console.log('Fehler', errors); await browser.close();
})().catch(e=>{console.log('TESTFEHLER', e.message); process.exit(1);});
