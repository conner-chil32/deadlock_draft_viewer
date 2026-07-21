# ---------------------------------------------------------------------------
# Draft order
# ---------------------------------------------------------------------------
# Each entry is (relative_team, action_type).
# relative_team is "first" or "second" — resolved against the chosen first_team
# at runtime so the order is symmetric regardless of which team goes first.

DRAFT_ORDER = [
    ("first",  "ban"),   # 1
    ("second", "ban"),   # 2
    ("first",  "pick"),  # 3
    ("second", "pick"),  # 4
    ("second", "pick"),  # 5
    ("first",  "pick"),  # 6
    ("first",  "pick"),  # 7
    ("second", "pick"),  # 8
    ("second", "ban"),   # 9
    ("first",  "ban"),   # 10
    ("second", "pick"),  # 11
    ("first",  "pick"),  # 12
    ("first",  "pick"),  # 13
    ("second", "pick"),  # 14
    ("second", "pick"),  # 15
    ("first",  "pick"),  # 16
]


# ---------------------------------------------------------------------------
# Slot storage
# ---------------------------------------------------------------------------

class DraftSlots:
    """
    Tracks hero assignments for each team's picks and bans.
    Slots are None when empty, hero-name strings when filled.
    """

    NUM_PICKS = 6
    NUM_BANS  = 2

    def __init__(self):
        self.reset()

    def reset(self):
        self.team1_picks = [None] * self.NUM_PICKS
        self.team1_bans  = [None] * self.NUM_BANS
        self.team2_picks = [None] * self.NUM_PICKS
        self.team2_bans  = [None] * self.NUM_BANS

    def _picks(self, team: int) -> list:
        return self.team1_picks if team == 1 else self.team2_picks

    def _bans(self, team: int) -> list:
        return self.team1_bans if team == 1 else self.team2_bans

    def assign_pick(self, team: int, hero_name: str) -> bool:
        slots = self._picks(team)
        for i, s in enumerate(slots):
            if s is None:
                slots[i] = hero_name
                return True
        return False

    def assign_ban(self, team: int, hero_name: str) -> bool:
        slots = self._bans(team)
        for i, s in enumerate(slots):
            if s is None:
                slots[i] = hero_name
                return True
        return False


# ---------------------------------------------------------------------------
# Draft manager
# ---------------------------------------------------------------------------

TEAM_NAMES = {1: "Hidden King", 2: "ArchMother"}


class DraftManager:
    """
    Tracks the current position in DRAFT_ORDER and routes hero assignments
    to the correct DraftSlots team/type.
    """

    def __init__(self):
        self.slots      = DraftSlots()
        self.step       = 0          # current index into DRAFT_ORDER
        self.first_team = 1          # actual team number that goes "first"

    def start(self, first_team: int):
        """Reset and begin a new draft with the given team going first."""
        self.first_team = first_team
        self.step       = 0
        self.slots.reset()

    # ------------------------------------------------------------------
    # Current-step queries
    # ------------------------------------------------------------------

    @property
    def is_complete(self) -> bool:
        return self.step >= len(DRAFT_ORDER)

    def current_team(self) -> int | None:
        """Actual team number (1 or 2) whose turn it is."""
        if self.is_complete:
            return None
        relative, _ = DRAFT_ORDER[self.step]
        return self.first_team if relative == "first" else 3 - self.first_team

    def current_action_type(self) -> str | None:
        """'pick' or 'ban' for the current step."""
        if self.is_complete:
            return None
        _, action = DRAFT_ORDER[self.step]
        return action

    def current_label(self) -> str:
        """Human-readable description of the current step."""
        if self.is_complete:
            return "Draft Complete"
        team = self.current_team()
        action = self.current_action_type().capitalize()
        return f"{TEAM_NAMES[team]}: {action}"

    def step_label(self) -> str:
        """e.g. '3 / 16'."""
        if self.is_complete:
            return f"{len(DRAFT_ORDER)} / {len(DRAFT_ORDER)}"
        return f"{self.step + 1} / {len(DRAFT_ORDER)}"

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def assign(self, hero_name: str) -> tuple[int, str] | None:
        """
        Assign a hero to the current draft slot.
        Returns (team, action_type) on success, None if draft is complete.
        """
        if self.is_complete:
            return None
        team   = self.current_team()
        action = self.current_action_type()
        if action == "pick":
            self.slots.assign_pick(team, hero_name)
        else:
            self.slots.assign_ban(team, hero_name)
        self.step += 1
        return team, action
