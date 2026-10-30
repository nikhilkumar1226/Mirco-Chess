import random

import pytest

from ai import get_ai_move
from chess_engine import GameState
from helpers import position, square, find_move
from main import find_legal_moves


def castles(gs):
    return [m for m in gs.get_valid_moves() if m.is_castle]


def play(gs, *moves):
    """Play moves given as "d1 d2" strings."""
    for text in moves:
        start, end = text.split()
        gs.make_move(find_move(gs.get_valid_moves(), start, end)[0])


def both_can_castle(white_to_move=True):
    """Kings and rooks on their starting squares; the pawns block the a- and d-files."""
    return position({"a5": "black_king", "a4": "black_pawn", "d5": "black_rook",
                     "a1": "white_rook", "d2": "white_pawn", "d1": "white_king"}, white_to_move)


def white_can_castle(**extra):
    """White king d1 and rook a1 with nothing in the way, plus any extra pieces."""
    return position({"d5": "black_king", "a1": "white_rook", "d1": "white_king", **extra})


def test_white_castles():
    gs = white_can_castle()
    move = find_move(gs.get_valid_moves(), "d1", "b1")[0]
    assert move.is_castle
    gs.make_move(move)
    assert gs.board[4] == ["--", "white_king", "white_rook", "--"]
    assert gs.white_king_location == square("b1")
    assert "white" not in gs.castling_rights


def test_black_castles():
    gs = position({"a5": "black_king", "d5": "black_rook", "a1": "white_king"}, white_to_move=False)
    move = find_move(gs.get_valid_moves(), "a5", "c5")[0]
    assert move.is_castle
    gs.make_move(move)
    assert gs.board[0] == ["--", "black_rook", "black_king", "--"]
    assert gs.black_king_location == square("c5")
    assert "black" not in gs.castling_rights


def test_castling_in_the_starting_position_needs_b1_and_c1_cleared():
    gs = GameState()
    assert gs.castling_rights == {"white", "black"}
    assert castles(gs) == []
    play(gs, "c1 a2", "b5 d4", "b1 c2", "c5 b4")
    assert len(castles(gs)) == 1


def test_castling_is_typed_as_the_kings_move_in_the_terminal_game():
    gs = white_can_castle()
    legal = find_legal_moves(gs, square("d1"), square("b1"))
    assert len(legal) == 1 and legal[0].is_castle


@pytest.mark.parametrize("blocker", [
    {"b1": "white_bishop"},
    {"c1": "white_knight"},
    {"b1": "black_knight"},
])
def test_no_castling_through_pieces(blocker):
    assert castles(white_can_castle(**blocker)) == []


def test_no_castling_out_of_check():
    gs = white_can_castle(d4="black_rook")
    assert gs.in_check()
    assert castles(gs) == []


def test_no_castling_through_an_attacked_square():
    # The rook on c4 covers c1, the square the king crosses
    assert castles(white_can_castle(c4="black_rook")) == []


def test_no_castling_into_check():
    # The rook on b4 covers b1, where the king would land
    gs = white_can_castle(b4="black_rook")
    assert castles(gs) == []
    assert not [m for m in gs.get_all_possible_moves() if m.is_castle]


def test_moving_the_king_loses_castling_rights():
    gs = white_can_castle()
    play(gs, "d1 d2")
    assert "white" not in gs.castling_rights
    play(gs, "d5 c5", "d2 d1", "c5 d5")
    assert castles(gs) == []


def test_moving_the_rook_loses_castling_rights():
    gs = white_can_castle()
    play(gs, "a1 a2", "d5 c5", "a2 a1", "c5 d5")
    assert "white" not in gs.castling_rights
    assert castles(gs) == []


def test_capturing_the_rook_loses_castling_rights():
    # The knight takes the rook on a1; the other rook comes back to a1, but castling is gone
    gs = position({"d5": "black_king", "b3": "black_knight", "a3": "white_rook",
                   "a1": "white_rook", "d1": "white_king"}, white_to_move=False)
    play(gs, "b3 a1")
    assert "white" not in gs.castling_rights
    play(gs, "a3 a1", "d5 c5")
    assert castles(gs) == []


def test_black_loses_rights_but_white_keeps_them():
    gs = both_can_castle(white_to_move=False)
    play(gs, "d5 c5")
    assert gs.castling_rights == {"white"}


def test_undo_restores_everything():
    gs = both_can_castle()
    board = [row[:] for row in gs.board]
    key, history = gs.position_key(), gs.position_history[:]

    castle = find_move(gs.get_valid_moves(), "d1", "b1")[0]
    gs.make_move(castle)
    reply = find_move(gs.get_valid_moves(), "a5", "b5")[0]  # Black's king moves too
    gs.make_move(reply)
    assert gs.castling_rights == frozenset()

    gs.undo_move(reply)
    gs.undo_move(castle)
    assert gs.board == board
    assert gs.white_king_location == square("d1") and gs.black_king_location == square("a5")
    assert gs.castling_rights == {"white", "black"}
    assert gs.position_key() == key and gs.position_history == history
    assert gs.white_to_move


def test_castling_rights_are_part_of_the_position():
    # After the king steps out and back the board looks the same, but it's a different
    # position because White can no longer castle
    gs = white_can_castle()
    start_key = gs.position_key()
    play(gs, "d1 c1", "d5 c5", "c1 d1", "c5 d5")
    assert gs.position_key()[0] == start_key[0]
    assert gs.position_key() != start_key


def test_ai_search_finds_castling_and_leaves_the_game_untouched():
    gs = both_can_castle()
    assert any(m.is_castle for m in gs.get_all_possible_moves())
    board, key = [row[:] for row in gs.board], gs.position_key()
    assert get_ai_move(gs, depth=4) in gs.get_valid_moves()
    assert gs.board == board and gs.position_key() == key


def test_random_games_undo_back_to_the_start():
    rng = random.Random(1)
    castled = 0
    for _ in range(100):
        gs = GameState()
        start = gs.position_key()
        played = []
        for _ in range(40):
            moves = gs.get_valid_moves()
            if not moves:
                break
            # Random moves rarely castle, so castle whenever it's allowed
            castle_moves = [m for m in moves if m.is_castle]
            move = castle_moves[0] if castle_moves else rng.choice(moves)
            castled += move.is_castle
            gs.make_move(move)
            played.append(move)
        for move in reversed(played):
            gs.undo_move(move)
        assert gs.position_key() == start and gs.castling_rights_log == []
        assert gs.white_king_location == square("d1") and gs.black_king_location == square("a5")
    assert castled > 0
