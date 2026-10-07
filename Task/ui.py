import math
import tkinter as tk
from utility import PLAYER_COLOR_MAP

WIDTH = 1080        # 1080 # extra 280px on the right for the player info panel
HEIGHT = 700        # 700
HEX_SIZE = 16       # 16
PANEL_X = 810       # left edge of player info panel
CELL_SIZE = 30      # 30


# -----------------------------
# Geometry helpers
# -----------------------------
def axial_to_pixel(q, r):
    x = WIDTH // 2 + CELL_SIZE * (q + r / 2)
    y = HEIGHT // 2 + CELL_SIZE * (math.sqrt(3)/2 * r)
    return x, y


def hexagon_points(cx, cy, size):
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.extend([
            cx + size * math.cos(angle),
            cy + size * math.sin(angle)
        ])
    return pts

def lighten_color(color, factor=0.5):
    # COLORS_RGB = {
    #     "red": (255, 0, 0),
    #     "blue": (0, 0, 255),
    #     "green": (0, 200, 0),
    #     "yellow": (255, 255, 0),
    #     "purple": (160, 0, 160),
    #     "orange": (255, 140, 0),
    # }

    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    # Support both named + hex colors
    # if color in COLORS_RGB:
    #     r, g, b = COLORS_RGB[color]
    # else:
    r, g, b = hex_to_rgb(color)

    # Lighten toward white
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)

    return f'#{r:02x}{g:02x}{b:02x}'





# -----------------------------
# Base UI
# -----------------------------
SLIDER_HEIGHT = 40   # extra window height for the speed control

def agent_type_label(agent):
    """
    Return a short human-readable type string for any agent.

    Derived automatically from the class name by inserting spaces before
    capital letters — e.g. "GameAgent" -> "Game Agent", "AggressiveAgent" ->
    "Aggressive Agent". This means any agent (starter-pack or grading-server)
    gets a sensible label without needing to be named explicitly here, and
    new agents added later don't require updating this function.
    """
    if agent is None:
        return "?"
    name = type(agent).__name__
    if name == "HumanAgent":
        return "Human"
    if name == "RandomAgent":
        return "Random"
    # Insert a space before each capital letter that follows a lowercase
    # letter, e.g. "GameAgent" -> "Game Agent"
    import re
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)


