import sys
from pathlib import Path
from itertools import permutations
from random import Random
from types import SimpleNamespace
from unittest.mock import patch

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "Task"))

import Tutorial.GameAgent as tutorial_agent
import Task.GameAgent as task_agent
from utility import PlayerId
from game import ChineseCheckersGame


def check_goal_assignment(agent_module):
    p1 = PlayerId.PLAYER_1
    p2 = PlayerId.PLAYER_2
    goal = frozenset({(0, 0), (3, 0)})
    pieces = {(0, 1): p1, (0, -1): p1, (2, 0): p2}
    before = dict(pieces)
    # Both pieces are near the same target, but only one can be assigned to it.
    assert agent_module.evaluate_player_pieces(pieces, p1, goal) == -10
    assert pieces == before
    assert agent_module.evaluate_player_pieces({}, p1, goal) == 0
    assert agent_module.evaluate_player_pieces({cell: p1 for cell in goal}, p1, goal) == 0

    rng = Random(42)
    cells = [(q, r) for q in range(-2, 3) for r in range(-2, 3)]
    for count in range(1, 5):
        for trial in range(8):
            player_pieces = tuple(rng.sample(cells, count))
            goal_cells = tuple(rng.sample(cells, 4))
            expected = min(
                sum(agent_module.hex_dist(piece, target)**2
                    for piece, target in zip(player_pieces, targets))
                for targets in permutations(goal_cells, count)
            )
            assert agent_module.goal_assignment_cost(player_pieces, goal_cells) == expected


def check_selection(agent_module):
    p1 = PlayerId.PLAYER_1
    p2 = PlayerId.PLAYER_2
    pieces = {(0, 0): p1, (4, 0): p2}
    moves = [((0, 0), (1, 0)), ((0, 0), (2, 0))]
    game = SimpleNamespace(pieces=pieces, players=(p1, p2),
                           goal_triangles={p1: frozenset({(3, 0)}), p2: frozenset({(-3, 0)})})
    keys = [agent_module.position_key(agent_module.simulate_move(pieces, move)) for move in moves]

    # Helping the opponent hurts; harming their opportunities helps.
    for own_scores, opponent_scores, expected in [
        ([5, 3], [4, -2], 1),
        ([5, 3], [0, 0], 0),
        ([3, 3], [0, 2], 0),
        ([3, 3], [0, 0], 0),
    ]:
        scores = dict(zip(keys, zip(own_scores, opponent_scores)))
        def evaluate_board(game, board, player, mobility_weight):
            score = scores.get(agent_module.position_key(board), (0, 0))
            return score[0 if player == p1 else 1]
        agent = agent_module.GameAgent()
        with (
            patch.object(agent_module, 'get_playable_moves', return_value=moves),
            patch.object(agent_module, 'evaluate_player_board', side_effect=evaluate_board),
        ):
            assert agent.select_move(game, p1) == moves[expected]
        assert agent.positions_count == {keys[expected]: 1}
        assert len(agent.recent_positions) == 1
        assert pieces == {(0, 0): p1, (4, 0): p2}

    # Own-position memory applies even without a matching whole-board key.
    agent = agent_module.GameAgent()
    agent.recent_positions = [(p1, frozenset({(1, 0)}))]
    with (
        patch.object(agent_module, 'get_playable_moves', return_value=moves),
        patch.object(agent_module, 'evaluate_player_board', return_value=0),
    ):
        assert agent.select_move(game, p1) == moves[1]

    # A win takes priority even when it repeats an own-piece arrangement.
    game.goal_triangles[p1] = frozenset({(1, 0)})
    with (
        patch.object(agent_module, 'get_playable_moves', return_value=moves),
        patch.object(agent_module, 'evaluate_player_board', return_value=0),
    ):
        assert agent.select_move(game, p1) == moves[0]

    before_counts = dict(agent.positions_count)
    before_recent = list(agent.recent_positions)
    with patch.object(agent_module, 'get_playable_moves', return_value=[]):
        assert agent.select_move(game, p1) is None
    assert agent.positions_count == before_counts
    assert agent.recent_positions == before_recent

    with (
        patch.object(agent_module, 'get_playable_moves', return_value=moves[:1]),
        patch.object(agent_module, 'evaluate_player_board', return_value=0),
    ):
        for turn in range(20):
            assert agent.select_move(game, p1) == moves[0]
    assert len(agent.recent_positions) == 12
    assert agent_module.GameAgent().recent_positions == []


def check_mobility_weight(agent_module):
    p1 = PlayerId.PLAYER_1
    goal = frozenset({(0, 0), (1, 0)})
    game = SimpleNamespace(goal_triangles={p1: goal})
    with (
        patch.object(agent_module, 'evaluate_player_pieces', return_value=-10),
        patch.object(agent_module, 'evaluate_player_progress', return_value=8),
    ):
        assert agent_module.evaluate_player_board(game, {(2, 0): p1, (3, 0): p1}, p1, 0.25) == -8
        assert agent_module.evaluate_player_board(game, {(0, 0): p1, (3, 0): p1}, p1, 0.25) == -9
        assert agent_module.evaluate_player_board(game, {(0, 0): p1, (1, 0): p1}, p1, 0.25) == -10


def check_real_snapshot(agent_module):
    p1 = PlayerId.PLAYER_1
    p2 = PlayerId.PLAYER_2
    agents = {p1: agent_module.GameAgent(), p2: agent_module.GameAgent()}
    game = ChineseCheckersGame(agents)
    snapshot = game.snapshot()
    before = dict(snapshot.pieces)
    move = agents[p1].select_move(snapshot, p1)
    assert move in agent_module.get_playable_moves(snapshot, p1)
    assert dict(snapshot.pieces) == before
    game.step(move)
    assert game.loser is None


if __name__ == "__main__":
    for agent_module in (tutorial_agent, task_agent):
        check_goal_assignment(agent_module)
        check_selection(agent_module)
        check_mobility_weight(agent_module)
        check_real_snapshot(agent_module)
        print(agent_module.__name__, 'strategy checks passed')
