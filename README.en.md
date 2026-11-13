# mms_aligner — Multi-Tier Time-Aligned Transcription for Turkish

*(GitHub repository name: **aligner4turkish**; the project/folder is
referred to as **mms_aligner** for short — see [CITATION.cff](CITATION.cff).)*

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164016.svg)](https://doi.org/10.5281/zenodo.22164016)

[Türkçe README](README.md)

**Keywords:** forced alignment, speech processing, speech recognition,
speech-to-text, transcription, syllabification, wav2vec2, MMS, ASR,
phonetics, linguistics, Turkish, Turkish language, Praat, TextGrid

A batch command-line tool that takes an audio recording (wav) and its
correct transcript (txt), performs **real forced alignment** with the
`facebook/mms-1b-fl102` (wav2vec2/CTC) model, and produces a Praat
TextGrid file with character-, syllable-, and word-level timestamps.

## Highlights

- **4-tier TextGrid output**: `segments` (letters), `syllables`,
  `words`, `txt` (full transcript).
- **Batch processing**: processes every `wav+txt` pair in `input/` in
  one run and writes to `output/`; a problem in one file is skipped
  (with the run continuing) and reported in a summary at the end.
- **VAD-informed gap decisions**: silence boundaries are decided from
  the raw audio energy (a simple VAD) rather than the CTC model's own
  (sometimes inaccurate) "blank" prediction.
- **Rule-based Turkish syllabification**: a syllable engine built on a
  sonority hierarchy and an acoustic arbiter mechanism; for the origin
  and a detailed explanation of the same approach, see
  [ipa4turkish](https://github.com/akif-k/ipa4turkish)
  (Kılıç, M. A. <https://doi.org/10.5281/zenodo.22081832>).
- **Zero-crossing-aligned boundaries**: every timestamp is snapped to
  the nearest true waveform zero-crossing (up to 10 ms deviation).
- **Multi-format audio support**: dropping a non-wav file (M4A, MP3,
  OGG, FLAC, WMA, ...) into `input/` auto-converts it to wav if ffmpeg
  is installed; wav files themselves never need ffmpeg.
- **No extra compiler or espeak-ng required** (wav audio is read
  directly with `soundfile`).

## Quick start

```bash
conda env create -f environment.yml
conda activate mms_aligner

# Put your own audio+transcript pairs into input/
# (input/sample.wav + input/sample.txt is included as an example)

python mmsaligner.py        # or: ./run.sh  (run.bat on Windows)
```

Output for `input/sample.wav` is written to `output/sample.TextGrid`.

## Model and offline use

On the first run, the `facebook/mms-1b-fl102` model (~4 GB) is
downloaded from the Hugging Face Hub into the project's `models/`
folder. On later runs the model and the Turkish language adapter are
loaded straight from `models/` **without any network access**; if a
file is missing, the program notices and downloads it.

You can copy the `models/` folder as-is to another computer (e.g. one
without internet access) and use the model there without downloading
it again.

## Project contents

```
mms_aligner/
├── mmsaligner.py          main program (batch forced alignment + TextGrid writing)
├── run.bat / .sh          easy launcher (Windows / Linux-macOS)
├── environment.yml        conda environment definition
├── config.json            VAD/gap/syllable settings (see config_ayarlari.txt)
├── syllable_rules.json    Turkish syllabification rules
├── input/                 input: wav + matching txt pairs (sample included)
├── output/                output: generated .TextGrid files
├── models/                downloaded model weights (not included in the repo)
├── config_ayarlari.txt    detailed guide to config.json settings (Turkish)
└── LICENSE, THIRD-PARTY-NOTICES.txt, CITATION.cff   license and citation
```

## Documentation

This README is a summary; the detailed docs are in Turkish:

| File | Contents |
|---|---|
| [config_ayarlari.txt](config_ayarlari.txt) | Practical, troubleshooting-oriented guide to `config.json` settings |
| [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) | License/attribution info for the algorithm, model, and packages used (**read this for the model's license**) |

## Troubleshooting

### Characters missing from the model's vocabulary

If the transcript contains characters that have no entry in the model's
vocabulary (e.g. `&`, `€`, emoji, letters from other scripts, invisible
characters such as a zero-width space), that file is skipped without
aligning and the offending characters are listed in the terminal along
with where they occur in the transcript (the program's messages are in
Turkish):

```
[ATLANDI] 'sample': transkriptte model sözlüğünde olmayan karakter(ler) var: '&' (U+0026 AMPERSAND)
  - Transkript: sample.txt
  - '&' (U+0026 AMPERSAND): 1 kez; konum: satır 1 sütun 12; kelimeler: &
```

For each character it shows the Unicode code point and name, how many
times it occurs (`kez`), its line (`satır`) and column (`sütun`), and
which words contain it (`kelimeler`); invisible characters are shown as
`(görünmez)` with their `U+XXXX` code.

To fix it, delete these characters from the transcript or write out
how they are read (e.g. `&` → `ve`). Digits, `%` and `/` are in the model's
vocabulary, but writing numbers out in words usually aligns better with
how they are pronounced.

### Transcripts that are not UTF-8

Transcripts must be saved as UTF-8 (UTF-8 with a BOM is fine too). If a
file was saved in another encoding (e.g. "ANSI"/Windows-1254 on
Windows), it is skipped and the line/column and value of the byte that
could not be decoded are printed. Re-save the file as UTF-8 in a text
editor.

### Missing-part warning

If part of what is spoken is missing from the transcript, the program
does not fail (the TextGrid is still written), but the timings around
that part come out wrong. To help you spot this, two checks run and, if
something looks off, a `[UYARI]` (warning) is printed to the terminal
and written to `mmsaligner.log`:

```
[UYARI] 'kayit': normalden belirgin şekilde uzun hizalanmış kelime(ler) var; transkriptte bu kelimelerin çevresinde eksik bir bölüm olabilir (Praat'ta kontrol edin)
  - "kopmuş": 2.121–3.141 sn arası (konuşma 1.02 sn; bu dosyanın hızına göre beklenen ~0.45 sn, 2.3 kat)
[UYARI] 'kayit': kaydın sonunda transkriptte olmayan konuşma olabilir
  - 5.020–6.002 sn arası etiketsiz bırakıldı, ama bu aralığın 0.61 sn'si sesli (vad_db_threshold'un üstünde)
```

- **Missing part in the middle:** untranscribed speech gets spread over
  the neighbouring words, so they look abnormally long relative to the
  file's own speaking rate (`long_word_warning_factor`).
- **Missing part at the start/end:** a warning is given if the unlabeled
  interval at the start/end of the recording contains speech energy
  (`edge_speech_warning_ms`).

These warnings are hints, not proof: a single missing short word is
usually not caught, and speakers who drag words out or noisy recordings
can trigger false warnings. See [config_ayarlari.txt](config_ayarlari.txt)
(Turkish) for the thresholds and how to turn them off.

### Long audio warning

If an audio file is longer than 10 minutes, a `[UYARI]` (warning) is
printed before alignment starts (the file is still processed). The
memory needed for alignment grows roughly with the square of the
duration; very long recordings can need several GB of memory, and a
drift at one point can carry over to the rest. Splitting recordings
(and transcripts) into 5–10 minute parts is recommended. The threshold
is set by `long_audio_warning_sec` (0 = off).

### Log file

Whenever a file is skipped, fails or gets a warning, the details are also written to
`mmsaligner.log` in the project folder, in addition to the terminal
(including the Python traceback for unexpected errors). The file is
deleted at the start of every run and only recreated when something
went wrong, so if it exists it always belongs to the latest run.

### Other issues

- **`ModuleNotFoundError: torch/torchaudio/transformers/soundfile`:**
  make sure the `mms_aligner` conda environment is active
  (`conda activate mms_aligner`).
- **HTTPS/SSL error while downloading the model (Windows, git-bash):**
  in some conda installs, `%CONDA_PREFIX%\etc\conda\activate.d\openssl_activate.sh`
  points `SSL_CERT_FILE` to the non-existent
  `${CONDA_PREFIX}/ssl/cacert.pem`; change that line to
  `${CONDA_PREFIX}/Library/ssl/cacert.pem`.
- **Garbled Turkish characters in the Windows console (e.g. `SE??M`):**
  this only comes from the console code page; TextGrid files always
  contain correct UTF-8. To fix the screen output, run `chcp 65001`
  before starting the program.
- **Another language:** the default language is Turkish
  (`lang_code="tur"`). For another language, change the
  `DynamicMMSAligner()` call in `main()` in `mmsaligner.py` to the
  corresponding ISO 639-3 code (e.g. `DynamicMMSAligner(lang_code="eng")`).
  The syllable tier still follows Turkish rules.

## License

This project's own code is licensed under **GNU GPLv3** (see
[LICENSE](LICENSE)) — you may use, modify, and redistribute it, but
derivative works must also stay open source (GPLv3) and must credit
this project.

The default model used (`facebook/mms-1b-fl102`) is licensed
**CC-BY-NC 4.0** and is **not licensed for commercial use** — this
restriction is independent of this project's own license. The general
approach of the forced alignment algorithm was inspired by
[MahmoudAshraf97/ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner)
(BSD License), though no code or package from that project is used —
it was written independently. See
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) for details.

## Release Notes

- **v1.0.4** — Offline use: the model and the Turkish language
  adapter are loaded without network access when they are complete in
  `models/`; missing files are downloaded. Added a "Model and offline
  use" section and more troubleshooting notes to the README; fixed the
  sample transcript (`input/sample.txt`).
- **v1.0.3** — Error-reporting improvements: characters missing from
  the model's vocabulary (including invisible ones) are now shown in
  the terminal with their Unicode name and their line/column position
  in the transcript, and the file is skipped with a clear message
  instead of an obscure error; for transcripts that are not UTF-8, the
  value and position of the byte that could not be decoded are
  reported; details of skipped/failed files are written to
  `mmsaligner.log` in the project folder. UTF-8 transcripts with a BOM
  (Windows Notepad) are now read correctly; a crash when printing
  certain characters (e.g. `€`, emoji) to the Windows console was
  fixed. Developer-only files (`clean.*`, `run_tests.py`,
  `test_cases.txt`) were removed from the repository. Added warnings
  that the transcript may be missing a part (abnormally long words, and
  speech left unlabeled at the start/end of the recording; settings
  `long_word_warning_factor`, `edge_speech_warning_ms`). Added a
  warning before alignment for audio files longer than 10 minutes
  (setting `long_audio_warning_sec`).
- **v1.0.2** — Added a Release Notes section to the README.
- **v1.0.1** — Documentation fixes: corrected the wording of the
  ctc-forced-aligner attribution (the algorithm was not "ported" from
  that project, only inspired by its general approach); added a DOI
  badge and keywords to the READMEs; updated CITATION.cff.
- **v1.0.0** — Initial release: Turkish forced alignment with the
  `facebook/mms-1b-fl102` model; produces a Praat TextGrid with
  letter/syllable/word/full-text tiers.

For all releases, see
[GitHub Releases](https://github.com/akif-k/aligner4turkish/releases).

## Citation

If you use this software, please cite it using the metadata in
[CITATION.cff](CITATION.cff). DOI:
[10.5281/zenodo.22164016](https://doi.org/10.5281/zenodo.22164016)
(this represents all versions and always resolves to the latest one).

## Development note

Anthropic's Claude Code was used to assist with code writing and
documentation during the development of this project.
