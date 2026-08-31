# mms_aligner — Türkçe İçin Çok Katmanlı Zaman Hizalı Transkripsiyon

*(GitHub deposu adı: **aligner4turkish**; proje/klasör adı olarak
kısaca **mms_aligner** kullanılır — bkz. [CITATION.cff](CITATION.cff).)*

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164016.svg)](https://doi.org/10.5281/zenodo.22164016)

[English README](README.en.md)

**Anahtar kelimeler:** forced alignment, speech processing, speech
recognition, speech-to-text, transcription, syllabification, wav2vec2,
MMS, ASR, phonetics, linguistics, Turkish, Turkish language, Praat,
TextGrid

Bir ses kaydını (wav) ve o kaydın doğru transkriptini (txt) alıp,
`facebook/mms-1b-fl102` (wav2vec2/CTC) modeliyle **gerçek forced
alignment** (zorlamalı hizalama) yapan; harf, hece ve kelime
seviyesinde zaman damgaları içeren bir Praat TextGrid dosyası üreten,
**toplu (batch)** çalışan bir komut satırı aracı.

## Öne çıkanlar

- **4 tier'li TextGrid çıktısı**: `segments` (harf), `syllables`
  (hece), `words` (kelime), `txt` (tüm transkript).
- **Toplu işleme**: `input/` klasöründeki her `wav+txt` çiftini tek
  seferde işler, `output/` klasörüne yazar; bir dosyada sorun olursa
  atlayıp devam eder, sonunda özet gösterir.
- **VAD tabanlı boşluk kararı**: sessizlik sınırları, CTC modelinin
  (isabetsiz olabilen) "blank" kararına değil, doğrudan ses enerjisine
  (basit bir VAD) dayanır.
- **Kural tabanlı Türkçe heceleme**: sonorluk hiyerarşisine ve akustik
  bir hakem mekanizmasına dayanan hece motoru; motorun kökeni ve
  ayrıntılı açıklaması için bkz.
  [ipa4turkish](https://github.com/akif-k/ipa4turkish)
  (Kılıç, M. A. <https://doi.org/10.5281/zenodo.22081832>).
- **Sıfır-genlik geçişine hizalanmış sınırlar**: tüm zaman damgaları en
  yakın gerçek dalga-formu geçişine (en fazla 10 ms sapmayla) taşınır.
- **Çoklu ses formatı desteği**: `input/`'a wav dışında (M4A, MP3, OGG,
  FLAC, WMA...) bir dosya konursa, sistemde ffmpeg kuruluysa otomatik
  olarak wav'a çevrilir; wav dosyaları için ffmpeg'e hiç gerek yoktur.
- Ek derleyici veya espeak-ng **gerekmez** (wav dosyaları doğrudan
  `soundfile` ile okunur).

## Hızlı başlangıç

```bash
conda env create -f environment.yml
conda activate mms_aligner

# input/ klasörüne kendi ses+transkript çiftlerinizi koyun
# (örnek olarak input/sample.wav + input/sample.txt zaten mevcut)

python mmsaligner.py        # ya da: ./run.sh  (Windows'ta run.bat)
```

Çıktı, `input/sample.wav` için `output/sample.TextGrid` olarak yazılır.

## Proje içeriği

```
mms_aligner/
├── mmsaligner.py          ana program (toplu forced alignment + TextGrid yazma)
├── run.bat / .sh          kolay başlatma (Windows / Linux-macOS)
├── clean.bat / .sh        output/ ve __pycache__ temizleme
├── run_tests.py           hece motoru regresyon testleri
├── environment.yml        conda ortamı tanımı
├── config.json            VAD/boşluk/hece ayarları (bkz. config_ayarlari.txt)
├── syllable_rules.json    Türkçe hece kuralları
├── test_cases.txt         run_tests.py için beklenen heceleme örnekleri
├── input/                 girdi: wav + eşleşen txt çiftleri (örnek dahil)
├── output/                çıktı: üretilen .TextGrid dosyaları
├── models/                indirilen model ağırlıkları (depoya dahil değil)
├── config_ayarlari.txt    config.json ayarları için ayrıntılı rehber
└── LICENSE, THIRD-PARTY-NOTICES.txt, CITATION.cff   lisans ve atıf
```

## Belgeler

Bu README bir özet niteliğindedir; ayrıntılı (Türkçe) belgeler:

| Dosya | İçerik |
|---|---|
| [config_ayarlari.txt](config_ayarlari.txt) | `config.json` ayarları için pratik, sorun-giderme odaklı rehber |
| [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) | Kullanılan algoritma/model/paketlerin lisans bilgileri (**model lisansı için mutlaka okuyun**) |

## Geliştirme

Hece kurallarında (`syllable_rules.json`) veya hece motorunda değişiklik
yaparken, önceden doğrulanmış kelimelerin bozulmadığından emin olmak
için bir regresyon test seti bulunur:

```bash
python run_tests.py
```

Yeni bir test eklemek için [test_cases.txt](test_cases.txt) dosyasına
`kelime -> hece1,hece2,...` biçiminde bir satır ekleyin (dosyanın
başındaki notasyon açıklamasına bakın).

## Lisans

Bu projenin kendi kodu **GNU GPLv3** ile lisanslanmıştır (bkz.
[LICENSE](LICENSE)) — kullanabilir, değiştirebilir ve dağıtabilirsiniz,
ancak türev çalışmaların da açık kaynak (GPLv3) kalması ve bu projeye
atıf yapılması gerekir.

Kullanılan varsayılan model (`facebook/mms-1b-fl102`) **CC-BY-NC 4.0**
lisanslıdır ve **ticari kullanıma kapalıdır** — bu, projenin kendi
lisansından bağımsız bir kısıtlamadır. Zorlamalı hizalama algoritmasının
genel yaklaşımı [MahmoudAshraf97/ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner)
(BSD Lisansı) projesinden esinlenmiştir (kod veya paket olarak
kullanılmamıştır, bağımsız yazılmıştır). Ayrıntılar için
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) dosyasına bakın.

## Sürüm Notları

- **v1.0.2** — README'ye bu Sürüm Notları bölümü eklendi.
- **v1.0.1** — Belge düzeltmeleri: ctc-forced-aligner atıf ifadesi
  düzeltildi (algoritma o projeden "port edilmedi", sadece genel
  yaklaşımından esinlenildi); README'lere DOI rozeti ve anahtar
  kelimeler eklendi; CITATION.cff güncellendi.
- **v1.0.0** — İlk sürüm: `facebook/mms-1b-fl102` modeliyle Türkçe
  zorlamalı hizalama; harf/hece/kelime/tam metin katmanlı Praat
  TextGrid çıktısı üretir.

Tüm sürümler için bkz.
[GitHub Releases](https://github.com/akif-k/aligner4turkish/releases).

## Atıf

Bu yazılımı kullanıyorsanız lütfen [CITATION.cff](CITATION.cff)
dosyasındaki bilgilerle atıfta bulunun. DOI:
[10.5281/zenodo.22164016](https://doi.org/10.5281/zenodo.22164016)
(bu, tüm sürümleri temsil eder ve her zaman en son sürüme yönlenir).

## Gelistirme Notu

Bu projenin gelistirilmesinde, kod yazimi ve dokumantasyon calismalarina
destek olarak Anthropic'in Claude Code araci kullanilmistir.
