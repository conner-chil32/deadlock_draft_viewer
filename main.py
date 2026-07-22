import ctypes
import json
import pygame
import random
import sys
from tkinter import filedialog
from pynput import keyboard

from draft import DRAFT_ORDER, DraftManager, DraftSlots, TEAM_NAMES
from hero import Hero
from heroes import HERO_REGISTRY
from keybinds import KeybindManager
from draft_overlay import DraftOverlayWindow
from menu import Button
from status_window import StatusWindow

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

# Minimum time (ms) the render image is held on screen.
# Actual hold = max(RENDER_MIN_MS, voice_line_duration).
RENDER_MIN_MS = 10_000

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

# Draft manager (order + slot state).
draft_manager = DraftManager()


def import_draft(parent=None):
    """Open a file picker, load a draft JSON, and print the actions to the console."""
    file_path = filedialog.askopenfilename(
        parent=parent,
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
    (voice line playing + 2 s after card appears) or once the draft is
    complete. Safe to call from the key listener thread.
    """
    global pending_hero
    if draft_manager.is_complete:
        print(f"Draft complete — ignoring '{hero.name}'")
        return
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
    """Load and return (render, card, crit) surfaces scaled to fit the main window."""
    render_raw  = pygame.image.load(str(hero.get_asset("render"))).convert_alpha()
    card_raw    = pygame.image.load(str(hero.get_asset("card"))).convert_alpha()
    crit_raw    = pygame.image.load(str(hero.get_asset("crit"))).convert_alpha()
    return (
        scale_to_fit(render_raw, WINDOW_WIDTH, WINDOW_HEIGHT),
        scale_to_fit(card_raw,   WINDOW_WIDTH, WINDOW_HEIGHT),
        scale_to_fit(crit_raw,   WINDOW_WIDTH, WINDOW_HEIGHT),
    )


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

    # Pre-initialise the mixer before pygame.init() so the audio subsystem is
    # fully ready before the first voice line plays, preventing a cut-off.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
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

    # Load heroes, register keybinds, and build the name→object lookup
    hero_map: dict = {}
    for combo, name, volume in HERO_REGISTRY:
        try:
            h = Hero(name, volume=volume)
            keybind_manager.register(combo, lambda hero=h: activate_hero(hero), label=name)
            hero_map[name] = h
            print(f"Loaded: {h!r}")
        except Exception as e:
            print(f"[WARN] Could not load hero '{name}': {e}")

    keybind_manager.register("f1",  toggle_background, label="toggle_background")
    keybind_manager.register("esc", shutdown,          label="shutdown")

    # Per-hero surface cache: hero.name -> (render_surf, card_surf, crit_surf)
    hero_cache = {}

    # Display state machine  ("idle" | "render" | "card" | "crit")
    display_state    = "idle"
    active_hero      = None
    render_surf      = None
    card_surf        = None
    crit_surf        = None
    render_started_at = 0   # ticks when current render began

    listener      = None   # Started only when Manual Draft is chosen
    draft_overlay = None    # Created when draft mode is entered
    status_window = None    # Created when draft mode is entered

    # Shared args for StatusWindow so we don't repeat them in each branch
    _sw_kwargs = dict(
        hero_names=list(hero_map.keys()),
        on_hero_select=lambda name: activate_hero(hero_map[name]) if name in hero_map else None,
    )

    print(f"Window created: {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
    print("-" * 50)

    # Main event loop
    try:
        while window_open:
            now = pygame.time.get_ticks()
            events = pygame.event.get()

            if status_window is not None:
                status_window.update(
                    app_state, solid_background, active_hero,
                    display_state, now, unlock_at, draft_manager
                )

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
                        import_draft(None)

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
                        app_state     = "draft"
                        draft_overlay = DraftOverlayWindow()
                        status_window = StatusWindow(**_sw_kwargs)
                        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
                        listener.start()
                        print(f"Manual Draft started — Hidden King picks first.")
                        print(f"Step 1: {draft_manager.current_label()}")
                        print("-" * 50)
                    elif btn_team2_first.is_clicked(event):
                        first_team = 2
                        draft_manager.start(first_team)
                        app_state     = "draft"
                        draft_overlay = DraftOverlayWindow()
                        status_window = StatusWindow(**_sw_kwargs)
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
                active_hero      = hero
                unlock_at        = float('inf')
                display_state    = "crit" if action_type == "ban" else "render"
                render_started_at = now
                play_voice_line(hero, action_type)

            # Transitions when voice line finishes
            # Render holds for max(RENDER_MIN_MS, voice_line_duration).
            if not pygame.mixer.music.get_busy():
                if display_state == "render":
                    if now - render_started_at >= RENDER_MIN_MS:
                        display_state = "card"
                        unlock_at     = now + CARD_LOCKOUT_MS
                elif display_state == "crit" and unlock_at == float('inf'):
                    unlock_at = now + CARD_LOCKOUT_MS

            # Main window only shows the render image (card/crit live in the overlay)
            displayed_surface = render_surf if display_state == "render" else None

            # Draw main window
            if solid_background:
                screen.fill(SOLID_TEST_COLOR)
            elif TRANSPARENT_BACKGROUND:
                screen.fill(TRANSPARENT_COLOR)
            else:
                screen.fill((0, 0, 0))

            if displayed_surface is not None:
                rect = displayed_surface.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
                screen.blit(displayed_surface, rect)

            # Update the draft overlay every frame
            if draft_overlay is not None:
                draft_overlay.update(now, draft_manager.slots, hero_map, solid_background,
                                     voice_playing=pygame.mixer.music.get_busy())

            pygame.display.flip()
            clock.tick(60)

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Shutting down...")
    finally:
        if listener:
            listener.stop()
        if draft_overlay:
            draft_overlay.destroy()
        if status_window:
            status_window.destroy()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    main()
