# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for Deadlock Draft Viewer.

Build with:
    python build.py
(which invokes `pyinstaller DeadlockDraftViewer.spec` and then copies the
`assets/` folder into the output -- see build.py for why that's a separate
step instead of a PyInstaller `datas` entry.)

Or directly:
    pyinstaller --noconfirm --clean DeadlockDraftViewer.spec

IMPORTANT: this uses the onedir layout (EXE + COLLECT), not --onefile.
--onefile re-extracts its bundle to a volatile temp directory on every
launch, which would silently discard any user edits to shipped assets.
onedir produces a persistent folder, which is what we want.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = Path(SPECPATH)
APP_NAME = "DeadlockDraftViewer"

block_cipher = None

# pynput selects its platform backend (e.g. pynput.keyboard._darwin) via a
# dynamically *computed* importlib.import_module() call -- PyInstaller's
# static analysis can't see that, so the backend module (and, on macOS, the
# pyobjc framework packages it imports) can silently go missing from the
# build. Force-collect them explicitly. The pyobjc packages only exist on
# macOS, so this is skipped harmlessly on other build platforms.
datas = []
binaries = []
hiddenimports = ["tkinter", "tkinter.filedialog"]

_force_collect = ["pynput"]
if sys.platform == "darwin":
    _force_collect += ["objc", "Quartz", "AppKit", "Foundation", "HIServices"]

for _pkg in _force_collect:
    try:
        _datas, _binaries, _hiddenimports = collect_all(_pkg)
    except Exception:
        continue
    datas += _datas
    binaries += _binaries
    hiddenimports += _hiddenimports

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    # `datas` here only holds pynput/pyobjc package data collected above.
    # The app's own `assets/` folder is deliberately excluded: build.py
    # copies it alongside the exe instead, so it stays a plain,
    # user-editable directory rather than being packed into PyInstaller's
    # internal archive.
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
