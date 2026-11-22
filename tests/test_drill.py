"""Square-colour drill: parsing, scoring, logging and spoken feedback."""

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
    ("light square", "light"),
    ("dark square", "dark"),
    ("a light square", "light"),
    ("lite", "light"),
    ("lights", "light"),
    ("darke", "dark"),
    ("dark one", "dark"),
    ("light one", "light"),
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
    assert len(default) == drill.N_SQUARES == 20


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
    assert lines[0] == "You scored 18 out of 30."
    assert lines[1] == "Your thinking time was 42 seconds."
    assert lines[2] == "Your best is 30 out of 30 in 35 seconds."
    lines = drill.summarise(30, 30, 28, previous={"score": 29, "total": 30, "seconds": 40}, new_best=True)
    assert "That's your best so far." in lines
    assert drill.summarise(1, 30, 1)[0] == "You scored 1 out of 30."
    assert drill.summarise(1, 30, 1)[1] == "Your thinking time was 1 second."
    assert drill.summarise(30, 30, 12.5)[1] == "Your thinking time was 12.5 seconds."


def test_parse_and_store_seconds():
    assert drill.parse_seconds("42") == 42
    assert drill.parse_seconds("29.4") == 29.4
    assert drill.parse_seconds("30.0") == 30
    assert drill.store_seconds(12.04) == 12
    assert drill.store_seconds(12.06) == 12.1
    assert drill.store_seconds(30) == 30


def test_append_and_read_log(path):
    drill.append_result(path, {"Date": "2026-11-19", "Score": 18, "Total": 20, "Seconds": 42})
    drill.append_result(path, {"Date": "2026-11-19", "Score": 30, "Total": 30, "Seconds": 29})
    drill.append_result(path, {"Date": "2026-11-19", "Score": 30, "Total": 30, "Seconds": 29.4})
    rows = drill.read_results(path)
    assert rows == [
        {"date": "2026-11-19", "score": 18, "total": 20, "seconds": 42},
        {"date": "2026-11-19", "score": 30, "total": 30, "seconds": 29},
        {"date": "2026-11-19", "score": 30, "total": 30, "seconds": 29.4},
    ]
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f))
    assert header == ["Date", "Score", "Total", "Seconds"]


class FixedRng:
    def __init__(self, squares):
        self.squares = list(squares)

    def shuffle(self, items):
        items[:] = list(self.squares) + [s for s in items if s not in self.squares]


class FakeClock:
    """A clock that only moves when a test explicitly advances it."""

    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class ScriptedUI:
    """A UI whose say() and hear() advance a fake clock separately.

    Speech time is applied in say(); thinking time is applied in hear()
    and reported as last_thinking_seconds, so a test can show that only
    the latter is counted.
    """

    def __init__(self, answers, clock, think=1.0, speak=10.0, listener=None):
        self.answers = list(answers)
        self.clock = clock
        self.think_times = list(think) if isinstance(think, (list, tuple)) else None
        self.default_think = think if not isinstance(think, (list, tuple)) else 1.0
        self.speak = speak
        self.said = []
        self.last_thinking_seconds = None
        self.listener = listener
        self.hear_prompts = []

    def say(self, text):
        self.said.append(text)
        self.clock.advance(self.speak)

    def hear(self, prompt):
        self.hear_prompts.append(prompt)
        think = self.think_times.pop(0) if self.think_times is not None else self.default_think
        self.clock.advance(think)
        self.last_thinking_seconds = think
        return self.answers.pop(0)


def _half_and_half():
    all_sq = drill.all_squares()
    lights = [s for s in all_sq if drill.square_colour(s) == "light"][:10]
    darks = [s for s in all_sq if drill.square_colour(s) == "dark"][:10]
    assert len(lights) == 10 and len(darks) == 10
    return lights + darks


