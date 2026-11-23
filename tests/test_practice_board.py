"""The practice board: commands, the unrated log row, the milestone, and the drawing."""

import builtins
import csv
import io
import os

import chess
import chess.pgn
import pytest

from different_engine import game, milestones, practice_board as pb, ratings, settings as config
from different_engine.moves import parse, special_command, vocabulary
from different_engine.speech import grammar_phrases


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["practice board", "Practice board.", "practise board",
                                  "show practice board", "open the practice board",
                                  "practice board please"])
def test_practice_board_is_recognised(text):
    assert special_command(text) == "practice board"
    assert game.session_command(text) == "practice-board"
    r = parse(chess.Board(), text)
    assert r.kind == "command" and r.command == "practice board"


@pytest.mark.parametrize("text, expected", [
    ("show board", "show board"), ("board", "show board"), ("show moves", "show moves"),
    ("show me the moves", "show moves"), ("last moves", "last move"), ("practice", None),
])
def test_practice_board_does_not_clash_with_other_commands(text, expected):
    assert special_command(text) == expected


def test_position_is_still_the_position_request():
    r = parse(chess.Board(), "position")
    assert r.kind == "command" and r.command == "position"


def test_practice_board_words_are_in_the_grammar():
    phrases = grammar_phrases()
    assert "practice board" in phrases and "practise board" in phrases
    assert {"practice", "practise", "board"} <= set(vocabulary())


def test_help_lists_practice_board_in_both_sections():
    line = "  practice board                 Unrated game with a board showing whose pieces are where"
    text = game.format_help("before")
    assert text.count(line) == 2
    assert line in game.format_help("during")


# ---------------------------------------------------------------------------
# What is drawn (no window needed)
# ---------------------------------------------------------------------------

def test_occupied_squares_say_whose_but_not_which():
    board = chess.Board()
    squares = pb.occupied_squares(board)
    assert len(squares) == 32
    assert ("e1", "white") in squares and ("e8", "black") in squares
    assert all(len(item) == 2 for item in squares)      # no piece type anywhere
    board.push_san("e4")
    names = [name for name, _ in pb.occupied_squares(board)]
    assert "e4" in names and "e2" not in names


def _pieces_on(items, x0, y0):
    return [i for i in items if i[0] == "oval"
            and x0 <= i[1][0] + 10 and i[1][2] - 10 <= x0 + pb.SQUARE
            and y0 <= i[1][1] + 10 and i[1][3] - 10 <= y0 + pb.SQUARE]


def test_every_piece_type_looks_the_same():
    shapes = set()
    for piece_type in chess.PIECE_TYPES:
        board = chess.Board(None)
        board.set_piece_at(chess.D4, chess.Piece(piece_type, chess.WHITE))
        shapes.add(tuple(pb.drawing_items(board)))
    assert len(shapes) == 1


def test_white_and_black_pieces_differ_only_in_colour():
    white, black = chess.Board(None), chess.Board(None)
    white.set_piece_at(chess.D4, chess.Piece(chess.KNIGHT, chess.WHITE))
    black.set_piece_at(chess.D4, chess.Piece(chess.KNIGHT, chess.BLACK))
    w, b = pb.drawing_items(white), pb.drawing_items(black)
    assert [i[:2] for i in w] == [i[:2] for i in b]      # same shapes, same places
    assert w != b
    w_fills = {i[2] for i in w if i[0] == "oval"}
    assert pb.WHITE_PIECE[0] in w_fills and pb.BLACK_PIECE[0] not in w_fills
    assert pb.BLACK_PIECE[0] in {i[2] for i in b if i[0] == "oval"}


def test_squares_are_plain_light_and_dark_with_no_highlight():
    board = chess.Board()
    board.push_san("e4")
    rects = [i for i in pb.drawing_items(board) if i[0] == "rect"]
    assert len(rects) == 64
    assert {r[2] for r in rects} == {pb.LIGHT, pb.DARK}


def test_board_is_seen_from_the_players_side():
    x, y = pb.square_origin(chess.A1, white_at_bottom=True)
    assert x == pb.MARGIN and y == pb.MARGIN + 7 * pb.SQUARE           # a1 bottom left
    x, y = pb.square_origin(chess.A1, white_at_bottom=False)
    assert x == pb.MARGIN + 7 * pb.SQUARE and y == pb.MARGIN           # a1 top right
    texts = [i for i in pb.drawing_items(chess.Board(), white_at_bottom=False) if i[0] == "text"]
    bottom = sorted((t for t in texts if t[1][1] > pb.MARGIN + 8 * pb.SQUARE), key=lambda t: t[1][0])
    assert "".join(t[2] for t in bottom) == "hgfedcba"
    left = sorted((t for t in texts if t[1][0] < pb.MARGIN), key=lambda t: t[1][1])
    assert "".join(t[2] for t in left) == "12345678"


