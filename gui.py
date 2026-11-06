"""Micro Chess in a pygame window: click a piece and then its new square, or drag it there.

The AI thinks in a background thread, so the window keeps responding while it searches.
The main loop is async so the same code runs in a web browser with pygbag, where there
are no threads: there each search waits for a frame showing "Thinking..." and then runs
with a time limit.
"""

import asyncio
import copy
import json
import os
import queue
import random
import sys
import threading
import traceback

import pygame

import settings
import stats
from ai import (get_ai_move, search_move, analyse, position_score, analyse_position, move_mates_within,
                MATE_SCORE)
from chess_engine import (GameState, ROWS, EMPTY, HOLE, VARIANTS, read_game_code, write_game_code,
                          square_letter)
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
IN_BROWSER = sys.platform == "emscripten"  # running in a web page, made with pygbag
BROWSER_TIME_LIMIT = 1.0  # seconds: in the browser every search stops by then, so the page never freezes for long
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
# The buttons above Start game
MENU_PAGES = [("Puzzles", "puzzles"), ("Editor", "editor"), ("Stats", "stats"), ("Settings", "settings")]

# The board editor: its board sizes as (label, (rows, columns)), the pieces it can place, and
# how many boards it remembers
EDITOR_SIZES = [("4x4", (4, 4)), ("4x5", (5, 4)), ("5x5", (5, 5))]
EDITOR_PIECES = ("king", "rook", "bishop", "knight", "pawn")
SAVED_BOARDS = 20

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
NOTICE_MS = 4000  # how long a message (like "Game code copied") stays up
# Where game codes go when there's no clipboard to copy them to (and are pasted from)
CODE_PATH = os.path.join(os.path.expanduser("~"), ".micro_chess_code.txt")
# The puzzles, made by tools/make_puzzles.py
PUZZLES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles.json")
EVAL_BAR_DEPTH = 4  # how deep the search for the evaluation bar looks (as deep as Medium)
EVAL_BAR = pygame.Rect(BOARD_X + BOARD_AREA_WIDTH + 5, BOARD_Y, 10, BOARD_AREA_HEIGHT)  # between board and panel
REVIEW_DEPTH = 4  # how deep game review searches to judge each move
MISTAKE, BLUNDER = 150, 300  # a move that gives away this many centipawns is marked "?" or "??"
MARK_COLORS = {"?": pygame.Color("#f0b25a"), "??": CHECK_TEXT}
BETTER_ARROW = (60, 175, 85, 170)  # in review, the move that would have been better
MOVE_LINE_HEIGHT = 26  # the move list's rows
REVIEW_LABELS = {"first": "|<", "back": "<", "forward": ">", "last": ">|", "done": "Done"}


def copy_text(text):
    """Put text on the clipboard. Returns False if there's no clipboard to put it on."""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
        return True
    except Exception:  # no clipboard here (in a browser it may not exist at all)
        return False


def pasted_text():
    """The text on the clipboard, or None if it's empty or there's no clipboard"""
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        data = pygame.scrap.get(pygame.SCRAP_TEXT)
    except Exception:
        return None
    text = data.decode("utf-8", errors="replace").replace("\x00", "").strip() if data else ""
    return text or None


def load_puzzles(path=None):
    """The puzzles from puzzles.json: [{"id", "code", "mate_in", "solution"}, ...], or none if it can't be read"""
    try:
        with open(path or PUZZLES_PATH) as file:
            puzzles = json.load(file)
    except (OSError, ValueError):
        return []
    if not isinstance(puzzles, list):
        return []
    return [puzzle for puzzle in puzzles
            if isinstance(puzzle, dict) and {"id", "code", "mate_in", "solution"} <= puzzle.keys()]


def code_problem(code):
    """Why a position code can't be played (see GameState.from_code), or None if it can"""
    try:
        GameState.from_code(code)
    except ValueError as problem:
        return str(problem)
    return None


