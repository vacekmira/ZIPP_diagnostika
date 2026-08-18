(() => {
  const storageKey = "zipp.technician";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const toast = $("[data-toast]");
  let technician = localStorage.getItem(storageKey) || "";

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
      throw new Error("Nejprve zadejte jméno technika.");
    }
    return technician;
  }

  function updateTechnicianUI() {
    $$('[data-technician-name]').forEach((node) => { node.textContent = technician || "Nastavit"; });
  }

  function openTechnicianDialog() {
    const dialog = $("[data-technician-dialog]");
    if (!dialog) return;
    dialog.querySelector("input").value = technician;
    if (!dialog.open) dialog.showModal();
    setTimeout(() => dialog.querySelector("input").focus(), 0);
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    let data = null;
    try { data = await response.json(); } catch (_) { /* response has no JSON */ }
    if (!response.ok) {
      const detail = data?.detail;
      const message = typeof detail === "string" ? detail : detail?.message || data?.message || "Změnu se nepodařilo uložit.";
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
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
    notify(`Technik nastaven: ${technician}`);
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
      }) });
      location.href = `/projects/${project.id}`;
    } catch (error) { notify(error.message, "error"); }
  });

  $$('[data-project-state]').forEach((button) => button.addEventListener("click", async () => {
    const action = button.dataset.projectState;
    if (action === "archive" && !confirm("Archivovat zakázku? V archivu bude pouze pro čtení.")) return;
    try {
      await api(`/api/projects/${button.dataset.project}/${action}`, { method: "POST", body: JSON.stringify({ technician_name: technicianName() }) });
      location.reload();
    } catch (error) { notify(error.message, "error"); }
  }));

  function renderSide(button, done) {
    button.classList.toggle("done", done);
    button.setAttribute("aria-pressed", String(done));
    button.querySelector("strong").textContent = done ? "✓ Hotovo" : "○ Neprovedeno";
  }

  function updateTruss(data) {
    const row = $(`[data-truss-id="${data.id}"]`);
    if (!row) return;
    row.dataset.version = data.version;
    const label = $("[data-label]", row);
    const type = $("[data-type]", row);
    if (label) label.textContent = data.label;
    if (type) type.textContent = data.type_label;
    const left = $('[data-side="left"]', row);
    const right = $('[data-side="right"]', row);
    if (left) renderSide(left, data.left_done);
    if (right) renderSide(right, data.right_done);
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
      notify(`${button.dataset.side === "left" ? "Levá" : "Pravá"} strana uložena`);
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
      const target = $("[data-bay-progress]");
      if (target) target.textContent = `${bay.progress.completed} / ${bay.progress.required} stran hotovo · ${bay.progress.remaining} zbývá`;
    } catch (_) { /* reconnect will resync */ }
  }

  const bayNameForm = $("[data-bay-name-form]");
  if (bayNameForm) bayNameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api(`/api/bays/${bayNameForm.dataset.bayId}`, { method: "PATCH", body: JSON.stringify({
        name: new FormData(bayNameForm).get("name"), technician_name: technicianName(),
      }) });
      notify("Název lodě uložen");
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
      if (error.status === 409 && error.data?.detail?.confirmation_required && confirm("Dotčené vazníky obsahují data. Budou zachovány v historii, ale skryty z aktuální struktury. Pokračovat?")) {
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
          const current = select.querySelector("option[selected]")?.value || "normal";
          if (select.value !== current) {
            const updated = await api(`/api/trusses/${row.dataset.trussId}/type`, { method: "PATCH", body: JSON.stringify({
              type: select.value, technician_name: technicianName(), expected_version: Number(row.dataset.version),
            }) });
            row.dataset.version = updated.version;
          }
        }
      }
      notify("Označení a typy uloženy");
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
    if (!confirm("Zrušit celou dilatační dvojici a nastavit oba vazníky jako běžné?")) return;
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
    if (!Number.isNaN(value.valueOf())) time.textContent = value.toLocaleString("cs-CZ");
  });

  const projectId = document.body.dataset.projectId;
  const connection = $("[data-connection]");
  let socket;
  let retry = 1000;
  let reloadTimer;
  function connectionState(state, text) {
    if (!connection) return;
    connection.dataset.state = state;
    connection.querySelector("span").textContent = text;
    $$('[data-side]').forEach((button) => { if (state === "offline") button.disabled = true; else if (!button.closest(".is-excluded")) button.disabled = false; });
  }
  function connect() {
    if (!projectId) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    connectionState("connecting", "Připojuji…");
    socket = new WebSocket(`${protocol}//${location.host}/ws/projects/${projectId}`);
    socket.onopen = () => { retry = 1000; connectionState("online", "Připojeno"); refreshProgress($("[data-bay-id]")?.dataset.bayId); };
    socket.onmessage = (event) => {
      if (event.data === "pong") return;
      let message; try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.truss) updateTruss(message.truss);
      if (message.bay_id === Number($("[data-bay-id]")?.dataset.bayId)) refreshProgress(message.bay_id);
      if (["bay.resized", "dilation_pair.created", "dilation_pair.removed", "truss.excluded", "truss.restored"].includes(message.type)) {
        clearTimeout(reloadTimer); reloadTimer = setTimeout(() => location.reload(), 600);
      }
    };
    socket.onclose = () => { connectionState("offline", "Odpojeno"); setTimeout(connect, retry); retry = Math.min(retry * 1.7, 15000); };
    socket.onerror = () => socket.close();
  }
  connect();
  setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send("ping"); }, 25000);
})();
