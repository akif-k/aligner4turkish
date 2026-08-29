#!/usr/bin/env bash
# output/ klasorunun icerigini ve calisirken olusan gecici dosyalari
# (orn. __pycache__) siler. input/ klasorune (girdi) ve klasorlerin
# kendisine dokunmaz. models/ klasorune de DOKUNMAZ (yeniden indirmek
# pahalidir).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

YES=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES=1 ;;
        *)
            echo "Bilinmeyen secenek: $arg" >&2
            echo "Kullanim: $0 [-y|--yes]" >&2
            exit 1
            ;;
    esac
done

TARGET_DIRS=(output)

echo "Silinecek:"
for d in "${TARGET_DIRS[@]}"; do
    echo "  - $SCRIPT_DIR/$d/*"
done
echo "  - __pycache__ klasorleri (proje icinde)"

if [ "$YES" -ne 1 ]; then
    read -r -p "Devam edilsin mi? [e/H] " reply
    case "$reply" in
        [eEyY]*) ;;
        *) echo "Iptal edildi."; exit 0 ;;
    esac
fi

for d in "${TARGET_DIRS[@]}"; do
    mkdir -p "$d"
    find "$d" -mindepth 1 -delete
done

find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} +

echo "Temizlendi."
