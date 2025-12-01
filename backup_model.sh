#!/bin/bash

# -------------------------------------------------------------
# Backup script for MyPlayer fine-tuned models
# Creates a timestamped tar.gz archive of all model directories
# under my_player/ai/models/ and stores them in:
#   /home/dhiman/FineTunedModels/
# -------------------------------------------------------------

set -e

# Paths
PROJECT_ROOT="$(dirname "$(readlink -f "$0")")"
MODELS_DIR="$PROJECT_ROOT/my_player/ai/models"
DEST_DIR="/home/dhiman/FineTunedModels"

# Timestamp (YYYYMMDD_HHMMSS)
TS=$(date +"%Y%m%d_%H%M%S")

# Output filename
ARCHIVE_NAME="models_backup_${TS}.tar.gz"
ARCHIVE_PATH="${DEST_DIR}/${ARCHIVE_NAME}"

echo "-------------------------------------------------------------"
echo "  MyPlayer Model Backup Script"
echo "-------------------------------------------------------------"
echo "Project Root   : $PROJECT_ROOT"
echo "Models Folder  : $MODELS_DIR"
echo "Destination    : $DEST_DIR"
echo "Archive Name   : $ARCHIVE_NAME"
echo "-------------------------------------------------------------"

# Ensure destination exists
mkdir -p "$DEST_DIR"

# Verify models directory exists
if [ ! -d "$MODELS_DIR" ]; then
    echo "[ERROR] Models directory not found: $MODELS_DIR"
    exit 1
fi

echo "[INFO] Creating compressed archive..."
tar -czvf "$ARCHIVE_PATH" -C "$MODELS_DIR" .

echo "-------------------------------------------------------------"
echo "[SUCCESS] Backup created:"
echo "          $ARCHIVE_PATH"
echo "-------------------------------------------------------------"
