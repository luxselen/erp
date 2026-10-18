# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('templates', 'templates'), ('app/static', 'app/static')]
binaries = []
hiddenimports = ['app', 'app.config', 'app.models', 'app.security', 'app.utils', 'app.ai', 'app.demo', 'app.blueprints.auth', 'app.blueprints.base', 'app.blueprints.sales', 'app.blueprints.purchase', 'app.blueprints.finance', 'app.blueprints.stock', 'app.blueprints.report', 'app.blueprints.invoice', 'app.blueprints.voucher', 'app.blueprints.advanced', 'app.blueprints.ai', 'app.blueprints.extras', 'openpyxl', 'openpyxl.workbook', 'openpyxl.reader.excel', 'webview', 'webview.platforms.edgechromium']
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('openpyxl')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ERP系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
