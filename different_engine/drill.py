"""The spoken square-colour drill, matching the Colour flash drill in Chapter 3.

Thirty random squares are named with the spelling alphabet (for example
"delta five"), matching the Colour flash target in the book. The player
answers "light" or "dark" ("white" and "black" are accepted too). Each
answer is marked at once, and at the end the score and time are spoken
and written to drill_log.csv.
"""

import csv
import datetime
import os
import random
import re
import time

from . import settings as config

N_SQUARES = 30
COLUMNS = ["Date", "Score", "Total", "Seconds"]

FILES_SPOKEN = {
    "a": "alpha", "b": "bravo", "c": "charlie", "d": "delta",
    "e": "echo", "f": "foxtrot", "g": "golf", "h": "hotel",
}
RANKS_SPOKEN = {
    "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight",
}

DRILL_PHRASE = re.compile(
    r"\b(square\s+drill|colour\s+drill|color\s+drill|square\s+colours|square\s+colors)\b"
)


def is_drill_command(text):
    """True if the player asked for the square-colour drill."""
    t = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return bool(DRILL_PHRASE.search(t))


def all_squares():
    return [f + r for f in "abcdefgh" for r in "12345678"]


def speak_square(square):
    """'d5' -> 'delta five', so the file letter is hard to mishear."""
    square = square.lower()
    return f"{FILES_SPOKEN[square[0]]} {RANKS_SPOKEN[square[1]]}"


def square_colour(square):
    """'light' or 'dark'. a1 is dark, as on a standard board."""
    file_n = ord(square[0].lower()) - ord("a") + 1
    rank_n = int(square[1])
    return "dark" if file_n % 2 == rank_n % 2 else "light"


def parse_colour_answer(text):
    """'light' or 'dark', or None if the answer wasn't clear.

    'white' is treated as light, 'black' as dark.
    """
    t = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    words = set(t.split())
    light = bool(words & {"light", "white"})
    dark = bool(words & {"dark", "black"})
    if light and not dark:
        return "light"
    if dark and not light:
        return "dark"
    return None


def pick_squares(rng=None, n=N_SQUARES):
    """n distinct random squares."""
    rng = rng or random.Random()
    squares = all_squares()
    rng.shuffle(squares)
    return squares[:n]


def read_results(path=None):
    """Every drill row, oldest first.  Unreadable rows are skipped."""
    path = path or config.DRILL_LOG
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                score = int(row.get("Score", ""))
                total = int(row.get("Total", ""))
                seconds = int(row.get("Seconds", ""))
            except ValueError:
                continue
            rows.append({
                "date": row.get("Date", ""),
                "score": score,
                "total": total,
                "seconds": seconds,
            })
    return rows


def append_result(path, row):
    """Add one drill result, creating the file (with headings) if needed."""
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in COLUMNS})


def best_result(rows):
    """The best score, with the shortest time for that score.  None if no rows."""
    if not rows:
        return None
    return max(rows, key=lambda r: (r["score"], -r["seconds"], r["total"]))


def is_new_best(score, seconds, previous):
    if previous is None:
        return True
    return (score, -seconds) > (previous["score"], -previous["seconds"])


def summarise(score, total, seconds, previous=None, new_best=False):
    """Plain-English lines for the end of a drill."""
    noun = "second" if seconds == 1 else "seconds"
    lines = [f"You scored {score} out of {total} in {seconds} {noun}."]
    if new_best:
        lines.append("That's your best so far.")
    elif previous:
        best_noun = "second" if previous["seconds"] == 1 else "seconds"
        lines.append(
            f"Your best is {previous['score']} out of {previous['total']} "
            f"in {previous['seconds']} {best_noun}."
        )
    return lines


def run_drill(ui, path=None, rng=None, now=None, clock=time.monotonic, n=N_SQUARES):
    """Run one drill, save the result, and tell the player the score and time.

    Returns a dict with score, total, seconds and date.
    """
    path = path or config.DRILL_LOG
    squares = pick_squares(rng, n)
    previous = best_result(read_results(path))
    ui.say("Square-colour drill. I'll name thirty squares. Say light or dark after each one. "
           "White and black are fine too.")
    start = clock()
    score = 0
    for i, square in enumerate(squares, 1):
        print(f"  {i}/{n}: {square}")
        answer = ui.ask(f"{speak_square(square)}.", parse_colour_answer, "Light or dark?")
        correct = square_colour(square)
        if answer == correct:
            score += 1
            ui.say("Right.")
        else:
            ui.say(f"No, {correct}.")
    seconds = int(round(clock() - start))
    date = (now or datetime.date.today()).isoformat()
    append_result(path, {"Date": date, "Score": score, "Total": n, "Seconds": seconds})
    new_best = is_new_best(score, seconds, previous)
    for line in summarise(score, n, seconds, previous, new_best):
        ui.say(line)
    return {"score": score, "total": n, "seconds": seconds, "date": date}
