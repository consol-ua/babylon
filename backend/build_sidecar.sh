#!/usr/bin/env bash
set -e

echo "Compiling Python backend into a standalone sidecar binary using PyInstaller..."
pyinstaller --noconfirm --onedir --windowed \
    --name "python-sidecar" \
    --add-data "audio_engine.py:." \
    --add-data "ai_pipeline.py:." \
    main.py

echo "Build complete. Executable generated in backend/dist/python-sidecar"
