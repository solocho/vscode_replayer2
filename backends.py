"""
Backends: what actually presses keys and tells time.

RealBackend   - drives your real keyboard through pyautogui (pausable with Esc).
SimBackend    - virtual clock plus a tiny fake VS Code. Used to plan the day (how long will it take?)
                and by selftest.py to prove the typed files come out exactly right.
"""
import platform
import time
import webbrowser


class Control:
    """Esc toggles pause / resume. Gives loud, colored feedback (and optional beeps)."""

    def __init__(self, quiet=False, say=None, beep=False):
        self.paused = False
        self.recover_needed = False
        self.quiet = quiet
        self.say = say
        self.beep = beep
        self._down = False

    def _beep(self, pattern):
        try:
            if platform.system() == "Windows":
                import winsound
                for freq, ms in pattern:
                    winsound.Beep(freq, ms)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass

    def toggle(self):
        self.paused = not self.paused
        if self.paused:
            self.recover_needed = True
        if not self.quiet:
            msg = ("|| PAUSED - press Esc again to continue" if self.paused
                   else ">> RESUMING - settling back in...")
            if self.say:
                self.say("paused" if self.paused else "resumed", msg)
            else:
                print("\n" + msg)
            if self.beep:
                self._beep([(700, 180)] if self.paused else [(900, 120), (1200, 120)])

    def listen(self):
        try:
            from pynput import keyboard
        except Exception as exc:
            if self.say:
                self.say("error", f"Esc pause/resume is NOT available (pynput problem: {exc})")
            return False

        def on_press(key):
            try:
                if key == keyboard.Key.esc and not self._down:      # one toggle per physical press
                    self._down = True
                    self.toggle()
            except Exception as exc:
                if self.say:
                    self.say("error", f"Esc handler error: {exc}")

        def on_release(key):
            if key == keyboard.Key.esc:
                self._down = False

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        if self.say:
            self.say("ok", "Esc key listener is active (Esc = pause / resume)")
        return True


class RealBackend:
    def __init__(self, say=None, beep=True):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        self.pg = pyautogui
        self.os_name = platform.system()
        self.ctl = Control(say=say, beep=beep)
        self.stop_errors = (pyautogui.FailSafeException, KeyboardInterrupt)
        try:
            import pyperclip
        except ImportError:
            pyperclip = None
        self.pyperclip = pyperclip

    def sleep(self, seconds):
        """Human-time sleep: freezes while paused."""
        left = seconds
        while left > 0:
            while self.ctl.paused:
                time.sleep(0.05)
            step = min(0.25, left)
            time.sleep(step)
            left -= step

    def settle(self, seconds):
        """Short UI wait between keystrokes. Never interrupted by pause, so key sequences stay whole."""
        time.sleep(seconds)

    def press(self, key):
        self.pg.press(key)

    def hotkey(self, *keys):
        self.pg.hotkey(*keys)

    def write(self, text):
        self.pg.write(text)

    def paste(self, text):
        if self.pyperclip:
            self.pyperclip.copy(text)
            self.pg.hotkey("command" if self.os_name == "Darwin" else "ctrl", "v")

    def open_url(self, url):
        webbrowser.open(url)


# ------------------------------------------------------------------ simulation
class SimInterrupt(Exception):
    pass


