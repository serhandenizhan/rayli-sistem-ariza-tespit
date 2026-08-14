# İstanbul Raylı Sistem — Arıza Tespiti ve Canlı İzleme

Raylı sistemlerde (tren/vagon/dingil) çok sensörlü verilerden arıza tespiti ve sınıflandırması
için uçtan uca bir proje. **Gerçek İstanbul metro ağı** (İBB Açık Veri Portalı) üzerinde sentetik
sensör verisi üretiminden, çok görevli 1D-CNN + LSTM modelinin eğitilmesine, canlı akış
simülasyonuna ve gerçek zamanlı ağ haritalı dashboard'a kadar tüm adımları içerir.

Öne çıkanlar:

- **Gerçek ağ**: 20 işletmedeki hat, 265 gerçek istasyon, gerçek koordinatlar; trenler M2, M4,
  M1A, M5, M7, M3, M8, T1 hatlarında gerçek istasyon dizisinde işliyor
- **Gerçekçi sefer**: istasyonlar arası hızlanma/frenleme, istasyonda bekleme, terminalde dönüş
- **Çok görevli model**: arıza tipi (6 sınıf) + arıza şiddeti (4 seviye) tek gövdeden
- **Sızıntısız doğrulama**: akan veride etiket yok; skorlama ayrı cevap anahtarıyla, tahminden sonra
- **Histerezis**: tek tick'lik sınıf sıçramaları alarm üretmez
- **Canlı harita**: trenler gerçek hatlar üzerinde, tahmin rengiyle hareket eder
- **55 birim testi**: arayüzde okunabilir sonuç paneliyle

## Klasör yapısı

```
rayli_ariza_tespiti/
├── data/                       # üretilen veri setleri
│   ├── rayli_sistem_tum_veri.csv
│   ├── rayli_sistem_train.csv
│   ├── rayli_sistem_test.csv
│   ├── rayli_sistem_test_akis.csv            # ETİKETSİZ test verisi (canlı akışa verilen)
│   ├── rayli_sistem_test_cevap_anahtari.csv  # cevap anahtarı (yalnızca doğrulama için)
│   ├── istanbul_metro_agi.json               # gerçek hat/istasyon ağ modeli (İBB verisi)
│   └── ray_kusur_noktalari.json              # hat üzerindeki sabit ray kusuru konumları
├── docs/
│   └── rayli_sistem_veri_semasi.md   # veri şeması: kolon açıklamaları, sınıf mantığı
├── src/
│   ├── istanbul_metro_agi.py   # İBB açık verisinden GERÇEK metro ağı modeli
│   ├── rayli_veri_uret.py      # sentetik veri üretim scripti (gerçek ağ üzerinde)
│   ├── rayli_model.py          # model mimarisi (CNNLSTM) + paylaşılan sabitler
│   ├── rayli_veri_utils.py     # veri yükleme / sekans (pencere) oluşturma yardımcıları
│   ├── rayli_dl_egitim.py      # modeli SIFIRDAN eğitip test eden script
│   ├── rayli_tahmin.py         # kayıtlı modeli YENİDEN EĞİTMEDEN yükleyip tahmin üreten script
│   ├── rayli_etiketsiz_uret.py # test setini etiketsiz akış + cevap anahtarı olarak ayırır
│   ├── rayli_canli_akis_sunucu.py  # canlı akış simülasyonu + SSE API (FastAPI)
│   └── rayli_kafka.py          # Kafka üretici/tüketici adaptörü (opsiyonel kaynak)
├── testler/                    # pytest birim testleri (55 test)
├── web/                        # Next.js (React) canlı izleme dashboard'u + ağ haritası
├── calistir.sh                 # uçtan uca çalıştırma: kurulum -> eğitim -> akış -> arayüz
├── testleri_calistir.sh        # testleri çalıştırır, results/test_ozeti.json üretir
├── model/
│   └── rayli_cnn_lstm_model.pt # eğitilmiş model ağırlıkları + ölçekleyici bilgisi
├── results/
│   ├── confusion_matrix.png / .csv
│   ├── training_curves.png
│   ├── egitim_ozeti.json       # dashboard'ın okuduğu makine-okunur eğitim özeti
│   └── test_classification_report.txt
├── requirements.txt
└── README.md
```

