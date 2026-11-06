"""Stats and the rating: counted for games against the computer and remembered between launches."""

import json

import pytest

import stats
from helpers import position

pygame = pytest.importorskip("pygame")
import gui  # noqa: E402


def test_fresh_stats_when_nothing_was_saved(tmp_path):
    assert stats.load(tmp_path / "missing.json") == {"rating": 1000, "games": {}}


def test_saved_stats_come_back(tmp_path):
    path = tmp_path / "stats.json"
    saved = stats.fresh_stats()
    stats.record(saved, "donut", "hard", "win")
    stats.save(saved, path)
    assert stats.load(path) == saved


@pytest.mark.parametrize("text", ["{ not json", "[1, 2]", '"rating"', ""])
def test_a_damaged_file_gives_fresh_stats(tmp_path, text):
    path = tmp_path / "stats.json"
    path.write_text(text)
    assert stats.load(path) == stats.fresh_stats()


def test_odd_values_are_left_out(tmp_path):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({
        "rating": "high",
        "games": {
            "micro/easy": {"wins": 2, "draws": 1, "losses": 0},  # fine
            "tiny/hard": {"wins": -1},  # a negative count
            "donut/medium": {"wins": True},  # not a number
            "pillars/easy": "lots",  # not counts at all
        },
    }))
    loaded = stats.load(path)
    assert loaded["rating"] == 1000
    assert loaded["games"] == {"micro/easy": {"wins": 2, "draws": 1, "losses": 0}}


def test_saving_where_it_cannot_write_does_not_crash(tmp_path):
    stats.save(stats.fresh_stats(), tmp_path / "no such folder" / "stats.json")


def test_the_rating():
    assert stats.new_rating(1000, 1000, 1) == 1016  # beating an equal: half of K
    assert stats.new_rating(1000, 1000, 0.5) == 1000
    assert stats.new_rating(1000, 1600, 1) > 1030  # beating Hard is worth more...
    assert stats.new_rating(1000, 800, 1) < 1010  # ...than beating Easy
    assert stats.new_rating(1000, 800, 0.5) < 1000  # a draw with Easy costs a little
    assert isinstance(stats.new_rating(1234, 1200, 0.5), int)


def test_recording_counts_the_game_and_moves_the_rating():
    record = stats.fresh_stats()
    stats.record(record, "micro", "medium", "win")
    stats.record(record, "micro", "medium", "draw")
    stats.record(record, "micro", "hard", "loss")
    assert stats.counts_for(record, "micro", "medium") == (1, 1, 0)
    assert stats.counts_for(record, "micro", "hard") == (0, 0, 1)
    assert stats.counts_for(record, "tiny", "easy") == (0, 0, 0)
    assert record["rating"] != 1000


# ---- in the window ------------------------------------------------------------

def mate_in_one(app):
    """White to move: c4-c5 promoting to a rook is checkmate"""
    app.gs = position({"a5": "black_king", "b3": "white_king", "c4": "white_pawn"})
    app.move_log, app.move_texts = [], []
    app.refresh()
    app.play([m for m in app.valid_moves if m.is_promotion and m.promotion_piece == "rook"][0])


def test_a_win_against_the_computer_is_counted_once(app):
    mate_in_one(app)
    assert app.stats["rating"] > 1000 and stats.counts_for(app.stats, "micro", "easy") == (1, 0, 0)
    assert app.notice[0].startswith("Win: rating")
    assert stats.load()["rating"] == app.stats["rating"]  # saved straight away
    app.record_result()  # a second look at the same finished game changes nothing
    assert stats.counts_for(app.stats, "micro", "easy") == (1, 0, 0)


def test_a_loss_counts_as_a_loss(menu):
    menu.human_is_white = False  # the computer plays White, and its pawn mates
    menu.difficulty = "hard"
    menu.start_game()
    mate_in_one(menu)
    assert stats.counts_for(menu.stats, "micro", "hard") == (0, 0, 1) and menu.stats["rating"] < 1000


def test_friends_puzzles_and_set_up_positions_are_not_counted(menu):
    menu.two_players = True
    menu.start_game()
    mate_in_one(menu)
    menu.two_players = False
    menu.load_game("micro k.../..../.K../..P./.... w -", [])  # a pasted position
    mate_in_one(menu)
    assert menu.stats == stats.fresh_stats()


def test_the_stats_screen(menu):
    menu.stats["rating"] = 1111
    stats.record(menu.stats, "pillars", "medium", "win")
    page = next(rect for rect, _, name in menu.menu_page_buttons() if name == "stats")
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=page.center))
    assert menu.in_stats
    menu.draw()
    menu.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not menu.in_stats and menu.in_menu and menu.running


def test_a_damaged_stats_file_does_not_stop_the_game(menu, tmp_path):
    with open(stats.STATS_PATH, "w") as file:
        file.write("{ damaged")
    assert gui.ChessGUI().stats == stats.fresh_stats()
