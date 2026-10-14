#!/usr/bin/env python3
"""Expert RAW manual-focus sweep, driven over adb from macOS.

Taps through N manual-focus positions in Samsung's Expert RAW app, captures at
each, then pulls the new DNG/JPG pairs off the phone.

The phone must already be unlocked, awake, and sitting on the Expert RAW photo
screen with manual focus available. This script does not launch the app -- it
only drives taps, so anything covering the camera UI (notification shade, a
permission dialog) silently eats them.

Usage:
    python3 tools/focus_sweep.py --name sample_01
    python3 tools/focus_sweep.py --name sample_01 --dry-run   # move focus, no captures

Stdlib only; no dependency on the capillary_od package.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# --- Screen geometry -------------------------------------------------------
#
# Every coordinate below was read off ONE phone at ONE resolution. They are not
# portable: a different screen size, a different Expert RAW version, or even a
# different aspect-ratio setting inside the app will move these buttons. The
# preflight check refuses to run if the phone's resolution differs from
# REFERENCE_SIZE unless you pass --scale.
#
# To re-measure: Developer options -> Pointer location ON, touch each control,
# read X/Y off the top bar, then turn it back off.

REFERENCE_SIZE = (1080, 2340)

MF_BUTTON = (90, 1850)       # opens the manual-focus slider
SHUTTER = (540, 2090)

SLIDER_Y = 1897
RESET_SWIPE = (650, 780)     # drag right, drives focus to the 0.0 end stop
STEP_SWIPE = (650, 550)      # drag left by one 0.1 increment

# --- Timing ----------------------------------------------------------------

MF_OPEN_TIME = 1.0           # slider animates in
FOCUS_SETTLE_TIME = 1.5      # lens physically moves
CAPTURE_WAIT_TIME = 6.0      # shutter -> app ready for the next tap

# Expert RAW writes the DNG well after the JPG appears, so the pull waits for
# files to show up rather than sleeping a fixed amount.
FILE_POLL_INTERVAL = 5.0
FILE_WAIT_TIMEOUT = 420.0
FILE_QUIET_PERIOD = 15.0     # no new files for this long => phone is done

PHONE_FOLDER = "/sdcard/DCIM/Expert RAW"
IMAGE_SUFFIXES = (".dng", ".jpg", ".jpeg")
DEFAULT_OUTPUT = Path.home() / "expert_raw_focus" / "captures"

# Captures land outside the repo by default: these are tens of MB per DNG and
# the project directory is OneDrive-synced.


class SweepError(RuntimeError):
    """Something is wrong with the phone or the setup; abort with a message."""


# --- adb plumbing ----------------------------------------------------------


def find_adb(explicit: str | None) -> str:
    """Locate adb, preferring an explicit path, then PATH, then the usual spots."""
    candidates = []
    if explicit:
        candidates.append(explicit)

    on_path = shutil.which("adb")
    if on_path:
        candidates.append(on_path)

    candidates += [
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        str(Path.home() / "Library/Android/sdk/platform-tools/adb"),
    ]

    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate

    raise SweepError(
        "adb not found. Install it with `brew install --cask android-platform-tools`, "
        "or pass --adb /path/to/adb."
    )


@dataclass
class Device:
    adb: str
    serial: str | None = None

    def _base(self) -> list[str]:
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, *args, check: bool = True, timeout: float = 60.0) -> subprocess.CompletedProcess:
        result = subprocess.run(
            self._base() + [str(a) for a in args],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise SweepError(f"adb {' '.join(str(a) for a in args)} failed: {detail}")
        return result

    def shell(self, command: str, check: bool = True) -> str:
        return self.run("shell", command, check=check).stdout

    def tap(self, x: int, y: int, label: str = "") -> None:
        suffix = f"  ({label})" if label else ""
        print(f"  tap ({x}, {y}){suffix}")
        self.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int, label: str = "") -> None:
        suffix = f"  ({label})" if label else ""
        print(f"  swipe ({x1}, {y1}) -> ({x2}, {y2}){suffix}")
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")


# --- Preflight -------------------------------------------------------------


def list_devices(adb: str) -> list[tuple[str, str]]:
    result = subprocess.run([adb, "devices"], text=True, capture_output=True, timeout=30)
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


def select_device(adb: str, serial: str | None) -> Device:
    devices = list_devices(adb)

    if not devices:
        raise SweepError(
            "No device found. Check that:\n"
            "  - the cable carries data (charge-only cables show nothing)\n"
            "  - USB debugging is on (Settings > Developer options)\n"
            "  - you tapped Allow on the phone's debugging prompt"
        )

    if serial:
        match = [d for d in devices if d[0] == serial]
        if not match:
            raise SweepError(f"Device {serial} not attached. Attached: {devices}")
        chosen = match[0]
    elif len(devices) > 1:
        listing = "\n".join(f"  {s}  ({state})" for s, state in devices)
        raise SweepError(f"Multiple devices attached; pick one with --serial:\n{listing}")
    else:
        chosen = devices[0]

    serial_id, state = chosen
    if state == "unauthorized":
        raise SweepError(
            f"Device {serial_id} is unauthorized. Unlock the phone and tap Allow on the "
            "'Allow USB debugging?' prompt (check 'Always allow')."
        )
    if state != "device":
        raise SweepError(f"Device {serial_id} is in state '{state}', expected 'device'.")

    return Device(adb=adb, serial=serial_id)


def screen_size(device: Device) -> tuple[int, int] | None:
    """Physical resolution, or None if it can't be parsed."""
    output = device.shell("wm size", check=False)
    # "Physical size: 1080x2340" and possibly an "Override size:" line, which is
    # what input coordinates actually use when present.
    override = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    physical = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    match = override or physical
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def screen_is_on(device: Device) -> bool | None:
    """True/False, or None if the state can't be determined."""
    output = device.shell("dumpsys power", check=False)
    match = re.search(r"Display Power: state=(\w+)", output)
    if match:
        return match.group(1).upper() == "ON"
    match = re.search(r"mScreenState=(\w+)", output)
    if match:
        return match.group(1).upper() == "ON"
    return None