class BaseUI:
    def __init__(self, game, agents=None):
        self.game   = game
        self.agents = agents or {}   # {PlayerId: agent}
        self.root = tk.Tk()
        self.root.title("Chinese Checkers")
        self.root.resizable(False, False)

        # Guard flag set to True when the window is closing — checked by
        # all root.after() callbacks so they don't fire on a dead window
        self._closing = False
        self._tick_job = None   # after() job id for tick_move_timer; cancelled on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Per-player timing state
        import time as _time
        self._time        = _time
        self._move_start  = {}   # {PlayerId: float timestamp}
        self._move_times  = {}   # {PlayerId: float seconds (current move)}
        self._total_times = {}   # {PlayerId: float seconds (total)}
        for pid in game.players:
            self._move_times[pid]  = 0.0
            self._total_times[pid] = 0.0

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT, bg="lightblue")
        self.canvas.pack()

        # Speed control — sits below the canvas, visible in all UI modes
        ctrl_frame = tk.Frame(self.root, bg="#d0d0d0", height=SLIDER_HEIGHT)
        ctrl_frame.pack(fill=tk.X)

        tk.Label(
            ctrl_frame, text="Hop Speed:",
            bg="#d0d0d0", font=("Arial", 10, "bold")
        ).pack(side=tk.LEFT, padx=(10, 4), pady=6)

        # _hop_speed: Scale widget read directly (avoids tk.IntVar cross-root issues)
        self._speed_slider = tk.Scale(
            ctrl_frame,
            from_=1, to=10,
            orient=tk.HORIZONTAL,
            length=160,
            showvalue=True,
            bg="#d0d0d0",
            highlightthickness=0,
            font=("Arial", 9),
        )
        self._speed_slider.set(5)   # default: mid-range
        self._speed_slider.pack(side=tk.LEFT, pady=4)

        tk.Label(
            ctrl_frame, text="(Slow ←→ Fast)",
            bg="#d0d0d0", font=("Arial", 9), fg="#555555"
        ).pack(side=tk.LEFT, padx=(4, 0))

    # ---------------------------
    # Move timing
    # ---------------------------
    def start_move_timer(self, player):
        """Call when a player's turn begins."""
        self._move_start[player] = self._time.time()
        self._move_times[player] = 0.0

    def stop_move_timer(self, player):
        """Call when a player's turn ends. Returns elapsed seconds."""
        if player in self._move_start:
            elapsed = self._time.time() - self._move_start.pop(player)
            self._move_times[player]  = elapsed
            self._total_times[player] = self._total_times.get(player, 0.0) + elapsed
            return elapsed
        return 0.0

    def tick_move_timer(self):
        """Update current move time for the active player and redraw panel."""
        for pid, start in self._move_start.items():
            self._move_times[pid] = self._time.time() - start
        if not self._closing:
            self.draw_board()
            self._tick_job = self.root.after(500, self.tick_move_timer)

    def get_game_time(self) -> float:
        """
        Total game time, defined as the sum of every player's recorded move
        time across the whole game (self._total_times). This reflects actual
        agent thinking/decision time, not wall-clock time — so it's stable,
        reproducible, and meaningful for comparing agent performance, since
        it isn't affected by animation speed, UI redraw lag, or how long a
        human happens to leave the window open.
        """
        return sum(self._total_times.values())

    # ---------------------------
    # Player info panel
    # ---------------------------
    def draw_player_panel(self):
        """
        Draw a player info panel in the right margin showing:
          • Colour swatch + player number + agent type
          • Current move time
          • Total time used
          • Total game time — shown only once the game has ended, since it's
            a final summary stat (sum of all players' move times) rather than
            something meaningful to watch tick during play
        Active player row is highlighted.
        """
        px      = PANEL_X
        py      = 20
        row_h   = 28
        label_w = 152   # width reserved for "P# Agent Name" before time columns
        move_w  = 59    # width of the Move column
        total_w = 59    # width of the Total column

        # Game Time row only takes up space once the game has actually ended
        game_time_row_h = 20 if self.game.game_over else 0
        panel_h = len(self.game.players) * row_h + 38 + game_time_row_h

        # Panel background
        self.canvas.create_rectangle(
            px - 8, py - 10,
            WIDTH - 4, py + panel_h,
            fill="#e8eaf0", outline="#aaaacc", width=1,
        )

        # Column headers — centered over their column width so they align
        # with the centered time values drawn below
        header_specs = (
            ("Player", 0,               "nw"),
            ("Move",   label_w + move_w // 2,  "n"),
            ("Total",  label_w + move_w + total_w // 2, "n"),
        )
        for label, ox, anchor in header_specs:
            self.canvas.create_text(
                px + ox, py,
                text=label, anchor=anchor,
                font=("Courier", 8, "bold"), fill="#444466",
            )
        py += 16

        # One row per player
        for pid in self.game.players:
            is_active = (pid == self.game.current_player and not self.game.game_over)
            mid = py + row_h // 2   # vertical centre of this row

            # Highlight — symmetrical around mid
            if is_active:
                self.canvas.create_rectangle(
                    px - 6, mid - row_h // 2,
                    WIDTH - 6, mid + row_h // 2,
                    fill="#d0d8ff", outline="",
                )

            # Colour swatch — centred vertically
            swatch_h = 12
            self.canvas.create_rectangle(
                px - 4, mid - swatch_h // 2,
                px + 8,  mid + swatch_h // 2,
                fill=PLAYER_COLOR_MAP[pid], outline="",
            )

            # Player number + agent type — live agents dict takes priority,
            # fall back to types restored from the save file during replay.
            # The raw saved class name is formatted the same way as
            # agent_type_label so replays show "Greedy Agent" etc. without
            # needing a duplicate hardcoded list here.
            agent_lbl = agent_type_label(self.agents.get(pid))
            if agent_lbl == "?" and hasattr(self, '_saved_agent_types'):
                raw = self._saved_agent_types.get(str(pid), "")
                if raw == "HumanAgent":
                    agent_lbl = "Human"
                elif raw == "RandomAgent":
                    agent_lbl = "Random"
                elif raw:
                    import re
                    agent_lbl = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw)
                else:
                    agent_lbl = "?"
            self.canvas.create_text(
                px + 12, mid,
                text=f"P{pid.value}  {agent_lbl}",
                anchor="w",
                font=("Courier", 9, "bold"),
                fill="#111133",
            )

            # Current move time — vertically centred, horizontally centred
            # under the "Move" header
            cur = self._move_times.get(pid, 0.0)
            self.canvas.create_text(
                px + label_w + move_w // 2, mid,
                text=f"{cur:.3f}s",
                anchor="center",
                font=("Courier", 9),
                fill="#003399" if is_active else "#222244",
            )

            # Total time — vertically centred, horizontally centred under
            # the "Total" header
            tot = self._total_times.get(pid, 0.0)
            self.canvas.create_text(
                px + label_w + move_w + total_w // 2, mid,
                text=f"{tot:.3f}s",
                anchor="center",
                font=("Courier", 9),
                fill="#222244",
            )

            py += row_h

        # Game time — sum of every player's total move time. Only drawn
        # once the game is over; during live play this row is simply
        # omitted rather than showing a constantly-changing number that
        # isn't meaningful until the game has actually finished.
        if self.game.game_over:
            # Thin separator line above the final summary stat
            self.canvas.create_line(
                px - 6, py + 4,
                WIDTH - 6, py + 4,
                fill="#aaaacc", width=1,
            )
            game_time = self.get_game_time()
            self.canvas.create_text(
                px, py + 8,
                text=f"Game Time: {game_time:.2f}s",
                anchor="nw",
                font=("Courier", 9, "bold"), fill="#111133",
            )

    def _on_close(self):
        """Called when the user closes the window. Stops all pending callbacks."""
        self._closing = True
        if self._tick_job is not None:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None
        self.root.destroy()

    def refresh(self):
        self.draw_board()
        self.root.update_idletasks()
        self.root.update()

    def draw_board(self):
        pass


# -----------------------------
# Viewer UI
# Handles passive board display for AI-vs-AI games, and replay controls
# for previously saved games. ReplayUI has been merged here since it only
# needed draw_board() and key bindings — no click/hover machinery required.
# -----------------------------
class ViewerUI(BaseUI):
    def __init__(self, game, agents=None):
        super().__init__(game, agents=agents)
        self.replay_index  = 0
        self.is_replaying  = False
        # Frozen at construction time — True only if loaded from a saved game
        self._is_replay_mode = bool(self.game.move_history)

        # Replay key bindings — only active when playing back a saved game.
        if self._is_replay_mode:
            self.root.bind("<space>", self.toggle_replay)
            self.root.bind("<Right>", self.step_replay)
            self.root.bind("<Left>", self.step_replay_back)

        # Goal triangle tint colors (lightened player colors)
        self.goal_colors = {}
        for idx in range(self.game.num_players):
            pid = self.game.players[idx]
            self.goal_colors[idx] = lighten_color(PLAYER_COLOR_MAP[pid], 0.6)

        # Animation state (shared with InteractiveUI)
        self.animating        = False
        self._anim_origin     = None
        self.anim_piece_pos   = None
        self.anim_piece_owner = None
        self._draw_highlights = None

        # Debug state
        self.debug = False
        self.debug_items = []
        self.debug_label_id = None

        self.root.bind("<Key-d>", self.toggle_debug)
        self.root.bind("<Key-D>", self.toggle_debug)

        # Restore agent types and total times saved in the history file (replay mode)
        if hasattr(self.game, 'agent_types') and self.game.agent_types:
            self._saved_agent_types = self.game.agent_types   # {str(PlayerId): class_name}
        else:
            self._saved_agent_types = {}

        if hasattr(self.game, 'total_times') and self.game.total_times:
            from utility import PlayerId
            str_to_pid = {str(p): p for p in PlayerId}
            for k, v in self.game.total_times.items():
                pid = str_to_pid.get(k)
                if pid:
                    self._total_times[pid] = v

        # Draw the initial board so the canvas isn't blank on open
        self.draw_board()

    def draw_board(self):
        self.canvas.delete("all")

        for cell in self.game.cells:
            x, y = axial_to_pixel(*cell)
            pts = hexagon_points(x, y, HEX_SIZE)

            # Goal triangle tint
            color = "lightgray"
            for pid, goal_cells in self.game.goal_triangles.items():
                if cell in goal_cells:
                    color = self.goal_colors[pid.value - 1]
                    break

            # Piece overrides tint
            if cell in self.game.pieces:
                color = PLAYER_COLOR_MAP[self.game.pieces[cell]]

            self.canvas.create_polygon(pts, fill=color, outline="black")

        # Turn label — matches InteractiveUI style
        pid = self.game.current_player
        self.canvas.create_text(
            100, 30,
            text=f"Player {pid.value}'s Turn",
            fill=PLAYER_COLOR_MAP[pid],
            font=("Arial", 16, "bold"),
        )

        if self._draw_highlights:
            self._draw_highlights()

        self.draw_player_panel()
        self.draw_debug_label()
        if self.debug:
            self.draw_debug_overlay()

    # -----------------------------
    # Replay controls
    # -----------------------------
    def _apply_replay_move(self, move):
        """
        Lightweight move for replay: moves the piece and advances the turn.
        Skips validation, logging, sanity checks, and win detection so that
        a game_over flag in the history doesn't halt playback mid-replay.
        Also reads move_time from the history entry (if present) so the
        player panel can show how long each move took during replay.

        Swap moves are handled atomically: the player's piece enters the goal
        cell AND the evicted opponent piece is placed on evicted_to. Without
        both steps, the swap appears as a teleport with the evicted piece
        vanishing from the board entirely.
        """
        start, end = tuple(move[0]), tuple(move[1])

        # Read the full history entry for this move
        entry_idx = self.replay_index - 1
        entry = {}
        if 0 <= entry_idx < len(self.game.move_history):
            entry = self.game.move_history[entry_idx]

        if entry.get('is_swap'):
            # Swap: player's piece goes to end, evicted opponent piece goes
            # to evicted_to (which is the cell the player's piece came from)
            evicted_to    = tuple(entry['evicted_to'])
            evicted_owner_str = entry.get('evicted_owner', '')
            from utility import PlayerId
            str_to_pid = {str(p): p for p in PlayerId}
            evicted_owner = str_to_pid.get(evicted_owner_str)

            # Move the player's piece to end (the goal cell)
            if start in self.game._pieces:
                player_owner = self.game._pieces.pop(start)
                self.game._pieces[end] = player_owner

            # Place the evicted piece on evicted_to (the player's former cell)
            if evicted_owner:
                self.game._pieces.pop(evicted_to, None)  # clear if anything there
                self.game._pieces[evicted_to] = evicted_owner
        else:
            # Normal move
            if start in self.game._pieces:
                owner = self.game._pieces.pop(start)
                self.game._pieces[end] = owner

        # Update move timing for the player panel
        move_time = entry.get('move_time', 0.0)
        from utility import PlayerId
        str_to_pid = {str(p): p for p in PlayerId}
        pid = str_to_pid.get(entry.get('player', ''))
        if pid:
            self._move_times[pid] = move_time

        self.game._next_turn()

    def _reset_to_start(self):
        """Reset pieces and turn order to the beginning of the recorded game."""
        self.game._pieces = {
            (tuple(pos) if not isinstance(pos, tuple) else pos): owner
            for pos, owner in self.game._initial_pieces.items()
        }
        self.game._game_over = False
        self.game._winner = None
        self.game._current_player = self.game._players[0]
        self.replay_index = 0

    def _draw_replay_highlights(self, path):
        """
        Draw the path line and start/end hex rings on top of the current board.
        path is a list of (q, r) tuples from start to end.
        """
        # Dashed line through every waypoint
        for i in range(len(path) - 1):
            x1, y1 = axial_to_pixel(*path[i])
            x2, y2 = axial_to_pixel(*path[i + 1])
            self.canvas.create_line(
                x1, y1, x2, y2,
                fill="white", width=2, dash=(4, 3), smooth=True,
            )
        # Gold ring on start, white ring on destination
        for cell, ring_color in ((path[0], "gold"), (path[-1], "white")):
            cx, cy = axial_to_pixel(*cell)
            pts = hexagon_points(cx, cy, HEX_SIZE)
            self.canvas.create_polygon(pts, fill="", outline=ring_color, width=3)

    def _get_move_path(self, move):
        """
        Reconstruct the full cell-by-cell path for a move using the MoveEngine.
        Falls back to [start, end] if no jump path is found (adjacent move).
        """
        start = tuple(move[0])
        end   = tuple(move[1])

        paths = self.game._engine.get_all_moves_with_paths(start, self.game._pieces)
        if end in paths:
            return [tuple(c) for c in paths[end]]

        # Adjacent (non-jump) move — straight line is correct
        return [start, end]

    def play_animated_move(self, move, callback=None):
        """
        Animate a live game move with path highlights and hop animation.
        Path is resolved from the current board state BEFORE game.step() is
        called — the Driver calls game.step() inside the callback.
        """
        if not move:
            if callback:
                callback()
            return

        start, end = move
        path = self._get_move_path([start, end])

        def on_complete():
            if callback:
                self.root.after(50, callback)

        self.animate_move_with_callback(path, callback=on_complete)

    def _execute_replay_move(self, move, then=None):
        """
        Animate the piece along the full hop path, then apply the move and
        call `then()`. Uses the shared animate_move_with_callback machinery.
        """
        path = self._get_move_path(move)

        def on_complete():
            self._apply_replay_move(move)
            self.draw_board()
            if then:
                then()

        self.animate_move_with_callback(path, callback=on_complete)

    def toggle_replay(self, event=None):
        self.is_replaying = not self.is_replaying
        if self.is_replaying:
            self.root.after(300, self.run_replay)

    def run_replay(self):
        if not self.is_replaying or self.replay_index >= len(self.game.move_history):
            self.is_replaying = False
            self.draw_board()
            return

        move = self.game.move_history[self.replay_index]['move']
        self.replay_index += 1

        def next_move():
            if self.is_replaying and not self._closing:
                self.root.after(300, self.run_replay)

        self._execute_replay_move(move, then=next_move)

    def step_replay(self, event=None):
        """Advance one move forward. Disabled during auto-playback."""
        if self.is_replaying:
            return
        if self.replay_index < len(self.game.move_history):
            move = self.game.move_history[self.replay_index]['move']
            self.replay_index += 1
            self._execute_replay_move(move)

    def step_replay_back(self, event=None):
        """Rewind one move. Disabled during auto-playback."""
        if self.is_replaying:
            return
        if self.replay_index <= 0:
            return

        target = self.replay_index - 1
        self._reset_to_start()

        for i in range(target):
            self.replay_index += 1   # increment BEFORE apply, matching run_replay/step_replay
            self._apply_replay_move(self.game.move_history[i]['move'])

        self.draw_board()


    # -----------------------------
    # Animation (shared with InteractiveUI)
    # -----------------------------
    def animate_move_with_callback(self, path, callback=None):
        """
        Hop-by-hop animation: previews the path with highlights, then slides
        the piece cell-by-cell. Shared by ViewerUI (replay) and InteractiveUI.

        IMPORTANT: Does NOT modify game.pieces — caller does that in callback.
        """
        if not path or len(path) < 2:
            self.animating = False
            if callback:
                self.root.after(10, callback)
            return

        piece_owner = self.game.pieces.get(tuple(path[0]))
        if not piece_owner:
            self.animating = False
            if callback:
                callback()
            return

        self.animating        = True
        self._anim_origin     = tuple(path[0])
        self.anim_piece_pos   = tuple(path[0])
        self.anim_piece_owner = piece_owner

        # Scale hop speed from slider (1=slow … 10=fast)
        speed      = self._speed_slider.get()        # 1–10
        HOP_FRAMES = max(4, 20 - speed * 2)          # 18 (slow) → 4 (fast)
        HOP_MS     = 16                               # fixed ~60 FPS frame rate
        PAUSE_MS   = max(30, 220 - speed * 20)       # 200ms (slow) → 30ms (fast)
        PREVIEW_MS = 500                              # preview pause always the same
        base_r     = HEX_SIZE * 0.85
        color      = PLAYER_COLOR_MAP[piece_owner]
        path       = [tuple(c) for c in path]
        start_cell = path[0]
        end_cell   = path[-1]

        def draw_highlights():
            for i in range(len(path) - 1):
                x1, y1 = axial_to_pixel(*path[i])
                x2, y2 = axial_to_pixel(*path[i + 1])
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill="white", width=2, dash=(4, 3), smooth=True,
                )
            for cell, ring_color in ((start_cell, "gold"), (end_cell, "white")):
                cx, cy = axial_to_pixel(*cell)
                pts = hexagon_points(cx, cy, HEX_SIZE)
                self.canvas.create_polygon(pts, fill="", outline=ring_color, width=3)

        self._draw_highlights = draw_highlights

        def draw_piece_at(cell):
            self.draw_board()
            cx, cy = axial_to_pixel(*cell)
            self.canvas.create_oval(
                cx - base_r, cy - base_r,
                cx + base_r, cy + base_r,
                fill=color, outline="black", width=2,
            )

        def hop(seg, frame):
            # Bail out silently if the window has been closed
            if self._closing:
                return

            src = path[seg]
            dst = path[seg + 1]
            x1, y1 = axial_to_pixel(*src)
            x2, y2 = axial_to_pixel(*dst)

            if frame < HOP_FRAMES:
                t = frame / HOP_FRAMES
                cx = x1 + (x2 - x1) * t
                cy = y1 + (y2 - y1) * t
                self.draw_board()
                self.canvas.create_oval(
                    cx - base_r, cy - base_r,
                    cx + base_r, cy + base_r,
                    fill=color, outline="black", width=2,
                )
                self.root.after(HOP_MS, hop, seg, frame + 1)
            else:
                self.anim_piece_pos = dst
                draw_piece_at(dst)
                next_seg = seg + 1
                if next_seg < len(path) - 1:
                    self.root.after(PAUSE_MS, hop, next_seg, 0)
                else:
                    self.animating        = False
                    self.anim_piece_pos   = None
                    self.anim_piece_owner = None
                    self._anim_origin     = None
                    self._draw_highlights = None
                    self.draw_board()
                    if callback:
                        self.root.after(50, callback)

        self.draw_board()
        if not self._closing:
            self.root.after(PREVIEW_MS, lambda: hop(0, 0))

    def toggle_debug(self, event=None):
        self.debug = not self.debug
        print(f"Debug mode: {'ON' if self.debug else 'OFF'}")
        self.draw_board()

    def draw_debug_overlay(self):
        """Draw axial coordinates on every cell."""
        self.debug_items.clear()

        for cell in self.game.cells:
            cx, cy = axial_to_pixel(*cell)
            text_color = "white" if cell in self.game.pieces else "black"
            tid = self.canvas.create_text(
                cx, cy,
                text=f"{cell[0]},{cell[1]}",
                fill=text_color,
                font=("Arial", 7, "bold")
            )
            self.debug_items.append(tid)

    def draw_debug_label(self):
        if self.debug_label_id:
            for tid in self.debug_label_id:
                self.canvas.delete(tid)
            self.debug_label_id = []

        LEFT_X = WIDTH - 220
        # Use the flag frozen at construction time so live-game history
        # accumulating mid-game doesn't incorrectly show replay controls
        is_replay = getattr(self, '_is_replay_mode', False)
        ids = []
        y = HEIGHT - 10

        # Debug line — always shown
        tid = self.canvas.create_text(
            LEFT_X, y,
            text=f"Debug {'ON' if self.debug else 'OFF'}  D",
            anchor="sw",
            fill="black",
            font=("Arial", 10, "bold"),
        )
        ids.append(tid)
        y -= 18

        # Replay controls — only shown when a saved game is loaded
        if is_replay:
            for text in ("Step backward  ←", "Step forward  →", "Play / Pause  Space"):
                tid = self.canvas.create_text(
                    LEFT_X, y,
                    text=text,
                    anchor="sw",
                    fill="#444444",
                    font=("Arial", 10, "bold"),
                )
                ids.append(tid)
                y -= 18

            # Status / move counter at top of block
            status     = "▶ Playing" if self.is_replaying else "⏸ Paused"
            move_count = f"Move {self.replay_index} / {len(self.game.move_history)}"
            tid = self.canvas.create_text(
                LEFT_X, y,
                text=f"{status}    {move_count}",
                anchor="sw",
                fill="black",
                font=("Arial", 10, "bold"),
            )
            ids.append(tid)

        self.debug_label_id = ids


