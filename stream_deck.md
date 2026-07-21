# Stream Deck Integration

## Overview

A Stream Deck can replace (or supplement) the keyboard keybinds used to trigger
hero picks and bans, and can reflect the live draft state back onto its LCD
buttons in real time — showing hero icons, highlighting whose turn it is, and
locking buttons visually when input is blocked.

---

## Python Library

The official community Python library is **`streamdeck`** by Dean Camera.

```
pip install streamdeck
```

It communicates over USB HID (no official Elgato SDK needed) and supports all
current Stream Deck hardware generations.  It also requires the `hidapi` native
library, which on Windows ships as a DLL and is typically included automatically
by the package installer.

---

## How Buttons Map to Heroes

The current application maps `HERO_REGISTRY` entries to keyboard combos:

```python
# heroes.py
HERO_REGISTRY = [
    ("shift+1", "abrams", 0.8),
    ("shift+2", "apollo", 0.8),
    ...
]
```

For the Stream Deck, each hero would instead map to a **button index** — the
physical position on the deck.  A natural extension would be to add an optional
fourth field:

```python
HERO_REGISTRY = [
    ("shift+1", "abrams", 0.8, 0),   # Stream Deck button 0
    ("shift+2", "apollo", 0.8, 1),   # Stream Deck button 1
    ...
]
```

If the fourth field is absent or `None`, only the keyboard combo is registered.
Both input methods can remain active simultaneously so the operator can use
whichever is convenient.

---

## Button Icons

Each Stream Deck model has an LCD grid; the most common (15-key) renders each
button at **72×72 pixels** (older models) or **96×96 pixels** (newer MK.2+).

Each hero already has an `icon.png` asset at `assets/heroes/<name>/icon.png`.
These images would need to be resized and converted to the `PIL.Image` format
expected by the `streamdeck` library:

```python
from PIL import Image
from StreamDeck.ImageHelpers import PILHelper

def hero_button_image(deck, hero):
    icon = Image.open(str(hero.icon)).convert("RGB")
    return PILHelper.create_scaled_key_image(deck, icon, margins=[4, 4, 4, 4])
```

---

## Integration Architecture

### Initialisation

A `StreamDeckManager` class (new file `stream_deck_manager.py`) would:

1. Enumerate connected decks via `DeviceManager().enumerate()`.
2. Open the first available deck.
3. Register a `key_change_callback` that mirrors the existing `activate_hero()`
   flow — it sets `pending_hero` just as the keyboard listener does, so the
   rest of the application logic is unchanged.
4. Push icon images to each button for every registered hero.

```python
from StreamDeck.DeviceManager import DeviceManager

class StreamDeckManager:
    def __init__(self, hero_registry):
        devices = DeviceManager().enumerate()
        if not devices:
            return
        self.deck = devices[0]
        self.deck.open()
        self.deck.set_key_callback(self._on_key_change)
        self._load_icons(hero_registry)

    def _on_key_change(self, deck, key_index, state):
        if state:  # button pressed (not released)
            hero = self._key_to_hero.get(key_index)
            if hero:
                activate_hero(hero)   # same function as keyboard path

    def update(self, draft_state):
        # Refresh button visuals to reflect current lock / pick / ban state
        ...

    def close(self):
        if self.deck:
            self.deck.close()
```

The `key_change_callback` runs in the `streamdeck` library's own thread, which
is safe because `activate_hero()` only writes to `pending_hero` (a simple
global assignment, protected by Python's GIL), identical to the `pynput`
listener thread already in use.

### Per-frame visual updates

`StreamDeckManager.update(draft_state)` would be called once per frame from the
main loop (alongside `status_window.update()`).  It would apply visual overlays
to each button to communicate draft state:

| Condition | Visual treatment |
|---|---|
| Hero already picked or banned | Dimmed / greyed icon |
| Hero available, not current turn | Normal icon |
| Input locked (voice line playing) | Red border overlay on all buttons |
| Current turn team's hero buttons | Green/blue border highlight |
| Draft complete | All buttons dim |

These overlays can be composited in Python using `PIL.ImageDraw` before pushing
the final image to the deck.

---

## Threading Model

The integration fits naturally into the existing threading model:

```
Main thread (pygame loop)
    ├── pynput listener thread  →  sets pending_hero
    ├── streamdeck callback thread  →  sets pending_hero
    └── tkinter (status_window.root.update() each frame)
```

Both input sources write to the same `pending_hero` variable and the main loop
consumes it once per frame — no additional synchronisation is needed.

---

## Files to Add / Modify

| File | Change |
|---|---|
| `stream_deck_manager.py` | New file — `StreamDeckManager` class |
| `heroes.py` | Add optional button-index field to `HERO_REGISTRY` entries |
| `main.py` | Instantiate `StreamDeckManager` after hero loading; call `stream_deck_manager.update(...)` each frame; call `stream_deck_manager.close()` in the `finally` block |
| `requirements.txt` | Add `streamdeck` and `Pillow` |

---

## Hardware Notes

- The `streamdeck` library supports the **Stream Deck Original** (15 keys),
  **Mini** (6 keys), **XL** (32 keys), and **Plus** models.
- With 15 keys on the Original, the current 16-hero draft roster would require
  paging or a 2-page layout (page 1 = heroes 1–15, page 2 = hero 16 + utility
  buttons such as undo or reset).
- The **XL** (32 keys) can fit the full 16-hero roster with room for utility
  buttons on a single page, making it the most comfortable choice for this
  use case.
