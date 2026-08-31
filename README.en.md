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

## Project contents

```
mms_aligner/
├── mmsaligner.py          main program (batch forced alignment + TextGrid writing)
├── run.bat / .sh          easy launcher (Windows / Linux-macOS)
├── clean.bat / .sh        cleans output/ and __pycache__
├── run_tests.py           regression tests for the syllable engine
├── environment.yml        conda environment definition
├── config.json            VAD/gap/syllable settings (see config_ayarlari.txt)
├── syllable_rules.json    Turkish syllabification rules
├── test_cases.txt         expected-syllabification examples for run_tests.py
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

## Development

When changing the syllabification rules (`syllable_rules.json`) or the
syllable engine, a regression test suite lets you confirm previously
validated words still come out right:

```bash
python run_tests.py
```

To add a new test, add a `word -> syllable1,syllable2,...` line to
[test_cases.txt](test_cases.txt) (see the notation notes at the top of
that file).

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

## Citation

If you use this software, please cite it using the metadata in
[CITATION.cff](CITATION.cff). DOI:
[10.5281/zenodo.22164016](https://doi.org/10.5281/zenodo.22164016)
(this represents all versions and always resolves to the latest one).

## Development note

Anthropic's Claude Code was used to assist with code writing and
documentation during the development of this project.
