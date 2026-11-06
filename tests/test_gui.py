import os

import pytest

# Run without opening a window or playing sound (conftest.py sets this up too)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

import gui  # noqa: E402  (needs the environment variables above)
from helpers import position, square, find_move  # noqa: E402


def click_at(app, pos):
    """Press and release the mouse button without moving"""
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def drag(app, start, end, release=True):
    """Drag the piece on square `start` to square `end` (names like "a1")"""
    start_pos = app.square_rect(*square(start)).center
    end_pos = app.square_rect(*square(end)).center
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start_pos))
    app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=end_pos, rel=(0, 0), buttons=(1, 0, 0)))
    if release:
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=end_pos))


def click(app, name):
    click_at(app, app.square_rect(*square(name)).center)


def click_menu(app, label):
    click_at(app, next(rect for rect, _, _, text in app.menu_buttons() if text == label).center)


def press(app, key):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def wait_for_ai(app):
    """Wait for the background search (the AI's move or a hint) and use its answer"""
    app.search_thread.join(timeout=10)
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


def broken_search(*args, **kwargs):
    raise RuntimeError("search failed")


def test_a_failed_ai_search_still_plays_a_move(app, monkeypatch, capsys):
    monkeypatch.setattr(gui, "get_ai_move", broken_search)
    click(app, "a1")
    click(app, "a4")
    app.update()
    wait_for_ai(app)
    assert not app.ai_thinking
    assert len(app.move_log) == 2 and app.is_human_turn()  # a random legal reply
    assert "search failed" in capsys.readouterr().err  # the error is still reported


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
    press(app, pygame.K_ESCAPE)  # no move played yet, so nothing to lose
    assert not app.running


def test_esc_asks_before_quitting_a_game_in_progress(app):
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_ESCAPE)
    assert app.confirming_quit and app.running
    app.draw()
    press(app, pygame.K_ESCAPE)  # Esc again keeps playing
    assert not app.confirming_quit and app.running
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_RETURN)
    assert not app.running


def test_quit_dialog_buttons(app):
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_ESCAPE)
    click_at(app, app.keep_playing_rect().center)
    assert not app.confirming_quit and app.running
    press(app, pygame.K_ESCAPE)
    click_at(app, app.quit_rect().center)
    assert not app.running


def test_the_board_ignores_input_while_the_quit_dialog_is_open(app):
    click(app, "a1")
    click(app, "a4")
    app.update()
    wait_for_ai(app)
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_u)
    press(app, pygame.K_r)
    click(app, "d1")
    assert len(app.move_log) == 2 and app.selected is None and app.confirming_quit


def test_esc_quits_at_once_from_the_menu(menu):
    press(menu, pygame.K_ESCAPE)
    assert not menu.running


def test_esc_quits_at_once_after_the_game(app):
    # Pawn to c5 as a rook is checkmate
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    click_at(app, app.promotion_options()[0][0].center)
    assert app.result == "checkmate"
    press(app, pygame.K_ESCAPE)
    assert not app.running and not app.confirming_quit


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


@pytest.mark.parametrize("label, key, square_size", [("Micro", "micro", 80), ("Tiny", "tiny", 80),
                                                     ("Donut", "donut", 64), ("Pillars", "pillars", 64)])
def test_choosing_a_board_on_the_menu(menu, label, key, square_size):
    click_menu(menu, label)
    menu.draw()  # the menu describes the chosen board
    press(menu, pygame.K_RETURN)
    assert menu.gs.variant.key == key and menu.square_size == square_size
    area = pygame.Rect(gui.BOARD_X, gui.BOARD_Y, gui.BOARD_AREA_WIDTH, gui.BOARD_AREA_HEIGHT)
    assert area.contains(menu.board_rect())
    for r in range(menu.gs.rows):
        for c in range(menu.gs.cols):
            assert menu.square_at(menu.square_rect(r, c).center) == (r, c)
    menu.draw()


def test_moves_on_a_5x5_board_are_named_by_its_ranks(menu):
    click_menu(menu, "Donut")
    press(menu, pygame.K_RETURN)
    rows = menu.gs.rows
    start, end = menu.square_rect(*square("d2", rows)).center, menu.square_rect(*square("d3", rows)).center
    click_at(menu, start)
    click_at(menu, end)
    assert menu.move_texts == ["d2-d3"]


