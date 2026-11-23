"""Every milestone detector, announcements, progress output, and add-only recompute."""

import csv
import json

import chess
import chess.pgn
import pytest

from different_engine import drill, milestones, ratings, settings as config
from different_engine.game import format_status


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GAMES_DIR", str(tmp_path / "games"))
    monkeypatch.setattr(config, "RATING_LOG", str(tmp_path / "rating_log.csv"))
    monkeypatch.setattr(config, "DRILL_LOG", str(tmp_path / "drill_log.csv"))
    monkeypatch.setattr(config, "MILESTONES_FILE", str(tmp_path / "milestones.json"))
    (tmp_path / "games").mkdir()
    return tmp_path


def row(**kwargs):
    base = {
        "Date": "2026-11-01",
        "Opponent": "Stockfish level 2",
        "Opponent rating": "1000",
        "Colour": "White",
        "Result": "0",
        "First lost thread": "",
        "Position requests": "0",
        "How it ended": "Checkmate",
        "PGN file": "",
        "Illegal attempts": "0",
        "Illegal attempt moves": "",
        "Position request moves": "",
        "Reconstruction": "",
        "Reconstruction per cent": "",
    }
    base.update(kwargs)
    return base


def write_pgn(tmp_path, name, moves, headers=None):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    game = chess.pgn.Game.from_board(board)
    if headers:
        game.headers.update(headers)
    rel = f"games/{name}"
    path = tmp_path / "games" / name
    path.write_text(str(game) + "\n", encoding="utf-8")
    return rel, board


def test_milestone_count_is_twenty_five():
    assert milestones.TOTAL == 25
    assert len(milestones.MILESTONES) == 25
    assert len({m[0] for m in milestones.MILESTONES}) == 25
    groups = [m[1] for m in milestones.MILESTONES]
    assert groups.count("Foundations") == 3
    assert groups.count("First games") == 7
    assert milestones.MILESTONES[3][0] == "move_12"
    assert groups.count("Holding the board") == 7
    assert groups.count("Mastery") == 8


def test_perfect_drill_detectors(store):
    drills = [
        {"date": "2026-11-01", "score": 19, "total": 20, "seconds": 15},
        {"date": "2026-11-02", "score": 20, "total": 20, "seconds": 70},
    ]
    assert milestones.detect(rows=[], drills=drills) == {"perfect_drill"}
    drills.append({"date": "2026-11-03", "score": 20, "total": 20, "seconds": 59})
    assert milestones.detect(rows=[], drills=drills) >= {"perfect_drill", "perfect_drill_90"}
    assert "perfect_drill_60" not in milestones.detect(rows=[], drills=drills)
    drills.append({"date": "2026-11-04", "score": 20, "total": 20, "seconds": 39})
    earned = milestones.detect(rows=[], drills=drills)
    assert {"perfect_drill", "perfect_drill_90", "perfect_drill_60"} <= earned
    # A short perfect drill of fewer than 20 squares does not count
    assert "perfect_drill" not in milestones.detect(
        rows=[], drills=[{"date": "x", "score": 10, "total": 10, "seconds": 10}]
    )
    # Older 20-square and 30-square perfect rows both count
    assert milestones.detect(
        rows=[], drills=[{"date": "x", "score": 20, "total": 20, "seconds": 20}]
    ) == {"perfect_drill", "perfect_drill_90", "perfect_drill_60"}
    assert milestones.detect(
        rows=[], drills=[{"date": "x", "score": 30, "total": 30, "seconds": 35}]
    ) == {"perfect_drill", "perfect_drill_90", "perfect_drill_60"}
    # A 19/20 or 29/30 does not count even with a fast time
    assert milestones.detect(
        rows=[], drills=[
            {"date": "x", "score": 19, "total": 20, "seconds": 15},
            {"date": "y", "score": 29, "total": 30, "seconds": 20},
        ]
    ) == set()
    # Exactly 60 seconds is not "under 60"
    only_60 = milestones.detect(
        rows=[], drills=[{"date": "x", "score": 20, "total": 20, "seconds": 60}]
    )
    assert only_60 == {"perfect_drill"}
    # Exactly 40 seconds is not "under 40"
    only_40 = milestones.detect(
        rows=[], drills=[{"date": "x", "score": 20, "total": 20, "seconds": 40}]
    )
    assert only_40 == {"perfect_drill", "perfect_drill_90"}
    # A 30/30 at exactly 60 seconds is likewise only the untimed milestone
    assert milestones.detect(
        rows=[], drills=[{"date": "x", "score": 30, "total": 30, "seconds": 60}]
    ) == {"perfect_drill"}


