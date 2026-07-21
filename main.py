import ctypes
import json
import pygame
import random
import sys
import tkinter as tk
from tkinter import filedialog
from pynput import keyboard

from draft import DRAFT_ORDER, DraftManager, DraftSlots, TEAM_NAMES
from hero import Hero
from keybinds import KeybindManager

# Configuration parameters
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
WINDOW_FRAMELESS = False       # Remove title bar / border (recommended for overlays)
TRANSPARENT_BACKGROUND = True  # Make the empty background see-through

# Chroma-key color used as the transparent background.
# Magenta is chosen because it is extremely unlikely to appear in hero artwork.
TRANSPARENT_COLOR = (255, 0, 255)

# Solid color shown when the background toggle is active (for OBS testing).
SOLID_TEST_COLOR = (0, 0, 0)

# How long (ms) the lockout persists after the card is shown.
CARD_LOCKOUT_MS = 2000

# Global state
window_open = True
solid_background = False  # Toggle with F1
app_state = "menu"        # "menu" | "team_select" | "draft"
first_team = None          # Set during team_select; 1 or 2

# Hero requested by the key listener thread; picked up by the main loop.
pending_hero = None

# pygame ticks timestamp after which a new hero activation is allowed.
# float('inf') while a voice line is playing; set to now+CARD_LOCKOUT_MS on card show.
unlock_at = 0

# Single shared keybind manager; populated in main().
keybind_manager = KeybindManager()

# Shared tkinter root — created once in main(), reused by import_draft().
tk_root = None

# Draft manager (order + slot state).
draft_manager = DraftManager()


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

