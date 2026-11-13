# Toplu extraction: uyarı sınıflandırması

Bu rapor ilk toplu extraction'ın tarihsel incelemesidir. Güncel uygulama
[sabit bölge extraction raporunda](approved_region_extraction.md) açıklanır.
Sonraki insan onayları yalnız bölge sınırları içindir; içerik, şekil içi sıra ve
anlam ilişkilerinin doğrulandığı anlamına gelmez. Audit bağlantıları Git dışı
yerel inceleme materyaline aittir.

Bu rapor mevcut `audit/corpus/pages.jsonl` kayıtlarının metin/blok incelemesine
ve kaynak PDF'den 110 DPI ile render edilen 23 sayfanın asistan tarafından görsel
karşılaştırılmasına dayanır. İnsan onayı değildir; `human_review_status` alanları
değiştirilmedi. Extraction, config, soru seti ve mevcut çıktı kayıtları değiştirilmedi.
Render'lar ve blok düzeyindeki kanıtlar `audit/corpus/layout_review/` altındadır.

## Öncelikli kontrol: PDF 651 / basılı 14-28

Footer uyarısını üreten gövde bloğu (sıralanmış blok indeksi 16, sıfır tabanlı):

```text
3.
Electrical wiring discrepancies to include crossing
connections. [Figure 14-32]
```

Tam bbox: `[63.0, 694.7192993164062, 293.59906005859375, 720.3593139648438]`.
Ham blokta `3.` sonrasında tab, `crossing` sonrasında satır sonundan önce boşluk
vardır; bunlar `layout_review/evidence.json` içinde değiştirilmeden saklanır.
Koordinatlar PDF point, başlangıç sol üst; sayfa boyutu 594 × 774 point.
Footer sınırı `y=720`; taşma yalnızca **0.359314 point**.

Görüntüde bu blok sol sütunun son liste maddesidir. Mevcut gövde kaydında tüm
metin korunur; blok kırpılmamış. Footer'a ayrılan tek blok `14-28`, bbox:
`[516.5838012695312, 727.9802856445312, 542.15380859375, 740.290283203125]`.
Sayfa numarası gövdeye karışmamış. Bu uyarı için metin kurtarma gerekmez; gelecekte
footer eşiğinin değerlendirilmesi yeterlidir. Şimdilik kural değişikliği yapılmadı.

Ayrı sorun: Şekil 14-30'un sağa atanan metinleri, listedeki 3. madde ile 4. madde
arasına giriyor. Liste maddeleri kaybolmamış; okuma akışı kesiliyor.

## Uyarılı 20 sayfa

“Kayıp yok” PDF'nin çıkarılabilir metin bloklarının kaybolmadığını ifade eder;
şekillerin görsel ilişkilerinin veya tüm görünen yazıların doğru çözümlendiğini
garanti etmez. Aşağıdaki işlemler öneridir, uygulanmadı.

