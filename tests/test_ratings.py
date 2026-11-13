"""Tests for the rating log and the Chapter 14 performance formula."""

from different_engine import ratings


def make(results_by_level):
    games = []
    for rating, results in results_by_level:
        games += [{"opponent": f"Level {rating}", "rating": rating, "result": r} for r in results]
    return games


def test_book_worked_example():
    # 24 games, eight each against 1100, 1200 and 1300: 11 wins, 4 draws, 9 losses -> 1233
    results = [1] * 11 + [0.5] * 4 + [0] * 9
    games = [{"opponent": "x", "rating": (1100, 1200, 1300)[i % 3], "result": r} for i, r in enumerate(results)]
    p = ratings.performance(games)
    assert p["average"] == 1200
    assert (p["wins"], p["draws"], p["losses"]) == (11, 4, 9)
    assert p["performance"] == 1233


def test_draws_pull_towards_average():
    p = ratings.performance(make([(1500, [0.5, 0.5, 0.5])]))
    assert p["performance"] == 1500


def test_rolling_window_of_thirty():
    old = make([(1000, [0] * 10)])
    new = make([(1400, [1, 0] * 15)])     # 30 recent games, 50 per cent
    games = old + new
    assert len(ratings.recent(games)) == 30
    assert ratings.performance(ratings.recent(games))["performance"] == 1400
    assert ratings.recent(games[:25]) == games[:25]


def test_report_guide_and_cautions():
    lines = ratings.report(make([(1200, [1, 0, 0.5])]), "Level 1200")
    text = " ".join(lines)
    assert "is 1200" in text and "just a guide" in text and "at least 20" in text
    assert "rough estimates" in text and "not a verdict" in text


def test_report_suggests_level_change():
    up = " ".join(ratings.report(make([(1200, [1, 1, 1, 1])]), "Level 1200"))
    assert "up a level" in up
    down = " ".join(ratings.report(make([(1200, [0, 0, 0, 0])]), "Level 1200"))
    assert "down a level" in down
    fine = " ".join(ratings.report(make([(1200, [1, 0, 0.5, 1])]), "Level 1200"))
    assert "a level" not in fine


def test_report_no_guide_after_twenty():
    text = " ".join(ratings.report(make([(1200, [1, 0] * 10)]), "Level 1200"))
    assert "just a guide" not in text


def test_csv_round_trip(tmp_path):
    path = tmp_path / "log.csv"
    ratings.append_game(path, {"Date": "2026-11-11", "Opponent": "Level 3", "Opponent rating": 1200, "Result": "1"})
    ratings.append_game(path, {"Date": "2026-11-12", "Opponent": "Level 3", "Opponent rating": 1200, "Result": "0.5"})
    games = ratings.read_games(path)
    assert [g["result"] for g in games] == [1.0, 0.5]
    assert path.read_text(encoding="utf-8-sig").splitlines()[0].startswith("Date,Opponent,Opponent rating")


def test_result_values():
    assert ratings.result_value("½") == 0.5
    assert ratings.result_value("1") == 1.0
    assert ratings.result_value("0") == 0.0
    assert ratings.result_value("abc") is None


OLD_HEADER = ("Date,Opponent,Opponent rating,Colour,Time control,Result,First lost thread,Rule breaks,"
              "Notes,Position requests,How it ended,Start position,PGN file")


def test_new_columns_round_trip(tmp_path):
    path = tmp_path / "log.csv"
    ratings.append_game(path, {"Date": "2026-11-12", "Opponent": "Level 3", "Opponent rating": 1200,
                               "Result": "0", "Illegal attempts": 2, "Illegal attempt moves": "5, 9",
                               "Position request moves": "7", "Reconstruction": "24/28",
                               "Reconstruction per cent": 86, "Slips": "7 Nf6 visualisation"})
    assert [g["result"] for g in ratings.read_games(path)] == [0.0]
    import csv
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["Reconstruction"] == "24/28" and rows[0]["Illegal attempt moves"] == "5, 9"
    assert list(rows[0]) == ratings.COLUMNS


def test_old_log_is_upgraded(tmp_path):
    path = tmp_path / "log.csv"
    old_rows = ["2026-11-01,Stockfish level 2,1000,White,untimed,1,,,\"A note, with a comma\",1,Checkmate,usual,games/a.pgn",
                "2026-11-02,Stockfish level 2,1000,Black,untimed,0.5,12,yes,,3,Draw agreed,usual,games/b.pgn"]
    path.write_text(OLD_HEADER + "\n" + "\n".join(old_rows) + "\n", encoding="utf-8-sig")
    ratings.append_game(path, {"Date": "2026-11-12", "Opponent": "Stockfish level 2", "Opponent rating": 1000,
                               "Result": "0", "Reconstruction": "10/12"})
    games = ratings.read_games(path)
    assert [g["result"] for g in games] == [1.0, 0.5, 0.0]
    import csv
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == ratings.COLUMNS
    assert rows[0]["Notes"] == "A note, with a comma" and rows[1]["First lost thread"] == "12"
    assert rows[0]["Reconstruction"] == "" and rows[2]["Reconstruction"] == "10/12"
    # a second game doesn't rewrite anything again
    before = path.read_text(encoding="utf-8-sig")
    ratings.append_game(path, {"Date": "2026-11-13", "Opponent": "x", "Opponent rating": 1000, "Result": "1"})
    assert path.read_text(encoding="utf-8-sig").startswith(before)
    assert len(ratings.read_games(path)) == 4


def test_hand_added_columns_are_kept(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text(OLD_HEADER + ",My column\n2026-11-01,x,1000,White,untimed,1,,,,0,Checkmate,usual,a.pgn,keep me\n",
                    encoding="utf-8-sig")
    ratings.append_game(path, {"Date": "2026-11-12", "Opponent": "x", "Opponent rating": 1000, "Result": "0"})
    import csv
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["My column"] == "keep me" and rows[1]["My column"] == ""
    assert len(ratings.read_games(path)) == 2
