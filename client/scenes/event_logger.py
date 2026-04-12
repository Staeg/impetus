"""Event logging: transforms game events into human-readable log strings."""

from shared.constants import (
    BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPRAWL_IDOL_VP,
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
        event_log.append(f"The {fname} faction plays {event['agenda']}")
        faction_agendas[event["faction"]] = event["agenda"]

    elif etype == "agenda_random":
        fname = faction_full_name(event["faction"])
        event_log.append(f"The {fname} faction randomly plays {event['agenda']}")
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
        event_log.append(f"The {fname} faction draws Change: {', '.join(cards)}")

    elif etype == "war_declared":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        event_log.append(f"War declared between {fa} and {fb}!")

    elif etype == "war_staged":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        event_log.append(f"War staged between {fa} and {fb}.")

    elif etype == "war_resolved":
        winner = event.get("winner")
        if winner:
            wname = faction_full_name(winner)
            loser = event.get("loser", "?")
            lname = faction_full_name(loser)
            if event.get("forced"):
                guided = faction_full_name(event.get("guided_faction", winner))
                event_log.append(f"{wname} defeated {lname}! (guided spirit's choice)")
            else:
                event_log.append(
                    f"{wname} defeated {lname}! "
                    f"(Roll: {event.get('roll_a','?')}+{event.get('power_a','?')} vs "
                    f"{event.get('roll_b','?')}+{event.get('power_b','?')})")
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
        cost = event.get("cost", 0)
        if cost:
            event_log.append(f"Spoils: {fname} conquered enemy territory for {cost} gold")
        else:
            event_log.append(f"Spoils: {fname} conquered enemy territory")

    elif etype == "vp_scored":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        faction_name = faction_full_name(event.get("faction", "?"))
        event_log.append(f"{name} scored {event.get('vp_gained', 0)} VP from {faction_name} (total: {event.get('total_vp', 0)})")
        adaptation_multipliers = event.get("adaptation_multipliers", [])
        era_multipliers = event.get("era_multipliers", [])

        def _multiplier_suffix(scope: str) -> str:
            parts = []
            for item in adaptation_multipliers:
                if item.get("scope") == scope:
                    parts.append(f"{item.get('label', 'Adaptation')} {item.get('multiplier', 1.0):g}x")
            for item in era_multipliers:
                if item.get("scope") == scope:
                    parts.append(f"{item.get('label', 'Era')} {item.get('multiplier', 1.0):g}x")
            return f" ({', '.join(parts)})" if parts else ""

        b_idols = event.get("battle_idols", 0)
        b_wars = event.get("wars_won", 0)
        if b_idols and b_wars:
            b_vp = b_idols * BATTLE_IDOL_VP * b_wars
            event_log.append(f"  Battle: {b_idols} idol x {b_wars} wars = {b_vp:.1f}{_multiplier_suffix('battle')}")
        a_idols = event.get("affluence_idols", 0)
        a_gold = event.get("gold_gained", 0)
        if a_idols and a_gold:
            a_vp = a_idols * AFFLUENCE_IDOL_VP * a_gold
            event_log.append(f"  Affluence: {a_idols} idol x {a_gold} gold = {a_vp:.1f}{_multiplier_suffix('affluence')}")
        s_idols = event.get("sprawl_idols", event.get("spread_idols", 0))
        s_terr = event.get("territories_gained", 0)
        if s_idols and s_terr:
            s_vp = s_idols * SPRAWL_IDOL_VP * s_terr
            event_log.append(f"  Sprawl: {s_idols} idol x {s_terr} terr = {s_vp:.1f}{_multiplier_suffix('sprawl')}")

    elif etype == "era_transition":
        if event.get("vp_reset"):
            event_log.append(
                f"Era 2 begins. VP totals reset to 0. New VP target: {event.get('new_vp_target', '?')}"
            )
        else:
            event_log.append(
                f"Era 2 begins. New VP target: {event.get('new_vp_target', '?')}"
            )

    elif etype == "era_vp_reset":
        event_log.append(
            f"VP totals reset for Era start. Target: {event.get('new_vp_target', '?')}"
        )

    elif etype == "restrained":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} restrained {event.get('agenda', '?')}.")

    elif etype == "shaping_chosen":
        fname = faction_full_name(event["faction"])
        event_log.append(f"{fname} was shaped by {event.get('card', '?')}.")

    elif etype == "adaptation_chosen":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        event_log.append(f"{name} adapted with {event.get('card', '?')}.")

    elif etype == "havoc":
        fname = faction_full_name(event["faction"])
        event_log.append(
            f"{fname} caused Havoc: {event.get('old_type', '?')} became {event.get('new_type', '?')}."
        )

    elif etype == "regard_shift":
        fname = faction_full_name(event["faction"])
        other = faction_full_name(event["other_faction"])
        event_log.append(f"{fname} regained {event.get('delta', 0)} Regard with {other}.")

    elif etype == "ejected":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"{name} ejected from {fname}")

    elif etype == "worship_gained":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"The {fname} faction now worships {name}")

    elif etype == "worship_replaced":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        old_name = spirits.get(event.get("old_spirit", ""), {}).get("name", event.get("old_spirit", "?")[:6])
        fname = faction_full_name(event["faction"])
        event_log.append(f"The {fname} faction now worships {name} (was {old_name})")

    elif etype == "faction_respawning":
        fname = faction_full_name(event["faction"])
        gold_lost = event.get("gold_lost", 0)
        event_log.append(f"{fname} lost all territory! Lost {gold_lost} gold — choosing where to reappear.")

    elif etype == "faction_respawned":
        fname = faction_full_name(event["faction"])
        h = event.get("hex")
        if h:
            event_log.append(f"{fname} reappeared at ({h['q']}, {h['r']}).")
        else:
            event_log.append(f"{fname} reappeared.")

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
