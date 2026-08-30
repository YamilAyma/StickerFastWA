# StickerFast WA

<div align="center">

[![English Version](https://img.shields.io/badge/Language-English-blue.svg)](README.md)
[![Versión en Español](https://img.shields.io/badge/Idioma-Español-brightgreen.svg)](README_ES.md)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
![GUI Framework](https://img.shields.io/badge/GUI-pywebview%20%2B%20PyQt5-green.svg)
![License](https://img.shields.io/badge/license-MIT-informational.svg)

**Aplicación de escritorio de alto rendimiento para la creación, optimización y exportación por lotes de paquetes de stickers estáticos y animados para WhatsApp.**

> [!NOTE]
> Este proyecto es un **fork y continuación activa** del desarrollo original creado por [Felipe Gomez (@FelipeGCx)](https://github.com/FelipeGCx/StickerFastWA), modernizado con soporte completo para Windows, conversión de video por lotes, compresión adaptativa (< 500 KB), previsualización interactiva y distribución portable.

</div>

---

## 📋 Tabla de Contenidos

- [Descripción General](#-descripción-general)
- [Origen y Reconocimientos](#-origen-y-reconocimientos)
- [Características Principales](#-características-principales)
- [Arquitectura y Tecnologías](#-arquitectura-y-tecnologías)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Uso de la Aplicación](#-uso-de-la-aplicación)
- [Compilación y Distribución](#-compilación-y-distribución)
- [Pruebas Automatizadas](#-pruebas-automatizadas)
- [Internacionalización (i18n)](#-internacionalización-i18n)

---

## 📌 Descripción General

**StickerFast WA** automatiza la transformación de colecciones de imágenes y videos en paquetes de stickers listos para importar en WhatsApp mediante las aplicaciones móviles **Sticker Maker** (`.wastickers`) y **Wemoji** (`.wemojipack`). 

La herramienta procesa automáticamente el recorte, redimensionado (512x512 px con esquinas redondeadas), recorte de bordes transparentes, conversión a WebP, extracción y muestreo de cuadros de video, compresión adaptativa multinivel para garantizar el límite de peso por sticker (< 500 KB) y la generación del archivo de metadatos e icono de bandeja (*tray icon* de 96x96 px).

---

## 🌱 Origen y Reconocimientos

Este repositorio es una continuación y evolución del software original:

- **Autor Original**: [Felipe Gomez (@FelipeGCx)](https://github.com/FelipeGCx) — Repositorio base: [FelipeGCx/StickerFastWA](https://github.com/FelipeGCx/StickerFastWA).
- **Mantenimiento y Evolución (Fork)**: [Yamil Ayma (@YamilAyma)](https://github.com/YamilAyma/StickerFastWA).

### Mejoras y Aportes en esta Continuación:
| Área | Implementación |
| :--- | :--- |
| **Compatibilidad Windows** | Corrección en llamadas a sistema (`os.startfile`), normalización de rutas y corrección de filtros de diálogos nativos en `pywebview`. |
| **Procesamiento de Video** | Conversión por lotes de videos (`.mp4`, `.webm`, `.mov`, etc.) a WebP animado con OpenCV. |
| **Compresión Adaptativa** | Sistema multinivel (*frame-stepping* y downscaling) para garantizar estrictamente el límite de 500 KB de WhatsApp. |
| **Modos de Recorte** | Soporte para recorte central `1:1` (*Center-Crop*) y ajuste proporcional `Orig` (*Fit*). |
| **Previsualización Interactiva** | Modal emergente con visualización en cuadrícula de miniaturas y selector de exclusión de archivos. |
| **UX & Control en Tiempo Real** | Barra de progreso porcentual y botón para cancelación inmediata del proceso. |
| **Distribución Portable** | Script y especificación PyInstaller (`build.py` / `StickerFastWA.spec`) para generar binarios independientes. |

---

## 🚀 Características Principales

### 1. Soporte Multiformato y Procesamiento de Video
- **Formatos de Imagen**: Soporte para `.png`, `.jpg`, `.jpeg`, `.webp` (estático y animado) y `.gif`.
- **Procesamiento de Video por Lotes**: Conversión directa de videos (`.mp4`, `.webm`, `.mov`, `.avi`, `.mkv`) a stickers animados WebP con muestreo inteligente de cuadros a ~12 FPS y límite temporal de 3–4 segundos.
- **Control de Recorte (*Crop Mode*)**:
  - `1:1 Center-Crop`: Recorte central cuadrado exacto para enfocar el área principal.
  - `Orig / Fit`: Ajuste proporcional manteniendo la relación de aspecto original con fondo transparente.

### 2. Algoritmo de Compresión Adaptativa Multinivel
Para asegurar compatibilidad estricta con las restricciones de WhatsApp (< 500 KB por sticker animado):
- **Nivel 1 (Frame-Stepping)**: Reducción del conteo de cuadros a la mitad ajustando proporcionalmente la duración por cuadro.
- **Nivel 2 (Downscaling Medio)**: Reescalado automático a resolución 384x384 px.
- **Nivel 3 (Downscaling Agresivo)**: Reescalado a resolución 256x256 px con muestreo reducido (1/3 de cuadros) para animaciones pesadas.

### 3. Previsualización Interactiva y Exclusión Selectiva
- Modal emergente con visualización en cuadrícula (*grid preview*) de miniaturas generadas dinámicamente en Base64 (incluyendo primer cuadro representativo de videos).
- Selección/deselección de archivos individuales para excluirlos selectivamente del paquete final antes de la compilación.

### 4. Barra de Progreso y Cancelación en Tiempo Real
- Monitorización del progreso porcentual y conteo de archivos procesados `(X/Total)`.
- Indicador visual y botón de cancelación inmediata del hilo de procesamiento.

### 5. Compatibilidad Multiplataforma Optimizada
- Soporte nativo para Windows (`os.startfile`, normalización de rutas POSIX/Windows, diálogos nativos de archivo sin congelamiento) y entornos Linux (`xdg-open`, integración GLib).

### 6. Interfaz Moderna y Personalizable
- Ventana compacta *frameless* con transparencia, arrastre fluido y modo *Always-on-Top*.
- Sistema de temas integrado: **Modo Oscuro** (*Dark Mode*) y **Modo Claro** (*Light Mode*).
- Persistencia de preferencias del usuario en formato JSON (`src/data/user.json`).

---

## 🛠 Arquitectura y Tecnologías

```
┌────────────────────────────────────────────────────────┐
│               Frontend (UI / WebView)                  │
│       HTML5 • CSS3 (Variables & Glassmorphism) • JS    │
└───────────────────────────┬────────────────────────────┘
                            │ PyWebView JS-API Bridge
┌───────────────────────────▼────────────────────────────┐
│                    Capa de Entrada                     │
│                  src/app.py (PyQt5)                    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                   Motor de Lógica                      │
│                  src/logic/sfwa.py                     │
├────────────────────────────────────────────────────────┤
│ • Pillow / WebP (Transformación & Renderizado)         │
│ • OpenCV cv2 (Muestreo y Procesamiento de Video)       │
│ • Compresión Adaptativa (< 500 KB Guard)               │
│ • Empaquetador ZIP (.wastickers / .wemojipack)         │
└────────────────────────────────────────────────────────┘
```

### Stack Tecnológico:
- **Lenguaje Base**: Python 3.10+
- **Motor de GUI**: [pywebview](https://pywebview.flowrl.com/) + PyQt5 / PyQtWebEngine
- **Procesamiento de Imagen**: Pillow, webp, pygifsicle, NumPy
- **Procesamiento de Video**: OpenCV (`cv2`)
- **Serialización & Utilidades**: Munch, PyAutoGUI, JSON, ZipFile

---

## 📂 Estructura del Proyecto

```
StickerFastWA/
├── build.py                     # Script de compilación con PyInstaller
├── StickerFastWA.spec           # Especificación de build para ejecutable portable
├── requirements.txt             # Dependencias del proyecto
├── src/
│   ├── app.py                   # Punto de entrada de la aplicación y puente PyWebView API
│   ├── data/
│   │   └── user.json            # Preferencias persistentes del usuario (tema, idioma, etc.)
│   ├── lang/                    # Archivos de localización i18n
│   │   ├── es.json              # Español
│   │   ├── en.json              # Inglés
│   │   ├── fr.json              # Francés
│   │   ├── de.json              # Alemán
│   │   ├── it.json              # Italiano
│   │   └── pt.json              # Portugués
│   ├── logic/
│   │   ├── __init__.py
│   │   └── sfwa.py              # Motor central de procesamiento y lógica de empaquetado
│   ├── resources/
│   │   ├── compressed/          # Plantillas base (.wastickers y .wemojipack)
│   │   ├── license/             # Documentación legal en múltiples idiomas
│   │   └── terms/               # Términos de uso en múltiples idiomas
│   ├── tests/
│   │   ├── test_create.py       # Pruebas de integración para generación de packs
│   │   └── test_webp.py         # Pruebas de conversión de formato WebP
│   └── view/                    # Interfaz gráfica web
│       ├── index.html           # Estructura del maquetado
│       ├── style.css            # Hoja de estilos (temas, animaciones, responsive)
│       ├── main.js              # Controlador del DOM y llamadas a pywebview API
│       └── assets/              # Iconografía SVG e imágenes base
```

---

## 📦 Requisitos Previos

- **Python**: Versión 3.10 o superior.
- **Gestor de paquetes**: `pip`.
- *(Opcional para procesamiento de video)*: `opencv-python` (incluido en dependencias).

---

## 🔧 Instalación y Configuración

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/YamilAyma/StickerFastWA.git
   cd StickerFastWA
   ```

2. **Crear y activar un entorno virtual**:
   - **En Windows (PowerShell)**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - **En Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🖥 Uso de la Aplicación

### Ejecución en Modo Desarrollo:
```bash
python src/app.py
```

### Flujo de Creación de un Paquete:
1. **Seleccionar Formato de Destino**: Escoger entre *Sticker Maker* (`.wastickers`) o *Wemoji* (`.wemojipack`).
2. **Definir Modo de Animación**: Activar la casilla de animación si el lote contiene GIFs, WebP animados o archivos de video.
3. **Completar Metadatos**: Ingresar el **Nombre del Paquete** (*Name Pack*) y el **Nombre del Autor** (*Author*).
4. **Seleccionar Modo de Recorte**: Elegir entre recorte central `1:1` o ajuste proporcional `Orig`.
5. **Seleccionar Directorio de Origen**: Indicar la carpeta donde residen las imágenes o videos (máximo 30 elementos por paquete).
6. **Previsualizar / Excluir Elementos (Opcional)**: Hacer clic en el icono de ojo para abrir el modal de previsualización y desmarcar elementos no deseados.
7. **Seleccionar Icono del Paquete**: Escoger una imagen de portada (*Tray Icon*).
8. **Generar Paquete**: Presionar el botón **CREAR PACK** y esperar a que la barra de progreso complete el 100%.

---

## 🏗 Compilación y Distribución

Para generar un ejecutable portable independiente (sin necesidad de tener Python instalado):

```bash
python build.py
```

El binario y los recursos empaquetados se generarán en el directorio:
```
dist/StickerFastWA/
```

---

## 🧪 Pruebas Automatizadas

El proyecto incluye tests de integración que crean entornos temporales aislados para validar la generación correcta de paquetes `.wastickers` y `.wemojipack`:

```bash
# Ejecutar suite de pruebas
python src/tests/test_create.py
```

O utilizando `pytest`:
```bash
pytest src/tests/
```

---

## 🌐 Internacionalización (i18n)

StickerFast WA cuenta con soporte nativo para 6 idiomas:
- 🇪🇸 **Español** (`es`)
- 🇺🇸 **Inglés** (`en`)
- 🇫🇷 **Francés** (`fr`)
- 🇩🇪 **Alemán** (`de`)
- 🇮🇹 **Italiano** (`it`)
- 🇧🇷 **Portugués** (`pt`)

El idioma se puede alternar en tiempo real desde la sección de configuración de la aplicación y se almacena automáticamente en las preferencias del usuario.

---

<div align="center">
Desarrollado para la optimización y creación ágil de stickers en WhatsApp.
</div>
