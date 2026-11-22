"""Take-back, the short rating command, and related after-game wording."""

import builtins
import csv

import chess
import chess.pgn
import pytest

from different_engine import game, ratings, settings as config
from different_engine.moves import parse, special_command, fuzzy_command, is_illegal_attempt


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeEngine:
    """Plays a fixed list of replies for Black."""
    replies = ["e5", "Nc6", "a6", "Nf6", "Be7", "b5"]

    def __init__(self, path, level):
        pass

    def choose_move(self, board):
        return board.parse_san(self.replies[len(board.move_stack) // 2])

    def accepts_draw(self, board, colour):
        return False

    def close(self):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path / "games"))
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "DRILL_LOG", str(tmp_path / "drill_log.csv"))
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(game, "Engine", FakeEngine)
    speaker = Speaker()

    def script(answers):
        answers = iter(answers)
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    return speaker, script, tmp_path


def read_pgn(tmp_path):
    (path,) = list((tmp_path / "games").glob("*.pgn"))
    with open(path, encoding="utf-8") as f:
        return chess.pgn.read_game(f), path


def read_log(tmp_path):
    with open(tmp_path / "rating_log.csv", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def settings(**extra):
    values = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    values.update(extra)
    return values


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "take back", "takeback", "undo", "go back", "take that back", "Take back!",
])
def test_takeback_synonyms(text):
    r = parse(chess.Board(), text)
    assert r.kind == "command" and r.command == "take back"
    assert r.move is None and not is_illegal_attempt(r)


def test_take_as_capture_is_not_a_takeback():
    b = chess.Board()
    b.push_san("e4")
    b.push_san("d5")
    r = parse(b, "pawn takes d5")
    assert r.kind == "move" and b.san(r.move) == "exd5"
    r = parse(b, "e takes d5")
    assert r.kind == "move" and b.san(r.move) == "exd5"
    assert special_command("pawn takes d5") is None
    assert parse(chess.Board(), "knight f3").kind == "move"


def test_normal_moves_unaffected_by_new_commands():
    b = chess.Board()
    assert parse(b, "e4").kind == "move"
    assert parse(b, "knight f3").command is None
    assert parse(b, "reset rating").command == "reset rating"
    assert parse(b, "rating").command == "rating"


# ---------------------------------------------------------------------------
# take_back helper
# ---------------------------------------------------------------------------

def test_take_back_user_and_engine_move():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    message, reply = game.take_back(board, chess.WHITE)
    assert board.fen() == chess.STARTING_FEN
    assert board.turn == chess.WHITE
    assert "pawn to e4" in message.lower()
    assert "pawn to e5" in message.lower()
    assert "are undone" in message
    assert message.endswith("Your move.")
    assert reply is None


def test_take_back_when_engine_has_not_replied():
    board = chess.Board()
    board.push_san("e4")
    message, reply = game.take_back(board, chess.WHITE)
    assert board.fen() == chess.STARTING_FEN
    assert board.turn == chess.WHITE
    assert "pawn to e4" in message.lower()
    assert "is undone" in message
    assert "my reply" not in message.lower()
    assert reply is None


def test_take_back_nothing_to_take_back():
    board = chess.Board()
    fen = board.fen()
    message, reply = game.take_back(board, chess.WHITE)
    assert message == "Nothing to take back."
    assert board.fen() == fen
    # Black to move at the start, only the engine has moved
    board = chess.Board()
    board.push_san("e4")
    message, reply = game.take_back(board, chess.BLACK)
    assert message == "Nothing to take back."
    assert board.peek() == chess.Move.from_uci("e2e4")


def test_multiple_consecutive_take_backs():
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6"]:
        board.push_san(san)
    log = {"lost_mark": 2}
    message, reply = game.take_back(board, chess.WHITE, log)
    assert [m.uci() for m in board.move_stack] == ["e2e4", "e7e5"]
    assert "knight to f3" in message.lower()
    assert "knight to c6" in message.lower()
    assert "pawn to e5" in message.lower()          # last engine move, for orientation
    assert log["lost_mark"] == 2                    # still at this move number
    message, reply = game.take_back(board, chess.WHITE, log)
    assert list(board.move_stack) == []
    assert log["lost_mark"] is None                 # mark was after the restored position
    assert game.take_back(board, chess.WHITE)[0] == "Nothing to take back."


def test_lost_thread_mark_kept_when_still_at_that_move():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    log = {"lost_mark": 1}
    game.take_back(board, chess.WHITE, log)
    assert log["lost_mark"] == 1
    assert board.fullmove_number == 1


# ---------------------------------------------------------------------------
# A whole game
# ---------------------------------------------------------------------------

