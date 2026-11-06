"""Micro Chess AI: picks moves with minimax search and alpha-beta pruning."""

import random
import time
from dataclasses import dataclass
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
# How long each level may think, in seconds (it stops sooner once it reaches its depth)
DIFFICULTY_TIMES = {"easy": 0.3, "medium": 0.8, "hard": 1.5}
# With a chess clock the AI expects about this many more moves, and shares out its time
MOVES_TO_GO = 20
MIN_THINKING_TIME = 0.05  # seconds, however little is left on the clock

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

# The transposition table: what a search has learned about each position, so a position
# reached again by a different order of moves isn't searched twice. A stored score is
# EXACT, or only a LOWER or UPPER bound when the search was cut short by alpha-beta.
EXACT, LOWER, UPPER = "exact", "lower", "upper"
TABLE_LIMIT = 200_000  # positions; the table starts again empty if it gets this big

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


EVALUATION_TABLES = {}  # (game mode key, layout) -> EvaluationTables; custom boards differ in their layout


def tables_for(game_state):
    variant = game_state.variant
    cache_key = (variant.key, variant.layout)
    if cache_key not in EVALUATION_TABLES:
        EVALUATION_TABLES[cache_key] = EvaluationTables(variant)
    return EVALUATION_TABLES[cache_key]


class Search:
    """What one search keeps track of: its transposition table, how many positions it has
    looked at, and when it has to stop. A new one is made for every move, so the table
    never grows old or large."""

    def __init__(self, use_table=True, deadline=None):
        self.table = {} if use_table else None  # position key -> (depth, score, bound, best move)
        self.nodes = 0
        self.deadline = deadline  # a time.perf_counter() time to stop at, or None for no limit
        self.stopped = False
        # The line of play the search expects from the position it last finished at each ply:
        # the best move found there, then the line it expects after that move
        self.lines = {}

    def out_of_time(self):
        """True once the deadline has passed (the clock is checked every 256 positions)"""
        if self.deadline is not None and self.nodes % 256 == 0 and time.perf_counter() >= self.deadline:
            self.stopped = True
        return self.stopped


@dataclass
class SearchResult:
    move: object  # the chosen Move
    score: int  # its score, good for White when positive
    depth: int  # how many plies deep the deepest finished search went
    nodes: int  # how many positions the search looked at
    line: list  # the moves the search expects to follow, starting with the chosen move


def is_mate_score(score):
    return abs(score) >= MATE_SCORE - 100


def to_table(score, ply):
    """A mate score counts plies from the root; the table stores it counted from this position,
    because the same position can be reached at different distances from the root"""
    if is_mate_score(score):
        return score + ply if score > 0 else score - ply
    return score


def from_table(score, ply):
    if is_mate_score(score):
        return score - ply if score > 0 else score + ply
    return score


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

def legal_moves_in_order(game_state, captures_only=False, first=None):
    """Yield the legal moves (or only the captures and promotions), most promising first,
    starting with `first` if it's one of them.

    Each move is only checked for legality (does it leave our king in check?)
    when the search actually reaches it, so moves skipped by pruning cost nothing.
    """
    moves = game_state.get_all_possible_moves()
    if captures_only:
        moves = [move for move in moves if move.piece_captured != "--" or move.is_promotion]
    moves = order_moves(moves)
    if first is not None and first in moves:
        moves.remove(first)
        moves.insert(0, first)
    for move in moves:
        game_state.make_move(move)
        legal = not game_state.is_king_attacked(white=not game_state.white_to_move)
        game_state.undo_move(move)
        if legal:
            yield move


def quiescence(game_state, alpha, beta, maximizing_player, ply, plies_left=QUIESCENCE_PLIES, search=None):
    """At the end of the main search, play on with captures and promotions until the position is quiet.

    Without this the search would stop in the middle of an exchange and believe, say,
    that a rook which has just taken a pawn is safe when it can be taken back. The side
    to move may also "stand pat": keep the evaluation as it is if no capture improves on
    it. A side in check can't stand pat, so then every move is tried (and none means mate).
    """
    if search is not None:
        search.nodes += 1
        if search.out_of_time():
            return 0
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
        score = quiescence(game_state, alpha, beta, not maximizing_player, ply + 1, plies_left - 1, search)
        game_state.undo_move(move)
        if search is not None and search.stopped:
            return 0
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


