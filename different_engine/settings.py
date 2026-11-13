"""Where things live, and remembering the player's last settings."""

import json
import os

# Everything is kept inside the Different Engine folder itself, so it is easy to find.
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_DIR = os.path.join(APP_DIR, "games")
MODELS_DIR = os.path.join(APP_DIR, "models")
ENGINE_DIR = os.path.join(APP_DIR, "engine")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
RATING_LOG = os.path.join(APP_DIR, "rating_log.csv")

DEFAULTS = {
    "colour": "white",          # "white", "black" or "random"
    "level": 2,                 # engine level, 1 to 8
    "position_limit": 3,        # position read-outs allowed per game (-1 = unlimited)
    "start": "usual",           # "usual" or "custom"
    "custom_fen": "",           # last custom position
    "stockfish_path": "",       # leave empty to find Stockfish automatically
    "hands_free": False,        # True: listen continuously instead of pressing Enter
    "voice_rate": 160,          # speaking speed, words per minute
    "microphone": None,         # device number from --test-mic, or None for the default
    "checkpoint_reminders": True,   # a short "good moment for a checkpoint" every five moves
}


def load():
    """Read settings.json, falling back to the defaults for anything missing."""
    settings = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            settings.update(json.load(f))
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        print("(Your settings file could not be read, so the usual settings will be used.)")
    return settings


def save(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        print("(Your settings could not be saved, but the game will carry on.)")
