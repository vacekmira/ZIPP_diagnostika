(() => {
  const scriptVersion = "Alpha 8";
  if (document.body) document.body.dataset.jsVersion = scriptVersion;
  const storageKey = "zipp.technician";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const toast = $("[data-toast]");
  let technician = localStorage.getItem(storageKey) || "";
  const storedLanguage = localStorage.getItem("zipp.language");
  let language = ["cs", "sk"].includes(storedLanguage) ? storedLanguage : (window.ZIPP_LANG || "cs");
  const catalog = window.ZIPP_I18N || {};
  const t = (key) => catalog[language]?.[key] || catalog.cs?.[key] || key;

  function parseHeight(value) {
    const text = String(value || '').trim().replace(',', '.');
    if (!text) return null;
    const height = Number(text);
    if (!Number.isFinite(height) || height <= 0 || height > 1000) throw new Error(t('error.validation'));
    return height;
  }

  $$('[data-language]').forEach((button) => button.addEventListener("click", () => {
    language = button.dataset.language === "sk" ? "sk" : "cs";
    localStorage.setItem("zipp.language", language);
    document.cookie = `zipp_language=${language}; Path=/; Max-Age=31536000; SameSite=Lax`;
    location.reload();
  }));
  if (document.cookie.match(/(?:^|; )zipp_language=([^;]+)/)?.[1] !== language) {
    document.cookie = `zipp_language=${language}; Path=/; Max-Age=31536000; SameSite=Lax`;
    if (window.ZIPP_LANG !== language) location.reload();
  }

  function notify(message, kind = "ok") {
    if (!toast) return;
    toast.textContent = message;
    toast.dataset.kind = kind;
    toast.classList.add("show");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove("show"), 3500);
  }

  function technicianName() {
    if (!technician) {
      openTechnicianDialog();
      throw new Error(t("error.technician"));
    }
    return technician;
  }

  function updateTechnicianUI() {
    $$('[data-technician-name]').forEach((node) => { node.textContent = technician || t("tech.set"); });
  }

  function openTechnicianDialog() {
    const dialog = $("[data-technician-dialog]");
    if (!dialog) return;
    dialog.querySelector("input").value = technician;
    if (!dialog.open) dialog.showModal();
    setTimeout(() => dialog.querySelector("input").focus(), 0);
  }

  function responseError(response, data) {
      const detail = data?.detail;
      if (response.status === 401) {
        location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
      }
      const serverMessages = {
        "Na vyřazeném vazníku nelze měnit diagnostiku.": "error.excluded",
        "Archivovanou zakázku je nutné nejprve reaktivovat.": "error.archived",
        "Vazník mezitím změnil jiný technik.": "error.conflict",
        "Pro důvod Jiné je poznámka povinná.": "error.other_note",
        "Vazník je v dilatační dvojici; změňte celou dvojici.": "error.pair_member",
        "Dilatační typ lze vytvořit pouze jako dvojici.": "error.pair_only",
        "Dilatační dvojici mohou tvořit pouze dva sousední vazníky ve stejné lodi.": "error.pair_adjacent",
        "Jeden z vazníků už je součástí jiné dilatační dvojice.": "error.pair_exists",
        "Vyřazený vazník nelze zařadit do dilatační dvojice.": "error.pair_excluded",
        "Zmenšení skryje vazníky s existujícími daty.": "error.resize_data",
        "Zmenšení by rozdělilo dilatační dvojici.": "error.resize_pair",
        "Potvrzovací název zakázky nesouhlasí.": "error.project_confirmation",
      };
      const raw = typeof detail === "string" ? detail : detail?.message || data?.message;
      const message = serverMessages[raw] ? t(serverMessages[raw])
        : (raw === "authentication_required" ? t("error.auth") : (Array.isArray(detail) ? t("error.validation") : raw)) || t("save.failed");
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      return error;
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let data = null;
    try { data = await response.json(); } catch (_) { /* response has no JSON */ }
    if (!response.ok) throw responseError(response, data);
    return data;
  }

  async function downloadPdf(url, fallbackFilename) {
    const response = await fetch(url, { headers: { Accept: "application/pdf" } });
    if (!response.ok) {
      let data = null;
      try { data = await response.json(); } catch (_) { /* non-JSON server error */ }
      throw responseError(response, data);
    }
    const blob = await response.blob();
    if (!blob.type.toLowerCase().includes("pdf") || blob.size < 5) {
      throw new Error(t("save.failed"));
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const matched = disposition.match(/filename="?([^";]+)"?/i);
    const filename = matched?.[1] || fallbackFilename;
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1500);
    return filename;
  }

  updateTechnicianUI();
  $$('[data-change-technician]').forEach((button) => button.addEventListener("click", openTechnicianDialog));
  const techForm = $("[data-technician-form]");
  if (techForm) techForm.addEventListener("submit", (event) => {
    event.preventDefault();
    technician = new FormData(techForm).get("technician").trim();
    if (!technician) return;
    localStorage.setItem(storageKey, technician);
    updateTechnicianUI();
    techForm.closest("dialog").close();
    notify(`${t("tech.current")}: ${technician}`);
  });
  if (!technician) openTechnicianDialog();

  $$('[data-close-dialog]').forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));
  const projectDialog = $("[data-project-dialog]");
  const openProject = $("[data-open-project]");
  if (openProject) openProject.addEventListener("click", () => projectDialog.showModal());
  const projectForm = $("[data-project-form]");
  if (projectForm) projectForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(projectForm));
    try {
      const project = await api("/api/projects", { method: "POST", body: JSON.stringify({
        name: values.name, note: values.note || null, bay_count: Number(values.bay_count),
        default_truss_count: Number(values.default_truss_count), technician_name: technicianName(),
        default_height_m: parseHeight(values.default_height_m),
      }) });
      location.href = `/projects/${project.id}`;
    } catch (error) { notify(error.message, "error"); }
  });

  $$('[data-project-state]').forEach((button) => button.addEventListener("click", async () => {
    const action = button.dataset.projectState;
    if (action === "archive" && !confirm(t("confirm.archive"))) return;
    try {
      await api(`/api/projects/${button.dataset.project}/${action}`, { method: "POST", body: JSON.stringify({ technician_name: technicianName() }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  }));

  function updateProjectName(projectId, name) {
    const currentProject = Number(document.body.dataset.projectId) === Number(projectId);
    if (currentProject) {
      $$('[data-project-name]').forEach((node) => { node.textContent = name; });
      document.title = document.title.replace(/^.*?(?= · )/, name);
      const planImage = $("[data-plan-image]");
      if (planImage) planImage.alt = `${t("plan.title")} · ${name}`;
      const deleteForm = $("[data-project-delete-form]");
      if (deleteForm) {
        deleteForm.dataset.projectName = name;
        const shownName = $("[data-delete-project-name]", deleteForm);
        if (shownName) shownName.textContent = name;
      }
    }
    const card = $(`[data-project-card-id="${projectId}"]`);
    const cardName = card && $("[data-project-name]", card);
    if (cardName) cardName.textContent = name;
  }

  const renameDialog = $("[data-project-rename-dialog]");
  const renameButton = $("[data-open-project-rename]");
  const renameForm = $("[data-project-name-form]");
  if (renameButton && renameDialog) renameButton.addEventListener("click", () => {
    const input = $("[data-project-name-input]", renameDialog);
    if (input) input.value = $("[data-project-name]")?.textContent.trim() || input.value;
    renameDialog.showModal();
    setTimeout(() => input?.select(), 0);
  });
  if (renameForm) renameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = new FormData(renameForm).get("name");
    try {
      const project = await api(`/api/projects/${renameForm.dataset.projectId}/name`, {
        method: "PATCH", body: JSON.stringify({ name, technician_name: technicianName() }),
      });
      updateProjectName(project.id, project.name);
      renameDialog.close();
      notify(t("save.project_name"));
    } catch (error) { notify(error.message, "error"); }
  });

  const deleteDialog = $("[data-project-delete-dialog]");
  const deleteButton = $("[data-open-project-delete]");
  const deleteForm = $("[data-project-delete-form]");
  if (deleteButton && deleteDialog) deleteButton.addEventListener("click", () => {
    deleteForm.reset();
    $("[data-confirm-project-delete]", deleteForm).disabled = true;
    deleteDialog.showModal();
    setTimeout(() => deleteForm.elements.confirmation_name.focus(), 0);
  });
  if (deleteForm) {
    const confirmation = deleteForm.elements.confirmation_name;
    const confirmButton = $("[data-confirm-project-delete]", deleteForm);
    confirmation.addEventListener("input", () => {
      confirmButton.disabled = confirmation.value.trim() !== deleteForm.dataset.projectName;
    });
    deleteForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (confirmation.value.trim() !== deleteForm.dataset.projectName) return;
      confirmButton.disabled = true;
      try {
        await api(`/api/projects/${deleteForm.dataset.projectId}`, {
          method: "DELETE",
          body: JSON.stringify({ confirmation_name: confirmation.value.trim(), technician_name: technicianName() }),
        });
        location.href = "/";
      } catch (error) {
        notify(error.message, "error");
        confirmButton.disabled = false;
      }
    });
  }

  const exportStorageKey = "zipp.exportOptions";
  const exportDefaults = { page_size: "A3", orientation: "landscape", font_size: "auto", show_access: "false" };
  const validExportValues = {
    page_size: ["A4", "A3", "A2", "A1", "A0"],
    orientation: ["landscape", "portrait"],
    font_size: ["auto", "7", "9", "10", "12", "14"],
    show_access: ["false", "true"],
  };

  function storedExportOptions() {
    let stored = {};
    try {
      stored = JSON.parse(localStorage.getItem(exportStorageKey)
        || localStorage.getItem("zipp.planExportOptions") || "{}");
    } catch (_) { /* invalid old preference */ }
    const legacyFont = { small: "7", normal: "10", larger: "12", large: "14" }[
      localStorage.getItem("zipp.exportFontSize")
    ];
    if (!stored.font_size && legacyFont) stored.font_size = legacyFont;
    return Object.fromEntries(Object.entries(exportDefaults).map(([key, fallback]) => [
      key, validExportValues[key].includes(stored[key]) ? stored[key] : fallback,
    ]));
  }

  function applyExportOptions(form, options) {
    Object.entries(options).forEach(([key, value]) => { form.elements[key].value = value; });
  }

  function readExportOptions(form) {
    return Object.fromEntries(Object.keys(exportDefaults).map((key) => [key, form.elements[key].value]));
  }

  $$('[data-open-export]').forEach((button) => button.addEventListener("click", () => {
    const dialog = document.getElementById(button.dataset.openExport);
    const form = dialog && $("[data-export-form]", dialog);
    if (!dialog || !form) return;
    applyExportOptions(form, storedExportOptions());
    $("[data-export-error]", form).textContent = "";
    dialog.showModal();
  }));

  $$('[data-export-form]').forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const options = readExportOptions(form);
    const dialog = form.closest("dialog");
    const errorNode = $("[data-export-error]", form);
    const submit = $("[data-export-submit]", form);
    errorNode.textContent = "";
    localStorage.setItem(exportStorageKey, JSON.stringify(options));
    submit.disabled = true;
    try {
      const query = new URLSearchParams({ lang: language, ...options });
      await downloadPdf(`${form.dataset.exportEndpoint}?${query}`, form.dataset.exportFilename);
      dialog.close();
      notify(t(form.dataset.exportReadyKey));
    } catch (error) {
      const recommendations = error.data?.detail?.recommendations || [];
      errorNode.textContent = [error.message, ...recommendations].join("\n");
      notify(error.message, "error");
    } finally {
      submit.disabled = false;
    }
  }));

  const initialPlanImage = $("[data-plan-image]");
  const layerForm = $('[data-plan-layer-form]');
  if (layerForm && initialPlanImage) {
    const applyLayer = () => {
      const url = new URL(initialPlanImage.src);
      url.searchParams.set('show_access', layerForm.elements.show_access.value);
      initialPlanImage.src = url.toString();
    };
    layerForm.elements.show_access.value = localStorage.getItem('zipp.planAccess') === 'true' ? 'true' : 'false';
    applyLayer();
    layerForm.addEventListener('change', () => {
      localStorage.setItem('zipp.planAccess', layerForm.elements.show_access.value);
      applyLayer();
    });
  }
  if (initialPlanImage) {
    const alignPositionOne = () => {
      const viewport = initialPlanImage.closest(".plan-viewport");
      if (viewport) viewport.scrollLeft = viewport.scrollWidth;
    };
    if (initialPlanImage.complete) requestAnimationFrame(alignPositionOne);
    else initialPlanImage.addEventListener("load", alignPositionOne, { once: true });
  }

  function renderSide(button, done) {
    button.classList.toggle("done", done);
    button.setAttribute("aria-pressed", String(done));
    button.querySelector("strong").textContent = done ? `✓ ${t("state.done")}` : `○ ${t("state.pending")}`;
  }

  function updateTruss(data) {
    const row = $(`[data-truss-id="${data.id}"]`);
    if (!row) return;
    row.dataset.version = data.version;
    const label = $("[data-label]", row);
    const type = $("[data-type]", row);
    if (label) label.textContent = data.label;
    if (type) type.textContent = t(`type.${data.type}`);
    const left = $('[data-side="left"]', row);
    const right = $('[data-side="right"]', row);
    if (left) renderSide(left, data.left_done);
    if (right) renderSide(right, data.right_done);
    $$('[data-access-method]', row).forEach(button => {
      button.setAttribute('aria-pressed', String(data[`${button.dataset.accessSide}_access`] === button.dataset.accessMethod));
    });
    const note = $('[data-access-note]', row);
    if (note) note.textContent = data.access_note || '';
  }

  $$('[data-side]').forEach((button) => button.addEventListener("click", async () => {
    const row = button.closest("[data-truss-id]");
    const done = button.getAttribute("aria-pressed") !== "true";
    button.disabled = true;
    try {
      const data = await api(`/api/trusses/${row.dataset.trussId}/diagnostics/${button.dataset.side}`, {
        method: "PUT",
        body: JSON.stringify({ done, technician_name: technicianName(), expected_version: Number(row.dataset.version) }),
      });
      updateTruss(data);
      notify(t(button.dataset.side === "left" ? "save.left" : "save.right"));
      refreshProgress(row.closest("[data-bay-id]")?.dataset.bayId);
    } catch (error) {
      notify(error.message, "error");
      if (error.status === 409) setTimeout(() => location.reload(), 1000);
    } finally { button.disabled = false; }
  }));

  async function refreshProgress(bayId) {
    if (!bayId) return;
    try {
      const bay = await api(`/api/bays/${bayId}`);
      bay.trusses.forEach(updateTruss);
      $$('[data-height-form]').forEach(form => { form.dataset.revision = bay.project_revision; });
      const target = $("[data-bay-progress]");
      if (target) target.textContent = `${bay.progress.completed} / ${bay.progress.required} ${t("progress.done")} · ${bay.progress.remaining} ${t("progress.remaining")}`;
    } catch (_) { /* reconnect will resync */ }
  }

  function updateHeights(project) {
    $$('[data-height-form]').forEach(form => {
      form.dataset.revision = project.revision;
      if (!form.contains(document.activeElement)) {
        const bayId = form.dataset.heightEndpoint.match(/bays\/(\d+)/)?.[1];
        const value = bayId ? project.bays.find(bay => bay.id === Number(bayId))?.height_m : project.default_height_m;
        form.elements.height_m.value = value ?? '';
      }
    });
    project.bays.forEach(bay => $$(`[data-height-bay="${bay.id}"]`).forEach(node => {
      node.textContent = `${t('height.label')}: ${bay.effective_height_m == null ? t('access.not_set') : `${String(bay.effective_height_m).replace('.', ',')} m`}`;
    }));
  }
  $$('[data-height-form]').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = $('button', form); submit.disabled = true;
    try {
      const project = await api(form.dataset.heightEndpoint, {method: 'PUT', body: JSON.stringify({
        height_m: parseHeight(form.elements.height_m.value), expected_revision: Number(form.dataset.revision), technician_name: technicianName(),
      })});
      updateHeights(project); notify(t('height.saved'));
    } catch (error) { notify(error.message, 'error'); }
    finally { submit.disabled = false; }
  }));

  $$('[data-access-method]').forEach(button => button.addEventListener('click', async () => {
    const row = button.closest('[data-truss-id]');
    if (row.dataset.accessBusy === 'true') return;
    row.dataset.accessBusy = 'true';
    $$('[data-access-method]', row).forEach(node => { node.disabled = true; });
    try {
      const data = await api(`/api/trusses/${row.dataset.trussId}/access/${button.dataset.accessSide}`, {method: 'PUT', body: JSON.stringify({
        method: button.getAttribute('aria-pressed') === 'true' ? null : button.dataset.accessMethod,
        expected_version: Number(row.dataset.version), technician_name: technicianName(),
      })});
      updateTruss(data); notify(t('access.saved'));
    } catch (error) {
      notify(error.message, 'error');
      if (error.data?.detail?.current) updateTruss(error.data.detail.current);
    } finally {
      row.dataset.accessBusy = 'false';
      $$('[data-access-method]', row).forEach(node => { node.disabled = false; });
    }
  }));
  const noteDialog = $('[data-access-note-dialog]');
  const noteForm = $('[data-access-note-form]');
  $$('[data-edit-access-note]').forEach(button => button.addEventListener('click', () => {
    const row = button.closest('[data-truss-id]');
    noteForm.dataset.trussId = row.dataset.trussId;
    noteForm.dataset.version = row.dataset.version;
    noteForm.elements.note.value = $('[data-access-note]', row).textContent;
    $('[data-note-label]', noteForm).textContent = $('[data-label]', row).textContent;
    $('[data-note-error]', noteForm).textContent = '';
    noteDialog.showModal();
  }));
  if (noteForm) noteForm.addEventListener('submit', async event => {
    event.preventDefault();
    const submit = $('button.button.primary', noteForm); submit.disabled = true;
    try {
      const data = await api(`/api/trusses/${noteForm.dataset.trussId}/access-note`, {method: 'PUT', body: JSON.stringify({
        note: noteForm.elements.note.value, expected_version: Number(noteForm.dataset.version), technician_name: technicianName(),
      })});
      updateTruss(data); noteDialog.close(); notify(t('access.note_saved'));
    } catch (error) { $('[data-note-error]', noteForm).textContent = error.message; }
    finally { submit.disabled = false; }
  });
  const selection = new Map();
  const selectionButton = $('[data-select-mode]');
  const bulkForm = $('[data-bulk-form]');
  let bulkValues = {};
  const showSelection = () => {
    $('[data-selected-count]').textContent = `${t('access.selected')}: ${selection.size}`;
    $('[data-open-bulk]').disabled = selection.size === 0;
    $$('[data-select-truss]').forEach(button => {
      const row = button.closest('[data-truss-id]');
      const selected = selection.has(Number(row.dataset.trussId));
      button.setAttribute('aria-pressed', String(selected)); row.classList.toggle('selected-truss', selected);
    });
  };
  function setSelectionMode(active) {
    selectionButton.setAttribute('aria-pressed', String(active));
    $('[data-bulk-toolbar]').hidden = !active;
    $$('[data-select-truss]').forEach(button => { button.hidden = !active; });
    if (!active) selection.clear();
    showSelection();
  }
  if (selectionButton) {
    selectionButton.addEventListener('click', () => setSelectionMode(selectionButton.getAttribute('aria-pressed') !== 'true'));
    $('[data-end-selection]').addEventListener('click', () => setSelectionMode(false));
    $$('[data-select-truss]').forEach(button => button.addEventListener('click', () => {
      const row = button.closest('[data-truss-id]'); const id = Number(row.dataset.trussId);
      if (selection.has(id)) selection.delete(id); else selection.set(id, Number(row.dataset.version));
      showSelection();
    }));
    $('[data-select-all]').addEventListener('click', () => {
      $$('[data-select-truss]').forEach(button => {
        const row = button.closest('[data-truss-id]'); selection.set(Number(row.dataset.trussId), Number(row.dataset.version));
      }); showSelection();
    });
    $('[data-open-bulk]').addEventListener('click', () => {
      bulkValues = {};
      $$('[data-bulk-method]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.bulkMethod === 'keep')));
      $('[data-bulk-count]').textContent = `${t('access.selected')}: ${selection.size}`;
      $('[data-bulk-submit]').disabled = true; $('[data-bulk-error]').textContent = '';
      $('[data-bulk-dialog]').showModal();
    });
    $$('[data-bulk-method]').forEach(button => button.addEventListener('click', () => {
      const field = `${button.dataset.accessSide}_access`;
      if (button.dataset.bulkMethod === 'keep') delete bulkValues[field];
      else bulkValues[field] = button.dataset.bulkMethod === 'clear' ? null : button.dataset.bulkMethod;
      $$(`[data-bulk-method][data-access-side="${button.dataset.accessSide}"]`).forEach(node => node.setAttribute('aria-pressed', String(node === button)));
      $('[data-bulk-submit]').disabled = Object.keys(bulkValues).length === 0;
    }));
    bulkForm.addEventListener('submit', async event => {
      event.preventDefault(); const submit = $('[data-bulk-submit]'); submit.disabled = true;
      try {
        const data = await api(`/api/bays/${$('[data-bay-id]').dataset.bayId}/access/bulk`, {method:'POST', body:JSON.stringify({
          items: [...selection].map(([truss_id, expected_version]) => ({truss_id, expected_version})),
          ...bulkValues, technician_name: technicianName(),
        })});
        data.changed.forEach(updateTruss); $('[data-bulk-dialog]').close(); setSelectionMode(false); notify(t('access.bulk_saved'));
      } catch (error) { $('[data-bulk-error]').textContent = error.message; }
      finally { submit.disabled = false; }
    });
  }

  const bayNameForm = $("[data-bay-name-form]");
  if (bayNameForm) bayNameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/bays/${bayNameForm.dataset.bayId}`, { method: "PATCH", body: JSON.stringify({
        name: new FormData(bayNameForm).get("name"), technician_name: technicianName(),
      }) });
      notify(t("save.bay_name"));
    } catch (error) { notify(error.message, "error"); }
  });

  const resizeForm = $("[data-resize-form]");
  if (resizeForm) resizeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const trussCount = Number(new FormData(resizeForm).get("truss_count"));
    const send = (confirmResize) => api(`/api/bays/${resizeForm.dataset.bayId}/resize`, { method: "POST", body: JSON.stringify({
      truss_count: trussCount, confirm: confirmResize, technician_name: technicianName(),
    }) });
    try { await send(false); location.reload(); }
    catch (error) {
      if (error.status === 409 && error.data?.detail?.confirmation_required && confirm(t("confirm.resize"))) {
        try { await send(true); location.reload(); } catch (secondError) { notify(secondError.message, "error"); }
      } else notify(error.message, "error");
    }
  });

  const labelsForm = $("[data-labels-form]");
  if (labelsForm) labelsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const rows = $$(".admin-row", labelsForm);
    const items = rows.map((row) => ({ truss_id: Number(row.dataset.trussId), label: $('[name="label"]', row).value, expected_version: Number(row.dataset.version) }));
    try {
      const result = await api(`/api/bays/${labelsForm.dataset.bayId}/labels/bulk`, { method: "POST", body: JSON.stringify({ technician_name: technicianName(), items }) });
      result.changed.forEach((item) => { const row = $(`.admin-row[data-truss-id="${item.id}"]`); if (row) row.dataset.version = item.version; });
      for (const row of rows) {
        const select = $('[name="type"]', row);
        if (!select.disabled) {
          const current = row.dataset.currentType || "normal";
          if (select.value !== current) {
            const updated = await api(`/api/trusses/${row.dataset.trussId}/type`, { method: "PATCH", body: JSON.stringify({
              type: select.value, technician_name: technicianName(), expected_version: Number(row.dataset.version),
            }) });
            row.dataset.version = updated.version;
          }
        }
      }
      notify(t("save.labels"));
      setTimeout(() => location.reload(), 500);
    } catch (error) { notify(error.message, "error"); }
  });

  const pairForm = $("[data-pair-form]");
  if (pairForm) pairForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(pairForm);
    const a = pairForm.elements.truss_a_id.selectedOptions[0];
    const b = pairForm.elements.truss_b_id.selectedOptions[0];
    try {
      await api(`/api/bays/${pairForm.dataset.bayId}/dilation-pairs`, { method: "POST", body: JSON.stringify({
        technician_name: technicianName(), truss_a_id: Number(form.get("truss_a_id")), truss_b_id: Number(form.get("truss_b_id")),
        expected_version_a: Number(a.dataset.version), expected_version_b: Number(b.dataset.version),
      }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  });

  $$('[data-remove-pair]').forEach((button) => button.addEventListener("click", async () => {
    if (!confirm(t("confirm.remove_pair"))) return;
    try {
      await api(`/api/dilation-pairs/${button.dataset.removePair}/remove`, { method: "POST", body: JSON.stringify({
        technician_name: technicianName(), type_a: "normal", type_b: "normal",
        expected_version_a: Number(button.dataset.av), expected_version_b: Number(button.dataset.bv),
      }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  }));

  const excludeForm = $("[data-exclude-form]");
  if (excludeForm) excludeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(excludeForm);
    try {
      await api(`/api/trusses/${excludeForm.dataset.trussId}/exclude`, { method: "POST", body: JSON.stringify({
        technician_name: technicianName(), expected_version: Number(excludeForm.dataset.version),
        reason: form.get("reason"), note: form.get("note") || null,
      }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  });

  $$('[data-restore]').forEach((button) => button.addEventListener("click", async () => {
    try {
      await api(`/api/trusses/${button.dataset.restore}/restore`, { method: "POST", body: JSON.stringify({
        technician_name: technicianName(), expected_version: Number(button.dataset.version),
      }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  }));

  $$('[data-local-time]').forEach((time) => {
    const value = new Date(time.dateTime);
    if (!Number.isNaN(value.valueOf())) time.textContent = value.toLocaleString(language === "sk" ? "sk-SK" : "cs-CZ");
  });

  const projectId = document.body.dataset.projectId;
  const projectList = $("[data-project-list]");
  const connection = $("[data-connection]");
  $$('[data-side]').forEach((button) => { button.dataset.readonly = String(button.disabled); });
  let socket;
  let retry = 1000;
  let reloadTimer;
  let reconnectTimer;
  let heartbeatTimer;
  let pongTimer;
  let intentionalClose = false;
  function connectionState(state, text) {
    if (!connection) return;
    connection.dataset.state = state;
    connection.querySelector("span").textContent = text;
    $$('[data-side]').forEach((button) => {
      if (state !== "online") button.disabled = true;
      else if (!button.closest(".is-excluded") && button.dataset.readonly !== "true") button.disabled = false;
    });
  }
  function connect() {
    if (!projectId && !projectList) return;
    if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    connectionState("connecting", t("connection.connecting"));
    const socketPath = projectId ? `/ws/projects/${projectId}` : "/ws/projects";
    socket = new WebSocket(`${protocol}//${location.host}${socketPath}`);
    socket.onopen = () => {
      retry = 1000;
      connectionState("online", t("connection.online"));
      refreshProgress($("[data-bay-id]")?.dataset.bayId);
      clearInterval(heartbeatTimer);
      const ping = () => {
        if (socket?.readyState !== WebSocket.OPEN) return;
        socket.send("ping");
        clearTimeout(pongTimer);
        pongTimer = setTimeout(() => socket?.close(4000, "heartbeat_timeout"), 12000);
      };
      ping();
      heartbeatTimer = setInterval(ping, 20000);
    };
    socket.onmessage = (event) => {
      if (event.data === "pong") { clearTimeout(pongTimer); return; }
      let message; try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.truss) updateTruss(message.truss);
      if (message.trusses) message.trusses.forEach(updateTruss);
      if (message.project_revision) $$('[data-height-form]').forEach(form => { form.dataset.revision = message.project_revision; });
      if (message.type === 'height.updated' && message.project) updateHeights(message.project);
      if (message.type === "project.renamed" && message.project) {
        updateProjectName(message.project.id, message.project.name);
      }
      if (message.type === "project.deleted") {
        const card = $(`[data-project-card-id="${message.project_id}"]`);
        if (card) card.remove();
        if (Number(projectId) === Number(message.project_id)) {
          notify(t("project.deleted_redirect"), "error");
          clearTimeout(reloadTimer); reloadTimer = setTimeout(() => { location.href = "/"; }, 1200);
          return;
        }
      }
      if (message.bay_id === Number($("[data-bay-id]")?.dataset.bayId)) refreshProgress(message.bay_id);
      const planImage = $("[data-plan-image]");
      if (["project.archived", "project.reactivated"].includes(message.type)) {
        clearTimeout(reloadTimer); reloadTimer = setTimeout(() => location.reload(), 300);
      }
      if (!planImage && ["bay.resized", "dilation_pair.created", "dilation_pair.removed", "truss.excluded", "truss.restored"].includes(message.type)) {
        clearTimeout(reloadTimer); reloadTimer = setTimeout(() => location.reload(), 600);
      }
      if (planImage && message.type !== "connected") {
        const url = new URL(planImage.src);
        url.searchParams.set("revision", message.project_revision || Date.now());
        planImage.src = url.toString();
      }
    };
    socket.onclose = (event) => {
      clearInterval(heartbeatTimer); clearTimeout(pongTimer);
      if (event.code === 4401) { location.href = `/login?next=${encodeURIComponent(location.pathname)}`; return; }
      if (intentionalClose) return;
      connectionState("offline", t("connection.offline"));
      clearTimeout(reconnectTimer);
      const jitter = Math.round(Math.random() * 350);
      reconnectTimer = setTimeout(connect, retry + jitter);
      retry = Math.min(retry * 1.7, 15000);
    };
    socket.onerror = () => { /* onclose owns reconnect and UI state */ };
  }
  connect();
  addEventListener("online", connect);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) connect(); });
  addEventListener("beforeunload", () => { intentionalClose = true; clearTimeout(reconnectTimer); clearInterval(heartbeatTimer); });
})();
