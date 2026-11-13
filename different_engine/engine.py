"""The chess engine (Stockfish) at a strength the player chooses.

Levels 1 to 3 use Stockfish's "Skill Level" with a shallow search, because its
UCI_Elo setting does not go below about 1320.  Levels 4 to 8 use UCI_Elo.
The ratings are rough estimates, as the book warns: use them to measure your
progress against the same machine, not as an exact human rating.
"""

import chess
import chess.engine

# level: (estimated rating, engine options, search limit)
LEVELS = {
    1: (800, {"Skill Level": 0}, chess.engine.Limit(depth=1)),
    2: (1000, {"Skill Level": 0}, chess.engine.Limit(depth=3, time=0.2)),
    3: (1200, {"Skill Level": 3}, chess.engine.Limit(depth=5, time=0.3)),
    4: (1400, {"UCI_LimitStrength": True, "UCI_Elo": 1400}, chess.engine.Limit(time=0.5)),
    5: (1600, {"UCI_LimitStrength": True, "UCI_Elo": 1600}, chess.engine.Limit(time=0.5)),
    6: (1800, {"UCI_LimitStrength": True, "UCI_Elo": 1800}, chess.engine.Limit(time=0.7)),
    7: (2000, {"UCI_LimitStrength": True, "UCI_Elo": 2000}, chess.engine.Limit(time=1.0)),
    8: (2300, {"UCI_LimitStrength": True, "UCI_Elo": 2300}, chess.engine.Limit(time=1.0)),
}


def level_rating(level):
    return LEVELS[level][0]


def level_name(level):
    return f"Level {level} (about {level_rating(level)})"


class Engine:
    """A thin wrapper round python-chess's Stockfish connection."""

    def __init__(self, path, level):
        self.level = level
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(path)
        except (OSError, chess.engine.EngineError) as exc:
            raise RuntimeError(f"The Stockfish chess engine at {path} would not start. ({exc})") from exc
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
