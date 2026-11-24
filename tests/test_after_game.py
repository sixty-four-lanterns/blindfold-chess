"""A whole game and the after-game report, with a stand-in engine and scripted answers."""

import builtins
import csv

import chess
import chess.pgn
import pytest

from different_engine import game, ratings, reconstruction, review, settings as config


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
        return chess.pgn.read_game(f)


def read_log(tmp_path):
    with open(tmp_path / "rating_log.csv", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_whole_game_and_report(setup, monkeypatch, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)

    def fake_window(board, white_at_bottom, on_score):
        assert white_at_bottom
        guess = board.copy()
        guess.remove_piece_at(chess.A8)                     # forget one rook
        score = reconstruction.score_reconstruction(board, guess)
        on_score(score)
        return score
    monkeypatch.setattr(reconstruction, "reconstruct_position", fake_window)
    looked = [
        {"move_number": 2, "san": "Nf3", "played": "Knight to f3", "best_san": "Nf3", "best": "Knight to f3",
         "loss": 0, "matched": True},
        {"move_number": 3, "san": "Bb5", "played": "Bishop to b5", "best_san": "Bc4", "best": "Bishop to c4",
         "loss": 80, "matched": False},
        {"move_number": 5, "san": "O-O", "played": "Castles kingside", "best_san": "d4", "best": "Pawn to d4",
         "loss": 220, "matched": False},
    ]
    monkeypatch.setattr(review, "analyse_game", lambda *a, **k: looked)

    script([
        "knight e5", "", "e4",                       # move 1: one illegal attempt, one mishearing
        "position", "Nf3",                           # move 2: a position request
        "lost thread", "I've lost the thread", "Bb5",  # move 3: marked once, kept
        "Ba4", "castles kingside",
        "resign", "yes",                             # move 6 (after the checkpoint reminder)
        "review",                                    # ask for the after-game review
        "yes",                                       # lost the thread at move 3? yes
        "no",                                        # honesty rules
        "a short note",
        "yes",                                       # reconstruction
        "yes",                                       # slip review
        "visualisation", "chess",                    # the two slips
        "no",                                        # read the moves aloud
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)

    out = capsys.readouterr().out
    assert game.CHECKPOINT not in said               # shown on screen only, never spoken
    assert out.count(game.CHECKPOINT) == 1
    assert "I'll note that you lost the thread at move 3" in said
    assert "already noted that you first lost the thread at move 3" in said
    assert "During the game you told me you had lost the thread at move 3" in said
    assert "You placed 31 of 32 pieces on the correct square, which is 97 per cent." in said
    assert "At move 5 you played castles kingside. The engine preferred pawn to d4." in said
    assert "You tried one illegal move, at move 1." in said
    assert "You asked for the position once, at move 2." in said
    assert "That was position request 1 of 3." not in said
    assert "  That was position request 1 of 3." in out
    assert "Your rating is 600." in said             # loss at level 2 (1000) -> 600
    assert "Your blindfold performance rating is" not in said
    assert "  Your blindfold performance rating is 600." in out
    assert "That comes from" in out and "That comes from" not in said
    assert "will open in a new window" not in said
    assert "Check my position" in out and "Check my position" not in said
    assert "Say review for the after-game review" in said
    # saved and the rating are spoken before the reconstruction test
    assert said.index("Game saved in your games folder.") < said.index("Say review for the after-game review")
    assert said.index("Your rating is 600.") < said.index("You placed 31 of 32")
    # the final position isn't shown before the reconstruction test
    assert said.index("Game saved in your games folder.") < said.index("You placed 31 of 32")

    headers = read_pgn(tmp_path).headers
    assert headers["FirstLostThread"] == "3" and headers["LostThreadMarked"] == "3"
    assert headers["PositionRequests"] == "1" and headers["PositionRequestMoves"] == "2"
    assert headers["IllegalAttempts"] == "1 (1: knight e5)"
    assert headers["Reconstruction"] == "31/32, 97%"
    assert headers["AverageCentipawnLoss"] == "100" and headers["EngineMatches"] == "1/3"
    assert headers["Slips"] == "3 Bb5 visualisation; 5 O-O chess"

    (row,) = read_log(tmp_path)
    assert row["Result"] == "0" and row["First lost thread"] == "3" and row["Notes"] == "a short note"
    assert row["Illegal attempts"] == "1" and row["Illegal attempt moves"] == "1"
    assert row["Position request moves"] == "2" and row["Reconstruction"] == "31/32"
    assert row["Reconstruction per cent"] == "97" and row["Engine matches"] == "1/3"
    assert len(ratings.read_games(config.RATING_LOG)) == 1


def test_no_window_and_first_illegal_attempt_suggested(setup, monkeypatch):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, level=3)

    def no_display(*args, **kwargs):
        raise RuntimeError("no display")
    monkeypatch.setattr(reconstruction, "reconstruct_position", no_display)
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]:
        board.push_san(san)
    log = {"illegal": [{"move": 2, "said": "bishop b5", "reason": "No bishop of yours can go to b5."}],
           "requests": [], "lost_mark": None}
    script(["review",         # ask for the after-game review
            "yes",            # was the illegal attempt at move 2 when you lost the thread?
            "no", "", "yes",  # honesty, note, reconstruction (no window)
            "no"])            # read aloud (no engine path, so no slip review question)
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN, chess.WHITE, "1/2-1/2",
                "Draw agreed", 0, log, engine_path=None)
    said = "\n".join(speaker.said)
    assert "Your first illegal move attempt was at move 2, when you said 'bishop b5'" in said
    assert "couldn't open a board window" in said
    assert read_pgn(tmp_path).headers["FirstLostThread"] == "2"
    assert "Reconstruction" not in read_pgn(tmp_path).headers
    (row,) = read_log(tmp_path)
    assert row["Result"] == "0.5" and row["Reconstruction"] == ""


