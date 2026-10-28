from ai import get_ai_move
from helpers import position, square, find_move
from main import find_legal_moves


def test_pawn_can_promote_to_rook_bishop_or_knight():
    gs = position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"})
    choices = find_move(gs.get_valid_moves(), "c4", "c5")
    assert sorted(m.promotion_piece for m in choices) == ["bishop", "knight", "rook"]

    for move in choices:
        gs.make_move(move)
        assert gs.board[0][2] == "white_" + move.promotion_piece
        gs.undo_move(move)
        assert gs.board[1][2] == "white_pawn" and gs.board[0][2] == "--"


def test_promotion_by_capture_and_for_black():
    # Black pawn on b2 can capture on a1 or c1, or push to b1: 3 squares x 3 pieces
    gs = position({"d5": "black_king", "b2": "black_pawn", "a1": "white_rook",
                   "c1": "white_knight", "d3": "white_king"}, white_to_move=False)
    pawn_moves = [m for m in gs.get_valid_moves() if m.piece_moved == "black_pawn"]
    assert len(pawn_moves) == 9 and all(m.is_promotion for m in pawn_moves)


def test_human_pawn_promotes_in_terminal_game():
    # This is the path main.py uses for the human's move
    gs = position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"})
    legal = find_legal_moves(gs, square("c4"), square("c5"))
    assert len(legal) == 3
    move = next(m for m in legal if m.promotion_piece == "bishop")
    gs.make_move(move)
    assert gs.board[0][2] == "white_bishop"


def test_illegal_move_finds_nothing():
    gs = position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"})
    assert find_legal_moves(gs, square("c4"), square("c3")) == []


def test_ai_chooses_the_promotion_that_mates():
    # b2-b1 as a rook is checkmate; as a bishop or knight it isn't even check
    gs = position({"c3": "black_king", "b2": "black_pawn", "d1": "white_king"}, white_to_move=False)
    move = get_ai_move(gs, depth=2)
    assert (move.start_row, move.start_col, move.end_row, move.end_col) == (3, 1, 4, 1)
    assert move.promotion_piece == "rook"
