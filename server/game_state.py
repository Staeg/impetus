"""Core game state machine and turn resolution."""

import random
from typing import Optional
from shared.constants import (
    Phase, AgendaType, IdolType, FACTION_NAMES, VP_TO_WIN,
    STARTING_INFLUENCE, CHANGE_DECK,
)
from shared.models import HexCoord, Idol, GameStateSnapshot
from server.hex_map import HexMap
from server.faction import Faction
from server.spirit import Spirit
from server.war import War
from server.agenda import resolve_agendas, draw_spoils_agenda, resolve_spoils, resolve_spoils_choice
from server.scoring import calculate_scoring


class GameState:
    """Authoritative game state. Drives the entire game flow."""

    def __init__(self):
        self.turn: int = 0
        self.phase: Phase = Phase.LOBBY
        self.hex_map = HexMap()
        self.factions: dict[str, Faction] = {}
        self.spirits: dict[str, Spirit] = {}
        self.wars: list[War] = []
        self.pending_actions: dict[str, dict] = {}
        # Drawn hands for current phase
        self.drawn_hands: dict[str, list] = {}
        # Spirits needing to submit ejection agenda choice
        self.ejection_pending: dict[str, str] = {}  # spirit_id -> faction_id
        # Spirits needing to submit change choice
        self.change_pending: dict[str, list] = {}  # spirit_id -> drawn change cards
        # Track trade factions for spoils
        self.normal_trade_factions: list[str] = []
        # Spoils of war choice pending (spirit_id -> pending data)
        self.spoils_pending: dict[str, dict] = {}

    def setup_game(self, player_info: list[dict]) -> list[dict]:
        """Initialize the game with the given players. Returns setup events.

        player_info: list of {spirit_id, name}
        """
        events = []

        # Create factions
        for faction_id in FACTION_NAMES:
            faction = Faction(faction_id)
            # Initialize regard with all other factions
            for other_id in FACTION_NAMES:
                if other_id != faction_id:
                    faction.regard[other_id] = 0
            self.factions[faction_id] = faction

        # Create spirits
        for info in player_info:
            spirit = Spirit(info["spirit_id"], info["name"])
            self.spirits[spirit.spirit_id] = spirit

        # --- Setup: each faction draws and resolves a random Change modifier ---
        events.append({"type": "setup_start"})
        for fid, faction in self.factions.items():
            card = random.choice(CHANGE_DECK)
            faction.change_modifiers[card.value] = faction.change_modifiers.get(card.value, 0) + 1
            events.append({
                "type": "change",
                "faction": fid,
                "modifier": card.value,
            })

        # --- Setup turn: all factions resolve a random agenda (no player input) ---
        agenda_choices = {}
        for fid, faction in self.factions.items():
            card = faction.draw_random_agenda()
            agenda_choices[fid] = card.agenda_type
            events.append({
                "type": "agenda_random",
                "faction": fid,
                "agenda": card.agenda_type.value,
            })

        self.normal_trade_factions = [
            fid for fid, at in agenda_choices.items()
            if at == AgendaType.TRADE
        ]

        resolve_agendas(self.factions, self.hex_map, agenda_choices,
                        self.wars, events)

        # Cleanup the setup turn
        for faction in self.factions.values():
            faction.cleanup_deck()
            faction.reset_turn_tracking()

        self.turn = 1
        self.phase = Phase.VAGRANT_PHASE
        return events

    def get_snapshot(self) -> GameStateSnapshot:
        return GameStateSnapshot(
            turn=self.turn,
            phase=self.phase,
            factions={fid: f.to_state(self.hex_map) for fid, f in self.factions.items()},
            spirits={sid: s.to_state() for sid, s in self.spirits.items()},
            wars=[w.to_state() for w in self.wars],
            all_idols=list(self.hex_map.idols),
            hex_ownership=self.hex_map.get_ownership_dict(),
        )

    def get_phase_options(self, spirit_id: str) -> dict:
        """Return the options available to a spirit for the current phase."""
        spirit = self.spirits[spirit_id]

        if self.phase == Phase.VAGRANT_PHASE:
            if not spirit.is_vagrant:
                return {"action": "none", "reason": "not_vagrant"}
            # Can guide any unoccupied, non-eliminated faction or place an idol
            available_factions = [
                fid for fid, f in self.factions.items()
                if f.guiding_spirit is None and not f.eliminated
                and f.presence_spirit != spirit_id
            ]
            presence_blocked = [
                fid for fid, f in self.factions.items()
                if f.guiding_spirit is None and not f.eliminated
                and f.presence_spirit == spirit_id
            ]
            neutral_hexes = [
                {"q": q, "r": r}
                for q, r in self.hex_map.get_neutral_hexes()
            ]
            return {
                "action": "choose",
                "available_factions": available_factions,
                "presence_blocked": presence_blocked,
                "neutral_hexes": neutral_hexes,
                "idol_types": [t.value for t in IdolType],
                "can_place_idol": not spirit.has_placed_idol_as_vagrant,
            }

        elif self.phase == Phase.AGENDA_PHASE:
            if spirit.is_vagrant:
                return {"action": "none", "reason": "vagrant"}
            if spirit.guided_faction is None:
                return {"action": "none", "reason": "no_faction"}
            # Guard against double-draw on reconnection
            if spirit_id in self.drawn_hands:
                hand = self.drawn_hands[spirit_id]
            else:
                faction = self.factions[spirit.guided_faction]
                draw_count = 1 + spirit.influence
                hand = faction.draw_agenda_cards(draw_count)
                self.drawn_hands[spirit_id] = hand
            return {
                "action": "choose_agenda",
                "hand": [c.to_dict() for c in hand],
                "influence": spirit.influence,
            }

        return {"action": "none"}

    def needs_input(self, spirit_id: str) -> bool:
        """Check if this spirit needs to submit an action for the current phase."""
        spirit = self.spirits[spirit_id]
        if self.phase == Phase.VAGRANT_PHASE:
            return spirit.is_vagrant
        elif self.phase == Phase.AGENDA_PHASE:
            return not spirit.is_vagrant and spirit.guided_faction is not None
        return False

    def get_spirits_needing_input(self) -> list[str]:
        """Return list of spirit IDs that still need to submit actions."""
        needed = []
        for sid in self.spirits:
            if self.needs_input(sid) and sid not in self.pending_actions:
                needed.append(sid)
        return needed

    def submit_action(self, spirit_id: str, action: dict) -> Optional[str]:
        """Submit an action for the current phase. Returns error message or None."""
        spirit = self.spirits.get(spirit_id)
        if not spirit:
            return "Unknown spirit"

        if spirit_id in self.pending_actions:
            return "Already submitted"

        if self.phase == Phase.VAGRANT_PHASE:
            return self._validate_vagrant_action(spirit, action)
        elif self.phase == Phase.AGENDA_PHASE:
            return self._validate_agenda_action(spirit, action)

        return "No input needed"

    def _validate_vagrant_action(self, spirit: Spirit, action: dict) -> Optional[str]:
        if not spirit.is_vagrant:
            return "Not vagrant"
        guide_target = action.get("guide_target")
        idol_type = action.get("idol_type")

        if not guide_target and not idol_type:
            return "Must choose at least one action"

        # If both guidance and idol placement are available, require both
        can_guide = any(
            f.guiding_spirit is None and not f.eliminated
            and f.presence_spirit != spirit.spirit_id
            for f in self.factions.values()
        )
        can_place_idol = (
            not spirit.has_placed_idol_as_vagrant
            and any(self.hex_map.ownership.get(h) is None for h in self.hex_map.all_hexes)
        )
        if can_guide and can_place_idol:
            if not guide_target:
                return "Must also choose a Faction to Guide"
            if not idol_type:
                return "Must also place an Idol"

        if guide_target:
            if guide_target not in self.factions:
                return f"Unknown faction: {guide_target}"

        if idol_type:
            if spirit.has_placed_idol_as_vagrant:
                return "Already placed an idol this vagrant stint"
            hex_q = action.get("idol_q")
            hex_r = action.get("idol_r")
            if idol_type not in [t.value for t in IdolType]:
                return f"Unknown idol type: {idol_type}"
            if (hex_q, hex_r) not in self.hex_map.all_hexes:
                return "Invalid hex"
            if self.hex_map.ownership.get((hex_q, hex_r)) is not None:
                return "Hex is not neutral"

        self.pending_actions[spirit.spirit_id] = action
        return None

    def _validate_agenda_action(self, spirit: Spirit, action: dict) -> Optional[str]:
        if spirit.is_vagrant or spirit.guided_faction is None:
            return "Not guiding a faction"
        agenda_index = action.get("agenda_index")
        hand = self.drawn_hands.get(spirit.spirit_id, [])
        if not isinstance(agenda_index, int) or agenda_index < 0 or agenda_index >= len(hand):
            return f"Invalid agenda index: {agenda_index}"
        self.pending_actions[spirit.spirit_id] = action
        return None

    def submit_ejection_choice(self, spirit_id: str, agenda_type: str) -> Optional[str]:
        """Submit the ejection agenda card choice."""
        if spirit_id not in self.ejection_pending:
            return "No ejection pending"
        try:
            at = AgendaType(agenda_type)
        except ValueError:
            return f"Invalid agenda type: {agenda_type}"
        faction_id = self.ejection_pending[spirit_id]
        self.factions[faction_id].add_agenda_card(at)
        del self.ejection_pending[spirit_id]
        return None

    def submit_change_choice(self, spirit_id: str, card_index: int) -> Optional[str]:
        """Submit the change card choice for guiding spirits."""
        if spirit_id not in self.change_pending:
            return "No change pending"
        cards = self.change_pending[spirit_id]
        if card_index < 0 or card_index >= len(cards):
            return f"Invalid card index: {card_index}"
        # Apply the chosen card
        spirit = self.spirits[spirit_id]
        faction = self.factions[spirit.guided_faction]
        chosen = cards[card_index]
        faction.change_modifiers[chosen.value] = faction.change_modifiers.get(chosen.value, 0) + 1
        del self.change_pending[spirit_id]
        return None

    def all_inputs_received(self) -> bool:
        return len(self.get_spirits_needing_input()) == 0

    def resolve_current_phase(self) -> list[dict]:
        """Resolve the current phase and transition. Returns events."""
        if self.phase == Phase.VAGRANT_PHASE:
            return self._resolve_vagrant_phase()
        elif self.phase == Phase.AGENDA_PHASE:
            return self._resolve_agenda_phase()
        elif self.phase == Phase.WAR_PHASE:
            return self._resolve_war_phase()
        elif self.phase == Phase.SCORING:
            return self._resolve_scoring()
        elif self.phase == Phase.CLEANUP:
            return self._resolve_cleanup()
        return []

    def _resolve_vagrant_phase(self) -> list[dict]:
        events = []

        # Group guide attempts by target faction, and collect idol placements
        guide_attempts: dict[str, list[str]] = {}
        idol_placements = []

        for spirit_id, action in self.pending_actions.items():
            guide_target = action.get("guide_target")
            idol_type = action.get("idol_type")
            if guide_target:
                guide_attempts.setdefault(guide_target, []).append(spirit_id)
            if idol_type:
                idol_placements.append((spirit_id, action))

        # Resolve idol placements (always succeed, but limit 1 neutral idol per spirit)
        for spirit_id, action in idol_placements:
            spirit = self.spirits[spirit_id]
            idol_type = IdolType(action["idol_type"])
            pos = HexCoord(action["idol_q"], action["idol_r"])

            # Remove existing neutral idol if any
            existing_neutral = self.hex_map.get_spirit_idols_in_neutral(spirit_id)
            for old_idol in existing_neutral:
                self.hex_map.idols.remove(old_idol)
                spirit.idols.remove(old_idol)
                events.append({
                    "type": "idol_removed",
                    "spirit": spirit_id,
                    "idol_type": old_idol.type.value,
                    "hex": old_idol.position.to_dict(),
                })

            idol = spirit.place_idol(idol_type, pos)
            self.hex_map.place_idol(idol)
            spirit.has_placed_idol_as_vagrant = True
            events.append({
                "type": "idol_placed",
                "spirit": spirit_id,
                "idol_type": idol_type.value,
                "hex": pos.to_dict(),
            })

        # Resolve guide attempts
        for target_faction, spirit_ids in guide_attempts.items():
            if len(spirit_ids) == 1:
                spirit_id = spirit_ids[0]
                spirit = self.spirits[spirit_id]
                faction = self.factions[target_faction]
                spirit.guide_faction(target_faction)
                faction.guiding_spirit = spirit_id
                events.append({
                    "type": "guided",
                    "spirit": spirit_id,
                    "faction": target_faction,
                })
                # Check presence
                self._check_presence(faction, spirit, events)
            else:
                # Contested - all fail, single event with all spirits
                events.append({
                    "type": "guide_contested",
                    "spirits": spirit_ids,
                    "faction": target_faction,
                })

        self.pending_actions.clear()
        self.phase = Phase.AGENDA_PHASE
        return events

    def _check_presence(self, faction: Faction, spirit: Spirit, events: list):
        """Check and update presence for a faction when a spirit guides or leaves."""
        if faction.presence_spirit is None:
            faction.presence_spirit = spirit.spirit_id
            events.append({
                "type": "presence_gained",
                "spirit": spirit.spirit_id,
                "faction": faction.faction_id,
            })
        elif faction.presence_spirit != spirit.spirit_id:
            # Compare idol counts
            current_idols = self.hex_map.count_spirit_idols_in_faction(
                faction.presence_spirit, faction.faction_id)
            new_idols = self.hex_map.count_spirit_idols_in_faction(
                spirit.spirit_id, faction.faction_id)
            if new_idols >= current_idols:
                old_spirit = faction.presence_spirit
                faction.presence_spirit = spirit.spirit_id
                events.append({
                    "type": "presence_replaced",
                    "spirit": spirit.spirit_id,
                    "old_spirit": old_spirit,
                    "faction": faction.faction_id,
                })

    def _check_eliminations(self, events: list):
        """Check all factions for 0 territories and mark as eliminated."""
        for fid, faction in self.factions.items():
            if faction.eliminated:
                continue
            territories = self.hex_map.get_faction_territories(fid)
            if len(territories) > 0:
                continue
            faction.eliminated = True
            events.append({
                "type": "faction_eliminated",
                "faction": fid,
            })
            # Eject guiding spirit
            if faction.guiding_spirit:
                spirit = self.spirits[faction.guiding_spirit]
                faction.guiding_spirit = None
                spirit.become_vagrant()
                events.append({
                    "type": "ejected",
                    "spirit": spirit.spirit_id,
                    "faction": fid,
                })
            # Clear presence
            faction.presence_spirit = None
            # Remove wars involving this faction
            wars_to_remove = [w for w in self.wars
                              if w.faction_a == fid or w.faction_b == fid]
            for w in wars_to_remove:
                self.wars.remove(w)
                events.append({
                    "type": "war_ended",
                    "war_id": w.war_id,
                    "reason": "faction_eliminated",
                    "faction": fid,
                })

    def _resolve_agenda_phase(self) -> list[dict]:
        events = []
        agenda_choices: dict[str, AgendaType] = {}
        self.normal_trade_factions = []

        # Resolve spirit choices
        for spirit_id, action in self.pending_actions.items():
            spirit = self.spirits[spirit_id]
            hand = self.drawn_hands.get(spirit_id, [])
            idx = action["agenda_index"]
            chosen = hand[idx]
            agenda_choices[spirit.guided_faction] = chosen.agenda_type
            # Track all drawn cards for return to deck during cleanup
            faction = self.factions[spirit.guided_faction]
            faction.played_agenda_this_turn.extend(hand)
            events.append({
                "type": "agenda_chosen",
                "spirit": spirit_id,
                "faction": spirit.guided_faction,
                "agenda": chosen.agenda_type.value,
            })

        # Non-guided factions draw random agenda (skip eliminated)
        for fid, faction in self.factions.items():
            if fid not in agenda_choices:
                if faction.eliminated:
                    continue
                card = faction.draw_random_agenda()
                agenda_choices[fid] = card.agenda_type
                events.append({
                    "type": "agenda_random",
                    "faction": fid,
                    "agenda": card.agenda_type.value,
                })

        # All spirits lose 1 influence
        for spirit in self.spirits.values():
            if not spirit.is_vagrant and spirit.guided_faction:
                spirit.lose_influence(1)

        # Track trade factions before resolving
        self.normal_trade_factions = [
            fid for fid, at in agenda_choices.items()
            if at == AgendaType.TRADE
        ]

        # Handle Change differently for guided factions
        change_factions_guided = []
        change_factions_auto = []
        for fid, at in agenda_choices.items():
            if at == AgendaType.CHANGE:
                faction = self.factions[fid]
                if faction.guiding_spirit:
                    spirit = self.spirits[faction.guiding_spirit]
                    if spirit.influence > 0:
                        change_factions_guided.append((fid, faction.guiding_spirit))
                    else:
                        change_factions_auto.append(fid)
                else:
                    change_factions_auto.append(fid)

        # Resolve non-change agendas + auto-change
        non_change_choices = {fid: at for fid, at in agenda_choices.items()
                             if at != AgendaType.CHANGE}
        # Add auto-change factions back
        for fid in change_factions_auto:
            non_change_choices[fid] = AgendaType.CHANGE

        resolve_agendas(self.factions, self.hex_map, non_change_choices,
                       self.wars, events)

        # Handle guided change (spirit gets to choose)
        for fid, spirit_id in change_factions_guided:
            spirit = self.spirits[spirit_id]
            draw_count = 1 + spirit.influence
            cards = random.sample(CHANGE_DECK, min(draw_count, len(CHANGE_DECK)))
            self.change_pending[spirit_id] = cards
            events.append({
                "type": "change_draw",
                "spirit": spirit_id,
                "faction": fid,
                "cards": [c.value for c in cards],
            })

        # Check for ejection (0 influence spirits)
        for spirit in self.spirits.values():
            if not spirit.is_vagrant and spirit.guided_faction and spirit.influence == 0:
                faction_id = spirit.guided_faction
                faction = self.factions[faction_id]
                self.ejection_pending[spirit.spirit_id] = faction_id
                events.append({
                    "type": "ejection_pending",
                    "spirit": spirit.spirit_id,
                    "faction": faction_id,
                })

        self.pending_actions.clear()
        self.drawn_hands.clear()

        # If no change/ejection choices needed, advance
        if not self.change_pending and not self.ejection_pending:
            self._finalize_agenda_phase(events)

        return events

    def finalize_sub_choices(self) -> list[dict]:
        """Called after all change/ejection choices are submitted."""
        events = []
        self._finalize_agenda_phase(events)
        return events

    def _finalize_agenda_phase(self, events: list):
        """Handle ejections and advance to war phase."""
        # Process ejections
        for spirit_id, faction_id in list(self.ejection_pending.items()):
            # If still pending (not yet submitted), auto-resolve
            pass

        # Actually eject spirits whose ejection has been resolved
        spirits_to_eject = []
        for spirit in self.spirits.values():
            if not spirit.is_vagrant and spirit.guided_faction and spirit.influence == 0:
                if spirit.spirit_id not in self.ejection_pending:
                    spirits_to_eject.append(spirit)

        for spirit in spirits_to_eject:
            faction = self.factions[spirit.guided_faction]
            faction.guiding_spirit = None
            # Check presence on leaving
            self._check_presence(faction, spirit, events)
            spirit.become_vagrant()
            events.append({
                "type": "ejected",
                "spirit": spirit.spirit_id,
                "faction": faction.faction_id,
            })

        self.ejection_pending.clear()
        self.phase = Phase.WAR_PHASE

    def _resolve_war_phase(self) -> list[dict]:
        events = []
        war_results = []

        # Resolve ripe wars
        ripe_wars = [w for w in self.wars if w.is_ripe]
        for war in ripe_wars:
            result = war.resolve(self.factions, self.hex_map)
            war_results.append(result)
            events.append({
                "type": "war_resolved",
                **result,
            })
            self.wars.remove(war)

        # Ripen pending wars
        pending_wars = [w for w in self.wars if not w.is_ripe]
        for war in pending_wars:
            if war.ripen(self.hex_map):
                events.append({
                    "type": "war_ripened",
                    "war_id": war.war_id,
                    "faction_a": war.faction_a,
                    "faction_b": war.faction_b,
                    "battleground": [
                        {"q": war.battleground[0][0], "r": war.battleground[0][1]},
                        {"q": war.battleground[1][0], "r": war.battleground[1][1]},
                    ] if war.battleground else None,
                })

        # Resolve spoils of war
        if war_results:
            self.spoils_pending = resolve_spoils(
                self.factions, self.hex_map, war_results, self.wars,
                events, self.normal_trade_factions, spirits=self.spirits)
        else:
            self.spoils_pending = {}

        # Check for faction eliminations after territory changes
        self._check_eliminations(events)

        if not self.spoils_pending:
            self.phase = Phase.SCORING
        # Otherwise stay in WAR_PHASE until spoils choices are submitted
        return events

    def _resolve_scoring(self) -> list[dict]:
        events = calculate_scoring(self.factions, self.spirits, self.hex_map)

        # Check for winner
        winner = None
        max_vp = 0
        for spirit in self.spirits.values():
            if spirit.victory_points >= VP_TO_WIN:
                if spirit.victory_points > max_vp:
                    max_vp = spirit.victory_points
                    winner = spirit.spirit_id

        if winner:
            # Check for ties
            winners = [s.spirit_id for s in self.spirits.values()
                      if s.victory_points == max_vp]
            self.phase = Phase.GAME_OVER
            events.append({
                "type": "game_over",
                "winners": winners,
                "scores": {s.spirit_id: s.victory_points for s in self.spirits.values()},
            })
        else:
            self.phase = Phase.CLEANUP

        return events

    def _resolve_cleanup(self) -> list[dict]:
        events = []
        # Return played/spoils cards to decks, then reset turn tracking
        for faction in self.factions.values():
            if faction.eliminated:
                continue
            faction.cleanup_deck()
            faction.reset_turn_tracking()

        # Clear all transient per-turn state
        self.pending_actions.clear()
        self.drawn_hands.clear()
        self.change_pending.clear()
        self.ejection_pending.clear()
        self.spoils_pending.clear()

        self.turn += 1
        self.phase = Phase.VAGRANT_PHASE
        events.append({"type": "turn_start", "turn": self.turn})
        return events

    def submit_spoils_choice(self, spirit_id: str, card_index: int) -> tuple[Optional[str], list[dict]]:
        """Submit a spoils of war card choice. Returns (error, events)."""
        if spirit_id not in self.spoils_pending:
            return "No spoils pending", []
        cards = self.spoils_pending[spirit_id]["cards"]
        if card_index < 0 or card_index >= len(cards):
            return f"Invalid card index: {card_index}", []
        events = []
        resolve_spoils_choice(self.factions, self.hex_map, self.wars, events,
                              spirit_id, card_index, self.spoils_pending,
                              self.spirits)
        # Check for faction eliminations after spoils territory changes
        self._check_eliminations(events)
        # If all spoils resolved, advance to scoring
        if not self.spoils_pending:
            self.phase = Phase.SCORING
        return None, events

    def submit_spoils_change_choice(self, spirit_id: str, card_index: int) -> tuple[Optional[str], list[dict]]:
        """Submit a spoils change modifier choice (second stage of spoils Change)."""
        if spirit_id not in self.spoils_pending:
            return "No spoils pending", []
        pending = self.spoils_pending[spirit_id]
        if pending.get("stage") != "change_choice":
            return "Not in change choice stage", []
        change_cards = pending.get("change_cards", [])
        if card_index < 0 or card_index >= len(change_cards):
            return f"Invalid card index: {card_index}", []

        events = []
        chosen = change_cards[card_index]
        winner = pending["winner"]
        faction = self.factions[winner]
        faction.change_modifiers[chosen.value] = faction.change_modifiers.get(chosen.value, 0) + 1
        events.append({
            "type": "change",
            "faction": winner,
            "modifier": chosen.value,
        })

        del self.spoils_pending[spirit_id]
        if not self.spoils_pending:
            self.phase = Phase.SCORING
        return None, events

    def has_pending_sub_choices(self) -> bool:
        return bool(self.change_pending) or bool(self.ejection_pending)
