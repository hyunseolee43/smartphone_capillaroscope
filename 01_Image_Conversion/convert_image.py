import os
import shutil
import subprocess
import traceback

import rawpy
from tifffile import imwrite, imread


def convert_with_rawpy(image):
    try:
        with rawpy.imread(image) as raw:
            rgb16 = raw.postprocess(
                gamma=(1, 1),
                use_camera_wb=True,
                output_color=rawpy.ColorSpace.raw, 
                no_auto_scale=True, 
                highlight_mode=rawpy.HighlightMode.Ignore, 
                no_auto_bright=True, 
                output_bps=16
            )
        out_tif = os.path.splitext(image)[0] + '.tif'
        imwrite(out_tif, rgb16)
        return True
    except Exception as e:
        print(f"rawpy failed: {e}")
        return False


def main():
    folder = input("Enter the folder containing .dng files: ").strip()
    if not os.path.isdir(folder):
        print("Error: Not a valid directory.")
        return

    for fname in os.listdir(folder):
        if not fname.lower().endswith('.dng'):
            continue
        path = os.path.join(folder, fname)
        if convert_with_rawpy(path):
            continue

        print(f"Failed to convert {path} with all methods.")

if __name__ == '__main__':
    main()
