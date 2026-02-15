"""Agenda card system and resolution logic."""

import random
from shared.constants import AgendaType, AGENDA_RESOLUTION_ORDER, ChangeModifierTarget, CHANGE_DECK
from server.war import War


def resolve_agendas(factions: dict, hex_map, agenda_choices: dict[str, AgendaType],
                    wars: list, events: list, is_spoils: bool = False,
                    spoils_conquests: dict = None,
                    normal_trade_factions: list[str] = None):
    """Resolve all agenda choices in the correct order.

    Args:
        factions: dict of faction_id -> Faction
        hex_map: HexMap instance
        agenda_choices: dict of faction_id -> AgendaType chosen
        wars: list of active War objects (will be mutated to add new wars)
        events: list to append event dicts to
        is_spoils: if True, these are Spoils of War agendas
        spoils_conquests: dict of faction_id -> hex coord for spoils expand targets
        normal_trade_factions: factions that traded normally this turn (for spoils trade)
    """
    for agenda_type in AGENDA_RESOLUTION_ORDER:
        playing_factions = [fid for fid, choice in agenda_choices.items()
                           if choice == agenda_type]
        if not playing_factions:
            continue

        if agenda_type == AgendaType.STEAL:
            _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils)
        elif agenda_type == AgendaType.BOND:
            _resolve_bond(factions, hex_map, playing_factions, events, is_spoils)
        elif agenda_type == AgendaType.TRADE:
            _resolve_trade(factions, playing_factions, events, is_spoils,
                          normal_trade_factions or [])
        elif agenda_type == AgendaType.EXPAND:
            _resolve_expand(factions, hex_map, playing_factions, events, is_spoils, spoils_conquests)
        elif agenda_type == AgendaType.CHANGE:
            _resolve_change(factions, playing_factions, events, is_spoils)


def _resolve_steal(factions, hex_map, playing_factions, wars, events, is_spoils):
    """Steal: -1 regard and -1 gold to all neighbors. +1 gold per gold lost by neighbors.
    Then wars erupt with neighbors at -2 regard or less."""
    # Calculate gold losses simultaneously
    gold_losses = {}  # faction_id -> gold actually lost
    gold_gains = {}   # stealing faction -> gold gained
    regard_changes = []

    neighbor_map = {}  # stealing faction -> list of neighbor faction IDs
    regard_penalty_map = {}  # stealing faction -> regard_penalty value

    for fid in playing_factions:
        faction = factions[fid]
        steal_bonus = faction.change_modifiers.get(ChangeModifierTarget.STEAL.value, 0)
        gold_stolen_per_neighbor = 1 + steal_bonus
        regard_penalty = 1 + steal_bonus
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

    for (stealer, victim), loss in gold_losses.items():
        pass  # losses already calculated from original gold

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


def _resolve_bond(factions, hex_map, playing_factions, events, is_spoils=False):
    """Bond: +1 regard with all neighbors."""
    for fid in playing_factions:
        faction = factions[fid]
        bond_bonus = faction.change_modifiers.get(ChangeModifierTarget.BOND.value, 0)
        regard_gain = 1 + bond_bonus
        neighbors = hex_map.get_live_neighbor_ids(fid, factions)

        for other_fid in neighbors:
            faction.modify_regard(other_fid, regard_gain)
            factions[other_fid].modify_regard(fid, regard_gain)

        events.append({
            "type": "bond",
            "faction": fid,
            "regard_gain": regard_gain,
            "neighbors": neighbors,
            "is_spoils": is_spoils,
        })


