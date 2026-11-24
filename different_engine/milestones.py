"""Milestones and a short progress bar, worked out from the game and drill logs.

Achievements are stored in milestones.json with the date they were first
noticed.  Recomputing from the logs only ever adds milestones: ones you have
already earned stay earned, even if the rating log is later reset.
"""

import csv
import datetime
import json
import os
import re
from collections import Counter

import chess
import chess.pgn

from . import ratings, settings as config
from .engine import LEVELS

# id, group, short title (for "New milestone: ..."), longer description (for "Next up")
MILESTONES = [
    # perfect_drill_90 and perfect_drill_60 keep their historical ids so
    # already-earned entries in milestones.json are not lost. The thresholds
    # and display text are now 60 and 40 seconds, scaled from 90 and 60
    # when the drill was shortened from 30 squares to 20.
    ("perfect_drill", "Foundations",
     "a perfect drill",
     "Get a perfect drill"),
    ("perfect_drill_90", "Foundations",
     "a perfect drill in under 60 seconds",
     "Get a perfect drill in under 60 seconds"),
    ("perfect_drill_60", "Foundations",
     "a perfect drill in under 40 seconds",
     "Get a perfect drill in under 40 seconds"),
    ("move_12", "First games",
     "reaching move 12",
     "Reach move 12 in a game"),
    ("complete_game", "First games",
     "a completed game",
     "Finish a game without resigning"),
    ("move_20_no_position", "First games",
     "move 20 with no position request",
     "Reach move 20 without asking for the position"),
    ("no_illegal", "First games",
     "a game with no illegal moves",
     "Play a game with no illegal move attempts"),
    ("first_checkmate", "First games",
     "first checkmate",
     "Deliver a checkmate"),
    ("first_win", "First games",
     "first win",
     "Win a game"),
    ("practice_board", "First games",
     "a practice board game",
     "Play a game with the practice board"),
    ("reconstruction_100", "Holding the board",
     "a perfect reconstruction",
     "Score 100 per cent on the reconstruction test"),
    ("five_no_lost_thread", "Holding the board",
     "five games in a row with no lost thread",
     "Finish five games in a row without losing the thread"),
    ("win_above_usual", "Holding the board",
     "a win one level up",
     "Win a game one level above your most common level"),
    ("forty_move_game", "Holding the board",
     "a 40-move game",
     "Play a game that lasts 40 moves"),
    ("zero_position_requests", "Holding the board",
     "a game with no position requests",
     "Finish a game without asking for the position"),
    ("five_completed_games", "Holding the board",
     "five completed games",
     "Finish five games without resigning"),
    ("practice_board_5", "Holding the board",
     "five practice board games",
     "Play 5 games with the practice board"),
    ("rating_1200", "Mastery",
     "a rating of 1200",
     "Reach a blindfold rating of 1200"),
    ("rating_1400", "Mastery",
     "a rating of 1400",
     "Reach a blindfold rating of 1400"),
    ("rating_1600", "Mastery",
     "a rating of 1600",
     "Reach a blindfold rating of 1600"),
    ("rating_1800", "Mastery",
     "a rating of 1800",
     "Reach a blindfold rating of 1800"),
    ("ten_games", "Mastery",
     "ten rated games",
     "Play 10 rated games"),
    ("thirty_games", "Mastery",
     "thirty rated games",
     "Play 30 rated games"),
    ("five_wins", "Mastery",
     "five wins",
     "Win 5 games"),
    ("ten_wins", "Mastery",
     "ten wins",
     "Win 10 games"),
]

GROUPS = ("Foundations", "First games", "Holding the board", "Mastery")
TOTAL = len(MILESTONES)
BY_ID = {m[0]: m for m in MILESTONES}


def title_of(milestone_id):
    return BY_ID[milestone_id][2]


def description_of(milestone_id):
    return BY_ID[milestone_id][3]


def group_of(milestone_id):
    return BY_ID[milestone_id][1]


# ---------------------------------------------------------------------------
# Reading the logs
# ---------------------------------------------------------------------------

