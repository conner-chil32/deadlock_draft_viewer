import ctypes
import json
import pygame
import random
import sys
from pynput import keyboard

try:
    from pygame._sdl2 import video as _sdl2_video
    _SDL2_AVAILABLE = True
except ImportError:
    _SDL2_AVAILABLE = False

import mac_pynput_fix
mac_pynput_fix.apply()

import file_dialog
from draft import DRAFT_ORDER, DraftManager, DraftSlots, TEAM_NAMES
from hero import Hero, resource_path
from heroes import HERO_REGISTRY, resolve_hero_name
from keybinds import KeybindManager
from draft_overlay import DraftOverlayWindow
from menu import Button
from status_window import StatusWindow

# Application version
VERSION = "0.0.2"

# Configuration parameters
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
WINDOW_FRAMELESS = False       # Remove title bar / border (recommended for overlays)
TRANSPARENT_BACKGROUND = True  # Make the empty background see-through

# Resolution choices offered on the Settings screen. More settings will be
# added here later.
RESOLUTION_PRESETS = [
    (1280, 720),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
]

# Chroma-key color used as the transparent background.
# Magenta is chosen because it is extremely unlikely to appear in hero artwork.
TRANSPARENT_COLOR = (255, 0, 255)

# Solid color shown when the background toggle is active (for OBS testing).
SOLID_TEST_COLOR = (0, 0, 0)

# How long (ms) the lockout persists after the card is shown.
CARD_LOCKOUT_MS = 1000

# Minimum time (ms) the render image is held on screen.
# Actual hold = max(RENDER_MIN_MS, voice_line_duration).
RENDER_MIN_MS  = 5_000
FADE_IN_MS     = 250    # duration of the fade-in
FADE_OUT_MS    = 250    # duration of the fade-out

# Import draft playback timing (ms) — edit to change wait durations
IMPORT_START_DELAY_MS = 5_000   # delay before the first action fires after import
IMPORT_BAN_WAIT_MS    = 5_000   # wait after a ban crit is shown before the next action
IMPORT_PICK_WAIT_MS   = 7_000   # wait after a pick card is shown before the next action

# Global state
window_open = True
solid_background = False  # Toggle with F1
app_state = "menu"        # "menu" | "team_select" | "draft"
first_team = None          # Set during team_select; 1 or 2

# Hero requested by the key listener thread; picked up by the main loop.
pending_hero = None

# Slot (team, action_type, index) armed for replacement, or None. Set by
# clicking a filled slot's body in the status window; consumed by the next
# hero activation instead of the normal draft-order assignment.
edit_target = None

# Carries edit_target's value alongside pending_hero from activation time
# through to the main loop's draft-state block, since edit_target itself is
# cleared immediately once a hero is captured (so the UI stops highlighting
# it right away).
pending_edit_target = None

# pygame ticks timestamp after which a new hero activation is allowed.
# float('inf') while a voice line is playing; set to now+CARD_LOCKOUT_MS on card show.
unlock_at = 0

# Single shared keybind manager; populated in main().
keybind_manager = KeybindManager()

# Draft manager (order + slot state).
draft_manager = DraftManager()


