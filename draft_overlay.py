import pygame
try:
    from pygame._sdl2 import video as _sdl2_video
    _SDL2_AVAILABLE = True
except ImportError:
    _SDL2_AVAILABLE = False

from draft import DraftSlots
from hero import resource_path

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
SLOT_W          = 130
SLOT_H          = 180
PICKS_PER_TEAM  = DraftSlots.NUM_PICKS   # 6
BANS_PER_TEAM   = DraftSlots.NUM_BANS    # 2
COLS            = PICKS_PER_TEAM + BANS_PER_TEAM  # 8 per row
ROWS            = 2                               # one row per team

TRANSPARENT_COLOR = (255, 0, 255)   # Magenta chroma key
SOLID_COLOR       = (0,   0,   0)   # Black solid background

# How long the gloat image is shown before switching to the card portrait.
GLOAT_DURATION_MS = 2000


class DraftOverlayWindow:
    """
    Secondary pygame window showing the 16 draft slots as hero portrait tiles.

    Layout (two rows of eight):
        [P1][P2][P3][P4][P5][P6][B1][B2]   <- Team 1
        [P1][P2][P3][P4][P5][P6][B1][B2]   <- Team 2

    Pick slots : hero's gloat image for GLOAT_DURATION_MS, then card.
    Ban slots  : hero's crit image (permanent).
    Background : follows the same chroma-key / solid toggle as the main window.
    """

    WIN_TITLE = "Draft Overlay"

    def __init__(self):
        if not _SDL2_AVAILABLE:
            raise RuntimeError(
                "pygame._sdl2.video is not available. Make sure you are using pygame 2.x."
            )

        w = COLS * SLOT_W
        h = ROWS * SLOT_H

        self._window   = _sdl2_video.Window(self.WIN_TITLE, size=(w, h))
        self._renderer = _sdl2_video.Renderer(self._window)

        try:
            icon_surf = pygame.image.load(str(resource_path("assets/heroes/abrams/icon.png")))
            self._window.set_icon(icon_surf)
        except Exception:
            pass

        # slot_key (team, slot_type, slot_idx) -> ticks when hero first appeared
        self._slot_first_seen: dict = {}

        # hero.name -> {"card": Texture|None, "gloat": Texture|None, "crit": Texture|None}
        # Also stores the scaled size so we can centre the image in the slot.
        self._tex_cache: dict = {}

        # Track when the render phase started so gloat matches render duration.
        self._render_started_at: int  = 0
        self._was_render:        bool = False

        # team -> whether that team's hero card images are horizontally
        # mirrored (picks and bans alike). ArchMother (team 2) defaults on.
        self.flip_team = {1: False, 2: True}

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _load_images(self, hero) -> None:
        """Load, scale, and cache Textures for a hero's card, gloat, and crit."""
        if hero.name in self._tex_cache:
            return

        def _texture(asset_type):
            try:
                raw    = pygame.image.load(str(hero.get_asset(asset_type))).convert_alpha()
                scale  = min(SLOT_W / raw.get_width(), SLOT_H / raw.get_height())
                size   = (int(raw.get_width() * scale), int(raw.get_height() * scale))
                scaled = pygame.transform.smoothscale(raw, size)
                tex    = _sdl2_video.Texture.from_surface(self._renderer, scaled)
                return tex, size
            except Exception:
                return None, (0, 0)

        self._tex_cache[hero.name] = {
            k: _texture(k) for k in ("card", "gloat", "crit")
        }

    def _blit(self, tex_entry, cx: int, cy: int, flip: bool = False) -> None:
        """Draw a (Texture, size) entry centred on (cx, cy), optionally
        mirrored horizontally."""
        tex, (w, h) = tex_entry
        if tex is None:
            return
        dest = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        tex.draw(dstrect=dest, flip_x=flip)

    def set_flip(self, team: int, flipped: bool) -> None:
        """Set whether a team's hero card images (picks and bans) are
        horizontally mirrored."""
        self.flip_team[team] = flipped

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, now: int, slots, hero_map: dict,
               solid_background: bool, display_state: str = "idle") -> None:
        """Draw all 16 slots and present the renderer. Call once per frame.

        display_state: the main window's current display state.
                       Gloat is shown on the most-recently-filled pick slot
                       exactly while display_state == 'render', so both
                       windows transition from gloat/render to card together.
        """
        bg = SOLID_COLOR if solid_background else TRANSPARENT_COLOR
        self._renderer.draw_color = (*bg, 255)
        self._renderer.clear()

        is_render = display_state == "render"

        # Record when the render phase starts so we can ignore pick slots
        # that were filled in earlier rounds (prevents gloat flash).
        if is_render and not self._was_render:
            self._render_started_at = now
        self._was_render = is_render

        for team, picks, bans in [
            (1, slots.team1_picks, slots.team1_bans),
            (2, slots.team2_picks, slots.team2_bans),
        ]:
            row = 0 if team == 1 else 1
            cy  = row * SLOT_H + SLOT_H // 2
            flip = self.flip_team.get(team, False)

            # ---- Pick slots ----
            for idx, hero_name in enumerate(picks):
                cx = idx * SLOT_W + SLOT_W // 2
                if hero_name and hero_name in hero_map:
                    hero = hero_map[hero_name]
                    self._load_images(hero)
                    key = (team, "pick", idx)
                    if key not in self._slot_first_seen:
                        self._slot_first_seen[key] = now
                    # Gloat only while render is active AND this slot was
                    # filled during the current render session.
                    show_gloat = (
                        is_render
                        and self._slot_first_seen[key] >= self._render_started_at
                    )
                    img_type = "gloat" if show_gloat else "card"
                    entry = self._tex_cache[hero.name][img_type]
                    if entry[0] is None:          # fall back to card if gloat missing
                        entry = self._tex_cache[hero.name]["card"]
                    self._blit(entry, cx, cy, flip=flip)

            # ---- Ban slots ----
            for idx, hero_name in enumerate(bans):
                cx = (PICKS_PER_TEAM + idx) * SLOT_W + SLOT_W // 2
                if hero_name and hero_name in hero_map:
                    hero = hero_map[hero_name]
                    self._load_images(hero)
                    self._blit(self._tex_cache[hero.name]["crit"], cx, cy, flip=flip)

        self._renderer.present()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear slot timing state (call if the draft is restarted)."""
        self._slot_first_seen.clear()

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self._window.hide()
        except Exception:
            pass

    def show(self) -> None:
        try:
            self._window.show()
        except Exception:
            pass
