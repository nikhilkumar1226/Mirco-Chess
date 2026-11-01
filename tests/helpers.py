from chess_engine import GameState, ROWS, EMPTY, HOLE, MICRO

FILES = "abcdef"


def position(pieces, white_to_move=True, variant=MICRO):
    """Build a GameState from a dict like {"a5": "black_king", "b3": "white_king"}.

    The board has the variant's shape (and holes) but only the pieces given.
    """
    board = [[EMPTY if square != HOLE else HOLE for square in row] for row in variant.start_board()]
    for name, piece in pieces.items():
        r, c = square(name, len(board))
        board[r][c] = piece
    return GameState(board=board, white_to_move=white_to_move, variant=variant)


def square(name, rows=ROWS):
    """'b3' -> (row, col)"""
    return rows - int(name[1]), FILES.index(name[0])


def find_move(moves, start, end, rows=ROWS):
    """Find the move from square name `start` to `end` (e.g. "d2", "d3") in a list of moves."""
    (sr, sc), (er, ec) = square(start, rows), square(end, rows)
    return [m for m in moves if (m.start_row, m.start_col, m.end_row, m.end_col) == (sr, sc, er, ec)]
