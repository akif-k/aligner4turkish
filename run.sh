#!/usr/bin/env bash
# mms_aligner'i calistirir (Linux/macOS). "mms_aligner" adli conda ortamini
# kullanir; input/ klasorundeki wav+txt ciftlerini isleyip output/
# klasorune .TextGrid yazar. Windows icin bkz. run.bat.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# conda'yi bul ve "mms_aligner" ortamini etkinlestir.
if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base)"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    CONDA_BASE="$HOME/miniconda3"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    CONDA_BASE="$HOME/anaconda3"
else
    echo "HATA: conda bulunamadi. Once 'mms_aligner' ortamini olusturun:" >&2
    echo "  conda env create -f environment.yml" >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate mms_aligner

python "$SCRIPT_DIR/mmsaligner.py"
