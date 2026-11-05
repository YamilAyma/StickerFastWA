"use strict";
window.StickerFonts = (() => {
  const { t } = window.I18n;
  const picker = document.getElementById("editor-font-family");
  const search = document.getElementById("editor-font-search");
  let catalog = [];
  const loaded = new Map();
  const normalize = (value) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  function refresh(selected = picker.value || "default") {
    picker.replaceChildren();
    const fallback = document.createElement("option");
    fallback.value = "default";
    fallback.textContent = t("Predeterminada (Arial)");
    picker.append(fallback);
    const groups = new Map(),
      query = normalize(search.value);
    for (const font of catalog) {
      if (
        font.id !== selected &&
        !normalize(font.family + " " + t(font.category)).includes(query)
      )
        continue;
      if (!groups.has(font.category)) {
        const group = document.createElement("optgroup");
        group.label = t(font.category);
        groups.set(font.category, group);
        picker.append(group);
      }
      const option = document.createElement("option");
      option.value = font.id;
      option.textContent = font.family;
      groups.get(font.category).append(option);
    }
    picker.value = Array.from(picker.options).some(
      (option) => option.value === selected,
    )
      ? selected
      : "default";
  }
  const ready = fetch("/web/fonts/catalog.json")
    .then((response) => {
      if (!response.ok) throw new Error();
      return response.json();
    })
    .then((data) => {
      catalog = data;
      refresh();
    })
    .catch(() => {
      catalog = [];
      refresh();
    });
  async function load(id) {
    if (id === "default") return;
    await ready;
    const font = catalog.find((item) => item.id === id);
    if (!font) throw new Error("Unknown font");
    if (!loaded.has(id)) {
      const face = new FontFace("StickerFont_" + id, `url("${font.url}")`, {
        weight: "700",
        style: "normal",
      });
      let timer;
      const promise = Promise.race([
        face.load(),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error("Font timeout")), 15000);
        }),
      ])
        .then((result) => {
          document.fonts.add(result);
        })
        .catch((error) => {
          loaded.delete(id);
          throw error;
        })
        .finally(() => clearTimeout(timer));
      loaded.set(id, promise);
    }
    return loaded.get(id);
  }
  search.addEventListener("input", () => refresh());
  return {
    ready,
    load,
    refresh,
    select(id) {
      refresh(id);
    },
    family(id) {
      return id === "default"
        ? "Arial, sans-serif"
        : `"StickerFont_${id}", Arial, sans-serif`;
    },
  };
})();