| PDF sayfa | Neden / sınıf | Metin kaybı veya sıra sorunu | Gereken işlem |
|---|---|---|---|
| 626 | Tam genişlikte Şekil 14-3 altyazısı; ayrıca solda Şekil 14-2 | Blok kaybı yok. `Research is` ile `optimized by...` arasına 14-3 altyazısı giriyor. 14-2'de yinelenen etiketler de var. | Şekil/altyazıları gövdeden ayır; yinelenen görsel etiketleri ayrıca incele. |
| 628 | Tam genişlikte Şekil 14-5, petek biçimli etiket listesi | Kayıp yok. Şeklin sağ etiketleri Educational Psychology gövdesinden sonra geliyor; tek şekil parçalanıyor. | Şekli tek kayıt olarak ayır; etiketleri düz liste olarak koru. |
| 629 | Şekil 14-6, disiplin diyagramı | Blok kaybı yok. Diyagramın sağ etiketleri `Pilots` / `are required...` cümlesinin arasına giriyor. Bazı bloklar farklı görsel konumları birlikte içeriyor. | Şekli ayır; etiket/blok içi sıralamayı gözden geçir. |
| 633 | Tam genişlikte Şekil 14-12; PEAR People kategori kutuları | Kayıp yok. Sol şekil listeleri Actions gövdesi ile sağ sütundaki `job...` devamını ayırıyor; kategori başlıkları kendi listelerinden kopuyor. | Şekli ayır; dört kategori ile listelerinin ilişkisini koru. |
| 634 | Tam genişlikte Şekil 14-13; Environment kategori kutuları | Kayıp yok. MEDA 4. maddesi ile `or reduce...` devamına şekil listesi/altyazısı giriyor. | Şekli ayır; MEDA madde akışını koru. |
| 635 | Üstte tam genişlikte Şekil 14-14 ve 14-15 | Kayıp yok. İki şeklin sağ listeleri sol gövdenin tamamından sonra geliyor; Actions ve Resources parçaları birbirinden kopuyor. | İki ayrı şekil kaydı; listelerin ait olduğu şekil korunmalı. |
| 638 | Şekil 14-18; geniş poster başlığı, etiketler ve risk kutuları | Kayıp yok. `When work` / `resumes...` arasına poster giriyor; risk kutuları da bölünüyor. | Posteri ayır; üç risk kutusunu ayrı alt bloklarla koru. |
| 640 | Şekil 14-19; geniş poster/kutu metni | Kayıp yok. Sol gövdedeki `cause of` / sağdaki `fatigue...` arasına etiketler giriyor. Risk metni tek blokta, görseldeki sol–orta–sağ sırasından farklı. | Posteri ayır; risk kutularının iç sırasını ayrıca ele al. |
| 641 | Şekil 14-20; geniş poster/kutu metni | Kayıp yok. Bazı risk önerileri gövde paragrafından sonra geliyor; orta kutu önce, sol/sağ öneriler birleşik blokta sonra çıkıyor. | Posteri ayır; birden çok kutuyu birleştiren bloğu incele. |
| 642 | Şekil 14-21; geniş poster/kutu metni | Kayıp yok. Poster açıklaması MITIGATING THE RISK'ten sonra geliyor; `delays` / `or cancellations...` arasına şekil metni giriyor. | Posteri ayır; açıklama ve risk kutuları için yerel sıra belirle. |
| 643 | Şekil 14-22; geniş poster/kutu metni | Kayıp yok. `having the` / `proper parts...` arasına sağ şekil etiketleri/risk kutusu giriyor. | Posteri ayır; gövde cümlesini kesintisiz tut. |
| 644 | Şekil 14-23; geniş poster/kutu metni | Kayıp yok. Fatigue açıklaması risk başlığı ve sol gövdeden sonra geliyor; `service` / `or technical publications...` devamı kesiliyor. | Posteri ayır; açıklama/risk sırası korunmalı. |
| 646 | Şekil 14-25; geniş poster/kutu metni | Kayıp yok. Şekil parçaları assertiveness listesinin 4. maddesi ile sağdaki `Example: John...` arasına giriyor; orta/sağ risk kutuları birleşmiş. | Posteri ayır; madde–örnek bağını ve risk kutularını koru. |
| 648 | Şekil 14-27; geniş poster/kutu metni | Kayıp yok. `foods` / `lacking the proper nutrition...` arasına poster etiketleri ve risk metni giriyor. | Posteri ayır; risk önerilerinin kutu ilişkisini koru. |
| 649 | Şekil 14-28; geniş poster/kutu metni | Kayıp yok. Poster açıklaması ve sağ etiketler, sol gövde bölümlerinden sonra geliyor; risk kutuları görsel sıra ile uyuşmuyor. | Posteri ayır; açıklama ve üç risk kutusunu düzenle. |
| 650 | Altta Şekil 14-29; geniş poster/kutu metni | Kayıp yok. Üst gövdedeki `the` / `group's perception...` arasına posterin sol parçaları giriyor. | Önce üst iki sütunun gövdesi; poster bağımsız kayıt olmalı. |
| 651 | Şekil 14-30 + footer sınırında liste maddesi | Footer kaynaklı kesilme/karışma yok. Şekil metni 3. ve 4. liste maddesinin arasına giriyor. | Footer için kurtarma gerekmiyor; posteri ayır, 1–8 listesini koru. |
| 652 | Şekil 14-31; geniş poster/kutu metni | Kayıp yok. `chain of events is` / `broken...` arasına şekil etiketleri giriyor; orta risk kutusu gövdeden sonra geliyor. | Posteri ayır; gövde devamı ve kutu ilişkisini koru. |
| 654 | Şekil 14-36, tam genişlikte grafik | Kaynak blok kaybı yok; grafik başlığı ve sağ yazıları sol gövdeden sonra geliyor. Görseldeki TECHNICAL CAUSES metni `T`, `ECHN`, `ICAL`, `CAUS`, `ES` olarak parçalı; HUMAN CAUSES da bölünmüş. Grafik anlamı düz metinde güvenilir değil. | Grafiği ayır; etiket/anlam için görsel destekli ayrı doğrulama. Gövdedeki %80 ifadesi ve altyazı korunuyor. |
| 655 | Şekil 14-37; tam genişlikte olay–neden kutuları | Kayıp ve sıra sorunu görülmedi. Beş çift üstten alta doğru; bütün kutular aynı sütuna atanmış. | Hata düzeltmesi gerekmiyor; gelecekte olay–neden çiftlerini bölmeden taşı. |

