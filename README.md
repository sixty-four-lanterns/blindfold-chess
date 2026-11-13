# The Different Engine

**A home-built, voice-driven blindfold chess partner.**

Companion software for *Eyes Closed, Mind Open: The Complete Guide to Blindfold Chess for Club Players* by Peter H Galloway (Sixty-Four Lanterns, 2026). Chapter 13, "Babbage's Different Engine", explains the idea behind it.

The Different Engine listens to your moves, checks them, replies in a spoken voice and keeps the score, so you can play a whole game without looking at a board or a screen. It works on **Windows 10 and 11**, on a **Raspberry Pi** or other **Linux** computer, and on a **Mac**.

You don't need any programming experience. The first time you start it, it installs everything it needs by itself.

---

## How it works

Each turn goes round the same loop (Figure 13.1 in the book):

1. **Listen.** You press Enter and say your move.
2. **Speech to text.** An offline speech-recognition model turns your voice into words.
3. **Request?** "Repeat" replays the engine's last move. "Position" reads out the whole position (king, queen, rooks, bishops, knights, then pawns from a to h, White first), up to the limit you set.
4. **Understand the move.** It accepts the moves you'd say to a person: "knight f3", "knight from g1 to f3", "pawn takes d5", "castles kingside".
5. **Legal and clear?** An illegal or ambiguous move is never guessed; you're asked to say it again.
6. **The engine replies** at the strength you chose.
7. **Text to speech.** The reply is spoken aloud: "Bishop to g4." Captures, checks and castling are announced.
8. **Game over?** The game is saved as a PGN file, shown on screen, and added to your rating log, and your current blindfold rating is worked out.

## What you need

- A Raspberry Pi (a Pi 4 or Pi 5 is best), **or** any Windows, Linux or Mac computer. An old laptop already has a microphone and speakers, so it costs nothing.
- A microphone and a speaker, or a headset. A USB headset works well.
- An internet connection **the first time only**, to download the free parts (about 150 MB in all). After that it works offline.

---

## Step 1: Download the files

1. On this page, click the green **Code** button, then **Download ZIP**.
2. Find the ZIP file in your Downloads folder and unpack it:
   - **Windows:** right-click the file, choose **Extract All**, then **Extract**.
   - **Mac:** double-click the file.
   - **Raspberry Pi / Linux:** right-click the file and choose **Extract Here**.
3. You now have a folder called something like `blindfold-chess-main`. You can move it anywhere you like, for example to your Desktop or Documents.

## Step 2: Start it

### Windows 10 and 11

1. Open the folder and double-click **Start-Windows.bat**.
2. If a blue box says "Windows protected your PC", click **More info**, then **Run anyway**. (This appears for any file downloaded from the internet.)
3. If Python isn't installed yet, the window offers to install it for you; type **Y**. When it has finished, close the window and double-click **Start-Windows.bat** again.
   *If it can't install Python itself*, it opens python.org. Download Python, and in the installer **tick "Add python.exe to PATH"** before clicking **Install Now**.
4. The first start takes a few minutes while it sets itself up and downloads the speech model and the Stockfish chess engine. Later starts take a few seconds.

To start it next time, just double-click **Start-Windows.bat** again.

### Raspberry Pi and other Linux computers

1. Open the folder in the file manager.
2. Open a terminal in that folder: on a Raspberry Pi, press **F4** (or choose **Tools > Open Current Folder in Terminal**).
3. Type this and press Enter:

   ```
   bash start-linux.sh
   ```

4. The first time, it lists a few free programs it needs (the voice, the microphone library, the chess engine and so on) and asks whether to install them. Press Enter to say yes, and type your password if asked; that is normal. Then it sets itself up, which takes a few minutes.

To start it next time, open a terminal in the folder again and type `bash start-linux.sh`.

*Prefer to double-click?* Type `chmod +x start-linux.sh` once in the terminal. After that you can double-click **start-linux.sh** and choose **Execute in Terminal**.

### Mac

1. Open **Terminal** (in Applications > Utilities).
2. Type `bash ` (with a space after it), then drag **start-mac.command** from the folder into the Terminal window, and press Enter.
3. If Python isn't installed, it tells you where to get it (python.org, the big yellow button). Install it, then repeat step 2.
4. The first time, your Mac asks whether Terminal may use the microphone. Click **OK**.

*Prefer to double-click?* In Terminal type `chmod +x ` (with a space), drag **start-mac.command** in, and press Enter. After that you can right-click **start-mac.command** and choose **Open** (the first time), and double-click it after that.

## Step 3: Test the microphone

