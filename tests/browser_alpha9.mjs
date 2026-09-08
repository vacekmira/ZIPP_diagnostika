import { chromium } from "file:///C:/Users/vac0172/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";
import fs from "node:fs/promises";
import path from "node:path";

const base = process.env.ZIPP_E2E_URL || "http://127.0.0.1:8765";
const password = process.env.ZIPP_E2E_PASSWORD || "Alpha9-test!";
const output = path.resolve("tmp/browser-alpha9");
await fs.mkdir(output, { recursive: true });

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function login(page) {
  await page.goto(`${base}/`);
  if (page.url().includes("/login")) {
    await page.locator('input[name="password"]').fill(password);
    await Promise.all([
      page.waitForURL(`${base}/`),
      page.locator('button[type="submit"]').click(),
    ]);
  }
  await page.waitForSelector('body[data-app-version="Alpha 9"][data-js-version="Alpha 9"]');
}

async function createProject(page, name, bays, trusses) {
  await page.goto(`${base}/`);
  await page.locator("[data-open-project]").click();
  const form = page.locator("[data-project-form]");
  await form.locator('[name="name"]').fill(name);
  await form.locator('[name="bay_count"]').fill(String(bays));
  await form.locator('[name="default_truss_count"]').fill(String(trusses));
  await form.locator('[name="note"]').fill("Příliš žluťoučký kůň a slovenský kôň – Alpha 9 E2E.");
  await Promise.all([
    page.waitForURL(/\/projects\/\d+$/),
    form.locator('button[type="submit"]').click(),
  ]);
  return Number(page.url().match(/\/projects\/(\d+)$/)[1]);
}

async function savePdfDownload(page, clickTarget, filename) {
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    clickTarget.click(),
  ]);
  const destination = path.join(output, filename);
  await download.saveAs(destination);
  const data = await fs.readFile(destination);
  check(data.subarray(0, 4).toString("ascii") === "%PDF", `${filename} is not a PDF`);
  check(data.length > 5_000, `${filename} is unexpectedly small`);
  return { filename: download.suggestedFilename(), path: destination, bytes: data.length };
}

async function mode(page, value) {
  await page.locator(`[data-work-mode-link="${value}"]`).click();
  await page.waitForSelector(`body[data-work-mode="${value}"]`);
  await page.waitForSelector('[data-connection][data-state="online"]');
  const box = await page.locator(`[data-work-mode-link="${value}"]`).boundingBox();
  check(box.width >= 110 && box.height >= 48, 'Mode tabs are too small');
}

async function geometry(page) {
  return page.locator('article[data-truss-id]').evaluateAll(nodes => nodes.map(node => ({
    id: node.dataset.trussId, position: node.dataset.position, type: node.dataset.trussType,
    pair: node.dataset.pairId, label: node.querySelector('[data-label]').textContent,
  })));
}

const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: true,
});
const contextA = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
const contextB = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
for (const context of [contextA, contextB]) {
  await context.addInitScript(() => {
    localStorage.setItem("zipp.technician", "Alpha 9 browser tester");
    localStorage.setItem("zipp.language", "cs");
  });
}
const pageA = await contextA.newPage();
const pageB = await contextB.newPage();
const consoleErrors = [];
for (const page of [pageA, pageB]) {
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
}

