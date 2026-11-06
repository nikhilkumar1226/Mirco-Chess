"""Puzzle mode: the puzzles in puzzles.json, and solving them in the window."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

import ai  # noqa: E402
import gui  # noqa: E402
import settings  # noqa: E402
from chess_engine import GameState, VARIANTS, PILLARS, read_game_code, move_code  # noqa: E402
from helpers import position, square  # noqa: E402

PUZZLES = gui.load_puzzles()


def test_there_are_puzzles_for_every_board():
    assert 30 <= len(PUZZLES) <= 60
    assert len({puzzle["id"] for puzzle in PUZZLES}) == len(PUZZLES)
    assert {puzzle["code"].split()[0] for puzzle in PUZZLES} == set(VARIANTS)
    assert {puzzle["mate_in"] for puzzle in PUZZLES} == {1, 2, 3}


@pytest.mark.parametrize("puzzle", PUZZLES, ids=lambda puzzle: puzzle["id"])
def test_each_puzzle_has_exactly_one_winning_first_move(puzzle):
    gs = GameState.from_code(puzzle["code"])
    moves = puzzle["mate_in"]
    winners = ai.mating_moves(gs, moves)
    assert len(winners) == 1
    if moves > 1:
        assert not ai.mating_moves(gs, moves - 1)  # and no quicker mate
    # The solution starts with that move and ends in checkmate
    start, line = read_game_code(" ".join([puzzle["code"]] + puzzle["solution"]))
    assert line[0] == winners[0] and len(line) == 2 * moves - 1
    for move in line:
        start.make_move(move)
    assert start.get_game_result() == "checkmate"


def test_mating_moves():
    # Re2-a2 is the only mate in 1; from e1 the rook needs two moves (Re2, then Ra2)
    gs = position({"c5": "white_king", "e2": "white_rook", "a4": "black_king"}, variant=PILLARS)
    assert [(m.start_row, m.start_col, m.end_row, m.end_col) for m in ai.mating_moves(gs, 1)] == [(3, 4, 3, 0)]
    gs = position({"c5": "white_king", "e1": "white_rook", "a3": "black_king"}, variant=PILLARS)
    assert ai.mating_moves(gs, 1) == []
    assert len(ai.mating_moves(gs, 2)) == 1


def test_damaged_puzzle_files_give_no_puzzles(tmp_path):
    path = tmp_path / "puzzles.json"
    assert gui.load_puzzles(str(path)) == []  # missing
    path.write_text("[{")
    assert gui.load_puzzles(str(path)) == []
    path.write_text('{"id": 1}')
    assert gui.load_puzzles(str(path)) == []
    path.write_text('[{"id": "x"}, {"id": "y", "code": "c", "mate_in": 1, "solution": []}]')
    assert [puzzle["id"] for puzzle in gui.load_puzzles(str(path))] == ["y"]


# ---- in the window ------------------------------------------------------------

@pytest.fixture
def menu(monkeypatch, tmp_path):
    monkeypatch.setattr(gui, "ANIMATION_MS", 0)
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    app = gui.ChessGUI()
    yield app
    pygame.quit()


def click_square(app, name):
    pos = app.square_rect(*square(name, app.gs.rows)).center
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def play_code(app, code):
    """Play a move written as in a game code ("c1b3", "c4c5r") by clicking"""
    click_square(app, code[:2])
    click_square(app, code[2:4])
    if len(code) == 5:
        piece = {"r": "rook", "b": "bishop", "n": "knight"}[code[4]]
        rect = next(rect for rect, move in app.promotion_options() if move.promotion_piece == piece)
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def click_button(app, rect):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def puzzle_button(app, action):
    return next(rect for rect, _, name in app.puzzle_buttons() if name == action)


def first_puzzle(mate_in):
    return next(i for i, puzzle in enumerate(PUZZLES) if puzzle["mate_in"] == mate_in)


def test_puzzles_open_from_the_menu(menu):
    click_button(menu, next(rect for rect, _, page in menu.menu_page_buttons() if page == "puzzles"))
    assert not menu.in_menu and menu.puzzle_index == 0
    assert menu.gs.to_code() == PUZZLES[0]["code"]
    side = "White" if menu.gs.white_to_move else "Black"
    assert menu.puzzle_status_line() == f"Puzzle 1/{len(PUZZLES)}: {side} to move, mate in {PUZZLES[0]['mate_in']}"
    assert menu.flipped == (not menu.gs.white_to_move)
    menu.draw()


@pytest.mark.parametrize("mate_in", [2, 3])
def test_solving_a_puzzle(menu, mate_in):
    index = first_puzzle(mate_in)
    menu.start_puzzle(index)
    solution = PUZZLES[index]["solution"]
    for number, code in enumerate(solution):
        if number % 2 == 0:
            play_code(menu, code)  # the solver's move...
        else:
            menu.update()  # ...and the computer's defence, which is the one in the solution
            assert move_code(menu.move_log[-1], menu.gs.rows) == code
    assert menu.puzzle_status == "solved" and menu.result == "checkmate"
    menu.draw()
    assert PUZZLES[index]["id"] in gui.ChessGUI().settings["solved_puzzles"]  # remembered
    click_button(menu, puzzle_button(menu, "next"))
    assert menu.puzzle_index != index and menu.puzzle_status is None


def test_a_move_that_misses_the_mate(menu):
    index = first_puzzle(2)
    menu.start_puzzle(index)
    wrong = next(move for move in menu.gs.get_valid_moves() if not ai.move_mates_within(menu.gs, move, 2))
    menu.play(wrong)
    assert menu.puzzle_status == "failed" and menu.puzzle_reply is None
    assert menu.puzzle_status_line().startswith("Not quite")
    menu.draw()
    click_button(menu, puzzle_button(menu, "retry"))
    assert menu.puzzle_status is None and menu.move_log == [] and menu.gs.to_code() == PUZZLES[index]["code"]


def test_show_solution_then_step_back_through_it(menu):
    index = first_puzzle(2)
    menu.start_puzzle(index)
    wrong = next(move for move in menu.gs.get_valid_moves() if not ai.move_mates_within(menu.gs, move, 2))
    menu.play(wrong)
    click_button(menu, puzzle_button(menu, "solution"))
    assert menu.puzzle_status == "solution" and menu.result == "checkmate"
    assert len(menu.move_log) == len(PUZZLES[index]["solution"])
    assert [label for _, label, _ in menu.puzzle_buttons()] == ["Retry", "Next"]
    menu.draw()
    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT))
    assert menu.review_index == len(menu.move_log) - 1
    menu.draw()


def test_puzzles_have_no_hints_evaluation_clock_or_undo(menu):
    menu.toggle_setting("eval_bar")
    menu.set_clock(3)
    menu.start_puzzle(first_puzzle(2))
    assert not menu.can_ask_for_hint() and menu.eval_score is None and menu.clock_ms is None
    play_code(menu, PUZZLES[first_puzzle(2)]["solution"][0])
    menu.undo()
    assert len(menu.move_log) == 1
    menu.update()
    assert not menu.ai_thinking  # the computer only defends; it never starts a search of its own


def test_starting_an_ordinary_game_leaves_the_puzzles(menu):
    menu.start_puzzle(0)
    menu.open_menu()
    menu.start_game()
    assert menu.puzzle_index is None and menu.gs.to_code() == GameState().to_code()
