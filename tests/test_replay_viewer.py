"""'Show board' between games: the command, the replay logic, PGN loading,
the analysis bar's arithmetic and the text fallback.  No window is opened."""

import builtins
import os
import time

import chess
import chess.engine
import pytest

from different_engine import game, replay_viewer as rv, settings as config, speech
from different_engine.moves import parse, special_command, vocabulary


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def played(*sans, fen=None):
    board = chess.Board(fen) if fen else chess.Board()
    for san in sans:
        board.push_san(san)
    return board


# --- the command -------------------------------------------------------------

@pytest.mark.parametrize("said", ["show board", "Show the board", "show me the board", "board",
                                  "see the board", "view board", "show board please"])
def test_show_board_phrases(said):
    assert special_command(said) == "show board"
    assert game.session_command(said) == "show-board"


def test_show_board_does_not_steal_position_or_moves():
    assert special_command("position") != "show board"
    assert parse(chess.Board(), "position").command == "position"
    assert special_command("show position") != "show board"
    assert special_command("knight f3") is None
    assert parse(chess.Board(), "e4").kind == "move"
    assert special_command("show bord") == "show board"        # a near miss is still understood


def test_show_board_words_are_in_the_grammar():
    phrases = speech.grammar_phrases()                          # its assert checks the vocabulary
    for p in ("show board", "show the board", "board"):
        assert p in phrases
    assert {"show", "board"} <= set(vocabulary())


def test_help_lists_show_board():
    text = game.format_help("between")
    assert "show board" in text and "load a PGN" in text


# --- between games -------------------------------------------------------------

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path / "games"))
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))

    def script(answers):
        answers = iter(answers)
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    return Speaker(), script, tmp_path


def test_between_games_shows_the_last_game(setup, monkeypatch, capsys):
    speaker, script, tmp_path = setup
    opened = []

    def fake_opener(replay, white_at_bottom, engine_path, games_dir, review=False):
        opened.append((replay, white_at_bottom, engine_path))
    monkeypatch.setattr(rv, "open_viewer", fake_opener)
    monkeypatch.setattr(rv.show_board, "__defaults__", (None, None, None, fake_opener))

    ui = game.Interface(speaker)
    game.remember_game(ui, played("e4", "e5", "Nf3"), chess.BLACK, "/fake/stockfish",
                       {"White": "Engine", "Black": "Player", "Result": "1-0"})
    script(["show board", "no"])
    assert game.between_games(ui) is False
    (replay, white_at_bottom, engine_path), = opened
    assert replay.length == 3 and replay.move_label(3) == "2. Nf3"
    assert white_at_bottom is False                 # the player had Black
    assert engine_path == "/fake/stockfish"
    assert speaker.said.count("Enter command.") == 2
    assert not any("will open" in t.lower() for t in speaker.said)
    out = capsys.readouterr().out
    assert "will open in a new window" not in out
    assert ("  Another game? Say yes or no. Or say: show board, square drill, milestones, "
            "rating, reset rating, level 1 to 8, or help.") in out


def test_show_board_refused_once_the_game_has_started(setup, monkeypatch):
    speaker, script, tmp_path = setup

    class FakeEngine:
        def __init__(self, path, level):
            pass

        def choose_move(self, board):
            return board.parse_san("e5")

        def close(self):
            pass
    monkeypatch.setattr(game, "Engine", FakeEngine)
    called = []
    monkeypatch.setattr(game, "show_last_board", lambda ui, path=None: called.append(path))
    script(["show board", "e4", "show board", "resign", "yes", ""])
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    assert called == ["/fake/stockfish"]            # before the first move only
    assert "The board is available between games. Your move." in speaker.said


def test_finish_remembers_the_game(setup):
    speaker, script, tmp_path = setup
    ui = game.Interface(speaker)
    script([""])
    board = played("e4", "e5")
    game.finish(ui, dict(config.DEFAULTS, level=2), board, chess.STARTING_FEN, chess.WHITE,
                "1/2-1/2", "Draw agreed", 0, {"takebacks": 0}, engine_path="/sf")
    assert ui.last_game["board"].move_stack == board.move_stack
    assert ui.last_game["player"] == chess.WHITE and ui.last_game["engine_path"] == "/sf"


