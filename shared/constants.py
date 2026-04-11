"""Game constants shared between client and server."""

from enum import Enum


# Map
MAP_SIDE_LENGTH = 5


# Factions
class FactionId(str, Enum):
    MOUNTAIN = "mountain"
    MESA     = "mesa"
    SAND     = "sand"
    PLAINS   = "plains"
    RIVER    = "river"
    JUNGLE   = "jungle"


FACTION_NAMES = list(FactionId)

FACTION_COLORS = {
    FactionId.MOUNTAIN: (200, 50, 50),     # red
    FactionId.MESA:     (220, 140, 40),    # orange
    FactionId.SAND:     (220, 210, 60),    # yellow
    FactionId.PLAINS:   (60, 180, 60),     # green
    FactionId.RIVER:    (50, 100, 220),    # blue
    FactionId.JUNGLE:   (140, 50, 200),    # purple
}

FACTION_DISPLAY_NAMES = {
    FactionId.MOUNTAIN: "Mountain",
    FactionId.MESA:     "Mesa",
    FactionId.SAND:     "Sand",
    FactionId.PLAINS:   "Plains",
    FactionId.RIVER:    "River",
    FactionId.JUNGLE:   "Jungle",
}

RACES = ["Elves", "Orcs", "Fae", "Dwarves", "Goblins", "Elementals"]

# Starting hex positions for the 6 factions (axial coords around center 0,0)
FACTION_START_HEXES = {
    FactionId.MOUNTAIN: (1, -1),
    FactionId.MESA:     (1, 0),
    FactionId.SAND:     (0, 1),
    FactionId.PLAINS:   (-1, 1),
    FactionId.RIVER:    (-1, 0),
    FactionId.JUNGLE:   (0, -1),
}

# Neutral color
NEUTRAL_COLOR = (120, 120, 120)

# Display
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
FPS = 60
TITLE = "Impetus"
HEX_SIZE = 46

# Game rules
STARTING_GOLD = 0
STARTING_INFLUENCE = 3
MAX_INFLUENCE = 3
VP_TO_WIN = 100

# Scoring multipliers
BATTLE_IDOL_VP = 5
AFFLUENCE_IDOL_VP = 2
SPRAWL_IDOL_VP = 5
SPREAD_IDOL_VP = SPRAWL_IDOL_VP

# Era 2 idol adjustments
ERA2_AFFLUENCE_IDOL_VP_MULTIPLIER = 0.5
ERA2_DEFAULT_CARD_DRAW = 3
ERA2_SHORT_DEAL_VP = 5

# Server
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
RECONNECT_TIMEOUT = 60


class Phase(str, Enum):
    LOBBY = "lobby"
    SETUP = "setup"
    VAGRANT_PHASE = "vagrant_phase"
    AGENDA_PHASE = "agenda_phase"
    WAR_PHASE = "war_phase"
    SCORING = "scoring"
    CLEANUP = "cleanup"
    GAME_OVER = "game_over"


class Era(str, Enum):
    ERA_1 = "era_1"
    ERA_2 = "era_2"


class AgendaType(str, Enum):
    STEAL = "steal"
    TRADE = "trade"
    EXPAND = "expand"
    CHANGE = "change"


# Resolution order for agendas
AGENDA_RESOLUTION_ORDER = [
    AgendaType.TRADE,
    AgendaType.STEAL,
    AgendaType.EXPAND,
    AgendaType.CHANGE,
]


class IdolType(str, Enum):
    BATTLE = "battle"
    AFFLUENCE = "affluence"
    SPRAWL = "sprawl"
    SPREAD = "sprawl"


GuidanceStep = str


class ChangeModifierTarget(str, Enum):
    TRADE = "trade"
    STEAL = "steal"
    EXPAND = "expand"


# The change modifier deck: one card for each of the other 3 agenda types
CHANGE_DECK = [
    ChangeModifierTarget.TRADE,
    ChangeModifierTarget.STEAL,
    ChangeModifierTarget.EXPAND,
]

# Starting Change modifiers per faction habitat
HABITAT_STARTING_MODIFIERS: dict[FactionId, dict[ChangeModifierTarget, int]] = {
    FactionId.MOUNTAIN: {ChangeModifierTarget.TRADE: 1, ChangeModifierTarget.STEAL: 1},
    FactionId.MESA:     {ChangeModifierTarget.TRADE: 2},
    FactionId.SAND:     {ChangeModifierTarget.STEAL: 1, ChangeModifierTarget.EXPAND: 1},
    FactionId.PLAINS:   {ChangeModifierTarget.EXPAND: 2},
    FactionId.RIVER:    {ChangeModifierTarget.TRADE: 1, ChangeModifierTarget.EXPAND: 1},
    FactionId.JUNGLE:   {ChangeModifierTarget.STEAL: 2},
}
