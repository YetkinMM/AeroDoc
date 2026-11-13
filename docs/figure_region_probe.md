# Şekil bölgesi denemesi: iki iterasyon

Tarihsel deneme raporudur. Sonraki sınır onayları tam içerik doğrulaması değildir;
güncel uygulama [sabit bölge extraction raporunda](approved_region_extraction.md).
Aşağıdaki görseller/ölçümler Git dışında tutulan yerel audit artefaktlarına bağlıdır.

Tam sayfa/neden/işlem tablosu: [32 sayfalık işlem tablosu](extraction_action_table.md).
Bu çalışma yalnızca ayrı deneme kodu ve rapor ekler; üretim extraction kurallarını
ve çıktılarını değiştirmez. Görsel değerlendirme asistana aittir; insan onayı yoktur.

## Kapsam ve yöntem

Sayfalar: 625, 636, 645, 647; ek olarak üst üste iki şekil içeren 635 ve tam
genişlikte grafik içeren 654. İki iterasyon sınırında duruldu. Betiğin toplam
çalışması 19,788 saniye, yürütme tavanı 720 saniye; üçüncü yöntem/tur denenmedi.
Bu süre betiğin süresidir; raporlama ve görsel incelemeyi kapsamaz.

Kod: `scripts/probe_figure_regions.py`. Çalıştırma:

```powershell
.\.venv\Scripts\python.exe -B scripts/probe_figure_regions.py
```

1. **İlk yöntem:** `get_image_info()` ile görüntülerin sayfadaki yerleşim bbox'ları;
   alttaki gerçek altyazı ile konumsal eşleme ve bbox birleşimi. Önceki altyazı
   ikinci şekil için üst arama sınırı olur. Sağ sütundan başlayan altyazı sağ
   sütunla sınırlandırılır. Sayfa bazında manuel koordinat kullanılmaz.
2. **Tek düzeltme:** `get_drawings()` çizimlerinden altyazının en çok 20 pt üstünde
   biten, en az 120 × 70 pt olan uygun dış çerçeve seçilir. En büyük uygun
   çerçeve + altyazı birleşimine 1 pt pay eklenir. Taşan görüntü/gölge bbox'ları
   aday bölgeyi büyütmez; ayrıca kaydedilir. Çerçeve yoksa ilk yönteme dönülür.

Altyazı çapası, metin bloğunun başındaki `Figure N-N.` biçimidir. Gövde içindeki
`[Figure ...]` ve cümle içi atıflar çapa kabul edilmedi. Altı sayfada **7 gerçek
altyazı** kullanıldı; Figure içeren diğer **9 blok** çapa dışında kaldı. Bu basit
regex'in yeni belgelerde güvenilirliği ayrıca değerlendirilmelidir.

Değerlendirme için 625/636/645'te mevcut manuel bölgelerin blok üyeliği kullanıldı.
635/647/654'te görsel incelemeye dayanan asistan referans etiketleri ayrı fonksiyonda
tanımlandı; aday üretimine verilmedi. Bunlar insan etiketleri veya bağımsız test
seti değildir. Yöntem bu altı geliştirme örneğinde değerlendirildi.

## Sonuç: uyarı sayısı yerine ayrım ve koruma

| PDF | Gerçek şekil metin bloğu | İlk tur kaçan | İkinci tur kaçan | Yanlış kapsanan gövde (iki tur) | İkinci tur gövde sırası |
|---|---:|---:|---:|---:|---|
| 625 | 7 | 0 | 0 | 0 | Manuel ayrım ile aynı |
| 636 | 5 | 1 | 0 | 0 | Manuel ayrım ile aynı |
| 645 | 14 | 5 | 0 | 0 | Manuel ayrım ile aynı |
| 647 | 13 | 0 | 0 | 0 | `very` ardından `difficult`; arada şekil kalmıyor |
| 635 | 8 | 6 | 0 | 0 | İki şekil ayrılıyor, alt gövde sol–sağ okunuyor |
| 654 | 26 | 1 | 0 | 0 | Grafik gövdeden çıkıyor; kaynaklar sol–sağ okunuyor |

İlk turda 636'nın SHEL başlığı; 645'in eksen ve sağ açıklamaları; 635'in Actions /
Resources başlıkları ve listeleri; 654'ün `Accidents in Aviation` başlığı kaçtı.
635'te görüntü sadece simgeyi kapsadığından, liste alanını tahmin edemedi. 654'te
bir görüntü bbox'ı x=652,398'e kadar uzanıyor (sayfa genişliği 594); sayfaya kırpmak
başlığı kurtarmıyor. İkinci tur görünür dış çerçeveyi kullanarak bunları kapsadı.

Her iki turda her kaynak metin bloğu gövde/şekil/footer bölümlemesinde tam bir
kez korunuyor. Kısmi çakışmalar ilk turda 645'te 5, 635'te 1, 654'te 1; bu bloklar
atılmadan gövdede bırakılıyor. İkinci turda kısmi/çoklu bölge çakışması yok.
Burada korunan şey PDF'nin çıkarılabilir metin bloklarıdır; şeklin görsel anlamı
veya blok içi yazı sırası için başarı iddiası yoktur. 654'ün `TECHNICAL CAUSES`
etiketi hâlâ parçalıdır; bölge tespiti bu sorunu çözmez.

Gövde sırası metriği, referans şekil blokları çıkarıldıktan sonraki sol–sağ blok
sırasıyla karşılaştırmadır; tek başına anlam doğruluğu ölçütü değildir. Render'lar
da incelendi. 625'te `deployment of systems / and services`, 647'de
`very / difficult` devamında şekil bloğu kalmadığı ayrıca kontrol edildi.
Ham blok metinlerine normalizasyon uygulanmadı; deneme gövdesi kaynak satır
sonlarını korur ve üretim gövdesinin biçimlendirmesini değiştirmez.

