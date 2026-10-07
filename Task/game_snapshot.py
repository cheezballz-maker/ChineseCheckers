# game_snapshot.py
from types import MappingProxyType


class GameSnapshot:
    """
    A fully immutable, disconnected snapshot of game state passed to agents
    each turn. Agents read from this object and return a move — they never
    touch the live game.

    Move methods return all physically legal moves. It is the agent's
    responsibility to avoid submitting a move that exits the goal triangle —
    doing so is treated as an illegal move and forfeits the game.

    Instances should only be created via ChineseCheckersGame.snapshot(), not
    by constructing GameSnapshot directly. The factory method ensures all data
    is copied out of the live game before the snapshot is built, so there are
    no references from the snapshot back to the live game object.
    """

    def __init__(self,
                 num_players, players, current_player,
                 pieces, initial_pieces, cells, triangles,
                 goal_triangles, move_history,
                 game_over, winner, loser,
                 engine):
        """
        Construct a snapshot from pre-copied data.
        All mutable collections must already be frozen by the caller
        (ChineseCheckersGame.snapshot()) before being passed here.
        Do not call this directly — use game.snapshot() instead.
        """
        self._num_players    = num_players
        self._current_player = current_player
        self._game_over      = game_over
        self._winner         = winner
        self._loser          = loser

        self._players        = players          # tuple
        self._pieces         = pieces           # MappingProxyType
        self._initial_pieces = initial_pieces   # MappingProxyType
        self._cells          = cells            # frozenset
        self._triangles      = triangles        # tuple of frozensets
        self._goal_triangles = goal_triangles   # MappingProxyType of frozensets
        self._move_history   = move_history     # tuple of independent dicts

        # The engine is stateless (read-only board geometry), safe to share
        self._engine         = engine

    # ---------------------------
    # Properties (mirrors ChineseCheckersGame)
    # ---------------------------

    @property
    def num_players(self) -> int:
        return self._num_players

    @property
    def players(self) -> tuple:
        return self._players

    @property
    def current_player(self):
        return self._current_player

    @property
    def pieces(self) -> MappingProxyType:
        return self._pieces

    @property
    def cells(self) -> frozenset:
        return self._cells

    @property
    def triangles(self) -> tuple:
        return self._triangles

    @property
    def goal_triangles(self) -> MappingProxyType:
        return self._goal_triangles

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
        return self._move_history

    @property
    def initial_pieces(self) -> MappingProxyType:
        return self._initial_pieces

    # ---------------------------
    # Move Generation Methods
    # ---------------------------

    def get_all_legal_moves(self, player_id=None) -> list[tuple]:
        """
        Returns all physically legal (start, end) moves for player_id,
        including swap moves when eligible.
        Defaults to the current player if player_id is not provided.

        Note: includes moves that exit the goal triangle. Submitting
        such a move forfeits the match — avoiding them is the agent's
        responsibility.

        Swap moves appear as regular (start, end) tuples where end is
        occupied by an opponent piece inside player_id's goal. Agents
        may submit these normally — apply_move detects and executes
        them atomically.

        Example:
            moves = snapshot.get_all_legal_moves()
            moves = snapshot.get_all_legal_moves(some_player_id)
        """
        player_id = player_id or self._current_player
        moves     = []
        for pos, owner in self._pieces.items():
            if owner != player_id:
                continue
            for end in self._engine.get_legal_moves(pos, self._pieces):
                moves.append((pos, end))

        # Add swap moves if eligible (mirrors game.py _get_swap_moves)
        moves.extend(self._get_swap_moves(player_id))
        return moves

    def _get_swap_moves(self, player_id) -> list[tuple]:
        """
        Mirror of ChineseCheckersGame._get_swap_moves — see game.py for
        the full rule description. Agents need swap moves in their legal
        move list so they can choose to use or ignore them.
        """
        from board import DIRECTIONS
        goal_set = self._goal_triangles[player_id]

        # Condition 1: every goal cell occupied (no empty slots left)
        if any(c not in self._pieces for c in goal_set):
            return []

        # Condition 2: at least one goal cell holds an opponent piece
        opponent_in_goal = [
            pos for pos, owner in self._pieces.items()
            if pos in goal_set and owner != player_id
        ]
        if not opponent_in_goal:
            return []

        # Condition 4: no regular legal goal entry exists
        for pos, owner in self._pieces.items():
            if owner != player_id:
                continue
            for end in self._engine.get_legal_moves(pos, self._pieces):
                if end in goal_set:
                    return []

        # Condition 3: player has a piece directly adjacent to the goal edge
        adjacent_pieces = []
        for pos, owner in self._pieces.items():
            if owner != player_id or pos in goal_set:
                continue
            for dq, dr in DIRECTIONS:
                if (pos[0] + dq, pos[1] + dr) in goal_set:
                    adjacent_pieces.append(pos)
                    break

        if not adjacent_pieces:
            return []

        return [(my_piece, opp_cell)
                for my_piece in adjacent_pieces
                for opp_cell in opponent_in_goal]

    def get_legal_moves(self, pos) -> frozenset:
        """
        Returns all physically reachable destination cells for the piece at pos.

        Note: includes cells that would take the piece back out of its goal
        triangle. Submitting such a move forfeits the match.

        Example:
            destinations = snapshot.get_legal_moves((2, -3))
        """
        if pos not in self._pieces:
            return frozenset()
        return frozenset(self._engine.get_legal_moves(pos, self._pieces))

    def get_moves_with_paths(self, pos) -> dict:
        """
        Returns {destination: [pos, ..., destination]} for every physically
        reachable cell from pos, with the shortest path (fewest hops) to each.

        Note: includes goal-exiting paths. Submitting such a move forfeits
        the match.

        Example:
            paths = snapshot.get_moves_with_paths((2, -3))
            for dest, path in paths.items():
                print(f'-> {dest} in {len(path)-1} hops via {path}')
        """
        if pos not in self._pieces:
            return {}
        return self._engine.get_all_moves_with_paths(pos, self._pieces)

    def get_all_legal_moves_for(self, player_id, pieces) -> list[tuple]:
        """
        Returns all physically legal (start, end) moves for player_id on an
        ARBITRARY board state passed in as a plain dict — not necessarily the
        current position.

        This is the key method for lookahead: agents can simulate hypothetical
        moves and query what options would exist from that position.

        Note: results include goal-exiting moves. Filtering these is the
        agent's responsibility.

        Example:
            future = dict(snapshot.pieces)          # mutable plain dict copy
            future[end] = future.pop(start)         # apply a hypothetical move
            responses = snapshot.get_all_legal_moves_for(opponent, future)
        """
        return self._engine.get_all_legal_moves_for(player_id, pieces)

    def get_moves_with_paths_for(self, pos, pieces) -> dict:
        """
        Returns {destination: [pos, ..., destination]} for every physically
        reachable cell from pos, on an ARBITRARY board state passed in as a
        plain dict — not necessarily the current position.

        This is the path-aware counterpart to get_all_legal_moves_for, needed
        by agents that perform multi-ply lookahead (e.g. minimax) and must
        check intermediate hop cells — such as detecting a move that enters
        the goal mid-chain and exits again — on simulated future positions,
        not just the live board.

        Example:
            future = dict(snapshot.pieces)
            future[end] = future.pop(start)
            paths = snapshot.get_moves_with_paths_for(some_pos, future)
        """
        if pos not in pieces:
            return {}
        return self._engine.get_all_moves_with_paths(pos, pieces)

    # ---------------------------
    # Board Query Methods
    # ---------------------------

    def get_starting_positions(self, player_id) -> frozenset:
        """
        Returns the cells that player_id occupied at the start of the game.
        Useful for computing how far pieces have advanced.

        Example:
            start = snapshot.get_starting_positions(snapshot.current_player)
        """
        return frozenset(
            pos for pos, owner in self._initial_pieces.items() if owner == player_id
        )
