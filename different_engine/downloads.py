"""First-run downloads: the speech-recognition model and the Stockfish engine.

Both are fetched once and kept in the Different Engine folder.  If the
computer already has Stockfish installed (for example with apt or Homebrew),
that copy is used instead.
"""

import os
import platform
import shutil
import ssl
import stat
import sys
import tarfile
import urllib.request
import zipfile

from .settings import MODELS_DIR, ENGINE_DIR

VOSK_MODEL = "vosk-model-small-en-us-0.15"
VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL}.zip"

STOCKFISH_RELEASE = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/"


class SetupError(Exception):
    """A problem we can explain to the player in plain English."""


def _ssl_context():
    """Use certifi's certificates if available (python.org Pythons on a Mac lack them)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _download(url, dest, what):
    """Download with a simple progress read-out."""
    print(f"Downloading {what} (this only happens once)...")
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60, context=_ssl_context()) as response, open(tmp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done, shown = 0, -1
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                percent = done * 100 // total if total else -1
                if percent != shown and percent % 5 == 0:
                    print(f"\r  {percent}% of {total // 1_000_000} MB", end="", flush=True)
                    shown = percent
        print()
        os.replace(tmp, dest)
    except Exception as exc:          # network errors come in many shapes
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SetupError(f"I couldn't download {what}. Please check that this computer is connected to "
                         f"the internet and try again.\n(Details: {exc})") from exc


def ensure_vosk_model():
    """Return the folder of the speech model, downloading it on first use."""
    folder = os.path.join(MODELS_DIR, VOSK_MODEL)
    if os.path.isdir(os.path.join(folder, "am")):
        return folder
    os.makedirs(MODELS_DIR, exist_ok=True)
    archive = os.path.join(MODELS_DIR, VOSK_MODEL + ".zip")
    _download(VOSK_URL, archive, "the speech-recognition model (about 40 MB)")
    try:
        with zipfile.ZipFile(archive) as z:
            z.extractall(MODELS_DIR)
    except zipfile.BadZipFile as exc:
        raise SetupError("The speech model download was damaged. Please run the program again.") from exc
    finally:
        os.remove(archive)
    return folder


def _stockfish_asset():
    """Pick the official Stockfish download that suits this computer."""
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if sys.platform.startswith("win"):
        return "stockfish-windows-arm64-universal.zip" if arm else "stockfish-windows-x86-64-universal.zip"
    if sys.platform == "darwin":
        return "stockfish-macos-universal.tar.gz"
    if sys.platform.startswith("linux"):
        if arm and sys.maxsize > 2**32:
            return "stockfish-linux-arm64-universal.tar.gz"
        if machine in ("x86_64", "amd64"):
            return "stockfish-linux-x86-64-universal.tar.gz"
    return None


def find_stockfish(configured=""):
    """Look for Stockfish: the settings file, our own engine folder, then the system."""
    candidates = [configured] if configured else []
    if os.path.isdir(ENGINE_DIR):
        for name in sorted(os.listdir(ENGINE_DIR)):
            if name.startswith("stockfish"):
                candidates.append(os.path.join(ENGINE_DIR, name))
    candidates += [shutil.which("stockfish") or "", "/usr/games/stockfish",
                   "/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish"]
    for path in candidates:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def ensure_stockfish(configured=""):
    """Return a path to Stockfish, downloading the official build if there is none."""
    found = find_stockfish(configured)
    if found:
        return found
    asset = _stockfish_asset()
    if asset is None:
        raise SetupError("I couldn't find the Stockfish chess engine, and there is no ready-made download "
                         "for this kind of computer. On a Raspberry Pi with a 32-bit system, open a terminal "
                         "and type:  sudo apt install stockfish   then start the program again.")
    os.makedirs(ENGINE_DIR, exist_ok=True)
    archive = os.path.join(ENGINE_DIR, asset)
    _download(STOCKFISH_RELEASE + asset, archive, "the Stockfish chess engine (about 80 MB)")
    exe_name = "stockfish.exe" if sys.platform.startswith("win") else "stockfish"
    target = os.path.join(ENGINE_DIR, exe_name)
    try:
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                member = next(n for n in z.namelist() if n.endswith(".exe"))
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive) as t:
                member = next(m for m in t.getmembers()
                              if m.isfile() and os.path.basename(m.name).startswith("stockfish-"))
                with t.extractfile(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (StopIteration, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise SetupError("The Stockfish download was damaged. Please run the program again.") from exc
    finally:
        os.remove(archive)
    os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return target
