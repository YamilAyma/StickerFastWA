# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/yamilayma/Desktop/pruebas-herramientas/stickerswa-desktop/StickerFastWA/src/app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/yamilayma/Desktop/pruebas-herramientas/stickerswa-desktop/StickerFastWA/src/view', 'src/view'), ('C:/Users/yamilayma/Desktop/pruebas-herramientas/stickerswa-desktop/StickerFastWA/src/lang', 'src/lang'), ('C:/Users/yamilayma/Desktop/pruebas-herramientas/stickerswa-desktop/StickerFastWA/src/data', 'src/data'), ('C:/Users/yamilayma/Desktop/pruebas-herramientas/stickerswa-desktop/StickerFastWA/src/resources', 'src/resources')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StickerFastWA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StickerFastWA',
)
