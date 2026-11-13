"""A simple board for setting up a custom starting position with the mouse.

Uses tkinter, which comes with Python, so nothing extra has to be installed.
The board and its palette of pieces (BoardView) are also used by the
reconstruction test at the end of a game (reconstruction.py).
"""

import chess

WHITE_GLYPHS = {chess.KING: "\u2654", chess.QUEEN: "\u2655", chess.ROOK: "\u2656",
                chess.BISHOP: "\u2657", chess.KNIGHT: "\u2658", chess.PAWN: "\u2659"}
BLACK_GLYPHS = {chess.KING: "\u265A", chess.QUEEN: "\u265B", chess.ROOK: "\u265C",
                chess.BISHOP: "\u265D", chess.KNIGHT: "\u265E", chess.PAWN: "\u265F"}
LETTERS = {chess.KING: "K", chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B", chess.KNIGHT: "N", chess.PAWN: "P"}
# Fonts known to contain the chess symbols; if none is found we draw lettered discs instead.
SYMBOL_FONTS = ["DejaVu Sans", "Segoe UI Symbol", "Apple Symbols", "Arial Unicode MS",
                "Noto Sans Symbols 2", "Noto Sans Symbols2", "FreeSerif", "Symbola"]
SQUARE = 64
LIGHT, DARK, HIGHLIGHT = "#f0d9b5", "#b58863", "#f6f669"


def position_problems(board):
    """Plain-English reasons why a position can't be played (empty list if fine)."""
    status = board.status()
    problems = []
    checks = [
        (chess.STATUS_NO_WHITE_KING, "White needs a king."),
        (chess.STATUS_NO_BLACK_KING, "Black needs a king."),
        (chess.STATUS_TOO_MANY_KINGS, "Each side must have exactly one king."),
        (chess.STATUS_TOO_MANY_WHITE_PAWNS, "White has more than eight pawns."),
        (chess.STATUS_TOO_MANY_BLACK_PAWNS, "Black has more than eight pawns."),
        (chess.STATUS_PAWNS_ON_BACKRANK, "Pawns can't stand on the first or eighth rank."),
        (chess.STATUS_TOO_MANY_WHITE_PIECES, "White has more than sixteen pieces."),
        (chess.STATUS_TOO_MANY_BLACK_PIECES, "Black has more than sixteen pieces."),
        (chess.STATUS_OPPOSITE_CHECK, "The side that has just moved is in check, which can't happen. "
                                      "Change whose turn it is, or move a piece."),
        (chess.STATUS_TOO_MANY_CHECKERS, "The king is in check from too many pieces at once."),
        (chess.STATUS_IMPOSSIBLE_CHECK, "That check could not have come about in a real game."),
    ]
    for flag, message in checks:
        if status & flag:
            problems.append(message)
    if not problems and board.is_game_over():
        problems.append("The game would already be over in this position (checkmate, stalemate "
                        "or not enough pieces to mate). Please change it.")
    return problems


def tidy(board):
    """Remove castling rights and en passant squares that the position doesn't allow."""
    board.castling_rights = board.clean_castling_rights()
    if board.ep_square is not None and not board.has_legal_en_passant():
        board.ep_square = None
    return board


class BoardView:
    """The board and the palette of pieces: drawing them and handling the mouse.

    `left` and `right` are tkinter frames for the board and the palette.
    `on_edit` is called whenever the player changes the board.
    """

    def __init__(self, root, left, right, board, white_at_bottom=True, on_edit=None):
        import tkinter as tk
        from tkinter import font as tkfont
        self.board = board
        self.flipped = not white_at_bottom
        self.tool = None
        self.drag = None
        self.locked = False            # True: the board can be looked at but not changed
        self.shown = None              # another board to show instead, e.g. the true position
        self.marks = {}                # square -> colour, to highlight squares
        self.on_edit = on_edit or (lambda: None)

        self.canvas = tk.Canvas(left, width=8 * SQUARE + 20, height=8 * SQUARE + 20, highlightthickness=0)
        self.canvas.pack()
        families = set(tkfont.families(root))
        self.symbol_font = next((f for f in SYMBOL_FONTS if f in families), None)
        self.piece_font = (self.symbol_font or "TkDefaultFont",
                           int(SQUARE * 0.62) if self.symbol_font else int(SQUARE * 0.3), "bold")

        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", self.right_click)
        self.canvas.bind("<Button-2>", self.right_click)        # right-click on some Macs
        self._make_palette(tk, right)

    # --- drawing -----------------------------------------------------------
    def square_xy(self, sq):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        if self.flipped:
            f, r = 7 - f, 7 - r
        return 20 + f * SQUARE, (7 - r) * SQUARE

    def square_at(self, x, y):
        f, r = (x - 20) // SQUARE, 7 - y // SQUARE
        if not (0 <= f < 8 and 0 <= r < 8):
            return None
        if self.flipped:
            f, r = 7 - f, 7 - r
        return chess.square(f, r)

    def glyph(self, piece):
        if not self.symbol_font:
            return LETTERS[piece.piece_type]
        return (WHITE_GLYPHS if piece.color else BLACK_GLYPHS)[piece.piece_type]

    def draw_piece(self, x, y, piece):
        """Draw a piece centred on (x, y): a chess symbol, or a lettered disc."""
        if self.symbol_font:
            self.canvas.create_text(x, y, text=self.glyph(piece), font=self.piece_font, fill="black")
        else:
            r = SQUARE * 0.36
            fill, ink = ("white", "black") if piece.color else ("black", "white")
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline="black", width=2)
            self.canvas.create_text(x, y, text=self.glyph(piece), font=self.piece_font, fill=ink)

    def draw(self):
        canvas = self.canvas
        board = self.shown or self.board
        canvas.delete("all")
        dragging = self.drag and self.drag["moved"] and not self.shown
        for sq in chess.SQUARES:
            x, y = self.square_xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2
            colour = self.marks.get(sq) or (LIGHT if light else DARK)
            canvas.create_rectangle(x, y, x + SQUARE, y + SQUARE, fill=colour, outline="")
            piece = board.piece_at(sq)
            if piece and not (dragging and self.drag["from"] == sq):
                self.draw_piece(x + SQUARE / 2, y + SQUARE / 2, piece)
        for i in range(8):     # coordinates round the edge
            f = 7 - i if self.flipped else i
            r = i if self.flipped else 7 - i
            canvas.create_text(20 + i * SQUARE + SQUARE / 2, 8 * SQUARE + 10, text="abcdefgh"[f])
            canvas.create_text(10, i * SQUARE + SQUARE / 2, text=str(r + 1))
        if dragging:
            d = self.drag
            self.draw_piece(d["x"], d["y"], d["piece"])

    def flip(self):
        self.flipped = not self.flipped
        self.draw()

    def set_locked(self, locked):
        """Stop (or allow) changes, for example once a reconstruction has been checked."""
        self.locked = locked
        for b in self.tool_buttons:
            b.config(state="disabled" if locked else "normal")

    # --- mouse handling on the board ---------------------------------------
    def press(self, event):
        sq = self.square_at(event.x, event.y)
        if sq is None or self.locked:
            return
        self.drag = {"from": sq, "piece": self.board.piece_at(sq), "x": event.x, "y": event.y,
                     "start": (event.x, event.y), "moved": False}

    def motion(self, event):
        d = self.drag
        if not d or not d["piece"]:
            return
        if abs(event.x - d["start"][0]) + abs(event.y - d["start"][1]) > 6:
            d["moved"] = True
        d["x"], d["y"] = event.x, event.y
        self.draw()

    def release(self, event):
        d, self.drag = self.drag, None
        if not d:
            return
        board = self.board
        target = self.square_at(event.x, event.y)
        if d["moved"] and d["piece"]:
            board.remove_piece_at(d["from"])
            if target is not None:              # dropped off the board = removed
                board.set_piece_at(target, d["piece"])
            self.on_edit()
        elif self.tool == "remove":
            board.remove_piece_at(d["from"])
            self.on_edit()
        elif self.tool is not None:
            board.set_piece_at(d["from"], self.tool)
            self.on_edit()
        self.draw()

    def right_click(self, event):
        sq = self.square_at(event.x, event.y)
        if sq is not None and not self.locked:
            self.board.remove_piece_at(sq)
            self.on_edit()
            self.draw()

    # --- the palette of pieces ---------------------------------------------
    def _make_palette(self, tk, right):
        tk.Label(right, text="1. Click a piece below, then click squares to place it.\n"
                             "2. Drag pieces on the board to move them.\n"
                             "3. Right-click a piece (or use Remove) to take it off.",
                 justify="left").pack(anchor="w")
        palette = tk.Frame(right, pady=8)
        palette.pack(anchor="w")
        self.tool_buttons = []
        symbol_font = self.symbol_font

        for row, colour in enumerate((chess.WHITE, chess.BLACK)):
            for col, pt in enumerate((chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)):
                piece = chess.Piece(pt, colour)
                b = tk.Button(palette, text=self.glyph(piece), width=2,
                              font=(symbol_font, 24) if symbol_font else ("TkDefaultFont", 14, "bold"))
                if not symbol_font and colour == chess.BLACK:
                    b.config(fg="white", bg="#333333", activebackground="#555555", activeforeground="white")
                b.config(command=lambda p=piece, btn=b: self.select(p, btn))
                b.orig_bg = b.cget("bg")
                b.grid(row=row, column=col, padx=1, pady=1)
                self.tool_buttons.append(b)
        remove_btn = tk.Button(palette, text="Remove", width=8)
        remove_btn.config(command=lambda: self.select("remove", remove_btn))
        remove_btn.orig_bg = remove_btn.cget("bg")
        remove_btn.grid(row=2, column=0, columnspan=3, pady=4, sticky="w")
        self.tool_buttons.append(remove_btn)
        self.chosen = tk.Label(right, text="Selected: nothing yet", font=("TkDefaultFont", 10, "bold"))
        self.chosen.pack(anchor="w")

    def select(self, tool, button):
        self.tool = tool
        for b in self.tool_buttons:
            b.config(relief="raised", bg=b.orig_bg)
        button.config(relief="sunken", bg=HIGHLIGHT)
        if tool == "remove":
            self.chosen.config(text="Selected: Remove (click pieces to take them off)")
        else:
            colour = "White" if tool.color else "Black"
            self.chosen.config(text=f"Selected: {colour} {chess.piece_name(tool.piece_type)}")


