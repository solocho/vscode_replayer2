"""
The 'developer': turns recorded steps into VS Code actions, the way a person would do them.
Opens files with Ctrl+P, types them out, saves, re-reads code, runs commands in the integrated
terminal, checks the result in a browser, fixes bugs by retyping only the broken part.
"""
import json
import random
from pathlib import Path

# Stops VS Code from "helping" (auto-close brackets, auto-indent, suggestions) so typed code stays exact.
SETTINGS = {
    "editor.autoClosingBrackets": "never", "editor.autoClosingQuotes": "never",
    "editor.autoClosingOvertype": "never", "editor.autoClosingDelete": "never",
    "editor.autoSurround": "never", "editor.autoIndent": "none",
    "editor.detectIndentation": False, "editor.insertSpaces": True,
    "editor.trimAutoWhitespace": False, "editor.formatOnType": False,
    "editor.formatOnPaste": False, "editor.formatOnSave": False,
    "editor.quickSuggestions": {"other": False, "comments": False, "strings": False},
    "editor.suggestOnTriggerCharacters": False, "editor.acceptSuggestionOnEnter": "off",
    "editor.acceptSuggestionOnCommitCharacter": False, "editor.tabCompletion": "off",
    "editor.wordBasedSuggestions": "off", "editor.snippetSuggestions": "none",
    "editor.parameterHints.enabled": False, "editor.inlineSuggest.enabled": False,
    "editor.linkedEditing": False, "emmet.triggerExpansionOnTab": False,
    "files.autoSave": "off", "files.trimTrailingWhitespace": False,
    "files.insertFinalNewline": False,
}


def prepare_workspace(root: Path):
    vs = Path(root) / ".vscode"
    vs.mkdir(parents=True, exist_ok=True)
    f = vs / "settings.json"
    cur = {}
    if f.exists():
        try:
            cur = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cur = {}
    cur.update(SETTINGS)
    f.write_text(json.dumps(cur, indent=2), encoding="utf-8")


