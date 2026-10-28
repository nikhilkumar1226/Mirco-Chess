from chess_engine import GameState, ROWS, COLS, EMPTY

FILES = "abcd"


def position(pieces, white_to_move=True):
    """Build a GameState from a dict like {"a5": "black_king", "b3": "white_king"}."""
    board = [[EMPTY] * COLS for _ in range(ROWS)]
    for square, piece in pieces.items():
        board[ROWS - int(square[1])][FILES.index(square[0])] = piece
    return GameState(board=board, white_to_move=white_to_move)


def square(name):
    """'b3' -> (row, col)"""
    return ROWS - int(name[1]), FILES.index(name[0])


def find_move(moves, start, end):
    """Find the move from square name `start` to `end` (e.g. "d2", "d3") in a list of moves."""
    (sr, sc), (er, ec) = square(start), square(end)
    return [m for m in moves if (m.start_row, m.start_col, m.end_row, m.end_col) == (sr, sc, er, ec)]
