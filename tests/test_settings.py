import json

import settings


def test_defaults_when_nothing_was_saved(tmp_path):
    assert settings.load(tmp_path / "missing.json") == settings.DEFAULTS


def test_saved_settings_come_back(tmp_path):
    path = tmp_path / "settings.json"
    chosen = dict(settings.DEFAULTS, sound=False, variant_key="donut", difficulty="hard")
    settings.save(chosen, path)
    assert settings.load(path) == chosen


def test_a_damaged_file_gives_the_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ not json")
    assert settings.load(path) == settings.DEFAULTS
    path.write_text("[1, 2, 3]")
    assert settings.load(path) == settings.DEFAULTS


def test_unknown_or_invalid_values_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "sound": "no",               # wrong type
        "hints": False,              # fine
        "variant_key": "giant",      # not a board
        "difficulty": "impossible",  # not a level
        "two_players": 1,            # a number, not true/false
        "colour": "blue",            # not a setting
    }))
    loaded = settings.load(path)
    assert loaded == dict(settings.DEFAULTS, hints=False)


def test_saving_where_it_cannot_write_does_not_crash(tmp_path):
    settings.save(settings.DEFAULTS, tmp_path / "no such folder" / "settings.json")


def test_solved_puzzles_keep_only_their_names(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"solved_puzzles": ["micro-1", 7, None, "tiny-3"]}))
    assert settings.load(path)["solved_puzzles"] == ["micro-1", "tiny-3"]
    path.write_text(json.dumps({"solved_puzzles": "micro-1"}))  # not a list at all
    assert settings.load(path)["solved_puzzles"] == []


def test_changing_loaded_settings_never_changes_the_defaults(tmp_path):
    loaded = settings.load(tmp_path / "missing.json")
    loaded["solved_puzzles"].append("micro-1")
    assert settings.DEFAULTS["solved_puzzles"] == []