def _resolve_trade(factions, playing_factions, events, is_spoils,
                   normal_trade_factions: list[str] = None):
    """Trade: +1 gold, +1 gold for every other faction playing Trade this turn.

    For spoils trade, normal_trade_factions counts as additional "others trading"
    for the spoils trader's bonus, and each normal trader gets +1 gold.
    """
    normal_trade_factions = normal_trade_factions or []

    for fid in playing_factions:
        faction = factions[fid]
        trade_bonus = faction.change_modifiers.get(ChangeModifierTarget.TRADE.value, 0)
        base = 1
        others_trading = len(playing_factions) - 1
        # Spoils traders also benefit from factions that traded normally this turn
        if is_spoils:
            others_trading += len(normal_trade_factions)
        total = base + others_trading + trade_bonus * others_trading
        faction.add_gold(total)
        events.append({
            "type": "trade",
            "faction": fid,
            "gold_gained": total,
            "is_spoils": is_spoils,
        })

    # Spoils trade gives +1 gold (+ Trade modifier) to every faction that traded normally
    if is_spoils and normal_trade_factions:
        for fid in normal_trade_factions:
            bonus = 1 + factions[fid].change_modifiers.get(ChangeModifierTarget.TRADE.value, 0)
            factions[fid].add_gold(bonus)
            events.append({
                "type": "trade_spoils_bonus",
                "faction": fid,
                "gold_gained": bonus,
            })


def _resolve_expand(factions, hex_map, playing_factions, events, is_spoils,
                    spoils_conquests: dict = None):
    """Expand: spend gold equal to territory count to claim a random neutral hex.
    If can't afford or no hexes available, +1 gold instead.

    For spoils: take the loser's battleground hex instead of paying gold.
    spoils_conquests is used for spoils expand to specify which hex to take.
    """
    for fid in playing_factions:
        faction = factions[fid]
        expand_discount = faction.change_modifiers.get(ChangeModifierTarget.EXPAND.value, 0)
        expand_fail_bonus = 1 + expand_discount
        territory_count = len(hex_map.get_faction_territories(fid))
        cost = max(0, territory_count - expand_discount)

        if is_spoils and spoils_conquests and fid in spoils_conquests:
            # Spoils expand: take the target hex
            target = spoils_conquests[fid]
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


def _resolve_change(factions, playing_factions, events, is_spoils=False):
    """Change: draw from the change modifier deck, apply permanent modifier."""
    for fid in playing_factions:
        faction = factions[fid]
        # Draw a random change card
        card = random.choice(CHANGE_DECK)
        faction.add_change_modifier(card.value)
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


def draw_spoils_agenda() -> AgendaType:
    """Draw a random agenda card for spoils of war."""
    return random.choice(list(AgendaType))


