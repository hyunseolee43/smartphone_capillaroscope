# Smartphone Nailfold Capillaroscope

A smartphone-based nailfold capillaroscope: raw DNG capture through to
haemoglobin concentration, capillary segmentation, and flow analysis.
Durr Lab master's project.

> **Status.** The optical-density pipeline runs end to end and is magnification-
> calibrated, but measured `[Hb]` currently reads **~55% below venous ground
> truth** and that discrepancy is unexplained. See
> [`03_Optical_Density_Calculation/DECISIONS.md`](03_Optical_Density_Calculation/DECISIONS.md)
> before quoting any absolute number from this repository.

## What is tracked in git

Only a subset of the working tree is under version control. Image data is far
too large (`00_Images/` alone is ~36 GB) and is **not** in the repository —
it lives alongside it in OneDrive and must be obtained separately.

| | tracked |
|---|---|
| `01_Image_Conversion/`, `04_Extinction_coefficient/`, `05_Capillary_Segmentation/` | yes |
| `06_Remote_Phone_Control/` | yes — kept for reference, **superseded**, see Capture |
| `BackgroundSubtract.py`, `README.md` | yes |
| `00_Images/` and every other folder below | **no** — add a `.gitignore` before `git add -A` |

`03_Optical_Density_Calculation/`, where the current pipeline lives, is **not yet
tracked**. A stray `.DS_Store` is already committed under
`06_Remote_Phone_Control/`; a `.gitignore` would have caught it.

## Layout

```text
smartphone_capillaroscope/
|-- 00_Images/                      raw + processed image data (NOT in git, ~36 GB)
|-- 01_Image_Conversion/            DNG -> linear TIFF/npz
|-- 02_Image_Quality_Assessment/    focus ranking, MTF, magnification
|-- 03_Optical_Density_Calculation/ OD and [Hb]  <- the main pipeline
|-- 04_Extinction_coefficient/      LED-weighted extinction coefficients
|-- 05_Capillary_Segmentation/      vessel masks, straightening, kymographs
|-- 06_Remote_Phone_Control/        adb capture scripts (SUPERSEDED, see below)
|-- 07_Nature_Comm_Samples/         reference figures
|-- 07_PCB_Design/                  illumination board
|-- 08_Full_Workflow/
|-- 09_Samsung_Deliverables/
|-- 10_IRB_CES/
|-- 12_Mobile NFC Captured Data/
|-- 13_mCap_Analysis/
|-- 14_Phantom_fabrication/
|-- BackgroundSubtract.py
`-- README.md
```

## Capture

**Focal stacks are captured natively through Camera2 in the Android app**
(`FocalStackCapture`), driving `LENS_FOCUS_DISTANCE` directly.

The scripts in `06_Remote_Phone_Control/` (`control_tap.py`, `control_drag.py`,
`burst_raw.sh`, `focus_sweep.py`) drive Samsung Expert RAW's UI over
`adb shell input tap`. **That approach is superseded and should not be
revived.** An Android app cannot inject touches into another app, so it can
never move inside the app; and Expert RAW applies processing that
`FocalStackCapture` deliberately disables (noise reduction, hot-pixel, shading,
edge, tonemap), while routing frames through the gallery loses the
`CaptureResult` metadata the analysis reads black level, white level and CFA
pattern from. Both break the intensity linearity optical density depends on.

The folder is kept for reference only.

## The optical-density pipeline

`03_Optical_Density_Calculation/` is where the current work lives. Two
documents there are authoritative and kept up to date:

- **[`PIPELINE.md`](03_Optical_Density_Calculation/PIPELINE.md)** — the flowchart,
  the measurement, step-by-step protocol, constants, QC checks, known gaps.
- **[`DECISIONS.md`](03_Optical_Density_Calculation/DECISIONS.md)** — why each
  choice was made, with the evidence and what would overturn it. Read this
  before changing a setting.

### Code

| file | what |
|---|---|
| `demo_mac.ipynb` | the notebook you run: load image, pick ROIs, inspect results |
| `capillary.py` | all 74 pipeline functions; settings via `configure()` |
| `flat_field.py` | flat construction, focus matching, exposure detection |
| `magnification.py` | NBS-chart calibration (period fitting, deskew) |
| `diameter_response.py` | OD-vs-diameter checks and spread analysis |
| `consistency_analysis.ipynb` | variance components, ICC, repeatability |
| `magnification_calibration.ipynb` | builds `results/magnification_curve.csv` |

Settings live in `capillary.py` and are changed with `configure()`, never by
assignment — most functions read them as module globals, so assigning in the
notebook would change the notebook's copy and leave the module's untouched:

```python
import capillary as cap
cap.configure(PIX_UM=0.8123, SO2=0.90)
cap.settings()
```

### The measurement

```
[Hb] (g/dL) = 64500 x OD / (D_cm x eps x 10)

