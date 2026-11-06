"""The board editor: set up a position on a 4x4, 4x5 or 5x5 board, with holes, and play it."""

import pytest

pygame = pytest.importorskip("pygame")

import gui  # noqa: E402
from chess_engine import EMPTY, HOLE  # noqa: E402
from helpers import square  # noqa: E402


def click(app, pos):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def control(app, action, value=None):
    return next(rect for rect, name, item, _ in app.editor_controls() if name == action and item == value)


def choose(app, action, value=None):
    click(app, control(app, action, value).center)


def put(app, tool, *names):
    """Pick a piece (or a hole, or EMPTY for the eraser) and click it onto squares like "a1" """
    choose(app, "tool" if tool in (HOLE, EMPTY) else "piece", tool)
    for name in names:
        click(app, app.editor_square_rect(*square(name, app.editor_size[0])).center)


@pytest.fixture
def editor(menu):
    click(menu, next(rect for rect, _, page in menu.menu_page_buttons() if page == "editor").center)
    return menu


def test_the_editor_opens_from_the_menu_with_an_empty_board(editor):
    assert editor.in_editor and editor.editor_size == (5, 4)
    assert all(square == EMPTY for row in editor.editor_board for square in row)
    assert editor.editor_problem() == "White needs exactly one king"
    editor.draw()


def test_set_up_a_position_and_play_a_friend(editor):
    put(editor, "white_king", "d1")
    put(editor, "black_king", "a5")
    put(editor, "white_rook", "b1")
    assert editor.editor_problem() is None
    editor.draw()
    choose(editor, "play", True)
    assert not editor.in_editor and not editor.in_menu and editor.two_players
    assert editor.gs.to_code() == "custom k.../..../..../..../.R.K w -"
    assert editor.gs.castling_rights == frozenset()  # never any castling on a custom board
    editor.draw()


def test_play_and_save_wait_for_a_position_that_can_be_played(editor):
    put(editor, "white_king", "d1")
    put(editor, "black_king", "a5")
    put(editor, "white_pawn", "b5")  # a pawn on its last rank
    assert "last rank" in editor.editor_problem()
    choose(editor, "play", False)
    choose(editor, "save")
    assert editor.in_editor and editor.settings["custom_boards"] == []
    put(editor, EMPTY, "b5")
    put(editor, "white_rook", "a1")  # gives check on the a-file...
    choose(editor, "side", False)
    assert editor.editor_problem() is None  # ...which is fine with Black to move
    choose(editor, "side", True)
    assert editor.editor_problem() == "Black is in check, but it's White's move"
    put(editor, "black_king", "b5")  # a second black king
    assert editor.editor_problem() == "Black needs exactly one king"


def test_holes_and_board_sizes(editor):
    choose(editor, "size", (5, 5))
    assert editor.editor_size == (5, 5) and len(editor.editor_board[0]) == 5
    put(editor, HOLE, "c3", "b2")
    put(editor, EMPTY, "b2")
    put(editor, "white_king", "e1")
    put(editor, "black_king", "a5")
    choose(editor, "play", True)
    assert editor.gs.board[2][2] == HOLE and editor.gs.board[3][1] == EMPTY
    assert not editor.gs.variant.lone_knight_draws  # a hole could make that mate possible
    assert editor.square_size == 64
    editor.draw()


def test_clear_and_the_4x4_board(editor):
    put(editor, "white_king", "d1")
    choose(editor, "size", (4, 4))
    assert editor.editor_size == (4, 4) and editor.editor_board == [[EMPTY] * 4 for _ in range(4)]
    put(editor, "white_knight", "b2")
    choose(editor, "clear")
    assert editor.editor_board == [[EMPTY] * 4 for _ in range(4)]


def test_saved_boards_are_remembered(editor):
    put(editor, "white_king", "d1")
    put(editor, "black_king", "a5")
    choose(editor, "save")
    first = editor.editor_code()
    put(editor, "black_knight", "c3")
    choose(editor, "save")
    assert editor.settings["custom_boards"] == [first, editor.editor_code()]
    again = gui.ChessGUI()
    assert again.settings["custom_boards"] == editor.settings["custom_boards"]
    again.open_editor()
    choose(again, "saved")
    assert again.editor_code() == first
    choose(again, "saved")
    assert again.editor_board[2][2] == "black_knight"


def test_play_the_computer_on_a_custom_board(editor):
    editor.difficulty = "easy"
    put(editor, "white_king", "d1")
    put(editor, "black_king", "a5")
    put(editor, "black_rook", "d5")
    choose(editor, "play", False)
    assert not editor.two_players
    click(editor, editor.square_rect(*square("d1")).center)
    click(editor, editor.square_rect(*square("c1")).center)
    editor.update()
    editor.search_thread.join(timeout=10)
    editor.update()
    assert len(editor.move_log) == 2  # the computer answered
    editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    assert editor.gs.to_code() == "custom k..r/..../..../..../...K w -"  # restart: back to the custom start


def test_escape_and_back_return_to_the_menu(editor):
    editor.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not editor.in_editor and editor.in_menu and editor.running
    editor.open_editor()
    click(editor, editor.editor_back_rect().center)
    assert not editor.in_editor and editor.in_menu
