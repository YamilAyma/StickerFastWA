#!/usr/bin/env bash
cd -- "$(dirname -- "$0")" || exit 1
if ! command -v python3 >/dev/null; then
  echo 'Instala Python 3.10 o posterior desde python.org y vuelve a abrir este lanzador.'
  read -r -p 'Pulsa Enter para cerrar.'
  exit 1
fi
if ! python3 start_web.py "$@"; then
  read -r -p 'No se pudo iniciar. Pulsa Enter para cerrar.'
  exit 1
fi
