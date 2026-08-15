# İstanbul Raylı Sistem — Arıza Tespiti ve Canlı İzleme

Raylı sistemlerde (tren/vagon/dingil) çok sensörlü verilerden arıza tespiti ve sınıflandırması
için uçtan uca bir proje. **Gerçek İstanbul metro ağı** (İBB Açık Veri Portalı) üzerinde sentetik
sensör verisi üretiminden, çok görevli 1D-CNN + LSTM modelinin eğitilmesine, canlı akış
simülasyonuna ve gerçek zamanlı ağ haritalı dashboard'a kadar tüm adımları içerir.

Öne çıkanlar:

- **Gerçek ağ**: 19 hat, 216 gerçek istasyon, gerçek koordinatlar; **Metro İstanbul
  işletmesindeki 17 yolcu hattının tamamında** tren işliyor (M1A, M1B, M2, M3, M4, M5, M6, M7,
  M8, M9, T1, T3, T4, T5, F1, F2, F4) — 24 tren, 96 dingil (uzun hatlarda 2 tren).
  Marmaray ve M11 kapsam dışıdır (işletmecisi Ulaştırma Bakanlığı, Metro İstanbul değil)
- **Gerçekçi sefer**: istasyonlar arası hızlanma/frenleme, istasyonda bekleme, terminalde dönüş
- **Çok görevli model**: arıza tipi (6 sınıf) + arıza şiddeti (4 seviye) tek gövdeden
- **Sızıntısız doğrulama**: akan veride etiket yok; skorlama ayrı cevap anahtarıyla, tahminden sonra
- **Histerezis**: tek tick'lik sınıf sıçramaları alarm üretmez
- **Belirsizlik farkındalığı**: softmax entropisi eşiği aşarsa tahmin "belirsiz" sayılır ve
  alarm üretmez — modelin kararsız kaldığı anlar operatöre yansımaz
- **Alarm önceliklendirme**: şiddet + süre + güven birleşiminden 0-1 öncelik skoru
- **Kalıcılık**: alarmlar ve metrikler SQLite'a yazılır, geçmişe dönük sorgulanabilir
- **Canlı harita**: gerçek İstanbul coğrafyası (kıyı çizgisi, Boğaz, Haliç, Adalar) üzerinde
  trenler gerçek hatlarda, tahmin rengiyle hareket eder
- **Sekmeli arayüz**: canlı izleme / dingiller / doğrulama / geçmiş / testler
- **İnteraktif harita**: fare tekerleğiyle yakınlaştırma, sürükleyerek kaydırma, ilçe adları
- **Denetimsiz anomali tespiti**: autoencoder, 6 sınıflık modeli tamamlayan "bilinmeyen anomali" katmanı
- **Kalıcılık + Docker**: SQLite alarm geçmişi, hafif `docker-compose` (API + web)
- **86 birim testi**: arayüzde okunabilir sonuç paneliyle

## Klasör yapısı

```
rayli_ariza_tespiti/
├── data/                       # üretilen veri setleri
│   ├── rayli_sistem_train.csv
│   ├── rayli_sistem_test.csv
│   ├── rayli_sistem_test_akis.csv            # ETİKETSİZ test verisi (canlı akışa verilen)
│   ├── rayli_sistem_test_cevap_anahtari.csv  # cevap anahtarı (yalnızca doğrulama için)
│   ├── istanbul_metro_agi.json               # gerçek hat/istasyon ağ modeli (İBB verisi)
│   ├── istanbul_cografya.json                # harita zemini: ilçe sınırları (geoBoundaries)
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
API_PORT=8001 WEB_PORT=3001 ./calistir.sh   # 8000/3000 meşgulse alternatif port
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
| Arıza tipi | %99.2 | 0.9804 |
| Arıza şiddeti | %96.5 | 0.85 |

`bearing_fault` 0.997, `rail_crack` 0.990, `normal` 0.995 F1; en zayıf sınıf `motor_fault`
(0.924). Sınıf dengesizliği, karekök yumuşatmalı ters frekans ağırlığıyla ele alınır — tam
"balanced" ağırlık precision'ı ciddi biçimde düşürüyordu. Ayrıntılar `results/test_classification_report.txt` ve `results/confusion_matrix.csv`
içinde.

## Gerçek İstanbul metro ağı

Hat güzergâhları, istasyon adları ve koordinatları **İBB Açık Veri Portalı**'ndaki resmi
Metro İstanbul veri setlerinden gelir:

- *Raylı Sistem İstasyon Noktaları Verisi* (GeoJSON) — 343 istasyon noktası
- *Raylı Sistem Hatları Vektör Verisi* (GeoJSON) — hat güzergâh geometrisi

Harita zemini (kara parçası ve kıyı çizgisi) ise **geoBoundaries** ADM2 ilçe sınırlarından
gelir (Open Data Commons ODbL 1.0). Denizler ayrı bir veri değildir — karanın çizilmediği yerdir;
Boğaz, Haliç, Marmara ve Karadeniz bu şekilde ortaya çıkar.

`src/istanbul_metro_agi.py` bunlardan `data/istanbul_metro_agi.json` ve
`data/istanbul_cografya.json` üretir. Kaynak veride
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
- **Canlı ağ haritası**: gerçek İstanbul coğrafyası (ilçe sınırları ve adları, kıyı çizgisi,
  Boğaz) üzerine çizilen raylı sistem ağı; trenler gerçek hatlar üzerinde hareket eder, ikon
  rengi modelin tahminidir, ray kusurları üçgenle işaretlidir.
  **Fare tekerleğiyle yakınlaştırma, sürükleyerek kaydırma**; 4x üzerinde istasyon adları
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
./testleri_calistir.sh              # 86 test
./testleri_calistir.sh -k metro     # sadece ağ testleri
```

