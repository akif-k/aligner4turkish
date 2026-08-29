import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import unicodedata

import numpy as np
import soundfile as sf
import torch
import torchaudio
from transformers import AutoProcessor, Wav2Vec2ForCTC

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SAMPLING_FREQ = 16000

DEFAULT_CONFIG = {
    "gap_threshold_ms": 50.0,
    "vad_db_threshold": -40.0,
    "syllable_word_gap_ms": 10.0,
    "syllable_intensity_band_low_hz": 70.0,
    "syllable_intensity_band_high_hz": 1000.0,
    "syllable_intensity_dip_db": 2.0,
}


def load_config():
    """config.json'daki ayarlari (varsa) DEFAULT_CONFIG uzerine uygular;
    dosya yoksa veya bir anahtar eksikse varsayilan deger kullanilir."""
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    return config

# --- Gercek CTC forced-alignment yardimcilari ----------------------------
# Asagidaki algoritmanin genel yaklasimi (CTC path'inden segment/span
# cikarma), MahmoudAshraf97/ctc-forced-aligner (BSD) projesinden esinle-
# nilmistir; o projenin kodu veya derlenmesi gereken ozel C++ uzantisi
# (forced_align_impl.cpp) burada KULLANILMAMISTIR - bunun yerine
# torchaudio.functional.forced_align ile bagimsiz olarak yazilmistir.


class _Segment:
    __slots__ = ("label", "start", "end")

    def __init__(self, label, start, end):
        self.label = label
        self.start = start
        self.end = end


def _merge_repeats(path, idx_to_token):
    """Ardisik ayni etiketli cerceveleri tek bir Segment'te birlestirir."""
    i1 = 0
    n = len(path)
    segments = []
    while i1 < n:
        i2 = i1
        while i2 < n and path[i1] == path[i2]:
            i2 += 1
        segments.append(_Segment(idx_to_token[path[i1]], i1, i2 - 1))
        i1 = i2
    return segments


def _get_spans(tokens, segments, blank):
    """Karakter seviyesindeki segment'leri, `tokens` icindeki kelime
    sinirlarina gore kelime seviyesinde gruplara ayirir; her kelime icin
    ilk ve son harfinin `segments` listesindeki (start_idx, end_idx)
    indeks araligini dondurur (bosluk/star kapatma islemi
    _contiguous_bounds'ta, tum kelimeler icin ortak sekilde yapilir)."""
    ltr_idx = 0
    tokens_idx = 0
    intervals = []
    start = 0
    for seg_idx, seg in enumerate(segments):
        if tokens_idx == len(tokens):
            assert seg_idx == len(segments) - 1
            assert seg.label == blank
            continue
        cur_token = tokens[tokens_idx].split(" ")
        ltr = cur_token[ltr_idx]
        if seg.label == blank:
            continue
        assert seg.label == ltr, f"{seg.label} != {ltr}"
        if ltr_idx == 0:
            start = seg_idx
        if ltr_idx == len(cur_token) - 1:
            ltr_idx = 0
            tokens_idx += 1
            intervals.append((start, seg_idx))
            while tokens_idx < len(tokens) and len(tokens[tokens_idx]) == 0:
                intervals.append((seg_idx, seg_idx))
                tokens_idx += 1
        else:
            ltr_idx += 1

    return intervals


def _contiguous_bounds(item_ranges, segments):
    """`item_ranges` icindeki her ogenin (segments listesindeki
    (start_idx, end_idx) demeti) gercek baslangic/bitis cercevesini,
    aralarindaki bosluklari (blank/<star>) ortadan bolerek hesaplar:
    onceki ogenin bitisi = bir sonraki ogenin baslangici olur. Ilk ve son
    ogenin disindaki (kaydin basindaki/sonundaki sessizlik) sinirlara
    dokunulmaz; bu, _add_edge_silence tarafindan ayri bir "" araligi
    olarak ele alinir."""
    starts = [segments[s].start for s, _ in item_ranges]
    ends = [segments[e].end + 1 for _, e in item_ranges]
    for k in range(len(item_ranges) - 1):
        gap_from, gap_to = ends[k], starts[k + 1]
        if gap_to > gap_from:
            split = gap_from + (gap_to - gap_from) // 2
            ends[k] = split
            starts[k + 1] = split
    return list(zip(starts, ends))


def _bandpass_filtered(waveform, sr, low_hz, high_hz):
    """torchaudio'nun highpass+lowpass biquad filtrelerini ardarda
    uygulayarak basit bir bant-gecirgen filtre olusturur (ek bir
    kutuphane - orn. scipy - gerektirmeden). Hece heceleme kurallarinin
    coz(e)medigi durumlarda hakem olarak kullanilan intensity konturu
    icin, sesin dusuk frekans (temel frekans + ilk formant civari)
    bandini izole eder."""
    filtered = torchaudio.functional.highpass_biquad(waveform, sr, low_hz)
    filtered = torchaudio.functional.lowpass_biquad(filtered, sr, high_hz)
    return filtered


def _intensity_dip_prefers_prev_coda(filtered_np, sr, t0, t1, dip_db, hop_ms=5.0):
    """[t0, t1] araligi (2 unsurlu, kurallarla cozulemeyen bir onset
    adayinin kapladigi zaman) icinde, bant-gecirgen (bkz.
    _bandpass_filtered) intensity konturunda gercek bir "dip" (dusum)
    olup olmadigina ve konumuna gore, ilk unsurun (leftover) ONCEKI
    hecenin kodasina ZORLA eklenip eklenmeyecegine karar verir:
      - Net bir dip yoksa (dip derinligi dip_db'nin altindaysa) -> True
        (guvenli varsayilan: onceki hecenin kodasina eklenir).
      - Dip, araligin ILK yarisindaysa (cekirdekten uzak unsura
        yakinsa) -> True (o unsurun kendi basina "zayif" oldugunu,
        onceki heceye ait olabilecegini dogrular).
      - Dip, araligin IKINCI yarisindaysa (cekirdege yakin unsura
        yakinsa) -> False (dip ikinci unsurla iliskili, ilk unsur hece
        disi/haric kalir - mevcut varsayilan davranis)."""
    hop = max(1, int(round(hop_ms / 1000.0 * sr)))
    i0 = max(0, int(round(t0 * sr)))
    i1 = min(len(filtered_np), int(round(t1 * sr)))
    if i1 - i0 < 2:
        return True

    eps = 1e-10
    times_db = []
    i = i0
    while i < i1:
        j = min(i + hop, i1)
        rms = float(np.sqrt(np.mean(filtered_np[i:j] ** 2))) + eps
        times_db.append(((i + j) / 2.0 / sr, 20.0 * math.log10(rms)))
        i = j
    if not times_db:
        return True

    min_t, min_db = min(times_db, key=lambda td: td[1])
    edge_db = max(times_db[0][1], times_db[-1][1])
    if edge_db - min_db < dip_db:
        return True

    return min_t <= (t0 + t1) / 2.0


