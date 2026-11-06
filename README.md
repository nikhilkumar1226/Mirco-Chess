# Micro Chess

![Micro Chess: a game in progress against the computer, with the evaluation bar and the line the computer expects beside the board, and the move list and captured pieces on the right](docs/screenshot.png)

Chess on a 4×5 board, with a pygame interface and a computer opponent.

## What is Micro Chess?

Micro Chess is a small chess variant invented by Glimne in 1997. The board is 4 squares wide and
5 high, and each side has only five pieces: a king, a rook, a bishop, a knight and a pawn. Games
are short and sharp, since a single mistake can decide them.

### Starting position

```
    a   b   c   d
  +---+---+---+---+
5 | k | n | b | r |
  +---+---+---+---+
4 | p |   |   |   |
  +---+---+---+---+
3 |   |   |   |   |
  +---+---+---+---+
2 |   |   |   | P |
  +---+---+---+---+
1 | R | B | N | K |
  +---+---+---+---+
```

Uppercase letters are White, lowercase are Black: **K** king, **R** rook, **B** bishop, **N** knight,
**P** pawn. White moves first.

### Rules

The pieces move as in ordinary chess, with these differences:

- **Pawns** move one square at a time (there is no two-square first move, so no en passant).
- **Promotion:** there is no queen, so a pawn that reaches the far rank becomes a rook, bishop or knight.
- **Castling:** the king moves two squares toward its rook and the rook jumps to the square the king
  crossed. For White that is king d1→b1 and rook a1→c1; for Black, king a5→c5 and rook d5→b5. It's
  allowed only if neither the king nor that rook has moved, the squares between them are empty, and
  the king isn't in check and doesn't pass through or land on an attacked square.
- **Draws:** stalemate, threefold repetition, or insufficient material: neither side has the pieces
  to checkmate. That's the two kings alone, a king and knight against a king, or kings with only
  bishops that all stand on squares of the same color. None of these can ever reach checkmate on
  this board.

## Game modes

Besides the classic 4×5 board, there are three more small boards to choose from on the start menu.
They follow the rules above, except that there's no castling. The starting positions were picked
by having the computer play hundreds of games on candidate setups and keeping ones where White
and Black win about equally often.

**Tiny** (4×4): the quickest games. The pawns meet on the first move.

```
    a   b   c   d
  +---+---+---+---+
4 | k | b | r | n |
  +---+---+---+---+
3 |   | p |   |   |
  +---+---+---+---+
2 |   |   | P |   |
  +---+---+---+---+
1 | N | R | B | K |
  +---+---+---+---+
```

**Donut** (5×5) and **Pillars** (5×5) have holes in the board, marked `#`. No piece can stand on a
hole, and rooks, bishops and pawns can't move across one, but knights jump over holes as usual.
Holes also block check, and a hole next to a king takes away an escape square.

```
Donut                              Pillars
    a   b   c   d   e                  a   b   c   d   e
  +---+---+---+---+---+              +---+---+---+---+---+
5 | r | n |   | b | k |            5 | k |   | n | r | b |
  +---+---+---+---+---+              +---+---+---+---+---+
4 | p | p |   |   |   |            4 | p |   |   |   | p |
  +---+---+---+---+---+              +---+---+---+---+---+
3 |   |   | # |   |   |            3 |   | # |   | # |   |
  +---+---+---+---+---+              +---+---+---+---+---+
2 |   |   |   | P | P |            2 | P |   |   |   | P |
  +---+---+---+---+---+              +---+---+---+---+---+
1 | K | B |   | N | R |            1 | B | R | N |   | K |
  +---+---+---+---+---+              +---+---+---+---+---+
```

## Features

- A pygame interface: click or drag the pieces, with each piece's legal moves marked
- Four boards: the classic 4×5, a 4×4, and two 5×5 boards with holes in them
- Hints: press H (or the Hint button) and an arrow shows the best move the AI can find
- Play against the computer as White or Black (the board turns around when you play Black), at
  Easy, Medium or Hard, or play a friend on the same computer
