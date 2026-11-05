"use strict";
window.AnimationEditor = (() => {
  const { t } = window.I18n,
    $ = (id) => document.getElementById("animation-" + id),
    dialog = $("editor");
  const defaults = {
    start: 0,
    end: 1,
    crop_mode: "fit",
    zoom: 1,
    x: 0,
    y: 0,
    rotate: 0,
    flip: false,
    text: "",
    font: "default",
    font_size: 40,
    text_y: 432,
    text_color: "#ffffff",
    remove_bg: false,
  };
  const numeric = new Set([
    "start",
    "end",
    "zoom",
    "x",
    "y",
    "rotate",
    "font_size",
    "text_y",
  ]);
  let session = null,
    info = null,
    result = null,
    mode = "source",
    index = 0,
    playing = false,
    timer = null,
    clock = 0,
    baseTime = 0,
    resolve = null,
    file = null,
    version = 0,
    busy = false,
    readonly = false,
    history = [],
    cache = new Map();
  function values() {
    const options = {};
    for (const key of Object.keys(defaults)) {
      const element = $(key);
      options[key] =
        element.type === "checkbox"
          ? element.checked
          : numeric.has(key)
            ? Number(element.value)
            : element.value;
    }
    if (!info?.animated) options.end = null;
    return options;
  }
  function assign(options) {
    for (const [key, value] of Object.entries(options)) {
      if ($(key).type === "checkbox") $(key).checked = value;
      else $(key).value = value ?? 0;
    }
  }
  function error(message = "") {
    $("error").textContent = t(message);
    $("error").hidden = !message;
  }
  function markerState() {
    for (const id of ["mark-start", "mark-end"])
      $(id).disabled = busy || readonly || mode !== "source" || !info;
  }
  $("mark-start").addEventListener("click", () => {
    if (busy || readonly || mode !== "source") return;
    $("start").value = position(index).toFixed(3);
    record();
  });
  $("mark-end").addEventListener("click", () => {
    if (busy || readonly || mode !== "source") return;
    $("end").value = (
      index + 1 < count() ? position(index + 1) : info.duration
    ).toFixed(3);
    record();
  });
  function pause() {
    playing = false;
    $("play").setAttribute("aria-pressed", "false");
    clearTimeout(timer);
  }
  function timeline() {
    if (mode === "result" && result) {
      let elapsed = 0;
      return result.durations.map((duration) => {
        const value = elapsed / 1000;
        elapsed += duration;
        return value;
      });
    }
    if (info?.frame_times) return info.frame_times;
    return null;
  }
  function count() {
    return mode === "result" ? result.frames : info.frames;
  }
  function position(frame) {
    const times = timeline();
    return times ? times[frame] : frame / (info.fps || 1);
  }
  function duration() {
    return mode === "result" ? result.duration_ms / 1000 : info.duration;
  }
  async function show(frame) {
    if (!session || !info || busy) return;
    const token = version,
      currentMode = mode;
    index = Math.max(0, Math.min(count() - 1, Math.round(frame)));
    const chosen = index;
    $("seek").max = Math.max(0, count() - 1);
    $("seek").value = index;
    $("position").textContent =
      `${index + 1} / ${count()} · ${position(index).toFixed(3)} s`;
    const url =
      mode === "result"
        ? `/api/animations/${session}/results/${result.result_id}/frame/${index}`
        : `/api/animations/${session}/frame?t=${position(index)}`;
    try {
      let image = cache.get(url);
      if (!image) {
        image = new Image();
        image.alt = t("Vista del sticker");
        const loaded = new Promise((done, fail) => {
          image.onload = done;
          image.onerror = fail;
        });
        image.src = url;
        await loaded;
        if (cache.size >= 12) cache.delete(cache.keys().next().value);
        cache.set(url, image);
      }
      if (token !== version || currentMode !== mode || chosen !== index) return;
      $("screen").replaceChildren(image);
    } catch {
      if (
        token === version &&
        !busy &&
        currentMode === mode &&
        chosen === index
      )
        error("No se pudo leer el cuadro.");
    }
  }
  function switchMode(next) {
    pause();
    mode = next;
    markerState();
    cache.clear();
    show(0);
  }
  async function tick() {
    if (!playing || !info || busy) return;
    const end =
      mode === "source" && !readonly
        ? Math.min(Number($("end").value), duration())
        : duration();
    const start = mode === "source" && !readonly ? Number($("start").value) : 0;
    const span = Math.max(0.008, end - start),
      elapsed = (performance.now() - clock) / 1000 + baseTime;
    const seconds = start + ((((elapsed - start) % span) + span) % span);
    const times = timeline();
    let frame = 0;
    if (times) {
      for (let i = 0; i < times.length; i++) {
        if (times[i] <= seconds) frame = i;
        else break;
      }
    } else frame = Math.floor(seconds * (info.fps || 1));
    await show(frame);
    if (playing) timer = setTimeout(tick, 50);
  }
  function dirty() {
    pause();
    result = null;
    $("apply").disabled = true;
    $("result").disabled = true;
    $("validation").textContent = "";
    mode = "source";
    markerState();
    show(index);
  }
  function record() {
    history.push(values());
    if (history.length > 20) history.shift();
    $("undo").disabled = history.length < 2;
    dirty();
  }
  function controls(value) {
    busy = value;
    markerState();
    $("source").disabled = value || !info;
    $("result").disabled = value || !result;
    $("play").disabled = value || !info || count() < 2;
    $("prev").disabled = value || !info || count() < 2;
    $("next").disabled = value || !info || count() < 2;
    $("fields").disabled = value;
    $("render").disabled = value || readonly;
    $("apply").disabled = value || !result;
    $("reset").disabled = value;
    $("undo").disabled = value || history.length < 2;
  }
  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        t(
          typeof data.detail === "string"
            ? data.detail
            : "Revisa los datos del formulario.",
        ),
      );
    return data;
  }
  async function close(output = null) {
    const id = session;
    version++;
    pause();
    session = null;
    cache.clear();
    $("screen").replaceChildren();
    dialog.close();
    const done = resolve;
    resolve = null;
    if (done) done(output);
    if (id)
      fetch(`/api/animations/${id}`, { method: "DELETE" }).catch(() => {});
  }
  $("close").addEventListener("click", () => close());
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  $("play").addEventListener("click", () => {
    if (!info || busy) return;
    if (playing) {
      pause();
      return;
    }
    playing = true;
    $("play").setAttribute("aria-pressed", "true");
    clock = performance.now();
    baseTime = position(index);
    tick();
  });
  $("seek").addEventListener("input", () => {
    pause();
    show(Number($("seek").value));
  });
  $("prev").addEventListener("click", () => {
    pause();
    show(index - 1);
  });
  $("next").addEventListener("click", () => {
    pause();
    show(index + 1);
  });
  $("source").addEventListener("click", () => switchMode("source"));
  $("result").addEventListener("click", () => switchMode("result"));
  for (const key of Object.keys(defaults))
    $(key).addEventListener("change", record);
  $("undo").addEventListener("click", () => {
    if (busy || history.length < 2) return;
    history.pop();
    assign(history[history.length - 1]);
    $("undo").disabled = history.length < 2;
    dirty();
  });
  $("reset").addEventListener("click", () => {
    if (busy || !info) return;
    assign({ ...defaults, end: Math.min(10, info.duration) });
    record();
  });
  $("render").addEventListener("click", async () => {
    if (!session || busy) return;
    const options = values();
    const length = options.end - options.start;
    if (
      info.animated &&
      (!Number.isFinite(options.start) ||
        !Number.isFinite(options.end) ||
        options.start < 0 ||
        options.end > info.duration + 0.001 ||
        length < info.min_seconds - 0.0001 ||
        length > 10.0001)
    ) {
      error(
        info.video
          ? "El fragmento de video debe durar entre 1 y 10 segundos y estar dentro del video."
          : "Elige un fragmento válido de hasta 10 segundos.",
      );
      return;
    }
    const id = session,
      token = version;
    pause();
    controls(true);
    error();
    $("validation").textContent = t("Procesando todos los cuadros…");
    try {
      const data = await request(`/api/animations/${id}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options),
        signal: AbortSignal.timeout(300000),
      });
      if (token !== version) {
        fetch(`/api/animations/${id}`, { method: "DELETE" }).catch(() => {});
        return;
      }
      result = data;
      $("result").disabled = false;
      $("validation").textContent =
        `${t("Validado")} · ${data.width} × ${data.height} · ${(data.bytes / 1024).toFixed(1)} KB · ${(data.duration_ms / 1000).toFixed(3)} s · ${data.frames} ${t("cuadros")}`;
      controls(false);
      switchMode("result");
    } catch (failure) {
      if (token === version) {
        error(failure.message || "No se pudo procesar la animación.");
        $("validation").textContent = "";
      }
    } finally {
      if (token === version) controls(false);
    }
  });
  $("apply").addEventListener("click", async () => {
    if (!result || busy || !session) return;
    const token = version;
    controls(true);
    try {
      const response = await fetch(result.url);
      if (!response.ok) throw new Error();
      const blob = await response.blob();
      if (token !== version) return;
      const edited = new File(
        [blob],
        file.name.replace(/\.[^.]+$/, "") + "-animado.webp",
        { type: "image/webp", lastModified: Date.now() },
      );
      close(edited);
    } catch {
      error("No se pudo guardar la animación.");
    } finally {
      if (token === version) controls(false);
    }
  });
  async function open(input, readOnly = false) {
    if (dialog.open) return null;
    version++;
    const token = version;
    readonly = readOnly;
    $("title").textContent = t(
      readonly ? "Vista de la animación" : "Edita tu animación",
    );
    $("close").textContent = t(readonly ? "Cerrar" : "Cancelar");
    $("source").hidden = readonly;
    $("result").hidden = readonly;
    file = input;
    session = null;
    info = null;
    result = null;
    history = [];
    cache.clear();
    mode = "source";
    index = 0;
    $("options").hidden = readonly;
    $("markers").hidden = readonly;
    $("render").hidden = readonly;
    $("apply").hidden = readonly;
    $("reset").hidden = readonly;
    $("undo").hidden = readonly;
    $("result").disabled = true;
    $("info").textContent = t("Leyendo la animación…");
    $("validation").textContent = "";
    error();
    controls(true);
    dialog.showModal();
    const promise = new Promise((done) => {
      resolve = done;
    });
    try {
      await window.StickerFonts.ready;
      $("font").replaceChildren();
      const option = document.createElement("option");
      option.value = "default";
      option.textContent = "Comic Neue";
      $("font").append(option);
      for (const font of window.StickerFonts.choices()) {
        const option = document.createElement("option");
        option.value = font.id;
        option.textContent = font.family;
        $("font").append(option);
      }
      const body = new FormData();
      body.append("file", input);
      const data = await request("/api/animations", {
        method: "POST",
        body,
        signal: AbortSignal.timeout(30000),
      });
      if (token !== version) {
        fetch(`/api/animations/${data.id}`, { method: "DELETE" }).catch(
          () => {},
        );
        return promise;
      }
      session = data.id;
      info = data;
      assign({ ...defaults, end: Math.min(data.duration, 10) });
      $("start").max = data.duration;
      $("end").max = data.duration;
      history = [values()];
      $("info").textContent =
        `${data.width} × ${data.height} · ${data.duration.toFixed(3)} s · ${t("Máximo 10 segundos por animación.")}`;
      controls(false);
      show(0);
    } catch (failure) {
      if (token === version) {
        error(failure.message);
        $("info").textContent = t("No se pudo leer la animación.");
      }
    }
    return promise;
  }
  return {
    open,
    async matches(input) {
      if (/\.(gif|mp4|webm|mov|avi|mkv)$/i.test(input.name)) return true;
      if (!/\.webp$/i.test(input.name)) return false;
      const bytes = new Uint8Array(await input.arrayBuffer());
      const view = new DataView(bytes.buffer);
      for (let i = 12; i + 8 <= bytes.length; ) {
        if (String.fromCharCode(...bytes.subarray(i, i + 4)) === "ANIM")
          return true;
        const size = view.getUint32(i + 4, true);
        i += 8 + size + (size % 2);
      }
      return false;
    },
    async viewResult(url) {
      const response = await fetch(url);
      if (!response.ok) throw new Error(t("No se pudo leer la animación."));
      return open(new File([await response.blob()], "result.webp"), true);
    },
  };
})();
