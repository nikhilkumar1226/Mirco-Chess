import os

import pytest

# Run without opening a window or playing sound
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

import gui  # noqa: E402  (needs the environment variables above)
from helpers import position, square, find_move  # noqa: E402


@pytest.fixture
def menu(monkeypatch):
    # Moves appear at once, so tests don't have to wait for pieces to slide
    monkeypatch.setattr(gui, "ANIMATION_MS", 0)
    app = gui.ChessGUI()
    yield app
    pygame.quit()


@pytest.fixture
def app(menu):
    """A game against the AI on Easy, playing White"""
    menu.difficulty = "easy"
    menu.start_game()
    return menu


def click_at(app, pos):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def click(app, name):
    click_at(app, app.square_rect(*square(name)).center)


def click_menu(app, label):
    click_at(app, next(rect for rect, _, _, text in app.menu_buttons() if text == label).center)


def press(app, key):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def wait_for_ai(app):
    app.ai_thread.join(timeout=10)
    app.update()


def load(app, gs):
    app.gs = gs
    app.move_log = []
    app.move_texts = []
    app.refresh()


def test_window_starts_and_draws(app):
    for _ in range(3):
        app.update()
        app.draw()
        pygame.display.flip()
    assert pygame.display.get_caption()[0] == "Micro Chess"
    assert app.screen.get_size() == (gui.WIDTH, gui.HEIGHT)


def test_a1_is_a_dark_square(app):
    app.draw()
    assert app.screen.get_at(app.square_rect(*square("a1")).topleft) == gui.DARK_SQUARE
    assert app.screen.get_at(app.square_rect(*square("a2")).topleft) == gui.LIGHT_SQUARE
    assert app.screen.get_at(app.square_rect(*square("b1")).topleft) == gui.LIGHT_SQUARE
    assert app.screen.get_at(app.square_rect(*square("c3")).topleft) == gui.DARK_SQUARE


def test_click_selects_a_piece_and_clicking_elsewhere_deselects(app):
    click(app, "a1")
    assert app.selected == square("a1")
    assert len(app.moves_from(app.selected)) == 3  # a2, a3 and the capture on a4
    click(app, "c3")
    assert app.selected is None


def test_opponent_pieces_cannot_be_selected(app):
    click(app, "a4")
    assert app.selected is None


def test_human_move_then_ai_replies_in_the_background(app):
    click(app, "a1")
    click(app, "a4")
    assert app.gs.board[1][0] == "white_rook"
    app.update()
    assert app.ai_thinking
    wait_for_ai(app)
    assert not app.ai_thinking
    assert len(app.move_log) == 2 and app.is_human_turn()
    assert app.last_move is app.move_log[-1]


def test_undo_takes_back_your_move_and_the_ai_reply(app):
    click(app, "a1")
    click(app, "a4")
    app.update()
    wait_for_ai(app)
    press(app, pygame.K_u)
    assert app.move_log == [] and app.gs.board == gui.GameState().board


def test_undo_while_the_ai_is_thinking_ignores_its_answer(app):
    click(app, "a1")
    click(app, "a4")
    app.update()
    press(app, pygame.K_u)
    wait_for_ai(app)
    assert app.move_log == [] and app.is_human_turn()


def test_promotion_picker(app):
    load(app, position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    assert [m.promotion_piece for m in app.promotion_choices] == ["rook", "bishop", "knight"]
    app.draw()
    click_at(app, app.promotion_options()[2][0].center)
    assert app.gs.board[0][2] == "white_knight"


def test_game_over_and_play_again(app):
    # Pawn to c5 as a rook is checkmate
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    click_at(app, app.promotion_options()[0][0].center)
    assert app.result == "checkmate"
    app.draw()
    click_at(app, app.play_again_rect().center)
    assert app.result is None and app.move_log == [] and not app.in_menu


def test_game_over_back_to_menu(app):
    load(app, position({"a5": "black_king", "d5": "white_rook", "b3": "white_king"}, white_to_move=False))
    assert app.result == "checkmate"
    click_at(app, app.menu_button_rect().center)
    assert app.in_menu


def test_restart_and_quit_keys(app):
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_r)
    assert app.move_log == [] and not app.ai_thinking
    press(app, pygame.K_ESCAPE)
    assert not app.running


def test_starts_on_the_menu(menu):
    menu.draw()
    menu.update()
    assert menu.in_menu and not menu.ai_thinking


def test_menu_play_black_on_hard(menu):
    click_menu(menu, "Black")
    click_menu(menu, "Hard")
    click_at(menu, menu.start_button_rect().center)
    assert not menu.in_menu
    assert (menu.human_is_white, menu.difficulty, menu.two_players) == (False, "hard", False)
    menu.update()
    assert menu.ai_thinking  # the AI plays White, so it moves first
    wait_for_ai(menu)
    assert len(menu.move_log) == 1 and menu.is_human_turn()


def test_two_player_mode_has_no_ai(menu):
    click_menu(menu, "2 Players")
    click_menu(menu, "Hard")  # disabled in a 2-player game
    assert menu.difficulty == "medium"
    press(menu, pygame.K_RETURN)
    click(menu, "d2")
    click(menu, "d3")
    menu.update()
    assert not menu.ai_thinking
    click(menu, "b5")  # now Black moves
    click(menu, "c3")
    assert len(menu.move_log) == 2
    press(menu, pygame.K_u)  # takes back just one move
    assert len(menu.move_log) == 1 and not menu.gs.white_to_move