def board_geometry(rows, cols):
    """(square size, left, top) for a board of this size, as big as fits its space and centered in it"""
    size = min(SQUARE_SIZE, BOARD_AREA_WIDTH // cols, BOARD_AREA_HEIGHT // rows)
    return size, BOARD_X + (BOARD_AREA_WIDTH - cols * size) // 2, BOARD_Y + (BOARD_AREA_HEIGHT - rows * size) // 2


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


def line_text(line, rows, count=4):
    """The first few moves of a line of play, written as in the move list: "b5-c3 d1-c1 a4-a3" """
    return " ".join(move_notation(move, rows) for move in line[:count])


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
        self.notice = None  # (message, time it goes away) shown at the top of the window
        self.waiting_search = None  # in the browser: a search to run at the start of the next frame
        self.eval_waiting = False  # in the browser: the evaluation bar is to be worked out next frame
        self.start_code = None  # a position code to start games from, instead of the board's usual start
        self.stats = stats.load()
        self.in_stats = False  # the stats screen is open (over the start menu)
        self.puzzles = load_puzzles()
        self.puzzle_index = None  # which puzzle is being solved, or None in an ordinary game
        # The board editor (it opens from the start menu, which stays underneath it)
        self.in_editor = False
        self.editor_tool = "white_king"  # a piece, HOLE or EMPTY (the eraser)
        self.editor_white_to_move = True
        self.saved_board_index = -1  # which saved board "Saved boards" showed last
        self.resize_editor(5, 4)
        self.new_game()

    # ---- game state -------------------------------------------------------

    def start_game(self):
        """Leave the start menu and play with the chosen settings"""
        self.in_menu = False
        self.start_code = None
        self.puzzle_index = None
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
        minutes = self.settings["clock"] if self.puzzle_index is None else 0  # puzzles aren't timed
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
            self.record_result()

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
        if self.start_code:
            self.gs = GameState.from_code(self.start_code)
        else:
            self.gs = GameState(variant=VARIANTS[self.variant_key])
        self.start_state = copy.deepcopy(self.gs)  # for the game code
        if self.puzzle_index is not None:
            self.puzzle_white = self.gs.white_to_move  # the solver plays the side to move
            self.puzzle_moves_left = self.puzzles[self.puzzle_index]["mate_in"]
        self.game_recorded = False  # whether this game's result has gone into the stats
        self.puzzle_status = None  # "solved", "failed" or "solution" once the puzzle is over
        self.puzzle_reply = None  # the computer's defence, played once the solver's move has slid into place
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
        # Show the board from Black's side when playing Black against the computer (or solving as Black)
        if self.puzzle_index is not None:
            self.flipped = not self.puzzle_white
        else:
            self.flipped = not self.two_players and not self.human_is_white
        self.cancel_search()
        self.refresh()

    def layout_board(self):
        """Size the squares so this game's board fits its space, and make what's drawn on them"""
        size, self.board_x, self.board_y = board_geometry(self.gs.rows, self.gs.cols)
        self.square_size = size
        self.images = self.images_for(size)

        self.last_move_overlay = translucent_square(LAST_MOVE, size)
        self.selected_overlay = translucent_square(SELECTED, size)
        self.check_overlay = check_glow(size)
        self.move_dot = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.move_dot, MOVE_HINT, (size // 2, size // 2), size // 6)
        self.capture_ring = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.capture_ring, MOVE_HINT, (size // 2, size // 2), size // 2 - 2, size // 11)

    def images_for(self, square_size):
        """The piece images for squares of this size (loaded the first time they're needed)"""
        piece_size = square_size * 4 // 5
        if piece_size not in self.piece_images:
            self.piece_images[piece_size] = load_piece_images(piece_size)
        return self.piece_images[piece_size]

    def refresh(self):
        """Work out the legal moves and the game's status after the position changed"""
        self.valid_moves = self.gs.get_valid_moves()
        self.result = self.gs.get_game_result()
        self.check = self.gs.in_check()
        self.last_move = self.move_log[-1] if self.move_log else None
        self.update_eval()

    def update_eval(self):
        """The score for the evaluation bar and the line of play the AI expects
        (None and an empty line while the bar is switched off, or in a puzzle, where it would give the answer away)"""
        if not self.settings["eval_bar"] or self.puzzle_index is not None:
            self.eval_score, self.eval_line, self.eval_waiting = None, [], False
        elif IN_BROWSER:
            self.eval_waiting = True  # next frame, after this one has shown "Thinking..."
        else:
            self.work_out_eval()

    def work_out_eval(self, time_limit=None):
        self.eval_score, self.eval_line = analyse_position(self.board_view()[0], EVAL_BAR_DEPTH, time_limit)
        self.eval_waiting = False

    def show_notice(self, message):
        self.notice = (message, pygame.time.get_ticks() + NOTICE_MS)

    def game_code(self):
        """This game as text: the position it started from and the moves played since"""
        return write_game_code(self.start_state, self.move_log)

    def copy_game_code(self):
        """Ctrl+C (Cmd+C on a Mac): copy the game code, or save it to a file if there's no clipboard"""
        code = self.game_code()
        if copy_text(code):
            self.show_notice("Game code copied")
            return
        try:
            with open(CODE_PATH, "w") as file:
                file.write(code + "\n")
            self.show_notice(f"No clipboard: saved the game code to {CODE_PATH.replace(os.path.expanduser('~'), '~')}")
        except Exception:  # (a browser may not let it write files at all)
            self.show_notice("Couldn't copy the game code")

    def paste_game_code(self):
        """Ctrl+V (Cmd+V): play on from a game code on the clipboard (or in the file that copying
        saves to when there's no clipboard)"""
        text = pasted_text()
        if text is None:
            try:
                with open(CODE_PATH) as file:
                    text = file.read().strip()
            except Exception:
                text = ""
        if not text:
            self.show_notice("Nothing to paste: copy a game code first")
            return
        try:
            start, moves = read_game_code(text)
        except ValueError as problem:
            self.show_notice(f"That isn't a game code: {problem}")
            return
        self.puzzle_index = None
        self.load_game(start.to_code(), moves)
        self.show_notice("Game loaded")

    def load_game(self, start_code, moves):
        """Start a game from a position code, then play the moves (quickly and silently)"""
        self.start_code = start_code
        self.in_menu = self.in_settings = False
        self.new_game()
        for move in moves:
            self.gs.make_move(move)
            self.move_log.append(move)
            check = self.gs.in_check()
            mated = check and not self.gs.get_valid_moves()
            self.move_texts.append(move_notation(move, self.gs.rows) + ("#" if mated else "+" if check else ""))
        self.refresh()

    def play(self, move, animate=True):
        solving = (self.puzzle_index is not None and self.puzzle_status is None
                   and move.piece_moved.startswith("white" if self.puzzle_white else "black"))
        forces_mate = solving and move_mates_within(self.gs, move, self.puzzle_moves_left)
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
        if solving:
            self.judge_puzzle_move(forces_mate)
        self.record_result()

    def record_result(self):
        """Count a finished game against the computer in the stats, once. Only games from a board's
        usual start count: a position set up in the editor (or pasted in) could be a sure win."""
        if (self.result is None or self.game_recorded or self.two_players or self.puzzle_index is not None
                or self.start_code is not None):
            return
        self.game_recorded = True
        if self.result in ("checkmate", "time"):
            outcome = "loss" if self.gs.white_to_move == self.human_is_white else "win"  # the side to move lost
        else:
            outcome = "draw"
        before = self.stats["rating"]
        stats.record(self.stats, self.variant_key, self.difficulty, outcome)
        stats.save(self.stats)
        self.show_notice(f"{outcome.title()}: rating {self.stats['rating']} ({self.stats['rating'] - before:+d})")

    def undo(self):
        """Take back your last move and the AI's reply to it (one move in a 2-player game)"""
        if self.puzzle_index is not None:
            return  # in a puzzle, R starts it again instead
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
        if self.puzzle_index is not None:
            return self.gs.white_to_move == self.puzzle_white
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
        """How the i-th move (from 0) did: ("??", better line) if it threw away a lot,
        ("?", better line) if it threw away a fair amount, otherwise ("", []). The better
        line is the move that should have been played, then the moves the AI expects after it.

        A search scores the position before the move (with the best reply to everything)
        and after it; the difference is what the move gave away.
        """
        gs = self.position_after(i)
        white = gs.white_to_move
        # (In the browser with a time limit; the move is then judged one ply less deep than
        # the deepest search before it that finished, so the two scores still compare)
        before = analyse(gs, REVIEW_DEPTH, BROWSER_TIME_LIMIT if IN_BROWSER else None)
        gs.make_move(self.move_log[i])
        played = position_score(gs, before.depth - 1)
        gs.undo_move(self.move_log[i])
        lost = before.score - played if white else played - before.score
        if lost < MISTAKE:
            return "", []
        return ("??" if lost >= BLUNDER else "?"), before.line

    def review_step(self, action):
        """Move through the review: "first", "back", "forward" or "last" (or "done" to stop)"""
        if action == "done":
            self.stop_review()
            return
        targets = {"first": 0, "back": self.review_index - 1, "forward": self.review_index + 1,
                   "last": len(self.move_log)}
        self.show_review_position(targets[action])

    # ---- board editor ---------------------------------------------------------

    def open_editor(self):
        self.in_editor = True

    def open_stats(self):
        self.in_stats = True

    def resize_editor(self, rows, cols):
        """An empty board of this size in the editor"""
        self.editor_size = (rows, cols)
        self.editor_board = [[EMPTY] * cols for _ in range(rows)]

    def editor_code(self):
        """The editor's position as a position code (a "custom" board, which never has castling)"""
        ranks = "/".join("".join(square_letter(piece) for piece in row) for row in self.editor_board)
        return f"custom {ranks} {'w' if self.editor_white_to_move else 'b'} -"

    def editor_problem(self):
        """Why the position in the editor can't be played yet, or None if it can"""
        return code_problem(self.editor_code())

    def play_editor_board(self, two_players):
        """Play the editor's position, against the computer or a friend (once it's a position that can be played)"""
        if self.editor_problem():
            return
        self.two_players = two_players
        self.start_code = self.editor_code()
        self.puzzle_index = None
        self.in_editor = self.in_menu = False
        self.new_game()

    def save_editor_board(self):
        if self.editor_problem():
            return
        boards = self.settings["custom_boards"]
        code = self.editor_code()
        if code in boards:
            boards.remove(code)
        boards.append(code)
        del boards[:-SAVED_BOARDS]  # only the latest are kept
        self.save_settings()
        self.show_notice(f"Board saved ({len(boards)} saved)")

    def load_saved_board(self):
        """Put the next saved board on the editor (they take turns, each time this is pressed)"""
        boards = [code for code in self.settings["custom_boards"] if code_problem(code) is None]
        if not boards:
            return
        self.saved_board_index = (self.saved_board_index + 1) % len(boards)
        game = GameState.from_code(boards[self.saved_board_index])
        self.editor_size = (game.rows, game.cols)
        self.editor_board = [row[:] for row in game.board]
        self.editor_white_to_move = game.white_to_move
        self.show_notice(f"Saved board {self.saved_board_index + 1} of {len(boards)}")

    def handle_editor_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.in_editor = False  # back to the start menu
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.handle_editor_click(event.pos)

    def handle_editor_click(self, pos):
        square = self.editor_square_at(pos)
        if square is not None:
            # Put the chosen piece (or a hole) there, or empty the square with the eraser
            r, c = square
            self.editor_board[r][c] = self.editor_tool
            return
        if self.editor_back_rect().collidepoint(pos):
            self.in_editor = False
            return
        for rect, action, value, _ in self.editor_controls():
            if not rect.collidepoint(pos) or not self.editor_control_enabled(action, value):
                continue
            if action == "size":
                self.resize_editor(*value)
            elif action == "clear":
                self.resize_editor(*self.editor_size)
            elif action in ("piece", "tool"):
                self.editor_tool = value
            elif action == "side":
                self.editor_white_to_move = value
            elif action == "save":
                self.save_editor_board()
            elif action == "saved":
                self.load_saved_board()
            elif action == "play":
                self.play_editor_board(two_players=value)

    def editor_control_enabled(self, action, value):
        if action in ("play", "save"):
            return self.editor_problem() is None
        if action == "saved":
            return bool(self.settings["custom_boards"])
        return True

    # ---- puzzles ------------------------------------------------------------

    def open_puzzles(self):
        """Start the first puzzle not solved yet (or the first one, once they're all solved)"""
        solved = self.settings["solved_puzzles"]
        unsolved = [i for i, puzzle in enumerate(self.puzzles) if puzzle["id"] not in solved]
        if self.puzzles:
            self.start_puzzle(unsolved[0] if unsolved else 0)

    def start_puzzle(self, index):
        self.puzzle_index = index % len(self.puzzles)
        self.start_code = self.puzzles[self.puzzle_index]["code"]
        self.in_menu = self.in_settings = False
        self.new_game()

    def next_puzzle(self):
        """The next puzzle not solved yet, after this one"""
        solved = self.settings["solved_puzzles"]
        count = len(self.puzzles)
        later = [(self.puzzle_index + step) % count for step in range(1, count + 1)]
        self.start_puzzle(next((i for i in later if self.puzzles[i]["id"] not in solved), later[0]))

    def judge_puzzle_move(self, forces_mate):
        """After the solver's move: solved, a miss, or the computer finds its best defence"""
        puzzle = self.puzzles[self.puzzle_index]
        if self.result == "checkmate":
            self.puzzle_status = "solved"
            if puzzle["id"] not in self.settings["solved_puzzles"]:
                self.settings["solved_puzzles"].append(puzzle["id"])
                self.save_settings()
        elif not forces_mate:
            self.puzzle_status = "failed"
        else:
            self.puzzle_moves_left -= 1
            # The defence that holds out longest, played after the solver's move has slid into place
            self.puzzle_reply = search_move(self.gs, depth=2 * self.puzzle_moves_left, rng=random.Random(0)).move

    def show_solution(self):
        """Play the puzzle's winning line from the start; the review arrows step through it"""
        puzzle = self.puzzles[self.puzzle_index]
        _, moves = read_game_code(" ".join([puzzle["code"]] + puzzle["solution"]))
        self.load_game(puzzle["code"], moves)
        self.puzzle_status = "solution"

    def puzzle_status_line(self):
        """What the status bar says during a puzzle"""
        puzzle = self.puzzles[self.puzzle_index]
        if self.puzzle_status == "solved":
            solved = len(self.settings["solved_puzzles"])
            return f"Solved! {solved} of {len(self.puzzles)} puzzles solved"
        if self.puzzle_status == "failed":
            return "Not quite: there's no forced mate after that"
        if self.puzzle_status == "solution":
            return "The solution: press Left to step back through it"
        side = "White" if self.puzzle_white else "Black"
        moves = self.puzzle_moves_left
        return f"Puzzle {self.puzzle_index + 1}/{len(self.puzzles)}: {side} to move, mate in {moves}"

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
        # With a chess clock, the computer keeps an eye on the time left on its own clock
        time_left = None
        if kind == "ai" and self.clock_ms is not None:
            time_left = self.clock_ms["white" if self.gs.white_to_move else "black"] / 1000

        if IN_BROWSER:
            # No threads in a browser: the search runs at the start of the next frame, once
            # this one has shown "Thinking..."
            self.waiting_search = (search_id, kind, position, difficulty, time_left)
            return
        self.search_thread = threading.Thread(target=self.search_for, daemon=True,
                                              args=(search_id, kind, position, difficulty, time_left))
        self.search_thread.start()

    def search_for(self, search_id, kind, position, difficulty, time_left, time_limit=None):
        """Find a move and hand it to update() (on a thread on the desktop, or straight away in the browser)"""
        try:
            move = get_ai_move(position, difficulty, time_left=time_left, time_limit=time_limit)
        except Exception:
            traceback.print_exc()
            move = None  # update() copes with a search that found nothing
        self.search_results.put((search_id, kind, move))

    def run_waiting_searches(self):
        """In the browser, at the start of a frame: the searches asked for last frame, now that
        it has shown "Thinking...", each stopping within the time limit"""
        if self.waiting_search:
            search, self.waiting_search = self.waiting_search, None
            self.search_for(*search, time_limit=BROWSER_TIME_LIMIT)
        if self.eval_waiting:
            self.work_out_eval(BROWSER_TIME_LIMIT)

    def cancel_search(self):
        """Forget any search still running (its answer is ignored when it arrives)"""
        self.search_id += 1
        self.waiting_search = None
        self.ai_thinking = False
        self.hint_thinking = False

    def can_ask_for_hint(self):
        return (self.settings["hints"] and self.puzzle_index is None and not self.in_menu and self.result is None
                and self.is_human_turn()
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
        if self.puzzle_reply and self.animation is None:
            reply, self.puzzle_reply = self.puzzle_reply, None
            self.play(reply)
        if (not self.in_menu and self.result is None and not self.is_human_turn() and not self.ai_thinking
                and self.puzzle_index is None):
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
        elif self.in_editor:
            self.handle_editor_event(event)
        elif self.in_stats:
            if (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN)) or \
                    (event.type == pygame.MOUSEBUTTONDOWN and self.done_button_rect().collidepoint(event.pos)):
                self.in_stats = False
        elif event.type == pygame.KEYDOWN:
            command = getattr(event, "mod", 0) & (pygame.KMOD_CTRL | pygame.KMOD_META)  # Ctrl, or Cmd on a Mac
            if command and event.key == pygame.K_c and not self.in_menu:
                self.copy_game_code()
            elif command and event.key == pygame.K_v:
                self.paste_game_code()
            elif event.key == pygame.K_ESCAPE and self.review_index is not None:
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
        for rect, _, page in self.menu_page_buttons():
            if rect.collidepoint(pos) and self.menu_page_enabled(page):
                {"puzzles": self.open_puzzles, "editor": self.open_editor, "stats": self.open_stats,
                 "settings": self.open_settings}[page]()

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

        if self.puzzle_status is not None:
            for rect, _, action in self.puzzle_buttons():
                if rect.collidepoint(pos):
                    {"retry": self.new_game, "solution": self.show_solution, "next": self.next_puzzle}[action]()
                    return
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
            return self.dialog_buttons([("Play again", "again", 112), ("Review", "review", 86), ("Menu", "menu", 72)], 8)
        return self.dialog_buttons([("Play again", "again", 124), ("Menu", "menu", 124)], 12)

    def puzzle_buttons(self):
        """(rect, label, action) for the buttons on the panel that ends a puzzle"""
        buttons = [("Retry", "retry", 76), ("Show solution", "solution", 136), ("Next", "next", 68)]
        if self.puzzle_status == "solution":
            buttons.pop(1)
        return self.dialog_buttons(buttons, 8)

    def dialog_buttons(self, buttons, gap):
        """Lay out [(label, action, width), ...] as a centered row of buttons on a dialog over the board"""
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
        headings, top = [], 76
        for heading, setting, _ in MENU_CHOICES:
            height = 60 if setting == "variant_key" else 40  # room for a picture of each board
            headings.append((heading, setting, (left, top), height))
            top += 24 + height + 10
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

    def menu_page_buttons(self):
        """(rect, label, page) for the row of buttons above Start game: Puzzles, Settings and so on"""
        gap = 10
        width = (MENU_WIDTH - gap * (len(MENU_PAGES) - 1)) // len(MENU_PAGES)
        left = (WIDTH - MENU_WIDTH) // 2
        return [(pygame.Rect(left + i * (width + gap), 394, width, 34), label, page)
                for i, (label, page) in enumerate(MENU_PAGES)]

    def menu_page_enabled(self, page):
        return page != "puzzles" or bool(self.puzzles)

    def menu_settings_rect(self):
        return next(rect for rect, _, page in self.menu_page_buttons() if page == "settings")

    def start_button_rect(self):
        return pygame.Rect((WIDTH - MENU_WIDTH) // 2, 438, MENU_WIDTH, 46)

    # ---- board editor geometry ----------------------------------------------

    def editor_square_rect(self, r, c):
        size, left, top = board_geometry(*self.editor_size)
        return pygame.Rect(left + c * size, top + r * size, size, size)

    def editor_square_at(self, pos):
        """The (row, col) of the editor's board under a screen position, or None"""
        size, left, top = board_geometry(*self.editor_size)
        rows, cols = self.editor_size
        if left <= pos[0] < left + cols * size and top <= pos[1] < top + rows * size:
            return (pos[1] - top) // size, (pos[0] - left) // size
        return None

    def editor_controls(self):
        """(rect, action, value, label) for every button on the editor's panel, top to bottom"""
        left, width = SIDE_PANEL_X + 14, SIDE_PANEL_WIDTH - 28
        controls = []

        def row(y, height, items):
            """[(action, value, label), ...] side by side across the panel"""
            gap = 4
            item_width = (width - gap * (len(items) - 1)) // len(items)
            for i, (action, value, label) in enumerate(items):
                controls.append((pygame.Rect(left + i * (item_width + gap), y, item_width, height), action, value, label))

        row(BOARD_Y + 28, 28, [("size", size, label) for label, size in EDITOR_SIZES])
        row(BOARD_Y + 86, 32, [("piece", f"white_{kind}", "") for kind in EDITOR_PIECES])
        row(BOARD_Y + 120, 32, [("piece", f"black_{kind}", "") for kind in EDITOR_PIECES])
        row(BOARD_Y + 158, 28, [("tool", HOLE, "Hole"), ("tool", EMPTY, "Eraser"), ("clear", None, "Clear")])
        row(BOARD_Y + 216, 28, [("side", True, "White"), ("side", False, "Black")])
        row(BOARD_Y + 254, 28, [("save", None, "Save"), ("saved", None, "Saved")])
        row(BOARD_Y + 296, 32, [("play", False, "Play the computer")])
        row(BOARD_Y + 334, 32, [("play", True, "Play a friend")])
        return controls

    def editor_back_rect(self):
        """The Back button, at the right of the status bar"""
        return pygame.Rect(WIDTH - 16 - 64, HEIGHT - STATUS_HEIGHT + 9, 64, 30)

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
        elif self.in_editor:
            self.draw_editor()
        elif self.in_stats:
            self.draw_stats()
        elif self.in_menu:
            self.draw_menu()
        else:
            self.draw_game()
        if self.notice and pygame.time.get_ticks() < self.notice[1]:
            self.draw_notice(self.notice[0])

    def draw_notice(self, message):
        """A short message in a dark box at the top of the window"""
        label = self.small_font.render(message, True, TEXT)
        box = label.get_rect(midtop=(WIDTH // 2, 6)).inflate(20, 12)
        box.top = 4
        pygame.draw.rect(self.screen, STATUS_BACKGROUND, box, border_radius=8)
        pygame.draw.rect(self.screen, MUTED_TEXT, box, 1, border_radius=8)
        self.screen.blit(label, label.get_rect(center=box.center))

    def draw_game(self):
        self.draw_board()
        if self.settings["coordinates"]:
            self.draw_coordinates()
        if self.eval_score is not None or self.eval_waiting:
            self.draw_eval_bar()
        self.draw_side_panel()
        self.draw_status()
        if self.dragging:
            self.draw_dragged_piece()
        if self.promotion_choices:
            self.draw_promotion_picker()
        if self.puzzle_status is not None and self.review_index is None:
            self.draw_puzzle_dialog()
        elif self.result is not None and self.review_index is None and self.puzzle_index is None:
            self.draw_game_over()
        if self.confirming_quit:
            self.draw_quit_dialog()

    def draw_menu(self):
        title = self.title_font.render("Micro Chess", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 40)))

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

        for button, text, page in self.menu_page_buttons():
            enabled = self.menu_page_enabled(page)
            hover = enabled and button.collidepoint(mouse)
            pygame.draw.rect(self.screen, CHOICE_HOVER if hover else CHOICE, button, border_radius=10)
            label = self.small_font.render(text, True, TEXT if enabled else DISABLED_TEXT)
            self.screen.blit(label, label.get_rect(center=button.center))
        button = self.start_button_rect()
        pygame.draw.rect(self.screen, BUTTON_HOVER if button.collidepoint(mouse) else BUTTON, button,
                         border_radius=12)
        label = self.font.render("Start game", True, TEXT)
        self.screen.blit(label, label.get_rect(center=button.center))

    def draw_stats(self):
        """The rating, and wins-draws-losses against the computer on each board at each level"""
        title = self.title_font.render("Stats", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 48)))
        rating = self.big_font.render(f"Rating {self.stats['rating']}", True, TEXT)
        self.screen.blit(rating, rating.get_rect(center=(WIDTH // 2, 104)))
        levels = "   ".join(f"{level.title()} {stats.LEVEL_RATINGS[level]}" for level in stats.LEVEL_RATINGS)
        about = self.small_font.render(f"The computer's ratings: {levels}", True, MUTED_TEXT)
        self.screen.blit(about, about.get_rect(center=(WIDTH // 2, 136)))

        left = (WIDTH - MENU_WIDTH) // 2
        columns = [left + 120 + i * 94 for i in range(3)]  # the centers of the Easy, Medium and Hard columns
        for x, level in zip(columns, stats.LEVEL_RATINGS):
            label = self.small_font.render(level.upper(), True, MUTED_TEXT)
            self.screen.blit(label, label.get_rect(center=(x + 40, 172)))
        rows = [(variant.name, key) for key, variant in VARIANTS.items()]
        for i, (name, key) in enumerate(rows):
            y = 200 + i * 40
            pygame.draw.rect(self.screen, CHOICE, (left, y - 15, MENU_WIDTH, 32), border_radius=8)
            self.screen.blit(self.font.render(name, True, TEXT), (left + 14, y - 9))
            for x, level in zip(columns, stats.LEVEL_RATINGS):
                wins, draws, losses = stats.counts_for(self.stats, key, level)
                color = TEXT if wins + draws + losses else DISABLED_TEXT
                cell = self.font.render(f"{wins}-{draws}-{losses}", True, color)
                self.screen.blit(cell, cell.get_rect(center=(x + 40, y + 1)))
        note = self.small_font.render("Wins-draws-losses against the computer, from each board's usual start",
                                      True, MUTED_TEXT)
        self.screen.blit(note, note.get_rect(center=(WIDTH // 2, 200 + len(rows) * 40)))

        button = self.done_button_rect()
        mouse = pygame.mouse.get_pos()
        pygame.draw.rect(self.screen, BUTTON_HOVER if button.collidepoint(mouse) else BUTTON, button,
                         border_radius=12)
        label = self.font.render("Done", True, TEXT)
        self.screen.blit(label, label.get_rect(center=button.center))

    def draw_editor(self):
        """The board editor: the board on the left, the panel of pieces and buttons on the right"""
        rows, cols = self.editor_size
        size = board_geometry(rows, cols)[0]
        images = self.images_for(size)
        for r in range(rows):
            for c in range(cols):
                rect = self.editor_square_rect(r, c)
                piece = self.editor_board[r][c]
                if piece == HOLE:
                    self.screen.fill(HOLE_COLOR, rect)
                    pygame.draw.rect(self.screen, HOLE_EDGE, rect.inflate(-6, -6), 3, border_radius=4)
                    continue
                self.screen.fill(DARK_SQUARE if (r + c) % 2 == (rows - 1) % 2 else LIGHT_SQUARE, rect)
                if piece != EMPTY:
                    self.screen.blit(images[piece], images[piece].get_rect(center=rect.center))

        area = pygame.Rect(SIDE_PANEL_X, BOARD_Y, SIDE_PANEL_WIDTH, BOARD_AREA_HEIGHT)
        pygame.draw.rect(self.screen, SIDE_PANEL, area, border_radius=12)
        for text, y in (("BOARD SIZE", 10), ("PIECES", 68), ("TO MOVE", 198)):
            self.screen.blit(self.small_font.render(text, True, MUTED_TEXT), (area.x + 14, area.y + y))
        mouse = pygame.mouse.get_pos()
        for rect, action, value, label in self.editor_controls():
            enabled = self.editor_control_enabled(action, value)
            chosen = ((action == "size" and value == self.editor_size)
                      or (action in ("piece", "tool") and value == self.editor_tool)
                      or (action == "side" and value == self.editor_white_to_move))
            if action == "play":
                fill = (BUTTON_HOVER if rect.collidepoint(mouse) else BUTTON) if enabled else CHOICE
            elif chosen:
                fill = BUTTON
            else:
                fill = CHOICE_HOVER if enabled and rect.collidepoint(mouse) else CHOICE
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            if action == "piece":
                self.screen.blit(self.small_images[value], self.small_images[value].get_rect(center=rect.center))
            else:
                text = self.small_font.render(label, True, TEXT if enabled else DISABLED_TEXT)
                self.screen.blit(text, text.get_rect(center=rect.center))

        # The status bar says what's still wrong with the position, if anything
        bar = pygame.Rect(0, HEIGHT - STATUS_HEIGHT, WIDTH, STATUS_HEIGHT)
        self.screen.fill(STATUS_BACKGROUND, bar)
        problem = self.editor_problem()
        message = self.small_font.render(problem or "Ready to play", True, CHECK_TEXT if problem else TEXT)
        self.screen.blit(message, message.get_rect(midleft=(16, bar.centery)))
        back = self.editor_back_rect()
        pygame.draw.rect(self.screen, CHOICE_HOVER if back.collidepoint(mouse) else CHOICE, back, border_radius=6)
        label = self.small_font.render("Back", True, TEXT)
        self.screen.blit(label, label.get_rect(center=back.center))

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
            line = self.review_marks[self.review_index - 1][1]
            return line[0] if line else None
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
        score = self.eval_score or 0  # (until the first score is worked out, the bar is even)
        white_height = round(EVAL_BAR.height * white_share(score))
        self.screen.fill((40, 44, 40), EVAL_BAR)
        white_y = EVAL_BAR.y if self.flipped else EVAL_BAR.bottom - white_height
        self.screen.fill((240, 240, 235), (EVAL_BAR.x, white_y, EVAL_BAR.width, white_height))
        pygame.draw.rect(self.screen, MUTED_TEXT, EVAL_BAR, 1)
        label = self.small_font.render(score_text(score), True, MUTED_TEXT)
        self.screen.blit(label, label.get_rect(center=(EVAL_BAR.centerx, EVAL_BAR.bottom + 16)))
        # Beside the score, under the side panel: the line the AI expects, as many moves as fit
        left = EVAL_BAR.right + 12
        for count in range(4, 0, -1):
            text = "Thinking..." if self.eval_waiting else line_text(self.eval_line, self.gs.rows, count)
            line = self.small_font.render(text, True, MUTED_TEXT)
            if left + line.get_width() <= WIDTH - 16:
                break
        self.screen.blit(line, line.get_rect(midleft=(left, EVAL_BAR.bottom + 16)))

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
        if self.settings["hints"] and self.puzzle_index is None:
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

        text = self.review_status_text()
        room = buttons[0][0].x - 16 - 12
        label = self.font.render(text, True, TEXT)
        if label.get_width() > room:
            label = self.small_font.render(text, True, TEXT)
        self.screen.blit(label, label.get_rect(midleft=(16, bar.centery)))

    def review_status_text(self):
        """Which move the review shows; for a mistake, also the better move and what the AI expects after it"""
        index, total = self.review_index, len(self.move_log)
        if index == 0:
            return "Start of the game"
        text = f"Move {index}/{total}: {self.move_texts[index - 1]}"
        if index > len(self.review_marks):
            return text + " (checking...)"
        mark, better_line = self.review_marks[index - 1]
        if mark:
            text += f"{mark} better: {line_text(better_line, self.gs.rows, 3)}"
        return text

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

        if self.puzzle_index is not None:
            text, color = self.puzzle_status_line(), TEXT
        elif self.result is not None:
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

        if self.puzzle_index is not None:
            keys = "R retry  N menu"
        else:
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

    def draw_puzzle_dialog(self):
        puzzle = self.puzzles[self.puzzle_index]
        if self.puzzle_status == "solved":
            title, detail = "Solved!", f"Mate in {puzzle['mate_in']}"
        elif self.puzzle_status == "failed":
            title, detail = "Not quite", "That doesn't force mate"
        else:
            title, detail = "Solution", line_text(self.move_log, self.gs.rows, 5)
        self.draw_dialog(title, detail, [(rect, label, BUTTON, BUTTON_HOVER)
                                         for rect, label, _ in self.puzzle_buttons()])

    def draw_quit_dialog(self):
        self.draw_dialog("Quit the game?", "This game will be lost",
                         [(self.keep_playing_rect(), "Keep playing", BUTTON, BUTTON_HOVER),
                          (self.quit_rect(), "Quit", CHOICE, CHOICE_HOVER)])

    # ---- main loop --------------------------------------------------------

    async def run(self):
        while self.running:
            self.run_waiting_searches()  # (only ever any in the browser)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
            await asyncio.sleep(0)  # in the browser, this lets the page show the frame and take input
        pygame.quit()


async def main():
    await ChessGUI().run()


if __name__ == "__main__":
    asyncio.run(main())
