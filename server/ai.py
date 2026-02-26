"""AI player action helpers — fully random within valid options."""

import random
from shared.hex_utils import hex_neighbors


def _would_gain_worship(game_state, spirit_id: str, faction_id: str) -> bool:
    """Return True if guiding faction_id would grant spirit_id worship of it."""
    faction = game_state.factions[faction_id]
    if faction.worship_spirit is None:
        return True
    # Another spirit holds worship — AI gains it only if it has >= idols in territory
    current_idols = game_state.hex_map.count_spirit_idols_in_faction(
        faction.worship_spirit, faction_id)
    new_idols = game_state.hex_map.count_spirit_idols_in_faction(
        spirit_id, faction_id)
    return new_idols >= current_idols

AI_NAMES = ["Amadeus", "Catherine", "Dumisai", "Eudokia", "Grem", "Hanno", "Ivah", "Kairos"]


def assign_ai_names(count: int) -> list[str]:
    return random.sample(AI_NAMES, count)


def get_ai_vagrant_action(game_state, spirit_id, excluded_factions=None) -> dict:
    options = game_state.get_phase_options(spirit_id)
    available = [
        f for f in options.get("available_factions", [])
        if excluded_factions is None or f not in excluded_factions
    ]
    can_place = options.get("can_place_idol", False)
    neutral = options.get("neutral_hexes", [])
    idol_types = options.get("idol_types", [])

    # Exclude hexes where this spirit already has an idol
    existing_idol_positions = {
        (i.position.q, i.position.r)
        for i in game_state.hex_map.idols
        if i.owner_spirit == spirit_id
    }

    # Filter neutral hexes: must be adjacent to at least one owned (non-neutral) hex
    valid_idol_hexes = [
        h for h in neutral
        if (h["q"], h["r"]) not in existing_idol_positions
        and any(
            game_state.hex_map.ownership.get((nq, nr)) is not None
            for nq, nr in hex_neighbors(h["q"], h["r"])
            if (nq, nr) in game_state.hex_map.ownership
        )
    ]
    # Fallback: if no faction-adjacent neutral hex found, use any eligible neutral hex
    idol_hexes = valid_idol_hexes if valid_idol_hexes else [
        h for h in neutral if (h["q"], h["r"]) not in existing_idol_positions
    ]
    can_place = can_place and bool(idol_hexes)

    def choose_guide_target(candidates):
        # Priority 1: factions where guiding would grant worship
        worship_candidates = [
            fid for fid in candidates
            if _would_gain_worship(game_state, spirit_id, fid)
        ]
        pool = worship_candidates if worship_candidates else candidates
        if worship_candidates:
            # Priority 2: most total idols in territory
            idol_counts = {
                fid: len(game_state.hex_map.get_idols_in_territories(fid))
                for fid in pool
            }
            max_idols = max(idol_counts.values())
            pool = [fid for fid in pool if idol_counts[fid] == max_idols]
            # Priority 3: factions that already worship another spirit
            already_worshipped = [
                fid for fid in pool
                if game_state.factions[fid].worship_spirit is not None
            ]
            if already_worshipped:
                pool = already_worshipped
        return random.choice(pool)

    can_swell = options.get("can_swell", False)

    action = {}
    if available and can_place:
        action["guide_target"] = choose_guide_target(available)
        h = random.choice(idol_hexes)
        action["idol_type"] = random.choice(idol_types)
        action["idol_q"], action["idol_r"] = h["q"], h["r"]
    elif available:
        action["guide_target"] = choose_guide_target(available)
    elif can_place:
        h = random.choice(idol_hexes)
        action["idol_type"] = random.choice(idol_types)
        action["idol_q"], action["idol_r"] = h["q"], h["r"]
    elif can_swell:
        action["swell"] = True
    return action


def get_ai_agenda_choice(game_state, spirit_id) -> dict:
    options = game_state.get_phase_options(spirit_id)
    hand = options.get("hand", [])
    return {"agenda_index": random.randrange(len(hand))} if hand else {}


def get_ai_change_choice(cards: list) -> int:
    return random.randrange(len(cards))


def get_ai_ejection_choice(agenda_pool: list, agenda_types: list) -> tuple[str, str]:
    return random.choice(agenda_pool), random.choice(agenda_types)


def get_ai_spoils_choice(pending_list) -> list[int]:
    return [random.randrange(len(p.cards)) for p in pending_list]


def get_ai_spoils_change_choice(change_pendings) -> list[int]:
    return [random.randrange(len(p.change_cards)) for p in change_pendings]


def get_ai_battleground_choice(war_choices: list[dict]) -> list[dict]:
    """Random battleground selection — picks first valid option for each war."""
    result = []
    for wc in war_choices:
        if wc["mode"] == "full":
            result.append({"war_id": wc["war_id"], "pair_index": 0})
        else:
            h = wc["enemy_hexes"][0]
            result.append({"war_id": wc["war_id"], "hex": h})
    return result
