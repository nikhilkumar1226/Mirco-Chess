import random
import time

import pytest

import ai
from ai import (get_ai_move, search_move, evaluate_board, minimax_alpha_beta, quiescence, Search,
                DIFFICULTY_DEPTHS, DIFFICULTY_MARGINS, MATE_SCORE)
from chess_engine import GameState, MICRO, DONUT
from helpers import position, square, find_move


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


def exact_score(gs, move, depth):
    """The move's score from a search without any pruning window"""
    gs.make_move(move)
    score = minimax_alpha_beta(gs, depth - 1, float("-inf"), float("inf"), gs.white_to_move)
    gs.undo_move(move)
    return score


def test_easy_picks_varied_moves_within_its_margin():
    gs = GameState()
    scores = [(move, exact_score(gs, move, DIFFICULTY_DEPTHS["easy"])) for move in gs.get_valid_moves()]
    best = max(score for _, score in scores)
    allowed = [move for move, score in scores if best - score <= DIFFICULTY_MARGINS["easy"]]
    chosen = [get_ai_move(gs, "easy", rng=random.Random(seed)) for seed in range(30)]
    assert all(move in allowed for move in chosen)
    assert len({(m.start_row, m.start_col, m.end_row, m.end_col) for m in chosen}) > 1


@pytest.mark.parametrize("pieces, white_to_move, mate", [
    ({"a5": "black_king", "c4": "white_pawn", "b3": "white_king"}, True, ("c4", "c5")),
    ({"c3": "black_king", "a4": "black_rook", "d1": "white_king"}, False, ("a4", "a1")),
])
def test_easy_never_misses_a_mate_in_one(pieces, white_to_move, mate):
    gs = position(pieces, white_to_move)
    for seed in range(20):
        move = get_ai_move(gs, "easy", rng=random.Random(seed))
        assert is_move(move, *mate) and move.promotion_piece in (None, "rook")


def grab_the_defended_pawn():
    """White to move: Ra1xa4 wins a pawn, but the knight on c5 takes the rook back"""
    return position({"d1": "white_king", "a1": "white_rook", "b2": "white_pawn", "d5": "black_king",
                     "a4": "black_pawn", "c4": "black_pawn", "c5": "black_knight"})


def test_quiescence_sees_the_recapture():
    gs = grab_the_defended_pawn()
    gs.make_move(find_move(gs.get_valid_moves(), "a1", "a4")[0])
    assert evaluate_board(gs) > 100  # judged as it stands, White is a pawn up...
    assert quiescence(gs, float("-inf"), float("inf"), False, 2) < -100  # ...but not after Nxa4


def test_even_a_one_move_search_does_not_grab_a_defended_pawn():
    move = get_ai_move(grab_the_defended_pawn(), depth=1)
    assert not is_move(move, "a1", "a4")


def test_quiescence_spots_checkmate():
    # White is mated (Ra1 with the black king on c3 covering c2 and d2)
    gs = position({"c3": "black_king", "a1": "black_rook", "d1": "white_king"})
    assert quiescence(gs, float("-inf"), float("inf"), True, 1) == -(MATE_SCORE - 1)


def test_quiescence_scores_are_whole_numbers():
    rng = random.Random(8)
    for _ in range(30):
        gs = GameState()
        for _ in range(rng.randrange(0, 16)):
            moves = gs.get_valid_moves()
            if not moves:
                break
            gs.make_move(rng.choice(moves))
        assert isinstance(quiescence(gs, float("-inf"), float("inf"), gs.white_to_move, 1), int)


def full_window_score(gs, depth, search):
    return minimax_alpha_beta(gs, depth, float("-inf"), float("inf"), gs.white_to_move, search=search)


def test_the_transposition_table_gives_the_same_scores_with_less_work():
    rng = random.Random(4)
    with_table_nodes = without_table_nodes = 0
    for variant in (MICRO, DONUT):
        gs = GameState(variant=variant)
        for _ in range(6):  # a few moves into a game
            gs.make_move(rng.choice(gs.get_valid_moves()))
        for move in gs.get_valid_moves():
            gs.make_move(move)
            with_table, without_table = Search(), Search(use_table=False)
            assert full_window_score(gs, 4, with_table) == full_window_score(gs, 4, without_table)
            gs.undo_move(move)
            with_table_nodes += with_table.nodes
            without_table_nodes += without_table.nodes
    assert with_table_nodes < without_table_nodes


def test_the_ai_picks_the_same_move_without_the_table(monkeypatch):
    with_table = get_ai_move(GameState(), depth=4, rng=random.Random(3))
    monkeypatch.setattr(ai, "Search", lambda: Search(use_table=False))
    assert get_ai_move(GameState(), depth=4, rng=random.Random(3)) == with_table