def _vad_silence_span(waveform_np, sr, t0, t1, db_threshold, hop_ms=5.0):
    """[t0, t1] saniye araligi icinde, ardisik hop_ms genisligindeki
    pencerelerin RMS enerjisini dBFS'e cevirip db_threshold'un ALTINDA
    kalan EN UZUN surekli alt-araligi bulur (basit, enerji tabanli bir
    VAD). Sessiz bir alt aralik yoksa (t0, t0) (sifir uzunluk) doner.
    Bu, CTC modelinin kendi "blank" karari yerine dogrudan ses enerjisini
    kullanarak gercek sessizligin nerede basladigini/bittigini bulur."""
    hop = max(1, int(round(hop_ms / 1000.0 * sr)))
    i0 = max(0, int(round(t0 * sr)))
    i1 = min(len(waveform_np), int(round(t1 * sr)))
    if i1 <= i0:
        return t0, t0

    eps = 1e-10
    best_start, best_end, best_len = None, None, 0
    cur_start = None
    i = i0
    while i < i1:
        j = min(i + hop, i1)
        rms = float(np.sqrt(np.mean(waveform_np[i:j] ** 2))) + eps
        db = 20.0 * math.log10(rms)
        if db < db_threshold:
            if cur_start is None:
                cur_start = i
        elif cur_start is not None:
            if j - cur_start > best_len:
                best_len, best_start, best_end = j - cur_start, cur_start, i
            cur_start = None
        i = j
    if cur_start is not None and i1 - cur_start > best_len:
        best_start, best_end = cur_start, i1

    if best_start is None:
        return t0, t0
    return best_start / sr, best_end / sr


def _char_bounds_with_gaps(item_ranges, segments, stride_ms, waveform_np, sr, gap_threshold_ms, vad_db_threshold):
    """`_contiguous_bounds` ile ayni amaca hizmet eder (segments tier'i
    icin komsu harfler arasindaki sinirlari hesaplar), ANCAK bosluga
    KARAR VERME ve onun sinirlarini BELIRLEME islemi, CTC modelinin
    (isabetsiz olabilen) "blank" cercevelerine degil, dogrudan ses
    enerjisine (VAD, dB esigiyle - bkz. _vad_silence_span) dayanir: CTC
    yolunun bosluk sandigi her aralikta VAD'a gore fiilen sessiz olan en
    uzun alt-aralik bulunur; bu alt-aralik gap_threshold_ms'i asarsa
    ayri, etiketsiz ("") bir aralik olarak (sinirlari VAD'dan, ornek
    hassasiyetinde) kullanilir; asmiyorsa (kisa/gurultu benzeriyse)
    orijinal CTC araliginin tam ortasindan bolunerek kapatilir."""
    starts = [segments[s].start * stride_ms / 1000.0 for s, _ in item_ranges]
    ends = [(segments[e].end + 1) * stride_ms / 1000.0 for _, e in item_ranges]
    gaps = [None] * (len(item_ranges) - 1)
    for k in range(len(item_ranges) - 1):
        t0, t1 = ends[k], starts[k + 1]
        if t1 <= t0:
            continue
        sil_start, sil_end = _vad_silence_span(waveform_np, sr, t0, t1, vad_db_threshold)
        if (sil_end - sil_start) * 1000.0 > gap_threshold_ms:
            ends[k] = sil_start
            starts[k + 1] = sil_end
            gaps[k] = (sil_start, sil_end)
        else:
            split = (t0 + t1) / 2.0
            ends[k] = split
            starts[k + 1] = split
    return list(zip(starts, ends)), gaps


def _find_nearest_zero_crossing(waveform_np, sr, time_sec, max_deviation_sec=0.010):
    """`time_sec` zamanini, dalga formunda en yakin sifir gecisine
    (ardisik iki ornegin isareti degistigi ya da tam sifir oldugu nokta)
    en fazla `max_deviation_sec` sapmayla tasir; uygun bir sifir gecisi
    bulunamazsa zamani degistirmeden dondurur. Ayni (zaman, dalga formu)
    girdisi icin her zaman ayni sonucu urettiginden (saf/deterministik
    fonksiyon), farkli tier'lerde ayni ham sinir icin ayri ayri
    cagrilsa bile sonuc otomatik olarak tutarli olur."""
    n = len(waveform_np)
    center = int(round(time_sec * sr))
    max_dev = max(1, int(round(max_deviation_sec * sr)))
    lo = max(1, center - max_dev)
    hi = min(n - 1, center + max_dev)
    best_idx, best_dist = None, None
    for i in range(lo, hi + 1):
        if waveform_np[i - 1] * waveform_np[i] <= 0:
            dist = abs(i - center)
            if best_dist is None or dist < best_dist:
                best_dist, best_idx = dist, i
    if best_idx is None:
        return time_sec
    return best_idx / sr


