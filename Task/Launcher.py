"""
Launcher.py — Chinese Checkers GUI Launcher

Single-panel launcher supporting 2, 3, 4, or 6 players.
Each player slot can be assigned an AI agent file or set to Human.
A Replay button opens a file dialog and starts playback immediately.
"""

import importlib.util
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from game import ChineseCheckersGame
from utility import PlayerId, PLAYER_COLOR_MAP
from HumanAgent import HumanAgent
from ui import ViewerUI, InteractiveUI


# ── Valid player counts ───────────────────────────────────────────────────────
VALID_COUNTS = [2, 3, 4, 6]
ALL_PLAYER_IDS = [
    PlayerId.PLAYER_1, PlayerId.PLAYER_2, PlayerId.PLAYER_3,
    PlayerId.PLAYER_4, PlayerId.PLAYER_5, PlayerId.PLAYER_6,
]

# ── Palette ───────────────────────────────────────────────────────────────────
BG         = "#1a1a2e"
PANEL      = "#16213e"
ACCENT     = "#e94560"
ACCENT2    = "#0f3460"
TEXT       = "#eaeaea"
SUBTEXT    = "#8899aa"
BTN_FG     = "#ffffff"
BTN_ACTIVE = "#ff6b81"
ENTRY_BG   = "#0f3460"
DIVIDER    = "#2a2a4a"
ROW_ALT    = "#111828"

FONT_TITLE = ("Georgia", 22, "bold")
FONT_HEAD  = ("Georgia", 11, "bold")
FONT_BODY  = ("Courier", 10)
FONT_BTN   = ("Georgia", 10, "bold")
FONT_SMALL = ("Courier", 9)


# ── Agent loader ──────────────────────────────────────────────────────────────
def load_agent_from_file(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        spec   = importlib.util.spec_from_file_location("_dyn_agent", path)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.dirname(path))
        spec.loader.exec_module(module)
        sys.path.pop(0)
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and hasattr(obj, "select_move") and name != "Agent":
                return obj()
        messagebox.showerror("Agent Error",
                             f"No agent class with select_move found in:\n{path}")
    except Exception as exc:
        messagebox.showerror("Agent Error", f"Failed to load agent:\n{exc}")
    return None


def short_name(path):
    return os.path.splitext(os.path.basename(path))[0] if path else ""


# ── Shared game runner ────────────────────────────────────────────────────────
def run_game(agents, on_close=None):
    game      = ChineseCheckersGame(agents)
    has_human = any(isinstance(a, HumanAgent) for a in agents.values())
    ui        = InteractiveUI(game, agents=agents) if has_human else ViewerUI(game, agents=agents)

    if on_close:
        ui.root.protocol("WM_DELETE_WINDOW", lambda: _close_window(ui, on_close))

    # Start the live timer tick via after() rather than calling directly,
    # so the job ID is captured in _tick_job from the very first schedule
    # and after_cancel() in _on_close can reliably stop it before the window
    # is destroyed — preventing the "invalid command name" Tkinter error.
    ui._tick_job = ui.root.after(500, ui.tick_move_timer)

    def next_turn():
        if game.game_over:
            if game.winner:
                print(f"Winner: {game.winner}")
            game.save_history()
            ui.draw_board()
            return

        player = game.current_player
        agent  = agents[player]
        ui.start_move_timer(player)

        if isinstance(agent, HumanAgent):
            move = ui.get_move_blocking()
            # Human: stop timer when they submit their move click
            elapsed = ui.stop_move_timer(player)
        else:
            legal = game.get_all_legal_moves(player)
            move  = agent.select_move(game.snapshot(), player) if legal else None
            # Stop immediately after select_move — thinking time only, not animation
            elapsed = ui.stop_move_timer(player)


        if move is None:
            game.step(None)
            if game.game_over:
                game.save_history(
                    agent_types={str(pid): type(a).__name__ for pid, a in agents.items()},
                    total_times=ui._total_times,
                )
            ui.root.after(400, next_turn)
            return

        def after_animation():
            game.step(move)
            # Stamp the pre-recorded thinking time (not animation time) onto the move
            game._stamp_move_time(elapsed)
            ui.draw_board()
            if game.game_over:
                game.save_history(
                    agent_types={str(pid): type(a).__name__ for pid, a in agents.items()},
                    total_times=ui._total_times,
                )
                ui.draw_board()
            else:
                ui.root.after(350, next_turn)

        if hasattr(ui, "play_animated_move"):
            ui.play_animated_move(move, callback=after_animation)
        else:
            game.step(move)
            game._stamp_move_time(elapsed)
            if game.game_over:
                game.save_history(
                    agent_types={str(pid): type(a).__name__ for pid, a in agents.items()},
                    total_times=ui._total_times,
                )
            ui.draw_board()
            ui.root.after(350, next_turn)

    next_turn()
    if on_close is None:
        ui.root.mainloop()