def test_mate_scores_stay_right_when_stored_in_the_table():
    # The same mate is stored at one distance from the root and read back at another
    for ply in (1, 4, 9):
        score = MATE_SCORE - 7
        assert ai.from_table(ai.to_table(score, ply), ply) == score
        assert ai.from_table(ai.to_table(-score, ply), ply) == -score
    assert ai.to_table(MATE_SCORE - 7, 3) == MATE_SCORE - 4  # mate 4 plies after this position
    assert ai.to_table(250, 3) == 250  # ordinary scores are stored as they are


def test_a_depth_means_one_exact_repeatable_search():
    first = search_move(GameState(), depth=4, rng=random.Random(2))
    again = search_move(GameState(), depth=4, rng=random.Random(2))
    assert first.depth == again.depth == 4
    assert (first.move, first.score, first.nodes) == (again.move, again.score, again.nodes)


def test_each_level_searches_down_to_its_depth():
    for difficulty in ("easy", "medium", "hard"):
        result = search_move(GameState(), difficulty, rng=random.Random(1))
        assert result.depth == DIFFICULTY_DEPTHS[difficulty]


def test_the_ai_stops_when_its_time_is_up(monkeypatch):
    # Hard with hardly any time and no depth limit still answers, and quickly
    monkeypatch.setitem(ai.DIFFICULTY_TIMES, "hard", 0.05)
    monkeypatch.setitem(ai.DIFFICULTY_DEPTHS, "hard", 30)
    gs = GameState(variant=DONUT)
    start = time.perf_counter()
    result = search_move(gs, "hard")
    assert time.perf_counter() - start < 0.5
    assert result.move in gs.get_valid_moves() and 1 <= result.depth < 30
    assert gs.position_key() == GameState(variant=DONUT).position_key()  # every move was taken back
    assert gs.position_history == GameState(variant=DONUT).position_history


def test_the_first_depth_always_finishes(monkeypatch):
    monkeypatch.setitem(ai.DIFFICULTY_TIMES, "medium", 0)
    result = search_move(GameState(), "medium")
    assert result.depth == 1 and result.move in GameState().get_valid_moves()


def test_a_chess_clock_shortens_the_thinking_time():
    assert ai.time_budget("hard") == ai.DIFFICULTY_TIMES["hard"]
    assert ai.time_budget("hard", time_left=600) == ai.DIFFICULTY_TIMES["hard"]  # plenty of time left
    assert ai.time_budget("hard", time_left=10) == 10 / ai.MOVES_TO_GO  # a fair share of what's left
    assert ai.time_budget("hard", time_left=0.2) == ai.MIN_THINKING_TIME


def test_a_mate_ends_the_search_at_once():
    gs = position({"a5": "black_king", "c4": "white_pawn", "b3": "white_king"})
    result = search_move(gs, "hard")
    assert is_move(result.move, "c4", "c5") and result.depth == 1 and result.score == MATE_SCORE - 2


def turned_around(gs):
    """The same position seen from the other side: board rotated, colors swapped"""
    swap = {"white": "black", "black": "white"}
    board = [[piece if piece == "--" else swap[piece.split("_")[0]] + "_" + piece.split("_")[1]
              for piece in reversed(row)] for row in reversed(gs.board)]
    return GameState(board=board, white_to_move=not gs.white_to_move)


def test_start_position_is_even():
    assert evaluate_board(GameState()) == 0


def test_evaluation_treats_both_sides_the_same():
    rng = random.Random(5)
    for _ in range(50):
        gs = GameState()
        for _ in range(rng.randrange(1, 20)):
            moves = gs.get_valid_moves()
            if not moves:
                break
            gs.make_move(rng.choice(moves))
        score = evaluate_board(gs)
        assert isinstance(score, int)
        assert evaluate_board(turned_around(gs)) == -score


def test_evaluation_rewards_better_squares():
    # A centralised knight beats one in the corner; an advanced pawn beats one at home
    corner = position({"a5": "black_king", "d1": "white_king", "a1": "white_knight"})
    center = position({"a5": "black_king", "d1": "white_king", "b3": "white_knight"})
    assert evaluate_board(center) > evaluate_board(corner)
    home = position({"a5": "black_king", "d1": "white_king", "d2": "white_pawn"})
    advanced = position({"a5": "black_king", "d1": "white_king", "d4": "white_pawn"})
    assert evaluate_board(advanced) > evaluate_board(home)


def test_mate_scores_dwarf_normal_scores():
    # Even a huge material edge (two rooks, bishop and knight against a bare king) is far below a mate
    gs = position({"a5": "black_king", "d1": "white_king", "a1": "white_rook", "b1": "white_rook",
                   "c2": "white_bishop", "b3": "white_knight"})
    assert abs(evaluate_board(gs)) < MATE_SCORE // 10
