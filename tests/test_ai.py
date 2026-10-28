import random
import time

import pytest

from ai import get_ai_move, DIFFICULTY_DEPTHS
from chess_engine import GameState
from helpers import position, square


def is_move(move, start, end):
    return ((move.start_row, move.start_col), (move.end_row, move.end_col)) == (square(start), square(end))


def test_ai_can_play_white():
    gs = GameState()
    move = get_ai_move(gs, "easy")
    assert move.piece_moved.startswith("white")


def test_ai_as_white_finds_mate_in_one():
    # c4-c5 promoting to a rook is checkmate (the white king covers a4 and b4)
    gs = position({"a5": "black_king", "c4": "white_pawn", "b3": "white_king"})
    move = get_ai_move(gs, depth=2)
    assert is_move(move, "c4", "c5") and move.promotion_piece == "rook"


def test_ai_as_black_finds_mate_in_one():
    # Ra4-a1 is checkmate: the black king on c3 covers c2 and d2
    gs = position({"c3": "black_king", "a4": "black_rook", "d1": "white_king"}, white_to_move=False)
    move = get_ai_move(gs, depth=2)
    assert is_move(move, "a4", "a1")


@pytest.mark.parametrize("difficulty", list(DIFFICULTY_DEPTHS))
def test_every_difficulty_returns_a_legal_move(difficulty):
    gs = GameState()
    assert get_ai_move(gs, difficulty) in gs.get_valid_moves()


def test_unknown_difficulty_is_rejected():
    with pytest.raises(ValueError):
        get_ai_move(GameState(), "impossible")


def test_hard_is_quick_enough():
    gs = GameState()
    start = time.perf_counter()
    get_ai_move(gs, "hard")
    assert time.perf_counter() - start < 2.0


def test_ai_prefers_the_fastest_mate():
    # Ra4-a1 mates at once. A waiting move like Ra4-a2 also forces mate one move
    # later, so if every mate scored the same the AI would sometimes dawdle.
    gs = position({"c3": "black_king", "a4": "black_rook", "d1": "white_king"}, white_to_move=False)
    for seed in range(20):
        move = get_ai_move(gs, depth=4, rng=random.Random(seed))
        assert is_move(move, "a4", "a1")


def test_ai_varies_between_equally_good_moves():
    # Nothing can be captured here, so all of White's moves score the same
    gs = position({"a5": "black_king", "d1": "white_king", "a2": "white_pawn"})
    chosen = set()
    for seed in range(30):
        move = get_ai_move(gs, depth=2, rng=random.Random(seed))
        chosen.add((move.start_row, move.start_col, move.end_row, move.end_col))
    assert len(chosen) > 1


def test_same_seed_gives_same_move():
    a = get_ai_move(GameState(), "medium", rng=random.Random(7))
    b = get_ai_move(GameState(), "medium", rng=random.Random(7))
    assert a == b
