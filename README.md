# Smartphone Nailfold Capillaroscope Project

This repository contains image data, conversion tools, analysis notebooks, and
phone-control scripts for a smartphone-based nailfold capillaroscope workflow.
It is organized as a Durr Lab master's project workflow, starting with raw
smartphone images and ending with optical density, capillary segmentation, and
flow/velocity analysis.

## Repository Layout

```text
smartphone_capillaroscope/
|-- 00_Images/
|-- 01_Image_Conversion/
|-- 02_Image_Quality_Assessment/
|-- 03_Optical_Density_Calculation/
|-- 04_Extinction_coefficient/
|-- 05_Capillary_Segmentation/
|-- 06_Remote_Phone_Control/
|-- BackgroundSubtract.py
|-- convert_to_ipynb.py
`-- README.md
```

## Folder Contents

### `00_Images/`

Raw and processed smartphone capillaroscope image data. The folder includes:

- `1x nailfold/`: nailfold image sets collected at 1x magnification, including
  DNG, JPG, RAW, TIFF, and PNG-derived outputs.
- `1x resolution target/`: resolution-target acquisitions for image quality and
  MTF analysis.
- `3.3x/`: higher-magnification image sets organized by acquisition date and
  focus/exposure setting folders.

Common file types in this folder include `.dng`, `.raw`, `.jpg`, `.tif`,
`.tiff`, `.png`, `.mov`, `.mp4`, `.csv`, `.json`, `.txt`, and `.zip`.
Several acquisition folders also contain `focus_pipeline_out/` results with:

- `focus_ranking.csv`
- `pipeline_params.txt`
- `calibration.json`

### `01_Image_Conversion/`

Tools for converting smartphone raw image formats into TIFF images for later
analysis.

- `convert_image.py`: converts `.dng` files in a selected folder to 16-bit TIFF
  using `rawpy` and `tifffile`.
- `convert_image.ipynb`: notebook version of the DNG conversion workflow.
- `extract_raw_subifd.m`: MATLAB helper for reading a raw DNG SubIFD and saving
  an uncompressed 16-bit TIFF.

Typical Python conversion:

```bash
python 01_Image_Conversion/convert_image.py
```

The script prompts for the folder containing `.dng` files and writes `.tif`
files next to the source images.

### `02_Image_Quality_Assessment/`

Focus and resolution analysis tools.

- `focus_pipeline.ipynb`: focus detection pipeline for capillary phantom image
  stacks. It creates inpainted bead-free frames, computes multiple focus
  metrics, combines them into a consensus score, and ranks in-focus images.
- `read_mtf.ipynb`: notebook for reading and reviewing MTF-related results.
- `MTF_Analysis.m`: MATLAB slanted-edge MTF analysis script.
- `simple_MTF_Analysis.m`: folder-based TIFF MTF workflow using the same
  slanted-edge method.

Outputs from focus analysis are commonly saved in `focus_pipeline_out/`
folders inside the relevant image acquisition directories.

### `03_Optical_Density_Calculation/`

Notebooks and MATLAB scripts for computing capillary intensity, background
intensity, and optical density.

- `full_pipeline.ipynb`: end-to-end Python workflow for capillary/background
  intensity extraction and optical-density calculation.
- `OD_fixed_BG.ipynb`: optical density pipeline using a separately acquired
  reference background image.
- `capillary_crop.ipynb`: capillary cropping and profile extraction workflow.
- `intensity_profile/`: CSV outputs containing capillary and background
  intensity profiles and mean profiles.
- `MATLAB_code/`: MATLAB scripts for single-capillary, multiple-capillary, and
  background/flow calculations.

Representative outputs include intensity profiles, mean capillary intensity
`I`, mean background intensity `I0`, and optical-density-related values.

### `04_Extinction_coefficient/`

Spectral and hemoglobin extinction-coefficient utilities.

- `compute_led_power_density.py`: generates a Gaussian LED spectral power
  density table on a wavelength grid and saves it to Excel, optionally with a
  CSV copy.
- `plotHbExtinctionFromMeasuredSpectra.m`: MATLAB script that combines measured
  illumination spectra with Prahl hemoglobin extinction data to compute
  effective extinction coefficients for HbO2 and Hb.
- `prahl_extinction.txt`: hemoglobin extinction coefficient reference data.
- `Combined_Spectra.xlsx`: measured or combined spectra workbook.
- `led_574nm.xlsx`: generated or measured 574 nm LED spectrum workbook.

Example LED spectrum generation:

```bash
python 04_Extinction_coefficient/compute_led_power_density.py --lambda0 574 --fwhm 35 --step 1 --out 04_Extinction_coefficient/led_574nm.xlsx --csv
```

### `05_Capillary_Segmentation/`

Capillary detection, straightening, kymograph, and velocity-analysis tools.

- `automated_capillary.ipynb`: automated capillary segmentation workflow using
  vesselness filtering, thresholding, skeletonization, and centerline handling.
- `capillary_straighten.ipynb`: straightens capillaries along their centerline
  for profile and downstream analysis.
- `velocity_ST_diagram.ipynb`: space-time diagram and velocity analysis.
- `lowpassfilter.ipynb`: stabilization/filtering workflow.
- `flowmap_utils.py`: helper functions for centerline sorting, skeleton pruning,
  vessel wall extraction, flow direction propagation, and geometric transforms.
- `kymograph_utils.py`: helper functions for loading frame sequences,
  compensating kymographs, Radon-transform velocity estimation, and
  interpolation.
- `crop_coords.json`: saved crop coordinates.
- `capillary_mask.tif`, `cropped_capillary.tif`, `cropped_image.png`,
  `cropped_image_debug.png`: example/intermediate segmentation outputs.

### `06_Remote_Phone_Control/`

Android Debug Bridge scripts for controlling Samsung Expert RAW during image
acquisition.

- `burst_raw.sh`: launches Expert RAW and captures a burst of images using the
  camera key event.
- `control_tap.py`: sweeps focus, shutter, ISO, and white balance by tapping
  calibrated UI locations, with MediaStore polling to wait for captures.
- `control_drag.py`: sweeps controls by relative drag/swipe steps from
  calibrated slider positions.

Example burst capture:

```bash
bash 06_Remote_Phone_Control/burst_raw.sh 5 2
```

This captures 5 shots with a 2 second delay, assuming the phone is connected
and `adb` can see the device.

## Top-Level Utilities

- `BackgroundSubtract.py`: ImageJ/Jython macro-style script that converts the
  active image to 32-bit grayscale, applies a Gaussian blur background estimate,
  divides the original image by the blurred background, and displays a
  background-subtracted TIFF result.
- `convert_to_ipynb.py`: converts percent-format Python notebooks into `.ipynb`
  files. The current target is `optical_density_pipeline.py` to
  `optical_density_pipeline.ipynb` if that source file is present.

## Suggested Workflow

1. Acquire smartphone images using Expert RAW manually or with scripts in
   `06_Remote_Phone_Control/`.
2. Store raw image sets under `00_Images/`, organized by magnification, date,
   subject/sample, or acquisition setting.
3. Convert `.dng` files to `.tif` using `01_Image_Conversion/convert_image.py`
   or the MATLAB SubIFD extraction helper.
4. Use `02_Image_Quality_Assessment/focus_pipeline.ipynb` to rank focus-sweep
   image stacks and identify the best frames.
5. Use `03_Optical_Density_Calculation/` notebooks to crop capillaries,
   extract intensity profiles, estimate background intensity, and compute
   optical density.
6. Use `04_Extinction_coefficient/` scripts to generate LED spectra and compute
   effective hemoglobin extinction coefficients when needed.
7. Use `05_Capillary_Segmentation/` notebooks and utilities for vessel
   segmentation, centerline extraction, capillary straightening, kymographs, and
   velocity analysis.

## Python Dependencies

The Python scripts and notebooks use a mix of scientific imaging packages. A
typical environment should include:

```bash
pip install rawpy tifffile numpy pandas matplotlib scipy scikit-image opencv-python imageio plantcv networkx openpyxl
```

Some notebooks may require additional packages depending on the exact cells
being run. MATLAB is needed for `.m` scripts, and ImageJ/Fiji is needed for
`BackgroundSubtract.py`.

## External Tools

- `adb`: required for the remote phone-control scripts in
  `06_Remote_Phone_Control/`.
- Samsung Expert RAW: the phone-control scripts launch
  `com.samsung.android.app.galaxyraw`.
- MATLAB with Image Processing Toolbox: required for the MTF, DNG SubIFD, and
  extinction-coefficient MATLAB scripts.
- ImageJ/Fiji: required for the top-level background subtraction script.

## Notes

- Large raw image files are kept inside the repository under `00_Images/`.
- Generated TIFFs, focus-ranking outputs, segmentation masks, crop images, and
  intensity CSVs are also present and can be regenerated from the corresponding
  notebooks/scripts.
- Several scripts contain acquisition-specific paths or calibrated screen
  coordinates. Check paths and coordinates before running them on a new image
  set or phone display.
