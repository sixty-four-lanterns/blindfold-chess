"""Square-colour drill: parsing, scoring, logging and spoken feedback."""

import builtins
import csv
import datetime
import random

import pytest

from different_engine import drill, settings as config
from different_engine.game import Interface


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


@pytest.fixture
def path(tmp_path, monkeypatch):
    log = tmp_path / "drill_log.csv"
    monkeypatch.setattr(config, "DRILL_LOG", str(log))
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    return log


def test_square_colours_standard_board():
    assert drill.square_colour("a1") == "dark"
    assert drill.square_colour("h1") == "light"
    assert drill.square_colour("a8") == "light"
    assert drill.square_colour("h8") == "dark"
    assert drill.square_colour("d5") == "light"
    assert drill.square_colour("e4") == "light"
    assert drill.square_colour("f6") == "dark"
    assert drill.square_colour("c2") == "light"


def test_speak_square_uses_spelling_alphabet():
    assert drill.speak_square("d5") == "delta five"
    assert drill.speak_square("a1") == "alpha one"
    assert drill.speak_square("h8") == "hotel eight"
    assert drill.speak_square("C3") == "charlie three"


@pytest.mark.parametrize("text,colour", [
    ("light", "light"),
    ("dark", "dark"),
    ("white", "light"),
    ("black", "dark"),
    ("it's light", "light"),
    ("Dark!", "dark"),
    ("WHITE", "light"),
    ("  black  ", "dark"),
])
def test_parse_colour_answer(text, colour):
    assert drill.parse_colour_answer(text) == colour


def test_parse_colour_answer_rejects_unclear():
    assert drill.parse_colour_answer("") is None
    assert drill.parse_colour_answer("maybe") is None
    assert drill.parse_colour_answer("light dark") is None
    assert drill.parse_colour_answer("white black") is None


def test_is_drill_command():
    for phrase in ("square drill", "colour drill", "color drill",
                   "square colours", "square colors", "please start the square drill"):
        assert drill.is_drill_command(phrase)
    assert not drill.is_drill_command("e4")
    assert not drill.is_drill_command("progress")
    assert not drill.is_drill_command("")


def test_pick_squares_are_unique():
    squares = drill.pick_squares(rng=random.Random(0), n=30)
    assert len(squares) == 30
    assert len(set(squares)) == 30
    assert all(len(s) == 2 and s[0] in "abcdefgh" and s[1] in "12345678" for s in squares)
    default = drill.pick_squares(rng=random.Random(1))
    assert len(default) == drill.N_SQUARES == 30


def test_best_result_prefers_score_then_time():
    rows = [
        {"score": 28, "total": 30, "seconds": 20, "date": "2026-11-01"},
        {"score": 30, "total": 30, "seconds": 50, "date": "2026-11-02"},
        {"score": 30, "total": 30, "seconds": 35, "date": "2026-11-03"},
    ]
    best = drill.best_result(rows)
    assert best["score"] == 30 and best["seconds"] == 35
    assert drill.best_result([]) is None
    assert drill.is_new_best(30, 34, best)
    assert not drill.is_new_best(30, 35, best)
    assert not drill.is_new_best(29, 10, best)
    assert drill.is_new_best(30, 10, None)


def test_summarise_lines():
    lines = drill.summarise(18, 30, 42, previous={"score": 30, "total": 30, "seconds": 35}, new_best=False)
    assert lines[0] == "You scored 18 out of 30 in 42 seconds."
    assert lines[1] == "Your best is 30 out of 30 in 35 seconds."
    lines = drill.summarise(30, 30, 28, previous={"score": 29, "total": 30, "seconds": 40}, new_best=True)
    assert "That's your best so far." in lines
    assert drill.summarise(1, 30, 1)[0] == "You scored 1 out of 30 in 1 second."


def test_append_and_read_log(path):
    drill.append_result(path, {"Date": "2026-11-19", "Score": 18, "Total": 20, "Seconds": 42})
    drill.append_result(path, {"Date": "2026-11-19", "Score": 30, "Total": 30, "Seconds": 29})
    rows = drill.read_results(path)
    assert rows == [
        {"date": "2026-11-19", "score": 18, "total": 20, "seconds": 42},
        {"date": "2026-11-19", "score": 30, "total": 30, "seconds": 29},
    ]
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f))
    assert header == ["Date", "Score", "Total", "Seconds"]


class FixedRng:
    def __init__(self, squares):
        self.squares = list(squares)

    def shuffle(self, items):
        items[:] = list(self.squares) + [s for s in items if s not in self.squares]


def test_run_drill_scores_logs_and_gives_feedback(path, monkeypatch, capsys):
    all_sq = drill.all_squares()
    lights = [s for s in all_sq if drill.square_colour(s) == "light"][:15]
    darks = [s for s in all_sq if drill.square_colour(s) == "dark"][:15]
    assert len(lights) == 15 and len(darks) == 15
    squares = lights + darks
    answers = ["light"] * 15 + ["white"] * 15  # white is light, so the second half is wrong
    times = iter([10.0, 52.4])  # 42 seconds when rounded
    monkeypatch.setattr(builtins, "input", lambda prompt="": answers.pop(0))
    speaker = Speaker()
    result = drill.run_drill(
        Interface(speaker),
        path=path,
        rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19),
        clock=lambda: next(times),
    )
    said = "\n".join(speaker.said)
    assert result == {"score": 15, "total": 30, "seconds": 42, "date": "2026-11-19"}
    assert said.count("Right.") == 15
    assert said.count("No, dark.") == 15
    assert "No, light." not in said
    assert "You scored 15 out of 30 in 42 seconds." in said
    assert "That's your best so far." in said
    assert "I'll name thirty squares." in said
    assert drill.speak_square(squares[0]) in said
    out = capsys.readouterr().out
    assert f"1/30: {squares[0]}" in out
    assert f"30/30: {squares[-1]}" in out
    rows = drill.read_results(path)
    assert rows == [{"date": "2026-11-19", "score": 15, "total": 30, "seconds": 42}]

    answers.extend(["light"] * 15 + ["dark"] * 15)
    result2 = drill.run_drill(
        Interface(speaker),
        path=path,
        rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19),
        clock=iter([0.0, 30.0]).__next__,
    )
    assert result2["score"] == 30 and result2["seconds"] == 30
    said = "\n".join(speaker.said)
    assert "You scored 30 out of 30 in 30 seconds." in said
    assert said.count("That's your best so far.") == 2
    rows = drill.read_results(path)
    assert rows[-1] == {"date": "2026-11-19", "score": 30, "total": 30, "seconds": 30}