class Driver:
    def __init__(self, root, me, backend):
        self.root, self.me, self.b = Path(root), me, backend
        mac = backend.os_name == "Darwin"
        self.MOD = "command" if mac else "ctrl"
        self.SWITCH = "command" if mac else "alt"
        self.PY = "py -3.12" if backend.os_name == "Windows" else "python3"
        self.GO_END = (self.MOD, "down") if mac else ("ctrl", "end")
        self.GO_TOP = (self.MOD, "up") if mac else ("ctrl", "home")
        self.SEL_END = (self.MOD, "shift", "down") if mac else ("ctrl", "shift", "end")
        self.LINE_START = ("command", "left") if mac else ("home",)
        self.folder = ""
        self.state = {}               # full path -> text the editor should hold
        self.cur = None
        self.terminal_made = False
        self.focus = "editor"

    # ---------- helpers ----------
    def full(self, rel):
        return f"{self.folder}/{rel}" if self.folder else rel

    def settle(self, seconds):
        self.b.settle(seconds)
        self.me.advance(seconds)

    def gate(self):
        """Honour Esc-pause. After a pause, settle back in (the user may have clicked elsewhere)."""
        ctl = self.b.ctl
        while ctl.paused:
            self.b.sleep(0.05)
        if ctl.recover_needed:
            ctl.recover_needed = False
            self.recover()

    def recover(self):
        self.me.sleep(self.me.rng.uniform(1.0, 2.5))
        if self.focus == "terminal":
            self.b.hotkey(self.MOD, "shift", "p")
            self.settle(0.6)
            self.b.write("Terminal: Focus Terminal")
            self.settle(0.6)
            self.b.press("enter")
            self.settle(0.6)
        elif self.cur:
            self.open_file(self.cur)
            self.b.hotkey(*self.GO_END)          # typing always continues at the end of the file

    def emit(self, ch):
        self.gate()
        if ch == "\n":
            self.b.press("enter")
            if self.me.rng.random() < 0.06:      # people hit save now and then
                self.b.hotkey(self.MOD, "s")
        elif ch == "\t":
            self.b.press("tab")
        elif ch.isascii() and ch.isprintable():
            self.b.write(ch)
        else:
            self.b.paste(ch)

    def back(self):
        self.gate()
        self.b.press("backspace")

    def type_human(self, text):
        self.me.type_text(text, self.emit, self.back)

    # ---------- editor ----------
    def open_file(self, full):
        self.b.hotkey(self.MOD, "p")
        self.settle(0.7)
        self.b.write(full.replace("\\", "/"))
        self.settle(0.7)
        self.b.press("enter")
        self.settle(0.9)
        self.focus, self.cur = "editor", full

    def write(self, rel, text, clean=False):
        self.gate()
        text = text.replace("\r\n", "\n")
        full = self.full(rel)
        p = self.root / full
        p.parent.mkdir(parents=True, exist_ok=True)
        self.me.thinking(1, 5)
        old = None if clean else self.state.get(full)
        if clean or old is None:
            if not p.exists():
                p.write_text("", encoding="utf-8")
                self.settle(1.0)
            self.open_file(full)
            if clean:                              # resumed mid-file: start the file over
                self.b.hotkey(self.MOD, "a")
                self.b.press("backspace")
            remaining = text
        else:                                      # edit: keep the top, delete the changed tail, retype
            self.open_file(full)
            old_l, new_l = old.splitlines(True), text.splitlines(True)
            keep = 0
            while keep < min(len(old_l), len(new_l)) and old_l[keep] == new_l[keep]:
                keep += 1
            if keep < len(old_l):
                self.me.sleep(self.me.rng.uniform(1, 3))     # "this part is wrong..."
                self.gate()
                self.b.hotkey("ctrl", "g")
                self.settle(0.4)
                self.b.write(str(keep + 1))
                self.b.press("enter")
                self.settle(0.3)
                self.b.hotkey(*self.LINE_START)
                self.b.hotkey(*self.SEL_END)
                self.settle(0.4)
                self.b.press("backspace")
            else:
                self.b.hotkey(*self.GO_END)
            remaining = "".join(new_l[keep:])
        self.state[full] = text
        self.type_human(remaining)
        self.gate()
        self.b.hotkey(self.MOD, "s")
        self.settle(0.4)

    def review(self, rel):
        """Scroll back through a file and re-read it, like a person checking their work."""
        self.gate()
        full = self.full(rel)
        self.open_file(full)
        self.b.hotkey(*self.GO_TOP)
        lines = len(self.state.get(full, "").splitlines())
        for _ in range(max(1, min(8, lines // 25))):
            self.me.sleep(self.me.rng.uniform(2, 5) * self.me.energy.think_mult(self.me.t))
            self.gate()
            self.b.press("pagedown")
        self.me.sleep(self.me.rng.uniform(1, 3))
        self.gate()
        self.b.hotkey(*self.GO_END)

    # ---------- terminal ----------
    def new_terminal(self):
        self.b.hotkey("ctrl", "shift", "`")         # a NEW terminal (the first one is busy running us)
        self.settle(2.0)
        self.terminal_made = True
        self.focus = "terminal"
        if self.folder:
            self.type_human(f"cd {self.folder}")
            self.gate()
            self.b.press("enter")
            self.settle(0.8)

    def run(self, command, wait=8, new_terminal=False):
        self.gate()
        self.me.thinking(1, 4)
        if new_terminal or not self.terminal_made:
            self.new_terminal()
        elif self.focus != "terminal":
            self.b.hotkey("ctrl", "`")
            self.settle(0.8)
            self.focus = "terminal"
        self.type_human(command.replace("{PY}", self.PY))
        self.settle(0.3)
        self.gate()
        self.b.press("enter")
        self.me.wait(wait)                          # let the command run
        self.me.thinking(3, 8)                      # read the output

    # ---------- browser ----------
    def browser(self, url="", wait=6, refresh=False):
        """Open (or refresh) the running app, look around, switch back to VS Code."""
        self.gate()
        url = url.replace("{FOLDER_URI}", (self.root / self.folder).resolve().as_uri())
        url = url.replace("{WORKSPACE_URI}", self.root.resolve().as_uri())
        if refresh:
            self.b.hotkey(self.SWITCH, "tab")
            self.settle(1.2)
            self.b.hotkey(self.MOD, "r")
        else:
            self.b.open_url(url)
        self.me.wait(wait)                          # page loads, a human looks at it
        for key in self.me.rng.sample(["pagedown", "pagedown", "pageup", "home"], 3):
            self.gate()
            self.b.press(key)
            self.me.sleep(self.me.rng.uniform(1.0, 3.0))
        self.gate()
        self.b.hotkey(self.SWITCH, "tab")           # back to VS Code
        self.settle(1.2)

    # ---------- projects ----------
    def start_project(self, folder):
        self.gate()
        self.folder = folder
        (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.me.sleep(self.me.rng.uniform(30, 120))  # decide what to build next, set things up
        self.new_terminal()
        self.me.thinking(2, 6)

    def rebuild_state(self, projects, p_index, s_index):
        """After a crash: work out what the editor should already contain."""
        for i in range(p_index + 1):
            end = s_index if i == p_index else len(projects[i]["steps"])
            folder = projects[i]["folder"]
            for s in projects[i]["steps"][:end]:
                if s["type"] == "write":
                    self.state[f"{folder}/{s['path']}"] = s["content"].replace("\r\n", "\n")
        self.folder = projects[p_index]["folder"]
