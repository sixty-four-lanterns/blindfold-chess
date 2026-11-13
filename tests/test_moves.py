"""Tests for the move parser.  Run with:  python -m pytest"""

import chess
import pytest

from different_engine.moves import (parse, normalise, describe_move, describe_position,
                                    for_speech, describe_game, parse_number, is_illegal_attempt,
                                    join_words, number_word)


def san(board, text):
    result = parse(board, text)
    assert result.kind == "move", f"{text!r}: {result.message}"
    return board.san(result.move)


START = chess.Board()


@pytest.mark.parametrize("text,expected", [
    ("knight f3", "Nf3"),
    ("Knight F3", "Nf3"),
    ("knight to f3", "Nf3"),
    ("knight from g1 to f3", "Nf3"),
    ("knight g1 f3", "Nf3"),
    ("knight foxtrot three", "Nf3"),
    ("night eff three", "Nf3"),
    ("pawn e4", "e4"),
    ("e4", "e4"),
    ("echo four", "e4"),
    ("pawn to echo four", "e4"),
    ("e two e four", "e4"),
    ("from e2 to e4", "e4"),
    ("Nf3", "Nf3"),
    ("g1f3", "Nf3"),
    ("knight to charlie three", "Nc3"),
    ("pawn to alpha three", "a3"),
    ("pawn to a for", "a4"),
    ("pawn hotel three", "h3"),
])
def test_opening_moves(text, expected):
    assert san(START, text) == expected


def test_pawn_capture():
    b = chess.Board()
    for m in ["e4", "d5"]:
        b.push_san(m)
    assert san(b, "pawn takes d5") == "exd5"
    assert san(b, "e takes d5") == "exd5"
    assert san(b, "pawn captures delta five") == "exd5"
    assert san(b, "exd5") == "exd5"


def test_capture_word_requires_capture():
    assert parse(START, "knight takes f3").kind == "problem"


def test_ambiguous_knights_ask_again():
    # Knights on b1 and f3 can both reach d2
    b = chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPP1PPPP/RN1QKB1R w KQkq - 0 1")
    r = parse(b, "knight d2")
    assert r.kind == "problem" and "more than one knight" in r.message.lower()
    assert san(b, "knight from b1 to d2") == "Nbd2"
    assert san(b, "knight b d2") == "Nbd2"
    assert san(b, "knight foxtrot d2") == "Nfd2"
    assert parse(b, "Nd2").kind == "problem"


def test_ambiguous_pawn_capture():
    b = chess.Board("4k3/8/8/3p4/2P1P3/8/8/4K3 w - - 0 1")
    assert parse(b, "pawn takes d5").kind == "problem"
    assert san(b, "c takes d5") == "cxd5"
    assert san(b, "echo pawn takes delta five") == "exd5"
    assert san(b, "pawn from e4 takes d5") == "exd5"


def test_illegal_moves_are_refused():
    r = parse(START, "knight e5")
    assert r.kind == "problem" and "no knight" in r.message.lower()
    assert parse(START, "e5").kind == "problem"
    assert parse(START, "bishop c4").kind == "problem"


def test_unnamed_piece_means_pawn_never_guesses():
    b = chess.Board()
    b.push_san("e4"); b.push_san("e5")
    r = parse(b, "f3")          # pawn f3 is legal
    assert r.kind == "move" and b.san(r.move) == "f3"
    r = parse(b, "b5")          # bishop could go to b5, but no pawn can: ask, don't guess
    assert r.kind == "problem" and "name it" in r.message


@pytest.mark.parametrize("text,expected", [
    ("castles kingside", "O-O"), ("castle king side", "O-O"), ("castles short", "O-O"),
    ("kingside castles", "O-O"), ("O-O", "O-O"),
    ("castles queenside", "O-O-O"), ("castles queen side", "O-O-O"), ("castles long", "O-O-O"),
    ("queen side castle", "O-O-O"), ("O-O-O", "O-O-O"),
])
def test_castling(text, expected):
    b = chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
    assert san(b, text) == expected