def test_complete_game_and_not_resigned(store):
    resigned = row(Result="0", **{"How it ended": "Player resigned"})
    mate = row(Result="1", **{"How it ended": "Checkmate"})
    draw = row(Result="0.5", **{"How it ended": "Draw agreed"})
    unknown = row(Result="1", **{"How it ended": ""})
    earned = milestones.detect(rows=[resigned], drills=[])
    assert "complete_game" not in earned
    assert "complete_game" in milestones.detect(rows=[mate], drills=[])
    assert "complete_game" in milestones.detect(rows=[draw], drills=[])
    assert "complete_game" not in milestones.detect(rows=[unknown], drills=[])


def test_first_win_and_first_checkmate(store):
    loss_mate = row(Result="0", **{"How it ended": "Checkmate"})
    assert milestones.detect(rows=[loss_mate], drills=[]) & {"first_win", "first_checkmate"} == set()
    win_draw = row(Result="1", **{"How it ended": "Draw agreed"})
    assert milestones.detect(rows=[win_draw], drills=[]) & {"first_win", "first_checkmate"} == {"first_win"}
    win_mate = row(Result="1", **{"How it ended": "Checkmate"})
    assert {"first_win", "first_checkmate", "complete_game"} <= milestones.detect(rows=[win_mate], drills=[])


def test_no_illegal_and_zero_position_requests(store):
    blank = row(**{"Illegal attempts": "", "Position requests": ""})
    earned = milestones.detect(rows=[blank], drills=[])
    assert "no_illegal" not in earned
    assert "zero_position_requests" not in earned
    zero = row(**{"Illegal attempts": "0", "Position requests": "0"})
    earned = milestones.detect(rows=[zero], drills=[])
    assert {"no_illegal", "zero_position_requests"} <= earned
    some = row(**{"Illegal attempts": "2", "Position requests": "1"})
    earned = milestones.detect(rows=[some], drills=[])
    assert "no_illegal" not in earned
    assert "zero_position_requests" not in earned


def test_move_20_and_forty_move_from_pgn(store):
    short_moves = ["e4", "e5", "Nf3", "Nc6"]  # 2 full moves
    rel, _ = write_pgn(store, "short.pgn", short_moves)
    short = row(**{"PGN file": rel, "Position requests": "0"})
    earned = milestones.detect(rows=[short], drills=[])
    assert "move_12" not in earned
    assert "move_20_no_position" not in earned
    assert "forty_move_game" not in earned

    # 40 full moves: 80 half-moves of a repeating king walk is awkward;
    # build 40 White moves (79 half-moves) from a long game of pawn/knight shuffles.
    board = chess.Board()
    made = []
    # Play a legal developing sequence, then shuffle knights and king if needed
    opening = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7",
               "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3", "Nb8", "d4", "Nbd7"]
    for san in opening:
        board.push_san(san)
        made.append(san)
    # Continue with quiet moves until 40 full moves are reached
    while (len(board.move_stack) + 1) // 2 < 40:
        move = next(iter(board.legal_moves))
        made.append(board.san(move))
        board.push(move)
    rel40, _ = write_pgn(store, "long.pgn", made)
    assert milestones.move_count(row(**{"PGN file": rel40})) >= 40
    long_row = row(**{"PGN file": rel40, "Position requests": "0", "Position request moves": ""})
    earned = milestones.detect(rows=[long_row], drills=[])
    assert "move_12" in earned
    assert "forty_move_game" in earned
    assert "move_20_no_position" in earned

    # Reach move 20, but asked at move 12
    rel20, _ = write_pgn(store, "mid.pgn", made)  # still long, that's fine
    asked = row(**{"PGN file": rel20, "Position requests": "1", "Position request moves": "12"})
    earned = milestones.detect(rows=[asked], drills=[])
    assert "move_20_no_position" not in earned

    # Asked only at move 21: still reached 20 without asking
    late = row(**{"PGN file": rel20, "Position requests": "1", "Position request moves": "21"})
    earned = milestones.detect(rows=[late], drills=[])
    assert "move_20_no_position" in earned

    # Requests used but no move numbers: cannot tell
    unclear = row(**{"PGN file": rel20, "Position requests": "1", "Position request moves": ""})
    earned = milestones.detect(rows=[unclear], drills=[])
    assert "move_20_no_position" not in earned

    # No PGN: cannot detect move-count milestones
    no_pgn = row(**{"PGN file": "", "Position requests": "0"})
    earned = milestones.detect(rows=[no_pgn], drills=[])
    assert "move_12" not in earned
    assert "move_20_no_position" not in earned
    assert "forty_move_game" not in earned


