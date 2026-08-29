#!/usr/bin/env python
# test_cases.txt'teki ornekleri, GUNCEL syllable_rules.json'a gore
# mmsaligner.py'nin ("segments" tier'inden turetilen) hece motorunun
# uretecegi hecelemeyle karsilastirir.
#
# Yeni bir kural denerken/eklerken kullanim:
#   1. test_cases.txt'e yeni bir satir ekleyin: "kelime -> hece1,hece2,..."
#      (bkz. o dosyanin basindaki notasyon aciklamasi).
#   2. syllable_rules.json'u (ya da mmsaligner.py'deki hece motorunu)
#      degistirin.
#   3. python run_tests.py
#      calistirip TUM satirlarin gectigini (hem yeni eklediginiz hem de
#      eskiden gecen satirlarin hala gectigini) dogrulayin.
#
# Not: Her kelime, cevresinde baska kelime/sessizlik olmadan, TEK BASINA
# hecelenir (_build_syllable_tier dogrudan cagrilir); bu, ses/VAD/kelime-
# sinirlarindan bagimsiz olarak SADECE hece kurallarini (syllable_rules.json)
# test eder.

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_CASES_PATH = os.path.join(BASE_DIR, "test_cases.txt")

# Windows'ta konsolun varsayilan kod sayfasi (orn. cp1254) Turkce'ye ozgu
# harflari basamayabilir; ciktiyi UTF-8'e zorla (Python 3.7+).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, BASE_DIR)
from mmsaligner import load_syllable_rules, _build_syllable_tier  # noqa: E402


def _word_to_chars(word):
    """Bir kelimeyi, her harfi 0.1 saniyelik ayri bir sahte (zamanlamasi
    onemsiz, sadece sirali) `chars` ogesine cevirir - _build_syllable_tier
    zaman degerlerine degil sadece SIRAYA ve metne bakar."""
    chars = []
    t = 0.0
    for ch in word:
        chars.append({"text": ch, "start": round(t, 3), "end": round(t + 0.1, 3)})
        t += 0.1
    return chars


def main():
    rules = load_syllable_rules()
    total = 0
    failed = 0

    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "->" not in line:
                print(f"[HATA] satir {line_no}: '->' bulunamadi, atlandi: {line}")
                continue

            word, expected_str = line.split("->", 1)
            word = word.strip()
            expected = [s.strip() for s in expected_str.strip().split(",")]

            got = [iv["text"] for iv in _build_syllable_tier(_word_to_chars(word), rules)]

            total += 1
            if got == expected:
                print(f"[OK]   satir {line_no}: {word} -> {','.join(got)}")
            else:
                failed += 1
                print(f"[FAIL] satir {line_no}: {word}")
                print(f"       beklenen : {','.join(expected)}")
                print(f"       gercek   : {','.join(got)}")

    print(f"\n{total - failed}/{total} test gecti.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