class Button:
    """Simple rectangular button for the menu screen."""

    def __init__(self, rect, text, font,
                 color=(40, 40, 40), hover_color=(70, 70, 70),
                 text_color=(255, 255, 255), border_color=(180, 180, 180)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.border_color = border_color

    def draw(self, surface):
        hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        fill = self.hover_color if hovered else self.color
        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(surface, self.border_color, self.rect, width=2, border_radius=8)
        label = self.font.render(self.text, True, self.text_color)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def is_clicked(self, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


def import_draft():
    """Open a file picker, load a draft JSON, and print the actions to the console."""
    file_path = filedialog.askopenfilename(
        parent=tk_root,
        title="Select Draft JSON",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )

    if not file_path:
        print("Import cancelled.")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load JSON: {e}")
        return

    if not isinstance(data, list):
        print("Unexpected JSON format: expected a list of draft actions.")
        return

    TEAM_NAMES = {
        "team1": "Hidden King",
        "team2": "ArchMother",
    }

    print(f"Imported draft from: {file_path}")
    print("-" * 50)
    for entry in data:
        team_raw    = entry.get("team", "?")
        team_name   = TEAM_NAMES.get(team_raw, str(team_raw))
        action_type = entry.get("type", "?").capitalize()
        hero        = entry.get("hero", "?")
        print(f"{team_name}: {action_type} -> {hero}")
    print("-" * 50)


# ---------------------------------------------------------------------------


def make_window_transparent(hwnd: int) -> None:
    """
    Apply Windows layered-window transparency using a chroma key.
    Pixels drawn in TRANSPARENT_COLOR will become invisible at the OS level.
    """
    GWL_EXSTYLE  = -20
    WS_EX_LAYERED = 0x00080000
    LWA_COLORKEY  = 0x00000001

    r, g, b = TRANSPARENT_COLOR
    # Windows COLORREF format: 0x00BBGGRR
    color_ref = r | (g << 8) | (b << 16)

    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, color_ref, 0, LWA_COLORKEY)


def activate_hero(hero):
    """
    Request a hero to be displayed. Ignored during the lockout period
    (voice line playing + 2 s after card appears). Safe to call from
    the key listener thread.
    """
    global pending_hero
    if pygame.time.get_ticks() < unlock_at:
        print(f"Locked — ignoring '{hero.name}'")
        return
    pending_hero = hero


def toggle_background():
    """Switch between the transparent chroma key and a solid test background."""
    global solid_background
    solid_background = not solid_background
    mode = "solid (OBS test)" if solid_background else "transparent (chroma key)"
    print(f"Background mode: {mode}")


def on_press(key):
    """Handle key press events globally."""
    try:
        keybind_manager.on_press(key)
    except Exception as e:
        print(f"Error handling key press: {e}")


def shutdown():
    """Shut down the application."""
    global window_open
    print("Shutting down...")
    window_open = False


def on_release(key):
    """Handle key release events globally."""
    try:
        keybind_manager.on_release(key)
    except Exception as e:
        print(f"Error handling key release: {e}")


def scale_to_fit(surface, max_width, max_height):
    """Scale a surface to fit within bounds, preserving aspect ratio."""
    width, height = surface.get_size()
    scale = min(max_width / width, max_height / height)
    new_size = (int(width * scale), int(height * scale))
    return pygame.transform.smoothscale(surface, new_size)


def load_hero_surfaces(hero):
    """
    Load and return (render_surface, card_surface, crit_surface) for a hero.
    All three are independently scaled to fit the window.
    """
    render_raw = pygame.image.load(str(hero.get_asset("render"))).convert_alpha()
    render_surf = scale_to_fit(render_raw, WINDOW_WIDTH, WINDOW_HEIGHT)

    card_raw = pygame.image.load(str(hero.get_asset("card"))).convert_alpha()
    card_surf = scale_to_fit(card_raw, WINDOW_WIDTH, WINDOW_HEIGHT)

    crit_raw = pygame.image.load(str(hero.get_asset("crit"))).convert_alpha()
    crit_surf = scale_to_fit(crit_raw, WINDOW_WIDTH, WINDOW_HEIGHT)

    return render_surf, card_surf, crit_surf


def play_voice_line(hero, voice_type: str):
    """Play a random voice line of the given type ('select'/'pick' or 'ban')."""
    # Map draft action types to voice folder names
    voice_folder = "select" if voice_type == "pick" else voice_type
    voice_lines = hero.get_voice_lines(voice_folder)
    if not voice_lines:
        # Fall back to select lines if the requested type has none
        voice_lines = hero.get_voice_lines("select")
    if not voice_lines:
        print(f"No voice lines found for '{hero.name}'")
        return
    chosen = random.choice(voice_lines)
    print(f"Playing {voice_type} voice line: {chosen.name}")
    pygame.mixer.music.load(str(chosen))
    pygame.mixer.music.set_volume(hero.volume)
    pygame.mixer.music.play()


def main():
    """Initialize and run the application."""
    global window_open, pending_hero, unlock_at, app_state, first_team

    # Initialize Pygame
    pygame.init()

    flags = 0
    if WINDOW_FRAMELESS:
        flags |= pygame.NOFRAME

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), flags)
    pygame.display.set_caption("Deadlock Draft Viewer")
    clock = pygame.time.Clock()

    # if TRANSPARENT_BACKGROUND:
    #     hwnd = pygame.display.get_wm_info()["window"]
    #     make_window_transparent(hwnd)

    # Fonts
    title_font  = pygame.font.SysFont("segoeui", 52, bold=True)
    button_font = pygame.font.SysFont("segoeui", 30)

    # Menu buttons (centred in the window)
    btn_w, btn_h = 320, 70
    cx = WINDOW_WIDTH  // 2
    cy = WINDOW_HEIGHT // 2
    btn_manual = Button(
        (cx - btn_w // 2, cy - btn_h - 20, btn_w, btn_h),
        "Manual Draft", button_font
    )
    btn_import = Button(
        (cx - btn_w // 2, cy + 20, btn_w, btn_h),
        "Import Draft", button_font
    )

    # Team-select buttons
    btn_team1_first = Button(
        (cx - btn_w // 2, cy - btn_h - 20, btn_w, btn_h),
        "Team 1 First", button_font
    )
    btn_team2_first = Button(
        (cx - btn_w // 2, cy + 20, btn_w, btn_h),
        "Team 2 First", button_font
    )

    # Draft-mode setup (heroes + keybinds)
    abrams = Hero("abrams", volume=0.8)
    apollo = Hero("apollo", volume=0.8)
    bebop = Hero("bebop", volume=0.8)
    
    
    keybind_manager.register("shift+1", lambda: activate_hero(abrams), label="abrams")
    keybind_manager.register("shift+2", lambda: activate_hero(apollo), label="apollo")
    keybind_manager.register("shift+3", lambda: activate_hero(bebop), label="bebop")
    
    
    keybind_manager.register("f1",  toggle_background, label="toggle_background")
    keybind_manager.register("esc", shutdown,          label="shutdown")

    # Per-hero surface cache: hero.name -> (render_surf, card_surf, crit_surf)
    hero_cache = {}

    # Display state machine  ("idle" | "render" | "card" | "crit")
    display_state  = "idle"
    active_hero    = None
    render_surf    = None
    card_surf      = None
    crit_surf      = None

    listener = None  # Started only when Manual Draft is chosen

    # ------------------------------------------------------------------
    # Status window (tkinter)
    # ------------------------------------------------------------------
    global tk_root
    WIN_BG = "#1e1e2e"
    WIN_FG = "#cdd6f4"
    LBL_FG = "#89b4fa"
    FONT_LABEL = ("Segoe UI", 9, "bold")
    FONT_VALUE = ("Consolas", 10)

    LOCKED_FG   = "#f38ba8"   # Red tint for locked
    UNLOCKED_FG = "#a6e3a1"   # Green tint for unlocked
    DIM_FG      = "#585b70"   # Muted colour for static keybind labels

    tk_root = tk.Tk()
    tk_root.title("Draft Viewer — Status")
    tk_root.geometry("680x340")
    tk_root.resizable(False, False)
    tk_root.configure(bg=WIN_BG)
    tk_root.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent accidental close

    # ------------------------------------------------------------------
    # Two-column layout: left = status info, right = draft slots
    # ------------------------------------------------------------------
    cols = tk.Frame(tk_root, bg=WIN_BG)
    cols.pack(fill="both", expand=True)

    left_col = tk.Frame(cols, bg=WIN_BG)
    left_col.pack(side="left", fill="y", padx=(0, 0))

    tk.Frame(cols, bg="#313244", width=2).pack(side="left", fill="y", padx=4)

    right_col = tk.Frame(cols, bg=WIN_BG)
    right_col.pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------------
    # Left column — status rows + keybinds
    # ------------------------------------------------------------------
    def _row(parent, label_text, var, value_fg=None):
        frame = tk.Frame(parent, bg=WIN_BG)
        frame.pack(fill="x", padx=10, pady=3)
        tk.Label(frame, text=label_text, bg=WIN_BG, fg=LBL_FG,
                 font=FONT_LABEL, anchor="w", width=14).pack(side="left")
        lbl = tk.Label(frame, textvariable=var, bg=WIN_BG,
                       fg=value_fg or WIN_FG, font=FONT_VALUE, anchor="w")
        lbl.pack(side="left")
        return lbl

    sv_state        = tk.StringVar(value="Menu")
    sv_bg_mode      = tk.StringVar(value="Chroma Key")
    sv_hero         = tk.StringVar(value="\u2014")
    sv_hero_state   = tk.StringVar(value="\u2014")
    sv_locked       = tk.StringVar(value="\u2014")
    sv_draft_step   = tk.StringVar(value="\u2014")
    sv_draft_action = tk.StringVar(value="\u2014")

    tk.Frame(left_col, bg="#313244", height=2).pack(fill="x", pady=(8, 4))
    _row(left_col, "State:",       sv_state)
    _row(left_col, "Background:",  sv_bg_mode)
    _row(left_col, "Hero:",        sv_hero)
    _row(left_col, "Hero State:",  sv_hero_state)
    locked_lbl = _row(left_col, "Hero Select:",  sv_locked)
    _row(left_col, "Draft Step:",  sv_draft_step)
    _row(left_col, "Next Action:", sv_draft_action)

    tk.Frame(left_col, bg="#313244", height=2).pack(fill="x", pady=(6, 4))
    tk.Label(left_col, text="  Keybinds", bg=WIN_BG, fg=LBL_FG,
             font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=10)

    KEYBINDS = [
        ("F1",       "Toggle background mode"),
        ("Shift+1",  "Select hero: Abrams"),
        ("Shift+2",  "Select hero: Apollo"),
        ("Shift+3",  "Select hero: Bebop"),
        ("ESC",      "Exit"),
    ]
    for key, desc in KEYBINDS:
        row = tk.Frame(left_col, bg=WIN_BG)
        row.pack(fill="x", padx=10, pady=1)
        tk.Label(row, text=key, bg=WIN_BG, fg=WIN_FG,
                 font=("Consolas", 9, "bold"), width=10, anchor="w").pack(side="left")
        tk.Label(row, text=desc, bg=WIN_BG, fg=DIM_FG,
                 font=("Segoe UI", 9), anchor="w").pack(side="left")

    tk.Frame(left_col, bg="#313244", height=2).pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------
    # Right column — draft slots
    # ------------------------------------------------------------------
    EMPTY_SLOT  = "\u2500\u2500\u2500\u2500\u2500\u2500"
    SLOT_W      = 7
    SLOT_BG     = "#313244"
    SLOT_FG     = WIN_FG
    SLOT_BAN_FG = "#f38ba8"

    sv_t1_picks = [tk.StringVar(value=EMPTY_SLOT) for _ in range(DraftSlots.NUM_PICKS)]
    sv_t1_bans  = [tk.StringVar(value=EMPTY_SLOT) for _ in range(DraftSlots.NUM_BANS)]
    sv_t2_picks = [tk.StringVar(value=EMPTY_SLOT) for _ in range(DraftSlots.NUM_PICKS)]
    sv_t2_bans  = [tk.StringVar(value=EMPTY_SLOT) for _ in range(DraftSlots.NUM_BANS)]

    def _slot_row(parent, label_text, slot_vars, fg):
        row = tk.Frame(parent, bg=WIN_BG)
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text=label_text, bg=WIN_BG, fg=LBL_FG,
                 font=FONT_LABEL, width=5, anchor="w").pack(side="left")
        for var in slot_vars:
            tk.Label(row, textvariable=var, bg=SLOT_BG, fg=fg,
                     font=("Consolas", 8), width=SLOT_W,
                     relief="flat", padx=2, anchor="center").pack(side="left", padx=1)

    def _team_block(parent, team_label, pick_vars, ban_vars):
        tk.Label(parent, text=team_label, bg=WIN_BG, fg=WIN_FG,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=8, pady=(8, 0))
        _slot_row(parent, "Picks:", pick_vars, SLOT_FG)
        _slot_row(parent, "Bans:",  ban_vars,  SLOT_BAN_FG)

    tk.Frame(right_col, bg="#313244", height=2).pack(fill="x", pady=(8, 0))
    tk.Label(right_col, text="  Draft Slots", bg=WIN_BG, fg=LBL_FG,
             font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=8)
    _team_block(right_col, "Hidden King", sv_t1_picks, sv_t1_bans)
    tk.Frame(right_col, bg="#313244", height=1).pack(fill="x", padx=8, pady=(6, 0))
    _team_block(right_col, "ArchMother",  sv_t2_picks, sv_t2_bans)
    tk.Frame(right_col, bg="#313244", height=2).pack(fill="x", pady=(6, 0))

    def _update_slot_vars():
        """Sync StringVars with the current draft_manager.slots state."""
        slots = draft_manager.slots
        for i, v in enumerate(sv_t1_picks):
            v.set(slots.team1_picks[i] or EMPTY_SLOT)
        for i, v in enumerate(sv_t1_bans):
            v.set(slots.team1_bans[i] or EMPTY_SLOT)
        for i, v in enumerate(sv_t2_picks):
            v.set(slots.team2_picks[i] or EMPTY_SLOT)
        for i, v in enumerate(sv_t2_bans):
            v.set(slots.team2_bans[i] or EMPTY_SLOT)

    print(f"Window created: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    print("-" * 50)

    # Main event loop
    try:
        while window_open:
            now = pygame.time.get_ticks()
            events = pygame.event.get()

            # Update status window every frame
            sv_state.set(app_state.replace("_", " ").title())
            sv_bg_mode.set("Solid (OBS)" if solid_background else "Chroma Key")
            sv_hero.set(active_hero.name.capitalize() if active_hero else "—")
            sv_hero_state.set(display_state.capitalize() if app_state == "draft" else "—")
            if app_state == "draft":
                is_locked = now < unlock_at
                sv_locked.set("Locked" if is_locked else "Unlocked")
                locked_lbl.config(fg=LOCKED_FG if is_locked else UNLOCKED_FG)
                sv_draft_step.set(draft_manager.step_label())
                sv_draft_action.set(draft_manager.current_label())
            else:
                sv_locked.set("—")
                locked_lbl.config(fg=WIN_FG)
                sv_draft_step.set("—")
                sv_draft_action.set("—")
            _update_slot_vars()
            tk_root.update()

            for event in events:
                if event.type == pygame.QUIT:
                    window_open = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if app_state == "menu":
                        window_open = False

            # ------------------------------------------------------------------
            # MENU STATE
            # ------------------------------------------------------------------
            if app_state == "menu":
                for event in events:
                    if btn_manual.is_clicked(event):
                        app_state = "team_select"
                    elif btn_import.is_clicked(event):
                        import_draft()

                screen.fill((20, 20, 30))
                title_surf = title_font.render("Deadlock Draft Viewer", True, (220, 220, 220))
                screen.blit(title_surf, title_surf.get_rect(center=(cx, cy - 160)))
                btn_manual.draw(screen)
                btn_import.draw(screen)
                pygame.display.flip()
                clock.tick(60)
                continue

            # ------------------------------------------------------------------
            # TEAM SELECT STATE
            # ------------------------------------------------------------------
            if app_state == "team_select":
                for event in events:
                    if btn_team1_first.is_clicked(event):
                        first_team = 1
                        draft_manager.start(first_team)
                        app_state = "draft"
                        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                        listener.start()
                        print(f"Manual Draft started — Hidden King picks first.")
                        print(f"Step 1: {draft_manager.current_label()}")
                        print("-" * 50)
                    elif btn_team2_first.is_clicked(event):
                        first_team = 2
                        draft_manager.start(first_team)
                        app_state = "draft"
                        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                        listener.start()
                        print(f"Manual Draft started — ArchMother picks first.")
                        print(f"Step 1: {draft_manager.current_label()}")
                        print("-" * 50)

                screen.fill((20, 20, 30))
                subtitle = title_font.render("Who picks first?", True, (220, 220, 220))
                screen.blit(subtitle, subtitle.get_rect(center=(cx, cy - 160)))
                btn_team1_first.draw(screen)
                btn_team2_first.draw(screen)
                pygame.display.flip()
                clock.tick(60)
                continue

            # ------------------------------------------------------------------
            # DRAFT STATE
            # ------------------------------------------------------------------

            # Pick up a pending hero from the key listener thread
            if pending_hero is not None:
                hero = pending_hero
                pending_hero = None

                # Capture action type BEFORE assigning (assign advances the step)
                action_type = draft_manager.current_action_type() or "pick"
                result = draft_manager.assign(hero.name)
                if result:
                    team, action = result
                    team_name = TEAM_NAMES[team]
                    print(f"[{draft_manager.step}/{len(DRAFT_ORDER)}] "
                          f"{team_name}: {action.capitalize()} -> {hero.name.capitalize()}")
                    if not draft_manager.is_complete:
                        print(f"Next \u2014 Step {draft_manager.step + 1}: {draft_manager.current_label()}")
                    else:
                        print("Draft complete.")

                if hero.name not in hero_cache:
                    try:
                        hero_cache[hero.name] = load_hero_surfaces(hero)
                    except Exception as e:
                        print(f"Failed to load surfaces for '{hero.name}': {e}")
                        hero_cache[hero.name] = (None, None, None)

                render_surf, card_surf, crit_surf = hero_cache[hero.name]
                active_hero = hero
                unlock_at   = float('inf')

                if action_type == "ban":
                    display_state = "crit"
                else:
                    display_state = "render"

                play_voice_line(hero, action_type)

            # Transitions when voice line finishes
            if not pygame.mixer.music.get_busy():
                if display_state == "render":
                    display_state = "card"
                    unlock_at     = now + CARD_LOCKOUT_MS
                elif display_state == "crit" and unlock_at == float('inf'):
                    unlock_at     = now + CARD_LOCKOUT_MS

            # Determine which surface to draw
            if display_state == "render":
                displayed_surface = render_surf
            elif display_state == "card":
                displayed_surface = card_surf
            elif display_state == "crit":
                displayed_surface = crit_surf
            else:
                displayed_surface = None

            # Draw — fill based on current background mode
            if solid_background:
                screen.fill(SOLID_TEST_COLOR)
            elif TRANSPARENT_BACKGROUND:
                screen.fill(TRANSPARENT_COLOR)
            else:
                screen.fill((0, 0, 0))

            if displayed_surface is not None:
                rect = displayed_surface.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
                screen.blit(displayed_surface, rect)

            pygame.display.flip()
            clock.tick(60)

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Shutting down...")
    finally:
        if listener:
            listener.stop()
        if tk_root:
            tk_root.destroy()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    main()