def read_game_rows(path=None):
    """Every row of the rating log, including hand-added ones."""
    path = path or config.RATING_LOG
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if (r.get("Result") or "").strip() != "unrated"]


PRACTICE_NOTE = "Practice board game"


def is_practice_row(row):
    """A practice-board game: unrated, but it still earns its own milestone."""
    return (row.get("Notes") or "").strip().startswith(PRACTICE_NOTE)


def read_practice_rows(path=None):
    """Practice-board rows of the rating log.  read_game_rows() leaves these
    out, because they are unrated."""
    path = path or config.RATING_LOG
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if is_practice_row(r)]


def read_drill_rows(path=None):
    from . import drill
    return drill.read_results(path or config.DRILL_LOG)


def _int_field(row, *names):
    for name in names:
        raw = (row.get(name) or "").strip()
        if raw == "":
            continue
        try:
            return int(float(str(raw).split()[0].replace(",", "")))
        except ValueError:
            continue
    return None


def result_of(row):
    return ratings.result_value(row.get("Result", ""))


def ending_of(row, pgn=None):
    how = (row.get("How it ended") or "").strip()
    if how:
        return how
    headers = pgn.headers if pgn is not None else pgn_headers(row)
    if headers:
        return (headers.get("Ending") or headers.get("Termination") or "").strip()
    return ""


def is_resigned(row, pgn=None):
    return "resign" in ending_of(row, pgn).lower()


def is_completed(row, pgn=None):
    """A finished game that was not resigned.  False if we cannot tell."""
    if result_of(row) is None:
        return False
    how = ending_of(row, pgn)
    if not how:
        return False
    return "resign" not in how.lower()


def is_checkmate_win(row, pgn=None):
    if result_of(row) != 1.0:
        return False
    return "checkmate" in ending_of(row, pgn).lower()


def lost_the_thread(row, pgn=None):
    """True if a lost thread was recorded, otherwise False.

    A blank log field is treated as no lost thread, unless the PGN file
    marks one (for example after the player said 'lost thread' during play
    but skipped the after-game review).
    """
    raw = (row.get("First lost thread") or "").strip().lower()
    if raw in ("never", "none", "no", "-"):
        return False
    if raw:
        return True
    headers = pgn.headers if pgn is not None else pgn_headers(row)
    if headers:
        marked = (headers.get("LostThreadMarked") or "").strip()
        if marked and marked.lower() not in ("never", "none", "-", ""):
            return True
        first = (headers.get("FirstLostThread") or "").strip().lower()
        if first and first not in ("never", "none", "-", ""):
            return True
    return False


def pgn_path_of(row):
    path = (row.get("PGN file") or "").strip()
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(config.APP_DIR, path)
    return path


def load_pgn(row):
    path = pgn_path_of(row)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return chess.pgn.read_game(f)
    except (OSError, ValueError):
        return None


def pgn_headers(row):
    game = load_pgn(row)
    return game.headers if game is not None else None


def move_count(row, pgn=None):
    """Full moves reached, e.g. 40 after White's or Black's 40th move."""
    if pgn is None:
        pgn = load_pgn(row)
    if pgn is None:
        return None
    moves = list(pgn.mainline_moves())
    if not moves:
        return 0
    return (len(moves) + 1) // 2


def request_move_numbers(row):
    text = (row.get("Position request moves") or "").strip()
    if not text or text == "-":
        return []
    return [int(n) for n in re.findall(r"\d+", text)]


def reconstruction_perfect(row):
    raw = (row.get("Reconstruction per cent") or "").strip().rstrip("%")
    if raw:
        try:
            return float(raw) >= 100
        except ValueError:
            pass
    frac = (row.get("Reconstruction") or "").strip()
    m = re.match(r"(\d+)\s*/\s*(\d+)", frac)
    if m and int(m.group(2)) > 0:
        return int(m.group(1)) == int(m.group(2))
    return False


