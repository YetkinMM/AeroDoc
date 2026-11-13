# Minimum normalizasyon ve kaynak izli chunking

Extraction'dan ayrı bir adımdır. `pages.jsonl`, `figures.jsonl`, onaylı bölge
config'i ve kaynak PDF salt okunur girdilerdir. Embedding veya retrieval çalışmaz.
Geliştirme soruları/cevap anahtarı okunarak chunk sınırı ayarlanmaz.

## Kullanım

Windows / PowerShell, proje kökünde:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-chunking.lock.txt
.\.venv\Scripts\python.exe -B scripts/fetch_chunk_tokenizer.py
.\.venv\Scripts\python.exe -B scripts/build_chunks.py
.\.venv\Scripts\python.exe -B scripts/build_chunks.py --output audit/chunking_repeat
.\.venv\Scripts\python.exe -B scripts/verify_chunks.py
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Doğrudan bağımlılıklar `requirements-chunking.txt`, bu çalışmada kullanılan tüm
çözülmüş sürümler `requirements-chunking.lock.txt` içinde. İlgili sürümler:
PyMuPDF 1.26.6, tokenizers 0.22.1, huggingface-hub 0.36.0; Python 3.13.2.
Model ağırlığı indirilmez. Fetch komutu yalnız checksum doğrulamalı dört küçük
tokenizer/config dosyasını `audit/tokenizers/` altında tutar; chunking ağ istemez.

`verify_chunks.py` bu çalışmanın `audit/chunking/extraction_input_snapshot.json`
koruma kaydını da kullanır. Bu kayıt Git dışında olduğundan temiz checkout'ta
önce yalnız chunking ve unit testler çalıştırılabilir; koruma kaydı yerel inceleme
kanıtıdır. İki çıktının byte eşitliği ayrıca doğrudan karşılaştırılabilir.

## Tokenizer ve nihai metin bütçesi

Model/tokenizer:
[BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5/tree/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a),
revision **`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`**.

Kendi `tokenizer.json` dosyası Hugging Face Tokenizers ile yüklenir. Modelin Bert
post-processor'ı `[CLS]` ve `[SEP]` ekler; ikisi de `token_count` içindedir.
Truncation ve padding kapalıdır. 499 adet tek-token `word` girdisinin 501 token
olduğu ve sessizce kesilmediği gerçek tokenizer ile test edilir.

Config: `config/chunking.json`. Hedef **400**, kesin üst sınır **500**; overlap
hedefi **32**, izin verilen üst sınır **50** token. Ölçülen şey modele gönderilecek
**tam `chunk.text`** alanıdır. İçindeki doğal başlıklar, altyazılar, paragraf
ayırıcıları ve overlap dahil sayılır; özel token'lar da eklenir. Sonraki embedding
adımı ek bir başlık/query instruction/prefix eklerse bütçe yeniden ölçülmelidir.

Başlık bağlamı politikası **none**: model metnine metadata'dan başlık veya altyazı
eklenmez. Kaynak başlığı yalnız kendi akışında birincil içerik olarak yer alır;
başka parçaların önüne gizlice kopyalanmaz. `section_path`, `figure_id`, `caption`
metadata'sı otomatik olarak embedding girdisi değildir.

## Normalizasyon ve ham metne geri dönüş

- Ham blok metni `normalized_blocks.jsonl/raw_text` içinde aynen korunur. Buradaki
  “ham blok”, extraction JSON'undaki `ordered_blocks[].text` veya figure
  `blocks[].text` değeridir; PDF dosyasının byte aralığı değildir.
- Gövde satır kırılmaları boşluğa dönüşür, gereksiz boşluklar toparlanır. Kaynaktaki
  paragraf, liste ve tipografiyle saptanan başlık ayrımları korunur.
- Figure metninin satır/blok sırası yeniden kurulmaz; satır ayrımları korunur.
- Tireler topluca silinmez. Yalnız `letters-\nletters` biçiminde bölünmüş kelimenin
  tiresiz birleşimi kaynak PDF'nin başka yerinde **tam kelime** olarak bulunursa
  tire ve satır arası boşluk kaldırılır. Tüm 677 sayfa taranır; pozitif kanıtlar
  önbellekten kullanılsa bile PDF blok metni ve koordinatlı karakter aralığıyla
  yeniden doğrulanır. Substring kanıt sayılmaz.
