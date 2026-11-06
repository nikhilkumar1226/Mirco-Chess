"""Position codes and game codes: a game written as one line of text."""

import random

import pytest

from chess_engine import GameState, VARIANTS, DONUT, read_game_code, write_game_code, move_code
from helpers import position, find_move


def random_position(variant, rng, moves):
    gs = GameState(variant=variant)
    for _ in range(moves):
        legal = gs.get_valid_moves()
        if not legal:
            break
        gs.make_move(rng.choice(legal))
    return gs


@pytest.mark.parametrize("key, code", [
    ("micro", "micro knbr/p.../..../...P/RBNK w WB"),
    ("tiny", "tiny kbrn/.p../..P./NRBK w -"),
    ("donut", "donut rn.bk/pp.../..#../...PP/KB.NR w -"),
    ("pillars", "pillars k.nrb/p...p/.#.#./P...P/BRN.K w -"),
])
def test_starting_positions(key, code):
    assert GameState(variant=VARIANTS[key]).to_code() == code


@pytest.mark.parametrize("variant", list(VARIANTS.values()), ids=lambda v: v.key)
def test_positions_survive_the_round_trip(variant):
    rng = random.Random(6)
    for _ in range(25):
        gs = random_position(variant, rng, rng.randrange(0, 20))
        copy = GameState.from_code(gs.to_code())
        assert copy.board == gs.board and copy.white_to_move == gs.white_to_move
        assert copy.castling_rights == gs.castling_rights and copy.variant is gs.variant
        assert copy.to_code() == gs.to_code()


def test_castling_rights_are_part_of_the_code():
    gs = GameState()
    for start, end in [("c1", "a2"), ("b5", "d4"), ("d1", "c1")]:  # White's king leaves its corner
        gs.make_move(find_move(gs.get_valid_moves(), start, end)[0])
    assert gs.to_code().endswith(" b B")
    assert GameState.from_code(gs.to_code()).castling_rights == {"black"}


def test_custom_boards():
    gs = GameState.from_code("custom k..../.#.../...../...#./....K b -")
    assert gs.variant.key == "custom" and (gs.rows, gs.cols) == (5, 5) and not gs.white_to_move
    assert gs.castling_rights == frozenset()
    # Holes can make a lone knight's mate possible, so on boards with holes it isn't a draw
    assert not gs.variant.lone_knight_draws
    assert GameState.from_code("custom k.../..../..../...K w -").variant.lone_knight_draws


@pytest.mark.parametrize("code, problem", [
    ("micro knbr/p.../..../...P/RBNK w", "four parts"),
    ("giant knbr/p.../..../...P/RBNK w -", "Unknown board"),
    ("micro knbr/p.../..../...P/RBNX w WB", "Unknown letter"),
    ("micro knbr/p.../...../...P/RBNK w WB", "same number"),
    ("donut rn.bk/pp.../.....//...PP/KB.NR w -", "same number"),
    ("donut rn.bk/pp.../...../...PP/KB.NR w -", "shape of the Donut"),
    ("micro knbr/p.../..../...P/RBNK x WB", "w or b"),
    ("micro knbr/p.../..../...P/RBNK w KQ", "WB, W, B or -"),
    ("micro knbr/p.../..../...P/RBN. w WB", "White needs exactly one king"),
    ("micro knbk/p.../..../...P/RBNK w -", "Black needs exactly one king"),
    ("micro knbr/p.../..../...P/RBKN w WB", "can't castle"),
    ("micro knbP/p.../..../...P/RBNK w B", "last rank"),
    ("micro k..r/..../..../..../...K b -", "White is in check, but it's Black's move"),
    ("custom k./.K w -", "4x4, 4x5 or 5x5"),
])
def test_codes_that_make_no_sense_are_refused(code, problem):
    with pytest.raises(ValueError, match=problem):
        GameState.from_code(code)


def test_any_text_gives_a_position_or_a_clear_error():
    rng = random.Random(3)
    for _ in range(500):
        text = "".join(rng.choice("micro donut custom kKnNrRpP.#/ wb-WB124") for _ in range(rng.randrange(0, 40)))
        try:
            read_game_code(text)
        except ValueError:
            pass


def test_a_game_code_replays_the_game():
    rng = random.Random(2)
    for variant in VARIANTS.values():
        start = GameState(variant=variant)
        game = GameState(variant=variant)
        played = []
        for _ in range(30):
            legal = game.get_valid_moves()
            if not legal:
                break
            played.append(rng.choice(legal))
            game.make_move(played[-1])
        code = write_game_code(start, played)
        start_again, moves = read_game_code(code)
        assert start_again.to_code() == start.to_code() and moves == played
        assert write_game_code(start_again, moves) == code


def test_game_codes_write_promotions_and_castling():
    gs = position({"a5": "black_king", "c4": "white_pawn", "b3": "white_king"})
    promotion = [m for m in gs.get_valid_moves() if m.is_promotion and m.promotion_piece == "knight"][0]
    assert move_code(promotion, gs.rows) == "c4c5n"
    code = write_game_code(gs, [promotion])
    assert read_game_code(code)[1] == [promotion]

    gs = position({"d5": "black_king", "a1": "white_rook", "d1": "white_king"})
    castle = [m for m in gs.get_valid_moves() if m.is_castle][0]
    assert move_code(castle, gs.rows) == "d1b1"
    assert read_game_code(write_game_code(gs, [castle]))[1][0].is_castle


def test_an_illegal_move_in_a_game_code_is_refused():
    with pytest.raises(ValueError, match="c1c4 isn't a legal move"):
        read_game_code("micro knbr/p.../..../...P/RBNK w WB c1c4")


def test_a_knight_can_not_land_on_a_hole_in_a_game_code():
    # On the Donut board the knight on d1 could jump to c3, but c3 is a hole
    with pytest.raises(ValueError, match="d1c3"):
        read_game_code(GameState(variant=DONUT).to_code() + " d1c3")