def _snap_tier_boundaries(items, waveform_np, sr, max_deviation_sec=0.010):
    """Bir tier'in ic sinirlarini (ilk araligin 0'daki basi ve son
    araligin kaydin tam sonundaki bitisi haric) en yakin sifir gecisine
    tasir; boluslugu bozmamak icin, iki komsu araligin ortak sinirinin
    tek bir defa hesaplanip her ikisine de yazilmasi saglanir.
    Her sinir BAGIMSIZ olarak kaydirildigi icin (komsu sinirlarla
    koordinasyon olmadan), KISA araliklarda (orn. segments/syllables
    tier'indeki harfler, genelde 20-40 ms) bir sinirin ileri, hemen
    yanindakinin geri kaymasi araligi kucultebilir, hatta TERSINE
    cevirebilir (start > end - Praat'in kabul etmeyecegi gecersiz bir
    aralik). Bunu onlemek icin, tum sinirlar ONCE (hala ORIJINAL, birbirini
    etkilememis konumlarina gore) bagimsiz hesaplanir, SONRA soldan saga
    MONOTON ARTAN olacak (ve komsu araliklar arasinda en az 1 ms kalacak)
    sekilde sinirlanir - boylece hicbir aralik asla sifira cokmez ya da
    ters donmez, sadece (nadir/asiri durumlarda) planlanandan biraz daha
    az kaydirilmis olabilir."""
    if len(items) < 2:
        return items

    raw_snaps = [
        round(_find_nearest_zero_crossing(waveform_np, sr, items[k]["end"], max_deviation_sec), 3)
        for k in range(len(items) - 1)
    ]
    min_gap = 0.001  # TextGrid'in 3 ondalikli hassasiyetinde en kucuk anlamli fark
    for k in range(1, len(raw_snaps)):
        if raw_snaps[k] < raw_snaps[k - 1] + min_gap:
            raw_snaps[k] = raw_snaps[k - 1] + min_gap

    for k, snapped in enumerate(raw_snaps):
        items[k]["end"] = snapped
        items[k + 1]["start"] = snapped
    return items


def _add_edge_silence(items, total_duration):
    """Ilk/son gerceklestirilmis (harf/kelime) araligi ile kaydin tam
    basi/sonu arasinda fark varsa (konusmadan once/sonra sessizlik),
    bunu ayri, bos metinli ("") bir aralik olarak ekler. Boylece
    baslangic siniri "anlamli sinyalin basladigi an", bitis siniri de
    "bittigi an" olur; ayrica frame kotasinin ses suresini tam
    bolmemesinden dogan kucuk son-sinir farki da bu araya emilir."""
    if not items:
        return items
    if items[-1]["end"] < total_duration:
        items.append({"text": "", "start": items[-1]["end"], "end": round(total_duration, 3)})
    else:
        items[-1]["end"] = round(total_duration, 3)
    if items[0]["start"] > 0:
        items.insert(0, {"text": "", "start": 0.0, "end": items[0]["start"]})
    return items


# --- Hece (syllables) tier motoru -----------------------------------
# ~/ipa_verbatim projesindeki syllables.py'nin (rules.json'daki IPA
# sembolu -> hece degeri tablosunu yorumlayan genel motor) Turkce duz
# yazim harflerine uyarlanmis portu. Algoritma birebir aynidir; sadece
# kural tablosu (syllable_rules.json, IPA yerine Turkce harflerle
# anahtarlanmis) ve tier'lerin anahtar adlari (xmin/xmax yerine
# start/end) farklidir. TUM hece kurallari syllable_rules.json'da veri
# olarak tutulur; bu fonksiyonlar sadece o kurallari yorumlar - yeni bir
# hece degeri/kalibi/siralama kurali icin normalde bu kodu degil,
# syllable_rules.json'u duzenlemeniz yeterlidir.
SYLLABLE_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "syllable_rules.json")


