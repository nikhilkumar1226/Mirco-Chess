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
