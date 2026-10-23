"""
Human-style developer session for VS Code.

Builds the projects in plan.json inside the REAL VS Code editor with real keystrokes, behaving like a
person over a long working day: uneven typing, typos fixed with backspace, getting tired, distractions,
coffee and lunch breaks, re-reading code, running it, checking the browser, fixing bugs.

QUICK START
  1. pip install -r requirements.txt
  2. VS Code: File > Open Folder... > an EMPTY folder (every project is built in a sub-folder).
  3. In VS Code's integrated terminal:
         python /path/to/vscode_replayer/main.py --hours 10
  4. During the countdown click inside the VS Code editor, then hands off keyboard and mouse.

CONTROLS
  Esc                      pause; press Esc again to resume exactly where it stopped
  mouse into a screen corner   emergency stop (progress is saved; continue later with --resume)

USEFUL OPTIONS
  --hours 10     total length of the day (typing speed is calibrated so the day lasts about this long)
  --wpm 70       skip calibration and use this base typing speed
  --only 1,3     run only some projects (numbers from plan.json)
  --resume       continue after a crash / emergency stop
  --dry-run      just print the plan and the estimated length
  --speed 20     TEST ONLY: sped-up thinking and rests (typing keystrokes still real)
"""
import argparse
import json
import random
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

from backends import RealBackend, SimBackend
from driver import Driver, prepare_workspace
from human import HumanTypist
from ui import Console, paint

HERE = Path(__file__).resolve().parent
STATE_FILE = ".replayer_state.json"


def hms(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def load_projects(plan_path, only=None):
    plan_path = Path(plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    projects = []
    for n, rel in enumerate(plan["projects"], 1):
        if only and n not in only:
            continue
        rec = json.loads((plan_path.parent / rel).read_text(encoding="utf-8"))
        rec["number"] = n
        projects.append(rec)
    return projects


class Checkpoint:
    """Written before and after every step, so a crash never costs more than one step."""

    def __init__(self, path, meta):
        self.path, self.meta = Path(path), meta

    def save(self, p, s, busy, me):
        data = dict(self.meta, project=p, step=s, busy=busy, elapsed=me.t, energy=me.energy.level)
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))


def execute(d, step, clean=False):
    kind = step["type"]
    if kind == "write":
        d.write(step["path"], step["content"], clean)
    elif kind == "review":
        d.review(step["path"])
    elif kind == "run":
        d.run(step["command"], step.get("wait", 8), step.get("new_terminal", False))
    elif kind == "browser":
        d.browser(step.get("url", ""), step.get("wait", 6), step.get("refresh", False))
    elif kind == "pause":
        d.me.sleep(step.get("seconds", 3))


def run_session(d, projects, ckpt=None, resume=None, log=lambda *a: None):
    """Run all projects. resume = (project_index, step_index, busy) to continue after a crash.
    log(kind, text) receives colored status lines."""
    me = d.me
    p0, s0, busy0 = resume or (0, 0, False)
    for pi in range(p0, len(projects)):
        proj = projects[pi]
        first = s0 if pi == p0 else 0
        if first == 0:
            if ckpt:
                ckpt.save(pi, 0, False, me)
            log("plain", "")
            log("project", f"=== Project {pi + 1}/{len(projects)}: {proj['name']}   "
                           f"(session {hms(me.t)}, energy {me.energy.eff(me.t):.0%})")
            d.start_project(proj["folder"])
        else:
            d.folder = proj["folder"]
        steps = proj["steps"]
        for si in range(first, len(steps)):
            step = steps[si]
            clean = busy0 and pi == p0 and si == s0
            if ckpt:
                ckpt.save(pi, si, True, me)
            what = step.get("path") or step.get("command") or step.get("url") or ""
            what = what.replace("{PY}", d.PY)
            verb = {"write": "TYPING", "review": "READING", "run": "RUNNING",
                    "browser": "BROWSER", "pause": "THINKING"}.get(step["type"], step["type"])
            log(step["type"], f"[{hms(me.t)}] {verb:<8} {what[:52]:<52} "
                              f"step {si + 1}/{len(steps)} | energy {me.energy.eff(me.t):.0%}")
            began = me.t
            execute(d, step, clean)
            if step["type"] == "write":
                log("info", f"           typed {len(step['content']):,} characters in {hms(me.t - began)[2:]}")
            if ckpt:
                ckpt.save(pi, si + 1, False, me)
        if pi < len(projects) - 1:
            log("pause", f"[{hms(me.t)}] finishing up, getting ready for the next project...")
            me.sleep(me.rng.uniform(60, 240))
    return me.t


