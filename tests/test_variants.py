"""The game modes: other board sizes, and boards with holes."""

import itertools
import random
import time

import pytest

from ai import get_ai_move, evaluate_board, DIFFICULTY_DEPTHS
from chess_engine import GameState, VARIANTS, TINY, DONUT, PILLARS, EMPTY, HOLE
from helpers import position, find_move
from play_terminal import parse_move, print_board

ALL_VARIANTS = list(VARIANTS.values())


def destinations(gs, start):
    """Names of the squares the piece on `start` can move to"""
    return {"abcde"[m.end_col] + str(gs.rows - m.end_row) for m in gs.get_valid_moves()
            if "abcde"[m.start_col] + str(gs.rows - m.start_row) == start}


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=lambda v: v.key)
def test_every_start_is_a_fair_legal_position(variant):
    gs = GameState(variant=variant)
    assert not gs.in_check() and not gs.is_king_attacked(white=False)
    assert gs.get_game_result() is None
    # Black's pieces are White's turned around, so neither side starts with an edge
    turned = [[piece.replace("white", "BLACK").replace("black", "white").replace("BLACK", "black")
               for piece in reversed(row)] for row in reversed(gs.board)]
    assert turned == gs.board
    assert evaluate_board(gs) == 0


@pytest.mark.parametrize("variant, size", [(TINY, (4, 4)), (DONUT, (5, 5)), (PILLARS, (5, 5))],
                         ids=lambda v: getattr(v, "key", ""))
def test_board_sizes_and_holes(variant, size):
    gs = GameState(variant=variant)
    assert (gs.rows, gs.cols) == size
    holes = {(r, c) for r in range(gs.rows) for c in range(gs.cols) if gs.board[r][c] == HOLE}
    assert holes == {"tiny": set(), "donut": {(2, 2)}, "pillars": {(2, 1), (2, 3)}}[variant.key]


def test_nothing_can_land_on_a_hole():
    # The hole on c3 is next to the king and a knight's jump from the knight
    gs = position({"c2": "white_king", "a2": "white_knight", "a5": "black_king"}, variant=DONUT)
    assert "c3" not in destinations(gs, "c2")
    assert "c3" not in destinations(gs, "a2")


def test_rooks_and_bishops_cannot_slide_across_a_hole():
    gs = position({"c1": "white_rook", "a1": "white_bishop", "e1": "white_king", "a5": "black_king"},
                  variant=DONUT)
    assert destinations(gs, "c1") >= {"c2", "b1", "d1"} and not destinations(gs, "c1") & {"c3", "c4", "c5"}
    assert "b2" in destinations(gs, "a1") and not destinations(gs, "a1") & {"c3", "d4", "e5"}


def test_holes_block_attacks_on_the_king():
    # The rook on c5 would give check down the c-file, but the hole on c3 is in the way
    gs = position({"c1": "white_king", "c5": "black_rook", "a5": "black_king"}, variant=DONUT)
    assert not gs.in_check()
    assert "c2" in destinations(gs, "c1")


def test_knights_jump_over_holes():
    # From b2 the knight jumps past the hole on b3 to a4 and c4; d3 is a hole itself
    gs = position({"b2": "white_knight", "e1": "white_king", "a5": "black_king"}, variant=PILLARS)
    assert destinations(gs, "b2") == {"a4", "c4", "d1"}


def test_a_pawn_is_stuck_behind_a_hole():
    gs = position({"c2": "white_pawn", "e1": "white_king", "a5": "black_king"}, variant=DONUT)
    assert destinations(gs, "c2") == set()


def test_pawns_promote_on_the_last_rank_of_any_board():
    gs = position({"b3": "white_pawn", "d1": "white_king", "d4": "black_king"}, variant=TINY)
    promotions = find_move(gs.get_valid_moves(), "b3", "b4", rows=4)
    assert {m.promotion_piece for m in promotions} == {"rook", "bishop", "knight"}


def test_only_micro_has_castling():
    for variant in (TINY, DONUT, PILLARS):
        gs = GameState(variant=variant)
        assert gs.castling_rights == frozenset()


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=lambda v: v.key)
@pytest.mark.parametrize("piece", ["white_knight", "white_bishop"])
def test_a_lone_knight_or_bishop_can_never_checkmate(variant, piece):
    # The draw rule says these can't win, so try every placement of the two kings and the
    # piece, with either side to move (a hole beside a king could have made a mate possible)
    assert variant.lone_knight_draws and variant.same_color_bishops_draw
    empty = [[HOLE if square == HOLE else EMPTY for square in row] for row in variant.start_board()]
    squares = [(r, c) for r, row in enumerate(empty) for c, square in enumerate(row) if square == EMPTY]
    for placement in itertools.permutations(squares, 3):
        board = [row[:] for row in empty]
        for (r, c), name in zip(placement, ["white_king", "black_king", piece]):
            board[r][c] = name
        for white_to_move in (True, False):
            gs = GameState(board, white_to_move, variant=variant)
            if gs.is_king_attacked(white=not white_to_move):
                continue  # impossible: the side that just moved left its king in check
            assert not (gs.in_check() and not gs.get_valid_moves())


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=lambda v: v.key)
def test_random_games_stay_legal_and_undo_back_to_the_start(variant):
    rng = random.Random(3)
    for _ in range(20):
        gs = GameState(variant=variant)
        start = gs.position_key()
        played = []
        for _ in range(60):
            moves = gs.get_valid_moves()
            if not moves:
                break
            move = rng.choice(moves)
            assert gs.board[move.end_row][move.end_col] != HOLE
            gs.make_move(move)
            assert not gs.is_king_attacked(white=not gs.white_to_move)
            played.append(move)
        for move in reversed(played):
            gs.undo_move(move)
        assert gs.position_key() == start


@pytest.mark.parametrize("variant", ALL_VARIANTS, ids=lambda v: v.key)
@pytest.mark.parametrize("difficulty", list(DIFFICULTY_DEPTHS))
def test_the_ai_plays_every_board(variant, difficulty):
    gs = GameState(variant=variant)
    start = time.perf_counter()
    move = get_ai_move(gs, difficulty, rng=random.Random(1))
    assert move in gs.get_valid_moves()
    assert time.perf_counter() - start < 2.0


def test_the_ai_finds_a_mate_that_needs_a_hole():
    # Re2-a2 is mate only because the king's one escape square, b3, is a hole
    gs = position({"c5": "white_king", "e2": "white_rook", "a4": "black_king"}, variant=PILLARS)
    move = get_ai_move(gs, depth=2)
    assert find_move([move], "e2", "a2")
    gs.make_move(move)
    assert gs.get_game_result() == "checkmate"


def test_terminal_version_reads_and_prints_bigger_boards(capsys):
    assert parse_move("e5 a1", rows=5, cols=5) == ((0, 4), (4, 0))
    assert parse_move("e2 e3") == (None, None)  # no e-file on the 4x5 board
    assert parse_move("a5 a4", rows=4, cols=4) == (None, None)  # no 5th rank on the 4x4 board
    print_board(GameState(variant=PILLARS).board)
    assert "3 |. # . # . |" in capsys.readouterr().out
