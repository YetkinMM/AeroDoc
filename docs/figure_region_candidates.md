# Şekil bölgesi adayları: inceleme paketi

Bu rapor adayların henüz kabul edilmediği tarihsel aşamayı anlatır. Sonraki kullanıcı
onayları yalnız `region_boundary_only` kapsamında alınmıştır; güncel 37 tekil bölge
ve kapsamı Git'teki `config/figure_regions.json` içindedir. Güncel uygulama için
[sabit bölge extraction raporuna](approved_region_extraction.md) bakın. Aşağıdaki
pending/uygulanmadı ifadeleri raporun üretildiği aşamaya aittir. Şekil içi sıra ve
anlam ilişkileri onaylanmamıştır; görsel/audit bağlantıları yerel, Git dışı kanıttır.

Önce açılacak overlay'ler:

- [636: SHEL / otomatik ve manuel](../audit/figure_region_candidates/page_636.overlay.png)
- [635: iki ayrı şekil](../audit/figure_region_candidates/page_635.overlay.png)
- [647: sağ üst soru listesi](../audit/figure_region_candidates/page_647.overlay.png)
- [654: grafik](../audit/figure_region_candidates/page_654.overlay.png)

Kırmızı `P<sayfa>-A<no>` otomatik aday, yeşil `P<sayfa>-M<no>` mevcut manuel
koordinattır. Etikette Figure kimliği de bulunur. Yeşil renk insan doğrulaması veya
kabul anlamına gelmez. Bir sayfada birden fazla bölge bağımsız kimlikle gösterilir.

## Üretilen materyal

Değiştirilmemiş `probe_figure_regions.candidates(..., iteration=2)` yöntemi
`scripts/build_figure_region_candidates.py` üzerinden 624–655'in tamamına uygulandı.
Yeni algoritma/iyileştirme turu yapılmadı. Manuel koordinatlar aday üretimine
karıştırılmadı; yalnızca karşılaştırma ve yeşil overlay için kopyalandı.

`audit/figure_region_candidates/` altında:

- 32 adet `page_<PDF>.overlay.png`.
- `figure_regions.candidates.json`: **37 otomatik aday + 3 manuel karşılaştırma
  kaydı**, toplam 40. Tüm kayıtlar `review_status=pending`, `accepted=false`.
  Figure 14-1–14-37 kimlikleri bulunuyor; bu, bölgelerin doğru kapsandığı anlamına
  gelmez. 624, 632 ve 639'da otomatik aday yok.
- `checklist.md` / `checklist.json`: 32 sayfanın basılı etiketi, aday sayıları,
  Figure kimlikleri, manuel bbox/blok farkları, belirsizlik ve gerekli kontrol,
  overlay yolu.
- `diagnostics.json`: kaynak metin blokları, görüntü yerleşimleri, çizim bbox'ları,
  olası ince/kenar/tam sayfa geometri işaretleri ve kaynak blok kimlikleri.
- `agent_checks.json`: asistanın yaptığı ayrı kontroller; kayıtları kabul etmez.
- `initial_state.json` ve `preservation_check.json`: başlangıç git durumu ve
  korunan 147 dosyanın hash denetimi.

Aday dosyası belge kimliği, kaynak PDF SHA-256, kaynak URL, PyMuPDF 1.26.6,
aday üretici sürümü, değişmeden kullanılan detektör kodunun hash'i ve config hash'i
taşır. Bbox birimi PDF point, başlangıç sol üst, sıra `[x0,y0,x1,y1]`.
Yeni kayıtlar pending üretildi; asistan notları eklendikten sonra da pending kaldı.
`human_verified` yazılmadı; mevcut manuel koordinatlar insan onayına yükseltilmedi.

## Öncelikli bulgular

