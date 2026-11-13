#!/usr/bin/env bash
# The Different Engine - starter for Linux, including Raspberry Pi OS.
#
# The first time, this installs everything that is needed (it asks before
# installing anything with "sudo"). After that it simply starts the program.
# Anything you add after the name is passed on, e.g.  bash start-linux.sh --text

cd "$(dirname "$0")" || exit 1

finish() {
    echo
    read -r -p "Press Enter to close this window. " _
    exit "${1:-1}"
}

echo
echo "  The Different Engine"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 isn't installed on this computer."
    echo "On Raspberry Pi OS, Debian or Ubuntu, open a terminal and type:"
    echo "    sudo apt install python3"
    finish 1
fi

# --- System packages: only those that are missing -------------------------
missing=()
python3 -c "import venv, ensurepip" >/dev/null 2>&1 || missing+=(python3-venv)
python3 -c "import tkinter" >/dev/null 2>&1 || missing+=(python3-tk)
command -v espeak-ng >/dev/null 2>&1 || missing+=(espeak-ng)
{ ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null; } | grep -q libportaudio || missing+=(libportaudio2)
if ! command -v stockfish >/dev/null 2>&1 && [ ! -x /usr/games/stockfish ]; then
    missing+=(stockfish)
fi

if [ ${#missing[@]} -gt 0 ]; then
    echo "A few free programs need adding to this computer first:"
    echo "    ${missing[*]}"
    if command -v apt-get >/dev/null 2>&1; then
        echo "I can install them now. You may be asked for your password; that is normal."
        read -r -p "Install them now? [Y/n] " answer
        case "$answer" in
            [nN]*) echo "Skipping. Some parts (such as the voice) may not work." ;;
            *) sudo apt-get update && sudo apt-get install -y "${missing[@]}" \
                   || echo "Some packages could not be installed; carrying on anyway." ;;
        esac
    else
        echo "Please install them with your system's package manager, then run this again."
        echo "Carrying on for now."
    fi
    echo
fi

if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    echo "Python's 'venv' part is still missing, so I can't set up the program."
    echo "Please type:  sudo apt install python3-venv   and then run this again."
    finish 1
fi

# --- A private Python workspace for the program ---------------------------
if [ ! -x .venv/bin/python ]; then
    echo "First run: setting things up. This takes a few minutes and only happens once."
    if ! python3 -m venv .venv; then
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

# --- Start -----------------------------------------------------------------
.venv/bin/python -m different_engine "$@"
status=$?
if [ $status -ne 0 ]; then
    finish $status
fi
