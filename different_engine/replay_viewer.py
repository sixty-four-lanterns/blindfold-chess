"""Look at a finished game on a board, between games.

'Show board' opens a window with the game you have just played.  You can step
through it move by move (Start, Back, Forward, End, or the arrow keys), turn
the board round, and load any other game from a PGN file for analysis.

Beside the board is an analysis bar.  Stockfish looks at each position for a
fraction of a second, in the background, so stepping never waits for it; the
bar, the figure under it (+0.8 means White is about eight-tenths of a pawn
better, M3 means mate in three) and the engine's best move are filled in as
soon as each look is finished.  Every look is remembered, so stepping back is
instant.  If Stockfish can't be started, the bar is simply left out.

The board is never shown during a game: this is blindfold chess.

Everything apart from the window itself is plain code that can be tested on
any computer (Replay, eval_fraction, eval_text, ascii_board and so on).  If
the window can't be opened (no tkinter, or no screen), the final position is
printed as text instead.
"""

import glob
import math
import os
import queue
import threading

import chess
import chess.pgn

SECONDS_PER_POSITION = 0.25
MARK = "#d0d0d0"                     # light grey, for the last move's two squares
BAR_WHITE, BAR_DARK = "#ffffff", "#404040"
BAR_WIDTH = 26


# ---------------------------------------------------------------------------
# The game being looked at (no window needed)
# ---------------------------------------------------------------------------

class Replay:
    """A starting position, the moves played from it, and the PGN headers."""

    def __init__(self, start=None, moves=(), headers=None):
        self.start = (start or chess.Board()).copy(stack=False)
        self.moves = list(moves)
        self.headers = dict(headers or {})

    @classmethod
    def from_board(cls, board, headers=None):
        """From a board that still holds its move stack (a finished game)."""
        start = board.copy()
        moves = []
        while start.move_stack:
            moves.append(start.pop())
        moves.reverse()
        return cls(start, moves, headers)

    @classmethod
    def from_pgn_file(cls, path):
        """The first game in a PGN file.  A FEN/SetUp header is respected.
        Raises ValueError if the file holds no readable game."""
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            game = chess.pgn.read_game(f)
        if game is None:
            raise ValueError("There is no game in that file.")
        if game.errors:
            raise ValueError(f"That game could not be read: {game.errors[0]}")
        return cls(game.board(), list(game.mainline_moves()), dict(game.headers))

    @property
    def length(self):
        return len(self.moves)

    def clamp(self, ply):
        return max(0, min(self.length, ply))

    def board_at(self, ply):
        """The position after `ply` half-moves (0 is the starting position)."""
        board = self.start.copy(stack=False)
        for move in self.moves[:self.clamp(ply)]:
            board.push(move)
        return board

    def last_move(self, ply):
        """The move that led to the position at `ply`, or None at the start."""
        ply = self.clamp(ply)
        return self.moves[ply - 1] if ply else None

    def move_label(self, ply):
        """'12. Nf3' or '12... Nf6' for the move just played, or 'Starting position'."""
        ply = self.clamp(ply)
        if ply == 0:
            return "Starting position"
        before = self.board_at(ply - 1)
        san = before.san(self.moves[ply - 1])
        dots = "." if before.turn == chess.WHITE else "..."
        return f"{before.fullmove_number}{dots} {san}"

    def counter(self, ply):
        return f"Move {self.clamp(ply)} of {self.length}"

    def title(self):
        h = self.headers
        if not h.get("White") and not h.get("Black"):
            return "The Different Engine - game viewer"
        return (f"{h.get('White', '?')} v {h.get('Black', '?')}  {h.get('Result', '*')}"
                " - The Different Engine")


def step(ply, action, length):
    """Where Start, Back, Forward and End go from `ply` in a game of `length` half-moves."""
    target = {"start": 0, "back": ply - 1, "forward": ply + 1, "end": length}[action]
    return max(0, min(length, target))


def latest_saved_pgn(games_dir):
    """The most recently changed .pgn file in the games folder, or None."""
    files = glob.glob(os.path.join(games_dir or "", "*.pgn"))
    return max(files, key=os.path.getmtime) if files else None


# ---------------------------------------------------------------------------
# The analysis bar (no window needed)
# ---------------------------------------------------------------------------

def eval_fraction(cp=None, mate=None):
    """How much of the bar is White's, from 0.0 to 1.0, for a score from White's side.

    A mate fills the bar for the side giving it.  Otherwise a gentle S-curve
    (the logistic one used by many chess sites) turns centipawns into a share:
    level is a half, a pawn up is about 0.59, a rook up about 0.84.
    """
    if mate is not None:
        if mate > 0:
            return 1.0
        if mate < 0:
            return 0.0
        return 0.5
    if cp is None:
        return 0.5
    cp = max(-2000, min(2000, cp))
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


