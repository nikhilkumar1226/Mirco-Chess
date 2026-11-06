"""Micro Chess AI: picks moves with minimax search and alpha-beta pruning."""

import random
from functools import lru_cache

from chess_engine import EMPTY, HOLE, KNIGHT_OFFSETS, ROOK_DIRECTIONS, BISHOP_DIRECTIONS


# ============================================================================
# AI IMPLEMENTATION USING MINIMAX + ALPHA-BETA PRUNING
# ============================================================================

# How many moves (plies) ahead the AI looks at each difficulty level
DIFFICULTY_DEPTHS = {"easy": 2, "medium": 4, "hard": 6}
# How many centipawns worse than the best move a move may score and still be picked.
# Easy chooses at random from every move that is at most three pawns worse, so it
# sometimes gives away a knight or bishop, as a beginner would. The others play their best.
DIFFICULTY_MARGINS = {"easy": 300, "medium": 0, "hard": 0}

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
# How many captures (or replies to check) the quiescence search plays at most past the full depth
QUIESCENCE_PLIES = 8

# How far the game is from the endgame: knights and bishops count 1, rooks 2.
# The king's table slides from the middlegame one (all the pieces of the starting
# position still on the board) to the endgame one (none left).
PHASE_WEIGHTS = {'knight': 1, 'bishop': 1, 'rook': 2}


def build_rays(rows, cols, holes):
    """For every square and piece type, the lines of squares it attacks along (nearest first).

    A knight's "lines" are single squares; a rook or bishop stops at the first piece in each
    line. Holes are left out, and a line ends at one.
    """
    def usable(r, c):
        return 0 <= r < rows and 0 <= c < cols and (r, c) not in holes

    rays = {}
    for r in range(rows):
        for c in range(cols):
            rays['knight', r, c] = [[(r + dr, c + dc)] for dr, dc in KNIGHT_OFFSETS if usable(r + dr, c + dc)]
            for kind, directions in (('rook', ROOK_DIRECTIONS), ('bishop', BISHOP_DIRECTIONS)):
                lines = []
                for dr, dc in directions:
                    line, nr, nc = [], r + dr, c + dc
                    while usable(nr, nc):
                        line.append((nr, nc))
                        nr, nc = nr + dr, nc + dc
                    if line:
                        lines.append(line)
                rays[kind, r, c] = lines
    return rays


def reach_table(reach):
    """A bonus of 5 points for every square more than average a piece reaches from each square"""
    squares = [count for row in reach for count in row]
    average = round(sum(squares) / len(squares))
    return [[5 * (count - average) for count in row] for row in reach]