def test_saying_no_to_the_suggestion_asks_the_usual_question(setup):
    speaker, script, tmp_path = setup
    script(["no", "eleven"])
    lost = game.lost_thread_question(game.Interface(speaker), marked=None,
                                     illegal=[{"move": 4, "said": "Nf6", "reason": ""}])
    assert lost == "11"
    script(["never"])
    assert game.lost_thread_question(game.Interface(speaker), marked=7) == ""
    script(["9"])
    assert game.lost_thread_question(game.Interface(speaker), marked=7) == "9"


def test_checkpoint_due():
    board = chess.Board()
    assert not game.checkpoint_due(board, chess.WHITE, set())
    for san in ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"]:
        board.push_san(san)
    assert board.fullmove_number == 6
    assert game.checkpoint_due(board, chess.WHITE, set())
    assert not game.checkpoint_due(board, chess.BLACK, set())
    assert not game.checkpoint_due(board, chess.WHITE, {6})


def test_not_sure_is_not_yes():
    assert game.is_yes("yes please".split()) and not game.is_yes("not sure".split())


def test_default_play_skips_start_and_skips_review_if_declined(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=5, position_limit=2, checkpoint_reminders=True)
    script([
        "e4",
        "Nf3",
        "lost thread", "I've lost the thread", "Bb5",
        "Ba4", "castles kingside",
        "resign", "yes",
        "",                                          # decline the after-game review
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)

    assert "You're White, level 5, two position requests." in said
    assert "Shall we start from the usual opening position" not in said
    assert game.CHECKPOINT not in said               # on screen only
    assert game.CHECKPOINT in capsys.readouterr().out  # reminders follow settings.json, default on
    assert "I'll note that you lost the thread at move 3" in said
    assert "already noted that you first lost the thread at move 3" in said
    assert "Say review for the after-game review" in said
    assert "During the game you told me you had lost the thread" not in said
    assert "honesty rules" not in said
    assert "reconstruct" not in said.lower()
    assert "biggest slips" not in said
    assert "read the moves" not in said
    assert "Game saved in your games folder." in said
    assert "Your rating is 1200." in said            # loss at level 5 (1600) -> 1200
    assert "Your blindfold performance rating is" not in said
    assert said.index("Game saved in your games folder.") < said.index("Say review for the after-game review")
    assert said.index("Your rating is 1200.") < said.index("Say review for the after-game review")

    headers = read_pgn(tmp_path).headers
    assert headers["LostThreadMarked"] == "3"
    assert headers["FirstLostThread"] == "never"
    assert "Reconstruction" not in headers
    (row,) = read_log(tmp_path)
    assert row["Result"] == "0"
    assert row["First lost thread"] == ""
    assert row["Rule breaks"] == ""
    assert row["Notes"] == ""
    assert row["Reconstruction"] == ""
    assert row["Average centipawn loss"] == ""
    assert row["Slips"] == ""


def test_finish_skips_review_but_saves_and_rates(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, level=3)
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]:
        board.push_san(san)
    log = {"illegal": [{"move": 2, "said": "bishop b5", "reason": "No bishop of yours can go to b5."}],
           "requests": [3], "lost_mark": 2}
    script([""])                                     # decline the review
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN, chess.WHITE, "1/2-1/2",
                "Draw agreed", 1, log, engine_path=None)
    said = "\n".join(speaker.said)
    assert "Game saved in your games folder." in said
    assert "Your rating is 1200." in said            # draw at level 3 (1200)
    assert "Your blindfold performance rating is" not in said
    assert "Say review for the after-game review" in said
    assert "lose the thread" not in said
    assert "illegal move attempt" not in said
    assert "honesty" not in said
    assert "reconstruct" not in said.lower()
    assert "You asked for the position" not in said
    headers = read_pgn(tmp_path).headers
    assert headers["LostThreadMarked"] == "2"
    assert headers["FirstLostThread"] == "never"
    assert headers["PositionRequests"] == "1"
    (row,) = read_log(tmp_path)
    assert row["Result"] == "0.5"
    assert row["First lost thread"] == ""
    assert row["Notes"] == ""
    assert row["Reconstruction"] == ""
    assert row["Position requests"] == "1"