- Bu corpus'ta `long-\nterm` ve `uncom-\nmanded` için tiresiz kanıt yoktur;
  tireleri korundu, belirsizlik loglandı. Normalizasyon yalnız satır boşluğunu
  toparlar; kelimeyi varsayımla düzeltmez. Gerçek veride tiresiz kelime birleştirme
  sayısı **0**; kanıtlı birleştirme davranışı unit testle sınanır.

`source_refs` alanındaki `raw_start/raw_end`, ham bloktaki **yarı açık Python
Unicode karakter aralığıdır**. `chunk_start/chunk_end` aynı referansın nihai
`text` içindeki karşılığıdır. `block_key`, PDF/basılı sayfa ve `source_block_id`
birlikte saklanır. `role=primary` gerçek içeriği, `role=overlap` kasıtlı tekrarı
ayırt eder. Aralıklar byte veya tokenizer offset'i değildir.

`normalized_blocks.jsonl` ayrıca `raw_to_normalized_map` taşır; buradaki karşılık
alanları `normalized_start/normalized_end` adındadır. Bir ham boşluk dizisi iki
paragraf ayırıcısına karşılık gelebilir; yalnız boşluk içeren ham aralıkların
örtüşmesi içerik tekrarı değildir. Kaynak dışı biçimlendirme aralıklarında yalnız
boşluk/satır ayracı bulunabilir; kaynak dışı kelime eklenmesi doğrulamada reddedilir.

Birleştirme logu kaynak sayfa/blok/aralık, özgün metin ve tiresiz kullanım kanıtını
tutar. Fiziksel sayfa/sütun geçişi birleştirmeleri iki kaynak bloğuyla ayrıca
loglanır. Footer blokları kaynak kayıtlarına veya chunk'lara alınmaz.

## Sınırlar, başlıklar ve sayfa geçişleri

Başlıklar orijinal PDF'de extraction bloğunun bbox'ı ile eşlenen satırların bold
tipografisi ve gerçek metniyle belirlenir. Dict blok numarası doğrudan kullanılmaz:
görüntü blokları yüzünden text-block kimliklerinden farklı olabilir. Normal prose'un
ilk harfinin büyük olması başlık sayılmaz.

`section_path` yalnız açık bölüm başlığı ve en son açık alt başlığı tutar;
aralarındaki daha derin hiyerarşi tahmin edilmez. Bu nedenle örneğin alt başlığın
PEAR/Environment gibi bir ara ebeveyni eksik olabilir. Figure yolları belirsizse
`[]` bırakılır. Art arda gelen başlıklar sonraki metnin önünde birlikte korunur;
tek başına boş başlık chunk'ları üretilmez.

Aynı bölüm içindeki paragraflar için paragraf/cümle sınırları tercih edilir; kısa
chunk'lar uygundur. Hedefe ulaşmak için farklı bölümler veya farklı şekiller
birleştirilmez. Overlap yalnız aynı kaynak grubunun içinde kalır. Uzun cümle
zorunlu bölünürse kelime sınırı, zorunluysa karakter sınırı kullanılır ve raporlanır.

Fiziksel sayfa/sütun geçişi: başlık araya girmemiş, önceki parça bitmemiş ve sonraki
parça küçük harfle devam ediyorsa aynı paragraf birleştirilebilir. Sayfa sonları
körlemesine birleştirilmez. 624–625 devamı doğrulandı:

> Proper documentation of all maintenance work is a key element, and AMTs typically
> spend as much time updating maintenance logs as they do performing the work.

Bu metni içeren chunk 266 token, PDF sayfaları `[624,625]`; kaynak aralıkları
gerçekten kullanılan sayfaları içerir. Metadata başlık etiketleri önceki sayfalardan
gelse de model metninde kullanılmayan başlık blokları kaynak listesine eklenmez.

## Şekiller ve 655

36 inline figure kaydı `type=figure` chunk'larına dönüştürülür. Figure kimliği ve
mevcut altyazı saklanır; büyük şekil parçalara ayrılsa da `figure_id` aynıdır.
Altyazı metadata'sı her parçada bulunabilir ama kaynak metin parçasında yer almıyorsa
başına kopyalanmaz ve kullanılmamış altyazı bloğu `source_refs` içine yazılmaz.
Şekil içi oklar, grafik değerleri veya anlam ilişkileri çıkarılmaz/uydurulmaz.

