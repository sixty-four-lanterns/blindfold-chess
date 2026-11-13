"""One game of blindfold chess, going round the loop in Figure 13.1:

    listen -> speech to text -> request? -> understand the move -> legal and clear?
    -> the engine replies -> text to speech -> game over?
"""

import datetime
import os
import random

import chess
import chess.pgn

from . import ratings, review, settings as config
from .engine import Engine, LEVELS, level_name, level_rating
from .moves import (parse, describe_move, describe_position, describe_game, parse_number,
                    is_illegal_attempt)
from .reconstruction import describe_reconstruction, short_score


class Stop(Exception):
    """The player wants to leave the program."""


class Interface:
    """Talking to the player: by voice (with typing allowed) or by keyboard only."""

    def __init__(self, speaker, listener=None):
        self.speaker = speaker
        self.listener = listener

    def say(self, text):
        self.speaker.say(text)

    def hear(self, prompt):
        try:
            if self.listener:
                return self.listener.listen("  " + prompt + " Press Enter, then speak (or type it): ")
            return input("  " + prompt + " ")
        except EOFError:
            raise Stop()

    def type_in(self, prompt):
        """Free text (such as a note) is always typed."""
        try:
            return input("  " + prompt + " ").strip()
        except EOFError:
            raise Stop()

    def ask(self, question, understand, prompt="Your answer:"):
        """Ask until `understand(text)` returns something other than None."""
        self.say(question)
        failures = 0
        while True:
            text = self.hear(prompt)
            value = understand(text.lower())
            if value is not None:
                return value
            failures += 1
            if self.listener and failures >= 2:
                prompt = "Please type your answer and press Enter:"
                self.say("Sorry, I didn't catch that. You can type the answer instead.")
            else:
                self.say("Sorry, I didn't catch that. " + question)

    def yes_no(self, question):
        def understand(text):
            words = text.split()
            if is_yes(words):
                return True
            if is_no(words):
                return False
            return None
        return self.ask(question, understand, "Yes or no?")


def is_yes(words):
    if "not" in words:              # "not sure" isn't a yes
        return False
    return any(w in ("yes", "y", "yeah", "yep", "please", "ok", "okay", "sure", "right", "correct") for w in words)


def is_no(words):
    return any(w in ("no", "n", "nope", "never", "skip") for w in words)


# ---------------------------------------------------------------------------
# Before the game
# ---------------------------------------------------------------------------

def limit_words(limit):
    if limit < 0:
        return "unlimited position requests"
    return f"{limit} position request{'' if limit == 1 else 's'}"


def choose_settings(ui, s, first_time):
    if not first_time:
        ui.say(f"Last time you chose {s['colour']}, engine level {s['level']}, "
               f"and {limit_words(s['position_limit'])}.")
        if ui.yes_no("Would you like the same settings again?"):
            return s

    def colour(text):
        for c in ("white", "black", "random"):
            if c in text:
                return c
        return None
    s["colour"] = ui.ask("Which colour would you like to play: white, black, or random?", colour)

    def level(text):
        n = parse_number(text)
        return n if n in LEVELS else None
    ui.say("The engine has eight levels. " +
           " ".join(f"Level {n} is about {level_rating(n)}." for n in (1, 3, 5, 8)))
    s["level"] = ui.ask("Which level would you like, from 1 to 8? If unsure, start low.", level)

    def limit(text):
        if "unlimited" in text or "no limit" in text:
            return -1
        n = parse_number(text)
        return n if n is not None and 0 <= n <= 99 else None
    s["position_limit"] = ui.ask("How many times may you ask me to read out the position in each game? "
                                 "Say a number, or 'unlimited'.", limit)
    return s


def choose_start(ui, s, player_colour):
    """Usual starting position, or a custom one set up with the mouse."""
    def start(text):
        if any(w in text for w in ("usual", "normal", "standard", "start")):
            return "usual"
        if any(w in text for w in ("custom", "set", "own", "fen")):
            return "custom"
        return None
    s["start"] = ui.ask("Shall we start from the usual opening position, or would you like to set up "
                        "a custom position? Say 'usual' or 'custom'.", start)
    if s["start"] == "usual":
        return chess.STARTING_FEN

    ui.say("A board will open in a new window. Set up the position with the mouse, choose whose turn it is, "
           "then click 'Start the game'.")
    try:
        from .board_editor import edit_position
        fen = edit_position(s.get("custom_fen") or None, white_at_bottom=(player_colour == chess.WHITE))
    except Exception:          # no tkinter, or no screen (for example over SSH)
        fen = typed_fen(ui)
    if not fen:
        ui.say("No position was chosen, so we'll use the usual starting position.")
        return chess.STARTING_FEN
    s["custom_fen"] = fen
    return fen