def test_holes_cannot_be_moved_to(menu):
    click_menu(menu, "Donut")
    press(menu, pygame.K_RETURN)
    # The knight on d1 could jump to c3 if it weren't a hole
    click(menu, "d1")
    click(menu, "c3")
    assert menu.move_log == []
    drag(menu, "d1", "c3")
    assert menu.move_log == [] and menu.selected == square("d1")  # dropped back where it was
    menu.draw()


def test_bigger_board_flips_for_black(menu):
    click_menu(menu, "Pillars")
    click_menu(menu, "Black")
    press(menu, pygame.K_RETURN)
    assert menu.flipped
    for r in range(menu.gs.rows):
        for c in range(menu.gs.cols):
            assert menu.square_at(menu.square_rect(r, c).center) == (r, c)
    menu.update()
    wait_for_ai(menu)
    assert len(menu.move_log) == 1
    menu.draw()


def screen_square(app, name):
    """(column, row) of a square on the screen, counted from the top left"""
    rect, board = app.square_rect(*square(name)), app.board_rect()
    return (rect.x - board.x) // app.square_size, (rect.y - board.y) // app.square_size


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
    for r in range(menu.gs.rows):
        for c in range(menu.gs.cols):
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
    assert menu.move_texts == ["d2-d3", "b5-c3+", "d1-c2"]
    # White's and Black's moves side by side, one numbered row per pair
    cells = dict((index, rect) for rect, index in menu.move_cells())
    assert cells[0].y == cells[1].y < cells[2].y and cells[0].x == cells[2].x < cells[1].x
    menu.draw()
    press(menu, pygame.K_u)
    assert menu.move_texts == ["d2-d3", "b5-c3+"]


def test_checkmate_is_marked_in_the_move_list(app):
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))
    click(app, "c4")
    click(app, "c5")
    click_at(app, app.promotion_options()[0][0].center)
    assert app.move_texts == ["c4-c5=R#"]


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


def switch(app, name):
    """Flip one of the switches on the settings screen by clicking its row"""
    click_at(app, next(rect for rect, setting in app.settings_rows() if setting == name).center)


def test_settings_screen_opens_from_the_menu_and_the_game(menu):
    click_at(menu, menu.menu_settings_rect().center)
    assert menu.in_settings
    menu.draw()
    press(menu, pygame.K_ESCAPE)  # back to the menu, not out of the game
    assert not menu.in_settings and menu.in_menu and menu.running

    press(menu, pygame.K_RETURN)
    click_at(menu, menu.gear_button_rect().center)
    assert menu.in_settings
    click_at(menu, menu.done_button_rect().center)
    assert not menu.in_settings and not menu.in_menu
    press(menu, pygame.K_s)
    assert menu.in_settings


def test_switches_are_remembered_next_time(menu):
    menu.open_settings()
    switch(menu, "sound")
    assert not menu.settings["sound"] and menu.sounds.muted
    assert not gui.ChessGUI().settings["sound"]


def test_menu_choices_are_remembered_next_time(menu):
    for label in ("Donut", "Black", "Hard"):
        click_menu(menu, label)
    press(menu, pygame.K_RETURN)
    again = gui.ChessGUI()
    assert again.in_menu
    assert (again.variant_key, again.human_is_white, again.difficulty) == ("donut", False, "hard")


def test_hints_switched_off(app):
    app.open_settings()
    switch(app, "hints")
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_h)
    click_at(app, app.hint_button_rect().center)
    assert not app.hint_thinking and not app.can_ask_for_hint()
    app.draw()


def test_switching_hints_off_clears_the_hint(app):
    press(app, pygame.K_h)
    wait_for_ai(app)
    assert app.hint is not None
    app.toggle_setting("hints")
    assert app.hint is None


def test_animations_switched_off(app, monkeypatch):
    monkeypatch.setattr(gui, "ANIMATION_MS", 10_000)
    app.toggle_setting("animations")
    click(app, "a1")
    click(app, "a4")
    assert app.animation is None


def test_move_dots_switched_off(app):
    click(app, "d1")  # the king can step to c2
    target = app.square_rect(*square("c2")).center
    app.draw()
    with_dots = app.screen.get_at(target)
    app.toggle_setting("show_moves")
    app.draw()
    assert app.screen.get_at(target) != with_dots
    assert app.screen.get_at(target) in (gui.DARK_SQUARE, gui.LIGHT_SQUARE)


