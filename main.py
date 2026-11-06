"""Micro Chess: opens the game window. For the terminal version run play_terminal.py.

The game's main loop is async, so this same file starts it in a web browser with pygbag.
"""

import asyncio

from gui import main

asyncio.run(main())