OD  = -log10(I_capillary / I_background)    at each centerline point
D   = that point's own diameter             (mask ray-cast)
eps = SO2 x 33376 + (1 - SO2) x 35754       LED-weighted, 525 nm
```

Applied **per point** along the capillary, not once per vessel, because the
diameter varies along its length. Median over points within an ROI.

### Calibration

- **Magnification is 2.96x, not the nominal 3.3x.** Calibrated from an NBS
  1963A chart across 15 focus positions; `PIX_UM` is looked up per image from
  `results/magnification_curve.csv`. The nominal value was 12.7% high, so every
  `[Hb]` computed before this was ~11% too high.
- **Flat-field correction is implemented but OFF** (`APPLY_FLAT`). A paired test
  on 20 ROIs found no measurable benefit; see `DECISIONS.md`.
- **Dark subtraction is not applied** — measured dark is ~0.2% of signal.
- Exposure is read automatically from each image's metadata sidecar. Flats
  exist for 1/45, 1/50 and 1/60 only; images at 1/20 and 1/30 cannot be
  flat-corrected and the notebook disables the correction for them.

## Other folders

### `01_Image_Conversion/`
`convert_image.py` / `convert_image.ipynb` convert `.dng` to 16-bit TIFF with
`rawpy` + `tifffile`; `extract_raw_subifd.m` is the MATLAB equivalent.
The pipeline consumes the `green_proxy_linear.npz` + metadata sidecar this
step produces.

### `02_Image_Quality_Assessment/`
`focus_pipeline.ipynb` ranks focus-sweep stacks. `MTF_Analysis.m` and
`simple_MTF_Analysis.m` are slanted-edge MTF scripts; `read_mtf.ipynb` reviews
the results.

### `04_Extinction_coefficient/`
`plotHbExtinctionFromMeasuredSpectra.m` combines measured illumination spectra
with Prahl's haemoglobin data (`prahl_extinction.txt`) to give the LED-weighted
coefficients the pipeline uses. `compute_led_power_density.py` generates a
Gaussian LED spectrum. `led_525nm.xlsx` is the current green LED;
`led_574nm.xlsx` is from the earlier amber configuration.

### `05_Capillary_Segmentation/`
`automated_capillary.ipynb` (vesselness, threshold, skeletonize),
`capillary_straighten.ipynb`, `velocity_ST_diagram.ipynb`, plus
`flowmap_utils.py` and `kymograph_utils.py`.

### `BackgroundSubtract.py`
ImageJ/Fiji Jython macro: 32-bit grayscale, Gaussian background estimate,
divide, display.

## Dependencies

```bash
pip install rawpy tifffile numpy pandas matplotlib scipy scikit-image \
            opencv-python imageio networkx openpyxl imagecodecs Pillow
```

`opencv-python`, not `-headless` — the ROI pickers need the GUI build.
`imagecodecs` is required to read JPEG-XL-compressed DNGs.

MATLAB with the Image Processing Toolbox is needed for the `.m` scripts;
ImageJ/Fiji for `BackgroundSubtract.py`.

## Notes

- Several scripts contain acquisition-specific paths. Check them before running
  on a new image set.
- `00_Images/` is not in the repository. Notebook paths assume it sits at the
  location shown in the layout above.
- Notebooks are committed with outputs. Consider `nbstripout` before adding
  more — `demo_mac.ipynb` alone is ~2.7 MB of stored output.
