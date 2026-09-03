"""Native file-open dialog that avoids a pygame/tkinter crash on macOS.

pygame (SDL) and tkinter each try to install their own NSApplication
subclass as the shared macOS application object. Creating a tkinter window
in the same process as an already-initialised pygame display raises
'NSInvalidArgumentException: unrecognized selector ... macOSVersion' and
aborts the whole process. Running the tkinter dialog in a short-lived,
isolated subprocess sidesteps the conflict entirely, on every platform.
"""
import subprocess
import sys

INTERNAL_FLAG = "--internal-file-dialog"


def ask_open_json(title: str = "Select Draft JSON"):
    """
    Show a native 'open file' dialog filtered to JSON files, in an isolated
    subprocess so it never shares a process with pygame.

    Returns the selected path, or None if the user cancelled or the dialog
    could not be shown.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller build: sys.executable *is* our own app, not a plain
        # Python interpreter. Re-invoke it with a hidden flag so it only
        # runs the dialog and exits, instead of relaunching the whole
        # application. main.py's entry point checks for this flag and
        # calls run_internal_dialog().
        cmd = [sys.executable, INTERNAL_FLAG, title]
    else:
        cmd = [sys.executable, __file__, INTERNAL_FLAG, title]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        print(f"Failed to open file dialog: {e}")
        return None

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(f"File dialog error: {stderr or 'unknown error'}")
        return None

    path = result.stdout.strip()
    return path or None


def run_internal_dialog(title: str) -> None:
    """Runs inside the isolated subprocess: show the dialog, print the path."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    path = filedialog.askopenfilename(
        title=title,
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()
    sys.stdout.write(path)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == INTERNAL_FLAG:
        run_internal_dialog(sys.argv[2])
    else:
        sys.stderr.write("file_dialog.py is not meant to be run directly.\n")
        sys.exit(1)
