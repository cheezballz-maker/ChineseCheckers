# board.py
from collections import deque

# Axial hex directions
DIRECTIONS = [
    (1, 0), (1, -1), (0, -1),
    (-1, 0), (-1, 1), (0, 1)
]

# ---------------------------
# Board Generation
# ---------------------------
def generate_board(radius=4):
    """
    Returns (cells, triangles):
      cells     - set of all (q, r) positions on the full star board
      triangles - list of 6 sets, each holding the 10 cells of one corner triangle,
                  indexed 0-5 clockwise from the top-right
    """
    cells = set()

    # Center hex
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            if max(abs(q), abs(r), abs(-q - r)) <= radius:
                cells.add((q, r))

    # Base triangle anchored just outside the hex, rotated 6 times
    base = set()
    for i in range(1, 5):
        for j in range(i):
            base.add((5 + j - i, -5 - j))

    def rot60(q, r):
        return -r, q + r

    triangles = []
    tri = base
    for _ in range(6):
        triangles.append(tri)
        cells |= tri
        tri = {rot60(q, r) for q, r in tri}

    return cells, triangles


# ---------------------------
# Exceptions
# ---------------------------
class IllegalMove(Exception):
    pass


# ---------------------------
# Move Engine
# ---------------------------
class MoveEngine:
    """
    Computes physically legal moves based purely on board geometry and piece
    positions. Strategy-level restrictions (such as whether a piece should be
    allowed to leave its goal triangle) are the responsibility of the caller.
    """

    def __init__(self, cells):
        # Stored privately and exposed only via a read-only property so this
        # cannot be mutated OR reassigned through any reference to the engine
        # — including the engine reference shared with GameSnapshot. A plain
        # mutable attribute would let a malicious agent corrupt the live
        # game's board geometry via snap._engine.cells.add(...) or outright
        # reassignment (snap._engine.cells = {...}).
        self._cells = frozenset(cells)

    @property
    def cells(self) -> frozenset:
        return self._cells

    def get_adjacent(self, pos, pieces) -> list[tuple[int, int]]:
        """One-step moves to empty board cells."""
        q, r = pos
        return [
            (q + dq, r + dr)
            for dq, dr in DIRECTIONS
            if (q + dq, r + dr) in self.cells and (q + dq, r + dr) not in pieces
        ]

    def get_jumps(self, start, pieces) -> set[tuple[int, int]]:
        """
        Returns the set of all cells reachable via chained jumps from start.
        Purely geometric — no strategy-level restrictions applied.
        """
        visited = set()
        results = set()

        def dfs(pos):
            for dq, dr in DIRECTIONS:
                mid  = (pos[0] + dq,     pos[1] + dr)
                jump = (pos[0] + 2 * dq, pos[1] + 2 * dr)
                if (mid in pieces
                        and jump in self.cells
                        and jump not in pieces
                        and jump not in visited):
                    visited.add(jump)
                    results.add(jump)
                    dfs(jump)

        dfs(start)
        return results

    def get_legal_moves(self, pos, pieces) -> set[tuple[int, int]]:
        """
        Returns all physically reachable destination cells for the piece at pos.
        Returns an empty set if pos holds no piece.
        """
        if pos not in pieces:
            return set()
        return set(self.get_adjacent(pos, pieces)) | self.get_jumps(pos, pieces)

    def get_all_moves_with_paths(self, pos, pieces) -> dict:
        """
        Returns {destination: [pos, ..., destination]} for every physically
        reachable cell from pos, with the shortest path (fewest hops) to each.

        Adjacent moves produce a two-cell path [pos, dest].
        Jump moves use BFS so the first time any cell is reached it is
        guaranteed to be via the minimum number of jumps.
        """
        if pos not in pieces:
            return {}

        moves = {}

        # Single-step adjacent
        for dest in self.get_adjacent(pos, pieces):
            moves[dest] = [pos, dest]

        # Multi-jump BFS: queue holds (current_cell, path_so_far)
        queue   = deque([(pos, [pos])])
        visited = {pos}

        while queue:
            current, path = queue.popleft()
            for dq, dr in DIRECTIONS:
                mid  = (current[0] + dq,     current[1] + dr)
                jump = (current[0] + 2 * dq, current[1] + 2 * dr)
                if (mid in pieces
                        and jump in self.cells
                        and jump not in pieces
                        and jump not in visited):
                    visited.add(jump)
                    new_path = path + [jump]
                    moves[jump] = new_path
                    queue.append((jump, new_path))

        return moves

    def get_all_legal_moves_for(self, player_id, pieces) -> list[tuple]:
        """
        Returns all physically legal (start, end) moves for player_id on an
        arbitrary board state. No strategy-level restrictions are applied.
        """
        moves = []
        for pos, owner in pieces.items():
            if owner != player_id:
                continue
            for end in self.get_legal_moves(pos, pieces):
                moves.append((pos, end))
        return moves

    def validate_move(self, start, end, pieces, player_id):
        """
        Raises IllegalMove if the move is physically invalid; returns normally
        otherwise. Checks: piece exists, belongs to player, destination is on
        the board, destination is empty, destination is reachable.

        Strategy-level legality (e.g. no-exit-goal) is enforced by the game,
        not here.
        """
        if start not in pieces:
            raise IllegalMove(f"No piece at {start}.")
        if pieces[start] != player_id:
            raise IllegalMove(f"Piece at {start} belongs to another player.")
        if end not in self.cells:
            raise IllegalMove(f"Destination {end} is outside the board.")
        if end in pieces:
            raise IllegalMove(f"Destination {end} is occupied.")
        if end not in self.get_legal_moves(start, pieces):
            raise IllegalMove(f"No legal path from {start} to {end}.")
