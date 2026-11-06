"""Wins, draws and losses against the computer, and a rating, remembered between launches
in a small JSON file next to the settings."""

import json
import os

STATS_PATH = os.path.join(os.path.expanduser("~"), ".micro_chess_stats.json")

START_RATING = 1000
LEVEL_RATINGS = {"easy": 800, "medium": 1200, "hard": 1600}  # the computer's fixed rating at each level
K_FACTOR = 32  # the most one game can move the rating
RESULTS = ("wins", "draws", "losses")


def fresh_stats():
    """No games yet: {"rating": 1000, "games": {"micro/easy": {"wins": 0, "draws": 0, "losses": 0}, ...}}"""
    return {"rating": START_RATING, "games": {}}


def is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def load(path=None):
    """The saved stats, or fresh ones if the file is missing or damaged. Anything odd in it is
    left out, so a damaged file never stops the game from starting."""
    stats = fresh_stats()
    try:
        with open(path or STATS_PATH) as file:
            saved = json.load(file)
    except Exception:  # missing, damaged, or (in a browser) no files to read at all
        return stats
    if not isinstance(saved, dict):
        return stats
    if is_count(saved.get("rating")):
        stats["rating"] = saved["rating"]
    games = saved.get("games")
    if isinstance(games, dict):
        for key, counts in games.items():
            if isinstance(counts, dict) and all(is_count(counts.get(result, 0)) for result in RESULTS):
                stats["games"][key] = {result: counts.get(result, 0) for result in RESULTS}
    return stats


def save(stats, path=None):
    try:
        with open(path or STATS_PATH, "w") as file:
            json.dump(stats, file, indent=2)
    except Exception:
        pass  # e.g. a read-only home folder, or a browser: the stats just aren't remembered


def expected_score(rating, opponent):
    """The Elo expectation: 0.5 against an equal opponent, more against a weaker one"""
    return 1 / (1 + 10 ** ((opponent - rating) / 400))


def new_rating(rating, opponent, score):
    """The rating after a game scoring 1 (a win), 0.5 (a draw) or 0 (a loss) against `opponent`"""
    return round(rating + K_FACTOR * (score - expected_score(rating, opponent)))


def record(stats, board, difficulty, outcome):
    """Count a game against the computer ("win", "draw" or "loss") and update the rating"""
    counts = stats["games"].setdefault(f"{board}/{difficulty}", {result: 0 for result in RESULTS})
    counts[{"win": "wins", "draw": "draws", "loss": "losses"}[outcome]] += 1
    score = {"win": 1, "draw": 0.5, "loss": 0}[outcome]
    stats["rating"] = new_rating(stats["rating"], LEVEL_RATINGS[difficulty], score)


def counts_for(stats, board, difficulty):
    """(wins, draws, losses) on a board at a level"""
    counts = stats["games"].get(f"{board}/{difficulty}", {})
    return tuple(counts.get(result, 0) for result in RESULTS)