def minimax_alpha_beta(game_state, depth, alpha, beta, maximizing_player, ply=1, search=None):
    """
    Minimax Algorithm with Alpha-Beta Pruning

    Args:
        game_state: Current game position
        depth: How many moves to look ahead
        alpha: Best value maximizing player can guarantee
        beta: Best value minimizing player can guarantee
        maximizing_player: True if maximizing (White), False if minimizing (Black)
        ply: How many moves deep we already are (used to prefer faster mates)
        search: Optional Search, for its transposition table and to count positions

    Returns:
        Best evaluation score for current position
    """
    if search is not None:
        search.nodes += 1
        search.lines[ply] = []  # filled in below if this position is searched
        if search.out_of_time():
            return 0  # the answer is thrown away
    # Draws by repetition or insufficient material
    if game_state.is_threefold_repetition() or game_state.is_insufficient_material():
        return 0

    # Reached the full depth: settle any captures first, then evaluate
    if depth == 0:
        return quiescence(game_state, alpha, beta, maximizing_player, ply, search=search)

    # A position already searched to this depth (reached by another order of moves) isn't
    # searched again, if what was learned about it is enough to decide here
    table = search.table if search is not None else None
    key = game_state.position_history[-1]
    known_best = None
    if table is not None and key in table:
        stored_depth, stored_score, bound, known_best = table[key]
        score = from_table(stored_score, ply)
        if stored_depth == depth and (bound == EXACT or (bound == LOWER and score >= beta)
                                      or (bound == UPPER and score <= alpha)):
            search.lines[ply] = [known_best]  # the line stops here: what follows wasn't stored
            return score

    window = (alpha, beta)
    best = float('-inf') if maximizing_player else float('inf')
    best_move = None
    # White maximizes the score and Black minimizes it; the move that was best here before goes first
    for move in legal_moves_in_order(game_state, first=known_best):
        game_state.make_move(move)
        score = minimax_alpha_beta(game_state, depth - 1, alpha, beta, not maximizing_player, ply + 1, search)
        game_state.undo_move(move)
        if search is not None and search.stopped:
            return 0  # out of time: unwind without storing anything

        if (score > best) if maximizing_player else (score < best):
            best, best_move = score, move
            if search is not None:
                search.lines[ply] = [move] + search.lines.get(ply + 1, [])
        if maximizing_player:
            alpha = max(alpha, score)
        else:
            beta = min(beta, score)

        # Alpha-Beta Pruning: Cut off if beta <= alpha
        if beta <= alpha:
            break

    if best_move is None:
        if game_state.in_check():
            # Checkmate: the side to move has lost. Subtracting ply makes a
            # quicker mate worth more than a slower one
            return -(MATE_SCORE - ply) if game_state.white_to_move else MATE_SCORE - ply
        return 0  # Stalemate is a draw

    if table is not None:
        # A score outside the window is only a bound: the true score is at most (or at least) that
        bound = UPPER if best <= window[0] else LOWER if best >= window[1] else EXACT
        if len(table) >= TABLE_LIMIT:
            table.clear()
        table[key] = (depth, to_table(best, ply), bound, best_move)
    return best

@dataclass
class Analysis:
    score: int  # how good the position is for White
    line: list  # the moves the search expects to follow
    depth: int  # how many plies deep the search went


def analyse(game_state, depth, time_limit=None):
    """Score a position with a search `depth` plies deep. With a time limit (in seconds) it
    searches 1 ply deep, then 2, 3 and so on up to `depth`, and keeps the deepest search
    that finished in time (the first one always finishes).

    A forced mate scores close to MATE_SCORE (less the moves it takes), negative if Black mates.
    """
    search = Search()
    deadline = None if time_limit is None else time.perf_counter() + time_limit
    analysis = None
    for current_depth in ([depth] if time_limit is None else range(1, depth + 1)):
        if analysis and time.perf_counter() >= deadline:
            break
        search.deadline = deadline if analysis else None
        score = minimax_alpha_beta(game_state, current_depth, float('-inf'), float('inf'),
                                   game_state.white_to_move, search=search)
        if search.stopped:
            break
        analysis = Analysis(score, search.lines.get(1, []), current_depth)
    return analysis


def position_score(game_state, depth, time_limit=None):
    """How good the position is for White, in centipawns (see analyse)"""
    return analyse(game_state, depth, time_limit).score


def analyse_position(game_state, depth, time_limit=None):
    """(score, line): how good the position is for White, and the moves the search expects to follow"""
    analysis = analyse(game_state, depth, time_limit)
    return analysis.score, analysis.line


def move_mates_within(game_state, move, moves):
    """True if `move` forces checkmate within `moves` moves of the side playing it (counting
    this one), whatever the defence. A full search checks every reply."""
    white = game_state.white_to_move
    game_state.make_move(move)
    # The mate comes on the side's last move at the latest: 2 * moves - 2 plies after this one
    score = position_score(game_state, 2 * moves - 2)
    game_state.undo_move(move)
    own_score = score if white else -score
    return own_score >= MATE_SCORE - (2 * moves - 1)


