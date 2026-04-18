"""Victory point calculation per phase."""

from __future__ import annotations

from shared.constants import (
    IdolType,
    BATTLE_IDOL_VP,
    AFFLUENCE_IDOL_VP,
    SPRAWL_IDOL_VP,
    ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER,
    Era,
)


def _factor_segment(label: str, multiplier: float, tooltip: str) -> dict:
    text = f"* {multiplier:g}"
    return {"text": text, "label": label, "multiplier": multiplier, "tooltip": tooltip}


def _spirit_faction_factors(spirit, faction_id: str) -> list[dict]:
    devotion_map = {
        "Mesa Devotion": ("mesa", "VP gained from Mesa is tripled; VP from other factions is halved."),
        "Mountain Devotion": ("mountain", "VP gained from Mountain is tripled; VP from other factions is halved."),
        "Sand Devotion": ("sand", "VP gained from Sand is tripled; VP from other factions is halved."),
        "Jungle Devotion": ("jungle", "VP gained from Jungle is tripled; VP from other factions is halved."),
        "River Devotion": ("river", "VP gained from River is tripled; VP from other factions is halved."),
        "Plains Devotion": ("plains", "VP gained from Plains is tripled; VP from other factions is halved."),
    }
    factors = []
    for card_name, (devoted_faction, tooltip) in devotion_map.items():
        if card_name not in spirit.adaptation_effects:
            continue
        multiplier = 3.0 if devoted_faction == faction_id else 0.5
        factors.append(_factor_segment(card_name, multiplier, f"{card_name}: {tooltip}"))
    return factors


def _spirit_idol_factors(spirit, idol_type) -> list[dict]:
    avatar_map = {
        "Avatar of Battle": (IdolType.BATTLE, "VP gained from Battle Idols is doubled; VP from other Idol types is halved."),
        "Avatar of Affluence": (IdolType.AFFLUENCE, "VP gained from Affluence Idols is doubled; VP from other Idol types is halved."),
        "Avatar of Sprawl": (IdolType.SPRAWL, "VP gained from Sprawl Idols is doubled; VP from other Idol types is halved."),
    }
    factors = []
    for card_name, (matching_type, tooltip) in avatar_map.items():
        if card_name not in spirit.adaptation_effects:
            continue
        multiplier = 2.0 if idol_type == matching_type else 0.5
        factors.append(_factor_segment(card_name, multiplier, f"{card_name}: {tooltip}"))
    return factors


def _multiply_factors(factors: list[dict]) -> float:
    result = 1.0
    for factor in factors:
        result *= factor["multiplier"]
    return result


def _format_breakdown_line(prefix: str, base_value: float, factors: list[dict], total_value: float) -> tuple[str, list[dict]]:
    parts = [prefix]
    spans = []
    cursor = len(prefix)
    for factor in factors:
        segment = f" {factor['text']}"
        start = cursor + 1
        parts.append(segment)
        cursor += len(segment)
        spans.append({
            "start": start,
            "end": start + len(factor["text"]),
            "tooltip": factor["tooltip"],
        })
    total_text = f" = {total_value:.1f}"
    parts.append(total_text)
    return "".join(parts), spans


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

            contribution_groups: dict[tuple, dict] = {}

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
                    if ("Usurper" in spirit.adaptation_effects
                            and spirit_id == faction.worship_spirit
                            and spirit_id != idol.owner_spirit):
                        share += 0.5

                if share <= 0:
                    continue

                idol_type = idol.type
                factors = []
                if era == Era.ERA_2 and idol_type == IdolType.AFFLUENCE:
                    factors.append(_factor_segment("Era 2", ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER, "Era 2 applies a global Affluence nerf before other multipliers."))
                if era == Era.ERA_2 and share != 1.0:
                    if spirit_id == faction.worship_spirit and spirit_id == idol.owner_spirit:
                        tooltip = "Era 2 share: 0.5 for worship plus 0.5 for owning the Idol."
                    elif spirit_id == faction.worship_spirit and "Usurper" in spirit.adaptation_effects:
                        tooltip = "Era 2 share: 0.5 for worship plus 0.5 extra from Usurper."
                    elif spirit_id == faction.worship_spirit:
                        tooltip = "Era 2 share: the worshipping Spirit gets half of each Idol's VP."
                    else:
                        tooltip = "Era 2 share: the Idol's owner gets half of that Idol's VP."
                    factors.append(_factor_segment("Era 2 share", share, tooltip))
                factors.extend(_spirit_faction_factors(spirit, faction_id))
                factors.extend(_spirit_idol_factors(spirit, idol_type))

                multiplier = _multiply_factors(factors)
                if idol_type == IdolType.BATTLE:
                    label, suffix, base_unit, amount = "Battle", "wars", BATTLE_IDOL_VP, faction.wars_won_this_turn
                elif idol_type == IdolType.AFFLUENCE:
                    label, suffix, base_unit, amount = "Affluence", "gold", AFFLUENCE_IDOL_VP, faction.gold_gained_this_turn
                else:
                    label, suffix, base_unit, amount = "Sprawl", "terr", SPRAWL_IDOL_VP, faction.territories_gained_this_turn
                key = (
                    idol_type.value,
                    tuple((factor["text"], factor["tooltip"]) for factor in factors),
                )
                group = contribution_groups.setdefault(key, {
                    "label": label,
                    "suffix": suffix,
                    "base_unit": base_unit,
                    "amount": amount,
                    "count": 0,
                    "value": 0.0,
                    "factors": factors,
                })
                base_value = base_unit * amount
                group["count"] += 1
                group["value"] += base_value * multiplier

            vp_gained = sum(item["value"] for item in contribution_groups.values())
            if vp_gained > 0:
                spirit.victory_points += vp_gained
                contributions = []
                ordered_groups = sorted(
                    contribution_groups.values(),
                    key=lambda item: {"Battle": 0, "Affluence": 1, "Sprawl": 2}.get(item["label"], 99),
                )
                for info in ordered_groups:
                    if not info["count"] or not info["amount"] or info["value"] <= 0:
                        continue
                    prefix = f"  {info['label']}: {info['count']} idol x {info['amount']} {info['suffix']}"
                    line, spans = _format_breakdown_line(prefix, info["base_unit"] * info["amount"], info["factors"], info["value"])
                    contributions.append({"line": line, "spans": spans})

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
                    "vp_gained": vp_gained,
                    "total_vp": spirit.victory_points,
                    "contributions": contributions,
                })

    return events
