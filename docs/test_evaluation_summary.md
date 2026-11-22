# AeroDoc test değerlendirmesi

[Sabit test seti](../eval/test_questions.json) · `test-v0.1` · corpus `v0.1` · 18 cevaplanabilir, 6 cevaplanamaz soru.

SHA-256 · `ff6e07e27748bfc57af22b3fdb153ee5b38289fb431a158b673e5d9022bc056c`

| Çalıştırma | Sonuç |
| --- | --- |
| `20261122T093333Z-8b2c8ea3` | BM25 ve BGE retrieval tamamlandı. Cevap üretiminde T01 bağlantı hatası verdi, T02 bütçe sınırında durdu ve kalan 22 soru çalıştırılmadı. |
| `20261122T094126Z-3ecd1ad3` | BM25 k=5 ve GPT-6 Luna ile 17 `answered`, 7 `insufficient_evidence`. Sağlayıcı hatası yok. |

## Development baseline

[Development seti](../eval/dev_questions.json) sekiz cevaplanabilir ve iki
cevaplanamaz soru içerir. k=5 için BM25'in üç retrieval metriği de %100,00.
BGE için page_hit %87,50, evidence_recall %75,00 ve all_evidence_hit %75,00.
Retrieval paydası sekiz cevaplanabilir sorudur. Ayrı development cevap
çalıştırmasında sekiz `answered` ve iki `insufficient_evidence` kaydedildi.
Bu sonuçlar sabit test setinin metriklerine dahil değildir.

## Sabit test setinde retrieval

Payda 18 cevaplanabilir soru. `page_hit` en az bir kaynak sayfanın getirilmesini ölçer. `evidence_recall`, getirilen chunk’ların kapsadığı kanıt birimlerinin soru bazında makro ortalamasıdır. `all_evidence_hit`, tüm kanıt birimleri getirilen soruların oranıdır.

| Yöntem | k | page_hit | evidence_recall | all_evidence_hit |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 1 | %88,89 | %67,59 | %61,11 |
| BM25 | 3 | %94,44 | %83,33 | %77,78 |
| BM25 | 5 | %100,00 | %94,44 | %94,44 |
| BGE | 1 | %72,22 | %56,48 | %50,00 |
| BGE | 3 | %88,89 | %75,00 | %72,22 |
| BGE | 5 | %94,44 | %88,89 | %88,89 |

**T14** cevaplanabilir. BM25 k=5 doğru PDF sayfasını (639, basılı 14-16)
getirdi, ancak yorgun birinin kendini uyanık hissedebileceğini belirten cümle
ilk beş chunk’ta bulunmadı. Cevap üretimi `insufficient_evidence` döndürdü.
Cevaplanamaz T19–T24’ün tamamı da `insufficient_evidence` döndürdü.

## Maliyet kaydı

Tamamlanan çalıştırmada kullanım temelli tahmin test için **0,005499625 USD**
ve bağlantı probu için **0,00003025 USD**, toplam **0,005529875 USD**.
Yerel SQLite defteri ayrıca önceki belirsiz çağrıdan kalan
**0,2634 USD** rezervasyon tutarını korudu. Bu rezervasyon yerel bütçede yer
tutar ve kullanım temelli toplama dahil değildir. Bu tutarlar sağlayıcı
faturasıyla doğrulanmadı.

## Asistan incelemesi

ChatGPT’nin sağladığı metin karşılaştırması, 17 cevabın temel bilgilerinin referanslarla uyumlu olduğunu ve atıf metinlerinde belirgin çelişki veya desteksiz temel iddia görülmediğini bildiriyor. T05’te iki kişi şartı doğrudan destekleniyor. “Biri yapar, diğeri denetler” ifadesi duplicate inspection bağlamından makul bir çıkarım. T13 ve T17’de işaretlenen ek ifadeler atıf metinlerinde doğrudan destekleniyor.

Karşılaştırma bu küçük, kaynak metinden hazırlanmış setteki mevcut model cevaplarını, referansları ve atıf chunk’larını kapsar. Doğruluk, eksiksizlik ve anlamsal kaynak desteği için insan inceleme alanları `pending`. Ayrı `assistant_review` kaydı ve ayrıntılı çalışma çıktıları yerel `audit/test_runs/` dizininde tutulur.