def mating_moves(game_state, moves):
    """The moves that force checkmate within `moves` moves (see move_mates_within)"""
    return [move for move in game_state.get_valid_moves() if move_mates_within(game_state, move, moves)]


def time_budget(difficulty, time_left=None):
    """How many seconds the AI may think: its level's time, and with a chess clock no more
    than a fair share of what's left on its clock"""
    budget = DIFFICULTY_TIMES[difficulty]
    if time_left is not None:
        budget = min(budget, max(MIN_THINKING_TIME, time_left / MOVES_TO_GO))
    return budget


def score_root_moves(game_state, moves, depth, margin, search):
    """Score each of the root moves with a search `depth` plies deep, or None if time ran out.

    Returns ([(score, move, expected line), ...], best score).
    """
    # White wants the highest score, Black the lowest
    ai_is_white = game_state.white_to_move
    scored_moves = []
    best_score = float('-inf') if ai_is_white else float('inf')

    for move in moves:
        game_state.make_move(move)
        # After our move it's the opponent's turn: they maximize if they are White.
        # The window stops one point past the margin below the best score so far: that
        # still prunes worse moves, but moves within the margin get their exact score
        # (scores are whole numbers), so we know which ones are good enough.
        if ai_is_white:
            score = minimax_alpha_beta(game_state, depth - 1, best_score - margin - 1, float('inf'), False,
                                       ply=2, search=search)
        else:
            score = minimax_alpha_beta(game_state, depth - 1, float('-inf'), best_score + margin + 1, True,
                                       ply=2, search=search)
        game_state.undo_move(move)
        if search.stopped:
            return None

        scored_moves.append((score, move, [move] + search.lines.get(2, [])))
        best_score = max(best_score, score) if ai_is_white else min(best_score, score)
    return scored_moves, best_score


def search_move(game_state, difficulty="medium", depth=None, rng=None, time_left=None, time_limit=None):
    """
    Main AI function - Get the best move using Minimax + Alpha-Beta Pruning
    Works for whichever side is to move, so the AI can play White or Black.

    It searches 1 ply deep, then 2, 3 and so on (iterative deepening), up to its level's
    depth or until its time is up, keeping the result of the deepest search that finished.
    Each search tries the moves the last one liked best first, which makes it quicker.

    Args:
        game_state: Current game state
        difficulty: "easy", "medium" or "hard" (sets how deep and how long the AI searches,
            and how much worse than the best move its choice may be)
        depth: Optional exact search depth: one search that deep with no time limit, so the
            result doesn't depend on how fast the computer is
        rng: Optional random.Random, used to choose between moves that are good enough
        time_left: Optional seconds left on the AI's chess clock
        time_limit: Optional most seconds to think, if that's less than its level allows

    Returns:
        A SearchResult, or None if no moves are available
    """
    if difficulty not in DIFFICULTY_DEPTHS:
        raise ValueError(f"difficulty must be one of {list(DIFFICULTY_DEPTHS)}, not {difficulty!r}")
    margin = DIFFICULTY_MARGINS[difficulty]
    rng = rng or random

    valid_moves = game_state.get_valid_moves()
    if not valid_moves:
        return None

    if depth is not None:
        depths, deadline = [depth], None
    else:
        depths = range(1, DIFFICULTY_DEPTHS[difficulty] + 1)
        budget = time_budget(difficulty, time_left)
        deadline = time.perf_counter() + (budget if time_limit is None else min(budget, time_limit))
    search = Search()
    moves = order_moves(valid_moves)
    finished = None
    for current_depth in depths:
        if finished and time.perf_counter() >= deadline:
            break  # no time left to start another depth
        search.deadline = deadline if finished else None  # the first depth always gets to finish
        result = score_root_moves(game_state, moves, current_depth, margin, search)
        if result is None:
            break  # out of time: go with the deepest search that finished
        scored_moves, best_score = result
        finished = (current_depth, scored_moves, best_score)
        # Next time, search the best moves first
        moves = [move for _, move, _ in sorted(scored_moves, key=lambda scored: scored[0],
                                               reverse=game_state.white_to_move)]
        if is_mate_score(best_score):
            break  # a deeper search could only find slower mates

    reached, scored_moves, best_score = finished
    if is_mate_score(best_score):
        margin = 0  # a mate is coming: take the quickest win, or put off the loss the longest
    # Pick at random between the moves within the margin (with no margin, the equally good ones)
    score, move, line = rng.choice([scored for scored in scored_moves if abs(scored[0] - best_score) <= margin])
    return SearchResult(move, score, reached, search.nodes, line)


def get_ai_move(game_state, difficulty="medium", depth=None, rng=None, time_left=None, time_limit=None):
    """The move search_move chooses (see there), or None if there are no moves"""
    result = search_move(game_state, difficulty, depth, rng, time_left, time_limit)
    return result.move if result else None
