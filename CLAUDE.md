# CLAUDE.md

Bu dosya, bu depo üzerinde çalışan bir Claude ajanı (Claude Code vb.) için bağlam sağlar.

## Proje özeti

Raylı sistemlerde (tren/vagon/dingil) çok sensörlü verilerden arıza tespiti ve sınıflandırması
için uçtan uca bir proje: **gerçek İstanbul metro ağı** üzerinde sentetik veri üretimi +
**çok görevli** (arıza tipi + şiddet) 1D-CNN/LSTM modeli + **canlı akış simülasyonu**
(FastAPI/SSE, histerezisli) + **Next.js dashboard** (canlı ağ haritası dahil) + pytest.
Tek komutla çalışır: `./calistir.sh` (kurulum → eğitim → etiketsiz akış → API → arayüz).

## Kurulum ve sık kullanılan komutlar

```bash
./calistir.sh                   # UÇTAN UCA: kurulum + eğitim + canlı akış + dashboard
./calistir.sh --egitmeden       # eğitimi atla, mevcut checkpoint ile başlat
./calistir.sh --hiz 10          # simülasyon hız çarpanı (1x = gerçek zaman, 2 sn/tick)
./calistir.sh --kor-mod         # cevap anahtarını arayüze hiç gönderme

pip install -r requirements.txt

cd src
python rayli_veri_uret.py       # sentetik veriyi (yeniden) üretir -> ../data/*.csv
python rayli_dl_egitim.py       # modeli SIFIRDAN eğitir, test eder -> ../model, ../results
python rayli_tahmin.py          # kayıtlı modeli RETRAIN ETMEDEN yükler, test setini değerlendirir
python rayli_tahmin.py --n 20   # ilk 20 sekans için satır satır gerçek/tahmin karşılaştırması
python rayli_etiketsiz_uret.py  # test setini etiketsiz akış + cevap anahtarı olarak ayırır
python rayli_canli_akis_sunucu.py --konsol   # canlı akışı arayüzsüz, konsolda izle
python rayli_canli_akis_sunucu.py --histerezis 5   # N ardışık tick kuralı
python istanbul_metro_agi.py    # İBB açık verisinden metro ağı modelini kurar
python istanbul_metro_agi.py --indir   # ham GeoJSON'ları İBB'den yeniden indir
python rayli_kafka.py --uret    # etiketsiz akışı Kafka topic'ine yayınla (broker gerekir)

./testleri_calistir.sh          # pytest (55 test) + results/test_ozeti.json üretir
```

Model zaten eğitilmiş haliyle repoda mevcuttur (`model/rayli_cnn_lstm_model.pt`) — geliştirme
yaparken her seferinde yeniden eğitmek gerekmez, `rayli_tahmin.py` üzerinden hızlıca doğrulama
yapılabilir.

## Kod organizasyonu (src/)

- `istanbul_metro_agi.py` — **gerçek metro ağı modeli + harita zemini**. İBB Açık Veri
  Portalı'ndaki resmi GeoJSON'lardan (istasyon noktaları + hat vektörleri)
  `data/istanbul_metro_agi.json` üretir:
  20 işletmedeki hat, 265 gerçek istasyon, gerçek koordinatlar, harita için sadeleştirilmiş
  güzergâh geometrisi. İstasyon SIRASI kaynak veride yok — 2-opt ile iyileştirilmiş açık TSP
  yolu olarak türetiliyor (M4/M2/T1'de gerçek sırayla birebir örtüştüğü testlerle doğrulandı).
  `SIMULASYON_HATLARI` sabiti, tren işletilen hatları belirler.
  Ayrıca `cografya_kur()` ile **harita zemini** (`data/istanbul_cografya.json`) üretilir:
  geoBoundaries ADM2 ilçe sınırlarından (ODbL 1.0) ağın çevresine düşen 43 ilçe alınıp
  sadeleştirilir (76 KB). Haritada bu poligonlar dolu çizilir; **deniz ayrı bir veri değildir**,
  karanın çizilmediği yerdir — Boğaz, Haliç, Marmara ve Karadeniz böyle ortaya çıkar.
  Not: kaynak veride Adalar ilçesi "Prince Islands" adıyla geçtiği için `AD_DUZELTME` ile
  Türkçeleştirilir.
- `rayli_veri_uret.py` — sentetik veri üretim scripti, `data/` klasörünü doldurur. Ağ modelini
  (`istanbul_metro_agi`) kullanır: trenler gerçek hatlarda, gerçek istasyon dizisinde,
  gerçekçi sefer profiliyle (hızlanma/frenleme/istasyonda bekleme/terminalde dönüş) hareket eder.
- `rayli_model.py` — **tek gerçek kaynak (single source of truth)**: model mimarisi (`CNNLSTM`
  sınıfı), `SeqDataset`, ve paylaşılan sabitler (`FEATURE_COLS`, `GROUP_COLS`, `WINDOW=10`,
  `STRIDE=2`). Hem eğitim hem tahmin scripti bunu import eder. **Bu dosyada mimariyi
  değiştirirsen hem `rayli_dl_egitim.py` hem `rayli_tahmin.py` etkilenir — ikisini de
  değişiklikten sonra çalıştırıp doğrula.**
- `rayli_veri_utils.py` — `load_df`, `build_sequences`, `build_sequences_with_val_split`.
  Sekans (pencere) oluşturma mantığı burada; eğitim ve tahmin scriptleri aynı fonksiyonları
  kullanır ki iki taraf arasında sekans oluşturma farkı (ve dolayısıyla sessiz bir hata) oluşmasın.
- `rayli_dl_egitim.py` — eğitim döngüsü, test değerlendirmesi, `model/` ve `results/` altına
  kayıt.
- `rayli_tahmin.py` — `model/rayli_cnn_lstm_model.pt` içindeki checkpoint'i yükler (ağırlıklar +
  scaler parametreleri + sınıf isimleri), `rayli_model.rebuild_scaler_and_encoder` ile
  StandardScaler/LabelEncoder'ı checkpoint'ten yeniden kurar (sıfırdan fit ETMEZ), test verisi
  üzerinde tahmin üretir.
