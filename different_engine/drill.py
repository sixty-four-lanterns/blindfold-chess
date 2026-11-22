"""The spoken square-colour drill, matching the Colour flash drill in Chapter 3.

Twenty random squares are named with the spelling alphabet (for example
"delta five"). The book's Colour flash target remains thirty squares
in thirty seconds; this spoken round is shorter. The player
answers "light" or "dark" ("white" and "black" are accepted too). A
click marks a correct answer; a wrong one is spoken. Only the player's
thinking time is counted, and at the end the score and that time are
spoken and written to drill_log.csv.
"""

import csv
import datetime
import math
import os
import random
import re
import struct
import subprocess
import sys
import time
import wave

from . import settings as config

N_SQUARES = 20
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


LIGHT_WORDS = {"light", "white", "lite", "lights"}
DARK_WORDS = {"dark", "black", "darke"}


def parse_colour_answer(text):
    """'light' or 'dark', or None if the answer wasn't clear.

    'white' is treated as light, 'black' as dark.  'light square',
    'dark square', and a few common mishearings ('lite', 'lights',
    'darke', 'dark one') are accepted too.
    """
    t = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    words = set(t.split())
    light = bool(words & LIGHT_WORDS)
    dark = bool(words & DARK_WORDS)
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
                seconds = parse_seconds(row.get("Seconds", ""))
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


def parse_seconds(value):
    """Accept a whole number or one decimal place from the log."""
    seconds = float(value)
    if seconds == int(seconds):
        return int(seconds)
    return seconds


def store_seconds(seconds):
    """Round thinking time to one decimal place, as an int when it is whole."""
    seconds = max(0.0, round(float(seconds), 1))
    if seconds == int(seconds):
        return int(seconds)
    return seconds


def seconds_phrase(seconds):
    """12 -> '12 seconds'; 1 -> '1 second'; 12.5 -> '12.5 seconds'."""
    noun = "second" if seconds == 1 else "seconds"
    return f"{seconds} {noun}"


def summarise(score, total, seconds, previous=None, new_best=False):
    """Plain-English lines for the end of a drill."""
    lines = [f"You scored {score} out of {total}.",
             f"Your thinking time was {seconds_phrase(seconds)}."]
    if new_best:
        lines.append("That's your best so far.")
    elif previous:
        lines.append(
            f"Your best is {previous['score']} out of {previous['total']} "
            f"in {seconds_phrase(previous['seconds'])}."
        )
    return lines


# ---------------------------------------------------------------------------
# A short click for a correct answer
# ---------------------------------------------------------------------------

CLICK_SECONDS = 0.12   # long and loud enough to hear clearly (was 0.04)
CLICK_RATE = 22050
CLICK_FREQ = 1000


def click_wav_bytes(freq=CLICK_FREQ, duration=CLICK_SECONDS, rate=CLICK_RATE, amplitude=0.95):
    """A very short decaying tone, as WAV file bytes."""
    n = int(rate * duration)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 25)
        sample = int(amplitude * env * 32767 * math.sin(2 * math.pi * freq * t))
        frames += struct.pack("<h", max(-32768, min(32767, sample)))
    # A minimal 16-bit mono WAV header (44 bytes) plus the samples
    data_size = len(frames)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE", b"fmt ", 16,
        1, 1, rate, rate * 2, 2, 16, b"data", data_size,
    )
    return header + frames


def write_click_wav(path):
    raw = click_wav_bytes()
    # Write via the wave module so the header is always well-formed
    n = (len(raw) - 44) // 2
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(CLICK_RATE)
        w.writeframes(raw[44:])
    return path


def click_wav_path():
    """The packaged click, created on first use if the file is missing."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "click.wav")
    if os.path.exists(path):
        return path
    try:
        write_click_wav(path)
        return path
    except OSError:
        fallback = os.path.join(config.APP_DIR, "click.wav")
        os.makedirs(config.APP_DIR, exist_ok=True)
        write_click_wav(fallback)
        return fallback


def play_click(path=None):
    """Play the short click.  Returns True if a sound (or a terminal bell) was produced.

    Windows uses winsound, macOS afplay, and Linux paplay, aplay or pw-play.
    If none of those is available, simpleaudio is tried if it is installed,
    then a terminal bell.  Returns False only if nothing could be played,
    in which case the drill should say 'Correct.' instead.
    """
    path = path or click_wav_path()
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        if sys.platform == "darwin" and _which("afplay"):
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        for cmd in ("paplay", "aplay", "pw-play"):
            if _which(cmd):
                subprocess.Popen([cmd, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        try:
            import simpleaudio
            simpleaudio.WaveObject.from_wave_file(path).play()
            return True
        except Exception:
            pass
        print("", end="", flush=True)
        return True
    except Exception:
        return False


def _which(cmd):
    from shutil import which
    return which(cmd)


def _hear_thinking(ui, prompt, clock):
    """Hear one answer and the thinking time for that attempt."""
    start = clock()
    text = ui.hear(prompt)
    elapsed = getattr(ui, "last_thinking_seconds", None)
    if elapsed is None:
        elapsed = clock() - start
    return text, max(0.0, float(elapsed))


def run_drill(ui, path=None, rng=None, now=None, clock=time.monotonic, n=N_SQUARES,
              play=None):
    """Run one drill, save the result, and tell the player the score and time.

    Only the player's thinking time is counted: the clock starts when the
    square has finished being spoken, and stops when the player starts
    answering.  Machine speech, recognition delays and the click are excluded.

    `play` is play_click by default; pass a stub in tests.  Returns a dict
    with score, total, seconds and date.
    """
    path = path or config.DRILL_LOG
    squares = pick_squares(rng, n)
    previous = best_result(read_results(path))
    click = play if play is not None else play_click
    ui.say("Square-colour drill. I'll name twenty squares. Say light or dark after each one. "
           "White and black are fine too. A click means correct. Only your thinking time is counted.")
    thinking = 0.0
    score = 0
    for i, square in enumerate(squares, 1):
        print(f"  {i}/{n}: {square}")
        ui.say(f"{speak_square(square)}.")
        prompt = "Light or dark?"
        failures = 0
        while True:
            text, elapsed = _hear_thinking(ui, prompt, clock)
            thinking += elapsed
            answer = parse_colour_answer((text or "").lower())
            if answer is not None:
                break
            failures += 1
            if getattr(ui, "listener", None) and failures >= 2:
                prompt = "Please type your answer and press Enter:"
                ui.say("Sorry, I didn't catch that. You can type the answer instead.")
            else:
                ui.say("Sorry, I didn't catch that. Light or dark.")
        correct = square_colour(square)
        if answer == correct:
            score += 1
            if not click():
                ui.say("Correct.")
        else:
            ui.say(f"No, {correct}.")
    seconds = store_seconds(thinking)
    date = (now or datetime.date.today()).isoformat()
    append_result(path, {"Date": date, "Score": score, "Total": n, "Seconds": seconds})
    new_best = is_new_best(score, seconds, previous)
    for line in summarise(score, n, seconds, previous, new_best):
        ui.say(line)
    return {"score": score, "total": n, "seconds": seconds, "date": date}