def typed_fen(ui):
    from .board_editor import position_problems, tidy
    ui.say("I couldn't open the set-up board on this computer, so please type or paste a FEN instead.")
    while True:
        text = ui.type_in("FEN (or press Enter for the usual start):")
        if not text:
            return None
        try:
            board = tidy(chess.Board(text))
        except ValueError:
            ui.say("That FEN wasn't recognised. Please try again.")
            continue
        problems = position_problems(board)
        if not problems:
            return board.fen()
        ui.say("That position can't be played: " + " ".join(problems))


# ---------------------------------------------------------------------------
# The game itself
# ---------------------------------------------------------------------------

HELP = ("Say your move as you would to a person, for example: knight f3, knight from g1 to f3, "
        "pawn takes d5, castles kingside, or pawn to e8 queen. If I mishear a letter, use the spelling "
        "alphabet: alpha, bravo, charlie, delta, echo, foxtrot, golf, hotel. You can also say: repeat, "
        "for my last move; position, to hear the whole position; lost thread, if you lose track of "
        "the position, so that I can note the move; draw, to offer a draw; resign; "
        "and rating, for your rating so far.")

CHECKPOINT = "This would be a good moment for a checkpoint."


def checkpoint_due(board, player, reminded):
    """Once every five moves, on the player's turn (moves 6, 11, 16 ...)."""
    n = board.fullmove_number
    return (board.turn == player and bool(board.move_stack) and n > 1 and n % 5 == 1
            and n not in reminded)


