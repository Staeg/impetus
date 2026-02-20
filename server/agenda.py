"""Agenda card system and resolution logic."""

import random
from shared.constants import AgendaType, AGENDA_RESOLUTION_ORDER, ChangeModifierTarget, CHANGE_DECK
from server.war import War


def resolve_agendas(factions: dict, hex_map, agenda_choices: dict[str, AgendaType],
                    wars: list, events: list, is_spoils: bool = False,
                    spoils_conquests: dict = None,
                    normal_trade_factions: list[str] = None,
                    faction_counts: dict[str, int] = None):
    """Resolve all agenda choices in the correct order.

    Args:
        factions: dict of faction_id -> Faction
        hex_map: HexMap instance
        agenda_choices: dict of faction_id -> AgendaType chosen
        wars: list of active War objects (will be mutated to add new wars)
        events: list to append event dicts to
        is_spoils: if True, these are Spoils of War agendas
        spoils_conquests: dict of faction_id -> hex coord (or list of coords) for spoils expand targets
        normal_trade_factions: factions that traded normally this turn (for spoils trade)
        faction_counts: dict of faction_id -> int, how many times each faction plays this agenda type (for spoils duplicates). Defaults to 1 for all.
    """
    faction_counts = faction_counts or {}
    for agenda_type in AGENDA_RESOLUTION_ORDER:
        playing_factions = [fid for fid, choice in agenda_choices.items()
                           if choice == agenda_type]
        if not playing_factions:
            continue

        # Build per-agenda-type counts for this batch
        type_counts = {fid: faction_counts.get((fid, agenda_type), 1) for fid in playing_factions}

        if agenda_type == AgendaType.STEAL:
            _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils, type_counts)
        elif agenda_type == AgendaType.TRADE:
            _resolve_trade(factions, playing_factions, events, is_spoils,
                          normal_trade_factions or [], type_counts)
        elif agenda_type == AgendaType.EXPAND:
            _resolve_expand(factions, hex_map, playing_factions, events, is_spoils, spoils_conquests, type_counts)
        elif agenda_type == AgendaType.CHANGE:
            _resolve_change(factions, playing_factions, events, is_spoils, type_counts)


def _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils, faction_counts=None):
    """Steal: -1 regard and -1 gold to all neighbors. +1 gold per gold lost by neighbors.
    Then wars erupt with neighbors at -2 regard or less."""
    faction_counts = faction_counts or {}
    # Calculate gold losses simultaneously
    gold_losses = {}  # faction_id -> gold actually lost
    gold_gains = {}   # stealing faction -> gold gained
    regard_changes = []

    neighbor_map = {}  # stealing faction -> list of neighbor faction IDs
    regard_penalty_map = {}  # stealing faction -> regard_penalty value

    for fid in playing_factions:
        faction = factions[fid]
        count = faction_counts.get(fid, 1)
        steal_bonus = faction.change_modifiers.get(ChangeModifierTarget.STEAL, 0)
        gold_stolen_per_neighbor = (1 + steal_bonus) * count
        regard_penalty = (1 + steal_bonus) * count
        regard_penalty_map[fid] = regard_penalty
        total_gained = 0
        neighbors = hex_map.get_live_neighbor_ids(fid, factions)

        for other_fid in neighbors:
            other_faction = factions[other_fid]
            # Mark regard change (negate: regard_penalty is positive magnitude)
            regard_changes.append((fid, other_fid, -regard_penalty))
            # Calculate gold loss for neighbor (but don't apply yet - simultaneous)
            key = (fid, other_fid)
            actual_loss = min(other_faction.gold, gold_stolen_per_neighbor)
            gold_losses[key] = actual_loss
            total_gained += actual_loss

        neighbor_map[fid] = neighbors
        gold_gains[fid] = total_gained

    # Apply gold changes simultaneously
    # First, compute net gold loss per faction from all steals
    net_losses = {}
    for (stealer, victim), loss in gold_losses.items():
        net_losses[victim] = net_losses.get(victim, 0) + loss

    # But simultaneous means each steal sees original gold, so cap individually
    # Actually: simultaneous resolution means if A steals from B and C steals from B,
    # each sees B's original gold. So each independently takes min(B.gold, amount).
    # But B can't lose more than they have. We need to split fairly.
    # Simplification: each stealer takes min(victim_original_gold, amount), and
    # victim loses the total (capped at their gold).
    original_gold = {fid: f.gold for fid, f in factions.items()}

    # Apply losses to victims
    victim_total_loss = {}
    for (stealer, victim), loss in gold_losses.items():
        victim_total_loss[victim] = victim_total_loss.get(victim, 0) + loss

    for victim, total in victim_total_loss.items():
        actual = min(factions[victim].gold, total)
        if actual > 0:
            factions[victim].gold -= actual

    # Apply gains to stealers (always emit event for animations, even if 0 gold)
    for fid, gained in gold_gains.items():
        if gained > 0:
            factions[fid].add_gold(gained)
        events.append({
            "type": "steal",
            "faction": fid,
            "gold_gained": gained,
            "is_spoils": is_spoils,
            "regard_penalty": regard_penalty_map[fid],
            "neighbors": neighbor_map[fid],
        })

    # Apply regard changes
    for fid, other_fid, delta in regard_changes:
        factions[fid].modify_regard(other_fid, delta)
        factions[other_fid].modify_regard(fid, delta)

    # Check for war eruptions
    for fid in playing_factions:
        for other_fid in hex_map.get_live_neighbor_ids(fid, factions):
            regard = factions[fid].get_regard(other_fid)
            if regard <= -2:
                # Check if war already exists between these two
                existing = any(
                    (w.faction_a == fid and w.faction_b == other_fid) or
                    (w.faction_a == other_fid and w.faction_b == fid)
                    for w in wars
                )
                if not existing:
                    war = War(fid, other_fid)
                    wars.append(war)
                    events.append({
                        "type": "war_erupted",
                        "faction_a": fid,
                        "faction_b": other_fid,
                    })