Testler; veri şemasını ve **sızıntı korumalarını** (akış dosyasında etiket olmaması, kör modda
cevap anahtarının paketlere sızmaması), gerçek metro ağının doğruluğunu (istasyon sırası,
koordinatların İstanbul içinde olması), model checkpoint'ini ve canlı akış motorunu (histerezis
davranışı, doğruluk regresyon eşiği) doğrular. Sonuçlar `results/test_ozeti.json`'a yazılır ve
dashboard'daki **Birim Testleri** panelinde görünür.

## Denetimsiz anomali tespiti (autoencoder)

6 sınıflık denetimli sınıflandırıcı, dağılım dışı (out-of-distribution) bir girdide bile
yüksek güvenle yanlış sınıf söyleyebilir — bilinen bir sinir ağı problemi. Bunu tamamlamak
için `src/rayli_anomali.py` + `src/rayli_anomali_egitim.py`, **sadece `normal` verilerle
eğitilmiş küçük bir autoencoder** ekler:

```bash
cd src && python rayli_anomali_egitim.py
```

Eşik, ayrılan bir doğrulama biriminin yeniden yapılandırma hatasının 99. yüzdelik dilimidir.
Mevcut sonuç: normal pencerelerde **%1.4 yanlış alarm**, bilinen 6 arıza tipini ortalama
**%86.6** oranında "anomali" olarak yakalıyor.

En ilginç durum arayüzde **🔍 bilinmeyen anomali** rozetiyle işaretlenir: denetimli model
"normal" diyor ama bu katman aynı fikirde değil — "bu normal değil, ama ne olduğunu da
bilmiyorum" sinyali. Dürüstlük notu: bu sentetik veri setinde yalnızca 6 belgelenmiş arıza
tipi var; mekanizmanın asıl değeri, veri setinde hiç bulunmayan gerçekten yeni bir arıza
tipiyle karşılaşıldığında ortaya çıkar.

## Docker (hafif — mikroservis değil)

```bash
docker compose up --build
```

Yalnızca iki servis: **API** (FastAPI/PyTorch) ve **web** (Next.js). Kafka/Redis/Celery
bilinçli olarak yok — bu projede tek bir simüle akış var, eş zamanlı yük veya bağımsız
ölçeklenme ihtiyacı yok; o ayrım gerçek bir faydaya değil teorik bir beklentiye hizmet ederdi.
Kafka'ya geçmek istenirse `src/rayli_kafka.py` zaten opsiyonel bir adaptör olarak duruyor.

```bash
HIZ=10 KOR_MOD=1 docker compose up --build   # hız/kör mod ortam değişkeniyle ayarlanabilir
```

> **Doğrulandı**: `docker compose up --build` gerçekten çalıştırılıp test edildi (build, healthcheck,
> proxy, SQLite kalıcılığı — konteyner yeniden başlatıldığında alarm geçmişi korunuyor).

## Kafka ile besleme (opsiyonel)

Akış kaynağı CSV yerine bir mesaj kuyruğu da olabilir:

```bash
pip install kafka-python
python src/rayli_kafka.py --uret --hiz 20          # etiketsiz akışı topic'e yayınla
python src/rayli_canli_akis_sunucu.py --kaynak kafka
```

Etiketler Kafka'ya da gönderilmez — sızıntı ayrımı kaynaktan bağımsız korunur.
