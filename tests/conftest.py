"""Fixtures for the tests of the window, which run without opening one or playing sound."""

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture
def menu(monkeypatch, tmp_path):
    """The window on its start menu"""
    pygame = pytest.importorskip("pygame")
    import gui
    import settings
    # Moves appear at once, so tests don't have to wait for pieces to slide
    monkeypatch.setattr(gui, "ANIMATION_MS", 0)
    # Settings (and copied game codes) are saved in a temporary folder, never the real home folder
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(gui, "CODE_PATH", str(tmp_path / "code.txt"))
    app = gui.ChessGUI()
    yield app
    pygame.quit()


@pytest.fixture
def app(menu):
    """A game against the AI on Easy, playing White"""
    menu.difficulty = "easy"
    menu.start_game()
    return menu
