"""Micro Chess AI: picks moves with minimax search and alpha-beta pruning."""

from functools import lru_cache


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
    # Draws by repetition or bare kings
    if game_state.is_threefold_repetition() or game_state.is_insufficient_material():
        return 0

    # Base case: reached max depth
    if depth == 0:
        return evaluate_board(game_state)

    valid_moves = game_state.get_valid_moves()
    if not valid_moves:
        if game_state.in_check():
            # Checkmate: the side to move has lost
            return -9999 if game_state.white_to_move else 9999
        return 0  # Stalemate is a draw

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