def test_run_drill_scores_logs_and_gives_feedback(path, capsys):
    squares = _half_and_half()
    # white is light, so the second half (dark squares) is wrong
    answers = ["light"] * 10 + ["white"] * 10
    clock = FakeClock()
    clicks = []

    def play():
        clicks.append("click")
        clock.advance(50)  # feedback must not be counted
        return True

    ui = ScriptedUI(answers, clock, think=1.0, speak=10.0)
    result = drill.run_drill(
        ui,
        path=path,
        rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19),
        clock=clock,
        play=play,
    )
    said = "\n".join(ui.said)
    assert result == {"score": 10, "total": 20, "seconds": 20, "date": "2026-11-19"}
    assert clicks == ["click"] * 10
    assert "Correct." not in said
    assert said.count("No, dark.") == 10
    assert "No, light." not in said
    assert "You scored 10 out of 20." in said
    assert "Your thinking time was 20 seconds." in said
    assert "That's your best so far." in said
    assert "I'll name twenty squares." in said
    assert "A click means correct." in said
    assert "Only your thinking time is counted." in said
    assert drill.speak_square(squares[0]) in said
    # Lots of spoken time was added (intro, 20 squares, 10 corrections,
    # the summary, and 10 clicks of 50 seconds), but none of it is counted.
    assert clock.t > 100 + 20 + 200
    out = capsys.readouterr().out
    assert f"1/20: {squares[0]}" in out
    assert f"20/20: {squares[-1]}" in out
    rows = drill.read_results(path)
    assert rows == [{"date": "2026-11-19", "score": 10, "total": 20, "seconds": 20}]

    ui2 = ScriptedUI(["light"] * 10 + ["dark"] * 10, clock, think=1.0, speak=10.0)
    result2 = drill.run_drill(
        ui2,
        path=path,
        rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19),
        clock=clock,
        play=lambda: True,
    )
    assert result2["score"] == 20 and result2["seconds"] == 20
    said = "\n".join(ui2.said)
    assert "You scored 20 out of 20." in said
    assert "Your thinking time was 20 seconds." in said
    assert "That's your best so far." in said
    rows = drill.read_results(path)
    assert rows[-1] == {"date": "2026-11-19", "score": 20, "total": 20, "seconds": 20}


def test_run_drill_says_correct_when_click_cannot_play(path):
    squares = _half_and_half()
    clock = FakeClock()
    ui = ScriptedUI(["light"] * 10 + ["dark"] * 10, clock, think=0.5, speak=8.0)
    result = drill.run_drill(
        ui, path=path, rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19), clock=clock,
        play=lambda: False,
    )
    said = "\n".join(ui.said)
    assert result["score"] == 20
    assert result["seconds"] == 10  # 20 * 0.5, speech excluded
    assert said.count("Correct.") == 20
    assert "No," not in said
    assert "Your thinking time was 10 seconds." in said


def test_run_drill_includes_reask_thinking_but_not_reprompt_speech(path):
    squares = ["a1"]  # dark
    # First attempt unrecognised; second is the answer. Speech between them
    # must not be counted.
    answers = ["", "dark"]
    clock = FakeClock()
    ui = ScriptedUI(answers, clock, think=[2.0, 3.0], speak=10.0)
    result = drill.run_drill(
        ui, path=path, rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19), clock=clock, n=1,
        play=lambda: True,
    )
    said = "\n".join(ui.said)
    assert result == {"score": 1, "total": 1, "seconds": 5, "date": "2026-11-19"}
    assert "Sorry, I didn't catch that. Light or dark." in said
    assert "Your thinking time was 5 seconds." in said
    assert ui.hear_prompts == ["Light or dark?", "Light or dark?"]


def test_run_drill_stores_one_decimal_when_needed(path):
    squares = _half_and_half()[:3]
    clock = FakeClock()
    ui = ScriptedUI(["light", "light", "dark"], clock, think=0.7, speak=9.0)
    result = drill.run_drill(
        ui, path=path, rng=FixedRng(squares),
        now=datetime.date(2026, 11, 19), clock=clock, n=3,
        play=lambda: True,
    )
    assert result["seconds"] == 2.1
    rows = drill.read_results(path)
    assert rows[0]["seconds"] == 2.1


