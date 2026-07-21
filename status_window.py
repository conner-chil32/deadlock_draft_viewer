import tkinter as tk

from draft import DraftSlots
from heroes import HERO_REGISTRY


class StatusWindow:
    """
    A self-contained tkinter window that shows live draft state.
    Call update() once per frame from the main loop.
    """

    # Colour palette
    WIN_BG      = "#1e1e2e"
    WIN_FG      = "#cdd6f4"
    LBL_FG      = "#89b4fa"
    LOCKED_FG   = "#f38ba8"
    UNLOCKED_FG = "#a6e3a1"
    DIM_FG      = "#585b70"
    SEP_COLOR   = "#313244"
    SLOT_BG     = "#313244"
    SLOT_BAN_FG = "#f38ba8"

    # Fonts
    FONT_LABEL = ("Segoe UI",  9, "bold")
    FONT_VALUE = ("Consolas", 10)
    FONT_KEY   = ("Consolas",  9, "bold")
    FONT_DESC  = ("Segoe UI",  9)
    FONT_TEAM  = ("Segoe UI",  9, "bold")
    FONT_SLOT  = ("Consolas",  8)

    EMPTY_SLOT = "\u2500\u2500\u2500\u2500\u2500\u2500"   # ──────
    SLOT_W     = 7

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Draft Viewer \u2014 Status")
        self.root.geometry("680x340")
        self.root.resizable(False, False)
        self.root.configure(bg=self.WIN_BG)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        self._init_vars()
        self._build()

    # ------------------------------------------------------------------
    # StringVar initialisation
    # ------------------------------------------------------------------

    def _init_vars(self):
        self.sv_state        = tk.StringVar(value="Menu")
        self.sv_bg_mode      = tk.StringVar(value="Chroma Key")
        self.sv_hero         = tk.StringVar(value="\u2014")
        self.sv_hero_state   = tk.StringVar(value="\u2014")
        self.sv_locked       = tk.StringVar(value="\u2014")
        self.sv_draft_step   = tk.StringVar(value="\u2014")
        self.sv_draft_action = tk.StringVar(value="\u2014")

        self.sv_t1_picks = [tk.StringVar(value=self.EMPTY_SLOT) for _ in range(DraftSlots.NUM_PICKS)]
        self.sv_t1_bans  = [tk.StringVar(value=self.EMPTY_SLOT) for _ in range(DraftSlots.NUM_BANS)]
        self.sv_t2_picks = [tk.StringVar(value=self.EMPTY_SLOT) for _ in range(DraftSlots.NUM_PICKS)]
        self.sv_t2_bans  = [tk.StringVar(value=self.EMPTY_SLOT) for _ in range(DraftSlots.NUM_BANS)]

        self._locked_lbl = None   # Label reference for fg colour changes

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build(self):
        cols = tk.Frame(self.root, bg=self.WIN_BG)
        cols.pack(fill="both", expand=True)

        left_col = tk.Frame(cols, bg=self.WIN_BG)
        left_col.pack(side="left", fill="y")
        tk.Frame(cols, bg=self.SEP_COLOR, width=2).pack(side="left", fill="y", padx=4)
        right_col = tk.Frame(cols, bg=self.WIN_BG)
        right_col.pack(side="left", fill="both", expand=True)

        self._build_left(left_col)
        self._build_right(right_col)

    def _build_left(self, col):
        self._sep(col, (8, 4))
        self._row(col, "State:",       self.sv_state)
        self._row(col, "Background:",  self.sv_bg_mode)
        self._row(col, "Hero:",        self.sv_hero)
        self._row(col, "Hero State:",  self.sv_hero_state)
        self._locked_lbl = self._row(col, "Hero Select:", self.sv_locked)
        self._row(col, "Draft Step:",  self.sv_draft_step)
        self._row(col, "Next Action:", self.sv_draft_action)

        self._sep(col, (6, 4))
        tk.Label(col, text="  Keybinds", bg=self.WIN_BG, fg=self.LBL_FG,
                 font=self.FONT_TEAM, anchor="w").pack(fill="x", padx=10)

        keybinds = (
            [("F1",  "Toggle background mode")]
            + [(self._fmt_combo(c), f"Hero: {n.capitalize()}") for c, n, _ in HERO_REGISTRY]
            + [("ESC", "Exit")]
        )
        for key, desc in keybinds:
            row = tk.Frame(col, bg=self.WIN_BG)
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=key,  bg=self.WIN_BG, fg=self.WIN_FG,
                     font=self.FONT_KEY,  width=10, anchor="w").pack(side="left")
            tk.Label(row, text=desc, bg=self.WIN_BG, fg=self.DIM_FG,
                     font=self.FONT_DESC, anchor="w").pack(side="left")

        self._sep(col, (6, 0))

    def _build_right(self, col):
        self._sep(col, (8, 0))
        tk.Label(col, text="  Draft Slots", bg=self.WIN_BG, fg=self.LBL_FG,
                 font=self.FONT_TEAM, anchor="w").pack(fill="x", padx=8)
        self._team_block(col, "Hidden King", self.sv_t1_picks, self.sv_t1_bans)
        tk.Frame(col, bg=self.SEP_COLOR, height=1).pack(fill="x", padx=8, pady=(6, 0))
        self._team_block(col, "ArchMother",  self.sv_t2_picks, self.sv_t2_bans)
        self._sep(col, (6, 0))

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _sep(self, parent, pady=(4, 4)):
        tk.Frame(parent, bg=self.SEP_COLOR, height=2).pack(fill="x", pady=pady)

    def _row(self, parent, label_text, var) -> tk.Label:
        frame = tk.Frame(parent, bg=self.WIN_BG)
        frame.pack(fill="x", padx=10, pady=3)
        tk.Label(frame, text=label_text, bg=self.WIN_BG, fg=self.LBL_FG,
                 font=self.FONT_LABEL, anchor="w", width=14).pack(side="left")
        lbl = tk.Label(frame, textvariable=var, bg=self.WIN_BG,
                       fg=self.WIN_FG, font=self.FONT_VALUE, anchor="w")
        lbl.pack(side="left")
        return lbl

    def _slot_row(self, parent, label_text, slot_vars, fg):
        row = tk.Frame(parent, bg=self.WIN_BG)
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text=label_text, bg=self.WIN_BG, fg=self.LBL_FG,
                 font=self.FONT_LABEL, width=5, anchor="w").pack(side="left")
        for var in slot_vars:
            tk.Label(row, textvariable=var, bg=self.SLOT_BG, fg=fg,
                     font=self.FONT_SLOT, width=self.SLOT_W,
                     relief="flat", padx=2, anchor="center").pack(side="left", padx=1)

    def _team_block(self, parent, team_label, pick_vars, ban_vars):
        tk.Label(parent, text=team_label, bg=self.WIN_BG, fg=self.WIN_FG,
                 font=self.FONT_TEAM, anchor="w").pack(fill="x", padx=8, pady=(8, 0))
        self._slot_row(parent, "Picks:", pick_vars, self.WIN_FG)
        self._slot_row(parent, "Bans:",  ban_vars,  self.SLOT_BAN_FG)

    @staticmethod
    def _fmt_combo(combo: str) -> str:
        return "+".join(p.capitalize() for p in combo.split("+"))

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(self, app_state: str, solid_background: bool,
               active_hero, display_state: str,
               now: int, unlock_at: float, draft_manager) -> None:
        """Refresh all labels and pump the tkinter event loop."""
        self.sv_state.set(app_state.replace("_", " ").title())
        self.sv_bg_mode.set("Solid (OBS)" if solid_background else "Chroma Key")
        self.sv_hero.set(active_hero.name.capitalize() if active_hero else "\u2014")
        self.sv_hero_state.set(display_state.capitalize() if app_state == "draft" else "\u2014")

        if app_state == "draft":
            is_locked = now < unlock_at
            self.sv_locked.set("Locked" if is_locked else "Unlocked")
            self._locked_lbl.config(fg=self.LOCKED_FG if is_locked else self.UNLOCKED_FG)
            self.sv_draft_step.set(draft_manager.step_label())
            self.sv_draft_action.set(draft_manager.current_label())
        else:
            self.sv_locked.set("\u2014")
            self._locked_lbl.config(fg=self.WIN_FG)
            self.sv_draft_step.set("\u2014")
            self.sv_draft_action.set("\u2014")

        self._update_slots(draft_manager.slots)
        self.root.update()

    def _update_slots(self, slots) -> None:
        for i, v in enumerate(self.sv_t1_picks):
            v.set(slots.team1_picks[i] or self.EMPTY_SLOT)
        for i, v in enumerate(self.sv_t1_bans):
            v.set(slots.team1_bans[i] or self.EMPTY_SLOT)
        for i, v in enumerate(self.sv_t2_picks):
            v.set(slots.team2_picks[i] or self.EMPTY_SLOT)
        for i, v in enumerate(self.sv_t2_bans):
            v.set(slots.team2_bans[i] or self.EMPTY_SLOT)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass
