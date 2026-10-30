# play_terminal.py - play Micro Chess in the terminal against the AI
import sys
from chess_engine import GameState
from ai import get_ai_move, DIFFICULTY_DEPTHS

# Board settings
ROWS, COLS = 5, 4

# Mapping your piece names to simple chars for terminal display
PIECE_SYMBOLS = {
    "white_king": "K", "white_rook": "R", "white_bishop": "B", "white_knight": "N", "white_pawn": "P",
    "black_king": "k", "black_rook": "r", "black_bishop": "b", "black_knight": "n", "black_pawn": "p",
    "--": "."
}

def print_board(board):
    print("   a b c d")
    print("  +" + "--"*COLS + "+")
    for r in range(ROWS):
        row_str = str(ROWS - r) + " |"
        for c in range(COLS):
            piece = board[r][c]
            row_str += PIECE_SYMBOLS.get(piece, "?") + " "
        row_str += "|"
        print(row_str)
    print("  +" + "--"*COLS + "+")

FILES = "abcd"   # columns, left to right
RANKS = "12345"  # rows, numbered from the bottom (1) to the top (5)

def parse_square(text):
    """Convert a square like 'b3' to (row, col). Returns None if it isn't on the board."""
    if len(text) != 2 or text[0] not in FILES or text[1] not in RANKS:
        return None
    return ROWS - int(text[1]), FILES.index(text[0])

def parse_move(move_str):
    """Convert input like 'a2 a3' to ((row1, col1), (row2, col2)), or (None, None) if invalid."""
    parts = move_str.strip().lower().split()
    if len(parts) != 2:
        return None, None
    start, end = parse_square(parts[0]), parse_square(parts[1])
    if start is None or end is None:
        return None, None
    return start, end

def move_to_notation(move):
    """Convert move object back to notation for display"""
    cols = ['a', 'b', 'c', 'd']
    start_notation = cols[move.start_col] + str(ROWS - move.start_row)
    end_notation = cols[move.end_col] + str(ROWS - move.end_row)
    if move.is_promotion:
        return f"{start_notation} {end_notation} (promotes to {move.promotion_piece})"
    if move.is_castle:
        return f"{start_notation} {end_notation} (castles)"
    return f"{start_notation} {end_notation}"

PROMOTION_CHOICES = {"r": "rook", "b": "bishop", "n": "knight"}

def ask_promotion_piece():
    """Ask the human which piece their pawn should become"""
    while True:
        answer = input("Promote to (r)ook, (b)ishop or k(n)ight? ").strip().lower()
        if answer in PROMOTION_CHOICES:
            return PROMOTION_CHOICES[answer]
        print("Please type r, b or n.")

def find_legal_moves(gs, start_sq, end_sq):
    """The engine's own legal moves from start_sq to end_sq (empty list if that move is illegal).

    We use the engine's Move objects (instead of building a new one) so details
    like pawn promotion are kept.
    """
    return [m for m in gs.get_valid_moves()
            if (m.start_row, m.start_col) == start_sq and (m.end_row, m.end_col) == end_sq]

def game_over_message(gs, result):
    """Text to show when the game ends (result comes from gs.get_game_result())"""
    if result == "checkmate":
        winner = "Black" if gs.white_to_move else "White"
        return f"Checkmate! {winner} wins!"
    if result == "stalemate":
        return "Stalemate! It's a draw."
    if result == "repetition":
        return "Draw by threefold repetition."
    return "Draw - only the two kings are left."

def ask_choice(question, choices, default):
    """Ask until the answer is one of the choices' first letters (Enter picks the default)"""
    options = "/".join(choices)
    while True:
        answer = input(f"{question} ({options}) [{default}]: ").strip().lower()
        if answer == "":
            return default
        for choice in choices:
            if answer in (choice, choice[0]):
                return choice
        print(f"Please type one of: {options}")

def main():
    gs = GameState()

    print("Welcome to Terminal Micro Chess!")
    print("Moves format: 'a2 a3' (from-square to-square). Files: a-d, Ranks: 1-5")
    print("To castle, type the king's move: 'd1 b1' for White, 'a5 c5' for Black.")
    print("Enter 'quit' to exit.\n")

    human_color = ask_choice("Play as", ["white", "black"], "white")
    difficulty = ask_choice("Difficulty", list(DIFFICULTY_DEPTHS), "medium")
    human_is_white = human_color == "white"
    print(f"\nYou play {human_color.title()}, the AI plays {'Black' if human_is_white else 'White'} ({difficulty}).\n")

    while True:
        print_board(gs.board)
        result = gs.get_game_result()
        if result is not None:
            print(game_over_message(gs, result))
            break
        if gs.in_check():
            print("Check!")

        side = "White" if gs.white_to_move else "Black"
        if gs.white_to_move == human_is_white:
            # Human player
            print(f"{side}'s move:")
            move_input = input("Enter your move: ").strip()
            if move_input.lower() == "quit":
                print("Thanks for playing!")
                sys.exit()

            start_sq, end_sq = parse_move(move_input)
            if start_sq is None or end_sq is None:
                print("Invalid move format. Please enter moves like 'a2 a3'.\n")
                continue

            legal = find_legal_moves(gs, start_sq, end_sq)
            if not legal:
                print("Invalid move. Try again.\n")
                continue

            move = legal[0]
            if move.is_promotion:
                piece = ask_promotion_piece()
                move = next(m for m in legal if m.promotion_piece == piece)
            gs.make_move(move)
            print(f"{side} played: {move_to_notation(move)}\n")
        else:
            # AI player
            print(" .....thinking....")

            best_move = get_ai_move(gs, difficulty)
            gs.make_move(best_move)  # never None here: the game would already be over
            print(f"{side} played: {move_to_notation(best_move)}\n")

if __name__ == "__main__":
    main()