def test_coordinates_on_every_edge():
    texts = [i[2] for i in pb.drawing_items(chess.Board()) if i[0] == "text"]
    for label in "abcdefgh12345678":
        assert texts.count(label) == 2


def test_every_square_has_its_name_in_the_middle():
    board = chess.Board()
    labels = [i for i in pb.drawing_items(board) if i[0] == "label"]
    assert sorted(i[2] for i in labels) == sorted(chess.SQUARE_NAMES)
    by_name = {i[2]: i for i in labels}
    x, y = pb.square_origin(chess.E4)
    assert by_name["e4"][1] == (x + pb.SQUARE / 2, y + pb.SQUARE / 2)
    items = pb.drawing_items(board)
    last_piece = max(n for n, i in enumerate(items) if i[0] == "oval")
    first_label = min(n for n, i in enumerate(items) if i[0] == "label")
    assert first_label > last_piece                  # drawn on top of the spheres


def test_square_names_contrast_with_what_is_under_them():
    board = chess.Board()
    labels = {i[2]: i[3] for i in pb.drawing_items(board) if i[0] == "label"}
    assert labels["e1"] == pb.LABEL_ON_WHITE_PIECE   # dark text on ivory
    assert labels["e8"] == pb.LABEL_ON_BLACK_PIECE   # light text on charcoal
    light_empty, dark_empty = labels["e4"], labels["d4"]      # e4 is light, d4 dark
    assert pb.square_colour(chess.E4) == pb.LIGHT and pb.square_colour(chess.D4) == pb.DARK
    assert light_empty not in (pb.LIGHT, pb.DARK) and dark_empty not in (pb.LIGHT, pb.DARK)
    assert light_empty != dark_empty

    def brightness(colour):
        return sum(pb._rgb(colour))
    assert brightness(light_empty) < brightness(pb.LIGHT)    # a little darker than the square
    assert brightness(dark_empty) > brightness(pb.DARK)      # a little lighter than the square
    assert brightness(pb.LABEL_ON_WHITE_PIECE) < brightness(pb.WHITE_PIECE[0])
    assert brightness(pb.LABEL_ON_BLACK_PIECE) > brightness(pb.BLACK_PIECE[0])


def test_soft_edge_fades_into_the_square():
    items = pb.piece_items(0, 0, pb.LIGHT, white=False)
    first = items[0][2]                          # the widest, faintest ring
    assert first != pb.BLACK_PIECE[0]
    assert pb.blend(pb.LIGHT, "#000000", 0) == pb.LIGHT
    assert pb.blend("#000000", "#ffffff", 0.5) == "#808080"


# ---------------------------------------------------------------------------
# The controller (fake process)
# ---------------------------------------------------------------------------

class FakeProcess:
    def __init__(self, first="ready\n"):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(first)
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.alive = False

    def kill(self):
        self.alive = False


def test_controller_sends_positions_once_and_closes():
    procs = []

    def popen(args, **kwargs):
        assert args[1:3] == ["-m", "different_engine.practice_board"]
        assert "--black" in args
        procs.append(FakeProcess())
        return procs[-1]

    window = pb.PracticeBoard(white_at_bottom=False, popen=popen)
    board = chess.Board()
    assert window.open(board) and window.is_open
    window.update(board)                         # unchanged: not sent again
    board.push_san("e4")
    window.update(board)
    stdin = procs[0].stdin
    sent = stdin.getvalue().splitlines()
    assert sent == [f"board {chess.Board().board_fen()}", f"board {board.board_fen()}"]
    window.close()
    assert not window.is_open
    assert window.update(board) is False         # closed: nothing happens


def test_controller_reports_a_window_that_could_not_open():
    window = pb.PracticeBoard(popen=lambda args, **kw: FakeProcess(first=""))
    assert window.open(chess.Board()) is False
    assert not window.is_open

    def broken(args, **kw):
        raise OSError("no python")
    assert pb.PracticeBoard(popen=broken).open(chess.Board()) is False


@pytest.mark.skipif(not os.environ.get("DISPLAY") and os.name != "nt",
                    reason="needs a screen for tkinter")
