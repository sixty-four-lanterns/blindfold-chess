"""The reconstruction test: after the game, set up the final position from memory.

The board starts empty.  Nothing about the true position is shown until the
player clicks 'Check my position'.  The score is simple, to match the book's
short training games: one point for each piece (the right type and colour) on
its correct square.  A perfect score means every piece is in place and nothing
extra has been added.

score_reconstruction() and describe_reconstruction() need no window, so they
can be tested on any computer.  The window itself uses tkinter, like the
set-up board.
"""

import chess

from .moves import join_words, number_word

CORRECT, WRONG, MISSING = "#8fd18f", "#e57373", "#f4b350"     # green, red, amber

def _pieces(board):
    """square -> piece, from a chess.Board or a plain dictionary."""
    return board.piece_map() if hasattr(board, "piece_map") else dict(board)


def score_reconstruction(true_board, guessed_board):
    """Compare the player's board with the true one.

    correct: the right piece on the right square
    missing: a square that should hold a piece, left empty
    wrong:   a square that should hold a piece, holding a different one
    extras:  a piece on a square that should be empty
    percent: correct pieces as a percentage of the pieces in the true position
    """
    truth, guess = _pieces(true_board), _pieces(guessed_board)
    correct = sorted(sq for sq, piece in truth.items() if guess.get(sq) == piece)
    missing = sorted(sq for sq in truth if sq not in guess)
    wrong = sorted(sq for sq, piece in truth.items() if sq in guess and guess[sq] != piece)
    extras = sorted(sq for sq in guess if sq not in truth)
    total = len(truth)
    if total:
        percent = 100 * len(correct) / total
    else:
        percent = 100 if not guess else 0
    return {
        "correct": len(correct), "missing": len(missing), "wrong": len(wrong), "extras": len(extras),
        "total": total, "placed": len(guess), "percent": int(percent + 0.5),
        "perfect": len(correct) == total and not extras,
        "correct_squares": correct, "missing_squares": missing,
        "wrong_squares": wrong, "extra_squares": extras,
    }


def short_score(score):
    """A compact form for the PGN file and the log: "24/28, 86%"."""
    return f"{score['correct']}/{score['total']}, {score['percent']}%"


def describe_reconstruction(score):
    """The score in plain English, for speaking aloud."""
    c, total, extras = score["correct"], score["total"], score["extras"]
    if total == 0:
        if not extras:
            return "The final board was empty, and you left it empty. Perfect."
        return "The final board was empty, but you placed some pieces on it."
    if score["perfect"]:
        return (f"You placed all {total} pieces on the correct squares, with nothing extra. "
                "A perfect reconstruction, well done!")
    text = (f"You placed {c} of {total} pieces on the correct square, "
            f"which is {score['percent']} per cent.")
    details = []
    w, m = score["wrong"], score["missing"]
    if w:
        details.append(f"on {number_word(w)} {'square' if w == 1 else 'squares'} you put the wrong piece")
    if m:
        details.append(f"{number_word(m)} {'piece was' if m == 1 else 'pieces were'} missing")
    if extras:
        details.append(f"you placed {number_word(extras)} extra {'piece' if extras == 1 else 'pieces'}")
    if details:
        joined = join_words(details)
        text += " " + joined[0].upper() + joined[1:] + "."
    return text


def marks_for(score):
    """Square colours for comparing the two boards after the check."""
    marks = {}
    for sq in score["correct_squares"]:
        marks[sq] = CORRECT
    for sq in score["wrong_squares"] + score["extra_squares"]:
        marks[sq] = WRONG
    for sq in score["missing_squares"]:
        marks[sq] = MISSING
    return marks


def reconstruct_position(true_board, white_at_bottom=True, on_score=None):
    """Open the reconstruction window on an empty board.

    Returns the score (see score_reconstruction), or None if the player
    skipped the test.  `on_score(score)` is called once the position has been
    checked, so that the score can be spoken.
    """
    import tkinter as tk
    from .board_editor import BoardView

    truth = true_board.copy(stack=False)
    guess = chess.Board(None)             # an empty board: nothing is given away
    state = {"score": None, "truth_shown": False}

    root = tk.Tk()
    root.title("The Different Engine \u2014 reconstruct the final position")
    root.resizable(False, False)

    left = tk.Frame(root, padx=10, pady=10)
    left.grid(row=0, column=0, sticky="n")
    right = tk.Frame(root, padx=10, pady=10)
    right.grid(row=0, column=1, sticky="n")

    view = BoardView(root, left, right, guess, white_at_bottom)

    tk.Label(right, text="Put every piece where you think it stood at the end of the game.\n"
                         "Nothing is checked until you click 'Check my position'.",
             justify="left", wraplength=340).pack(anchor="w", pady=4)

    def clear():
        guess.clear()
        view.draw()

    tools = tk.Frame(right, pady=4)
    tools.pack(anchor="w")
    clear_btn = tk.Button(tools, text="Clear the board", command=clear)
    clear_btn.grid(row=0, column=0, padx=2)
    tk.Button(tools, text="Turn board round", command=view.flip).grid(row=0, column=1, padx=2)

    message = tk.Label(right, text="", wraplength=340, justify="left", font=("TkDefaultFont", 11, "bold"))
    message.pack(anchor="w", pady=6)
    legend = tk.Label(right, text="", wraplength=340, justify="left")
    legend.pack(anchor="w")

    def compare():
        state["truth_shown"] = not state["truth_shown"]
        view.shown = truth if state["truth_shown"] else None
        compare_btn.config(text="Show my position" if state["truth_shown"] else "Show the true position")
        root.title("The Different Engine \u2014 " +
                   ("the true final position" if state["truth_shown"] else "your reconstruction"))
        view.draw()

    def check():
        score = score_reconstruction(truth, guess)
        state["score"] = score
        view.set_locked(True)
        clear_btn.config(state="disabled")
        check_btn.config(state="disabled")
        skip_btn.config(text="Close")
        message.config(text=describe_reconstruction(score), fg="#206020" if score["perfect"] else "black")
        view.marks = marks_for(score)
        legend.config(text="Green: the right piece on the right square.\n"
                           "Red: the wrong piece, or a piece that shouldn't be there.\n"
                           "Amber: a piece you left out.")
        compare_btn.config(state="normal")
        root.title("The Different Engine \u2014 your reconstruction")
        view.draw()
        if on_score:
            root.after(100, lambda: on_score(score))

    end = tk.Frame(right, pady=6)
    end.pack(anchor="w")
    check_btn = tk.Button(end, text="Check my position", command=check, bg="#4a7a3a", fg="white",
                          font=("TkDefaultFont", 11, "bold"))
    check_btn.grid(row=0, column=0, padx=2)
    compare_btn = tk.Button(end, text="Show the true position", command=compare, state="disabled")
    compare_btn.grid(row=0, column=1, padx=2)
    skip_btn = tk.Button(end, text="Skip", command=root.destroy)
    skip_btn.grid(row=0, column=2, padx=2)

    view.draw()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    root.mainloop()
    return state["score"]


if __name__ == "__main__":          # handy for trying the window on its own
    print(reconstruct_position(chess.Board()))