def load_syllable_rules():
    with open(SYLLABLE_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _classify_syllable_value(text, rules):
    """Bir harfi 'V' (unlu/cekirdek), 'C' (unsuz) ya da None (haric)
    olarak siniflandirir; hece degerini de dondurur (haric ise 0)."""
    vowel_value = rules["vowel_value"]
    value = rules["hece_degerleri"].get(text)
    if not value:
        return None, 0
    if value == vowel_value:
        return "V", value
    return "C", value


def _parse_syllable_types(rules):
    """rules['syllable_types_priority'] listesini (orn. ["CV","CVC",...])
    ayristirir; her kalip tam olarak bir 'V' icermelidir. Donen deger:
    (allowed_pairs, max_onset, max_coda) - bkz. ipa_verbatim/syllables.py
    parse_syllable_types()."""
    allowed_pairs = set()
    for pattern in rules["syllable_types_priority"]:
        if pattern.count("V") != 1 or any(ch not in "CV" for ch in pattern):
            raise ValueError(
                f"Gecersiz hece tipi deseni: {pattern!r} (yalnizca 'C'/'V' "
                f"iceren, tam olarak bir 'V' iceren bir dize olmali)"
            )
        v_pos = pattern.index("V")
        allowed_pairs.add((v_pos, len(pattern) - v_pos - 1))
    if (0, 0) not in allowed_pairs:
        raise ValueError(
            "syllable_types_priority listesinde tek basina 'V' (cekirdek) "
            "tipi bulunmali; algoritma kapasite/sira kurali saglanamadiginda "
            "en son bu sekle geriler."
        )
    max_onset = max(o for o, _c in allowed_pairs)
    max_coda = max(c for _o, c in allowed_pairs)
    return allowed_pairs, max_onset, max_coda


def _syllable_ordering_check(rules, key):
    """rules[key]'e ('coda_ordering'/'onset_ordering') gore, bir koda/
    onset kumesinin hece degerleri sirasinin gecerli olup olmadigini
    kontrol eden bir fonksiyon dondurur."""
    checks = {
        "ascending": lambda values: all(values[i] < values[i + 1] for i in range(len(values) - 1)),
        "descending": lambda values: all(values[i] > values[i + 1] for i in range(len(values) - 1)),
        "none": lambda _values: True,
    }
    name = rules.get(key, "none")
    if name not in checks:
        raise ValueError(f"{key!r} icin bilinmeyen deger: {name!r} (gecerli: {sorted(checks)})")
    return checks[name]


_FRONT_VOWELS = {"i", "e", "ö", "ü"}
_BACK_VOWELS = {"ı", "a", "o", "u"}


def _epenthetic_vowel(following_vowel):
    """Yaziya ozgu (konusmada Turkce'nin dogal ses dizilimine uymayan)
    CC- onset kumelerinde (orn. "sp", "st", "sk", "sf" - "spor", "staj",
    "skor"; rules["epenthesis_onset_clusters"]'te listelenen, s+patlamali/
    surtunmeli kumeler), kumenin ilk unsurunu (orn. "s") KENDI ayri
    hecesi yapmak icin, bir sonraki hecenin unlusune gore uyumlu bir
    tureme unlusu secer: on unlu (i,e,ö,ü) ise 'i', arka unlu (ı,a,o,u)
    ise 'ı'. Eslesme yoksa (bilinmeyen/haric sembol) bos dizi doner."""
    if following_vowel in _FRONT_VOWELS:
        return "i"
    if following_vowel in _BACK_VOWELS:
        return "ı"
    return ""


def _assign_syllable_ids(chars, rules, intensity_arbiter=None):
    """chars: [{"text","start","end"}, ...] (bir hece grubunun harf
    dizisi). Donen deger: (syllable_id, epenthesis_vowel_of).
    syllable_id, her sembol icin ait oldugu hece numarasini (int, 0'dan
    baslar) ya da None (haric/atanamamis) tutar, chars ile ayni
    uzunlukta bir liste olarak. epenthesis_vowel_of ise,
    `rules["epenthesis_onset_clusters"]`'te (orn. "sp","st","sk","sf")
    gecen bir 2-unsurlu kumenin ILK (cekirdekten en uzak) unsurunun
    indeksini, ona eklenecek tureme unlusune (bkz. _epenthetic_vowel)
    esler - diger TUM hece disi/atanamamis semboller (VAD sessizligi
    dahil) bu sozlukte YER ALMAZ.
    ipa_verbatim/syllables.py'nin assign_syllable_ids() fonksiyonunun
    portudur; ANCAK onset secimi o projedeki "maksimal onset" ilkesinden
    farkli olarak `syllable_types_priority`'nin SIRASINI (CV/CVC/VC/CVCC
    -> CCVC/CCVCC) fiilen uygular: ONCE tek unsurlu (ya da onsetsiz) bir
    onset denenir; disarida kalan unsur ONCEKI hecenin kodasina TAMAMEN
    sigarsa bu tercih edilir (orn. "hiçbir": "ç" "hiç"e koda oldugu icin
    "çb" hic denenmez; "matris": "t" "mat"a koda oldugu icin "tr"
    denenmez). Sigmazsa (ya da onceki hece hic yoksa, orn. "tren"/"spor"
    kelime/grup basinda), 2-unsurlu onsete (CCVC/CCVCC) geriye dusulur -
    BU DA sadece `rules["onset_clusters"]`'teki ACIK LISTEDE (pl, tr, kr
    gibi) geciyorsa kabul edilir (genel bir sonorluk kuraliyla degil,
    cunku gercek bir onset kumesi olusturmayan ama tesadufen sonorlugu
    artan iki unsur da olabilir), ya da `rules["epenthesis_onset_clusters"]`'te
    (sp, st gibi) geciyorsa ilk unsur bir tureme unlusuyle KENDI hecesi
    olur. Kurallarin COZEMEDIGI (ne kodaya sigan ne de gecerli bir onset/
    epentez kumesi olan) durumlarda, `intensity_arbiter` verilmisse (bkz.
    _intensity_dip_prefers_prev_coda) intensity konturu HAKEM olarak
    devreye girer: True donerse ilk unsur onceki hecenin kodasina ZORLA
    eklenir, aksi halde (ya da intensity_arbiter=None ise) mevcut
    (guvenli) varsayilan davranis olan hece disi/haric kalma surer."""
    symbols = [c["text"] for c in chars]
    allowed_pairs, max_onset, max_coda = _parse_syllable_types(rules)
    coda_check = _syllable_ordering_check(rules, "coda_ordering")
    onset_clusters = set(rules.get("onset_clusters", []))
    epenthesis_onset_clusters = set(rules.get("epenthesis_onset_clusters", []))

    n = len(symbols)
    kinds, values = [None] * n, [0] * n
    for i, sym in enumerate(symbols):
        kinds[i], values[i] = _classify_syllable_value(sym, rules)

    syllable_id = [None] * n
    epenthesis_vowel_of = {}
    vowel_indices = [i for i in range(n) if kinds[i] == "V"]

    next_syl_no = 0
    onset_len_of = {}
    prev_vowel_i = None

    def resolve_coda(coda_candidates, onset_len_for_owner):
        coda = list(coda_candidates)
        while coda and not (
            len(coda) <= max_coda
            and (onset_len_for_owner, len(coda)) in allowed_pairs
            and coda_check([values[i] for i in coda])
        ):
            coda.pop()
        return coda

    for vi in vowel_indices:
        syl_no = next_syl_no
        next_syl_no += 1
        syllable_id[vi] = syl_no

        c_block_start = (prev_vowel_i + 1) if prev_vowel_i is not None else 0
        c_block = [i for i in range(c_block_start, vi) if kinds[i] == "C"]
        onset_candidates = c_block[-max_onset:] if max_onset > 0 else []
        leftover = onset_candidates[:-1]

        # ONCELIK (syllable_types_priority sirasi): CV/CVC/VC/CVCC (tek
        # unsurlu ya da onsetsiz onset) CCVC/CCVCC'den (2 unsurlu onset)
        # ONCE denenir. "leftover" (varsa, onset_candidates'in cekirdekten
        # en uzak unsuru) ONCEKI hecenin kodasina TAMAMEN sigarsa, minimal
        # onset tercih edilir (orn. "hiçbir": "ç" "hiç"e koda olarak
        # sigdigi icin "çb" kumesi hic denenmez, "matris": "t" "mat"a koda
        # olarak sigdigi icin "tr" kumesi denenmez). Sigmazsa (ya da
        # onceki hece hic yoksa, orn. "tren"/"spor" kelime basinda),
        # CCVC/CCVCC'ye (onset_clusters/epenthesis_onset_clusters'ta
        # gecerliyse) geriye dusulur.
        leftover_fits_prev_coda = False
        if leftover and prev_vowel_i is not None:
            prev_syl_no = syllable_id[prev_vowel_i]
            leftover_fits_prev_coda = len(resolve_coda(leftover, onset_len_of[prev_syl_no])) == len(leftover)

        onset_take = onset_candidates[-1:]
        forced_prev_coda = []
        if leftover and not leftover_fits_prev_coda:
            cluster_text = "".join(symbols[i] for i in onset_candidates)
            if cluster_text in onset_clusters:
                onset_take = onset_candidates
            elif cluster_text in epenthesis_onset_clusters:
                epenthesis_vowel_of[onset_candidates[0]] = _epenthetic_vowel(symbols[vi])
            elif intensity_arbiter is not None and prev_vowel_i is not None:
                # Kurallar cozemedi (ne kodaya sigdi ne gecerli bir onset/
                # epentez kumesi olustu) - intensity konturu hakem olur.
                t0 = chars[onset_candidates[0]]["start"]
                t1 = chars[onset_candidates[-1]]["end"]
                if intensity_arbiter(t0, t1):
                    forced_prev_coda = leftover

        for i in onset_take:
            syllable_id[i] = syl_no
        onset_len_of[syl_no] = len(onset_take)

        onset_set = set(onset_take)
        coda_candidates = [i for i in c_block if i not in onset_set]

        if prev_vowel_i is not None:
            prev_syl_no = syllable_id[prev_vowel_i]
            for i in forced_prev_coda:
                syllable_id[i] = prev_syl_no
            coda = resolve_coda([i for i in coda_candidates if i not in forced_prev_coda], onset_len_of[prev_syl_no])
            for i in coda:
                syllable_id[i] = prev_syl_no
            # coda_candidates - forced_prev_coda - coda: hece disi/bos kalir (syllable_id=None).

        prev_vowel_i = vi

    if vowel_indices:
        last_vi = vowel_indices[-1]
        last_syl_no = syllable_id[last_vi]
        tail_block = [i for i in range(last_vi + 1, n) if kinds[i] == "C"]
        coda = resolve_coda(tail_block, onset_len_of[last_syl_no])
        for i in coda:
            syllable_id[i] = last_syl_no

    return syllable_id, epenthesis_vowel_of


def _build_syllable_tier(chars, rules, intensity_arbiter=None):
    """`chars` ("segments" tier'i, [{"text","start","end"}, ...]) icin
    "syllables" tier'ini uretir: ayni heceye ait ardisik chars araliklari
    tek bir aralikta birlesir (text = hecedeki harflerin birlesimi, orn.
    "dar"); haric tutulan ya da hecelenmemis (VAD sessizligi dahil)
    araliklar kendi chars sinirinda ayri ve bos ("") kalir - TEK istisna,
    bir sonraki hecenin onset'ine s+patlamali gibi bir kume yuzunden
    katilamayan unsurdur: bu, kendi ayri hecesi olarak, uyumlu bir
    tureme unlusuyle birlikte gosterilir (orn. "s" + "por" -> "s" hecesi
    "sı" olarak; bkz. _epenthetic_vowel). `intensity_arbiter` bkz.
    _assign_syllable_ids."""
    syllable_id, epenthesis_vowel_of = _assign_syllable_ids(chars, rules, intensity_arbiter)

    result = []
    current = None  # {"start", "end", "text", "syl_no"}

    def flush():
        if current is not None:
            result.append({"start": current["start"], "end": current["end"], "text": current["text"]})

    for i, c in enumerate(chars):
        syl_no = syllable_id[i]
        if syl_no is None:
            flush()
            current = None
            text = c["text"] + epenthesis_vowel_of[i] if i in epenthesis_vowel_of else ""
            result.append({"start": c["start"], "end": c["end"], "text": text})
            continue

        if current is not None and current["syl_no"] == syl_no:
            current["end"] = c["end"]
            current["text"] += c["text"]
        else:
            flush()
            current = {"start": c["start"], "end": c["end"], "text": c["text"], "syl_no": syl_no}

    flush()
    return result


def _build_syllable_tier_per_word(
    chars, word_chars_ranges, word_gaps_ms, syllable_word_gap_ms, rules, intensity_arbiter=None
):
    """`_build_syllable_tier`'i, hece kurallarinin VARSAYILAN olarak
    KELIME SINIRINI GECMEMESI icin, kelime kelime (ya da birbirine
    yeterince yakin/baglantili soylenmis kelime GRUPLARI halinde) uygular.
    `word_chars_ranges`: her kelimenin `chars` listesindeki (start_idx,
    end_idx) araligi (dahil). `word_gaps_ms`: ardisik iki kelime arasinda
    VAD'a gore olcülen bosluk suresi (ms), len(word_chars_ranges)-1
    uzunlugunda. Iki kelime arasindaki bu bosluk `syllable_word_gap_ms`'i
    ASARSA (config.json, varsayilan 10 ms) kelimeler AYRI hecelenir (hece
    kelime sinirini hicbir zaman gecmez); asmiyorsa (kelimeler birbirine
    cok yakin/baglantili soylenmisse) TEK bir akis olarak BIRLIKTE
    hecelenir (bu durumda hece kelime sinirini gecebilir - baglantili
    konusmayi yansitir). Kelime araliklari disinda kalan chars ogeleri
    (bas/son sessizligi, kelimeler arasindaki VAD sessizligi) oldugu gibi
    (metnini degistirmeden) kopyalanir. `intensity_arbiter` bkz.
    _assign_syllable_ids."""
    groups = [[0]]
    for i, gap_ms in enumerate(word_gaps_ms):
        if gap_ms > syllable_word_gap_ms:
            groups.append([i + 1])
        else:
            groups[-1].append(i + 1)

    result = []
    covered_until = -1  # chars listesinde son islenen indeks (dahil)

    def copy_through(start_idx, end_idx):
        for i in range(start_idx, end_idx + 1):
            result.append({"start": chars[i]["start"], "end": chars[i]["end"], "text": chars[i]["text"]})

    for group in groups:
        g_start = word_chars_ranges[group[0]][0]
        g_end = word_chars_ranges[group[-1]][1]
        if g_start > covered_until + 1:
            copy_through(covered_until + 1, g_start - 1)
        result.extend(_build_syllable_tier(chars[g_start : g_end + 1], rules, intensity_arbiter))
        covered_until = g_end

    if covered_until < len(chars) - 1:
        copy_through(covered_until + 1, len(chars) - 1)

    return result


_PUNCT_RE = re.compile(r"[.,!?;:\"'()\[\]{}«»„“”‘’—–\-…]")

# Modelin sozlugunde bulunmayan harfler icin ASCII yedegi (fallback):
# facebook/mms-1b-fl102'nin "tur" sozlugu Turkce'ye ozgu harfleri (ç, ğ,
# ı, ö, ş, ü) native icerir, ama sozlukte olmayan baska bir harfle
# karsilasilirsa (orn. baska bir dil/model kullanilirsa) bu ASCII
# donusumune dusulur.
_TURKISH_ASCII_MAP = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U",
})