def test_speech_start_and_thinking_helpers():
    from different_engine import speech
    result = {"text": "light", "result": [
        {"word": "light", "start": 0.8, "end": 1.2},
    ]}
    assert speech.speech_start_offset(result) == 0.8
    assert speech.utterance_duration(result) == pytest.approx(0.4)
    assert speech.speech_start_offset({"text": "light"}) is None
    assert speech.utterance_duration({"text": "light"}) is None
    # Prefer the first-word start, so trailing recognition delay is excluded.
    assert speech.thinking_seconds(pre_mic=2.0, first_word_start=0.8) == pytest.approx(2.8)
    # Fallback: arrival time minus the spoken duration.
    assert speech.thinking_seconds(
        pre_mic=2.0, result_arrived=5.0, mic_started=2.0, duration=0.4,
    ) == pytest.approx(4.6)
    # No word times and no result: just the wait before the microphone.
    assert speech.thinking_seconds(pre_mic=1.5) == 1.5
    # Typed answer: the whole interval is thinking time (no mic).
    assert speech.thinking_seconds(pre_mic=3.2) == 3.2


def test_play_click_windows_uses_winsound(monkeypatch, tmp_path):
    import sys
    wav = str(tmp_path / "click.wav")
    drill.write_click_wav(wav)
    played = []

    class Dummy:
        SND_FILENAME = 0x00020000
        SND_ASYNC = 0x0001

        @staticmethod
        def PlaySound(path, flags):
            played.append((path, flags))

    monkeypatch.setattr(drill.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", Dummy)
    assert drill.play_click(wav) is True
    assert played[0][0] == wav
    assert played[0][1] == Dummy.SND_FILENAME | Dummy.SND_ASYNC


def test_play_click_linux_uses_paplay(monkeypatch, tmp_path):
    wav = str(tmp_path / "click.wav")
    drill.write_click_wav(wav)
    pops = []

    class Proc:
        pass

    monkeypatch.setattr(drill.sys, "platform", "linux")
    monkeypatch.setattr(drill, "_which", lambda cmd: "/usr/bin/paplay" if cmd == "paplay" else None)
    monkeypatch.setattr(
        drill.subprocess, "Popen",
        lambda args, **kwargs: pops.append(args) or Proc(),
    )
    assert drill.play_click(wav) is True
    assert pops == [["paplay", wav]]


def test_play_click_falls_back_to_terminal_bell(monkeypatch, tmp_path, capsys):
    import sys
    wav = str(tmp_path / "click.wav")
    drill.write_click_wav(wav)
    monkeypatch.setattr(drill.sys, "platform", "linux")
    monkeypatch.setattr(drill, "_which", lambda cmd: None)
    monkeypatch.setitem(sys.modules, "simpleaudio", None)
    assert drill.play_click(wav) is True
    assert "\a" in capsys.readouterr().out


def test_play_click_returns_false_when_nothing_can_play(monkeypatch, tmp_path):
    wav = str(tmp_path / "click.wav")
    drill.write_click_wav(wav)
    monkeypatch.setattr(drill.sys, "platform", "linux")
    monkeypatch.setattr(drill, "_which", lambda cmd: None)

    def boom(*args, **kwargs):
        raise OSError("no audio")

    monkeypatch.setattr("builtins.print", boom)
    assert drill.play_click(wav) is False


def test_packaged_click_wav_is_a_short_wave_file():
    import wave
    path = drill.click_wav_path()
    assert path.endswith("click.wav")
    with wave.open(path, "r") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == drill.CLICK_RATE
        assert 0 < w.getnframes() / w.getframerate() <= 0.1


def test_drill_colour_words_are_in_the_speech_grammar():
    from different_engine.speech import grammar_phrases
    phrases = set(grammar_phrases())
    for phrase in ("light", "dark", "light square", "dark square",
                   "lite", "lights", "darke", "dark one", "light one",
                   "white", "black"):
        assert phrase in phrases, phrase