def run_replay(filepath, on_close=None):
    game = ChineseCheckersGame.load_from_history(filepath)
    ui   = ViewerUI(game)
    if on_close:
        ui.root.protocol("WM_DELETE_WINDOW", lambda: _close_window(ui, on_close))
    if on_close is None:
        ui.root.mainloop()


def _close_window(ui, on_close):
    """Destroy the game window and notify the launcher."""
    # Delegate to _on_close so after_cancel and all cleanup always runs
    # regardless of which code path closes the window. Without this,
    # tick_move_timer's pending after() job fires on a destroyed window.
    ui._on_close()
    on_close()


# ── Styled widget helpers ─────────────────────────────────────────────────────
def accent_btn(parent, text, command, width=20):
    return tk.Button(
        parent, text=text, command=command,
        bg=ACCENT, fg=BTN_FG, activebackground=BTN_ACTIVE,
        activeforeground=BTN_FG, font=FONT_BTN,
        relief=tk.FLAT, bd=0, padx=14, pady=8,
        cursor="hand2", width=width,
    )


def ghost_btn(parent, text, command, width=10):
    return tk.Button(
        parent, text=text, command=command,
        bg=ACCENT2, fg=SUBTEXT, activebackground=DIVIDER,
        activeforeground=TEXT, font=FONT_SMALL,
        relief=tk.FLAT, bd=0, padx=8, pady=5,
        cursor="hand2", width=width,
    )


# ── Single player row ─────────────────────────────────────────────────────────
class PlayerRow(tk.Frame):
    """
    One row per player slot.  Shows a colour swatch, player label,
    agent name display, Browse button, and a Human checkbox.
    """
    def __init__(self, parent, player_id, index, **kw):
        bg = ROW_ALT if index % 2 else PANEL
        super().__init__(parent, bg=bg, **kw)
        self._filepath = None
        self.human_var = tk.BooleanVar(value=False)
        self._pid      = player_id

        # Colour swatch
        swatch_color = PLAYER_COLOR_MAP[player_id]
        tk.Frame(self, bg=swatch_color, width=6).pack(side=tk.LEFT, fill=tk.Y)

        # Player label
        tk.Label(
            self, text=f"Player {index + 1}", font=FONT_HEAD,
            bg=bg, fg=TEXT, width=9, anchor="w",
        ).pack(side=tk.LEFT, padx=(10, 6), pady=8)

        # Agent name display
        self._name_var = tk.StringVar(value="— not selected —")
        tk.Label(
            self, textvariable=self._name_var,
            font=FONT_SMALL, bg=ENTRY_BG, fg=TEXT,
            width=22, anchor="w", padx=6, pady=4,
        ).pack(side=tk.LEFT, padx=(0, 8))

        # Browse button
        ghost_btn(self, "Browse…", self._browse, width=9).pack(side=tk.LEFT, padx=(0, 10))

        # Human checkbox
        tk.Checkbutton(
            self, text="Human", variable=self.human_var,
            bg=bg, fg=SUBTEXT, selectcolor=ACCENT2,
            activebackground=bg, activeforeground=TEXT,
            font=FONT_SMALL, command=self._on_human_toggle,
        ).pack(side=tk.LEFT)

    def _browse(self):
        path = filedialog.askopenfilename(
            title=f"Select Agent for Player {self._pid.value}",
            filetypes=[("Python files", "*.py")],
        )
        if path:
            self._filepath = path
            self._name_var.set(short_name(path))
            self.human_var.set(False)

    def _on_human_toggle(self):
        if self.human_var.get():
            self._filepath = None
            self._name_var.set("Human Player")
        else:
            self._name_var.set("— not selected —")

    def get_agent(self):
        if self.human_var.get():
            return HumanAgent()
        return load_agent_from_file(self._filepath)

    def reset(self):
        self._filepath = None
        self.human_var.set(False)
        self._name_var.set("— not selected —")