def _resolve_trade(factions, playing_factions, events, is_spoils,
                   normal_trade_factions: list[str] = None, faction_counts=None):
    """Trade: +1 gold, +1 gold for every other faction playing Trade this turn.
    Also +1 regard with each other faction playing Trade this turn (bilateral).

    For spoils trade, normal_trade_factions counts as additional "others trading"
    for the spoils trader's bonus, and each normal trader gets +1 gold and regard.

    When faction_counts has count > 1 for a faction, gold is multiplied by count
    and regard is applied count times. Self-instances don't count as co-traders.
    """
    normal_trade_factions = normal_trade_factions or []
    faction_counts = faction_counts or {}

    # Determine all co-traders for each faction (for regard)
    for fid in playing_factions:
        faction = factions[fid]
        count = faction_counts.get(fid, 1)
        trade_bonus = faction.change_modifiers.get(ChangeModifierTarget.TRADE, 0)
        base = 1
        others_trading = len(playing_factions) - 1
        # Spoils traders also benefit from factions that traded normally this turn
        if is_spoils:
            others_trading += len(normal_trade_factions)
        total = (base + others_trading + trade_bonus * others_trading) * count
        faction.add_gold(total)

        # Regard: +1 + trade_bonus with each co-trader (bilateral), applied count times
        regard_gain = 1 + trade_bonus
        co_traders = [other for other in playing_factions if other != fid]
        if is_spoils:
            co_traders = co_traders + normal_trade_factions
        for other_fid in co_traders:
            faction.modify_regard(other_fid, regard_gain * count)
            factions[other_fid].modify_regard(fid, regard_gain * count)

        events.append({
            "type": "trade",
            "faction": fid,
            "gold_gained": total,
            "is_spoils": is_spoils,
            "regard_gain": regard_gain if co_traders else 0,
            "co_traders": co_traders,
        })

    # Spoils trade gives +1 gold (+ Trade modifier) and regard to every faction that traded normally
    if is_spoils and normal_trade_factions:
        for fid in normal_trade_factions:
            trade_bonus = factions[fid].change_modifiers.get(ChangeModifierTarget.TRADE, 0)
            bonus = 1 + trade_bonus
            factions[fid].add_gold(bonus)
            # Regard with each spoils trader
            regard_gain = 1 + trade_bonus
            spoils_traders = list(playing_factions)
            for spoils_fid in spoils_traders:
                factions[fid].modify_regard(spoils_fid, regard_gain)
                factions[spoils_fid].modify_regard(fid, regard_gain)
            events.append({
                "type": "trade_spoils_bonus",
                "faction": fid,
                "gold_gained": bonus,
                "regard_gain": regard_gain if spoils_traders else 0,
                "co_traders": spoils_traders,
            })


