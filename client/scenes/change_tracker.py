"""Tracks per-turn changes to faction state for display in the faction panel."""

import copy
from dataclasses import dataclass, field
from client.faction_names import faction_full_name


@dataclass
class ChangeEntry:
    field: str          # "gold", "territories", "regard", "modifier", "guiding_spirit", "worship_spirit"
    delta: int | None   # numerical delta (None for qualitative)
    label: str          # display label e.g. "Trade", "Steal (Mesa)"
    log_index: int      # index into event_log list
    target: str | None = None   # for regard: which neighbor faction. for modifier: which type
    old_value: str | None = None  # for qualitative changes: the old name
    new_value: str | None = None  # for qualitative changes: the new name


class FactionChangeTracker:
    """Accumulates per-faction change entries across a turn for panel display."""

    def __init__(self):
        self.old_state: dict[str, dict] = {}   # faction_id -> snapshot of faction data
        self.old_spirits: dict[str, dict] = {}  # spirit_id -> snapshot of spirit data
        self.changes: dict[str, list[ChangeEntry]] = {}  # faction_id -> list of changes
        # Previous turn's data, shown until current turn has changes
        self.prev_old_state: dict[str, dict] = {}
        self.prev_changes: dict[str, list[ChangeEntry]] = {}

    def snapshot_and_reset(self, factions: dict, spirits: dict):
        """Deep-copy current faction state and clear accumulated changes.
        Preserves previous turn's data so deltas remain visible until new events arrive."""
        self.prev_old_state = self.old_state
        self.prev_changes = self.changes
        self.old_state = copy.deepcopy(factions)
        self.old_spirits = copy.deepcopy(spirits)
        self.changes = {}

    def _use_prev(self) -> bool:
        """True when current turn has no changes yet, so we show previous turn's."""
        return not self.changes and bool(self.prev_changes)

    def get_changes(self, faction_id: str) -> list[ChangeEntry]:
        source = self.prev_changes if self._use_prev() else self.changes
        return source.get(faction_id, [])

    def get_field_changes(self, faction_id: str, field_name: str,
                          target: str | None = None) -> list[ChangeEntry]:
        """Get changes for a specific faction+field (optionally filtered by target)."""
        return [
            c for c in self.get_changes(faction_id)
            if c.field == field_name and (target is None or c.target == target)
        ]

    def get_old_value(self, faction_id: str, field_name: str):
        """Get the snapshotted old value for a faction field."""
        state = self.prev_old_state if self._use_prev() else self.old_state
        fd = state.get(faction_id, {})
        if field_name == "gold":
            return fd.get("gold", 0)
        elif field_name == "territories":
            return len(fd.get("territories", []))
        elif field_name == "guiding_spirit":
            return fd.get("guiding_spirit")
        elif field_name == "worship_spirit":
            return fd.get("worship_spirit")
        return None

    def get_old_regard(self, faction_id: str, neighbor_id: str) -> int:
        state = self.prev_old_state if self._use_prev() else self.old_state
        fd = state.get(faction_id, {})
        return fd.get("regard", {}).get(neighbor_id, 0)

    def _add(self, faction_id: str, entry: ChangeEntry):
        self.changes.setdefault(faction_id, []).append(entry)

    def process_event(self, event: dict, log_index: int, factions: dict, spirits: dict):
        """Process a game event and record change entries."""
        etype = event.get("type", "")
        faction_id = event.get("faction", "")

        if etype == "trade":
            gold = event.get("gold_gained", 0)
            if gold:
                self._add(faction_id, ChangeEntry(
                    field="gold", delta=gold,
                    label="Trade", log_index=log_index,
                ))
            regard_gain = event.get("regard_gain", 0)
            co_traders = event.get("co_traders", [])
            for nb in co_traders:
                if regard_gain:
                    self._add(faction_id, ChangeEntry(
                        field="regard", delta=regard_gain,
                        label="Trade", log_index=log_index,
                        target=nb,
                    ))
                    self._add(nb, ChangeEntry(
                        field="regard", delta=regard_gain,
                        label=f"Trade ({faction_full_name(faction_id)})",
                        log_index=log_index,
                        target=faction_id,
                    ))

        elif etype == "trade_spoils_bonus":
            gold = event.get("gold_gained", 0)
            if gold:
                self._add(faction_id, ChangeEntry(
                    field="gold", delta=gold,
                    label="Spoils Trade", log_index=log_index,
                ))
            regard_gain = event.get("regard_gain", 0)
            co_traders = event.get("co_traders", [])
            for nb in co_traders:
                if regard_gain:
                    self._add(faction_id, ChangeEntry(
                        field="regard", delta=regard_gain,
                        label="Spoils Trade", log_index=log_index,
                        target=nb,
                    ))
                    self._add(nb, ChangeEntry(
                        field="regard", delta=regard_gain,
                        label=f"Spoils Trade ({faction_full_name(faction_id)})",
                        log_index=log_index,
                        target=faction_id,
                    ))

        elif etype == "steal":
            gold = event.get("gold_gained", 0)
            penalty = event.get("regard_penalty", 1)
            neighbors = event.get("neighbors", [])
            if gold:
                self._add(faction_id, ChangeEntry(
                    field="gold", delta=gold,
                    label="Steal", log_index=log_index,
                ))
            for nb in neighbors:
                if penalty:
                    # Derive visible victim gold loss without going below zero,
                    # using this tracker's current old+delta view.
                    old_gold = self.get_old_value(nb, "gold") or 0
                    tracked_delta = sum(
                        c.delta or 0
                        for c in self.get_field_changes(nb, "gold")
                    )
                    current_tracked_gold = max(0, old_gold + tracked_delta)
                    victim_loss = min(current_tracked_gold, penalty)
                    if victim_loss > 0:
                        self._add(nb, ChangeEntry(
                            field="gold", delta=-victim_loss,
                            label=f"Steal ({faction_full_name(faction_id)})",
                            log_index=log_index,
                        ))
                # Neighbor loses gold (we don't know exact per-neighbor amounts from the event)
                # Regard is bilateral; negate penalty (positive magnitude from server)
                if penalty:
                    self._add(faction_id, ChangeEntry(
                        field="regard", delta=-penalty,
                        label="Steal", log_index=log_index,
                        target=nb,
                    ))
                    self._add(nb, ChangeEntry(
                        field="regard", delta=-penalty,
                        label=f"Steal ({faction_full_name(faction_id)})",
                        log_index=log_index,
                        target=faction_id,
                    ))

        elif etype == "expand":
            cost = event.get("cost", 0)
            if cost:
                self._add(faction_id, ChangeEntry(
                    field="gold", delta=-cost,
                    label="Expand", log_index=log_index,
                ))
            self._add(faction_id, ChangeEntry(
                field="territories", delta=1,
                label="Expand", log_index=log_index,
            ))

        elif etype == "expand_failed":
            gold = event.get("gold_gained", 0)
            if gold:
                self._add(faction_id, ChangeEntry(
                    field="gold", delta=gold,
                    label="Expand (fail)", log_index=log_index,
                ))

        elif etype == "expand_spoils":
            self._add(faction_id, ChangeEntry(
                field="territories", delta=1,
                label="Spoils Expand", log_index=log_index,
            ))

        elif etype == "change":
            modifier = event.get("modifier", "?")
            self._add(faction_id, ChangeEntry(
                field="modifier", delta=1,
                label="Change", log_index=log_index,
                target=modifier,
            ))

        elif etype == "guided":
            spirit_id = event.get("spirit", "")
            spirit_name = spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            old_guiding = self.old_state.get(faction_id, {}).get("guiding_spirit")
            old_name = spirits.get(old_guiding, {}).get("name", old_guiding) if old_guiding else "none"
            self._add(faction_id, ChangeEntry(
                field="guiding_spirit", delta=None,
                label="Guided", log_index=log_index,
                old_value=old_name,
                new_value=spirit_name,
            ))

        elif etype == "ejected":
            spirit_id = event.get("spirit", "")
            spirit_name = spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            self._add(faction_id, ChangeEntry(
                field="guiding_spirit", delta=None,
                label="Ejected", log_index=log_index,
                old_value=spirit_name,
                new_value="none",
            ))

        elif etype == "worship_gained":
            spirit_id = event.get("spirit", "")
            spirit_name = spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            self._add(faction_id, ChangeEntry(
                field="worship_spirit", delta=None,
                label="Worship", log_index=log_index,
                old_value="none",
                new_value=spirit_name,
            ))

        elif etype == "worship_replaced":
            spirit_id = event.get("spirit", "")
            old_spirit_id = event.get("old_spirit", "")
            spirit_name = spirits.get(spirit_id, {}).get("name", spirit_id[:6])
            old_name = spirits.get(old_spirit_id, {}).get("name", old_spirit_id[:6])
            self._add(faction_id, ChangeEntry(
                field="worship_spirit", delta=None,
                label="Worship", log_index=log_index,
                old_value=old_name,
                new_value=spirit_name,
            ))
