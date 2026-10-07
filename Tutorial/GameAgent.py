import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
main_modules = project_root / "Task"
sys.path.append(str(project_root))
sys.path.append(str(main_modules))

from Agent import Agent
from game_snapshot import GameSnapshot
from utility import PlayerId
from Tutorial.rules import get_playable_moves

# Geometric distance between two cell positions
def hex_dist(a, b):
    # "a" and "b" are two hexagonal locations
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq)+abs(dr)+abs(dq+dr))//2

# Returns the shortest distance to the goal (as a collective triangle)
def dist_to_goal(cell, goal:set):
    dists = set()
    for goal_cell in goal:
        dists.add(hex_dist(cell, goal_cell))
    return min(dists)

# Evaluate the difference in distance to the goal before and after a move is performed (aka the distance closed)
def score_move(move: tuple[tuple[int,int],tuple[int,int]], goal:frozenset[tuple[int,int]]):
    before_dist = dist_to_goal(move[0],goal)
    after_dist = dist_to_goal(move[1],goal)
    return before_dist - after_dist

# Predict the board state after a single move has been played
def simulate_move(pieces, move):
    predicted_board = dict(pieces)
    start, end = move
    if end not in predicted_board:
        predicted_board[end] = predicted_board.pop(start)
    else:
        predicted_board[start], predicted_board[end] = (
            predicted_board[end],
            predicted_board[start],
        )
    return predicted_board


class GameAgent(Agent):
    def select_move(self, game: GameSnapshot, player: PlayerId):
        moves = get_playable_moves(game, player)
        goal = game.goal_triangles[player]
        if not moves:
            return None
        best_score = score_move(moves[0],goal)
        best_move = moves[0]
        for move in moves:
            score = score_move(move, goal)
            if score > best_score:
                best_score = score
                best_move = move
        return best_move

if __name__ == "__main__":
    from game import ChineseCheckersGame
    # agent = GameAgent()

    # match = ChineseCheckersGame({
    #     PlayerId.p1: agent,
    #     PlayerId.p2: agent,
    # })

    # snapshot = match.snapshot()
    # player = snapshot.current_player


    p1 = PlayerId.PLAYER_1
    p2 = PlayerId.PLAYER_2
    pieces = {
                (0, 0): p1, 
                (1, 0): p2
              }
    future = simulate_move(pieces, ((0, 0), (0, 1)))

    assert future == {(0, 1): p1, (1, 0): p2}
    assert pieces == {(0, 0): p1, (1, 0): p2}
    assert future is not pieces

    future = simulate_move(pieces, ((0, 0), (1, 0)))

    assert future == {(0, 0): p2, (1, 0): p1}
    assert pieces == {(0, 0): p1, (1, 0): p2}