def test_n_goes_back_to_the_menu(app):
    press(app, pygame.K_n)
    assert app.in_menu
    app.draw()


def screen_square(app, name):
    """(column, row) of a square on the screen, counted from the top left"""
    rect = app.square_rect(*square(name))
    return (rect.x - gui.BOARD_X) // gui.SQUARE_SIZE, (rect.y - gui.BOARD_Y) // gui.SQUARE_SIZE


def test_board_is_seen_from_whites_side_when_playing_white(app):
    assert not app.flipped
    assert screen_square(app, "a1") == (0, 4) and screen_square(app, "d5") == (3, 0)


@pytest.mark.parametrize("two_players, flipped", [(False, True), (True, False)])
def test_board_flips_when_playing_black_against_the_computer(menu, two_players, flipped):
    menu.human_is_white, menu.two_players = False, two_players
    menu.start_game()
    assert menu.flipped == flipped
    if flipped:
        assert screen_square(menu, "a5") == (3, 4) and screen_square(menu, "d1") == (0, 0)


def test_clicks_find_the_right_square_when_flipped(menu):
    menu.human_is_white = False
    menu.start_game()
    for r in range(gui.ROWS):
        for c in range(gui.COLS):
            assert menu.square_at(menu.square_rect(r, c).center) == (r, c)
    menu.update()  # the AI plays White's first move
    wait_for_ai(menu)
    click(menu, "b5")
    assert menu.selected == square("b5")


def test_move_notation():
    gs = position({"a5": "black_king", "a4": "black_pawn", "c4": "white_pawn",
                   "a1": "white_rook", "d1": "white_king"})
    moves = gs.get_valid_moves()
    assert gui.move_notation(find_move(moves, "d1", "d2")[0]) == "d1-d2"
    assert gui.move_notation(find_move(moves, "a1", "a4")[0]) == "a1xa4"
    assert gui.move_notation(find_move(moves, "c4", "c5")[0]) == "c4-c5=R"
    assert gui.move_notation(find_move(moves, "d1", "b1")[0]) == "O-O"


def test_move_list_pairs_moves_by_number(menu):
    menu.two_players = True
    menu.start_game()
    for start, end in [("d2", "d3"), ("b5", "c3"), ("d1", "c2")]:  # the knight checks, the king steps away
        click(menu, start)
        click(menu, end)
    assert menu.move_list() == [("1.", "d2-d3", "b5-c3+"), ("2.", "d1-c2", "")]
    menu.draw()
    press(menu, pygame.K_u)
    assert menu.move_list() == [("1.", "d2-d3", "b5-c3+")]


def test_checkmate_is_marked_in_the_move_list(app):
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    click_at(app, app.promotion_options()[0][0].center)
    assert app.move_list() == [("1.", "c4-c5=R#", "")]


def test_captured_pieces_and_material(menu):
    menu.two_players = True
    menu.start_game()
    for start, end in [("a1", "a4"), ("a5", "a4")]:  # rook takes pawn, king takes rook
        click(menu, start)
        click(menu, end)
    assert menu.captured_pieces() == (["black_pawn"], ["white_rook"])
    assert menu.material_balance() == -4
    menu.draw()


def test_long_games_fit_in_the_move_list(menu):
    menu.two_players = True
    menu.start_game()
    knight_dance = [("c1", "a2"), ("b5", "a3"), ("a2", "c1"), ("a3", "b5")] * 2
    for start, end in knight_dance + [("c1", "a2"), ("b5", "a3")] * 6:
        if menu.result:
            break
        click(menu, start)
        click(menu, end)
    menu.draw()


def test_moves_slide_into_place(app, monkeypatch):
    monkeypatch.setattr(gui, "ANIMATION_MS", 10_000)
    click(app, "a1")
    click(app, "a4")
    pieces, progress = app.sliding_pieces()
    assert pieces == [("white_rook", square("a1"), square("a4"))] and 0 <= progress < 1
    app.draw()

    # The AI's reply waits until the rook has arrived
    app.update()
    wait_for_ai(app)
    assert len(app.move_log) == 1
    monkeypatch.setattr(gui, "ANIMATION_MS", 0)
    app.update()
    assert len(app.move_log) == 2


def test_castling_slides_the_rook_too(menu, monkeypatch):
    menu.two_players = True
    menu.start_game()
    load(menu, position({"d5": "black_king", "a1": "white_rook", "d1": "white_king"}))
    monkeypatch.setattr(gui, "ANIMATION_MS", 10_000)
    click(menu, "d1")
    click(menu, "b1")
    pieces, _ = menu.sliding_pieces()
    assert pieces == [("white_king", square("d1"), square("b1")), ("white_rook", square("a1"), square("c1"))]
    menu.draw()


def test_undo_stops_the_animation(app, monkeypatch):
    monkeypatch.setattr(gui, "ANIMATION_MS", 10_000)
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_u)
    assert app.animation is None and app.sliding_pieces() == ([], 1)


def test_m_toggles_sound(app):
    press(app, pygame.K_m)
    assert app.sounds.muted
    app.draw()
    press(app, pygame.K_m)
    assert not app.sounds.muted
