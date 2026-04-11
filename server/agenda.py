"""Agenda card system and resolution logic."""

import random
from shared.constants import AgendaType, AGENDA_RESOLUTION_ORDER, ChangeModifierTarget, CHANGE_DECK, Era, IdolType
from server.war import War


def _territory_power(factions, hex_map, faction_id: str) -> int:
    return len(hex_map.get_faction_territories(faction_id))


def _has_shape(factions, faction_id: str, card_name: str) -> bool:
    return card_name in factions[faction_id].shaping_effects


def _apply_havoc(factions, hex_map, faction_id: str, events: list[dict], is_spoils: bool) -> None:
    faction_territories = hex_map.get_faction_territories(faction_id)
    faction_idols = [
        idol for idol in hex_map.idols
        if idol.position.to_tuple() in faction_territories
    ]
    if not faction_idols:
        return
    idol = random.choice(faction_idols)
    old_type = idol.type
    new_type = random.choice([itype for itype in (IdolType.BATTLE, IdolType.AFFLUENCE, IdolType.SPRAWL) if itype != old_type])
    idol.type = new_type
    events.append({
        "type": "havoc",
        "faction": faction_id,
        "position": idol.position.to_dict(),
        "old_type": old_type.value,
        "new_type": new_type.value,
        "is_spoils": is_spoils,
    })