- Highlights for the last move and for a king in check, plus a picker for pawn promotion
- A side panel with the move list and the captured pieces
- Sliding piece animations, and move and capture sounds generated in code (no sound files)
- A settings screen where you switch the extras on or off: sound, the legal-move dots, animations,
  the Hint button, board coordinates and the "Quit the game?" question. Your settings and your last
  choices on the start menu are remembered between launches
- An optional chess clock (off unless you choose one)
- An optional evaluation bar showing who is ahead, by the computer's reckoning, and the moves it expects
- Game review: step through a finished game, with mistakes marked and a better move shown for each
- Puzzles: 48 checkmate puzzles (mate in 1, 2 or 3) across the four boards, made and checked by the
  computer
- A board editor: set up any position on a 4×4, 4×5 or 5×5 board, with holes if you like, then play
  it against the computer or a friend
- Stats and a rating: your wins, draws and losses against the computer on each board and level, and
  a rating that goes up and down with each game
- Game codes: copy a game as one line of text and paste it back in later, or send it to a friend
- Undo, restart, and a game-over screen with **Play again**
- The computer thinks in a background thread, so the window never freezes
- A terminal version that needs nothing but Python, with all four boards
- A pytest test suite, including GUI tests that run without opening a window

## Installing guide

You need Python 3 (developed with Python 3.13) and pygame 2.1 or newer.

```bash
git clone https://github.com/nikhilkumar1226/Mirco-Chess.git
cd Mirco-Chess
python3 -m pip install -r requirements.txt
python3 main.py
```

To keep the packages separate from the rest of your system, create a virtual environment first:

```bash
python3 -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
```

The terminal version doesn't need pygame:

```bash
python3 play_terminal.py
```

## Controls

On the start menu, choose the board, your opponent (**Computer** or **2 Players**), your color
and the difficulty, then click **Start game** or press Enter.

| Action | Control |
| --- | --- |
| Select a piece | Click it: dots mark the squares it can move to, rings mark captures |
| Move | Click one of the marked squares, or drag the piece there |
| Cancel a selection | Click anywhere else |
| Castle | Move the king two squares (d1→b1 for White, a5→c5 for Black) |
| Promote a pawn | Choose rook, bishop or knight in the picker |
| Hint | **H** or the **Hint** button: an arrow shows the best move (searched at Hard strength) |
| Undo | **U**: takes back your move and the computer's reply (one move in a 2-player game) |
| Restart | **R** |
| Back to the menu | **N** |
| Settings | **S**, the cog button above the move list, or **Settings** on the start menu |
| Sound on/off | **M** (or in Settings) |
| Review a finished game | **Review** on the game-over panel, **←**, or click a move in the list |
| Step through the review | **←** **→**, **Home** / **End**, or the buttons in the status bar; **Esc** to finish |
| Copy the game code | **Ctrl+C** (**Cmd+C** on a Mac) |
| Paste a game code | **Ctrl+V** (**Cmd+V** on a Mac), during a game or on the start menu |
| Puzzles, editor, stats | **Puzzles**, **Editor** and **Stats** on the start menu |
| Quit | **Esc** (once a game has started, it asks first: **Enter** quits, **Esc** keeps playing) |

The settings are saved in a small file, `.micro_chess.json`, in your home folder, along with the
puzzles you've solved and the boards you've saved in the editor. Delete it to go back to the
defaults. The stats are kept next to it, in `.micro_chess_stats.json`.

**Chess clock:** there's no clock unless you pick one in Settings: 1, 3, 5 or 10 minutes for each
player. The running clock is lit up above the move list and turns red in the last 10 seconds. If
your time runs out you lose, unless your opponent has only their king left, which makes it a draw.
The clock stops while the settings or the "Quit the game?" question are open, and choosing a
different clock during a game starts both clocks again.

