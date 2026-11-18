# Kaynaklı yanıt üretimi

`gpt-6-luna` düşük maliyetli metin üretimi, Responses API ve katı Structured
Outputs desteği nedeniyle seçildi. 18 Kasım 2026 tarihinde resmî model
sayfasında tarihli snapshot listelenmiyordu. Üretim ayarı `reasoning.effort=none`
ve `max_output_tokens=1200`. Responses API'de bu sınır görünür çıktı ve varsa
reasoning token'larının toplamına uygulanır.

- [Model, fiyatlar ve snapshot bilgisi](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [Responses API referansı](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Structured Outputs kılavuzu](https://developers.openai.com/api/docs/guides/structured-outputs)

## Bütçe ve kayıt

18 Kasım 2026 itibarıyla standart fiyatlar milyon token başına 0,10 USD
girdi, 0,01 USD cache hit, 0,125 USD cache write ve 0,50 USD çıktıdır.
272.000 girdi token'ı aşılırsa girdi/cache fiyatları iki katına ve çıktı
fiyatı 1,5 katına çıkar. İstek standart servis katmanında çalışır.

Uygulama, ek bir token sayım isteği göndermeden, modelin 1.050.000 token
bağlam sınırını girdi için güvenli bir üst sınır olarak kullanır. Talimat,
pasajlar ve şema bu model sınırının içindedir. Her girdiyi cache write
tarifesinden ve cache hit indirimsiz hesaplamak kısa çağrılarda bile
0,2634 USD rezervasyon oluşturur. Kullanım geldiğinde bu tutar bildirilen
girdi ve çıktı üzerinden aynı muhafazakâr tarifeyle güncellenir.
Bildirilmeyen kullanımda rezervasyon korunur. Bu yüzden tek bir belirsiz
çağrı sonraki bir çağrının bütçeye sığmasını engelleyebilir.

0,50 USD sınırı SQLite işlemi içinde çağrıdan önce kontrol edilir. CLI,
HTTP ve probe yeniden başlatma sonrasında aynı
`audit/answers/ledger.sqlite3` dosyasını kullanır. SDK otomatik yeniden
deneme yapmaz. Bu kontrol uygulamanın yerel muhasebesidir. Sağlayıcı
tarafında kesin bir fatura limiti sağlamaz.

Defter gönderim öncesi rezervasyonu, çağrı sonucunu, varsa sağlayıcının
usage kaydını, süreleri, üretim ayarlarını, prompt hash'ini, corpus ve index
hash'lerini ve getirilen chunk kimliklerini saklar. Cache anahtarı soruyu,
sıralı pasaj metinleri ve kimliklerini, prompt'u, şemayı, model ve üretim
ayarlarını içerir. `origin=cache` yeni harcama yapılmadığını, `cached_usage`
ilk çağrının kullanımını gösterir. Canlı üretim çıktıları zamanla değişebilir.

## Atıflar ve development incelemesi

- `answered` geçerli şema ve getirilen pasajlarla eşleşen atıflar içerir.
- `insufficient_evidence` için cevap ve kaynaklar boştur.
- `provider_error` altında timeout, rate limit, kimlik doğrulama, eksik
  yerel anahtar, izin, kota, refusal, geçersiz şema/atıf ve kesilen çıktı
  ayrı hata kodlarıyla gösterilir.
- `budget_exceeded` durumunda model çağrısı başlatılmaz.

PDF ve basılı sayfa etiketleri, kaynak aralıkları ve diğer metadata chunk
kayıtlarından gelir. Otomatik kontroller çıktı şemasını ve atıf kimliklerini
doğrular. İddiaların kaynaklarca anlamsal olarak desteklenmesi insan
incelemesi gerektirir.

On soruluk development kontrolünde yerel `POST /ask` tüm sorular için
HTTP 200 döndürdü. Sekiz cevaplanabilir soru `answered`, iki cevaplanamaz
soru `insufficient_evidence` durumuyla sonuçlandı. Bu sonuç durum ve
biçim kontrolünü gösterir. Cevap doğruluğu insan incelemesi bekler.
Development raporu
`audit/answers/development.json` altında soru durumunu, beklenen
cevaplanabilirliği, cevap ve kaynakları verir. `human_review=pending`
olan satırlarda doğruluk ve iddia başına destek insan incelemesi gerektirir.
Development referans cevapları ve kanıt anahtarı modele gönderilmez.
