"""
Offline self-test (no keyboard, no VS Code, no network needed).

Plays the whole day against a fake editor and checks that:
  1. every typed file ends up byte-for-byte identical to the recording,
  2. Esc pauses in the middle of typing / edits / terminal commands do no damage,
  3. a crash in the middle of the day can be resumed with exactly the same result,
  4. the planner lands near the requested day length.

    python selftest.py
"""
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

import main
from backends import SimBackend, SimInterrupt
from driver import Driver
from human import HumanTypist

HERE = Path(__file__).resolve().parent


def expected_files(projects):
    want = {}
    for p in projects:
        for s in p["steps"]:
            if s["type"] == "write":
                want[f"{p['folder']}/{s['path']}"] = s["content"].replace("\r\n", "\n")
    return want


def check(editor, want, label):
    bad = [k for k, v in want.items() if editor.files.get(k) != v]
    print(f"  {label}: {len(want) - len(bad)}/{len(want)} files identical", "OK" if not bad else f"MISMATCH {bad}")
    return not bad


def session(projects, backend, wpm, hours, seed, tmp, ckpt=None, resume=None, me_state=None):
    me = HumanTypist(backend, wpm=wpm, hours=hours, seed=seed, log=lambda *a: None)
    d = Driver(tmp, me, backend)
    if resume:
        me.resume_at(me_state["elapsed"], me_state["energy"])
        d.rebuild_state(projects, resume[0], resume[1])
    total = main.run_session(d, projects, ckpt, resume, log=lambda *a: None)
    return me, d, total


def run():
    projects = main.load_projects(HERE / "plan.json")
    want = expected_files(projects)
    ok = True
    wpm, hours = 43, 10

    print("1) full day with Esc pauses injected at awkward moments")
    tmp = tempfile.mkdtemp()
    b = SimBackend(track=True)
    b.pause_plan = [(1500, 40), (4100, 75), (9000, 30), (15500, 120), (22000, 45), (30000, 20)]
    me, d, total = session(projects, b, wpm, hours, 7, tmp)
    ok &= check(b.editor, want, "typed files")
    print(f"  session length {main.hms(total)}  | keystrokes {b.keys:,} | terminals opened {b.editor.terminals}")
    print(f"  breaks taken: {me._next} | pauses survived: {6 - len(b.pause_plan)}")
    shutil.rmtree(tmp, ignore_errors=True)

    print("2) crash in the middle of the day, then resume")
    for crash_at in (4000, 21000, 38000, 55000, 73000):
        tmp = tempfile.mkdtemp()
        state = Path(tmp) / main.STATE_FILE
        meta = {"wpm": wpm, "seed": 11, "hours": hours, "projects": [p["name"] for p in projects]}
        b = SimBackend(track=True)
        b.stop_after_keys = crash_at
        ckpt = main.Checkpoint(state, meta)
        try:
            session(projects, b, wpm, hours, 11, tmp, ckpt)
            print(f"  (crash point {crash_at} was beyond the end of the day)")
        except SimInterrupt:
            pass
        saved = json.loads(state.read_text())
        b.keys, b.ctl.paused = 0, False           # VS Code is still open with its (possibly half-typed) buffers
        resume = (saved["project"], saved["step"], saved["busy"])
        session(projects, b, wpm, hours, 11, tmp, ckpt, resume, saved)
        ok &= check(b.editor, want, f"crash at key {crash_at:>7,} (project {saved['project'] + 1}, step {saved['step'] + 1}) -> resumed")
        shutil.rmtree(tmp, ignore_errors=True)

    print("3) planner accuracy")
    for target in (6, 10):
        w, est, warn = main.calibrate(projects, target, 0.03)
        real = [main.estimate(projects, target, w, 0.03, s) for s in (1, 2, 3, 4)]
        print(f"  --hours {target}: {w:g} wpm; planned {main.hms(est)}; four random days: "
              + ", ".join(main.hms(r) for r in real) + (f"  ({warn})" if warn else ""))

    print("\nALL CHECKS PASSED" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
