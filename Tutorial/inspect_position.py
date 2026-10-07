"""Run from the project root: python -B -m Tutorial.inspect_position"""
import sys
from pathlib import Path

main_modules = Path(__file__).resolve().parent.parent/"Task"
sys.path.append(str(main_modules))
from game import ChineseCheckersGame
from utility import PlayerId
from Tutorial.rules import get_playable_moves


def main():
    # None is sufficient here: this script calls no agent and runs no GUI.
    match = ChineseCheckersGame({
        PlayerId.PLAYER_1: None,
        PlayerId.PLAYER_2: None,
    })
    snapshot = match.snapshot()
    player = snapshot.current_player
    moves = get_playable_moves(snapshot, player)

    print("Player:", player.name)
    print("Own pieces:", list(snapshot.pieces.values()).count(player))
    print("Goal cells:", len(snapshot.goal_triangles[player]))
    print("Playable moves:", len(moves))
    print("First move:", moves[0] if moves else None)


if __name__ == "__main__":
    main()