def resolve_agendas(factions: dict, hex_map, agenda_choices: dict[str, AgendaType],
                    wars: list, events: list, is_spoils: bool = False,
                    spoils_conquests: dict = None,
                    normal_trade_factions: list[str] = None,
                    faction_counts: dict[str, int] = None,
                    guided_expand_choices: dict[str, tuple] = None,
                    normal_expand_factions: list[str] = None,
                    era: Era = Era.ERA_1,
                    current_turn: int = 0):
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
        guided_expand_choices: dict of faction_id -> (q, r) for guided spirit expand hex choices (non-spoils only)
        normal_expand_factions: factions that played Expand normally this turn (for spoils trade expand bonus)
    """
    faction_counts = faction_counts or {}
    # Expand factions for the Trade bonus: either from current choices or from
    # the passed normal_expand_factions list (for spoils batches)
    expand_factions_this_batch = [fid for fid, choice in agenda_choices.items()
                                  if choice == AgendaType.EXPAND]
    # For spoils batches, also include factions that expanded normally this turn
    all_expand_factions = expand_factions_this_batch + (normal_expand_factions or [])

    for agenda_type in AGENDA_RESOLUTION_ORDER:
        playing_factions = [fid for fid, choice in agenda_choices.items()
                           if choice == agenda_type]
        if not playing_factions:
            continue

        # Build per-agenda-type counts for this batch, including permanent Shape effects.
        type_counts = {}
        for fid in playing_factions:
            count = faction_counts.get((fid, agenda_type), 1)
            if agenda_type == AgendaType.STEAL and _has_shape(factions, fid, "Amplified Steal"):
                count += 1
            elif agenda_type == AgendaType.CHANGE and _has_shape(factions, fid, "Amplified Change"):
                count += 1
            elif agenda_type == AgendaType.TRADE and _has_shape(factions, fid, "Amplified Trade"):
                count += 1
            elif agenda_type == AgendaType.EXPAND and _has_shape(factions, fid, "Amplified Expand"):
                count += 1
            type_counts[fid] = count

        if agenda_type == AgendaType.STEAL:
            _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils, type_counts, era=era, current_turn=current_turn)
        elif agenda_type == AgendaType.TRADE:
            _resolve_trade(factions, hex_map, playing_factions, events, is_spoils,
                          normal_trade_factions or [], type_counts,
                          expand_factions=all_expand_factions)
        elif agenda_type == AgendaType.EXPAND:
            _resolve_expand(factions, hex_map, playing_factions, events, is_spoils,
                           spoils_conquests, type_counts, guided_expand_choices)
        elif agenda_type == AgendaType.CHANGE:
            _resolve_change(factions, hex_map, playing_factions, events, is_spoils, type_counts)


def _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils, faction_counts=None,
                   era: Era = Era.ERA_1, current_turn: int = 0):
    """Steal: -1 regard and -1 gold to all neighbors. +1 gold per gold lost by neighbors.
    Then wars erupt with neighbors at -2 regard or less (skipped when is_spoils=True)."""
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
        is_global = _has_shape(factions, fid, "Globalization")
        neighbors = [other for other in factions if other != fid] if is_global else hex_map.get_live_neighbor_ids(fid, factions)

        for other_fid in neighbors:
            other_faction = factions[other_fid]
            weaker_other = _territory_power(factions, hex_map, other_fid) < _territory_power(factions, hex_map, fid)
            if _has_shape(factions, fid, "Fair Weather Friends") and weaker_other:
                adjusted_penalty = regard_penalty * 2
            else:
                adjusted_penalty = regard_penalty
            # Mark regard change (negate: regard_penalty is positive magnitude)
            regard_changes.append((fid, other_fid, -adjusted_penalty))
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

    # Check for war declarations (spoils Steal does not start new wars)
    if not is_spoils:
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
                        war = War(
                            fid,
                            other_fid,
                            declared_turn=current_turn,
                            resolve_turn=current_turn if era == Era.ERA_1 else current_turn + 1,
                        )
                        wars.append(war)
                        events.append({
                            "type": "war_declared",
                            "faction_a": fid,
                            "faction_b": other_fid,
                        })


def _resolve_trade(factions, hex_map, playing_factions, events, is_spoils,
                   normal_trade_factions: list[str] = None, faction_counts=None,
                   expand_factions: list[str] = None):
    """Trade: +1 gold, +1 gold for every other faction playing Trade this turn,
    +1 gold for every faction playing Expand this turn.
    Also +1 regard with each other faction playing Trade this turn (bilateral).
    Regard bonus only applies to co-traders, not Expand factions.

    For spoils trade, normal_trade_factions counts as additional "others trading"
    for the spoils trader's bonus, and each normal trader gets +1 gold and regard.
    Spoils trade also benefits from normal Expand factions (normal_expand_factions).

    When faction_counts has count > 1 for a faction, gold is multiplied by count
    and regard is applied count times. Self-instances don't count as co-traders.
    """
    normal_trade_factions = normal_trade_factions or []
    faction_counts = faction_counts or {}
    expand_factions = expand_factions or []

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
        # +1 gold per Expand faction this turn (no regard bonus)
        expand_bonus = len(expand_factions)
        extra_expand_partners = []
        if _has_shape(factions, fid, "Unilateral Agreement"):
            extra_expand_partners = [
                other for other in expand_factions
                if other != fid and other not in playing_factions and other not in normal_trade_factions
            ]
            expand_bonus += len(extra_expand_partners)
        total = (base + others_trading + trade_bonus * others_trading + expand_bonus) * count
        faction.add_gold(total)

        # Regard: co-traders always count; Unilateral Agreement also treats other
        # Expanders as co-traders for this faction's bonus.
        co_traders = [other for other in playing_factions if other != fid]
        if is_spoils:
            co_traders = co_traders + normal_trade_factions
        for other in extra_expand_partners:
            if other not in co_traders:
                co_traders.append(other)
        applied_regard = 0
        for other_fid in co_traders:
            if _has_shape(factions, fid, "Hellbound") or _has_shape(factions, other_fid, "Hellbound"):
                continue
            regard_gain = 1 + trade_bonus
            if (_has_shape(factions, fid, "Fair Weather Friends")
                    and _territory_power(factions, hex_map, other_fid) > _territory_power(factions, hex_map, fid)):
                regard_gain *= 2
            faction.modify_regard(other_fid, regard_gain * count)
            factions[other_fid].modify_regard(fid, regard_gain * count)
            applied_regard = max(applied_regard, regard_gain)

        events.append({
            "type": "trade",
            "faction": fid,
            "gold_gained": total,
            "is_spoils": is_spoils,
            "regard_gain": applied_regard if co_traders else 0,
            "co_traders": co_traders,
            "expand_bonus": expand_bonus,
        })

    # Spoils trade gives +1 gold (+ Trade modifier) and regard to every faction that traded normally
    if is_spoils and normal_trade_factions:
        for fid in normal_trade_factions:
            trade_bonus = factions[fid].change_modifiers.get(ChangeModifierTarget.TRADE, 0)
            # +1 base + expand bonus for normal traders too (no regard for expand)
            expand_bonus = len(expand_factions)
            bonus = 1 + trade_bonus + expand_bonus
            factions[fid].add_gold(bonus)
            # Regard with each spoils trader
            regard_gain = 1 + trade_bonus
            spoils_traders = list(playing_factions)
            for spoils_fid in spoils_traders:
                if _has_shape(factions, fid, "Hellbound") or _has_shape(factions, spoils_fid, "Hellbound"):
                    continue
                if (_has_shape(factions, fid, "Fair Weather Friends")
                        and _territory_power(factions, hex_map, spoils_fid) > _territory_power(factions, hex_map, fid)):
                    pair_gain = regard_gain * 2
                else:
                    pair_gain = regard_gain
                factions[fid].modify_regard(spoils_fid, pair_gain)
                factions[spoils_fid].modify_regard(fid, pair_gain)
            events.append({
                "type": "trade_spoils_bonus",
                "faction": fid,
                "gold_gained": bonus,
                "regard_gain": regard_gain if spoils_traders else 0,
                "co_traders": spoils_traders,
                "expand_bonus": expand_bonus,
            })


def _resolve_expand(factions, hex_map, playing_factions, events, is_spoils,
                    spoils_conquests: dict = None, faction_counts=None,
                    guided_expand_choices: dict = None):
    """Expand: spend gold equal to territory count to claim a neutral hex.
    If can't afford or no hexes available, +1 gold instead.

    For normal Expand: guided spirits have pre-chosen their target hex via
    guided_expand_choices (faction_id -> (q, r)). Non-guided factions
    prioritize reachable hexes with the highest total Idol count, then break
    ties randomly. All targets are collected first, then contest detection
    runs: if two or more factions target the same hex, all fail.

    For spoils: claim a territory from the loser instead of paying gold.
    spoils_conquests maps faction_id -> list of hex coords to claim.
    """
    faction_counts = faction_counts or {}
    guided_expand_choices = guided_expand_choices or {}

    if is_spoils:
        # Spoils path: costs gold same as normal Expand (territory count - modifier).
        for fid in playing_factions:
            faction = factions[fid]
            expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
            expand_fail_bonus = 1 + expand_discount
            territory_count = len(hex_map.get_faction_territories(fid))
            cost = max(0, territory_count - expand_discount)

            if spoils_conquests and fid in spoils_conquests:
                targets = spoils_conquests[fid]
                if not isinstance(targets, list):
                    targets = [targets]
                for target in targets:
                    if faction.gold >= cost:
                        faction.gold -= cost
                        hex_map.claim_hex(target, fid)
                        faction.territories_gained_this_turn += 1
                        events.append({
                            "type": "expand_spoils",
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
                            "is_spoils": True,
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
                    "is_spoils": True,
                })
        return

    # Normal expand: collect all targets simultaneously, then detect contests.
    expand_info = {}  # faction_id -> (target, expand_fail_bonus, cost)
    for fid in playing_factions:
        faction = factions[fid]
        expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
        expand_fail_bonus = 1 + expand_discount
        territory_count = len(hex_map.get_faction_territories(fid))
        cost = max(0, territory_count - expand_discount)

        if fid in guided_expand_choices:
            target = guided_expand_choices[fid]
        else:
            allow_enemy = _has_shape(factions, fid, "Special Military Operations")
            available_targets = list(hex_map.get_expand_targets(fid, allow_enemy=allow_enemy))
            if available_targets:
                idol_counts = {
                    h: len(hex_map.get_idols_at_hex(h[0], h[1]))
                    for h in available_targets
                }
                max_idols = max(idol_counts.values())
                best_targets = [h for h, count in idol_counts.items() if count == max_idols]
                target = random.choice(best_targets)
            else:
                target = None

        expand_info[fid] = (target, expand_fail_bonus, cost)

    # Contest detection: if two or more factions target the same hex, all fail.
    hex_claims: dict[tuple, list[str]] = {}
    for fid, (target, _, cost) in expand_info.items():
        if target is not None and factions[fid].gold >= cost:
            hex_claims.setdefault(target, []).append(fid)
    contested_fids = {
        fid
        for claimants in hex_claims.values()
        if len(claimants) > 1
        for fid in claimants
    }

    # Apply results
    for fid in playing_factions:
        faction = factions[fid]
        target, expand_fail_bonus, cost = expand_info[fid]

        if target is not None and faction.gold >= cost and fid not in contested_fids:
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
            evt = {
                "type": "expand_failed",
                "faction": fid,
                "gold_gained": expand_fail_bonus,
            }
            if fid in contested_fids:
                evt["contested"] = True
            events.append(evt)


def _resolve_change(factions, hex_map, playing_factions, events, is_spoils=False, faction_counts=None):
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
            if _has_shape(factions, fid, "Havoc"):
                _apply_havoc(factions, hex_map, fid, events, is_spoils)


def _pick_enemy_territory(hex_map, winner: str, loser: str):
    """Pick a random adjacent enemy territory, preferring hexes with more idols.

    Only considers loser territories that border at least one winner territory.
    """
    territories = hex_map.get_adjacent_enemy_territories(winner, loser)
    if not territories:
        return None
    idol_counts = {hx: 0 for hx in territories}
    for idol in hex_map.idols:
        pos = (idol.position.q, idol.position.r)
        if pos in idol_counts:
            idol_counts[pos] += 1
    max_count = max(idol_counts.values())
    best = [h for h, cnt in idol_counts.items() if cnt == max_count]
    return random.choice(best)


def resolve_spoils(factions, hex_map, war_results, wars, events,
                   normal_trade_factions: list[str], spirits: dict = None):
    """Collect spoils draws for all war winners.

    Guided spirits with multiple cards get a choice (returned in spoils_pending).
    Non-guided factions and single-card draws are auto-resolved and stored in
    auto_spoils_choices for later batch resolution.

    For Expand spoils:
    - Guided winner: spirit must choose a target hex via spoils_expand_choice;
      the entry is placed in spoils_pending with no target_hex yet.
    - Non-guided winner: target hex is auto-picked (most idols) and stored
      immediately in target_hex.

    Returns (spoils_pending, auto_spoils_choices) where:
    - spoils_pending: spirit_id -> list of pending choice dicts
    - auto_spoils_choices: list of {winner, loser, agenda_type, target_hex}
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
            drawn = sorted(
                random.sample(faction.agenda_pool, min(draw_count, len(faction.agenda_pool))),
                key=lambda c: AGENDA_RESOLUTION_ORDER.index(c.agenda_type)
                              if c.agenda_type in AGENDA_RESOLUTION_ORDER else 99,
            )

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
                    "target_hex": None,
                    "guided": True,
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
            "target_hex": None,
            "guided": False,
        })
        events.append({
            "type": "spoils_drawn",
            "faction": winner,
            "agenda": spoils_type.value,
        })

    return spoils_pending, auto_spoils_choices