def _resolve_expand(factions, hex_map, playing_factions, events, is_spoils,
                    spoils_conquests: dict = None, faction_counts=None):
    """Expand: spend gold equal to territory count to claim a random neutral hex.
    If can't afford or no hexes available, +1 gold instead.

    For spoils: take the loser's battleground hex instead of paying gold.
    spoils_conquests maps faction_id -> list of hex coords to claim.
    """
    faction_counts = faction_counts or {}
    for fid in playing_factions:
        faction = factions[fid]
        expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
        expand_fail_bonus = 1 + expand_discount
        territory_count = len(hex_map.get_faction_territories(fid))
        cost = max(0, territory_count - expand_discount)

        if is_spoils and spoils_conquests and fid in spoils_conquests:
            # Spoils expand: take the target hex(es)
            targets = spoils_conquests[fid]
            if not isinstance(targets, list):
                targets = [targets]
            for target in targets:
                hex_map.claim_hex(target, fid)
                faction.territories_gained_this_turn += 1
                events.append({
                    "type": "expand_spoils",
                    "faction": fid,
                    "hex": {"q": target[0], "r": target[1]},
                })
            continue

        target = hex_map.get_random_reachable_neutral(fid)
        if target is not None and faction.gold >= cost:
            faction.gold -= cost
            hex_map.claim_hex(target, fid)
            faction.territories_gained_this_turn += 1
            events.append({
                "type": "expand",
                "faction": fid,
                "hex": {"q": target[0], "r": target[1]},
                "cost": cost,
            })
        else:
            faction.add_gold(expand_fail_bonus)
            events.append({
                "type": "expand_failed",
                "faction": fid,
                "gold_gained": expand_fail_bonus,
            })


def _resolve_change(factions, playing_factions, events, is_spoils=False, faction_counts=None):
    """Change: draw from the change modifier deck, apply permanent modifier."""
    faction_counts = faction_counts or {}
    for fid in playing_factions:
        faction = factions[fid]
        count = faction_counts.get(fid, 1)
        for _ in range(count):
            # Draw a random change card
            card = random.choice(CHANGE_DECK)
            faction.add_change_modifier(card)
            events.append({
                "type": "change",
                "faction": fid,
                "modifier": card.value,
                "is_spoils": is_spoils,
            })


def _cancel_wars_on_hex(wars, hex_coord, events, factions):
    """Cancel any wars whose battleground includes the given hex.

    Called after a spoils Expand conquers a battleground hex, since the
    territorial change invalidates other wars' battlegrounds.
    """
    from shared.constants import FACTION_DISPLAY_NAMES
    to_remove = []
    for w in wars:
        if not w.battleground:
            continue
        if w.battleground[0] == hex_coord or w.battleground[1] == hex_coord:
            to_remove.append(w)
    for w in to_remove:
        wars.remove(w)
        fa = FACTION_DISPLAY_NAMES.get(w.faction_a, w.faction_a)
        fb = FACTION_DISPLAY_NAMES.get(w.faction_b, w.faction_b)
        events.append({
            "type": "war_ended",
            "war_id": w.war_id,
            "reason": "territorial_changes",
            "faction_a": w.faction_a,
            "faction_b": w.faction_b,
            "message": f"War between {fa} and {fb} dissipated due to territorial changes.",
        })


def resolve_spoils(factions, hex_map, war_results, wars, events,
                   normal_trade_factions: list[str], spirits: dict = None):
    """Collect spoils draws for all war winners.

    Guided spirits with multiple cards get a choice (returned in spoils_pending).
    Non-guided factions and single-card draws are auto-resolved and stored in
    auto_spoils_choices for later batch resolution.

    Returns (spoils_pending, auto_spoils_choices) where:
    - spoils_pending: spirit_id -> list of pending choice dicts
    - auto_spoils_choices: list of {winner, loser, agenda_type, battleground}
    """
    spirits = spirits or {}
    spoils_pending = {}
    auto_spoils_choices = []

    for result in war_results:
        winner = result.get("winner")
        if not winner:
            continue
        loser = result.get("loser")
        faction = factions[winner]

        if not faction.agenda_pool:
            events.append({"type": "spoils_wasted", "faction": winner})
            continue

        # Check if winner is guided by a spirit
        if faction.guiding_spirit and faction.guiding_spirit in spirits:
            spirit = spirits[faction.guiding_spirit]
            draw_count = 1 + spirit.influence
            drawn = random.sample(faction.agenda_pool, min(draw_count, len(faction.agenda_pool)))

            if len(drawn) == 1:
                # No meaningful choice — auto-resolve
                card = drawn[0]
                faction.played_agenda_this_turn.append(card)
                spoils_type = card.agenda_type
                result["spoils"] = spoils_type.value
                auto_spoils_choices.append({
                    "winner": winner,
                    "loser": loser,
                    "agenda_type": spoils_type,
                    "battleground": result.get("battleground"),
                })
                events.append({
                    "type": "spoils_drawn",
                    "faction": winner,
                    "agenda": spoils_type.value,
                })
                continue

            cards = [c.agenda_type for c in drawn]
            spoils_pending.setdefault(faction.guiding_spirit, []).append({
                "cards": cards,
                "winner": winner,
                "loser": loser,
                "battleground": result.get("battleground"),
            })
            events.append({
                "type": "spoils_choice",
                "spirit": faction.guiding_spirit,
                "faction": winner,
                "cards": [c.value for c in cards],
            })
            continue

        # Non-guided: single random draw, auto-resolve later
        card = random.choice(faction.agenda_pool)
        faction.played_agenda_this_turn.append(card)
        spoils_type = card.agenda_type
        result["spoils"] = spoils_type.value
        auto_spoils_choices.append({
            "winner": winner,
            "loser": loser,
            "agenda_type": spoils_type,
            "battleground": result.get("battleground"),
        })
        events.append({
            "type": "spoils_drawn",
            "faction": winner,
            "agenda": spoils_type.value,
        })

    return spoils_pending, auto_spoils_choices


