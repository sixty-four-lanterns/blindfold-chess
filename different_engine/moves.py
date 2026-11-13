"""Understanding spoken moves, and putting moves and positions into words.

This module has no sound in it at all: it works on plain text, so it can be
tested on any computer.  The rule throughout is the one in Chapter 13: if the
words could mean more than one move, or no legal move, we never guess - we say
so and ask the player to repeat.
"""

import re
from dataclasses import dataclass
from typing import Optional

import chess

PIECE_WORDS = {
    "king": chess.KING, "queen": chess.QUEEN, "rook": chess.ROOK,
    "bishop": chess.BISHOP, "knight": chess.KNIGHT, "pawn": chess.PAWN,
}
PIECE_NAMES = {v: k for k, v in PIECE_WORDS.items()}

# Words a person (or the speech recogniser) might use, mapped to one form.
SYNONYMS = {
    # pieces
    "night": "knight", "nite": "knight", "knights": "knight", "horse": "knight",
    "rock": "rook", "rooks": "rook", "bishops": "bishop", "queens": "queen",
    "kings": "king", "pawns": "pawn", "prawn": "pawn", "porn": "pawn",
    # capturing
    "takes": "x", "take": "x", "captures": "x", "capture": "x", "takes on": "x",
    # files: the NATO spelling alphabet, and letters written as they sound
    "alpha": "a", "alfa": "a", "bravo": "b", "charlie": "c", "delta": "d",
    "echo": "e", "foxtrot": "f", "golf": "g", "hotel": "h",
    "bee": "b", "be": "b", "see": "c", "sea": "c", "dee": "d", "eff": "f",
    "gee": "g", "aitch": "h",
    # ranks: number words and their sound-alikes
    "one": "1", "won": "1", "two": "2", "too": "2", "three": "3", "tree": "3",
    "four": "4", "for": "4", "fore": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "ate": "8",
    # castling
    "castle": "castles", "castling": "castles", "castled": "castles",
    "short": "kingside", "long": "queenside",
    # promotion
    "promotes": "promote", "promoting": "promote", "promotion": "promote",
    "equals": "promote", "becomes": "promote", "promoted": "promote",
}

# Words that carry no meaning for the move itself.
FILLER = {
    "on", "the", "um", "uh", "er", "please", "move", "my", "i", "play",
    "and", "then", "check", "checkmate", "mate", "en", "passant", "in",
    "passing", "ep", "square", "piece", "goes", "go", "moves", "with",
    "to", "of", "an",
}

COMMANDS = {
    "repeat": "repeat", "again": "repeat", "position": "position",
    "resign": "resign", "draw": "draw", "help": "help",
    "rating": "rating", "log": "rating", "quit": "quit",
    # "lost thread", "lost the thread", "I've lost the thread"
    "lost": "lost thread", "thread": "lost thread",
}

FILES = "abcdefgh"
RANKS = "12345678"


@dataclass
class ParseResult:
    """What we made of the player's words."""
    kind: str                         # "move", "command" or "problem"
    move: Optional[chess.Move] = None
    command: Optional[str] = None
    message: str = ""                 # what to tell the player if kind == "problem"
    illegal: bool = False             # a clearly named move that isn't legal (not a mishearing)


def is_illegal_attempt(result):
    """True if the player clearly named a move (a piece and a square, or notation)
    that isn't legal.  Mishearings, half-heard moves and moves that could mean
    more than one thing are not counted: those are the machine's problem, not
    a slip of the player's mental board."""
    return result.kind == "problem" and result.illegal