- `rayli_etiketsiz_uret.py` — `rayli_sistem_test.csv`'yi ikiye ayırır: etiketsiz akış verisi
  (`..._test_akis.csv`) + cevap anahtarı (`..._test_cevap_anahtari.csv`), `sample_id` ile eşleşir.
- `rayli_canli_akis_sunucu.py` — canlı akış motoru + FastAPI/SSE sunucusu. Etiketsiz veriyi tick
  tick yayınlar, her dingil için 10'luk kayan pencere tutar, dolunca 32 dingili tek batch'te
  modele sokar; **tahminden sonra** cevap anahtarıyla eşleştirip çevrimiçi metrik hesaplar.
  Ölçekleme/model yükleme mantığı `rayli_model.py`'den gelir — tahmin scriptiyle birebir aynıdır.
  **Histerezis**: bir sınıf N ardışık tick tahmin edilmeden "yerleşik" olmaz (`yerlesik` alanı);
  alarm günlüğü yalnızca yerleşik değişimlerde kayıt atar. Kör mod ve histerezis çalışma anında
  `/api/kontrol` ile değiştirilebilir. Uç noktalar: `/api/meta`, `/api/ag` (harita için ağ +
  ray kusurları), `/api/durum`, `/api/olaylar`, `/api/testler`, `/api/akis` (SSE), `/api/kontrol`.
