import os

import pytest

# Run without opening a window or playing sound
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

import gui  # noqa: E402  (needs the environment variables above)
from helpers import position, square  # noqa: E402


@pytest.fixture
def app():
    app = gui.ChessGUI(difficulty="easy")
    yield app
    pygame.quit()


def click(app, name):
    r, c = square(name)
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app.square_rect(r, c).center))


def press(app, key):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def wait_for_ai(app):
    app.ai_thread.join(timeout=10)
    app.update()


def load(app, gs):
    app.gs = gs
    app.move_log = []
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
    rect, _ = app.promotion_options()[2]
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert app.gs.board[0][2] == "white_knight"


def test_game_over_and_play_again(app):
    # Pawn to c5 as a rook is checkmate
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    rect, _ = app.promotion_options()[0]
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert app.result == "checkmate"
    app.draw()
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app.play_again_rect().center))
    assert app.result is None and app.move_log == []


def test_restart_and_quit_keys(app):
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_r)
    assert app.move_log == [] and not app.ai_thinking
    press(app, pygame.K_ESCAPE)
    assert not app.running
