#!/usr/bin/env bash

# Exit on any error
set -e

echo "[RUN_APP] Activating virtual environment..."
# Modify path if your venv is somewhere else:
source "/home/david/DMC_app/venv_hailo_rpi5_examples/bin/activate"

# If you also need environment variables from setup_env.sh, uncomment:
# echo "[RUN_APP] Sourcing setup_env.sh..."
# source "/home/david/DMC_app/setup_env.sh"

echo "[RUN_APP] Running main.py with arguments..."

python "/home/david/DMC_app/main.py" \
  --labels-json "/home/david/DMC_app/resources/barcode-labels.json" \
  --hef-path "/home/david/DMC_app/resources/yolov11_model_DMC_c.hef" \
  --input "rpi" \
  --use-frame

echo "[RUN_APP] Done."