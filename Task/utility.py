from enum import Enum, auto

class PlayerId(Enum):
    PLAYER_1 = auto()
    PLAYER_2 = auto()
    PLAYER_3 = auto()
    PLAYER_4 = auto()
    PLAYER_5 = auto()
    PLAYER_6 = auto()


PLAYER_COLORS = [
    "#e74c3c",  # red
    "#3498db",  # blue
    "#2ecc71",  # green
    "#f1c40f",  # bright yellow
    "#9b59b6",  # purple
    "#e67e22"   # orange
]

PLAYER_COLOR_MAP = {
    PlayerId.PLAYER_1: PLAYER_COLORS[0],
    PlayerId.PLAYER_2: PLAYER_COLORS[1],
    PlayerId.PLAYER_3: PLAYER_COLORS[2],
    PlayerId.PLAYER_4: PLAYER_COLORS[3],
    PlayerId.PLAYER_5: PLAYER_COLORS[4],
    PlayerId.PLAYER_6: PLAYER_COLORS[5]
}
