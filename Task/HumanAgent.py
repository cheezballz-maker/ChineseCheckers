from Agent import Agent


class HumanAgent(Agent):
    """
    Marker class for human-controlled player.
    The Driver handles interaction via UI.
    """

    def select_move(self, game, player):
        raise NotImplementedError(
            "HumanAgent does not select moves directly. Driver handles this."
        )