Uyarıları “zararsız geniş başlık” diye topluca kapatmak uygun değil: poster
başlıkları şekillerin parçası ve eşlik eden bloklarda gerçek sıralama sorunları var.
Bağımsız geniş gövde başlığı veya klasik veri tablosu saptanmadı; 633–635 ve
posterlerde tablo benzeri kutulu listeler var. 19 sayfada düzleştirilmiş çıktı
sırası/şekil bütünlüğü sorunu, 655'te beklenen tam genişlik uyarısı var.

## Uyarısız sayfalardan sabit örneklem

Yöntem: `random.Random(42).sample(uyarısız_sayfalar, 3)`; adaylar PDF sayfa
sırasıyla `[624, 625, 627, 630, 631, 632, 636, 637, 639, 645, 647, 653]`.
Seçim sırası **647, 625, 624**; önceden incelenmiş sayfalar örneklemden çıkarılmadı.

| Sayfa | Görsel karşılaştırma | Gereken işlem |
|---|---|---|
| 647 | Kayıp görülmedi. Sağ üst Şekil 14-26'nın 12 sorusu ve altyazısı, sol alttaki `Confined spaces ... very` ile sağdaki `difficult to perform tasks...` arasına giriyor. Şekil tek sütunda kaldığı için uyarı üretmiyor. | Şekil 14-26'yı gövdeden ayır; cümle devamını koru. |
| 625 | Gövde sol–sağ akışı ve `deployment of systems` / `and services` devamı doğru. Şekil 14-1 ayrı kayıtta; bu örnek kontrol şeklin tüm iç ilişkilerine onay değildir. | Gövde için yeni işlem yok; şeklin iç sırası inceleme bekler. |
| 624 | Başlıklar, hata türleri, numaralı listeler ve sol–sağ gövde sırası görüntüyle uyumlu. Footer karışması görülmedi. | Yeni işlem yok. |

## Sınır ve sonuç

23 sayfanın çıkarılabilir metin blokları gövde + şekiller + footer toplamıyla
karşılaştırıldı; her kaynak blok tam bir kez mevcut. Bu otomatik muhasebe kontrolü,
görseldeki tüm yazıların/ilişkilerin çözümlendiği veya insan tarafından doğrulandığı
anlamına gelmez. Şekil ayrımı ve yerel sıralama, normalizasyondan önce ele alınmalı.
Bu çalışmada yalnızca rapor ve inceleme kanıtları üretildi; extraction kuralları,
insan inceleme durumları ve önceki çıktılar değişmedi. Chunking, commit ve push yok.
