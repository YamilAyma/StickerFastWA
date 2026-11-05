"use strict";
const { t } = window.I18n;
const $ = (id) => document.getElementById(id);
const entries = [];
const allowed = new Set([
  "png",
  "jpg",
  "jpeg",
  "webp",
  "gif",
  "mp4",
  "webm",
  "mov",
  "avi",
  "mkv",
]);
const videos = new Set(["mp4", "webm", "mov", "avi", "mkv"]);
let icon = null;
let iconUrl = null;
let activeJob = null;
let busy = false;
let pollTimer = null;
let uploadRequest = null;
let resultJob = null;
let resultGeneration = 0;
const storage = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* Preferences are optional. */
    }
  },
};
const session = {
  get() {
    try {
      return sessionStorage.getItem("stickerfast-job");
    } catch {
      return null;
    }
  },
  set(id) {
    try {
      id
        ? sessionStorage.setItem("stickerfast-job", id)
        : sessionStorage.removeItem("stickerfast-job");
    } catch {
      /* Reload recovery is optional. */
    }
  },
};
function showMessage(text = "") {
  $("message").textContent = t(text);
  $("message").hidden = !text;
}
function suffix(file) {
  return file.name.split(".").pop().toLowerCase();
}
function selected() {
  return entries.filter((entry) => entry.selected);
}
function bytes(size) {
  return size >= 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)} MB`
    : `${Math.ceil(size / 1024)} KB`;
}
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("theme").textContent =
    theme === "dark" ? t("Tema claro") : t("Tema oscuro");
  $("theme").setAttribute(
    "aria-label",
    t(theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"),
  );
  storage.set("stickerfast-theme", theme);
}
setTheme(storage.get("stickerfast-theme") || "dark");
$("theme").addEventListener("click", () =>
  setTheme(
    document.documentElement.dataset.theme === "dark" ? "light" : "dark",
  ),
);
$("author").value = storage.get("stickerfast-author") || "";

function setBusy(value) {
  busy = value;
  document.body.classList.toggle("busy", value);
  $("settings-fields").disabled = value;
  $("files").disabled = value;
  $("clear").disabled = value;
  for (const control of $("media-grid").querySelectorAll("input, button"))
    control.disabled = value;
  updateSummary();
}
function updateSummary() {
  const selection = selected();
  $("count").textContent = `${entries.length} / 30`;
  $("selected-count").textContent = t(
    selection.length === 1 ? "{count} sticker" : "{count} stickers",
    { count: selection.length },
  );
  $("selection-summary").textContent = t("{count} seleccionados · {size}", {
    count: selection.length,
    size: bytes(selection.reduce((sum, entry) => sum + entry.file.size, 0)),
  });
  $("empty-note").hidden = entries.length > 0;
  $("collection-toolbar").hidden = entries.length === 0;
  $("create").disabled = busy || selection.length === 0;
}
function renderFiles() {
  $("media-grid").replaceChildren();
  for (const entry of entries) {
    const card = document.createElement("article");
    card.className = `media-card${entry.selected ? "" : " excluded"}`;
    const preview = document.createElement("div");
    preview.className = "preview";
    const media = document.createElement(
      videos.has(suffix(entry.file)) ? "video" : "img",
    );
    media.src = entry.url;
    if (media.tagName === "VIDEO") {
      media.muted = true;
      media.playsInline = true;
      media.preload = "metadata";
      media.setAttribute("aria-label", entry.file.name);
    } else {
      media.alt = entry.file.name;
      media.loading = "lazy";
    }
    media.addEventListener("error", () => {
      preview.replaceChildren(document.createTextNode(t("Sin vista previa")));
    });
    preview.append(media);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-file";
    remove.textContent = "×";
    remove.setAttribute(
      "aria-label",
      t("Quitar {name}", { name: entry.file.name }),
    );
    remove.addEventListener("click", () => {
      if (busy) return;
      URL.revokeObjectURL(entry.url);
      entries.splice(entries.indexOf(entry), 1);
      renderFiles();
    });
    const meta = document.createElement("div");
    meta.className = "media-meta";
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = entry.selected;
    checkbox.setAttribute(
      "aria-label",
      t("Incluir {name}", { name: entry.file.name }),
    );
    checkbox.addEventListener("change", () => {
      entry.selected = checkbox.checked;
      card.classList.toggle("excluded", !entry.selected);
      updateSummary();
    });
    const filename = document.createElement("span");
    filename.textContent = entry.file.name;
    filename.title = entry.file.name;
    label.append(checkbox, filename);
    const info = document.createElement("small");
    info.textContent = `${suffix(entry.file).toUpperCase()} · ${bytes(entry.file.size)}`;
    meta.append(label, info);
    const actions = document.createElement("div");
    actions.className = "card-actions";
    if (!videos.has(suffix(entry.file)) && suffix(entry.file) !== "gif") {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "quiet";
      edit.textContent = t("Editar imagen");
      edit.addEventListener("click", async () => {
        if (busy) return;
        edit.disabled = true;
        try {
          const result = await window.StickerEditor.open(entry.file);
          if (result && entries.includes(entry)) {
            entry.original ??= entry.file;
            URL.revokeObjectURL(entry.url);
            entry.file = result;
            entry.url = URL.createObjectURL(result);
            renderFiles();
          }
        } catch (error) {
          showMessage(error.message);
        } finally {
          edit.disabled = busy;
        }
      });
      actions.append(edit);
    }
    if (entry.original) {
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "text-button";
      restore.textContent = t("Restaurar original");
      restore.addEventListener("click", () => {
        if (busy) return;
        URL.revokeObjectURL(entry.url);
        entry.file = entry.original;
        entry.original = null;
        entry.url = URL.createObjectURL(entry.file);
        renderFiles();
      });
      actions.append(restore);
    }
    card.append(preview, remove, meta, actions);
    $("media-grid").append(card);
  }
  updateSummary();
}
function addFiles(files) {
  if (busy) return;
  const errors = [];
  for (const file of files) {
    if (!allowed.has(suffix(file))) {
      errors.push(t("{name}: formato no admitido.", { name: file.name }));
      continue;
    }
    if (!file.size || file.size > 25 * 1024 * 1024) {
      errors.push(
        t("{name}: debe pesar entre 1 byte y 25 MB.", { name: file.name }),
      );
      continue;
    }
    if (
      entries.some(
        (entry) =>
          entry.file.name === file.name &&
          entry.file.size === file.size &&
          entry.file.lastModified === file.lastModified,
      )
    )
      continue;
    if (entries.length >= 30) {
      errors.push(t("Puedes añadir hasta 30 archivos."));
      break;
    }
    entries.push({ file, url: URL.createObjectURL(file), selected: true });
  }
  if (
    entries.some(
      (entry) => videos.has(suffix(entry.file)) || suffix(entry.file) === "gif",
    )
  )
    $("animated").checked = true;
  showMessage(errors.join(" "));
  renderFiles();
}
$("files").addEventListener("change", (event) => {
  addFiles(event.target.files);
  event.target.value = "";
});
for (const name of ["dragenter", "dragover"])
  $("dropzone").addEventListener(name, (event) => {
    event.preventDefault();
    if (!busy) $("dropzone").classList.add("dragging");
  });
for (const name of ["dragleave", "drop"])
  $("dropzone").addEventListener(name, (event) => {
    event.preventDefault();
    $("dropzone").classList.remove("dragging");
  });
$("dropzone").addEventListener("drop", (event) =>
  addFiles(event.dataTransfer.files),
);
// Prevent a file dropped elsewhere from navigating away from an active job.
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());
$("clear").addEventListener("click", () => {
  if (busy) return;
  entries.forEach((entry) => URL.revokeObjectURL(entry.url));
  entries.length = 0;
  renderFiles();
});
function clearIcon() {
  if (iconUrl) URL.revokeObjectURL(iconUrl);
  icon = null;
  iconUrl = null;
  $("icon").value = "";
  $("tray-preview").textContent = "✦";
  $("icon-label").textContent = t("O usaremos el primer sticker.");
  $("remove-icon").hidden = true;
}
$("remove-icon").addEventListener("click", clearIcon);
$("icon").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (
    !["png", "jpg", "jpeg", "gif", "webp"].includes(suffix(file)) ||
    !file.size ||
    file.size > 25 * 1024 * 1024
  ) {
    showMessage(t("Elige una imagen válida de hasta 25 MB para el icono."));
    event.target.value = "";
    return;
  }
  clearIcon();
  icon = file;
  iconUrl = URL.createObjectURL(file);
  const image = document.createElement("img");
  image.src = iconUrl;
  image.alt = "";
  $("tray-preview").replaceChildren(image);
  $("icon-label").textContent = file.name;
  $("remove-icon").hidden = false;
});
async function responseData(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? t("Revisa los datos del formulario.")
      : t(data.detail);
    const error = new Error(detail || t("No se pudo completar la solicitud."));
    error.status = response.status;
    throw error;
  }
  return data;
}
async function api(url, options) {
  return responseData(
    await fetch(url, { ...options, signal: AbortSignal.timeout(15000) }),
  );
}
function upload(form) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    uploadRequest = request;
    request.open("POST", "/api/jobs");
    request.timeout = 120000;
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable)
        $("job-status").textContent =
          `${t("Subiendo archivos…")} ${Math.round((event.loaded / event.total) * 100)} %`;
    });
    request.onload = () => {
      uploadRequest = null;
      let data;
      try {
        data = JSON.parse(request.responseText);
      } catch {
        reject(new Error(t("Respuesta del servidor no válida.")));
        return;
      }
      if (request.status >= 200 && request.status < 300) resolve(data);
      else
        reject(
          new Error(
            Array.isArray(data.detail)
              ? t("Revisa los datos del formulario.")
              : t(data.detail) || t("No se pudo subir el contenido."),
          ),
        );
    };
    request.onerror = () => {
      uploadRequest = null;
      reject(new Error(t("No se pudo conectar con el servidor local.")));
    };
    request.ontimeout = () => {
      uploadRequest = null;
      reject(
        new Error(
          t(
            "La carga tardó demasiado. Comprueba el servidor antes de reintentar.",
          ),
        ),
      );
    };
    request.send(form);
  });
}
function finishJob(title, description) {
  clearTimeout(pollTimer);
  setBusy(false);
  $("job-title").textContent = title;
  $("job-status").textContent = description;
  $("cancel").hidden = true;
  $("retry").hidden = true;
  $("delete-job").hidden = false;
}
async function poll() {
  if (!activeJob) return;
  const id = activeJob;
  try {
    const job = await api(`/api/jobs/${id}`);
    if (activeJob !== id) return;
    $("retry").hidden = true;
    $("progress").value = job.progress;
    $("job-percentage").textContent = `${job.progress} %`;
    if (job.status === "completed") {
      finishJob(
        t("Tu pack está listo"),
        t("Descárgalo e impórtalo en la app elegida."),
      );
      $("download").href = job.download_url;
      $("download").hidden = false;
      loadResults(id, job.preview_url);
    } else if (job.status === "failed") {
      finishJob(
        t("No se pudo crear el pack"),
        t(job.error) || t("Revisa tus archivos y vuelve a intentarlo."),
      );
    } else if (job.status === "cancelled") {
      finishJob(
        t("Creación cancelada"),
        t("Tu colección sigue aquí. Puedes ajustarla y volver a empezar."),
      );
    } else {
      $("job-title").textContent =
        job.status === "queued"
          ? t("Tu pack está en cola")
          : t("Creando tus stickers");
      $("job-status").textContent =
        job.status === "queued"
          ? t("Esperando un turno de procesamiento…")
          : t("Procesando {current} de {total} archivos…", {
              current: job.current,
              total: job.total,
            });
      $("cancel").disabled = false;
      $("cancel").hidden = false;
      pollTimer = setTimeout(poll, 600);
    }
  } catch (error) {
    if (activeJob !== id) return;
    if (error.status === 404) {
      clearResults();
      finishJob(
        t("El trabajo ya no está disponible"),
        t(
          "El servidor pudo haberse reiniciado o el resultado expiró. Puedes crear otro pack.",
        ),
      );
      activeJob = null;
      session.set(null);
      $("delete-job").hidden = true;
    } else {
      $("job-status").textContent = t(
        "No se pudo consultar el progreso. El trabajo puede seguir ejecutándose.",
      );
      $("retry").hidden = false;
      $("cancel").disabled = false;
    }
  }
}
$("retry").addEventListener("click", () => {
  clearTimeout(pollTimer);
  poll();
});
$("cancel").addEventListener("click", async () => {
  if (!activeJob) return;
  $("cancel").disabled = true;
  try {
    await api(`/api/jobs/${activeJob}/cancel`, { method: "POST" });
    $("job-status").textContent = t(
      "Cancelando… Esperando a que termine el archivo actual.",
    );
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, 500);
  } catch (error) {
    showMessage(error.message);
    $("cancel").disabled = false;
    clearTimeout(pollTimer);
    poll();
  }
});
$("delete-job").addEventListener("click", async () => {
  if (!activeJob) return;
  try {
    await api(`/api/jobs/${activeJob}`, { method: "DELETE" });
    activeJob = null;
    session.set(null);
    $("job-panel").hidden = true;
    clearResults();
    showMessage();
  } catch (error) {
    showMessage(error.message);
  }
});
$("pack-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const selection = selected();
  if (!selection.length) {
    showMessage(t("Selecciona al menos un archivo."));
    return;
  }
  const name = $("name").value.trim();
  if (
    !name ||
    name === "." ||
    name === ".." ||
    /[\\/:*?"<>|\x00-\x1f]/.test(name)
  ) {
    showMessage(
      "Usa un nombre sin separadores ni caracteres especiales de archivo.",
    );
    $("name").focus();
    return;
  }
  const author = $("author").value.trim();
  if (!author) {
    showMessage("Escribe el nombre del autor.");
    $("author").focus();
    return;
  }
  if (
    selection.reduce((sum, entry) => sum + entry.file.size, icon?.size || 0) >
    100 * 1024 * 1024
  ) {
    showMessage("Los archivos seleccionados y el icono superan los 100 MB.");
    return;
  }
  const animated = $("animated").checked;
  if (
    animated &&
    selection.some(
      (entry) => !["gif", "webp", ...videos].includes(suffix(entry.file)),
    )
  ) {
    showMessage("Para un pack animado, selecciona solo GIF, WebP o videos.");
    return;
  }
  if (!animated && selection.some((entry) => videos.has(suffix(entry.file)))) {
    showMessage("Activa Pack animado para convertir videos.");
    return;
  }
  showMessage();
  // Keep the previous result available until the next job has been accepted.
  const previous = activeJob;
  const form = new FormData();
  selection.forEach((entry) => form.append("files", entry.file));
  form.append("name", name);
  form.append("author", author);
  form.append("package", $("package").value);
  form.append("animated", String(animated));
  form.append("crop_mode", $("crop-mode").value);
  if (icon) form.append("icon", icon);
  setBusy(true);
  clearTimeout(pollTimer);
  $("job-panel").hidden = false;
  $("job-title").textContent = t("Preparando tu colección");
  $("job-status").textContent = t("Subiendo archivos…");
  $("progress").value = 0;
  $("job-percentage").textContent = "0 %";
  $("download").hidden = true;
  $("delete-job").hidden = true;
  $("retry").hidden = true;
  $("cancel").hidden = false;
  $("cancel").disabled = true;
  $("job-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const job = await upload(form);
    clearResults();
    activeJob = job.id;
    session.set(activeJob);
    storage.set("stickerfast-author", author);
    if (previous)
      api(`/api/jobs/${previous}`, { method: "DELETE" }).catch(() => {});
    await poll();
  } catch (error) {
    showMessage(error.message);
    setBusy(false);
    if (previous) {
      activeJob = previous;
      await poll();
    } else {
      $("job-title").textContent = t("No se pudo iniciar el trabajo");
      $("job-status").textContent = t(
        "Revisa tus archivos y vuelve a intentarlo.",
      );
      $("cancel").hidden = true;
    }
  }
});
activeJob = session.get();
if (activeJob && /^[a-f0-9]{32}$/.test(activeJob)) {
  $("job-panel").hidden = false;
  setBusy(true);
  poll();
} else {
  activeJob = null;
  session.set(null);
  updateSummary();
}
window.addEventListener("beforeunload", (event) => {
  if (uploadRequest) {
    event.preventDefault();
    event.returnValue = "";
  }
});

$("language").value = window.I18n.language;
$("language").addEventListener("change", () => {
  window.I18n.setLanguage($("language").value);
  setTheme(document.documentElement.dataset.theme);
  renderFiles();
  setBusy(busy);
  if (!icon) $("icon-label").textContent = t("O usaremos el primer sticker.");
  showMessage();
  if (activeJob) {
    clearTimeout(pollTimer);
    poll();
  }
});

function clearResults() {
  resultGeneration++;
  resultJob = null;
  $("result-panel").hidden = true;
  $("result-grid").replaceChildren();
  $("result-image").removeAttribute("src");
  if ($("result-dialog").open) $("result-dialog").close();
}
function stickerDetail(sticker) {
  const detail = `${sticker.width} × ${sticker.height} · ${bytes(sticker.bytes)}`;
  return sticker.frames > 1
    ? `${detail} · ${(sticker.duration_ms / 1000).toLocaleString(window.I18n.language)} s · ${t("{count} cuadros", { count: sticker.frames })}`
    : detail;
}
async function loadResults(id, url, force = false) {
  if (!url || (!force && resultJob === `${id}:${window.I18n.language}`)) return;
  const token = ++resultGeneration;
  resultJob = `${id}:${window.I18n.language}`;
  $("result-panel").hidden = false;
  $("result-grid").replaceChildren();
  $("result-message").textContent = t("Cargando el resultado del paquete…");
  $("result-message").hidden = false;
  $("result-retry").hidden = true;
  try {
    const manifest = await api(url);
    if (token !== resultGeneration || activeJob !== id) return;
    $("result-message").hidden = true;
    for (const sticker of manifest.stickers) {
      const card = document.createElement("article");
      card.className = "media-card result-card";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "preview transparency";
      const title = t("Sticker {number}", { number: sticker.index + 1 });
      button.setAttribute("aria-label", t("Ampliar {name}", { name: title }));
      const image = document.createElement("img");
      image.src = sticker.url;
      image.alt = title;
      image.loading = "lazy";
      image.addEventListener("error", () => {
        button.textContent = t("Sin vista previa");
      });
      button.append(image);
      button.addEventListener("click", () => {
        $("result-dialog-title").textContent = title;
        $("result-image").src = sticker.url;
        $("result-image").alt = title;
        $("result-detail").textContent = stickerDetail(sticker);
        $("result-dialog").showModal();
      });
      const meta = document.createElement("div");
      meta.className = "media-meta";
      const label = document.createElement("strong");
      label.textContent = title;
      const info = document.createElement("small");
      info.textContent = stickerDetail(sticker);
      meta.append(label, info);
      card.append(button, meta);
      $("result-grid").append(card);
    }
  } catch (error) {
    if (token !== resultGeneration) return;
    resultJob = null;
    $("result-message").textContent = t(
      "No se pudo cargar la vista previa. El paquete sigue disponible para descargar.",
    );
    $("result-retry").hidden = false;
  }
}
$("result-retry").addEventListener("click", () => {
  if (activeJob)
    loadResults(activeJob, `/api/jobs/${activeJob}/stickers`, true);
});
$("close-result").addEventListener("click", () => $("result-dialog").close());
