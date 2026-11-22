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
8. **Game over?** The game is saved as a PGN file and added to your rating log, and your current blindfold rating is spoken. After-game extras (the reconstruction test, a slip review and so on) run only if you say **review**.

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

The first time it starts, it also puts a shortcut called **The Different Engine** on your Desktop. After that, just double-click the shortcut (or **Start-Windows.bat** again).

### Raspberry Pi and other Linux computers

1. Open the folder in the file manager.
2. Open a terminal in that folder: on a Raspberry Pi, press **F4** (or choose **Tools > Open Current Folder in Terminal**).
3. Type this and press Enter:

   ```
   bash start-linux.sh
   ```

4. The first time, it lists a few free programs it needs (the voice, the microphone library, the chess engine and so on) and asks whether to install them. Press Enter to say yes, and type your password if asked; that is normal. Then it sets itself up, which takes a few minutes.

To start it next time, open a terminal in the folder again and type `bash start-linux.sh`.

The first time it starts, it also puts a shortcut called **The Different Engine** on your Desktop, if you have a Desktop folder. Double-click that next time (choose **Execute in Terminal** if asked). If the icon is not trusted at first, right-click it, choose **Properties** and allow it to launch, or type `chmod +x start-linux.sh` once in the terminal and double-click **start-linux.sh** itself.

### Mac

1. Open **Terminal** (in Applications > Utilities).
2. Type `bash ` (with a space after it), then drag **start-mac.command** from the folder into the Terminal window, and press Enter.
3. If Python isn't installed, it tells you where to get it (python.org, the big yellow button). Install it, then repeat step 2.
4. The first time, your Mac asks whether Terminal may use the microphone. Click **OK**.

*Prefer to double-click?* In Terminal type `chmod +x ` (with a space), drag **start-mac.command** in, and press Enter. After that you can right-click **start-mac.command** and choose **Open** (the first time), and double-click it after that. (The starter does not add a Desktop icon on a Mac by itself.)

## Step 3: Test the microphone

The first time you start, and only that once, it offers a short microphone test. You can say no and go straight into a game. If you say yes, say **"knight f3"** and check that it repeats it back correctly, then say **"stop"** to finish the test.

