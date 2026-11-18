# AeroDoc: toplu extraction

Minimum normalizasyon ve chunking artık ayrı bir komutla kullanılabilir:
`.\.venv\Scripts\python.exe -B scripts/build_chunks.py`.
Bağımlılık/tokenizer kurulumu, kaynak izleme ve doğrulama için
[chunking kullanım belgesine](docs/chunking.md) bakın. Bu komut extraction
çıktılarını değiştirmez; embedding veya retrieval çalıştırmaz.

## Güncel kullanım

```powershell
.\.venv\Scripts\python.exe scripts/extract_corpus.py
```

PDF hash'i, manifest metadata'sı, sayfa sayısı ve bölüm sınırları doğrulandıktan
sonra config'teki 32 sayfa çıkarılır. Normalizasyon, chunking ve retrieval bu
aşamada uygulanmaz. Geliştirme soruları ve kaynak manifesti değiştirilmez.

Temiz checkout'ta eski `audit/` dosyaları gerekmez: kaynak PDF'yi manifestteki
hash ile sağlayıp ortamı kurmak yeterlidir. Eski beş audit örneği yoksa örnek
regresyonu `not_available` olarak raporlanır; yapılmamış karşılaştırma başarılı
sayılmaz. Kaynak/sınır doğrulamaları ve blok muhasebesi yine çalışır.

Extraction artık yalnız `config/figure_regions.json` içindeki **37 kabul edilmiş
sabit bölgeyi** kullanır; canlı şekil tespiti yapmaz. Bölge dosyasının PDF hash'i
eşleşmezse durur. 625, 636 ve 645'te manuel sınırlar aktiftir; aynı şeklin
alternatifleri tekrar işlenmez. Onay yalnız `region_boundary_only` kapsamındadır.

Güncel uygulama ve doğrulama: [sabit bölge extraction raporu](docs/approved_region_extraction.md).

Çıktılar Git dışında, `audit/corpus/` altında tutulur:

- `pages.jsonl`: ham metin, sıralanmış gövde, blok koordinatları, footer blokları,
  kaynak/config hash'leri, sürümler ve ayrı otomatik/insan inceleme durumları.
- `figures.jsonl`: 37 ayrı `type=figure` kaydı. 36'sının metni/blokları burada
  bulunur; sayfalarda yalnız `figure_refs` vardır. 655'in kaydı gövde bloklarına
  referans verir, metni ikinci kez kopyalamaz ve `indexable=false` taşır.
- `review_report.json` ve `review_report.md`: sayfa bazında inceleme gerekçeleri.
- `run_summary.json`: sınır kontrolleri, beş örneğin karşılaştırmaları ve 655'in
  beş olay–neden çiftinin tam metni ve sıra kontrolü.
- `baseline/`: beş eski örneğin JSON/TXT/ham TXT/PNG dosyalarının hash'li kopyası;
  sonraki çalıştırmalarda değiştirilmez.

Her toplu çalıştırma önceki çıktı dizinini `audit/corpus_backups/` altına yedekler.
Bu geçişten önceki corpus ayrıca `audit/accepted_region_migration/corpus_before/`
altında korundu. İndeks için yalnız sayfa `text` alanı ve `indexable=true` olan
şekil `text` alanı kullanılmalı; ham metin, bloklar, footer ve referanslar ayrı
metin belgeleri olarak indekslenmemeli.

Uyarısız sayfalar dahil tüm yeni kayıtlar `human_review_status=not_reviewed`
olarak kalır. Şekillerin iç okuma sırası henüz doğrulanmadı. Kaynak uyuşmazlığında
çıkarım başlamaz. Örnek regresyonunda rapor yazılır ve komut başarısız çıkış
koduyla sonlanır; downstream kullanımdan önce farkları incele.

Tek sayfa komutu config'teki `audit.pdf_page` sayfasını çıkarır. Önceki çıktıları
değiştirmeden çalıştırmak ve doğrulama testlerini yürütmek için:

```powershell
.\.venv\Scripts\python.exe scripts/audit_first_page.py --output audit/corpus/single_page_check
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

`--output` verilmezse tek sayfa komutu önceki gibi `audit/` altına yazar.
Ortak extraction kodu `scripts/extraction.py` içindedir. Sonraki adım inceleme,
ayrı normalizasyon ve kaynak sayfa/blok referanslarını koruyan chunking'dir.
İnsan tarafından doğrulanmış 10 geliştirme sorusu baseline için hazırdır.

## İlk kurulum ve önceki tek sayfa denetimi

Aşağıdaki notlar ilk denetim aşamasını anlatır; güncel toplu kullanım yukarıdadır.

Bu küçük başlangıç paketi sadece bölüm sınırlarını kontrol eder ve PDF'nin
624. sayfasının metnini çıkarır. Otomatik 32 sayfa extraction, chunking,
embedding, FAISS veya LLM henüz eklenmedi.

## 1. Klasörü aç ve PDF'yi yerleştir

Paketi bir klasöre çıkar. VS Code'da bu klasörü aç.
Orijinal PDF'yi `data/raw/amtg_handbook.pdf` olarak koy.

Resmî kaynak:
https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/amtg_handbook.pdf

PDF pakete dahil değildir. Büyük PDF `.gitignore` ile Git dışında tutulur.
`data/raw/manifest.json` Git'e eklenebilir.

## 2. Python ortamını kur

Python 3.11 veya üstü kullan. Windows / PowerShell'de klasörün kökünde:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/audit_first_page.py
```