def test_take_back_in_play_recorded_in_log_and_pgn(setup, capsys):
    speaker, script, tmp_path = setup
    script([
        "e4",
        "take back",
        "d4",
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), settings(), "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Taken back." in said
    assert "pawn to e4" in said.lower()
    assert "pawn to e5" in said.lower()
    assert "are undone" in said
    assert "Game saved in your games folder." in said
    assert ".pgn" not in said
    out = capsys.readouterr().out
    assert "Full location of the game:" in out
    assert str(tmp_path / "games") in out
    assert "Take-backs: 1" in out

    pgn, path = read_pgn(tmp_path)
    assert pgn.headers["Takebacks"] == "1"
    # The taken-back e4/e5 are gone; the game is d4, e5, resign
    moves = [move.san() for move in pgn.mainline()]
    assert moves[0] == "d4" and "e4" not in moves[:1]
    (row,) = read_log(tmp_path)
    assert row["Takebacks"] == "1"
    assert row["Result"] == "unrated"                # resigned in the first five moves


def test_nothing_to_take_back_in_play(setup):
    speaker, script, tmp_path = setup
    script(["take back", "resign", "yes", ""])
    game.play(game.Interface(speaker), settings(), "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Nothing to take back." in said
    (row,) = read_log(tmp_path)
    assert row["Takebacks"] == "0"
    assert read_pgn(tmp_path)[0].headers["Takebacks"] == "0"


def test_multiple_takebacks_and_position_requests_unaffected(setup):
    speaker, script, tmp_path = setup
    script([
        "e4",
        "position",          # request at move 2, before take-back
        "take back",         # undo Nf3? no: after e4, engine e5, it's move 2; position, then take back e4+e5
        "d4",
        "take back",
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), settings(), "/fake/stockfish")
    pgn, _ = read_pgn(tmp_path)
    assert pgn.headers["Takebacks"] == "2"
    assert pgn.headers["PositionRequests"] == "1"
    (row,) = read_log(tmp_path)
    assert row["Takebacks"] == "2"
    assert row["Position requests"] == "1"


def test_take_back_after_checkmate_before_after_game(setup):
    speaker, script, tmp_path = setup
    fen = "4k3/8/4K3/8/8/8/8/7Q w - - 0 1"
    s = settings(start="custom", custom_fen=fen, level=1)
    script([
        "queen h8",          # checkmate, supported by the king on e6
        "take back",         # offered after the result is announced
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Checkmate" in said
    assert "Taken back." in said
    assert "queen to h8" in said.lower()
    assert "is undone" in said
    assert "my reply" not in said.lower()
    pgn, _ = read_pgn(tmp_path)
    assert pgn.headers["Takebacks"] == "1"
    assert pgn.headers["Ending"] == "Player resigned"
    assert list(pgn.mainline()) == []                # mate was undone, then resign


def test_rating_during_game_does_not_use_a_request_or_block_the_game(setup):
    speaker, script, tmp_path = setup
    script([
        "e4",
        "rating",
        "my rating",
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), settings(), "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert said.count("There are no games in your rating log yet.") == 3   # the early resignation is unrated
    assert "You can only change that before your first move" not in said
    assert "You can only do that before your first move" not in said
    (row,) = read_log(tmp_path)
    assert row["Position requests"] == "0"


def test_milestones_during_game(setup):
    speaker, script, tmp_path = setup
    script(["e4", "milestones", "resign", "yes", ""])
    game.play(game.Interface(speaker), settings(), "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "You can only change that before your first move" not in said
    # progress_lines always mentions milestones or levels
    assert "milestone" in said.lower() or "foundations" in said.lower() or "earned" in said.lower()


def test_between_games_accepts_rating_and_milestones(setup):
    speaker, script, tmp_path = setup
    script(["milestones", "rating", "no"])
    assert game.between_games(game.Interface(speaker)) is False
    said = "\n".join(speaker.said)
    assert "There are no games in your rating log yet." in said
    assert "milestone" in said.lower() or "foundations" in said.lower() or "earned" in said.lower()


def test_finish_does_not_speak_the_filename(setup, capsys):
    speaker, script, tmp_path = setup
    board = chess.Board()
    for san in ["e4", "e5"]:
        board.push_san(san)
    script([""])
    game.finish(game.Interface(speaker), settings(), board, chess.STARTING_FEN,
                chess.WHITE, "1/2-1/2", "Draw agreed", 0, {"takebacks": 0}, engine_path=None)
    said = "\n".join(speaker.said)
    assert "Game saved in your games folder." in said
    assert ".pgn" not in said
    assert "I've saved the game" not in said
    out = capsys.readouterr().out
    assert "Full location of the game:" in out


def test_fuzzy_command_matches_near_misses_but_not_moves():
    assert special_command("progess") == "progress"          # one letter dropped
    assert special_command("posision") == "position"
    assert parse(chess.Board(), "posision").command == "position"
    assert special_command("e4") is None
    assert special_command("knight f3") is None
    assert fuzzy_command("knight f3") is None
    assert fuzzy_command("e4") is None
    assert fuzzy_command("draw") is None                     # short words stay exact
    assert fuzzy_command("help") is None
