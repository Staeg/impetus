"""Core game state machine and turn resolution."""

import random
from dataclasses import dataclass, field
from typing import Any, Optional
from shared.constants import (
    Phase, AgendaType, IdolType, FACTION_NAMES, RACES, VP_TO_WIN,
    STARTING_INFLUENCE, CHANGE_DECK, FACTION_START_HEXES, HABITAT_STARTING_MODIFIERS,
)
from shared.protocol import SubPhase

# Left-to-right ribbon order: sorted by x then y of flat-top axial hex positions
RIBBON_HEX_ORDER = [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0)]
from shared.models import HexCoord, Idol, GameStateSnapshot
from server.hex_map import HexMap
from server.faction import Faction
from server.spirit import Spirit
from server.war import War
from server.agenda import resolve_agendas, resolve_spoils, finalize_all_spoils
from server.scoring import calculate_scoring


@dataclass
class SpoilsPendingEntry:
    """Represents one pending spoils choice for a guided spirit."""
    winner: str
    loser: str
    cards: list          # list of AgendaType
    chosen_card: Any = None
    stage: str = ""      # SubPhase.CHANGE_CHOICE or EXPAND_CHOICE when awaiting follow-up
    change_cards: list = field(default_factory=list)
    expand_hexes: list = field(default_factory=list)  # available enemy territories for Expand choice
    expand_target: Any = None  # chosen (q, r) tuple after spoils_expand_choice


