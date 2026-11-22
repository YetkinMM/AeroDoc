# AeroDoc’u Docker ile çalıştırma

Docker Desktop’ı Linux container modunda çalıştır. Komutları proje kökünde
çalıştır. Servis container içinde `0.0.0.0:8000`, host üzerinde
`127.0.0.1:8000` dinler. Varsayılan retrieval BM25 ve `k=5` kullanır.
Image, Python 3.13 ve `requirements-docker.lock.txt` ile kurulur. BGE model
dosyaları, PyTorch ve CUDA varsayılan image’a girmez. BGE için Windows CLI’da
`python -m scripts.ask --retrieval bge` ve mevcut [BGE kurulum adımları](retrieval.md)
kullanılabilir.

## Girdiler ve kalıcı veriler

| Host yolu | Container yolu | Erişim |
| --- | --- | --- |
| `audit/chunking/chunks.jsonl` | `/app/audit/chunking/chunks.jsonl` | Salt okunur |
| `audit/retrieval/index.json` | `/app/audit/retrieval/index.json` | Salt okunur |
| `audit/retrieval/bm25.json` | `/app/audit/retrieval/bm25.json` | Salt okunur |
| `audit/answers/` | `/app/audit/answers/` | Okuma ve yazma |

SQLite bütçe kayıtları, belirsiz rezervasyonlar ve cevap cache’i aynı
`audit/answers/ledger.sqlite3` dosyasındadır. Compose dizini bağlar, böylece
SQLite işlem sırasında gerekli yan dosyaları aynı konumda açabilir.
Container kullanıcısı UID/GID 10001 ile çalışır. Docker Desktop’ta proje
yolunun paylaşılabilir olduğundan emin ol. Linux host’ta UID/GID 10001’e
girdiler için okuma, defter ve defter dizini için okuma/yazma erişimi ver.

Mevcut kurulumda bu defteri yerinde kullan. Başka bir checkout’a geçiyorsan
önce mevcut AeroDoc süreçlerini durdur ve mevcut defteri yeni checkout’ın
aynı göreli yoluna taşı. Aynı bütçeyle çalışan Windows CLI, yerel API ve
Docker arasında geçiş yaparken önce çalışan süreci durdur. Özellikle Docker
Desktop üzerinden paylaşılan SQLite dosyasına Windows ve Linux süreçlerinden
eşzamanlı yazma. Compose servisini tek örnek ve tek worker olarak çalıştır.
Container defter eksikse açılmaz.

## Temiz checkout hazırlığı

