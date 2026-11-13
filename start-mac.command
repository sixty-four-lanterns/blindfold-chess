#!/bin/bash
# The Different Engine - starter for macOS.
#
# The first time, this installs everything that is needed. After that it
# simply starts the program. Anything you add after the name is passed on,
# e.g.  bash start-mac.command --text

cd "$(dirname "$0")" || exit 1

finish() {
    echo
    read -r -p "Press Enter to close this window. " _
    exit "${1:-1}"
}

echo
echo "  The Different Engine"
echo

# --- Python 3.9 or newer ---------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python 3 isn't installed on this Mac yet."
    if command -v brew >/dev/null 2>&1; then
        read -r -p "Install it now with Homebrew? [Y/n] " answer
        case "$answer" in
            [nN]*) ;;
            *) brew install python python-tk && PY=python3 ;;
        esac
    fi
    if [ -z "$PY" ]; then
        echo "Please download it from  https://www.python.org/downloads/  (the big yellow button),"
        echo "install it, then double-click start-mac.command again."
        open "https://www.python.org/downloads/" 2>/dev/null
        finish 1
    fi
fi

# --- Optional extras with Homebrew ---------------------------------------
if command -v brew >/dev/null 2>&1; then
    if ! command -v stockfish >/dev/null 2>&1; then
        read -r -p "Install the Stockfish chess engine with Homebrew? (If not, I'll download it myself.) [Y/n] " answer
        case "$answer" in [nN]*) ;; *) brew install stockfish ;; esac
    fi
    if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
        version=$("$PY" -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')")
        read -r -p "Install the board window (python-tk) with Homebrew? [Y/n] " answer
        case "$answer" in [nN]*) ;; *) brew install "python-tk@$version" ;; esac
    fi
fi
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "(The custom-position board can't open with this Python, but you can paste a FEN instead.)"
fi

# --- A private Python workspace for the program ---------------------------
if [ ! -x .venv/bin/python ]; then
    echo "First run: setting things up. This takes a few minutes and only happens once."
    if ! "$PY" -m venv .venv; then
        rm -rf .venv
        echo "Sorry, I couldn't set up Python's workspace (.venv)."
        finish 1
    fi
fi

if [ ! -f .venv/installed.txt ] || [ requirements.txt -nt .venv/installed.txt ]; then
    echo "Installing the Python packages (needs the internet)..."
    .venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1
    if ! .venv/bin/python -m pip install -r requirements.txt; then
        echo
        echo "Sorry, the Python packages could not be installed."
        echo "Please check the internet connection and run this again."
        finish 1
    fi
    date > .venv/installed.txt
fi

echo "(The first time, your Mac will ask whether Terminal may use the microphone: please click OK.)"
.venv/bin/python -m different_engine "$@"
status=$?
if [ $status -ne 0 ]; then
    finish $status
fi
