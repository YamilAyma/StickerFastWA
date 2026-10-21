"use strict";
window.I18n = (() => {
  const catalogs = window.STICKERFAST_TRANSLATIONS;
  let language = "es";
  try {
    language = localStorage.getItem("stickerfast-language") || "es";
  } catch {
    /* Optional storage. */
  }
  if (!Object.hasOwn(catalogs, language)) language = "es";
  const normalize = (value) => value.trim().replace(/\s+/g, " ");
  const textNodes = [];
  const walker = document.createTreeWalker(
    document.documentElement,
    NodeFilter.SHOW_TEXT,
  );
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest("script, style")) continue;
    const key = normalize(node.textContent);
    if (Object.hasOwn(catalogs.es, key)) textNodes.push({ node, key });
  }
  const attributes = [];
  for (const element of document.querySelectorAll(
    "[placeholder], [aria-label]",
  )) {
    for (const attribute of ["placeholder", "aria-label"]) {
      const key = element.getAttribute(attribute);
      if (key && Object.hasOwn(catalogs.es, key))
        attributes.push({ element, attribute, key });
    }
  }
  function t(key, values = {}) {
    if (!key) return "";
    const template = Object.hasOwn(catalogs[language], key)
      ? catalogs[language][key]
      : key;
    return template.replace(
      /\{(\w+)\}/g,
      (match, name) => values[name] ?? match,
    );
  }
  function setLanguage(value) {
    language = Object.hasOwn(catalogs, value) ? value : "es";
    document.documentElement.lang = language;
    for (const { node, key } of textNodes) {
      // Keep text nodes intact so changing language preserves nested controls and SVGs.
      if (node.isConnected)
        node.textContent = node.textContent.replace(/\S[\s\S]*\S|\S/, t(key));
    }
    for (const { element, attribute, key } of attributes)
      element.setAttribute(attribute, t(key));
    try {
      localStorage.setItem("stickerfast-language", language);
    } catch {
      /* Optional storage. */
    }
  }
  setLanguage(language);
  return {
    t,
    setLanguage,
    get language() {
      return language;
    },
  };
})();
