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

## Model ve çevrimdışı kullanım

İlk çalıştırmada `facebook/mms-1b-fl102` modeli (~4 GB) Hugging Face
Hub'dan indirilip proje içindeki `models/` klasörüne kaydedilir.
Sonraki çalıştırmalarda model ve Türkçe dil adaptörü **internete hiç
bağlanılmadan** doğrudan `models/` klasöründen yüklenir; bir dosya
eksikse program bunu fark edip eksik kısmı internetten indirir.

`models/` klasörünü olduğu gibi başka bir bilgisayara (ör. internet
erişimi olmayan bir makineye) kopyalayarak modeli yeniden indirmeden
kullanabilirsiniz.

## Proje içeriği

```
mms_aligner/
├── mmsaligner.py          ana program (toplu forced alignment + TextGrid yazma)
├── run.bat / .sh          kolay başlatma (Windows / Linux-macOS)
├── environment.yml        conda ortamı tanımı
├── config.json            VAD/boşluk/hece ayarları (bkz. config_ayarlari.txt)
├── syllable_rules.json    Türkçe hece kuralları
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

## Sorun giderme

### Sözlükte olmayan karakterler

Transkriptte modelin sözlüğünde karşılığı olmayan karakterler varsa
(ör. `&`, `€`, emoji, başka alfabelerin harfleri, sıfır genişlikli boşluk
gibi görünmeyen karakterler), o dosya hizalanmadan atlanır ve terminalde
sorunlu karakterler, transkriptteki konumlarıyla birlikte listelenir:

```
[ATLANDI] 'sample': transkriptte model sözlüğünde olmayan karakter(ler) var: '&' (U+0026 AMPERSAND)
  - Transkript: sample.txt
  - '&' (U+0026 AMPERSAND): 1 kez; konum: satır 1 sütun 12; kelimeler: &
```

Her karakter için Unicode kod noktası ve adı, kaç kez geçtiği, hangi
satır ve sütunda bulunduğu ve hangi kelimelerde geçtiği gösterilir
(görünmeyen karakterler `(görünmez)` ve `U+XXXX` koduyla yazılır).

Çözüm için bu karakterleri transkriptten silin ya da okunuşlarıyla
yazın (ör. `&` → `ve`). Rakamlar, `%` ve `/` modelin sözlüğünde bulunur,
ancak okunuşa göre hizalama için sayıları yazıyla yazmak genellikle
daha iyi sonuç verir.

### UTF-8 olmayan transkriptler

Transkriptler UTF-8 olarak kaydedilmelidir (BOM'lu UTF-8 de olur).
Dosya başka bir kodlamayla (ör. Windows'taki "ANSI"/Windows-1254)
kaydedilmişse, dosya atlanır ve çözülemeyen baytın satır/sütun konumu
ile değeri yazdırılır. Dosyayı metin düzenleyicide açıp UTF-8 olarak
kaydetmeniz yeterlidir.

### Metinde eksik bölüm uyarısı

Transkriptte seste konuşulan bir bölüm eksikse program hata vermez
(TextGrid yine oluşturulur), ama o bölümün çevresindeki zamanlamalar
yanlış çıkar. Bunu fark etmeniz için iki kontrol yapılır ve sorun
görülürse terminale ve `mmsaligner.log` dosyasına `[UYARI]` yazılır:

```
[UYARI] 'kayit': normalden belirgin şekilde uzun hizalanmış kelime(ler) var; transkriptte bu kelimelerin çevresinde eksik bir bölüm olabilir (Praat'ta kontrol edin)
  - "kopmuş": 2.121–3.141 sn arası (konuşma 1.02 sn; bu dosyanın hızına göre beklenen ~0.45 sn, 2.3 kat)
[UYARI] 'kayit': kaydın sonunda transkriptte olmayan konuşma olabilir
  - 5.020–6.002 sn arası etiketsiz bırakıldı, ama bu aralığın 0.61 sn'si sesli (vad_db_threshold'un üstünde)
