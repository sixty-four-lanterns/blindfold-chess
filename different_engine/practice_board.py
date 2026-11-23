"""The practice board: an unrated halfway step between sight and blindfold.

During a practice game a small window shows the board with its coordinates
(a-h and 1-8 round the edge) and each square's name, small, in its middle.
Every occupied square shows the same soft, shaded sphere: ivory for White
and charcoal for Black.  You can see where the pieces
are and whose they are, but never which piece it is.  There is no last-move
mark and no analysis.

The window runs in its own small process, so it keeps redrawing (and can be
moved or closed) while the game is waiting for you to speak or type.  The
game sends it the position after every move; closing it does not end the
game.  If no window can be opened (no screen, or no tkinter), the game goes
on without it.

Everything that decides what is drawn is plain code (occupied_squares,
drawing_items, and so on) and can be tested on any computer.
"""

import os
import queue
import subprocess
import sys
import threading

import chess

SQUARE = 64                 # same size as the other board windows
MARGIN = 22                 # room for the coordinates on every side
LIGHT, DARK = "#f0d9b5", "#b58863"      # the colours used by the other boards
COORD_COLOUR = "#555555"
# One shape for every piece; only the colour tells you whose it is.
# (body, soft edge, sheen) for White's pieces and for Black's.
WHITE_PIECE = ("#f3efe1", "#8a8a8a", "#ffffff")     # ivory, with a grey outline
BLACK_PIECE = ("#3a3a3a", "#262626", "#6c6c6c")     # charcoal
# Square names (e4 and so on) in the middle of every square, in a small font.
LABEL_FONT = ("TkDefaultFont", 8)
LABEL_ON_WHITE_PIECE = "#3a3a3a"        # dark text on an ivory piece
LABEL_ON_BLACK_PIECE = "#e8e8e8"        # light text on a charcoal piece
SOFT_LAYERS = 5             # rings blended into the square: a soft, fuzzy edge
SOFT_STEP = 1.3             # pixels per ring
TITLE = "Practice board"

# The generic piece: a shaded sphere, lit from the top left, as fractions of a square.
SPHERE = (0.18, 0.18, 0.82, 0.82)       # (left, top, right, bottom) from the square's top-left
SHADOW = {True: 0.18, False: 0.35}      # how much darker the sphere's far side is (White, Black)
SHADE_STEPS = 8                         # graded ovals from the shaded side to the highlight


# ---------------------------------------------------------------------------
# What to draw (no window needed)
# ---------------------------------------------------------------------------

def occupied_squares(board):
    """Occupied squares, a1 first, with whose piece stands there, e.g.
    [('a1', 'white'), ...].  Says nothing about which piece it is."""
    return [(chess.square_name(sq), "white" if board.color_at(sq) else "black")
            for sq in chess.SQUARES if board.piece_at(sq) is not None]


def canvas_size():
    return 2 * MARGIN + 8 * SQUARE


def square_origin(square, white_at_bottom=True):
    """Top-left corner (x, y) of a square on the canvas, from the player's side."""
    f, r = chess.square_file(square), chess.square_rank(square)
    if not white_at_bottom:
        f, r = 7 - f, 7 - r
    return MARGIN + f * SQUARE, MARGIN + (7 - r) * SQUARE


def square_colour(square):
    light = (chess.square_file(square) + chess.square_rank(square)) % 2
    return LIGHT if light else DARK


def _rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def blend(background, foreground, amount):
    """`amount` of the way from background to foreground, as #rrggbb."""
    b, f = _rgb(background), _rgb(foreground)
    return "#" + "".join(f"{round(bb + (ff - bb) * amount):02x}" for bb, ff in zip(b, f))


