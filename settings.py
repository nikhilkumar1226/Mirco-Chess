"""The player's settings, remembered between launches in a small JSON file in their home folder."""

import copy
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
    # Remembered as you play
    "solved_puzzles": [],  # the ids of the puzzles solved so far
    "custom_boards": [],  # position codes of the boards saved in the board editor
}
# Settings that can only take some values
CHOICES = {
    "variant_key": tuple(VARIANTS),
    "difficulty": tuple(DIFFICULTY_DEPTHS),
    "clock": (0, 1, 3, 5, 10),
}


def load(path=None):
    """The saved settings, with the default for anything missing, unknown or unreadable"""
    settings = copy.deepcopy(DEFAULTS)  # a copy of the lists too, so changing them never changes the defaults
    try:
        with open(path or SETTINGS_PATH) as file:
            saved = json.load(file)
    except Exception:  # missing, damaged, or (in a browser) no files to read at all
        return settings
    if isinstance(saved, dict):
        for key, value in saved.items():
            if key in DEFAULTS and type(value) is type(DEFAULTS[key]) and value in CHOICES.get(key, (value,)):
                if isinstance(value, list):
                    value = [item for item in value if isinstance(item, str)]
                settings[key] = value
    return settings


def save(settings, path=None):
    try:
        with open(path or SETTINGS_PATH, "w") as file:
            json.dump(settings, file, indent=2)
    except Exception:
        pass  # e.g. a read-only home folder, or a browser: the settings just aren't remembered
