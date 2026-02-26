"""Game constants shared between client and server."""

from enum import Enum

# Map
MAP_SIDE_LENGTH = 5

# Factions
FACTION_NAMES = ["mountain", "mesa", "sand", "plains", "river", "jungle"]

FACTION_COLORS = {
    "mountain": (200, 50, 50),     # red
    "mesa": (220, 140, 40),        # orange
    "sand": (220, 210, 60),        # yellow
    "plains": (60, 180, 60),       # green
    "river": (50, 100, 220),       # blue
    "jungle": (140, 50, 200),      # purple
}

FACTION_DISPLAY_NAMES = {
    "mountain": "Mountain",
    "mesa": "Mesa",
    "sand": "Sand",
    "plains": "Plains",
    "river": "River",
    "jungle": "Jungle",
}

RACES = ["Elves", "Orcs", "Fae", "Dwarves", "Goblins", "Elementals"]

# Starting hex positions for the 6 factions (axial coords around center 0,0)
FACTION_START_HEXES = {
    "mountain": (1, -1),
    "mesa": (1, 0),
    "sand": (0, 1),
    "plains": (-1, 1),
    "river": (-1, 0),
    "jungle": (0, -1),
}

# Neutral color
NEUTRAL_COLOR = (120, 120, 120)

# Display
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
FPS = 60
TITLE = "Impetus"
HEX_SIZE = 42

# Game rules
STARTING_GOLD = 0
STARTING_INFLUENCE = 3
MAX_INFLUENCE = 3
VP_TO_WIN = 100

# Scoring multipliers
BATTLE_IDOL_VP = 5
AFFLUENCE_IDOL_VP = 2
SPREAD_IDOL_VP = 5

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


class SubPhase(str, Enum):
    CHANGE_CHOICE        = "change_choice"
    EJECTION_CHOICE      = "ejection_choice"
    SPOILS_CHOICE        = "spoils_choice"
    SPOILS_CHANGE_CHOICE = "spoils_change_choice"
    BATTLEGROUND_CHOICE  = "battleground_choice"
    EXPAND_CHOICE        = "expand_choice"


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
    SPREAD = "spread"


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
HABITAT_STARTING_MODIFIERS: dict[str, dict[ChangeModifierTarget, int]] = {
    "mountain": {ChangeModifierTarget.TRADE: 1, ChangeModifierTarget.STEAL: 1},
    "mesa":     {ChangeModifierTarget.TRADE: 2},
    "sand":     {ChangeModifierTarget.STEAL: 1, ChangeModifierTarget.EXPAND: 1},
    "plains":   {ChangeModifierTarget.EXPAND: 2},
    "river":    {ChangeModifierTarget.TRADE: 1, ChangeModifierTarget.EXPAND: 1},
    "jungle":   {ChangeModifierTarget.STEAL: 2},
}


class MessageType(str, Enum):
    # Client -> Server
    JOIN_GAME = "join_game"
    READY = "ready"
    START_GAME = "start_game"
    SET_LOBBY_OPTIONS = "set_lobby_options"
    TOGGLE_SPECTATOR = "toggle_spectator"
    SUBMIT_VAGRANT_ACTION = "submit_vagrant_action"
    SUBMIT_AGENDA_CHOICE = "submit_agenda_choice"
    SUBMIT_CHANGE_CHOICE = "submit_change_choice"
    SUBMIT_EJECTION_AGENDA = "submit_ejection_agenda"
    SUBMIT_SPOILS_CHOICE = "submit_spoils_choice"
    SUBMIT_SPOILS_CHANGE_CHOICE = "submit_spoils_change_choice"
    SUBMIT_BATTLEGROUND_CHOICE = "submit_battleground_choice"
    SUBMIT_EXPAND_CHOICE       = "submit_expand_choice"
    # Server -> Client
    LOBBY_STATE = "lobby_state"
    GAME_START = "game_start"
    PHASE_START = "phase_start"
    WAITING_FOR = "waiting_for"
    PHASE_RESULT = "phase_result"
    GAME_OVER = "game_over"
    ERROR = "error"