def play(ui, s, engine_path):
    """Play one game and record it.  Returns normally when the game is over."""
    colour = s["colour"] if s["colour"] != "random" else random.choice(["white", "black"])
    player = chess.WHITE if colour == "white" else chess.BLACK
    start_fen = choose_start(ui, s, player)
    config.save(s)

    board = chess.Board(start_fen)
    engine = Engine(engine_path, s["level"])
    limit, used = s["position_limit"], 0
    last_reply = None
    result = termination = None
    # For the after-game report: what went wrong, and when
    log = {"illegal": [], "requests": [], "lost_mark": None}
    reminded = set()

    ui.say(f"You are playing {colour} against {level_name(s['level'])}, with {limit_words(limit)}. "
           "Say help at any time.")
    if start_fen != chess.STARTING_FEN:
        ui.say("Here is the starting position. " + describe_position(board))
    try:
        while True:
            outcome = board.outcome(claim_draw=True)
            if outcome:
                result = outcome.result()
                termination = outcome.termination.name.replace("_", " ").capitalize()  # e.g. "Checkmate"
                ui.say(describe_outcome(outcome, player))
                break

            if board.turn != player:                         # 4. the engine replies
                move = engine.choose_move(board)
                last_reply = describe_move(board, move)
                board.push(move)
                ui.say(last_reply + ".")                     # 5. text to speech
                continue

            if s.get("checkpoint_reminders", True) and checkpoint_due(board, player, reminded):
                reminded.add(board.fullmove_number)
                ui.say(CHECKPOINT)

            heard = ui.hear("Your move:")                    # 1. listen, 2. speech to text
            if ui.listener:
                print(f"  (I heard: {heard or 'nothing'})")
            r = parse(board, heard)                          # request? / understand the move

            if r.kind == "problem":                          # not legal or not clear: ask again
                if is_illegal_attempt(r):
                    log["illegal"].append({"move": board.fullmove_number, "said": heard.strip(),
                                           "reason": r.message})
                ui.say(r.message)
            elif r.kind == "move":
                ui.say(describe_move(board, r.move) + ".")
                board.push(r.move)
            elif r.command == "repeat":
                ui.say(f"My last move was {last_reply[0].lower() + last_reply[1:]}." if last_reply
                       else "I haven't made a move yet.")
            elif r.command == "position":
                if limit < 0 or used < limit:
                    used += 1
                    log["requests"].append(board.fullmove_number)
                    ui.say(describe_position(board))
                    if limit >= 0:
                        ui.say(f"That was position request {used} of {limit}.")
                else:
                    ui.say(f"I'm sorry, you have used all {limit} of your position requests for this game. "
                           "Try to rebuild the position in your mind, then tell me your move.")
            elif r.command == "lost thread":
                if log["lost_mark"] is None:
                    log["lost_mark"] = board.fullmove_number
                    ui.say(f"I'll note that you lost the thread at move {log['lost_mark']}. "
                           "Take your time; your move when you're ready.")
                else:
                    ui.say(f"I've already noted that you first lost the thread at move {log['lost_mark']}, "
                           "so I'll keep that. Your move when you're ready.")
            elif r.command == "help":
                left = "unlimited" if limit < 0 else str(limit - used)
                ui.say(HELP + f" Position requests left: {left}.")
            elif r.command == "rating":
                for line in ratings.report(ratings.read_games(config.RATING_LOG)):
                    ui.say(line)
            elif r.command == "resign":
                if ui.yes_no("Do you really want to resign?"):
                    result = "0-1" if player == chess.WHITE else "1-0"
                    termination = "Player resigned"
                    ui.say("You resign. Well played, and better luck next game.")
                    break
                ui.say("Then the game goes on. Your move.")
            elif r.command == "draw":
                if board.fullmove_number < 20 and board.root().fen() == chess.STARTING_FEN:
                    ui.say("It's a little early for a draw, so let's play on. Your move.")
                elif engine.accepts_draw(board, not player):
                    result, termination = "1/2-1/2", "Draw agreed"
                    ui.say("I accept your draw offer. The game is drawn.")
                    break
                ui.say("Thank you, but I'd rather play on. Your move.")
            elif r.command == "quit":
                if ui.yes_no("Stop now without saving this game?"):
                    raise Stop()
    finally:
        engine.close()

    finish(ui, s, board, start_fen, player, result, termination, used, log, engine_path)


def describe_outcome(outcome, player):
    if outcome.termination == chess.Termination.CHECKMATE:
        return "Checkmate. You win, well done!" if outcome.winner == player else "Checkmate. I win this time."
    reasons = {
        chess.Termination.STALEMATE: "Stalemate. The game is drawn.",
        chess.Termination.INSUFFICIENT_MATERIAL: "Neither side has enough pieces to checkmate. The game is drawn.",
        chess.Termination.THREEFOLD_REPETITION: "The same position has come up three times. The game is drawn.",
        chess.Termination.FIVEFOLD_REPETITION: "The same position has come up five times. The game is drawn.",
        chess.Termination.FIFTY_MOVES: "Fifty moves without a capture or pawn move. The game is drawn.",
        chess.Termination.SEVENTYFIVE_MOVES: "Seventy-five moves without a capture or pawn move. The game is drawn.",
    }
    return reasons.get(outcome.termination, "The game is over.")


# ---------------------------------------------------------------------------
# After the game: PGN, rating log and the strength gauge
# ---------------------------------------------------------------------------

def lost_thread_question(ui, marked=None, illegal=()):
    """Ask where the thread was first lost, starting from what we already know.
    Returns the move number as text, or "" for never."""
    def move_number(text):
        if any(w in text for w in ("never", "didn't", "did not", "none")):
            return ""
        n = parse_number(text)
        return str(n) if n is not None and n > 0 else None

    plain = ("At which move did you first lose the thread of the position? "
             "Say the move number, or 'never'.")
    if marked:
        suggestion = marked
        question = (f"During the game you told me you had lost the thread at move {marked}. "
                    "Is that right? Say yes, another move number, or 'never'.")
    elif illegal:
        first = illegal[0]
        suggestion = first["move"]
        question = (f"Your first illegal move attempt was at move {first['move']}, when you said "
                    f"'{first['said']}'. Was that when you first lost the thread? "
                    "Say yes, the move number when you did, or 'never'.")
    else:
        return ui.ask(plain, move_number)

    def understand(text):
        number = move_number(text)
        if number is not None:
            return number
        if is_yes(text.split()):
            return str(suggestion)
        if is_no(text.split()):
            return "ask"
        return None
    answer = ui.ask(question, understand)
    return ui.ask(plain, move_number) if answer == "ask" else answer


