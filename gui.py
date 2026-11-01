"""Micro Chess in a pygame window: click a piece and then its new square, or drag it there.

The AI thinks in a background thread, so the window keeps responding while it searches.
"""

import copy
import os
import queue
import random
import threading
import traceback

import pygame

import settings
from ai import get_ai_move, position_score, MATE_SCORE
from chess_engine import GameState, ROWS, EMPTY, HOLE, VARIANTS
from sounds import Sounds

# Layout, in pixels
BOARD_X, BOARD_Y = 36, 20  # top-left corner of the space for the board; the margins hold the coordinates
BOARD_AREA_WIDTH, BOARD_AREA_HEIGHT = 320, 400  # every board is sized to fit this space
SQUARE_SIZE = 80  # the biggest a square gets (on boards 4 squares wide); wider boards get smaller ones
PICKER_SIZE = 80  # each choice in the promotion picker
STATUS_HEIGHT = 48
SIDE_PANEL_X = BOARD_X + BOARD_AREA_WIDTH + 20  # the move list and captured pieces, right of the board
SIDE_PANEL_WIDTH = 196
CAPTURED_SIZE = 28  # captured pieces are shown small
WIDTH = SIDE_PANEL_X + SIDE_PANEL_WIDTH + 16
HEIGHT = BOARD_Y + BOARD_AREA_HEIGHT + 32 + STATUS_HEIGHT
FPS = 60
ANIMATION_MS = 160  # how long a piece takes to slide to its new square

# Colors
DARK_SQUARE = pygame.Color("#96b68d")
LIGHT_SQUARE = pygame.Color("#c8d6c9")
BACKGROUND = pygame.Color("#262b25")
HOLE_COLOR = pygame.Color("#1a1e19")
HOLE_EDGE = pygame.Color("#11140f")
STATUS_BACKGROUND = pygame.Color("#1c201b")
PANEL = pygame.Color("#eef2ec")
SIDE_PANEL = pygame.Color("#2f362d")
LATEST_MOVE = pygame.Color("#3e483b")
TEXT = pygame.Color("#e6ece4")
DARK_TEXT = pygame.Color("#1f2a1d")
MUTED_TEXT = pygame.Color("#97a394")
CHECK_TEXT = pygame.Color("#ff7b6e")
BUTTON = pygame.Color("#5b8a51")
BUTTON_HOVER = pygame.Color("#6b9e60")
CHOICE = pygame.Color("#343c32")
CHOICE_HOVER = pygame.Color("#3f493d")
DISABLED_TEXT = pygame.Color("#5d665b")
LAST_MOVE = (246, 226, 90, 105)        # highlights are drawn see-through (the 4th number is alpha)
SELECTED = (246, 226, 90, 170)
MOVE_HINT = (25, 50, 25, 80)
DROP_TARGET = (250, 250, 240)
HINT_ARROW = (40, 110, 225, 170)
GHOST_ALPHA = 90  # how faint a dragged piece's starting square looks
CHECK = (225, 40, 30)
DIM = (10, 14, 10, 150)

FILES = "abcdef"
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
PIECE_NAMES = [f"{color}_{kind}" for color in ("white", "black")
               for kind in ("king", "rook", "bishop", "knight", "pawn")]

# Start menu: (heading, the setting it changes, [(button label, value), ...])
MENU_CHOICES = [
    ("Board", "variant_key", [(variant.name, key) for key, variant in VARIANTS.items()]),
    ("Opponent", "two_players", [("Computer", False), ("2 Players", True)]),
    ("Play as", "human_is_white", [("White", True), ("Black", False)]),
    ("Difficulty", "difficulty", [("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")]),
]
MENU_WIDTH = 400
ICON_SQUARE = 6  # the size of a square in the little pictures of the boards on the menu
MENU_SETTINGS = ("variant_key", "two_players", "human_is_white", "difficulty")  # remembered for next time

# The settings screen: (label, setting) for each on/off switch
SETTING_SWITCHES = [
    ("Sound effects", "sound"),
    ("Show where a piece can move", "show_moves"),
    ("Animations", "animations"),
    ("Hint button", "hints"),
    ("Board coordinates", "coordinates"),
    ("Ask before quitting a game", "confirm_quit"),
    ("Evaluation bar", "eval_bar"),
    ("Game review", "review"),
    ("Chess clock (min)", "clock"),  # a row of choices instead of a switch
]
SETTINGS_ROW_HEIGHT = 37
CLOCK_CHOICES = [("Off", 0), ("1", 1), ("3", 3), ("5", 5), ("10", 10)]  # minutes for each player

HINT_DIFFICULTY = "hard"  # hints come from the strongest search

# For the move list (c4-c5=R) and the material count next to the captured pieces
PIECE_LETTERS = {"rook": "R", "bishop": "B", "knight": "N"}
MATERIAL = {"pawn": 1, "knight": 3, "bishop": 3, "rook": 5, "king": 0}
CAPTURE_ORDER = ["rook", "bishop", "knight", "pawn"]

REVIEW_KEYS = {pygame.K_LEFT: "back", pygame.K_RIGHT: "forward", pygame.K_HOME: "first", pygame.K_UP: "first",
               pygame.K_END: "last", pygame.K_DOWN: "last"}

DRAW_TEXT = {
    "stalemate": ("Stalemate", "It's a draw"),
    "repetition": ("Draw", "Threefold repetition"),
    "insufficient_material": ("Draw", "Insufficient material"),
    "time_draw": ("Time's up!", "Draw: no pieces left to win"),
}
LOW_TIME_MS = 10_000  # a clock turns red when it gets this low
EVAL_BAR_DEPTH = 4  # how deep the search for the evaluation bar looks (as deep as Medium)
EVAL_BAR = pygame.Rect(BOARD_X + BOARD_AREA_WIDTH + 5, BOARD_Y, 10, BOARD_AREA_HEIGHT)  # between board and panel
REVIEW_DEPTH = 4  # how deep game review searches to judge each move
MISTAKE, BLUNDER = 150, 300  # a move that gives away this many centipawns is marked "?" or "??"
MARK_COLORS = {"?": pygame.Color("#f0b25a"), "??": CHECK_TEXT}
BETTER_ARROW = (60, 175, 85, 170)  # in review, the move that would have been better
MOVE_LINE_HEIGHT = 26  # the move list's rows
REVIEW_LABELS = {"first": "|<", "back": "<", "forward": ">", "last": ">|", "done": "Done"}


def load_piece_images(size):
    """Load images/<piece>.png for every piece, scaled to size x size pixels"""
    images = {}
    for name in PIECE_NAMES:
        image = pygame.image.load(os.path.join(IMAGE_DIR, f"{name}.png")).convert_alpha()
        images[name] = pygame.transform.smoothscale(image, (size, size))
    return images


def square_name(r, c, rows=ROWS):
    """The name of square (row, col) on a board with this many rows, e.g. "a1" """
    return f"{FILES[c]}{rows - r}"


def move_notation(move, rows=ROWS):
    """The move for the move list: d2-d3, a1xa4 (a capture), c4-c5=R (promotion) or O-O (castling)"""
    if move.is_castle:
        return "O-O"
    separator = "x" if move.piece_captured != EMPTY else "-"
    text = (square_name(move.start_row, move.start_col, rows) + separator
            + square_name(move.end_row, move.end_col, rows))
    if move.is_promotion:
        text += "=" + PIECE_LETTERS[move.promotion_piece]
    return text