def opponent_level(row):
    text = row.get("Opponent") or ""
    m = re.search(r"beginner\s*([12])\b", text, re.I)    # beginner 1 and 2 are -1 and 0
    if m:
        return int(m.group(1)) - 2
    m = re.search(r"level\s*(\d+)", text, re.I)
    if m:
        return int(m.group(1))
    try:
        rating = float(row.get("Opponent rating") or "")
    except ValueError:
        return None
    for level, (est, *_) in LEVELS.items():
        if est == rating:
            return level
    return None


def most_common_level(rows):
    levels = [opponent_level(r) for r in rows]
    levels = [lv for lv in levels if lv]
    if not levels:
        return None
    counts = Counter(levels)
    top = max(counts.values())
    return min(lv for lv, c in counts.items() if c == top)


def performance_rating(rows=None, path=None):
    games = ratings.read_games(path or config.RATING_LOG)
    if rows is not None and path is None:
        # When the caller already has in-memory rows (tests), use those.
        games = []
        for row in rows:
            result = result_of(row)
            try:
                rating = float(row.get("Opponent rating", ""))
            except ValueError:
                continue
            if result is None:
                continue
            games.append({"opponent": row.get("Opponent", ""), "rating": rating,
                          "result": result, "date": row.get("Date", "")})
    window = ratings.recent(games)
    p = ratings.performance(window)
    return p["performance"] if p else None


def rated_games(rows):
    return [r for r in rows if result_of(r) is not None and _rating(r) is not None]


def _rating(row):
    try:
        return float(row.get("Opponent rating", ""))
    except ValueError:
        return None


def win_count(rows):
    return sum(1 for r in rows if result_of(r) == 1.0)


def perfect_drills(drills, max_seconds=None):
    """Perfect drills of at least 20 squares, optionally in under max_seconds.

    Older 20-square rows and 30-square rows both count.
    """
    found = []
    for d in drills:
        if d["total"] < 20 or d["score"] != d["total"]:
            continue
        if max_seconds is not None and not (d["seconds"] < max_seconds):
            continue
        found.append(d)
    return found


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def detect(rows=None, drills=None, pgns=None, practice_rows=None):
    """The set of milestone ids that the current logs support.

    Practice-board games are unrated, so they are not among the rows read
    from the log; they are read separately (or picked out of `rows` when the
    caller passes rows in) and earn only the practice-board milestone.
    """
    if practice_rows is None:
        practice_rows = read_practice_rows() if rows is None else [r for r in rows if is_practice_row(r)]
    rows = list(rows if rows is not None else read_game_rows())
    rows = [r for r in rows if not is_practice_row(r)]
    drills = list(drills if drills is not None else read_drill_rows())
    pgns = pgns or {}

    def pgn_for(i, row):
        if i in pgns:
            return pgns[i]
        return load_pgn(row)

    earned = set()

    if practice_rows:
        earned.add("practice_board")
    if len(practice_rows) >= 5:
        earned.add("practice_board_5")
    if perfect_drills(drills):
        earned.add("perfect_drill")
    if perfect_drills(drills, max_seconds=60):
        earned.add("perfect_drill_90")
    if perfect_drills(drills, max_seconds=40):
        earned.add("perfect_drill_60")

    completed = 0
    no_thread_streak = 0
    max_no_thread_streak = 0
    usual = most_common_level(rows)

    for i, row in enumerate(rows):
        pgn = pgn_for(i, row)
        if is_completed(row, pgn):
            completed += 1
            earned.add("complete_game")
        if completed >= 5:
            earned.add("five_completed_games")

        if not lost_the_thread(row, pgn):
            no_thread_streak += 1
            max_no_thread_streak = max(max_no_thread_streak, no_thread_streak)
        else:
            no_thread_streak = 0

        illegal = _int_field(row, "Illegal attempts")
        if illegal == 0:
            earned.add("no_illegal")

        requests = _int_field(row, "Position requests")
        if requests == 0:
            earned.add("zero_position_requests")

        if is_checkmate_win(row, pgn):
            earned.add("first_checkmate")
        if result_of(row) == 1.0:
            earned.add("first_win")
        if reconstruction_perfect(row):
            earned.add("reconstruction_100")

        moves = move_count(row, pgn)
        if moves is not None and moves >= 12:
            earned.add("move_12")
        if moves is not None and moves >= 40:
            earned.add("forty_move_game")
        if moves is not None and moves >= 20:
            asked_by_move_20 = False
            if requests == 0:
                asked_by_move_20 = False
            else:
                nums = request_move_numbers(row)
                if requests and not nums:
                    asked_by_move_20 = None  # cannot tell when they asked
                else:
                    asked_by_move_20 = any(n <= 20 for n in nums)
            if asked_by_move_20 is False:
                earned.add("move_20_no_position")

        if usual is not None and result_of(row) == 1.0 and opponent_level(row) == usual + 1:
            earned.add("win_above_usual")

    if max_no_thread_streak >= 5:
        earned.add("five_no_lost_thread")

    n_rated = len(rated_games(rows))
    if n_rated >= 10:
        earned.add("ten_games")
    if n_rated >= 30:
        earned.add("thirty_games")
    wins = win_count(rows)
    if wins >= 5:
        earned.add("five_wins")
    if wins >= 10:
        earned.add("ten_wins")

    perf = performance_rating(rows)
    if perf is not None:
        for threshold in (1200, 1400, 1600, 1800):
            if perf >= threshold:
                earned.add(f"rating_{threshold}")

    return earned


