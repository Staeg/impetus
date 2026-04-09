"""Shared helpers for sending pending-choice prompts to players."""

from __future__ import annotations

from dataclasses import dataclass

from shared.protocol import S2C, create_message


@dataclass(frozen=True)
class PendingChoicePrompt:
    """A phase/sub-phase prompt targeted at one spirit."""

    spirit_id: str
    phase: str
    turn: int
    options: dict


async def send_choice_prompts(room, prompts: list[PendingChoicePrompt]) -> None:
    """Send phase_start prompts to their target spirits."""

    for prompt in prompts:
        await room.send_to(prompt.spirit_id, create_message(S2C.PHASE_START, {
            "phase": prompt.phase,
            "turn": prompt.turn,
            "options": prompt.options,
        }))


async def broadcast_waiting_for(room, spirit_ids: list[str]) -> None:
    """Broadcast the spirits still needed for the current pending choice."""

    await room.broadcast(create_message(S2C.WAITING_FOR, {
        "players_remaining": spirit_ids,
    }))
