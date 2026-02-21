"""Victory point calculation per phase."""

from shared.constants import IdolType, BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP


def calculate_scoring(factions: dict, spirits: dict, hex_map) -> list[dict]:
    """Calculate VP for all spirits based on Worship and idols.

    Returns a list of scoring event dicts.
    """
    events = []

    for faction_id, faction in factions.items():
        if not faction.worship_spirit:
            continue

        spirit = spirits.get(faction.worship_spirit)
        if not spirit:
            continue

        idols = hex_map.get_idols_in_territories(faction_id)
        if not idols:
            continue

        battle_idols = sum(1 for i in idols if i.type == IdolType.BATTLE)
        affluence_idols = sum(1 for i in idols if i.type == IdolType.AFFLUENCE)
        spread_idols = sum(1 for i in idols if i.type == IdolType.SPREAD)

        vp_gained = (battle_idols * BATTLE_IDOL_VP * faction.wars_won_this_turn
                     + affluence_idols * AFFLUENCE_IDOL_VP * faction.gold_gained_this_turn
                     + spread_idols * SPREAD_IDOL_VP * faction.territories_gained_this_turn)

        if vp_gained > 0:
            spirit.victory_points += vp_gained
            events.append({
                "type": "vp_scored",
                "spirit": spirit.spirit_id,
                "faction": faction_id,
                "battle_idols": battle_idols,
                "affluence_idols": affluence_idols,
                "spread_idols": spread_idols,
                "wars_won": faction.wars_won_this_turn,
                "gold_gained": faction.gold_gained_this_turn,
                "territories_gained": faction.territories_gained_this_turn,
                "vp_gained": vp_gained,
                "total_vp": spirit.victory_points,
            })

    return events
