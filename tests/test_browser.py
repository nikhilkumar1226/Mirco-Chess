"""The browser version (made with pygbag): an async main loop, searches without threads, and
nothing that can go wrong in a browser (saving, sound, the clipboard) ever stopping the game."""

import asyncio
import builtins
import os
import time

import pytest

pygame = pytest.importorskip("pygame")

import ai  # noqa: E402
import gui  # noqa: E402
import settings  # noqa: E402
import sounds  # noqa: E402
import stats  # noqa: E402
from helpers import position, square  # noqa: E402

MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


def click(app, name):
    pos = app.square_rect(*square(name)).center
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def fails(*args, **kwargs):
    raise RuntimeError("not available here")


@pytest.fixture
def browser(app, monkeypatch):
    """The game as it runs in a web page: any attempt to start a thread fails"""
    monkeypatch.setattr(gui, "IN_BROWSER", True)
    monkeypatch.setattr(gui.threading, "Thread", fails)
    return app


def test_main_py_ends_by_starting_the_async_loop():
    with open(MAIN_PY) as file:
        lines = [line for line in file.read().splitlines() if line.strip()]
    assert lines[-1] == "asyncio.run(main())"  # pygbag needs this to be the last thing main.py does


def test_the_main_loop_is_async(menu):
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    asyncio.run(menu.run())
    assert not menu.running


def test_the_computer_moves_without_a_thread(browser, monkeypatch):
    limits = []
    real_search = gui.get_ai_move

    def recording_search(position, difficulty, **options):
        limits.append(options["time_limit"])
        return real_search(position, difficulty, **options)

    monkeypatch.setattr(gui, "get_ai_move", recording_search)
    click(browser, "a1")
    click(browser, "a4")
    browser.update()
    assert browser.ai_thinking and browser.waiting_search  # this frame shows "Thinking..."...
    browser.draw()
    browser.run_waiting_searches()  # ...and the next one starts with the search
    browser.update()
    assert len(browser.move_log) == 2 and limits == [gui.BROWSER_TIME_LIMIT]


def test_a_browser_search_keeps_to_the_time_limit(browser, monkeypatch):
    monkeypatch.setitem(ai.DIFFICULTY_DEPTHS, "hard", 30)  # deep enough to need the whole limit
    monkeypatch.setitem(ai.DIFFICULTY_TIMES, "hard", 10)
    monkeypatch.setattr(gui, "BROWSER_TIME_LIMIT", 0.3)
    browser.difficulty = "hard"
    click(browser, "a1")
    click(browser, "a2")
    browser.update()
    start = time.perf_counter()
    browser.run_waiting_searches()
    assert time.perf_counter() - start < 0.8
    browser.update()
    assert len(browser.move_log) == 2


def test_hints_without_a_thread(browser):
    browser.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    assert browser.hint_thinking and browser.waiting_search
    browser.run_waiting_searches()
    browser.update()
    assert browser.hint in browser.valid_moves


def test_a_move_cancels_a_waiting_hint(browser):
    browser.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h))
    click(browser, "a1")
    click(browser, "a4")
    assert browser.waiting_search is None
    browser.update()  # the computer's search waits now instead
    assert browser.waiting_search[1] == "ai"


def test_the_evaluation_bar_waits_for_a_frame(browser):
    browser.toggle_setting("eval_bar")
    assert browser.eval_waiting and browser.eval_score is None
    browser.draw()  # the bar shows "Thinking..."
    browser.run_waiting_searches()
    assert not browser.eval_waiting and browser.eval_score is not None and browser.eval_line
    browser.draw()


def test_game_review_keeps_to_the_time_limit(browser, monkeypatch):
    limits = []
    real_analyse = gui.analyse

    def recording_analyse(game_state, depth, time_limit=None):
        limits.append(time_limit)
        return real_analyse(game_state, depth, time_limit)

    monkeypatch.setattr(gui, "analyse", recording_analyse)
    browser.gs = position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"})
    browser.move_log, browser.move_texts = [], []
    browser.refresh()
    browser.play([m for m in browser.valid_moves if m.promotion_piece == "rook"][0])
    browser.start_review()
    browser.update()
    assert browser.review_marks == [("", [])] and limits == [gui.BROWSER_TIME_LIMIT]


def test_saving_and_loading_never_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(builtins, "open", fails)  # e.g. a browser that won't open files
    settings.save(settings.DEFAULTS, tmp_path / "settings.json")
    stats.save(stats.fresh_stats(), tmp_path / "stats.json")
    assert settings.load(tmp_path / "settings.json") == settings.DEFAULTS
    assert stats.load(tmp_path / "stats.json") == stats.fresh_stats()


def test_copying_and_pasting_codes_never_crash(app, monkeypatch):
    monkeypatch.setattr(gui, "copy_text", lambda text: False)
    monkeypatch.setattr(gui, "pasted_text", lambda: None)
    monkeypatch.setattr(builtins, "open", fails)
    app.copy_game_code()
    assert app.notice[0] == "Couldn't copy the game code"
    app.paste_game_code()
    assert app.notice[0].startswith("Nothing to paste")


def test_the_clipboard_fails_silently(monkeypatch):
    monkeypatch.setattr(pygame.scrap, "get_init", fails)
    assert gui.copy_text("micro") is False
    assert gui.pasted_text() is None


def test_sound_fails_silently(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    monkeypatch.setattr(pygame.mixer, "init", fails)
    player = sounds.Sounds()
    assert player.sounds == {}
    player.play("move")

    class BrokenSound:
        def play(self):
            raise RuntimeError("the page won't play sound")

    player.sounds = {"move": BrokenSound()}
    player.play("move")  # no error