## Hızlı başlangıç (tek komut)

```bash
./calistir.sh
```

Bu komut sırasıyla: sanal ortamı kurar → sentetik veriyi hazırlar → **modeli sıfırdan eğitir**
(~15 sn) → test setinin etiketsiz akış kopyasını ve cevap anahtarını üretir → canlı akış API'sini
(`:8000`) başlatır → Next.js dashboard'unu (`:3000`) açar. Tarayıcıdan
<http://localhost:3000> adresine gidin.

Seçenekler:

```bash
./calistir.sh --egitmeden     # mevcut checkpoint ile başlat (eğitimi atla)
./calistir.sh --hiz 10        # simülasyonu 10x hızlandır (1x = gerçek zamanlı, 2 sn/tick)
./calistir.sh --veri-uret     # sentetik veriyi de yeniden üret
./calistir.sh --kor-mod       # cevap anahtarını arayüze hiç gönderme (tam kör demo)
```

## Kurulum (elle)

```bash
pip install -r requirements.txt
```

## Kullanım

Veri setini yeniden üretmek isterseniz (mevcut `data/` klasöründekiler zaten hazır, tekrar
çalıştırmak isteğe bağlıdır — aynı seed ile aynı sonucu üretir):

```bash
cd src
python rayli_veri_uret.py
```

Modeli sıfırdan eğitmek ve test etmek için:

```bash
cd src
python rayli_dl_egitim.py
```

Bu komut `data/` altındaki train/test CSV'lerini okur, modeli eğitir, `model/` altına ağırlıkları
kaydeder ve `results/` altına confusion matrix, eğitim eğrileri ile test raporunu yazar.

**Proje, önceden eğitilmiş model (`model/rayli_cnn_lstm_model.pt`) ile birlikte geldiği için
eğitimi tekrar çalıştırmadan da doğrudan kullanılabilir durumdadır.** Sadece tahmin/değerlendirme
görmek isterseniz:

```bash
cd src
python rayli_tahmin.py            # test setinin tamamı için sınıflandırma raporu
python rayli_tahmin.py --n 20     # ilk 20 sekans için satır satır gerçek/tahmin karşılaştırması
```

## Veri seti özeti

Sentetik olarak üretilmiş, 3 tren × 4 vagon × 2 dingil (24 zaman serisi), her biri 50 dakikalık,
2 saniyelik pencerelerle örneklenmiş çok sensörlü veri (titreşim, akustik, sıcaklık, elektriksel,
hız/yük/konum). Ayrıntılı kolon açıklamaları `docs/rayli_sistem_veri_semasi.md` içinde.

6 sınıf: `normal`, `wheel_flat` (teker düzlüğü), `bearing_fault` (rulman arızası),
`brake_fault` (fren arızası), `motor_fault` (motor arızası), `rail_crack` (ray çatlağı).

Train/test bölmesi **kronolojik** (rastgele değil): ilk %80 zaman dilimi train, son %20'si test —
böylece veri sızıntısı (data leakage) önlenir ve gerçek canlı akış senaryosuna uygun bir
değerlendirme yapılır. Her iki sette de tüm sınıflar temsil edilecek şekilde bazı arıza
bölümleri kasıtlı olarak (dedicated episodes) yerleştirilmiştir.

## Model