class SimEditor:
    """Just enough VS Code to check the typing logic: files, cursor, selection, quick-open, goto-line."""

    def __init__(self):
        self.files, self.cur, self.mode = {}, None, "editor"
        self.buf, self.cursor, self.sel = "", 0, None
        self.commands, self.terminals = [], 0
        self.term = ""

    def char(self, ch):
        if self.mode in ("quick", "goto", "palette"):
            self.buf += ch
        elif self.mode == "terminal":
            self.term += ch
        else:
            self._del_sel()
            d = self.files[self.cur]
            self.files[self.cur] = d[:self.cursor] + ch + d[self.cursor:]
            self.cursor += 1

    def _del_sel(self):
        if self.sel is not None:
            d = self.files[self.cur]
            a, b = sorted((self.sel, self.cursor))
            self.files[self.cur] = d[:a] + d[b:]
            self.cursor, self.sel = a, None

    def press(self, key):
        if key == "enter":
            if self.mode == "quick":
                self.cur = self.buf
                self.files.setdefault(self.cur, "")
                self.cursor, self.sel, self.mode = 0, None, "editor"
            elif self.mode == "goto":
                line = int(self.buf) - 1
                d = self.files[self.cur]
                self.cursor = sum(len(x) for x in d.splitlines(True)[:line])
                self.sel, self.mode = None, "editor"
            elif self.mode == "palette":
                self.mode = "terminal" if "Focus Terminal" in self.buf else "editor"
            elif self.mode == "terminal":
                self.commands.append(self.term)
                self.term = ""
            else:
                self.char("\n")
        elif key == "backspace":
            if self.mode == "terminal":
                self.term = self.term[:-1]
            elif self.sel is not None:
                self._del_sel()
            else:
                d = self.files[self.cur]
                self.files[self.cur] = d[:self.cursor - 1] + d[self.cursor:]
                self.cursor -= 1
        elif key == "tab":
            self.char("    ")

    def hotkey(self, *k):
        k = tuple(x for x in k)
        if k[1:] == ("p",) and len(k) == 2:
            self.mode, self.buf = "quick", ""
        elif k == ("ctrl", "g"):
            self.mode, self.buf = "goto", ""
        elif k == ("ctrl", "shift", "`"):
            self.mode, self.terminals = "terminal", self.terminals + 1
        elif k == ("ctrl", "`"):
            self.mode = "terminal"
        elif len(k) == 3 and k[1:] == ("shift", "p"):
            self.mode, self.buf = "palette", ""
        elif k[1:] == ("a",) and self.mode == "editor":
            self.sel, self.cursor = 0, len(self.files[self.cur])
        elif k in (("home",), ("command", "left")):
            self.sel = None
        elif k in (("ctrl", "home"), ("command", "up")):
            self.cursor, self.sel = 0, None
        elif k in (("ctrl", "end"), ("command", "down")):
            self.cursor, self.sel = len(self.files[self.cur]), None
        elif k in (("ctrl", "shift", "end"), ("command", "shift", "down")):
            self.sel, self.cursor = self.cursor, len(self.files[self.cur])


class SimBackend:
    def __init__(self, track=True, os_name="Linux"):
        self.os_name = os_name
        self.clock = 0.0
        self.ctl = Control(quiet=True)
        self.editor = SimEditor() if track else None
        self.keys = 0
        self.urls = []
        self.pause_plan = []          # [(virtual_time, pause_length)]
        self._resume_at = None
        self.stop_after_keys = None   # raise SimInterrupt after this many keys (crash test)
        self.stop_errors = (SimInterrupt,)

    def _logic(self):
        if self.pause_plan and not self.ctl.paused and self.clock >= self.pause_plan[0][0]:
            self._resume_at = self.clock + self.pause_plan.pop(0)[1]
            self.ctl.toggle()
        elif self.ctl.paused and self._resume_at is not None and self.clock >= self._resume_at:
            self._resume_at = None
            self.ctl.toggle()

    def sleep(self, seconds):
        self.clock += seconds
        self._logic()

    def settle(self, seconds):
        self.clock += seconds

    def _key(self):
        self.keys += 1
        if self.stop_after_keys is not None and self.keys >= self.stop_after_keys:
            self.stop_after_keys = None
            raise SimInterrupt("simulated crash")

    def press(self, key):
        self._key()
        if self.editor:
            self.editor.press(key)

    def hotkey(self, *keys):
        self._key()
        if self.editor:
            self.editor.hotkey(*keys)

    def write(self, text):
        self._key()
        if self.editor:
            for ch in text:
                self.editor.char(ch)

    def paste(self, text):
        self.write(text)

    def open_url(self, url):
        self.urls.append(url)