def piece_items(x0, y0, background, white=True, size=SQUARE):
    """Ovals for one generic piece in the square whose top-left is (x0, y0).

    Every piece type is the same shaded sphere; `white` only chooses the
    colours.  The outer rings fade into the square's own colour, so the edge
    looks soft without needing transparency (which tkinter canvases do not
    have).  Inside, graded ovals drift towards the top left to give the shading.
    """
    body, edge, sheen = WHITE_PIECE if white else BLACK_PIECE
    left, top, right, bottom = SPHERE
    items = []
    for ring in range(SOFT_LAYERS, 0, -1):           # widest and faintest first
        grow = ring * SOFT_STEP
        fill = blend(background, edge, (SOFT_LAYERS + 1 - ring) / SOFT_LAYERS)
        items.append(("oval", (x0 + left * size - grow, y0 + top * size - grow,
                               x0 + right * size + grow, y0 + bottom * size + grow), fill))
    shade = blend(body, "#000000", SHADOW[bool(white)])
    items.append(("oval", (x0 + left * size, y0 + top * size,
                           x0 + right * size, y0 + bottom * size), shade))
    for k in range(SHADE_STEPS):                     # the lit side, then the highlight
        f = k / (SHADE_STEPS - 1)
        r = 0.32 * (1 - f) + 0.06
        cx = cy = 0.5 - 0.12 * f
        fill = blend(shade, sheen, f * 0.9) if k else body
        items.append(("oval", (x0 + (cx - r) * size, y0 + (cy - r) * size,
                               x0 + (cx + r) * size, y0 + (cy + r) * size), fill))
    return items


def label_colour(square, owner=None):
    """Colour of a square's name: subtle on an empty square, and contrasting
    with the piece on an occupied one.  `owner` is chess.WHITE, chess.BLACK or None."""
    if owner is None:
        background = square_colour(square)
        other = DARK if background == LIGHT else LIGHT
        return blend(background, other, 0.75 if background == LIGHT else 0.5)
    return LABEL_ON_WHITE_PIECE if owner else LABEL_ON_BLACK_PIECE


def drawing_items(board, white_at_bottom=True):
    """Everything on the practice board, in drawing order.

    Each item is ("rect", (x0, y0, x1, y1), fill), ("oval", (x0, y0, x1, y1), fill),
    ("label", (x, y), square name, fill) for the name in the middle of each
    square, or ("text", (x, y), text, fill) for the coordinates round the edge.  Every piece is the same sphere, so the
    list depends only on whose piece stands on a square, never on which piece.
    """
    items = []
    for sq in chess.SQUARES:
        x, y = square_origin(sq, white_at_bottom)
        items.append(("rect", (x, y, x + SQUARE, y + SQUARE), square_colour(sq)))
    for sq in chess.SQUARES:
        if board.piece_at(sq) is not None:
            x, y = square_origin(sq, white_at_bottom)
            items.extend(piece_items(x, y, square_colour(sq), white=board.color_at(sq)))
    for sq in chess.SQUARES:
        x, y = square_origin(sq, white_at_bottom)
        items.append(("label", (x + SQUARE / 2, y + SQUARE / 2), chess.square_name(sq),
                      label_colour(sq, board.color_at(sq))))
    far = MARGIN + 8 * SQUARE
    for i in range(8):
        f = i if white_at_bottom else 7 - i
        r = 7 - i if white_at_bottom else i
        x = MARGIN + i * SQUARE + SQUARE / 2
        y = MARGIN + i * SQUARE + SQUARE / 2
        letter, number = "abcdefgh"[f], str(r + 1)
        items.append(("text", (x, far + MARGIN / 2), letter, COORD_COLOUR))
        items.append(("text", (x, MARGIN / 2), letter, COORD_COLOUR))
        items.append(("text", (MARGIN / 2, y), number, COORD_COLOUR))
        items.append(("text", (far + MARGIN / 2, y), number, COORD_COLOUR))
    return items


def board_key(board):
    """Only where the pieces stand (and whose they are) matters to the window."""
    return board.board_fen()


# ---------------------------------------------------------------------------
# The window (runs in its own process: python -m different_engine.practice_board)
# ---------------------------------------------------------------------------