`python` bulunmazsa ilk komutta `py -3 -m venv .venv` kullan.
Aktivasyon gerekmez; komutlar sanal ortamın Python'unu doğrudan çağırır.

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/audit_first_page.py
```

## 3. Çıktıyı kontrol et

Beklenen sınırlar:

| PDF sırası (1 tabanlı) | Sayfadan okunan basılı etiket |
| --- | --- |
| 623 | Görünür altbilgi etiketi yok: null |
| 624 | 14-1 |
| 655 | 14-32 |
| 656 | G-1 |

`623` önceki bölümün ethics metniyle biter. Bu sayfada PDF label metadata'sı
13-8'i işaret etse de görünür basılı altbilgi yoktur; basılı etiket null
tutulur. `624` ayrıca Chapter 14 / Human Factors başlığını, `656` Glossary başlığını
içermeli. Etiketler `get_text()` çıktısının ilk veya son satırından tahmin
edilmez; sayfanın alt 54 PDF point'lik bölgesinden okunur.

Üretilen dosyalar:

| Dosya | Amaç |
| --- | --- |
| `data/raw/manifest.json` | Gerçek SHA-256, gerçek sayfa sayısı ve kaynak URL |
| `audit/boundary_check.json` | Dört sınır kontrolünün sonuçları |
| `audit/page_624.raw.txt` | PyMuPDF'nin ham metni |
| `audit/page_624.txt` | Sol sütun, ardından sağ sütun sırasındaki aday metin |
| `audit/page_624.json` | Metin, sayfa metadata'sı, blok koordinatları ve uyarılar |
| `audit/page_624.png` | Karşılaştırma için orijinal sayfanın görünümü |

Şu sırayı gözünle doğrula:

1. Chapter 14 → Human Factors → Introduction → FAA Involvement.
2. Sol sütunun sonuna kadar ilerle; Human error paragrafına erken atlamamalı.
3. Sol sütunun sonunda "usually result in human error ..." cümlesi bulunur.
4. Sonra sağ sütundaki "Human error is the unintentional act ..." paragrafı gelir.
5. Omission, Commission ve Extraneous maddelerinin üçü de korunmalı.

Kaynak metnin satır sonları ve madde işaretleri bu aşamada agresif biçimde
temizlenmez. `review_status` alanı her yeniden çalıştırmada
`needs_manual_review` olur; script kendi çıktısını doğrulanmış ilan etmez.

## Bu yaklaşımın sınırı

624. sayfa için metin bloklarını sol ve sağ sütuna ayırmak uygun bir ilk
adaydır. Başlık korunur, altbilgi gövde metninden ayrılır. Bu kuralı diğer
31 sayfada çalışır kabul etme: tam genişlikte şekil, kutu, tablo ve farklı
okuma sıraları için ek inceleme gerekir. Sütun sınırını geçen bloklar
uyarı üretir. Tekrarlayan başlıkları kitap genelinde kaldırma işi henüz
yapılmadı. Metin düzeni görüntüyle karşılaştırılarak kontrol edilmelidir.

Bir manifest zaten varsa ve PDF hash'i değişmişse script durur. Dosyanın
baskısını/kaynağını incele; eski hash'i sessizce değiştirme. Corpus kapsamı
veya extraction yöntemi değişince ilgili sürümü de kaydet.

## Sonraki küçük adım

Önce bu tek sayfanın sırasını birlikte kontrol et. Ardından farklı düzenleri
temsil eden toplam 5 örnek sayfa seç ve 32 sayfalık bölüme geçişi hazırla.
10 development sorusu ve ayrı test kümesi daha sonra hazırlanacak.

Teknik kaynaklar:
- https://pymupdf.readthedocs.io/en/latest/page.html
- https://pymupdf.readthedocs.io/en/latest/recipes-text.html

## Kaynaklı yanıt ve yerel API

Kök `.env` dosyasına `.env.example` şablonundaki `OPENAI_API_KEY` değerini
ekle. Mevcut chunk ve retrieval index çıktıları kurulumdan önce hazır olmalı.
Eksikse [chunking](docs/chunking.md) ve [retrieval](docs/retrieval.md) adımlarını kullan.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-answers.txt
.\.venv\Scripts\python.exe -m scripts.ask --probe
.\.venv\Scripts\python.exe -m scripts.ask "What is the difference between omission, commission, and extraneous errors?"
.\.venv\Scripts\python.exe -m scripts.ask_api
```

Sunucu yalnızca `127.0.0.1:8000` adresini dinler. Tarayıcıda
[Swagger UI](http://127.0.0.1:8000/docs) sayfasını aç, `POST /ask` için
**Try it out** seç ve `{"question":"What are the three types of human error?"}`
gönder. Soru en fazla 2.000 karakter olabilir. `GET /health` ücretli çağrı yapmaz.
Terminalde BGE seçmek için `--retrieval bge` kullanabilirsin. Varsayılan BM25 ve
`k=5` ayarları [config/answers.json](config/answers.json) dosyasındadır.

Sunucu çalışırken mevcut on soruyu birer kez HTTP üzerinden çalıştırmak ve
insan incelemesi için JSON raporunu üretmek için aşağıdaki ilk komutu kullan.
İkinci komut mock provider ile yerel testleri çalıştırır.

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_answers
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

[Yanıt üretimi belgesi](docs/answers.md) model seçimini, maliyet hesabını,
çıktı durumlarını ve development raporunun kapsamını açıklar.