def _full_moves(n_full):
    """A legal sequence that reaches n_full full moves (same count as move_count)."""
    board = chess.Board()
    made = []
    opening = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7",
               "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3", "Nb8", "d4", "Nbd7"]
    for san in opening:
        if (len(board.move_stack) + 1) // 2 >= n_full:
            break
        board.push_san(san)
        made.append(san)
    while (len(board.move_stack) + 1) // 2 < n_full:
        move = next(iter(board.legal_moves))
        made.append(board.san(move))
        board.push(move)
    return made


def test_move_12_from_pgn_and_existing_log(store):
    rel11, _ = write_pgn(store, "eleven.pgn", _full_moves(11))
    eleven = row(Result="0", **{"How it ended": "Player resigned", "PGN file": rel11})
    assert milestones.move_count(eleven) == 11
    earned = milestones.detect(rows=[eleven], drills=[])
    assert "move_12" not in earned
    assert "forty_move_game" not in earned

    # White's 12th move is enough: same full-move convention as the 40-move milestone
    made12 = _full_moves(12)
    rel12, _ = write_pgn(store, "twelve.pgn", made12)
    assert milestones.move_count(row(**{"PGN file": rel12})) == 12
    twelve = row(Result="0", **{"How it ended": "Player resigned", "PGN file": rel12})
    earned = milestones.detect(rows=[twelve], drills=[])
    assert "move_12" in earned
    assert "forty_move_game" not in earned

    # An unrated row still counts if passed in, same as forty_move_game
    unrated = row(Result="unrated", **{"How it ended": "Player resigned", "PGN file": rel12})
    assert "move_12" in milestones.detect(rows=[unrated], drills=[])

    # Recompute from existing rating-log rows (past games count)
    ratings.append_game(config.RATING_LOG, {
        "Date": "2026-11-01", "Opponent": "Stockfish level 2", "Opponent rating": 1000,
        "Result": "0", "How it ended": "Checkmate", "PGN file": rel12,
    })
    new, achieved = milestones.recompute(today=__import__("datetime").date(2026, 11, 22))
    assert "move_12" in new
    assert achieved["move_12"] == "2026-11-22"
    assert milestones.announcement_lines(new, achieved)[0] == "New milestone: reaching move 12."


def test_reconstruction_100(store):
    assert "reconstruction_100" not in milestones.detect(rows=[row()], drills=[])
    by_pct = row(**{"Reconstruction per cent": "100"})
    assert "reconstruction_100" in milestones.detect(rows=[by_pct], drills=[])
    by_frac = row(**{"Reconstruction": "28/28", "Reconstruction per cent": ""})
    assert "reconstruction_100" in milestones.detect(rows=[by_frac], drills=[])
    almost = row(**{"Reconstruction per cent": "99", "Reconstruction": "27/28"})
    assert "reconstruction_100" not in milestones.detect(rows=[almost], drills=[])


def test_five_no_lost_thread(store):
    clean = [row(Date=f"2026-11-0{i}", **{"First lost thread": ""}) for i in range(1, 5)]
    assert "five_no_lost_thread" not in milestones.detect(rows=clean, drills=[])
    five = clean + [row(Date="2026-11-05", **{"First lost thread": "never"})]
    assert "five_no_lost_thread" in milestones.detect(rows=five, drills=[])
    # A lost thread in the middle breaks the streak
    broken = (
        [row(Date="2026-11-01", **{"First lost thread": ""})] * 4
        + [row(Date="2026-11-05", **{"First lost thread": "12"})]
        + [row(Date="2026-11-06", **{"First lost thread": ""})] * 4
    )
    assert "five_no_lost_thread" not in milestones.detect(rows=broken, drills=[])
    # Lost thread marked only in the PGN (review skipped)
    rel, _ = write_pgn(store, "marked.pgn", ["e4", "e5"], headers={"LostThreadMarked": "1"})
    marked = [row(Date=f"2026-11-0{i}", **{"First lost thread": "", "PGN file": rel}) for i in range(1, 6)]
    assert "five_no_lost_thread" not in milestones.detect(rows=marked, drills=[])


