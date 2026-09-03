import pygame
try:
    from pygame._sdl2 import video as _sdl2_video
    _SDL2_AVAILABLE = True
except ImportError:
    _SDL2_AVAILABLE = False

from hero import resource_path
from heroes import HERO_REGISTRY


class StatusWindow:
    """
    A self-contained pygame/SDL2 window that shows live draft state.
    Call update() once per frame from the main loop.

    This used to be a tkinter window, but tkinter and pygame (SDL) each try
    to install their own NSApplication subclass as the shared macOS
    application object. Creating a tkinter window in the same process as an
    already-initialised pygame display crashes on macOS with
    'NSInvalidArgumentException: unrecognized selector ... macOSVersion'.
    Drawing this panel with pygame/SDL2 instead means it shares the same
    process-wide application object as the rest of the app, so the conflict
    can't happen.

    Layout is 2x1: Status and Draft Slots share the top row, Hero Keybinds
    spans the full width on the bottom row. Draft Slots and Hero Keybinds
    each have a "-" button in their own header that shrinks them to a thin
    strip (click the strip to expand again); the window resizes to
    reclaim/give back the space.

    The Status panel also has "Main Window" / "Draft Overlay" Hide/Show
    buttons. These don't affect this window's own layout -- they set the
    public main_window_visible / draft_overlay_visible attributes, which
    the caller (main.py) reads each frame to hide/show those other
    application windows.
    """

    WIN_TITLE = "Draft Viewer \u2014 Status"

    # Colour palette (same values as the old tkinter theme)
    WIN_BG      = (30,  30,  46)
    WIN_FG      = (205, 214, 244)
    LBL_FG      = (137, 180, 250)
    LOCKED_FG   = (243, 139, 168)
    UNLOCKED_FG = (166, 227, 161)
    DIM_FG      = (88,  91,  112)
    UNAVAIL_FG  = (60,  60,  70)
    SEP_COLOR   = (49,  50,  68)
    SLOT_BG     = (49,  50,  68)
    SLOT_BAN_FG = (243, 139, 168)
    BTN_ON_FG   = (166, 227, 161)
    BTN_OFF_FG  = (88,  91,  112)
    ARMED_FG    = (250, 189, 47)

    EMPTY_SLOT = "------"
    EMPTY_DASH = "-"

    # Layout constants
    LEFT_W      = 300   # Status pane width (top-left, not collapsible)
    MID_W       = 340   # Draft Slots pane width, expanded
    HERO_COL_W  = 215   # per-column width in the Hero Keybinds pane
    COLLAPSED_W = 30    # Draft Slots collapsed strip width
    COLLAPSED_H = 30    # Hero Keybinds collapsed strip height
    TOP_H       = 350   # height of the top row (Status / Draft Slots)
    SEP_W       = 2      # separator thickness
    PAD         = 10
    CHUNK       = 10    # heroes per hero-keybinds sub-column
    ROW_H       = 20

    def __init__(self, hero_names: list = None, on_hero_select=None,
                 on_slot_edit=None):
        """
        hero_names    : list of hero folder names that loaded successfully;
                        only these are clickable in the Hero Keybinds panel.
        on_hero_select: callback(hero_name: str) called when the operator
                        clicks a hero in the status window UI.
        on_slot_edit  : callback(team, action_type, index) called when the
                        operator clicks an already-filled slot's body to
                        arm/disarm it for replacement by the next hero pick.
        """
        if not _SDL2_AVAILABLE:
            raise RuntimeError(
                "pygame._sdl2.video is not available. Make sure you are using pygame 2.x."
            )

        self._hero_names     = set(hero_names or [])
        self._on_hero_select = on_hero_select
        self._on_slot_edit   = on_slot_edit
        # Currently-armed slot (team, action_type, index) or None; set via
        # update()'s edit_target argument, supplied by the caller.
        self._edit_target = None
        # Rebuilt every frame Draft Slots is expanded: (Rect, team, action_type, index).
        self._slot_edit_rects = []

        entries = list(HERO_REGISTRY)
        self._hero_chunks = [entries[i:i + self.CHUNK] for i in range(0, len(entries), self.CHUNK)]
        num_chunks = max(1, len(self._hero_chunks))
        self._hero_pane_w = num_chunks * self.HERO_COL_W
        max_hero_rows = max((len(c) for c in self._hero_chunks), default=0)
        # Header (title + "-" button) + subtitle + one row per hero + bottom pad.
        self._bottom_h = (self.PAD + 24) + 18 + max_hero_rows * self.ROW_H + self.PAD

        # Collapse state for the Draft Slots ("mid") and Hero Keybinds
        # ("right") panes within this window.
        self._pane_visible = {"mid": True, "right": True}
        # Rebuilt every frame: pane_key -> Rect (click-to-collapse/expand).
        self._pane_toggle_rects = {}
        # Rebuilt every frame: toggle_id -> Rect, for the Hide/Show buttons
        # that control the OTHER application windows (see class docstring).
        self._app_toggle_rects = {}
        # Rebuilt every frame the hero panel is visible: (Rect, hero_name).
        self._hero_click_rects = []

        # Visibility of the other application windows, set by clicking the
        # buttons in the Status panel and read by main.py every frame.
        self.main_window_visible   = True
        self.draft_overlay_visible = True

        self._width  = self.LEFT_W + self.MID_W
        self._height = self.TOP_H + self.SEP_W + self._bottom_h

        self._window   = _sdl2_video.Window(self.WIN_TITLE, size=(self._width, self._height))
        self._renderer = _sdl2_video.Renderer(self._window)

        try:
            icon_surf = pygame.image.load(str(resource_path("assets/icon.ico")))
            self._window.set_icon(icon_surf)
        except Exception:
            pass

        self._font_label = pygame.font.SysFont("Segoe UI", 13, bold=True)
        self._font_value = pygame.font.SysFont("Consolas", 14)
        self._font_key   = pygame.font.SysFont("Consolas", 13, bold=True)
        self._font_desc  = pygame.font.SysFont("Segoe UI", 13)
        self._font_team  = pygame.font.SysFont("Segoe UI", 14, bold=True)
        self._font_slot  = pygame.font.SysFont("Consolas", 11)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_text(self, text: str, pos, font, color=None) -> tuple:
        color = color or self.WIN_FG
        surf = font.render(text, True, color)
        tex = _sdl2_video.Texture.from_surface(self._renderer, surf)
        dest = pygame.Rect(pos[0], pos[1], *surf.get_size())
        self._renderer.blit(tex, dest)
        return surf.get_size()

    def _fill(self, rect, color) -> None:
        self._renderer.draw_color = (*color, 255)
        self._renderer.fill_rect(rect)

    def _draw_vsep(self, x: int, y: int, height: int) -> None:
        self._fill(pygame.Rect(x, y, self.SEP_W, height), self.SEP_COLOR)

    def _draw_hsep(self, y: int) -> None:
        self._fill(pygame.Rect(0, y, self._width, self.SEP_W), self.SEP_COLOR)

    def _draw_pane_title(self, x0: int, y0: int, title: str) -> int:
        """Draw a plain pane title with no collapse button (used for the
        always-visible Status pane). Returns the y content should start at."""
        self._draw_text(title, (x0 + self.PAD, y0 + self.PAD), self._font_team, self.LBL_FG)
        return y0 + self.PAD + 24

    def _draw_pane_header(self, x0: int, y0: int, title: str, pane_key: str) -> int:
        """Draw a pane's title plus a "-" button that collapses it. Returns
        the y coordinate content should start at."""
        y = y0 + self.PAD
        self._draw_text(title, (x0 + self.PAD, y), self._font_team, self.LBL_FG)

        btn_size = 16
        btn_x = x0 + self.PAD + 150
        rect = pygame.Rect(btn_x, y - 2, btn_size, btn_size)
        self._fill(rect, self.SLOT_BG)
        self._draw_text("-", (btn_x + 5, y - 3), self._font_team, self.WIN_FG)
        self._pane_toggle_rects[pane_key] = rect

        return y0 + self.PAD + 24

    def _draw_collapsed_v(self, x0: int, w: int, h: int, title: str, pane_key: str) -> None:
        """Draw a vertically-collapsed pane as a narrow clickable strip with
        a rotated label and a "+" expand indicator."""
        self._pane_toggle_rects[pane_key] = pygame.Rect(x0, 0, w, h)

        self._draw_text("+", (x0 + w // 2 - 4, self.PAD), self._font_team, self.LBL_FG)

        surf = self._font_team.render(title, True, self.DIM_FG)
        rotated = pygame.transform.rotate(surf, 90)
        tex = _sdl2_video.Texture.from_surface(self._renderer, rotated)
        rw, rh = rotated.get_size()
        dest = pygame.Rect(x0 + max(0, (w - rw) // 2), max(0, (h - rh) // 2), rw, rh)
        self._renderer.blit(tex, dest)

    def _draw_collapsed_h(self, y0: int, h: int, title: str, pane_key: str) -> None:
        """Draw a horizontally-collapsed pane as a thin, full-width strip
        with a "+" expand indicator."""
        rect = pygame.Rect(0, y0, self._width, h)
        self._pane_toggle_rects[pane_key] = rect

        text_y = y0 + (h - 16) // 2
        self._draw_text("+", (self.PAD, text_y), self._font_team, self.LBL_FG)
        self._draw_text(title, (self.PAD + 20, text_y), self._font_team, self.DIM_FG)

    # ------------------------------------------------------------------
    # Panel sections
    # ------------------------------------------------------------------

    def _draw_status(self, app_state, solid_background, active_hero,
                      display_state, now, unlock_at, draft_manager) -> None:
        x = self.PAD
        y = self._draw_pane_title(0, 0, "Status")
        label_w = 118

        def row(label, value, color=None):
            nonlocal y
            self._draw_text(label, (x, y), self._font_label, self.LBL_FG)
            self._draw_text(value, (x + label_w, y), self._font_value, color)
            y += 22

        row("State:", app_state.replace("_", " ").title())
        row("Background:", "Solid (OBS)" if solid_background else "Chroma Key")
        row("Hero:", self._hero_display_name(active_hero.name) if active_hero else self.EMPTY_DASH)
        row("Hero State:", display_state.capitalize() if app_state == "draft" else self.EMPTY_DASH)

        if app_state in ("draft", "import_draft"):
            is_locked = now < unlock_at
            row("Hero Select:", "Locked" if is_locked else "Unlocked",
                self.LOCKED_FG if is_locked else self.UNLOCKED_FG)
            row("Draft Step:", draft_manager.step_label())
            row("Next Action:", draft_manager.current_label())
        else:
            row("Hero Select:", self.EMPTY_DASH)
            row("Draft Step:", self.EMPTY_DASH)
            row("Next Action:", self.EMPTY_DASH)

        y += 10
        self._draw_text("Keybinds", (x, y), self._font_team, self.LBL_FG)
        y += 24
        for key, desc in [("F1", "Toggle background"), ("ESC", "Exit")]:
            self._draw_text(key, (x, y), self._font_key, self.WIN_FG)
            self._draw_text(desc, (x + 60, y), self._font_desc, self.DIM_FG)
            y += 20

        y += 10
        self._draw_text("Windows", (x, y), self._font_team, self.LBL_FG)
        y += 24
        y = self._draw_toggle_row(x, y, "Main Window", self.main_window_visible, "main_window")
        y = self._draw_toggle_row(x, y, "Draft Overlay", self.draft_overlay_visible, "draft_overlay")

    def _draw_toggle_row(self, x: int, y: int, label: str, visible: bool, toggle_id: str) -> int:
        """Draw a label + Hide/Show button. Clicking it flips the named
        application window's visibility flag (handled in _handle_events)."""
        self._draw_text(label, (x, y), self._font_label, self.LBL_FG)

        btn_w, btn_h = 52, 20
        btn_x = x + 150
        rect = pygame.Rect(btn_x, y - 2, btn_w, btn_h)
        self._fill(rect, self.SLOT_BG)
        text = "Hide" if visible else "Show"
        color = self.BTN_ON_FG if visible else self.BTN_OFF_FG
        self._draw_text(text, (btn_x + 8, y - 1), self._font_desc, color)
        self._app_toggle_rects[toggle_id] = rect

        return y + 26

    def _draw_slots(self, x0, slots) -> None:
        y = self._draw_pane_header(x0, 0, "Draft Slots", "mid")
        x = x0 + self.PAD
        self._slot_edit_rects = []
        y = self._draw_team_block(x, y, 1, "Hidden King", slots.team1_picks, slots.team1_bans)
        y += 8
        y = self._draw_team_block(x, y, 2, "ArchMother", slots.team2_picks, slots.team2_bans)
        y += 16
        self._draw_text("Click a filled slot to replace it", (x, y), self._font_desc, self.DIM_FG)
        y += 16
        hint = ("Click a hero below to select it"
                if self._pane_visible["right"]
                else "Expand Hero Keybinds (below) to select a hero")
        self._draw_text(hint, (x, y), self._font_desc, self.DIM_FG)

    def _draw_team_block(self, x, y, team, team_label, picks, bans) -> int:
        self._draw_text(team_label, (x, y), self._font_team, self.WIN_FG)
        y += 20
        y = self._draw_slot_row(x, y, "Picks:", team, "pick", picks, self.WIN_FG)
        y = self._draw_slot_row(x, y, "Bans:", team, "ban", bans, self.SLOT_BAN_FG)
        return y

    def _draw_slot_row(self, x, y, label, team, action_type, values, fg) -> int:
        self._draw_text(label, (x, y), self._font_label, self.LBL_FG)
        slot_x = x + 55
        slot_w = 42
        for idx, v in enumerate(values):
            rect = pygame.Rect(slot_x, y - 2, slot_w - 4, 20)
            self._fill(rect, self.SLOT_BG)
            text = self._fit_slot_text(self._hero_display_name(v)) if v else self.EMPTY_SLOT
            self._draw_text(text, (rect.x + 2, rect.y + 2), self._font_slot, fg)
            if v:
                if self._edit_target == (team, action_type, idx):
                    self._renderer.draw_color = (*self.ARMED_FG, 255)
                    self._renderer.draw_rect(rect)
                self._slot_edit_rects.append((rect, team, action_type, idx))
            slot_x += slot_w
        return y + 24

    def _draw_hero_keybinds(self, y0) -> None:
        content_top = self._draw_pane_header(0, y0, "Hero Keybinds", "right")
        self._draw_text("(click a hero to select)", (self.PAD, content_top), self._font_desc, self.DIM_FG)
        content_y = content_top + 18

        self._hero_click_rects = []
        for c_idx, chunk in enumerate(self._hero_chunks):
            cx = self.PAD + c_idx * self.HERO_COL_W
            for i, (combo, name, _volume) in enumerate(chunk):
                cy = content_y + i * self.ROW_H
                self._draw_text(self._fmt_combo(combo), (cx, cy), self._font_key, self.WIN_FG)
                available = name in self._hero_names
                color = self.DIM_FG if available else self.UNAVAIL_FG
                self._draw_text(self._hero_display_name(name), (cx + 78, cy), self._font_desc, color)
                rect = pygame.Rect(cx, cy - 2, self.HERO_COL_W - 12, self.ROW_H)
                self._hero_click_rects.append((rect, name))

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _handle_events(self, events) -> None:
        """Handle collapse, window-visibility, and hero-select clicks,
        using the hit rects computed during the previous frame's draw."""
        for event in events:
            if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
                continue
            window = getattr(event, "window", None)
            if window is None or window.id != self._window.id:
                continue

            handled = False
            for pane_key, rect in self._pane_toggle_rects.items():
                if rect.collidepoint(event.pos):
                    self._pane_visible[pane_key] = not self._pane_visible[pane_key]
                    handled = True
                    break
            if handled:
                continue

            for toggle_id, rect in self._app_toggle_rects.items():
                if rect.collidepoint(event.pos):
                    if toggle_id == "main_window":
                        self.main_window_visible = not self.main_window_visible
                    elif toggle_id == "draft_overlay":
                        self.draft_overlay_visible = not self.draft_overlay_visible
                    handled = True
                    break
            if handled:
                continue

            # Clicking a filled slot's body arms/disarms it for replacement.
            for rect, team, action_type, idx in self._slot_edit_rects:
                if rect.collidepoint(event.pos):
                    if self._on_slot_edit:
                        self._on_slot_edit(team, action_type, idx)
                    handled = True
                    break
            if handled:
                continue

            if not self._on_hero_select:
                continue
            for rect, name in self._hero_click_rects:
                if name in self._hero_names and rect.collidepoint(event.pos):
                    self._on_hero_select(name)
                    break

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, app_state: str, solid_background: bool,
               active_hero, display_state: str,
               now: int, unlock_at: float, draft_manager, events=(),
               edit_target=None) -> None:
        """Handle clicks, redraw the panel, and present it. Call once per frame.

        events     : this frame's pygame.event.get() list (shared with the
                     main loop), used to detect clicks on this window.
        edit_target: (team, action_type, index) of the slot currently armed
                     for replacement (see on_slot_edit), or None. Owned by
                     the caller; only used here to highlight the slot.
        """
        self._edit_target = edit_target
        self._handle_events(events)
        self._pane_toggle_rects = {}
        self._app_toggle_rects = {}

        mid_visible  = self._pane_visible["mid"]
        hero_visible = self._pane_visible["right"]

        mid_w  = self.MID_W if mid_visible else self.COLLAPSED_W
        hero_h = self._bottom_h if hero_visible else self.COLLAPSED_H

        row1_w = self.LEFT_W + mid_w
        new_width  = max(row1_w, self._hero_pane_w if hero_visible else 0, self.LEFT_W)
        new_height = self.TOP_H + self.SEP_W + hero_h
        if (new_width, new_height) != (self._width, self._height):
            self._width, self._height = new_width, new_height
            self._window.size = (self._width, self._height)

        r = self._renderer
        r.draw_color = (*self.WIN_BG, 255)
        r.clear()

        # Top row: Status (always) + Draft Slots (collapsible)
        self._draw_status(app_state, solid_background, active_hero,
                           display_state, now, unlock_at, draft_manager)
        self._draw_vsep(self.LEFT_W, 0, self.TOP_H)
        if mid_visible:
            self._draw_slots(self.LEFT_W, draft_manager.slots)
        else:
            self._slot_edit_rects = []
            self._draw_collapsed_v(self.LEFT_W, mid_w, self.TOP_H, "Draft Slots", "mid")

        # Bottom row: Hero Keybinds, spanning the full width (collapsible)
        self._draw_hsep(self.TOP_H)
        content_y0 = self.TOP_H + self.SEP_W
        if hero_visible:
            self._draw_hero_keybinds(content_y0)
        else:
            self._hero_click_rects = []
            self._draw_collapsed_h(content_y0, hero_h, "Hero Keybinds", "right")

        r.present()

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_combo(combo: str) -> str:
        return "+".join(p.capitalize() for p in combo.split("+"))

    @staticmethod
    def _hero_display_name(name: str) -> str:
        """Convert a hero folder name to a readable display name.
        'grey_talon' -> 'Grey Talon',  'abrams' -> 'Abrams'
        """
        return name.replace("_", " ").title()

    @staticmethod
    def _fit_slot_text(text: str, max_chars: int = 6) -> str:
        return text if len(text) <= max_chars else text[:max_chars - 1] + "\u2026"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        try:
            self._window.destroy()
        except Exception:
            pass
