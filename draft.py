class DraftSlots:
    """
    Tracks hero assignments for each team's picks and bans.

    Each team has NUM_PICKS pick slots and NUM_BANS ban slots.
    A slot is None when empty, or a hero name string when filled.
    """

    NUM_PICKS = 6
    NUM_BANS  = 2

    def __init__(self):
        self.reset()

    def reset(self):
        """Clear all slots."""
        self.team1_picks = [None] * self.NUM_PICKS
        self.team1_bans  = [None] * self.NUM_BANS
        self.team2_picks = [None] * self.NUM_PICKS
        self.team2_bans  = [None] * self.NUM_BANS

    # ------------------------------------------------------------------
    # Slot access helpers
    # ------------------------------------------------------------------

    def _picks(self, team: int) -> list:
        return self.team1_picks if team == 1 else self.team2_picks

    def _bans(self, team: int) -> list:
        return self.team1_bans if team == 1 else self.team2_bans

    def next_empty_pick(self, team: int) -> int | None:
        """Return the index of the next empty pick slot, or None if full."""
        for i, s in enumerate(self._picks(team)):
            if s is None:
                return i
        return None

    def next_empty_ban(self, team: int) -> int | None:
        """Return the index of the next empty ban slot, or None if full."""
        for i, s in enumerate(self._bans(team)):
            if s is None:
                return i
        return None

    def assign_pick(self, team: int, hero_name: str) -> bool:
        """Fill the next available pick slot. Returns True if successful."""
        idx = self.next_empty_pick(team)
        if idx is None:
            return False
        self._picks(team)[idx] = hero_name
        return True

    def assign_ban(self, team: int, hero_name: str) -> bool:
        """Fill the next available ban slot. Returns True if successful."""
        idx = self.next_empty_ban(team)
        if idx is None:
            return False
        self._bans(team)[idx] = hero_name
        return True

    def __repr__(self) -> str:
        return (
            f"DraftSlots("
            f"t1_picks={self.team1_picks}, t1_bans={self.team1_bans}, "
            f"t2_picks={self.team2_picks}, t2_bans={self.team2_bans})"
        )
