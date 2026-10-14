#!/usr/bin/env bash
set -euo pipefail

N=${1:-5}          # number of shots
DELAY=${2:-2}      # seconds between shots

# Ensure phone is connected
adb get-state 1>/dev/null

# launch Expert RAW
adb shell monkey -p com.samsung.android.app.galaxyraw -c android.intent.category.LAUNCHER 1
sleep 1

for i in $(seq 1 "$N"); do
  echo "Shot $i / $N"
  adb shell input keyevent 27 # 27 = CAMERA
  sleep "$DELAY"
done
