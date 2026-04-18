"""Event logging: transforms game events into human-readable log strings."""

from shared.constants import BATTLE_IDOL_VP, AFFLUENCE_IDOL_VP, SPRAWL_IDOL_VP
from client.faction_names import faction_full_name


def _append_line(event_log: list[str], event_log_meta: list[dict], text: str,
                 factions: list[str] | None = None, spans: list[dict] | None = None) -> None:
    event_log.append(text)
    event_log_meta.append({
        "factions": [fid for fid in (factions or []) if fid],
        "spans": list(spans or []),
    })


def _add_faction_spans(line: str, factions: list[str], spans: list[dict]) -> None:
    seen: set[tuple[int, int]] = set()
    for faction_id in factions:
        name = faction_full_name(faction_id)
        if not name:
            continue
        start = 0
        while True:
            idx = line.find(name, start)
            if idx < 0:
                break
            key = (idx, idx + len(name))
            if key not in seen:
                spans.append({
                    "start": idx,
                    "end": idx + len(name),
                    "kind": "faction",
                    "faction_id": faction_id,
                })
                seen.add(key)
            start = idx + len(name)


def _build_spans(line: str, factions: list[str], tooltip_spans: list[dict] | None = None) -> list[dict]:
    spans = list(tooltip_spans or [])
    _add_faction_spans(line, factions, spans)
    spans.sort(key=lambda item: (item["start"], item["end"]))
    return spans


