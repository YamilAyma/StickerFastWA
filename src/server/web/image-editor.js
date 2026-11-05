"use strict";
window.StickerEditor = (() => {
  const { t } = window.I18n;
  const $ = (id) => document.getElementById(id);
  const dialog = $("image-editor");
  const canvas = $("editor-canvas");
  const ctx = canvas.getContext("2d");
  const art = document.createElement("canvas");
  art.width = art.height = 512;
  const artCtx = art.getContext("2d", { willReadFrequently: true });
  const layer = document.createElement("canvas");
  layer.width = layer.height = 512;
  const layerCtx = layer.getContext("2d");
  const outline = document.createElement("canvas");
  outline.width = outline.height = 512;
  const outlineCtx = outline.getContext("2d");
  let source = null,
    file = null,
    resolve = null,
    tool = "move",
    drag = null,
    path = [],
    history = [];
  let angle = 0,
    flip = 1,
    saving = false,
    generation = 0;
  const values = {
    zoom: 1,
    x: 0,
    y: 0,
    text: "",
    "text-color": "#ffffff",
    font: 40,
    "text-y": 432,
    border: 0,
    "border-color": "#ffffff",
  };
  function sync() {
    for (const key of Object.keys(values))
      $("editor-" + key).value = values[key];
  }
  function posed() {
    layerCtx.clearRect(0, 0, 512, 512);
    layerCtx.save();
    layerCtx.translate(256 + Number(values.x), 256 + Number(values.y));
    layerCtx.rotate((angle * Math.PI) / 180);
    layerCtx.scale(Number(values.zoom) * flip, Number(values.zoom));
    layerCtx.drawImage(art, -256, -256);
    layerCtx.restore();
  }
  function draw() {
    posed();
    ctx.clearRect(0, 0, 512, 512);
    const border = Number(values.border);
    if (border) {
      outlineCtx.clearRect(0, 0, 512, 512);
      outlineCtx.drawImage(layer, 0, 0);
      outlineCtx.globalCompositeOperation = "source-in";
      outlineCtx.fillStyle = values["border-color"];
      outlineCtx.fillRect(0, 0, 512, 512);
      outlineCtx.globalCompositeOperation = "source-over";
      for (let i = 0; i < 32; i++) {
        const radians = (i * Math.PI) / 16;
        ctx.drawImage(
          outline,
          Math.cos(radians) * border,
          Math.sin(radians) * border,
        );
      }
    }
    ctx.drawImage(layer, 0, 0);
    if (values.text.trim()) {
      const size = Number(values.font);
      ctx.font = `700 ${size}px Arial, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      ctx.lineWidth = Math.max(2, size / 10);
      ctx.strokeStyle = "#10213c";
      ctx.fillStyle = values["text-color"];
      const words = values.text.trim().split(/\s+/);
      const lines = [];
      let line = "";
      for (const word of words) {
        const next = line ? line + " " + word : word;
        if (ctx.measureText(next).width > 460 && line) {
          lines.push(line);
          line = word;
        } else line = next;
      }
      lines.push(line);
      lines.slice(0, 3).forEach((text, index, all) => {
        const y =
          Number(values["text-y"]) +
          (index - (all.length - 1) / 2) * size * 1.15;
        ctx.strokeText(text, 256, y, 460);
        ctx.fillText(text, 256, y, 460);
      });
    }
    if (path.length) {
      ctx.save();
      ctx.strokeStyle = "#64ffda";
      ctx.lineWidth = 3;
      ctx.setLineDash([8, 5]);
      ctx.beginPath();
      path.forEach((point, i) =>
        i ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y),
      );
      ctx.stroke();
      ctx.restore();
    }
  }
  function record() {
    history.push({
      pixels: artCtx.getImageData(0, 0, 512, 512),
      values: { ...values },
      angle,
      flip,
    });
    if (history.length > 12) history.shift();
    $("editor-undo").disabled = history.length < 2;
  }
  function bake() {
    posed();
    artCtx.clearRect(0, 0, 512, 512);
    artCtx.drawImage(layer, 0, 0);
    values.zoom = 1;
    values.x = 0;
    values.y = 0;
    angle = 0;
    flip = 1;
    sync();
  }
  function reset() {
    artCtx.clearRect(0, 0, 512, 512);
    const scale = Math.min(
      512 / source.naturalWidth,
      512 / source.naturalHeight,
    );
    const width = source.naturalWidth * scale,
      height = source.naturalHeight * scale;
    artCtx.drawImage(
      source,
      (512 - width) / 2,
      (512 - height) / 2,
      width,
      height,
    );
    Object.assign(values, {
      zoom: 1,
      x: 0,
      y: 0,
      text: "",
      "text-color": "#ffffff",
      font: 40,
      "text-y": 432,
      border: 0,
      "border-color": "#ffffff",
    });
    angle = 0;
    flip = 1;
    path = [];
    sync();
    draw();
  }
  function chooseTool(value) {
    tool = value;
    dialog
      .querySelectorAll("[data-tool]")
      .forEach((button) =>
        button.setAttribute(
          "aria-pressed",
          String(button.dataset.tool === tool),
        ),
      );
    $("editor-hint").textContent = t(
      tool === "move"
        ? "Arrastra para mover. También puedes usar los controles de posición."
        : tool === "cut"
          ? "Dibuja un contorno cerrado: conservaremos su interior."
          : "Pinta sobre las zonas que quieras hacer transparentes.",
    );
    canvas.style.cursor = tool === "move" ? "grab" : "crosshair";
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) * 512) / rect.width,
      y: ((event.clientY - rect.top) * 512) / rect.height,
    };
  }
  function erase(from, to) {
    artCtx.save();
    artCtx.globalCompositeOperation = "destination-out";
    artCtx.lineCap = "round";
    artCtx.lineWidth = Number($("editor-brush").value);
    artCtx.beginPath();
    artCtx.moveTo(from.x, from.y);
    artCtx.lineTo(to.x, to.y);
    artCtx.stroke();
    artCtx.beginPath();
    artCtx.arc(to.x, to.y, artCtx.lineWidth / 2, 0, Math.PI * 2);
    artCtx.fill();
    artCtx.restore();
  }
  function applyCut() {
    if (path.length < 3) {
      path = [];
      draw();
      return;
    }
    bake();
    artCtx.save();
    artCtx.globalCompositeOperation = "destination-in";
    artCtx.beginPath();
    path.forEach((p, i) =>
      i ? artCtx.lineTo(p.x, p.y) : artCtx.moveTo(p.x, p.y),
    );
    artCtx.closePath();
    artCtx.fill();
    artCtx.restore();
    path = [];
    draw();
    record();
  }
  canvas.addEventListener("pointerdown", (event) => {
    if (!source || saving || drag || event.button !== 0) return;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    const p = point(event);
    drag = {
      pointer: event.pointerId,
      start: p,
      last: p,
      x: Number(values.x),
      y: Number(values.y),
    };
    if (tool === "cut") path = [p];
    if (tool === "erase") {
      bake();
      erase(p, p);
      draw();
    }
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag || drag.pointer !== event.pointerId) return;
    const p = point(event);
    if (tool === "move") {
      values.x = Math.max(-512, Math.min(512, drag.x + p.x - drag.start.x));
      values.y = Math.max(-512, Math.min(512, drag.y + p.y - drag.start.y));
      sync();
    }
    if (tool === "cut" && path.length < 4096) path.push(p);
    if (tool === "erase") erase(drag.last, p);
    drag.last = p;
    draw();
  });
  function finishPointer(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    drag = null;
    if (tool === "cut") applyCut();
    else record();
  }
  canvas.addEventListener("pointerup", finishPointer);
  canvas.addEventListener("pointercancel", (event) => {
    if (drag?.pointer === event.pointerId) {
      drag = null;
      path = [];
      draw();
      record();
    }
  });
  dialog
    .querySelectorAll("[data-tool]")
    .forEach((button) =>
      button.addEventListener("click", () => chooseTool(button.dataset.tool)),
    );
  for (const key of Object.keys(values)) {
    $("editor-" + key).addEventListener("input", (event) => {
      values[key] = event.target.value;
      draw();
    });
    $("editor-" + key).addEventListener("change", record);
  }
  $("editor-rotate").addEventListener("click", () => {
    angle = (angle + 90) % 360;
    draw();
    record();
  });
  $("editor-flip").addEventListener("click", () => {
    flip *= -1;
    draw();
    record();
  });
  $("editor-circle").addEventListener("click", () => {
    bake();
    artCtx.save();
    artCtx.globalCompositeOperation = "destination-in";
    artCtx.beginPath();
    artCtx.arc(256, 256, 248, 0, Math.PI * 2);
    artCtx.fill();
    artCtx.restore();
    draw();
    record();
  });
  $("editor-reset").addEventListener("click", () => {
    if (!source || saving) return;
    reset();
    record();
    chooseTool("move");
  });
  $("editor-undo").addEventListener("click", () => {
    if (!source || saving) return;
    if (history.length < 2) return;
    history.pop();
    const state = history[history.length - 1];
    artCtx.putImageData(state.pixels, 0, 0);
    Object.assign(values, state.values);
    angle = state.angle;
    flip = state.flip;
    path = [];
    sync();
    draw();
    $("editor-undo").disabled = history.length < 2;
  });
  function close(result) {
    generation++;
    const done = resolve;
    resolve = null;
    source = null;
    file = null;
    history = [];
    drag = null;
    path = [];
    saving = false;
    artCtx.clearRect(0, 0, 512, 512);
    ctx.clearRect(0, 0, 512, 512);
    dialog.close();
    if (done) done(result);
  }
  $("editor-close").addEventListener("click", () => close(null));
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close(null);
  });
  $("editor-remove-bg").addEventListener("click", async () => {
    if (!source || saving) return;
    const token = generation;
    saving = true;
    $("editor-save").disabled = true;
    $("editor-fields").disabled = true;
    $("editor-error").hidden = true;
    $("editor-hint").textContent = t(
      "Quitando fondo… La primera vez puede tardar mientras se descarga el modelo.",
    );
    try {
      // Send artwork only, preserving editable text and borders as separate layers.
      posed();
      const blob = await new Promise((done) => layer.toBlob(done, "image/png"));
      if (!blob) throw new Error();
      const body = new FormData();
      body.append("file", blob, "sticker.png");
      const response = await fetch("/api/remove-background", {
        method: "POST",
        body,
        signal: AbortSignal.timeout(180000),
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(t(data.detail));
      }
      const bitmap = await createImageBitmap(await response.blob());
      if (token !== generation) {
        bitmap.close();
        return;
      }
      artCtx.clearRect(0, 0, 512, 512);
      artCtx.drawImage(bitmap, 0, 0, 512, 512);
      bitmap.close();
      values.zoom = 1;
      values.x = 0;
      values.y = 0;
      angle = 0;
      flip = 1;
      sync();
      draw();
      record();
    } catch (error) {
      if (token !== generation) return;
      $("editor-error").textContent =
        error.message && error.name !== "TimeoutError"
          ? error.message
          : t(
              "No se pudo quitar el fondo. La primera vez se necesita Internet para descargar el modelo.",
            );
      $("editor-error").hidden = false;
    } finally {
      if (token === generation) {
        saving = false;
        $("editor-save").disabled = false;
        $("editor-fields").disabled = false;
        chooseTool(tool);
      }
    }
  });
  $("editor-save").addEventListener("click", () => {
    if (!source || saving) return;
    const token = generation;
    saving = true;
    $("editor-save").disabled = true;
    $("editor-fields").disabled = true;
    path = [];
    draw();
    canvas.toBlob((blob) => {
      if (token !== generation) return;
      if (!blob) {
        saving = false;
        $("editor-save").disabled = false;
        $("editor-fields").disabled = false;
        $("editor-error").textContent = t("No se pudo guardar la imagen.");
        $("editor-error").hidden = false;
        return;
      }
      const result = new File(
        [blob],
        file.name.replace(/\.[^.]+$/, "") + "-editado.png",
        { type: "image/png", lastModified: Date.now() },
      );
      close(result);
    }, "image/png");
  });
  return {
    async open(input) {
      if (dialog.open) return null;
      const header = new Uint8Array(await input.arrayBuffer());
      if (dialog.open) return null;
      // Never flatten GIF or animated WebP while editing a still image.
      if (
        /\.gif$/i.test(input.name) ||
        (header[0] === 82 && header[8] === 87 && isAnimatedWebP(header))
      )
        throw new Error(
          t(
            "La edición de animaciones se añadirá después. El archivo conserva su animación.",
          ),
        );
      const token = ++generation;
      return new Promise((done) => {
        resolve = done;
        file = input;
        source = null;
        saving = false;
        history = [];
        $("editor-fields").disabled = true;
        $("editor-save").disabled = true;
        $("editor-error").hidden = true;
        $("editor-undo").disabled = true;
        ctx.clearRect(0, 0, 512, 512);
        dialog.showModal();
        const image = new Image();
        const url = URL.createObjectURL(input);
        image.onload = () => {
          URL.revokeObjectURL(url);
          if (token !== generation) return;
          if (image.naturalWidth * image.naturalHeight > 25000000) {
            $("editor-error").textContent = t(
              "Imagen demasiado grande (máximo 25 megapíxeles).",
            );
            $("editor-error").hidden = false;
            return;
          }
          source = image;
          reset();
          record();
          chooseTool("move");
          $("editor-fields").disabled = false;
          $("editor-save").disabled = false;
        };
        image.onerror = () => {
          URL.revokeObjectURL(url);
          if (token !== generation) return;
          $("editor-error").textContent = t(
            "No se pudo leer el archivo. Comprueba que sea una imagen o un video válido.",
          );
          $("editor-error").hidden = false;
        };
        image.src = url;
      });
    },
  };
  function isAnimatedWebP(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let offset = 12; offset + 8 <= bytes.length; ) {
      const tag = String.fromCharCode(...bytes.subarray(offset, offset + 4));
      if (tag === "ANIM") return true;
      const size = view.getUint32(offset + 4, true);
      offset += 8 + size + (size % 2);
    }
    return false;
  }
})();