def test_castling_not_allowed():
    r = parse(START, "castles kingside")
    assert r.kind == "problem" and "can't castle" in r.message


def test_castles_without_side_only_if_unique():
    b = chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
    assert parse(b, "castles").kind == "problem"
    b = chess.Board("4k3/8/8/8/8/8/8/4K2R w K - 0 1")
    assert san(b, "castles") == "O-O"


@pytest.mark.parametrize("text,expected", [
    ("pawn to e8 queen", "e8=Q"), ("e8 queen", "e8=Q"), ("pawn e8 promotes to a knight", "e8=N"),
    ("e8 equals rook", "e8=R"), ("pawn to echo eight, bishop", "e8=B"), ("e8=Q", "e8=Q"),
    ("pawn takes d8 queen", "exd8=Q"),
])
def test_promotion(text, expected):
    b = chess.Board("3r4/4P2k/8/8/8/8/8/4K3 w - - 0 1")
    assert san(b, text) == expected


def test_promotion_needs_piece():
    b = chess.Board("3r4/4P2k/8/8/8/8/8/4K3 w - - 0 1")
    r = parse(b, "pawn e8")
    assert r.kind == "problem" and "promote" in r.message


def test_en_passant():
    b = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert san(b, "pawn takes d6") == "exd6"
    assert san(b, "pawn takes d6 en passant") == "exd6"


@pytest.mark.parametrize("text,command", [
    ("repeat", "repeat"), ("say again", "repeat"), ("position", "position"), ("position please", "position"),
    ("resign", "resign"), ("draw", "draw"), ("offer a draw", "draw"), ("help", "help"), ("rating", "rating"),
    ("lost thread", "lost thread"), ("lost the thread", "lost thread"), ("I've lost the thread", "lost thread"),
    ("I have lost the thread", "lost thread"), ("Lost the thread!", "lost thread"),
])
def test_commands(text, command):
    r = parse(START, text)
    assert r.kind == "command" and r.command == command


def test_nothing_heard():
    assert parse(START, "").kind == "problem"
    assert parse(START, "banana").kind == "problem"
    assert "square" in parse(START, "knight").message


def test_a_file_is_not_dropped():
    b = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    assert san(b, "rook a8") == "Ra8+"
    assert san(b, "rook to a8") == "Ra8+"


def test_normalise():
    assert normalise("Knight from golf one to foxtrot three") == ["knight", "from", "g1", "f3"]
    assert normalise("bishop takes delta three") == ["bishop", "x", "d3"]


def test_describe_move():
    b = chess.Board()
    assert describe_move(b, chess.Move.from_uci("g1f3")) == "Knight to f3"
    assert describe_move(b, chess.Move.from_uci("e2e4")) == "Pawn to e4"
    b = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 2 4")
    assert describe_move(b, chess.Move.from_uci("h5f7")) == "Queen takes f7, checkmate"
    b = chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
    assert describe_move(b, chess.Move.from_uci("e1g1")) == "Castles kingside"
    assert describe_move(b, chess.Move.from_uci("e1c1")) == "Castles queenside"
    b = chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPP1PPPP/RN1QKB1R w KQkq - 0 1")
    assert describe_move(b, chess.Move.from_uci("b1d2")) == "Knight from b1 to d2"
    b = chess.Board("4k3/8/8/3p4/2P1P3/8/8/4K3 w - - 0 1")
    assert describe_move(b, chess.Move.from_uci("e4d5")) == "E-pawn takes d5"
    b = chess.Board("3r4/4P2k/8/8/8/8/8/4K3 w - - 0 1")
    assert describe_move(b, chess.Move.from_uci("e7d8q")) == "Pawn takes d8, promotes to a queen"


def test_describe_position_order():
    text = describe_position(chess.Board())
    assert text.startswith("White: King e1. Queen d1. Rooks a1 and h1. Bishops c1 and f1. "
                           "Knights b1 and g1. Pawns a2, b2, c2, d2, e2, f2, g2 and h2. Black: King e8.")
    assert text.endswith("White to move.")