def test_coordinates_switched_off(app):
    board = app.board_rect()
    margin = pygame.Rect(0, board.y, board.x, board.height)  # where the rank numbers go
    app.draw()
    assert pygame.transform.average_color(app.screen, margin)[:3] != tuple(gui.BACKGROUND)[:3]
    app.toggle_setting("coordinates")
    app.draw()
    assert pygame.transform.average_color(app.screen, margin)[:3] == tuple(gui.BACKGROUND)[:3]


def test_quitting_without_being_asked(app):
    app.toggle_setting("confirm_quit")
    click(app, "a1")
    click(app, "a4")
    press(app, pygame.K_ESCAPE)
    assert not app.running and not app.confirming_quit


class FakeTime:
    """Stands in for pygame's millisecond counter, so a test can move time on"""

    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


@pytest.fixture
def timed(app):
    """The game against the AI with a 1-minute clock, and the fake time it runs on"""
    time = FakeTime()
    app.ticks = time
    app.set_clock(1)
    return app, time


def test_no_clock_unless_one_is_chosen(app):
    assert app.settings["clock"] == 0 and app.clock_ms is None
    app.update()
    app.draw()


def test_the_clock_runs_for_the_side_to_move(timed):
    app, time = timed
    time.now = 1500
    app.update()
    assert app.clock_ms == {"white": 58_500, "black": 60_000}
    click(app, "a1")
    click(app, "a4")
    time.now = 4000
    app.update()  # Black (the AI) is thinking now
    assert app.clock_ms == {"white": 58_500, "black": 57_500}
    app.draw()
    wait_for_ai(app)


def test_the_clock_stops_while_settings_are_open(timed):
    app, time = timed
    app.open_settings()
    time.now = 5000
    app.update()
    press(app, pygame.K_ESCAPE)
    app.update()
    assert app.clock_ms["white"] == 60_000


def test_running_out_of_time_loses(timed):
    app, time = timed
    click(app, "a1")
    click(app, "a4")
    app.update()
    wait_for_ai(app)
    time.now = 61_000  # White has used up the minute
    app.update()
    assert app.result == "time" and app.clock_ms["white"] == 0
    assert gui.game_over_text(app.result, app.gs.white_to_move) == ("Time's up!", "Black wins on time")
    press(app, pygame.K_u)  # a game lost on time can't be taken back
    assert len(app.move_log) == 2 and app.result == "time"
    app.update()
    assert not app.ai_thinking
    app.draw()


def test_running_out_of_time_is_a_draw_if_the_other_side_has_only_a_king(timed):
    app, time = timed
    load(app, position({"a5": "black_king", "d1": "white_king", "d2": "white_rook"}))
    time.now = 61_000
    app.update()
    assert app.result == "time_draw"
    app.draw()


def test_the_computer_keeps_an_eye_on_its_clock(timed, monkeypatch):
    app, time = timed
    seen = []

    def recording_search(position, difficulty, **options):
        seen.append(options.get("time_left"))
        return position.get_valid_moves()[0]

    monkeypatch.setattr(gui, "get_ai_move", recording_search)
    click(app, "a1")
    click(app, "a4")
    app.update()
    wait_for_ai(app)
    assert seen == [60.0]  # Black's clock had its full minute


def test_choosing_a_clock_in_settings_restarts_it(timed):
    app, time = timed
    time.now = 10_000
    app.update()
    app.open_settings()
    click_at(app, next(rect for rect, minutes in app.clock_choice_rects() if minutes == 5).center)
    assert app.clock_ms == {"white": 300_000, "black": 300_000}
    app.draw()
    click_at(app, next(rect for rect, minutes in app.clock_choice_rects() if minutes == 0).center)
    assert app.clock_ms is None
    assert gui.ChessGUI().settings["clock"] == 0


def test_clock_text():
    assert gui.clock_text(180_000) == "3:00"
    assert gui.clock_text(65_400) == "1:06"
    assert gui.clock_text(9_340) == "9.3"
    assert gui.clock_text(0) == "0.0"


def bar_colors(app):
    """The colors down the middle of the evaluation bar, top to bottom"""
    bar = gui.EVAL_BAR
    return [tuple(app.screen.get_at((bar.centerx, y)))[:3] for y in range(bar.y + 2, bar.bottom - 2)]


def test_evaluation_bar_is_off_unless_switched_on(app):
    assert app.eval_score is None
    app.draw()
    assert (240, 240, 235) not in bar_colors(app)