class EvaluationTables:
    """Everything evaluate_board looks up for one game mode's board, worked out once.

    Micro Chess uses the hand-made tables above. For other boards they are made from
    the board's shape: knights, bishops and (in the endgame) the king prefer squares
    from which they reach more of the board, so the center counts, and squares next
    to holes or edges count less.
    """

    def __init__(self, variant):
        board = variant.start_board()
        rows, cols = len(board), len(board[0])
        holes = {(r, c) for r in range(rows) for c in range(cols) if board[r][c] == HOLE}
        self.rays = build_rays(rows, cols, holes)
        # The king's square and the squares around it
        self.king_zones = {(r, c): {(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                                    if 0 <= r + dr < rows and 0 <= c + dc < cols and (r + dr, c + dc) not in holes}
                           for r in range(rows) for c in range(cols)}

        if variant.key == "micro":
            tables = PIECE_TABLES
            self.king_middlegame, self.king_endgame = KING_MIDDLEGAME_TABLE, KING_ENDGAME_TABLE
        else:
            def reach(kind):
                return [[sum(len(line) for line in self.rays[kind, r, c]) for c in range(cols)] for r in range(rows)]
            tables = {
                'pawn': [[30 if r == 1 else 10 if r == 2 else 0 for c in range(cols)] for r in range(rows)],
                'knight': reach_table(reach('knight')),
                'bishop': reach_table(reach('bishop')),
                'rook': [[10 if r == 1 else 0 for c in range(cols)] for r in range(rows)],
            }
            # Stay at home while there are pieces about (-10 for every rank forward), then centralize
            self.king_middlegame = [[max(-30, 10 - 10 * (rows - 1 - r)) for c in range(cols)] for r in range(rows)]
            self.king_endgame = reach_table([[len(self.king_zones[r, c]) - 1 for c in range(cols)]
                                             for r in range(rows)])

        # Material plus table bonus for every piece on every square, signed (+ White, - Black),
        # so evaluating a position is just a lookup per piece. Black uses the table turned around.
        self.square_scores = {}
        for kind, table in tables.items():
            self.square_scores["white_" + kind] = [[PIECE_VALUES[kind] + table[r][c] for c in range(cols)]
                                                   for r in range(rows)]
            self.square_scores["black_" + kind] = [[-(PIECE_VALUES[kind] + table[rows - 1 - r][cols - 1 - c])
                                                    for c in range(cols)] for r in range(rows)]
        self.max_phase = max(1, sum(PHASE_WEIGHTS.get(piece.split("_")[1], 0)
                                    for row in board for piece in row if piece not in (EMPTY, HOLE)))

    def king_square_score(self, table_row, table_col, phase):
        """The king's table bonus, blended between middlegame and endgame by the game phase"""
        middlegame = self.king_middlegame[table_row][table_col]
        endgame = self.king_endgame[table_row][table_col]
        return (middlegame * phase + endgame * (self.max_phase - phase)) // self.max_phase


EVALUATION_TABLES = {}  # game mode key -> EvaluationTables


def tables_for(game_state):
    variant = game_state.variant
    if variant.key not in EVALUATION_TABLES:
        EVALUATION_TABLES[variant.key] = EvaluationTables(variant)
    return EVALUATION_TABLES[variant.key]


@lru_cache(maxsize=1000)
def get_piece_value(piece):
    """Get numerical value of a piece (cached for performance)"""
    if piece == "--":
        return 0
    return PIECE_VALUES.get(piece.split('_')[1], 0)


def evaluate_board(game_state):
    """Evaluate board position: Positive = good for White, Negative = good for Black.

    The score is in centipawns and always a whole number. For each side it adds up:
    - material and piece-square tables (how much each piece is worth where it stands)
    - mobility: a small bonus for each square a knight, bishop or rook can move to
    - king safety: a penalty for each enemy attack on the squares around the king
    """
    tables = tables_for(game_state)
    board = game_state.board
    rows, cols = game_state.rows, game_state.cols
    zones = {"white": tables.king_zones[game_state.white_king_location],
             "black": tables.king_zones[game_state.black_king_location]}
    score = 0
    phase = 0
    for r in range(rows):
        for c in range(cols):
            piece = board[r][c]
            if piece == EMPTY or piece == HOLE or piece.endswith("king"):
                continue
            score += tables.square_scores[piece][r][c]
            color, kind = piece.split("_")
            if kind == "pawn":
                continue
            phase += PHASE_WEIGHTS[kind]

            enemy_zone = zones["black" if color == "white" else "white"]
            reachable = zone_attacks = 0
            for line in tables.rays[kind, r, c]:
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

    phase = min(phase, tables.max_phase)  # a promoted pawn can push it past the start
    wr, wc = game_state.white_king_location
    br, bc = game_state.black_king_location
    score += tables.king_square_score(wr, wc, phase)
    score -= tables.king_square_score(rows - 1 - br, cols - 1 - bc, phase)
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

def legal_moves_in_order(game_state, captures_only=False):
    """Yield the legal moves (or only the captures and promotions), most promising first.

    Each move is only checked for legality (does it leave our king in check?)
    when the search actually reaches it, so moves skipped by pruning cost nothing.
    """
    moves = game_state.get_all_possible_moves()
    if captures_only:
        moves = [move for move in moves if move.piece_captured != "--" or move.is_promotion]
    for move in order_moves(moves):
        game_state.make_move(move)
        legal = not game_state.is_king_attacked(white=not game_state.white_to_move)
        game_state.undo_move(move)
        if legal:
            yield move


def quiescence(game_state, alpha, beta, maximizing_player, ply, plies_left=QUIESCENCE_PLIES):
    """At the end of the main search, play on with captures and promotions until the position is quiet.

    Without this the search would stop in the middle of an exchange and believe, say,
    that a rook which has just taken a pawn is safe when it can be taken back. The side
    to move may also "stand pat": keep the evaluation as it is if no capture improves on
    it. A side in check can't stand pat, so then every move is tried (and none means mate).
    """
    if game_state.is_insufficient_material():
        return 0
    if plies_left == 0:
        return evaluate_board(game_state)  # the limit, in case the captures and checks go on and on
    in_check = game_state.in_check()

    if in_check:
        best = float('-inf') if maximizing_player else float('inf')
    else:
        best = evaluate_board(game_state)  # standing pat
        if maximizing_player:
            if best >= beta:
                return best
            alpha = max(alpha, best)
        else:
            if best <= alpha:
                return best
            beta = min(beta, best)

    found_move = False
    for move in legal_moves_in_order(game_state, captures_only=not in_check):
        found_move = True
        game_state.make_move(move)
        score = quiescence(game_state, alpha, beta, not maximizing_player, ply + 1, plies_left - 1)
        game_state.undo_move(move)
        if maximizing_player:
            best = max(best, score)
            alpha = max(alpha, score)
        else:
            best = min(best, score)
            beta = min(beta, score)
        if beta <= alpha:
            break

    if in_check and not found_move:
        return -(MATE_SCORE - ply) if game_state.white_to_move else MATE_SCORE - ply
    return best


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
    # Draws by repetition or insufficient material
    if game_state.is_threefold_repetition() or game_state.is_insufficient_material():
        return 0

    # Reached the full depth: settle any captures first, then evaluate
    if depth == 0:
        return quiescence(game_state, alpha, beta, maximizing_player, ply)

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

def position_score(game_state, depth):
    """How good the position is for White, in centipawns, from a search `depth` plies deep.

    A forced mate scores close to MATE_SCORE (less the moves it takes), negative if Black mates.
    """
    return minimax_alpha_beta(game_state, depth, float('-inf'), float('inf'), game_state.white_to_move)


def get_ai_move(game_state, difficulty="medium", depth=None, rng=None):
    """
    Main AI function - Get the best move using Minimax + Alpha-Beta Pruning
    Works for whichever side is to move, so the AI can play White or Black.

    Args:
        game_state: Current game state
        difficulty: "easy", "medium" or "hard" (sets how deep the AI searches, and
            how much worse than the best move its choice may be)
        depth: Optional exact search depth, overrides difficulty's depth
        rng: Optional random.Random, used to choose between moves that are good enough

    Returns:
        Best move for current player, or None if no moves available
    """
    if difficulty not in DIFFICULTY_DEPTHS:
        raise ValueError(f"difficulty must be one of {list(DIFFICULTY_DEPTHS)}, not {difficulty!r}")
    if depth is None:
        depth = DIFFICULTY_DEPTHS[difficulty]
    margin = DIFFICULTY_MARGINS[difficulty]
    rng = rng or random

    valid_moves = game_state.get_valid_moves()
    if not valid_moves:
        return None

    # White wants the highest score, Black the lowest
    ai_is_white = game_state.white_to_move
    scored_moves = []
    best_score = float('-inf') if ai_is_white else float('inf')

    # Evaluate each possible move
    for move in order_moves(valid_moves):
        game_state.make_move(move)
        # After our move it's the opponent's turn: they maximize if they are White.
        # The window stops one point past the margin below the best score so far: that
        # still prunes worse moves, but moves within the margin get their exact score
        # (scores are whole numbers), so we know which ones are good enough.
        if ai_is_white:
            score = minimax_alpha_beta(game_state, depth - 1, best_score - margin - 1, float('inf'), False)
        else:
            score = minimax_alpha_beta(game_state, depth - 1, float('-inf'), best_score + margin + 1, True)
        game_state.undo_move(move)

        scored_moves.append((score, move))
        best_score = max(best_score, score) if ai_is_white else min(best_score, score)

    if abs(best_score) >= MATE_SCORE - 100:
        margin = 0  # a mate is coming: take the quickest win, or put off the loss the longest
    # Pick at random between the moves within the margin (with no margin, the equally good ones)
    return rng.choice([move for score, move in scored_moves if abs(score - best_score) <= margin])