**Evaluation bar:** switch it on in Settings for a bar between the board and the move list. White's
part grows from White's side of the board as White gets ahead. The number under it is the lead in
pawns (+1.2 means White is ahead by about a pawn, -0.5 Black by half a pawn), or +M2 / -M2 for a
forced mate in 2 moves. Beside the number are the first few moves of the line the computer expects,
such as `b5-c3 d1-c1 a4-a3`. It comes from a 4-move-deep search after every move, the same as Medium.

**Game review:** when a game ends, click **Review** to step through it. The computer checks every
move with a short search, comparing the best score it can find before the move with the score
after it. A move that gave away 1.5 pawns or more is marked **?**, and 3 pawns or more **??**.
For a marked move, a green arrow shows the move that would have been better, and the status bar
shows that move and the moves the computer expects after it. You can switch review off in Settings.

## Puzzles

Click **Puzzles** on the start menu for a checkmate puzzle, such as "White to move: mate in 2". You
play the side to move. While your moves still force mate, the computer answers with its best
defence, the one that holds out longest. Find the mate and it says **Solved!**; play a move that
lets the mate slip and it says **Not quite**. Either way you can **Retry**, **Show solution** (then
press ← to step back through it) or go on to the **Next** puzzle. Solved puzzles are remembered, and
**Puzzles** always starts with one you haven't solved yet. Hints, the evaluation bar, the clock and
undo are switched off during puzzles, since they would give the answer away.

The 48 puzzles in `puzzles.json` were made by `tools/make_puzzles.py`. It plays games between the
computer's levels on every board and keeps each position where exactly one first move forces mate
in 1, 2 or 3 moves, and there's no quicker mate. Every puzzle is then checked again by a plain
search through every move and reply. To make a new set:

```bash
python3 tools/make_puzzles.py
```

## Board editor

Click **Editor** on the start menu. Choose the board's size (4×4, 4×5 or 5×5), pick a piece from the
palette and click squares to put it there. **Hole** cuts a square out of the board, **Eraser** empties
one and **Clear** empties the whole board. Choose which side moves first, then click **Play the
computer** (with the side and difficulty chosen on the start menu) or **Play a friend**.

The status bar says what's wrong until the position can be played: each side needs exactly one
king, a pawn can't stand on the rank where it would promote, and the side that isn't moving can't be
in check. There's no castling on boards made in the editor. **Save** keeps the board, and **Saved**
puts your saved boards back on the editor, one after another. **R** during the game starts it again
from your position.

## Stats and rating

Every game you finish against the computer counts: a win, a draw or a loss on that board at that
level. Your rating starts at 1000 and changes after each game, by how surprising the result was
(the Elo system). The computer's levels count as fixed ratings: Easy 800, Medium 1200 and Hard 1600.
So beating Hard raises your rating a lot, and drawing with Easy lowers it a little. Only games from
a board's usual starting position count, not positions from the editor or pasted in. Click
**Stats** on the start menu to see them.

## Game codes

A position can be written as one line of text, a bit like the FEN codes used for ordinary chess:

```
micro knbr/p.../..../...P/RBNK w WB
```

That's the board (`micro`, `tiny`, `donut`, `pillars`, or `custom` for a board from the editor),
then the ranks from the top down with uppercase letters for White's pieces, lowercase for Black's,
`.` for an empty square and `#` for a hole, then whose move it is (`w` or `b`) and who may still
castle (`WB`, `W`, `B` or `-`). A game code is the starting position's code followed by the moves
played, written as their two squares, with the new piece's letter after a promotion:

```
micro knbr/p.../..../...P/RBNK w WB c1b3 a5b4 b3c5
```

