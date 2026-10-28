import copy
from functools import lru_cache

class GameState:
    def __init__(self):
        self.board = [
            ["black_king", "black_knight", "black_bishop", "black_rook"],
            ["black_pawn", "--", "--", "--"],
            ["--", "--", "--", "--"],
            ["--", "--", "--", "white_pawn"],
            ["white_rook", "white_bishop", "white_knight", "white_king"]
        ]
        self.white_to_move = True
        self.white_king_location = (4, 3)
        self.black_king_location = (0, 0)
        self.checkmate = False
        self.stalemate = False

    def get_valid_moves(self):
        moves = []
        for r in range(len(self.board)):
            for c in range(len(self.board[r])):
                piece = self.board[r][c]
                if piece != "--" and \
                   ((piece.startswith("white") and self.white_to_move) or
                    (piece.startswith("black") and not self.white_to_move)):

                    if piece.endswith("pawn"):
                        self.get_pawn_moves(r, c, moves)
                    elif piece.endswith("knight"):
                        self.get_knight_moves(r, c, moves)
                    elif piece.endswith("rook"):
                        self.get_rook_moves(r, c, moves)
                    elif piece.endswith("bishop"):
                        self.get_bishop_moves(r, c, moves)
                    elif piece.endswith("king"):
                        self.get_king_moves(r, c, moves)
        
        # Check for game end conditions
        if len(moves) == 0:
            if self.in_check():
                self.checkmate = True
            else:
                self.stalemate = True
        
        return moves

    def get_pawn_moves(self, r, c, moves):
        direction = -1 if self.white_to_move else 1
        promotion_row = 0 if self.white_to_move else 4
        
        # Forward move
        if 0 <= r + direction < 5 and self.board[r + direction][c] == "--":
            if r + direction == promotion_row:
                # Promotion - just promote to queen for simplicity
                moves.append(Move((r, c), (r + direction, c), self.board, is_promotion=True))
            else:
                moves.append(Move((r, c), (r + direction, c), self.board))
                
        # Capture moves
        for dc in [-1, 1]:
            nr, nc = r + direction, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
                target = self.board[nr][nc]
                if target != "--" and target.startswith("white" if not self.white_to_move else "black"):
                    if nr == promotion_row:
                        moves.append(Move((r, c), (nr, nc), self.board, is_promotion=True))
                    else:
                        moves.append(Move((r, c), (nr, nc), self.board))

    def get_knight_moves(self, r, c, moves):
        knight_moves = [(2,1),(2,-1),(-2,1),(-2,-1),(1,2),(1,-2),(-1,2),(-1,-2)]
        ally = "white" if self.white_to_move else "black"
        for dr, dc in knight_moves:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--" or not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))

    def get_rook_moves(self, r, c, moves):
        directions = [(-1,0),(1,0),(0,-1),(0,1)]
        ally = "white" if self.white_to_move else "black"
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--":
                    moves.append(Move((r, c), (nr, nc), self.board))
                elif not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))
                    break
                else:
                    break
                nr += dr
                nc += dc

    def get_bishop_moves(self, r, c, moves):
        directions = [(-1,-1),(-1,1),(1,-1),(1,1)]
        ally = "white" if self.white_to_move else "black"
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--":
                    moves.append(Move((r, c), (nr, nc), self.board))
                elif not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))
                    break
                else:
                    break
                nr += dr
                nc += dc

    def get_king_moves(self, r, c, moves):
        king_moves = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
        ally = "white" if self.white_to_move else "black"
        for dr, dc in king_moves:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 4:
                if self.board[nr][nc] == "--" or not self.board[nr][nc].startswith(ally):
                    moves.append(Move((r, c), (nr, nc), self.board))

    def in_check(self):
        """Check if current player's king is in check"""
        king_row = self.white_king_location[0] if self.white_to_move else self.black_king_location[0]
        king_col = self.white_king_location[1] if self.white_to_move else self.black_king_location[1]
        enemy = "black" if self.white_to_move else "white"
        
        # Check if any enemy piece can attack the king
        for r in range(5):
            for c in range(4):
                piece = self.board[r][c]
                if piece != "--" and piece.startswith(enemy):
                    if self.can_attack(r, c, king_row, king_col):
                        return True
        return False

    def can_attack(self, from_r, from_c, to_r, to_c):
        """Check if piece at from_r,from_c can attack to_r,to_c"""
        piece = self.board[from_r][from_c]
        
        if piece.endswith("pawn"):
            direction = 1 if piece.startswith("black") else -1
            if from_r + direction == to_r and abs(from_c - to_c) == 1:
                return True
        elif piece.endswith("knight"):
            dr, dc = abs(from_r - to_r), abs(from_c - to_c)
            if (dr == 2 and dc == 1) or (dr == 1 and dc == 2):
                return True
        elif piece.endswith("rook"):
            if from_r == to_r or from_c == to_c:
                return self.clear_path(from_r, from_c, to_r, to_c)
        elif piece.endswith("bishop"):
            if abs(from_r - to_r) == abs(from_c - to_c):
                return self.clear_path(from_r, from_c, to_r, to_c)
        elif piece.endswith("king"):
            if abs(from_r - to_r) <= 1 and abs(from_c - to_c) <= 1:
                return True
        return False

    def clear_path(self, from_r, from_c, to_r, to_c):
        """Check if path is clear between two positions"""
        dr = 0 if from_r == to_r else (1 if to_r > from_r else -1)
        dc = 0 if from_c == to_c else (1 if to_c > from_c else -1)
        
        r, c = from_r + dr, from_c + dc
        while (r, c) != (to_r, to_c):
            if self.board[r][c] != "--":
                return False
            r += dr
            c += dc
        return True

    def make_move(self, move):
        # Check if king is being captured - game over
        if move.piece_captured.endswith("king"):
            self.checkmate = True
        
        self.board[move.start_row][move.start_col] = "--"
        
        # Handle pawn promotion
        if move.is_promotion and move.piece_moved.endswith("pawn"):
            color = "white" if move.piece_moved.startswith("white") else "black"
            self.board[move.end_row][move.end_col] = f"{color}_knight"  # Promote to knight
        else:
            self.board[move.end_row][move.end_col] = move.piece_moved
        
        # Update king positions
        if move.piece_moved == "white_king":
            self.white_king_location = (move.end_row, move.end_col)
        elif move.piece_moved == "black_king":
            self.black_king_location = (move.end_row, move.end_col)
            
        self.white_to_move = not self.white_to_move

    def undo_move(self, move):
        """Undo a move - needed for minimax algorithm"""
        self.board[move.start_row][move.start_col] = move.piece_moved
        self.board[move.end_row][move.end_col] = move.piece_captured
        
        # Update king positions
        if move.piece_moved == "white_king":
            self.white_king_location = (move.start_row, move.start_col)
        elif move.piece_moved == "black_king":
            self.black_king_location = (move.start_row, move.start_col)
            
        self.white_to_move = not self.white_to_move
        self.checkmate = False
        self.stalemate = False


class Move:
    def __init__(self, start_sq, end_sq, board, is_promotion=False):
        self.start_row, self.start_col = start_sq
        self.end_row, self.end_col = end_sq
        self.piece_moved = board[self.start_row][self.start_col]
        self.piece_captured = board[self.end_row][self.end_col]
        self.is_promotion = is_promotion

    def __eq__(self, other):
        return (self.start_row, self.start_col, self.end_row, self.end_col) == \
               (other.start_row, other.start_col, other.end_row, other.end_col)


# ============================================================================
# AI IMPLEMENTATION USING MINIMAX + ALPHA-BETA PRUNING
# ============================================================================

# Piece values for evaluation
PIECE_VALUES = {'pawn': 1, 'knight': 3, 'bishop': 3, 'rook': 5, 'king': 1000}

@lru_cache(maxsize=1000)
def get_piece_value(piece):
    """Get numerical value of a piece (cached for performance)"""
    if piece == "--":
        return 0
    return PIECE_VALUES.get(piece.split('_')[1], 0)

def evaluate_board(game_state):
    """Evaluate board position: Positive = good for White, Negative = good for Black"""
    if game_state.checkmate:
        return -9999 if game_state.white_to_move else 9999
    if game_state.stalemate:
        return 0
    
    # Material evaluation
    score = sum(
        get_piece_value(piece) if piece.startswith("white") else -get_piece_value(piece)
        for row in game_state.board for piece in row if piece != "--"
    )
    return score

def minimax_alpha_beta(game_state, depth, alpha, beta, maximizing_player):
    """
    Minimax Algorithm with Alpha-Beta Pruning
    
    Args:
        game_state: Current game position
        depth: How many moves to look ahead
        alpha: Best value maximizing player can guarantee
        beta: Best value minimizing player can guarantee
        maximizing_player: True if maximizing (White), False if minimizing (Black)
    
    Returns:
        Best evaluation score for current position
    """
    # Base case: reached max depth or game over
    if depth == 0 or game_state.checkmate or game_state.stalemate:
        return evaluate_board(game_state)
    
    valid_moves = game_state.get_valid_moves()
    
    if maximizing_player:  # White's turn (maximize score)
        max_eval = float('-inf')
        for move in valid_moves:
            game_state.make_move(move)
            eval_score = minimax_alpha_beta(game_state, depth - 1, alpha, beta, False)
            game_state.undo_move(move)
            
            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)
            
            # Alpha-Beta Pruning: Cut off if beta <= alpha
            if beta <= alpha:
                break
        return max_eval
    
    else:  # Black's turn (minimize score)
        min_eval = float('inf')
        for move in valid_moves:
            game_state.make_move(move)
            eval_score = minimax_alpha_beta(game_state, depth - 1, alpha, beta, True)
            game_state.undo_move(move)
            
            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)
            
            # Alpha-Beta Pruning: Cut off if beta <= alpha
            if beta <= alpha:
                break
        return min_eval

def get_ai_move(game_state, depth=3):
    """
    Main AI function - Get the best move using Minimax + Alpha-Beta Pruning
    Can be called from anywhere in the code when AI move is needed
    
    Args:
        game_state: Current game state
        depth: Search depth (default 3)
    
    Returns:
        Best move for current player, or None if no moves available
    """
    valid_moves = game_state.get_valid_moves()
    if not valid_moves:
        return None
    
    best_move = None
    best_score = float('inf')  # Black wants to minimize score
    
    # Evaluate each possible move
    for move in valid_moves:
        game_state.make_move(move)
        # Get score from White's perspective (maximizing player)
        score = minimax_alpha_beta(game_state, depth - 1, float('-inf'), float('inf'), True)
        game_state.undo_move(move)
        
        # Black chooses move with lowest score
        if score < best_score:
            best_score = score
            best_move = move
    
    return best_move