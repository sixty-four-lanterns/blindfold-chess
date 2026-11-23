"""One game of blindfold chess, going round the loop in Figure 13.1:

    listen -> speech to text -> request? -> understand the move -> legal and clear?
    -> the engine replies -> text to speech -> game over?
"""

import datetime
import os
import random
import re

import chess
import chess.pgn

from . import drill, milestones, ratings, review, settings as config
from .engine import Engine, LEVELS, level_name, level_rating
from .moves import (parse, describe_move, describe_position, describe_game, parse_number,
                    format_move_list, is_illegal_attempt, is_help_command, number_word,
                    special_command, parse_level_command)
from .reconstruction import describe_reconstruction, short_score


class Stop(Exception):
    """The player wants to leave the program."""


class Interface:
    """Talking to the player: by voice (with typing allowed) or by keyboard only."""

    def __init__(self, speaker, listener=None):
        self.speaker = speaker
        self.listener = listener
        self.help_context = None
        self.help_requests_left = None

    def say(self, text):
        self.speaker.say(text)

    def hear(self, prompt):
        """Listen or read a line.  'help' prints the command list and listens again.

        Nothing is spoken for help.  In hands-free mode the listener is started
        again after the list has been printed, so the next move can be said as usual.
        """
        try:
            while True:
                if self.listener:
                    text = self.listener.listen("  " + prompt + " Press Enter, then speak (or type it): ")
                    self.last_thinking_seconds = getattr(self.listener, "last_thinking_seconds", None)
                else:
                    text = input("  " + prompt + " ")
                    # Text mode: thinking time is measured by the caller if it started
                    # a clock around this call; leave last_thinking_seconds unset.
                    self.last_thinking_seconds = None
                if is_help_command(text):
                    print_help(self.help_context, self.help_requests_left)
                    continue
                return text
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
            value = understand((text or "").lower())
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
    word = number_word(limit)
    return f"{word} position request{'' if limit == 1 else 's'}"


def choose_settings(ui, s, first_time, offer_same=True):
    if offer_same and not first_time:
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

    # Instructions only: the window is about to open, so nothing is spoken.
    print("  Set up the position with the mouse, choose whose turn it is, then click 'Start the game'.")
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


def saved_start_fen(s):
    """Use the saved start without asking.  Falls back to the usual opening."""
    if s.get("start") == "custom" and s.get("custom_fen"):
        try:
            return chess.Board(s["custom_fen"]).fen()
        except ValueError:
            pass
    return chess.STARTING_FEN


