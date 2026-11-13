"""Tests for the slip review and the after-game summary (Stockfish only if available)."""

import os
import shutil

import chess
import pytest

from different_engine import review


def m(n, loss, matched=False, san="Nf3"):
    return {"move_number": n, "san": san, "played": "Knight to f3", "best_san": "e4",
            "best": "Pawn to e4", "loss": loss, "matched": matched}


def test_biggest_slips_in_game_order_and_skip_tiny_ones():
    looked = [m(1, 0, True), m(2, 30), m(3, 400), m(4, 60), m(5, 900), m(6, 120), m(7, 10)]
    slips = review.biggest_slips(looked)
    assert [s["move_number"] for s in slips] == [3, 5, 6]
    assert [s["move_number"] for s in review.biggest_slips(looked, how_many=2)] == [3, 5]


def test_tiny_slips_only_when_nothing_bigger():
    looked = [m(1, 10), m(2, 40), m(3, 0, True), m(4, 20)]
    assert [s["move_number"] for s in review.biggest_slips(looked)] == [2, 4]
    assert review.biggest_slips([m(1, 0, True)]) == []


def test_move_quality():
    q = review.move_quality([m(1, 0, True), m(2, 100), m(3, 1000), m(4, 0, True)])
    assert q == {"moves": 4, "average_loss": 275, "matched": 2}
    assert review.move_quality([]) is None
    text = review.describe_quality(q)
    assert "275" in text and "2 of your 4 moves" in text and "accuracy" not in text.lower()


def test_describe_slip_is_plain_english():
    text = review.describe_slip(m(7, 450))
    assert text.startswith("At move 7 you played knight to f3. The engine preferred pawn to e4.")
    assert "piece or more" in text and "450" not in text
    assert "small slip" in review.describe_slip(m(7, 60))


@pytest.mark.parametrize("text,tag", [
    ("chess", "chess"), ("a chess mistake", "chess"), ("visualisation", "visualisation"),
    ("visualization", "visualisation"), ("I lost the board", "visualisation"), ("not sure", "not sure"),
    ("don't know", "not sure"), ("skip", "skipped"), ("no", "skipped"), ("banana", None),
])
def test_classify_tag(text, tag):
    assert review.classify_tag(text) == tag


def test_summary_lines():
    lines = review.summary_lines("7", [{"move": 5, "said": "knight e5", "reason": ""},
                                       {"move": 9, "said": "Bc4", "reason": ""},
                                       {"move": 9, "said": "bishop c4", "reason": ""}],
                                 [7, 12],
                                 {"correct": 24, "total": 28, "percent": 86, "extras": 1},
                                 {"moves": 20, "average_loss": 45, "matched": 9})
    text = " ".join(lines)
    assert "lost the thread at move 7" in text
    assert "three illegal moves, at moves 5 and 9" in text
    assert "position twice, at moves 7 and 12" in text
    assert "24 of 28 pieces correctly, 86 per cent, with one extra piece" in text
    assert "centipawn loss was 45" in text and "9 of your 20 moves" in text


def test_summary_lines_clean_game():
    text = " ".join(review.summary_lines("", [], []))
    assert "didn't lose the thread" in text and "didn't try any illegal" in text
    assert "didn't ask for the position" in text and "reconstruction" not in text


def find_stockfish():
    return os.environ.get("STOCKFISH") or shutil.which("stockfish") or (
        "/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None)


@pytest.mark.skipif(not find_stockfish(), reason="Stockfish not installed")
def test_analyse_game_finds_a_blunder():
    board = chess.Board()
    moves = [board.push_san(san) for san in ["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"]]
    # White played well; Black's 3...Nf6 allowed mate
    looked = review.analyse_game(find_stockfish(), chess.Board(), moves, chess.BLACK, seconds=0.1)
    assert [x["move_number"] for x in looked] == [1, 2, 3]
    assert looked[2]["san"] == "Nf6" and looked[2]["loss"] >= 500
    assert review.biggest_slips(looked)[-1]["san"] == "Nf6"


def test_analyse_game_without_stockfish_returns_none():
    assert review.analyse_game("/no/such/stockfish", chess.Board(), [], chess.WHITE) is None
