"""Workaround for a macOS crash when starting a pynput keyboard.Listener.

pynput's Darwin backend resolves the current keyboard layout via HIToolbox's
Text Input Source Manager (TISCopyCurrentKeyboardInputSource /
TISGetInputSourceProperty) once, when the listener's background thread
starts (pynput._util.darwin.keycode_context(), invoked from
pynput.keyboard.Listener._run(), which pynput always runs on a dedicated
thread rather than the main thread).

Recent macOS versions (observed on macOS 26 "Tahoe") assert that these TSM
calls happen on the main dispatch queue. Calling them from the listener's
own thread aborts the whole process with 'dispatch_assert_queue_fail'
(EXC_BREAKPOINT / SIGTRAP) -- this is a pynput bug, not specific to this
app; see e.g. https://github.com/moses-palmer/pynput/issues/511.

Fix: capture the keyboard layout context once, from the main thread, before
pynput ever starts a listener thread, then monkeypatch pynput so it reuses
that cached context instead of re-querying TIS off the main thread.
"""
import contextlib
import sys
import threading

_applied = False


def apply() -> None:
    """Install the workaround. Safe to call on any platform or thread --
    it is a no-op everywhere except macOS, and only takes effect when
    called from the main thread (which is also the only place it's safe
    to query the keyboard layout in the first place).

    Must be called before the first pynput.keyboard.Listener is started.
    """
    global _applied
    if _applied or sys.platform != "darwin":
        return
    if threading.current_thread() is not threading.main_thread():
        return

    try:
        from pynput._util import darwin as pynput_util_darwin
    except Exception:
        return

    try:
        with pynput_util_darwin.keycode_context() as context:
            cached_context = context
    except Exception:
        return

    @contextlib.contextmanager
    def _cached_keycode_context():
        yield cached_context

    # pynput.keyboard._darwin imports keycode_context by name at module load
    # time, so it has its own reference independent of the one on
    # pynput._util.darwin. Patch both so every caller picks up the cache.
    pynput_util_darwin.keycode_context = _cached_keycode_context
    try:
        from pynput.keyboard import _darwin as pynput_kbd_darwin
        pynput_kbd_darwin.keycode_context = _cached_keycode_context
    except Exception:
        pass

    _applied = True