# --- stepping through a game ---------------------------------------------------

def test_step_and_board_at():
    replay = rv.Replay.from_board(played("e4", "e5", "Nf3", "Nc6"))
    assert replay.length == 4
    assert rv.step(4, "forward", 4) == 4 and rv.step(0, "back", 4) == 0
    assert rv.step(2, "back", 4) == 1 and rv.step(2, "forward", 4) == 3
    assert rv.step(2, "start", 4) == 0 and rv.step(2, "end", 4) == 4
    assert replay.board_at(0).fen() == chess.STARTING_FEN
    assert replay.board_at(2).piece_at(chess.E5) == chess.Piece(chess.PAWN, chess.BLACK)
    assert replay.move_label(0) == "Starting position"
    assert replay.move_label(3) == "2. Nf3" and replay.move_label(4) == "2... Nc6"
    assert replay.counter(3) == "Move 3 of 4"
    assert replay.last_move(4) == chess.Move.from_uci("b8c6") and replay.last_move(0) is None


def test_replay_from_a_custom_start():
    fen = "4k3/8/8/8/8/8/4P3/4K3 b - - 0 40"
    replay = rv.Replay.from_board(played("Kd7", "e4", fen=fen))
    assert replay.start.fen() == fen
    assert replay.move_label(1) == "40... Kd7" and replay.move_label(2) == "41. e4"


def test_load_pgn_with_and_without_fen(tmp_path):
    plain = tmp_path / "plain.pgn"
    plain.write_text('[White "Morphy"]\n[Black "Duke"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 d6 1-0\n\n'
                     '[White "Second"]\n\n1. d4 *\n')
    rp = rv.Replay.from_pgn_file(str(plain))
    assert rp.length == 4 and rp.move_label(4) == "2... d6"
    assert "Morphy v Duke  1-0" in rp.title()

    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    custom = tmp_path / "custom.pgn"
    custom.write_text(f'[White "A"]\n[Black "B"]\n[Result "*"]\n[SetUp "1"]\n[FEN "{fen}"]\n\n1. e4 Kd7 *\n')
    rp = rv.Replay.from_pgn_file(str(custom))
    assert rp.start.fen() == fen and rp.board_at(2).piece_at(chess.D7).piece_type == chess.KING

    empty = tmp_path / "empty.pgn"
    empty.write_text("")
    with pytest.raises(ValueError):
        rv.Replay.from_pgn_file(str(empty))


def test_latest_saved_pgn(tmp_path):
    assert rv.latest_saved_pgn(str(tmp_path)) is None
    old, new = tmp_path / "a.pgn", tmp_path / "b.pgn"
    old.write_text("1. e4 *")
    new.write_text("1. d4 *")
    os.utime(old, (1, 1))
    assert rv.latest_saved_pgn(str(tmp_path)) == str(new)


def test_no_game_yet_opens_latest_saved(tmp_path):
    (tmp_path / "g.pgn").write_text('[White "Engine"]\n[Black "Player"]\n\n1. e4 e5 *\n')
    seen = []
    speaker = Speaker()
    rv.show_board(speaker, None, games_dir=str(tmp_path),
                  opener=lambda r, **k: seen.append((r, k["white_at_bottom"])))
    (replay, white_at_bottom), = seen
    assert replay.length == 2 and white_at_bottom is False
    assert speaker.said == []


# --- the analysis bar ----------------------------------------------------------

def test_eval_fraction():
    assert rv.eval_fraction(0) == pytest.approx(0.5)
    assert rv.eval_fraction(None) == 0.5
    assert 0.55 < rv.eval_fraction(100) < 0.62
    assert rv.eval_fraction(-100) == pytest.approx(1 - rv.eval_fraction(100))
    assert rv.eval_fraction(300) < rv.eval_fraction(900) < 1.0
    assert rv.eval_fraction(100000) == rv.eval_fraction(2000)        # clamped
    assert rv.eval_fraction(mate=3) == 1.0 and rv.eval_fraction(mate=-2) == 0.0


def test_eval_text():
    assert rv.eval_text(80) == "+0.8" and rv.eval_text(-134) == "-1.3"
    assert rv.eval_text(3) == "0.0" and rv.eval_text(None) == ""
    assert rv.eval_text(mate=3) == "M3" and rv.eval_text(mate=-2) == "-M2"