| PDF | Sonuç / gereken kontrol |
|---|---|
| 625, 636, 645 | İkinci tur denemesiyle bbox'lar birebir aynı. Otomatik ve manuel bölgelerin metin bloğu üyeliği aynı; geometri farkları checklist'te. Şekil iç sırası ayrıca açık. |
| 635 | P635-A01 = 14-14, P635-A02 = 14-15; iki bölge ayrık. Önceki asistan referansındaki 8 şekil/altyazı bloğu kapsanıyor, gövde kapsaması yok. |
| 647 | P647-A01, 12 soru bloğu ve altyazıyı kapsıyor. Varsayımsal bölge çıkarımından sonra `very` ile `difficult` blokları ardışık; mevcut gövde dosyası değiştirilmedi. |
| 654 | P654-A01, referanstaki 26 grafik/altyazı bloğunu kapsıyor; etiketler bölge dışında kalmıyor. TECHNICAL CAUSES'ın kaynak metinde parçalanması çözülmedi. |
| 655 | P655-A01, beş olay–neden çifti ve altyazıyı kapsıyor (21 footer dışı blok). `intended_handling=preserve_in_body`; beş çiftin tam metni ve doğru sırası mevcut gövdede korunmalı. Hiçbir gövde silme/eleme önerisi yok. |
| 653 | **Manuel kontrol öncelikli.** 14-32 / P653-A02 ve 14-35 / P653-A04 yalnızca altyazıyı kapsıyor. 14-32'nin 4 olay/neden bloğu ve 14-35'in 25 iş kartı bloğu adayların dışında. Algoritmanın sayfadaki önceki altyazıyı sütun ayrımı olmadan üst arama sınırı yapması bu düzende yetersiz. Bölgeler düzeltilmedi/kabul edilmedi. |
| 631 | Üç şekil var; A kimlikleri altyazıların y konumuna göre verildiğinden Figure numaraları sayısal sırada değil. Eşlemeyi `figure_id` ile kontrol et. |
| 624, 632, 639 | Aday yok. 632/639 görüntülerinde gövde düzeni görüldü; görüntü ve çizim envanteri boş. Aday yokluğu otomatik insan doğrulaması değildir. |

Yalnızca belirtilen overlay'ler bu turda asistan tarafından görüntülendi
(635, 636, 647, 654, 655, 653, 632, 639, 631). Diğer sayfalarda otomatik envanter ve
önceki inceleme kanıtları var; bu paketin tüm sayfaları insan incelemesine açıktır.
37 adayın tümü birbirinden ayrık olsa da bu doğru şekil kapsamı garantisi değildir.

İnce çizgiler, grafik eksenleri ve şekil çerçeveleri körlemesine elenmedi. Önceki
yöntem aynı kaldı: ince/sayfa kenarı/tam sayfa işaretleri yalnızca tanı verisidir.
Stroke inceliği çerçeveyi geçersiz kılmaz. Bbox taşmaları, fallback/yalnız altyazı
bölgeleri ve uzun metin içeren kutular checklist'te ayrı kontrol ister.

## Kabul edilmiş bölge dosyasına geçiş — henüz uygulanmadı

Gelecekte kullanıcı tarafından kabul edilen kayıtlar ayrı
`config/figure_regions.json` dosyasına alınmalı; pending aday dosyası extraction
girdisi yapılmamalı. Kabul kararı, asistanın `agent_reviewed` kontrolünden ayrı
tutulmalı. İnsan onayı ancak kullanıcının açık onayıyla kaydedilmeli.

Extraction bu dosyayı yükleyerek sayfa başına **çoklu kabul edilmiş bbox** okumalı;
çalışma sırasında görüntü/çizim tespiti yapmamalı. Dosya düzeyindeki `document_id`
ve özellikle **`source_sha256` gerçek PDF hash'iyle eşleşmeli**; uyuşmazlıkta
çalışma durmalı, aday tespitine veya başka baskının koordinatlarına sessiz dönüş
olmamalı. Sayfa sınırları, koordinat birimi ve bölgeler arası çakışmalar da
doğrulanmalı.

`separate_figure` kabul edilen metni metadata/bloklarıyla saklar; kısmi kesişen
bloklar atılmadan incelemeye gider. `preserve_in_body` gövdeden çıkarmayı engeller;
özellikle 655'in beş olay–neden çiftinin sırası ve retrieval erişimi korunmalı.
Bu değişiklikler henüz uygulanmadı; `config/figure_regions.json` oluşturulmadı.

Mevcut 32 sayfanın 670 kaynak metin bloğu tanı envanteriyle eşleşiyor. Korunan
147 dosyada değişiklik yok; extraction, eski audit çıktıları, footer toleransı,
geliştirme seti ve insan inceleme kayıtları korunmuştur. Bu adımda yalnızca ayrı
aday üretici kodu, bu rapor ve yeni aday materyalleri eklendi. Normalizasyon,
chunking, commit ve push yapılmadı.