def test_real_window_draws_and_closes():
    pytest.importorskip("tkinter")
    seen = {}

    def snapshot(root):
        canvas = [w for w in root.winfo_children()][0]
        seen["items"] = len(canvas.find_all())
        root.destroy()

    board = chess.Board()
    out = io.StringIO()
    read_end, write_end = os.pipe()               # stays open, like the game's pipe
    os.write(write_end, f"board {board.board_fen()}\n".encode())
    stdin = os.fdopen(read_end)
    pb.run_window(True, stdin=stdin, stdout=out, snapshot=snapshot)
    os.close(write_end)                           # the reader thread sees the end and stops
    assert out.getvalue() == "ready\n"
    assert seen["items"] > 64


# ---------------------------------------------------------------------------
# A practice game: unrated, noted, and earning its milestone
# ---------------------------------------------------------------------------

class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


class FakeEngine:
    replies = ["e5", "Nc6", "a6", "Nf6", "Be7", "b5"]

    def __init__(self, path, level):
        pass

    def choose_move(self, board):
        return board.parse_san(self.replies[len(board.move_stack) // 2])

    def accepts_draw(self, board, colour):
        return False

    def close(self):
        pass


class FakeWindow:
    made = []

    def __init__(self, white_at_bottom=True):
        self.white_at_bottom = white_at_bottom
        self.opens, self.positions, self.closed = 0, [], False
        self.open_now = False
        FakeWindow.made.append(self)

    @property
    def is_open(self):
        return self.open_now

    def open(self, board):
        self.opens += 1
        self.open_now = True
        self.update(board)
        return True

    def update(self, board):
        if self.open_now and (not self.positions or self.positions[-1] != board.board_fen()):
            self.positions.append(board.board_fen())

    def close(self):
        self.open_now = False
        self.closed = True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path / "games"))
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "DRILL_LOG", str(tmp_path / "drill_log.csv"))
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(game, "Engine", FakeEngine)
    FakeWindow.made = []
    speaker = Speaker()
    ui = game.Interface(speaker)
    ui.practice_window_factory = FakeWindow

    def script(answers):
        answers = iter(answers)
        monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    return ui, speaker, script, tmp_path