def pregame_command(text):
    """Colour or settings, said before the first move.  Returns a keyword, or None."""
    if not text or not str(text).strip():
        return None
    t = re.sub(r"[^a-z\s]", " ", str(text).lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    if "settings" in t.split() or t in ("set up", "setup"):
        return "settings"
    if re.search(r"\bswitch\s+(colour|color|colours|colors|sides)\b", t):
        return "switch"
    if re.search(r"\bplay(?:\s+as)?\s+black\b", t) or t == "black":
        return "black"
    if re.search(r"\bplay(?:\s+as)?\s+white\b", t) or t == "white":
        return "white"
    if t in ("random", "play random", "play as random") or re.search(r"\brandom\s+(colour|color)\b", t):
        return "random"
    return None


def resolve_colour(command, current):
    """Turn a pre-game colour command into 'white' or 'black' for this game,
    and the value to store in settings ('white', 'black' or 'random')."""
    if command == "switch":
        new = "black" if current == "white" else "white"
        return new, new
    if command == "random":
        return random.choice(["white", "black"]), "random"
    return command, command


def session_command(text):
    """Commands for before the first move, between games, or (for progress) at any time."""
    special = special_command(text)
    session = {
        "square drill": "drill",
        "reset rating": "reset-rating",
        "progress": "progress",
        "rating": "rating",
        "help": "help",
        "level": "level",
        "show board": "show-board",
        "practice board": "practice-board",
    }
    if special in session:
        return session[special]
    return pregame_command(text)


def reset_rating(ui, path=None, today=None):
    """Ask for confirmation, then archive the rating log.  Returns the archive path, or None."""
    path = path or config.RATING_LOG
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        ui.say("There are no games in your rating log yet, so there is nothing to reset.")
        return None
    if not ui.yes_no("This will start your rating again from scratch. Your old games will be kept "
                     "in a dated file. Do you want to reset your rating?"):
        ui.say("Your rating is unchanged.")
        return False
    archive = ratings.archive_and_reset(path, today=today)
    if not archive:
        ui.say("There are no games in your rating log yet, so there is nothing to reset.")
        return None
    ui.say(f"Your rating has been reset. Your old games are kept in {os.path.basename(archive)}.")
    print(f"  (The archived log is {archive}.)")
    return archive


def show_progress(ui):
    for line in milestones.progress_lines():
        ui.say(line)


def run_square_drill(ui):
    previous = (getattr(ui, "help_context", None), getattr(ui, "help_requests_left", None))
    ui.help_context, ui.help_requests_left = "drill", None
    try:
        drill.run_drill(ui)
    finally:
        ui.help_context, ui.help_requests_left = previous
    milestones.update_and_announce(ui)


def remember_game(ui, board, player, engine_path=None, headers=None):
    """Keep a copy of the finished game (with its moves) for 'show board'."""
    ui.last_game = {"board": board.copy(), "player": player,
                    "engine_path": engine_path, "headers": dict(headers or {})}


def show_last_board(ui, engine_path=None):
    """Open the game viewer on the last game of this session (between games only)."""
    from . import replay_viewer
    last = getattr(ui, "last_game", None)
    engine_path = engine_path or (last or {}).get("engine_path") or getattr(ui, "engine_path", None)
    return replay_viewer.show_board(ui, last, engine_path=engine_path, games_dir=config.GAMES_DIR)


def between_games(ui, s=None):
    """True if the player would like another game.

    Also accepts square drill, progress, rating, reset rating, a level
    change and 'show board' (look through the last game, or load a PGN)
    between games.  'practice board' starts the next game straight away as
    an unrated practice-board game.
    """
    def understand(text):
        cmd = session_command(text)
        if cmd == "level":
            return ("level", text)
        if cmd in ("drill", "progress", "reset-rating", "rating", "help", "show-board",
                   "practice-board"):
            return cmd
        words = (text or "").split()
        if is_yes(words):
            return "play"
        if is_no(words):
            return "quit"
        return None

    while True:
        ui.help_context, ui.help_requests_left = "between", None
        # Shown on screen only; just "Enter command." is spoken.
        print("  Another game? Say yes or no. Or say: show board, practice board, square drill, "
              "milestones, rating, reset rating, level 1 to 8, or help.")
        pending = getattr(ui, "pending_command", None)   # said at the review question
        ui.pending_command = None
        choice = understand(pending) if pending else None
        if choice is None:
            choice = ui.ask("Enter command.", understand, "Yes, no, or a command?")
        if choice == "play":
            return True
        if choice == "practice-board":
            ui.practice_next = True              # the next game is a practice game
            return True
        if choice == "quit":
            return False
        if choice == "help":
            print_help("between")
        elif isinstance(choice, tuple) and choice[0] == "level":
            if s is None:
                s = config.load()
            apply_level_command(ui, s, choice[1])
        elif choice == "show-board":
            show_last_board(ui)
        elif choice == "drill":
            run_square_drill(ui)
        elif choice == "progress":
            show_progress(ui)
        elif choice == "rating":
            ui.say(ratings.spoken_rating(ratings.read_games(config.RATING_LOG)))
        elif choice == "reset-rating":
            reset_rating(ui)


# ---------------------------------------------------------------------------
# The game itself
# ---------------------------------------------------------------------------

# Which command groups are "now available" in each situation.
# "before" (a game has started but the player has not yet moved) includes
# both in-game commands and the pre-game / between-games commands.
HELP_NOW = {
    "during": {"during"},
    "before": {"during", "before"},
    "between": {"before"},
    "after": {"after"},
    "review": {"after"},
    "drill": {"drill"},
}


def _help_requests_line(requests_left):
    if requests_left is None:
        return None
    if isinstance(requests_left, str):
        text = requests_left
    elif requests_left < 0:
        text = "unlimited"
    else:
        text = str(requests_left)
    return f"  Position requests left: {text}"


def format_help(context=None, requests_left=None):
    """A compact, grouped command list for the screen.  Nothing here is spoken."""
    during = [
        "  repeat                         Repeat the engine's last move",
        "  last move                      Your last move and my reply",
        "  take back / undo / go back     Undo your last move and its reply",
        "  position                       Hear the position (uses a request)",
        "  show moves                     The whole game on screen (uses a position request)",
        "  practice board                 Unrated game with a board showing whose pieces are where",
    ]
    requests = _help_requests_line(requests_left)
    if requests and context in ("during", "before", None):
        during.append(requests)
    during += [
        "  lost thread                    Note that you have lost the thread",
        "  rating                         Your current blindfold rating",
        "  milestones / progress          Your milestones so far",
        "  help                           Show this list (nothing is spoken)",
        "  level 1 to 8                   Change the engine's level",
        "  draw                           Offer a draw",
        "  resign                         Resign (it will check first)",
    ]
    groups = [
        ("during", "During a game", during),
        ("before", "Before your first move, or between games", [
            "  settings                       Colour, level, requests and start",
            "  level 1 to 8                   Change the engine's level",
            "  play white / play black / switch colours / random",
            "  square drill / drill           The 20-square colour test",
            "  reset rating                   Start your rating again",
            "  show board                     See the last game and step through it, or load a PGN",
            "  practice board                 Unrated game with a board showing whose pieces are where",
        ]),
        ("after", "After a game", [
            "  review                         Or press Enter to skip",
            "  In the review: chess / visualisation / not sure / skip",
            "  never                          You never lost the thread",
        ]),
        ("drill", "Square-colour drill", [
            "  light / dark                   White and black are fine too",
        ]),
    ]
    now = HELP_NOW.get(context, set())
    lines = ["Commands"]
    current = [g for g in groups if g[0] in now]
    later = [g for g in groups if g[0] not in now]

    def add(key, title, body, mark):
        heading = f"Now available -- {title}" if mark else title
        if lines[-1] not in ("Commands", "Also available at other times"):
            lines.append("")
        lines.append(heading)
        lines.extend(body)

    if current:
        for key, title, body in current:
            add(key, title, body, True)
        if later:
            lines.append("")
            lines.append("Also available at other times")
            for key, title, body in later:
                add(key, title, body, False)
    else:
        for key, title, body in groups:
            add(key, title, body, False)
    return "\n".join(lines)


def print_help(context=None, requests_left=None):
    """Print the command list to the screen.  Does not speak."""
    print()
    print(format_help(context, requests_left))
    print()

CHECKPOINT = "This would be a good moment for a checkpoint."


def checkpoint_due(board, player, reminded):
    """Once every five moves, on the player's turn (moves 6, 11, 16 ...)."""
    n = board.fullmove_number
    return (board.turn == player and bool(board.move_stack) and n > 1 and n % 5 == 1
            and n not in reminded)


def rating_for_status(games=None):
    """Short rating for the on-screen status line, e.g. '1233 (14 games)'."""
    if games is None:
        games = ratings.read_games(config.RATING_LOG)
    window = ratings.recent(games)
    p = ratings.performance(window)
    if not p:
        return "no rating yet"
    noun = "game" if p["games"] == 1 else "games"
    return f"{p['performance']} ({p['games']} {noun})"


def format_status(board, player, level, limit, used, games=None, milestones_count=None, takebacks=0):
    """A compact status line: move, colour, level, requests left, rating and milestones.

    Never includes the board, the moves, or an evaluation.
    Take-backs are shown only when there has been at least one in this game.
    """
    colour = "White" if player == chess.WHITE else "Black"
    left = "unlimited" if limit < 0 else str(max(0, limit - used))
    if milestones_count is None:
        milestones_count = milestones.counts()
    earned, total = milestones_count
    line = (f"Move {board.fullmove_number} | You: {colour} | Level {level} | "
            f"Position requests left: {left} | Blindfold rating: {rating_for_status(games)} | "
            f"Milestones {earned}/{total}")
    if takebacks:
        line += f" | Take-backs: {takebacks}"
    return line


def print_status(board, player, level, limit, used, games=None, takebacks=0):
    print("  " + format_status(board, player, level, limit, used, games, takebacks=takebacks))


def _as_spoken(text):
    """Lower-case the first letter so the phrase sits mid-sentence."""
    return text[0].lower() + text[1:] if text else text


def _plain_move(text):
    """Drop a trailing check or checkmate from a move description."""
    return re.sub(r", (?:checkmate|check)$", "", text or "")


def _replay(board):
    """The starting position of `board` and the moves that led to it."""
    start = board.copy()
    moves = []
    while start.move_stack:
        moves.append(start.pop())
    moves.reverse()
    return start, moves


def player_move_count(board, player):
    """How many moves the player has made from the starting position."""
    start, moves = _replay(board)
    count = 0
    for move in moves:
        if start.turn == player:
            count += 1
        start.push(move)
    return count


def last_engine_reply(board, player):
    """The engine's last move still on the board, in words, or None."""
    if not board.move_stack or board.turn != player:
        return None
    previous = board.copy()
    move = previous.pop()
    return describe_move(previous, move)


def last_moves_spoken(board, player):
    """Words for the 'last move' command, taken from the current board.

    Mentions the player's last move and, if there is one, the engine's reply
    after it.  An earlier engine move is not described as a reply.  Reflects
    take-backs, because it reads the history as it stands now.
    """
    start, moves = _replay(board)
    if not moves:
        return "No moves yet."

    cursor = start.copy()
    last_player_idx = last_engine_idx = None
    descriptions = []
    for i, move in enumerate(moves):
        descriptions.append(describe_move(cursor, move))
        if cursor.turn == player:
            last_player_idx = i
        else:
            last_engine_idx = i
        cursor.push(move)

    if last_player_idx is None:
        return f"I played {_as_spoken(_plain_move(descriptions[last_engine_idx]))}."
    your = _as_spoken(_plain_move(descriptions[last_player_idx]))
    if last_engine_idx is not None and last_engine_idx > last_player_idx:
        mine = _as_spoken(_plain_move(descriptions[last_engine_idx]))
        return f"Your last move was {your}, and I played {mine}."
    return f"Your last move was {your}."


def take_back(board, player, log=None):
    """Undo the player's last move and the engine's reply, if the engine has already played.

    Mutates `board`.  If `log` has a lost-thread mark after the restored
    position, that mark is cleared.  Returns (message, last_reply), where
    last_reply is the engine move still on the board (for 'repeat'), or None.

    If the player has not yet moved, the board is left as it is and the
    message is 'Nothing to take back.'
    """
    start, moves = _replay(board)
    last_player_idx = None
    cursor = start.copy()
    for i, move in enumerate(moves):
        if cursor.turn == player:
            last_player_idx = i
        cursor.push(move)
    if last_player_idx is None:
        return "Nothing to take back.", last_engine_reply(board, player)

    before = start.copy()
    for move in moves[:last_player_idx]:
        before.push(move)
    player_desc = _plain_move(describe_move(before, moves[last_player_idx]))
    engine_desc = None
    if last_player_idx + 1 < len(moves):
        after_player = before.copy()
        after_player.push(moves[last_player_idx])
        engine_desc = _plain_move(describe_move(after_player, moves[last_player_idx + 1]))

    while len(board.move_stack) > last_player_idx:
        board.pop()

    if log is not None and log.get("lost_mark") is not None and log["lost_mark"] > board.fullmove_number:
        log["lost_mark"] = None

    your = _as_spoken(player_desc)
    if engine_desc:
        message = (f"Taken back. Your move {your} and my reply "
                   f"{_as_spoken(engine_desc)} are undone.")
    else:
        message = f"Taken back. Your move {your} is undone."
    reply = last_engine_reply(board, player)
    if reply:
        message += f" My last move was {_as_spoken(reply)}."
    message += " Your move."
    return message, reply


def set_engine_level(engine, level):
    """Retarget a running engine, including the stand-in used in tests."""
    setter = getattr(engine, "set_level", None)
    if callable(setter):
        setter(level)
    elif hasattr(engine, "level"):
        engine.level = level
    return engine


def apply_level_command(ui, s, text, engine=None, player_has_moved=False):
    """Handle 'level 4' / 'set level four' / 'change level to 4'.

    Before the first move, or between games, the new level is used at once.
    After the player has moved, it is saved for the next game and this game
    stays at its current level.  Returns the new game level if this game
    should change, otherwise None.
    """
    requested = parse_level_command(text)
    if requested is None:
        return None
    if requested == "invalid":
        ui.say("Please say a level from 1 to 8.")
        return None
    if player_has_moved:
        s["level"] = requested
        config.save(s)
        ui.say(f"Level {requested} from your next game.")
        return None
    s["level"] = requested
    config.save(s)
    if engine is not None:
        set_engine_level(engine, requested)
    ui.say(f"Engine level {requested}, about {level_rating(requested)}.")
    return requested


PRACTICE_ON = "Practice board on. This game won't be rated."


def open_practice_board(ui, board, player, window=None):
    """Open (or reopen) the practice-board window on this position.

    Returns the window controller.  If no window can be opened, the game is
    still a practice game; a short note is printed (nothing is spoken).
    """
    if window is None:
        factory = getattr(ui, "practice_window_factory", None)
        if factory is None:
            from .practice_board import PracticeBoard as factory
        window = factory(white_at_bottom=(player == chess.WHITE))
    if not window.open(board):
        print("  (I couldn't open the practice board window on this computer. It needs a screen "
              "and tkinter. This game is still a practice game, so it isn't rated.)")
    return window


def play(ui, s, engine_path, setup=False, quick=None):
    """Play one game and record it.  Returns normally when the game is over.

    A plain start uses the saved settings and starting position.  Pass
    setup=True to ask for the starting position first (as --setup does).
    quick= is accepted for compatibility: quick=True is a plain start,
    quick=False is the same as setup=True.
    """
    if quick is not None:
        setup = not quick

    ask_for_start = setup
    # Practice board: chosen between games, before the first move, or mid-game.
    # Either way the game is unrated.  It survives a restart (new settings).
    practice = bool(getattr(ui, "practice_next", False))
    ui.practice_next = False
    practice_announced = False
    while True:
        window = None
        colour = s["colour"] if s["colour"] != "random" else random.choice(["white", "black"])
        player = chess.WHITE if colour == "white" else chess.BLACK
        if ask_for_start:
            start_fen = choose_start(ui, s, player)
            config.save(s)
            ask_for_start = False
        else:
            start_fen = saved_start_fen(s)

        board = chess.Board(start_fen)
        game_level = s["level"]
        engine = Engine(engine_path, game_level)
        limit, used = s["position_limit"], 0
        last_reply = None
        result = termination = None
        # For the after-game report: what went wrong, and when
        log = {"illegal": [], "requests": [], "lost_mark": None, "takebacks": 0,
               "practice": practice}
        reminded = set()
        player_has_moved = False
        restart = False
        milestones.recompute()

        opening = f"You're {colour.capitalize()}, level {game_level}, {limit_words(limit)}."
        print("  The game is about to begin.")              # on screen only
        if board.turn == player:
            opening += " Your move."
        ui.say(opening)
        if start_fen != chess.STARTING_FEN:
            ui.say("Here is the starting position. " + describe_position(board))
        if practice and not practice_announced:
            ui.say(PRACTICE_ON)
            practice_announced = True
        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
        try:
            if practice:
                window = open_practice_board(ui, board, player)
            while True:
                if window is not None:
                    window.update(board)                 # after every move, and take-backs
                outcome = board.outcome(claim_draw=True)
                if outcome:
                    result = outcome.result()
                    termination = outcome.termination.name.replace("_", " ").capitalize()  # e.g. "Checkmate"
                    ui.say(describe_outcome(outcome, player))
                    if player_has_moved:
                        ui.help_context = "during"
                        ui.help_requests_left = "unlimited" if limit < 0 else max(0, limit - used)
                        heard = ui.hear("If that wasn't the move you meant, say take back. "
                                        "Otherwise press Enter to finish:")
                        if ui.listener:
                            print(f"  (I heard: {heard or 'nothing'})")
                        if special_command(heard) == "take back":
                            message, last_reply = take_back(board, player, log)
                            if message.startswith("Nothing"):
                                ui.say(message)
                            else:
                                log["takebacks"] += 1
                                player_has_moved = player_move_count(board, player) > 0
                                result = termination = None
                                ui.say(message)
                                print_status(board, player, game_level, limit, used,
                                             takebacks=log["takebacks"])
                                continue
                    break

                if board.turn != player:                         # 4. the engine replies
                    move = engine.choose_move(board)
                    last_reply = describe_move(board, move)
                    board.push(move)
                    ui.say(last_reply + ".")                     # 5. text to speech
                    print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                    continue

                if s.get("checkpoint_reminders", True) and checkpoint_due(board, player, reminded):
                    reminded.add(board.fullmove_number)
                    print("  " + CHECKPOINT)                     # on screen only: not spoken

                ui.help_context = "before" if not player_has_moved else "during"
                ui.help_requests_left = "unlimited" if limit < 0 else max(0, limit - used)
                heard = ui.hear("Your move:")                    # 1. listen, 2. speech to text
                if ui.listener:
                    print(f"  (I heard: {heard or 'nothing'})")

                cmd = session_command(heard)
                if cmd:
                    if cmd == "help":
                        print_help(ui.help_context, ui.help_requests_left)
                        continue
                    if cmd == "progress":
                        show_progress(ui)
                        continue
                    if cmd == "rating":
                        ui.say(ratings.spoken_rating(ratings.read_games(config.RATING_LOG)))
                        continue
                    if cmd == "level":
                        changed = apply_level_command(
                            ui, s, heard, engine=engine, player_has_moved=player_has_moved)
                        if changed is not None:
                            game_level = changed
                        print_status(board, player, game_level, limit, used,
                                     takebacks=log["takebacks"])
                        continue
                    if cmd == "practice-board" or (cmd == "show-board" and practice):
                        if not practice:
                            practice = log["practice"] = True
                            ui.say(PRACTICE_ON)
                            practice_announced = True
                            window = open_practice_board(ui, board, player)
                        elif window is not None and window.is_open:
                            print("  The practice board is already open.")
                        else:
                            window = open_practice_board(ui, board, player, window)
                        continue
                    if cmd == "show-board":
                        if player_has_moved:
                            ui.say("The board is available between games. Your move.")
                            continue
                        show_last_board(ui, engine_path)
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                        continue
                    if cmd in ("drill", "reset-rating"):
                        if player_has_moved:
                            ui.say("You can only do that before your first move, or between games. Your move.")
                            continue
                        if cmd == "drill":
                            run_square_drill(ui)
                        else:
                            reset_rating(ui)
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                        continue
                    if player_has_moved:
                        ui.say("You can only change that before your first move. Your move.")
                        continue
                    if cmd == "settings":
                        s = choose_settings(ui, s, first_time=True, offer_same=False)
                        colour_now = s["colour"] if s["colour"] != "random" else colour
                        player_now = chess.WHITE if colour_now == "white" else chess.BLACK
                        choose_start(ui, s, player_now)
                        config.save(s)
                        ui.say("Starting again with your new settings.")
                        restart = True
                        break
                    new_colour, stored = resolve_colour(cmd, colour)
                    s["colour"] = stored
                    config.save(s)
                    if new_colour == colour:
                        ui.say(f"You'll play {new_colour} again. Starting again from the start.")
                    else:
                        ui.say(f"You'll play {new_colour}. Starting again from the start.")
                    restart = True
                    break

                r = parse(board, heard)                          # request? / understand the move

                if r.kind == "problem":                          # not legal or not clear: ask again
                    if is_illegal_attempt(r):
                        log["illegal"].append({"move": board.fullmove_number, "said": heard.strip(),
                                               "reason": r.message})
                    ui.say(r.message)
                elif r.kind == "move":
                    ui.say(describe_move(board, r.move) + ".")
                    board.push(r.move)
                    player_has_moved = True
                    print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                elif r.command == "repeat":
                    ui.say(f"My last move was {last_reply[0].lower() + last_reply[1:]}." if last_reply
                           else "I haven't made a move yet.")
                elif r.command == "last move":
                    ui.say(last_moves_spoken(board, player))
                elif r.command == "level":
                    changed = apply_level_command(
                        ui, s, heard, engine=engine, player_has_moved=player_has_moved)
                    if changed is not None:
                        game_level = changed
                    print_status(board, player, game_level, limit, used,
                                 takebacks=log["takebacks"])
                elif r.command == "position":
                    if limit < 0 or used < limit:
                        used += 1
                        log["requests"].append(board.fullmove_number)
                        ui.say(describe_position(board))
                        if limit >= 0:
                            # The count is already on the status line; don't speak it.
                            print("  " + f"That was position request {used} of {limit}.")
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                    else:
                        ui.say("Sorry, you've used all your position requests for this game.")
                        print("  " + (f"I'm sorry, you have used all {limit} of your position requests "
                                      "for this game. Try to rebuild the position in your mind, "
                                      "then tell me your move."))
                elif r.command == "show moves":
                    # Printed only: the score sheet is never spoken.
                    if not board.move_stack:
                        print("  No moves yet.")
                    elif limit < 0 or used < limit:
                        used += 1
                        log["requests"].append(board.fullmove_number)
                        print("  " + format_move_list(board))
                        if limit >= 0:
                            print("  " + f"That was position request {used} of {limit}.")
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                    else:
                        ui.say("Sorry, you've used all your position requests for this game.")
                        print("  " + (f"I'm sorry, you have used all {limit} of your position requests "
                                      "for this game. Try to rebuild the position in your mind, "
                                      "then tell me your move."))
                elif r.command == "lost thread":
                    if log["lost_mark"] is None:
                        log["lost_mark"] = board.fullmove_number
                        ui.say(f"I'll note that you lost the thread at move {log['lost_mark']}. "
                               "Take your time; your move when you're ready.")
                    else:
                        ui.say(f"I've already noted that you first lost the thread at move {log['lost_mark']}, "
                               "so I'll keep that. Your move when you're ready.")
                elif r.command == "take back":
                    message, last_reply = take_back(board, player, log)
                    if not message.startswith("Nothing"):
                        log["takebacks"] += 1
                        player_has_moved = player_move_count(board, player) > 0
                        print_status(board, player, game_level, limit, used,
                                     takebacks=log["takebacks"])
                    ui.say(message)
                elif r.command == "help":
                    print_help(ui.help_context, ui.help_requests_left)
                elif r.command == "rating":
                    ui.say(ratings.spoken_rating(ratings.read_games(config.RATING_LOG)))
                elif r.command == "progress":
                    show_progress(ui)
                elif r.command == "square drill":
                    if player_has_moved:
                        ui.say("You can only do that before your first move, or between games. Your move.")
                    else:
                        run_square_drill(ui)
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
                elif r.command == "reset rating":
                    if player_has_moved:
                        ui.say("You can only do that before your first move, or between games. Your move.")
                    else:
                        reset_rating(ui)
                        print_status(board, player, game_level, limit, used, takebacks=log["takebacks"])
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
            if window is not None:
                window.close()                           # the game is over (or restarting)

        if restart:
            continue
        break

    finish(ui, s, board, start_fen, player, result, termination, used, log, engine_path,
           game_level=game_level)


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

    ui.help_context, ui.help_requests_left = "review", None
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
    # Instructions only: the window is about to open, so nothing is spoken.
    print("  Put the pieces where you think they stood at the end of the game, "
          "then click 'Check my position'. Click 'Skip' if you change your mind.")
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
    ui.help_context, ui.help_requests_left = "review", None
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


def wants_review(ui):
    """True if the player asked for the after-game review."""
    def understand(text):
        text = (text or "").strip()
        if not text:
            return False
        words = text.split()
        if "review" in words or is_yes(words):
            return True
        if is_no(words):
            return False
        cmd = session_command(text)
        if cmd in ("drill", "progress", "reset-rating", "rating", "level", "show-board",
                   "practice-board"):
            # A between-games command: skip the review and do it straight after.
            ui.pending_command = text
            return False
        return None
    ui.help_context, ui.help_requests_left = "after", None
    return ui.ask("Say review for the after-game review, or press Enter to carry on.",
                  understand, "Review, or press Enter?")


def _apply_review_data(headers, row, reconstruction, looked):
    quality = looked["quality"] if looked else None
    if reconstruction:
        headers["Reconstruction"] = short_score(reconstruction)
        row["Reconstruction"] = f"{reconstruction['correct']}/{reconstruction['total']}"
        row["Reconstruction per cent"] = reconstruction["percent"]
    if quality:
        headers["AverageCentipawnLoss"] = str(quality["average_loss"])
        headers["EngineMatches"] = f"{quality['matched']}/{quality['moves']}"
        row["Average centipawn loss"] = quality["average_loss"]
        row["Engine matches"] = f"{quality['matched']}/{quality['moves']}"
    if looked and looked["slips"]:
        headers["Slips"] = row["Slips"] = slips_text(looked["slips"])
    return quality


UNRATED_RESIGN_MOVES = 5


def player_moves_made(board, player):
    """How many moves the player has made in this game (from its start position)."""
    turn = board.root().turn
    count = 0
    for _ in board.move_stack:
        if turn == player:
            count += 1
        turn = not turn
    return count


def is_early_resignation(board, player, termination):
    """A resignation in the first five moves: saved, but not rated."""
    return termination == "Player resigned" and player_moves_made(board, player) < UNRATED_RESIGN_MOVES


def finish(ui, s, board, start_fen, player, result, termination, used, log=None, engine_path=None,
           quick=False, game_level=None):
    log = log or {}
    level = game_level if game_level is not None else s["level"]
    illegal, requests = log.get("illegal", []), log.get("requests", [])
    now = datetime.datetime.now()
    score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
    if player == chess.BLACK and result in ("1-0", "0-1"):
        score = 1.0 - score
    score_text = {1.0: "1", 0.5: "0.5", 0.0: "0"}[score]

    # Save the PGN straight away, so that nothing below can lose the game.
    # The after-game review is offered afterwards; if the player takes it,
    # the file and the rating-log row are updated in place.
    engine_name = f"The Different Engine, {level_name(level)}"
    headers = {
        "Event": "Blindfold game", "Site": "The Different Engine", "Date": now.strftime("%Y.%m.%d"),
        "Round": "-", "White": "Player" if player == chess.WHITE else engine_name,
        "Black": engine_name if player == chess.WHITE else "Player", "Result": result,
        "TimeControl": "-", "Termination": "normal", "Ending": termination,
        "PositionRequests": str(used), "FirstLostThread": "never",
        "PositionRequestMoves": ", ".join(str(n) for n in requests) or "-",
        "IllegalAttempts": illegal_header(illegal),
        "Takebacks": str(log.get("takebacks", 0)),
    }
    if log.get("practice"):
        headers["Event"] = "Practice board game"
        headers["PracticeBoard"] = "yes"
    if log.get("lost_mark"):
        headers["LostThreadMarked"] = str(log["lost_mark"])
    if board.root().fen() != chess.STARTING_FEN:
        headers["SetUp"], headers["FEN"] = "1", board.root().fen()

    os.makedirs(config.GAMES_DIR, exist_ok=True)
    base = f"{now:%Y-%m-%d_%H%M}_{'white' if player else 'black'}_level{level}"
    path = os.path.join(config.GAMES_DIR, base + ".pgn")
    n = 2
    while os.path.exists(path):
        path = os.path.join(config.GAMES_DIR, f"{base}_{n}.pgn")
        n += 1
    pgn_text = save_pgn(path, board, headers)
    remember_game(ui, board, player, engine_path, headers)
    ui.say("Game saved in your games folder.")
    print(f"  Full location of the game: {path}")

    opponent = ratings.opponent_name(level)
    row = {
        "Date": now.strftime("%Y-%m-%d"), "Opponent": opponent, "Opponent rating": level_rating(level),
        "Colour": "White" if player == chess.WHITE else "Black", "Time control": "untimed",
        "Result": score_text, "First lost thread": "", "Rule breaks": "", "Notes": "",
        "Position requests": used, "How it ended": termination,
        "Start position": "usual" if start_fen == chess.STARTING_FEN else start_fen,
        "PGN file": os.path.relpath(path, config.APP_DIR),
        "Illegal attempts": len(illegal),
        "Illegal attempt moves": ", ".join(str(a["move"]) for a in illegal),
        "Position request moves": ", ".join(str(n) for n in requests),
        "Takebacks": log.get("takebacks", 0),
    }
    practice = bool(log.get("practice"))
    early = is_early_resignation(board, player, termination)
    unrated = practice or early
    if unrated:
        # Kept in the log for the record, but "unrated" is skipped by the
        # rating, the level-up check and the milestones (apart from the
        # practice-board milestone, which looks for the note below).
        row["Result"] = "unrated"
    if practice:
        row["Notes"] = f"Practice board game (scored {score_text}), not rated"
    elif early:
        row["Notes"] = f"Resigned in the first {UNRATED_RESIGN_MOVES} moves (scored {score_text}), not rated"
    ratings.append_game(config.RATING_LOG, row)

    games = ratings.read_games(config.RATING_LOG)
    if practice:
        print("  This was a practice board game, so it isn't rated.")   # said at the start
    elif early:
        ui.say("You resigned within the first five moves, so this game isn't rated.")
    # Only a short rating line is spoken; the rest of the report is on screen.
    p = ratings.performance(ratings.recent(games))
    if p:
        ui.say(f"Your rating is {p['performance']}.")
    else:
        ui.say("You have no rating yet.")
    for line in ratings.report(games, opponent):
        print("  " + line)
    print(f"  (Your rating log is in {config.RATING_LOG}; it opens in any spreadsheet.)\n")

    # Auto level-up applies only if the player has not already chosen a
    # different level for the next game.
    if s["level"] == level:
        new_level, message = ratings.maybe_level_up(games, level)
        if new_level:
            s["level"] = new_level
            config.save(s)
            ui.say(message)

    # --quick used to skip the extras; a plain start now does the same unless
    # the player asks for a review.  The quick flag is kept only as a no-op.
    del quick  # accepted for compatibility; review is always offered once
    if wants_review(ui):
        _run_review(ui, board, player, engine_path, path, headers, row, log, illegal, requests, pgn_text)
    milestones.update_and_announce(ui)


def _run_review(ui, board, player, engine_path, path, headers, row, log, illegal, requests, pgn_text):
    reconstruction = looked = quality = None
    try:
        lost = lost_thread_question(ui, log.get("lost_mark"), illegal)
        breaks = "yes" if ui.yes_no("Did you break any of your honesty rules, for example by taking a peek?") else ""
        notes = ui.type_in("Type a one-line note about the game for your log, or just press Enter to skip:")
        row["First lost thread"] = lost
        row["Rule breaks"] = breaks
        # Keep the unrated note (practice board, early resignation) in front of the player's own
        row["Notes"] = "; ".join(n for n in (row.get("Notes") or "", notes) if n)
        headers["FirstLostThread"] = lost or "never"
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
        quality = _apply_review_data(headers, row, reconstruction, looked)
        try:
            pgn_text = save_pgn(path, board, headers)
        except OSError:
            pass
        ratings.update_game(config.RATING_LOG, row["PGN file"], row)

    print("\n" + "-" * 60 + "\n" + pgn_text + "\n" + "-" * 60)
    print(f"  Full location of the game: {path}\n")
    for line in review.summary_lines(lost, illegal, requests, reconstruction, quality):
        ui.say(line)
    print()

    if ui.yes_no("Would you like me to read the moves of the game aloud?"):
        for line in describe_game(board.root(), board.move_stack):
            ui.say(line)