def foreground_app(device: Device) -> str | None:
    """Best-effort package name of the focused app."""
    output = device.shell("dumpsys window", check=False)
    match = re.search(r"mCurrentFocus=\S+\s+\S+\s+([\w.]+)/", output)
    if match:
        return match.group(1)

    output = device.shell("dumpsys activity activities", check=False)
    match = re.search(r"topResumedActivity=\S+\s+\S+\s+([\w.]+)/", output)
    if match:
        return match.group(1)
    return None


def scaled(point: tuple[int, int], factor: tuple[float, float]) -> tuple[int, int]:
    return round(point[0] * factor[0]), round(point[1] * factor[1])


def preflight(device: Device, assume_yes: bool, allow_scale: bool) -> tuple[float, float]:
    """Check the phone is in a usable state. Returns the coordinate scale factor."""
    print("Preflight:")

    size = screen_size(device)
    scale = (1.0, 1.0)
    if size is None:
        print("  ! could not read screen size; assuming reference coordinates are correct")
    elif size == REFERENCE_SIZE:
        print(f"  screen {size[0]}x{size[1]} (matches reference)")
    else:
        message = (
            f"screen is {size[0]}x{size[1]}, coordinates were measured on "
            f"{REFERENCE_SIZE[0]}x{REFERENCE_SIZE[1]}"
        )
        if not allow_scale:
            raise SweepError(
                f"{message}.\n"
                "Every tap would land in the wrong place. Either re-measure the "
                "coordinates at the top of this file (Developer options > Pointer "
                "location), or pass --scale to scale them proportionally -- which is "
                "a guess, so verify it with --dry-run first."
            )
        scale = (size[0] / REFERENCE_SIZE[0], size[1] / REFERENCE_SIZE[1])
        print(f"  ! {message}; scaling by {scale[0]:.3f} x {scale[1]:.3f}")

    on = screen_is_on(device)
    if on is False:
        raise SweepError("Screen is off. Wake and unlock the phone, then open Expert RAW.")
    print(f"  screen on: {'yes' if on else 'unknown'}")

    package = foreground_app(device)
    print(f"  foreground app: {package or 'unknown'}")
    if package and "raw" not in package.lower() and "camera" not in package.lower():
        print(
            f"  ! '{package}' does not look like Expert RAW. If the camera is not the "
            "visible, focused app, every tap goes to the wrong place."
        )
        if not assume_yes and not confirm("Continue anyway?"):
            raise SweepError("Aborted.")

    listing = device.run("shell", f'ls -1 "{PHONE_FOLDER}"', check=False)
    if listing.returncode != 0:
        raise SweepError(
            f"Cannot list {PHONE_FOLDER} on the phone. Take one photo in Expert RAW by "
            "hand so the folder exists, or edit PHONE_FOLDER to match where it saves."
        )
    print(f"  {PHONE_FOLDER} is readable")

    return scale


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