def read_log(tmp_path):
    with open(tmp_path / "rating_log.csv", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_pgn(tmp_path):
    (path,) = list((tmp_path / "games").glob("*.pgn"))
    with open(path, encoding="utf-8") as f:
        return chess.pgn.read_game(f)


SIX_MOVES = ["Nf3", "Bb5", "Ba4", "O-O"]     # with e4 first: five moves, then resign


def test_practice_board_before_the_first_move(setup):
    ui, speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["practice board", "e4"] + SIX_MOVES + ["resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    assert speaker.said.count(game.PRACTICE_ON) == 1
    assert "You resigned within the first five moves, so this game isn't rated." not in speaker.said
    (window,) = FakeWindow.made
    assert window.white_at_bottom and window.closed
    assert window.positions[0] == chess.Board().board_fen()
    assert len(window.positions) == 1 + 10        # every move, both sides
    (row,) = read_log(tmp_path)
    assert row["Result"] == "unrated"
    assert row["Notes"] == "Practice board game (scored 0), not rated"
    assert ratings.read_games(config.RATING_LOG) == []           # rating unaffected
    assert milestones.read_game_rows() == []
    assert "practice_board" in milestones.load()
    assert any("New milestone: a practice board game." == t for t in speaker.said)
    pgn = read_pgn(tmp_path)
    assert pgn.headers["PracticeBoard"] == "yes"
    assert len(list(pgn.mainline_moves())) == 10


def test_practice_board_mid_game_makes_it_unrated(setup):
    ui, speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "Nf3", "practice board", "Bb5", "Ba4", "O-O", "resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    assert speaker.said.count(game.PRACTICE_ON) == 1
    (window,) = FakeWindow.made
    assert window.positions[0].startswith("r1bqkbnr/pppp1ppp/2n5")   # the position at that moment
    (row,) = read_log(tmp_path)
    assert row["Result"] == "unrated" and row["Notes"].startswith("Practice board game")


def test_practice_board_or_show_board_when_already_open(setup, capsys):
    ui, speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["practice board", "e4", "practice board", "show board", "resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    (window,) = FakeWindow.made
    assert capsys.readouterr().out.count("The practice board is already open.") == 2
    assert speaker.said.count(game.PRACTICE_ON) == 1
    assert "The board is available between games. Your move." not in speaker.said
    assert window.opens == 1


def test_show_board_reopens_a_closed_practice_board(setup):
    ui, speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)

    class ClosingWindow(FakeWindow):
        def update(self, board):
            super().update(board)
            if board.move_stack:            # the player closes it after the first move
                self.open_now = False
    ui.practice_window_factory = ClosingWindow
    script(["practice board", "e4", "show board", "resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    (window,) = FakeWindow.made
    assert window.opens == 2
    assert speaker.said.count(game.PRACTICE_ON) == 1


def test_practice_board_between_games_starts_a_practice_game(setup):
    ui, speaker, script, tmp_path = setup
    script(["practice board"])
    assert game.between_games(ui, dict(config.DEFAULTS)) is True
    assert ui.practice_next is True
    s = dict(config.DEFAULTS, colour="white", level=2)
    script(["e4", "resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    assert ui.practice_next is False
    assert speaker.said.count(game.PRACTICE_ON) == 1
    (row,) = read_log(tmp_path)
    assert row["Notes"].startswith("Practice board game")


def test_an_ordinary_game_after_a_practice_game_is_rated(setup):
    ui, speaker, script, tmp_path = setup
    s = dict(config.DEFAULTS, colour="white", level=2)
    ui.practice_next = True
    script(["e4", "resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    script(["e4"] + SIX_MOVES + ["resign", "yes", ""])
    game.play(ui, s, "/fake/stockfish")
    rows = read_log(tmp_path)
    assert [r["Result"] for r in rows] == ["unrated", "0"]
    assert len(ratings.read_games(config.RATING_LOG)) == 1


def test_review_note_is_kept_after_the_practice_note(setup, monkeypatch):
    ui, speaker, script, tmp_path = setup
    row = {"Notes": "Practice board game (scored 1), not rated", "PGN file": "x.pgn"}
    monkeypatch.setattr(game, "lost_thread_question", lambda *a: "")
    monkeypatch.setattr(game, "reconstruction_test", lambda *a: None)
    monkeypatch.setattr(game, "slip_review", lambda *a: None)
    monkeypatch.setattr(game, "save_pgn", lambda *a: "")
    monkeypatch.setattr(ratings, "update_game", lambda *a: True)
    script(["no", "fun game", "no"])
    game._run_review(ui, chess.Board(), chess.WHITE, None, str(tmp_path / "x.pgn"), {}, row,
                     {}, [], [], "")
    assert row["Notes"] == "Practice board game (scored 1), not rated; fun game"


# ---------------------------------------------------------------------------
# The milestone
# ---------------------------------------------------------------------------

def test_practice_board_milestone_definition():
    assert milestones.group_of("practice_board") == "First games"
    assert milestones.title_of("practice_board") == "a practice board game"
    assert milestones.description_of("practice_board") == "Play a game with the practice board"


def _practice_row(**kw):
    base = {"Date": "2026-11-22", "Opponent": "Stockfish level 2", "Opponent rating": "1000",
            "Result": "unrated", "How it ended": "Checkmate", "Notes":
            "Practice board game (scored 1), not rated", "Position requests": "0",
            "Illegal attempts": "0", "PGN file": ""}
    base.update(kw)
    return base


def test_milestone_from_an_unrated_practice_row_only():
    earned = milestones.detect(rows=[_practice_row()], drills=[])
    assert earned == {"practice_board"}                # nothing else from a practice game
    early = _practice_row(Notes="Resigned in the first 5 moves (scored 0), not rated")
    assert "practice_board" not in milestones.detect(rows=[early], drills=[])


def test_milestone_read_from_the_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    ratings.append_game(config.RATING_LOG, _practice_row())
    assert milestones.read_game_rows() == []
    assert len(milestones.read_practice_rows()) == 1
    assert "practice_board" in milestones.detect(drills=[])
    assert ratings.read_games(config.RATING_LOG) == []


def test_five_practice_board_games_milestone_definition():
    assert milestones.group_of("practice_board_5") == "Holding the board"
    assert milestones.title_of("practice_board_5") == "five practice board games"
    assert milestones.description_of("practice_board_5") == "Play 5 games with the practice board"
    ids = [m[0] for m in milestones.MILESTONES]
    assert ids.index("practice_board_5") == ids.index("five_completed_games") + 1


def test_five_practice_board_games_needs_five_not_four():
    four = milestones.detect(rows=[_practice_row() for _ in range(4)], drills=[])
    assert four == {"practice_board"}
    five = milestones.detect(rows=[_practice_row() for _ in range(5)], drills=[])
    assert five == {"practice_board", "practice_board_5"}
    other_unrated = [_practice_row(Notes="Resigned in the first 5 moves (scored 0), not rated")] * 3
    assert "practice_board_5" not in milestones.detect(
        rows=[_practice_row() for _ in range(4)] + other_unrated, drills=[])


def test_five_practice_board_games_from_the_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    for n in range(5):
        ratings.append_game(config.RATING_LOG, _practice_row())
        earned = milestones.detect(drills=[])
        assert ("practice_board_5" in earned) == (n == 4)
    assert ratings.read_games(config.RATING_LOG) == []           # still unrated