- `rayli_kafka.py` — Kafka adaptörü. Üretici etiketsiz akışı topic'e yayınlar, tüketici topic'i
  DataFrame'e çevirir; sunucu `--kaynak kafka` ile aynı boru hattını mesaj kuyruğundan besler.
  `kafka-python` kurulu değilse anlaşılır bir hata verir (varsayılan akış CSV'dir).

## Web arayüzü (web/)

Next.js 15 (App Router) + React 19, TypeScript, ek UI kütüphanesi yok (grafikler ve harita elle
yazılmış SVG). `web/next.config.mjs` içindeki rewrite ile `/api/*` istekleri FastAPI'ye (`:8000`)
proxy'lenir — tarayıcı tarafında CORS/SSE sorunu olmaz. `lib/useAkis.ts` SSE bağlantısını ve
kontrol çağrılarını yönetir; `lib/tipler.ts` sunucu paketlerinin tip tanımıdır (sunucudaki
payload alanlarını değiştirirsen burayı da güncelle). Arayüz metinleri Türkçedir.

Paneller: üst kontrol barı (play/duraklat/baştan, hız, **histerezis**, **kör mod** — hepsi
çalışma anında), KPI kartları, **MetroHarita** (gerçek koordinatlarla İstanbul ağı; kara/deniz
zemini ilçe poligonlarından çizilir, trenler tahmin rengiyle hareket eder, ray kusurları üçgenle
işaretlidir; `--deniz`/`--kara`/`--kara-sinir` CSS değişkenleriyle renklendirilir), hat bazında gruplanmış dingil
kartları (şiddet rozeti + histerezis bekleme göstergesi), sensör akış grafiği, iki başlıklı model
çıktısı (tip + şiddet), alarm günlüğü, canlı doğrulama, **TestPaneli** (pytest sonuçları),
eğitim özeti.

Kontrol durumları (play/pause, kör mod, histerezis) SSE paketinden DEĞİL, her kontrol çağrısının
kendi yanıtından güncellenir — aksi hâlde duraklatınca yeni paket gelmediği için butonlar donmuş
görünüyordu.

## Veri hakkında kritik noktalar

- `data/rayli_sistem_{tum_veri,train,test}.csv` — kolon şeması `docs/rayli_sistem_veri_semasi.md`
  içinde tam olarak açıklanmıştır.
- `data/istanbul_metro_agi.json` (depoda tutulur) ağ modelidir; `data/harici/` altındaki ham İBB
  GeoJSON'ları önbellektir ve **git'e girmez** (gerektiğinde `--indir` ile yeniden çekilir).
- `data/ray_kusur_noktalari.json` — gerçek hat üzerindeki sabit ray kusuru konumları (hangi
  istasyonlar arasında olduğu dahil); haritada üçgenle gösterilir.
- `data/istanbul_cografya.json` — harita zemini (ilçe poligonları, geoBoundaries/ODbL 1.0).
  Yeniden dağıtılan açık veri olduğu için kaynak/lisans bilgisi dosyanın içinde tutulur ve
  bu bir testle korunur.
- Konum kolonları (`lat`, `lon`, `next_station`, `line_id`) harita/bağlam içindir; **özellik
  (feature) DEĞİLDİR** — `FEATURE_COLS` listesine eklenmemelidir.
- Train/test bölmesi **kronolojiktir, rastgele DEĞİLDİR** (ilk %80 zaman dilimi train, son %20
  test) — amaç hem veri sızıntısını (leakage) önlemek hem de gerçek canlı akış senaryosunu
  simüle etmek. Yeni bir train/test bölmesi yaparken bu ilkeyi koru.
- 6 sınıf: `normal`, `wheel_flat`, `bearing_fault`, `brake_fault`, `motor_fault`, `rail_crack`.
  `rayli_veri_uret.py` içindeki `make_dedicated_episodes()` fonksiyonu, her sınıfın hem train
  hem test zaman diliminde en az birkaç örnekle temsil edilmesini garanti eder — bu olmadan
  bazı sınıflar rastgele yerleşimden dolayı test setinde hiç görünmeyebilir (bu proje daha önce
  bu hatayı yaşadı, düzeltildi).
- Canlı akışta kullanılan `rayli_sistem_test_akis.csv` dosyasında **etiket kolonu yoktur**;
  etiketler ayrı cevap anahtarında tutulur ve yalnızca tahmin üretildikten SONRA skorlamak için
  okunur. Bu ayrımı bozma — akış dosyasına etiket geri eklemek sızıntı demektir.
- `fault_severity` kolonu bir yardımcı/açıklayıcı etikettir, **model girişi (feature) olarak
  KULLANILMAMALI** — hedef değişkenle (`fault_type`) doğrudan ilişkili olduğu için sızıntıya yol
  açar. `FEATURE_COLS` listesinde zaten yok; yeni özellik eklerken bu ayrımı koru.
- Pencere/örnekleme aralığı 2 saniye; model, 10 ardışık satırdan oluşan (20 saniyelik geçmiş)
  sekanslar üzerinde çalışır ve sekansın SON adımındaki sınıfı tahmin eder (canlı akışta "şu
  anki durum" tahminine karşılık gelir).

## Bilinen basitleştirmeler (gerçekçilik notları)

Sentetik veri gerçekçi ama tam fiziksel doğrulukta değildir; ilerideki iyileştirmeler için not:

- Ham sensör sinyali yok, doğrudan özellik (RMS, kurtosis, FFT tepe frekansı vb.) simüle edildi.
- Sıcaklık/nem gibi yavaş değişen sensörler bağımsız gürültüyle üretildi; gerçekte zamanla
  yumuşak trend (otokorelasyon) gösterirler.
- `rail_crack` konuma bağlı bir arızadır; artık gerçek hat üzerinde sabit km noktalarına
  bağlıdır (tren her geçişte tetikler), ancak hâlâ zaman bazlı pencereye örnekleniyor.
- İstasyon sırası kaynak veriden değil, coğrafi konumlardan türetiliyor (bkz.
  `istanbul_metro_agi.py`); şubeli hatlarda (M2'nin Seyrantepe kolu) şube, ana hattın
  arasına yerleşiyor.
- Hat başına tek tren var ve trenler birbirini etkilemiyor (sinyalizasyon/takip mesafesi yok).

## Model performansı (referans — `results/` içinde detaylı)

Model **çok görevlidir**: tek gövde (CNN+LSTM), iki başlık — arıza tipi (6 sınıf) ve arıza
şiddeti (none/mild/moderate/severe). Toplam kayıp = tip + `SEVERITY_AGIRLIK`(0.4) × şiddet.

Gerçek metro ağı verisiyle eğitilen mevcut model, test setinde:
- **Arıza tipi: accuracy %98.7, macro F1 0.9679** (`rail_crack` 0.974, `normal` 0.993,
  en zayıf `motor_fault` F1 0.926)
- **Arıza şiddeti: accuracy %95.5, macro F1 0.8247** (mild/moderate sınırları doğası gereği bulanık)

Canlı akış simülasyonu aynı checkpoint'le uçtan uca ~%98.7 tip / ~%95.5 şiddet doğruluğu üretir;
bu örtüşme canlı hattın (pencereleme + ölçekleme) doğru kurulduğunun kanıtıdır — akışta ciddi bir
sapma görürsen önce pencere/scaler tarafına bak. `testler/test_model.py` bunun için %90/%85
regresyon eşiği tutar.

Geçmiş not: eski (gerçek ağ öncesi) sentetik veride skor %98.9 / 0.9754 idi. Gerçek sefer
profiline geçince (trenler istasyonlarda duruyor, titreşim imzası kayboluyor) problem doğal
olarak zorlaştı. Motor arızası bir ara F1 0.50'ye düşmüştü; sebebi motor akımının sürüş
dinamiğinden bağımsız üretilmesi ve arıza örneklerinin azlığıydı — akım artık ivme/yük ile
ilişkilendirildi ve arıza bölümü sayısı artırıldı.

## Testler (testler/)

`./testleri_calistir.sh` → pytest (şu an **58 test**, hepsi geçiyor) + `results/test_ozeti.json`.
Özet dosyasını `testler/conftest.py` içindeki küçük eklenti üretir (ek bağımlılık yok) ve
dashboard'daki **Birim Testleri** paneli `/api/testler` üzerinden bunu gösterir. Testlerin Türkçe
docstring'i arayüzde açıklama olarak görünür — yeni test yazarken docstring'i anlamlı yaz.

- `test_veri_semasi.py` — şema, eksik değer, kronolojik bölme, **sızıntı korumaları** (akış
  dosyasında etiket olmaması), fiziksel akıl kontrolleri (trenler duraklarda duruyor mu vb.)
- `test_metro_agi.py` — ağ modeli: koordinatlar İstanbul içinde mi, km sırası artıyor mu,
  bilinen hat terminalleri (M4/T1/M2) doğru mu, M4'ün ilk 5 istasyonu gerçek sırayla mı;
  coğrafya katmanı: ilçelerin varlığı, poligon geçerliliği, lisans bilgisinin korunması
- `test_model.py` — iki başlıklı çıktı, checkpoint alanları, scaler yeniden kurulumu, sekans
  hizası, **doğruluk regresyon eşiği**
- `test_canli_akis.py` — pencere dolmadan tahmin yok, histerezis davranışı, kör modda sızıntı
  olmaması, reset, canlı doğruluk eşiği, akışın 300/300 tamamlanması

## Sıradaki olası görevler

- Kalıcılık: tahminleri/alarmları SQLite'a yazıp geçmişe dönük sorgulama.
- Aynı hatta birden fazla tren (şu an hat başına 1 tren, 8 hat = 32 dingil).
- Marmaray/M11 gibi diğer hatlara da tren koymak (`SIMULASYON_HATLARI`).
- Gerçek (sentetik olmayan) veriye uyarlama; bkz. "Bilinen basitleştirmeler".

## Diğer notlar

- Rastgelelik `SEED=42` ile sabitlenmiştir (hem `numpy` hem `torch`) — kod değişmediği sürece
  sonuçlar deterministik olarak yeniden üretilebilir. **Tek istisna**: `rayli_veri_uret.py`
  içindeki `START_TIME` (verinin başladığı saat/dakika) artık her çalıştırmada `SEED=42`'den
  bağımsız, ayrı bir üreteçle (`_saat_rng`) rastgele seçiliyor — bu sadece zaman damgası
  etiketini değiştirir, sensör değerlerinin/arıza örüntülerinin deterministik sırasını bozmaz.
- Ortam: PyTorch (CPU), scikit-learn, pandas, numpy, matplotlib, FastAPI/uvicorn, pytest —
  bkz. `requirements.txt`. Python 3.9 kullanılıyor: **f-string içinde iç içe aynı tırnak
  kullanılamaz** (`f"{d['k']}"` hata verir), `"{}".format(...)` ile yaz.
- Kod içi yorumlar ve dokümantasyon Türkçedir; yeni kod eklerken bu tutarlılığı koru.
- **Yeni özellik eklendiğinde bu dosya (CLAUDE.md) güncellenmelidir** — proje hafızası burasıdır.
- Git: tamamlanan her özellikten sonra commit + push atılır (kullanıcının kalıcı tercihi).