def test_bar_split_follows_the_board():
    assert rv.bar_split(0.5, 512) == 256
    assert rv.bar_split(1.0, 512) == 0            # all White: White fills up from the bottom
    assert rv.bar_split(0.25, 400, white_at_bottom=True) == 300
    assert rv.bar_split(0.25, 400, white_at_bottom=False) == 100


def test_game_over_eval():
    mate = played("f3", "e5", "g4", "Qh4")
    assert rv.game_over_eval(mate) == (None, -1, "Checkmate")
    assert rv.game_over_eval(chess.Board()) is None
    assert rv.game_over_eval(chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"))[2] == "Stalemate"


def test_analyser_caches_and_closes():
    class FakeSimpleEngine:
        looks = 0
        quit_called = False

        def analyse(self, board, limit):
            FakeSimpleEngine.looks += 1
            move = next(iter(board.legal_moves))
            return {"score": chess.engine.PovScore(chess.engine.Cp(42), board.turn), "pv": [move]}

        def quit(self):
            FakeSimpleEngine.quit_called = True

    a = rv.Analyser("/fake", popen=lambda path: FakeSimpleEngine())
    board = played("e4")
    a.request("k", board)
    for _ in range(100):
        if a.result("k"):
            break
        time.sleep(0.01)
    found = a.result("k")
    assert found["cp"] == -42                     # Black to move, +42 for Black = -0.42 for White
    assert found["best"] == board.san(next(iter(board.legal_moves)))
    a.request("k", board)                          # already known: not looked at again
    time.sleep(0.05)
    assert FakeSimpleEngine.looks == 1
    a.request("mate", played("f3", "e5", "g4", "Qh4"))
    assert a.result("mate")["mate"] == -1          # no engine needed
    a.close()
    assert FakeSimpleEngine.quit_called


STOCKFISH = "/workspace/stockfish/stockfish-ubuntu-x86-64-avx2"


@pytest.mark.skipif(not os.path.exists(STOCKFISH), reason="Stockfish not on this computer")
def test_analyser_with_stockfish():
    a = rv.Analyser(STOCKFISH, seconds=0.05)
    try:
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
        a.request(1, board)
        for _ in range(200):
            if a.result(1):
                break
            time.sleep(0.02)
        assert a.result(1)["mate"] == 1 and a.result(1)["best"] == "Ra8#"
    finally:
        a.close()


# --- no window -----------------------------------------------------------------

def test_ascii_board_from_each_side():
    board = played("e4")
    white = rv.ascii_board(board).splitlines()
    assert white[0] == "  8  r n b q k b n r"
    assert white[4] == "  4  . . . . P . . ."
    assert white[-1] == "     a b c d e f g h"
    black = rv.ascii_board(board, white_at_bottom=False).splitlines()
    assert black[0] == "  1  R N B K Q B N R"
    assert black[-1] == "     h g f e d c b a"


def test_text_fallback_when_no_window(capsys):
    def broken(*a, **k):
        raise RuntimeError("no display")
    speaker = Speaker()
    how = rv.show_board(speaker, {"board": played("e4", "e5"), "player": chess.WHITE}, opener=broken)
    assert how == "text"
    assert any("as text" in s for s in speaker.said)
    assert not any("will open" in s.lower() for s in speaker.said)
    out = capsys.readouterr().out
    assert "will open in a new window" not in out
    assert "  5  . . . . p . . ." in out and "1... e5" in out


def test_board_launch_option_opens_viewer_silently(monkeypatch, tmp_path):
    from different_engine import __main__ as entry, replay_viewer, settings as config
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path))
    monkeypatch.setattr(entry, "ensure_stockfish", lambda path: "/fake/stockfish")
    calls = []

    def fake_show(ui, last, engine_path=None, games_dir=None, review=False):
        calls.append((last, engine_path, games_dir, ui.speaker.backend, review))
        return "window"

    monkeypatch.setattr(replay_viewer, "show_board", fake_show)
    monkeypatch.setattr(entry, "VoiceInput", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no microphone")))
    monkeypatch.setattr(entry, "play", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no game")))
    assert entry.main(["--board"]) == 0
    assert calls == [(None, "/fake/stockfish", str(tmp_path), None, True)]