```

- **Ortada eksik bölüm:** Metinde olmayan konuşma komşu kelimelere
  yayıldığı için o kelimeler, dosyanın kendi konuşma hızına göre
  anormal uzun görünür (`long_word_warning_factor`).
- **Başta/sonda eksik bölüm:** Kaydın başındaki/sonundaki etiketsiz
  aralıkta konuşma enerjisi varsa uyarı verilir (`edge_speech_warning_ms`).

Bu uyarılar bir ipucudur, kesin tespit değildir: tek bir kısa kelimenin
eksikliği genellikle yakalanamaz; kelimeleri çok uzatarak okuyan
konuşmacılarda ya da gürültülü kayıtlarda yanlış uyarı görülebilir.
Eşikler ve kapatma için bkz. [config_ayarlari.txt](config_ayarlari.txt).

### Uzun ses dosyası uyarısı

Ses dosyası 10 dakikadan uzunsa, hizalama başlamadan önce `[UYARI]`
yazılır (dosya yine işlenir). Hizalamanın bellek ihtiyacı kabaca
sürenin karesiyle büyür; çok uzun kayıtlar birkaç GB bellek isteyebilir
ve bir yerdeki kayma sonrasına yayılabilir. Kayıtları (ve transkriptleri)
5–10 dakikalık parçalara bölmeniz önerilir. Eşik `long_audio_warning_sec`
ile değiştirilebilir (0 = kapalı).

### Log dosyası

Bir dosya atlandığında, hata verdiğinde ya da uyarı aldığında, ayrıntılar terminale ek
olarak proje klasöründeki `mmsaligner.log` dosyasına da yazılır
(beklenmeyen hatalar için Python hata dökümü dahil). Bu dosya her
çalıştırmanın başında silinir ve yalnızca sorun olduğunda yeniden
oluşturulur; yani varsa, her zaman son çalıştırmaya aittir.

### Diğer sorunlar

- **`ModuleNotFoundError: torch/torchaudio/transformers/soundfile`:**
  `mms_aligner` conda ortamının etkin olduğundan emin olun
  (`conda activate mms_aligner`).
- **Model indirirken HTTPS/SSL hatası (Windows, git-bash):** Bazı conda
  kurulumlarında `%CONDA_PREFIX%\etc\conda\activate.d\openssl_activate.sh`
  dosyası `SSL_CERT_FILE` değişkenini var olmayan
  `${CONDA_PREFIX}/ssl/cacert.pem` yoluna yönlendirir; bu satırı
  `${CONDA_PREFIX}/Library/ssl/cacert.pem` olarak düzeltin.
- **Windows konsolunda Türkçe karakterler bozuk görünüyor (ör. `SE??M`):**
  Bu yalnızca konsolun kod sayfasından kaynaklanır, TextGrid dosyaları
  her zaman doğru UTF-8 içerir. Ekran çıktısını düzeltmek için
  çalıştırmadan önce `chcp 65001` komutunu verin.
- **Başka bir dil:** Varsayılan dil Türkçedir (`lang_code="tur"`).
  Başka bir dil için `mmsaligner.py` içindeki `main()` fonksiyonunda
  `DynamicMMSAligner()` çağrısını ilgili ISO 639-3 koduyla değiştirin
  (ör. `DynamicMMSAligner(lang_code="eng")`). Hece katmanı Türkçe
  kurallarına göre çalışır.

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

- **v1.0.4** — Çevrimdışı kullanım: model ve Türkçe dil adaptörü
  `models/` klasöründe eksiksiz varsa internete bağlanılmadan
  yükleniyor; bir dosya eksikse internetten indiriliyor. README'ye
  "Model ve çevrimdışı kullanım" bölümü ve ek sorun giderme notları
  eklendi; örnek transkript (`input/sample.txt`) düzeltildi.
- **v1.0.3** — Hata raporlama iyileştirmeleri: model sözlüğünde
  olmayan karakterler (görünmeyenler dahil) artık terminalde Unicode
  adı ve transkriptteki satır/sütun konumuyla gösteriliyor ve dosya
  anlaşılmaz bir hata yerine açık bir mesajla atlanıyor; UTF-8 olmayan
  transkriptlerde çözülemeyen baytın değeri ve konumu bildiriliyor;
  atlanan/hatalı dosyaların ayrıntıları proje klasöründeki
  `mmsaligner.log` dosyasına yazılıyor. BOM'lu UTF-8 transkriptler
  (Windows Not Defteri) artık sorunsuz okunuyor; Windows konsolunda
  bazı karakterler (ör. `€`, emoji) yazdırılırken programın çökmesi
  önlendi. Geliştirici dosyaları (`clean.*`, `run_tests.py`,
  `test_cases.txt`) depodan çıkarıldı. Transkriptte eksik bölüm
  olabileceğini gösteren uyarılar eklendi (anormal uzun kelimeler ve
  kaydın başında/sonunda etiketsiz kalan konuşma; ayarlar
  `long_word_warning_factor`, `edge_speech_warning_ms`). 10 dakikadan
  uzun ses dosyaları için hizalama öncesinde uyarı eklendi (ayar
  `long_audio_warning_sec`).
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
