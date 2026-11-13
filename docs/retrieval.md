# BM25 ve BGE development baseline

Bu aşama mevcut 111 chunk'ı (75 body, 36 figure) değiştirmeden arar.
İki yöntem de yalnız `chunk.text` kullanır; section_path, altyazı metadata'sı veya
başka bağlam eklenmez. Metnin içinde zaten bulunan başlık/altyazılar korunur.
655'in beş olay–neden çifti body olarak birer kez bulunur; preserve_in_body
şekil referansından ikinci kopya oluşturulmaz. Extraction ve chunking ayarları
değiştirilmez, geliştirme sorularına göre parametre ayarı yapılmaz.

## Kurulum ve çalıştırma

Windows PowerShell, proje kökünden:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-retrieval.lock.txt
.\.venv\Scripts\python.exe scripts/fetch_retrieval_model.py
# Yeni checkout'ta bir kez; bu oturumun mevcut snapshot'ı üzerine çalıştırmayın:
# .\.venv\Scripts\python.exe scripts/verify_retrieval.py --record-inputs
.\.venv\Scripts\python.exe scripts/retrieval.py build
.\.venv\Scripts\python.exe scripts/retrieval.py search --method bm25 --question "How does fatigue affect maintenance?" -k 5
.\.venv\Scripts\python.exe scripts/retrieval.py search --method bge --question "How does fatigue affect maintenance?" -k 5
.\.venv\Scripts\python.exe scripts/evaluate_retrieval.py
.\.venv\Scripts\python.exe scripts/verify_retrieval.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements-retrieval.txt` doğrudan bağımlılıkları, `.lock.txt` bu Windows /
Python 3.13.2 ortamında çözümlenen sürümleri kaydeder. İlk model indirmesi ağ
erişimi gerektirir. Sonraki build/search/evaluation işlemleri yalnız yerel
dosyalardan çalışır. Ağ gerekmeden arama yapılabilmesi için önce extraction ve
chunking çıktıları, ardından model dosyaları ve index üretilmelidir.

Python arayüzü: `Searcher("bm25" veya "bge").search(question, k)`.
Sonuçlar orijinal chunk alanlarının tamamını ve `score`, `rank` alanlarını
taşır. Büyük skor önce gelir; eşit skorda chunk_id alfabetik artan sıralanır.
BM25 ve cosine skorlarının ölçekleri birbirleriyle karşılaştırılamaz.

## Sabit yöntemler

`config/retrieval.json` yöntemleri açıkça sabitler. BM25, küçük harfe çevrilmiş
metinde `[a-z0-9]+` sözcükleri kullanır; stopword, stemming ve eş anlamlı
genişletmesi yoktur. Sorguda tekrarlanan kelimeler bir kez sayılır.
k1=1.5, b=0.75; idf=`log(1+(N-df+0.5)/(df+0.5))`.
Corpus sırası ve chunk_id eşlemesi index manifestinde saklanır.

BGE: BAAI/bge-small-en-v1.5 revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, chunking tokenizer'ıyla aynıdır.
[Sabit revision'daki resmî kullanım belgesi](https://huggingface.co/BAAI/bge-small-en-v1.5/blob/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/README.md#using-huggingface-transformers)
uyarınca ilk tokenın son hidden state'i (CLS) alınır ve L2 normalize edilir.
Sorguya tam olarak `Represent this sentence for searching relevant passages: `
öneklenir; passage'a instruction eklenmez. Bu karar değerlendirmeden önce
sabitlenmiştir. Model `eval()` ve `torch.inference_mode()` ile CPU / float32,
tek thread, deterministic algorithms ve eager attention kullanır. Vektörler
384 boyutludur. Normalize edilmiş vektörlerin doğrudan matris çarpımı exact
cosine aramasıdır; yaklaşık index kullanılmaz.

Resmî örnekteki truncation yerine burada **truncation=False** kullanılır.
Instruction ve özel tokenlar dahil nihai sorgu/passage uzunluğu önce ölçülür;
500 token üstünde işlem hata verir. Sessiz kesme yapılmaz. Passage sayımları
chunking'de kaydedilen token_count ile ayrıca eşleştirilir. Sorgu başındaki
boşluklar değiştirilmez; yalnız boş sorgu reddedilir.

Model dosyaları immutable Hub revision'dan indirilir; LFS ağırlık SHA256'sı
Hub metadata'sıyla, tokenizer/config hash'leri mevcut chunking config'iyle
karşılaştırılır. Yerel model manifestindeki hash'ler her model yüklemesinde
yeniden doğrulanır. Index; chunks/config/uygulama SHA256'sı, sıralı chunk_id
listesi, model dosya hash'leri, paket/Python sürümleri, cihaz, dtype, boyut ve
token uzunluklarını kaydeder. Bunlar değişirse eski index kullanılmaz; açıkça
`build` gerekir. Index dosyalarının hash'leri ve vektör normları da kontrol edilir.

## Kanıt değerlendirmesi

`eval/dev_questions.json` salt okunur kullanılır. Sekiz cevaplanabilir soruda
k=1,3,5 için page_hit, evidence_recall ve all_evidence_hit hesaplanır.
Page_hit herhangi bir beklenen kaynak sayfası eşleşmesidir; kanıt başarısıyla
aynı şey değildir. Evidence_recall sorudaki alıntıların bulunan oranıdır;
toplu değer sekiz sorunun makro ortalamasıdır. All_evidence_hit bütün alıntıların
bulunmasını gerektirir. Cevaplanamaz iki soru paydalara katılmaz; ilk beş sonucu
ve skorları ayrıca raporlanır. Yetersiz kaynak eşiği belirlenmez.

Eşleşme yalnız `" ".join(text.split())` boşluk/satır kırılması normalizasyonuyla
yapılır; büyük/küçük harf, noktalama, tire veya sözcük değiştirilmez, fuzzy yoktur.
Alıntı önce beklenen PDF sayfasının gerçek ham gövde bloklarında veya tek şeklin
ham bloklarında, kaynak sırasıyla aranır. Her eşleşmenin harfleri ham blok ve
karakter koordinatlarına bağlanır. Getirilen chunk source_refs aralıklarının
bu koordinatların tamamını örtmesi gerekir. Metadata kanıt sayılmaz.

Bir alıntı iki chunk arasında bölünmüşse, yalnız gerçekten aynı kaynak
alıntısının bitişik ham aralıklarını örten getirilen parçalar birlikte sayılır.
Getirilen metinler sıralarına göre birleştirilmez; aradaki kaynak sözcükleri
atlanamaz. Farklı sayfa/gövde/şekil akışları birleştirilmez. İntentional overlap
aralık birleşimi olarak sayılır, ek kanıt sayılmaz. Alıntı kaynakta bulunamazsa
başarısız kabul edilip açıkça raporlanır. Her alıntı için tek chunk sırası ve
tüm gereken aralıkların ilk kez örtüldüğü prefix sırası raporlanır. D03'ün
624 ve 625 kanıtları ayrı değerlendirilir.

## Üretilen dosyalar ve kontroller

Tüm veriler `.gitignore` kapsamındaki `audit/retrieval/` altındadır:

- `model/`: sabit model, tokenizer ve artifact hash manifesti.
- `index.json`, `embeddings.npy`, `bm25.json`: ortak chunk_id eşlemesi ve index.
- `evaluation.json`: 10 soru için 111 sonuç, metadata, skor, kanıt aralıkları,
  soru bazında ve toplu metrikler; sorgu süreleri yükleme süresinden ayrıdır.
- `report.md`: okunabilir karşılaştırma, alıntılar ve kaçırılan kanıt sıraları.
- `verification.json`, `embeddings.repeat.npy`: bağımsız tekrar encoding,
  20 sorgunun sıralama kontrolü, metadata ve 655/footer kontrolleri.
- `input_snapshot.json`: bu oturum başındaki takip edilen dosyaların ve
  extraction/chunking çıktılarının hash'leri; mevcut çalışmayı koruma kontrolü.

`verify_retrieval.py` aynı girdiyi yeniden encode eder; embedding'leri atol=1e-6,
rtol=1e-5 ile karşılaştırır. Yeni model/arama nesnelerinde her iki yöntemin tüm
soru sıralamalarını yeniden doğrular. Embedding dosyaları için byte eşitliği
zorunlu değildir. Yeni bir checkout'ta oturum snapshot'ı yoksa bu kontrole
başlamadan önce korunacak girdiler için yerel snapshot oluşturulmalıdır;
`--record-inputs` seçeneği bu işlemi yapar ve mevcut snapshot varsa durur;
snapshot önceki dosyaların yerine geçmez ve index üretiminin girdisi değildir.

Testler BM25 formülünü, skor/tie sırasını, metadata korumasını, stale index/ID
eşleşmesini, tokenizer'ın özel token ve instruction sayımını, 500 sınırını,
CLS/normalizasyonu, çok alıntılı/çok sayfalı kanıtları ve eksik kaynak aralığının
reddedilmesini sınar. Model testleri yerel model yoksa açıkça skip olur.

Bu bir **development baseline**'dır; accuracy veya bağımsız test başarısı değildir.
Şekil sınırları yalnız `region_boundary_only` kapsamında onaylıdır; şekil içi
metin sırası ve anlamsal ilişkiler doğrulanmış değildir. Grafik değeri veya
ilişkisi üretilmez. Retrieval sonucu cevap veya cevaplanabilirlik kararı değildir.
Hybrid, reranker, LLM cevabı ve API bu aşamada yoktur.