def test_win_above_usual_level(store):
    # Most common level is 2 (three games); a win at level 3 counts
    games = [
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "0"}),
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "0"}),
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "1"}),
        row(Opponent="Stockfish level 3", **{"Opponent rating": "1200", "Result": "1"}),
    ]
    assert "win_above_usual" in milestones.detect(rows=games, drills=[])
    # Only playing and winning at the usual level does not count
    only_two = [
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "1"}),
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "1"}),
    ]
    assert "win_above_usual" not in milestones.detect(rows=only_two, drills=[])
    # A loss at the next level does not count
    loss = [
        row(Opponent="Stockfish level 2", **{"Opponent rating": "1000", "Result": "0"}),
        row(Opponent="Stockfish level 3", **{"Opponent rating": "1200", "Result": "0"}),
    ]
    assert "win_above_usual" not in milestones.detect(rows=loss, drills=[])


def test_five_completed_games(store):
    wins = [row(Result="1", **{"How it ended": "Checkmate"}) for _ in range(4)]
    assert "five_completed_games" not in milestones.detect(rows=wins, drills=[])
    wins.append(row(Result="0.5", **{"How it ended": "Stalemate"}))
    assert "five_completed_games" in milestones.detect(rows=wins, drills=[])
    # Resignations do not count towards the five
    mixed = [row(Result="0", **{"How it ended": "Player resigned"}) for _ in range(5)]
    mixed += [row(Result="1", **{"How it ended": "Checkmate"}) for _ in range(4)]
    assert "five_completed_games" not in milestones.detect(rows=mixed, drills=[])


def test_rating_thresholds_and_game_counts(store):
    # One win against 1000 -> performance 1400
    one = [row(Result="1", **{"Opponent rating": "1000", "Opponent": "Stockfish level 2"})]
    earned = milestones.detect(rows=one, drills=[])
    assert "rating_1200" in earned and "rating_1400" in earned
    assert "rating_1600" not in earned
    assert "ten_games" not in earned and "five_wins" not in earned

    ten_wins = [row(Result="1", **{"Opponent rating": "1400", "Opponent": "Stockfish level 4"})
                for _ in range(10)]
    earned = milestones.detect(rows=ten_wins, drills=[])
    assert {"ten_games", "five_wins", "ten_wins", "first_win"} <= earned
    assert "thirty_games" not in earned
    # 10 wins against 1400: performance = 1400 + 400 = 1800
    assert {"rating_1200", "rating_1400", "rating_1600", "rating_1800"} <= earned

    thirty = [row(Result="0.5", **{"Opponent rating": "1000"}) for _ in range(30)]
    earned = milestones.detect(rows=thirty, drills=[])
    assert "thirty_games" in earned and "ten_games" in earned
    assert "five_wins" not in earned
    # Performance of all draws against 1000 is 1000
    assert "rating_1200" not in earned


def test_hand_added_rows_count(store):
    # A row typed into the CSV, with no PGN, still counts for result-based milestones
    path = store / "rating_log.csv"
    ratings.append_game(path, {
        "Date": "2026-11-19", "Opponent": "Stockfish level 5", "Opponent rating": 1600,
        "Result": "1", "How it ended": "Checkmate", "Illegal attempts": 0,
        "Position requests": 0, "Reconstruction per cent": 100,
    })
    rows = milestones.read_game_rows(path)
    earned = milestones.detect(rows=rows, drills=[])
    assert {"first_win", "first_checkmate", "complete_game", "no_illegal",
            "zero_position_requests", "reconstruction_100"} <= earned


def test_progress_lines_and_bars():
    lines = milestones.progress_lines(achieved={})
    assert lines[0] == "Foundations [---] 0/3"
    assert lines[1] == "First games [-------] 0/7"
    assert lines[2] == "Holding the board [-------] 0/7"
    assert lines[3] == "Mastery [--------] 0/8"
    assert "You've earned 0 of 25 milestones." in lines
    assert lines[-1].startswith("Next up: Get a perfect drill.")
    # Next 2–3 are the first unearned ones
    assert "Get a perfect drill in under 60 seconds." in lines[-1]
    assert "Get a perfect drill in under 40 seconds." in lines[-1]

    some = {"perfect_drill": "2026-11-01", "perfect_drill_60": "2026-11-02",
            "perfect_drill_90": "2026-11-03", "complete_game": "2026-11-04",
            "first_win": "2026-11-05"}
    lines = milestones.progress_lines(achieved=some)
    assert lines[0] == "Foundations [###] 3/3"
    assert lines[1] == "First games [##-----] 2/7"
    assert "You've earned 5 of 25 milestones." in lines
    assert "Next up: Reach move 12 in a game." in lines[-1]

    all_ids = {m[0]: "2026-11-19" for m in milestones.MILESTONES}
    lines = milestones.progress_lines(achieved=all_ids)
    assert "You've earned 25 of 25 milestones." in lines
    assert "You've earned every milestone. Well done." in lines