655'in `page_body_reference` kaydı yeni figure akışı üretmez. Gövdedeki beş kaynak
olay–neden çifti **beş body chunk'ı** olarak, olay/CAUSE başlıkları ve ortak
`event_cause_pair_id` ile korunur. Çiftler arasında overlap yoktur. Figure 14-37
altyazısı kaynak akışındaki son çiftte birincil metin olarak bir kez bulunur;
çiftlerin metadata'sında aynı gerçek altyazıyla ilişki saklanır. 655'te ikinci
indeks metni veya `type=figure` kopyası yoktur.

## Çıktılar ve bu çalışmanın sonuçları

Üretilenler `audit/chunking/` ve ikinci çalıştırma `audit/chunking_repeat/`
altındadır; mevcut `audit/` ignore kuralıyla Git dışında kalır:

- `chunks.jsonl`: nihai model metni, token sayısı, kararlı kimlik ve kaynak aralıkları.
- `normalized_blocks.jsonl`: ham ve normalize bloklar, dönüşüm haritası.
- `normalization_log.jsonl`, `headings.json`, `hyphen_evidence.json`: karar kanıtları.
- `run_manifest.json`: girdi/tokenizer hash'leri, revision, Python/paket sürümleri.
- `report.json` / `report.md`: istatistikler, zorunlu bölmeler, örneklerin tam metni.
- `verification.json`: bağımsız aralık/kapsam ve iki çalıştırma karşılaştırması.

| Ölçüm | Sonuç |
|---|---|
| Gövde / figure chunk | 75 / 36 (toplam 111) |
| Token min / medyan / p95 / max | 13 / 137 / 388 / 400 |
| p95 yöntemi | Nearest rank, `ceil(0.95 * N)` |
| Uygun kaynak blokları | 638; 32 footer bloğu dışlandı |
| Boşluk dışı kaynak kapsamı | 78.222 karakter, birincil kapsam tam |
| Yanlışlıkla birincil tekrar / kayıp | 0 / 0 |
| Kasıtlı overlap karakter kopyaları | 2.538; ayrı sayıldı, aynı grupta kaldı |
| Normalizasyon logu | 333 parça boşluk/dönüşüm kaydı; 2 belirsiz tire; 36 fiziksel geçiş |
| Açık başlık / stil bbox eşleşme belirsizliği | 57 / 0; iç hiyerarşi yine tahmin edilmedi |
| Gerçek veride zorunlu uzun cümle bölmesi | 0; sentetik uzun cümle testi mevcut |
| Çok sayfalı chunk | 22 |
| 655 | 5 ayrı body çifti, ikinci figure kopyası yok |
| Testler | Mevcut testlerle toplam 27 geçti; gerçek BGE tokenizer testleri dahil |

İki çalıştırmanın `chunks.jsonl` byte hash'i aynı:
`9973c8a69999c324989dd3ab04c8d8a65083870e395709725d01efd537a4a2c4`.
97 korunan mevcut dosyanın hash'i değişmedi; extraction kodu, onaylı bölgeler,
extraction çıktıları ve geliştirme seti korundu.
İki boş kaynak bloğu (`p654:b1`, `p654:b7`) ham blok arşivinde tutulur;
boş metin için yapay chunk veya kaynak referansı üretilmez.

Örnekler (`audit/chunking/report.md` tam metinleri içerir):

- Çok sayfalı: `...:chunk:0fd87866fd3a89b329440114`, 266 token, `[624,625]`.
- Figure: `...:chunk:fe067bcb9042bb4b76113e93`, 160 token, Figure 14-1 / PDF 625;
  kaynak altyazı: “Human factors exist in both proper and improper actions.”
- Olay–neden: `...:chunk:fafa04ac346854b8112850dc`, 206 token, PDF 655;
  `INCIDENT` → Excalibur Airways olayı → `CAUSE` → kaynak bakım nedeni.

Sınırlar: kısa kaynak bölümleri nedeniyle chunk'lar çoğunlukla 400 token'dan
küçüktür. Cümle devamı/sınırı kuralları heuristiktir; kaynak referansı ve kapsam
garantisi anlam bütünlüğünün insan tarafından onaylandığı anlamına gelmez. Kaynak
PDF karakter bozuklukları düzeltilmez. Özellikle grafik etiketlerinin parçalı
yapısı ve figure blok sırasının sınırlamaları korunur. Bölge sınırı onayları tam
metin/şekil anlamı doğrulaması değildir.

Bu aşama embedding veya retrieval çalıştırmaz. Üretilen veriler ve tokenizer
önbelleği Git dışında tutulur.
