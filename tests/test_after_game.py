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


def test_whole_game_and_report(setup, monkeypatch):
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
        "usual",
        "knight e5", "", "e4",                       # move 1: one illegal attempt, one mishearing
        "position", "Nf3",                           # move 2: a position request
        "lost thread", "I've lost the thread", "Bb5",  # move 3: marked once, kept
        "Ba4", "castles kingside",
        "resign", "yes",                             # move 6 (after the checkpoint reminder)
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

    assert said.count(game.CHECKPOINT) == 1
    assert "I'll note that you lost the thread at move 3" in said
    assert "already noted that you first lost the thread at move 3" in said
    assert "During the game you told me you had lost the thread at move 3" in said
    assert "You placed 31 of 32 pieces on the correct square, which is 97 per cent." in said
    assert "At move 5 you played castles kingside. The engine preferred pawn to d4." in said
    assert "You tried one illegal move, at move 1." in said
    assert "You asked for the position once, at move 2." in said
    assert "Your blindfold performance rating is" in said
    # the final position isn't shown before the reconstruction test
    assert said.index("I've saved the game") < said.index("You placed 31 of 32")

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
    script(["yes",            # was the illegal attempt at move 2 when you lost the thread?
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
