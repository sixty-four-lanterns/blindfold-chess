"""The two beginner levels below level 1: about 400 and 600."""

import random

import chess
import pytest

from different_engine import engine, game, milestones, ratings, settings as config
from different_engine.moves import parse_level_command, parse_beginner, special_command
from different_engine.speech import grammar_phrases


def test_levels_and_labels():
    assert engine.level_rating(-1) == 400 and engine.level_rating(0) == 600
    assert engine.level_rating(1) == 800 and engine.level_rating(8) == 2300
    assert (engine.MIN_LEVEL, engine.MAX_LEVEL) == (-1, 8)
    assert engine.level_label(-1) == "beginner 1" and engine.level_label(0) == "beginner 2"
    assert engine.level_label(3) == "level 3"
    assert engine.level_name(-1) == "Beginner 1 (about 400)"
    assert engine.level_name(4) == "Level 4 (about 1400)"
    assert engine.level_slug(0) == "beginner2" and engine.level_slug(5) == "level5"


@pytest.mark.parametrize("text, level", [
    ("beginner 1", -1), ("beginner one", -1), ("Beginner two", 0), ("level beginner 2", 0),
    ("set level beginner one", -1), ("change level to beginner two", 0),
    ("beginner", "invalid"), ("beginner 3", "invalid"),
    ("level 1", 1), ("level 0", "invalid"), ("level 9", "invalid"), ("level", None),
])
def test_level_commands(text, level):
    assert parse_level_command(text) == level


def test_beginner_is_a_level_command_and_in_the_grammar():
    assert special_command("beginner 1") == "level"
    assert game.session_command("beginner two") == "level"
    assert parse_beginner("e4") is None
    phrases = grammar_phrases()
    assert {"beginner one", "beginner two", "level beginner one"} <= set(phrases)


def test_random_move_rates_make_beginner_1_weaker_than_beginner_2():
    assert engine.RANDOM_MOVE_RATE[-1] > engine.RANDOM_MOVE_RATE[0] > 0
    assert not engine.is_beginner(1)


class FixedRandom:
    def __init__(self, value):
        self.value = value
        self.inner = random.Random(1)

    def random(self):
        return self.value

    def choices(self, *args, **kwargs):
        return self.inner.choices(*args, **kwargs)


def test_beginner_choice_uses_the_engine_or_a_random_legal_move():
    board = chess.Board()
    best = chess.Move.from_uci("e2e4")
    calls = []

    def engine_move():
        calls.append(1)
        return best
    # Below the rate: a random legal move, and Stockfish is not asked.
    move = engine.beginner_choice(board, -1, engine_move, FixedRandom(0.1))
    assert move in board.legal_moves and not calls
    # Above the rate: Stockfish's move.
    assert engine.beginner_choice(board, -1, engine_move, FixedRandom(0.9)) == best
    # Level 1 and above never play random moves.
    assert engine.beginner_choice(board, 1, engine_move, FixedRandom(0.0)) == best


def test_random_moves_happen_at_about_the_stated_rate():
    board = chess.Board()
    rng = random.Random(42)
    sentinel = chess.Move.null()
    picks = [engine.beginner_choice(board, 0, lambda: sentinel, rng) for _ in range(4000)]
    share = sum(1 for m in picks if m != sentinel) / len(picks)
    assert abs(share - engine.RANDOM_MOVE_RATE[0]) < 0.03