def eval_text(cp=None, mate=None):
    """'+0.8', '-1.3', '0.0', 'M3' (White mates in 3) or '-M2' (Black mates in 2)."""
    if mate is not None:
        if mate == 0:
            return "#"
        return f"M{mate}" if mate > 0 else f"-M{-mate}"
    if cp is None:
        return ""
    value = cp / 100
    if abs(value) < 0.05:
        return "0.0"
    return f"{value:+.1f}"


def game_over_eval(board):
    """(cp, mate, note) for a finished position, without asking the engine, or None."""
    if board.is_checkmate():
        winner_white = board.turn == chess.BLACK
        return (None, 1 if winner_white else -1, "Checkmate")
    if board.is_stalemate():
        return (0, None, "Stalemate")
    if board.is_insufficient_material():
        return (0, None, "Not enough pieces to mate")
    return None


def bar_split(fraction, height, white_at_bottom=True):
    """The y-coordinate where White's part of a bar `height` pixels tall meets Black's.

    White's share sits at the player's end of the board: at the bottom when
    White is at the bottom, at the top when the board is turned round.
    """
    fraction = max(0.0, min(1.0, fraction))
    white_px = round(fraction * height)
    return height - white_px if white_at_bottom else white_px


class Analyser:
    """Looks at positions with Stockfish on a background thread, and remembers them.

    request(key, board) asks for a look (most recent request first);
    result(key) is None until it is ready, then a dict with 'cp', 'mate'
    (both from White's side) and 'best' (the best move in SAN, or '').
    """

    def __init__(self, engine_path, seconds=SECONDS_PER_POSITION, popen=None):
        import chess.engine
        popen = popen or chess.engine.SimpleEngine.popen_uci
        self.engine = popen(engine_path)        # raises if Stockfish won't start
        self.limit = chess.engine.Limit(time=seconds)
        self.cache = {}
        self.jobs = queue.LifoQueue()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._work, daemon=True)
        self.thread.start()

    def request(self, key, board):
        if key in self.cache:
            return
        over = game_over_eval(board)
        if over:
            self.cache[key] = {"cp": over[0], "mate": over[1], "best": "", "note": over[2]}
            return
        self.jobs.put((key, board.copy(stack=False)))

    def result(self, key):
        return self.cache.get(key)

    def _work(self):
        while not self.stopped.is_set():
            try:
                key, board = self.jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            if key in self.cache:
                continue
            try:
                info = self.engine.analyse(board, self.limit)
            except Exception:
                if self.stopped.is_set():
                    return
                continue
            score = info.get("score")
            white = score.white() if score is not None else None
            pv = info.get("pv") or []
            try:
                best = board.san(pv[0]) if pv else ""
            except Exception:
                best = ""
            self.cache[key] = {"cp": white.score() if white is not None else None,
                               "mate": white.mate() if white is not None else None,
                               "best": best, "note": ""}

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
        try:
            self.engine.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text fallback
# ---------------------------------------------------------------------------

def ascii_board(board, white_at_bottom=True):
    """The position as text, from the player's side.  Capital letters are White."""
    files = "abcdefgh" if white_at_bottom else "hgfedcba"
    ranks = range(7, -1, -1) if white_at_bottom else range(8)
    lines = []
    for r in ranks:
        row = []
        for f_char in files:
            piece = board.piece_at(chess.square(ord(f_char) - ord("a"), r))
            row.append(piece.symbol() if piece else ".")
        lines.append(f"  {r + 1}  " + " ".join(row))
    lines.append("     " + " ".join(files))
    return "\n".join(lines)


def print_text_board(ui, replay, white_at_bottom=True):
    board = replay.board_at(replay.length)
    ui.say("I couldn't open a board window on this computer, so here is the final position as text. "
           "Capital letters are White.")
    print()
    print(ascii_board(board, white_at_bottom))
    if replay.length:
        print(f"\n  Last move: {replay.move_label(replay.length)}  ({replay.counter(replay.length)})")
    print()


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

