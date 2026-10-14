"""
Generate LED spectral power density on the *correct* wavelength grid for a given LED.

- Grid is constructed automatically as [λ0 - K·FWHM,  λ0 + K·FWHM] with K=4 by default.
- Step is configurable (default 1.0 nm).
- Spectrum model: Gaussian with FWHM parametrization (peak at λ0).
      I(λ) = A * exp( -4*ln(2) * ((λ - λ0)^2 / FWHM^2) )

Scaling options (choose one or none):
  --peak-value A       -> set A (W/nm) directly (peak spectral density at λ0).
  --total-power P      -> compute A so that ∫ I(λ) dλ = P watts (analytical Gaussian integral).
  (if neither is given, A=1.0 and units are 'arb').

Example (your LED):
  python3 compute_led_power_density.py --lambda0 525 --fwhm 30 --step 1 --out led_525nm.xlsx
"""

from __future__ import annotations

import argparse
import math
import os
from datetime import datetime

import numpy as np
import pandas as pd


def gaussian_normalized(lmbda: np.ndarray, lmbda0: float, fwhm: float) -> np.ndarray:
    return np.exp(-4.0 * np.log(2.0) * ((lmbda - lmbda0) ** 2) / (fwhm ** 2))



def main():
    p = argparse.ArgumentParser(description="Generate LED spectrum on a proper wavelength grid (λ0 ± K·FWHM).")
    p.add_argument("--lambda0", type=float, default=574.0, help="Peak wavelength λ0 in nm (default 574).")
    p.add_argument("--fwhm", type=float, default=35.0, help="FWHM bandwidth in nm (default 35).")
    p.add_argument("--kspan", type=float, default=4.0, help="Half-span in FWHM units; grid is λ0±K·FWHM (default 4).")
    p.add_argument("--step", type=float, default=1.0, help="Grid step in nm (default 1.0).")
    p.add_argument("--peak-value", dest="peak_value", type=float, default=None,
                   help="Peak spectral density A in W/nm at λ0.")
    p.add_argument("--total-power", dest="total_power", type=float, default=None,
                   help="Total power P in W; A is chosen so that the integral of I equals P.")
    p.add_argument("--out", default=None, help="Output Excel path (default auto-named).")
    p.add_argument("--csv", action="store_true", help="Also write a CSV copy next to the Excel file.")
    args = p.parse_args()

    if args.peak_value is not None and args.total_power is not None:
        raise SystemExit("Use only one of --peak-value or --total-power (not both).")

    # Build wavelength grid: [λmin, λmax] = [λ0 - K·FWHM, λ0 + K·FWHM]
    lam_min = args.lambda0 - args.kspan * args.fwhm
    lam_max = args.lambda0 + args.kspan * args.fwhm

    # Ensure increasing order and include the end by adding a tiny epsilon
    n_steps = max(2, int(math.floor((lam_max - lam_min) / args.step)) + 1)
    lam = np.linspace(lam_min, lam_max, n_steps, dtype=float)

    # Normalized Gaussian (peak=1 at λ0)
    I_norm = gaussian_normalized(lam, args.lambda0, args.fwhm)

    # Determine scale A and units
    if args.peak_value is not None:
        A = args.peak_value
        units = "W/nm"
        scale_note = f"Peak set by --peak-value (A={A} W/nm at λ0)."
    else:
        A = 1.0
        units = "arb"
        scale_note = "Unscaled (A=1). Units are arbitrary."

    I = A * I_norm

    discrete_power = float(np.trapezoid(I, lam))

    out_df = pd.DataFrame({
        "Wavelength (nm)": lam,
        "I_norm(λ) [peak=1]": I_norm,
        f"I(λ) [{units}]": I
    })

    # Output paths
    if args.out is None:
        base = f"led_{int(round(args.lambda0))}nm_fwhm{int(round(args.fwhm))}_k{int(args.kspan)}_step{args.step:g}nm"
        args.out = base + ".xlsx"
    out_xlsx = args.out
    out_csv = os.path.splitext(out_xlsx)[0] + ".csv"

    # Info sheet
    info = pd.DataFrame({
        "Field": [
            "Timestamp", "λ0 (nm)", "FWHM (nm)", "K (half-span)", "Step (nm)",
            "Scaling", "Units of I(λ)", "Continuous ∫I dλ (target if --total-power)",
            "Discrete ∫I dλ on grid"
        ],
        "Value": [
            datetime.now().isoformat(timespec="seconds"),
            args.lambda0, args.fwhm, args.kspan, args.step,
            scale_note, units,
            (f"{args.total_power} W" if args.total_power is not None else "(n/a)"),
            f"{discrete_power} {('W' if units=='W/nm' else 'arb·nm')}"
        ]
    })

    try:
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
            out_df.to_excel(writer, index=False, sheet_name="Spectrum")
            info.to_excel(writer, index=False, sheet_name="Info")
    except Exception as e:
        raise SystemExit(f"Failed to write Excel file: {e}")

    if args.csv:
        out_df.to_csv(out_csv, index=False)

    print(f"Wavelength grid: [{lam_min:.3f}, {lam_max:.3f}] nm with step {args.step} nm "
          f"({len(lam)} points).")
    print(f"Wrote: {out_xlsx}")
    if args.csv:
        print(f"Wrote: {out_csv}")
    print(scale_note)
    print(f"Discrete integral on grid ≈ {discrete_power} {('W' if units=='W/nm' else 'arb·nm')}")


if __name__ == "__main__":
    main()
