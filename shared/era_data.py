"""Shared Era 2 card data and labels."""

from __future__ import annotations


GUIDANCE_STEP_RESTRAIN = "restrain"
GUIDANCE_STEP_SHAPE = "shape"
GUIDANCE_STEP_ADAPT = "adapt"
GUIDANCE_STEP_EJECT = "eject"

GUIDANCE_STEP_ORDER = [
    GUIDANCE_STEP_RESTRAIN,
    GUIDANCE_STEP_SHAPE,
    GUIDANCE_STEP_ADAPT,
    GUIDANCE_STEP_EJECT,
]

SHAPING_CARDS = [
    "Glory in War",
    "Pyrrhic Defeat",
    "Fair Weather Friends",
    "Hellbound",
    "Turn the Other Cheek",
    "Amplified Steal",
    "Amplified Change",
    "Amplified Trade",
    "Amplified Expand",
    "Globalization",
    "Havoc",
    "Unilateral Agreement",
    "Special Military Operations",
]

ADAPTATION_CARDS = [
    "Mesa Devotion",
    "Mountain Devotion",
    "Sand Devotion",
    "Jungle Devotion",
    "River Devotion",
    "Plains Devotion",
    "Avatar of War",
    "Avatar of Affluence",
    "Avatar of Sprawl",
    "Changer of Ways",
    "Battle Blessing",
    "Usurper",
]

SHAPING_CARD_INFO = {
    "Glory in War": {
        "body": "Spoils drawn twice",
        "tooltip": "When drawing Spoils of War, draw and resolve an additional Agenda card from your Agenda pool.",
    },
    "Pyrrhic Defeat": {
        "body": "Spoils draw after losing",
        "tooltip": "Also draw Spoils of War when losing a War.",
    },
    "Fair Weather Friends": {
        "body": "+Regard with stronger and -Regard with weaker neighbors",
        "tooltip": "Double the Regard gained with stronger factions. Double the Regard lost with weaker factions.",
    },
    "Hellbound": {
        "body": "Can't gain Regard",
        "tooltip": "Cannot gain Regard with other factions, even if the source of that Regard is another faction.",
    },
    "Turn the Other Cheek": {
        "body": "Reset Regard after War",
        "tooltip": "After one of your Wars resolves, gain Regard with the opposing Faction equal to the current negative Regard with them.",
    },
    "Amplified Steal": {
        "body": "Steal resolves twice",
        "tooltip": "When resolving a Steal Agenda, resolve it an additional time.",
    },
    "Amplified Change": {
        "body": "Change resolves twice",
        "tooltip": "When resolving a Change Agenda, resolve it an additional time.",
    },
    "Amplified Trade": {
        "body": "Trade resolves twice",
        "tooltip": "When resolving a Trade Agenda, resolve it an additional time.",
    },
    "Amplified Expand": {
        "body": "Expand resolves twice",
        "tooltip": "When resolving an Expand Agenda, resolve it an additional time.",
    },
    "Globalization": {
        "body": "Steal from everyone",
        "tooltip": "Steal Agendas also affect factions that this faction is not neighbors with. Wars do not get declared with non-neighbors.",
    },
    "Havoc": {
        "body": "Change randomizes an Idol",
        "tooltip": "Change Agendas also switch the type of a random idol within this faction's territory to one of the other 2 types at random.",
    },
    "Unilateral Agreement": {
        "body": "Trade benefits from other Expands",
        "tooltip": "Trade Agendas also get bonuses from other factions' Expand Agendas.",
    },
    "Special Military Operations": {
        "body": "Expand can target non-neutral territories",
        "tooltip": "Expand Agendas can take over other factions' territories even without a War.",
    },
}

ADAPTATION_CARD_INFO = {
    "Mesa Devotion": {
        "body": "+VP from Mesa, -VP from others",
        "tooltip": "VP gained from the Mesa faction is tripled. VP gained from other factions is halved.",
    },
    "Mountain Devotion": {
        "body": "+VP from Mountain, -VP from others",
        "tooltip": "VP gained from the Mountain faction is tripled. VP gained from other factions is halved.",
    },
    "Sand Devotion": {
        "body": "+VP from Sand, -VP from others",
        "tooltip": "VP gained from the Sand faction is tripled. VP gained from other factions is halved.",
    },
    "Jungle Devotion": {
        "body": "+VP from Jungle, -VP from others",
        "tooltip": "VP gained from the Jungle faction is tripled. VP gained from other factions is halved.",
    },
    "River Devotion": {
        "body": "+VP from River, -VP from others",
        "tooltip": "VP gained from the River faction is tripled. VP gained from other factions is halved.",
    },
    "Plains Devotion": {
        "body": "+VP from Plains, -VP from others",
        "tooltip": "VP gained from the Plains faction is tripled. VP gained from other factions is halved.",
    },
    "Avatar of War": {
        "body": "+VP from War Idols, -VP from others",
        "tooltip": "VP gained from War Idols is doubled. VP gained from other Idols is halved.",
    },
    "Avatar of Affluence": {
        "body": "+VP from Affluence Idols, -VP from others",
        "tooltip": "VP gained from Affluence Idols is doubled. VP gained from other Idols is halved.",
    },
    "Avatar of Sprawl": {
        "body": "+VP from Sprawl Idols, -VP from others",
        "tooltip": "VP gained from Sprawl Idols is doubled. VP gained from other Idols is halved.",
    },
    "Changer of Ways": {
        "body": "Swap more Agendas when ejecting",
        "tooltip": "When Ejecting, replace an Agenda in the Faction's Agenda Pool an additional time.",
    },
    "Battle Blessing": {
        "body": "Affect War results more",
        "tooltip": "Triple your influence on the results of a War: when you would add an additional die to a Faction's power, instead add 3 such dice.",
    },
    "Usurper": {
        "body": "Gain more VP from others' Idols",
        "tooltip": "You gain full VP from Idols in Factions which Worship you, even if you do not own the Idol. The original owner still gets their 50% share.",
    },
}


def get_era_card_info(card_name: str) -> dict[str, str] | None:
    return SHAPING_CARD_INFO.get(card_name) or ADAPTATION_CARD_INFO.get(card_name)