# --- File transfer ---------------------------------------------------------


def phone_images(device: Device) -> set[str]:
    """Filenames of images currently in the capture folder."""
    output = device.run("shell", f'ls -1 "{PHONE_FOLDER}"', check=False).stdout
    return {
        name.strip()
        for name in output.splitlines()
        if name.strip().lower().endswith(IMAGE_SUFFIXES)
    }


def wait_for_new_images(device: Device, baseline: set[str], expected: int) -> list[str]:
    """Poll until `expected` new files appear, or writes go quiet, or we time out.

    Comparing against a baseline is what makes this safe to run twice in a row:
    taking the N most recent files would happily re-pull the previous run's
    images if this run captured fewer than it meant to.
    """
    print(f"\nWaiting for new files in {PHONE_FOLDER} (expecting {expected})...")

    deadline = time.monotonic() + FILE_WAIT_TIMEOUT
    last_change = time.monotonic()
    seen: set[str] = set()

    while time.monotonic() < deadline:
        current = phone_images(device) - baseline

        if current != seen:
            new_count = len(current - seen)
            seen = current
            last_change = time.monotonic()
            dng = sum(1 for n in seen if n.lower().endswith(".dng"))
            jpg = len(seen) - dng
            print(f"  +{new_count}  (total {len(seen)}: {dng} DNG, {jpg} JPG)")

        if len(seen) >= expected:
            return sorted(seen)

        if seen and time.monotonic() - last_change > FILE_QUIET_PERIOD:
            print(f"  no new files for {FILE_QUIET_PERIOD:.0f}s; assuming the phone is done")
            return sorted(seen)

        time.sleep(FILE_POLL_INTERVAL)

    print("  ! timed out waiting for files")
    return sorted(seen)


def pull_images(device: Device, names: list[str], destination: Path) -> int:
    pulled = 0
    for name in names:
        remote = f"{PHONE_FOLDER}/{name}"
        print(f"  pull {name}")
        result = device.run("pull", remote, str(destination), check=False, timeout=300)
        if result.returncode == 0:
            pulled += 1
        else:
            detail = (result.stderr or result.stdout or "").strip()
            print(f"  ! failed: {detail}")
    return pulled


# --- Sweep -----------------------------------------------------------------


