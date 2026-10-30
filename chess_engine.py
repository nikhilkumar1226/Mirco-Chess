"""Micro Chess rules: the board, how pieces move, check, checkmate and draws."""

ROWS, COLS = 5, 4
EMPTY = "--"
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


class GameState:
    def __init__(self, board=None, white_to_move=True):
        """Start a new game, or set up a custom position by passing a board.

        In a custom position a side may castle if its king and rook are on their starting squares.
        """
        if board is None:
            board = [
                ["black_king", "black_knight", "black_bishop", "black_rook"],
                ["black_pawn", "--", "--", "--"],
                ["--", "--", "--", "--"],
                ["--", "--", "--", "white_pawn"],
                ["white_rook", "white_bishop", "white_knight", "white_king"]
            ]
        self.board = [row[:] for row in board]
        self.white_to_move = white_to_move
        self.white_king_location = self.find_piece("white_king")
        self.black_king_location = self.find_piece("black_king")
        # The colors that may still castle, and the rights before each move (for undo_move)
        self.castling_rights = frozenset(
            color for color, (king_from, _, rook_from, _) in CASTLING_SQUARES.items()
            if self.board[king_from[0]][king_from[1]] == f"{color}_king"
            and self.board[rook_from[0]][rook_from[1]] == f"{color}_rook"
        )
        self.castling_rights_log = []
        # Every position reached so far, used to spot threefold repetition
        self.position_history = [self.position_key()]

    def position_key(self):
        """A snapshot of the position: where every piece is, whose turn it is and who may castle"""
        return tuple(tuple(row) for row in self.board), self.white_to_move, self.castling_rights

    def find_piece(self, piece):
        for r in range(ROWS):
            for c in range(COLS):
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
        "insufficient_material" - only the two kings are left (draw)
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
        """True if only the two kings are left on the board"""
        return all(piece == EMPTY or piece.endswith("king") for row in self.board for piece in row)

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

    def get_pawn_moves(self, r, c, moves):
        direction = -1 if self.white_to_move else 1
        promotion_row = 0 if self.white_to_move else 4

        targets = []

        # Forward move
        if 0 <= r + direction < 5 and self.board[r + direction][c] == "--":
            targets.append((r + direction, c))

        # Capture moves
        for dc in [-1, 1]:
            nr, nc = r + direction, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
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
        ally = "white" if self.white_to_move else "black"
        for dr, dc in KNIGHT_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--" or not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))

    def get_rook_moves(self, r, c, moves):
        self.get_sliding_moves(r, c, ROOK_DIRECTIONS, moves)

    def get_bishop_moves(self, r, c, moves):
        self.get_sliding_moves(r, c, BISHOP_DIRECTIONS, moves)

    def get_sliding_moves(self, r, c, directions, moves):
        """Rook and bishop: slide in each direction until hitting the edge or a piece."""
        ally = "white" if self.white_to_move else "black"
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--":
                    moves.append(Move((r, c), (nr, nc), self.board))
                elif not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))
                    break
                else:
                    break
                nr += dr
                nc += dc

    def get_king_moves(self, r, c, moves):
        ally = "white" if self.white_to_move else "black"
        for dr, dc in KING_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--" or not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))

    def get_castle_moves(self, r, c, moves):
        """Castling: allowed only if neither the king nor its rook has moved (and the rook
        wasn't captured), the squares between them are empty, and the king isn't in check
        and doesn't pass through or land on an attacked square.
        """
        color = "white" if self.white_to_move else "black"
        if color not in self.castling_rights:
            return
        king_from, king_to, rook_from, rook_to = CASTLING_SQUARES[color]
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
        if 0 <= r < ROWS and 0 <= c < COLS:
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

        # Rooks and bishops: walk along each line until we hit a piece
        for directions, slider in ((ROOK_DIRECTIONS, "_rook"), (BISHOP_DIRECTIONS, "_bishop")):
            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                while 0 <= nr < ROWS and 0 <= nc < COLS:
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
            _, _, (rook_r, rook_c), (to_r, to_c) = CASTLING_SQUARES[color]
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
                if not touched & {CASTLING_SQUARES[color][0], CASTLING_SQUARES[color][2]}
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
            _, _, (rook_r, rook_c), (to_r, to_c) = CASTLING_SQUARES[color]
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
        return (self.start_row, self.start_col, self.end_row, self.end_col, self.promotion_piece) == \
               (other.start_row, other.start_col, other.end_row, other.end_col, other.promotion_piece)
