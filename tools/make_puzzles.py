"""Make puzzles.json: positions with a forced mate in 1, 2 or 3 where only one first move wins.

It plays AI games on every board and looks at each position along the way. A position is
kept when exactly one first move forces mate in N and there's no quicker mate. The AI's
search finds them, and then a plain search through every move and reply (with no
evaluation and no shortcuts) checks each one before it's saved.

Run it from the repository's top folder:  python3 tools/make_puzzles.py
"""

import json
import os
import random
import sys

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOP)

from ai import mating_moves, search_move, get_ai_move  # noqa: E402
from chess_engine import GameState, VARIANTS, move_code  # noqa: E402

PUZZLES_PATH = os.path.join(TOP, "puzzles.json")
LONGEST_MATE = 3  # moves
PER_BOARD = 12  # puzzles from each board at most
PER_GAME = 2  # puzzles from any one game at most, so they aren't all alike
GAMES_PER_BOARD = 80


def forced_mate(game, moves):
    """A plain search: can the side to move force checkmate within `moves` of its moves?"""
    return any(mates_with(game, move, moves) for move in game.get_valid_moves())


def mates_with(game, move, moves):
    """A plain search: does `move` force checkmate within `moves` moves, whatever the replies?"""
    game.make_move(move)
    try:
        replies = game.get_valid_moves()
        if not replies:
            return game.in_check()  # checkmate; stalemate is only a draw
        if moves == 1:
            return False
        for reply in replies:
            game.make_move(reply)
            escaped = not forced_mate(game, moves - 1)
            game.undo_move(reply)
            if escaped:
                return False
        return True
    finally:
        game.undo_move(move)


def puzzle_in(game):
    """(mate in, the one winning move) if the position is a puzzle, otherwise None"""
    for moves in range(1, LONGEST_MATE + 1):
        winners = mating_moves(game, moves)
        if winners:
            return (moves, winners[0]) if len(winners) == 1 else None
    return None


def checked_by_plain_search(game, moves, winner):
    """The AI's search says `winner` is the only move that mates in `moves`: check it the slow way"""
    if moves > 1 and forced_mate(game, moves - 1):
        return False  # there's a quicker mate
    return [m for m in game.get_valid_moves() if mates_with(game, m, moves)] == [winner]


def solution(game, moves):
    """The winning line: the winning move, the AI's longest defence, the next winning move... to mate"""
    game = GameState.from_code(game.to_code())
    line = []
    for left in range(moves, 0, -1):
        # The quickest mate from here (it is never more than `left` moves away)
        winner = next(mating_moves(game, n)[0] for n in range(1, left + 1) if mating_moves(game, n))
        game.make_move(winner)
        line.append(move_code(winner, game.rows))
        if game.get_game_result() == "checkmate":
            return line
        defence = search_move(game, depth=2 * (left - 1), rng=random.Random(0)).move
        game.make_move(defence)
        line.append(move_code(defence, game.rows))
    raise AssertionError("the solution didn't end in checkmate")


def puzzles_from_board(variant, rng):
    found, seen = [], set()
    for game_number in range(GAMES_PER_BOARD):
        if len(found) >= PER_BOARD:
            break
        # A stronger side against a weaker one, so that mating attacks happen
        levels = ("medium", "easy") if game_number % 2 == 0 else ("easy", "medium")
        game = GameState(variant=variant)
        from_this_game = 0
        for ply in range(80):
            if game.get_game_result() or len(found) >= PER_BOARD or from_this_game >= PER_GAME:
                break
            position = GameState.from_code(game.to_code())  # just the position, without its history
            code = position.to_code()
            if ply >= 2 and code not in seen:
                seen.add(code)
                puzzle = puzzle_in(position)
                if puzzle and checked_by_plain_search(position, *puzzle):
                    moves = puzzle[0]
                    found.append({"code": code, "mate_in": moves, "solution": solution(position, moves)})
                    from_this_game += 1
                    print(f"  {variant.key}: mate in {moves}  {code}", flush=True)
            level = levels[0] if game.white_to_move else levels[1]
            game.make_move(get_ai_move(game, level, rng=rng))
    return found


def main():
    rng = random.Random(2026)
    puzzles = []
    for variant in VARIANTS.values():
        print(f"{variant.name}:", flush=True)
        puzzles += puzzles_from_board(variant, rng)
    # Easiest first: mate in 1, then 2, then 3
    puzzles.sort(key=lambda puzzle: (puzzle["mate_in"], list(VARIANTS).index(puzzle["code"].split()[0])))
    for number, puzzle in enumerate(puzzles, 1):
        puzzle["id"] = f"{puzzle['code'].split()[0]}-{number}"
    with open(PUZZLES_PATH, "w") as file:
        json.dump([{key: puzzle[key] for key in ("id", "code", "mate_in", "solution")} for puzzle in puzzles],
                  file, indent=1)
    counts = {n: sum(puzzle["mate_in"] == n for puzzle in puzzles) for n in range(1, LONGEST_MATE + 1)}
    print(f"Saved {len(puzzles)} puzzles to {PUZZLES_PATH}: " +
          ", ".join(f"{count} mate in {n}" for n, count in counts.items()))


if __name__ == "__main__":
    main()