def _asciify(text):
    text = text.translate(_TURKISH_ASCII_MAP)
    # Genel durum: kalan aksanli/birlesik karakterleri de (varsa) NFKD ile
    # ayirip birlesim (combining) isaretlerini atarak ASCII'ye indirger.
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _normalize_text(text, asciify=True):
    text = text.lower()
    if asciify:
        text = _asciify(text)
    text = _PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class DynamicMMSAligner:
    MODEL_ID = "facebook/mms-1b-fl102"

    def __init__(self, lang_code="tur"):
        self.model_id = self.MODEL_ID
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.lang_code = lang_code

        print(f"\n[MODEL] {self.model_id} yükleniyor ({self.device})...")
        self.processor = AutoProcessor.from_pretrained(self.model_id, cache_dir=MODELS_DIR)
        self.model = Wav2Vec2ForCTC.from_pretrained(self.model_id, cache_dir=MODELS_DIR).to(self.device)
        self.model.eval()

        try:
            self.processor.tokenizer.set_target_lang(self.lang_code)
            self.model.load_adapter(self.lang_code, cache_dir=MODELS_DIR)
        except Exception:
            pass

    def _generate_emissions(self, waveform, window_length=30, context_length=2, batch_size=4):
        """Uzun kayitlar icin baglamli (context) pencerelere bolerek, kisa
        kayitlarda tek gecişte model cikti olasiliklarini (emission) uretir.
        Sonuna, forced-align'in "<star>" (herhangi bir sese/sessizlige
        eslesebilen joker) tokeni icin kullanacagi sifir-logit'li bir sutun
        eklenir."""
        ratio = self.model.config.inputs_to_logits_ratio
        window = int(window_length * SAMPLING_FREQ)
        context = int(context_length * SAMPLING_FREQ)
        context_frames = context // ratio
        window_frames = window // ratio

        if waveform.size(0) < window:
            extension = 0
            context = 0
            input_tensor = waveform.unsqueeze(0)
        else:
            extension = math.ceil(waveform.size(0) / window) * window - waveform.size(0)
            padded = torch.nn.functional.pad(waveform, (context, context + extension))
            input_tensor = padded.unfold(0, window + 2 * context, window)

        emissions_arr = []
        with torch.no_grad():
            for i in range(0, input_tensor.size(0), batch_size):
                batch = input_tensor[i : i + batch_size].to(self.device)
                emissions_arr.append(self.model(batch).logits)

        emissions = torch.cat(emissions_arr, dim=0)
        if context > 0:
            emissions = emissions[:, context_frames : context_frames + window_frames]
        emissions = emissions.flatten(0, 1)
        if extension > 0:
            emissions = emissions[: -(extension // ratio)]

        emissions = torch.log_softmax(emissions, dim=-1)
        emissions = torch.cat(
            [emissions, torch.zeros(emissions.size(0), 1, device=emissions.device)], dim=1
        )
        stride_ms = ratio * 1000 / SAMPLING_FREQ
        return emissions, stride_ms

    def align(
        self, audio_path, text, gap_threshold_ms=None, vad_db_threshold=None, syllable_word_gap_ms=None,
        syllable_intensity_band_low_hz=None, syllable_intensity_band_high_hz=None, syllable_intensity_dip_db=None,
    ):
        config = load_config()
        if gap_threshold_ms is None:
            gap_threshold_ms = config["gap_threshold_ms"]
        if vad_db_threshold is None:
            vad_db_threshold = config["vad_db_threshold"]
        if syllable_word_gap_ms is None:
            syllable_word_gap_ms = config["syllable_word_gap_ms"]
        if syllable_intensity_band_low_hz is None:
            syllable_intensity_band_low_hz = config["syllable_intensity_band_low_hz"]
        if syllable_intensity_band_high_hz is None:
            syllable_intensity_band_high_hz = config["syllable_intensity_band_high_hz"]
        if syllable_intensity_dip_db is None:
            syllable_intensity_dip_db = config["syllable_intensity_dip_db"]

        # torchaudio.load() artik TorchCodec (ve dolayisiyla sisteme kurulu
        # paylasimli/DLL bir ffmpeg) gerektiriyor; wav dosyalari icin buna
        # hic gerek olmadigindan ses dogrudan soundfile ile okunuyor.
        data, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        waveform = torch.from_numpy(np.ascontiguousarray(data.T))
        if sr != SAMPLING_FREQ:
            waveform = torchaudio.transforms.Resample(sr, SAMPLING_FREQ)(waveform)
        waveform = waveform.mean(dim=0)  # mono'ya indirgeme
        total_duration = waveform.shape[0] / SAMPLING_FREQ
        waveform_np = waveform.numpy()  # VAD ve sifir-gecisi (zero-crossing) aramalari icin
        intensity_np = _bandpass_filtered(
            waveform, SAMPLING_FREQ, syllable_intensity_band_low_hz, syllable_intensity_band_high_hz
        ).numpy()  # hece motorunun onset/koda hakemligi icin (bkz. _intensity_dip_prefers_prev_coda)

        # Modelin egitildigi gibi (do_normalize) sifir-ortalama/birim-varyans
        # normalizasyonu, feature extractor uzerinden dosyanin tamami icin
        # bir kez uygulanir.
        normalized = self.processor.feature_extractor(
            waveform.numpy(), sampling_rate=SAMPLING_FREQ, return_tensors="pt"
        ).input_values[0]

        emissions, stride_ms = self._generate_emissions(normalized)

        dictionary = {k.lower(): v for k, v in self.processor.tokenizer.get_vocab().items()}
        dictionary["<star>"] = len(dictionary)
        blank_id = dictionary.get("<blank>", self.processor.tokenizer.pad_token_id)
        idx_to_token = {v: k for k, v in dictionary.items()}

        # Referans metni "kelime" birimlerine ayirip, her kelimeyi kendi
        # karakterlerine bolup aralarina "<star>" (joker) tokeni ekliyoruz;
        # boylece hizalama, kelime sinirlarini modelin "|" tahmin etmesine
        # guvenmeden, dogrudan referans metinden alir. Her harf ONCE oldugu
        # gibi (Turkce dahil) sozlukte aranir; modelin sozlugunde yoksa
        # ASCII karsiligina cevrilir (bkz. yukaridaki _TURKISH_ASCII_MAP).
        words_display = _normalize_text(text, asciify=False).split()
        if not words_display:
            raise ValueError("Hizalanacak metin bos.")

        tokens_starred, text_starred = [], []
        for w in words_display:
            tokens_starred.append("<star>")
            letters = [ch if ch in dictionary else _asciify(ch) for ch in w]
            tokens_starred.append(" ".join(letters))
            text_starred.append("<star>")
            text_starred.append(w)  # orijinal (Turkce) yazim, sadece goruntu icin

        token_indices = [
            dictionary[c] for c in " ".join(tokens_starred).split(" ") if c in dictionary
        ]

        log_probs = emissions.unsqueeze(0).float().cpu()
        targets = torch.tensor([token_indices], dtype=torch.int64)
        path, _scores = torchaudio.functional.forced_align(log_probs, targets, blank=blank_id)
        path = path.squeeze(0).tolist()

        segments = _merge_repeats(path, idx_to_token)
        blank_label = idx_to_token[blank_id]

        # Tier "segments": harf seviyesi (blank/star haric her segment).
        # Bosluga karar verme VAD (ses enerjisi, dB esigi) ile yapilir,
        # CTC modelinin "blank" karari isabetsiz olabildigi icin sadece
        # kaba bir aday araligi olarak kullanilir (bkz. _char_bounds_with_gaps).
        # gap_threshold_ms'yi ASMAYAN (VAD'a gore) bosluklar komsu
        # harfler arasinda ortadan bolunerek kapatilir (bosluksuz);
        # asanlar ise birlestirilmez, ayri, etiketsiz ("") bir aralik
        # olarak (VAD sinirlariyla) eklenir.
        char_ranges = [(i, i) for i, seg in enumerate(segments) if seg.label not in (blank_label, "<star>")]
        char_bounds, char_gaps = _char_bounds_with_gaps(
            char_ranges, segments, stride_ms, waveform_np, SAMPLING_FREQ, gap_threshold_ms, vad_db_threshold
        )
        chars = []
        seg_idx_to_chars_index = {}
        for idx, ((i, _), (s, e)) in enumerate(zip(char_ranges, char_bounds)):
            seg_idx_to_chars_index[i] = len(chars)
            chars.append({
                "text": segments[i].label,
                "start": round(s, 3),
                "end": round(e, 3),
            })
            if idx < len(char_gaps) and char_gaps[idx] is not None:
                g_from, g_to = char_gaps[idx]
                chars.append({
                    "text": "",
                    "start": round(g_from, 3),
                    "end": round(g_to, 3),
                })
        # _add_edge_silence, sessizlik varsa basa yeni bir "" ogesi ekleyip
        # butun listeyi 1 kaydirabilir; seg_idx_to_chars_index bu kaydirmadan
        # ONCE kaydedildigi icin, aynen _add_edge_silence'in kendi kosuluyla
        # ayni sekilde kontrol edip gerekirse esitleriz.
        had_leading_silence = bool(chars) and chars[0]["start"] > 0
        _add_edge_silence(chars, total_duration)
        if had_leading_silence:
            seg_idx_to_chars_index = {k: v + 1 for k, v in seg_idx_to_chars_index.items()}
        _snap_tier_boundaries(chars, waveform_np, SAMPLING_FREQ)

        # Tier "words": kelime seviyesi (star haric her kelime); butun
        # bosluklar (buyuklugune bakilmaksizin) her zaman ortadan
        # bolunerek komsu kelimelere paylastirilir.
        intervals = _get_spans(tokens_starred, segments, blank_label)
        word_texts = [t for t in text_starred if t != "<star>"]
        word_ranges = [r for r, t in zip(intervals, text_starred) if t != "<star>"]
        word_bounds = _contiguous_bounds(word_ranges, segments)
        words = [
            {
                "text": t,
                "start": round(s * stride_ms / 1000.0, 3),
                "end": round(e * stride_ms / 1000.0, 3),
            }
            for t, (s, e) in zip(word_texts, word_bounds)
        ]
        _add_edge_silence(words, total_duration)
        _snap_tier_boundaries(words, waveform_np, SAMPLING_FREQ)

        # Tier "syllables": "segments" tier'inin (yukaridaki, tum bosluk/
        # sinir islemleri tamamlanmis hali) hece kurallarina (bkz.
        # syllable_rules.json, ~/ipa_verbatim/syllables.py'nin Turkce
        # harflerine uyarlanmis portu) gore gruplanmasidir. Kelime sinirini
        # gecip gecmeyecegi VAD'a gore belirlenir (bkz.
        # _build_syllable_tier_per_word).
        word_chars_ranges = [(seg_idx_to_chars_index[s], seg_idx_to_chars_index[e]) for s, e in word_ranges]
        word_gaps_ms = []
        for (_s1, e1), (s2, _e2) in zip(word_ranges, word_ranges[1:]):
            t0 = (segments[e1].end + 1) * stride_ms / 1000.0
            t1 = segments[s2].start * stride_ms / 1000.0
            sil_start, sil_end = _vad_silence_span(waveform_np, SAMPLING_FREQ, t0, t1, vad_db_threshold)
            word_gaps_ms.append((sil_end - sil_start) * 1000.0)
        syllable_rules = load_syllable_rules()
        intensity_arbiter = lambda t0, t1: _intensity_dip_prefers_prev_coda(
            intensity_np, SAMPLING_FREQ, t0, t1, syllable_intensity_dip_db
        )
        syllables = _build_syllable_tier_per_word(
            chars, word_chars_ranges, word_gaps_ms, syllable_word_gap_ms, syllable_rules, intensity_arbiter
        )

        return chars, syllables, words, total_duration

def _escape_textgrid(text):
    """Praat TextGrid metin alaninda gomulu cift tirnaklari, format
    geregi ikiye katlayarak kacirir (" -> "")."""
    return text.replace('"', '""')

def export_to_textgrid(chars, syllables, words, raw_text, total_duration, output_path="sample.TextGrid"):
    """
    Praat uyumlu 4 Tier'li TextGrid dosyasi yazar:
        Tier 1 "segments"  -> harf seviyesi
        Tier 2 "syllables" -> hece seviyesi (bkz. syllable_rules.json)
        Tier 3 "words"     -> kelime seviyesi
        Tier 4 "txt"       -> tum kaydin orijinal transkripti, tek aralik
    """
    txt_text = re.sub(r"\s+", " ", raw_text).strip()

    def write_tier(f, item_no, name, intervals):
        f.write(f'    item [{item_no}]:\n')
        f.write('        class = "IntervalTier"\n')
        f.write(f'        name = "{name}"\n')
        f.write('        xmin = 0\n')
        f.write(f'        xmax = {total_duration:.3f}\n')
        f.write(f'        intervals: size = {len(intervals)}\n')
        for idx, iv in enumerate(intervals, 1):
            f.write(f'        intervals [{idx}]:\n')
            f.write(f'            xmin = {iv["start"]:.3f}\n')
            f.write(f'            xmax = {iv["end"]:.3f}\n')
            f.write(f'            text = "{_escape_textgrid(iv["text"])}"\n')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write('File type = "ooTextFile"\n')
        f.write('Object class = "TextGrid"\n\n')
        f.write(f'xmin = 0\n')
        f.write(f'xmax = {total_duration:.3f}\n')
        f.write('tiers? <exists>\n')
        f.write('size = 4\n')
        f.write('item []:\n')

        write_tier(f, 1, "segments", chars)
        write_tier(f, 2, "syllables", syllables)
        write_tier(f, 3, "words", words)

        # --- Tier 4: txt (tum transkript, tek aralik) ---
        f.write('    item [4]:\n')
        f.write('        class = "IntervalTier"\n')
        f.write('        name = "txt"\n')
        f.write('        xmin = 0\n')
        f.write(f'        xmax = {total_duration:.3f}\n')
        f.write('        intervals: size = 1\n')
        f.write('        intervals [1]:\n')
        f.write('            xmin = 0\n')
        f.write(f'            xmax = {total_duration:.3f}\n')
        f.write(f'            text = "{_escape_textgrid(txt_text)}"\n')

    print(f"\n[BAŞARILI] '{output_path}' başarıyla oluşturuldu!")

# .wav disindaki bu formatlar, input/'da bulunurlarsa otomatik olarak
# 16 kHz/16 bit/mono PCM .wav'a cevrilir (ffmpeg gerektirir; bkz.
# _convert_other_formats). ffmpeg kurulu degilse bu formatlar sessizce
# atlanir (crash olmaz), sadece bir uyari yazilir.
OTHER_AUDIO_EXTENSIONS = {
    ".m4a", ".aac", ".mp3", ".opus", ".amr", ".ogg", ".oga", ".flac",
    ".wma", ".3gp", ".3gpp", ".caf",
}


def _convert_other_formats(input_dir):
    """input_dir icindeki OTHER_AUDIO_EXTENSIONS'taki formatlari 16 kHz/
    16 bit/mono PCM .wav'a cevirip AYNI input_dir icine yazar (ffmpeg
    ile). Ayni taban adda (orn. "kayit.mp3" icin "kayit.wav") zaten bir
    .wav dosyasi varsa, o dosya ATLANIR (yeniden donusturulmez/uzerine
    yazilmaz) - boylece elle yerlestirilmis bir wav'a dokunulmaz."""
    source_files = sorted(
        p for p in glob.glob(os.path.join(input_dir, "*"))
        if os.path.splitext(p)[1].lower() in OTHER_AUDIO_EXTENSIONS
    )
    if not source_files:
        return

    if shutil.which("ffmpeg") is None:
        print(f"[UYARI] input/ klasöründe {len(source_files)} adet .wav olmayan ses "
              f"dosyası var, ama sistemde ffmpeg kurulu değil; bunlar dönüştürülemeyecek "
              f"ve atlanacak. ffmpeg kurup tekrar deneyin.")
        return

    for src in source_files:
        base_name = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(input_dir, base_name + ".wav")
        if os.path.exists(dst):
            continue
        print(f"[DÖNÜŞTÜRÜLÜYOR] {os.path.basename(src)} -> {base_name}.wav")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-ar", str(SAMPLING_FREQ), "-ac", "1",
             "-sample_fmt", "s16", dst],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[HATA] '{os.path.basename(src)}' dönüştürülemedi: {result.stderr.strip()[-300:]}")

def main():
    if not os.path.isdir(INPUT_DIR):
        print(f"[HATA] '{INPUT_DIR}' klasörü bulunamadı! İçine hizalanacak .wav dosyalarını ve"
              f" her biriyle aynı adı taşıyan .txt transkriptlerini koyun.")
        sys.exit(1)

    _convert_other_formats(INPUT_DIR)

    wav_paths = sorted(glob.glob(os.path.join(INPUT_DIR, "*.wav")))
    if not wav_paths:
        print(f"[HATA] '{INPUT_DIR}' klasöründe hiç .wav dosyası bulunamadı!")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    aligner = None  # ilk basarili dosyada bir kez yuklenir (model yukleme pahalidir)
    succeeded, failed = [], []

    for wav_path in wav_paths:
        base_name = os.path.splitext(os.path.basename(wav_path))[0]
        text_path = os.path.join(INPUT_DIR, base_name + ".txt")
        output_path = os.path.join(OUTPUT_DIR, base_name + ".TextGrid")

        if not os.path.exists(text_path):
            print(f"[ATLANDI] '{base_name}': eşleşen transkript '{base_name}.txt' bulunamadı.")
            failed.append((base_name, "transkript bulunamadı"))
            continue

        try:
            with open(text_path, "r", encoding="utf-8") as f:
                text_content = f.read().strip()

            if aligner is None:
                aligner = DynamicMMSAligner()

            print(f"\n[İŞLENİYOR] {base_name}")
            chars, syllables, words, duration = aligner.align(wav_path, text_content)
            export_to_textgrid(chars, syllables, words, text_content, duration, output_path=output_path)
            succeeded.append(base_name)
        except Exception as e:
            print(f"[HATA] '{base_name}' hizalanamadı: {e}")
            failed.append((base_name, str(e)))
            continue

    print("\n==========================================")
    print(f"Toplam: {len(wav_paths)}  Başarılı: {len(succeeded)}  Başarısız/atlandı: {len(failed)}")
    if failed:
        print("Başarısız/atlanan dosyalar:")
        for base_name, reason in failed:
            print(f"  - {base_name}: {reason}")
    print("==========================================")

if __name__ == "__main__":
    main()
