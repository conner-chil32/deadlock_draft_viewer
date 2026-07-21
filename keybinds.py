# Maps base digit/symbol keys to their shifted character on a US keyboard layout.
# Used because pynput delivers the OS-resolved character, so Shift+1 arrives as "!".
SHIFT_MAP = {
    '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')',
    '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
    ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
    '`': '~',
}

# All pynput key identifiers that belong to each modifier family.
MODIFIER_FAMILIES = {
    'shift': {'shift', 'shift_l', 'shift_r'},
    'ctrl':  {'ctrl',  'ctrl_l',  'ctrl_r'},
    'alt':   {'alt',   'alt_l',   'alt_r'},
    'cmd':   {'cmd',   'cmd_l',   'cmd_r'},
}


class KeybindManager:
    """
    Manages arbitrary keyboard combos and fires registered callbacks.

    Combos are specified as human-readable strings such as:
        "shift+1"       "ctrl+a"        "alt+f4"
        "ctrl+shift+z"  "space"         "shift+tab"

    Modifiers recognised: shift, ctrl, alt, cmd.
    Only one non-modifier key per combo is supported.
    """

    def __init__(self):
        # label -> (frozenset[modifier_families], trigger_key, callback, raw_combo)
        self._bindings: dict = {}
        # All pynput key identifiers currently held down.
        self._held: set = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, combo: str, callback, label: str = None) -> None:
        """
        Register a callback for a key combo.

        Args:
            combo:    Human-readable combo string, e.g. "shift+1", "ctrl+a".
            callback: Callable invoked (with no arguments) when the combo fires.
            label:    Optional unique label; defaults to the combo string itself.
                      Re-using a label overwrites the previous binding for that label.
        """
        mod_families, trigger_key = self._parse_combo(combo)
        self._bindings[label or combo] = (mod_families, trigger_key, callback, combo)

    def on_press(self, key) -> str:
        """
        Process a pynput key-press event.

        Updates held-key state, checks all registered bindings, and fires
        any callbacks whose combo is fully satisfied.

        Returns:
            Normalised key identifier string (suitable for console logging).
        """
        identifier = self._normalize(key)
        self._held.add(identifier)

        for _label, (mod_families, trigger_key, callback, combo) in self._bindings.items():
            if identifier == trigger_key:
                if all(self._modifier_held(m) for m in mod_families):
                    print(f"Keybind '{combo}' triggered")
                    callback()

        return identifier

    def on_release(self, key) -> str:
        """
        Process a pynput key-release event.

        Returns:
            Normalised key identifier string.
        """
        identifier = self._normalize(key)
        self._held.discard(identifier)
        return identifier

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_combo(self, combo: str):
        """
        Parse a combo string into (frozenset[modifier_families], trigger_key).

        Resolves shifted digit/symbol keys automatically via SHIFT_MAP so
        that "shift+1" correctly matches the "!" character pynput delivers.
        """
        parts = [p.strip().lower() for p in combo.split('+')]
        mod_families = set()
        keys = []

        for part in parts:
            if part in MODIFIER_FAMILIES:
                mod_families.add(part)
            else:
                keys.append(part)

        if not keys:
            raise ValueError(f"Combo has no non-modifier key: '{combo}'")
        if len(keys) > 1:
            raise ValueError(
                f"Combo '{combo}' has multiple non-modifier keys. "
                "Only one non-modifier key per combo is supported."
            )

        key = keys[0]

        # pynput delivers the OS-shifted character for digit/symbol keys,
        # so resolve "1" -> "!" when shift is required.
        if 'shift' in mod_families and key in SHIFT_MAP:
            key = SHIFT_MAP[key]

        return frozenset(mod_families), key

    def _modifier_held(self, family: str) -> bool:
        """Return True if any pynput key in the given modifier family is held."""
        return bool(self._held & MODIFIER_FAMILIES[family])

    @staticmethod
    def _normalize(key) -> str:
        """Return a consistent lowercase string identifier for a pynput key."""
        if hasattr(key, 'char') and key.char is not None:
            return key.char.lower()
        if hasattr(key, 'name'):
            return key.name
        return str(key)