def test_evaluation_bar_follows_the_game(app):
    app.toggle_setting("eval_bar")
    assert app.eval_score is not None
    app.draw()
    colors = bar_colors(app)
    assert (240, 240, 235) in colors and (40, 44, 40) in colors
    click(app, "a1")
    click(app, "a4")  # takes a pawn, but Black's king takes the rook back
    assert app.eval_score < -200
    assert gui.ChessGUI().settings["eval_bar"]  # remembered next time


def test_evaluation_bar_shows_a_forced_mate(app):
    app.toggle_setting("eval_bar")
    load(app, position({"a5": "black_king", "c4": "white_pawn", "b3": "white_king"}))  # c4-c5=R mates
    assert gui.score_text(app.eval_score) == "+M1"
    app.draw()
    assert set(bar_colors(app)) == {(240, 240, 235)}  # all White's
    app.flipped = True
    app.draw()
    assert set(bar_colors(app)) == {(240, 240, 235)}


def test_evaluation_bar_shows_the_line_the_ai_expects(app):
    app.toggle_setting("eval_bar")
    assert len(app.eval_line) >= 3
    assert len(gui.line_text(app.eval_line, app.gs.rows, 3).split()) == 3
    app.draw()


def test_line_text():
    gs = gui.GameState()
    line = [find_move(gs.get_valid_moves(), "d2", "d3")[0]]
    gs.make_move(line[0])
    line.append(find_move(gs.get_valid_moves(), "b5", "c3")[0])
    assert gui.line_text(line, gs.rows) == "d2-d3 b5-c3"
    assert gui.line_text(line, gs.rows, 1) == "d2-d3"


def test_score_text():
    assert gui.score_text(0) == "0.0"
    assert gui.score_text(4) == "0.0"
    assert gui.score_text(120) == "+1.2"
    assert gui.score_text(-50) == "-0.5"
    assert gui.score_text(gui.MATE_SCORE - 2) == "+M1"
    assert gui.score_text(-(gui.MATE_SCORE - 4)) == "-M2"
    assert gui.score_text(-(gui.MATE_SCORE - 1)) == "0-1"  # Black has mated


def mate_with_a_promotion(app):
    """Play c4-c5=R, checkmate, from the mate_in_one position"""
    mate_in_one(app)
    click(app, "c4")
    click(app, "c5")
    click_at(app, app.promotion_options()[0][0].center)
    assert app.result == "checkmate"


def finish_review(app):
    """Let review judge every move (it does one per frame)"""
    for _ in app.move_log:
        app.update()


def test_review_steps_through_a_finished_game(app):
    mate_with_a_promotion(app)
    app.draw()
    click_at(app, app.review_button_rect().center)
    assert app.review_index == 1
    finish_review(app)
    assert app.review_marks == [("", [])]  # mating is never a mistake
    app.draw()
    press(app, pygame.K_LEFT)
    assert app.review_index == 0
    assert app.board_view()[0].board[1][2] == "white_pawn"  # the pawn is back on c4
    assert app.board_view()[1] is None
    app.draw()
    press(app, pygame.K_LEFT)  # can't go back past the start
    assert app.review_index == 0
    press(app, pygame.K_END)
    assert app.review_index == 1 and app.board_view()[0].board[0][2] == "white_rook"
    press(app, pygame.K_ESCAPE)  # back to the game-over panel, the game is still there
    assert app.review_index is None and app.running and app.result == "checkmate"


def test_review_buttons_and_clicking_moves(menu):
    menu.two_players = True
    menu.start_game()
    for start, end in [("d2", "d3"), ("b5", "c3"), ("d1", "c2")]:
        click(menu, start)
        click(menu, end)
    menu.result = "repetition"  # pretend the game is over here
    menu.start_review()
    assert menu.review_index == 3
    for action, expected in [("first", 0), ("forward", 1), ("last", 3), ("back", 2)]:
        click_at(menu, next(rect for rect, name in menu.review_buttons() if name == action).center)
        assert menu.review_index == expected
    first_move = next(rect for rect, index in menu.move_cells() if index == 0)
    click_at(menu, first_move.center)
    assert menu.review_index == 1
    menu.draw()
    click_at(menu, next(rect for rect, name in menu.review_buttons() if name == "done").center)
    assert menu.review_index is None


