"""Looking back over a finished game.

Two things live here:

* the optional slip review: Stockfish, at full strength, goes through the
  player's moves and finds the two or three that gave away the most, so the
  player can say whether each was a chess mistake or a visualisation mistake;
* the short after-game summary (where the thread was lost, illegal attempts,
  position requests, the reconstruction score and the move-quality figures).

Only analyse_game() needs Stockfish.  Everything else works on plain data,
so it can be tested on any computer.

The move-quality figures are deliberately plain: the average centipawn loss
(a centipawn is a hundredth of a pawn) and how many moves matched the engine's
first choice.  They are not turned into an "accuracy rating"; the accuracy
score in this program is the reconstruction test.
"""

import chess
import chess.engine

from .moves import describe_move, join_words, number_word

SECONDS_PER_LOOK = 0.2     # two looks per player move: about 0.4 seconds a move, fine on a Raspberry Pi
CAP = 1000                 # evaluations and losses are capped, so one missed mate can't swamp the average
SMALL_SLIP = 50            # losses below this are ignored, unless there is nothing bigger


def _points(score, player):
    """An engine score from the player's point of view, in centipawns, capped."""
    value = score.pov(player).score(mate_score=10000)
    return max(-CAP, min(CAP, value))


def _score_after(engine, board, player, limit):
    """How good the position is for the player after their move."""
    if board.is_checkmate():
        return CAP                      # the player has just given mate
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    return _points(engine.analyse(board, limit)["score"], player)


def analyse_game(engine_path, start_board, moves, player, seconds=SECONDS_PER_LOOK, progress=None):
    """Look at each of the player's moves.  Returns a list with one entry per
    player move, or None if Stockfish could not be used."""
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    except Exception:
        return None
    limit = chess.engine.Limit(time=seconds)
    board = start_board.copy(stack=False)
    looked = []
    try:
        for move in moves:
            if board.turn == player:
                info = engine.analyse(board, limit)
                best = info["pv"][0]
                best_score = _points(info["score"], player)
                if move == best:
                    played_score = best_score
                else:
                    after = board.copy(stack=False)
                    after.push(move)
                    played_score = _score_after(engine, after, player, limit)
                looked.append({
                    "move_number": board.fullmove_number,
                    "san": board.san(move), "played": describe_move(board, move),
                    "best_san": board.san(best), "best": describe_move(board, best),
                    "loss": min(CAP, max(0, best_score - played_score)),
                    "matched": move == best,
                })
                if progress:
                    progress()
            board.push(move)
    except Exception:
        return None
    finally:
        try:
            engine.quit()
        except Exception:
            pass
    return looked


def biggest_slips(looked, how_many=3, small=SMALL_SLIP):
    """The moves that gave away the most, in the order they were played.
    Tiny losses are left out, unless there is nothing bigger."""
    ranked = sorted((i for i, m in enumerate(looked) if m["loss"] > 0), key=lambda i: -looked[i]["loss"])
    chosen = [i for i in ranked if looked[i]["loss"] >= small][:how_many]
    if not chosen:
        chosen = ranked[:2]
    return [looked[i] for i in sorted(chosen)]


def move_quality(looked):
    """Average centipawn loss and how many moves matched the engine's first choice."""
    if not looked:
        return None
    return {"moves": len(looked),
            "average_loss": round(sum(m["loss"] for m in looked) / len(looked)),
            "matched": sum(1 for m in looked if m["matched"])}


def how_big(loss):
    """A loss in plain English, roughly, without engine numbers."""
    if loss < 100:
        return "That was only a small slip."
    if loss < 200:
        return "That cost you roughly a pawn."
    if loss < 400:
        return "That cost you roughly two or three pawns' worth."
    return "That was a big slip, worth a piece or more."


def _lower_first(text):
    return text[0].lower() + text[1:]


def describe_slip(slip):
    return (f"At move {slip['move_number']} you played {_lower_first(slip['played'])}. "
            f"The engine preferred {_lower_first(slip['best'])}. {how_big(slip['loss'])}")


def classify_tag(text):
    """The player's verdict on a slip: "chess", "visualisation", "not sure" or "skipped".
    Returns None if the answer wasn't understood."""
    t = (text or "").lower()
    if any(w in t for w in ("not sure", "unsure", "don't know", "dont know", "no idea", "both")):
        return "not sure"
    if any(w in t for w in ("visual", "vision", "board", "lost", "picture", "memory")):
        return "visualisation"
    if "chess" in t:
        return "chess"
    if any(w in t.split() for w in ("skip", "pass", "next", "no")):
        return "skipped"
    return None


def describe_quality(quality):
    if not quality:
        return "There were none of your moves to look at."
    n, k = quality["moves"], quality["matched"]
    return (f"Your average centipawn loss was {quality['average_loss']} a move; a centipawn is a hundredth "
            f"of a pawn, and lower is better. {k} of your {n} {'move' if n == 1 else 'moves'} "
            f"matched the engine's first choice. These figures depend a lot on the kind of position, "
            "so compare them over many games rather than one.")


# ---------------------------------------------------------------------------
# The after-game summary
# ---------------------------------------------------------------------------

def _moves_list(numbers):
    numbers = list(numbers)
    return f"at move {numbers[0]}" if len(numbers) == 1 else "at moves " + join_words(numbers)


def _times(n):
    return {1: "once", 2: "twice"}.get(n, f"{number_word(n)} times")


def summary_lines(lost, illegal, requests, reconstruction=None, quality=None):
    """The short after-game summary, as plain-English sentences.

    lost:           the move at which the thread was first lost ("" or None for never)
    illegal:        list of {"move", "said", "reason"} for illegal attempts
    requests:       list of move numbers at which the position was read out
    reconstruction: the reconstruction score, or None if not taken
    quality:        move_quality(), or None if the game wasn't analysed
    """
    lines = ["Here is a short summary of the game."]
    lines.append(f"You first lost the thread at move {lost}." if lost
                 else "You didn't lose the thread of the position.")
    if illegal:
        n = len(illegal)
        lines.append(f"You tried {number_word(n)} illegal {'move' if n == 1 else 'moves'}, "
                     f"{_moves_list(sorted(set(a['move'] for a in illegal)))}.")
    else:
        lines.append("You didn't try any illegal moves.")
    if requests:
        lines.append(f"You asked for the position {_times(len(requests))}, {_moves_list(requests)}.")
    else:
        lines.append("You didn't ask for the position.")
    if reconstruction:
        r = reconstruction
        lines.append(f"In the reconstruction test you placed {r['correct']} of {r['total']} pieces "
                     f"correctly, {r['percent']} per cent"
                     + (", with nothing extra." if not r["extras"] else
                        f", with {number_word(r['extras'])} extra {'piece' if r['extras'] == 1 else 'pieces'}."))
    if quality:
        lines.append(f"Your average centipawn loss was {quality['average_loss']}, and "
                     f"{quality['matched']} of your {quality['moves']} moves matched the engine's first choice.")
    return lines