def draw_on(canvas, board, white_at_bottom=True):
    canvas.delete("all")
    for item in drawing_items(board, white_at_bottom):
        kind = item[0]
        if kind == "rect":
            canvas.create_rectangle(*item[1], fill=item[2], outline="")
        elif kind == "oval":
            canvas.create_oval(*item[1], fill=item[2], outline="")
        elif kind == "label":
            canvas.create_text(*item[1], text=item[2], fill=item[3], font=LABEL_FONT)
        else:
            canvas.create_text(*item[1], text=item[2], fill=item[3],
                               font=("TkDefaultFont", 10, "bold"))


def _give_focus_back_to_console():
    """On Windows, hand the keyboard back to the console the game runs in."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def run_window(white_at_bottom=True, stdin=None, stdout=None, snapshot=None):
    """The window's own main loop.  Reads commands, one per line, from stdin:

        board <board FEN>     show this position
        close                 close the window

    The end of stdin (the game has finished, or the program has stopped)
    closes the window too.  Prints 'ready' once the window is up.
    `snapshot` is for testing: called with the root window after the first draw.
    """
    import tkinter as tk
    from .window_icon import create_root

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    root = create_root()
    root.title(TITLE)
    root.resizable(False, False)
    size = canvas_size()
    canvas = tk.Canvas(root, width=size, height=size, highlightthickness=0, bg="#e8e8e8")
    canvas.pack()
    draw_on(canvas, chess.Board(None), white_at_bottom)

    commands = queue.Queue()

    def read():
        try:
            for line in stdin:
                commands.put(line.strip())
        except Exception:
            pass
        commands.put("close")

    threading.Thread(target=read, daemon=True).start()

    def poll():
        try:
            while True:
                line = commands.get_nowait()
                if line == "close":
                    root.destroy()
                    return
                if line.startswith("board "):
                    try:
                        board = chess.Board(line[6:].strip() + " w - - 0 1")
                    except ValueError:
                        continue
                    draw_on(canvas, board, white_at_bottom)
        except queue.Empty:
            pass
        root.after(80, poll)

    root.update()
    root.after(150, _give_focus_back_to_console)
    try:
        stdout.write("ready\n")
        stdout.flush()
    except Exception:
        pass
    root.after(30, poll)
    if snapshot:
        root.after(400, lambda: snapshot(root))
    root.mainloop()


# ---------------------------------------------------------------------------
# The game's side: start the window, send it positions, close it
# ---------------------------------------------------------------------------

class PracticeBoard:
    """Controls the practice-board window from the game.  Never raises."""

    def __init__(self, white_at_bottom=True, popen=None):
        self.white_at_bottom = white_at_bottom
        self.popen = popen or subprocess.Popen
        self.process = None
        self.shown = None

    @property
    def is_open(self):
        return self.process is not None and self.process.poll() is None

    def open(self, board):
        """Open the window (if it isn't open already) on this position.
        Returns True if the window is open."""
        if self.is_open:
            self.update(board)
            return True
        package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        args = [sys.executable, "-m", "different_engine.practice_board"]
        if not self.white_at_bottom:
            args.append("--black")
        try:
            self.process = self.popen(args, cwd=package_parent, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      text=True, bufsize=1)
            first = self.process.stdout.readline() if self.process.stdout else ""
        except Exception:
            self.process = None
            return False
        if first.strip() != "ready":
            self.close()
            return False
        self.shown = None
        self.update(board)
        return True

    def update(self, board):
        """Show this position, if it has changed.  Does nothing if the window is closed."""
        if not self.is_open:
            return False
        key = board_key(board)
        if key == self.shown:
            return True
        return self._send(f"board {key}") and self._remember(key)

    def _remember(self, key):
        self.shown = key
        return True

    def _send(self, line):
        try:
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()
            return True
        except Exception:
            return False

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self._send("close")
        try:
            self.process.stdin.close()
        except Exception:
            pass
        try:
            self.process.wait(timeout=2)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        self.process = None
        self.shown = None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        run_window(white_at_bottom="--black" not in argv)
    except Exception:
        try:
            sys.stdout.write("error\n")
            sys.stdout.flush()
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
