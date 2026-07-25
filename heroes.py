# ---------------------------------------------------------------------------
# Hero roster
# ---------------------------------------------------------------------------
# Add a new hero by appending one entry:
#   (keybind_combo, folder_name, volume)
#
# keybind_combo : any combo understood by KeybindManager ("shift+1", "ctrl+a", …)
# folder_name   : must match the directory under assets/heroes/
# volume        : voice line playback volume, 0.0 – 1.0
# ---------------------------------------------------------------------------

# Maps JSON/API display names to internal folder names where they differ.
# Keys must be lowercased. Extend this when new mismatches are found.
HERO_NAME_ALIASES = {
    "lady geist":  "geist",
    "mo & krill":  "mo_krill",
    "mo and krill": "mo_krill",
    "the doorman": "doorman",
    "vyper":       "viper",
}


def resolve_hero_name(display_name: str) -> str:
    """Convert a JSON display name to the internal folder name used by hero_map."""
    key = display_name.lower()
    if key in HERO_NAME_ALIASES:
        return HERO_NAME_ALIASES[key]
    return key.replace(" ", "_")


HERO_REGISTRY = [
    ("shift+1", "abrams", 0.8),
    ("shift+2", "apollo", 0.8),
    ("shift+3", "bebop",  0.8),
    ("shift+4", "billy",  0.8),
    ("shift+5", "calico", 0.8),
    ("shift+6", "celeste", 0.8),
    ("shift+7", "doorman", 0.8),
    ("shift+8", "drifter", 0.8),
    ("shift+9", "dynamo", 0.8),
    ("shift+0", "graves", 0.8),
    ("ctrl+1", "grey_talon", 0.8),
    ("ctrl+2", "haze", 0.8),
    ("ctrl+3", "holliday", 0.8),
    ("ctrl+4", "infernus", 0.8),
    ("ctrl+5", "ivy", 0.8),
    ("ctrl+6", "kelvin", 0.8),
    ("ctrl+7", "geist", 0.8),
    ("ctrl+8", "lash", 0.8),
    ("ctrl+9", "mcginnis", 0.8),
    ("ctrl+0", "mina", 0.8),
    ("alt+1", "mirage", 0.8),
    ("alt+2", "mo_krill", 0.8),
    ("alt+3", "paige", 0.8),
    ("alt+4", "paradox", 0.8),
    ("alt+5", "pocket", 0.8),
    ("alt+6", "rem", 0.8),
    ("alt+7", "seven", 0.8),
    ("alt+8", "shiv", 0.8),
    ("alt+9", "silver", 0.8),
    ("alt+0", "sinclair", 0.8),
    ("ctrl+alt+1", "venator", 0.8),
    ("ctrl+alt+2", "victor", 0.8),
    ("ctrl+alt+3", "vindicta", 0.8),
    ("ctrl+alt+4", "viscous", 0.8),
    ("ctrl+alt+5", "viper", 0.8),
    ("ctrl+alt+6", "warden", 0.8),
    ("ctrl+alt+7", "wraith", 0.8),
    ("ctrl+alt+8", "yamato", 0.8),
]