def reconstruction_test(ui, board, player):
    """The reconstruction test on a blank board.  Returns the score, or None."""
    if not ui.yes_no("Would you like to reconstruct the final position from memory, on a blank board?"):
        return None
    ui.say("A blank board will open in a new window. Put the pieces where you think they stood at the "
           "end of the game, then click 'Check my position'. Click 'Skip' if you change your mind.")
    try:
        from .reconstruction import reconstruct_position
        score = reconstruct_position(board, white_at_bottom=(player == chess.WHITE),
                                     on_score=lambda sc: ui.say(describe_reconstruction(sc)))
    except Exception:          # no tkinter, or no screen (for example over SSH)
        ui.say("I couldn't open a board window on this computer, so we'll skip the reconstruction test "
               "this time. It needs a screen, and tkinter; on Linux, installing python3-tk adds it.")
        return None
    if score is None:
        ui.say("No reconstruction this time.")
    return score


def slip_review(ui, board, player, engine_path):
    """Optionally look through the game with Stockfish for the biggest slips.
    Returns {"quality": ..., "slips": [...]}, or None if not done."""
    if not engine_path or not board.move_stack:
        return None
    if not ui.yes_no("Would you like me to look through the game for the two or three biggest slips?"):
        return None
    ui.say("I'm looking through the game now. This may take a little while.")
    looked = review.analyse_game(engine_path, board.root(), board.move_stack, player,
                                 progress=lambda: print(".", end="", flush=True))
    print()
    if looked is None:
        ui.say("Sorry, I couldn't look through the game this time, so we'll carry on without it.")
        return None
    slips = review.biggest_slips(looked)
    if not slips:
        ui.say("I didn't find any slips worth mentioning. Well played.")
    for slip in slips:
        ui.say(review.describe_slip(slip))
        slip["tag"] = ui.ask("Was that a chess mistake or a visualisation mistake? "
                             "Say chess, visualisation, not sure, or skip.", review.classify_tag)
    return {"quality": review.move_quality(looked), "slips": slips}


def save_pgn(path, board, headers):
    game = chess.pgn.Game.from_board(board)
    # Keep headers plain, so every chess program can read the file
    game.headers.update({k: str(v).replace('"', "'").replace("\\", "/") for k, v in headers.items()})
    pgn_text = str(game)
    with open(path, "w", encoding="utf-8") as f:
        f.write(pgn_text + "\n")
    return pgn_text


def illegal_header(illegal):
    """Compact form for the PGN file: '2 (5: knight e5; 9: Bc4)'."""
    if not illegal:
        return "0"
    return f"{len(illegal)} (" + "; ".join(f"{a['move']}: {a['said']}" for a in illegal) + ")"


def slips_text(slips):
    """Compact form for the PGN file and the log: '7 Nf6 visualisation; 12 Bxe4 chess'."""
    return "; ".join(f"{m['move_number']} {m['san']} {m.get('tag') or 'untagged'}" for m in slips)


