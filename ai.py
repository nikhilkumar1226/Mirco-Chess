"""Micro Chess AI: picks moves with minimax search and alpha-beta pruning."""

import random
from functools import lru_cache

from chess_engine import ROWS, COLS, KNIGHT_OFFSETS, ROOK_DIRECTIONS, BISHOP_DIRECTIONS


# ============================================================================
# AI IMPLEMENTATION USING MINIMAX + ALPHA-BETA PRUNING
# ============================================================================

# How many moves (plies) ahead the AI looks at each difficulty level
DIFFICULTY_DEPTHS = {"easy": 2, "medium": 4, "hard": 6}

# Score for checkmate, far above any normal evaluation (which stays within a few thousand).
# A mate found sooner scores higher, so the AI goes for the fastest win
MATE_SCORE = 100000

# Piece values in centipawns (a pawn is 100). Kings are never captured, so they count 0.
PIECE_VALUES = {'pawn': 100, 'knight': 300, 'bishop': 300, 'rook': 500, 'king': 0}

# Piece-square tables: a bonus (or penalty) for each piece depending on where it stands.
# Written from White's side with rank 5 at the top, like the board is printed. Black's
# pieces use the table turned around (a5 for Black is d1 for White), because the
# starting position looks the same from both sides that way.
# Every step is 5 or 10 points, so slightly different moves can still score exactly the same.
PAWN_TABLE = [
    [0, 0, 0, 0],          # rank 5: pawns promote as soon as they get here
    [30, 30, 30, 30],      # rank 4: one step from promoting
    [10, 10, 10, 10],      # rank 3
    [0, 0, 0, 0],          # rank 2: White's pawn starts here
    [0, 0, 0, 0],
]
KNIGHT_TABLE = [            # knights want the center, where they reach the most squares
    [-20, -10, -10, -20],
    [-10, 10, 10, -10],
    [-10, 15, 15, -10],
    [-10, 10, 10, -10],
    [-20, -10, -10, -20],
]
BISHOP_TABLE = [
    [-10, -5, -5, -10],
    [-5, 5, 5, -5],
    [-5, 10, 10, -5],
    [-5, 5, 5, -5],
    [-10, -5, -5, -10],
]
ROOK_TABLE = [
    [0, 0, 0, 0],
    [10, 10, 10, 10],      # rank 4: Black's pawn rank, the rook's favourite
    [0, 0, 0, 0],
    [0, 0, 0, 0],
    [0, 5, 5, 0],
]
# The king hides in its corner while there are pieces around to attack it
# (b1 is where it lands after castling), and heads for the center in the endgame
KING_MIDDLEGAME_TABLE = [
    [-30, -30, -30, -30],
    [-20, -20, -20, -20],
    [-10, -10, -10, -10],
    [0, 0, 0, 0],
    [10, 20, 10, 0],
]
KING_ENDGAME_TABLE = [
    [-10, 0, 0, -10],
    [0, 10, 10, 0],
    [0, 10, 10, 0],
    [0, 10, 10, 0],
    [-10, 0, 0, -10],
]
PIECE_TABLES = {'pawn': PAWN_TABLE, 'knight': KNIGHT_TABLE, 'bishop': BISHOP_TABLE, 'rook': ROOK_TABLE}

# Mobility: points for every square a piece can move to
MOBILITY_BONUS = {'knight': 4, 'bishop': 4, 'rook': 2}
# King safety: penalty for every attack by an enemy piece on the king's square or a square next to it
KING_ZONE_ATTACK_PENALTY = 10

# How far the game is from the endgame: knights and bishops count 1, rooks 2.
# The king's table slides from the middlegame one (all 8) to the endgame one (0).
PHASE_WEIGHTS = {'knight': 1, 'bishop': 1, 'rook': 2}
MAX_PHASE = 8


def on_board(r, c):
    return 0 <= r < ROWS and 0 <= c < COLS


def build_square_scores():
    """Material plus table bonus for every piece on every square, signed (+ White, - Black).

    Worked out once here so evaluating a position is just a lookup per piece.
    """
    scores = {}
    for kind, table in PIECE_TABLES.items():
        scores["white_" + kind] = [[PIECE_VALUES[kind] + table[r][c] for c in range(COLS)] for r in range(ROWS)]
        scores["black_" + kind] = [[-(PIECE_VALUES[kind] + table[ROWS - 1 - r][COLS - 1 - c])
                                    for c in range(COLS)] for r in range(ROWS)]
    return scores


