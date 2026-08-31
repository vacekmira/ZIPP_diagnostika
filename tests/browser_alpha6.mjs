import { chromium } from "file:///C:/Users/vac0172/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";
import fs from "node:fs/promises";
import path from "node:path";

const base = process.env.ZIPP_E2E_URL || "http://127.0.0.1:8765";
const password = process.env.ZIPP_E2E_PASSWORD || "Alpha6-test!";
const output = path.resolve("tmp/browser-alpha6");
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
  await page.waitForSelector('body[data-app-version="Alpha 6"][data-js-version="Alpha 6"]');
}

async function createProject(page, name, bays, trusses) {
  await page.goto(`${base}/`);
  await page.locator("[data-open-project]").click();
  const form = page.locator("[data-project-form]");
  await form.locator('[name="name"]').fill(name);
  await form.locator('[name="bay_count"]').fill(String(bays));
  await form.locator('[name="default_truss_count"]').fill(String(trusses));
  await form.locator('[name="note"]').fill("Příliš žluťoučký kůň a slovenský kôň – Alpha 6 E2E.");
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

const browser = await chromium.launch({
  executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  headless: true,
});
const contextA = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
const contextB = await browser.newContext({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
for (const context of [contextA, contextB]) {
  await context.addInitScript(() => {
    localStorage.setItem("zipp.technician", "Alpha 6 browser tester");
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

  const projectId = await createProject(pageA, "Hala Alpha 6 E2E", 3, 24);
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

  const firstBayHref = await pageA.locator(".bay-card").first().getAttribute("href");
  await pageA.goto(`${base}${firstBayHref}`);
  for (const size of ["7", "14"]) {
    await pageA.locator("[data-open-bay-export]").click();
    await pageA.locator('[data-bay-export-form] select[name="font_size"]').selectOption(size);
    downloads.push(await savePdfDownload(
      pageA,
      pageA.locator("[data-bay-export-submit]"),
      `alpha6-browser-bay-${size}pt.pdf`,
    ));
  }

  await pageA.goto(`${base}/projects/${projectId}/plan`);
  check((await pageA.locator("h1[data-project-name]").textContent()) === "Hala Žďár – zkouška", "Plan heading has a stale project name");
  await pageA.locator("[data-open-plan-export]").click();
  const visibleDialog = pageA.locator("[data-plan-export-dialog]");
  check(await visibleDialog.isVisible(), "Plan export dialog is not visible");
  check(await visibleDialog.locator('[name="page_size"] option').count() === 5, "Plan dialog does not offer A4-A0");
  check(await visibleDialog.locator('[name="orientation"] option').count() === 2, "Plan dialog does not offer both orientations");
  check(await visibleDialog.locator('[name="font_size"] option').count() === 6, "Plan dialog does not offer Auto-14 pt");
  await pageA.screenshot({ path: path.join(output, "alpha6-plan-export-dialog.png"), fullPage: true });
  await visibleDialog.locator("[data-close-dialog]").click();
  const planCases = [
    ["A4", "landscape", "auto", "alpha6-browser-plan-A4-landscape-auto.pdf"],
    ["A3", "landscape", "10", "alpha6-browser-plan-A3-landscape-10.pdf"],
    ["A2", "portrait", "14", "alpha6-browser-plan-A2-portrait-14.pdf"],
  ];
  for (const [paper, orientation, font, filename] of planCases) {
    await pageA.locator("[data-open-plan-export]").click();
    const form = pageA.locator("[data-plan-export-form]");
    await form.locator('[name="page_size"]').selectOption(paper);
    await form.locator('[name="orientation"]').selectOption(orientation);
    await form.locator('[name="font_size"]').selectOption(font);
    downloads.push(await savePdfDownload(pageA, form.locator("[data-plan-export-submit]"), filename));
  }
  await pageA.locator("[data-open-plan-export]").click();
  check(await pageA.locator('[data-plan-export-form] [name="page_size"]').inputValue() === "A2", "Page-size preference was not restored");
  check(await pageA.locator('[data-plan-export-form] [name="orientation"]').inputValue() === "portrait", "Orientation preference was not restored");
  check(await pageA.locator('[data-plan-export-form] [name="font_size"]').inputValue() === "14", "Font-size preference was not restored");
  await pageA.locator("[data-plan-export-form] [data-close-dialog]").click();
  await pageA.screenshot({ path: path.join(output, "alpha6-plan-page.png"), fullPage: true });

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
  await pageA.screenshot({ path: path.join(output, "alpha6-after-delete.png"), fullPage: true });

  const result = {
    projectId,
    keptId,
    renamed: "Hala Žďár – zkouška",
    downloads,
    realtimeRename: true,
    realtimeDelete: true,
    consoleErrorsDuringNormalWorkflows: [],
  };
  await fs.writeFile(path.join(output, "browser-results.json"), JSON.stringify(result, null, 2), "utf8");
  console.log(JSON.stringify(result, null, 2));
} finally {
  await contextA.close();
  await contextB.close();
  await browser.close();
}