def test_for_speech():
    assert for_speech("Knight to f3") == "Knight to eff 3"
    assert for_speech("E-pawn takes d5") == "ee pawn takes dee 5"
    assert for_speech("Rook to a1") == "Rook to ay 1"


def test_describe_game():
    b = chess.Board()
    moves = [chess.Move.from_uci(u) for u in ["e2e4", "e7e5", "g1f3"]]
    assert describe_game(b, moves) == ["Move 1. White: Pawn to e4. Black: Pawn to e5.",
                                       "Move 2. White: Knight to f3."]


def test_parse_number():
    assert parse_number("12") == 12
    assert parse_number("twenty three") == 23
    assert parse_number("move thirty") == 30
    assert parse_number("never") is None


def test_position_validation():
    from different_engine.board_editor import position_problems, tidy
    assert position_problems(chess.Board()) == []
    assert "White needs a king." in position_problems(chess.Board("4k3/8/8/8/8/8/8/8 w - - 0 1"))
    assert any("first or eighth" in p for p in position_problems(chess.Board("4k2P/8/8/8/8/8/8/4K3 w - - 0 1")))
    # Black to move would mean White (who just moved) is in check
    assert any("just moved" in p for p in position_problems(chess.Board("4k3/8/8/8/8/8/8/r3K3 b - - 0 1")))
    assert position_problems(chess.Board("4k3/8/8/8/8/8/8/r3K3 w - - 0 1")) == []
    assert any("already be over" in p for p in position_problems(chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")))
    b = chess.Board("4k3/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert tidy(b).castling_xfen() == "KQ"


def test_speech_grammar_uses_known_words():
    from different_engine.speech import grammar_phrases
    phrases = grammar_phrases()        # raises if a phrase uses a word outside the vocabulary
    assert "knight f three" in phrases and "castles king side" in phrases and phrases[-1] == "[unk]"
    # every phrase the recogniser can produce should parse without crashing
    for phrase in phrases[:-1]:
        parse(START, phrase)


def test_lost_thread_is_not_a_move():
    b = chess.Board()
    b.push_san("e4")
    r = parse(b, "lost the thread")
    assert r.kind == "command" and r.move is None and not is_illegal_attempt(r)


@pytest.mark.parametrize("text", [
    "knight e5", "bishop c4", "e5", "pawn e5", "knight takes f3", "castles kingside", "castles queenside",
    "Nf6", "Bc4", "from e2 to e5",
])
def test_clearly_named_illegal_moves_are_illegal_attempts(text):
    r = parse(START, text)
    assert r.kind == "problem" and is_illegal_attempt(r), text


@pytest.mark.parametrize("board,text", [
    (START, ""), (START, "   "), (START, "banana"), (START, "knight"),            # nothing usable heard
    (chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPP1PPPP/RN1QKB1R w KQkq - 0 1"), "knight d2"),  # ambiguous
    (chess.Board("rnbqkbnr/pppppppp/8/8/8/5N2/PPP1PPPP/RN1QKB1R w KQkq - 0 1"), "Nd2"),        # ambiguous
    (chess.Board("3r4/4P2k/8/8/8/8/8/4K3 w - - 0 1"), "pawn e8"),               # promotion piece missing
    (chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1"), "castles"),            # which side?
])
def test_mishearings_and_ambiguities_are_not_illegal_attempts(board, text):
    r = parse(board, text)
    assert r.kind == "problem" and not is_illegal_attempt(r), text


def test_legal_moves_and_commands_are_not_illegal_attempts():
    assert not is_illegal_attempt(parse(START, "knight f3"))
    assert not is_illegal_attempt(parse(START, "position"))


def test_word_helpers():
    assert join_words([5]) == "5" and join_words([5, 9]) == "5 and 9" and join_words([5, 9, 12]) == "5, 9 and 12"
    assert number_word(2) == "two" and number_word(28) == "28"
