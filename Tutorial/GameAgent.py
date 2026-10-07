import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
main_modules = project_root / "Task"
sys.path.append(str(project_root))
sys.path.append(str(main_modules))

from Agent import Agent
from game_snapshot import GameSnapshot
from utility import PlayerId
from game import ChineseCheckersGame
from Tutorial.rules import get_playable_moves

def hex_dist(a, b):
    '''
    Geometric distance between two cell positions
    '''
    # "a" and "b" are two hexagonal locations
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq)+abs(dr)+abs(dq+dr))//2

def dist_to_goal(cell, goal:set):
    '''
    Returns the shortest distance to the goal (as a collective triangle)
    '''
    dists = set()
    for goal_cell in goal:
        dists.add(hex_dist(cell, goal_cell))
    return min(dists)

def score_move(move: tuple[tuple[int,int],tuple[int,int]], goal:frozenset[tuple[int,int]]):
    '''
    Evaluate the difference in distance to the goal before and after a move is performed (aka the distance closed)
    '''
    before_dist = dist_to_goal(move[0],goal)
    after_dist = dist_to_goal(move[1],goal)
    return before_dist - after_dist

def simulate_move(pieces, move):
    '''
    Predict the board state after a single move has been played
    '''
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

def evaluate_player_pieces(pieces, player, goal):
    '''
    Provide an aggregate score of ALL player's pieces in relation to the goal
    '''
    player_pieces = [piece for piece in pieces if pieces[piece] == player]
    dist_sq_sum = 0
    for piece in player_pieces:
        dist_sq_sum += dist_to_goal(piece, goal)**2
    return -dist_sq_sum

# Note: pieces can be a collection of moves from multiple players
def position_key(pieces) -> frozenset[tuple[tuple[int,int],PlayerId]]:
    return frozenset(pieces.items())

class GameAgent(Agent):
    def __init__(self):
        self.positions_count = {}
        
    def select_move(self, game: GameSnapshot, player: PlayerId):
        moves = get_playable_moves(game, player)
        goal = game.goal_triangles[player]
        pieces = game.pieces

        if not moves:
            return None
        
        best_move = moves[0]
        simulated_board = simulate_move(pieces, best_move)
        best_score = evaluate_player_pieces(simulated_board, player, goal)

        for move in moves:
            simulated_board = simulate_move(pieces, move)
            key = position_key(simulated_board)
            score = evaluate_player_pieces(simulated_board, player, goal)

            if score > best_score:
                best_score = score
                best_move = move
            elif score == best_score:
                best_key = position_key(simulate_move(pieces, best_move))
                if self.positions_count.get(key,0) < self.positions_count.get(best_key,0):
                    best_score = score
                    best_move = move
        best_key = position_key(simulate_move(pieces, best_move))         
        self.positions_count[best_key] = self.positions_count.get(best_key, 0) + 1
        return best_move

def run_match(agents, max_turns):
    game = ChineseCheckersGame(agents)
    turn = 0
    while not game.game_over and (turn < max_turns):
        snapshot = game.snapshot()
        player = snapshot.current_player
        move = agents[player].select_move(snapshot, player)
        game.step(move)
        turn += 1
    return turn, game

if __name__ == "__main__":

    agents = {
        PlayerId.PLAYER_1: GameAgent(),
        PlayerId.PLAYER_2: GameAgent(),
        }

    turns, game = run_match(agents, 500)
    print(turns, game.game_over, game.winner, game.loser)