You can run the test again at any time; see [Extra options](#extra-options) below.

## Step 4: It starts a game at once

After the welcome it goes straight into a game, using your last settings, or, the first time, these usual ones: you play **White**, the engine is at **level 2**, and you may ask for the position **three** times. It says something like: "Welcome to the Different Engine. You're White, level 2, three position requests. Your move." If you are playing Black, it announces the engine's first move instead.

Before your first move you can:

- Say **settings** to change your colour, the engine's level, your position-request limit, and whether to start from the usual opening position or a custom one.
- Say **play black**, **play white**, **switch colours** or **random** to change sides. The game starts again from the beginning, and your choice is remembered.
- Say **square drill** (or just **drill**) to run the spoken square-colour test (see [Square-colour drill](#square-colour-drill)).
- Say **milestones** (or **progress**) to hear how many milestones you have earned, and what to aim for next.
- Say **rating** (or **my rating**, or **what's my rating**) to hear your current blindfold rating and how many games it is based on.
- Say **reset rating** to start your rating again from scratch. It asks you to confirm first, and keeps your old games in a dated file.
- Say **show board** to look through your last game on a board, move by move with an analysis bar, or to load a PGN file (see [Show board](#show-board-going-through-the-game)).
- Say **level 4** (or any level from 1 to 8, or **set level 4**, or **change level to 4**) to change the engine's level. Spoken numbers such as "level four" work too. Before your first move it applies at once; after you have moved, it is saved for the next game.

To go through the full settings questions at launch, start the program with `--setup` (see [Extra options](#extra-options)).

The engine has eight levels:

  | Level | Rough rating | | Level | Rough rating |
  |---|---|---|---|---|
  | 1 | 800 | | 5 | 1600 |
  | 2 | 1000 | | 6 | 1800 |
  | 3 | 1200 | | 7 | 2000 |
  | 4 | 1400 | | 8 | 2300 |

Start low. You're training to hold the position, not to beat a grandmaster in a box.

## Step 5: Usual start or your own position

The usual opening position is used unless you have saved a custom one. To set a custom position, say **settings** before your first move (or start with `--setup`) and then say **custom**.

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
- Every five moves (at moves 6, 11, 16 and so on) it shows "This would be a good moment for a checkpoint" on screen (it isn't spoken), as a reminder to run through the position in your mind. It never reads the position for you. To switch the reminder off, change `"checkpoint_reminders"` to `false` in `settings.json`.
- After each move, a short **status line** is printed in the terminal, for example: `Move 12 | You: White | Level 3 | Position requests left: 2 | Blindfold rating: 1233 (14 games) | Milestones 9/22`. If you have taken a move back in this game, it also shows `Take-backs: N`. It never shows the board, the moves, or an evaluation.
- During the game it behaves like a sporting opponent and nothing more: no hints, no evaluations, no warnings about loose pieces. Those wait until the game is over, and only if you ask for a review.

### Things you can ask for

| Say | What happens |
|---|---|
| **repeat** | Repeats the engine's last move. Always allowed. |
| **last move** / **last moves** / **what was the last move** | Speaks your last move and the engine's reply, for example "Your last move was knight to f3, and I played pawn to e5." Always allowed; it does not use a position request. "Say last move" and "what did you play" work too. **repeat** still only repeats the engine's last move. |
| **take back** / **undo** / **go back** | Undoes your last move and the engine's reply, so you can say the move again if it was misheard. You can say this as often as you need; the game still counts for your rating. "Takeback" and "take that back" work too. If the game has just ended on a misheard move, you can still say **take back** before the after-game steps. |
| **position** | Reads out the whole position. Counts against your limit; once it's used up, it politely declines. |
| **lost thread** | Tells it you have lost track of the position ("lost the thread" and "I've lost the thread" work too). It notes the move number for your after-game report and carries on; it doesn't read the position out. If you say it again, it keeps the first move. |
| **help** / **commands** / **what can I say** | Shows the list of commands on the screen; nothing is spoken. During a game the list includes how many position requests you have left. |
| **settings** | Before your first move, opens the full settings dialogue (colour, level, position limit, and usual or custom start). After you have moved, it tells you it is too late for this game. |
| **level 1** to **level 8** / **set level N** / **change level to N** | Sets the engine's level (spoken numbers such as "four" are accepted too). Before your first move, or between games, it applies at once and it says "Engine level 4, about 1400." After you have moved, this game stays at its current level and it says "Level 4 from your next game." A number outside 1 to 8 gets a short reminder of the range. It does not use a position request. |
| **play white** / **play black** / **switch colours** / **random** | Before your first move, changes sides, starts the game again from the start, and remembers your choice. |
| **square drill** / **drill** / **colour drill** / **square colours** | Before your first move, or between games, runs the spoken square-colour drill. After you have moved, it tells you it is too late for this game. |
| **milestones** / **progress** / **how am I doing** | Tells you how many milestones you have earned, with a short progress bar for each level, and the next two or three to aim for. **Milestones** is the most reliable word to say; "progress" is also accepted, together with "achievements" and a few common mishearings of "progress". You can say this during a game too. |
| **reset rating** | Before your first move, or between games, starts your rating again from scratch, after asking you to confirm. Your old games are kept in a dated file. Milestones you have already earned are kept. |
| **show board** / **show the board** / **board** | Between games (or before your first move), opens the last game on a board so you can step through it move by move with an analysis bar, or load a PGN file. See [Show board](#show-board-going-through-the-game). Once you have moved, it says "The board is available between games." |
| **draw** | Offers a draw. The engine accepts if it doesn't think it is better (and not in the first 20 moves). |
| **resign** | Resigns the game (it checks first). If you resign within your first five moves, the game is still saved but isn't rated: it goes into the rating log marked "unrated" and doesn't count towards your rating, level-ups or milestones. |
| **rating** / **my rating** / **what's my rating** | Tells you your current blindfold rating and how many games it is based on, for example "Your blindfold rating is 1233 from 14 games." You can say this during a game (it does not use a position request) or between games. It is not the same as **reset rating**, which starts your rating again. |

## At the end of the game

When the game ends (checkmate, stalemate, a draw, or resignation):

1. It **saves the game as a PGN file** in the `games` folder and says **"Game saved in your games folder."** The full path is printed on the screen, but not read aloud. (It doesn't show the game on screen yet, because that would give away the final position.)
2. It adds a line to your **rating log** and tells you your **blindfold performance rating** (see below).
3. It then says: **"Say review for the after-game review, or press Enter to carry on."** If you press Enter, say no, or skip, that is the end of it. If you have just earned any milestones, it tells you, for example: "New milestone: first checkmate. You've earned 9 of 22." You can also say **show board** (or another between-games command such as **square drill** or **rating**) at this question: it skips the review and does that straight away. It then says **"Enter command."** The screen shows the choices: say **yes** for another game or **no** to finish, or say **show board**, **square drill**, **milestones**, **rating**, **reset rating**, **level** 1 to 8, or **help**. If you said **"lost thread"** during the game, that move has already been noted in the file.

If you say **review**, it then:

4. Asks **at which move you first lost the thread** of the position, using what it already knows. If you said "lost thread" during the game, it checks that move with you. If not, but you tried an illegal move, it reminds you of the first one (the move number and what you said) and asks whether that was where you lost the thread. Say yes, a move number, or "never". It then asks whether you **broke any of your honesty rules** (a peek, for example), and lets you type a one-line **note**. The PGN file and the rating-log row are then updated with your answers (it does not add a second row).
5. Offers a **reconstruction test**: "Would you like to reconstruct the final position from memory, on a blank board?" If you say yes, an empty board opens in a window, the right way round for the colour you played. Put the pieces where you think they stood at the end, using the mouse just as on the set-up board (click a piece, then click squares; drag to move; right-click to remove), then click **Check my position**. Nothing about the true position is shown until you do. You get **one point for each piece of the right type and colour on its correct square**, and your score as a percentage of the pieces in the true position. It also tells you how many squares had the wrong piece, how many pieces were missing, and how many extra pieces you put on empty squares. A perfect score means every piece is in place and nothing extra has been added. After the check you can click **Show the true position** to compare: green squares are right, red ones had the wrong piece or shouldn't have had a piece, and amber ones had a piece you left out. Click **Skip** if you'd rather not. The reconstruction board needs tkinter, the same as the set-up board (on Linux, `sudo apt install python3-tk`); if it can't open, it says so and carries on.
6. Offers to **look through the game for the two or three biggest slips**. The chess engine, at full strength, spends a fraction of a second on each of your moves (a Raspberry Pi manages a ten-move game in a few seconds). For each slip it tells you the move number, what you played and what the engine preferred, roughly how much it cost, in plain words, and asks whether it was a **chess mistake** or a **visualisation mistake** (say "chess", "visualisation", "not sure", or "skip"). It also works out two plain figures for your moves: the **average centipawn loss** (a centipawn is a hundredth of a pawn; lower is better, and a single move counts for at most ten pawns, so one missed mate can't swamp the average) and **how many of your moves matched the engine's first choice**. These are not turned into a made-up "accuracy rating"; in this program the accuracy score is the reconstruction test.
7. **Shows the whole game on screen**, with everything above in the PGN headers, and gives a short **summary**: where you first lost the thread, how many illegal moves you tried and when, how many times you asked for the position and when, your reconstruction score, and your move-quality figures if the game was looked through. Any chess program can open a PGN file. Go through the game with the analysis turned on, as described in Chapter 12.
8. Offers to **read all the moves of the game aloud**. Say yes or no.

### Show board: going through the game

Between games, say **show board** (or **show the board**, or just **board**) and a window opens with the game you have just finished, at its final position, the right way round for the colour you played. The two squares of the last move are shaded light grey.

- **Start**, **Back**, **Forward** and **End** step through the game; so do the **Left** and **Right** arrow keys, with **Home** and **End** to jump to either end. You can also click any move in the list.
- The current move is shown as, for example, **12. Nf3** (or **12... Nf6** for a Black move), with "Move 23 of 41" underneath.
- **Turn board round** turns the board (and the analysis bar) round.
- **Load PGN…** opens any game from a PGN file, your own or one from a book or a database, for the same move-by-move analysis. It reads the first game in the file, starts from its set-up position if it has one (a FEN header), and shows the White and Black names and the result.
- **The analysis bar**, beside the board, shows who is better in each position as you step through: the white part is White's share and the dark grey part Black's, with White's end at White's side of the board. Underneath is the evaluation in pawns (**+0.8** means White is about eight-tenths of a pawn better; **-1.5** means Black is a pawn and a half better; **M3** means White can mate in three, **-M2** that Black can mate in two) and the engine's **best move** in that position. Stockfish spends about a quarter of a second on each position in the background, starting with the one you are looking at and then going through the rest of the game, so the buttons never wait for it; "Thinking..." shows until the figure is ready. Each position is only looked at once, so going back is instant. If Stockfish can't be started, the bar is left out and everything else works as usual.
- **Close** (or the window's close button) shuts the window and the analysis, and you're back at **"Enter command."**

If you haven't finished a game yet in this session, it opens the most recent game in your `games` folder instead, or the usual starting position if there isn't one, so **Load PGN…** can still be used. The board is never shown during a game: if you say **show board** after your first move, it says "The board is available between games." It needs tkinter, like the set-up board; if no window can be opened, the final position is printed on the screen as text instead (capital letters are White).

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
- **Too easy or too hard:** if you score more than 70 per cent over your last five rated games at the current level, it moves the engine up one level automatically (level 8 is the maximum), saves that in `settings.json`, and tells you, for example: "You scored over 70 per cent in your last five games at level 3, so I've moved the engine up to level 4." The next game starts at the new level, and the count starts again, so it will not jump twice until you have played five games at the new level. Games in which you took a move back still count. It does not move the engine down automatically: if you are scoring less than about 30 per cent against your current level, it suggests that you try moving down a level.
- **Two cautions**, shown on screen each time (not spoken): the ratings given to engine levels are rough estimates, not always comparable with human ratings, so the gauge measures your progress against the same machine rather than your exact strength; and at low levels an engine makes odd blunders that a human would not, so treat the reading as a guide, not a verdict.

**The log** is a file called `rating_log.csv` in the Different Engine folder. It opens in Excel, LibreOffice, Numbers or Google Sheets. Each game has one row: date, opponent, opponent rating, colour, time control, result (1, 0.5 or 0), first lost thread, rule breaks, notes, position requests used, how the game ended, the starting position, the name of the PGN file, then the number of illegal attempts and the moves at which they came, the moves at which you asked for the position, the reconstruction score (for example 24/28) and its percentage, the average centipawn loss, how many moves matched the engine's first choice, and the slips with your verdicts (for example "7 Nf6 visualisation"), and how many times a move was taken back. The last few are left blank if you skipped the reconstruction test or the slip review. A log made by an earlier version is brought up to date automatically the next time you finish a game: every row is kept, and so is any column you added yourself. You can add your own games to it by hand, and they will be counted too.

To see your rating without playing, use the `--rating` option (see below).

To **start your rating again**, say **reset rating** before your first move or between games, or start the program with `--reset-rating`. It asks you to confirm. On yes, it renames `rating_log.csv` to something like `rating_log_archived_2026-11-19.csv` (or `_2` if that name is already used) and starts a fresh log. Your old games are never deleted. Milestones you have already earned stay earned.

---

## Square-colour drill

This is a spoken version of the Colour flash drill in Chapter 3 of the book, and it uses the same target: thirty squares in thirty seconds. Say **square drill** (or just **drill**, **colour drill** or **square colours**) before your first move or between games, or start the program with `--drill`.

It names thirty random squares, using the spelling alphabet so the file letter is hard to mishear, for example "delta five". The square is also printed on the screen. After each one, say **light** or **dark** (or type it, in text mode). **White** and **black** are accepted too. A short click means you were correct; if you were wrong it says so, for example "No, light."

Only your thinking time is counted: the clock starts when it has finished naming the square, and stops when you start to answer. The time it takes to read the square, to play the click or to say a correction, and any delay while it works out what you said, are not included. If it has to ask again because an answer wasn't recognised, the thinking time of each attempt is added, but not the time spent on the re-prompt.

At the end it tells you your score out of 30 and your thinking time in seconds, and whether that was your best so far. Each attempt is added to a file called `drill_log.csv` in the Different Engine folder (date, score, total, seconds), which opens in any spreadsheet. A perfect 30 out of 30, a perfect score in under 90 seconds, and a perfect score in under a minute each earn a milestone. The book's Colour flash target of thirty squares in thirty seconds is still the one to aim for in the end; the milestones are steps on the way, now measured by thinking time. Older log rows from when the drill was twenty squares, or from when the clock included the computer's speech, are kept, but they do not count towards the 30-square milestones, and those older times will only look harder.

---

## Milestones and progress

The program keeps a short list of milestones, worked out automatically from your rating log and your drill log. They are grouped in four levels: **Foundations**, **First games**, **Holding the board** and **Mastery**. You don't have to tick anything yourself. A file called `milestones.json` stores the date each one was first earned. If you add games or drill results to the logs by hand, they are counted too.

After each game, and after each square-colour drill, any newly earned milestone is announced, for example: "New milestone: first checkmate. You've earned 9 of 22."

Say **milestones** (or **progress**, or start the program with `--progress`), to hear (and see) a text progress bar for each level, and the next two or three milestones to aim for:

```
Foundations [###] 3/3
First games [##---] 2/5
Holding the board [-----] 0/6
Mastery [-----] 0/8
You've earned 5 of 22 milestones.
Next up: Reach move 20 without asking for the position. Play a game with no illegal move attempts. Deliver a checkmate in a blindfold game.
```

The status line during a game also shows `Milestones 9/22`. It never shows the board or an evaluation.

If you reset your rating, milestones you have already earned are kept. A later check of the logs will only add new ones; it never takes one away.

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
| `--setup` | Asks for your colour, the engine's level, your position-request limit and the starting position before the game, as it used to do at every launch. After the first time it also asks, "Would you like the same settings again?" |
| `--quick` | Does nothing extra: a plain start already begins the game at once. Kept so that older shortcuts still work. You can add it to other options, for example `--hands-free`. |
| `--drill` | Runs the square-colour drill, then starts a game as usual. |
| `--progress` | Shows your milestones and what to aim for next, then stops. |
| `--reset-rating` | Asks you to confirm, then archives the rating log and starts a fresh one. A game then starts as usual. |

How to add an option:

- **Windows:** open the folder, click in the address bar at the top, type `cmd` and press Enter. In the black window type, for example, `Start-Windows.bat --text` and press Enter. For the full settings questions, type `Start-Windows.bat --setup`.
- **Raspberry Pi / Linux:** in the terminal, type for example `bash start-linux.sh --test-mic`, or `bash start-linux.sh --setup`.
- **Mac:** in Terminal, type `bash `, drag in start-mac.command, type a space and the option (for example ` --setup` or ` --rating`) and press Enter. You can also type the whole line: `bash start-mac.command --setup`.

If it can't find a microphone at all, it tells you and lets you play by typing instead.

## Where things are kept

Everything stays inside the Different Engine folder:

| Folder or file | What it is |
|---|---|
| `games` | Your saved games (PGN files). |
| `rating_log.csv` | Your rating log, one row per game. |
| `settings.json` | Your last settings. Delete it to go back to the usual start (White, level 2, three position requests). |
| `models` | The speech-recognition model (downloaded on first run). |
| `engine` | The Stockfish chess engine, if it had to be downloaded. |
| `.venv` | The program's private copy of the Python parts. |

## If something goes wrong

- **It keeps mishearing me.** Speak a little more slowly, keep the microphone close, and use the spelling alphabet for the letters. A headset helps a lot in a noisy room. Run the microphone test to check. You can also say **take back** to undo your last move and the engine's reply, then say the move again. For your milestones, say **milestones** rather than "progress" if the recogniser misses "progress".
- **"I couldn't find a microphone."** Plug the microphone in before starting, check it is not muted, and on a Mac allow Terminal to use the microphone (System Settings > Privacy & Security > Microphone). If you have several microphones, use `--test-mic` to see their numbers and `--mic` to choose one.
- **I can't hear it speak.** Check the volume and that the right speaker is chosen. On a Raspberry Pi or Linux, the voice comes from a program called espeak-ng, which the starter installs; you can also type `sudo apt install espeak-ng`.
- **The custom-position board doesn't open.** It then asks you to paste a FEN instead. On Linux, `sudo apt install python3-tk` adds the board window.
- **The show-board window doesn't open.** It needs a screen and tkinter too; without them it prints the final position as text instead. If the analysis bar is missing, Stockfish couldn't be started.
- **The reconstruction board doesn't open.** It needs a screen and tkinter, like the set-up board. Over SSH, or without `python3-tk` on Linux, it skips the test and carries on; the game is saved either way.
- **To start again from scratch**, delete the `.venv` folder and run the starter again. Your games and rating log are kept.

## Privacy

Speech recognition runs offline on your own machine. Your voice and your games stay with you. The internet is only used the first time, to download the free parts.

## The free parts it uses

- [Vosk](https://alphacephei.com/vosk/) offline speech recognition, with its small English model, listening only for chess words.
- [python-chess](https://python-chess.readthedocs.io/) for the rules of the game.
- [Stockfish](https://stockfishchess.org/), the open-source chess engine.
- Your computer's own voice: Windows' built-in voice (through pyttsx3), espeak-ng on Linux, and the Mac's built-in voice.
- [sounddevice](https://python-sounddevice.readthedocs.io/) for the microphone, and tkinter (part of Python) for the set-up, reconstruction and show-board windows.

### For the technically minded

The program is in the `different_engine` folder: `moves.py` (understanding spoken moves and describing moves and positions), `speech.py` (listening and speaking), `engine.py` (Stockfish levels), `ratings.py` (the rating log, formula and rating reset), `drill.py` (the square-colour drill), `milestones.py` (milestones and the progress bar), `board_editor.py` (the set-up board, and the board drawing it shares with the reconstruction test), `reconstruction.py` (the reconstruction test and its scoring), `review.py` (the slip review and the after-game summary), `replay_viewer.py` (the show-board window, its analysis bar and the text fallback), `game.py` (the loop) and `downloads.py` (first-run downloads). To run the tests: `.venv/bin/python -m pip install pytest`, then `.venv/bin/python -m pytest` (on Windows, `.venv\Scripts\python`).

## Licence

MIT Licence. Free to use, copy, modify and share. See the LICENSE file.

---

*"In the Analytical Engine I had devised mechanical means equivalent to memory, also … other means equivalent to foresight."*
Charles Babbage, *Passages from the Life of a Philosopher* (1864)
