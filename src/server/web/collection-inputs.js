"use strict";
window.CollectionInputs = {
  async expand(incoming, api, existing) {
    const { t } = window.I18n;
    const files = [],
      warnings = [];
    let total = existing.reduce((sum, entry) => sum + entry.file.size, 0);
    for (const file of incoming) {
      if (!/\.zip$/i.test(file.name)) {
        files.push(file);
        total += file.size;
        continue;
      }
      if (file.size > 100 * 1024 * 1024)
        throw new Error(t("El ZIP supera los 100 MB."));
      const body = new FormData();
      body.append("file", file);
      const response = await api("/api/imports", {
        method: "POST",
        body,
        signal: AbortSignal.timeout(120000),
      });
      try {
        if (existing.length + files.length + response.files.length > 300)
          throw new Error(t("Puedes añadir hasta 300 archivos."));
        if (
          total + response.files.reduce((sum, item) => sum + item.size, 0) >
          250 * 1024 * 1024
        )
          throw new Error(t("La colección supera los 250 MB."));
        for (let start = 0; start < response.files.length; start += 6) {
          const batch = await Promise.all(
            response.files.slice(start, start + 6).map(async (item, index) => {
              const data = await fetch(item.url, {
                signal: AbortSignal.timeout(30000),
              });
              if (!data.ok) throw new Error(t("No se pudo importar el ZIP."));
              const blob = await data.blob();
              return new File(
                [blob],
                file.name.replace(/\.zip$/i, "") + "/" + item.name,
                { lastModified: file.lastModified + start + index },
              );
            }),
          );
          files.push(...batch);
        }
        total += response.files.reduce((sum, item) => sum + item.size, 0);
        if (response.ignored)
          warnings.push(
            t("Se omitieron {count} archivos no compatibles del ZIP.", {
              count: response.ignored,
            }),
          );
      } finally {
        await api(`/api/imports/${response.id}`, { method: "DELETE" }).catch(
          () => {},
        );
      }
    }
    return { files, warnings };
  },
};
