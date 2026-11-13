"""The rating log and the strength gauge (Chapter 14 of the book).

Every finished game adds one row to rating_log.csv, which opens in any
spreadsheet.  The performance rating uses the book's simple formula:

    Performance = average opponent rating + 400 x (wins - losses) / games played

Draws count as neither a win nor a loss.  Once there are more than 30 games,
only the most recent 30 are used (a rolling window).
"""

import csv
import os

COLUMNS = [
    "Date", "Opponent", "Opponent rating", "Colour", "Time control", "Result",
    "First lost thread", "Rule breaks", "Notes", "Position requests",
    "How it ended", "Start position", "PGN file",
    # added later: older logs are brought up to date automatically
    "Illegal attempts", "Illegal attempt moves", "Position request moves",
    "Reconstruction", "Reconstruction per cent", "Average centipawn loss",
    "Engine matches", "Slips",
]
WINDOW = 30           # rolling window size
MIN_GAMES = 20        # fewer than this: the figure is only a guide
GOOD_GAMES = 30       # "preferably thirty"

CAUTIONS = (
    "Two cautions. The ratings given to engine levels are rough estimates, and they "
    "are not always comparable with human ratings, so this gauge measures your progress "
    "against the same machine rather than your exact strength. And at low levels an "
    "engine makes odd blunders that a human would not, so treat the reading as a guide, "
    "not a verdict."
)


def upgrade_log(path):
    """If the log was made by an older version, rewrite it with the new columns.
    Every existing row is kept, and so is any column the player added by hand."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        old_columns = reader.fieldnames or []
        rows = list(reader)
    if old_columns[:len(COLUMNS)] == COLUMNS:
        return
    columns = COLUMNS + [c for c in old_columns if c and c not in COLUMNS]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) or "" for c in columns})


def append_game(path, row):
    """Add one game to the log, creating the file (with headings) if needed."""
    upgrade_log(path)
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    # utf-8-sig lets Excel on Windows open the file with the right characters
    columns = COLUMNS
    if not new_file:
        with open(path, newline="", encoding="utf-8-sig") as f:
            columns = next(csv.reader(f), None) or COLUMNS
    with open(path, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in columns})


def result_value(text):
    """'1', '0.5', '½', '1/2' or '0' -> 1.0, 0.5 or 0.0 (None if unreadable)."""
    t = str(text).strip().replace(",", ".")
    if t in ("1", "1.0", "win", "W"):
        return 1.0
    if t in ("0.5", ".5", "½", "1/2", "draw", "D"):
        return 0.5
    if t in ("0", "0.0", "loss", "L"):
        return 0.0
    return None


def read_games(path):
    """All usable games in the log, oldest first, as (opponent, rating, result) dicts."""
    if not os.path.exists(path):
        return []
    games = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            result = result_value(row.get("Result", ""))
            try:
                rating = float(row.get("Opponent rating", ""))
            except ValueError:
                continue
            if result is None:
                continue
            games.append({"opponent": row.get("Opponent", ""), "rating": rating,
                          "result": result, "date": row.get("Date", "")})
    return games


def recent(games, size=WINDOW):
    """The rolling window: the most recent `size` games once there are more."""
    return games[-size:] if len(games) > size else list(games)


def performance(games):
    """The book's formula.  Returns a dict of the figures, or None if no games."""
    n = len(games)
    if n == 0:
        return None
    wins = sum(1 for g in games if g["result"] == 1)
    losses = sum(1 for g in games if g["result"] == 0)
    draws = n - wins - losses
    average = sum(g["rating"] for g in games) / n
    perf = average + 400 * (wins - losses) / n
    score = (wins + 0.5 * draws) / n
    return {"games": n, "wins": wins, "draws": draws, "losses": losses,
            "average": round(average), "performance": round(perf), "score": score}


def report(games, current_opponent=None):
    """The gauge reading as a list of plain-English sentences."""
    if not games:
        return ["There are no games in your rating log yet."]
    window = recent(games)
    p = performance(window)
    which = (f"your last {p['games']} games" if len(games) > WINDOW
             else {1: "your only game", 2: "both your games"}.get(p["games"], f"all {p['games']} of your games"))
    w, d, l = p["wins"], p["draws"], p["losses"]
    lines = [
        f"Your blindfold performance rating is {p['performance']}.",
        f"That comes from {which}: {w} {'win' if w == 1 else 'wins'}, {d} {'draw' if d == 1 else 'draws'} "
        f"and {l} {'loss' if l == 1 else 'losses'}, against an average opponent rating of {p['average']}.",
    ]
    if p["games"] < MIN_GAMES:
        lines.append(f"With only {p['games']} {'game' if p['games'] == 1 else 'games'} this is just a guide. "
                     f"You need at least {MIN_GAMES} games, and preferably {GOOD_GAMES}, "
                     "before the figure is worth taking seriously.")

    # Level advice: the formula needs scores between about 30 and 70 per cent
    if current_opponent:
        at_level = [g for g in window if g["opponent"] == current_opponent]
        if len(at_level) >= 3:
            score = performance(at_level)["score"]
            percent = round(score * 100)
            if score > 0.7:
                lines.append(f"You have scored {percent} per cent against {current_opponent}. "
                             "Try moving the engine up a level, so that you score between about 30 and 70 per cent.")
            elif score < 0.3:
                lines.append(f"You have scored {percent} per cent against {current_opponent}. "
                             "Try moving the engine down a level, so that you score between about 30 and 70 per cent.")
    lines.append(CAUTIONS)
    return lines