def test_review_marks_a_blunder_and_shows_a_better_move(menu):
    menu.two_players = True
    menu.start_game()
    click(menu, "a1")
    click(menu, "a4")  # Ra1xa4+?? loses the rook to the king
    click(menu, "a5")
    click(menu, "a4")
    mark, better_line = menu.judge_move(0)
    better = better_line[0]
    assert mark == "??" and better in menu.position_after(0).get_valid_moves()
    assert menu.judge_move(1) == ("", [])  # taking the rook was right
    menu.result = "repetition"
    menu.start_review(1)
    finish_review(menu)
    assert menu.better_move() == better
    # The status bar names the better move and what the AI expects after it
    expected = gui.line_text(better_line, menu.gs.rows, 3)
    assert menu.review_status_text() == f"Move 1/2: a1xa4+?? better: {expected}"
    assert len(expected.split()) == 3
    menu.draw()


def test_review_switched_off(app):
    app.toggle_setting("review")
    mate_with_a_promotion(app)
    assert [label for _, label, _ in app.game_over_buttons()] == ["Play again", "Menu"]
    press(app, pygame.K_LEFT)
    assert app.review_index is None
    app.draw()


def test_undo_after_the_game_ends_stops_the_review(app):
    mate_with_a_promotion(app)
    app.start_review()
    press(app, pygame.K_u)
    assert app.review_index is None and app.review_marks == [] and app.result is None


def command_key(app, key):
    """Ctrl (or Cmd) plus a key"""
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_CTRL))


def play_moves(app, *moves):
    for start, end in moves:
        click(app, start)
        click(app, end)


def test_copy_and_paste_a_game_without_a_clipboard(menu):
    # The test window has no clipboard, so the code goes to a file and is read back from it
    menu.two_players = True
    menu.start_game()
    play_moves(menu, ("d2", "d3"), ("b5", "c3"))
    command_key(menu, pygame.K_c)
    assert "saved the game code" in menu.notice[0]
    with open(gui.CODE_PATH) as file:
        assert file.read().strip() == "micro knbr/p.../..../...P/RBNK w WB d2d3 b5c3"
    press(menu, pygame.K_r)
    command_key(menu, pygame.K_v)
    assert menu.move_texts == ["d2-d3", "b5-c3+"] and menu.notice[0] == "Game loaded"
    menu.draw()


def test_copy_and_paste_with_a_clipboard(app, monkeypatch):
    clipboard = []
    monkeypatch.setattr(gui, "copy_text", lambda text: clipboard.append(text) or True)
    monkeypatch.setattr(gui, "pasted_text", lambda: clipboard[-1])
    click(app, "a1")
    click(app, "a4")
    command_key(app, pygame.K_c)
    assert app.notice[0] == "Game code copied" and clipboard == [app.game_code()]
    app.new_game()
    command_key(app, pygame.K_v)
    assert app.move_texts == ["a1xa4+"]


def test_pasting_something_else_shows_a_message(app, monkeypatch):
    click(app, "a1")
    click(app, "a4")
    for text in ("hello there", "micro knbr/p.../..../...P/RBNK w WB c1c4", "custom k./.K w -"):
        monkeypatch.setattr(gui, "pasted_text", lambda: text)
        command_key(app, pygame.K_v)
        assert app.notice[0].startswith("That isn't a game code") and app.move_texts == ["a1xa4+"]
    monkeypatch.setattr(gui, "pasted_text", lambda: None)
    command_key(app, pygame.K_v)  # nothing on the clipboard and no file
    assert app.notice[0].startswith("Nothing to paste")
    app.draw()


def test_pasting_on_the_menu_starts_the_game(menu, monkeypatch):
    monkeypatch.setattr(gui, "pasted_text", lambda: "donut rn.bk/pp.../..#../...PP/KB.NR b - ")
    command_key(menu, pygame.K_v)
    assert not menu.in_menu and menu.gs.variant.key == "donut" and not menu.gs.white_to_move
    press(menu, pygame.K_r)  # restarting goes back to the pasted position
    assert not menu.gs.white_to_move and menu.move_log == []
    menu.draw()


def test_drag_a_piece_to_move_it(app, monkeypatch):
    monkeypatch.setattr(gui, "ANIMATION_MS", 10_000)
    drag(app, "a1", "a4")
    assert app.gs.board[1][0] == "white_rook" and app.move_texts == ["a1xa4+"]
    assert app.animation is None  # a dropped piece is already in place, so it doesn't slide
    assert app.dragging is None and app.selected is None


def test_dragged_piece_follows_the_mouse(app):
    drag(app, "a1", "a3", release=False)
    assert app.dragging == square("a1") and app.selected == square("a1")
    assert app.drag_pos == app.square_rect(*square("a3")).center
    app.draw()  # the piece under the mouse, a faint copy on a1 and an outline on a3


