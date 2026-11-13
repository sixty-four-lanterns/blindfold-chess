"""Tests for the reconstruction test's scoring (no window needed)."""

import chess

from different_engine.reconstruction import (score_reconstruction, describe_reconstruction,
                                             short_score, marks_for)

P = chess.Piece
WK, WQ, WR, WP = P(chess.KING, True), P(chess.QUEEN, True), P(chess.ROOK, True), P(chess.PAWN, True)
BK, BQ, BP = P(chess.KING, False), P(chess.QUEEN, False), P(chess.PAWN, False)


def test_perfect_from_the_start_position():
    s = score_reconstruction(chess.Board(), chess.Board())
    assert (s["correct"], s["total"], s["missing"], s["wrong"], s["extras"]) == (32, 32, 0, 0, 0)
    assert s["percent"] == 100 and s["perfect"]
    assert "perfect" in describe_reconstruction(s).lower()


def test_missing_pieces():
    truth = {chess.E1: WK, chess.E8: BK, chess.D1: WQ, chess.A2: WP}
    s = score_reconstruction(truth, {chess.E1: WK, chess.E8: BK})
    assert (s["correct"], s["missing"], s["wrong"], s["extras"]) == (2, 2, 0, 0)
    assert s["percent"] == 50 and not s["perfect"]
    assert s["missing_squares"] == sorted([chess.D1, chess.A2])


def test_wrong_piece_on_a_square():
    truth = {chess.E1: WK, chess.E8: BK, chess.D1: WQ}
    s = score_reconstruction(truth, {chess.E1: WK, chess.E8: BK, chess.D1: WR})
    assert (s["correct"], s["missing"], s["wrong"], s["extras"]) == (2, 0, 1, 0)
    # the right piece but the wrong colour is wrong too
    s = score_reconstruction(truth, {chess.E1: WK, chess.E8: BK, chess.D1: BQ})
    assert s["wrong"] == 1 and s["correct"] == 2


def test_extra_pieces_spoil_perfection_but_not_the_percentage():
    truth = {chess.E1: WK, chess.E8: BK}
    s = score_reconstruction(truth, {chess.E1: WK, chess.E8: BK, chess.H7: BP})
    assert s["correct"] == 2 and s["extras"] == 1 and s["percent"] == 100
    assert not s["perfect"]
    assert "one extra piece" in describe_reconstruction(s)


def test_a_piece_one_square_out_is_missing_plus_extra():
    truth = {chess.E1: WK, chess.E8: BK, chess.D1: WQ}
    s = score_reconstruction(truth, {chess.E1: WK, chess.E8: BK, chess.D2: WQ})
    assert (s["correct"], s["missing"], s["extras"]) == (2, 1, 1)


def test_empty_boards():
    empty = chess.Board(None)
    s = score_reconstruction(empty, empty)
    assert s["percent"] == 100 and s["perfect"] and s["total"] == 0
    s = score_reconstruction(empty, {chess.E1: WK})
    assert s["percent"] == 0 and not s["perfect"]
    # nothing placed at all on a real position
    s = score_reconstruction(chess.Board(), empty)
    assert s["correct"] == 0 and s["missing"] == 32 and s["percent"] == 0


def test_mixed_example_and_wording():
    # 28 pieces: start position without the a- and h-pawns
    truth = chess.Board()
    for sq in (chess.A2, chess.H2, chess.A7, chess.H7):
        truth.remove_piece_at(sq)
    guess = truth.copy()
    guess.set_piece_at(chess.D1, BQ)          # wrong colour queen
    guess.set_piece_at(chess.C1, WR)          # wrong piece
    guess.remove_piece_at(chess.B8)           # missing
    guess.remove_piece_at(chess.G8)           # missing
    guess.set_piece_at(chess.E4, WP)          # extra
    s = score_reconstruction(truth, guess)
    assert (s["correct"], s["total"], s["wrong"], s["missing"], s["extras"]) == (24, 28, 2, 2, 1)
    assert s["percent"] == 86                # 85.7 rounds up
    assert short_score(s) == "24/28, 86%"
    text = describe_reconstruction(s)
    assert text.startswith("You placed 24 of 28 pieces on the correct square, which is 86 per cent.")
    assert "On two squares you put the wrong piece, two pieces were missing and you placed one extra piece." in text


def test_rounding_is_not_bankers_rounding():
    truth = {sq: WP for sq in (chess.A3, chess.B3, chess.C3, chess.D3, chess.E3, chess.F3, chess.G3, chess.H3)}
    s = score_reconstruction(truth, {chess.A3: WP})
    assert s["percent"] == 13                # 12.5 -> 13


def test_marks_cover_every_compared_square():
    truth = {chess.E1: WK, chess.E8: BK, chess.D1: WQ}
    s = score_reconstruction(truth, {chess.E1: WK, chess.D1: WR, chess.H5: BQ})
    marks = marks_for(s)
    assert set(marks) == {chess.E1, chess.E8, chess.D1, chess.H5}