Üç retrieval girdisi mevcutsa yeniden üretim adımlarını atla. Eksikse
`data/raw/amtg_handbook.pdf` dosyasını [README’deki kaynak](../README.md)
üzerinden edin ve `data/raw/manifest.json` ile aynı PDF’yi kullan. Python
3.13 kurulu bir Windows host’ta:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-chunking.lock.txt
.\.venv\Scripts\python.exe -B scripts/extract_corpus.py
.\.venv\Scripts\python.exe -B scripts/fetch_chunk_tokenizer.py
.\.venv\Scripts\python.exe -B scripts/build_chunks.py
.\.venv\Scripts\python.exe -B scripts/retrieval.py build --bm25-only
```

Chunk üretimi sabit tokenizer’ı indirir. BM25 index üretimi tokenizer, model
ağırlığı veya embedding hesaplaması gerektirmez. Bu komut mevcut BGE
embedding’lerinin üzerine yazmayı reddeder. Her iki indeksi güncellemek için
tam retrieval build’ini kullan. Girdi dosyası eksikse Compose başlatmayı,
hash veya corpus eşleşmesi bozuksa uygulama açılışı durur.

Aynı bütçenin bir defteri zaten varsa onu kullan. Yalnızca ilk kez bütçe
oluşturulan bir kurulumda aşağıdaki komut boş defteri hazırlar. Ağ çağrısı yapmaz.

```powershell
.\.venv\Scripts\python.exe -B -c "from pathlib import Path; from scripts.answering import Ledger, read; Ledger(Path('audit/answers/ledger.sqlite3'), read('config/answers.json')['budget_usd'])"
```

## Başlatma, loglar ve durdurma

```powershell
docker compose --env-file .env.example build
docker compose --env-file .env.example up -d
docker compose --env-file .env.example logs -f aerodoc
docker compose --env-file .env.example stop
```

Örnekteki `--env-file .env.example`, Compose’un proje kökündeki yerel
`.env` dosyasını otomatik okumasını engeller. Gerçek cevap isteği göndermek
istediğinde anahtarı PowerShell oturumuna gizli girişle al ve çalışma anında
Compose’a aktar. Anahtar girmeden de servis açılır ve sağlık ve doğrulama
istekleri çalışır.

```powershell
$secret = Read-Host 'OpenAI API key' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
try {
    docker compose --env-file .env.example up -d --force-recreate --no-build
} finally {
    Remove-Item Env:OPENAI_API_KEY
    $secret.Dispose()
}
```

Anahtarı Docker yetkisi olan kullanıcılar çalışan container’ın ortamında
görebilir. Çözümlenmiş Compose config’ini veya container ortamını yazdırma.
Yalnız yapılandırmanın geçerliliğini kontrol etmek için
`docker compose --env-file .env.example config --quiet` kullan.

Container’ı yeniden oluşturmak veya durdurmak host’taki dosyaları silmez.
Defter dosyasını ya da onu içeren host dizinini silmek, bütçe geçmişini ve
cache’i siler.

## Doğrulama kapsamı

22 Kasım 2026’da kullanıcı terminalinde gerçek Docker build ve Compose
başlatma başarılı oldu. Container `Up` durumundaydı ve port
`127.0.0.1:8000` ile sınırlıydı. Tarayıcıda `/health`
`{"status":"ok","retrieval":"bm25"}` döndürdü ve `/docs` açıldı.

Codex oturumunda doğrudan Docker motoru erişimi reddedildi. Onaylı Docker
erişimiyle port eşlemesi ve image boyutu doğrulandı. `aerodoc:local`
image’ının ölçülen boyutu 239.044.293 bayt (yaklaşık 228 MiB).

- Çalışan servise gönderilen boş `POST /ask` isteği HTTP 422 ve
  `{"error_code":"invalid_request"}` döndürdü.
- Container içindeki BM25 araması mevcut 111 chunk üzerinden beş sıralı
  sonuç döndürdü. Her sonucun tüm corpus alanları, sayfa ve kaynak
  referansları dahil, orijinal kayıtla eşleşti.
- Container içinde FastAPI test istemcisi ve mock provider ile HTTP
  200 yanıtı ve atıf metadata’sı doğrulandı. Geçici SQLite defteri
  yeniden açılınca aynı istek cache’den karşılandı. Mock provider
  toplam bir kez çağrıldı ve ücretli API çağrısı yapılmadı.
- Compose restart işlemi container başlangıç zamanını değiştirdi ve
  `/health` tekrar başarılı oldu. Mevcut bütçe ve cache defterinin
  SHA-256 değeri restart öncesi ve sonrasında host ve container
  içinde aynıydı. Testler mevcut deftere yazmadı.

Yerel doğrulamada 51 test ve mevcut Windows BGE indeksiyle arama geçti.

Motor erişimi olan bir oturumda ücretsiz smoke test için:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
(Invoke-WebRequest http://127.0.0.1:8000/docs).StatusCode
curl.exe -s -i -H "Content-Type: application/json" --data "{}" http://127.0.0.1:8000/ask
docker compose --env-file .env.example exec -T aerodoc python -m scripts.retrieval search --method bm25 -k 5 --question "What are the three types of human error?"
docker image inspect aerodoc:local --format '{{.Size}}'
```

## GitHub Actions CI

`.github/workflows/ci.yaml` akışı `main` dalına push ve `main` hedefli
pull request olaylarında çalışır. Linux runner’da Python 3.13 kullanır.
Aynı Git ref’i için yeni bir çalışma başladığında önceki çalışma iptal
edilir. İşin zaman sınırı 15 dakika ve depo izni yalnızca okuma düzeyindedir.

`requirements-ci.txt` mevcut Docker ve chunking bağımlılıklarını, snapshot
testi için de sabit NumPy sürümünü kurar. CI, sabit tokenizer dosyalarını
indirip SHA-256 değerlerini doğrular. Küçük sentetik PDF ve chunk
fixture’larıyla extraction, chunking ve BM25 testlerini, mock provider
ile de API, cache ve bütçe koruma testlerini çalıştırır. Gerçek OpenAI
anahtarı veya GitHub secret gerekmez.

Yalnızca BGE ağırlıklarını gerektiren iki `ActualBGETests` testi
beklenen atlama olarak günlükte görünür. Başka bir test atlanırsa veya
tokenizer kurulumu ya da doğrulaması başarısız olursa CI hata verir.
Gerçek corpus ve sabit değerlendirme seti üzerinde değerlendirme,
canlı OpenAI çağrısı ve Compose smoke testleri CI kapsamı dışındadır.
Docker adımı image’ı yerel olarak oluşturur ve registry push ya da
deployment yapmaz.