`src/rayli_dl_egitim.py` bir **1D-CNN + LSTM** sekans sınıflandırıcısı eğitir: her dingil için
ardışık 10 pencere (20 saniyelik geçmiş) girdi olarak verilir, model bu geçmişe bakarak dizinin
son adımındaki arıza sınıfını tahmin eder. Bu tasarım, canlı akış (streaming) senaryosuna
doğrudan uyar: gerçek zamanlı sistemde son 20 saniyelik pencere sürekli kayar ve model her yeni
örnekte tahminini tazeler.

Sınıf dengesizliği `CrossEntropyLoss` içinde ters frekans ağırlıklandırmasıyla ele alınmıştır.
Doğrulama (validation), her dingilin kendi train zaman diliminin son %15'inden, sınır aşımı
olmadan ayrı pencerelerle oluşturulur; final değerlendirme ise tamamen ayrı, kronolojik olarak
sonraki test setinde yapılır.

### Çok görevli (multi-task) yapı

Tek gövde (CNN+LSTM), iki çıkış başlığı: **arıza tipi** (6 sınıf) ve **arıza şiddeti**
(none/mild/moderate/severe). Şiddet, operasyonda "ne kadar acil?" sorusunu yanıtlar ve toplam
kayba 0.4 ağırlıkla katılır (asıl görev tip sınıflandırmasıdır).

### Test sonuçları (mevcut eğitimden)

| Görev | Accuracy | Macro F1 |
|---|---|---|
| Arıza tipi | %98.7 | 0.9679 |
| Arıza şiddeti | %95.5 | 0.8247 |

`rail_crack` 0.974, `normal` 0.993, `bearing_fault` 0.986 F1; en zayıf sınıf `motor_fault`
(0.926). Ayrıntılar `results/test_classification_report.txt` ve `results/confusion_matrix.csv`
içinde.

## Gerçek İstanbul metro ağı

Hat güzergâhları, istasyon adları ve koordinatları **İBB Açık Veri Portalı**'ndaki resmi
Metro İstanbul veri setlerinden gelir:

- *Raylı Sistem İstasyon Noktaları Verisi* (GeoJSON) — 343 istasyon noktası
- *Raylı Sistem Hatları Vektör Verisi* (GeoJSON) — hat güzergâh geometrisi

`src/istanbul_metro_agi.py` bunlardan `data/istanbul_metro_agi.json` üretir. Kaynak veride
istasyonların hat üzerindeki **sırası bulunmadığı** için sıra, "toplam uzunluğu en kısa açık yol"
problemi olarak çözülür (açgözlü başlangıç + 2-opt iyileştirme). Sonuç gerçek sırayla örtüşür —
örneğin M4: Kadıköy → Ayrılık Çeşmesi → Acıbadem → Ünalan → Göztepe → … → Sabiha Gökçen
(bu, `testler/test_metro_agi.py` içinde test edilir).

Ham GeoJSON'lar `data/harici/` altında önbelleğe alınır (git'e girmez);
`python istanbul_metro_agi.py --indir` ile yeniden indirilebilir.

## Canlı akış simülasyonu ve dashboard

### Etiketli / etiketsiz ayrımı

Canlı akış gerçekçi olsun diye test seti ikiye ayrılır (`src/rayli_etiketsiz_uret.py`):

| Dosya | İçerik | Kim görür |
|---|---|---|
| `data/rayli_sistem_test_akis.csv` | sadece `sample_id` + sensörler, **etiket yok** | akışa verilir, modele girer, arayüze gider |
| `data/rayli_sistem_test_cevap_anahtari.csv` | `sample_id` → `fault_type`, `fault_severity` | yalnızca sunucu, **tahmin üretildikten sonra** skorlama için |

Sahadaki gerçek durumda sensör paketinde arıza etiketi bulunmaz; etiketi akıştan fiziksel olarak
çıkarmak sızıntının (leakage) yapısal olarak imkânsız olduğunu gösterir ve doğrulamayı ayrı bir
adıma dönüştürür. `--kor-mod` ile cevap anahtarı arayüze hiç gönderilmez (tam kör demo).