def log_event(event: dict, event_log: list[str], event_log_meta: list[dict], spirits: dict,
              my_spirit_id: str, faction_agendas: dict):
    """Append a human-readable log entry for the given game event.

    Pure data transformation: reads event dicts and appends strings to
    event_log. Also updates faction_agendas as a side effect for
    agenda_chosen/agenda_random events.

    Returns the event type string for the caller to handle side effects
    (animation fadeout on turn_start, preview clearing on guided, etc.).
    """
    etype = event.get("type", "")

    if etype == "idol_placed":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        _append_line(event_log, event_log_meta, f"{name} placed {event['idol_type']} idol")

    elif etype == "guided":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        line = f"{name} is guiding {fname}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "guide_contested":
        fname = faction_full_name(event["faction"])
        spirit_ids = event.get("spirits", [])
        names = [spirits.get(sid, {}).get("name", sid[:6]) for sid in spirit_ids]
        line = f"Contested guidance of {fname}! ({', '.join(names)})"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "swell":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        _append_line(event_log, event_log_meta, f"{name} Swelled (+{event.get('vp_gained', 10)} VP, total: {event.get('total_vp', 0)})")

    elif etype == "agenda_chosen":
        fname = faction_full_name(event["faction"])
        line = f"The {fname} faction plays {event['agenda']}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))
        faction_agendas[event["faction"]] = event["agenda"]

    elif etype == "agenda_random":
        fname = faction_full_name(event["faction"])
        line = f"The {fname} faction randomly plays {event['agenda']}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))
        faction_agendas[event["faction"]] = event["agenda"]

    elif etype == "steal":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        factions = [event["faction"], *event.get("neighbors", [])]
        line = f"{prefix}{fname} stole {event.get('gold_gained', 0)} gold"
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "trade":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        co_traders = event.get("co_traders", [])
        regard_part = ""
        if co_traders:
            regard_gain = event.get("regard_gain", 0)
            regard_part = f", +{regard_gain} regard"
        factions = [event["faction"], *co_traders]
        line = f"{prefix}{fname} traded for {event.get('gold_gained', 0)} gold{regard_part}"
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "trade_spoils_bonus":
        fname = faction_full_name(event["faction"])
        co_traders = event.get("co_traders", [])
        regard_part = ""
        if co_traders:
            regard_gain = event.get("regard_gain", 0)
            regard_part = f", +{regard_gain} regard"
        factions = [event["faction"], *co_traders]
        line = f"{fname} gained {event.get('gold_gained', 1)} gold{regard_part} from Spoils Trade"
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "expand":
        fname = faction_full_name(event["faction"])
        line = f"{fname} expanded territory"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "expand_failed":
        fname = faction_full_name(event["faction"])
        line = f"{fname} couldn't expand, gained gold"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "change":
        fname = faction_full_name(event["faction"])
        prefix = "Spoils: " if event.get("is_spoils") else ""
        line = f"{prefix}{fname} upgraded {event.get('modifier', '?')}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "change_draw":
        fname = faction_full_name(event["faction"])
        cards = event.get("cards", [])
        line = f"The {fname} faction draws Change: {', '.join(cards)}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "war_declared":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        factions = [event["faction_a"], event["faction_b"]]
        line = f"War declared between {fa} and {fb}!"
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "war_staged":
        fa = faction_full_name(event["faction_a"])
        fb = faction_full_name(event["faction_b"])
        factions = [event["faction_a"], event["faction_b"]]
        line = f"War staged between {fa} and {fb}."
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "war_resolved":
        winner = event.get("winner")
        if winner:
            loser = event.get("loser", "")
            wname = faction_full_name(winner)
            lname = faction_full_name(loser)
            if event.get("forced"):
                line = f"{wname} defeated {lname}! (guided spirit's choice)"
            else:
                line = (
                    f"{wname} defeated {lname}! "
                    f"(Roll: {event.get('roll_a','?')}+{event.get('power_a','?')} vs "
                    f"{event.get('roll_b','?')}+{event.get('power_b','?')})"
                )
            factions = [winner, loser]
            _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))
        else:
            _append_line(event_log, event_log_meta, "War ended in a tie!")

    elif etype == "spoils_drawn":
        fname = faction_full_name(event["faction"])
        line = f"Spoils: {fname} drew {event.get('agenda', '?')}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "spoils_choice":
        fname = faction_full_name(event["faction"])
        cards = event.get("cards", [])
        line = f"Spoils: {fname} choosing from {', '.join(cards)}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "expand_spoils":
        fname = faction_full_name(event["faction"])
        cost = event.get("cost", 0)
        line = (f"Spoils: {fname} conquered enemy territory for {cost} gold"
                if cost else f"Spoils: {fname} conquered enemy territory")
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "vp_scored":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        faction_id = event.get("faction", "")
        faction_name = faction_full_name(faction_id)
        header = f"{name} scored {event.get('vp_gained', 0)} VP from {faction_name} (total: {event.get('total_vp', 0)})"
        _append_line(event_log, event_log_meta, header, [faction_id], _build_spans(header, [faction_id]))
        for contribution in event.get("contributions", []):
            line = contribution.get("line", "")
            tooltip_spans = [
                {
                    "start": span["start"],
                    "end": span["end"],
                    "kind": "tooltip",
                    "tooltip": span["tooltip"],
                }
                for span in contribution.get("spans", [])
            ]
            _append_line(
                event_log,
                event_log_meta,
                line,
                [faction_id],
                _build_spans(line, [faction_id], tooltip_spans),
            )

    elif etype == "era_transition":
        if event.get("vp_reset"):
            _append_line(event_log, event_log_meta, f"Era 2 begins. VP totals reset to 0. New VP target: {event.get('new_vp_target', '?')}")
        else:
            _append_line(event_log, event_log_meta, f"Era 2 begins. New VP target: {event.get('new_vp_target', '?')}")

    elif etype == "era_vp_reset":
        _append_line(event_log, event_log_meta, f"VP totals reset for Era start. Target: {event.get('new_vp_target', '?')}")

    elif etype == "restrained":
        fname = faction_full_name(event["faction"])
        line = f"{fname} restrained {event.get('agenda', '?')}."
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "shaping_chosen":
        fname = faction_full_name(event["faction"])
        line = f"{fname} was shaped by {event.get('card', '?')}."
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "adaptation_chosen":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        _append_line(event_log, event_log_meta, f"{name} adapted with {event.get('card', '?')}.")

    elif etype == "havoc":
        fname = faction_full_name(event["faction"])
        line = f"{fname} caused Havoc: {event.get('old_type', '?')} became {event.get('new_type', '?')}."
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "regard_shift":
        fname = faction_full_name(event["faction"])
        other = faction_full_name(event["other_faction"])
        factions = [event["faction"], event["other_faction"]]
        line = f"{fname} regained {event.get('delta', 0)} Regard with {other}."
        _append_line(event_log, event_log_meta, line, factions, _build_spans(line, factions))

    elif etype == "ejected":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        line = f"{name} ejected from {fname}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "worship_gained":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        fname = faction_full_name(event["faction"])
        line = f"The {fname} faction now worships {name}"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "worship_replaced":
        name = spirits.get(event["spirit"], {}).get("name", event["spirit"][:6])
        old_name = spirits.get(event.get("old_spirit", ""), {}).get("name", event.get("old_spirit", "?")[:6])
        fname = faction_full_name(event["faction"])
        line = f"The {fname} faction now worships {name} (was {old_name})"
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "faction_respawning":
        fname = faction_full_name(event["faction"])
        gold_lost = event.get("gold_lost", 0)
        line = f"{fname} lost all territory! Lost {gold_lost} gold - choosing where to reappear."
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "faction_respawned":
        fname = faction_full_name(event["faction"])
        h = event.get("hex")
        line = f"{fname} reappeared at ({h['q']}, {h['r']})." if h else f"{fname} reappeared."
        _append_line(event_log, event_log_meta, line, [event["faction"]], _build_spans(line, [event["faction"]]))

    elif etype == "war_ended":
        fa_id = event.get("faction_a")
        fb_id = event.get("faction_b")
        if fa_id and fb_id:
            line = (
                f"War between {faction_full_name(fa_id)} and {faction_full_name(fb_id)} "
                f"dissipated due to territorial changes."
            )
            _append_line(event_log, event_log_meta, line, [fa_id, fb_id], _build_spans(line, [fa_id, fb_id]))
        elif event.get("message"):
            _append_line(event_log, event_log_meta, event["message"])
        else:
            _append_line(event_log, event_log_meta, f"War ended ({event.get('reason', 'unknown')})")

    elif etype == "setup_start":
        _append_line(event_log, event_log_meta, "--- Setup ---")

    elif etype == "turn_start":
        _append_line(event_log, event_log_meta, f"--- Turn {event.get('turn', '?')} ---")

    elif etype == "game_over":
        winners = event.get("winners", [])
        names = [spirits.get(w, {}).get("name", w[:6]) for w in winners]
        _append_line(event_log, event_log_meta, f"GAME OVER! Winner(s): {', '.join(names)}")

    return etype
