"""Ears and voice: listening with Vosk (offline) and speaking with pyttsx3.

Everything here is optional.  If there is no microphone, use --text mode; if
no voice can be found, the program simply prints what it would have said.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import time

from .moves import for_speech, vocabulary, NUMBER_WORDS

PIECES = ["king", "queen", "rook", "bishop", "knight", "pawn"]
FILE_WORDS = list("abcdefgh") + ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
RANK_WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight"]


# ---------------------------------------------------------------------------
# Speaking
# ---------------------------------------------------------------------------

class Speaker:
    """Prints everything, and also says it aloud if a voice is available."""

    def __init__(self, enabled=True, rate=160):
        self.rate = rate
        self.backend = None
        if enabled:
            self._choose_backend()

    def _choose_backend(self):
        # On a Mac the built-in "say" command is more dependable than pyttsx3.
        # On Linux, espeak-ng is likewise simpler than its pyttsx3 driver.
        # On Windows, a long-lived pyttsx3 engine often goes silent after the
        # microphone has been used, so we speak through Windows' own voice
        # (SAPI) in a fresh process each time.
        if sys.platform == "darwin" and shutil.which("say"):
            self.backend = "say"
            return
        if sys.platform.startswith("linux"):
            for cmd in ("espeak-ng", "espeak"):
                if shutil.which(cmd):
                    self.backend = cmd
                    return
        if sys.platform.startswith("win"):
            if shutil.which("cscript"):
                self.backend = "sapi"
                return
            if shutil.which("powershell"):
                self.backend = "powershell"
                return
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", self.rate)
            self.backend = "pyttsx3"
            return
        except Exception:
            pass
        print("(No speaking voice was found, so I'll print my replies instead. "
              "On Linux, installing espeak-ng fixes this.)")

    def _speak_sapi(self, spoken):
        """Speak with Windows SAPI via a short VBScript (faster than PowerShell)."""
        import tempfile
        sapi_rate = max(-10, min(10, int(round((self.rate - 160) / 20))))
        escaped = spoken.replace('"', '""')
        script = (f'Dim v: Set v = CreateObject("SAPI.SpVoice")\r\n'
                  f'v.Rate = {sapi_rate}\r\n'
                  f'v.Speak "{escaped}"\r\n')
        handle, path = tempfile.mkstemp(suffix=".vbs")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-16") as fh:
                fh.write(script)
            subprocess.run(["cscript", "//nologo", path], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _speak_powershell(self, spoken):
        escaped = spoken.replace("'", "''")
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"$s.Rate = {max(-10, min(10, int(round((self.rate - 160) / 20))))}; "
                  f"$s.Speak('{escaped}')")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=False)

    def say(self, text, show=True):
        if show:
            print(text)
        if not self.backend:
            return
        spoken = for_speech(text)
        try:
            if self.backend == "sapi":
                self._speak_sapi(spoken)
            elif self.backend == "powershell":
                self._speak_powershell(spoken)
            elif self.backend == "pyttsx3":
                # Re-create the engine each time; a reused one can go silent.
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                engine.say(spoken)
                engine.runAndWait()
                try:
                    engine.stop()
                except Exception:
                    pass
            elif self.backend == "say":
                subprocess.run(["say", "-r", str(self.rate), spoken], check=False)
            else:
                subprocess.run([self.backend, "-s", str(self.rate), spoken], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            if sys.platform.startswith("win") and self.backend != "powershell" and shutil.which("powershell"):
                try:
                    self._speak_powershell(spoken)
                    self.backend = "powershell"
                    return
                except Exception:
                    pass
            self.backend = None
            print("(The speaking voice stopped working, so I'll print my replies from now on.)")


# ---------------------------------------------------------------------------
# Listening
# ---------------------------------------------------------------------------

def grammar_phrases():
    """Example phrases for the recogniser.

    Vosk builds a small language model from these, so it expects chess words in
    chess order ("knight to f three") and ignores everything else.  This is
    what makes a small offline model accurate enough for chess.
    """
    phrases = set()
    for piece in PIECES:
        for f in FILE_WORDS:
            for r in RANK_WORDS:
                phrases.add(f"{piece} {f} {r}")
        for f, r in zip(FILE_WORDS, RANK_WORDS * 2):
            phrases.add(f"{piece} to {f} {r}")
            phrases.add(f"{piece} takes {f} {r}")
            phrases.add(f"{piece} captures {f} {r}")
            phrases.add(f"{piece} on {f} {r} takes {f} {r}")
            phrases.add(f"{piece} from {f} {r} to {f} {r}")
            phrases.add(f"{piece} {f} takes {f} {r}")
            phrases.add(f"{f} takes {f} {r}")
            phrases.add(f"{f} {r}")
            phrases.add(f"{f} {r} {f} {r}")
            phrases.add(f"{f} pawn takes {f} {r}")
            phrases.add(f"{piece} {f} {r} check")
    for f in FILE_WORDS:
        for promo in ("queen", "rook", "bishop", "knight"):
            phrases.add(f"pawn to {f} eight {promo}")
            phrases.add(f"{f} one promotes to {promo}")
            phrases.add(f"{f} eight equals {promo}")
            phrases.add(f"pawn takes {f} one promote to {promo}")
    phrases |= {
        "castles king side", "castles queen side", "castle king side", "castle queen side",
        "castles short", "castles long", "king side castle", "queen side castle",
        "takes en passant", "repeat", "say again", "position", "position please", "resign",
        "draw", "offer draw", "help", "rating", "yes", "no", "white", "black", "random",
        "usual", "custom", "keep", "change", "never", "stop", "unlimited", "level",
        "lost thread", "lost the thread",
        "chess", "visualisation", "visualization", "not sure", "skip",
    }
    for word, value in NUMBER_WORDS.items():
        if word not in ("won", "too", "for", "ate", "nought"):
            phrases.add(word)
            phrases.add(f"level {word}")
    for tens in ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"):
        for unit in ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine"):
            phrases.add(f"{tens} {unit}")
    words_used = {w for p in phrases for w in p.split()}
    assert words_used <= set(vocabulary()), words_used - set(vocabulary())
    return sorted(phrases) + ["[unk]"]


class VoiceInput:
    """Listens on the microphone and returns what was said, as text."""

    def __init__(self, model_path, device=None, hands_free=False):
        try:
            import sounddevice as sd
            import vosk
        except ImportError as exc:
            raise RuntimeError("The speech parts of the program aren't installed. Please start it with the "
                               "launcher for your computer, which installs them.") from exc
        except OSError as exc:      # sounddevice is installed but the PortAudio library isn't
            raise RuntimeError("The microphone library (PortAudio) isn't installed. On a Raspberry Pi or "
                               "other Linux computer, type:  sudo apt install libportaudio2") from exc
        self.sd, self.vosk = sd, vosk
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(model_path)
        self.grammar = json.dumps(grammar_phrases())
        self.device = device
        self.hands_free = hands_free
        try:
            info = sd.query_devices(device, "input")
        except Exception as exc:
            raise RuntimeError("I couldn't find a microphone. Please plug one in (or check that it is "
                               "switched on) and start again, or use text mode.") from exc
        self.rate = int(info["default_samplerate"])

    def recognise_raw(self, audio_bytes, rate=16000):
        """Recognise a recording (16-bit mono).  Used by the tests."""
        rec = self.vosk.KaldiRecognizer(self.model, rate, self.grammar)
        rec.AcceptWaveform(audio_bytes)
        return _clean(json.loads(rec.FinalResult()).get("text", ""))

    def listen(self, prompt="Press Enter, then speak (or type it here): ", timeout=10):
        """Wait for the player, then return the words they said ("" if nothing)."""
        if not self.hands_free:
            typed = input(prompt)
            if typed.strip():
                return typed            # they typed instead of speaking: that's fine too
        print("  Listening...")
        rec = self.vosk.KaldiRecognizer(self.model, self.rate, self.grammar)
        audio = queue.Queue()

        def callback(indata, frames, when, status):
            audio.put(bytes(indata))

        heard, last_word_time, speaking = [], None, False
        start = time.time()
        with self.sd.RawInputStream(samplerate=self.rate, blocksize=self.rate // 8, device=self.device,
                                    dtype="int16", channels=1, callback=callback):
            while True:
                try:
                    data = audio.get(timeout=0.25)
                except queue.Empty:
                    data = None
                if data is not None:
                    if rec.AcceptWaveform(data):
                        text = _clean(json.loads(rec.Result()).get("text", ""))
                        if text:
                            heard.append(text)
                            last_word_time = time.time()
                        speaking = False
                    else:
                        speaking = bool(_clean(json.loads(rec.PartialResult()).get("partial", "")))
                now = time.time()
                # Allow a short pause mid-move ("knight ... f3") before finishing.
                if heard and not speaking and now - last_word_time > 1.0:
                    break
                if not self.hands_free and now - start > (timeout if not heard and not speaking else 20):
                    heard.append(_clean(json.loads(rec.FinalResult()).get("text", "")))
                    break
        return " ".join(heard)


def _clean(text):
    return " ".join(w for w in text.split() if w != "[unk]")


def list_microphones():
    """Print the microphones the computer knows about."""
    import sounddevice as sd
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(f"  {index}: {dev['name']}")