def test_random_king_moves_are_less_likely():
    board = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    rng = random.Random(3)
    picks = [engine.random_move(board, rng) for _ in range(3000)]
    king = sum(1 for m in picks if board.piece_type_at(m.from_square) == chess.KING)
    n_king = sum(1 for m in board.legal_moves if board.piece_type_at(m.from_square) == chess.KING)
    n_all = board.legal_moves.count()
    assert king / len(picks) < n_king / n_all          # weighted down
    assert engine.random_move(chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")) is None   # stalemate


def test_level_up_from_beginner_1_to_beginner_2_to_level_1():
    def wins(level, n=5):
        return [{"opponent": ratings.opponent_name(level), "rating": engine.level_rating(level),
                 "result": 1.0, "date": ""} for _ in range(n)]
    assert ratings.opponent_name(-1) == "Stockfish beginner 1"
    assert ratings.opponent_name(3) == "Stockfish level 3"
    new, message = ratings.maybe_level_up(wins(-1), -1)
    assert new == 0
    assert message == ("You scored over 70 per cent in your last five games at beginner 1, "
                       "so I've moved the engine up to beginner 2.")
    new, message = ratings.maybe_level_up(wins(0), 0)
    assert new == 1 and message.endswith("moved the engine up to level 1.")
    assert ratings.maybe_level_up(wins(8), 8) == (None, None)


def test_rating_uses_400_and_600_opponents():
    games = [{"opponent": "Stockfish beginner 1", "rating": 400, "result": 1.0},
             {"opponent": "Stockfish beginner 2", "rating": 600, "result": 0.0}]
    assert ratings.performance(games)["performance"] == 500


def test_milestones_read_beginner_rows():
    assert milestones.opponent_level({"Opponent": "Stockfish beginner 1"}) == -1
    assert milestones.opponent_level({"Opponent": "Stockfish beginner 2"}) == 0
    assert milestones.opponent_level({"Opponent": "Stockfish level 2"}) == 2
    assert milestones.opponent_level({"Opponent": "someone", "Opponent rating": "600"}) == 0
    rows = [{"Opponent": "Stockfish beginner 1", "Opponent rating": "400", "Result": "0"}] * 3
    rows += [{"Opponent": "Stockfish beginner 2", "Opponent rating": "600", "Result": "1",
              "How it ended": "Checkmate"}]
    assert "win_above_usual" in milestones.detect(rows=rows, drills=[], pgns={i: None for i in range(4)})


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_spoken_and_printed_wording(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    speaker = Speaker()
    ui = game.Interface(speaker)
    s = dict(config.DEFAULTS, level=2)
    assert game.apply_level_command(ui, s, "beginner 1") == -1
    assert speaker.said[-1] == "Engine beginner 1, about 400."
    assert s["level"] == -1
    assert game.apply_level_command(ui, s, "beginner two", player_has_moved=True) is None
    assert speaker.said[-1] == "Beginner 2 from your next game."
    line = game.format_status(chess.Board(), chess.WHITE, -1, 3, 0, games=[], milestones_count=(0, 25))
    assert "| Beginner 1 |" in line
    assert "level 1 to 8 / beginner 1, 2" in game.format_help("before")


def test_settings_question_accepts_beginner_levels(tmp_path, monkeypatch):
    import builtins
    answers = iter(["white", "beginner two", "3"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    speaker = Speaker()
    s = game.choose_settings(game.Interface(speaker), dict(config.DEFAULTS), first_time=True)
    assert s["level"] == 0
    said = "\n".join(speaker.said)
    assert "two beginner levels below them. Beginner 1 is about 400." in said
    assert "from 1 to 8, or beginner 1 or 2?" in said


class FakeEngine:
    replies = ["e5", "Nc6", "a6", "Nf6", "Be7", "b5"]

    def __init__(self, path, level):
        self.level = level

    def choose_move(self, board):
        return board.parse_san(self.replies[len(board.move_stack) // 2])

    def accepts_draw(self, board, colour):
        return False

    def close(self):
        pass


def test_a_beginner_game_is_logged_with_its_rating(tmp_path, monkeypatch, capsys):
    import builtins, csv
    for name in ("APP_DIR",):
        monkeypatch.setattr(config, name, str(tmp_path))
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path / "games"))
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "DRILL_LOG", str(tmp_path / "drill_log.csv"))
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(game, "Engine", FakeEngine)
    answers = iter(["e4", "Nf3", "Bb5", "Ba4", "O-O", "resign", "yes", ""])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    speaker = Speaker()
    game.play(game.Interface(speaker), dict(config.DEFAULTS, colour="white", level=-1), "/fake")
    assert speaker.said[0] == "You're White, beginner 1. Your move."
    assert all("position request" not in line.lower() for line in speaker.said
               if line.startswith("You're "))
    out = capsys.readouterr().out
    assert "Three position requests." in out
    assert "Blindfold rating:" in out
    assert "Milestones " in out
    with open(tmp_path / "rating_log.csv", newline="", encoding="utf-8-sig") as f:
        (row,) = list(csv.DictReader(f))
    assert row["Opponent"] == "Stockfish beginner 1" and row["Opponent rating"] == "400"
    assert row["PGN file"].endswith("_white_beginner1.pgn")
    assert "Your rating is 0." in speaker.said           # 400 - 400 for one loss
