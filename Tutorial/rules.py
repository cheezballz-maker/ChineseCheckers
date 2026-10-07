"""Supplied rule adapter. We will unpack this in module 2.

Candidates come from the game's public API. This adapter filters the
goal restrictions implemented in ChineseCheckersGame.apply_move.
"""
import sys
from pathlib import Path

main_modules = Path(__file__).resolve().parent.parent/"Task"
sys.path.append(str(main_modules))

from game_snapshot import GameSnapshot
from utility import PlayerId


def follows_goal_rule(path, goal):
    """Return whether an engine-provided path passes the game's goal checks."""
    if not path:
        return False

    # The current game checks only the endpoints for a piece already in goal.
    if path[0] in goal:
        return path[-1] in goal

    entered_goal = False
    for cell in path[1:]:
        if cell in goal:
            entered_goal = True
        elif entered_goal:
            return False
    return True


def get_playable_moves(game: GameSnapshot, player: PlayerId):
    """Return sorted (start, end) moves that pass this game's goal checks.

    Use only with candidates from this snapshot, for the player taking a turn.
    The returned list is a new list; the snapshot is never modified.
    """
    goal = game.goal_triangles[player]
    playable = []
    paths_by_start = {}

    for start, end in game.get_all_legal_moves(player):
        # The API already validates swap eligibility. An occupied destination
        # in this candidate list denotes a swap, with no regular jump path.
        if end in game.pieces:
            playable.append((start, end))
            continue

        # Reuse paths when several candidates move the same piece.
        if start not in paths_by_start:
            paths_by_start[start] = game.get_moves_with_paths(start)
        path = paths_by_start[start].get(end, [])
        if follows_goal_rule(path, goal):
            playable.append((start, end))

    return sorted(playable)
