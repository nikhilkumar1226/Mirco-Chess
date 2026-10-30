"""Micro Chess in a pygame window: click a piece, then click the square to move it to.

The AI thinks in a background thread, so the window keeps responding while it searches.
"""

import copy
import os
import queue
import threading

import pygame

from ai import get_ai_move
from chess_engine import GameState, ROWS, COLS, EMPTY

# Layout, in pixels
SQUARE_SIZE = 80
PIECE_SIZE = 64
BOARD_X, BOARD_Y = 36, 20  # top-left corner of the board; the margins hold the coordinates
BOARD_WIDTH, BOARD_HEIGHT = COLS * SQUARE_SIZE, ROWS * SQUARE_SIZE
STATUS_HEIGHT = 48
WIDTH = BOARD_X + BOARD_WIDTH + 20
HEIGHT = BOARD_Y + BOARD_HEIGHT + 32 + STATUS_HEIGHT
FPS = 60

# Colors
DARK_SQUARE = pygame.Color("#96b68d")
LIGHT_SQUARE = pygame.Color("#c8d6c9")
BACKGROUND = pygame.Color("#262b25")
STATUS_BACKGROUND = pygame.Color("#1c201b")
PANEL = pygame.Color("#eef2ec")
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
CHECK = (225, 40, 30)
DIM = (10, 14, 10, 150)

FILES = "abcd"
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
PIECE_NAMES = [f"{color}_{kind}" for color in ("white", "black")
               for kind in ("king", "rook", "bishop", "knight", "pawn")]

# Start menu: (heading, the setting it changes, [(button label, value), ...])
MENU_CHOICES = [
    ("Opponent", "two_players", [("Computer", False), ("2 Players", True)]),
    ("Play as", "human_is_white", [("White", True), ("Black", False)]),
    ("Difficulty", "difficulty", [("Easy", "easy"), ("Medium", "medium"), ("Hard", "hard")]),
]
MENU_WIDTH = 312

DRAW_TEXT = {
    "stalemate": ("Stalemate", "It's a draw"),
    "repetition": ("Draw", "Threefold repetition"),
    "insufficient_material": ("Draw", "Insufficient material"),
}


def load_piece_images():
    """Load images/<piece>.png for every piece, scaled to fit a square"""
    images = {}
    for name in PIECE_NAMES:
        image = pygame.image.load(os.path.join(IMAGE_DIR, f"{name}.png")).convert_alpha()
        images[name] = pygame.transform.smoothscale(image, (PIECE_SIZE, PIECE_SIZE))
    return images


def translucent_square(rgba):
    surface = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
    surface.fill(rgba)
    return surface


def check_glow():
    """A red glow, strongest in the middle, drawn under a king that is in check"""
    surface = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
    center = SQUARE_SIZE // 2
    for radius in range(center, 0, -2):
        alpha = int(230 * (1 - radius / center) ** 0.6)
        pygame.draw.circle(surface, (*CHECK, alpha), (center, center), radius)
    return surface


def game_over_text(result, white_to_move):
    """(title, detail) saying how the game ended (result comes from get_game_result())"""
    if result == "checkmate":
        winner = "Black" if white_to_move else "White"
        return "Checkmate!", f"{winner} wins"
    return DRAW_TEXT[result]


def result_line(result, white_to_move):
    """How the game ended, in one line for the status bar"""
    title, detail = game_over_text(result, white_to_move)
    if result == "checkmate":
        return f"{title} {detail}"
    return f"{title} - {detail.lower()}"


class ChessGUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Micro Chess")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.images = load_piece_images()
        self.font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 22)
        self.big_font = pygame.font.Font(None, 44)
        self.title_font = pygame.font.Font(None, 64)

        self.last_move_overlay = translucent_square(LAST_MOVE)
        self.selected_overlay = translucent_square(SELECTED)
        self.check_overlay = check_glow()
        self.move_dot = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        pygame.draw.circle(self.move_dot, MOVE_HINT, (SQUARE_SIZE // 2, SQUARE_SIZE // 2), 13)
        self.capture_ring = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        pygame.draw.circle(self.capture_ring, MOVE_HINT, (SQUARE_SIZE // 2, SQUARE_SIZE // 2),
                           SQUARE_SIZE // 2 - 2, 7)

        # Settings chosen on the start menu
        self.two_players = False
        self.human_is_white = True
        self.difficulty = "medium"

        self.ai_results = queue.Queue()  # (search id, move) pairs from the AI thread
        self.search_id = 0
        self.running = True
        self.in_menu = True
        self.new_game()

    # ---- game state -------------------------------------------------------

    def start_game(self):
        """Leave the start menu and play with the chosen settings"""
        self.in_menu = False
        self.new_game()

    def open_menu(self):
        self.in_menu = True
        self.cancel_ai()

    def new_game(self):
        self.gs = GameState()
        self.move_log = []  # every move played, so U can take moves back
        self.selected = None  # (row, col) of the piece the player picked up
        self.promotion_choices = None  # the moves to pick from while the promotion picker is open
        self.cancel_ai()
        self.refresh()

    def refresh(self):
        """Work out the legal moves and the game's status after the position changed"""
        self.valid_moves = self.gs.get_valid_moves()
        self.result = self.gs.get_game_result()
        self.check = self.gs.in_check()
        self.last_move = self.move_log[-1] if self.move_log else None

    def play(self, move):
        self.gs.make_move(move)
        self.move_log.append(move)
        self.selected = None
        self.promotion_choices = None
        self.refresh()

    def undo(self):
        """Take back your last move and the AI's reply to it (one move in a 2-player game)"""
        # While the AI is thinking (or after you ended the game) only your move needs taking back
        count = 2 if self.is_human_turn() and not self.two_players else 1
        if len(self.move_log) < count:
            return
        for _ in range(count):
            self.gs.undo_move(self.move_log.pop())
        self.cancel_ai()
        self.selected = None
        self.promotion_choices = None
        self.refresh()

    def is_human_turn(self):
        return self.two_players or self.gs.white_to_move == self.human_is_white

    def moves_from(self, square):
        return [m for m in self.valid_moves if (m.start_row, m.start_col) == square]

    # ---- AI ---------------------------------------------------------------

    def start_ai(self):
        """Search for the AI's move in a background thread so the window doesn't freeze.

        The search makes and undoes moves on the board while it works, so it gets its own copy.
        """
        self.ai_thinking = True
        self.search_id += 1
        search_id, position, difficulty = self.search_id, copy.deepcopy(self.gs), self.difficulty

        def think():
            self.ai_results.put((search_id, get_ai_move(position, difficulty)))

        self.ai_thread = threading.Thread(target=think, daemon=True)
        self.ai_thread.start()

    def cancel_ai(self):
        """Forget any search still running (its answer is ignored when it arrives)"""
        self.search_id += 1
        self.ai_thinking = False

    def update(self):
        """Once per frame: play the AI's move when it is ready, or start the AI when it's its turn"""
        while not self.ai_results.empty():
            search_id, ai_move = self.ai_results.get()
            if search_id == self.search_id:
                self.ai_thinking = False
                # The AI searched a copy of the game: play the same move on the real one
                self.play(next(m for m in self.valid_moves if m == ai_move))
        if not self.in_menu and self.result is None and not self.is_human_turn() and not self.ai_thinking:
            self.start_ai()

    # ---- input ------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif self.in_menu:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.start_game()
            elif event.key == pygame.K_r:
                self.new_game()
            elif event.key == pygame.K_u:
                self.undo()
            elif event.key == pygame.K_n:
                self.open_menu()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.in_menu:
                self.handle_menu_click(event.pos)
            else:
                self.handle_click(event.pos)

    def handle_menu_click(self, pos):
        for rect, setting, value, _ in self.menu_buttons():
            if rect.collidepoint(pos) and self.menu_setting_enabled(setting):
                setattr(self, setting, value)
        if self.start_button_rect().collidepoint(pos):
            self.start_game()

    def handle_click(self, pos):
        if self.result is not None:
            if self.play_again_rect().collidepoint(pos):
                self.new_game()
            elif self.menu_button_rect().collidepoint(pos):
                self.open_menu()
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

        if not self.is_human_turn() or self.ai_thinking:
            return

        square = self.square_at(pos)
        if square is None:
            self.selected = None
            return

        if self.selected is not None:
            moves = [m for m in self.moves_from(self.selected) if (m.end_row, m.end_col) == square]
            if moves:
                if moves[0].is_promotion:
                    self.promotion_choices = moves  # one move per piece; the picker chooses
                else:
                    self.play(moves[0])
                return

        piece = self.gs.board[square[0]][square[1]]
        own_color = "white" if self.gs.white_to_move else "black"
        if piece.startswith(own_color) and square != self.selected:
            self.selected = square
        else:
            self.selected = None

    # ---- board geometry ---------------------------------------------------

    def square_rect(self, r, c):
        return pygame.Rect(BOARD_X + c * SQUARE_SIZE, BOARD_Y + r * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE)

    def square_at(self, pos):
        """The (row, col) under a screen position, or None if it's off the board"""
        x, y = pos[0] - BOARD_X, pos[1] - BOARD_Y
        if 0 <= x < BOARD_WIDTH and 0 <= y < BOARD_HEIGHT:
            return y // SQUARE_SIZE, x // SQUARE_SIZE
        return None

    def board_rect(self):
        return pygame.Rect(BOARD_X, BOARD_Y, BOARD_WIDTH, BOARD_HEIGHT)

    def promotion_options(self):
        """(rect, move) for each piece in the promotion picker, centered on the board"""
        board = self.board_rect()
        left = board.centerx - len(self.promotion_choices) * SQUARE_SIZE // 2
        top = board.centery - SQUARE_SIZE // 2 + 12
        return [(pygame.Rect(left + i * SQUARE_SIZE, top, SQUARE_SIZE, SQUARE_SIZE), move)
                for i, move in enumerate(self.promotion_choices)]

    def play_again_rect(self):
        rect = pygame.Rect(0, 0, 124, 44)
        rect.midright = (self.board_rect().centerx - 6, self.board_rect().centery + 40)
        return rect

    def menu_button_rect(self):
        rect = pygame.Rect(0, 0, 124, 44)
        rect.midleft = (self.board_rect().centerx + 6, self.board_rect().centery + 40)
        return rect

    # ---- start menu geometry ----------------------------------------------

    def menu_headings(self):
        """(heading, setting, position) for each group of choices on the start menu"""
        left = (WIDTH - MENU_WIDTH) // 2
        return [(heading, setting, (left, 150 + i * 92))
                for i, (heading, setting, _) in enumerate(MENU_CHOICES)]

    def menu_buttons(self):
        """(rect, setting, value, label) for every choice button on the start menu"""
        buttons = []
        for (_, setting, (left, top)), (_, _, choices) in zip(self.menu_headings(), MENU_CHOICES):
            gap = 10
            width = (MENU_WIDTH - gap * (len(choices) - 1)) // len(choices)
            for i, (label, value) in enumerate(choices):
                rect = pygame.Rect(left + i * (width + gap), top + 24, width, 44)
                buttons.append((rect, setting, value, label))
        return buttons

    def menu_setting_enabled(self, setting):
        # Side and difficulty only matter against the computer
        return setting == "two_players" or not self.two_players

    def start_button_rect(self):
        rect = pygame.Rect(0, 0, 200, 52)
        rect.center = (WIDTH // 2, 452)
        return rect

    # ---- drawing ----------------------------------------------------------

    def draw(self):
        self.screen.fill(BACKGROUND)
        if self.in_menu:
            self.draw_menu()
            return
        self.draw_board()
        self.draw_coordinates()
        self.draw_status()
        if self.promotion_choices:
            self.draw_promotion_picker()
        if self.result is not None:
            self.draw_game_over()

    def draw_menu(self):
        title = self.title_font.render("Micro Chess", True, TEXT)
        title_rect = title.get_rect(center=(WIDTH // 2, 70))
        self.screen.blit(title, title_rect)
        subtitle = self.small_font.render("Chess on a 4x5 board", True, MUTED_TEXT)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIDTH // 2, title_rect.bottom + 14)))

        for heading, setting, position in self.menu_headings():
            color = MUTED_TEXT if self.menu_setting_enabled(setting) else DISABLED_TEXT
            self.screen.blit(self.small_font.render(heading.upper(), True, color), position)

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
            text = self.font.render(label, True, TEXT if enabled else DISABLED_TEXT)
            self.screen.blit(text, text.get_rect(center=rect.center))

        button = self.start_button_rect()
        hover = button.collidepoint(mouse)
        pygame.draw.rect(self.screen, BUTTON_HOVER if hover else BUTTON, button, border_radius=12)
        label = self.font.render("Start game", True, TEXT)
        self.screen.blit(label, label.get_rect(center=button.center))

    def draw_board(self):
        for r in range(ROWS):
            for c in range(COLS):
                # a1 (row 4, column 0) is a dark square
                color = DARK_SQUARE if (r + c) % 2 == 0 else LIGHT_SQUARE
                self.screen.fill(color, self.square_rect(r, c))

        if self.last_move:
            for r, c in ((self.last_move.start_row, self.last_move.start_col),
                         (self.last_move.end_row, self.last_move.end_col)):
                self.screen.blit(self.last_move_overlay, self.square_rect(r, c))
        if self.selected:
            self.screen.blit(self.selected_overlay, self.square_rect(*self.selected))
        if self.check:
            king = self.gs.white_king_location if self.gs.white_to_move else self.gs.black_king_location
            self.screen.blit(self.check_overlay, self.square_rect(*king))

        for r in range(ROWS):
            for c in range(COLS):
                piece = self.gs.board[r][c]
                if piece != EMPTY:
                    image = self.images[piece]
                    self.screen.blit(image, image.get_rect(center=self.square_rect(r, c).center))

        if self.selected:
            for move in self.moves_from(self.selected):
                hint = self.move_dot if move.piece_captured == EMPTY else self.capture_ring
                self.screen.blit(hint, self.square_rect(move.end_row, move.end_col))

    def draw_coordinates(self):
        for r in range(ROWS):
            label = self.small_font.render(str(ROWS - r), True, MUTED_TEXT)
            rect = self.square_rect(r, 0)
            self.screen.blit(label, label.get_rect(center=(BOARD_X // 2, rect.centery)))
        for c in range(COLS):
            label = self.small_font.render(FILES[c], True, MUTED_TEXT)
            rect = self.square_rect(ROWS - 1, c)
            self.screen.blit(label, label.get_rect(center=(rect.centerx, BOARD_Y + BOARD_HEIGHT + 16)))

    def draw_status(self):
        bar = pygame.Rect(0, HEIGHT - STATUS_HEIGHT, WIDTH, STATUS_HEIGHT)
        self.screen.fill(STATUS_BACKGROUND, bar)

        if self.result is not None:
            text, color = result_line(self.result, self.gs.white_to_move), TEXT
        elif self.ai_thinking:
            text, color = "Thinking...", MUTED_TEXT
        else:
            side = "White" if self.gs.white_to_move else "Black"
            text, color = f"{side} to move", TEXT
            if self.check:
                text, color = f"{text} - Check!", CHECK_TEXT
        label = self.font.render(text, True, color)
        self.screen.blit(label, label.get_rect(midleft=(16, bar.centery)))

        keys = self.small_font.render("R restart  U undo  N menu", True, MUTED_TEXT)
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

    def draw_game_over(self):
        self.dim_board()
        board = self.board_rect()
        area = pygame.Rect(0, 0, BOARD_WIDTH - 32, 176)
        area.center = board.center
        self.draw_panel(area)

        title, detail = game_over_text(self.result, self.gs.white_to_move)
        title_label = self.big_font.render(title, True, DARK_TEXT)
        self.screen.blit(title_label, title_label.get_rect(center=(area.centerx, area.top + 36)))
        detail_label = self.font.render(detail, True, DARK_TEXT)
        self.screen.blit(detail_label, detail_label.get_rect(center=(area.centerx, area.top + 72)))

        mouse = pygame.mouse.get_pos()
        for button, text in ((self.play_again_rect(), "Play again"), (self.menu_button_rect(), "Menu")):
            hover = button.collidepoint(mouse)
            pygame.draw.rect(self.screen, BUTTON_HOVER if hover else BUTTON, button, border_radius=10)
            label = self.font.render(text, True, TEXT)
            self.screen.blit(label, label.get_rect(center=button.center))

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
