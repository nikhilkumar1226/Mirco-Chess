import pytest

from main import parse_move


def test_valid_move_is_parsed():
    # a2 is row 3, column 0 and a3 is row 2, column 0 (row 0 is rank 5 at the top)
    assert parse_move("a2 a3") == ((3, 0), (2, 0))
    assert parse_move("  D1 c2  ") == ((4, 3), (3, 2))


@pytest.mark.parametrize("text", [
    "a0 a1",      # rank 0 doesn't exist (this used to crash with IndexError)
    "a6 a5",      # rank 6 doesn't exist
    "e2 e3",      # file e doesn't exist
    "a10 a1",     # too many characters
    "a2",         # only one square
    "a2 a3 a4",   # too many squares
    "",           # nothing typed
    "hello",
])
def test_invalid_input_is_rejected(text):
    assert parse_move(text) == (None, None)