def finalize_all_spoils(factions, hex_map, wars, events,
                        all_spoils: list[dict],
                        normal_trade_factions: list[str]):
    """Resolve all collected spoils agendas simultaneously.

    all_spoils: list of {winner, loser, agenda_type, battleground} dicts.
    Resolves in standard agenda order (Trade -> Steal -> Expand -> Change).
    Spoils Expand uses contested-hex logic: if two factions target the same
    hex, neither gets it.

    A faction can appear multiple times (winning multiple wars). Each instance
    is tracked via faction_counts so resolvers apply effects the correct
    number of times.
    """
    from collections import Counter

    # Count instances per (faction, agenda_type)
    instance_counts = Counter()
    for entry in all_spoils:
        instance_counts[(entry["winner"], entry["agenda_type"])] += 1

    spoils_conquests = {}  # faction_id -> list of hex coords

    # Build conquest targets — detect contests
    expand_targets = {}  # hex_coord -> list of faction_ids wanting it
    for entry in all_spoils:
        winner = entry["winner"]
        loser = entry["loser"]
        agenda_type = entry["agenda_type"]
        battleground = entry.get("battleground")

        if agenda_type == AgendaType.EXPAND and battleground:
            loser_hex = None
            for h in battleground:
                coord = (h["q"], h["r"])
                if hex_map.ownership.get(coord) == loser:
                    loser_hex = coord
                    break
            if loser_hex:
                claimants = expand_targets.setdefault(loser_hex, [])
                if winner not in claimants:
                    claimants.append(winner)

    # Resolve contested spoils expand
    contested_expand_counts = Counter()  # faction_id -> number of contested expands
    for hex_coord, claimants in expand_targets.items():
        if len(claimants) == 1:
            spoils_conquests.setdefault(claimants[0], []).append(hex_coord)
        else:
            # Contested: neither gets the hex, both get expand_failed bonus
            for fid in claimants:
                contested_expand_counts[fid] += 1
                faction = factions[fid]
                expand_discount = faction.change_modifiers.get(
                    ChangeModifierTarget.EXPAND, 0)
                expand_fail_bonus = 1 + expand_discount
                faction.add_gold(expand_fail_bonus)
                events.append({
                    "type": "expand_failed",
                    "faction": fid,
                    "gold_gained": expand_fail_bonus,
                    "is_spoils": True,
                    "contested": True,
                })

    # Reduce expand instance counts by contested ones
    for fid, contested in contested_expand_counts.items():
        instance_counts[(fid, AgendaType.EXPAND)] -= contested
        if instance_counts[(fid, AgendaType.EXPAND)] <= 0:
            del instance_counts[(fid, AgendaType.EXPAND)]

    # Resolve each agenda type separately (since a faction can have multiple different
    # types, we can't use a single dict mapping faction -> type)
    for agenda_type in AGENDA_RESOLUTION_ORDER:
        type_factions = [fid for (fid, at), count in instance_counts.items()
                         if at == agenda_type and count > 0]
        if not type_factions:
            continue

        type_choices = {fid: agenda_type for fid in type_factions}
        type_counts = {(fid, agenda_type): instance_counts[(fid, agenda_type)]
                       for fid in type_factions}

        resolve_agendas(factions, hex_map, type_choices, wars, events,
                       is_spoils=True, spoils_conquests=spoils_conquests,
                       normal_trade_factions=normal_trade_factions,
                       faction_counts=type_counts)

    # Cancel wars whose battleground was conquered
    for hex_list in spoils_conquests.values():
        for conquered_hex in hex_list:
            _cancel_wars_on_hex(wars, conquered_hex, events, factions)
