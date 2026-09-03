#!/usr/bin/env python3
"""
Build a distributable, onedir PyInstaller build of Deadlock Draft Viewer.

Usage:
    pip install -r requirements-dev.txt
    python build.py

Produces:
    dist/DeadlockDraftViewer/
        DeadlockDraftViewer.exe   (or platform equivalent)
        _internal/...             PyInstaller runtime + bundled libraries
        assets/                   plain files, copied here (NOT bundled by
                                   PyInstaller) so a user can open the
                                   install folder and edit hero images,
                                   voice lines, etc. directly -- changes
                                   take effect the next time the app starts.

After this, feed dist/DeadlockDraftViewer/ to Inno Setup
(installer/installer.iss) to produce a Windows installer.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "DeadlockDraftViewer"
DIST_DIR = ROOT / "dist" / APP_NAME
SPEC_FILE = ROOT / f"{APP_NAME}.spec"


def main() -> None:
    if not SPEC_FILE.exists():
        sys.exit(f"Spec file not found: {SPEC_FILE}")

    print(f"Running PyInstaller ({SPEC_FILE.name})...")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)],
        cwd=ROOT,
        check=True,
    )

    if not DIST_DIR.exists():
        sys.exit(f"Expected PyInstaller output not found: {DIST_DIR}")

    assets_src = ROOT / "assets"
    assets_dst = DIST_DIR / "assets"
    print(f"Copying assets: {assets_src} -> {assets_dst}")
    if assets_dst.exists():
        shutil.rmtree(assets_dst)
    shutil.copytree(assets_src, assets_dst)

    print(f"\nBuild complete: {DIST_DIR}")
    print("Users can edit files under its 'assets' subfolder directly;")
    print("changes take effect the next time the app is launched.")
    print("\nNext: compile installer/installer.iss with Inno Setup (on")
    print("Windows) to produce a distributable installer.")


if __name__ == "__main__":
    main()