def test_default_play_uses_saved_custom_start(setup):
    speaker, script, tmp_path = setup
    fen = "8/8/8/4k3/8/4K3/8/8 w - - 0 1"
    s = dict(config.DEFAULTS, colour="white", level=1, start="custom", custom_fen=fen)
    script([""])                                     # decline the review
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Shall we start from the usual opening position" not in said
    assert "Here is the starting position" in said
    assert "Game saved in your games folder." in said
    headers = read_pgn(tmp_path).headers
    assert headers.get("SetUp") == "1"
    assert "4k3" in headers["FEN"]


def _patch_main(monkeypatch, speaker, listener=None):
    from different_engine import __main__ as entry
    calls = {"choose": 0, "mic": 0, "play": []}

    def fake_choose(ui, s, first_time, offer_same=True):
        calls["choose"] += 1
        return s

    def fake_mic(*a, **k):
        calls["mic"] += 1

    def fake_play(ui, s, engine_path, setup=False, quick=None):
        calls["play"].append({"settings": dict(s), "setup": setup})

    monkeypatch.setattr(entry, "choose_settings", fake_choose)
    monkeypatch.setattr(entry, "test_microphone", fake_mic)
    monkeypatch.setattr(entry, "play", fake_play)
    monkeypatch.setattr(entry, "ensure_stockfish", lambda path: "/fake/stockfish")
    monkeypatch.setattr(entry, "Speaker", lambda enabled=True, rate=160: speaker)
    if listener is not None:
        monkeypatch.setattr(entry, "ensure_vosk_model", lambda: "model")
        monkeypatch.setattr(entry, "VoiceInput", lambda *a, **k: listener)
    return entry, calls


def test_main_default_skips_settings(setup, monkeypatch):
    speaker, script, tmp_path = setup
    entry, calls = _patch_main(monkeypatch, speaker)
    script(["no"])
    assert entry.main(["--text"]) == 0
    assert calls["choose"] == 0
    assert calls["mic"] == 0
    assert calls["play"] == [{"settings": dict(config.DEFAULTS), "setup": False}]
    assert any("Welcome to the Different Engine" in t for t in speaker.said)
    assert (tmp_path / "settings.json").exists()


def test_main_quick_is_alias_for_default(setup, monkeypatch):
    import json
    speaker, script, tmp_path = setup
    saved = dict(config.DEFAULTS, colour="black", level=7, position_limit=0)
    (tmp_path / "settings.json").write_text(json.dumps(saved))
    entry, calls = _patch_main(monkeypatch, speaker)
    script(["no"])
    assert entry.main(["--text", "--quick", "--hands-free", "--mic", "2"]) == 0
    assert calls["choose"] == 0
    assert calls["play"][0]["setup"] is False
    assert calls["play"][0]["settings"]["colour"] == "black"
    assert calls["play"][0]["settings"]["level"] == 7
    assert calls["play"][0]["settings"]["position_limit"] == 0


def test_main_setup_asks_settings(setup, monkeypatch):
    import json
    speaker, script, tmp_path = setup
    (tmp_path / "settings.json").write_text(json.dumps(config.DEFAULTS))
    entry, calls = _patch_main(monkeypatch, speaker)
    script(["no"])
    assert entry.main(["--text", "--setup"]) == 0
    assert calls["choose"] == 1
    assert calls["play"][0]["setup"] is True


def test_main_setup_wins_over_quick(setup, monkeypatch):
    import json
    speaker, script, tmp_path = setup
    (tmp_path / "settings.json").write_text(json.dumps(config.DEFAULTS))
    entry, calls = _patch_main(monkeypatch, speaker)
    script(["no"])
    assert entry.main(["--text", "--setup", "--quick"]) == 0
    assert calls["choose"] == 1
    assert calls["play"][0]["setup"] is True


class DummyListener:
    """Use the scripted input() answers, as a real microphone would be asked to listen."""
    def listen(self, prompt=""):
        return input(prompt)


def test_main_first_run_offers_mic_test(setup, monkeypatch):
    speaker, script, tmp_path = setup
    entry, calls = _patch_main(monkeypatch, speaker, listener=DummyListener())
    script(["yes", "no"])                            # yes to the mic test, no to another game
    assert entry.main([]) == 0
    assert calls["mic"] == 1
    assert calls["choose"] == 0
    assert calls["play"][0]["setup"] is False


# ---------------------------------------------------------------------------
# Quick start, colour switch, status line and optional review
# ---------------------------------------------------------------------------

