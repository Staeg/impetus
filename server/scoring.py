"""Victory point calculation per phase."""

from shared.constants import (
    IdolType,
    BATTLE_IDOL_VP,
    AFFLUENCE_IDOL_VP,
    SPRAWL_IDOL_VP,
    ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER,
    Era,
)


def _spirit_faction_multiplier(spirit, faction_id: str) -> float:
    devotion_map = {
        "Mesa Devotion": "mesa",
        "Mountain Devotion": "mountain",
        "Sand Devotion": "sand",
        "Jungle Devotion": "jungle",
        "River Devotion": "river",
        "Plains Devotion": "plains",
    }
    for card_name, devoted_faction in devotion_map.items():
        if card_name in spirit.adaptation_effects:
            return 3.0 if devoted_faction == faction_id else 0.5
    return 1.0


def _spirit_idol_multiplier(spirit, idol_type) -> float:
    avatar_map = {
        "Avatar of Battle": IdolType.BATTLE,
        "Avatar of Affluence": IdolType.AFFLUENCE,
        "Avatar of Sprawl": IdolType.SPRAWL,
    }
    for card_name, matching_type in avatar_map.items():
        if card_name in spirit.adaptation_effects:
            return 2.0 if idol_type == matching_type else 0.5
    return 1.0


def calculate_scoring(factions: dict, spirits: dict, hex_map, era: Era = Era.ERA_1) -> list[dict]:
    """Calculate VP for all spirits based on Worship and idols.

    Returns a list of scoring event dicts.
    """
    events = []

    for faction_id, faction in factions.items():
        if not faction.worship_spirit:
            continue

        worship_spirit = spirits.get(faction.worship_spirit)
        if not worship_spirit:
            continue

        idols = hex_map.get_idols_in_territories(faction_id)
        if not idols:
            continue

        battle_idols = sum(1 for i in idols if i.type == IdolType.BATTLE)
        affluence_idols = sum(1 for i in idols if i.type == IdolType.AFFLUENCE)
        sprawl_idols = sum(1 for i in idols if i.type == IdolType.SPRAWL)

        recipients = {faction.worship_spirit}
        if era == Era.ERA_2:
            recipients.update({idol.owner_spirit for idol in idols})

        for spirit_id in recipients:
            spirit = spirits.get(spirit_id)
            if not spirit:
                continue
            battle_share = 0.0
            affluence_share = 0.0
            sprawl_share = 0.0

            for idol in idols:
                if era == Era.ERA_1:
                    if spirit_id != faction.worship_spirit:
                        continue
                    share = 1.0
                else:
                    share = 0.0
                    if spirit_id == faction.worship_spirit:
                        share += 0.5
                    if spirit_id == idol.owner_spirit:
                        share += 0.5
                    if "Usurper" in spirit.adaptation_effects and spirit_id == faction.worship_spirit:
                        share += 0.5
                share *= _spirit_faction_multiplier(spirit, faction_id)
                share *= _spirit_idol_multiplier(spirit, idol.type)

                if idol.type == IdolType.BATTLE:
                    battle_share += share * BATTLE_IDOL_VP * faction.wars_won_this_turn
                elif idol.type == IdolType.AFFLUENCE:
                    affluence_base = AFFLUENCE_IDOL_VP * faction.gold_gained_this_turn
                    if era == Era.ERA_2:
                        affluence_base *= ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER
                    affluence_share += share * affluence_base
                elif idol.type == IdolType.SPRAWL:
                    sprawl_share += share * SPRAWL_IDOL_VP * faction.territories_gained_this_turn

            vp_gained = battle_share + affluence_share + sprawl_share
            if vp_gained > 0:
                era_multipliers = []
                if era == Era.ERA_2:
                    era_multipliers.append({
                        "label": "Era 2",
                        "scope": IdolType.AFFLUENCE.value,
                        "multiplier": ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER,
                    })
                faction_multiplier = _spirit_faction_multiplier(spirit, faction_id)
                adaptation_multipliers = []
                if faction_multiplier != 1.0:
                    for card_name in spirit.adaptation_effects:
                        if "Devotion" in card_name:
                            adaptation_multipliers.append({
                                "label": card_name,
                                "scope": faction_id,
                                "multiplier": faction_multiplier,
                            })
                            break
                for idol_type in (IdolType.BATTLE, IdolType.AFFLUENCE, IdolType.SPRAWL):
                    idol_multiplier = _spirit_idol_multiplier(spirit, idol_type)
                    if idol_multiplier != 1.0:
                        for card_name in spirit.adaptation_effects:
                            if ((idol_type == IdolType.BATTLE and card_name == "Avatar of Battle")
                                    or (idol_type == IdolType.AFFLUENCE and card_name == "Avatar of Affluence")
                                    or (idol_type == IdolType.SPRAWL and card_name == "Avatar of Sprawl")):
                                adaptation_multipliers.append({
                                    "label": card_name,
                                    "scope": idol_type.value,
                                    "multiplier": idol_multiplier,
                                })
                                break
                if "Usurper" in spirit.adaptation_effects and era == Era.ERA_2 and spirit_id == faction.worship_spirit:
                    adaptation_multipliers.append({
                        "label": "Usurper",
                        "scope": "ownership_share",
                        "multiplier": 1.5,
                    })
                spirit.victory_points += vp_gained
                events.append({
                    "type": "vp_scored",
                    "spirit": spirit.spirit_id,
                    "faction": faction_id,
                    "battle_idols": battle_idols,
                    "affluence_idols": affluence_idols,
                    "sprawl_idols": sprawl_idols,
                    "wars_won": faction.wars_won_this_turn,
                    "gold_gained": faction.gold_gained_this_turn,
                    "territories_gained": faction.territories_gained_this_turn,
                    "era_multipliers": era_multipliers,
                    "adaptation_multipliers": adaptation_multipliers,
                    "vp_gained": vp_gained,
                    "total_vp": spirit.victory_points,
                })

    return events
