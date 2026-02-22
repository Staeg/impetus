"""Event logging: transforms game events into human-readable log strings."""

from shared.constants import (
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPREAD_IDOL_VP,
)
from client.faction_names import faction_full_name


def log_event(event: dict, event_log: list[str], spirits: dict,
              my_spirit_id: str, faction_agendas: dict):
    """Append a human-readable log entry for the given game event.

    Pure data transformation: reads event dicts and appends strings to
    event_log.  Also updates faction_agendas as a side effect for
    agenda_chosen/agenda_random events.

    Returns the event type string for the caller to handle side effects
    (animation fadeout on turn_start, preview clearing on guided, etc.).
    """
    etype = event.get("type", "")

    if etype == "idol_placed":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        event_log.append(f"{name} placed {event['idol_type']} idol")

    elif etype == "guided":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"{name} is guiding {fname}")

    elif etype == "guide_contested":
        fname = faction_full_name(event["faction"])
        spirit_ids = event.get("spirits", [])
        names = [spirits.get(sid, {}).get("name", sid[:6]) for sid in spirit_ids]
        event_log.append(f"Contested guidance of {fname}! ({', '.join(names)})")

    elif etype == "swell":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        event_log.append(f"{name} Swelled (+{event.get('vp_gained', 10)} VP, total: {event.get('total_vp', 0)})")

    elif etype == "agenda_chosen":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} plays {event['agenda']}")
        faction_agendas[event["faction"]] = event["agenda"]

    elif etype == "agenda_random":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} randomly plays {event['agenda']}")
        faction_agendas[event["faction"]] = event["agenda"]

    elif etype == "steal":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        event_log.append(f"{prefix}{fname} stole {event.get('gold_gained', 0)} gold")

    elif etype == "trade":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        co_traders = event.get("co_traders", [])
        regard_part = ""
        if co_traders:
            regard_gain = event.get("regard_gain", 0)
            regard_part = f", +{regard_gain} regard"
        event_log.append(f"{prefix}{fname} traded for {event.get('gold_gained', 0)} gold{regard_part}")

    elif etype == "trade_spoils_bonus":
        fname = faction_full_name(event["faction"])
        co_traders = event.get("co_traders", [])
        regard_part = ""
        if co_traders:
            regard_gain = event.get("regard_gain", 0)
            regard_part = f", +{regard_gain} regard"
        event_log.append(f"{fname} gained {event.get('gold_gained', 1)} gold{regard_part} from Spoils Trade")

    elif etype == "expand":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} expanded territory")

    elif etype == "expand_failed":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} couldn't expand, gained gold")

    elif etype == "change":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        event_log.append(f"{prefix}{fname} upgraded {event.get('modifier', '?')}")

    elif etype == "change_draw":
        fname = faction_full_name(event["faction"])
        cards = event.get("cards", [])
        event_log.append(f"{fname} draws Change: {', '.join(cards)}")

    elif etype == "war_erupted":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        event_log.append(f"War erupted between {fa} and {fb}!")

    elif etype == "war_ripened":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        event_log.append(f"War between {fa} and {fb} is ripe!")

    elif etype == "war_resolved":
        winner = event.get("winner")
        if winner:
            wname = faction_full_name(winner)
            loser = event.get("loser", "?")
            lname = faction_full_name(loser)
            event_log.append(
                f"{wname} won war against {lname}! (Roll: {event.get('roll_a', '?')}+{event.get('power_a', '?')} vs "
                f"{event.get('roll_b', '?')}+{event.get('power_b', '?')})")
        else:
            event_log.append("War ended in a tie!")

    elif etype == "spoils_drawn":
        fname = faction_full_name(event["faction"])
        event_log.append(f"Spoils: {fname} drew {event.get('agenda', '?')}")

    elif etype == "spoils_choice":
        fname = faction_full_name(event["faction"])
        cards = event.get("cards", [])
        event_log.append(f"Spoils: {fname} choosing from {', '.join(cards)}")

    elif etype == "expand_spoils":
        fname = faction_full_name(event["faction"])
        event_log.append(f"Spoils: {fname} conquered enemy territory")

    elif etype == "vp_scored":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        faction_name = faction_full_name(event.get("faction", "?"))
        event_log.append(f"{name} scored {event.get('vp_gained', 0)} VP from {faction_name} (total: {event.get('total_vp', 0)})")
        b_idols = event.get("battle_idols", 0)
        b_wars = event.get("wars_won", 0)
        if b_idols and b_wars:
            b_vp = b_idols * BATTLE_IDOL_VP * b_wars
            event_log.append(f"  Battle: {b_idols} idol x {b_wars} wars = {b_vp:.1f}")
        a_idols = event.get("affluence_idols", 0)
        a_gold = event.get("gold_gained", 0)
        if a_idols and a_gold:
            a_vp = a_idols * AFFLUENCE_IDOL_VP * a_gold
            event_log.append(f"  Affluence: {a_idols} idol x {a_gold} gold = {a_vp:.1f}")
        s_idols = event.get("spread_idols", 0)
        s_terr = event.get("territories_gained", 0)
        if s_idols and s_terr:
            s_vp = s_idols * SPREAD_IDOL_VP * s_terr
            event_log.append(f"  Spread: {s_idols} idol x {s_terr} terr = {s_vp:.1f}")

    elif etype == "ejected":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"{name} ejected from {fname}")

    elif etype == "worship_gained":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} now Worships {name}")

    elif etype == "worship_replaced":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        old_name = spirits.get(event.get("old_spirit", ""), {}).get("name", event.get("old_spirit", "?")[:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} now Worships {name} (was {old_name})")

    elif etype == "faction_eliminated":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} has been ELIMINATED!")

    elif etype == "war_ended":
        fa_id = event.get("faction_a")
        fb_id = event.get("faction_b")
        if fa_id and fb_id:
            event_log.append(
                f"War between {faction_full_name(fa_id)} and {faction_full_name(fb_id)} "
                f"dissipated due to territorial changes."
            )
        elif event.get("message"):
            event_log.append(event["message"])
        else:
            event_log.append(f"War ended ({event.get('reason', 'unknown')})")

    elif etype == "setup_start":
        event_log.append("--- Setup ---")

    elif etype == "turn_start":
        event_log.append(f"--- Turn {event.get('turn', '?')} ---")

    elif etype == "game_over":
        winners = event.get("winners", [])
        names = [spirits.get(w, {}).get("name", w[:6]) for w in winners]
        event_log.append(f"GAME OVER! Winner(s): {', '.join(names)}")

    return etype