def normalise(text):
    """Turn raw words into a list of simple tokens.

    "Knight from golf one to foxtrot three" -> ["knight", "from", "g1", "f3"]
    Lone letters and digits stay separate, e.g. "e takes d5" -> ["e", "x", "d5"].
    """
    text = text.lower().strip()
    text = re.sub(r"\b(o-o-o|0-0-0)\b", " castles queenside ", text)
    text = re.sub(r"\b(o-o|0-0)\b", " castles kingside ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\bking\s+side\b", "kingside", text)
    text = re.sub(r"\bqueen\s+side\b", "queenside", text)
    text = re.sub(r"\bking's\s+side\b", "kingside", text)

    raw = []
    for word in text.split():
        # split glued squares such as "f3" or "g1f3" into letters and digits
        if re.fullmatch(r"([a-h][1-8])+", word):
            raw.extend(word)
        else:
            raw.append(SYNONYMS.get(word, word))

    tokens = []
    for i, word in enumerate(raw):
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        prev = raw[i - 1] if i > 0 else ""
        # "promotes to a queen": here "a" is an article, not the a-file
        if word == "a" and nxt in PIECE_WORDS and prev in ("to", "promote"):
            continue
        if word in FILLER:
            continue
        tokens.append(word)

    # join a file letter followed by a rank digit into a square
    joined = []
    i = 0
    while i < len(tokens):
        if (tokens[i] in FILES and len(tokens[i]) == 1 and i + 1 < len(tokens)
                and tokens[i + 1] in RANKS and len(tokens[i + 1]) == 1):
            joined.append(tokens[i] + tokens[i + 1])
            i += 2
        else:
            joined.append(tokens[i])
            i += 1
    return joined


def _is_square(tok):
    return len(tok) == 2 and tok[0] in FILES and tok[1] in RANKS


def _try_notation(board, text):
    """Accept typed chess notation (Nf3, exd5, O-O, e7e8q) in text mode."""
    t = text.strip()
    if " " in t or not re.fullmatch(r"[KQRBNOa-h0-8x=+#\-]+", t):
        return None
    try:
        return ParseResult("move", move=board.parse_san(t))
    except chess.AmbiguousMoveError:
        return ParseResult("problem", message="That could mean more than one move. "
                                              "Please say which piece, for example 'knight from b1 to d2'.")
    except chess.IllegalMoveError:
        # Typed piece moves such as "Nf6" aren't understood word by word, so say so here.
        # (Pawn moves and castling get a fuller message further on.)
        if t[0] in "KQRBN":
            return ParseResult("problem", illegal=True,
                               message=f"{t} isn't a legal move here. Please say your move again.")
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(t.lower())
        if move in board.legal_moves:
            return ParseResult("move", move=move)
    except ValueError:
        pass
    return None


def parse(board, text):
    """Work out what the player said: a legal move, a command, or a problem."""
    if not text or not text.strip():
        return ParseResult("problem", message="I didn't hear anything. Please say your move again.")

    tokens = normalise(text)
    squares = [t for t in tokens if _is_square(t)]

    # Commands such as "repeat" or "position" (only when no square was said)
    if not squares:
        for tok in tokens:
            if tok in COMMANDS:
                return ParseResult("command", command=COMMANDS[tok])

    notation = _try_notation(board, text)
    if notation:
        return notation

    if "castles" in tokens or (not squares and ("kingside" in tokens or "queenside" in tokens)):
        return _parse_castling(board, tokens)

    if not squares:
        if any(t in PIECE_WORDS for t in tokens):
            return ParseResult("problem", message="I heard the piece but not the square. Please say the whole move again.")
        return ParseResult("problem", message="Sorry, I didn't catch a move. Please say it again.")

    target = chess.parse_square(squares[-1])
    target_index = len(tokens) - 1 - tokens[::-1].index(squares[-1])
    from_sq = chess.parse_square(squares[-2]) if len(squares) >= 2 else None

    before, after = tokens[:target_index], tokens[target_index + 1:]
    piece = next((PIECE_WORDS[t] for t in before if t in PIECE_WORDS), None)
    promo = next((PIECE_WORDS[t] for t in after if t in PIECE_WORDS), None)
    if promo is None and "promote" in before:     # "promote to queen on e8" is unusual, but allowed
        later = before[before.index("promote") + 1:]
        promo = next((PIECE_WORDS[t] for t in later if t in PIECE_WORDS), None)
        if promo is not None and piece == promo:
            piece = None
    from_file = next((FILES.index(t) for t in before if len(t) == 1 and t in FILES), None)
    from_rank = next((RANKS.index(t) for t in before if len(t) == 1 and t in RANKS), None)
    capture = "x" in tokens

    moves = [m for m in board.legal_moves if m.to_square == target]
    if from_sq is not None:
        moves = [m for m in moves if m.from_square == from_sq]
    if piece is not None:
        moves = [m for m in moves if board.piece_type_at(m.from_square) == piece]
    elif from_sq is None:
        # No piece named: as in written notation, that means a pawn.
        moves = [m for m in moves if board.piece_type_at(m.from_square) == chess.PAWN]
    if from_file is not None:
        moves = [m for m in moves if chess.square_file(m.from_square) == from_file]
    if from_rank is not None:
        moves = [m for m in moves if chess.square_rank(m.from_square) == from_rank]
    if capture:
        moves = [m for m in moves if board.is_capture(m)]

    if any(m.promotion for m in moves):
        if promo is None:
            return ParseResult("problem", message="Which piece would you like to promote to? "
                                                  "Please say the move again with the piece, for example 'pawn to "
                                                  f"{squares[-1]}, queen'.")
        moves = [m for m in moves if m.promotion == promo]

    square_name = squares[-1]
    if len(moves) == 1:
        return ParseResult("move", move=moves[0])
    if len(moves) > 1:
        name = PIECE_NAMES[board.piece_type_at(moves[0].from_square)]
        example = f"{name} from {chess.square_name(moves[0].from_square)} to {square_name}"
        return ParseResult("problem", message=f"More than one {name} can go to {square_name}. "
                                              f"Please say which one, for example '{example}'.")
    # nothing fits
    if piece is not None:
        what = "take on" if capture else "go to"
        return ParseResult("problem", illegal=True,
                           message=f"No {PIECE_NAMES[piece]} of yours can {what} {square_name}. "
                                   "Please say your move again.")
    if from_sq is not None:
        return ParseResult("problem", illegal=True,
                           message=f"That isn't a legal move from {squares[-2]} to {square_name}. "
                                   "Please say your move again.")
    # A square on its own means a pawn move, as in written notation.
    return ParseResult("problem", illegal=True,
                       message=f"No pawn can go to {square_name}. If you meant another piece, "
                               "please name it, for example 'knight " + square_name + "'.")


