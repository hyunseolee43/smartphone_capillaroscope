#!/usr/bin/env python3
import itertools
import subprocess
import time
from dataclasses import dataclass

FOCUS_TOGGLE_XY   = (490, 107)       
FOCUS_TRACK_XY    = (445, 525)            # mid-point on the focus control
FOCUS_STEPS    = [-8, -6, -4, -2, 0, +2, +4, +6, +8] 

SHUT_TOGGLE_XY   = (1220, 995)
SHUT_TRACK_XY    = (445, 544)
SHUT_STEPS       = [-4, -2, 0, +2, +4]       # negative = slower, positive = faster (flip if needed)

ISO_TOGGLE_XY    = (1445, 995)
ISO_TRACK_XY     = (445, 544)
ISO_STEPS        = [0, +2, +4, +6, +8]       

WB_TOGGLE_XY     = (1812, 995)
WB_TRACK_XY      = (445, 544)
WB_STEPS         = [-2, 0, +2]               # negative = cooler, positive = warmer

# Shots per combo
REPEAT_SHOTS     = 1

# Sweep mode: "product" = all combinations; "single" = sweep one control at a time
SWEEP_MODE       = "single"

# ============= Motion / Timing (tune as needed) =============
DY_PER_STEP      = 20    # vertical pixels per micro-step (typ. 15–25)
SWIPE_MS         = 60    # duration (ms) of each micro-swipe
STEP_PAUSE       = 0.06  # pause between micro-swipes
REVEAL_PAUSE     = 0.25  # wait after revealing a control
SETTLE_SEC       = 0.5   # wait after finishing all moves for a control
POST_SHOT_SEC    = 0.8   # wait after shutter
POST_SHOT_TAP    = (1000, 510)  # optional (x,y) to tap after every shot; None to skip
# POST_SHOT_TAP = None
DRY_RUN          = False # True prints commands without sending to device
# ============================================================


def sh(cmd: str):
    if DRY_RUN:
        print(f"[DRY] {cmd}")
        return
    subprocess.run(cmd, shell=True, check=True)

def tap(xy):
    x, y = xy
    sh(f"adb shell input tap {x} {y}")

def swipe_v(x, y, dy, ms):
    sh(f"adb shell input swipe {x} {y} {x} {y + dy} {ms}")

def shutter():
    sh("adb shell input keyevent 27")  # 27 = camera; helps take picture

def ensure_device_and_open():
    sh("adb get-state")
    sh("adb shell monkey -p com.samsung.android.app.galaxyraw -c android.intent.category.LAUNCHER 1")
    time.sleep(1.0)

def re_show_control(control: 'VControl'):
    tap(control.toggle_xy)
    time.sleep(REVEAL_PAUSE)

@dataclass
class VControl:
    name: str
    toggle_xy: tuple[int, int]
    track_xy: tuple[int, int]
    steps: list[int]
    positive_hint: str  # doc string for your own reference

    def reveal(self):
        tap(self.toggle_xy)
        time.sleep(REVEAL_PAUSE)

    def move_relative_steps(self, n: int):
        """Move vertically by n steps using micro-swipes from track mid-point."""
        if n == 0:
            return
        self.reveal()
        x0, y0 = self.track_xy
        sign = 1 if n > 0 else -1
        for _ in range(abs(n)):
            swipe_v(x0, y0, sign * DY_PER_STEP, SWIPE_MS)
            time.sleep(STEP_PAUSE)

    def settle(self):
        time.sleep(SETTLE_SEC)


def main():
    ensure_device_and_open()

    focus = VControl("FOCUS",  FOCUS_TOGGLE_XY, FOCUS_TRACK_XY, FOCUS_STEPS, "positive=toward infinity (flip if opposite)")
    shut  = VControl("SHUTTER", SHUT_TOGGLE_XY, SHUT_TRACK_XY, SHUT_STEPS,  "positive=faster/shorter (flip if opposite)")
    iso   = VControl("ISO",     ISO_TOGGLE_XY,  ISO_TRACK_XY,  ISO_STEPS,   "positive=higher ISO (flip if opposite)")
    wb    = VControl("WB",      WB_TOGGLE_XY,   WB_TRACK_XY,   WB_STEPS,    "positive=warmer (flip if opposite)")

    # controls = [focus, shut, iso, wb]
    controls = [focus]

    print("Sweep mode:", SWEEP_MODE)
    for c in controls:
        print(f" - {c.name}: steps={c.steps} ({c.positive_hint})")

    shot_count = 0

    if SWEEP_MODE == "product":
        combos = list(itertools.product(focus.steps, shut.steps, iso.steps, wb.steps))
        total  = len(combos) * REPEAT_SHOTS

        for (fs, ss, is_, wbs) in combos:
            label = f"[F{fs:+d} S{ss:+d} I{is_:+d} W{wbs:+d}]"
            print(f"\nSetting combo {label}")

            focus.move_relative_steps(fs); focus.settle()
            shut.move_relative_steps(ss);  shut.settle()
            iso.move_relative_steps(is_);  iso.settle()
            wb.move_relative_steps(wbs);   wb.settle()

            for r in range(REPEAT_SHOTS):
                shot_count += 1
                print(f"  -> Shot {shot_count}/{total} {label} (rep {r+1}/{REPEAT_SHOTS})")
                shutter(); time.sleep(POST_SHOT_SEC)
                if POST_SHOT_TAP:
                    tap(POST_SHOT_TAP); time.sleep(0.1)
                re_show_control(wb)

            # Undo to baseline for reproducibility
            wb.move_relative_steps(-wbs)
            iso.move_relative_steps(-is_)
            shut.move_relative_steps(-ss)
            focus.move_relative_steps(-fs)
            time.sleep(0.15)

    elif SWEEP_MODE == "single":
        for c in controls:
            print(f"\n--- Sweeping {c.name} only ---")
            for s in c.steps:
                c.move_relative_steps(-s); time.sleep(0.15)
                c.move_relative_steps(s); c.settle()
                for r in range(REPEAT_SHOTS):
                    shot_count += 1
                    print(f"  -> Shot {shot_count} [{c.name}{s:+d}] (rep {r+1}/{REPEAT_SHOTS})")
                    shutter(); time.sleep(POST_SHOT_SEC)
                    if POST_SHOT_TAP:
                        tap(POST_SHOT_TAP); time.sleep(0.1)
                    re_show_control(c)
    else:
        raise ValueError("SWEEP_MODE must be 'product' or 'single'")

    print(f"\nDone. Total shots: {shot_count}")

if __name__ == "__main__":
    main()