## Manuel bölgelerle karşılaştırma

İkinci tur bbox'ları yuvarlatılmıştır; tam değerler JSON raporundadır.

| PDF | Mevcut manuel bbox | İkinci tur aday bbox | IoU | Metin bloğu üyeliği |
|---|---|---|---:|---|
| 625 | [50, 450, 546, 716] | [53, 451.210, 540.626, 714.537] | 0,973 | Aynı 7 blok |
| 636 | [300, 35, 546, 260] | [302, 43.000, 541.250, 252.619] | 0,906 | Aynı 5 blok |
| 645 | [50, 35, 546, 290] | [52.829, 44.643, 542.195, 282.757] | 0,921 | Aynı 14 blok |

IoU yardımcı geometri ölçüsüdür; asıl sonuç doğru blok üyeliği ve gövde sırasıdır.
Mevcut manuel bölgeler değiştirilmedi.

## Çizgi / kenar / dikdörtgen gürültüsü

Çok ince geometri `min(bbox genişliği, yüksekliği) ≤ 1 pt`; sayfa kenarına yakınlık
5 pt; tam sayfaya yakın dikdörtgen alanı sayfanın en az %90'ı olarak işaretlendi.
Çizim path'i ve içindeki doğru parçası düzeyindeki sayılar farklıdır.

| PDF | Çizim path sayısı | İnce bbox'lı path | İnce/kenar doğru parçası | Sayfa kenarı path | Tam sayfa dikdörtgen |
|---|---:|---:|---:|---:|---:|
| 625 | 11 | 1 | 5 | 0 | 0 |
| 636 | 12 | 1 | 5 | 0 | 0 |
| 645 | 85 | 1 | 159 | 0 | 0 |
| 647 | 62 | 12 | 56 | 0 | 0 |
| 635 | 42 | 0 | 45 | 0 | 0 |
| 654 | 109 | 4 | 287 | 0 | 0 |

Bunlar “gürültü” kararı değil, **olası gürültü işaretleri**. Bu örneklerde sayfa
kenarı veya tam sayfa dikdörtgen bulunmaması başka sayfalarda olmayacağı anlamına
gelmez. İnce doğrular silinmedi; çizim envanterinde tutuldu. Özellikle 645/654'te
eksen, grafik elemanı ve çerçeve çizgisi olabilirler. Çerçevenin stroke genişliği
0,5 pt diye elenmedi: ince stroke ile ince geometrik bbox aynı şey değildir.
Örneğin 636'nın 0,5 pt dış çerçevesi ikinci turda bölgeyi tamamlayan kanıttır.

Her çizim ve işaretli doğru parçasının bbox'ı, türü ve stroke genişliği sayfa
JSON'unda saklıdır. İkinci turda yeterli alanı olan çerçeveler çapa olarak seçildi;
küçük/ince çizgiler bölgeyi tek başına belirlemedi, bağlam olarak korundu.

## Üstüne çizilmiş örnekler

Kırmızı: aday bölge; yeşil: varsa mevcut manuel bölge. Her iki turun 12 render'ı
asistan tarafından incelendi; ikinci turda kaçan şekil metni/yanlış gövde kapsaması
görülmedi. Bu gözlem insan doğrulaması değildir.

| PDF | İlk yöntem | Düzeltme turu |
|---|---|---|
| 625 | [Görüntü](../audit/figure_region_probe/iteration_1_page_625.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_625.png) |
| 636 | [Görüntü](../audit/figure_region_probe/iteration_1_page_636.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_636.png) |
| 645 | [Görüntü](../audit/figure_region_probe/iteration_1_page_645.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_645.png) |
| 647 | [Görüntü](../audit/figure_region_probe/iteration_1_page_647.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_647.png) |
| 635 | [Görüntü](../audit/figure_region_probe/iteration_1_page_635.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_635.png) |
| 654 | [Görüntü](../audit/figure_region_probe/iteration_1_page_654.png) | [Görüntü](../audit/figure_region_probe/iteration_2_page_654.png) |

## Öneri ve koruma kontrolü

**Hibrit yaklaşım önerilir:** altyazı + çerçeve + görüntü yerleşimlerinden aday
öner, metin bloklarının ayrımını ve cümle devamını kontrol et, sayfa görüntüsünde
inceledikten sonra manuel override olarak kabul et. Yalnızca görüntü bbox'ları
yeterli değil. Altı çerçeveli örnekte başarılı ikinci turu tüm bölüme otomatik
uygulamak için kanıt yetersiz; çerçevesiz, altyazısız veya karmaşık şekillerde
manuel inceleme gerekir. Genel detektör geliştirmeyi burada durduruyoruz.

İleride onaylanan düzeltmede dahi şekil içi sıra, grafik etiketleri ve olay–neden
ilişkileri ayrı tutulmalı. 651'in footer toleransı ve 655'in beş çifti bu denemede
ele alınmadı/değiştirilmedi.

Başlangıç git durumu, mevcut diff ve **115 dosyanın SHA-256 değerleri**
`audit/figure_region_probe/initial_state.json` içinde kaydedildi. Eski toplu
extraction değişiklikleri korunmuştur. Deneme sonunda korunan dosyalarda değişiklik
yok. `summary.json` iki turun ölçümlerini, sayfa JSON'ları bbox/metin/envanteri
tutar. `validation.json` ek bütünlük ve cümle devamı kontrollerini içerir.
Bu turda yalnızca iki yeni rapor, deneme betiği ve ayrı audit deneme artefaktları
eklendi. Normalizasyon, chunking, insan onayı, commit ve push yapılmadı.
