"""Micro Chess rules: the board, how pieces move, check, checkmate and draws.

The board can have other sizes, and holes, for the other game modes (see VARIANTS).
"""

from dataclasses import dataclass

ROWS, COLS = 5, 4  # the size of the Micro Chess board
EMPTY = "--"
HOLE = "##"  # a square cut out of the board: nothing can stand on it or slide across it
PROMOTION_PIECES = ("rook", "bishop", "knight")  # what a pawn can become

KNIGHT_OFFSETS = [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]
KING_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
ROOK_DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
BISHOP_DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

# Castling squares for each side: (king from, king to, rook from, rook to).
# The king moves two squares toward its rook, which jumps to the square the king crossed.
CASTLING_SQUARES = {
    "white": ((4, 3), (4, 1), (4, 0), (4, 2)),  # King d1-b1, Rook a1-c1
    "black": ((0, 0), (0, 2), (0, 3), (0, 1)),  # King a5-c5, Rook d5-b5
}

# The letters used to write positions: uppercase for White, lowercase for Black
PIECE_LETTERS = {"k": "king", "r": "rook", "b": "bishop", "n": "knight", "p": "pawn"}
KIND_LETTERS = {kind: letter for letter, kind in PIECE_LETTERS.items()}
FILES = "abcdef"
CUSTOM_SIZES = ((4, 4), (5, 4), (5, 5))  # (rows, columns) of the boards the board editor makes


def board_from_ranks(ranks):
    """The board written as ranks of letters, top (Black's side) first: "k", "P", "." for an
    empty square and "#" for a hole. Raises ValueError for a letter it doesn't know."""
    board = []
    for rank in ranks:
        row = []
        for letter in rank:
            if letter == ".":
                row.append(EMPTY)
            elif letter == "#":
                row.append(HOLE)
            elif letter.lower() in PIECE_LETTERS:
                color = "white" if letter.isupper() else "black"
                row.append(f"{color}_{PIECE_LETTERS[letter.lower()]}")
            else:
                raise ValueError(f"Unknown letter {letter!r} on the board")
        board.append(row)
    return board


def square_letter(piece):
    """The letter for a square: "K" for White's king, "p" for Black's pawn, "." when empty, "#" for a hole"""
    if piece in (EMPTY, HOLE):
        return "." if piece == EMPTY else "#"
    color, kind = piece.split("_")
    return KIND_LETTERS[kind].upper() if color == "white" else KIND_LETTERS[kind]


def square_code(r, c, rows):
    """A square's name on a board with this many rows, e.g. "a1" """
    return f"{FILES[c]}{rows - r}"


def move_code(move, rows):
    """A move as written in a game code: its two squares, plus the promotion's letter: "c1b3", "c4c5r" """
    text = square_code(move.start_row, move.start_col, rows) + square_code(move.end_row, move.end_col, rows)
    return text + KIND_LETTERS[move.promotion_piece] if move.is_promotion else text


@dataclass(frozen=True, eq=False)
class Variant:
    """A game mode: the board's shape, the starting position and which draws apply.

    layout is the board as seen from White's side, one string per rank from the top
    (Black's side) down: uppercase letters are White's pieces, lowercase Black's,
    "." is an empty square and "#" a hole.
    """
    key: str
    name: str
    description: str
    layout: tuple
    castling: dict = None  # the CASTLING_SQUARES of the sides that may castle
    # Whether a king with a lone knight, or kings with only bishops on one color of
    # square, are draws. Each is True only if no checkmate exists with those pieces on
    # this board (holes can trap a king, so it differs from board to board).
    lone_knight_draws: bool = True
    same_color_bishops_draw: bool = True

    def start_board(self):
        return board_from_ranks(self.layout)


MICRO = Variant(
    key="micro", name="Micro", description="The classic 4x5 board",
    layout=("knbr",
            "p...",
            "....",
            "...P",
            "RBNK"),
    castling=CASTLING_SQUARES,
)
# The other boards were picked by having the AI play hundreds of games on candidate
# starting positions and keeping ones where White and Black win about equally often.
TINY = Variant(
    key="tiny", name="Tiny", description="4x4, the quickest games",
    layout=("kbrn",
            ".p..",
            "..P.",
            "NRBK"),
)
DONUT = Variant(
    key="donut", name="Donut", description="5x5 with a hole in the middle",
    layout=("rn.bk",
            "pp...",
            "..#..",
            "...PP",
            "KB.NR"),
)
PILLARS = Variant(
    key="pillars", name="Pillars", description="5x5 with two holes beside the center",
    layout=("k.nrb",
            "p...p",
            ".#.#.",
            "P...P",
            "BRN.K"),
)
VARIANTS = {variant.key: variant for variant in (MICRO, TINY, DONUT, PILLARS)}


