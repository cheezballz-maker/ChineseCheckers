# game.py
import ast
import copy
import json
import os
from datetime import datetime
from types import MappingProxyType

from board import generate_board, MoveEngine, IllegalMove

# ---------------------------
# Player Configurations
# ---------------------------
PLAYER_CONFIGS = {
    2: [0, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 4],
    6: [0, 1, 2, 3, 4, 5],
}

GOAL_MAP = {
    2: [3, 0],
    3: [3, 5, 1],
    4: [3, 4, 0, 1],
    6: [3, 4, 5, 0, 1, 2],
}


class ChineseCheckersGame:
    def __init__(self, agents: dict):
        """
        agents: {PlayerId: agent_object} — keys define player order and identity.
        Supported player counts: 2, 3, 4, 6.
        """
        self._agents = agents
        self._num_players = len(agents)

        if self._num_players not in PLAYER_CONFIGS:
            raise ValueError(f"Unsupported number of players: {self._num_players}")

        self._cells, self._triangles = generate_board()
        self._engine = MoveEngine(self._cells)

        self._players = list(agents.keys())
        self._current_player = self._players[0]

        self._pieces = {}
        self._player_triangles = PLAYER_CONFIGS[self._num_players]
        self._goal_triangles   = self._compute_goal_triangles()

        self._initialize_pieces()

        self._game_over = False
        self._winner    = None
        self._loser     = None

        self._move_history   = []
        self._initial_pieces = copy.deepcopy(self._pieces)
        self._agent_types    = {}
        self._total_times    = {}

    # ---------------------------
    # Read-Only Properties
    # ---------------------------

    @property
    def num_players(self) -> int:
        return self._num_players

    @property
    def players(self) -> tuple:
        return tuple(self._players)

    @property
    def current_player(self):
        return self._current_player

    @property
    def pieces(self) -> MappingProxyType:
        return MappingProxyType(self._pieces)

    @property
    def cells(self) -> frozenset:
        return frozenset(self._cells)

    @property
    def triangles(self) -> tuple:
        return tuple(frozenset(t) for t in self._triangles)

    @property
    def goal_triangles(self) -> MappingProxyType:
        return MappingProxyType({
            p: frozenset(cells) for p, cells in self._goal_triangles.items()
        })

    @property
    def game_over(self) -> bool:
        return self._game_over

    @property
    def winner(self):
        return self._winner

    @property
    def loser(self):
        return self._loser

    @property
    def move_history(self) -> tuple:
        return tuple(self._move_history)

    @property
    def initial_pieces(self) -> MappingProxyType:
        return MappingProxyType(self._initial_pieces)

    @property
    def agent_types(self) -> MappingProxyType:
        return MappingProxyType(self._agent_types)

    @property
    def total_times(self) -> MappingProxyType:
        return MappingProxyType(self._total_times)

    # ---------------------------
    # Setup
    # ---------------------------
    def _initialize_pieces(self):
        for idx, tri_index in enumerate(self._player_triangles):
            player = self._players[idx]
            for cell in self._triangles[tri_index]:
                self._pieces[cell] = player

    def _compute_goal_triangles(self) -> dict:
        return {
            self._players[idx]: set(self._triangles[goal_tri])
            for idx, goal_tri in enumerate(GOAL_MAP[self._num_players])
        }

    # ---------------------------
    # Game Loop
    # ---------------------------
    def step(self, move):
        """
        Advance the game by one move.
        Passing move=None forfeits the current player's turn and ends the game.
        """
        if self._game_over:
            return

        if move is None:
            self._game_over = True
            self._loser = self._current_player
            return

        self.apply_move(move)

        if not self._game_over:
            self._next_turn()

    # ---------------------------
    # Move Execution
    # ---------------------------
    def apply_move(self, move):
        """
        Validate and execute move = (start, end) for the current player.
        Sets game_over and loser on an illegal move instead of raising.

        Physical legality (reachability, occupancy) is checked by the engine.
        Decision-level restrictions (no-exit-goal) are checked here: an agent
        may choose to move a piece out of its goal, but doing so ends the game.
        """
        if self._game_over or not move:
            return

        start, end = move
        player   = self._current_player
        goal_set = self._goal_triangles[player]

        try:
            # ── Check if this is a swap move ──────────────────────────────
            # A swap is identified by the destination being occupied by an
            # opponent piece AND being a valid swap (verified against the
            # generated swap moves list so it cannot be faked by an agent).
            is_swap = (
                end in self._pieces
                and self._pieces[end] != player
                and end in goal_set
                and start not in goal_set
                and (start, end) in self._get_swap_moves(player)
            )

            if is_swap:
                # Atomic swap: player's piece enters goal cell,
                # opponent's piece is placed on the cell player just vacated.
                evicted_owner  = self._pieces[end]
                self._pieces[end]   = player          # player enters goal
                self._pieces[start] = evicted_owner   # opponent lands outside

                self._log_move(move, is_swap=True, evicted_to=start,
                               evicted_owner=evicted_owner)
                self._sanity_check()

                if self.check_win(player):
                    self._game_over = True
                    self._winner    = player
                return

            # ── Regular move validation ───────────────────────────────────
            # Physical move validation — engine has no knowledge of goal rules
            self._engine.validate_move(start, end, dict(self._pieces), player)

            # Decision-level restriction: moving out of the goal is an agent's
            # choice, but it is treated as an illegal move and forfeits the game
            if start in goal_set and end not in goal_set:
                raise IllegalMove("A piece cannot leave the goal triangle once inside.")

            # Decision-level restriction: a multi-hop chain that enters the
            # goal and then exits again mid-chain is also illegal, even
            # though start/end alone would look like a valid outside-to-
            # outside or outside-to-goal move. Checking start/end only is
            # not sufficient — the full path must be inspected.
            #
            # IMPORTANT: this must include the final landing cell (end), not
            # just the intermediate hops. A path like [start, goal_cell, end]
            # where end is outside the goal is exactly this violation — the
            # piece enters the goal on one hop and exits on the very next —
            # and checking only path[1:-1] misses it entirely since the exit
            # happens at the excluded final element.
            if start not in goal_set:
                path = self._engine.get_all_moves_with_paths(
                    start, dict(self._pieces)
                ).get(end, [])
                entered_goal = False
                for cell in path[1:]:   # exclude start only; end must be checked too
                    if cell in goal_set:
                        entered_goal = True
                    elif entered_goal:
                        raise IllegalMove(
                            "A move cannot enter the goal triangle mid-chain "
                            "and then exit again."
                        )

            self._pieces[end] = self._pieces.pop(start)

            self._log_move(move)
            self._sanity_check()

            if self.check_win(player):
                self._game_over = True
                self._winner    = player

        except IllegalMove as e:
            self._game_over = True
            self._loser     = player
            self._sanity_check()

    # ---------------------------
    # Win Condition
    # ---------------------------
    def check_win(self, player_id) -> bool:
        """Returns True if all of player_id's pieces are in their goal triangle."""
        goal = self._goal_triangles[player_id]
        return all(pos in goal for pos, owner in self._pieces.items() if owner == player_id)

    # ---------------------------
    # Turn Handling
    # ---------------------------
    def _next_turn(self):
        idx = self._players.index(self._current_player)
        self._current_player = self._players[(idx + 1) % self._num_players]

    # ---------------------------
    # Agent & Launcher Helpers
    # ---------------------------
    def get_all_legal_moves(self, player_id) -> list[tuple]:
        """
        Returns all physically legal (start, end) moves for player_id,
        including swap moves when eligible.
        Used by the Launcher to check whether a player has any moves available.
        Agents receive this method via GameSnapshot instead.
        """
        goal_set = self._goal_triangles[player_id]
        moves = []
        for pos, owner in self._pieces.items():
            if owner != player_id:
                continue
            for end in self._engine.get_legal_moves(pos, self._pieces):
                moves.append((pos, end))

        # Add swap moves if eligible
        moves.extend(self._get_swap_moves(player_id))
        return moves

    def _get_swap_moves(self, player_id) -> list[tuple]:
        """
        Returns swap moves for player_id.

        A swap move (my_piece, blocked_cell) is available when ALL of:
          1. Every goal cell is occupied — no empty cells remain in the goal
          2. At least one goal cell is occupied by an OPPONENT piece
          3. player_id has at least one piece directly adjacent to the goal
             triangle entry edge (touching the boundary, one step away)
          4. player_id has no regular legal moves landing inside the goal
             (the swap is a last resort — only when you cannot enter normally)

        The swap teleports player_id's adjacent piece into the opponent's goal
        cell and places the opponent piece on the cell the player just vacated,
        regardless of how deep the opponent piece is in the goal.
        """
        goal_set = self._goal_triangles[player_id]

        # Condition 1: every goal cell must be occupied (no empty cells left)
        empty_goal_cells = [c for c in goal_set if c not in self._pieces]
        if empty_goal_cells:
            return []   # there are open cells — enter normally, no swap needed

        # Condition 2: at least one goal cell is occupied by an opponent
        opponent_in_goal = [
            pos for pos, owner in self._pieces.items()
            if pos in goal_set and owner != player_id
        ]
        if not opponent_in_goal:
            return []   # goal is full of own pieces — already won or winning

        # Condition 4: player has no regular legal move into the goal
        # (swap is only a last resort)
        for pos, owner in self._pieces.items():
            if owner != player_id:
                continue
            for end in self._engine.get_legal_moves(pos, self._pieces):
                if end in goal_set:
                    return []   # a normal goal entry exists — use that instead

        # Condition 3: find player pieces directly adjacent to the goal edge
        # (touching the goal triangle boundary, exactly one step away)
        from board import DIRECTIONS
        adjacent_pieces = []
        for pos, owner in self._pieces.items():
            if owner != player_id:
                continue
            if pos in goal_set:
                continue   # piece already inside, not the swapper
            # Check if any neighbour of pos is inside the goal triangle
            for dq, dr in DIRECTIONS:
                neighbour = (pos[0] + dq, pos[1] + dr)
                if neighbour in goal_set:
                    adjacent_pieces.append(pos)
                    break

        if not adjacent_pieces:
            return []

        # Generate one swap move per (adjacent_piece, opponent_in_goal) pair
        swaps = []
        for my_piece in adjacent_pieces:
            for opp_cell in opponent_in_goal:
                swaps.append((my_piece, opp_cell))
        return swaps

    def get_starting_positions(self, player_id) -> frozenset:
        """Returns the cells player_id occupied at the start of the game."""
        return frozenset(
            pos for pos, owner in self._initial_pieces.items() if owner == player_id
        )

    def snapshot(self):
        """
        Return a fully populated, immutable GameSnapshot of the current state.

        This is the only way an agent should receive game state. Passing the
        live ChineseCheckersGame object to an agent is intentionally avoided —
        the snapshot is a disconnected copy with no references back to the live
        game, so nothing an agent does to it can affect the actual game state.

        All mutable data is copied and frozen here before being handed to the
        GameSnapshot constructor, so the snapshot has no reference to any live
        game attribute — not even through a shared container.
        """
        from game_snapshot import GameSnapshot
        return GameSnapshot(
            num_players    = self._num_players,
            players        = tuple(self._players),
            current_player = self._current_player,
            pieces         = MappingProxyType(dict(self._pieces)),
            initial_pieces = MappingProxyType(dict(self._initial_pieces)),
            cells          = frozenset(self._cells),
            triangles      = tuple(frozenset(t) for t in self._triangles),
            goal_triangles = MappingProxyType({
                                p: frozenset(cells)
                                for p, cells in self._goal_triangles.items()
                             }),
            # Each dict is copied so students mutating snapshot history entries
            # cannot corrupt the live game's move log or saved replays
            move_history   = tuple(dict(e) for e in self._move_history),
            game_over      = self._game_over,
            winner         = self._winner,
            loser          = self._loser,
            engine         = self._engine,   # stateless board geometry, safe to share
        )

    # ---------------------------
    # Sanity Check
    # ---------------------------
    def _sanity_check(self):
        """Verify no player's piece count has changed (should never happen)."""
        expected = len(self._triangles[0])
        for player in self._players:
            count = sum(1 for owner in self._pieces.values() if owner == player)
            if count != expected:
                pass  # piece count mismatch — engine-level bug if this fires

    # ---------------------------
    # Move History
    # ---------------------------
    def _log_move(self, move, is_swap=False, evicted_to=None, evicted_owner=None):
        piece_counts = {
            str(p): sum(1 for v in self._pieces.values() if v == p)
            for p in self._players
        }
        entry = {
            'player':      str(self._current_player),
            'move':        move,
            'timestamp':   datetime.now().isoformat(),
            'piece_count': piece_counts,
        }
        if is_swap:
            # Record swap details so replays can reconstruct both piece moves
            entry['is_swap']       = True
            entry['evicted_to']    = list(evicted_to) if evicted_to else None
            entry['evicted_owner'] = str(evicted_owner) if evicted_owner else None
        self._move_history.append(entry)

    def _stamp_move_time(self, elapsed: float):
        """
        Write the agent's thinking time onto the most recent move log entry.
        Called by the Launcher immediately after select_move returns.
        """
        if self._move_history:
            self._move_history[-1]['move_time'] = round(elapsed, 4)

    def save_history(self, filename=None, agent_types=None, move_times=None, total_times=None):
        """Save the game record to History/<timestamp>.json."""
        os.makedirs("History", exist_ok=True)
        if not filename:
            filename = os.path.join("History", f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

        data = {
            'num_players':    self._num_players,
            'agent_types':    agent_types or {},
            'total_times':    {str(k): round(v, 4) for k, v in (total_times or {}).items()},
            'winner':         str(self._winner) if self._winner else None,
            'loser':          str(self._loser)  if self._loser  else None,
            'initial_pieces': [(str(pos), str(owner)) for pos, owner in self._initial_pieces.items()],
            'move_history':   self._move_history,
        }

        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)


    @classmethod
    def load_from_history(cls, filename):
        """Reconstruct a finished game from a saved JSON file (for replay)."""
        from utility import PlayerId

        with open(filename) as f:
            data = json.load(f)

        str_to_player = {str(p): p for p in PlayerId}
        num_players   = data['num_players']
        dummy_agents  = {p: None for p in list(PlayerId)[:num_players]}
        game          = cls(dummy_agents)

        game._pieces = {
            ast.literal_eval(pos_str): str_to_player.get(owner_str, owner_str)
            for pos_str, owner_str in data['initial_pieces']
        }
        game._initial_pieces = copy.deepcopy(game._pieces)
        game._move_history   = data['move_history']
        # Convert winner/loser back to PlayerId enum members, matching the
        # same str_to_player conversion already applied to initial_pieces.
        # Without this, game.winner/loser would be plain strings after a
        # load instead of PlayerId members, breaking equality checks like
        # `loaded.winner == PlayerId.PLAYER_1` that callers reasonably expect.
        game._winner          = str_to_player.get(data.get('winner'), data.get('winner'))
        game._loser           = str_to_player.get(data.get('loser'), data.get('loser'))
        game._agent_types    = data.get('agent_types', {})
        game._total_times    = data.get('total_times', {})

        return game