def estimate(projects, hours, wpm, typo, seed):
    tmp = tempfile.mkdtemp()
    try:
        backend = SimBackend(track=False)
        me = HumanTypist(backend, wpm=wpm, typo_rate=typo, hours=hours, seed=seed)
        run_session(Driver(tmp, me, backend), projects, log=lambda *a: None)
        return me.t
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def calibrate(projects, hours, typo):
    """Find the base typing speed that makes the whole day last about `hours` hours."""
    target = hours * 3600

    def avg(w):
        return sum(estimate(projects, hours, w, typo, s) for s in (101, 102)) / 2

    lo, hi = 25.0, 140.0
    if avg(hi) > target:
        return hi, avg(hi), "recordings are LONGER than the requested day even at a fast typing speed"
    if avg(lo) < target:
        return lo, avg(lo), "recordings are SHORTER than the requested day; add projects or lower --hours"
    for _ in range(9):
        mid = (lo + hi) / 2
        if avg(mid) > target:
            lo = mid
        else:
            hi = mid
    wpm = round((lo + hi) / 2, 1)
    return wpm, avg(wpm), ""


def main():
    ap = argparse.ArgumentParser(description="Human-style developer session for VS Code")
    ap.add_argument("--plan", default=str(HERE / "plan.json"))
    ap.add_argument("--workspace", default=".", help="the folder open in VS Code (default: current)")
    ap.add_argument("--hours", type=float, default=10.0)
    ap.add_argument("--wpm", type=float, default=None, help="skip calibration, use this typing speed")
    ap.add_argument("--typos", type=float, default=0.03)
    ap.add_argument("--only", default="", help="comma separated project numbers, e.g. 1,3")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--countdown", type=int, default=10)
    ap.add_argument("--silent", action="store_true", help="no beeps when you press Esc")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    only = {int(x) for x in a.only.split(",") if x.strip()}
    projects = load_projects(a.plan, only or None)
    root = Path(a.workspace).resolve()
    state_path = root / STATE_FILE
    resume = None

    if a.resume:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        wpm, seed, hours = saved["wpm"], saved["seed"], saved["hours"]
        resume = (saved["project"], saved["step"], saved["busy"])
        print(f"Resuming at project {resume[0] + 1}, step {resume[1] + 1} "
              f"(session {hms(saved['elapsed'])} in).")
    else:
        hours = a.hours
        seed = a.seed if a.seed is not None else random.randrange(10 ** 9)
        typed = sum(len(s.get("content", "")) for p in projects for s in p["steps"])
        print(f"{len(projects)} project(s), about {typed:,} characters to type.")
        if a.wpm:
            wpm = a.wpm
        else:
            print(f"Planning a {hours:g}-hour day (calibrating typing speed, ~30 s)...")
            wpm, est, warn = calibrate(projects, hours, a.typos)
            print(f"Base typing speed {wpm:g} wpm -> estimated day length {hms(est)}")
            if warn:
                print("NOTE:", warn)
    if a.dry_run:
        me = HumanTypist(SimBackend(track=False), wpm=wpm, hours=hours, seed=seed)
        print("\nBreak schedule for this seed:")
        for t, kind, minutes in me.schedule.events:
            print(f"  at {hms(t)}  {kind:<9} {minutes:4.0f} min")
        return

    console = Console()
    backend = RealBackend(say=console.note, beep=not a.silent)
    backend.ctl.listen()
    me = HumanTypist(backend, wpm=wpm, typo_rate=a.typos, speed=a.speed, hours=hours, seed=seed,
                     note=console.note)
    d = Driver(root, me, backend)
    meta = {"wpm": wpm, "seed": seed, "hours": hours, "projects": [p["name"] for p in projects]}
    ckpt = Checkpoint(state_path, meta)
    if resume:
        me.resume_at(saved["elapsed"], saved["energy"])
        d.rebuild_state(projects, resume[0], resume[1])
        if saved["project"] >= len(projects):
            console.line("ok", "Nothing left to do.")
            return
    prepare_workspace(root)

    console.line("plain", f"\nBuilding in {root}")
    console.line("ok", "Click inside the VS Code EDITOR now, then hands off.")
    console.line("info", "Esc = pause/resume (you will hear a beep).  Mouse into a screen corner = emergency stop.")
    for i in range(a.countdown, 0, -1):
        print(paint(f"  starting in {i}...  ", "yellow"), end="\r", flush=True)
        time.sleep(1)
    print()
    time.sleep(2)                                    # let VS Code load the workspace settings

    try:
        total = run_session(d, projects, ckpt, resume, log=console.note)
    except backend.stop_errors:
        console.line("error", "\nSTOPPED. Progress is saved. To continue later run the same command with --resume")
        return
    except Exception:
        console.line("error", "\nCRASHED - details below. Progress is saved; run the same command with --resume")
        traceback.print_exc()
        return
    console.line("ok", f"\nAll projects finished. Session length {hms(total)}.")
    state_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
