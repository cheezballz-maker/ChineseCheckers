"""
Student Agent
"""
import random

from Agent import Agent
from game_snapshot import GameSnapshot
from utility import PlayerId


class GameAgent(Agent):
    """
    Student implements this.
    """
    def select_move(self, game: GameSnapshot, player: PlayerId):
        moves = game.get_all_legal_moves(player)

        if not moves:
            return None

        # TODO: student logic here
        return random.choice(moves)
