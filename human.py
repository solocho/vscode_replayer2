"""
Human behaviour model: uneven typing rhythm, believable typos, fatigue, distractions, a day schedule.

Nothing here is constant. Speed drifts in bursts and slumps, mistakes become more common when
tired, thinking gets slower, and rests are scheduled at irregular intervals (coffee, lunch, ...).
"""
import math
import random

ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]

LABELS = {
    "coffee": "coffee break", "lunch": "lunch break", "bathroom": "bathroom break",
    "phone": "checking phone", "stretch": "stretching", "water": "getting water", "walk": "going for a walk",
}


def _hms(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def neighbors(ch):
    low = ch.lower()
    for r, row in enumerate(ROWS):
        i = row.find(low)
        if i == -1:
            continue
        out = []
        for dr in (-1, 0, 1):
            rr = r + dr
            if 0 <= rr < len(ROWS):
                for di in (-1, 0, 1):
                    j = i + di
                    if (dr, di) != (0, 0) and 0 <= j < len(ROWS[rr]):
                        out.append(ROWS[rr][j])
        return out
    return []


class Energy:
    """Stamina from 0 to 1. Drains while working, recovers while resting, dips after lunch."""

    def __init__(self, level=0.95):
        self.level = level

    def dip(self, t):
        hours = t / 3600
        return 0.10 * math.exp(-((hours - 5.5) ** 2) / (2 * 0.7 ** 2))

    def eff(self, t):
        return max(0.15, self.level - self.dip(t))

    def work(self, seconds):
        self.level = max(0.2, self.level - seconds / 3600 * 0.11)

    def rest(self, seconds):
        self.level = min(1.0, self.level + seconds / 60 * 0.009)

    def speed_mult(self, t):
        return 0.62 + 0.38 * self.eff(t)

    def typo_mult(self, t):
        return 1 + 2.0 * (1 - self.eff(t))

    def think_mult(self, t):
        return 1 + 1.5 * (1 - self.eff(t))


class Rhythm:
    """Slowly drifting speed: flow bursts, hesitant patches, ordinary stretches."""

    def __init__(self, rng):
        self.rng = rng
        self.current = self.target = 1.0
        self.until = 0.0

    def next(self, t):
        if t >= self.until:
            roll = self.rng.random()
            if roll < 0.22:
                self.target, span = self.rng.uniform(1.15, 1.4), self.rng.uniform(10, 50)
            elif roll < 0.42:
                self.target, span = self.rng.uniform(0.55, 0.85), self.rng.uniform(15, 70)
            else:
                self.target, span = self.rng.uniform(0.9, 1.1), self.rng.uniform(20, 120)
            self.until = t + span
        self.current += (self.target - self.current) * 0.04
        return self.current

    def slow_start(self):
        self.current = 0.7


class DaySchedule:
    """Irregular rests across the day: (start_second, kind, minutes). Lunch near the 40% mark."""

    KINDS = ["stretch", "coffee", "phone", "bathroom", "water", "walk"]

    def __init__(self, rng, hours):
        self.events = []
        total = hours * 3600
        t, lunch_done = 0.0, False
        while True:
            t += rng.uniform(42, 88) * 60
            if t >= total - 20 * 60:
                break
            if not lunch_done and hours >= 4 and t >= total * 0.40:
                minutes, kind, lunch_done = rng.uniform(32, 55), "lunch", True
            else:
                minutes, kind = rng.uniform(4, 14), rng.choice(self.KINDS)
            self.events.append((t, kind, minutes))
            t += minutes * 60

    def first_after(self, t):
        for i, (when, _, _) in enumerate(self.events):
            if when > t:
                return i
        return len(self.events)


class HumanTypist:
    def __init__(self, backend, wpm=80, typo_rate=0.03, speed=1.0, hours=10, seed=None, note=None, log=None):
        self.rng = random.Random(seed)
        self.backend = backend
        self.base = 60 / (wpm * 5)
        self.typo_rate = typo_rate
        self.speed = speed
        self.note = note or (lambda kind, msg: None)
        self.energy = Energy(self.rng.uniform(0.86, 1.0))
        self.rhythm = Rhythm(self.rng)
        self.schedule = DaySchedule(random.Random(f"{seed}-day"), hours)
        self.t = 0.0                 # session seconds in human time (unscaled)
        self._next = 0

    # ---------- time ----------
    def advance(self, seconds):
        self.t += seconds
        self.energy.work(seconds)

    def wait(self, seconds):
        """Fixed waits (a command running). Real time, never sped up."""
        self.backend.sleep(seconds)
        self.advance(seconds)

    def sleep(self, seconds):
        """Human pauses (thinking, reading). Sped up by --speed for quick tests."""
        self.backend.sleep(seconds / self.speed)
        self.advance(seconds)

    def thinking(self, lo=2, hi=8):
        seconds = self.rng.uniform(lo, hi) * self.energy.think_mult(self.t)
        if seconds >= 6:
            self.note("think", f"  ... thinking ({seconds:.0f}s)")
        self.sleep(seconds)

    def resume_at(self, t, level):
        self.t = t
        self.energy.level = level
        self._next = self.schedule.first_after(t)

    # ---------- rests ----------
    def maybe_break(self):
        events = self.schedule.events
        if self._next < len(events) and self.t >= events[self._next][0]:
            _, kind, minutes = events[self._next]
            self._next += 1
            self.take_break(kind, minutes)

    def take_break(self, kind, minutes):
        label = LABELS.get(kind, kind)
        total = minutes * 60
        self.note("rest-start", f"[{_hms(self.t)}] RESTING - {label} ({minutes:.0f} min)")
        left = total
        while left > 0:
            chunk = min(5.0, left)
            self.backend.sleep(chunk / self.speed)
            left -= chunk
            self.note("rest-tick", f"      {label}: {_hms(left)[2:]} left")
        self.t += total
        self.energy.rest(total)
        self.rhythm.slow_start()
        self.note("rest-end", f"[{_hms(self.t)}] back to work")

    def micro_pause(self):
        tired = 1 + 2.5 * (1 - self.energy.eff(self.t))
        roll = self.rng.random()
        if roll < 0.004 * tired:                       # looked away / checked the phone
            seconds = self.rng.uniform(20, 90)
            self.note("away", f"  ... looked away from the screen ({seconds:.0f}s)")
            self.sleep(seconds)
        elif roll < 0.024 * tired:                     # stared at the screen
            seconds = self.rng.uniform(5, 18)
            self.note("think", f"  ... staring at the screen ({seconds:.0f}s)")
            self.sleep(seconds)
        elif roll < 0.10:                              # worked out the next line
            self.sleep(self.rng.uniform(1.2, 5) * self.energy.think_mult(self.t))

    # ---------- typing ----------
    def _delay(self, ch, prev, indenting):
        mult = self.energy.speed_mult(self.t) * self.rhythm.next(self.t)
        d = self.base / mult
        d = max(0.015, self.rng.gauss(d, d * 0.38))
        if ch == " ":
            d *= 1.25
        elif ch in ".,;:)}]":
            d *= 1.7
        elif ch == "\n":
            d *= 2.4
        elif ch.isupper() or ch in "({[<>_\"'!@#$%^&*|~?+=":
            d *= 1.3
        elif ch.isdigit():
            d *= 1.2
        if ch == prev:
            d *= 0.8
        if indenting and ch in " \t":
            d *= 0.35
        return d

    def _typo(self, text, i):
        """Return (wrong keystrokes, how many intended chars they stand in for)."""
        ch = text[i]
        roll = self.rng.random()
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if roll < 0.15 and nxt.isalpha() and nxt != ch and ch.isalpha():
            return nxt + ch, 2                        # swapped letters
        if roll < 0.27:
            return ch + ch, 1                         # key pressed twice
        near = neighbors(ch) if ch.isalpha() else []
        if near:
            wrong = self.rng.choice(near)
            return (wrong.upper() if ch.isupper() else wrong), 1
        return ch + ch, 1

    def type_text(self, text, emit, backspace):
        i, prev, indenting = 0, "", True
        while i < len(text):
            ch = text[i]
            self.maybe_break()
            chance = self.typo_rate * self.energy.typo_mult(self.t)
            if ch.isalnum() and not indenting and self.rng.random() < chance:
                wrong, used = self._typo(text, i)
                for w in wrong:
                    emit(w)
                    self.sleep(self._delay(w, prev, False))
                    prev = w
                extras = text[i + used:i + used + self.rng.choice([0, 0, 1, 1, 2, 3, 4])]
                for e in extras:                       # kept typing before noticing
                    emit(e)
                    self.sleep(self._delay(e, prev, False))
                    prev = e
                self.sleep(self.rng.uniform(0.3, 1.3))   # "wait, that's wrong..."
                for _ in range(len(wrong) + len(extras)):
                    backspace()
                    self.sleep(self.rng.uniform(0.06, 0.16))
                continue                               # retype it properly
            emit(ch)
            self.sleep(self._delay(ch, prev, indenting))
            if ch == "\n":
                indenting = True
                self.micro_pause()
            elif ch not in " \t":
                indenting = False
            prev = ch
            i += 1