# -----------------------------
# Interactive UI
# -----------------------------
class InteractiveUI(ViewerUI):
    def __init__(self, game, agents=None):
        # Initialise all InteractiveUI fields BEFORE super().__init__(),
        # because ViewerUI.__init__ calls draw_board() which dispatches to
        # InteractiveUI.draw_board() and needs these attributes to exist.

        # Hover state
        self.hover_cell = None
        self.hover_moves = set()
        self.hover_move_paths = {}

        # Selection state
        self.selected = None
        self.valid_moves = set()
        self.selected_move_paths = {}
        self.chosen_move = None
        self.chosen_path = None

        self.cell_to_id = {}

        # goal_colors needs self.game, which is set by super().__init__()
        # so we init to empty and populate after the super call.
        self.goal_colors = {}

        super().__init__(game, agents=agents)

        # Populate goal_colors now that self.game is available
        # (ViewerUI.__init__ also builds this; override with InteractiveUI values)
        for pid in range(self.game.num_players):
            self.goal_colors[pid] = lighten_color(PLAYER_COLOR_MAP[self.game.players[pid]], 0.6)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", self.on_leave)

        # Debug toggle — also inherited from ViewerUI but re-bind to be safe
        self.root.bind("<Key-d>", self.toggle_debug)
        self.root.bind("<Key-D>", self.toggle_debug)

    def get_move_blocking(self):
        """Wait for human to select a move via clicks."""
        self.chosen_move = None
        self.chosen_path = None

        print(f"Waiting for move from {self.game.current_player}...")

        while self.chosen_move is None and not self.game.game_over:
            try:
                self.refresh()
                self.root.update_idletasks()
                self.root.update()
            except Exception as e:
                print(f"UI update error: {e}")
                break

            # Small sleep to prevent 100% CPU
            import time
            time.sleep(0.01)

        move = self.chosen_move
        # Reset for next turn
        self.chosen_move = None
        self.chosen_path = None

        if move is None:
            print(f"WARNING: No move received for {self.game.current_player}")

        return move

    def _on_animation_finished(self):
        if self.game.game_over or self.chosen_move is None:
            return

        print(f"Animation finished - applying move: {self.chosen_move}")

        try:
            self.game.step(self.chosen_move)
        except Exception as e:
            print(f"Error in game.step(): {e}")

        self.chosen_move = None
        self.chosen_path = None
        self.draw_board()

    def is_animating(self):
        return self.animating

    # -----------------------------
    # Input Handling
    # -----------------------------
    def on_hover(self, event):
        if self.animating or self.selected is not None:
            return

        cell = self.get_cell_from_click(event.x, event.y)

        if cell == self.hover_cell:
            return

        self.hover_cell = None
        self.hover_moves = set()
        self.hover_move_paths = {}

        if cell and self.game.pieces.get(cell) == self.game.current_player:
            self.hover_cell = cell

            self.hover_move_paths = self.game._engine.get_all_moves_with_paths(
                cell, self.game._pieces
            )
            self.hover_moves = set(self.hover_move_paths.keys())

        self.draw_board()

    def on_leave(self, event):
        if self.animating:
            return

        self.hover_cell = None
        self.hover_moves = set()
        self.hover_move_paths = {}

        self.draw_board()

    def on_click(self, event):
        if self.animating or self.game.game_over:
            return

        cell = self.get_cell_from_click(event.x, event.y)
        print(f"Click detected at {cell} | Selected: {self.selected} | Animating: {self.animating}")
        if cell is None:
            return

        if self.selected is None:
            # Select piece
            if self.game.pieces.get(cell) == self.game.current_player:
                self.selected = cell
                self.selected_move_paths = self.game._engine.get_all_moves_with_paths(
                    cell, self.game._pieces
                )
                self.valid_moves = set(self.selected_move_paths.keys())
                self.draw_board()
        else:
            # Try to make move
            if cell in self.valid_moves:
                path = self.selected_move_paths.get(cell)
                if path:
                    self.chosen_move = (path[0], path[-1])
                    self.chosen_path = path

                    print(f"Move chosen: {self.chosen_move}")

                    # Reset selection
                    self.selected = None
                    self.valid_moves = set()
                    self.selected_move_paths = {}

                    self.draw_board()

                    # Animate and apply move after animation
                    self.animate_move_with_callback(path, callback=self._on_animation_finished)
            else:
                # Deselect if clicked elsewhere
                self.selected = None
                self.valid_moves = set()
                self.selected_move_paths = {}
                self.draw_board()

    # -----------------------------
    # Drawing
    # -----------------------------
    def draw_board(self):
        self.canvas.delete("all")
        self.cell_to_id.clear()
        self.draw_debug_label()

        for cell in self.game.cells:
            x, y = axial_to_pixel(*cell)
            pts = hexagon_points(x, y, HEX_SIZE)

            fill = self.get_cell_color(cell)

            outline = "black"
            width = 1

            if cell == self.selected:
                outline = "gold"
                width = 4
            elif cell in self.valid_moves:
                outline = "green"
                width = 2
            elif cell in self.hover_moves:
                outline = "darkgreen"
                width = 2
            elif cell == self.hover_cell:
                outline = "white"
                width = 2

            cid = self.canvas.create_polygon(
                pts, fill=fill, outline=outline, width=width
            )
            self.cell_to_id[cid] = cell

        pid = self.game.current_player
        self.canvas.create_text(
            100, 30,
            text=f"Player {pid.value}'s Turn",
            fill=PLAYER_COLOR_MAP[pid],
            font=("Arial", 16, "bold")
        )

        # Repaint path/highlights on top if an animation is in progress
        if self._draw_highlights:
            self._draw_highlights()

        self.draw_move_paths()
        self.draw_player_panel()

        if self.debug:
            self.draw_debug_overlay()

        if self.game.game_over:
            self.canvas.create_text(
                WIDTH // 2, HEIGHT // 2 - 30,
                text="GAME OVER",
                font=("Arial", 36, "bold"),
                fill="red"
            )
            winner_text = f"Winner: {self.game.winner}" if self.game.winner else "Draw / Loss"
            self.canvas.create_text(
                WIDTH // 2, HEIGHT // 2 + 20,
                text=winner_text,
                font=("Arial", 18),
                fill="black"
            )

    def get_cell_color(self, cell):
        # Hide the piece at its origin while the hop animation is in progress
        if self.animating and cell == self._anim_origin:
            # Show goal tint or plain empty underneath
            for pid, goal_cells in self.game.goal_triangles.items():
                if cell in goal_cells:
                    return self.goal_colors[pid.value - 1]
            return "lightgray"

        if cell in self.game.pieces:
            return PLAYER_COLOR_MAP[self.game.pieces[cell]]

        if cell in self.valid_moves:
            return "lightgreen"

        if cell in self.hover_moves:
            return "#ccffcc"

        for pid, goal_cells in self.game.goal_triangles.items():
            if cell in goal_cells:
                return self.goal_colors[pid.value - 1]

        return "lightgray"

    def draw_move_paths(self):
        if self.animating:
            return

        paths = (
            self.selected_move_paths
            if self.selected is not None
            else self.hover_move_paths
        )

        color = "#2ecc71" if self.selected else "#4a90e2"

        for path in paths.values():
            for i in range(len(path) - 1):
                x1, y1 = axial_to_pixel(*path[i])
                x2, y2 = axial_to_pixel(*path[i + 1])

                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color,
                    width=3,
                    smooth=True
                )

    def draw_debug_overlay(self):
        """Extends base overlay with hover highlight and path step indices."""
        super().draw_debug_overlay()

        # Hover highlight ring
        if self.hover_cell:
            cx, cy = axial_to_pixel(*self.hover_cell)
            circle = self.canvas.create_oval(
                cx - HEX_SIZE, cy - HEX_SIZE,
                cx + HEX_SIZE, cy + HEX_SIZE,
                outline="red", width=2
            )
            self.debug_items.append(circle)

        # Path step indices
        if self.selected is not None:
            for path in self.selected_move_paths.values():
                for i, cell in enumerate(path):
                    cx, cy = axial_to_pixel(*cell)
                    tid = self.canvas.create_text(
                        cx, cy - 10,
                        text=str(i),
                        fill="blue",
                        font=("Arial", 8, "bold")
                    )
                    self.debug_items.append(tid)

    # -----------------------------
    # Animation
    # -----------------------------
    def play_animated_move(self, move, callback=None):
        """
        Animate a move and call callback when animation is finished.
        This does NOT call game.step() — that remains in Driver.
        """
        if not move:
            if callback:
                callback()
            return

        start, end = move

        # Find full path for smooth animation
        paths = self.game._engine.get_all_moves_with_paths(start, self.game._pieces)
        path = paths.get(end)

        if not path:
            path = [start, end]  # fallback

        def animation_complete():
            # Animation finished - notify driver
            if callback:
                self.root.after(50, callback)  # small safety delay

        self.animate_move_with_callback(path, callback=animation_complete)

    # -----------------------------
    # Helpers
    # -----------------------------
    def get_cell_from_click(self, x, y):
        closest = None
        min_dist = float("inf")

        for cell in self.game.cells:
            cx, cy = axial_to_pixel(*cell)
            dx = cx - x
            dy = cy - y
            dist = dx * dx + dy * dy

            if dist < min_dist:
                min_dist = dist
                closest = cell

        if min_dist <= (HEX_SIZE * 1.5) ** 2:
            return closest

        return None

    def show_game_over(self):
        self.canvas.create_text(
            WIDTH // 2,
            HEIGHT // 2,
            text="Game Over",
            font=("Arial", 24),
            fill="black"
        )


