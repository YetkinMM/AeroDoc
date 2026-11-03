# AeroDoc: ilk sayfa extraction kontrolü

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