const downloads = [];
try {
  await login(pageA);
  await login(pageB);

  const projectId = await createProject(pageA, "Hala Alpha 9 E2E", 3, 24);
  await pageB.goto(`${base}/projects/${projectId}`);
  await pageA.waitForSelector('[data-connection][data-state="online"]');
  await pageB.waitForSelector('[data-connection][data-state="online"]');

  await pageA.locator("[data-open-project-rename]").click();
  const renameForm = pageA.locator("[data-project-name-form]");
  await renameForm.locator('[name="name"]').fill("Hala Žďár – zkouška");
  await renameForm.locator('button[type="submit"]').click();
  await pageA.locator("h1[data-project-name]").waitFor({ state: "visible" });
  await pageA.waitForFunction(() => document.querySelector("h1[data-project-name]")?.textContent === "Hala Žďár – zkouška");
  await pageB.waitForFunction(() => document.querySelector("[data-project-name]")?.textContent === "Hala Žďár – zkouška");
  check(pageA.url().endsWith(`/projects/${projectId}`), "Rename changed the project id or URL");
  await pageA.reload();
  check((await pageA.locator("h1[data-project-name]").textContent()) === "Hala Žďár – zkouška", "Rename did not persist after reload");

  check(await pageA.locator('[data-height-form]').count() === 0, 'Height editor leaked into diagnostics');
  const diagnosticBayIds = await pageA.locator('[data-bay-card-id]').evaluateAll(nodes => nodes.map(node => node.dataset.bayCardId));
  await mode(pageA, 'survey');
  check(JSON.stringify(await pageA.locator('[data-bay-card-id]').evaluateAll(nodes => nodes.map(node => node.dataset.bayCardId))) === JSON.stringify(diagnosticBayIds), 'Modes use different bays');
  check(await pageA.locator('.summary-card').count() === 0, 'Diagnostic summary leaked into survey');
  await pageA.locator('[data-height-form] input').fill('8,5');
  const [projectHeight] = await Promise.all([
    pageA.waitForResponse(response => response.url().endsWith(`/api/projects/${projectId}/height`) && response.request().method() === 'PUT'),
    pageA.locator('[data-height-form] button').click(),
  ]);
  check(projectHeight.ok(), 'Project height was not saved');

  const firstBayHref = await pageA.locator(".bay-card").first().getAttribute("href");
  const bayUrl = `${base}${firstBayHref}`;
  await pageA.goto(bayUrl);
  await pageB.goto(bayUrl);
  await pageB.waitForSelector('[data-connection][data-state="online"]');
  await pageA.setViewportSize({width:390,height:844});
  await pageA.locator('[data-height-form] input').fill('12,25');
  const [bayHeight] = await Promise.all([
    pageA.waitForResponse(response => /\/api\/bays\/\d+\/height$/.test(response.url()) && response.request().method() === 'PUT'),
    pageA.locator('[data-height-form] button').click(),
  ]);
  check(bayHeight.ok(), 'Bay height was not saved');
  const rows = pageA.locator('.truss-row');
  const firstRow = rows.nth(0);
  for (const [side, method] of [['left','Ž'],['right','K']]) {
    const [saved] = await Promise.all([
      pageA.waitForResponse(response => response.url().endsWith(`/access/${side}`) && response.request().method() === 'PUT'),
      firstRow.locator(`[data-access-method="${method}"][data-access-side="${side}"]`).click(),
    ]);
    check(saved.ok(), `Access ${side} was not saved`);
  }
  await firstRow.locator('[data-edit-access-note]').click();
  await pageA.locator('[data-access-note-form] textarea').fill('Přístup přes žeriavovou dráhu – kôň, ľalia.');
  await pageA.locator('[data-access-note-form] button.primary').click();
  await pageA.locator('[data-access-note-dialog]').waitFor({state:'hidden'});
  check((await firstRow.locator('[data-access-note]').textContent()).includes('žeriavovou'), 'Note was not saved');
  await pageB.waitForFunction(() => document.querySelector('.truss-row [data-access-method="Ž"][data-access-side="left"]')?.getAttribute('aria-pressed') === 'true');
  await pageB.waitForFunction(() => document.querySelector('.truss-row [data-access-note]')?.textContent.includes('žeriavovou'));
  check((await pageB.locator('[data-height-bay]').textContent()).includes('12,25'), 'Height did not update in second browser');
  await pageA.locator('[data-select-mode]').click();
  await rows.nth(1).locator('[data-select-truss]').click();
  await rows.nth(2).locator('[data-select-truss]').click();
  await pageA.locator('[data-open-bulk]').click();
  await pageA.locator('[data-bulk-method="N"][data-access-side="left"]').click();
  await pageA.locator('[data-bulk-method="J"][data-access-side="right"]').click();
  await pageA.screenshot({path:path.join(output,'alpha9-mobile-bulk.png')});
  await pageA.locator('[data-bulk-submit]').click();
  await pageA.locator('[data-bulk-dialog]').waitFor({state:'hidden'});
  check(await rows.nth(1).locator('[data-access-method="N"][data-access-side="left"]').getAttribute('aria-pressed') === 'true', 'Bulk left not applied');
  check(await rows.nth(2).locator('[data-access-method="J"][data-access-side="right"]').getAttribute('aria-pressed') === 'true', 'Bulk right not applied');
  await mode(pageB, 'diagnostics');
  check(JSON.stringify(await geometry(pageA)) === JSON.stringify(await geometry(pageB)), 'Modes use different trusses');
  check(await pageA.locator('[data-side], .excluded-state').count() === 0, 'Diagnostic fields leaked into survey');
  check(await pageB.locator('[data-access-method], [data-height-form], [data-edit-access-note]').count() === 0, 'Survey editors leaked into diagnostics');
  const diagnosticFirst = pageB.locator('.truss-row').first();
  const [diagnosticSaved] = await Promise.all([
    pageB.waitForResponse(r => r.url().endsWith('/diagnostics/left') && r.request().method() === 'PUT'),
    diagnosticFirst.locator('[data-side="left"]').click(),
  ]);
  check(diagnosticSaved.ok(), 'Diagnostic change failed');
  await pageA.waitForFunction(version => Number(document.querySelector('.truss-row').dataset.version) >= version, (await diagnosticSaved.json()).version);
  check(await firstRow.locator('[data-access-method="Ž"][data-access-side="left"]').getAttribute('aria-pressed') === 'true', 'Diagnostics changed survey left');
  check((await firstRow.locator('[data-access-note]').textContent()).includes('žeriavovou'), 'Diagnostics changed survey note');
  for (const method of ['N', 'K']) {
    const [saved] = await Promise.all([
      pageA.waitForResponse(r => r.url().endsWith('/access/right') && r.request().method() === 'PUT'),
      firstRow.locator(`[data-access-method="${method}"][data-access-side="right"]`).click(),
    ]);
    check(saved.ok(), 'Survey change failed');
    await pageB.waitForFunction(version => Number(document.querySelector('.truss-row').dataset.version) >= version, (await saved.json()).version);
    check(await diagnosticFirst.locator('[data-side="left"]').getAttribute('aria-pressed') === 'true', 'Survey changed diagnostic L');
    check(await diagnosticFirst.locator('[data-side="right"]').getAttribute('aria-pressed') === 'false', 'Survey changed diagnostic P');
  }
  const touchSizes = await firstRow.locator('[data-access-method]').evaluateAll(nodes => nodes.map(node => ({w:node.getBoundingClientRect().width,h:node.getBoundingClientRect().height})));
  check(touchSizes.every(size => size.w >= 44 && size.h >= 48), 'Access chips are too small');
  check(await pageA.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page overflows horizontally');
  await firstRow.scrollIntoViewIfNeeded();
  await pageA.screenshot({path:path.join(output,'alpha9-mobile-access.png')});
  await mode(pageA, 'diagnostics');
  await pageA.locator('.truss-row').first().scrollIntoViewIfNeeded();
  await pageA.screenshot({path:path.join(output,'alpha9-mobile-diagnostics.png')});
  check(await pageA.locator('[data-access-method]').count() === 0, 'Mobile switch did not separate fields');
  await mode(pageA, 'survey');
  await pageA.reload();
  check(await firstRow.locator('[data-access-method="Ž"][data-access-side="left"]').getAttribute('aria-pressed') === 'true', 'Left access did not persist');
  check(await firstRow.locator('[data-access-method="K"][data-access-side="right"]').getAttribute('aria-pressed') === 'true', 'Right access did not persist');
  await pageA.setViewportSize({width:820,height:1180});
  await firstRow.scrollIntoViewIfNeeded();
  await pageA.screenshot({path:path.join(output,'alpha9-tablet-access.png')});
  check(await pageA.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Tablet page overflows horizontally');
  await mode(pageA, 'diagnostics');
  await pageA.locator('.truss-row').first().scrollIntoViewIfNeeded();
  await pageA.screenshot({path:path.join(output,'alpha9-tablet-diagnostics.png')});
  await mode(pageA, 'survey');

  // Geometry edits are shared immediately between the two working modes.
  const originalIds = (await geometry(pageA)).map(row => row.id);
  await pageA.locator('.bay-actions a').click();
  check(pageA.url().includes('mode=survey'), 'Settings lost the working mode');
  check(await pageA.locator('[data-shared-geometry]').isVisible(), 'Settings are not marked as shared');
  await pageA.locator('.admin-row').nth(1).locator('[name="label"]').fill('HIST-02');
  await Promise.all([pageA.waitForEvent('load'), pageA.locator('[form="labels-form"]').click()]);
  await pageB.waitForFunction(() => document.querySelectorAll('.truss-row [data-label]')[1]?.textContent === 'HIST-02');
  await pageA.locator('[data-resize-form] input').fill('25');
  await Promise.all([pageA.waitForEvent('load'), pageA.locator('[data-resize-form] button').click()]);
  await pageB.waitForFunction(() => document.querySelectorAll('article[data-truss-id]').length === 25);
  await pageA.locator('.breadcrumbs a').last().click();
  await pageA.waitForSelector('body[data-work-mode="survey"]');
  check(JSON.stringify(await geometry(pageA)) === JSON.stringify(await geometry(pageB)), 'Geometry diverged after label/size edits');
  check(JSON.stringify((await geometry(pageA)).slice(0,24).map(row => row.id)) === JSON.stringify(originalIds), 'Resize changed historical IDs');
  check((await geometry(pageA))[1].label === 'HIST-02', 'Label edit is not shared');
  await firstRow.locator('.truss-identity').click();
  check(await pageA.locator('[data-access-method]').count() === 10 && await pageA.locator('[data-exclude-form], .status-pair').count() === 0, 'Survey detail mixes diagnostics');
  check(pageA.url().includes('mode=survey'), 'Truss detail lost the mode');
  await pageA.locator('.hero a').click();
  await pageA.waitForSelector('body[data-work-mode="survey"]');
  await pageA.locator('[data-open-export="bay-export-dialog"]').click();
  const bayDialog = pageA.locator("#bay-export-dialog");
  check(await bayDialog.isVisible(), "Bay export dialog is not visible");
  const bayOptionSignature = await bayDialog.locator("option").evaluateAll((options) => options.map((option) => option.value));
  check(JSON.stringify(bayOptionSignature) === JSON.stringify([
    "A4", "A3", "A2", "A1", "A0", "landscape", "portrait", "auto", "7", "9", "10", "12", "14",
  ]), "Bay dialog does not offer the complete shared options");
  await pageA.screenshot({ path: path.join(output, "alpha9-bay-export-dialog.png"), fullPage: true });
  await bayDialog.locator("[data-close-dialog]").click();
  const bayCases = [
    ["A4", "landscape", "7", "alpha9-browser-bay-clean.pdf", 'false'],
    ["A3", "landscape", "10", "alpha9-browser-bay-access.pdf", 'true'],
    ["A2", "portrait", "14", "alpha9-browser-bay-A2-access.pdf", 'true'],
  ];
  for (const [paper, orientation, font, filename, access] of bayCases) {
    await mode(pageA, access === 'true' ? 'survey' : 'diagnostics');
    await pageA.locator('[data-open-export="bay-export-dialog"]').click();
    const form = bayDialog.locator("[data-export-form]");
    await form.locator('[name="page_size"]').selectOption(paper);
    await form.locator('[name="orientation"]').selectOption(orientation);
    await form.locator('[name="font_size"]').selectOption(font);
    await form.locator(`[name="show_access"][value="${access}"]`).check();
    downloads.push(await savePdfDownload(pageA, form.locator("[data-export-submit]"), filename));
  }

  await pageA.goto(`${base}/projects/${projectId}/plan?mode=survey`);
  for (const access of ['true','false']) {
    const [loaded] = await Promise.all([
      pageA.waitForResponse(response => response.url().includes('/plan.svg?') && response.url().includes(`show_access=${access}`)),
      pageA.locator(`[data-plan-layer-form] [name="show_access"][value="${access}"]`).check(),
    ]);
    const svg = await loaded.text();
    check(svg.includes('data-access-legend') === (access === 'true'), 'Plan access layer mismatch');
    check(svg.includes('12,25 m') === (access === 'true'), 'Bay override missing from plan');
    check(svg.includes('8,5 m') === (access === 'true'), 'Inherited height missing from plan');
    await pageA.screenshot({path:path.join(output,`alpha9-plan-access-${access}.png`)});
  }
  check((await pageA.locator("h1[data-project-name]").textContent()) === "Hala Žďár – zkouška", "Plan heading has a stale project name");
  await pageA.locator('[data-open-export="plan-export-dialog"]').click();
  const visibleDialog = pageA.locator("#plan-export-dialog");
  check(await visibleDialog.isVisible(), "Plan export dialog is not visible");
  const planOptionSignature = await visibleDialog.locator("option").evaluateAll((options) => options.map((option) => option.value));
  check(JSON.stringify(planOptionSignature) === JSON.stringify(bayOptionSignature), "Bay and plan dialogs do not have identical options");
  check(await visibleDialog.locator('[name="page_size"]').inputValue() === "A2", "Page-size preference was not shared from bay to plan");
  check(await visibleDialog.locator('[name="orientation"]').inputValue() === "portrait", "Orientation preference was not shared from bay to plan");
  check(await visibleDialog.locator('[name="font_size"]').inputValue() === "14", "Font-size preference was not shared from bay to plan");
  await pageA.screenshot({ path: path.join(output, "alpha9-plan-export-dialog.png"), fullPage: true });
  await visibleDialog.locator("[data-close-dialog]").click();
  const planCases = [
    ["A4", "landscape", "auto", "alpha9-browser-plan-clean.pdf", 'false'],
    ["A2", "portrait", "14", "alpha9-browser-plan-A2-access.pdf", 'true'],
    ["A3", "landscape", "10", "alpha9-browser-plan-access.pdf", 'true'],
  ];
  for (const [paper, orientation, font, filename, access] of planCases) {
    await mode(pageA, access === 'true' ? 'survey' : 'diagnostics');
    await pageA.locator('[data-open-export="plan-export-dialog"]').click();
    const form = visibleDialog.locator("[data-export-form]");
    await form.locator('[name="page_size"]').selectOption(paper);
    await form.locator('[name="orientation"]').selectOption(orientation);
    await form.locator('[name="font_size"]').selectOption(font);
    await form.locator(`[name="show_access"][value="${access}"]`).check();
    downloads.push(await savePdfDownload(pageA, form.locator("[data-export-submit]"), filename));
  }
  await pageA.screenshot({ path: path.join(output, "alpha9-plan-page.png"), fullPage: true });
  await pageA.goto(bayUrl);
  await pageA.locator('[data-open-export="bay-export-dialog"]').click();
  check(await pageA.locator('#bay-export-dialog [name="page_size"]').inputValue() === "A3", "Page-size preference was not shared from plan to bay");
  check(await pageA.locator('#bay-export-dialog [name="orientation"]').inputValue() === "landscape", "Orientation preference was not shared from plan to bay");
  check(await pageA.locator('#bay-export-dialog [name="font_size"]').inputValue() === "10", "Font-size preference was not shared from plan to bay");
  await pageA.locator("#bay-export-dialog [data-close-dialog]").click();

  const keptId = await createProject(pageA, "Hala, která zůstane", 1, 2);
  check(keptId !== projectId, "Control project reused the deleted project's id");
  await pageA.goto(`${base}/projects/${projectId}`);
  await pageB.goto(`${base}/projects/${projectId}`);
  await pageB.waitForSelector('[data-connection][data-state="online"]');
  check(await pageA.locator('[data-project-state="archive"]').count() === 1, "Archive action is no longer separate");
  await pageA.locator("[data-open-project-delete]").click();
  const deleteForm = pageA.locator("[data-project-delete-form]");
  const confirmButton = deleteForm.locator("[data-confirm-project-delete]");
  await deleteForm.locator('[name="confirmation_name"]').fill("Hala Žďár");
  check(await confirmButton.isDisabled(), "Delete became enabled for a non-exact name");
  await deleteForm.locator('[name="confirmation_name"]').fill("Hala Žďár – zkouška");
  check(await confirmButton.isEnabled(), "Delete stayed disabled for the exact name");
  await Promise.all([
    pageA.waitForURL(`${base}/`, { timeout: 10_000 }),
    pageB.waitForURL(`${base}/`, { timeout: 10_000 }),
    confirmButton.click(),
  ]);
  check(await pageA.locator(`[data-project-card-id="${projectId}"]`).count() === 0, "Deleted project remains in client A");
  check(await pageB.locator(`[data-project-card-id="${projectId}"]`).count() === 0, "Deleted project remains in client B");
  check(await pageA.locator(`[data-project-card-id="${keptId}"]`).count() === 1, "Unrelated project was removed");
  check(consoleErrors.length === 0, `Browser console errors during normal workflows: ${consoleErrors.join(" | ")}`);
  const missing = await pageA.goto(`${base}/projects/${projectId}`);
  check(missing.status() === 404, `Deleted project returned ${missing.status()} instead of 404`);
  await pageA.goto(`${base}/`);
  await pageA.screenshot({ path: path.join(output, "alpha9-after-delete.png"), fullPage: true });

  const result = {
    projectId,
    keptId,
    renamed: "Hala Žďár – zkouška",
    downloads,
    realtimeRename: true,
    realtimeDelete: true,
    sharedGeometryAfterLabelAndResize: true,
    diagnosticAndSurveyDataIndependent: true,
    mobileAndTabletModeSwitch: true,
    exportsFromBothModes: true,
    consoleErrorsDuringNormalWorkflows: [],
  };
  await fs.writeFile(path.join(output, "browser-results.json"), JSON.stringify(result, null, 2), "utf8");
  console.log(JSON.stringify(result, null, 2));
} finally {
  await contextA.close();
  await contextB.close();
  await browser.close();
}