def import_draft():
    """Open a file picker, parse a draft JSON, and return the action list (or None)."""
    file_path = file_dialog.ask_open_json(title="Select Draft JSON")

    if not file_path:
        print("Import cancelled.")
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load JSON: {e}")
        return None

    if not isinstance(data, list):
        print("Unexpected JSON format: expected a list of draft actions.")
        return None

    print(f"Loaded draft: {file_path} ({len(data)} actions)")
    return data


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
    Request a hero to be displayed. Ignored if the hero is already in the
    draft, if the draft is complete, or during the lockout period.
    Safe to call from the key listener thread.

    If a slot is currently armed for replacement (edit_target), this
    instead captures the hero for that slot, bypassing the draft-order,
    lock, and completion checks above (see start_slot_edit).
    """
    global pending_hero, pending_edit_target, edit_target

    if edit_target is not None:
        team, action_type, index = edit_target
        slots = draft_manager.slots
        already_drafted = (
            slots.team1_picks + slots.team2_picks +
            slots.team1_bans  + slots.team2_bans
        )
        current = draft_manager.get_hero(team, action_type, index)
        if hero.name in already_drafted and hero.name != current:
            print(f"'{hero.name}' already in draft — ignoring")
            return
        pending_edit_target = edit_target
        edit_target = None
        pending_hero = hero
        return

    if draft_manager.is_complete:
        print(f"Draft complete — ignoring '{hero.name}'")
        return
    if pygame.time.get_ticks() < unlock_at:
        print(f"Locked — ignoring '{hero.name}'")
        return
    slots = draft_manager.slots
    already_drafted = (
        slots.team1_picks + slots.team2_picks +
        slots.team1_bans  + slots.team2_bans
    )
    if hero.name in already_drafted:
        print(f"'{hero.name}' already in draft — ignoring")
        return
    pending_hero = hero


def start_slot_edit(team, action_type, index):
    """
    Arm (or disarm, if already armed) a specific slot for replacement by the
    next hero activation. Manual-draft only, to avoid conflicting with the
    Import Draft auto-play queue.
    """
    global edit_target
    if app_state != "draft":
        print("Slot editing is only available during Manual Draft.")
        return
    target = (team, action_type, index)
    if edit_target == target:
        edit_target = None
        print("Slot edit cancelled.")
    else:
        edit_target = target
        team_name = TEAM_NAMES[team]
        print(f"Editing {team_name} {action_type} slot {index + 1} — "
              f"pick a hero to replace it, or click it again to cancel.")


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
    global edit_target, pending_edit_target
    global WINDOW_WIDTH, WINDOW_HEIGHT

    # Pre-initialise the mixer before pygame.init().
    # buffer=2048 gives the MP3 decoder enough headroom to avoid start-of-clip
    # underruns.  The explicit mixer.init() call after pygame.init() ensures the
    # subsystem is fully ready before the first voice line is loaded.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

    flags = 0
    if WINDOW_FRAMELESS:
        flags |= pygame.NOFRAME

    icon_surf = pygame.image.load(str(resource_path("assets/heroes/abrams/icon.png")))
    pygame.display.set_icon(icon_surf)

    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), flags)
    pygame.display.set_caption(f"Deadlock Draft Viewer v{VERSION}")
    clock = pygame.time.Clock()

    # Wraps the window pygame.display.set_mode() already created, so it can
    # be hidden/shown from the status window without a second window.
    main_window = _sdl2_video.Window.from_display_module() if _SDL2_AVAILABLE else None
    main_window_shown    = True
    draft_overlay_shown  = True

    # if TRANSPARENT_BACKGROUND:
    #     hwnd = pygame.display.get_wm_info()["window"]
    #     make_window_transparent(hwnd)

    # Fonts
    title_font   = pygame.font.SysFont("segoeui", 52, bold=True)
    button_font  = pygame.font.SysFont("segoeui", 30)
    version_font = pygame.font.SysFont("segoeui", 18)

    # Menu / team-select / settings button layouts are rebuilt from scratch
    # whenever the window resolution changes (see the SETTINGS STATE below),
    # so they're built by small helpers instead of being one-off literals.
    def layout_menu_buttons():
        cx = WINDOW_WIDTH  // 2
        cy = WINDOW_HEIGHT // 2
        btn_w, btn_h, gap = 320, 70, 20
        total_h = 3 * btn_h + 2 * gap
        top = cy - total_h // 2
        manual = Button((cx - btn_w // 2, top, btn_w, btn_h), "Manual Draft", button_font)
        imp    = Button((cx - btn_w // 2, top + (btn_h + gap), btn_w, btn_h), "Import Draft", button_font)
        sett   = Button((cx - btn_w // 2, top + 2 * (btn_h + gap), btn_w, btn_h), "Settings", button_font)
        return cx, cy, manual, imp, sett

    def layout_team_select_buttons():
        cx = WINDOW_WIDTH  // 2
        cy = WINDOW_HEIGHT // 2
        btn_w, btn_h = 320, 70
        team1 = Button((cx - btn_w // 2, cy - btn_h - 20, btn_w, btn_h), "Team 1 First", button_font)
        team2 = Button((cx - btn_w // 2, cy + 20, btn_w, btn_h), "Team 2 First", button_font)
        return cx, cy, team1, team2

    def layout_settings_buttons():
        cx = WINDOW_WIDTH  // 2
        cy = WINDOW_HEIGHT // 2
        btn_w, btn_h, gap = 260, 50, 14
        n = len(RESOLUTION_PRESETS)
        total_h = n * btn_h + (n - 1) * gap
        top = cy - total_h // 2 + 20
        presets = []
        for i, (w, h) in enumerate(RESOLUTION_PRESETS):
            rect = (cx - btn_w // 2, top + i * (btn_h + gap), btn_w, btn_h)
            presets.append((Button(rect, f"{w} x {h}", button_font), (w, h)))
        back = Button((cx - 100, top + total_h + 30, 200, 50), "Back", button_font)
        return cx, cy, presets, back

    cx, cy, btn_manual, btn_import, btn_settings = layout_menu_buttons()
    _, _, btn_team1_first, btn_team2_first = layout_team_select_buttons()
    _, _, settings_preset_buttons, btn_settings_back = layout_settings_buttons()

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
    render_started_at  = 0      # ticks when current render began
    render_fade        = "idle"  # "idle" | "in" | "visible" | "out"
    render_alpha       = 0       # current surface alpha (0-255)
    render_fade_out_at = 0       # ticks when fade-out began

    listener      = None   # Started only when Manual Draft is chosen
    draft_overlay = None    # Created when draft mode is entered
    status_window = None    # Created when draft mode is entered

    # Import draft playback state
    import_queue         = []          # list of (Hero, action_type) to replay
    import_next_at       = 0           # ticks when to trigger the next import action
    import_active_action = None        # action_type of the currently-displaying step

    # Shared args for StatusWindow so we don't repeat them in each branch
    _sw_kwargs = dict(
        hero_names=list(hero_map.keys()),
        on_hero_select=lambda name: activate_hero(hero_map[name]) if name in hero_map else None,
        on_slot_edit=start_slot_edit,
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
                    display_state, now, unlock_at, draft_manager, events,
                    edit_target
                )
                if main_window is not None and status_window.main_window_visible != main_window_shown:
                    main_window_shown = status_window.main_window_visible
                    (main_window.show() if main_window_shown else main_window.hide())
                if draft_overlay is not None and status_window.draft_overlay_visible != draft_overlay_shown:
                    draft_overlay_shown = status_window.draft_overlay_visible
                    (draft_overlay.show() if draft_overlay_shown else draft_overlay.hide())
                if draft_overlay is not None:
                    draft_overlay.set_flip(1, status_window.flip_hidden_king_cards)
                    draft_overlay.set_flip(2, status_window.flip_archmother_cards)

            for event in events:
                if event.type == pygame.QUIT:
                    window_open = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if app_state == "settings":
                        app_state = "menu"
                    elif app_state in ("menu", "import_draft"):
                        window_open = False

            # ------------------------------------------------------------------
            # MENU STATE
            # ------------------------------------------------------------------
            if app_state == "menu":
                for event in events:
                    if btn_manual.is_clicked(event):
                        app_state = "team_select"
                    elif btn_settings.is_clicked(event):
                        app_state = "settings"
                    elif btn_import.is_clicked(event):
                        data = import_draft()
                        if data:
                            first_entry_team = data[0].get("team", "team1")
                            first_team = 1 if first_entry_team == "team1" else 2
                            draft_manager.start(first_team)

                            import_queue.clear()
                            for entry in data:
                                h_name      = entry.get("hero", "")
                                action_type = entry.get("type", "pick").lower()
                                folder_name = resolve_hero_name(h_name)
                                if folder_name in hero_map:
                                    import_queue.append((hero_map[folder_name], action_type))
                                else:
                                    print(f"[WARN] Import: unknown hero '{h_name}' — skipped")

                            if import_queue:
                                draft_overlay        = DraftOverlayWindow()
                                status_window        = StatusWindow(**_sw_kwargs)
                                main_window_shown     = True
                                draft_overlay_shown   = True
                                edit_target           = None
                                pending_edit_target   = None
                                import_next_at       = now + IMPORT_START_DELAY_MS
                                import_active_action = None
                                app_state            = "import_draft"
                                print(f"Import Draft — {len(import_queue)} actions queued.")
                                print("-" * 50)

                screen.fill((20, 20, 30))
                title_surf = title_font.render("Deadlock Draft Viewer", True, (220, 220, 220))
                screen.blit(title_surf, title_surf.get_rect(center=(cx, cy - 190)))
                btn_manual.draw(screen)
                btn_import.draw(screen)
                btn_settings.draw(screen)
                ver_surf = version_font.render(f"v{VERSION}", True, (120, 120, 140))
                screen.blit(ver_surf, ver_surf.get_rect(bottomright=(WINDOW_WIDTH - 12, WINDOW_HEIGHT - 12)))
                pygame.display.flip()
                clock.tick(60)
                continue

            # ------------------------------------------------------------------
            # SETTINGS STATE
            # ------------------------------------------------------------------
            if app_state == "settings":
                for event in events:
                    if btn_settings_back.is_clicked(event):
                        app_state = "menu"
                    else:
                        for btn, (w, h) in settings_preset_buttons:
                            if btn.is_clicked(event) and (w, h) != (WINDOW_WIDTH, WINDOW_HEIGHT):
                                WINDOW_WIDTH, WINDOW_HEIGHT = w, h
                                screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), flags)
                                if _SDL2_AVAILABLE:
                                    main_window = _sdl2_video.Window.from_display_module()
                                # Cached hero surfaces are scaled to the old
                                # resolution; drop them so they're rebuilt.
                                hero_cache.clear()
                                cx, cy, btn_manual, btn_import, btn_settings = layout_menu_buttons()
                                _, _, btn_team1_first, btn_team2_first = layout_team_select_buttons()
                                _, _, settings_preset_buttons, btn_settings_back = layout_settings_buttons()
                                print(f"Resolution changed to {WINDOW_WIDTH}x{WINDOW_HEIGHT}")
                                break

                screen.fill((20, 20, 30))
                title_surf = title_font.render("Settings", True, (220, 220, 220))
                screen.blit(title_surf, title_surf.get_rect(center=(cx, cy - 190)))
                subtitle_surf = version_font.render(
                    f"Resolution \u2014 current: {WINDOW_WIDTH} x {WINDOW_HEIGHT}",
                    True, (180, 180, 190)
                )
                screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(cx, cy - 130)))
                for btn, (w, h) in settings_preset_buttons:
                    btn.draw(screen)
                    if (w, h) == (WINDOW_WIDTH, WINDOW_HEIGHT):
                        tag_surf = version_font.render("current", True, (166, 227, 161))
                        screen.blit(tag_surf, tag_surf.get_rect(midleft=(btn.rect.right + 12, btn.rect.centery)))
                btn_settings_back.draw(screen)
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
                        main_window_shown   = True
                        draft_overlay_shown = True
                        edit_target         = None
                        pending_edit_target = None
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
                        main_window_shown   = True
                        draft_overlay_shown = True
                        edit_target         = None
                        pending_edit_target = None
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

            # Pick up a pending hero from the key listener thread (manual draft only)
            if app_state == "draft" and pending_hero is not None:
                hero = pending_hero
                pending_hero = None

                edit_info = pending_edit_target
                pending_edit_target = None

                if edit_info is not None:
                    edit_team, action_type, edit_index = edit_info
                    draft_manager.set_hero(edit_team, action_type, edit_index, hero.name)
                    team_name = TEAM_NAMES[edit_team]
                    print(f"[Edit] {team_name}: {action_type.capitalize()} slot "
                          f"{edit_index + 1} -> {hero.name.capitalize()}")
                else:
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

                play_voice_line(hero, action_type)

                if hero.name not in hero_cache:
                    try:
                        hero_cache[hero.name] = load_hero_surfaces(hero)
                    except Exception as e:
                        print(f"Failed to load surfaces for '{hero.name}': {e}")
                        hero_cache[hero.name] = (None, None, None)

                render_surf, card_surf, crit_surf = hero_cache[hero.name]
                active_hero       = hero
                unlock_at         = float('inf')
                display_state     = "crit" if action_type == "ban" else "render"
                render_started_at = now
                render_fade       = "in"
                render_alpha      = 0

            # ------------------------------------------------------------------
            # IMPORT DRAFT — auto-advance through the queue on a timer
            # ------------------------------------------------------------------
            if app_state == "import_draft":
                if now >= import_next_at:
                    if import_queue:
                        import_next_at       = float('inf')
                        next_hero, next_action_type = import_queue.pop(0)
                        import_active_action = next_action_type

                        result = draft_manager.assign(next_hero.name)
                        if result:
                            team, action = result
                            team_name = TEAM_NAMES[team]
                            print(f"[Import {draft_manager.step}/{len(DRAFT_ORDER)}] "
                                  f"{team_name}: {action.capitalize()} -> "
                                  f"{next_hero.name.capitalize()}")

                        play_voice_line(next_hero, next_action_type)

                        if next_hero.name not in hero_cache:
                            try:
                                hero_cache[next_hero.name] = load_hero_surfaces(next_hero)
                            except Exception as e:
                                print(f"Failed to load surfaces for '{next_hero.name}': {e}")
                                hero_cache[next_hero.name] = (None, None, None)

                        render_surf, card_surf, crit_surf = hero_cache[next_hero.name]
                        active_hero       = next_hero
                        unlock_at         = float('inf')
                        display_state     = "crit" if next_action_type == "ban" else "render"
                        render_started_at = now
                        render_fade       = "in"
                        render_alpha      = 0
                    else:
                        import_next_at       = float('inf')
                        import_active_action = None
                        print("Import draft complete.")

                # Detect when the current step has settled, then start the wait timer
                elif import_active_action == "ban" and display_state == "crit":
                    if (unlock_at != float('inf') and now >= unlock_at
                            and import_next_at == float('inf')):
                        import_next_at = now + IMPORT_BAN_WAIT_MS

                elif import_active_action == "pick" and display_state == "card":
                    if now >= unlock_at and import_next_at == float('inf'):
                        import_next_at = now + IMPORT_PICK_WAIT_MS

                # While waiting, preload the next hero's surfaces so the cache
                # is warm when the timer fires — no blocking after play_voice_line().
                if (import_queue
                        and import_next_at != float('inf')
                        and import_queue[0][0].name not in hero_cache):
                    nxt = import_queue[0][0]
                    try:
                        hero_cache[nxt.name] = load_hero_surfaces(nxt)
                    except Exception as e:
                        print(f"[Import] Preload failed for '{nxt.name}': {e}")
                        hero_cache[nxt.name] = (None, None, None)

            # --- Render fade state machine ---
            if display_state == "render":
                if render_fade == "in":
                    elapsed      = now - render_started_at
                    render_alpha = min(255, int(255 * elapsed / FADE_IN_MS))
                    if render_alpha >= 255:
                        render_fade = "visible"

                elif render_fade == "visible":
                    voice_done = not pygame.mixer.music.get_busy()
                    elapsed    = now - render_started_at
                    if voice_done and elapsed >= RENDER_MIN_MS:
                        render_fade        = "out"
                        render_fade_out_at = now

                elif render_fade == "out":
                    elapsed      = now - render_fade_out_at
                    render_alpha = max(0, 255 - int(255 * elapsed / FADE_OUT_MS))
                    if render_alpha <= 0:
                        display_state = "card"
                        unlock_at     = now + CARD_LOCKOUT_MS
                        render_fade   = "idle"

            # Crit transition when voice line finishes
            elif display_state == "crit" and not pygame.mixer.music.get_busy():
                if unlock_at == float('inf'):
                    unlock_at = now + CARD_LOCKOUT_MS

            # Draw main window
            if solid_background:
                screen.fill(SOLID_TEST_COLOR)
            elif TRANSPARENT_BACKGROUND:
                screen.fill(TRANSPARENT_COLOR)
            else:
                screen.fill((0, 0, 0))

            # Render shown with current fade alpha; set_alpha() multiplies
            # with per-pixel alpha so transparent areas stay transparent.
            if display_state == "render" and render_surf is not None:
                render_surf.set_alpha(render_alpha)
                rect = render_surf.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
                screen.blit(render_surf, rect)
                render_surf.set_alpha(255)  # reset for cache reuse

            # Update the draft overlay every frame
            if draft_overlay is not None:
                draft_overlay.update(now, draft_manager.slots, hero_map, solid_background,
                                     display_state=display_state)

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


def _selftest_pynput() -> int:
    """
    Diagnostic: construct and start a pynput keyboard.Listener exactly as
    Manual Draft mode does, and report success/failure.

    pynput selects its platform backend (e.g. pynput.keyboard._darwin) via
    a dynamically computed importlib.import_module() call, which static
    analyzers like PyInstaller's can't trace -- so it's easy for a frozen
    build to silently ship without that backend module (or without
    mac_pynput_fix.py's patch actually taking effect), reintroducing the
    macOS TIS/TSM main-thread crash. Run this against a built exe with:
        <executable> --selftest-pynput
    """
    import time
    try:
        listener = keyboard.Listener(on_press=lambda k: None, on_release=lambda k: None)
        listener.start()
        time.sleep(1)
        listener.stop()
        listener.join()
        print("SELFTEST_PYNPUT_OK")
        return 0
    except Exception as e:
        print(f"SELFTEST_PYNPUT_FAILED: {e!r}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest-pynput":
        sys.exit(_selftest_pynput())
    if len(sys.argv) >= 3 and sys.argv[1] == file_dialog.INTERNAL_FLAG:
        # Re-invoked as an isolated subprocess to show a native file dialog
        # (see file_dialog.py) — run it and exit without starting pygame.
        file_dialog.run_internal_dialog(sys.argv[2])
        sys.exit(0)
    main()