def build_rays():
    """For every square and piece type, the lines of squares it attacks along (nearest first).

    A knight's "lines" are single squares; a rook or bishop stops at the first piece in each line.
    """
    rays = {}
    for r in range(ROWS):
        for c in range(COLS):
            rays['knight', r, c] = [[(r + dr, c + dc)] for dr, dc in KNIGHT_OFFSETS if on_board(r + dr, c + dc)]
            for kind, directions in (('rook', ROOK_DIRECTIONS), ('bishop', BISHOP_DIRECTIONS)):
                lines = []
                for dr, dc in directions:
                    line, nr, nc = [], r + dr, c + dc
                    while on_board(nr, nc):
                        line.append((nr, nc))
                        nr, nc = nr + dr, nc + dc
                    if line:
                        lines.append(line)
                rays[kind, r, c] = lines
    return rays


SQUARE_SCORES = build_square_scores()
RAYS = build_rays()
# The king's square and the squares around it
KING_ZONES = {(r, c): {(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if on_board(r + dr, c + dc)}
              for r in range(ROWS) for c in range(COLS)}


@lru_cache(maxsize=1000)
def get_piece_value(piece):
    """Get numerical value of a piece (cached for performance)"""
    if piece == "--":
        return 0
    return PIECE_VALUES.get(piece.split('_')[1], 0)


def king_square_score(table_row, table_col, phase):
    """The king's table bonus, blended between middlegame and endgame by the game phase"""
    middlegame = KING_MIDDLEGAME_TABLE[table_row][table_col]
    endgame = KING_ENDGAME_TABLE[table_row][table_col]
    return (middlegame * phase + endgame * (MAX_PHASE - phase)) // MAX_PHASE


def evaluate_board(game_state):
    """Evaluate board position: Positive = good for White, Negative = good for Black.

    The score is in centipawns and always a whole number. For each side it adds up:
    - material and piece-square tables (how much each piece is worth where it stands)
    - mobility: a small bonus for each square a knight, bishop or rook can move to
    - king safety: a penalty for each enemy attack on the squares around the king
    """
    board = game_state.board
    zones = {"white": KING_ZONES[game_state.white_king_location],
             "black": KING_ZONES[game_state.black_king_location]}
    score = 0
    phase = 0
    for r in range(ROWS):
        for c in range(COLS):
            piece = board[r][c]
            if piece == "--" or piece.endswith("king"):
                continue
            score += SQUARE_SCORES[piece][r][c]
            color, kind = piece.split("_")
            if kind == "pawn":
                continue
            phase += PHASE_WEIGHTS[kind]

            enemy_zone = zones["black" if color == "white" else "white"]
            reachable = zone_attacks = 0
            for line in RAYS[kind, r, c]:
                for square in line:
                    if square in enemy_zone:
                        zone_attacks += 1
                    target = board[square[0]][square[1]]
                    if target == "--":
                        reachable += 1
                        continue
                    if not target.startswith(color):
                        reachable += 1
                    break
            # Attacks near the enemy king count against that king, i.e. in this piece's favour
            bonus = MOBILITY_BONUS[kind] * reachable + KING_ZONE_ATTACK_PENALTY * zone_attacks
            score += bonus if color == "white" else -bonus

    phase = min(phase, MAX_PHASE)  # a promoted pawn can push it past the start
    wr, wc = game_state.white_king_location
    br, bc = game_state.black_king_location
    score += king_square_score(wr, wc, phase)
    score -= king_square_score(ROWS - 1 - br, COLS - 1 - bc, phase)
    return score


def move_priority(move):
    """How promising a move looks before searching it (higher = search it earlier)"""
    priority = 0
    if move.piece_captured != "--":
        # Capture the most valuable piece, preferably with the least valuable one
        priority += 10000 + 10 * get_piece_value(move.piece_captured) - get_piece_value(move.piece_moved)
    if move.is_promotion:
        priority += 5000 + PIECE_VALUES[move.promotion_piece]
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