def test_dropping_on_an_illegal_square_puts_the_piece_back(app):
    drag(app, "a1", "c3")
    assert app.move_log == [] and app.dragging is None
    assert app.selected == square("a1")  # still selected, so a click can finish the move
    click(app, "a2")
    assert app.gs.board[3][0] == "white_rook"


def test_dropping_off_the_board_puts_the_piece_back(app):
    start = app.square_rect(*square("a1")).center
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start))
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(gui.WIDTH - 5, 5)))
    assert app.move_log == [] and app.dragging is None


def test_clicking_the_selected_piece_again_deselects_it(app):
    click(app, "a1")
    assert app.selected == square("a1")
    click(app, "a1")
    assert app.selected is None


def test_cannot_drag_the_opponents_pieces(app):
    drag(app, "a4", "a3")
    assert app.dragging is None and app.move_log == []


def test_dragging_a_pawn_to_the_last_rank_opens_the_picker(app):
    load(app, position({"a5": "black_king", "d1": "white_king", "c4": "white_pawn"}))
    drag(app, "c4", "c5")
    assert [m.promotion_piece for m in app.promotion_choices] == ["rook", "bishop", "knight"]
    click_at(app, app.promotion_options()[1][0].center)
    assert app.gs.board[0][2] == "white_bishop"


def test_drag_works_when_the_board_is_flipped(menu):
    menu.human_is_white = False
    menu.difficulty = "easy"
    menu.start_game()
    menu.update()
    wait_for_ai(menu)
    move = next(m for m in menu.valid_moves if not m.is_promotion)
    drag(menu, gui.square_name(move.start_row, move.start_col), gui.square_name(move.end_row, move.end_col))
    assert menu.move_log[-1] == move


def test_restart_while_dragging_drops_the_piece(app):
    drag(app, "a1", "a3", release=False)
    press(app, pygame.K_r)
    assert app.dragging is None


def mate_in_one(app):
    """White to move: c4-c5 promoting to a rook is checkmate"""
    load(app, position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"}))


def test_hint_shows_the_best_move(app):
    mate_in_one(app)
    press(app, pygame.K_h)
    assert app.hint_thinking
    app.draw()  # "Finding a hint..."
    wait_for_ai(app)
    assert not app.hint_thinking
    assert app.hint in app.valid_moves
    assert app.move_log == []  # a hint never plays the move for you
    assert gui.move_notation(app.hint) == "c4-c5=R"
    app.draw()  # the arrow


def test_a_failed_hint_search_shows_no_hint(app, monkeypatch, capsys):
    monkeypatch.setattr(gui, "get_ai_move", broken_search)
    press(app, pygame.K_h)
    wait_for_ai(app)
    assert not app.hint_thinking and app.hint is None
    assert app.can_ask_for_hint()  # the player can try again
    assert "search failed" in capsys.readouterr().err


def test_hint_button(app):
    app.draw()
    click_at(app, app.hint_button_rect().center)
    wait_for_ai(app)
    assert app.hint in app.valid_moves


def test_playing_a_move_clears_the_hint(app):
    press(app, pygame.K_h)
    wait_for_ai(app)
    assert app.hint is not None
    click(app, "a1")
    click(app, "a4")
    assert app.hint is None


def test_playing_before_the_hint_arrives_cancels_it(app):
    press(app, pygame.K_h)
    hint_thread = app.search_thread
    drag(app, "a1", "a4")
    hint_thread.join(timeout=10)
    app.update()
    assert app.hint is None and app.ai_thinking  # the AI is now working on its reply instead


def test_no_hints_on_the_computers_turn_or_after_the_game(app):
    click(app, "a1")
    click(app, "a4")
    app.update()  # the AI starts thinking
    press(app, pygame.K_h)
    assert not app.hint_thinking
    load(app, position({"a5": "black_king", "d5": "white_rook", "b3": "white_king"}, white_to_move=False))
    press(app, pygame.K_h)
    assert not app.hint_thinking and app.hint is None


def test_undo_clears_the_hint(menu):
    menu.two_players = True
    menu.start_game()
    click(menu, "d2")
    click(menu, "d3")
    press(menu, pygame.K_h)  # a hint for Black
    wait_for_ai(menu)
    assert menu.hint is not None and menu.hint.piece_moved.startswith("black")
    press(menu, pygame.K_u)
    assert menu.hint is None