def custom_variant(layout):
    """The game mode for a board made in the board editor (or read from a code). It has no
    castling. The can't-checkmate draws only apply when the board has no holes: on the plain
    4x4, 4x5 and 5x5 boards no such mate exists, but a hole can make one possible."""
    plain = not any("#" in rank for rank in layout)
    return Variant(key="custom", name="Custom", description=f"{len(layout[0])}x{len(layout)} board",
                   layout=tuple(layout), lone_knight_draws=plain, same_color_bishops_draw=plain)


class GameState:
    def __init__(self, board=None, white_to_move=True, variant=MICRO):
        """Start a new game, or set up a custom position by passing a board.

        In a custom position a side may castle if its king and rook are on their starting squares.
        """
        self.variant = variant
        if board is None:
            board = variant.start_board()
        self.board = [row[:] for row in board]
        self.rows, self.cols = len(self.board), len(self.board[0])
        self.white_to_move = white_to_move
        self.white_king_location = self.find_piece("white_king")
        self.black_king_location = self.find_piece("black_king")
        # The colors that may still castle, and the rights before each move (for undo_move)
        self.castling_squares = variant.castling or {}
        self.castling_rights = frozenset(
            color for color, (king_from, _, rook_from, _) in self.castling_squares.items()
            if self.board[king_from[0]][king_from[1]] == f"{color}_king"
            and self.board[rook_from[0]][rook_from[1]] == f"{color}_rook"
        )
        self.castling_rights_log = []
        # Every position reached so far, used to spot threefold repetition
        self.position_history = [self.position_key()]

    def position_key(self):
        """A snapshot of the position: where every piece is, whose turn it is and who may castle"""
        return tuple(tuple(row) for row in self.board), self.white_to_move, self.castling_rights

    def to_code(self):
        """The position as a line of text: the board's name, the ranks from the top down
        (letters as in the Variant layouts), the side to move and who may castle.
        For example "micro knbr/p.../..../...P/RBNK w WB"."""
        ranks = "/".join("".join(square_letter(piece) for piece in row) for row in self.board)
        castling = ("W" if "white" in self.castling_rights else "") + ("B" if "black" in self.castling_rights else "")
        return f"{self.variant.key} {ranks} {'w' if self.white_to_move else 'b'} {castling or '-'}"

    @classmethod
    def from_code(cls, code):
        """The position a code describes (see to_code). Raises ValueError saying what's wrong
        with a code that doesn't describe a position that can be played."""
        parts = code.split()
        if len(parts) != 4:
            raise ValueError("A position code has four parts: board, ranks, side to move and castling")
        key, ranks, side, castling = parts
        ranks = ranks.split("/")
        if len({len(rank) for rank in ranks}) != 1:
            raise ValueError("Every rank needs the same number of squares")
        board = board_from_ranks(ranks)
        holes = [[square == HOLE for square in row] for row in board]
        if key == "custom":
            if (len(ranks), len(ranks[0])) not in CUSTOM_SIZES:
                raise ValueError("Custom boards are 4x4, 4x5 or 5x5")
            variant = custom_variant(ranks)
        elif key in VARIANTS:
            variant = VARIANTS[key]
            if holes != [[square == HOLE for square in row] for row in variant.start_board()]:
                raise ValueError(f"That isn't the shape of the {variant.name} board")
        else:
            raise ValueError(f"Unknown board {key!r}")
        if side not in ("w", "b"):
            raise ValueError("The side to move is w or b")
        if castling not in ("-", "W", "B", "WB"):
            raise ValueError("Castling is WB, W, B or -")

        game = cls(board, side == "w", variant)
        problem = game.position_problem()
        if problem:
            raise ValueError(problem)
        rights = frozenset(color for color, letter in (("white", "W"), ("black", "B")) if letter in castling)
        if not rights <= game.castling_rights:
            raise ValueError("A side can't castle once its king or rook has left its corner")
        game.castling_rights = rights
        game.position_history = [game.position_key()]
        return game

    def position_problem(self):
        """Why this position can't be played, or None if it can: each side needs exactly one
        king, a pawn can't stand on the rank where it would promote, and the side that has
        just moved can't be in check"""
        for color in ("white", "black"):
            if sum(row.count(f"{color}_king") for row in self.board) != 1:
                return f"{color.title()} needs exactly one king"
        if "white_pawn" in self.board[0] or "black_pawn" in self.board[-1]:
            return "A pawn can't stand on the last rank, where it would promote"
        if self.is_king_attacked(white=not self.white_to_move):
            waiting, moving = ("Black", "White") if self.white_to_move else ("White", "Black")
            return f"{waiting} is in check, but it's {moving}'s move"
        return None

    def move_from_code(self, text):
        """The legal move a game code writes as text (e.g. "c1b3" or "c4c5r"); ValueError if there's none"""
        for move in self.get_valid_moves():
            if move_code(move, self.rows) == text:
                return move
        raise ValueError(f"{text} isn't a legal move there")

    def find_piece(self, piece):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] == piece:
                    return (r, c)
        return None

    def get_valid_moves(self):
        """Return all legal moves for the side to move.

        A move is only legal if it doesn't leave the mover's own king in check.
        """
        moves = []
        for move in self.get_all_possible_moves():
            self.make_move(move)
            # make_move switched the turn, so check the king of the side that just moved
            if not self.is_king_attacked(white=not self.white_to_move):
                moves.append(move)
            self.undo_move(move)
        return moves

    def get_game_result(self):
        """Return None while the game is still going, otherwise how it ended:

        "checkmate"             - the side to move is in check and has no legal moves (it lost)
        "stalemate"             - the side to move is not in check but has no legal moves (draw)
        "repetition"            - the same position has appeared three times (draw)
        "insufficient_material" - neither side has the pieces left to checkmate (draw)
        """
        if not self.get_valid_moves():
            return "checkmate" if self.in_check() else "stalemate"
        if self.is_threefold_repetition():
            return "repetition"
        if self.is_insufficient_material():
            return "insufficient_material"
        return None

    def is_threefold_repetition(self):
        """True if the current position (same pieces, same player to move) has occurred 3 times"""
        return self.position_history.count(self.position_history[-1]) >= 3

    def is_insufficient_material(self):
        """True if neither side has the pieces to checkmate, however the game goes on.

        That's when the kings are left with at most one knight, or with only bishops
        that all stand on squares of the same color (a bishop never changes color),
        on boards where no checkmate exists with those pieces (see Variant).
        """
        knights = 0
        bishop_colors = set()
        for r, row in enumerate(self.board):
            for c, piece in enumerate(row):
                if piece in (EMPTY, HOLE) or piece.endswith("king"):
                    continue
                if piece.endswith("knight"):
                    knights += 1
                elif piece.endswith("bishop"):
                    bishop_colors.add((r + c) % 2)
                else:
                    return False  # a pawn or a rook can still lead to checkmate
        if knights:
            return knights == 1 and not bishop_colors and self.variant.lone_knight_draws
        return not bishop_colors or (len(bishop_colors) == 1 and self.variant.same_color_bishops_draw)

    def get_all_possible_moves(self):
        """Moves that follow how each piece moves, without checking if the king is left in check."""
        moves = []
        for r in range(len(self.board)):
            for c in range(len(self.board[r])):
                piece = self.board[r][c]
                if piece != "--" and \
                   ((piece.startswith("white") and self.white_to_move) or
                    (piece.startswith("black") and not self.white_to_move)):

                    if piece.endswith("pawn"):
                        self.get_pawn_moves(r, c, moves)
                    elif piece.endswith("knight"):
                        self.get_knight_moves(r, c, moves)
                    elif piece.endswith("rook"):
                        self.get_rook_moves(r, c, moves)
                    elif piece.endswith("bishop"):
                        self.get_bishop_moves(r, c, moves)
                    elif piece.endswith("king"):
                        self.get_king_moves(r, c, moves)
                        self.get_castle_moves(r, c, moves)
        return moves

    def on_board(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_pawn_moves(self, r, c, moves):
        direction = -1 if self.white_to_move else 1
        promotion_row = 0 if self.white_to_move else self.rows - 1

        targets = []

        # Forward move
        if self.on_board(r + direction, c) and self.board[r + direction][c] == "--":
            targets.append((r + direction, c))

        # Capture moves
        for dc in [-1, 1]:
            nr, nc = r + direction, c + dc
            if self.on_board(nr, nc):
                target = self.board[nr][nc]
                if target != "--" and target.startswith("white" if not self.white_to_move else "black"):
                    targets.append((nr, nc))

        for nr, nc in targets:
            if nr == promotion_row:
                # Promotion: there's no queen in Micro Chess, so the pawn can
                # become a rook, bishop or knight (one move for each choice)
                for piece in PROMOTION_PIECES:
                    moves.append(Move((r, c), (nr, nc), self.board, promotion_piece=piece))
            else:
                moves.append(Move((r, c), (nr, nc), self.board))

    def get_knight_moves(self, r, c, moves):
        """Knights jump, so pieces and holes in between don't matter"""
        self.get_step_moves(r, c, KNIGHT_OFFSETS, moves)

    def get_step_moves(self, r, c, offsets, moves):
        """Knight and king: one jump or step to an empty square or an enemy piece"""
        ally = "white" if self.white_to_move else "black"
        for dr, dc in offsets:
            nr, nc = r + dr, c + dc
            if self.on_board(nr, nc):
                target = self.board[nr][nc]
                if target != HOLE and not target.startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))

    def get_rook_moves(self, r, c, moves):
        self.get_sliding_moves(r, c, ROOK_DIRECTIONS, moves)

    def get_bishop_moves(self, r, c, moves):
        self.get_sliding_moves(r, c, BISHOP_DIRECTIONS, moves)

    def get_sliding_moves(self, r, c, directions, moves):
        """Rook and bishop: slide in each direction until hitting the edge, a hole or a piece."""
        enemy = "black" if self.white_to_move else "white"
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while self.on_board(nr, nc):
                if self.board[nr][nc] == "--":
                    moves.append(Move((r, c), (nr, nc), self.board))
                elif self.board[nr][nc].startswith(enemy):
                    moves.append(Move((r, c), (nr, nc), self.board))
                    break
                else:
                    break  # our own piece, or a hole
                nr += dr
                nc += dc

    def get_king_moves(self, r, c, moves):
        self.get_step_moves(r, c, KING_OFFSETS, moves)

    def get_castle_moves(self, r, c, moves):
        """Castling: allowed only if neither the king nor its rook has moved (and the rook
        wasn't captured), the squares between them are empty, and the king isn't in check
        and doesn't pass through or land on an attacked square.
        """
        color = "white" if self.white_to_move else "black"
        if color not in self.castling_rights:
            return
        king_from, king_to, rook_from, rook_to = self.castling_squares[color]
        if (r, c) != king_from:
            return
        row = king_from[0]
        between = range(min(king_from[1], rook_from[1]) + 1, max(king_from[1], rook_from[1]))
        if any(self.board[row][col] != EMPTY for col in between):
            return
        # The king starts on king_from, crosses rook_to and lands on king_to
        enemy_is_white = not self.white_to_move
        if any(self.is_square_attacked(sq_r, sq_c, by_white=enemy_is_white)
               for sq_r, sq_c in (king_from, rook_to, king_to)):
            return
        moves.append(Move(king_from, king_to, self.board, is_castle=True))

    def in_check(self):
        """Check if the current player's king is in check"""
        return self.is_king_attacked(white=self.white_to_move)

    def is_king_attacked(self, white):
        """Check if White's king (white=True) or Black's king (white=False) is attacked"""
        r, c = self.white_king_location if white else self.black_king_location
        return self.is_square_attacked(r, c, by_white=not white)

    def piece_at(self, r, c):
        """The piece on a square, or None if the square is off the board"""
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.board[r][c]
        return None

    def is_square_attacked(self, r, c, by_white):
        """Check if any White (by_white=True) or Black piece attacks square (r, c).

        Instead of trying every enemy piece, we look outwards from the square:
        e.g. if an enemy knight sits a knight's jump away, the square is attacked.
        """
        enemy = "white" if by_white else "black"

        # Pawns capture diagonally forward, so an attacking White pawn sits one row below
        pawn_row = r + 1 if by_white else r - 1
        for dc in (-1, 1):
            if self.piece_at(pawn_row, c + dc) == enemy + "_pawn":
                return True

        for dr, dc in KNIGHT_OFFSETS:
            if self.piece_at(r + dr, c + dc) == enemy + "_knight":
                return True

        for dr, dc in KING_OFFSETS:
            if self.piece_at(r + dr, c + dc) == enemy + "_king":
                return True

        # Rooks and bishops: walk along each line until we hit a piece or a hole
        for directions, slider in ((ROOK_DIRECTIONS, "_rook"), (BISHOP_DIRECTIONS, "_bishop")):
            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                while 0 <= nr < self.rows and 0 <= nc < self.cols:
                    piece = self.board[nr][nc]
                    if piece != EMPTY:
                        if piece == enemy + slider:
                            return True
                        break
                    nr += dr
                    nc += dc

        return False

    def make_move(self, move):
        self.board[move.start_row][move.start_col] = "--"

        # Handle pawn promotion
        if move.is_promotion:
            color = "white" if move.piece_moved.startswith("white") else "black"
            self.board[move.end_row][move.end_col] = f"{color}_{move.promotion_piece}"
        else:
            self.board[move.end_row][move.end_col] = move.piece_moved

        # Castling: the rook jumps over to the square the king crossed
        if move.is_castle:
            color = move.piece_moved.split("_")[0]
            _, _, (rook_r, rook_c), (to_r, to_c) = self.castling_squares[color]
            self.board[rook_r][rook_c] = EMPTY
            self.board[to_r][to_c] = f"{color}_rook"

        # Update king positions
        if move.piece_moved == "white_king":
            self.white_king_location = (move.end_row, move.end_col)
        elif move.piece_moved == "black_king":
            self.black_king_location = (move.end_row, move.end_col)

        # A side can no longer castle once a move starts or ends on its king's or rook's
        # starting square: that piece has moved or been captured
        self.castling_rights_log.append(self.castling_rights)
        if self.castling_rights:
            touched = {(move.start_row, move.start_col), (move.end_row, move.end_col)}
            self.castling_rights = frozenset(
                color for color in self.castling_rights
                if not touched & {self.castling_squares[color][0], self.castling_squares[color][2]}
            )

        self.white_to_move = not self.white_to_move
        self.position_history.append(self.position_key())

    def undo_move(self, move):
        """Undo a move - needed for minimax algorithm"""
        self.board[move.start_row][move.start_col] = move.piece_moved
        self.board[move.end_row][move.end_col] = move.piece_captured

        # Put a castled rook back in its corner
        if move.is_castle:
            color = move.piece_moved.split("_")[0]
            _, _, (rook_r, rook_c), (to_r, to_c) = self.castling_squares[color]
            self.board[to_r][to_c] = EMPTY
            self.board[rook_r][rook_c] = f"{color}_rook"

        # Update king positions
        if move.piece_moved == "white_king":
            self.white_king_location = (move.start_row, move.start_col)
        elif move.piece_moved == "black_king":
            self.black_king_location = (move.start_row, move.start_col)

        self.castling_rights = self.castling_rights_log.pop()
        self.white_to_move = not self.white_to_move
        self.position_history.pop()


