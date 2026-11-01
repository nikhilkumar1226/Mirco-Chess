"""The player's settings, remembered between launches in a small JSON file in their home folder."""

import json
import os

from ai import DIFFICULTY_DEPTHS
from chess_engine import VARIANTS

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".micro_chess.json")

# Every setting, with its value until the player changes it
DEFAULTS = {
    # Chosen on the start menu
    "variant_key": "micro",
    "two_players": False,
    "human_is_white": True,
    "difficulty": "medium",
    # Switched on and off on the settings screen
    "sound": True,
    "show_moves": True,  # dots on the squares the selected piece can move to
    "animations": True,
    "hints": True,
    "coordinates": True,
    "confirm_quit": True,
    "eval_bar": False,
    "review": True,
    "clock": 0,  # minutes on each player's clock, or 0 for no clock
}
# Settings that can only take some values
CHOICES = {
    "variant_key": tuple(VARIANTS),
    "difficulty": tuple(DIFFICULTY_DEPTHS),
    "clock": (0, 1, 3, 5, 10),
}


def load(path=None):
    """The saved settings, with the default for anything missing, unknown or unreadable"""
    settings = dict(DEFAULTS)
    try:
        with open(path or SETTINGS_PATH) as file:
            saved = json.load(file)
    except (OSError, ValueError):
        return settings
    if isinstance(saved, dict):
        for key, value in saved.items():
            if key in DEFAULTS and type(value) is type(DEFAULTS[key]) and value in CHOICES.get(key, (value,)):
                settings[key] = value
    return settings


def save(settings, path=None):
    try:
        with open(path or SETTINGS_PATH, "w") as file:
            json.dump(settings, file, indent=2)
    except OSError:
        pass  # e.g. a read-only home folder: the settings just aren't remembered
