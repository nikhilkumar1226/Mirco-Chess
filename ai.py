"""Micro Chess AI: picks moves with minimax search and alpha-beta pruning."""

import random
from functools import lru_cache


# ============================================================================
# AI IMPLEMENTATION USING MINIMAX + ALPHA-BETA PRUNING
# ============================================================================

# How many moves (plies) ahead the AI looks at each difficulty level
DIFFICULTY_DEPTHS = {"easy": 2, "medium": 4, "hard": 6}

# Score for checkmate. A mate found sooner scores higher, so the AI goes for the fastest win
MATE_SCORE = 10000

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

def move_priority(move):
    """How promising a move looks before searching it (higher = search it earlier)"""
    priority = 0
    if move.piece_captured != "--":
        # Capture the most valuable piece, preferably with the least valuable one
        attacker = 0 if move.piece_moved.endswith("king") else get_piece_value(move.piece_moved)
        priority += 100 + 10 * get_piece_value(move.piece_captured) - attacker
    if move.is_promotion:
        priority += 50 + PIECE_VALUES[move.promotion_piece]
    return priority

def order_moves(moves):
    """Sort moves so captures and promotions come first.

    Alpha-beta pruning cuts off far more of the search when good moves are tried first.
    """
    return sorted(moves, key=move_priority, reverse=True)

def legal_moves_in_order(game_state):
    """Yield the legal moves, most promising first.

    Each move is only checked for legality (does it leave our king in check?)
    when the search actually reaches it, so moves skipped by pruning cost nothing.
    """
    for move in order_moves(game_state.get_all_possible_moves()):
        game_state.make_move(move)
        legal = not game_state.is_king_attacked(white=not game_state.white_to_move)
        game_state.undo_move(move)
        if legal:
            yield move

def minimax_alpha_beta(game_state, depth, alpha, beta, maximizing_player, ply=1):
    """
    Minimax Algorithm with Alpha-Beta Pruning

    Args:
        game_state: Current game position
        depth: How many moves to look ahead
        alpha: Best value maximizing player can guarantee
        beta: Best value minimizing player can guarantee
        maximizing_player: True if maximizing (White), False if minimizing (Black)
        ply: How many moves deep we already are (used to prefer faster mates)

    Returns:
        Best evaluation score for current position
    """
    # Draws by repetition or bare kings
    if game_state.is_threefold_repetition() or game_state.is_insufficient_material():
        return 0

    # Base case: reached max depth
    if depth == 0:
        return evaluate_board(game_state)

    found_legal_move = False

    if maximizing_player:  # White's turn (maximize score)
        max_eval = float('-inf')
        for move in legal_moves_in_order(game_state):
            found_legal_move = True
            game_state.make_move(move)
            eval_score = minimax_alpha_beta(game_state, depth - 1, alpha, beta, False, ply + 1)
            game_state.undo_move(move)

            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)

            # Alpha-Beta Pruning: Cut off if beta <= alpha
            if beta <= alpha:
                break
        best = max_eval

    else:  # Black's turn (minimize score)
        min_eval = float('inf')
        for move in legal_moves_in_order(game_state):
            found_legal_move = True
            game_state.make_move(move)
            eval_score = minimax_alpha_beta(game_state, depth - 1, alpha, beta, True, ply + 1)
            game_state.undo_move(move)

            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)

            # Alpha-Beta Pruning: Cut off if beta <= alpha
            if beta <= alpha:
                break
        best = min_eval

    if not found_legal_move:
        if game_state.in_check():
            # Checkmate: the side to move has lost. Subtracting ply makes a
            # quicker mate worth more than a slower one
            return -(MATE_SCORE - ply) if game_state.white_to_move else MATE_SCORE - ply
        return 0  # Stalemate is a draw
    return best

def get_ai_move(game_state, difficulty="medium", depth=None, rng=None):
    """
    Main AI function - Get the best move using Minimax + Alpha-Beta Pruning
    Works for whichever side is to move, so the AI can play White or Black.

    Args:
        game_state: Current game state
        difficulty: "easy", "medium" or "hard" (sets how deep the AI searches)
        depth: Optional exact search depth, overrides difficulty
        rng: Optional random.Random, used to choose between equally good moves

    Returns:
        Best move for current player, or None if no moves available
    """
    if depth is None:
        if difficulty not in DIFFICULTY_DEPTHS:
            raise ValueError(f"difficulty must be one of {list(DIFFICULTY_DEPTHS)}, not {difficulty!r}")
        depth = DIFFICULTY_DEPTHS[difficulty]
    rng = rng or random

    valid_moves = game_state.get_valid_moves()
    if not valid_moves:
        return None

    # White wants the highest score, Black the lowest
    ai_is_white = game_state.white_to_move
    best_moves = []
    best_score = float('-inf') if ai_is_white else float('inf')

    # Evaluate each possible move
    for move in order_moves(valid_moves):
        game_state.make_move(move)
        # After our move it's the opponent's turn: they maximize if they are White.
        # The window stops one point short of the best score so far: that still prunes
        # worse moves, but moves exactly as good get their exact score (scores are
        # whole numbers), so we can spot ties.
        if ai_is_white:
            score = minimax_alpha_beta(game_state, depth - 1, best_score - 1, float('inf'), False)
        else:
            score = minimax_alpha_beta(game_state, depth - 1, float('-inf'), best_score + 1, True)
        game_state.undo_move(move)

        if (ai_is_white and score > best_score) or (not ai_is_white and score < best_score):
            best_score = score
            best_moves = [move]
        elif score == best_score:
            best_moves.append(move)

    # Several moves can be equally good: pick one at random so games differ
    return rng.choice(best_moves)
