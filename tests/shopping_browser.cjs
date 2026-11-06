// Run with Playwright on NODE_PATH and the isolated shopping_test_server.py.
// ASSET_ORIGIN optionally tests deployed assets; EVERY /api request is routed
// to the local fixture, so this suite never writes production data.
const {chromium, webkit} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8765';
const origin = process.env.ASSET_ORIGIN || base;
const checks = [], errors = [];
const check = (label, actual, expected = true) => { assert.deepEqual(actual, expected, label); checks.push(label); };
const remote = data => fetch(base + '/__test__/remote', {method: 'POST', body: JSON.stringify(data)});
const stored = async () => (await fetch(base + '/__test__/state')).json();
const sync = page => page.evaluate(async () => {syncLastAttemptV55=0;lastLocalSaveAt=0;await syncFromServer();});
const saved = page => page.waitForFunction(() => saveRevisionV25 === savedRevisionV25 && !saveWorkerV25);
const row = (page, id) => page.locator(`[data-shopping-id="${id}"]`);

(async () => {
  const engine = process.env.BROWSER === 'webkit' ? webkit : chromium;
  const browser = await engine.launch(process.env.CHROME_PATH && engine === chromium
    ? {executablePath: process.env.CHROME_PATH, headless: true} : {headless: true});
  try {
    for (const width of [390, 1440]) {
      const label = name => `${process.env.BROWSER || 'chromium'} ${width}: ${name}`;
      await fetch(base + '/__test__/reset', {method: 'POST'});
      const context = await browser.newContext({viewport: {width, height: 900}, isMobile: width < 500, hasTouch: width < 500});
      let failWrites = false, malformed = false, delayWrite = false;
      let releaseWrite, writeStarted;
      const intercept = async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.pathname.startsWith('/api/')) {
          if (url.pathname === '/api/plan' && request.method() === 'POST') {
            if (failWrites) return route.fulfill({status: 503, json: {ok: false, error: 'test outage'}});
            if (malformed) return route.fulfill({status: 200, contentType: 'text/html', body: '<html>Not a save confirmation</html>'});
            if (delayWrite) { delayWrite = false; writeStarted?.(); await new Promise(resolve => releaseWrite = resolve); }
          }
          const response = await route.fetch({url: base + url.pathname + url.search});
          return route.fulfill({response});
        }
        if (url.origin !== new URL(origin).origin) return route.abort();
        if (!['GET', 'HEAD'].includes(request.method())) throw new Error('Unexpected write: ' + request.url());
        return route.continue();
      };
      await context.route('**/*', intercept);
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(label(error.message)));
      await page.goto(origin, {waitUntil: 'domcontentloaded'});
      await page.locator('.nav-btn[data-view="viewShopping"]').click();
      await page.waitForTimeout(80); // let the desktop navigation focus settle
      const category = page.locator('[data-inline-category="Meieri"]');
      await category.locator('button').click();
      let input = category.locator('input');
      await input.fill('Yoghurt naturell');
      await input.evaluate(el => {window.draftNode=el;el.setSelectionRange(4,9);});
      const stamp = new Date().toISOString();
      await remote({updatedAt: stamp, shoppingItems: [{id: 'bread', text: 'Brød', category: 'Bakevarer', updatedAt: stamp}]});
      await sync(page);
      check(label('draft survives remote sync'), await input.inputValue(), 'Yoghurt naturell');
      check(label('same focused DOM node and selection'), await input.evaluate(el =>
        el === window.draftNode && document.activeElement === el && el.selectionStart === 4 && el.selectionEnd === 9));
      check(label('other phone addition becomes visible while typing'), await row(page, 'bread').count(), 1);
      await input.press('Enter');
      await saved(page);
      check(label('Enter saves category and text'), (await stored()).shoppingItems.some(x => x.text === 'Yoghurt naturell' && x.category === 'Meieri' && x.manualCategory));
      check(label('composer stays focused after submit'), await input.evaluate(el => document.activeElement === el));
      check(label('submitted draft clears'), await input.inputValue(), '');
      await input.fill('Kefir');
      await category.getByRole('button', {name: 'Legg til', exact: true}).click();
      await saved(page);
      check(label('button saves exactly once'), (await stored()).shoppingItems.filter(x => x.text === 'Kefir').length, 1);

      await row(page, 'milk').locator('.shopping-check').check();
      await input.fill('Fløte til helgen');
      await page.waitForTimeout(1950);
      check(label('completion timer preserves draft and keyboard focus'), await input.evaluate(el => el.value === 'Fløte til helgen' && document.activeElement === el));
      await page.locator('.completed-toggle').click();
      await row(page, 'milk').locator('.shopping-check').uncheck();
      await saved(page);
      check(label('undo returns item to active list'), await row(page, 'milk').locator('.shopping-check').isChecked(), false);

      // Open row edit, then trigger a merge that replaces item objects.
      await row(page, 'milk').locator('.shopping-item-text').click();
      let edit = row(page, 'milk').locator('.shopping-edit-input');
      await edit.fill('2 liter lettmelk');
      await remote({updatedAt: new Date().toISOString(), shoppingItems: [{id: 'eggs', text: 'Egg', category: 'Meieri', updatedAt: new Date().toISOString()}]});
      await sync(page);
      check(label('row editor survives remote merge'), await edit.inputValue(), '2 liter lettmelk');
      await edit.press('Enter');
      await saved(page);
      check(label('edit writes current item, not stale object'), (await stored()).shoppingItems.find(x => x.id === 'milk').text, '2 l lettmelk');

      // Save acknowledgement may arrive while a different row is being edited.
      delayWrite = true;
      const began = new Promise(resolve => writeStarted = resolve);
      await input.fill('Smør'); await input.press('Enter'); await began;
      await row(page, 'milk').locator('.shopping-item-text').click();
      edit = row(page, 'milk').locator('.shopping-edit-input');
      await edit.fill('3 liter lettmelk');
      releaseWrite(); await saved(page);
      check(label('save acknowledgement preserves open editor'), await edit.inputValue(), '3 liter lettmelk');
      await edit.press('Enter'); await saved(page);
      check(label('edit after delayed acknowledgement persists'), (await stored()).shoppingItems.find(x => x.id === 'milk').text, '3 l lettmelk');

      // Cancelling cannot fall through to the blur-save handler.
      await row(page, 'milk').locator('.shopping-item-text').click();
      edit = row(page, 'milk').locator('.shopping-edit-input');
      await edit.fill('Should be cancelled'); await edit.press('Escape');
      check(label('Escape cancels without blur-save'), (await stored()).shoppingItems.find(x => x.id === 'milk').text, '3 l lettmelk');

      // A locally edited row deleted elsewhere becomes a new item on commit.
      await row(page, 'milk').locator('.shopping-item-text').click();
      edit = row(page, 'milk').locator('.shopping-edit-input'); await edit.fill('4 liter lettmelk');
      await remote({updatedAt: new Date().toISOString(), shoppingItems: [{id: 'milk', deleted: true, updatedAt: new Date().toISOString()}]});
      await sync(page); await edit.press('Enter'); await saved(page);
      check(label('remote deletion keeps tombstone and explicit new edit'), (await stored()).shoppingItems.some(x => x.id !== 'milk' && x.text === '4 l lettmelk' && !x.deleted));
      check(label('deleted original remains deleted'), (await stored()).shoppingItems.find(x => x.id === 'milk').deleted);

      await input.fill('Uferdig kategoriutkast');
      await page.locator('#shoppingQuickInput').fill('Uferdig hurtigutkast');
      await page.reload({waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelector('#shoppingQuickAdd')?.dataset.bound === 'true');
      input = category.locator('input');
      check(label('category draft survives reload'), await input.inputValue(), 'Uferdig kategoriutkast');
      check(label('quick draft survives reload'), await page.locator('#shoppingQuickInput').inputValue(), 'Uferdig hurtigutkast');
      await input.press('Escape');
      await page.reload({waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelector('#shoppingQuickAdd')?.dataset.bound === 'true');
      check(label('cancelled category draft stays cancelled'), await category.locator('input').count(), 0);

      // Failed save -> reload -> automatic retry, with concurrent meal-plan edit.
      failWrites = true;
      await page.locator('#shoppingQuickInput').fill('Havregryn offline');
      await page.locator('#shoppingQuickInput').press('Enter');
      await page.waitForFunction(() => !saveWorkerV25 && saveRevisionV25 > savedRevisionV25);
      check(label('failed save remains durably pending'), await page.evaluate(() => JSON.parse(localStorage.getItem('middag_state_v25'))._pendingSave));
      check(label('failed save is never labelled saved'), (await page.locator('#shoppingSaveStatus').innerText()).includes('Alle endringer'), false);
      await remote({updatedAt: new Date().toISOString(), items: {'2026-11-08': [{type: 'text', text: 'Partnerens middag'}]}, meta: {favorites: ['partner'], pantryItems: [{id: 'pantry', name: 'Ris'}]}});
      await page.reload({waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => !saveWorkerV25 && saveRevisionV25 > savedRevisionV25);
      failWrites = false;
      await page.evaluate(() => window.dispatchEvent(new Event('online')));
      await saved(page);
      const afterRetry = await stored();
      check(label('reload automatically resumes offline save'), afterRetry.shoppingItems.filter(x => x.text === 'Havregryn offline').length, 1);
      check(label('shopping retry preserves partner meal plan'), afterRetry.items['2026-11-08'][0].text, 'Partnerens middag');
      check(label('shopping retry preserves partner pantry'), afterRetry.meta.pantryItems[0].name, 'Ris');
      check(label('acknowledged save clears durable pending flag'), await page.evaluate(() => JSON.parse(localStorage.getItem('middag_state_v25'))._pendingSave), false);

      malformed = true;
      await page.locator('#shoppingQuickInput').fill('Brunost'); await page.locator('#shoppingQuickInput').press('Enter');
      await page.waitForFunction(() => !saveWorkerV25 && saveRevisionV25 > savedRevisionV25);
      check(label('HTTP 200 without valid acknowledgement remains pending'), await page.evaluate(() => JSON.parse(localStorage.getItem('middag_state_v25'))._pendingSave));
      malformed = false; await page.evaluate(() => retryShoppingSaveV25()); await saved(page);

      // Simultaneous clients write through the real API and CAS merge.
      const partnerContext = await browser.newContext({viewport: {width, height: 900}, isMobile: width < 500, hasTouch: width < 500});
      await partnerContext.route('**/*', intercept);
      const partner = await partnerContext.newPage();
      partner.on('pageerror', error => errors.push(label(error.message)));
      await partner.goto(origin, {waitUntil: 'domcontentloaded'});
      await partner.waitForFunction(() => document.querySelector('#shoppingQuickAdd')?.dataset.bound === 'true');
      await partner.evaluate(() => showView('viewShopping'));
      await Promise.all([
        page.evaluate(() => addShoppingItemV25('Samtidig eple', 'Frukt og grønt')),
        partner.evaluate(() => addShoppingItemV25('Samtidig pære', 'Frukt og grønt'))
      ]);
      await Promise.all([saved(page), saved(partner)]);
      check(label('both concurrent additions persist'), (await stored()).shoppingItems.filter(x => /^Samtidig /.test(x.text)).length, 2);
      await sync(page); await sync(partner);
      check(label('both clients converge'), await page.evaluate(() => shoppingItems.filter(x => /^Samtidig /.test(x.text)).length), 2);

      // A database revision is authoritative even if a client timestamp repeats.
      const sameTime = (await stored()).updatedAt;
      await remote({updatedAt: sameTime, shoppingItems: [{id: 'same-time', text: 'Samme klokkeslett', category: 'Annet', updatedAt: new Date().toISOString()}]});
      await sync(page);
      check(label('new database revision with same timestamp is shown'), await row(page, 'same-time').count(), 1);

      // Every category has the same reliable composer, including empty ones.
      const categories = await page.evaluate(() => [...CATEGORIES]);
      for (const [index, name] of categories.entries()) {
        const host = page.locator(`[data-inline-category="${name}"]`);
        if (!await host.locator('input').count()) await host.locator('button').click();
        await host.locator('input').fill(`Testvare ${index}`);
        await host.locator('input').press('Enter');
      }
      await saved(page);
      const categoryItems = (await stored()).shoppingItems;
      check(label('all 12 category composers save in their selected category'), categories.every((name, index) =>
        categoryItems.some(item => item.text === `Testvare ${index}` && item.category === name && item.manualCategory)));

      await row(page, 'bread').locator('.shopping-check').check(); await saved(page);
      await page.evaluate(() => addShoppingItemV25('Brød', 'Bakevarer')); await saved(page);
      check(label('adding a completed duplicate restores the actual stored item'), (await stored()).shoppingItems.find(x => x.id === 'bread').done, false);

      await row(page, 'bread').locator('.shopping-item-text').click();
      await row(page, 'bread').locator('.shopping-edit-input').fill('Grovbrød');
      // One click must both finish editing and check the other row.
      const targetId = categoryItems.find(x => x.text === `Testvare ${categories.indexOf('Bakevarer')}`).id;
      const target = row(page, targetId).locator('.shopping-check');
      await target.scrollIntoViewIfNeeded();
      const targetBox = await target.boundingBox();
      if (width < 500) await page.touchscreen.tap(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2);
      else await page.mouse.click(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2);
      await saved(page);
      check(label('clicking another checkbox commits row edit'), (await stored()).shoppingItems.find(x => x.id === 'bread').text, 'grovbrød');
      check(label('the same click also checks the target item'), (await stored()).shoppingItems.find(x => x.id === targetId).done);

      await row(page, 'bread').locator('.shopping-item-text').click();
      await row(page, 'bread').locator('.shopping-edit-input').fill('Ferdig etter omstart');
      await page.reload({waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelector('#shoppingQuickAdd')?.dataset.bound === 'true');
      check(label('unfinished row edit survives reload'), await row(page, 'bread').locator('.shopping-edit-input').inputValue(), 'Ferdig etter omstart');
      await row(page, 'bread').locator('.shopping-edit-input').press('Enter'); await saved(page);
      check(label('restored row edit saves'), (await stored()).shoppingItems.find(x => x.id === 'bread').text, 'ferdig etter omstart');

      delayWrite = true;
      const stalled = new Promise(resolve => writeStarted = resolve);
      await page.evaluate(() => {window.realAbortTimeout=AbortSignal.timeout;AbortSignal.timeout=()=>window.realAbortTimeout(150);});
      await page.locator('#shoppingQuickInput').fill('Etter tidsavbrudd');
      await page.locator('#shoppingQuickInput').press('Enter'); await stalled;
      await page.waitForFunction(() => !saveWorkerV25 && saveRevisionV25 > savedRevisionV25);
      check(label('stalled request times out without losing pending data'), await page.evaluate(() => JSON.parse(localStorage.getItem('middag_state_v25'))._pendingSave));
      await page.evaluate(() => {AbortSignal.timeout=window.realAbortTimeout;});
      releaseWrite();
      await page.evaluate(() => retryShoppingSaveV25()); await saved(page);
      check(label('timed-out request retries without duplicates'), (await stored()).shoppingItems.filter(x => x.text === 'Etter tidsavbrudd').length, 1);

      check(label('no horizontal overflow'), await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (process.env.SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.SCREENSHOT_DIR, {recursive: true});
        await page.screenshot({path: path.join(process.env.SCREENSHOT_DIR, `shopping-${width}.png`), fullPage: true});
      }
      await partnerContext.close();
      await context.close();
    }
    check('no uncaught browser errors', errors, []);
    console.log(JSON.stringify({origin, checks: checks.length, passed: checks}, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); console.error('Passed before failure:', checks); process.exitCode=1; });
