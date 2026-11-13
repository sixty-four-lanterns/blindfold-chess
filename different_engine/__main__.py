"""Start the Different Engine.  Normally run by the launcher for your computer:

    Start-Windows.bat   start-linux.sh   start-mac.command

Options (add them after the launcher name, or after "python -m different_engine"):
    --text        type moves instead of speaking them (no microphone needed)
    --test-mic    check the microphone: say "knight f3" and hear it repeated
    --rating      show your performance rating from the log, then stop
    --quiet       don't speak, just print
    --hands-free  listen all the time instead of waiting for Enter
    --mic N       use microphone number N (see --test-mic for the list)
"""

import argparse
import os
import sys

import chess

from . import settings as config, ratings
from .downloads import ensure_stockfish, ensure_vosk_model, SetupError
from .game import Interface, Stop, choose_settings, play
from .moves import parse, describe_move
from .speech import Speaker, VoiceInput, list_microphones


def test_microphone(speaker, listener):
    print("\nMicrophones on this computer:")
    try:
        list_microphones()
    except Exception:
        pass
    speaker.say("Microphone test. Say knight f3, or any other move from the starting position. "
                "Say stop when you have finished.")
    board = chess.Board()
    while True:
        heard = listener.listen("  Press Enter, then speak: ")
        print(f"  I heard: {heard or 'nothing'}")
        if "stop" in heard.split() or "quit" in heard.split():
            speaker.say("Microphone test finished.")
            return
        r = parse(board, heard)
        if r.kind == "move":
            speaker.say(f"I heard: {describe_move(board, r.move)}.")
        elif r.kind == "command":
            speaker.say(f"I heard the command: {r.command}.")
        else:
            speaker.say("I didn't catch a move. " + ("Please try again." if heard else "Is the microphone switched on?"))


def main(argv=None):
    p = argparse.ArgumentParser(prog="different_engine", description="The Different Engine: a voice-driven "
                                "blindfold chess partner.")
    p.add_argument("--text", action="store_true", help="type moves instead of speaking (no microphone)")
    p.add_argument("--test-mic", action="store_true", help="test the microphone and speech recognition")
    p.add_argument("--rating", "--log", action="store_true", help="show your performance rating and stop")
    p.add_argument("--quiet", action="store_true", help="print replies without speaking them")
    p.add_argument("--hands-free", action="store_true", help="listen all the time, without pressing Enter")
    p.add_argument("--mic", type=int, default=None, help="microphone number to use")
    args = p.parse_args(argv)

    print("\n  THE DIFFERENT ENGINE\n  A blindfold chess partner, after Charles Babbage\n")

    if args.rating:
        games = ratings.read_games(config.RATING_LOG)
        window = ratings.recent(games)
        if window:
            print(f"Games counted ({len(window)} most recent of {len(games)}):")
            for g in window:
                result = {1.0: "win", 0.5: "draw", 0.0: "loss"}[g["result"]]
                print(f"  {g['date']:<12} {g['opponent']:<22} {g['rating']:>6.0f}   {result}")
            print()
        for line in ratings.report(games, window[-1]["opponent"] if window else None):
            print(line)
        return 0

    first_time = not os.path.exists(config.SETTINGS_FILE)
    s = config.load()
    speaker = Speaker(enabled=not args.quiet, rate=s["voice_rate"])
    try:
        listener = None
        if not args.text:
            try:
                model = ensure_vosk_model()
                listener = VoiceInput(model, device=args.mic if args.mic is not None else s["microphone"],
                                      hands_free=args.hands_free or s["hands_free"])
            except (SetupError, RuntimeError) as exc:
                print(f"\n{exc}\n")
                if args.test_mic:
                    return 1
                print("For now we'll play by typing the moves instead.\n")
        if args.test_mic:
            test_microphone(speaker, listener)
            return 0
        if first_time and listener and Interface(speaker, listener).yes_no(
                "Welcome. As this is your first time, would you like to test the microphone first?"):
            test_microphone(speaker, listener)

        engine_path = ensure_stockfish(s["stockfish_path"])
        ui = Interface(speaker, listener)
        speaker.say("Welcome to the Different Engine.")
        while True:
            s = choose_settings(ui, s, first_time)
            config.save(s)
            first_time = False
            play(ui, s, engine_path)
            if not ui.yes_no("Would you like another game?"):
                speaker.say("Thank you for playing. Goodbye.")
                return 0
    except (Stop, KeyboardInterrupt):
        print("\nGoodbye.")
        return 0
    except SetupError as exc:
        print("\nSorry, something needs sorting out before we can play:\n")
        print(exc)
        return 1
    except RuntimeError as exc:
        print("\nSorry, there was a problem:\n")
        print(exc)
        print("\nYou can still play by typing your moves: start the program with --text "
              "(see the README for how).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
