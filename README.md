# StickerFast WA

<div align="center">

[![English Version](https://img.shields.io/badge/Language-English-blue.svg)](README.md)
[![Versión en Español](https://img.shields.io/badge/Idioma-Español-brightgreen.svg)](README_ES.md)

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
![GUI Framework](https://img.shields.io/badge/GUI-pywebview%20%2B%20PyQt5-green.svg)
![License](https://img.shields.io/badge/license-MIT-informational.svg)

**High-performance desktop application for batch creating, optimizing, and exporting static and animated sticker packs for WhatsApp.**

> [!NOTE]
> This project is an **active fork and continuation** of the original project created by [Felipe Gomez (@FelipeGCx)](https://github.com/FelipeGCx/StickerFastWA), modernized with complete Windows compatibility, batch video conversion, adaptive compression (< 500 KB), interactive visual preview, and portable standalone distribution.

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Project Origin & Acknowledgments](#-project-origin--acknowledgments)
- [Key Features](#-key-features)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Installation & Setup](#-installation--setup)
- [Usage Guide](#-usage-guide)
- [Build & Distribution](#-build--distribution)
- [Automated Testing](#-automated-testing)
- [Internationalization (i18n)](#-internationalization-i18n)

---

## 📌 Overview

**StickerFast WA** automates the conversion and packaging of image and video collections into ready-to-import sticker packs for WhatsApp via popular companion mobile apps: **Sticker Maker** (`.wastickers`) and **Wemoji** (`.wemojipack`).

The engine handles automated canvas fitting, resizing (512x512 px with rounded corners), transparent boundary auto-trimming, WebP conversion, video frame extraction and sampling, multi-level adaptive compression to guarantee WhatsApp's strict size constraints (< 500 KB per animated sticker), and package metadata generation including a 96x96 px tray icon.

---

## 🌱 Project Origin & Acknowledgments

This repository is an enhanced continuation and evolution of the original software:

- **Original Author**: [Felipe Gomez (@FelipeGCx)](https://github.com/FelipeGCx) — Base repository: [FelipeGCx/StickerFastWA](https://github.com/FelipeGCx/StickerFastWA).
- **Maintenance & Modernization (Fork)**: [Yamil Ayma (@YamilAyma)](https://github.com/YamilAyma/StickerFastWA).

### Enhancements & Contributions in this Fork:
| Area | Description |
| :--- | :--- |
| **Windows Compatibility** | Fixed OS folder opening (`os.startfile`), path separator normalization, and native file dialog filter compatibility in `pywebview`. |
| **Batch Video Processing** | Automated conversion of videos (`.mp4`, `.webm`, `.mov`, etc.) to animated WebP using OpenCV. |
| **Multi-Level Adaptive Compression** | Dynamic fallback system (frame-stepping & downscaling) to strictly enforce WhatsApp's 500 KB size ceiling. |
| **Aspect Ratio & Crop Modes** | Support for `1:1 Center-Crop` (square crop) and `Orig / Fit` (preserve original aspect ratio with transparency). |
| **Interactive Grid Preview** | Modal popup showing thumbnail previews of all detected images/video frames with checkboxes for selective file exclusion. |
| **Real-time UX & Control** | Real-time percentage progress bar `(X/Total)` and an instant cancellation trigger. |
| **Portable Distribution** | PyInstaller build script and spec (`build.py` / `StickerFastWA.spec`) for generating standalone distributables. |

---

## 🚀 Key Features

### 1. Multi-format & Batch Video Processing
- **Image Formats**: Supports `.png`, `.jpg`, `.jpeg`, `.webp` (static & animated), and `.gif`.
- **Batch Video Conversion**: Converts `.mp4`, `.webm`, `.mov`, `.avi`, and `.mkv` files directly into animated WebP stickers sampled at ~12 FPS (capped at 3–4 seconds).
- **Aspect Ratio & Crop Modes**:
  - `1:1 Center-Crop`: Exact square center cropping to keep the focal subject in frame.
  - `Orig / Fit`: Proportional fitting maintaining the original aspect ratio with transparent padding.

### 2. Multi-Level Adaptive Compression Guard
To strictly enforce WhatsApp's 500 KB limit for animated stickers:
- **Level 1 (Frame-Stepping)**: Halves the frame count while doubling per-frame duration.
- **Level 2 (Moderate Downscaling)**: Re-encodes frames downscaled to 384x384 px.
- **Level 3 (Aggressive Downscaling)**: Re-encodes frames downscaled to 256x256 px with 1/3 frame sampling for large inputs.

### 3. Interactive Preview & Selective File Exclusion
- Popup modal with a responsive thumbnail grid generated dynamically in Base64 (including video first-frame capture).
- Toggle individual checkboxes to exclude unwanted files from the final pack before compilation.

### 4. Real-time Progress & Immediate Cancellation
- Live progress feedback with percentage and completed count indicators `(X/Total)`.
- Non-blocking asynchronous cancellation support to abort processing midway safely.

### 5. Multiplatform Support
- Fully optimized for Windows (native dialogs, path sanitization, `os.startfile`) and Linux environments (`xdg-open`, GLib integration).

### 6. Modern & Customizable User Interface
- Frameless, translucent desktop window with smooth dragging and *Always-on-Top* mode.
- Built-in theme switcher: **Dark Mode** and **Light Mode**.
- User preferences persistence saved automatically to `src/data/user.json`.

---

## 🛠 Architecture & Tech Stack

```
┌────────────────────────────────────────────────────────┐
│               Frontend (UI / WebView)                  │
│       HTML5 • CSS3 (Variables & Glassmorphism) • JS    │
└───────────────────────────┬────────────────────────────┘
                            │ PyWebView JS-API Bridge
┌───────────────────────────▼────────────────────────────┐
│                    Entry Layer                         │
│                  src/app.py (PyQt5)                    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                   Logic Core Engine                    │
│                  src/logic/sfwa.py                     │
├────────────────────────────────────────────────────────┤
│ • Pillow / WebP (Image Transformation & Rendering)     │
│ • OpenCV cv2 (Video Sampling & Frame Extraction)       │
│ • Adaptive Compression (< 500 KB Guard Engine)         │
│ • ZIP Packager (.wastickers / .wemojipack)             │
└────────────────────────────────────────────────────────┘
```

### Technology Stack:
- **Core Runtime**: Python 3.10+
- **GUI Engine**: [pywebview](https://pywebview.flowrl.com/) + PyQt5 / PyQtWebEngine
- **Image Processing**: Pillow, webp, pygifsicle, NumPy
- **Video Processing**: OpenCV (`cv2`)
- **Serialization & Utilities**: Munch, PyAutoGUI, JSON, ZipFile

---

## 📂 Project Structure

```
StickerFastWA/
├── build.py                     # Standalone PyInstaller build script
├── StickerFastWA.spec           # PyInstaller bundle specification
├── requirements.txt             # Project runtime dependencies
├── README.md                    # English documentation
├── README_ES.md                 # Spanish documentation
├── src/
│   ├── app.py                   # App entrypoint and PyWebView JS-API bridge
│   ├── data/
│   │   └── user.json            # Persistent user settings (theme, language, folder)
│   ├── lang/                    # i18n localization JSON dictionaries
│   │   ├── en.json              # English
│   │   ├── es.json              # Spanish
│   │   ├── fr.json              # French
│   │   ├── de.json              # German
│   │   ├── it.json              # Italian
│   │   └── pt.json              # Portuguese
│   ├── logic/
│   │   ├── __init__.py
│   │   └── sfwa.py              # Central image/video processing and packaging engine
│   ├── resources/
│   │   ├── compressed/          # Base pack templates (.wastickers and .wemojipack)
│   │   ├── license/             # Legal documentation in 6 languages
│   │   └── terms/               # Terms of service in 6 languages
│   ├── tests/
│   │   ├── test_create.py       # Integration tests for pack creation
│   │   └── test_webp.py         # Format conversion unit tests
│   └── view/                    # Web-based UI assets
│       ├── index.html           # Main UI layout
│       ├── style.css            # Stylesheet (themes, animations, glassmorphism)
│       ├── main.js              # DOM handler and PyWebView bridge controller
│       └── assets/              # SVG icons and default graphics
```

---

## 📦 Prerequisites

- **Python**: Version 3.10 or higher.
- **Package Manager**: `pip`.
- *(Optional for video conversion)*: `opencv-python` (included in requirements).

---

## 🔧 Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/YamilAyma/StickerFastWA.git
   cd StickerFastWA
   ```

2. **Create and activate a virtual environment**:
   - **On Windows (PowerShell)**:
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - **On Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🖥 Usage Guide

### Running in Development Mode:
```bash
python src/app.py
```

### Pack Creation Workflow:
1. **Choose Target Format**: Select *Sticker Maker* (`.wastickers`) or *Wemoji* (`.wemojipack`).
2. **Enable Animated Mode**: Toggle the animated checkbox if your source directory contains GIFs, animated WebP, or video files.
3. **Fill in Metadata**: Enter the **Pack Name** (*Name Pack*) and **Author** (*Author*).
4. **Choose Crop Mode**: Select `1:1` for center square crop or `Orig` to fit the entire source frame.
5. **Select Source Directory**: Pick the folder containing your media files (up to 30 items per pack).
6. **Preview / Exclude Files (Optional)**: Click the eye icon to view the thumbnail grid modal and uncheck any files you wish to exclude.
7. **Select Tray Icon**: Choose an image to represent the pack icon.
8. **Generate Pack**: Click **CREAR PACK** and monitor the progress bar until completion.

---

## 🏗 Build & Distribution

To compile a standalone, portable desktop executable (no Python installation required for end users):

```bash
python build.py
```

The output application folder will be generated in:
```
dist/StickerFastWA/
```

---

## 🧪 Automated Testing

The repository includes end-to-end integration tests that use isolated temporary directories to validate the generation of valid `.wastickers` and `.wemojipack` archives:

```bash
# Run integration test suite
python src/tests/test_create.py
```

Or via `pytest`:
```bash
pytest src/tests/
```

---

## 🌐 Internationalization (i18n)

StickerFast WA includes native multi-language support for 6 languages:
- 🇺🇸 **English** (`en`)
- 🇪🇸 **Spanish** (`es`)
- 🇫🇷 **French** (`fr`)
- 🇩🇪 **German** (`de`)
- 🇮🇹 **Italian** (`it`)
- 🇧🇷 **Portuguese** (`pt`)

Languages can be switched dynamically in the in-app settings menu and are automatically persisted in user preferences.

---

<div align="center">
Built for seamless, optimized WhatsApp sticker pack generation.
</div>
