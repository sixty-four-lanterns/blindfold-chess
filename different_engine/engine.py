"""The chess engine (Stockfish) at a strength the player chooses.

Levels 1 to 3 use Stockfish's "Skill Level" with a shallow search, because its
UCI_Elo setting does not go below about 1320.  Levels 4 to 8 use UCI_Elo.

Below level 1 there are two beginner levels, Beginner 1 (about 400) and
Beginner 2 (about 600).  Stockfish cannot be made any weaker than level 1, so
at these levels the program itself sometimes plays a random legal move instead
of Stockfish's choice: 60 per cent of the time at Beginner 1 and 30 per cent
at Beginner 2.  The rest of the time it plays exactly like level 1, so it still
takes free pieces and finds a mate in one now and then, but it also leaves
pieces hanging and misses captures, as a beginner does.  Internally the
beginner levels are numbered -1 and 0, so that "one level up" is simply +1
and levels 1 to 8 (and every game already in the rating log) keep their
meaning.
The ratings are rough estimates, as the book warns: use them to measure your
progress against the same machine, not as an exact human rating.
"""

import random

import chess
import chess.engine

# level: (estimated rating, engine options, search limit)
LEVELS = {
    -1: (400, {"Skill Level": 0}, chess.engine.Limit(depth=1)),     # Beginner 1
    0: (600, {"Skill Level": 0}, chess.engine.Limit(depth=1)),      # Beginner 2
    1: (800, {"Skill Level": 0}, chess.engine.Limit(depth=1)),
    2: (1000, {"Skill Level": 0}, chess.engine.Limit(depth=3, time=0.2)),
    3: (1200, {"Skill Level": 3}, chess.engine.Limit(depth=5, time=0.3)),
    4: (1400, {"UCI_LimitStrength": True, "UCI_Elo": 1400}, chess.engine.Limit(time=0.5)),
    5: (1600, {"UCI_LimitStrength": True, "UCI_Elo": 1600}, chess.engine.Limit(time=0.5)),
    6: (1800, {"UCI_LimitStrength": True, "UCI_Elo": 1800}, chess.engine.Limit(time=0.7)),
    7: (2000, {"UCI_LimitStrength": True, "UCI_Elo": 2000}, chess.engine.Limit(time=1.0)),
    8: (2300, {"UCI_LimitStrength": True, "UCI_Elo": 2300}, chess.engine.Limit(time=1.0)),
}


MIN_LEVEL, MAX_LEVEL = min(LEVELS), max(LEVELS)

# How often a beginner level plays a random legal move instead of Stockfish's.
RANDOM_MOVE_RATE = {-1: 0.60, 0: 0.30}
# A random king move (other than castling) is chosen less often, so the
# beginner levels do not simply walk the king about.
KING_MOVE_WEIGHT = 0.3


def is_beginner(level):
    return level in RANDOM_MOVE_RATE


def level_rating(level):
    return LEVELS[level][0]


def level_label(level):
    """'level 3', or 'beginner 1' / 'beginner 2' for the two levels below level 1."""
    if is_beginner(level):
        return f"beginner {level + 2}"
    return f"level {level}"


def level_title(level):
    """'Level 3' or 'Beginner 1', for the start of a sentence or the status line."""
    label = level_label(level)
    return label[0].upper() + label[1:]


def level_slug(level):
    """For file names: 'level3' or 'beginner1'."""
    return level_label(level).replace(" ", "")


def level_name(level):
    return f"{level_title(level)} (about {level_rating(level)})"


def random_move(board, rng=random):
    """A random legal move, with plain king moves less likely."""
    moves = list(board.legal_moves)
    if not moves:
        return None
    weights = [KING_MOVE_WEIGHT if board.piece_type_at(m.from_square) == chess.KING
               and not board.is_castling(m) else 1.0 for m in moves]
    return rng.choices(moves, weights=weights, k=1)[0]


def beginner_choice(board, level, engine_move, rng=random):
    """The move a beginner level plays: sometimes random, otherwise `engine_move()`.

    `engine_move` is called only when the engine's choice is used.
    """
    rate = RANDOM_MOVE_RATE.get(level, 0.0)
    if rate and rng.random() < rate:
        move = random_move(board, rng)
        if move is not None:
            return move
    return engine_move()


class Engine:
    """A thin wrapper round python-chess's Stockfish connection."""

    def __init__(self, path, level, rng=None):
        self.level = level
        self.rng = rng or random.Random()
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(path)
        except (OSError, chess.engine.EngineError) as exc:
            raise RuntimeError(f"The Stockfish chess engine at {path} would not start. ({exc})") from exc
        _, options, self.limit = LEVELS[level]
        self.engine.configure(self._fit(options))

    def set_level(self, level):
        """Retarget an already-started engine to another level."""
        self.level = level
        _, options, self.limit = LEVELS[level]
        self.engine.configure(self._fit(options))

    def _fit(self, options):
        """Keep each setting within what this version of Stockfish accepts."""
        fitted = {}
        for name, value in options.items():
            if name not in self.engine.options:
                continue
            opt = self.engine.options[name]
            if isinstance(value, int) and not isinstance(value, bool) and opt.min is not None:
                value = max(opt.min, min(opt.max, value))
            fitted[name] = value
        return fitted

    def choose_move(self, board):
        if is_beginner(self.level):
            return beginner_choice(board, self.level,
                                   lambda: self.engine.play(board, self.limit).move, self.rng)
        return self.engine.play(board, self.limit).move

    def accepts_draw(self, board, engine_colour):
        """Accept a draw offer only if the engine thinks it is not better."""
        try:
            info = self.engine.analyse(board, chess.engine.Limit(time=0.3))
            score = info["score"].pov(engine_colour).score(mate_score=10000)
        except chess.engine.EngineError:
            return False
        return score is not None and score <= 30

    def close(self):
        try:
            self.engine.quit()
        except Exception:
            pass