### Sunucu

```bash
cd src
python rayli_canli_akis_sunucu.py                # http://127.0.0.1:8000
python rayli_canli_akis_sunucu.py --hiz 10       # 10x hızlı
python rayli_canli_akis_sunucu.py --konsol       # arayüz olmadan konsola akış
```

Sunucu, etiketsiz akış verisini zaman damgasına göre tick tick yayınlar (1x = 2 sn/tick), her
dingil için 10 örneklik kayan pencereyi tutar, pencere dolunca 24 dingili tek batch'te modele
sokar ve sonucu SSE (`/api/akis`) ile yayınlar.

| Uç nokta | Açıklama |
|---|---|
| `GET /api/meta` | sınıflar, dingiller, toplam tick, eğitim özeti |
| `GET /api/akis` | SSE canlı akış (her tick'te bir olay) |
| `GET /api/durum` / `GET /api/olaylar` | anlık durum / alarm günlüğü |
| `POST /api/kontrol` | `{"action":"play"\|"pause"\|"reset"\|"speed","value":10}` |

### Dashboard (Next.js + React)

```bash
cd web && npm install && npm run dev     # http://localhost:3000
```

Panolar:

- **Kontrol barı**: duraklat/devam/baştan, hız (1x–50x), **histerezis** (1–8 tick) ve
  **kör mod** — hepsi çalışma anında değiştirilebilir
- **Canlı ağ haritası**: gerçek koordinatlarla İstanbul raylı sistem ağı; trenler gerçek hatlar
  üzerinde hareket eder, ikon rengi modelin tahminidir, ray kusurları üçgenle işaretlidir
- **KPI'lar**: aktif alarm, baskın arıza tipi, canlı tip doğruluğu, canlı şiddet doğruluğu
- **Dingil kartları**: hat bazında gruplanmış, şiddet rozetli, histerezis bekleme göstergeli
- **Sensör akışı**: seçili dingil için çoklu sensör grafiği + model tahmin şeridi
- **Model çıktısı**: iki başlığın (tip + şiddet) softmax dağılımı
- **Alarm günlüğü**: gerçek istasyon adlarıyla, yalnızca yerleşik (histerezis sonrası) değişimler
- **Canlı doğrulama**: cevap anahtarına karşı akan karmaşıklık matrisi ve sınıf metrikleri
- **Birim testleri**: pytest sonuçları, açıklamalarıyla birlikte
- **Eğitim özeti**: loss/accuracy eğrileri ve offline referans skorları

Canlı akış sonunda ölçülen skorlar offline test raporuyla örtüşür (tip ~%98.7, şiddet ~%95.5) —
canlı hattın modeli ve ölçeklemeyi doğru kurduğunun uçtan uca kanıtı.

## Testler

```bash
./testleri_calistir.sh              # 55 test
./testleri_calistir.sh -k metro     # sadece ağ testleri
```

Testler; veri şemasını ve **sızıntı korumalarını** (akış dosyasında etiket olmaması, kör modda
cevap anahtarının paketlere sızmaması), gerçek metro ağının doğruluğunu (istasyon sırası,
koordinatların İstanbul içinde olması), model checkpoint'ini ve canlı akış motorunu (histerezis
davranışı, doğruluk regresyon eşiği) doğrular. Sonuçlar `results/test_ozeti.json`'a yazılır ve
dashboard'daki **Birim Testleri** panelinde görünür.

## Kafka ile besleme (opsiyonel)

Akış kaynağı CSV yerine bir mesaj kuyruğu da olabilir:

```bash
pip install kafka-python
python src/rayli_kafka.py --uret --hiz 20          # etiketsiz akışı topic'e yayınla
python src/rayli_canli_akis_sunucu.py --kaynak kafka
```

Etiketler Kafka'ya da gönderilmez — sızıntı ayrımı kaynaktan bağımsız korunur.
