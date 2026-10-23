"""Colored terminal output."""
import os
import sys

if os.name == "nt":
    os.system("")          # switches on ANSI colors in Windows consoles

ENABLED = bool(sys.stdout.isatty() or os.environ.get("FORCE_COLOR")) and not os.environ.get("NO_COLOR")
CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
         "blue": "34", "magenta": "35", "cyan": "36", "gray": "90"}
STYLES = {
    "project": ("bold", "magenta"),
    "write": ("green",), "review": ("blue",), "run": ("cyan",),
    "browser": ("magenta",), "pause": ("yellow",),
    "rest": ("bold", "yellow"), "tick": ("yellow",), "back": ("bold", "green"),
    "away": ("yellow",), "think": ("gray",), "info": ("gray",),
    "paused": ("bold", "red"), "resumed": ("bold", "green"),
    "error": ("bold", "red"), "ok": ("bold", "green"), "plain": (),
}


def paint(text, *styles):
    if not ENABLED or not styles:
        return text
    return "".join(f"\033[{CODES[s]}m" for s in styles) + text + "\033[0m"


class Console:
    """Prints colored lines, plus one 'live' line (rest countdown) that rewrites itself."""

    def __init__(self):
        self._live = False

    def _end_live(self):
        if self._live:
            print(flush=True)
            self._live = False

    def line(self, kind, text=""):
        self._end_live()
        print(paint(text, *STYLES.get(kind, ())), flush=True)

    def live(self, kind, text):
        print("\r" + paint(text, *STYLES.get(kind, ())) + ("\033[K" if ENABLED else "      "),
              end="", flush=True)
        self._live = True

    def note(self, kind, text):
        """Hook for HumanTypist and Control."""
        if kind == "rest-tick":
            self.live("tick", text)
        elif kind == "rest-start":
            self.line("rest", text)
        elif kind == "rest-end":
            self.line("back", text)
        else:
            self.line(kind, text)
