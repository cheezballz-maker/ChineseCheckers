"""Small exercise checks; run from the project root with -B -m."""

from unittest.mock import patch

from Tutorial.GameAgent import GameAgent
from game import ChineseCheckersGame
from utility import PlayerId
from Tutorial.rules import get_playable_moves


def main():
    agent = GameAgent()
    player = PlayerId.PLAYER_1
    first = ((1, -5), (1, -4))
    second = ((2, -5), (2, -4))

    try:
        for moves, expected in [([], None), ([first], first), ([first, second], first)]:
            # Temporarily supply a known list, without changing any source file.
            with patch("Tutorial.GameAgent.get_playable_moves", return_value=moves):
                actual = agent.select_move(None, player)
            if actual != expected:
                raise AssertionError(f"For {moves!r}: expected {expected!r}, got {actual!r}")
        print("PASS: empty, single, and multiple move selection")

        for count in (2, 3, 4, 6):
            players = list(PlayerId)[:count]
            match = ChineseCheckersGame({p: agent for p in players})
            snapshot = match.snapshot()
            before = dict(snapshot.pieces)
            move = agent.select_move(snapshot, snapshot.current_player)
            expected = get_playable_moves(snapshot, snapshot.current_player)[0]
            if move != expected:
                raise AssertionError(f"Expected the first playable move for {count} players")
            match.step(move)
            if match.loser is not None or len(match.move_history) != 1:
                raise AssertionError(f"Engine rejected the move for {count} players")
            if dict(snapshot.pieces) != before:
                raise AssertionError("The snapshot was modified")
        print("PASS: selected opening move accepted for 2, 3, 4, and 6 players")
        return 0
    except NotImplementedError:
        print("NOT READY: implement move selection in Tutorial/GameAgent.py")
        return 1
    except AssertionError as error:
        print("TRY AGAIN:", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
