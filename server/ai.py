"""AI player action helpers — fully random within valid options."""

import random
from shared.hex_utils import hex_neighbors

AI_NAMES = ["Amadeus", "Brandon", "Catherine", "Dumisai", "Eudokia"]


def assign_ai_names(count: int) -> list[str]:
    return random.sample(AI_NAMES, count)


def get_ai_vagrant_action(game_state, spirit_id) -> dict:
    options = game_state.get_phase_options(spirit_id)
    available = options.get("available_factions", [])
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

    action = {}
    if available and can_place:
        action["guide_target"] = random.choice(available)
        h = random.choice(idol_hexes)
        action["idol_type"] = random.choice(idol_types)
        action["idol_q"], action["idol_r"] = h["q"], h["r"]
    elif available:
        action["guide_target"] = random.choice(available)
    elif can_place:
        h = random.choice(idol_hexes)
        action["idol_type"] = random.choice(idol_types)
        action["idol_q"], action["idol_r"] = h["q"], h["r"]
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