def clock_text(ms):
    """A clock's time as minutes and seconds, or seconds and tenths in the last 10 seconds: 4:05, 9.3"""
    if ms < LOW_TIME_MS:
        return f"{ms / 1000:.1f}"
    seconds = -(-ms // 1000)  # rounded up, so a fresh 3-minute clock shows 3:00
    return f"{seconds // 60}:{seconds % 60:02d}"


def score_text(score):
    """The evaluation bar's number: pawns ahead for White (+1.2) or Black (-0.5), the moves
    to a forced mate (+M2), or the result once a side has been mated (1-0 or 0-1)"""
    if abs(score) >= MATE_SCORE - 100:
        moves = (MATE_SCORE - abs(score)) // 2
        if moves == 0:
            return "1-0" if score > 0 else "0-1"
        return f"{'+' if score > 0 else '-'}M{moves}"
    if round(score / 100, 1) == 0:
        return "0.0"
    return f"{score / 100:+.1f}"


def white_share(score):
    """How much of the evaluation bar is White's: a half when even, nearly all of it 4 pawns up"""
    if abs(score) >= MATE_SCORE - 100:
        return 1.0 if score > 0 else 0.0
    return 1 / (1 + 10 ** (-score / 400))


def has_only_king(board, color):
    return all(not piece.startswith(color) or piece.endswith("king") for row in board for piece in row)


def translucent_square(rgba, size):
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    surface.fill(rgba)
    return surface


def check_glow(size):
    """A red glow, strongest in the middle, drawn under a king that is in check"""
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = size // 2
    for radius in range(center, 0, -2):
        alpha = int(230 * (1 - radius / center) ** 0.6)
        pygame.draw.circle(surface, (*CHECK, alpha), (center, center), radius)
    return surface


def game_over_text(result, white_to_move):
    """(title, detail) saying how the game ended (result comes from get_game_result())"""
    # After a checkmate or a timeout, the side to move is the one that lost
    winner = "Black" if white_to_move else "White"
    if result == "checkmate":
        return "Checkmate!", f"{winner} wins"
    if result == "time":
        return "Time's up!", f"{winner} wins on time"
    return DRAW_TEXT[result]


def result_line(result, white_to_move):
    """How the game ended, in one line for the status bar"""
    title, detail = game_over_text(result, white_to_move)
    if result in ("checkmate", "time"):
        return f"{title} {detail}"
    return f"{title} - {detail.lower()}"


class ChessGUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Micro Chess")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.piece_images = {}  # piece size -> images, loaded when a board needs that size
        self.small_images = load_piece_images(CAPTURED_SIZE)
        self.sounds = Sounds()
        self.font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 22)
        self.big_font = pygame.font.Font(None, 44)
        self.title_font = pygame.font.Font(None, 64)

        # The settings from last time, including what was chosen on the start menu
        self.settings = settings.load()
        for name in MENU_SETTINGS:
            setattr(self, name, self.settings[name])
        self.sounds.muted = not self.settings["sound"]

        self.search_results = queue.Queue()  # (search id, "ai" or "hint", move) from search threads
        self.search_id = 0
        self.running = True
        self.confirming_quit = False  # the "Quit the game?" dialog is open
        self.in_settings = False  # the settings screen is open (over the menu or the game)
        self.in_menu = True
        self.new_game()

    # ---- game state -------------------------------------------------------

    def start_game(self):
        """Leave the start menu and play with the chosen settings"""
        self.in_menu = False
        self.save_settings()
        self.new_game()

    def save_settings(self):
        """Remember the settings, and what was chosen on the start menu, for next time"""
        for name in MENU_SETTINGS:
            self.settings[name] = getattr(self, name)
        settings.save(self.settings)

    def open_settings(self):
        self.in_settings = True
        self.dragging = None  # a piece being dragged goes back to its square

    def set_clock(self, minutes):
        """Choose the clock: both players start again with that many minutes (0 for no clock)"""
        self.settings["clock"] = minutes
        self.reset_clock()
        self.save_settings()

    def reset_clock(self):
        minutes = self.settings["clock"]
        self.clock_ms = {"white": minutes * 60_000, "black": minutes * 60_000} if minutes else None
        self.last_tick = self.ticks()

    def ticks(self):
        """Milliseconds since the game started up (the clocks use this)"""
        return pygame.time.get_ticks()

    def clock_running(self):
        """The clock of the side to move runs while a game is on and nothing is in front of the board"""
        return (self.clock_ms is not None and self.result is None and not self.in_menu
                and not self.in_settings and not self.confirming_quit)

    def run_clock(self):
        now = self.ticks()
        elapsed, self.last_tick = now - self.last_tick, now
        if not self.clock_running():
            return
        side = "white" if self.gs.white_to_move else "black"
        self.clock_ms[side] = max(0, self.clock_ms[side] - elapsed)
        if self.clock_ms[side] == 0:
            # Out of time: a loss, unless the other side has nothing left to checkmate with
            other = "black" if side == "white" else "white"
            self.result = "time_draw" if has_only_king(self.gs.board, other) else "time"
            self.selected = self.dragging = self.promotion_choices = self.hint = None
            self.cancel_search()

    def toggle_setting(self, name):
        self.settings[name] = not self.settings[name]
        self.sounds.muted = not self.settings["sound"]
        if name == "eval_bar":
            self.update_eval()
        if name == "review" and self.review_index is not None:
            self.stop_review()
        if name == "hints" and (self.hint or self.hint_thinking):
            self.hint = None
            self.cancel_search()  # forget the hint being worked out (the AI restarts if it was thinking)
        self.save_settings()

    def open_menu(self):
        self.in_menu = True
        self.dragging = None
        self.review_index = None
        self.cancel_search()

    def new_game(self):
        self.gs = GameState(variant=VARIANTS[self.variant_key])
        self.layout_board()
        self.move_log = []  # every move played, so U can take moves back
        self.move_texts = []  # the same moves as written in the move list, e.g. "d2-d3+"
        self.selected = None  # (row, col) of the piece the player picked up
        self.dragging = None  # (row, col) of a piece being dragged with the mouse
        self.drag_pos = (0, 0)  # where the mouse is while dragging
        self.release_deselects = False  # the dragged piece was already selected before this click
        self.promotion_choices = None  # the moves to pick from while the promotion picker is open
        self.animation = None  # (move, start time in ms) while a move is sliding into place
        self.hint = None  # the move suggested when the player asks for a hint
        self.review_index = None  # while reviewing a finished game: how many of its moves are shown
        self.review_state = None  # the position being reviewed
        self.review_marks = []  # (mark, better move) for each move, worked out during review
        self.reset_clock()
        # Show the board from Black's side when playing Black against the computer
        self.flipped = not self.two_players and not self.human_is_white
        self.cancel_search()
        self.refresh()

    def layout_board(self):
        """Size the squares so this game's board fits its space, and make what's drawn on them"""
        rows, cols = self.gs.rows, self.gs.cols
        size = self.square_size = min(SQUARE_SIZE, BOARD_AREA_WIDTH // cols, BOARD_AREA_HEIGHT // rows)
        # Centered in the space for the board
        self.board_x = BOARD_X + (BOARD_AREA_WIDTH - cols * size) // 2
        self.board_y = BOARD_Y + (BOARD_AREA_HEIGHT - rows * size) // 2
        piece_size = size * 4 // 5
        if piece_size not in self.piece_images:
            self.piece_images[piece_size] = load_piece_images(piece_size)
        self.images = self.piece_images[piece_size]

        self.last_move_overlay = translucent_square(LAST_MOVE, size)
        self.selected_overlay = translucent_square(SELECTED, size)
        self.check_overlay = check_glow(size)
        self.move_dot = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.move_dot, MOVE_HINT, (size // 2, size // 2), size // 6)
        self.capture_ring = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.capture_ring, MOVE_HINT, (size // 2, size // 2), size // 2 - 2, size // 11)

    def refresh(self):
        """Work out the legal moves and the game's status after the position changed"""
        self.valid_moves = self.gs.get_valid_moves()
        self.result = self.gs.get_game_result()
        self.check = self.gs.in_check()
        self.last_move = self.move_log[-1] if self.move_log else None
        self.update_eval()

    def update_eval(self):
        """The score for the evaluation bar (None while the bar is switched off)"""
        if self.settings["eval_bar"]:
            self.eval_score = position_score(self.board_view()[0], EVAL_BAR_DEPTH)
        else:
            self.eval_score = None

    def play(self, move, animate=True):
        self.gs.make_move(move)
        animate = animate and self.settings["animations"]
        self.animation = (move, pygame.time.get_ticks()) if animate else None
        self.sounds.play("capture" if move.piece_captured != EMPTY else "move")
        self.move_log.append(move)
        self.selected = None
        self.dragging = None
        self.promotion_choices = None
        self.hint = None
        self.cancel_search()  # a hint still being worked out is no use now
        self.refresh()
        suffix = "#" if self.result == "checkmate" else "+" if self.check else ""
        self.move_texts.append(move_notation(move, self.gs.rows) + suffix)

    def undo(self):
        """Take back your last move and the AI's reply to it (one move in a 2-player game)"""
        # While the AI is thinking (or after you ended the game) only your move needs taking back
        count = 2 if self.is_human_turn() and not self.two_players else 1
        if len(self.move_log) < count or self.result in ("time", "time_draw"):
            return  # (a game lost on time stays lost)
        for _ in range(count):
            self.gs.undo_move(self.move_log.pop())
            self.move_texts.pop()
        self.review_index = None
        self.review_marks = []
        self.animation = None
        self.hint = None
        self.cancel_search()
        self.selected = None
        self.dragging = None
        self.promotion_choices = None
        self.refresh()

    def choose_move(self, moves, animate=True):
        """Play a move, or open the promotion picker if there's one move per promotion piece"""
        if moves[0].is_promotion:
            self.promotion_choices = moves
        else:
            self.play(moves[0], animate)

    def is_human_turn(self):
        return self.two_players or self.gs.white_to_move == self.human_is_white

    def moves_from(self, square):
        return [m for m in self.valid_moves if (m.start_row, m.start_col) == square]

    def moves_between(self, start, end):
        return [m for m in self.moves_from(start) if (m.end_row, m.end_col) == end]

    def captured_pieces(self):
        """(pieces White has captured, pieces Black has captured), most valuable first"""
        moves = self.move_log if self.review_index is None else self.move_log[:self.review_index]
        captured = sorted((m.piece_captured for m in moves if m.piece_captured != EMPTY),
                          key=lambda piece: CAPTURE_ORDER.index(piece.split("_")[1]))
        return ([p for p in captured if p.startswith("black")],
                [p for p in captured if p.startswith("white")])

    def material_balance(self):
        """White's material minus Black's (pawn = 1, knight and bishop = 3, rook = 5)"""
        return sum(MATERIAL[piece.split("_")[1]] * (1 if piece.startswith("white") else -1)
                   for row in self.board_view()[0].board for piece in row if piece not in (EMPTY, HOLE))

    # ---- game review ------------------------------------------------------

    def can_review(self):
        return self.settings["review"] and self.result is not None and bool(self.move_log)

    def start_review(self, index=None):
        """Step through the finished game, starting after `index` moves (the last one if not given)"""
        if self.can_review():
            self.show_review_position(len(self.move_log) if index is None else index)

    def show_review_position(self, index):
        self.review_index = max(0, min(len(self.move_log), index))
        self.review_state = self.position_after(self.review_index)
        self.update_eval()

    def stop_review(self):
        self.review_index = None
        self.update_eval()

    def board_view(self):
        """(game, last move) to draw: the game itself, or the position being reviewed"""
        if self.review_index is None:
            return self.gs, self.last_move
        return self.review_state, self.move_log[self.review_index - 1] if self.review_index else None

    def position_after(self, count):
        """A copy of the game as it stood after its first `count` moves"""
        gs = copy.deepcopy(self.gs)
        for move in reversed(self.move_log[count:]):
            gs.undo_move(move)
        return gs

    def judge_move(self, i):
        """How the i-th move (from 0) did: ("??", better move) if it threw away a lot,
        ("?", better move) if it threw away a fair amount, otherwise ("", None).

        A search scores the position before the move (with the best reply to everything)
        and after it; the difference is what the move gave away.
        """
        gs = self.position_after(i)
        white = gs.white_to_move
        best = position_score(gs, REVIEW_DEPTH)
        gs.make_move(self.move_log[i])
        played = position_score(gs, REVIEW_DEPTH - 1)
        gs.undo_move(self.move_log[i])
        lost = best - played if white else played - best
        if lost < MISTAKE:
            return "", None
        better = get_ai_move(gs, depth=REVIEW_DEPTH, rng=random.Random(0))
        return ("??" if lost >= BLUNDER else "?"), better

    def review_step(self, action):
        """Move through the review: "first", "back", "forward" or "last" (or "done" to stop)"""
        if action == "done":
            self.stop_review()
            return
        targets = {"first": 0, "back": self.review_index - 1, "forward": self.review_index + 1,
                   "last": len(self.move_log)}
        self.show_review_position(targets[action])

    # ---- AI ---------------------------------------------------------------

    def start_search(self, kind, difficulty):
        """Search for a move in a background thread so the window doesn't freeze.

        kind is "ai" for the computer's move or "hint" for a suggestion to the player.
        The search makes and undoes moves on the board while it works, so it gets its own copy.
        """
        if kind == "ai":
            self.ai_thinking = True
        else:
            self.hint_thinking = True
        self.search_id += 1
        search_id, position = self.search_id, copy.deepcopy(self.gs)

        def think():
            try:
                move = get_ai_move(position, difficulty)
            except Exception:
                traceback.print_exc()
                move = None  # update() copes with a search that found nothing
            self.search_results.put((search_id, kind, move))

        self.search_thread = threading.Thread(target=think, daemon=True)
        self.search_thread.start()

    def cancel_search(self):
        """Forget any search still running (its answer is ignored when it arrives)"""
        self.search_id += 1
        self.ai_thinking = False
        self.hint_thinking = False

    def can_ask_for_hint(self):
        return (self.settings["hints"] and not self.in_menu and self.result is None and self.is_human_turn()
                and not self.ai_thinking and not self.hint_thinking and self.hint is None
                and not self.promotion_choices)

    def ask_for_hint(self):
        """Have the AI find the best move for the player; it's shown as an arrow"""
        if self.can_ask_for_hint():
            self.start_search("hint", HINT_DIFFICULTY)

    def sliding_pieces(self):
        """The pieces still sliding to their new squares and how far along they are (0 to 1).

        Returns ([(piece, from square, to square), ...], progress); the list is empty
        when nothing is moving. Castling slides the rook too.
        """
        if self.animation is None:
            return [], 1
        move, start_time = self.animation
        elapsed = pygame.time.get_ticks() - start_time
        if elapsed >= ANIMATION_MS:
            return [], 1
        pieces = [(move.piece_moved, (move.start_row, move.start_col), (move.end_row, move.end_col))]
        if move.is_castle:
            color = move.piece_moved.split("_")[0]
            _, _, rook_from, rook_to = self.gs.castling_squares[color]
            pieces.append((f"{color}_rook", rook_from, rook_to))
        t = elapsed / ANIMATION_MS
        return pieces, 1 - (1 - t) ** 3  # ease out: fast at first, then settle

    def update(self):
        """Once per frame: run the clock, play the AI's move when it is ready, or start the AI when it's its turn"""
        self.run_clock()
        if self.animation and not self.sliding_pieces()[0]:
            self.animation = None
        # Wait for the last move to finish sliding before showing the AI's reply
        while self.animation is None and not self.search_results.empty() and self.result is None:
            search_id, kind, found = self.search_results.get()
            if search_id != self.search_id:
                continue  # from a search that was cancelled
            # The search used a copy of the game: find the same move in the real one
            move = next((m for m in self.valid_moves if m == found), None)
            if kind == "hint":
                self.hint_thinking = False
                self.hint = move  # no arrow if the search failed
            else:
                self.ai_thinking = False
                # If the search failed, any legal move keeps the game going
                self.play(move or random.choice(self.valid_moves))
        if not self.in_menu and self.result is None and not self.is_human_turn() and not self.ai_thinking:
            self.start_search("ai", self.difficulty)
        # Game review judges one move per frame, so the window keeps responding
        if self.review_index is not None and len(self.review_marks) < len(self.move_log):
            self.review_marks.append(self.judge_move(len(self.review_marks)))

    # ---- input ------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif self.confirming_quit:
            self.handle_quit_dialog(event)
        elif self.in_settings:
            self.handle_settings_event(event)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.review_index is not None:
                self.stop_review()
            elif event.key == pygame.K_ESCAPE:
                self.ask_to_quit()
            elif event.key in REVIEW_KEYS and not self.in_menu:
                self.review_key(event.key)
            elif event.key == pygame.K_m:
                self.toggle_setting("sound")
            elif event.key == pygame.K_s:
                self.open_settings()
            elif self.in_menu:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.start_game()
            elif event.key == pygame.K_r:
                self.new_game()
            elif event.key == pygame.K_u:
                self.undo()
            elif event.key == pygame.K_n:
                self.open_menu()
            elif event.key == pygame.K_h:
                self.ask_for_hint()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.in_menu:
                self.handle_menu_click(event.pos)
            else:
                self.handle_click(event.pos)
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self.drag_pos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.drop(event.pos)

    def review_key(self, key):
        """The arrow keys, Home and End step through a finished game (Left also starts the review)"""
        if self.review_index is not None:
            self.review_step(REVIEW_KEYS[key])
        elif key == pygame.K_LEFT:
            self.start_review(len(self.move_log) - 1)

    def ask_to_quit(self):
        """Esc: quit at once if there's no game to lose (or the player said not to ask), otherwise ask first"""
        if self.in_menu or self.result is not None or not self.move_log or not self.settings["confirm_quit"]:
            self.running = False
        else:
            self.confirming_quit = True
            self.dragging = None  # a piece being dragged goes back to its square

    def handle_quit_dialog(self, event):
        """While "Quit the game?" is open, only its answers count"""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y):
                self.running = False
            elif event.key in (pygame.K_ESCAPE, pygame.K_n):
                self.confirming_quit = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.quit_rect().collidepoint(event.pos):
                self.running = False
            elif self.keep_playing_rect().collidepoint(event.pos):
                self.confirming_quit = False

    def handle_settings_event(self, event):
        """On the settings screen, clicks flip the switches; Done, Esc, Enter or S go back"""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_s):
                self.in_settings = False
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, name in self.settings_rows():
                if name == "clock":
                    for choice, minutes in self.clock_choice_rects():
                        if choice.collidepoint(event.pos):
                            self.set_clock(minutes)
                elif rect.collidepoint(event.pos):
                    self.toggle_setting(name)
            if self.done_button_rect().collidepoint(event.pos):
                self.in_settings = False

    def handle_menu_click(self, pos):
        for rect, setting, value, _ in self.menu_buttons():
            if rect.collidepoint(pos) and self.menu_setting_enabled(setting):
                setattr(self, setting, value)
        if self.start_button_rect().collidepoint(pos):
            self.start_game()
        elif self.menu_settings_rect().collidepoint(pos):
            self.open_settings()

    def handle_click(self, pos):
        if self.gear_button_rect().collidepoint(pos):
            self.open_settings()
            return

        if self.review_index is not None:
            for rect, action in self.review_buttons():
                if rect.collidepoint(pos):
                    self.review_step(action)
            for rect, index in self.move_cells():  # clicking a move in the list shows the position after it
                if rect.collidepoint(pos):
                    self.show_review_position(index + 1)
            return

        if self.result is not None:
            for rect, _, action in self.game_over_buttons():
                if rect.collidepoint(pos):
                    {"again": self.new_game, "review": self.start_review, "menu": self.open_menu}[action]()
                    return
            for rect, index in self.move_cells():
                if rect.collidepoint(pos):
                    self.start_review(index + 1)
            return

        if self.promotion_choices:
            for rect, move in self.promotion_options():
                if rect.collidepoint(pos):
                    self.play(move)
                    return
            # Clicking outside the picker cancels the move
            self.promotion_choices = None
            self.selected = None
            return

        if self.settings["hints"] and self.hint_button_rect().collidepoint(pos):
            self.ask_for_hint()
            return

        if not self.is_human_turn() or self.ai_thinking:
            return

        square = self.square_at(pos)
        if square is None:
            self.selected = None
            return

        if self.selected is not None:
            moves = self.moves_between(self.selected, square)
            if moves:
                self.choose_move(moves)
                return

        piece = self.gs.board[square[0]][square[1]]
        own_color = "white" if self.gs.white_to_move else "black"
        if piece.startswith(own_color):
            # Pick the piece up: it follows the mouse until the button is released
            self.release_deselects = square == self.selected
            self.selected = self.dragging = square
            self.drag_pos = pos
        else:
            self.selected = None

    def drop(self, pos):
        """The mouse button was released while dragging a piece"""
        start, self.dragging = self.dragging, None
        square = self.square_at(pos)
        if square == start:
            # Released where it was picked up, so it was a click: clicking the
            # selected piece again puts it down, otherwise it stays selected
            if self.release_deselects:
                self.selected = None
            return
        moves = self.moves_between(start, square)
        if moves:
            self.choose_move(moves, animate=False)  # the piece is already where it was dropped
        # Dropped anywhere else, the piece goes back and stays selected

    # ---- board geometry ---------------------------------------------------

    def square_rect(self, r, c):
        """Where square (row, col) is drawn on the screen"""
        if self.flipped:  # turned around, so a5 is bottom right
            r, c = self.gs.rows - 1 - r, self.gs.cols - 1 - c
        size = self.square_size
        return pygame.Rect(self.board_x + c * size, self.board_y + r * size, size, size)

    def square_at(self, pos):
        """The (row, col) under a screen position, or None if it's off the board"""
        board = self.board_rect()
        if board.collidepoint(pos):
            r, c = (pos[1] - board.y) // self.square_size, (pos[0] - board.x) // self.square_size
            return (self.gs.rows - 1 - r, self.gs.cols - 1 - c) if self.flipped else (r, c)
        return None

    def board_rect(self):
        return pygame.Rect(self.board_x, self.board_y, self.gs.cols * self.square_size,
                           self.gs.rows * self.square_size)

    def promotion_options(self):
        """(rect, move) for each piece in the promotion picker, centered on the board"""
        board = self.board_rect()
        left = board.centerx - len(self.promotion_choices) * PICKER_SIZE // 2
        top = board.centery - PICKER_SIZE // 2 + 12
        return [(pygame.Rect(left + i * PICKER_SIZE, top, PICKER_SIZE, PICKER_SIZE), move)
                for i, move in enumerate(self.promotion_choices)]

    def gear_button_rect(self):
        """The settings button, top right of the side panel"""
        return pygame.Rect(SIDE_PANEL_X + SIDE_PANEL_WIDTH - 14 - 26, BOARD_Y + 9, 26, 26)

    def hint_button_rect(self):
        """The Hint button, left of the settings button"""
        return pygame.Rect(self.gear_button_rect().x - 8 - 64, BOARD_Y + 9, 64, 26)

    def game_over_buttons(self):
        """(rect, label, action) for the buttons on the game-over panel"""
        if self.can_review():
            buttons, gap = [("Play again", "again", 112), ("Review", "review", 86), ("Menu", "menu", 72)], 8
        else:
            buttons, gap = [("Play again", "again", 124), ("Menu", "menu", 124)], 12
        x = self.board_rect().centerx - (sum(width for _, _, width in buttons) + gap * (len(buttons) - 1)) // 2
        rects = []
        for label, action, width in buttons:
            rect = pygame.Rect(x, 0, width, 44)
            rect.centery = self.board_rect().centery + 40
            rects.append((rect, label, action))
            x += width + gap
        return rects

    def play_again_rect(self):
        return next(rect for rect, _, action in self.game_over_buttons() if action == "again")

    def menu_button_rect(self):
        return next(rect for rect, _, action in self.game_over_buttons() if action == "menu")

    def review_button_rect(self):
        return next(rect for rect, _, action in self.game_over_buttons() if action == "review")

    def review_buttons(self):
        """(rect, action) for the buttons in the status bar while reviewing a game"""
        widths = {"first": 30, "back": 30, "forward": 30, "last": 30, "done": 56}
        x = WIDTH - 16 - sum(widths.values()) - 6 * (len(widths) - 1)
        buttons = []
        for action, width in widths.items():
            buttons.append((pygame.Rect(x, HEIGHT - STATUS_HEIGHT + 9, width, 30), action))
            x += width + 6
        return buttons

    def move_list_top(self):
        return BOARD_Y + 40 + (46 if self.clock_ms is not None else 0)  # the clocks go above the list

    def move_cells(self):
        """(rect, move index) for each move shown in the move list. Once the list is full the
        oldest moves scroll off the top, except that the move being reviewed stays in view."""
        top = self.move_list_top()
        shown = (BOARD_Y + BOARD_AREA_HEIGHT - 106 - 8 - top) // MOVE_LINE_HEIGHT
        rows = (len(self.move_texts) + 1) // 2
        first = max(0, rows - shown)
        if self.review_index:
            first = min(first, (self.review_index - 1) // 2)
        cells = []
        for row in range(first, min(rows, first + shown)):
            y = top + (row - first) * MOVE_LINE_HEIGHT
            for side in (0, 1):
                if 2 * row + side < len(self.move_texts):
                    rect = pygame.Rect(SIDE_PANEL_X + 14 + 20 + side * 74, y - 4, 72, MOVE_LINE_HEIGHT - 2)
                    cells.append((rect, 2 * row + side))
        return cells

    def keep_playing_rect(self):
        """The buttons of the "Quit the game?" dialog: Keep playing (140 wide) and Quit (100 wide)"""
        rect = pygame.Rect(0, 0, 140, 44)
        rect.midleft = (self.board_rect().centerx - 126, self.board_rect().centery + 40)
        return rect

    def quit_rect(self):
        rect = pygame.Rect(0, 0, 100, 44)
        rect.midleft = (self.keep_playing_rect().right + 12, self.board_rect().centery + 40)
        return rect

    # ---- start menu geometry ----------------------------------------------

    def menu_headings(self):
        """(heading, setting, position, button height) for each group of choices on the start menu"""
        left = (WIDTH - MENU_WIDTH) // 2
        headings, top = [], 88
        for heading, setting, _ in MENU_CHOICES:
            height = 60 if setting == "variant_key" else 40  # room for a picture of each board
            headings.append((heading, setting, (left, top), height))
            top += 24 + height + 14
        return headings

    def menu_buttons(self):
        """(rect, setting, value, label) for every choice button on the start menu"""
        buttons = []
        for (_, setting, (left, top), height), (_, _, choices) in zip(self.menu_headings(), MENU_CHOICES):
            gap = 10
            width = (MENU_WIDTH - gap * (len(choices) - 1)) // len(choices)
            for i, (label, value) in enumerate(choices):
                rect = pygame.Rect(left + i * (width + gap), top + 24, width, height)
                buttons.append((rect, setting, value, label))
        return buttons

    def menu_setting_enabled(self, setting):
        # Side and difficulty only matter against the computer
        return setting in ("variant_key", "two_players") or not self.two_players

    def menu_settings_rect(self):
        return pygame.Rect((WIDTH - MENU_WIDTH) // 2, 424, 128, 48)

    def start_button_rect(self):
        settings_button = self.menu_settings_rect()
        return pygame.Rect(settings_button.right + 12, 424, MENU_WIDTH - settings_button.width - 12, 48)

    # ---- settings screen geometry -----------------------------------------

    def settings_rows(self):
        """(rect, setting) for each switch on the settings screen; clicking anywhere on the row flips it"""
        left = (WIDTH - MENU_WIDTH) // 2
        return [(pygame.Rect(left, 84 + i * SETTINGS_ROW_HEIGHT, MENU_WIDTH, SETTINGS_ROW_HEIGHT - 6), name)
                for i, (_, name) in enumerate(SETTING_SWITCHES)]

    def clock_choice_rects(self):
        """(rect, minutes) for each choice on the clock's row of the settings screen"""
        row = next(rect for rect, name in self.settings_rows() if name == "clock")
        width, gap = 38, 4
        left = row.right - 10 - len(CLOCK_CHOICES) * width - (len(CLOCK_CHOICES) - 1) * gap
        return [(pygame.Rect(left + i * (width + gap), row.y + 4, width, row.height - 8), minutes)
                for i, (_, minutes) in enumerate(CLOCK_CHOICES)]

    def done_button_rect(self):
        rect = pygame.Rect(0, 0, 200, 48)
        rect.center = (WIDTH // 2, 448)
        return rect

    # ---- drawing ----------------------------------------------------------

    def draw(self):
        self.screen.fill(BACKGROUND)
        if self.in_settings:
            self.draw_settings()
            return
        if self.in_menu:
            self.draw_menu()
            return
        self.draw_board()
        if self.settings["coordinates"]:
            self.draw_coordinates()
        if self.eval_score is not None:
            self.draw_eval_bar()
        self.draw_side_panel()
        self.draw_status()
        if self.dragging:
            self.draw_dragged_piece()
        if self.promotion_choices:
            self.draw_promotion_picker()
        if self.result is not None and self.review_index is None:
            self.draw_game_over()
        if self.confirming_quit:
            self.draw_quit_dialog()

    def draw_menu(self):
        title = self.title_font.render("Micro Chess", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 48)))

        for heading, setting, position, _ in self.menu_headings():
            color = MUTED_TEXT if self.menu_setting_enabled(setting) else DISABLED_TEXT
            self.screen.blit(self.small_font.render(heading.upper(), True, color), position)
            if setting == "variant_key":  # what the chosen board is like, at the end of the line
                about = self.small_font.render(VARIANTS[self.variant_key].description, True, MUTED_TEXT)
                self.screen.blit(about, about.get_rect(topright=(position[0] + MENU_WIDTH, position[1])))

        mouse = pygame.mouse.get_pos()
        for rect, setting, value, label in self.menu_buttons():
            enabled = self.menu_setting_enabled(setting)
            chosen = getattr(self, setting) == value
            hover = enabled and rect.collidepoint(mouse)
            if chosen and enabled:
                fill = BUTTON_HOVER if hover else BUTTON
            else:
                fill = CHOICE_HOVER if hover else CHOICE
            pygame.draw.rect(self.screen, fill, rect, border_radius=10)
            if chosen and not enabled:
                pygame.draw.rect(self.screen, DISABLED_TEXT, rect, 2, border_radius=10)
            color = TEXT if enabled else DISABLED_TEXT
            if setting == "variant_key":
                self.draw_board_icon(VARIANTS[value], (rect.centerx, rect.top + 21))
                text = self.small_font.render(label, True, color)
                self.screen.blit(text, text.get_rect(center=(rect.centerx, rect.bottom - 11)))
            else:
                text = self.font.render(label, True, color)
                self.screen.blit(text, text.get_rect(center=rect.center))

        for button, text, fill, hover_fill in ((self.menu_settings_rect(), "Settings", CHOICE, CHOICE_HOVER),
                                               (self.start_button_rect(), "Start game", BUTTON, BUTTON_HOVER)):
            pygame.draw.rect(self.screen, hover_fill if button.collidepoint(mouse) else fill, button,
                             border_radius=12)
            label = self.font.render(text, True, TEXT)
            self.screen.blit(label, label.get_rect(center=button.center))

    def draw_settings(self):
        title = self.title_font.render("Settings", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 48)))
        mouse = pygame.mouse.get_pos()
        labels = {name: label for label, name in SETTING_SWITCHES}
        for rect, name in self.settings_rows():
            hover = rect.collidepoint(mouse) and name != "clock"
            pygame.draw.rect(self.screen, CHOICE_HOVER if hover else CHOICE, rect, border_radius=8)
            label = self.font.render(labels[name], True, TEXT)
            self.screen.blit(label, label.get_rect(midleft=(rect.x + 14, rect.centery)))
            if name != "clock":
                self.draw_switch(self.settings[name], pygame.Rect(rect.right - 14 - 44, rect.centery - 12, 44, 24))
        for (choice, minutes), (text, _) in zip(self.clock_choice_rects(), CLOCK_CHOICES):
            chosen = self.settings["clock"] == minutes
            fill = (BUTTON_HOVER if choice.collidepoint(mouse) else BUTTON) if chosen else \
                (CHOICE_HOVER if choice.collidepoint(mouse) else BACKGROUND)
            pygame.draw.rect(self.screen, fill, choice, border_radius=6)
            label = self.small_font.render(text, True, TEXT)
            self.screen.blit(label, label.get_rect(center=choice.center))

        button = self.done_button_rect()
        pygame.draw.rect(self.screen, BUTTON_HOVER if button.collidepoint(mouse) else BUTTON, button,
                         border_radius=12)
        label = self.font.render("Done", True, TEXT)
        self.screen.blit(label, label.get_rect(center=button.center))

    def draw_switch(self, on, rect):
        """An on/off switch: green with the knob on the right when on"""
        pygame.draw.rect(self.screen, BUTTON if on else DISABLED_TEXT, rect, border_radius=rect.height // 2)
        knob_x = rect.right - rect.height // 2 if on else rect.x + rect.height // 2
        pygame.draw.circle(self.screen, TEXT, (knob_x, rect.centery), rect.height // 2 - 3)

    def draw_gear(self, center, color):
        """A cog wheel, for the settings button"""
        x, y = center
        for i in range(8):  # the teeth
            direction = pygame.Vector2(1, 0).rotate(i * 45)
            across = pygame.Vector2(-direction.y, direction.x) * 2
            inner, outer = direction * 6, direction * 10
            pygame.draw.polygon(self.screen, color, [(x + p.x, y + p.y) for p in
                                                     (inner - across, outer - across, outer + across, inner + across)])
        pygame.draw.circle(self.screen, color, center, 7)
        pygame.draw.circle(self.screen, SIDE_PANEL, center, 3)

    def draw_board_icon(self, variant, center):
        """A little picture of a game mode's board: its squares, with the holes left out"""
        layout = variant.layout
        width, height = len(layout[0]) * ICON_SQUARE, len(layout) * ICON_SQUARE
        left, top = center[0] - width // 2, center[1] - height // 2
        for r, rank in enumerate(layout):
            for c, square in enumerate(rank):
                if square != "#":
                    color = DARK_SQUARE if (r + c) % 2 == (len(layout) - 1) % 2 else LIGHT_SQUARE
                    self.screen.fill(color, (left + c * ICON_SQUARE, top + r * ICON_SQUARE, ICON_SQUARE, ICON_SQUARE))

    def draw_board(self):
        gs, last_move = self.board_view()
        rows, cols = gs.rows, gs.cols
        for r in range(rows):
            for c in range(cols):
                rect = self.square_rect(r, c)
                if gs.board[r][c] == HOLE:  # a hole looks cut out of the board
                    self.screen.fill(HOLE_COLOR, rect)
                    pygame.draw.rect(self.screen, HOLE_EDGE, rect.inflate(-6, -6), 3, border_radius=4)
                    continue
                # a1 (bottom left) is a dark square
                color = DARK_SQUARE if (r + c) % 2 == (rows - 1) % 2 else LIGHT_SQUARE
                self.screen.fill(color, rect)

        if last_move:
            for r, c in ((last_move.start_row, last_move.start_col), (last_move.end_row, last_move.end_col)):
                self.screen.blit(self.last_move_overlay, self.square_rect(r, c))
        if self.selected:
            self.screen.blit(self.selected_overlay, self.square_rect(*self.selected))
        if self.check if self.review_index is None else gs.in_check():
            king = gs.white_king_location if gs.white_to_move else gs.black_king_location
            self.screen.blit(self.check_overlay, self.square_rect(*king))

        # A moving piece is drawn on its way, not on its new square; anything it
        # captures stays visible until the piece arrives
        sliding, progress = self.sliding_pieces()
        arriving = {to_square for _, _, to_square in sliding}
        for r in range(rows):
            for c in range(cols):
                piece = self.animation[0].piece_captured if (r, c) in arriving else gs.board[r][c]
                if piece not in (EMPTY, HOLE):
                    image = self.images[piece]
                    if (r, c) == self.dragging:  # only a faint copy stays behind
                        image = image.copy()
                        image.set_alpha(GHOST_ALPHA)
                    self.screen.blit(image, image.get_rect(center=self.square_rect(r, c).center))
        for piece, from_square, to_square in sliding:
            (x1, y1), (x2, y2) = self.square_rect(*from_square).center, self.square_rect(*to_square).center
            center = (x1 + (x2 - x1) * progress, y1 + (y2 - y1) * progress)
            image = self.images[piece]
            self.screen.blit(image, image.get_rect(center=center))

        if self.hint:
            self.draw_arrow(self.hint, HINT_ARROW)
        better = self.better_move()
        if better:
            self.draw_arrow(better, BETTER_ARROW)

        if self.selected and self.settings["show_moves"]:
            for move in self.moves_from(self.selected):
                hint = self.move_dot if move.piece_captured == EMPTY else self.capture_ring
                self.screen.blit(hint, self.square_rect(move.end_row, move.end_col))

        if self.dragging and self.settings["show_moves"]:
            target = self.square_at(self.drag_pos)
            if target and self.moves_between(self.dragging, target):
                pygame.draw.rect(self.screen, DROP_TARGET, self.square_rect(*target), 4)

    def better_move(self):
        """While reviewing a move that was marked as a mistake, the move that would have been better"""
        if self.review_index and self.review_index <= len(self.review_marks):
            return self.review_marks[self.review_index - 1][1]
        return None

    def draw_arrow(self, move, color):
        """A see-through arrow from a move's starting square to its end square"""
        board = self.board_rect()
        layer = pygame.Surface(board.size, pygame.SRCALPHA)
        corner = pygame.Vector2(board.topleft)
        start = pygame.Vector2(self.square_rect(move.start_row, move.start_col).center) - corner
        end = pygame.Vector2(self.square_rect(move.end_row, move.end_col).center) - corner
        direction = (end - start).normalize()
        across = pygame.Vector2(-direction.y, direction.x)
        scale = self.square_size / SQUARE_SIZE
        tip = end - direction * 10 * scale
        head_base = tip - direction * 28 * scale
        pygame.draw.line(layer, color, start, head_base, round(12 * scale))
        pygame.draw.polygon(layer, color, [tip, head_base + across * 20 * scale, head_base - across * 20 * scale])
        self.screen.blit(layer, board)

    def draw_eval_bar(self):
        """Who is ahead, by the AI's reckoning: White's part of the bar grows from White's side"""
        white_height = round(EVAL_BAR.height * white_share(self.eval_score))
        self.screen.fill((40, 44, 40), EVAL_BAR)
        white_y = EVAL_BAR.y if self.flipped else EVAL_BAR.bottom - white_height
        self.screen.fill((240, 240, 235), (EVAL_BAR.x, white_y, EVAL_BAR.width, white_height))
        pygame.draw.rect(self.screen, MUTED_TEXT, EVAL_BAR, 1)
        label = self.small_font.render(score_text(self.eval_score), True, MUTED_TEXT)
        self.screen.blit(label, label.get_rect(center=(EVAL_BAR.centerx, EVAL_BAR.bottom + 16)))

    def draw_dragged_piece(self):
        """The piece being dragged, under the mouse and on top of everything else"""
        image = self.images[self.gs.board[self.dragging[0]][self.dragging[1]]]
        self.screen.blit(image, image.get_rect(center=self.drag_pos))

    def draw_coordinates(self):
        board = self.board_rect()
        for r in range(self.gs.rows):
            label = self.small_font.render(str(self.gs.rows - r), True, MUTED_TEXT)
            rect = self.square_rect(r, 0)
            self.screen.blit(label, label.get_rect(center=(board.x - 18, rect.centery)))
        for c in range(self.gs.cols):
            label = self.small_font.render(FILES[c], True, MUTED_TEXT)
            rect = self.square_rect(self.gs.rows - 1, c)
            self.screen.blit(label, label.get_rect(center=(rect.centerx, board.bottom + 16)))

    def draw_side_panel(self):
        area = pygame.Rect(SIDE_PANEL_X, BOARD_Y, SIDE_PANEL_WIDTH, BOARD_AREA_HEIGHT)
        pygame.draw.rect(self.screen, SIDE_PANEL, area, border_radius=12)
        left = area.x + 14
        self.screen.blit(self.small_font.render("MOVES", True, MUTED_TEXT), (left, area.y + 14))

        mouse = pygame.mouse.get_pos()
        gear = self.gear_button_rect()
        self.draw_gear(gear.center, TEXT if gear.collidepoint(mouse) else MUTED_TEXT)
        if self.settings["hints"]:
            button = self.hint_button_rect()
            if self.can_ask_for_hint():
                fill, text_color = (BUTTON_HOVER if button.collidepoint(mouse) else BUTTON), TEXT
            else:
                fill, text_color = CHOICE, DISABLED_TEXT
            pygame.draw.rect(self.screen, fill, button, border_radius=8)
            label = self.small_font.render("Hint", True, text_color)
            self.screen.blit(label, label.get_rect(center=button.center))

        # Captured pieces at the bottom, one row per side, with the material count for the side ahead
        captured_top = area.bottom - 106
        pygame.draw.line(self.screen, BACKGROUND, (left, captured_top), (area.right - 14, captured_top), 2)
        self.screen.blit(self.small_font.render("CAPTURED", True, MUTED_TEXT), (left, captured_top + 12))
        balance = self.material_balance()
        for i, (pieces, lead) in enumerate(zip(self.captured_pieces(), (balance, -balance))):
            y = captured_top + 36 + i * 32
            x = left
            for piece in pieces:
                self.screen.blit(self.small_images[piece], (x, y))
                x += CAPTURED_SIZE - 6  # overlap a little so up to six pieces fit
            if lead > 0:
                label = self.small_font.render(f"+{lead}", True, MUTED_TEXT)
                self.screen.blit(label, label.get_rect(midleft=(x + 10, y + CAPTURED_SIZE // 2)))

        # The clocks, if there are any, go above the move list
        if self.clock_ms is not None:
            self.draw_clocks(pygame.Rect(left, area.y + 40, area.width - 28, 34))

        # The move list: the latest move (or the one being reviewed) is lit up, and in
        # review, mistakes are marked ? and blunders ??
        current = (len(self.move_texts) if self.review_index is None else self.review_index) - 1
        for rect, index in self.move_cells():
            if index % 2 == 0:
                number = self.small_font.render(f"{index // 2 + 1}.", True, MUTED_TEXT)
                self.screen.blit(number, (left, rect.y + 4))
            if index == current:
                pygame.draw.rect(self.screen, LATEST_MOVE, rect, border_radius=6)
            label = self.small_font.render(self.move_texts[index], True, TEXT)
            self.screen.blit(label, (rect.x + 6, rect.y + 4))
            mark = self.review_marks[index][0] if index < len(self.review_marks) else ""
            if mark:
                self.screen.blit(self.small_font.render(mark, True, MARK_COLORS[mark]),
                                 (rect.x + 6 + label.get_width(), rect.y + 4))

    def draw_review_status(self, bar):
        """While reviewing: which move is shown, what was wrong with it, and the buttons to step through"""
        mouse = pygame.mouse.get_pos()
        buttons = self.review_buttons()
        for rect, action in buttons:
            pygame.draw.rect(self.screen, CHOICE_HOVER if rect.collidepoint(mouse) else CHOICE, rect,
                             border_radius=6)
            label = self.small_font.render(REVIEW_LABELS[action], True, TEXT)
            self.screen.blit(label, label.get_rect(center=rect.center))

        index, total = self.review_index, len(self.move_log)
        text = "Start of the game" if index == 0 else f"Move {index}/{total}: {self.move_texts[index - 1]}"
        if index and index > len(self.review_marks):
            text += " (checking...)"
        elif index:
            mark, better = self.review_marks[index - 1]
            if mark:
                text += f"{mark} better: {move_notation(better, self.gs.rows)}"
        room = buttons[0][0].x - 16 - 12
        label = self.font.render(text, True, TEXT)
        if label.get_width() > room:
            label = self.small_font.render(text, True, TEXT)
        self.screen.blit(label, label.get_rect(midleft=(16, bar.centery)))

    def draw_clocks(self, rect):
        """Each player's time left, side by side; the one that is running is lit up"""
        width = (rect.width - 8) // 2
        to_move = "white" if self.gs.white_to_move else "black"
        for i, side in enumerate(("white", "black")):
            box = pygame.Rect(rect.x + i * (width + 8), rect.y, width, rect.height)
            running = side == to_move and self.result is None
            pygame.draw.rect(self.screen, PANEL if running else BACKGROUND, box, border_radius=8)
            # A white or black dot says whose clock it is
            dot = (box.x + 11, box.centery)
            pygame.draw.circle(self.screen, (250, 250, 245) if side == "white" else (20, 22, 20), dot, 5)
            pygame.draw.circle(self.screen, MUTED_TEXT, dot, 5, 1)
            ms = self.clock_ms[side]
            color = CHECK_TEXT if ms < LOW_TIME_MS else DARK_TEXT if running else TEXT
            label = self.font.render(clock_text(ms), True, color)
            self.screen.blit(label, label.get_rect(midright=(box.right - 8, box.centery)))

    def draw_status(self):
        bar = pygame.Rect(0, HEIGHT - STATUS_HEIGHT, WIDTH, STATUS_HEIGHT)
        self.screen.fill(STATUS_BACKGROUND, bar)
        if self.review_index is not None:
            self.draw_review_status(bar)
            return

        if self.result is not None:
            text, color = result_line(self.result, self.gs.white_to_move), TEXT
        elif self.ai_thinking:
            text, color = "Thinking...", MUTED_TEXT
        elif self.hint_thinking:
            text, color = "Finding a hint...", MUTED_TEXT
        else:
            side = "White" if self.gs.white_to_move else "Black"
            text, color = f"{side} to move", TEXT
            if self.check:
                text, color = f"{text} - Check!", CHECK_TEXT
            if self.hint:
                text += f" - hint: {move_notation(self.hint, self.gs.rows)}"
        label = self.font.render(text, True, color)
        self.screen.blit(label, label.get_rect(midleft=(16, bar.centery)))

        keys = ("H hint  " if self.settings["hints"] else "") + "R restart  U undo  N menu  S settings"
        keys = self.small_font.render(keys, True, MUTED_TEXT)
        if label.get_width() + keys.get_width() + 48 <= WIDTH:
            self.screen.blit(keys, keys.get_rect(midright=(WIDTH - 16, bar.centery)))

    def dim_board(self):
        board = self.board_rect()
        shade = pygame.Surface(board.size, pygame.SRCALPHA)
        shade.fill(DIM)
        self.screen.blit(shade, board)

    def draw_panel(self, rect):
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=12)

    def draw_promotion_picker(self):
        self.dim_board()
        options = self.promotion_options()
        area = options[0][0].unionall([rect for rect, _ in options]).inflate(24, 24)
        area.height += 36  # room for the title above the pieces
        area.y -= 36
        self.draw_panel(area)
        title = self.font.render("Promote to", True, DARK_TEXT)
        self.screen.blit(title, title.get_rect(midtop=(area.centerx, area.top + 12)))

        color = "white" if self.gs.white_to_move else "black"
        mouse = pygame.mouse.get_pos()
        for rect, move in options:
            fill = LIGHT_SQUARE if rect.collidepoint(mouse) else PANEL
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            image = self.images[f"{color}_{move.promotion_piece}"]
            self.screen.blit(image, image.get_rect(center=rect.center))

    def draw_dialog(self, title, detail, buttons):
        """A panel over the dimmed board: a title, a line of text and [(rect, label, fill, hover fill)] buttons"""
        self.dim_board()
        area = pygame.Rect(0, 0, BOARD_AREA_WIDTH - 16, 176)
        area.center = self.board_rect().center
        self.draw_panel(area)

        title_label = self.big_font.render(title, True, DARK_TEXT)
        self.screen.blit(title_label, title_label.get_rect(center=(area.centerx, area.top + 36)))
        detail_label = self.font.render(detail, True, DARK_TEXT)
        self.screen.blit(detail_label, detail_label.get_rect(center=(area.centerx, area.top + 72)))

        mouse = pygame.mouse.get_pos()
        for button, text, fill, hover_fill in buttons:
            pygame.draw.rect(self.screen, hover_fill if button.collidepoint(mouse) else fill, button,
                             border_radius=10)
            label = self.font.render(text, True, TEXT)
            self.screen.blit(label, label.get_rect(center=button.center))

    def draw_game_over(self):
        title, detail = game_over_text(self.result, self.gs.white_to_move)
        self.draw_dialog(title, detail, [(rect, label, BUTTON, BUTTON_HOVER)
                                         for rect, label, _ in self.game_over_buttons()])

    def draw_quit_dialog(self):
        self.draw_dialog("Quit the game?", "This game will be lost",
                         [(self.keep_playing_rect(), "Keep playing", BUTTON, BUTTON_HOVER),
                          (self.quit_rect(), "Quit", CHOICE, CHOICE_HOVER)])

    # ---- main loop --------------------------------------------------------

    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()


def main():
    ChessGUI().run()


if __name__ == "__main__":
    main()
