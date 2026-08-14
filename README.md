# Raylı Sistem Arıza Tespiti — Projesi

Raylı sistemlerde (tren/vagon/dingil) çok sensörlü verilerden arıza tespiti ve sınıflandırması
için uçtan uca bir örnek proje. Sentetik veri üretiminden 1D-CNN + LSTM tabanlı bir sınıflandırma
modelinin eğitilip test edilmesine kadar tüm adımları içerir.

## Klasör yapısı

```
rayli_ariza_tespiti/
├── data/                       # üretilen veri setleri
│   ├── rayli_sistem_tum_veri.csv
│   ├── rayli_sistem_train.csv
│   ├── rayli_sistem_test.csv
│   ├── rayli_sistem_test_akis.csv            # ETİKETSİZ test verisi (canlı akışa verilen)
│   └── rayli_sistem_test_cevap_anahtari.csv  # cevap anahtarı (yalnızca doğrulama için)
├── docs/
│   └── rayli_sistem_veri_semasi.md   # veri şeması: kolon açıklamaları, sınıf mantığı
├── src/
│   ├── rayli_veri_uret.py      # sentetik veri üretim scripti
│   ├── rayli_model.py          # model mimarisi (CNNLSTM) + paylaşılan sabitler
│   ├── rayli_veri_utils.py     # veri yükleme / sekans (pencere) oluşturma yardımcıları
│   ├── rayli_dl_egitim.py      # modeli SIFIRDAN eğitip test eden script
│   ├── rayli_tahmin.py         # kayıtlı modeli YENİDEN EĞİTMEDEN yükleyip tahmin üreten script
│   ├── rayli_etiketsiz_uret.py # test setini etiketsiz akış + cevap anahtarı olarak ayırır
│   └── rayli_canli_akis_sunucu.py  # canlı akış simülasyonu + SSE API (FastAPI)
├── web/                        # Next.js (React) canlı izleme dashboard'u
├── calistir.sh                 # uçtan uca çalıştırma: kurulum -> eğitim -> akış -> arayüz
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

### Test sonuçları (mevcut eğitimden)

- Genel doğruluk: %98.9
- Macro F1: 0.9754
- `rail_crack` kusursuz (1.000), `normal` 0.993 F1; `bearing_fault`, `brake_fault`,
  `wheel_flat` 0.97 civarı.
- En zayıf sınıf `motor_fault` (F1 0.939) — `normal` ile karışan sınırda örnekler burada
  toplanıyor. Ayrıntılar `results/test_classification_report.txt` ve
  `results/confusion_matrix.csv` içinde.

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

Panolar: canlı KPI'lar (aktif alarm, canlı doğruluk, canlı macro F1), 24 dingilin durum haritası,
seçili dingil için sensör akış grafiği + model tahmin şeridi, softmax olasılık dağılımı, alarm
günlüğü, **canlı doğrulama** paneli (cevap anahtarına karşı akan karmaşıklık matrisi, sınıf bazlı
precision/recall/F1, doğruluk trendi) ve offline eğitim özeti.

Canlı akış sonunda ölçülen skorlar offline test raporuyla örtüşür (accuracy ~%98.9,
macro F1 ~0.975) — canlı hattın modeli ve ölçeklemeyi doğru kurduğunun uçtan uca kanıtı.