def test_announcement_lines():
    achieved = {"first_checkmate": "2026-11-19", "first_win": "2026-11-19"}
    lines = milestones.announcement_lines(["first_checkmate", "first_win"], achieved)
    assert lines[0] == "New milestone: first checkmate."
    assert lines[1] == "New milestone: first win."
    assert lines[2] == "You've earned 2 of 25."
    assert milestones.announcement_lines([], achieved) == []


def test_recompute_only_adds_and_keeps_dates(store):
    drills = [{"date": "2026-11-01", "score": 30, "total": 30, "seconds": 25}]
    new, achieved = milestones.recompute(rows=[], drills=drills, today=__import__("datetime").date(2026, 11, 10))
    assert set(new) == {"perfect_drill", "perfect_drill_90", "perfect_drill_60"}
    assert achieved["perfect_drill"] == "2026-11-10"
    # A later recompute with no drills would, if it were allowed to remove, drop them.
    # It must keep them, with the original dates.
    new2, achieved2 = milestones.recompute(rows=[], drills=[], today=__import__("datetime").date(2026, 11, 19))
    assert new2 == []
    assert achieved2["perfect_drill"] == "2026-11-10"
    assert set(achieved2) >= {"perfect_drill", "perfect_drill_90", "perfect_drill_60"}
    saved = json.loads((store / "milestones.json").read_text())
    assert saved["achieved"]["perfect_drill"] == "2026-11-10"


def test_reset_rating_keeps_earned_milestones(store):
    ratings.append_game(config.RATING_LOG, {
        "Date": "2026-11-01", "Opponent": "Stockfish level 2", "Opponent rating": 1000,
        "Result": "1", "How it ended": "Checkmate",
    })
    new, achieved = milestones.recompute(today=__import__("datetime").date(2026, 11, 10))
    assert "first_win" in achieved and "first_checkmate" in achieved
    archive = ratings.archive_and_reset(config.RATING_LOG, today=__import__("datetime").date(2026, 11, 19))
    assert archive.endswith("rating_log_archived_2026-11-19.csv")
    assert not (store / "rating_log.csv").exists()
    assert (store / "rating_log_archived_2026-11-19.csv").exists()
    # Recompute from the now-empty log must not drop what was earned
    new2, achieved2 = milestones.recompute(today=__import__("datetime").date(2026, 11, 19))
    assert new2 == []
    assert "first_win" in achieved2 and "first_checkmate" in achieved2
    assert achieved2["first_win"] == "2026-11-10"
    # A second archive on the same day gets a suffix
    ratings.append_game(config.RATING_LOG, {
        "Date": "2026-11-19", "Opponent": "Stockfish level 2", "Opponent rating": 1000, "Result": "0",
    })
    archive2 = ratings.archive_and_reset(config.RATING_LOG, today=__import__("datetime").date(2026, 11, 19))
    assert archive2.endswith("rating_log_archived_2026-11-19_2.csv")
    # An empty or missing log is a no-op
    assert ratings.archive_and_reset(config.RATING_LOG) is None


def test_status_line_includes_milestones_not_eval(store):
    milestones.save({"first_win": "2026-11-19", "complete_game": "2026-11-19"})
    line = format_status(chess.Board(), chess.WHITE, 2, 3, 0, games=[])
    assert line.endswith("| Milestones 2/25")
    assert "Blindfold rating: no rating yet" in line
    assert "eval" not in line.lower()
    assert "fen" not in line.lower()
    earned, total = milestones.counts()
    assert (earned, total) == (2, 25)


class Speaker:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)


def test_update_and_announce(store):
    speaker = Speaker()

    class UI:
        def say(self, text):
            speaker.say(text)

    drills = [{"date": "2026-11-19", "score": 30, "total": 30, "seconds": 20}]
    new, achieved = milestones.update_and_announce(
        UI(), rows=[], drills=drills, today=__import__("datetime").date(2026, 11, 19)
    )
    said = "\n".join(speaker.said)
    assert "New milestone: a perfect drill." in said
    assert "New milestone: a perfect drill in under 60 seconds." in said
    assert "New milestone: a perfect drill in under 40 seconds." in said
    assert "You've earned 3 of 25." in said
    assert set(new) == {"perfect_drill", "perfect_drill_90", "perfect_drill_60"}
