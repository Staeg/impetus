"""Helpers for keeping pending sub-phase UIs open across partial results."""

from __future__ import annotations

from typing import Any, Mapping

from shared.protocol import SubPhase


_SUBPHASE_STATE_KEYS: dict[str, str] = {
    SubPhase.CHANGE_CHOICE: "change_cards",
    SubPhase.RESTRAIN_CHOICE: "change_cards",
    SubPhase.SHAPING_CHOICE: "change_cards",
    SubPhase.ADAPTATION_CHOICE: "change_cards",
    SubPhase.SPOILS_CHOICE: "spoils_entries",
    SubPhase.SPOILS_CHANGE_CHOICE: "spoils_change_entries",
    SubPhase.SPOILS_EXPAND_CHOICE: "spoils_expand_choices",
    SubPhase.WINNER_CHOICE: "winner_choice_wars",
    SubPhase.BATTLEGROUND_CHOICE: "battleground_choice_entries",
    SubPhase.WAR_SUPPORT_CHOICE: "war_support_entries",
    SubPhase.EJECTION_CHOICE: "ejection_pending",
    SubPhase.EXPAND_CHOICE: "expand_choice_hexes",
    SubPhase.RESPAWN_CHOICE: "respawn_choice_hexes",
}


def should_preserve_subphase(active_sub_phase: str | None, state: Mapping[str, Any]) -> bool:
    """Return True when local pending-choice state should keep a sub-phase open.

    The client receives shared snapshots after every player's submission. If the
    local player still has unresolved choice UI state, we must keep that
    sub-phase active instead of dropping back to the main phase from the
    snapshot.
    """

    if not active_sub_phase:
        return False
    state_key = _SUBPHASE_STATE_KEYS.get(active_sub_phase)
    if not state_key:
        return False
    return bool(state.get(state_key))
