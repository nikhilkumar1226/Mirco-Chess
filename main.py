# main_terminal.py
import sys
from chess_engine import GameState, Move, get_ai_move

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

def parse_move(move_str):
    #Convert input like 'a2 a3' to ((row1,col1), (row2,col2))
    try:
        start, end = move_str.strip().lower().split()
        cols = {'a':0, 'b':1, 'c':2, 'd':3}
        # Rows are numbered from bottom (1) to top (5)
        start_col = cols[start[0]]
        start_row = ROWS - int(start[1])
        end_col = cols[end[0]]
        end_row = ROWS - int(end[1])
        return (start_row, start_col), (end_row, end_col)
    except Exception:
        return None, None

def move_to_notation(move):
    """Convert move object back to notation for display"""
    cols = ['a', 'b', 'c', 'd']
    start_notation = cols[move.start_col] + str(ROWS - move.start_row)
    end_notation = cols[move.end_col] + str(ROWS - move.end_row)
    return f"{start_notation} {end_notation}"

def main():
    gs = GameState()

    print("Welcome to Terminal Micro Chess!")
    print("You play as White, AI plays as Black")
    print("Moves format: 'a2 a3' (from-square to-square). Files: a-d, Ranks: 1-5")
    print("Enter 'quit' to exit.\n")

    while True:
        print_board(gs.board)
        if gs.checkmate:
            winner = "Black" if gs.white_to_move else "White"
            print(f"Checkmate! {winner} wins!")
            break
        if gs.stalemate:
            print("Stalemate! It's a draw.")
            break

        if gs.white_to_move:
            # Human player (White)
            print("White's move:")
            move_input = input("Enter your move: ").strip()
            if move_input.lower() == "quit":
                print("Thanks for playing!")
                sys.exit()

            start_sq, end_sq = parse_move(move_input)
            if start_sq is None or end_sq is None:
                print("Invalid move format. Please enter moves like 'a2 a3'.\n")
                continue

            move = Move(start_sq, end_sq, gs.board)
            valid_moves = gs.get_valid_moves()

            if move not in valid_moves:
                print("Invalid move. Try again.\n")
                continue

            gs.make_move(move)
            print(f"White played: {move_input}\n")
        else:
            # AI player (Black)
            print(" .....thinking....")
            
            best_move = get_ai_move(gs, depth=3)  # Simply call the AI function
            if best_move:
                gs.make_move(best_move)
                move_notation = move_to_notation(best_move)
                print(f"Black played: {move_notation}\n")
            else:
                print("AI has no valid moves!\n")
                break

if __name__ == "__main__":
    main()