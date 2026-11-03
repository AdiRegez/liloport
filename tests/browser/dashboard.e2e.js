// Regressionstest: jede Aktion im Dashboard muss einen Dialog öffnen bzw. etwas bewirken
const { chromium } = require('playwright');
const B = process.argv[2] || 'http://127.0.0.1:8782';
(async () => {
  const browser = await chromium.launch(); const page = await browser.newPage({viewport:{width:1280,height:900}, locale:'de-CH'});
  const errors=[]; page.on('pageerror', e=>errors.push(e.message)); page.on('dialog', d=>d.accept());
  const da = (sel) => page.waitForSelector(sel, {timeout: 4000}).then(()=>1).catch(()=>0);
  const ok = (name, bed) => console.log((bed ? 'OK   ' : 'FEHLT') + ' ' + name);
  const zeile = async (text) => { const z = page.locator('.verz-zeile, .seite-zeile').filter({hasText: text}).first(); await z.hover(); return z; };
  await page.goto(B+'/'); await page.waitForTimeout(500);
  if (await page.locator('#beispiel-karte').count()) await page.click('#beispiel-karte button:has-text("Nein danke")');
  await page.waitForTimeout(300);
  // Neu → Verzeichnis (ohne Verzeichnisse öffnet «Neu» direkt den Verzeichnis-Dialog)
  await page.click('#plus-button'); await page.waitForTimeout(200);
  if (await page.locator('dialog button:has-text("Neues Verzeichnis")').count()) await page.click('dialog button:has-text("Neues Verzeichnis")');
  ok('Neu → Neues Verzeichnis', await page.locator('dialog h2:has-text("Neues Verzeichnis")').count());
  await page.fill('dialog input[type=text]', 'Semester 1'); await page.click('dialog button[type=submit]'); await page.waitForTimeout(500);
  ok('Verzeichnis angelegt', await page.locator('.verz-zeile:has-text("Semester 1")').count());
  // Neu → Seite
  await page.click('#plus-button'); await page.click('dialog button:has-text("Neue Seite")');
  ok('Neu → Neue Seite', await page.locator('dialog h2:has-text("Neue Seite")').count());
  await page.fill('dialog input[type=text]', 'Erste Seite'); await page.click('dialog button[type=submit]'); await page.waitForURL(/erste-seite/);
  ok('Seite angelegt, Editor offen', await page.waitForSelector('.editor-leiste').then(()=>true).catch(()=>false));
  await page.click('.editor-leiste button:has-text("Fertig")'); await page.waitForFunction(()=>!document.body.classList.contains('bearbeiten')); await page.waitForTimeout(800);
  await page.goto(B+'/'); await page.waitForSelector('.verz-zeile');
  // Verzeichnis-Aktionen
  let z = await zeile('Semester 1'); await z.locator('button:has-text("Seite")').click();
  ok('Verzeichnis → Seite', await page.locator('dialog h2:has-text("Neue Seite")').count()); await page.click('dialog button:has-text("Abbrechen")');
  z = await zeile('Semester 1'); await z.locator('button:has-text("Unterverzeichnis")').click();
  ok('Verzeichnis → Unterverzeichnis', await page.locator('dialog h2:has-text("Neues Verzeichnis")').count());
  await page.fill('dialog input[type=text]', 'Archiv'); await page.click('dialog button[type=submit]'); await page.waitForTimeout(500);
  z = await zeile('Archiv'); await z.locator('button:has-text("Bearbeiten")').click();
  ok('Verzeichnis → Bearbeiten', await page.locator('dialog h2:has-text("Verzeichnis bearbeiten")').count());
  await page.fill('dialog input[type=text]', 'Altes'); await page.click('dialog button[type=submit]'); await page.waitForTimeout(500);
  ok('Verzeichnis umbenannt', await page.locator('.verz-zeile:has-text("Altes")').count());
  z = await zeile('Semester 1'); await z.locator('button:has-text("Exportieren")').click();
  ok('Verzeichnis → Exportieren', await da('dialog h2:has-text("exportieren")')); await page.click('dialog button:has-text("Abbrechen")');
  // Seiten-Aktionen
  z = await zeile('Erste Seite'); await z.locator('button:has-text("Verschieben")').click();
  ok('Seite → Verschieben', await page.locator('dialog h2:has-text("verschieben")').count());
  await page.selectOption('dialog select', {label: '  Altes'}).catch(async ()=>{ const v = await page.evaluate(()=>[...document.querySelectorAll('dialog select option')].find(o=>o.textContent.includes('Altes')).value); await page.selectOption('dialog select', v); });
  await page.click('dialog button[type=submit]'); await page.waitForTimeout(500);
  ok('Seite verschoben', await page.locator('.verz-zeile:has-text("Altes") + ul .seite-zeile:has-text("Erste Seite")').count());
  await page.click('#reiter-kompetenzen'); await page.click('button:has-text("Kompetenzrahmen erstellen")');
  ok('Kompetenzrahmen erstellen', await da('dialog h2:has-text("Kompetenzrahmen erstellen")')); await page.click('dialog button:has-text("Abbrechen")');
  await page.click('button:has-text("Kompetenzrahmen importieren")'); ok('Kompetenzrahmen importieren', await da('dialog h2:has-text("importieren")')); await page.click('dialog button:has-text("Abbrechen")');
  await page.click('#reiter-verwaltung'); await page.click('summary:has-text("Profil")'); await page.fill('.profil-zeile input >> nth=0', 'Anna Muster'); await page.fill('.profil-zeile input >> nth=1', '12-345-678'); await page.click('.profil-zeile button:has-text("Speichern")'); await page.waitForTimeout(400);
  const prof = await page.evaluate(()=>fetch('/api/export-einstellungen').then(r=>r.json())); ok('Profil gespeichert', prof.autor==='Anna Muster' && prof.id==='12-345-678');
  await page.click('#reiter-portfolio');
  z = await zeile('Erste Seite'); await z.locator('button:has-text("Exportieren")').click();
  ok('Seite → Exportieren', await da('dialog h2:has-text("exportieren")')); await page.click('dialog button:has-text("Abbrechen")');
  z = await zeile('Erste Seite'); await z.locator('button:has-text("Exportieren")').click(); await da('dialog h2:has-text("exportieren")');
  ok('Export vorbelegt mit Profil', (await page.inputValue('dialog input[placeholder^="Name"]'))==='Anna Muster' && (await page.inputValue('dialog input[placeholder^="ID-Nummer"]'))==='12-345-678'); await page.click('dialog button:has-text("Abbrechen")');
  z = await zeile('Erste Seite'); await z.locator('button:has-text("Löschen")').click();
  ok('Seite → Löschen', await da('dialog h2:has-text("löschen")')); await page.click('dialog button[type=submit]'); await page.waitForTimeout(500);
  ok('Seite gelöscht', !(await page.locator('.seite-zeile:has-text("Erste Seite")').count()));
  z = await zeile('Altes'); await z.locator('button:has-text("Löschen")').click(); await page.waitForTimeout(500);
  ok('Verzeichnis gelöscht', !(await page.locator('.verz-zeile:has-text("Altes")').count()));
  // «Ganzes Portfolio exportieren» steht neu im Reiter «Verwaltung»
  await page.click('#reiter-verwaltung');
  const pexp = page.locator('#tab-verwaltung details', {hasText:'Ganzes Portfolio exportieren'});
  ok('Portfolio-Export unter Verwaltung', await pexp.count() === 1);
  await pexp.locator('summary').click();
  await pexp.locator('button:has-text("Ganzes Portfolio exportieren")').click();
  ok('Portfolio-Export → Dialog', await da('dialog .zweck-wahl')); await page.click('dialog button:has-text("Abbrechen")');
  console.log('Fehler:', errors); await browser.close();
})().catch(e=>{console.log('TESTFEHLER', e.message); process.exit(1);});