def _parse_castling(board, tokens):
    castles = [m for m in board.legal_moves if board.is_castling(m)]
    if "queenside" in tokens or "queen" in tokens:
        wanted, side = [m for m in castles if board.is_queenside_castling(m)], "queenside"
    elif "kingside" in tokens or "king" in tokens:
        wanted, side = [m for m in castles if board.is_kingside_castling(m)], "kingside"
    else:
        if len(castles) == 1:
            return ParseResult("move", move=castles[0])
        if not castles:
            return ParseResult("problem", illegal=True,
                               message="You can't castle at the moment. Please say another move.")
        return ParseResult("problem", message="Kingside or queenside? Please say 'castles kingside' or 'castles queenside'.")
    if wanted:
        return ParseResult("move", move=wanted[0])
    return ParseResult("problem", illegal=True,
                       message=f"You can't castle {side} at the moment. Please say another move.")


# ---------------------------------------------------------------------------
# Putting moves and positions into words
# ---------------------------------------------------------------------------

def describe_move(board, move):
    """Describe a move in words, before it is played: "Bishop takes e5, check"."""
    if board.is_castling(move):
        text = "Castles kingside" if board.is_kingside_castling(move) else "Castles queenside"
    else:
        piece = board.piece_type_at(move.from_square)
        to = chess.square_name(move.to_square)
        frm = chess.square_name(move.from_square)
        capture = board.is_capture(move)
        if piece == chess.PAWN:
            if capture:
                # name the file if two pawns could capture on the same square
                rivals = [m for m in board.legal_moves if m.to_square == move.to_square
                          and board.piece_type_at(m.from_square) == chess.PAWN and m.from_square != move.from_square
                          and board.is_capture(m)]
                text = (f"{frm[0]}-pawn takes {to}" if rivals else f"Pawn takes {to}")
                if board.is_en_passant(move):
                    text += ", en passant"
            else:
                text = f"Pawn to {to}"
            if move.promotion:
                text += f", promotes to a {PIECE_NAMES[move.promotion]}"
        else:
            name = PIECE_NAMES[piece].capitalize()
            san = board.san(move)
            # SAN adds a file/rank/square when two identical pieces could move there
            needs_from = len(re.sub(r"[x+#=QRBN]", "", san[1:])) > 2
            verb = "takes" if capture else "to"
            text = f"{name} from {frm} {verb} {to}" if needs_from else f"{name} {verb} {to}"
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        text += ", checkmate"
    elif after.is_check():
        text += ", check"
    return text[0].upper() + text[1:]


