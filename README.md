# Human-style developer session for VS Code

Builds five projects inside the real VS Code editor with real keystrokes, behaving like a person
over a long day. Intended use: recording study material you can watch later, offline.

| # | Project | What you learn |
|---|---------|----------------|
| 1 | LogLens - web log analyzer (CLI) | regex, dataclasses, argparse, statistics, unittest |
| 2 | MarkdownLite - Markdown to HTML | parsing, escaping, recursion, HTML output |
| 3 | Snake - tkinter game | game logic vs UI, state, a simple AI, JSON high scores |
| 4 | ChatRoom - TCP chat | sockets, threads, locks, a line protocol |
| 5 | InvoiceDesk - Flask + SQLite | web routes, templates, SQL, REST endpoint |

Each project is typed with a deliberate bug that its tests (or its output, or the browser) reveal,
and then fixed, so you watch real debugging. Finished source code is in `finished_projects/`.

## Seeing what it is doing (recommended way to run)
Start it from a SEPARATE PowerShell window (Start menu > PowerShell), not from VS Code's terminal,
and point it at your workspace folder:

    py -3.12 C:\...\vscode_replayer\main.py --hours 10 --workspace C:\...\coding-day

Put that window beside VS Code (or on a second monitor) and record only the VS Code window.
It prints colored status: green = typing, cyan = running commands, blue = reading code,
magenta = browser, yellow = resting (with a countdown: "RESTING - coffee break ... 07:12 left"),
red = paused or error. Esc beeps (low beep = paused, two high beeps = resumed); add `--silent` to turn
the beeps off. On start it prints "Esc key listener is active" - if you do not see that line, Esc will not work.

## Run
1. `pip install -r requirements.txt`
2. In VS Code: File > Open Folder > choose an EMPTY folder.
3. In VS Code's terminal: `python /path/to/vscode_replayer/main.py --hours 10`
   (it spends ~30 s planning, then a 10 s countdown: click into the editor, hands off.)
4. Esc = pause / resume. Mouse into a screen corner = emergency stop.
5. Crash or stop? Run the same command with `--resume`; it continues at the interrupted step.

Check everything offline first: `python selftest.py` (no keyboard or VS Code needed).

## The human model
- Typing speed drifts in bursts and slumps; indentation is typed fast, symbols slower.
- Mistakes: neighbouring key, swapped letters, doubled key. It keeps typing a few characters, notices,
  backspaces and retypes. Mistakes become more common and thinking slower as energy drops.
- Energy drains while working, recovers on rests, with a post-lunch dip.
- Irregular rests (coffee, bathroom, phone, stretch, walk, lunch of 30-55 min), plus short stares,
  glances away and "thinking" pauses. A different day every run (`--seed N` repeats one).
- Re-reads files by scrolling, runs code in new terminals, checks the browser, edits files by
  retyping only the part that changed.
- `--hours H` calibrates the base typing speed so the whole day lasts about H hours (+/- 30 min).

## Before a 10 hour run
- Stop the computer sleeping or locking; plug in power; close chat apps and turn off notifications.
- US keyboard layout. Windows, macOS, Linux X11 work (not Wayland). macOS: allow Accessibility and
  Input Monitoring for your terminal/VS Code.
- Close the Snake window if it ever grabs focus: press Esc (pause), click back into VS Code, Esc again.
- First time: try one project quickly, e.g. `python main.py --only 2 --hours 1.5 --speed 20`
  (`--speed` shortens only thinking and rests, never the real key presses).
- Edit `plan.json` to reorder or drop projects. New recordings are plain JSON (see recordings/).
- `pip install` on newer Linux may need a virtualenv; the first command in project 5 does it.