class Move:
    def __init__(self, start_sq, end_sq, board, promotion_piece=None, is_castle=False):
        self.start_row, self.start_col = start_sq
        self.end_row, self.end_col = end_sq
        self.piece_moved = board[self.start_row][self.start_col]
        self.piece_captured = board[self.end_row][self.end_col]
        self.promotion_piece = promotion_piece  # "rook", "bishop", "knight" or None
        self.is_promotion = promotion_piece is not None
        self.is_castle = is_castle  # the king's two-square move; make_move moves the rook too

    def __eq__(self, other):
        if not isinstance(other, Move):
            return NotImplemented  # so a move never equals None or anything else
        return (self.start_row, self.start_col, self.end_row, self.end_col, self.promotion_piece) == \
               (other.start_row, other.start_col, other.end_row, other.end_col, other.promotion_piece)
 


def read_game_code(code):
    """(start position, moves played) from a game code: a position code followed by the
    moves, e.g. "micro knbr/p.../..../...P/RBNK w WB c1b3 a5b4". Raises ValueError if
    the code is wrong or a move isn't legal."""
    parts = code.split()
    start, game = GameState.from_code(" ".join(parts[:4])), GameState.from_code(" ".join(parts[:4]))
    moves = []
    for text in parts[4:]:
        move = game.move_from_code(text)
        game.make_move(move)
        moves.append(move)
    return start, moves


def write_game_code(start, moves):
    """The game code for the moves played from a start position"""
    return " ".join([start.to_code()] + [move_code(move, start.rows) for move in moves])