def run_sweep(device: Device, positions: int, scale: tuple[float, float], dry_run: bool) -> None:
    mf_button = scaled(MF_BUTTON, scale)
    shutter = scaled(SHUTTER, scale)
    slider_y = round(SLIDER_Y * scale[1])
    reset = (round(RESET_SWIPE[0] * scale[0]), round(RESET_SWIPE[1] * scale[0]))
    step = (round(STEP_SWIPE[0] * scale[0]), round(STEP_SWIPE[1] * scale[0]))

    print("\nOpening manual focus and resetting to 0.0")
    device.tap(*mf_button, label="MF button")
    time.sleep(MF_OPEN_TIME)
    device.swipe(reset[0], slider_y, reset[1], slider_y, 500, label="reset to 0.0")
    time.sleep(FOCUS_SETTLE_TIME)

    for i in range(positions):
        focus_value = i / 10
        print(f"\n[{i + 1}/{positions}] expected MF {focus_value:.1f}")

        if dry_run:
            print("  (dry run: shutter not tapped -- check the MF readout now)")
            time.sleep(1.0)
        else:
            device.tap(*shutter, label="shutter")
            time.sleep(CAPTURE_WAIT_TIME)

        if i < positions - 1:
            device.tap(*mf_button, label="MF button")
            time.sleep(MF_OPEN_TIME)
            device.swipe(step[0], slider_y, step[1], slider_y, 350, label="step +0.1")
            time.sleep(FOCUS_SETTLE_TIME)


# --- Entry point -----------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", help="sample/run name (prompted for if omitted)")
    parser.add_argument("--positions", type=int, default=11, help="focus positions (default 11)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="output base directory")
    parser.add_argument("--adb", help="path to adb (default: PATH, then the usual locations)")
    parser.add_argument("--serial", help="device serial, if more than one is attached")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="drive the focus slider without capturing, to verify the coordinates",
    )
    parser.add_argument("--no-pull", action="store_true", help="capture but leave files on the phone")
    parser.add_argument(
        "--scale",
        action="store_true",
        help="scale coordinates if the screen size differs from the reference (a guess)",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompts")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.positions < 1:
        print("--positions must be at least 1", file=sys.stderr)
        return 2

    try:
        adb = find_adb(args.adb)
        device = select_device(adb, args.serial)
        print(f"Using {adb}\nDevice {device.serial}\n")

        scale = preflight(device, assume_yes=args.yes, allow_scale=args.scale)

        output_folder = None
        if not args.dry_run:
            name = args.name or input("Enter sample/run name: ")
            name = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
            if not name:
                raise SweepError("Run name cannot be empty.")

            output_folder = args.out / datetime.now().strftime("%Y-%m-%d") / name
            output_folder.mkdir(parents=True, exist_ok=True)
            print(f"\nSaving to {output_folder}")

        baseline = phone_images(device)
        print(f"{len(baseline)} image(s) already in {PHONE_FOLDER}")

        if args.dry_run:
            print("\nDRY RUN -- no photos will be taken. Watch the MF readout on the phone "
                  "and check it steps 0.0, 0.1, 0.2 ... without saturating early.")
        if not args.yes and not confirm("\nPhone unlocked and showing Expert RAW? Start?"):
            print("Aborted.")
            return 1

        run_sweep(device, args.positions, scale, args.dry_run)
        print("\nFocus sweep complete.")

        if args.dry_run:
            print("Dry run finished. If the slider stepped correctly, re-run without --dry-run.")
            return 0

        if args.no_pull:
            print("--no-pull: files left on the phone.")
            return 0

        # Two files per position when the app is set to save DNG + JPG.
        new_files = wait_for_new_images(device, baseline, expected=args.positions * 2)
        if not new_files:
            raise SweepError(
                "No new files appeared. The shutter taps probably missed, or Expert RAW "
                "is saving somewhere other than " + PHONE_FOLDER
            )

        print(f"\nPulling {len(new_files)} file(s):")
        pulled = pull_images(device, new_files, output_folder)
        print(f"\n{pulled}/{len(new_files)} file(s) copied to\n{output_folder}")

        dng = sum(1 for n in new_files if n.lower().endswith(".dng"))
        if dng != args.positions:
            print(
                f"\n! Expected {args.positions} DNG files, found {dng}. Check for missed "
                "shutter taps before trusting this run."
            )
        return 0 if pulled == len(new_files) else 1

    except SweepError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"\nError: adb timed out: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. The phone may be mid-sweep; check the focus slider.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
