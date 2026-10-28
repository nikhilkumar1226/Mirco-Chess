import random

from chess_engine import GameState, get_ai_move
from helpers import position, square, find_move


def destinations(moves, start):
    """All squares (as names like 'b2') a piece on `start` can move to."""
    sr, sc = square(start)
    return {"abcd"[m.end_col] + str(5 - m.end_row) for m in moves if (m.start_row, m.start_col) == (sr, sc)}


def test_start_position_has_11_legal_moves():
    # Pawn d2-d3, rook a2/a3/xa4, bishop a2/c2/d3, knight a2/b3/d3, king c2
    assert len(GameState().get_valid_moves()) == 11


def test_king_cannot_move_into_check():
    # The black rook on d5 controls the whole d-file, so Kc1 can't go to d1 or d2
    gs = position({"a5": "black_king", "d5": "black_rook", "c1": "white_king"})
    assert destinations(gs.get_valid_moves(), "c1") == {"b1", "b2", "c2"}


def test_pinned_piece_cannot_move():
    # The knight on d2 shields its king from the rook on d5, so it can't move at all
    gs = position({"a5": "black_king", "d5": "black_rook", "d2": "white_knight", "d1": "white_king"})
    assert destinations(gs.get_valid_moves(), "d2") == set()


def test_must_get_out_of_check():
    # White is in check from the rook on d5: every legal move must deal with it
    gs = position({"a5": "black_king", "d5": "black_rook", "d1": "white_king", "b3": "white_bishop"})
    assert gs.in_check()
    for move in gs.get_valid_moves():
        gs.make_move(move)
        assert not gs.is_king_attacked(white=True)
        gs.undo_move(move)


def test_game_is_not_over_at_the_start():
    assert GameState().get_game_result() is None


def test_checkmate_is_detected():
    # Rook d5 checks along rank 5, the white king on b3 covers a4 and b4
    gs = position({"a5": "black_king", "d5": "white_rook", "b3": "white_king"}, white_to_move=False)
    assert gs.get_valid_moves() == []
    assert gs.get_game_result() == "checkmate"


def test_stalemate_is_detected():
    # Black is not in check but every king move is attacked
    gs = position({"a5": "black_king", "b3": "white_king", "d3": "white_bishop"}, white_to_move=False)
    assert not gs.in_check()
    assert gs.get_valid_moves() == []
    assert gs.get_game_result() == "stalemate"


def test_ai_does_not_walk_into_check_when_stalemated():
    gs = position({"a5": "black_king", "b3": "white_king", "d3": "white_bishop"}, white_to_move=False)
    assert get_ai_move(gs) is None
    assert gs.get_game_result() == "stalemate"


def test_random_games_never_leave_a_king_in_check():
    rng = random.Random(0)
    for _ in range(100):
        gs = GameState()
        for _ in range(60):
            moves = gs.get_valid_moves()
            if not moves:
                break
            gs.make_move(rng.choice(moves))
            # The side that just moved must never have its king attacked
            assert not gs.is_king_attacked(white=not gs.white_to_move)
            assert gs.white_king_location and gs.black_king_location


def test_undo_restores_position():
    gs = GameState()
    before = [row[:] for row in gs.board]
    move = find_move(gs.get_valid_moves(), "a1", "a4")[0]  # rook captures the pawn
    gs.make_move(move)
    gs.undo_move(move)
    assert gs.board == before and gs.white_to_move
