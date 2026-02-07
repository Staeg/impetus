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
HEX_SIZE = 30

# Game rules
STARTING_GOLD = 0
STARTING_INFLUENCE = 3
MAX_INFLUENCE = 3
VP_TO_WIN = 10

# Scoring multipliers
BATTLE_IDOL_VP = 0.5
AFFLUENCE_IDOL_VP = 0.2
SPREAD_IDOL_VP = 0.5

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


class AgendaType(str, Enum):
    STEAL = "steal"
    BOND = "bond"
    TRADE = "trade"
    EXPAND = "expand"
    CHANGE = "change"


# Resolution order for agendas
AGENDA_RESOLUTION_ORDER = [
    AgendaType.STEAL,
    AgendaType.BOND,
    AgendaType.TRADE,
    AgendaType.EXPAND,
    AgendaType.CHANGE,
]


class IdolType(str, Enum):
    BATTLE = "battle"
    AFFLUENCE = "affluence"
    SPREAD = "spread"


class ChangeModifierTarget(str, Enum):
    TRADE = "trade"
    BOND = "bond"
    STEAL = "steal"
    EXPAND = "expand"


# The change modifier deck: one card for each of the other 4 agenda types
CHANGE_DECK = [
    ChangeModifierTarget.TRADE,
    ChangeModifierTarget.BOND,
    ChangeModifierTarget.STEAL,
    ChangeModifierTarget.EXPAND,
]


class MessageType(str, Enum):
    # Client -> Server
    JOIN_GAME = "join_game"
    READY = "ready"
    SUBMIT_VAGRANT_ACTION = "submit_vagrant_action"
    SUBMIT_AGENDA_CHOICE = "submit_agenda_choice"
    SUBMIT_CHANGE_CHOICE = "submit_change_choice"
    SUBMIT_EJECTION_AGENDA = "submit_ejection_agenda"
    SUBMIT_SPOILS_CHOICE = "submit_spoils_choice"
    # Server -> Client
    LOBBY_STATE = "lobby_state"
    GAME_START = "game_start"
    PHASE_START = "phase_start"
    WAITING_FOR = "waiting_for"
    PHASE_RESULT = "phase_result"
    GAME_OVER = "game_over"
    ERROR = "error"