Press **Ctrl+C** (**Cmd+C** on a Mac) during a game to copy its code, and **Ctrl+V** (**Cmd+V**) to
play on from a code. If there's no clipboard, the code is saved to `.micro_chess_code.txt` in your
home folder and pasted back from there. A code that doesn't make sense, or has an illegal move,
just gets a message saying what's wrong with it.

In the terminal version, type a move as two squares, such as `d2 d3`. To castle, type the king's
move (`d1 b1` or `a5 c5`). Type `quit` to leave.

## How the AI works

The computer uses **minimax search with alpha-beta pruning**. It tries every move, every reply to
it, every answer to that reply and so on, assuming both sides always pick their best option.
Alpha-beta pruning skips lines that can't change the final choice, which makes the search much
faster without changing its result.

**It searches deeper and deeper until its time is up** (iterative deepening): first one move (ply)
ahead, then two, then three and so on, each time trying the moves the last search liked best first.
It stops when it reaches its level's depth or its time runs out, and plays the best move from the
deepest search that finished:

| Level | Deepest | Most time |
| --- | --- | --- |
| Easy | 2 plies | 0.3 seconds |
| Medium | 4 plies | 0.8 seconds |
| Hard | 6 plies | 1.5 seconds |

With the chess clock on, it also never takes more than a twentieth of the time left on its clock.

At the end of each line it doesn't stop in the middle of an exchange: it plays on with captures and
promotions until the position is quiet (a **quiescence search**), so it can see that a rook which
has just taken a pawn is about to be taken back. Then it scores the position (positive is good for
White) by adding up:

- **Material:** pawn 100, knight and bishop 300, rook 500
- **Piece-square tables** for the 4×5 board: knights and bishops prefer the center, pawns gain value
  as they advance, and the king stays tucked in its corner while there are pieces around to attack
  it, then heads for the center in the endgame. On the other boards these tables are worked out
  from the board's shape, so squares next to a hole or an edge, where a piece reaches less, count
  for less
- **Mobility:** a small bonus for every square a knight, bishop or rook can move to
- **King safety:** a penalty for every enemy attack on the squares around the king

A few more details:

- Captures and promotions are searched first, which lets alpha-beta prune much more.
- A **transposition table** remembers the positions already searched, so a position reached by a
  different order of moves isn't searched again. It's cleared before every move.
- The search remembers the line it expects both sides to play (the principal variation), which the
  evaluation bar and game review show.
- A checkmate scores far above anything else, and a sooner mate scores higher, so it takes the
  quickest win and puts off a loss as long as it can.
- Draws by stalemate, repetition or insufficient material score 0.
- When several moves score exactly the same, it picks one of them at random.
- On Easy it picks at random from all the moves that score at most 300 (three pawns) below its best,
  so it sometimes gives away a knight or bishop and plays more varied games. It still always takes a
  checkmate in one when it has one.

Hard usually answers in about a tenth of a second, at about 60,000 positions a second, and always
within 2 seconds.

## Running the tests

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

The GUI and sound tests use SDL's dummy video and audio drivers, so no window opens and nothing plays.

## Project structure

```
Mirco-Chess/
├── main.py               # starts the pygame game
├── gui.py                # pygame interface: menu, game, puzzles, editor, settings, stats
├── sounds.py             # move and capture sounds, generated in code
├── settings.py           # loads and saves the settings
├── stats.py              # the stats and the rating
├── play_terminal.py      # the terminal version
├── chess_engine.py       # the rules and the boards: moves, castling, promotion, check, checkmate and draws
├── ai.py                 # the computer player: minimax with alpha-beta pruning
├── puzzles.json          # the puzzles
├── tools/make_puzzles.py # makes puzzles.json
├── images/               # piece images (60×60 PNG)
├── docs/screenshot.png   # the screenshot at the top of this page
├── tests/                # pytest tests
├── requirements.txt      # pygame
├── requirements-dev.txt  # pygame and pytest
└── pytest.ini
```

## License

MIT. See [LICENSE](LICENSE).
