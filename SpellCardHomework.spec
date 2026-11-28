# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.pyw'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets'), ('tools/ocr_ps.ps1', 'tools'), ('启动答题浏览器.bat', '.')],
    hiddenimports=['modules.whats_new', 'modules.settings_center', 'modules.usage_window',
                   'modules.single_instance', 'modules.update_ui', 'modules.update_download',
                   'modules.update_install', 'modules.shell_drag'],
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
    name='SpellCardHomework',
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
    version='installer/version_info.txt',
    icon=['assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpellCardHomework',
)
