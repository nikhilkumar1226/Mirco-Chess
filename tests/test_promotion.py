from helpers import position, square
from main import find_legal_moves


def test_human_pawn_promotes_in_terminal_game():
    # This is the path main.py uses for the human's move
    gs = position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"})
    move = find_legal_moves(gs, square("c4"), square("c5"))[0]
    gs.make_move(move)
    assert gs.board[0][2] != "white_pawn"
    assert gs.board[0][2].startswith("white_")


def test_illegal_move_finds_nothing():
    gs = position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"})
    assert find_legal_moves(gs, square("c4"), square("c3")) == []