def edit_position(start_fen=None, white_at_bottom=True):
    """Open the set-up window.  Returns a FEN string, or None if cancelled."""
    import tkinter as tk
    from tkinter import messagebox

    board = chess.Board(start_fen) if start_fen else chess.Board()
    state = {"result": None, "keep_rights": True}

    root = tk.Tk()
    root.title("The Different Engine - set up a position")
    root.resizable(False, False)

    left = tk.Frame(root, padx=10, pady=10)
    left.grid(row=0, column=0, sticky="n")
    right = tk.Frame(root, padx=10, pady=10)
    right.grid(row=0, column=1, sticky="n")

    def edited():
        state["keep_rights"] = False      # castling rights from a pasted FEN no longer apply
        message.config(text="")

    view = BoardView(root, left, right, board, white_at_bottom, on_edit=edited)

    turn = tk.StringVar(value="white" if board.turn else "black")
    turn_frame = tk.LabelFrame(right, text="Whose turn is it?", padx=6, pady=4)
    turn_frame.pack(anchor="w", fill="x", pady=4)
    tk.Radiobutton(turn_frame, text="White to move", variable=turn, value="white").pack(anchor="w")
    tk.Radiobutton(turn_frame, text="Black to move", variable=turn, value="black").pack(anchor="w")

    def set_board(new):
        board.set_fen(new.fen())
        turn.set("white" if board.turn else "black")
        view.draw()

    def usual():
        set_board(chess.Board())
        state["keep_rights"] = True

    def clear():
        board.clear()
        board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
        edited()
        view.draw()

    buttons = tk.Frame(right, pady=4)
    buttons.pack(anchor="w")
    tk.Button(buttons, text="Usual start", command=usual).grid(row=0, column=0, padx=2)
    tk.Button(buttons, text="Clear (kings only)", command=clear).grid(row=0, column=1, padx=2)
    tk.Button(buttons, text="Turn board round", command=view.flip).grid(row=0, column=2, padx=2)

    fen_frame = tk.LabelFrame(right, text="Shortcut: paste a FEN position", padx=6, pady=4)
    fen_frame.pack(anchor="w", fill="x", pady=8)
    fen_entry = tk.Entry(fen_frame, width=44)
    fen_entry.pack(anchor="w")

    def load_fen():
        text = fen_entry.get().strip()
        try:
            new = chess.Board(text)
        except ValueError:
            message.config(text="That FEN wasn't recognised. Please check it and try again.", fg="#b00000")
            return
        set_board(new)
        state["keep_rights"] = True
        message.config(text="Position loaded.", fg="#206020")

    tk.Button(fen_frame, text="Use this FEN", command=load_fen).pack(anchor="w", pady=2)
    fen_entry.bind("<Return>", lambda e: load_fen())

    message = tk.Label(right, text="", fg="#b00000", wraplength=330, justify="left")
    message.pack(anchor="w", pady=4)

    def confirm():
        candidate = board.copy(stack=False)
        candidate.turn = chess.WHITE if turn.get() == "white" else chess.BLACK
        if not state["keep_rights"]:
            candidate.set_castling_fen("KQkq")      # allowed if king and rook are still at home
            candidate.ep_square = None
        tidy(candidate)
        problems = position_problems(candidate)
        if problems:
            message.config(text="Please fix this first:\n- " + "\n- ".join(problems), fg="#b00000")
            messagebox.showwarning("Position needs fixing", "\n".join(problems), parent=root)
            return
        state["result"] = candidate.fen()
        root.destroy()

    end = tk.Frame(right, pady=6)
    end.pack(anchor="w")
    tk.Button(end, text="Start the game", command=confirm, bg="#4a7a3a", fg="white",
              font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, padx=2)
    tk.Button(end, text="Cancel", command=root.destroy).grid(row=0, column=1, padx=2)

    view.draw()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.mainloop()
    return state["result"]


if __name__ == "__main__":          # handy for trying the editor on its own
    print(edit_position())