# ── Main launcher ─────────────────────────────────────────────────────────────
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chinese Checkers")
        self.configure(bg=BG)
        self.resizable(False, False)

        self._rows: list[PlayerRow] = []   # all 6 possible rows, shown/hidden
        self._num_players = tk.IntVar(value=2)

        self._build()
        self._update_rows()

        # Centre on screen
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Header
        tk.Label(self, text="⬡  Chinese Checkers", font=FONT_TITLE,
                 bg=BG, fg=ACCENT).pack(pady=(20, 2))
        tk.Label(self, text="Configure players, then start a game or load a replay.",
                 font=FONT_SMALL, bg=BG, fg=SUBTEXT).pack(pady=(0, 10))
        tk.Frame(self, bg=ACCENT, height=2).pack(fill=tk.X)

        # ── Player count selector
        count_frame = tk.Frame(self, bg=PANEL)
        count_frame.pack(fill=tk.X, padx=0)

        tk.Label(count_frame, text="Number of Players:", font=FONT_HEAD,
                 bg=PANEL, fg=TEXT).pack(side=tk.LEFT, padx=(18, 12), pady=12)

        for n in VALID_COUNTS:
            tk.Radiobutton(
                count_frame, text=str(n), variable=self._num_players, value=n,
                command=self._update_rows,
                bg=PANEL, fg=TEXT, selectcolor=ACCENT2,
                activebackground=PANEL, activeforeground=ACCENT,
                font=FONT_HEAD, indicatoron=False,
                relief=tk.FLAT, padx=12, pady=4,
                cursor="hand2",
            ).pack(side=tk.LEFT, padx=4)

        tk.Frame(self, bg=DIVIDER, height=1).pack(fill=tk.X)

        # ── Player rows container (all 6 created, shown/hidden dynamically)
        self._rows_frame = tk.Frame(self, bg=PANEL)
        self._rows_frame.pack(fill=tk.X)

        for i, pid in enumerate(ALL_PLAYER_IDS):
            row = PlayerRow(self._rows_frame, pid, i)
            row.pack(fill=tk.X)
            self._rows.append(row)

        tk.Frame(self, bg=DIVIDER, height=1).pack(fill=tk.X)

        # ── Action buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=16)

        accent_btn(btn_frame, "▶  Start Game", self._start_game, width=18
                   ).pack(side=tk.LEFT, padx=(0, 12))

        ghost_btn(btn_frame, "⏵  Replay Saved Game", self._start_replay, width=20
                  ).pack(side=tk.LEFT)

        # ── Footer
        tk.Frame(self, bg=ACCENT, height=2).pack(fill=tk.X)
        tk.Label(self, text="Georgia Tech · KBAI",
                 font=FONT_SMALL, bg=BG, fg=SUBTEXT).pack(pady=(6, 10))

    # ── Row visibility ────────────────────────────────────────────────────────
    def _update_rows(self):
        n = self._num_players.get()
        for i, row in enumerate(self._rows):
            if i < n:
                row.pack(fill=tk.X)
            else:
                row.pack_forget()
                row.reset()

        # Force geometry recalculate
        self.update_idletasks()
        self.geometry("")   # let tk resize to fit content

    # ── Actions ───────────────────────────────────────────────────────────────
    def _start_game(self):
        n = self._num_players.get()
        agents = {}
        for i in range(n):
            pid   = ALL_PLAYER_IDS[i]
            agent = self._rows[i].get_agent()
            if agent is None:
                messagebox.showwarning(
                    "Missing Agent",
                    f"Player {i + 1} has no agent selected.\n"
                    "Please browse for an agent file or tick Human."
                )
                return
            agents[pid] = agent

        self.withdraw()
        run_game(agents, on_close=self.deiconify)

    def _start_replay(self):
        path = filedialog.askopenfilename(
            title="Select Replay File",
            initialdir="History",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        self.withdraw()
        run_replay(path, on_close=self.deiconify)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    Launcher().mainloop()