# ---------------------------------------------------------------------------
# Persistence: add only
# ---------------------------------------------------------------------------

def load(path=None):
    """id -> date, for milestones already earned."""
    path = path or config.MILESTONES_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("achieved"), dict):
        data = data["achieved"]
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str)}


def save(achieved, path=None):
    path = path or config.MILESTONES_FILE
    payload = {"achieved": achieved}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def recompute(path=None, rows=None, drills=None, pgns=None, today=None):
    """Add any newly detected milestones.  Never removes one already stored.

    Returns (new_ids in definition order, full achieved dict).
    """
    path = path or config.MILESTONES_FILE
    achieved = load(path)
    detected = detect(rows=rows, drills=drills, pgns=pgns)
    date = (today or datetime.date.today()).isoformat()
    new = []
    for milestone_id, *_ in MILESTONES:
        if milestone_id in detected and milestone_id not in achieved:
            achieved[milestone_id] = date
            new.append(milestone_id)
    try:
        save(achieved, path)
    except OSError:
        pass
    return new, achieved


def counts(achieved=None, path=None):
    """(earned, total), counting only known milestone ids."""
    if achieved is None:
        achieved = load(path)
    earned = sum(1 for mid, *_ in MILESTONES if mid in achieved)
    return earned, TOTAL


def announcement_lines(new_ids, achieved):
    """Spoken lines for newly earned milestones, or an empty list."""
    if not new_ids:
        return []
    lines = [f"New milestone: {title_of(mid)}." for mid in new_ids]
    earned, total = counts(achieved)
    lines.append(f"You've earned {earned} of {total}.")
    return lines


def update_and_announce(ui, path=None, rows=None, drills=None, today=None):
    new, achieved = recompute(path=path, rows=rows, drills=drills, today=today)
    for line in announcement_lines(new, achieved):
        ui.say(line)
    return new, achieved


def progress_bar(earned, total):
    return "[" + "#" * earned + "-" * (total - earned) + "]"


def next_milestones(achieved, n=3):
    return [m for m in MILESTONES if m[0] not in achieved][:n]


def progress_lines(achieved=None, path=None):
    """A text progress bar per level, then the next two or three to aim for."""
    if achieved is None:
        achieved = load(path)
    lines = []
    for group in GROUPS:
        ids = [m[0] for m in MILESTONES if m[1] == group]
        n = sum(1 for mid in ids if mid in achieved)
        lines.append(f"{group} {progress_bar(n, len(ids))} {n}/{len(ids)}")
    earned, total = counts(achieved)
    lines.append(f"You've earned {earned} of {total} milestones.")
    nxt = next_milestones(achieved)
    if nxt:
        aims = " ".join(m[3].rstrip(".") + "." for m in nxt)
        lines.append("Next up: " + aims)
    else:
        lines.append("You've earned every milestone. Well done.")
    return lines