def finalize_all_spoils(factions, hex_map, wars, events,
                        all_spoils: list[dict],
                        normal_trade_factions: list[str],
                        normal_expand_factions: list[str] = None,
                        era: Era = Era.ERA_1,
                        current_turn: int = 0):
    """Resolve all collected spoils agendas.

    all_spoils: list of {winner, loser, agenda_type, target_hex, guided} dicts.

    Expand is handled in two phases:
      Phase 1 — Guided (simultaneous): contest detection among affordable guided
        entries; contested pairs both fail. Entries with target_hex=None get
        adjacent territory auto-picked here.
      Phase 2 — Non-guided (sequential, random order): each greedily picks the
        best remaining adjacent loser territory, paying the normal Expand cost.

    Spoils Expand costs gold equal to territory count (minus modifiers), exactly
    like a normal Expand. If a faction cannot afford it or no target is available,
    they receive the expand_failed gold bonus instead.

    All other agenda types (Steal, Trade, Change) resolve via resolve_agendas
    in standard order.
    """
    from collections import Counter
    normal_expand_factions = normal_expand_factions or []

    # Separate Expand entries from the rest
    expand_entries = [e for e in all_spoils if e["agenda_type"] == AgendaType.EXPAND]
    non_expand_entries = [e for e in all_spoils if e["agenda_type"] != AgendaType.EXPAND]

    guided_expand = [e for e in expand_entries if e.get("guided", True)]
    non_guided_expand = [e for e in expand_entries if not e.get("guided", True)]

    # Phase 1: Guided Expand — simultaneous with contest detection
    # Assign targets to guided entries that don't have one yet
    for entry in guided_expand:
        if entry.get("target_hex") is None:
            entry["target_hex"] = _pick_enemy_territory(hex_map, entry["winner"], entry["loser"])

    # Snapshot territory counts per unique winner before any expand resolves.
    # Multiple entries for the same winner all use the pre-resolution count.
    winner_territory_snapshot: dict[str, int] = {}
    for entry in guided_expand:
        winner = entry["winner"]
        if winner not in winner_territory_snapshot:
            winner_territory_snapshot[winner] = len(hex_map.get_faction_territories(winner))

    # Compute per-entry cost info (parallel list, handles same-winner multiples)
    guided_expand_costs = []  # list of (target, cost, expand_fail_bonus) parallel to guided_expand
    for entry in guided_expand:
        winner = entry["winner"]
        faction = factions[winner]
        expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
        expand_fail_bonus = 1 + expand_discount
        territory_count = winner_territory_snapshot[winner]
        cost = max(0, territory_count - expand_discount)
        guided_expand_costs.append((entry.get("target_hex"), cost, expand_fail_bonus))

    # Track remaining gold per winner across simultaneous entries
    # (each entry deducts from the same faction's gold)
    winner_gold_available: dict[str, int] = {
        entry["winner"]: factions[entry["winner"]].gold for entry in guided_expand
    }

    # Detect contests among affordable guided entries with valid targets
    hex_claimants: dict[tuple, list[str]] = {}
    for entry, (target, cost, _) in zip(guided_expand, guided_expand_costs):
        winner = entry["winner"]
        if target is not None and winner_gold_available.get(winner, 0) >= cost:
            hex_claimants.setdefault(target, []).append(winner)
    contested_pairs: set[tuple[str, tuple]] = {
        (fid, hx)
        for hx, claimants in hex_claimants.items()
        if len(claimants) > 1
        for fid in claimants
    }

    for entry, (target, cost, expand_fail_bonus) in zip(guided_expand, guided_expand_costs):
        winner = entry["winner"]
        faction = factions[winner]
        affordable = winner_gold_available.get(winner, 0) >= cost
        if target is None or not affordable:
            faction.add_gold(expand_fail_bonus)
            events.append({
                "type": "expand_failed",
                "faction": winner,
                "gold_gained": expand_fail_bonus,
                "is_spoils": True,
            })
        elif (winner, target) in contested_pairs:
            faction.add_gold(expand_fail_bonus)
            events.append({
                "type": "expand_failed",
                "faction": winner,
                "gold_gained": expand_fail_bonus,
                "is_spoils": True,
                "contested": True,
            })
        else:
            faction.gold -= cost
            winner_gold_available[winner] = winner_gold_available.get(winner, 0) - cost
            hex_map.claim_hex(target, winner)
            faction.territories_gained_this_turn += 1
            events.append({
                "type": "expand_spoils",
                "faction": winner,
                "hex": {"q": target[0], "r": target[1]},
                "cost": cost,
            })

    # Phase 2: Non-guided Expand — sequential in random order
    random.shuffle(non_guided_expand)
    for entry in non_guided_expand:
        winner = entry["winner"]
        loser = entry["loser"]
        faction = factions[winner]
        expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND, 0)
        expand_fail_bonus = 1 + expand_discount
        territory_count = len(hex_map.get_faction_territories(winner))
        cost = max(0, territory_count - expand_discount)
        # Pick best adjacent loser territory still owned by loser
        target = _pick_enemy_territory(hex_map, winner, loser)
        if target is not None and faction.gold >= cost:
            faction.gold -= cost
            hex_map.claim_hex(target, winner)
            faction.territories_gained_this_turn += 1
            events.append({
                "type": "expand_spoils",
                "faction": winner,
                "hex": {"q": target[0], "r": target[1]},
                "cost": cost,
            })
        else:
            faction.add_gold(expand_fail_bonus)
            events.append({
                "type": "expand_failed",
                "faction": winner,
                "gold_gained": expand_fail_bonus,
                "is_spoils": True,
            })

    # Non-Expand: resolve in standard agenda order via resolve_agendas
    instance_counts = Counter()
    for entry in non_expand_entries:
        instance_counts[(entry["winner"], entry["agenda_type"])] += 1

    for agenda_type in AGENDA_RESOLUTION_ORDER:
        if agenda_type == AgendaType.EXPAND:
            continue  # already handled above
        type_factions = [fid for (fid, at), count in instance_counts.items()
                         if at == agenda_type and count > 0]
        if not type_factions:
            continue

        type_choices = {fid: agenda_type for fid in type_factions}
        type_counts = {(fid, agenda_type): instance_counts[(fid, agenda_type)]
                       for fid in type_factions}

        resolve_agendas(factions, hex_map, type_choices, wars, events,
                       is_spoils=True,
                       normal_trade_factions=normal_trade_factions,
                       faction_counts=type_counts,
                       normal_expand_factions=normal_expand_factions,
                       era=era,
                       current_turn=current_turn)