def resolve_spoils(factions, hex_map, war_results, wars, events,
                   normal_trade_factions: list[str], spirits: dict = None):
    """Resolve spoils of war agendas for war winners.

    If the winning faction is guided by a spirit, draw multiple spoils
    cards (1 + influence) and let the spirit choose.  Returns spoils_pending
    dict (spirit_id -> list of AgendaType) for any choices that need player
    input; empty dict means all spoils were auto-resolved.
    """
    spirits = spirits or {}
    spoils_choices = {}
    spoils_conquests = {}
    spoils_pending = {}  # spirit_id -> {"cards": [...], "winner": fid, "loser": fid, "battleground": ...}

    for result in war_results:
        winner = result.get("winner")
        if not winner:
            continue
        loser = result.get("loser")
        faction = factions[winner]

        # Check if winner is guided by a spirit with influence
        if faction.guiding_spirit and faction.guiding_spirit in spirits:
            spirit = spirits[faction.guiding_spirit]
            draw_count = 1 + spirit.influence
            if not faction.agenda_deck:
                # No cards to draw — spoils wasted
                events.append({
                    "type": "spoils_wasted",
                    "faction": winner,
                })
                continue
            drawn = random.sample(faction.agenda_deck, min(draw_count, len(faction.agenda_deck)))
            for c in drawn:
                faction.agenda_deck.remove(c)
            cards = [c.agenda_type for c in drawn]
            spoils_pending[faction.guiding_spirit] = {
                "cards": cards,
                "drawn_cards": drawn,
                "winner": winner,
                "loser": loser,
                "battleground": result.get("battleground"),
            }
            events.append({
                "type": "spoils_choice",
                "spirit": faction.guiding_spirit,
                "faction": winner,
                "cards": [c.value for c in cards],
            })
            continue

        # Non-guided: auto-resolve with single draw from faction deck
        if not faction.agenda_deck:
            # No cards to draw — spoils wasted
            events.append({
                "type": "spoils_wasted",
                "faction": winner,
            })
            continue
        card = random.choice(faction.agenda_deck)
        faction.agenda_deck.remove(card)
        faction.played_agenda_this_turn.append(card)
        spoils_type = card.agenda_type
        result["spoils"] = spoils_type.value

        if spoils_type == AgendaType.EXPAND and result.get("battleground"):
            bg = result["battleground"]
            loser_hex = None
            for h in bg:
                coord = (h["q"], h["r"])
                if hex_map.ownership.get(coord) == loser:
                    loser_hex = coord
                    break
            if loser_hex:
                spoils_conquests[winner] = loser_hex

        spoils_choices[winner] = spoils_type
        factions[winner].add_spoils_card(spoils_type)
        events.append({
            "type": "spoils_drawn",
            "faction": winner,
            "agenda": spoils_type.value,
        })

    # Resolve auto-resolved spoils agendas in order
    if spoils_choices:
        resolve_agendas(factions, hex_map, spoils_choices, wars, events,
                       is_spoils=True, spoils_conquests=spoils_conquests,
                       normal_trade_factions=normal_trade_factions)

    # Cancel wars whose battleground was conquered by spoils expand
    for conquered_hex in spoils_conquests.values():
        _cancel_wars_on_hex(wars, conquered_hex, events, factions)

    return spoils_pending


def resolve_spoils_choice(factions, hex_map, wars, events, spirit_id,
                          card_index, spoils_pending, spirits,
                          normal_trade_factions: list[str] = None):
    """Resolve a spirit's spoils card choice after player input."""
    pending = spoils_pending[spirit_id]
    cards = pending["cards"]
    drawn_cards = pending.get("drawn_cards", [])
    chosen = cards[card_index]
    winner = pending["winner"]
    loser = pending["loser"]
    battleground = pending.get("battleground")

    # Return unchosen cards to the deck; track chosen card for cleanup
    faction = factions[winner]
    chosen_card = drawn_cards[card_index] if drawn_cards else None
    for i, c in enumerate(drawn_cards):
        if i == card_index:
            faction.played_agenda_this_turn.append(c)
        else:
            faction.agenda_deck.append(c)

    spoils_conquests = {}
    if chosen == AgendaType.EXPAND and battleground:
        for h in battleground:
            coord = (h["q"], h["r"])
            if hex_map.ownership.get(coord) == loser:
                spoils_conquests[winner] = coord
                break

    factions[winner].add_spoils_card(chosen)
    events.append({
        "type": "spoils_drawn",
        "faction": winner,
        "agenda": chosen.value,
    })

    if chosen == AgendaType.CHANGE:
        # Spirit gets to choose a change modifier instead of random
        spirit = spirits[spirit_id]
        draw_count = 1 + spirit.influence
        change_cards = random.sample(CHANGE_DECK, min(draw_count, len(CHANGE_DECK)))
        pending["stage"] = "change_choice"
        pending["change_cards"] = change_cards
        # Don't delete from spoils_pending — still waiting for change choice
    else:
        resolve_agendas(factions, hex_map, {winner: chosen}, wars, events,
                       is_spoils=True, spoils_conquests=spoils_conquests,
                       normal_trade_factions=normal_trade_factions or [])
        # Cancel wars whose battleground was conquered by spoils expand
        for conquered_hex in spoils_conquests.values():
            _cancel_wars_on_hex(wars, conquered_hex, events, factions)
        del spoils_pending[spirit_id]
