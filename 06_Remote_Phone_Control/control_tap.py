#!/usr/bin/env python3
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Focus
FOCUS_TOGGLE_XY = (1848, 958)
FOCUS_X = 1805
FOCUS_Y = 432
FOCUS_PCTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]  # 0%..100%

FOCUS_TRACK_Y = None

REPEAT_SHOTS = 1

# Timing
REVEAL_PAUSE = 0.45          # wait after tapping toggle to reveal control
SETTLE_SEC = 0.50            # wait after setting a control
CAPTURE_WAIT_TIME = 6.0      # also scales the post-sweep drain wait (x30)
POST_SHOT_TAP = (1000, 510)  # set to None to disable

OUTPUT_BASE = Path.home() / "expert_raw_focus" / "captures"
PHONE_FOLDER = "/sdcard/DCIM/Expert RAW"

DRY_RUN = False  # see how it runs without touching the device

N_POSITIONS = len(FOCUS_PCTS) * REPEAT_SHOTS


def adb(*args) -> None:
    """Run an adb command, raising if it fails."""
    cmd = ["adb"] + [str(a) for a in args]
    if DRY_RUN:
        print(f"[DRY] {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)


def adb_out(*args) -> str:
    """Run an adb command and return stdout (text)."""
    cmd = ["adb"] + [str(a) for a in args]
    if DRY_RUN:
        print(f"[DRY OUT] {' '.join(cmd)}")
        return ""
    return subprocess.check_output(cmd, text=True).strip()


def tap(x, y):
    x = int(round(x)); y = int(round(y))
    adb("shell", f"input tap {x} {y}")


def shutter():
    """KEYCODE_CAMERA."""
    adb("shell", "input keyevent 27")


def ensure_device_and_open():
    adb("get-state")
    # Launch Samsung Expert RAW (adjust package if needed)
    adb("shell", "monkey -p com.samsung.android.app.galaxyraw "
                 "-c android.intent.category.LAUNCHER 1")
    time.sleep(1.0)


def latest_image_row():
    """
    Query MediaStore for newest image.
    Returns (id:int|None, name:str|None, ts:int|None).
    """
    out = adb_out(
        "shell", "content query "
                 "--uri content://media/external/images/media "
                 "--projection _id,_display_name,date_added "
                 "--sort date_added DESC --limit 1"
    )
    if not out:
        return (None, None, None)
    # Example row:
    # Row: 0 _id=12345, _display_name=IMG_20250827_..., date_added=1724766140
    m_id = re.search(r"_id=(\d+)", out)
    m_nm = re.search(r"_display_name=([^,\n]+)", out)
    m_ts = re.search(r"date_added=(\d+)", out)
    mid = int(m_id.group(1)) if m_id else None
    nm = m_nm.group(1) if m_nm else None
    ts = int(m_ts.group(1)) if m_ts else None
    return (mid, nm, ts)


def wait_for_new_image(prev_id, timeout_s=10.0, poll_s=0.25):
    """
    Poll MediaStore until a new image appears (id != prev_id) or timeout.
    Returns (ok, (id,name,ts)).
    """
    start = time.time()
    while time.time() - start < timeout_s:
        cur = latest_image_row()
        if cur[0] is not None and cur[0] != prev_id:
            return True, cur
        time.sleep(poll_s)
    return False, (None, None, None)


def exposure_timeout_s(shutter_value_s: float) -> float:
    """
    Dynamic timeout: exposure + processing buffer.
    Buffer = 1.5s + 0.2 * exposure; exposure clamped to [1/12000, 30].
    """
    exp = max(min(float(shutter_value_s), 30.0), 1.0 / 12000.0)
    buf = 1.5 + 0.2 * exp
    return exp + buf


def shoot_with_wait(current_shutter_value_s: float, label: str = ""):
    """
    Press shutter and wait for MediaStore to publish the new image.
    """
    prev_id, _prev_name, _ = latest_image_row()
    shutter()
    tmo = exposure_timeout_s(current_shutter_value_s)
    ok, cur = wait_for_new_image(prev_id, timeout_s=tmo, poll_s=0.3)
    if ok:
        print(f"   ✓ Capture saved: id={cur[0]} name={cur[1]} (≤ {tmo:.1f}s) {label}")
    else:
        print(f"   ! Timed out after {tmo:.1f}s waiting for MediaStore (continuing). {label}")
        time.sleep(0.8)


def latest_phone_files(suffixes: tuple[str, ...], count: int) -> list[str]:
    """Full phone paths of the `count` newest files in PHONE_FOLDER matching `suffixes`."""
    out = adb_out("shell", f'ls -1t "{PHONE_FOLDER}"')  # -t: newest first
    names = [
        n.strip() for n in out.splitlines()
        if n.strip().lower().endswith(suffixes)
    ]
    return [f"{PHONE_FOLDER}/{n}" for n in names[:count]]


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


@dataclass
class VControl:
    name: str
    toggle_xy: tuple[int, int]
    x: int
    y: int
    pcts: list[float]
    track_y: tuple[int, int] | None = None

    def reveal(self):
        tap(*self.toggle_xy)
        time.sleep(REVEAL_PAUSE)

    def set_value(self, value: float):
        """Tap the vertical track at the position for `value`.

        With track_y unset this degenerates to the original fixed-coordinate tap,
        which does not actually move the control.
        """
        self.reveal()
        if self.track_y is None:
            tap(self.x, self.y)
        else:
            lo, hi = self.pcts[0], self.pcts[-1]
            t = 0.0 if hi == lo else (value - lo) / (hi - lo)
            tap(self.x, lerp(self.track_y[0], self.track_y[1], t))
        time.sleep(SETTLE_SEC)


# =========================
# Main sweep logic
# =========================

def main():
    run_name = re.sub(r'[<>:"/\\|?*\s]', "_", sys.argv[1].strip()) if len(sys.argv) > 1 else ""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_folder = OUTPUT_BASE / (f"{stamp}_{run_name}" if run_name else stamp)
    output_folder.mkdir(parents=True, exist_ok=True)
    print(f"Saving to {output_folder}")

    ensure_device_and_open()

    focus = VControl("FOCUS", FOCUS_TOGGLE_XY, FOCUS_X, FOCUS_Y, FOCUS_PCTS, FOCUS_TRACK_Y)

    print(f"\nSweeping {focus.name}: {len(focus.pcts)} positions "
          f"x {REPEAT_SHOTS} shot(s) = {N_POSITIONS} captures")
    if focus.track_y is None:
        print("  ! FOCUS_TRACK_Y is not set -- every position taps the same coordinate,\n"
              "    so the focus will not actually move. Measure the slider end stops\n"
              "    and set FOCUS_TRACK_Y to get a real sweep.")

    shot_count = 0
    for i, v in enumerate(focus.pcts):
        # The slider already sits at the first position (0.0) when manual focus
        # opens, so shoot there before touching it, and only move the control
        # ahead of each later position.
        if i > 0:
            focus.set_value(v)
        for r in range(REPEAT_SHOTS):
            shot_count += 1
            print(f"  -> Shot {shot_count}/{N_POSITIONS} [FOCUS={v}] (rep {r + 1}/{REPEAT_SHOTS})")
            shoot_with_wait(1 / 125, label=f"[FOCUS={v}]")
            if POST_SHOT_TAP:
                tap(*POST_SHOT_TAP); time.sleep(0.1)

    print("\nFocus sweep completed.")


if __name__ == "__main__":
    main()