The first time you start, it offers a microphone test. Say **"knight f3"** and check that it repeats it back correctly. Say **"stop"** to finish the test.

You can run the test again at any time; see [Extra options](#extra-options) below.

## Step 4: Choose your settings

Before the game you choose, by voice or by typing:

- **Your colour:** white, black or random.
- **The engine's level**, from 1 to 8:

  | Level | Rough rating | | Level | Rough rating |
  |---|---|---|---|---|
  | 1 | 800 | | 5 | 1600 |
  | 2 | 1000 | | 6 | 1800 |
  | 3 | 1200 | | 7 | 2000 |
  | 4 | 1400 | | 8 | 2300 |

  Start low. You're training to hold the position, not to beat a grandmaster in a box.
- **How many times you may ask for the position** in each game: a number, or "unlimited".

Your choices are remembered. Next time it simply asks, "Would you like the same settings again?"

## Step 5: Usual start or your own position

Next it asks whether to start from the **usual** opening position or a **custom** one.

If you say **custom**, a board opens in a window:

- **To place a piece**, click it on the right (white pieces on the top row, black below), then click the squares where you want it.
- **To move a piece**, drag it with the mouse.
- **To take a piece off**, right-click it, or click **Remove** and then the piece. Dragging a piece off the board also removes it.
- **Usual start** puts all the pieces back. **Clear (kings only)** leaves just the two kings. **Turn board round** shows it from Black's side.
- Choose **White to move** or **Black to move**.
- **Shortcut:** if you have the position as a FEN (most chess programs and websites can copy one), paste it into the box and click **Use this FEN**.
- Click **Start the game**. If the position isn't possible (a missing king, a pawn on the back rank, the wrong side in check and so on) it tells you what to fix.

The game then carries on by voice from your position, and it reads the position to you once at the start (this doesn't count against your limit).

---

## Playing

When it says "Your move", **press Enter, then speak**. It stops listening when you stop talking. If you'd rather, you can type the move instead of speaking and press Enter.

### Saying your moves

Speak as you would to a person: name the piece and the square, and say "takes" for captures.

| You can say | Meaning |
|---|---|
| "knight f3" or "knight to f3" | Nf3 |
| "knight from g1 to f3" | Nf3 |
| "e4" or "pawn to e4" | e4 |
| "pawn takes d5", or "e takes d5" | exd5 |
| "bishop takes delta three" | Bxd3 |
| "castles kingside" / "castles short" | O-O |
| "castles queenside" / "castles long" | O-O-O |
| "pawn to e8 queen", "e8 promotes to knight" | e8=Q, e8=N |
| "knight from b1 to d2", or "knight b d2" | Nbd2 (when two knights could go there) |

- **If it mishears a letter, use the spelling alphabet:** alpha, bravo, charlie, delta, echo, foxtrot, golf, hotel. "Bishop takes delta three" is much harder to get wrong than "bishop takes d3".
- If you don't name a piece, it assumes a pawn, just as in written notation.
- If your words could mean two different moves, or no legal move, it says so and asks again. It never guesses. Treat it as a free drill: picture the move on your mental board before you repeat it.
- When you clearly name a move that isn't legal (a piece and a square, or notation), it quietly notes the move number and what you said, for the after-game report. Those are usually slips of the mental board: a piece that wasn't there, a blocked path, or a king left in check. Mishearings, half-heard moves and moves that could mean two things are never counted against you.
- Every five moves (at moves 6, 11, 16 and so on) it says "This would be a good moment for a checkpoint", as a reminder to run through the position in your mind. It never reads the position for you. To switch the reminder off, change `"checkpoint_reminders"` to `false` in `settings.json`.
- During the game it behaves like a sporting opponent and nothing more: no hints, no evaluations, no warnings about loose pieces. Those wait until the game is over.

### Things you can ask for

| Say | What happens |
|---|---|
| **repeat** | Repeats the engine's last move. Always allowed. |
| **position** | Reads out the whole position. Counts against your limit; once it's used up, it politely declines. |
| **lost thread** | Tells it you have lost track of the position ("lost the thread" and "I've lost the thread" work too). It notes the move number for your after-game report and carries on; it doesn't read the position out. If you say it again, it keeps the first move. |
| **help** | Reminds you what you can say, and how many position requests you have left. |
| **draw** | Offers a draw. The engine accepts if it doesn't think it is better (and not in the first 20 moves). |
| **resign** | Resigns the game (it checks first). |
| **rating** | Tells you your current blindfold rating. |

## At the end of the game

When the game ends (checkmate, stalemate, a draw, or resignation):

1. It asks **at which move you first lost the thread** of the position, using what it already knows. If you said "lost thread" during the game, it checks that move with you. If not, but you tried an illegal move, it reminds you of the first one (the move number and what you said) and asks whether that was where you lost the thread. Say yes, a move number, or "never". It then asks whether you **broke any of your honesty rules** (a peek, for example), and lets you type a one-line **note**.
2. It **saves the game as a PGN file** in the `games` folder and **tells you where it was saved**, straight away, so nothing that follows can lose the game. (It doesn't show the game on screen yet, because that would give away the final position.)
3. It offers a **reconstruction test**: "Would you like to reconstruct the final position from memory, on a blank board?" If you say yes, an empty board opens in a window, the right way round for the colour you played. Put the pieces where you think they stood at the end, using the mouse just as on the set-up board (click a piece, then click squares; drag to move; right-click to remove), then click **Check my position**. Nothing about the true position is shown until you do. You get **one point for each piece of the right type and colour on its correct square**, and your score as a percentage of the pieces in the true position. It also tells you how many squares had the wrong piece, how many pieces were missing, and how many extra pieces you put on empty squares. A perfect score means every piece is in place and nothing extra has been added. After the check you can click **Show the true position** to compare: green squares are right, red ones had the wrong piece or shouldn't have had a piece, and amber ones had a piece you left out. Click **Skip** if you'd rather not. The reconstruction board needs tkinter, the same as the set-up board (on Linux, `sudo apt install python3-tk`); if it can't open, it says so and carries on.
4. It offers to **look through the game for the two or three biggest slips**. Stockfish, at full strength, spends a fraction of a second on each of your moves (a Raspberry Pi manages a ten-move game in a few seconds). For each slip it tells you the move number, what you played and what the engine preferred, roughly how much it cost, in plain words, and asks whether it was a **chess mistake** or a **visualisation mistake** (say "chess", "visualisation", "not sure", or "skip"). It also works out two plain figures for your moves: the **average centipawn loss** (a centipawn is a hundredth of a pawn; lower is better, and a single move counts for at most ten pawns, so one missed mate can't swamp the average) and **how many of your moves matched the engine's first choice**. These are not turned into a made-up "accuracy rating"; in this program the accuracy score is the reconstruction test.
5. It **shows the whole game on screen**, with everything above in the PGN headers, and gives a short **summary**: where you first lost the thread, how many illegal moves you tried and when, how many times you asked for the position and when, your reconstruction score, and your move-quality figures if the game was looked through. Any chess program can open a PGN file. Go through the game with the analysis turned on, as described in Chapter 12.
6. It adds a line to your **rating log** and tells you your **blindfold performance rating** (see below).
7. It offers to **read all the moves of the game aloud**. Say yes or no.

## Your blindfold rating (the strength gauge)

This follows Chapter 14 of the book exactly.

**The formula:**

> Performance = average opponent rating + 400 × (wins − losses) ÷ games played

Draws count as neither a win nor a loss, so they simply pull the result towards the opponents' average.

*Example from the book:* 24 games against levels rated 1100, 1200 and 1300, eight against each. The average opponent rating is 1200. You win 11, draw 4 and lose 9. Performance = 1200 + 400 × (11 − 9) ÷ 24 = **1233**.

How the Different Engine uses it:

- After every game it works out your rating and says it aloud, as a whole number. Don't chase decimals; a steady trend over several months means far more than a change of twenty or thirty points.
- **Rolling window:** once you have played more than 30 games, it uses only your most recent 30, so the figure shows your current strength.
- **Fewer than 20 games:** it still shows the figure, but reminds you it is only a guide until you have played at least 20 games, and preferably 30.
- **Too easy or too hard:** if you are scoring more than about 70 per cent or less than about 30 per cent against your current level, it suggests moving the engine up or down a level.
- **Two cautions**, which it repeats each time: the ratings given to engine levels are rough estimates, not always comparable with human ratings, so the gauge measures your progress against the same machine rather than your exact strength; and at low levels an engine makes odd blunders that a human would not, so treat the reading as a guide, not a verdict.

**The log** is a file called `rating_log.csv` in the Different Engine folder. It opens in Excel, LibreOffice, Numbers or Google Sheets. Each game has one row: date, opponent, opponent rating, colour, time control, result (1, 0.5 or 0), first lost thread, rule breaks, notes, position requests used, how the game ended, the starting position, the name of the PGN file, then the number of illegal attempts and the moves at which they came, the moves at which you asked for the position, the reconstruction score (for example 24/28) and its percentage, the average centipawn loss, how many moves matched the engine's first choice, and the slips with your verdicts (for example "7 Nf6 visualisation"). The last few are left blank if you skipped the reconstruction test or the slip review. A log made by an earlier version is brought up to date automatically the next time you finish a game: every row is kept, and so is any column you added yourself. You can add your own games to it by hand, and they will be counted too.

To see your rating without playing, use the `--rating` option (see below).

---

## Extra options

You can add an option when you start the program:

| Option | What it does |
|---|---|
| `--text` | Type your moves instead of speaking (no microphone needed). |
| `--test-mic` | Microphone test: say "knight f3" and it repeats it back. |
| `--rating` | Shows your rating, wins, draws, losses and average opponent rating, then stops. |
| `--quiet` | Prints the replies without speaking them. |
| `--hands-free` | Listens all the time, so you don't need to press Enter. Best with a headset. |
| `--mic 2` | Uses microphone number 2 (the microphone test lists the numbers). |

How to add an option:

- **Windows:** open the folder, click in the address bar at the top, type `cmd` and press Enter. In the black window type, for example, `Start-Windows.bat --text` and press Enter.
- **Raspberry Pi / Linux:** in the terminal, type for example `bash start-linux.sh --test-mic`.
- **Mac:** in Terminal, type `bash `, drag in start-mac.command, type ` --rating` and press Enter.

If it can't find a microphone at all, it tells you and lets you play by typing instead.

## Where things are kept

Everything stays inside the Different Engine folder:

| Folder or file | What it is |
|---|---|
| `games` | Your saved games (PGN files). |
| `rating_log.csv` | Your rating log, one row per game. |
| `settings.json` | Your last settings. Delete it to be asked everything afresh. |
| `models` | The speech-recognition model (downloaded on first run). |
| `engine` | The Stockfish chess engine, if it had to be downloaded. |
| `.venv` | The program's private copy of the Python parts. |

## If something goes wrong

- **It keeps mishearing me.** Speak a little more slowly, keep the microphone close, and use the spelling alphabet for the letters. A headset helps a lot in a noisy room. Run the microphone test to check.
- **"I couldn't find a microphone."** Plug the microphone in before starting, check it is not muted, and on a Mac allow Terminal to use the microphone (System Settings > Privacy & Security > Microphone). If you have several microphones, use `--test-mic` to see their numbers and `--mic` to choose one.
- **I can't hear it speak.** Check the volume and that the right speaker is chosen. On a Raspberry Pi or Linux, the voice comes from a program called espeak-ng, which the starter installs; you can also type `sudo apt install espeak-ng`.
- **The custom-position board doesn't open.** It then asks you to paste a FEN instead. On Linux, `sudo apt install python3-tk` adds the board window.
- **The reconstruction board doesn't open.** It needs a screen and tkinter, like the set-up board. Over SSH, or without `python3-tk` on Linux, it skips the test and carries on; the game is saved either way.
- **To start again from scratch**, delete the `.venv` folder and run the starter again. Your games and rating log are kept.

## Privacy

Speech recognition runs offline on your own machine. Your voice and your games stay with you. The internet is only used the first time, to download the free parts.

## The free parts it uses

- [Vosk](https://alphacephei.com/vosk/) offline speech recognition, with its small English model, listening only for chess words.
- [python-chess](https://python-chess.readthedocs.io/) for the rules of the game.
- [Stockfish](https://stockfishchess.org/), the open-source chess engine.
- Your computer's own voice: Windows' built-in voice (through pyttsx3), espeak-ng on Linux, and the Mac's built-in voice.
- [sounddevice](https://python-sounddevice.readthedocs.io/) for the microphone, and tkinter (part of Python) for the set-up and reconstruction boards.

### For the technically minded

The program is in the `different_engine` folder: `moves.py` (understanding spoken moves and describing moves and positions), `speech.py` (listening and speaking), `engine.py` (Stockfish levels), `ratings.py` (the rating log and formula), `board_editor.py` (the set-up board, and the board drawing it shares with the reconstruction test), `reconstruction.py` (the reconstruction test and its scoring), `review.py` (the slip review and the after-game summary), `game.py` (the loop) and `downloads.py` (first-run downloads). To run the tests: `.venv/bin/python -m pip install pytest`, then `.venv/bin/python -m pytest` (on Windows, `.venv\Scripts\python`).

## Licence

MIT Licence. Free to use, copy, modify and share. See the LICENSE file.

---

*"In the Analytical Engine I had devised mechanical means equivalent to memory, also … other means equivalent to foresight."*
Charles Babbage, *Passages from the Life of a Philosopher* (1864)