def describe_position(board):
    """Read the position in the Chapter 12 order: king, queen, rooks, bishops,
    knights, then pawns from the a-file to the h-file, White first."""
    parts = []
    for colour, colour_name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        groups = []
        for piece in (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            squares = sorted(board.pieces(piece, colour), key=lambda s: (chess.square_file(s), chess.square_rank(s)))
            if not squares:
                continue
            names = [chess.square_name(s) for s in squares]
            label = PIECE_NAMES[piece].capitalize() + ("s" if len(names) > 1 else "")
            listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            groups.append(f"{label} {listed}")
        parts.append(f"{colour_name}: " + ". ".join(groups) + ".")
    turn = "White" if board.turn == chess.WHITE else "Black"
    return " ".join(parts) + f" {turn} to move."


LETTER_SOUNDS = {"a": "ay", "b": "bee", "c": "see", "d": "dee", "e": "ee", "f": "eff", "g": "gee", "h": "aitch"}


def for_speech(text):
    """Make squares easy for a synthetic voice: "f3" -> "eff 3", "e-pawn" -> "ee pawn"."""
    text = re.sub(r"\b([a-h])([1-8])\b", lambda m: f"{LETTER_SOUNDS[m.group(1)]} {m.group(2)}", text)
    text = re.sub(r"\b([a-hA-H])-pawn\b", lambda m: f"{LETTER_SOUNDS[m.group(1).lower()]} pawn", text)
    return text


def describe_game(start_board, moves):
    """Every move of a game in words, one line per move number."""
    board = start_board.copy(stack=False)
    lines = []
    for move in moves:
        number, words = board.fullmove_number, describe_move(board, move)
        if board.turn == chess.WHITE:
            lines.append(f"Move {number}. White: {words}.")
        elif lines and lines[-1].startswith(f"Move {number}. White"):
            lines[-1] += f" Black: {words}."
        else:
            lines.append(f"Move {number}. Black: {words}.")
        board.push(move)
    return lines


NUMBER_WORDS = {
    "zero": 0, "nought": 0, "one": 1, "won": 1, "two": 2, "too": 2, "three": 3, "four": 4, "for": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "ate": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}


def parse_number(text):
    """Find a whole number in typed or spoken text: "12", "twenty three" -> 23.
    Returns None if there is no number."""
    digits = re.search(r"\d+", text or "")
    if digits:
        return int(digits.group())
    total, found = 0, False
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        if word in NUMBER_WORDS:
            total += NUMBER_WORDS[word]
            found = True
        elif word == "hundred" and found:
            total *= 100
    return total if found else None


SMALL_NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten", "eleven", "twelve"]


def number_word(n):
    """Small counts as words, for speaking: 2 -> "two"; larger ones stay as figures."""
    return SMALL_NUMBERS[n] if 0 <= n < len(SMALL_NUMBERS) else str(n)


def join_words(items):
    """["a", "b", "c"] -> "a, b and c"."""
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def vocabulary():
    """Every word the speech recogniser should listen for."""
    words = set(PIECE_WORDS) | set(COMMANDS) | {
        "takes", "captures", "to", "from", "castles", "castle", "kingside", "queenside",
        "king", "queen", "side", "short", "long", "promote", "promotes", "equals", "check",
        "on", "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
        "a", "b", "c", "d", "e", "f", "g", "h", "one", "two", "three", "four", "five",
        "six", "seven", "eight", "nine", "ten", "zero", "yes", "no", "white", "black",
        "random", "level", "unlimited", "usual", "custom", "never", "stop", "change",
        "keep", "en", "passant", "offer", "please", "again", "say", "the",
        "chess", "visualisation", "visualization", "not", "sure", "skip",
    } | set(NUMBER_WORDS) - {"won", "too", "for", "ate", "nought"}
    return sorted(words)
