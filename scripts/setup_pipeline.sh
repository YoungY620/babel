#!/usr/bin/env bash
# Ubuntu x86_64. Supply Python 3.12 through actions/setup-python or uv.
set -euo pipefail
cd "$(dirname "$0")/../apps/pipeline"
PYTHON="${PYTHON:-python3.12}"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"'
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# CPU wheels avoid downloading CUDA libraries on the CPU-only runner.
.venv/bin/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