def finish(ui, s, board, start_fen, player, result, termination, used, log=None, engine_path=None):
    log = log or {}
    illegal, requests = log.get("illegal", []), log.get("requests", [])
    now = datetime.datetime.now()
    score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
    if player == chess.BLACK and result in ("1-0", "0-1"):
        score = 1.0 - score
    score_text = {1.0: "1", 0.5: "0.5", 0.0: "0"}[score]

    # Questions for the rating log (Chapter 14)
    lost = lost_thread_question(ui, log.get("lost_mark"), illegal)
    breaks = "yes" if ui.yes_no("Did you break any of your honesty rules, for example by taking a peek?") else ""
    notes = ui.type_in("Type a one-line note about the game for your log, or just press Enter to skip:")

    # Save the PGN straight away, so that nothing below can lose the game.
    # (It isn't shown on screen yet, as that would give away the final position.)
    engine_name = f"The Different Engine, {level_name(s['level'])}"
    headers = {
        "Event": "Blindfold game", "Site": "The Different Engine", "Date": now.strftime("%Y.%m.%d"),
        "Round": "-", "White": "Player" if player == chess.WHITE else engine_name,
        "Black": engine_name if player == chess.WHITE else "Player", "Result": result,
        "TimeControl": "-", "Termination": "normal", "Ending": termination,
        "PositionRequests": str(used), "FirstLostThread": lost or "never",
        "PositionRequestMoves": ", ".join(str(n) for n in requests) or "-",
        "IllegalAttempts": illegal_header(illegal),
    }
    if log.get("lost_mark"):
        headers["LostThreadMarked"] = str(log["lost_mark"])
    if board.root().fen() != chess.STARTING_FEN:
        headers["SetUp"], headers["FEN"] = "1", board.root().fen()

    os.makedirs(config.GAMES_DIR, exist_ok=True)
    base = f"{now:%Y-%m-%d_%H%M}_{'white' if player else 'black'}_level{s['level']}"
    path = os.path.join(config.GAMES_DIR, base + ".pgn")
    n = 2
    while os.path.exists(path):
        path = os.path.join(config.GAMES_DIR, f"{base}_{n}.pgn")
        n += 1
    pgn_text = save_pgn(path, board, headers)
    ui.say(f"I've saved the game in the games folder, in a file called {os.path.basename(path)}.")

    opponent = f"Stockfish level {s['level']}"
    row = {
        "Date": now.strftime("%Y-%m-%d"), "Opponent": opponent, "Opponent rating": level_rating(s["level"]),
        "Colour": "White" if player == chess.WHITE else "Black", "Time control": "untimed",
        "Result": score_text, "First lost thread": lost, "Rule breaks": breaks, "Notes": notes,
        "Position requests": used, "How it ended": termination,
        "Start position": "usual" if start_fen == chess.STARTING_FEN else start_fen,
        "PGN file": os.path.relpath(path, config.APP_DIR),
        "Illegal attempts": len(illegal),
        "Illegal attempt moves": ", ".join(str(a["move"]) for a in illegal),
        "Position request moves": ", ".join(str(n) for n in requests),
    }

    # The reconstruction test and the slip review.  Whatever happens here, the
    # game still goes into the rating log (the "finally" below).
    reconstruction = looked = None
    try:
        try:
            reconstruction = reconstruction_test(ui, board, player)
        except Stop:
            raise
        except Exception:
            ui.say("Something went wrong with the reconstruction test, so we'll skip it.")
        try:
            looked = slip_review(ui, board, player, engine_path)
        except Stop:
            raise
        except Exception:
            ui.say("Something went wrong while looking through the game, so we'll skip that.")
    finally:
        if reconstruction:
            headers["Reconstruction"] = short_score(reconstruction)
            row["Reconstruction"] = f"{reconstruction['correct']}/{reconstruction['total']}"
            row["Reconstruction per cent"] = reconstruction["percent"]
        quality = looked["quality"] if looked else None
        if quality:
            headers["AverageCentipawnLoss"] = str(quality["average_loss"])
            headers["EngineMatches"] = f"{quality['matched']}/{quality['moves']}"
            row["Average centipawn loss"] = quality["average_loss"]
            row["Engine matches"] = f"{quality['matched']}/{quality['moves']}"
        if looked and looked["slips"]:
            headers["Slips"] = row["Slips"] = slips_text(looked["slips"])
        if reconstruction or looked:
            try:
                pgn_text = save_pgn(path, board, headers)
            except OSError:
                pass
        ratings.append_game(config.RATING_LOG, row)

    print("\n" + "-" * 60 + "\n" + pgn_text + "\n" + "-" * 60)
    print(f"  Full location of the game: {path}\n")

    for line in review.summary_lines(lost, illegal, requests, reconstruction, quality):
        ui.say(line)
    print()
    for line in ratings.report(ratings.read_games(config.RATING_LOG), opponent):
        ui.say(line)
    print(f"  (Your rating log is in {config.RATING_LOG}; it opens in any spreadsheet.)\n")

    if ui.yes_no("Would you like me to read the moves of the game aloud?"):
        for line in describe_game(board.root(), board.move_stack):
            ui.say(line)