def open_viewer(replay, white_at_bottom=True, engine_path=None, games_dir=None, snapshot=None,
                review=False):
    """Open the viewer and wait until it is closed.  Raises if there is no window system.

    `snapshot` is for testing: a function called with the root window once it
    has been drawn, instead of waiting for the player.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from .board_editor import BoardView, SQUARE
    from .window_icon import create_root

    root = create_root(review=review)
    root.resizable(False, False)
    state = {"replay": replay, "ply": replay.length, "game_no": 0}

    left = tk.Frame(root, padx=10, pady=10)
    left.grid(row=0, column=0, sticky="n")
    right = tk.Frame(root, padx=10, pady=10)
    right.grid(row=0, column=1, sticky="n")
    hidden = tk.Frame(root)                 # BoardView's palette goes here and is never shown

    board_row = tk.Frame(left)
    board_row.pack()
    bar_frame = tk.Frame(board_row)
    bar_frame.pack(side="left", padx=(0, 6), anchor="n")
    board_frame = tk.Frame(board_row)
    board_frame.pack(side="left")

    view = BoardView(root, board_frame, hidden, replay.board_at(replay.length), white_at_bottom)
    view.set_locked(True)

    analyser = None
    if engine_path:
        try:
            analyser = Analyser(engine_path)
        except Exception:
            analyser = None
    bar_height = 8 * SQUARE
    bar = None
    if analyser:
        bar = tk.Canvas(bar_frame, width=BAR_WIDTH, height=bar_height, highlightthickness=1,
                        highlightbackground="#808080")
        bar.pack()
    eval_label = tk.Label(left, text="", font=("TkDefaultFont", 11, "bold"))
    best_label = tk.Label(left, text="", fg="#404040")
    if analyser:
        eval_label.pack(anchor="w", pady=(6, 0))
        best_label.pack(anchor="w")

    headers_label = tk.Label(right, text="", justify="left", font=("TkDefaultFont", 10, "bold"))
    headers_label.pack(anchor="w")
    move_label = tk.Label(right, text="", font=("TkDefaultFont", 14, "bold"))
    move_label.pack(anchor="w", pady=(8, 0))
    counter_label = tk.Label(right, text="")
    counter_label.pack(anchor="w")

    moves_box = tk.Listbox(right, width=30, height=14, activestyle="none", exportselection=False,
                           selectbackground="#c0c0c0", selectforeground="black")
    moves_box.pack(anchor="w", pady=6)

    def fill_moves():
        rp = state["replay"]
        moves_box.delete(0, "end")
        moves_box.insert("end", "Starting position")
        for i in range(1, rp.length + 1):
            moves_box.insert("end", rp.move_label(i))

    def analysis_key(ply):
        return (state["game_no"], ply)       # each loaded game has its own numbers

    def show_eval():
        if not analyser:
            return
        ply = state["ply"]
        found = analyser.result(analysis_key(ply))
        bar.delete("all")
        if found is None:
            fraction, text, best = 0.5, "Thinking...", ""
        else:
            fraction = eval_fraction(found["cp"], found["mate"])
            text = found["note"] or eval_text(found["cp"], found["mate"])
            if found["note"] and found["mate"] is None:
                text += " (0.0)"
            best = f"Best move: {found['best']}" if found["best"] else ""
        y = bar_split(fraction, bar_height, not view.flipped)
        if view.flipped:
            bar.create_rectangle(0, 0, BAR_WIDTH + 2, y, fill=BAR_WHITE, outline="")
            bar.create_rectangle(0, y, BAR_WIDTH + 2, bar_height + 2, fill=BAR_DARK, outline="")
        else:
            bar.create_rectangle(0, 0, BAR_WIDTH + 2, y, fill=BAR_DARK, outline="")
            bar.create_rectangle(0, y, BAR_WIDTH + 2, bar_height + 2, fill=BAR_WHITE, outline="")
        bar.create_line(0, bar_height / 2, BAR_WIDTH + 2, bar_height / 2, fill="#909090")
        eval_label.config(text=f"Evaluation: {text}")
        best_label.config(text=best)

    def poll():
        if analyser and root.winfo_exists():
            show_eval()
            root.after(150, poll)

    def queue_all():
        """Ask for every position, the current one last so it is looked at first."""
        if not analyser:
            return
        rp = state["replay"]
        board = rp.start.copy(stack=False)
        boards = [board.copy(stack=False)]
        for move in rp.moves:
            board.push(move)
            boards.append(board.copy(stack=False))
        for ply in range(len(boards) - 1, -1, -1):
            if ply != state["ply"]:
                analyser.request(analysis_key(ply), boards[ply])
        analyser.request(analysis_key(state["ply"]), boards[state["ply"]])

    def show():
        rp, ply = state["replay"], state["ply"]
        board = rp.board_at(ply)
        view.board = board
        view.marks = {}
        last = rp.last_move(ply)
        if last:
            view.marks = {last.from_square: MARK, last.to_square: MARK}
        view.draw()
        move_label.config(text=rp.move_label(ply))
        counter_label.config(text=rp.counter(ply))
        moves_box.selection_clear(0, "end")
        moves_box.selection_set(ply)
        moves_box.see(ply)
        if analyser:
            analyser.request(analysis_key(ply), board)
            show_eval()

    def go(action):
        state["ply"] = step(state["ply"], action, state["replay"].length)
        show()

    def picked(event=None):
        sel = moves_box.curselection()
        if sel:
            state["ply"] = state["replay"].clamp(sel[0])
            show()

    def set_replay(rp, ply):
        state["replay"], state["ply"] = rp, ply
        state["game_no"] += 1
        root.title(rp.title())
        h = rp.headers
        if h.get("White") or h.get("Black"):
            text = f"White: {h.get('White', '?')}\nBlack: {h.get('Black', '?')}\nResult: {h.get('Result', '*')}"
        else:
            text = "No game loaded yet"
        headers_label.config(text=text)
        fill_moves()
        queue_all()
        show()

    def load_pgn():
        path = filedialog.askopenfilename(
            parent=root, title="Load a game from a PGN file",
            initialdir=games_dir if games_dir and os.path.isdir(games_dir) else None,
            filetypes=[("PGN files", "*.pgn"), ("All files", "*.*")])
        if not path:
            return
        try:
            rp = Replay.from_pgn_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showwarning("Couldn't load that game", str(exc), parent=root)
            return
        set_replay(rp, 0)

    def flip():
        view.flip()
        show_eval()

    def close():
        if analyser:
            analyser.close()
        root.destroy()

    buttons = tk.Frame(right, pady=4)
    buttons.pack(anchor="w")
    for col, (text, action) in enumerate((("|< Start", "start"), ("< Back", "back"),
                                          ("Forward >", "forward"), ("End >|", "end"))):
        tk.Button(buttons, text=text, width=9, command=lambda a=action: go(a)).grid(row=0, column=col, padx=1)
    more = tk.Frame(right, pady=4)
    more.pack(anchor="w")
    tk.Button(more, text="Turn board round", command=flip).grid(row=0, column=0, padx=2)
    tk.Button(more, text="Load PGN\u2026", command=load_pgn).grid(row=0, column=1, padx=2)
    tk.Button(more, text="Close", command=close).grid(row=0, column=2, padx=2)
    tk.Label(right, text="Keys: Left and Right step through the moves;\nHome and End jump to the start and end.",
             justify="left", fg="#404040").pack(anchor="w", pady=(6, 0))

    root.bind("<Left>", lambda e: go("back"))
    root.bind("<Right>", lambda e: go("forward"))
    root.bind("<Home>", lambda e: go("start"))
    root.bind("<End>", lambda e: go("end"))
    moves_box.bind("<<ListboxSelect>>", picked)
    root.protocol("WM_DELETE_WINDOW", close)

    set_replay(replay, replay.length)
    root.focus_force()
    if analyser:
        root.after(150, poll)
    if snapshot:
        root.update()
        try:
            snapshot(root, state, go)
        finally:
            close()
        return
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.mainloop()


def show_board(ui, last_game=None, engine_path=None, games_dir=None, opener=open_viewer,
               *, review=False):
    """'Show board' between games: the last game, the latest saved one, or an empty start.

    Blocks until the window is closed.  Falls back to a text board if no window
    can be opened.  Returns 'window' or 'text'.  Pass review=True for the green
    knight icon used when the board is opened with --board.
    """
    if last_game:
        replay = Replay.from_board(last_game["board"], last_game.get("headers"))
        white_at_bottom = last_game.get("player", chess.WHITE) == chess.WHITE
        engine_path = engine_path or last_game.get("engine_path")
    else:
        replay, white_at_bottom = Replay(), True
        latest = latest_saved_pgn(games_dir)
        if latest:
            try:
                replay = Replay.from_pgn_file(latest)
            except (OSError, ValueError):
                replay = Replay()
            # Games saved by this program call you "Player"
            white_at_bottom = replay.headers.get("Black") != "Player"
    try:
        if opener is open_viewer:
            import tkinter  # noqa: F401  (checked first, so nothing misleading is said)
        opener(replay, white_at_bottom=white_at_bottom, engine_path=engine_path,
               games_dir=games_dir, review=review)
        return "window"
    except Exception:            # no tkinter, or no screen (for example over SSH)
        print_text_board(ui, replay, white_at_bottom)
        return "text"
