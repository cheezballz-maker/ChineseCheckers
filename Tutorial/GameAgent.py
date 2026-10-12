import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
main_modules = project_root / "Task"
sys.path.append(str(project_root))
sys.path.append(str(main_modules))

from functools import lru_cache

from Agent import Agent
from game_snapshot import GameSnapshot
from utility import PlayerId
from game import ChineseCheckersGame
from Tutorial.rules import get_playable_moves, follows_goal_rule

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
    Score the cost of assigning each player's piece to a different goal cell
    '''
    player_pieces = tuple(sorted(piece for piece in pieces if pieces[piece] == player))
    goal_cells = tuple(sorted(goal))
    return -goal_assignment_cost(player_pieces, goal_cells)


@lru_cache(maxsize=4096)
def goal_assignment_cost(player_pieces, goal_cells):
    '''
    Find the lowest sum of squared distances using each goal cell at most once
    '''
    if not player_pieces:
        return 0
    if len(player_pieces) > len(goal_cells):
        raise ValueError('There must be at least one goal cell for each piece')

    # A bit in used_cells records whether a goal cell has already been assigned.
    assignment_costs = {0: 0}
    for piece in player_pieces:
        next_assignment_costs = {}
        dists = [hex_dist(piece, goal_cell)**2 for goal_cell in goal_cells]
        for used_cells, cost in assignment_costs.items():
            for index, dist in enumerate(dists):
                cell_bit = 1 << index
                if used_cells & cell_bit:
                    continue
                next_used_cells = used_cells | cell_bit
                next_cost = cost + dist
                if (next_used_cells not in next_assignment_costs
                        or next_cost < next_assignment_costs[next_used_cells]):
                    next_assignment_costs[next_used_cells] = next_cost
        assignment_costs = next_assignment_costs
    return min(assignment_costs.values())

# Note: pieces can be a collection of moves from multiple players
def position_key(pieces) -> frozenset[tuple[tuple[int,int],PlayerId]]:
    return frozenset(pieces.items())

def evaluate_player_progress(game, simulated_board, player):
    '''
    Measures how well a player's pieces are advancing
    '''
    total_advancement = 0
    goal = game.goal_triangles[player]
    player_pieces = [piece for piece in simulated_board if simulated_board[piece] == player]

    for piece in player_pieces:
        best_piece_advancement = 0
        paths = game.get_moves_with_paths_for(piece, simulated_board)
        for end, path in paths.items():
            if not follows_goal_rule(path, goal):
                continue
            piece_advancement = score_move((piece, end),goal)
            if piece_advancement > best_piece_advancement:
                best_piece_advancement = piece_advancement
        total_advancement += best_piece_advancement
    return total_advancement


def evaluate_player_board(game, pieces, player, mobility_weight):
    '''
    Combine goal assignment with opportunities that matter less near the finish
    '''
    goal = game.goal_triangles[player]
    player_pieces = [piece for piece in pieces if pieces[piece] == player]
    if not player_pieces:
        return 0
    remaining_pieces = sum(piece not in goal for piece in player_pieces)
    position_score = evaluate_player_pieces(pieces, player, goal)
    progress_score = evaluate_player_progress(game, pieces, player)
    progress_weight = mobility_weight * remaining_pieces / len(player_pieces)
    return position_score + progress_weight * progress_score

class GameAgent(Agent):
    def __init__(self):
        self.positions_count = {}
        self.recent_positions = []
        self.repetition_weight = 2.0
        self.mobility_weight = 0.25
        self.opponent_weight = 0.8
        
    def select_move(self, game: GameSnapshot, player: PlayerId):
        '''
        Weigh our improvement against the opponents' improvement after each move
        '''
        moves = get_playable_moves(game, player)
        goal = game.goal_triangles[player]
        pieces = game.pieces

        if not moves:
            return None

        opponents = [opponent for opponent in game.players if opponent != player]
        before_score = evaluate_player_board(game, pieces, player, self.mobility_weight)

        opponent_before_scores = {}
        for opponent in opponents:
            opponent_before_scores[opponent] = evaluate_player_board(
                game, pieces, opponent, self.mobility_weight
            )

        best_move = None
        best_rank = None
        best_key = None

        for move in moves:
            simulated_board = simulate_move(pieces, move)
            key = position_key(simulated_board)
            after_score = evaluate_player_board(game, simulated_board, player, self.mobility_weight)
            player_improvement = after_score - before_score

            opponent_improvement = 0
            for opponent in opponents:
                opponent_after_score = evaluate_player_board(
                    game, simulated_board, opponent, self.mobility_weight
                )
                opponent_improvement += opponent_after_score - opponent_before_scores[opponent]

            # Average the opponents so larger games do not outweigh our own progress.
            if opponents:
                opponent_improvement /= len(opponents)

            # Helping opponents reduces the score; damaging their position increases it.
            combined_score = player_improvement - self.opponent_weight * opponent_improvement
            player_pieces = frozenset(piece for piece in simulated_board if simulated_board[piece] == player)
            own_key = (player, player_pieces)
            repeat_count = self.recent_positions.count(own_key)
            combined_score -= self.repetition_weight * repeat_count
            count = self.positions_count.get(key, 0)
            wins = all(
                cell in goal
                for cell, owner in simulated_board.items()
                if owner == player
            )

            # Compare wins first, then combined score, then fewer repetitions.
            rank = (wins, combined_score, -count)
            if best_rank is None or rank > best_rank:
                best_move = move
                best_rank = rank
                best_key = key
        
        self.positions_count[best_key] = self.positions_count.get(best_key, 0) + 1
        simulated_board = simulate_move(pieces, best_move)
        player_pieces = frozenset(piece for piece in simulated_board if simulated_board[piece] == player)
        self.recent_positions.append((player, player_pieces))
        self.recent_positions = self.recent_positions[-12:]
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

    p1 = PlayerId.PLAYER_1
    p2 = PlayerId.PLAYER_2

    match = ChineseCheckersGame({p1: None, p2: None})
    snapshot = match.snapshot()

    # No pieces: no opportunities.
    assert evaluate_player_progress(snapshot, {}, p1) == 0

    # Only an opponent's piece: no opportunities for p1.
    opponent_only = {(0, 0): p2}
    assert evaluate_player_progress(snapshot, opponent_only, p1) == 0

    # One own piece: its best regular step improves distance by 1.
    alone = {(0, 0): p1}
    assert evaluate_player_progress(snapshot, alone, p1) == 1

    # An opponent's piece provides a stepping stone.
    # Our piece can jump from (0, 0) over (-1, 1) to (-2, 2).
    with_bridge = {(0, 0): p1, (-1, 1): p2}
    assert evaluate_player_progress(snapshot, with_bridge, p1) == 2

    # Evaluating must not change the supplied board.
    assert with_bridge == {(0, 0): p1, (-1, 1): p2}
