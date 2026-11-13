# Kabul edilmiş sabit bölgelerle extraction

`config/figure_regions.json`, sınır onayları ve `region_selection.json` üzerinden
oluşturuldu. 655'in son açık sınır onayı kaydedildi. 40 onaylı alternatiften
**37 tekil aktif şekil** seçildi. 625, 636, 645 için sırasıyla `P625-M01`,
`P636-M01`, `P645-M01` aktiftir. Diğer alternatifler yeniden işlenmez.

Onay kapsamı **yalnız region_boundary_only**. Şekil içi sıra veya anlam ilişkileri
insan tarafından doğrulanmış değildir. Bu ayrım hem config'te hem yeni kayıtlarda
saklanır: `boundary_review_status=human_verified`, içerik için
`human_review_status=not_reviewed`.

## Çalıştırma ve doğrulama

```powershell
.\.venv\Scripts\python.exe -B scripts/extract_corpus.py
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Temiz checkout'ta yalnız kaynak PDF, Git'teki manifest/config ve Python bağımlılığı
gerekir. Tarihsel audit örnekleri olmadan da 32 sayfa üretilir. Bu durumda eski
örneklerle karşılaştırma `sample_regression_status=not_available`,
`regression_passed=null` olarak raporlanır; yapılmamış kontrol başarı sayılmaz.
Kaynak hash'i, bölüm sınırları, blok sahipliği ve 655'in beş çift kontrolü çalışır.

Yerel geçiş yedekleri ve ilk çalıştırma kopyaları varsa ek kontrol:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_approved_corpus.py
```

Bu son komut bu çalışma sırasında oluşturulan, Git dışında tutulan
`audit/accepted_region_migration/` kanıtlarını gerektirir; temiz checkout için
zorunlu bir adım değildir. Deneme/onay materyali hazırlayan diğer betikler de
tarihsel inceleme araçlarıdır; üretim extraction bağımlılığı değildir.

Extraction sırasında görüntü/çizim tespiti yapılmaz. `figure_regions_path` ile
gösterilen sabit dosya okunur; kaynak PDF SHA-256 ve belge kimliği eşleşmezse durur.
Her aktif bölgenin onayı aynı kimlik/sayfa/Figure/bbox'ı kapsamalı. Çakışan bölgeler,
yinelenen şekiller, geçersiz koordinatlar ve footer'a giren bölgeler reddedilir.
Kısmi metin bloğu kesişiminde metin kırpılmaz veya atılmaz; gövdede tutulup uyarılır.
Eski `audit.figure_regions_by_page` yalnız tarihsel inceleme verisidir.

Mevcut çıktı dizini her çalıştırmada `audit/corpus_backups/<UTC>_<kimlik>/` altına
kopyalanır. Bu geçişin eski corpus'u ayrıca
`audit/accepted_region_migration/corpus_before/` altında saklanır. Eski beş
tek-sayfa audit dosyası ve hash'li baseline değiştirilmez.

Tek sayfa komutu da aynı sabit dosyayı kullanır. Bu geçişte eski örneklerin üzerine
yazmamak için `--output audit/accepted_region_migration/single_page_check` kullanıldı.
Sayfa JSON'u yalnız şekil referanslarını, `page_<n>.figures.json` ayrı kayıtları taşır.

## Tek içerik sahibi ve sonraki indeks

`audit/corpus/pages.jsonl`: gövde, ham metin, footer, `source_block_id`, metadata,
`block_ownership` ve `figure_refs`. Gömülü şekil metni yoktur.

`audit/corpus/figures.jsonl`: 37 `type=figure` kaydı:

- **36 inline kayıt:** şekil metni, altyazı ve kaynak koordinatlı bloklar burada;
  gövdeden çıkarılır. PDF blok sırası korunur, iç okuma sırası doğrulanmış değildir.
- **655 için bir referans kaydı:** `content_storage=page_body_reference`,
  `indexable=false`; `source_block_ids` ve `body_record_id` ile mevcut gövdeye
  bağlanır. `text` veya `blocks` alanlarında ikinci metin kopyası yoktur.
  Beş olay–neden çifti, on başlık ve altyazı gövdede kalır.

İleride indeks yalnız sayfa `text` alanlarını ve `indexable=true` şekil `text`
alanlarını kullanmalı. `raw_text`, footer, blok alanları ve referanslar ayrı metin
belgeleri olarak indekslenmemeli. Böylece 655 içeriği tekrar indekslenmez.
Bu adımda indeksleme veya chunking yapılmadı.

## Kontrol sonuçları

| Kontrol | Sonuç |
|---|---|
| Sayfa / aktif şekil | 32 / 37 |
| Kaynak blok muhasebesi | 670 = 245 gövde + 393 şekil + 32 footer; kayıp/tekrar yok |
| PDF ham metni | 32 sayfada kaynak ve eski çıktı ile aynı |
| 624, 625, 636, 645, 655 gövdeleri | Önceki örneklerle birebir aynı |
| 625, 636, 645 şekil içeriği | Aynı bbox, metin ve bloklar; yeni metadata kimlikleri dışında aynı |
| 655 | Beş çiftin metni/sırası ve ilk INCIDENT başlığı aynı; referans kaydı eklendi |
| 647 | `very / difficult` arasında şekil metni kalmıyor |
| 651 | Son liste maddesi eksiksiz; footer karışması yok |
| Gövdesi değişen 25 sayfa | Kalan gövde bloklarının göreli sırası korunuyor; Figure altyazıları gövdede kalmıyor |
| Tekrarlanabilirlik | Aynı girdilerle iki çalıştırmada pages.jsonl ve figures.jsonl byte düzeyinde aynı |

Değişen sayfalar: 626, 627, 628, 629, 630, 631, 633, 634, 635, 637, 638,
640, 641, 642, 643, 644, 646, 647, 648, 649, 650, 651, 652, 653, 654.

Bağımsız kontrol `audit/accepted_region_migration/verification.json` içinde kaynak
PDF bloklarıyla karşılaştırmayı, 13 cümle devamı kontrolünü, değişen sayfaların
blok sırasını ve iki çalıştırmanın SHA-256 değerlerini kaydeder. Byte karşılaştırması
metin/bölge kayıtları içindir; çalışma özetindeki zaman ve yedek yolu doğal olarak
değişir. Unit testler hash/onay/bbox uyuşmazlığını, çakışma ve tekrarları, birden
çok şekli, kısmi blok korumasını ve preserve_in_body referansını kapsar.

## Kalan sınırlar

- 651: aynı footer geometrisi uyarısı; 0,3593 pt taşan madde bütünüyle korunur.
- 655: tam genişlik uyarısı beklenir; mevcut beş çiftin sırası regresyonla korunur.
- Şekil içi okuma sırası, kutu ilişkileri ve grafik anlamı hâlâ doğrulanmamış.
  Özellikle 654'ün parçalı grafik etiketlerini bölge ayırmak düzeltmez.
- Kaynak satır sonları, tireli bölünmeler ve PDF'deki karakter sorunları korunur;
  normalizasyon yapılmadı. Otomatik blok/sıra kontrolleri tam içerik insan onayı
  değildir.

Geliştirme soruları, kanıtları, kaynak manifesti ve footer toleransı değiştirilmedi.
Commit ve push yapılmadı.