class FlexibleEngine:
    """Plays any legal move, so the tests can switch the player to Black."""

    def __init__(self, path, level):
        pass

    def choose_move(self, board):
        return next(iter(board.legal_moves))

    def accepts_draw(self, board, colour):
        return False

    def close(self):
        pass


def test_pregame_command_phrases():
    assert game.pregame_command("settings") == "settings"
    assert game.pregame_command("open settings please") == "settings"
    assert game.pregame_command("play black") == "black"
    assert game.pregame_command("I'd like to play as black") == "black"
    assert game.pregame_command("play white") == "white"
    assert game.pregame_command("switch colours") == "switch"
    assert game.pregame_command("switch colors") == "switch"
    assert game.pregame_command("switch sides") == "switch"
    assert game.pregame_command("random") == "random"
    assert game.pregame_command("play random") == "random"
    assert game.pregame_command("e4") is None
    assert game.pregame_command("knight f3") is None
    assert game.pregame_command("") is None


def test_play_black_before_first_move_saves_and_restarts(setup, monkeypatch):
    monkeypatch.setattr(game, "Engine", FlexibleEngine)
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script([
        "play black",
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "You'll play black." in said
    assert "Starting again from the start." in said
    assert "You're Black, level 2, three position requests." in said
    assert s["colour"] == "black"
    import json
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["colour"] == "black"
    (row,) = read_log(tmp_path)
    assert row["Colour"] == "Black"
    assert row["Result"] == "unrated"                # resigned in the first five moves


def test_switch_colours_and_settings_help_mentioned(setup, monkeypatch, capsys):
    monkeypatch.setattr(game, "Engine", FlexibleEngine)
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=3)
    script(["help", "switch colours", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "Now available -- During a game" in out
    assert "Now available -- Before your first move, or between games" in out
    assert "play white / play black / switch colours / random" in out
    assert "square drill" in out and "progress" in out and "reset rating" in out
    assert "Position requests left:" in out
    assert "Now available" not in said
    assert "play white / play black / switch colours / random" not in said
    assert "You'll play black." in said
    assert "You're Black, level 3," in said
    assert s["colour"] == "black"


def test_colour_change_refused_after_first_move(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "play black", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "You can only change that before your first move" in said
    assert "You'll play black." not in said
    assert s["colour"] == "white"
    (row,) = read_log(tmp_path)
    assert row["Colour"] == "White"


def test_settings_before_first_move(setup, monkeypatch):
    monkeypatch.setattr(game, "Engine", FlexibleEngine)
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script([
        "settings",
        "black",
        "4",
        "1",
        "usual",
        "resign", "yes",
        "",
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Starting again with your new settings." in said
    assert "You're Black, level 4, one position request." in said
    assert s["colour"] == "black" and s["level"] == 4 and s["position_limit"] == 1
    import json
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["level"] == 4 and saved["colour"] == "black"


def test_setup_flag_asks_for_start_position(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["usual", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish", setup=True)
    said = "\n".join(speaker.said)
    assert "Shall we start from the usual opening position" in said
    assert "Game saved in your games folder." in said


def test_review_updates_pgn_and_log_without_duplicating_row(setup, monkeypatch):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, level=3)
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]:
        board.push_san(san)
    log = {"illegal": [{"move": 2, "said": "bishop b5", "reason": "No bishop of yours can go to b5."}],
           "requests": [3], "lost_mark": 2}
    script(["review", "yes", "no", "a note", "no", "no"])  # review, lost thread, honesty, note, no reconstruction, no read-aloud
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN, chess.WHITE, "1/2-1/2",
                "Draw agreed", 1, log, engine_path=None)
    rows = read_log(tmp_path)
    assert len(rows) == 1
    assert rows[0]["First lost thread"] == "2"
    assert rows[0]["Notes"] == "a note"
    assert rows[0]["Result"] == "0.5"
    assert read_pgn(tmp_path).headers["FirstLostThread"] == "2"


def test_checkpoint_off_when_settings_say_so(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, checkpoint_reminders=False)
    script([
        "e4", "Nf3", "Bb5", "Ba4", "castles kingside",
        "resign", "yes", "",
    ])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    assert game.CHECKPOINT not in "\n".join(speaker.said)
    (row,) = read_log(tmp_path)
    assert row["Result"] == "0"                      # five moves made, so the resignation is rated
    assert game.CHECKPOINT not in capsys.readouterr().out


def test_status_line_after_moves_has_no_board_or_eval(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=3, position_limit=3)
    script(["e4", "position", "Nf3", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    out = capsys.readouterr().out
    assert ("Move 1 | You: White | Level 3 | Position requests left: 3 | "
            "Blindfold rating: no rating yet | Milestones 0/25") in out
    assert ("Move 2 | You: White | Level 3 | Position requests left: 2 | "
            "Blindfold rating: no rating yet | Milestones 0/25") in out
    assert "rnbqkbnr" not in out.lower()
    assert "fen" not in out.lower()
    assert "eval" not in out.lower()
    assert "centipawn" not in out.lower()
    assert "evaluation" not in out.lower()


def test_format_status_with_and_without_rating(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    board = chess.Board()
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    line = game.format_status(board, chess.WHITE, 2, 3, 0, games=[])
    assert line == ("Move 1 | You: White | Level 2 | Position requests left: 3 | "
                    "Blindfold rating: no rating yet | Milestones 0/25")
    games = [{"opponent": "x", "rating": 1200, "result": 1.0}]
    board.push_san("e4")
    line = game.format_status(board, chess.BLACK, 4, -1, 0, games=games)
    assert line == ("Move 1 | You: Black | Level 4 | Position requests left: unlimited | "
                    "Blindfold rating: 1600 (1 game) | Milestones 0/25")
    line = game.format_status(board, chess.WHITE, 2, 3, 0, games=[], milestones_count=(9, 25))
    assert line.endswith("| Milestones 9/25")
    assert "Take-backs" not in line
    assert "eval" not in line.lower() and "board" not in line.lower()
    with_tb = game.format_status(board, chess.WHITE, 2, 3, 0, games=[], milestones_count=(9, 25), takebacks=2)
    assert with_tb.endswith("| Take-backs: 2")
    assert with_tb.startswith("Move 1 | You: White | Level 2 |")


def test_session_command_phrases():
    assert game.session_command("square drill") == "drill"
    assert game.session_command("colour drill") == "drill"
    assert game.session_command("color drill") == "drill"
    assert game.session_command("square colours") == "drill"
    assert game.session_command("square colors") == "drill"
    assert game.session_command("progress") == "progress"
    assert game.session_command("my progress") == "progress"
    assert game.session_command("milestones") == "progress"
    assert game.session_command("how am I doing") == "progress"
    assert game.session_command("process") == "progress"
    assert game.session_command("rating") == "rating"
    assert game.session_command("my rating") == "rating"
    assert game.session_command("what's my rating") == "rating"
    assert game.session_command("take back") is None
    assert game.session_command("reset rating") == "reset-rating"
    assert game.session_command("reset my rating") == "reset-rating"
    assert game.session_command("reset the rating") == "reset-rating"
    assert game.session_command("play black") == "black"
    assert game.session_command("settings") == "settings"
    assert game.session_command("help") == "help"
    assert game.session_command("commands") == "help"
    assert game.session_command("what can I say") == "help"
    assert game.session_command("last move") is None
    assert game.session_command("show moves") is None
    assert game.session_command("show board") == "show-board"
    assert game.session_command("level 4") == "level"
    assert game.session_command("set level four") == "level"
    assert game.session_command("e4") is None


def test_finish_announces_checkmate_milestones(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="black", level=2)
    board = chess.Board()
    for move in ["f3", "e5", "g4", "Qh4"]:
        board.push_san(move)
    script([""])   # decline the review
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN,
                chess.BLACK, "0-1", "Checkmate", 0, {})
    said = "\n".join(speaker.said)
    assert "New milestone: first checkmate." in said
    assert "New milestone: first win." in said
    assert "New milestone: a completed game." in said
    assert "You've earned" in said and "of 25" in said


def test_drill_and_reset_refused_after_first_move(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "square drill", "reset rating", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert said.count("You can only do that before your first move, or between games") == 2
    assert "Square-colour drill" not in said
    assert "Your rating has been reset" not in said


def test_progress_during_game(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["progress", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Foundations [" in said
    assert "Next up:" in said


def test_main_progress_stops_without_playing(setup, monkeypatch):
    speaker, script, tmp_path = setup
    entry, calls = _patch_main(monkeypatch, speaker)
    assert entry.main(["--text", "--progress"]) == 0
    assert calls["play"] == []
    assert any("Foundations [" in t for t in speaker.said)


def test_main_reset_rating_flag(setup, monkeypatch):
    speaker, script, tmp_path = setup
    ratings.append_game(config.RATING_LOG, {
        "Date": "2026-11-01", "Opponent": "Stockfish level 2", "Opponent rating": 1000, "Result": "1",
    })
    entry, calls = _patch_main(monkeypatch, speaker)
    script(["yes", "no"])   # confirm reset, then no to another game
    assert entry.main(["--text", "--reset-rating"]) == 0
    assert calls["play"]  # a game still starts after the reset
    assert not (tmp_path / "rating_log.csv").exists()
    assert (tmp_path / "rating_log_archived_2026-11-19.csv").exists() or list(tmp_path.glob("rating_log_archived_*.csv"))
    assert any("Your rating has been reset" in t for t in speaker.said)


def test_reset_rating_asks_and_can_be_declined(setup):
    import datetime
    speaker, script, tmp_path = setup
    ratings.append_game(config.RATING_LOG, {
        "Date": "2026-11-01", "Opponent": "Stockfish level 2", "Opponent rating": 1000, "Result": "1",
    })
    script(["no"])
    result = game.reset_rating(game.Interface(speaker), today=datetime.date(2026, 11, 19))
    assert result is False
    assert (tmp_path / "rating_log.csv").exists()
    assert list(tmp_path.glob("rating_log_archived_*.csv")) == []
    assert "Your rating is unchanged." in "\n".join(speaker.said)

    script(["yes"])
    result = game.reset_rating(game.Interface(speaker), today=datetime.date(2026, 11, 19))
    assert str(result).endswith("rating_log_archived_2026-11-19.csv")
    assert not (tmp_path / "rating_log.csv").exists()
    assert "Your rating has been reset. Your old games are kept in rating_log_archived_2026-11-19.csv." in "\n".join(speaker.said)



def test_format_help_marks_current_group_and_stays_compact():
    text = game.format_help("during", requests_left=2)
    lines = text.splitlines()
    assert lines[0] == "Commands"
    assert 1 < len(lines) <= 34
    assert all(ord(ch) < 128 for ch in text)
    assert "Now available -- During a game" in text
    assert "Position requests left: 2" in text
    assert "Now available -- Before your first move" not in text
    assert "Before your first move, or between games" in text
    assert "take back / undo / go back" in text
    assert "last move" in text
    assert "show moves                     The whole game on screen (uses a position request)" in text
    assert "level 1 to 8" in text
    assert "light / dark" in text
    assert "visualisation" in text
    assert "Also available at other times" in text

    before = game.format_help("before", requests_left="unlimited")
    assert "Now available -- During a game" in before
    assert "Now available -- Before your first move, or between games" in before
    assert "Position requests left: unlimited" in before

    after = game.format_help("after")
    assert "Now available -- After a game" in after
    assert "review" in after
    assert "Position requests left" not in after

    drill = game.format_help("drill")
    assert "Now available -- Square-colour drill" in drill
    assert "light / dark" in drill


def test_help_prints_list_and_is_not_spoken(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["help", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "Commands" in out
    assert "Now available -- During a game" in out
    assert "Now available -- Before your first move, or between games" in out
    assert "Position requests left: 3" in out
    assert "Now available" not in said
    assert "Position requests left" not in said
    assert "You resign" in said
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 0


def test_help_after_a_move_uses_during_context(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["e4", "help", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "Now available -- During a game" in out
    assert "Now available -- Before your first move" not in out
    assert "Position requests left: 3" in out
    assert "Now available" not in said
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 0


def test_help_between_games_is_printed_not_spoken(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    ui = game.Interface(speaker)
    script(["resign", "yes", "", "what can I say", "no"])
    game.play(ui, s, "/fake/stockfish")
    assert game.between_games(ui) is False
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "Now available -- Before your first move, or between games" in out
    assert "Now available -- During a game" not in out or out.rfind("Now available -- Before your first move") > out.rfind("Now available -- During a game")
    assert "Now available" not in said



def test_last_moves_spoken_covers_each_history_case():
    start = chess.Board()
    assert game.last_moves_spoken(start, chess.WHITE) == "No moves yet."
    assert game.last_moves_spoken(start, chess.BLACK) == "No moves yet."

    # Player moved, engine has not replied
    board = start.copy()
    board.push_san("e4")
    assert game.last_moves_spoken(board, chess.WHITE) == "Your last move was pawn to e4."

    # Both sides have moved, player's turn
    board.push_san("e5")
    assert game.last_moves_spoken(board, chess.WHITE) == (
        "Your last move was pawn to e4, and I played pawn to e5."
    )

    # After the player's latest move, before a reply: only the player's move
    board.push_san("Nf3")
    assert game.last_moves_spoken(board, chess.WHITE) == "Your last move was knight to f3."

    # The wording from the command's example: Nf3, engine replies e5
    example = chess.Board()
    example.push_san("Nf3")
    example.push_san("e5")
    assert game.last_moves_spoken(example, chess.WHITE) == (
        "Your last move was knight to f3, and I played pawn to e5."
    )

    # Engine moved first as White; the player (Black) has not moved
    opening = chess.Board()
    opening.push_san("e4")
    assert game.last_moves_spoken(opening, chess.BLACK) == "I played pawn to e4."

    # Player (Black) has answered, engine has not yet replied to that
    opening.push_san("e5")
    assert game.last_moves_spoken(opening, chess.BLACK) == "Your last move was pawn to e5."

    # After a take-back, the wording follows the current history
    after = chess.Board()
    for san in ("e4", "e5", "Nf3"):
        after.push_san(san)
    message, _ = game.take_back(after, chess.WHITE)
    assert message.startswith("Taken back.")
    assert game.last_moves_spoken(after, chess.WHITE) == (
        "Your last move was pawn to e4, and I played pawn to e5."
    )
    game.take_back(after, chess.WHITE)
    assert game.last_moves_spoken(after, chess.WHITE) == "No moves yet."


def test_last_move_command_in_play_does_not_use_a_request(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["last move", "e4", "last move", "repeat", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "No moves yet." in said
    assert "Your last move was pawn to e4, and I played pawn to e5." in said
    assert "My last move was pawn to e5." in said
    assert said.count("That was position request") == 0
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 0


def test_last_move_when_engine_opens_as_white(setup, monkeypatch):
    monkeypatch.setattr(game, "Engine", FlexibleEngine)
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="black", level=2, position_limit=2)
    script(["what did you play", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    # FlexibleEngine plays the first legal move, which from the start is a2a3? 
    # next(iter(board.legal_moves)) -- order is not guaranteed to be e4.
    # Just check the "I played ..." form and no position request.
    assert any(line.startswith("I played ") for line in speaker.said)
    assert "No moves yet." not in said
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 0



def test_level_command_applies_immediately_before_first_move(setup):
    import json
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["level 4", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Engine level 4, about 1400." in said
    assert "Level 4 from your next game." not in said
    assert s["level"] == 4
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["level"] == 4
    (row,) = read_log(tmp_path)
    assert row["Opponent"] == "Stockfish level 4"
    assert int(row["Position requests"]) == 0


def test_level_command_after_a_move_waits_until_next_game(setup):
    import json
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["e4", "change level to 5", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "Level 5 from your next game." in said
    assert "Engine level 5, about 1600." not in said
    assert s["level"] == 5
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["level"] == 5
    (row,) = read_log(tmp_path)
    assert row["Opponent"] == "Stockfish level 2"
    assert int(row["Position requests"]) == 0


def test_level_command_rejects_out_of_range(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["level 9", "level twenty", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert said.count("Please say a level from 1 to 8, or beginner 1 or 2.") == 2
    assert s["level"] == 2
    (row,) = read_log(tmp_path)
    assert row["Opponent"] == "Stockfish level 2"


def test_finish_auto_level_up_saves_and_announces(setup):
    import json
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=3)
    for _ in range(4):
        ratings.append_game(config.RATING_LOG, {
            "Date": "2026-11-01", "Opponent": "Stockfish level 3",
            "Opponent rating": 1200, "Result": "1",
        })
    script([""])
    board = chess.Board()
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN,
                chess.WHITE, "1-0", "Checkmate", 0)
    said = "\n".join(speaker.said)
    assert ("You scored over 70 per cent in your last five games at level 3, "
            "so I've moved the engine up to level 4.") in said
    assert "Try moving the engine up a level" not in said
    assert s["level"] == 4
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["level"] == 4
    assert ratings.maybe_level_up(ratings.read_games(config.RATING_LOG), 4) == (None, None)


def test_finish_does_not_auto_up_over_an_already_chosen_next_level(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=5)
    for _ in range(4):
        ratings.append_game(config.RATING_LOG, {
            "Date": "2026-11-01", "Opponent": "Stockfish level 3",
            "Opponent rating": 1200, "Result": "1",
        })
    script([""])
    game.finish(game.Interface(speaker), s, chess.Board(), chess.STARTING_FEN,
                chess.WHITE, "1-0", "Checkmate", 0, game_level=3)
    said = "\n".join(speaker.said)
    assert "moved the engine up" not in said
    assert s["level"] == 5


def test_finish_does_not_auto_up_at_level_eight(setup):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=8)
    for _ in range(4):
        ratings.append_game(config.RATING_LOG, {
            "Date": "2026-11-01", "Opponent": "Stockfish level 8",
            "Opponent rating": 2300, "Result": "1",
        })
    script([""])
    game.finish(game.Interface(speaker), s, chess.Board(), chess.STARTING_FEN,
                chess.WHITE, "1-0", "Checkmate", 0)
    said = "\n".join(speaker.said)
    assert "moved the engine up" not in said
    assert s["level"] == 8


def test_finish_speaks_only_the_short_rating(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, level=2)
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]:
        board.push_san(san)
    script([""])                                     # decline the review
    game.finish(game.Interface(speaker), s, board, chess.STARTING_FEN, chess.WHITE,
                "0-1", "Checkmate", 0, {})
    said = speaker.said
    assert "Your rating is 600." in said             # loss at level 2 (1000) -> 600
    assert said.count("Your rating is 600.") == 1
    assert "Your blindfold performance rating is 600." not in said
    assert not any(t.startswith("That comes from") for t in said)
    assert not any(t.startswith("With only") for t in said)
    assert ratings.CAUTIONS not in said
    out = capsys.readouterr().out
    assert "  Your blindfold performance rating is 600." in out
    assert "That comes from your only game: 0 wins, 0 draws and 1 loss, against an average opponent rating of 1000." in out
    assert "With only 1 game this is just a guide." in out
    assert ratings.CAUTIONS in out


def test_resigning_in_first_five_moves_is_saved_but_unrated(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "Nf3", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    assert "this game isn't rated" in said
    assert "You have no rating yet." in said
    assert "Your rating is" not in said
    assert "There are no games in your rating log yet." not in said
    assert "There are no games in your rating log yet." in capsys.readouterr().out
    assert "Game saved in your games folder." in said
    (row,) = read_log(tmp_path)
    assert row["Result"] == "unrated"
    assert "not rated" in row["Notes"]
    from different_engine import ratings
    assert ratings.read_games(config.RATING_LOG) == []
    from different_engine import milestones
    assert milestones.read_game_rows() == []


def test_player_moves_made_counts_only_the_players_moves():
    board = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6"]:
        board.push_san(san)
    assert game.player_moves_made(board, chess.WHITE) == 2
    assert game.player_moves_made(board, chess.BLACK) == 2
    board.push_san("Bb5")
    assert game.player_moves_made(board, chess.WHITE) == 3
    assert not game.is_early_resignation(board, chess.WHITE, "Checkmate")
    assert game.is_early_resignation(board, chess.WHITE, "Player resigned")


def test_show_board_at_review_question_skips_review_and_opens_board(setup, monkeypatch):
    speaker, script, tmp_path = setup
    opened = []
    monkeypatch.setattr(game, "show_last_board", lambda ui, engine_path=None: opened.append(ui.last_game))
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "resign", "yes", "show board", "no"])
    ui = game.Interface(speaker)
    game.play(ui, s, "/fake/stockfish")
    assert opened == []                              # nothing opens until the game is finished with
    assert game.between_games(ui, s) is False        # board opened, then "no" ends the session
    said = "\n".join(speaker.said)
    assert "Sorry, I didn't catch that" not in said
    assert "Did you break any of your honesty rules" not in said   # review skipped
    assert len(opened) == 1 and opened[0] is not None


def test_position_request_count_is_printed_not_spoken(setup, capsys):
    from different_engine.moves import describe_position

    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=1)
    script(["position", "position", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    # Welcome still names the limit; the position itself is still spoken.
    assert "You're White, level 2, one position request." in said
    assert describe_position(chess.Board()) in said
    # The count is on screen only.
    assert "That was position request 1 of 1." not in said
    assert "  That was position request 1 of 1." in out
    # Refusal is spoken, but without reciting the number; the full line is printed.
    assert "Sorry, you've used all your position requests for this game." in said
    assert "I'm sorry, you have used all 1 of your position requests" not in said
    assert "Try to rebuild the position in your mind" not in said
    assert ("  I'm sorry, you have used all 1 of your position requests for this game. "
            "Try to rebuild the position in your mind, then tell me your move.") in out
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 1


def test_show_moves_prints_score_sheet_and_uses_a_request(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["e4", "show moves", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "  1. e4 e5" in out
    assert "  That was position request 1 of 3." in out
    # Nothing about the moves, and no request count, is spoken.
    assert "1. e4 e5" not in said
    assert "Moves on screen" not in said
    assert "That was position request" not in said
    assert "No moves yet." not in out
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 1
    assert row["Position request moves"] == "2"


def test_show_moves_with_no_moves_does_not_use_a_request(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["show moves", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert "  No moves yet." in out
    assert "That was position request" not in out
    assert "No moves yet." not in said
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 0


def test_show_moves_respects_the_position_request_limit(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=1)
    script(["e4", "show moves", "show moves", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert out.count("  1. e4 e5") == 1
    assert "  That was position request 1 of 1." in out
    assert "That was position request 1 of 1." not in said
    assert "Sorry, you've used all your position requests for this game." in said
    assert "I'm sorry, you have used all 1 of your position requests" not in said
    assert "Try to rebuild the position in your mind" not in said
    assert ("  I'm sorry, you have used all 1 of your position requests for this game. "
            "Try to rebuild the position in your mind, then tell me your move.") in out
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 1


def test_show_moves_unlimited_position_requests(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=-1)
    script(["e4", "show moves", "show moves", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert out.count("  1. e4 e5") == 2
    assert "That was position request" not in out
    assert "That was position request" not in said
    assert "used all your position requests" not in said
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 2


def test_last_moves_is_unaffected_by_show_moves(setup, capsys):
    speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2, position_limit=3)
    script(["e4", "last moves", "show moves", "last move", "resign", "yes", ""])
    game.play(game.Interface(speaker), s, "/fake/stockfish")
    said = "\n".join(speaker.said)
    out = capsys.readouterr().out
    assert said.count("Your last move was pawn to e4, and I played pawn to e5.") == 2
    assert "  1. e4 e5" in out
    assert "  That was position request 1 of 3." in out
    (row,) = read_log(tmp_path)
    assert int(row["Position requests"]) == 1