class GameState:
    """Authoritative game state. Drives the entire game flow."""

    def __init__(self):
        self.turn: int = 0
        self.phase: Phase = Phase.LOBBY
        self.vp_to_win: int = VP_TO_WIN
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
        self.spoils_pending: dict[str, list[SpoilsPendingEntry]] = {}
        # Auto-resolved spoils waiting for batch finalization
        self.auto_spoils_choices: list[dict] = []
        # Winner choice state: one-guided wars where spirit picks who wins
        self.winner_choice_pending: dict[str, list[dict]] = {}  # spirit_id -> list of war dicts
        self._war_results_dice: list[dict] = []  # dice-resolved results saved while awaiting winner choices
        # Contested guidance cooldowns: spirit_id -> set of faction_ids blocked for 1 turn
        self.guidance_cooldowns: dict[str, set[str]] = {}
        # Tutorial mode: give human players priority in contested guidance on turn 2
        self.tutorial_mode: bool = False
        self.ai_spirit_ids: set[str] = set()
        # Phase-scoped agenda resolution state (declared here to avoid mid-method creation)
        self._stored_agenda_choices: dict[str, AgendaType] = {}
        self._guided_change_factions: list[str] = []
        self._guided_change_modifiers: dict[str, str] = {}
        # Guided expand hex choices (spirit_id -> faction_id pending, spirit_id -> (q,r) chosen)
        self.expand_pending: dict[str, str] = {}
        self.expand_chosen: dict[str, tuple] = {}
        # Spirits needing to choose where their faction respawns (spirit_id -> faction_id)
        self.respawn_pending: dict[str, str] = {}
        # Faction display order (left-to-right by starting hex x-position)
        self.faction_order: list[str] = list(FACTION_NAMES)

    def setup_game(self, player_info: list[dict], vp_to_win: int = VP_TO_WIN) -> tuple[GameStateSnapshot, list[tuple[list[dict], GameStateSnapshot]]]:
        """Initialize the game with the given players.

        Returns (initial_snapshot, turn_results) where:
        - initial_snapshot: state before any automated turns (just starting hexes)
        - turn_results: list of (events, post_turn_snapshot) per automated turn

        player_info: list of {spirit_id, name}
        """
        self.vp_to_win = vp_to_win
        # Create factions
        for faction_id in FACTION_NAMES:
            faction = Faction(faction_id)
            # Initialize regard with all other factions
            for other_id in FACTION_NAMES:
                if other_id != faction_id:
                    faction.regard[other_id] = 0
            self.factions[faction_id] = faction

        # Assign a unique race to each faction (shuffle so each game is different)
        races_shuffled = random.sample(RACES, len(FACTION_NAMES))
        for faction_id, race in zip(FACTION_NAMES, races_shuffled):
            self.factions[faction_id].race = race

        # Create spirits
        for info in player_info:
            spirit = Spirit(info["spirit_id"], info["name"])
            self.spirits[spirit.spirit_id] = spirit

        # Assign affinities so each habitat and each race appears at most once
        # across all spirits, and no pair exactly matches a faction combo.
        faction_combos = {(fid, self.factions[fid].race) for fid in self.factions}
        habitats = list(FACTION_NAMES)
        races = list(RACES)
        while True:
            random.shuffle(habitats)
            random.shuffle(races)
            pairs = list(zip(habitats, races))
            if all(pair not in faction_combos for pair in pairs):
                break
        for spirit, (habitat, race) in zip(self.spirits.values(), pairs):
            spirit.habitat_affinity = habitat
            spirit.race_affinity = race

        # Shuffle which faction starts at which position
        start_positions = list(FACTION_START_HEXES.values())
        random.shuffle(start_positions)
        faction_start_hexes = dict(zip(FACTION_NAMES, start_positions))
        self.hex_map = HexMap(faction_start_hexes)
        # Compute ribbon order from spatial position (left-to-right by hex x)
        pos_to_faction = {v: k for k, v in faction_start_hexes.items()}
        self.faction_order = [pos_to_faction[pos] for pos in RIBBON_HEX_ORDER]

        turn_results: list[tuple[list[dict], GameStateSnapshot]] = []

        def _run_automated_turn(turn_number: int, agenda_choices: dict[str, AgendaType],
                                agenda_event_type: str):
            """Resolve a full non-player turn (agenda, war, scoring) and cleanup state."""
            events: list[dict] = []
            events.append({"type": "turn_start", "turn": turn_number})

            for fid, at in agenda_choices.items():
                events.append({
                    "type": agenda_event_type,
                    "faction": fid,
                    "agenda": at.value,
                })

            self.normal_trade_factions = [
                fid for fid, at in agenda_choices.items()
                if at == AgendaType.TRADE
            ]
            resolve_agendas(self.factions, self.hex_map, agenda_choices, self.wars, events)
            events.extend(self._resolve_war_phase())
            events.extend(self._resolve_scoring())

            for faction in self.factions.values():
                faction.cleanup_deck()
                faction.reset_turn_tracking()

            # Automated opening turns cannot create player-driven pending choices.
            self.pending_actions.clear()
            self.drawn_hands.clear()
            self.change_pending.clear()
            self.ejection_pending.clear()
            self.spoils_pending.clear()
            self.auto_spoils_choices.clear()
            self.winner_choice_pending.clear()
            self._war_results_dice.clear()

            turn_results.append((events, self.get_snapshot()))

        # Apply habitat-based starting Change modifiers before any automated turns
        for fid, faction in self.factions.items():
            for modifier, count in HABITAT_STARTING_MODIFIERS.get(fid, {}).items():
                faction.change_modifiers[modifier] = count

        # Capture initial snapshot before the automated turn
        initial_snapshot = self.get_snapshot()

        # Turn 1: normal unguided turn (all factions play random agendas).
        turn_one_choices: dict[str, AgendaType] = {}
        for fid, faction in self.factions.items():
            card = faction.draw_random_agenda()
            faction.played_agenda_this_turn.append(card)
            turn_one_choices[fid] = card.agenda_type
        _run_automated_turn(
            turn_number=1,
            agenda_choices=turn_one_choices,
            agenda_event_type="agenda_random",
        )

        # Players begin taking actions on Turn 2.
        self.turn = 2
        self.phase = Phase.VAGRANT_PHASE
        # Append turn 2 marker to the last automated turn so the client
        # resets its change tracker and logs the turn boundary.
        if turn_results:
            turn_results[-1][0].append({"type": "turn_start", "turn": 2})
        return initial_snapshot, turn_results

    def get_snapshot(self) -> GameStateSnapshot:
        return GameStateSnapshot(
            turn=self.turn,
            phase=self.phase,
            factions={fid: f.to_state(self.hex_map) for fid, f in self.factions.items()},
            spirits={sid: s.to_state() for sid, s in self.spirits.items()},
            wars=[w.to_state() for w in self.wars],
            all_idols=list(self.hex_map.idols),
            hex_ownership=self.hex_map.get_ownership_dict(),
            faction_order=self.faction_order,
        )

    def get_phase_options(self, spirit_id: str) -> dict:
        """Return the options available to a spirit for the current phase."""
        spirit = self.spirits[spirit_id]

        if self.phase == Phase.VAGRANT_PHASE:
            if not spirit.is_vagrant:
                return {"action": "none", "reason": "not_vagrant"}
            # Can guide any unoccupied faction or place an idol
            cooldown_set = self.guidance_cooldowns.get(spirit_id, set())
            guidable = [
                fid for fid, f in self.factions.items()
                if f.guiding_spirit is None
                and f.worship_spirit != spirit_id
            ]
            available_factions = [fid for fid in guidable if fid not in cooldown_set]
            contested_blocked = [fid for fid in guidable if fid in cooldown_set]
            worship_blocked = [
                fid for fid, f in self.factions.items()
                if f.guiding_spirit is None
                and f.worship_spirit == spirit_id
            ]
            neutral_hexes = [
                {"q": q, "r": r}
                for q, r in self.hex_map.get_neutral_hexes()
            ]
            return {
                "action": "choose",
                "available_factions": available_factions,
                "worship_blocked": worship_blocked,
                "contested_blocked": contested_blocked,
                "neutral_hexes": neutral_hexes,
                "idol_types": [t.value for t in IdolType],
                "can_place_idol": not spirit.has_placed_idol_as_vagrant,
                "can_swell": not available_factions,
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
                _sort = {AgendaType.TRADE: 0, AgendaType.STEAL: 1,
                         AgendaType.EXPAND: 2, AgendaType.CHANGE: 3}
                hand = sorted(faction.draw_agenda_cards(draw_count),
                              key=lambda c: _sort.get(c.agenda_type, 99))
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
        is_swell = action.get("swell", False)

        if not guide_target and not idol_type and not is_swell:
            return "Must choose at least one action"

        # If both guidance and idol placement are available, require both
        cooldown_set = self.guidance_cooldowns.get(spirit.spirit_id, set())
        can_guide = any(
            f.guiding_spirit is None
            and f.worship_spirit != spirit.spirit_id
            and fid not in cooldown_set
            for fid, f in self.factions.items()
        )
        spirit_idol_hexes = {
            (i.position.q, i.position.r)
            for i in self.hex_map.idols
            if i.owner_spirit == spirit.spirit_id
        }
        can_place_idol = (
            not spirit.has_placed_idol_as_vagrant
            and any(
                self.hex_map.ownership.get(h) is None and h not in spirit_idol_hexes
                for h in self.hex_map.all_hexes
            )
        )
        if is_swell:
            if can_guide:
                return "Cannot Swell when Guidance targets are available"
            if not idol_type:
                self.pending_actions[spirit.spirit_id] = action
                return None
            # Swell with optional idol placement — fall through to idol validation

        if can_guide and can_place_idol:
            if not guide_target:
                return "Must also choose a Faction to Guide"
            if not idol_type:
                return "Must also place an Idol"

        if guide_target:
            if guide_target not in self.factions:
                return f"Unknown faction: {guide_target}"
            if guide_target in cooldown_set:
                return "Contested guidance cooldown: cannot target this faction this turn"

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
            if any(
                i.owner_spirit == spirit.spirit_id
                and i.position.q == hex_q and i.position.r == hex_r
                for i in self.hex_map.idols
            ):
                return "Hex already contains one of your Idols!"

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

    def submit_ejection_choice(self, spirit_id: str, remove_type: str, add_type: str) -> Optional[str]:
        """Submit the ejection agenda card replacement choice."""
        if spirit_id not in self.ejection_pending:
            return "No ejection pending"
        try:
            remove_at = AgendaType(remove_type)
        except ValueError:
            return f"Invalid remove agenda type: {remove_type}"
        try:
            add_at = AgendaType(add_type)
        except ValueError:
            return f"Invalid add agenda type: {add_type}"
        faction_id = self.ejection_pending[spirit_id]
        faction = self.factions[faction_id]
        pool_types = [c.agenda_type for c in faction.agenda_pool]
        if remove_at not in pool_types:
            return f"Type {remove_type} not in faction's agenda pool"
        faction.replace_agenda_card(remove_at, add_at)
        del self.ejection_pending[spirit_id]
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

        # Clear previous turn's contested guidance cooldowns before resolving new ones
        self.guidance_cooldowns.clear()

        # Group guide attempts by target faction, and collect idol placements
        guide_attempts: dict[str, list[str]] = {}
        idol_placements = []
        swell_spirits = []

        for spirit_id, action in self.pending_actions.items():
            guide_target = action.get("guide_target")
            idol_type = action.get("idol_type")
            if guide_target:
                guide_attempts.setdefault(guide_target, []).append(spirit_id)
            if idol_type:
                idol_placements.append((spirit_id, action))
            if action.get("swell"):
                swell_spirits.append(spirit_id)

        # Resolve idol placements (always succeed)
        for spirit_id, action in idol_placements:
            spirit = self.spirits[spirit_id]
            idol_type = IdolType(action["idol_type"])
            pos = HexCoord(action["idol_q"], action["idol_r"])

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
                # Check worship
                self._check_worship(faction, spirit, events)
            else:
                # Multiple spirits contested — resolve via Affinities first
                faction = self.factions[target_faction]
                faction_race = faction.race

                # Spirits whose habitat affinity matches this faction's habitat
                habitat_matches = [
                    sid for sid in spirit_ids
                    if self.spirits[sid].habitat_affinity == target_faction
                ]
                # Spirits whose race affinity matches this faction's race (ignoring habitat matches)
                race_matches = [
                    sid for sid in spirit_ids
                    if self.spirits[sid].race_affinity == faction_race
                    and sid not in habitat_matches
                ]

                if len(habitat_matches) == 1:
                    # Exactly one habitat-affinity winner — they guide, others waste their turn
                    winner_id = habitat_matches[0]
                    winner = self.spirits[winner_id]
                    faction.guiding_spirit = winner_id
                    winner.guide_faction(target_faction)
                    events.append({
                        "type": "guided",
                        "spirit": winner_id,
                        "faction": target_faction,
                    })
                    self._check_worship(faction, winner, events)
                    losers = [sid for sid in spirit_ids if sid != winner_id]
                    if losers:
                        events.append({
                            "type": "guide_contested",
                            "spirits": losers,
                            "faction": target_faction,
                            "won_by_affinity": winner_id,
                        })
                elif not habitat_matches and len(race_matches) == 1:
                    # No habitat contenders, exactly one race-affinity winner
                    winner_id = race_matches[0]
                    winner = self.spirits[winner_id]
                    faction.guiding_spirit = winner_id
                    winner.guide_faction(target_faction)
                    events.append({
                        "type": "guided",
                        "spirit": winner_id,
                        "faction": target_faction,
                    })
                    self._check_worship(faction, winner, events)
                    losers = [sid for sid in spirit_ids if sid != winner_id]
                    if losers:
                        events.append({
                            "type": "guide_contested",
                            "spirits": losers,
                            "faction": target_faction,
                            "won_by_affinity": winner_id,
                        })
                else:
                    # No clear affinity winner — normal contested resolution
                    # Cooldown applies only to the top-tier contenders
                    contested = habitat_matches or race_matches or spirit_ids
                    # Tutorial mode: on the first vagrant phase (turn 2), give uncontested
                    # guidance to a human player if they're the only human in the contest.
                    if self.tutorial_mode and self.turn == 2:
                        human_spirits = [s for s in contested if s not in self.ai_spirit_ids]
                        if len(human_spirits) == 1:
                            winner_id = human_spirits[0]
                            winner = self.spirits[winner_id]
                            faction.guiding_spirit = winner_id
                            winner.guide_faction(target_faction)
                            events.append({
                                "type": "guided",
                                "spirit": winner_id,
                                "faction": target_faction,
                            })
                            self._check_worship(faction, winner, events)
                            continue
                    events.append({
                        "type": "guide_contested",
                        "spirits": spirit_ids,
                        "faction": target_faction,
                    })
                    for sid in contested:
                        self.guidance_cooldowns.setdefault(sid, set()).add(target_faction)

        # Resolve swell actions
        for spirit_id in swell_spirits:
            spirit = self.spirits[spirit_id]
            spirit.victory_points += 10
            events.append({
                "type": "swell",
                "spirit": spirit_id,
                "vp_gained": 10,
                "total_vp": spirit.victory_points,
            })

        self.pending_actions.clear()
        self.phase = Phase.AGENDA_PHASE
        return events

    def _check_worship(self, faction: Faction, spirit: Spirit, events: list):
        """Check and update worship for a faction when a spirit guides or leaves."""
        if faction.worship_spirit is None:
            faction.worship_spirit = spirit.spirit_id
            events.append({
                "type": "worship_gained",
                "spirit": spirit.spirit_id,
                "faction": faction.faction_id,
            })
        elif faction.worship_spirit != spirit.spirit_id:
            # Compare idol counts
            current_idols = self.hex_map.count_spirit_idols_in_faction(
                faction.worship_spirit, faction.faction_id)
            new_idols = self.hex_map.count_spirit_idols_in_faction(
                spirit.spirit_id, faction.faction_id)
            if new_idols >= current_idols:
                old_spirit = faction.worship_spirit
                faction.worship_spirit = spirit.spirit_id
                events.append({
                    "type": "worship_replaced",
                    "spirit": spirit.spirit_id,
                    "old_spirit": old_spirit,
                    "faction": faction.faction_id,
                })

    def _check_respawns(self, events: list):
        """Check all factions for 0 territories and trigger a respawn."""
        neutral_hexes = list(self.hex_map.get_neutral_hexes())
        already_pending = set(self.respawn_pending.values())
        for fid, faction in self.factions.items():
            if fid in already_pending:
                continue  # Already queued for respawn, don't double-process
            territories = self.hex_map.get_faction_territories(fid)
            if len(territories) > 0:
                continue
            # Faction lost all territories: lose all gold
            lost_gold = faction.gold
            faction.gold = 0
            if faction.guiding_spirit and neutral_hexes:
                # Guided: defer hex choice to the spirit
                self.respawn_pending[faction.guiding_spirit] = fid
                events.append({
                    "type": "faction_respawning",
                    "faction": fid,
                    "gold_lost": lost_gold,
                })
            else:
                # Unguided (or no neutral hexes): auto-pick a random neutral hex
                if neutral_hexes:
                    chosen = random.choice(neutral_hexes)
                    neutral_hexes.remove(chosen)
                    self.hex_map.claim_hex(chosen, fid)
                    events.append({
                        "type": "faction_respawned",
                        "faction": fid,
                        "gold_lost": lost_gold,
                        "hex": {"q": chosen[0], "r": chosen[1]},
                    })
                else:
                    events.append({
                        "type": "faction_respawned",
                        "faction": fid,
                        "gold_lost": lost_gold,
                        "hex": None,
                    })

    def submit_respawn_choice(self, spirit_id: str, q: int, r: int) -> tuple[Optional[str], list[dict]]:
        """Submit a respawn hex choice for a guided spirit. Returns (error, events)."""
        if spirit_id not in self.respawn_pending:
            return "No respawn pending", []
        hex_coord = (q, r)
        if hex_coord not in self.hex_map.all_hexes:
            return "Invalid hex", []
        if self.hex_map.ownership.get(hex_coord) is not None:
            return "Hex is not neutral", []
        faction_id = self.respawn_pending[spirit_id]
        self.hex_map.claim_hex(hex_coord, faction_id)
        del self.respawn_pending[spirit_id]
        events = [{
            "type": "faction_respawned",
            "faction": faction_id,
            "hex": {"q": q, "r": r},
        }]
        if not self.respawn_pending:
            self.phase = Phase.SCORING
        return None, events

    def prepare_change_choices(self) -> list[dict]:
        """Process agenda inputs and identify Change choices needed before resolution.

        Called after all agenda inputs received but BEFORE resolve.
        Returns events for agenda_chosen/agenda_random + change_draw.
        Stores agenda_choices on self for later resolution.
        """
        events = []
        agenda_choices: dict[str, AgendaType] = {}

        # Resolve spirit choices
        for spirit_id, action in self.pending_actions.items():
            spirit = self.spirits[spirit_id]
            hand = self.drawn_hands.get(spirit_id, [])
            idx = action["agenda_index"]
            chosen = hand[idx]
            agenda_choices[spirit.guided_faction] = chosen.agenda_type
            # Track chosen card for scoring/cleanup (pool is static, no return needed)
            faction = self.factions[spirit.guided_faction]
            faction.played_agenda_this_turn.append(chosen)
            events.append({
                "type": "agenda_chosen",
                "spirit": spirit_id,
                "faction": spirit.guided_faction,
                "agenda": chosen.agenda_type.value,
            })

        # Non-guided factions draw random agenda
        for fid, faction in self.factions.items():
            if fid not in agenda_choices:
                card = faction.draw_random_agenda()
                faction.played_agenda_this_turn.append(card)
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

        # Store agenda choices for later resolution
        self._stored_agenda_choices = agenda_choices
        # Track which factions have guided change (modifier chosen by spirit)
        self._guided_change_factions = []

        # Identify guided Change spirits that need to choose
        for fid, at in agenda_choices.items():
            if at == AgendaType.CHANGE:
                faction = self.factions[fid]
                if faction.guiding_spirit:
                    spirit = self.spirits[faction.guiding_spirit]
                    if spirit.influence > 0:
                        draw_count = 1 + spirit.influence
                        cards = random.sample(CHANGE_DECK, min(draw_count, len(CHANGE_DECK)))
                        self.change_pending[faction.guiding_spirit] = cards
                        self._guided_change_factions.append(fid)
                        events.append({
                            "type": "change_draw",
                            "spirit": faction.guiding_spirit,
                            "faction": fid,
                            "cards": [c.value for c in cards],
                        })

        self.pending_actions.clear()
        self.drawn_hands.clear()

        return events

    def has_pending_change_choices(self) -> bool:
        """Check if there are still pending Change choices (separate from ejection)."""
        return bool(self.change_pending)

    def prepare_expand_choices(self) -> None:
        """Identify guided Expand factions whose spirit should choose a target hex.

        Called after prepare_change_choices() has set _stored_agenda_choices.
        Sets expand_pending: spirit_id -> faction_id for factions where expansion
        is possible (reachable hex exists AND faction can afford the cost).
        Non-guided factions and those that can't expand are handled automatically
        during resolution.
        """
        from shared.constants import ChangeModifierTarget
        self.expand_pending.clear()
        for fid, at in self._stored_agenda_choices.items():
            if at != AgendaType.EXPAND:
                continue
            faction = self.factions[fid]
            if not faction.guiding_spirit:
                continue
            spirit_id = faction.guiding_spirit
            expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
            territory_count = len(self.hex_map.get_faction_territories(fid))
            cost = max(0, territory_count - expand_discount)
            reachable = self.hex_map.get_reachable_neutral_hexes(fid)
            if not reachable or faction.gold < cost:
                continue
            self.expand_pending[spirit_id] = fid

    def has_pending_expand_choices(self) -> bool:
        """Check if any guided spirits still need to submit an expand hex choice."""
        return bool(self.expand_pending)

    def submit_expand_choice(self, spirit_id: str, q: int, r: int) -> Optional[str]:
        """Submit the expand target hex for a guided spirit. Returns error or None."""
        if spirit_id not in self.expand_pending:
            return "No expand choice pending"
        faction_id = self.expand_pending[spirit_id]
        reachable = self.hex_map.get_reachable_neutral_hexes(faction_id)
        if (q, r) not in reachable:
            return f"Hex ({q},{r}) is not a reachable neutral hex for this faction"
        self.expand_chosen[spirit_id] = (q, r)
        del self.expand_pending[spirit_id]
        return None

    def submit_change_choice(self, spirit_id: str, card_index: int) -> tuple[Optional[str], list[dict]]:
        """Submit the change card choice for guiding spirits. Returns (error, events)."""
        if spirit_id not in self.change_pending:
            return "No change pending", []
        cards = self.change_pending[spirit_id]
        if card_index < 0 or card_index >= len(cards):
            return f"Invalid card index: {card_index}", []
        # Apply the chosen card
        spirit = self.spirits[spirit_id]
        faction = self.factions[spirit.guided_faction]
        chosen = cards[card_index]
        faction.add_change_modifier(chosen)
        del self.change_pending[spirit_id]
        # Store modifier so resolve_agenda_phase_after_changes can emit
        # a visual event in the normal resolution order.
        self._guided_change_modifiers[spirit.guided_faction] = chosen.value
        # Mark as non-animated: the visual event comes later in resolution
        events = [{
            "type": "change",
            "faction": spirit.guided_faction,
            "modifier": chosen.value,
            "is_guided_modifier": True,
        }]
        return None, events

    def resolve_agenda_phase_after_changes(self) -> list[dict]:
        """Resolve all agendas after expand and Change choices have been submitted.

        Uses stored agenda_choices from prepare_change_choices().
        Guided change factions already had their modifier applied, so exclude
        them from the Change resolution in resolve_agendas.
        Guided expand factions have pre-chosen their target hex in expand_chosen.
        """
        events = []
        agenda_choices = self._stored_agenda_choices
        guided_change = self._guided_change_factions

        # Build faction_id -> hex mapping for guided expand choices
        guided_expand_choices = {}
        for spirit_id, hex_coord in self.expand_chosen.items():
            spirit = self.spirits.get(spirit_id)
            if spirit and spirit.guided_faction:
                guided_expand_choices[spirit.guided_faction] = hex_coord

        # Build resolution choices excluding guided change factions
        # (their modifier was already applied via submit_change_choice)
        resolve_choices = {}
        for fid, at in agenda_choices.items():
            if at == AgendaType.CHANGE and fid in guided_change:
                continue  # Skip - already resolved
            resolve_choices[fid] = at

        resolve_agendas(self.factions, self.hex_map, resolve_choices,
                       self.wars, events,
                       guided_expand_choices=guided_expand_choices)

        # Add visual change events for guided change factions.
        # The modifier was already applied; this puts them in the
        # resolution batch so they animate in normal agenda order.
        guided_modifiers = self._guided_change_modifiers
        for fid in guided_change:
            modifier = guided_modifiers.get(fid, "")
            if modifier:
                events.append({
                    "type": "change",
                    "faction": fid,
                    "modifier": modifier,
                })
        self._guided_change_modifiers = {}
        self.expand_chosen.clear()

        self._finalize_agenda_phase(events)

        self._stored_agenda_choices = {}
        self._guided_change_factions = []
        return events

    def _resolve_agenda_phase(self) -> list[dict]:
        """Resolve agenda phase (direct path via resolve_current_phase).

        Handles both prepare and resolve in one step. Used when called
        directly (e.g. from tests or when no change choices are needed).
        Expand choices are auto-resolved randomly (no interactive sub-phase).
        """
        if not self._stored_agenda_choices:
            # Need to prepare first (direct call path)
            events = self.prepare_change_choices()
            # Auto-resolve guided expand choices (non-interactive direct path)
            self.prepare_expand_choices()
            for spirit_id, faction_id in list(self.expand_pending.items()):
                reachable = list(self.hex_map.get_reachable_neutral_hexes(faction_id))
                if reachable:
                    self.expand_chosen[spirit_id] = random.choice(reachable)
                del self.expand_pending[spirit_id]
            if self.change_pending:
                # Change choices needed - can't resolve yet
                return events
            events.extend(self.resolve_agenda_phase_after_changes())
            return events
        return self.resolve_agenda_phase_after_changes()

    def finalize_sub_choices(self) -> list[dict]:
        """Called after all ejection choices are submitted. Ejects spirits and advances to CLEANUP."""
        events = []
        self._process_ejections(events)
        self.phase = Phase.CLEANUP
        return events

    def _finalize_agenda_phase(self, events: list):
        """Clear agenda state and advance to war phase."""
        self.phase = Phase.WAR_PHASE

    def _process_ejections(self, events: list):
        """Eject all 0-influence spirits whose ejection choices have been submitted."""
        spirits_to_eject = []
        for spirit in self.spirits.values():
            if not spirit.is_vagrant and spirit.guided_faction and spirit.influence == 0:
                if spirit.spirit_id not in self.ejection_pending:
                    spirits_to_eject.append(spirit)

        for spirit in spirits_to_eject:
            faction = self.factions[spirit.guided_faction]
            faction.guiding_spirit = None
            # Check worship on leaving
            self._check_worship(faction, spirit, events)
            spirit.become_vagrant()
            events.append({
                "type": "ejected",
                "spirit": spirit.spirit_id,
                "faction": faction.faction_id,
            })

        self.ejection_pending.clear()

    def _resolve_war_phase(self) -> list[dict]:
        events = []
        dice_results = []

        # Snapshot territory counts for simultaneous power calculation
        power_snapshot = {
            fid: len(self.hex_map.get_faction_territories(fid))
            for fid in self.factions
        }

        # Resolve all wars that erupted this turn
        for war in list(self.wars):
            guided_a = self.factions[war.faction_a].guiding_spirit
            guided_b = self.factions[war.faction_b].guiding_spirit

            if (guided_a and not guided_b) or (guided_b and not guided_a):
                # Exactly one faction is guided — that spirit picks the winner
                spirit_id = guided_a or guided_b
                guided_faction = war.faction_a if guided_a else war.faction_b
                self.winner_choice_pending.setdefault(spirit_id, []).append({
                    "war_id": war.war_id,
                    "faction_a": war.faction_a,
                    "faction_b": war.faction_b,
                    "guided_faction": guided_faction,
                })
            else:
                # Both or neither guided — dice formula
                result = war.resolve(power_snapshot[war.faction_a],
                                     power_snapshot[war.faction_b])
                dice_results.append(result)
                events.append({"type": "war_resolved", **result})
                if result.get("winner"):
                    self.factions[result["winner"]].wars_won_this_turn += 1
                self.wars.remove(war)

        # If winner choices are pending, save dice results and wait
        if self.winner_choice_pending:
            self._war_results_dice = dice_results
            return events

        # No winner choices needed — proceed to spoils immediately
        self._setup_spoils(dice_results, events)
        return events

    def _setup_spoils(self, war_results: list[dict], events: list[dict]) -> None:
        """Set up spoils pending state for the given war_results and finalize if no choices needed."""
        if war_results:
            raw_pending, self.auto_spoils_choices = resolve_spoils(
                self.factions, self.hex_map, war_results, self.wars,
                events, self.normal_trade_factions, spirits=self.spirits)
            # Convert plain dicts from resolve_spoils into SpoilsPendingEntry objects
            self.spoils_pending = {
                spirit_id: [
                    SpoilsPendingEntry(
                        winner=d["winner"], loser=d["loser"], cards=d["cards"],
                    )
                    for d in entries
                ]
                for spirit_id, entries in raw_pending.items()
            }
        else:
            self.spoils_pending = {}
            self.auto_spoils_choices = []

        if not self.spoils_pending:
            # No guided choices needed — finalize all spoils now
            self._finalize_spoils(events)
        # Otherwise stay in WAR_PHASE until spoils choices are submitted

    def has_pending_winner_choices(self) -> bool:
        """Return True if any spirit still needs to submit a winner choice."""
        return bool(self.winner_choice_pending)

    def submit_winner_choice(self, spirit_id: str, choices: list[dict]) -> tuple:
        """Submit winner choices for one-guided wars. Returns (error, events).

        choices: list of {war_id, winner: faction_id}
        """
        if spirit_id not in self.winner_choice_pending:
            return "No winner choice pending", []

        pending_entries = self.winner_choice_pending[spirit_id]
        pending_by_war = {e["war_id"]: e for e in pending_entries}

        if len(choices) != len(pending_entries):
            return f"Expected {len(pending_entries)} choices, got {len(choices)}", []

        events = []
        for choice in choices:
            war_id = choice.get("war_id")
            if war_id not in pending_by_war:
                return f"Unknown war_id {war_id}", []
            entry = pending_by_war[war_id]
            chosen_winner = choice.get("winner")
            if chosen_winner not in (entry["faction_a"], entry["faction_b"]):
                return f"Invalid winner {chosen_winner}", []

            war = next((w for w in self.wars if w.war_id == war_id), None)
            if war is None:
                return f"War {war_id} not found", []

            result = war.resolve_forced(chosen_winner, entry["guided_faction"])
            self._war_results_dice.append(result)
            events.append({"type": "war_resolved", **result})
            if result.get("winner"):
                self.factions[result["winner"]].wars_won_this_turn += 1
            self.wars.remove(war)

        del self.winner_choice_pending[spirit_id]

        if not self.winner_choice_pending:
            self._setup_spoils(self._war_results_dice, events)
            self._war_results_dice = []

        return None, events

    def _resolve_scoring(self) -> list[dict]:
        # Check worship for all guided factions before scoring
        events = []
        for fid, faction in self.factions.items():
            if faction.guiding_spirit:
                spirit = self.spirits.get(faction.guiding_spirit)
                if spirit:
                    self._check_worship(faction, spirit, events)

        events.extend(calculate_scoring(self.factions, self.spirits, self.hex_map))

        # Check for winner
        winner = None
        max_vp = 0
        for spirit in self.spirits.values():
            if spirit.victory_points >= self.vp_to_win:
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
            # Check for ejection (0 influence spirits) before cleanup
            for spirit in self.spirits.values():
                if not spirit.is_vagrant and spirit.guided_faction and spirit.influence == 0:
                    faction_id = spirit.guided_faction
                    self.ejection_pending[spirit.spirit_id] = faction_id
                    events.append({
                        "type": "ejection_pending",
                        "spirit": spirit.spirit_id,
                        "faction": faction_id,
                    })

            if not self.ejection_pending:
                self.phase = Phase.CLEANUP
            # Otherwise stay in SCORING until ejection choices are submitted

        return events

    def _resolve_cleanup(self) -> list[dict]:
        events = []
        # Return played/spoils cards to decks, then reset turn tracking
        for faction in self.factions.values():
            faction.cleanup_deck()
            faction.reset_turn_tracking()

        # Clear all transient per-turn state
        self.pending_actions.clear()
        self.drawn_hands.clear()
        self.change_pending.clear()
        self.ejection_pending.clear()
        self.spoils_pending.clear()
        self.auto_spoils_choices.clear()
        self.winner_choice_pending.clear()
        self._war_results_dice.clear()
        self._stored_agenda_choices = {}
        self._guided_change_factions = []
        self._guided_change_modifiers = {}
        self.expand_pending.clear()
        self.expand_chosen.clear()

        self.turn += 1
        self.phase = Phase.VAGRANT_PHASE
        events.append({"type": "turn_start", "turn": self.turn})
        return events

    def submit_spoils_choice(self, spirit_id: str, card_indices: list[int]) -> tuple[Optional[str], list[dict]]:
        """Submit spoils card choices for all pending wars. Returns (error, events).

        card_indices: list of chosen card index per pending war.
        """
        if spirit_id not in self.spoils_pending:
            return "No spoils pending", []
        pending_list = self.spoils_pending[spirit_id]
        if len(card_indices) != len(pending_list):
            return f"Expected {len(pending_list)} choices, got {len(card_indices)}", []
        for i, idx in enumerate(card_indices):
            if idx < 0 or idx >= len(pending_list[i].cards):
                return f"Invalid card index {idx} for war {i}", []

        events = []
        change_needed = False
        expand_needed = False
        # Process all choices, recording them on the pending entries
        for i in range(len(pending_list) - 1, -1, -1):
            pending = pending_list[i]
            chosen = pending.cards[card_indices[i]]
            pending.chosen_card = chosen

            faction = self.factions[pending.winner]
            from shared.models import AgendaCard
            faction.played_agenda_this_turn.append(AgendaCard(chosen))

            events.append({
                "type": "spoils_drawn",
                "faction": pending.winner,
                "agenda": chosen.value,
            })

            if chosen == AgendaType.CHANGE:
                spirit = self.spirits[spirit_id]
                draw_count = 1 + spirit.influence
                change_cards = random.sample(CHANGE_DECK, min(draw_count, len(CHANGE_DECK)))
                pending.stage = SubPhase.CHANGE_CHOICE
                pending.change_cards = change_cards
                change_needed = True
            elif chosen == AgendaType.EXPAND:
                # Spirit must choose which adjacent enemy territory to conquer
                enemy_territories = self.hex_map.get_adjacent_enemy_territories(pending.winner, pending.loser)
                if enemy_territories:
                    pending.stage = SubPhase.SPOILS_EXPAND_CHOICE
                    pending.expand_hexes = enemy_territories
                    expand_needed = True

        if not change_needed and not expand_needed:
            # All choices made, collect for batch finalization
            for pending in pending_list:
                self.auto_spoils_choices.append({
                    "winner": pending.winner,
                    "loser": pending.loser,
                    "agenda_type": pending.chosen_card,
                    "target_hex": None,
                    "guided": True,
                })
            del self.spoils_pending[spirit_id]

        # If all guided spirits have submitted, finalize
        if not self.spoils_pending:
            self._finalize_spoils(events)
        return None, events

    def submit_spoils_change_choice(self, spirit_id: str, card_indices: list[int]) -> tuple[Optional[str], list[dict]]:
        """Submit spoils change modifier choices. Returns (error, events).

        card_indices: list of chosen modifier index per pending change choice.
        """
        if spirit_id not in self.spoils_pending:
            return "No spoils pending", []
        pending_list = self.spoils_pending[spirit_id]
        change_pendings = [p for p in pending_list if p.stage == SubPhase.CHANGE_CHOICE]
        if len(card_indices) != len(change_pendings):
            return f"Expected {len(change_pendings)} change choices, got {len(card_indices)}", []
        for i, idx in enumerate(card_indices):
            if idx < 0 or idx >= len(change_pendings[i].change_cards):
                return f"Invalid change card index {idx} for choice {i}", []

        events = []
        for i, pending in enumerate(change_pendings):
            chosen = pending.change_cards[card_indices[i]]
            winner = pending.winner
            faction = self.factions[winner]
            faction.add_change_modifier(chosen)
            pending.chosen_card = AgendaType.CHANGE
            pending.stage = ""
            events.append({
                "type": "change",
                "faction": winner,
                "modifier": chosen.value,
            })

        # Check if any Expand choices are still pending
        expand_pendings = [p for p in pending_list if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
        if expand_pendings:
            return None, events  # stay pending — expand choices still needed

        # All sub-choices resolved — collect for batch finalization
        for pending in pending_list:
            target_hex = pending.expand_target if pending.chosen_card == AgendaType.EXPAND else None
            self.auto_spoils_choices.append({
                "winner": pending.winner,
                "loser": pending.loser,
                "agenda_type": pending.chosen_card if pending.chosen_card is not None else AgendaType.CHANGE,
                "target_hex": target_hex,
                "guided": True,
            })
        del self.spoils_pending[spirit_id]

        if not self.spoils_pending:
            self._finalize_spoils(events)
        return None, events

    def submit_spoils_expand_choice(self, spirit_id: str, choices: list[dict]) -> tuple[Optional[str], list[dict]]:
        """Submit spoils Expand target hex choices for guided winners.

        choices: list of {war_index, hex: {q, r}} where war_index is the position
        in the pending_list for this spirit's EXPAND_CHOICE entries.
        """
        if spirit_id not in self.spoils_pending:
            return "No spoils pending", []
        pending_list = self.spoils_pending[spirit_id]
        expand_pendings = [p for p in pending_list if p.stage == SubPhase.SPOILS_EXPAND_CHOICE]
        if len(choices) != len(expand_pendings):
            return f"Expected {len(expand_pendings)} expand choices, got {len(choices)}", []

        events = []
        for i, pending in enumerate(expand_pendings):
            h = choices[i].get("hex", {})
            chosen_hex = (h.get("q", 0), h.get("r", 0))
            if chosen_hex not in pending.expand_hexes:
                return f"Hex {chosen_hex} is not a valid enemy territory", []
            pending.expand_target = chosen_hex
            pending.stage = ""

        # Collect all entries for batch finalization
        for pending in pending_list:
            target_hex = pending.expand_target if pending.chosen_card == AgendaType.EXPAND else None
            self.auto_spoils_choices.append({
                "winner": pending.winner,
                "loser": pending.loser,
                "agenda_type": pending.chosen_card,
                "target_hex": target_hex,
                "guided": True,
            })
        del self.spoils_pending[spirit_id]

        if not self.spoils_pending:
            self._finalize_spoils(events)
        return None, events

    def _finalize_spoils(self, events: list):
        """Finalize all spoils simultaneously and advance to scoring.

        Guided Change modifiers are already applied during submit_spoils_change_choice
        and must be excluded from the batch to avoid double-applying.
        Guided Expand targets have been recorded in target_hex and are included.
        """
        if self.auto_spoils_choices:
            # Filter out guided Change entries (modifier already applied)
            batch = []
            for entry in self.auto_spoils_choices:
                if entry["agenda_type"] == AgendaType.CHANGE:
                    winner = entry["winner"]
                    faction = self.factions[winner]
                    if faction.guiding_spirit and faction.guiding_spirit in self.spirits:
                        continue
                batch.append(entry)
            finalize_all_spoils(self.factions, self.hex_map, self.wars, events,
                               batch, self.normal_trade_factions)
        self.auto_spoils_choices = []
        self._check_respawns(events)
        if not self.respawn_pending:
            self.phase = Phase.SCORING

    def has_pending_sub_choices(self) -> bool:
        """Check if ejection choices are still pending (change is handled earlier)."""
        return bool(self.ejection_pending)
