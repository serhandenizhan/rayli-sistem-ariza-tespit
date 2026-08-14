# CLAUDE.md

Bu dosya, bu depo üzerinde çalışan bir Claude ajanı (Claude Code vb.) için bağlam sağlar.

## Proje özeti

Raylı sistemlerde (tren/vagon/dingil) çok sensörlü verilerden arıza tespiti ve sınıflandırması
için uçtan uca bir proje: sentetik veri üretimi + 1D-CNN/LSTM sınıflandırma modeli (eğitim/test)
+ **canlı akış (live streaming) simülasyonu** (FastAPI/SSE) + **Next.js dashboard**.
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
```

Model zaten eğitilmiş haliyle repoda mevcuttur (`model/rayli_cnn_lstm_model.pt`) — geliştirme
yaparken her seferinde yeniden eğitmek gerekmez, `rayli_tahmin.py` üzerinden hızlıca doğrulama
yapılabilir.

## Kod organizasyonu (src/)

- `rayli_veri_uret.py` — sentetik veri üretim scripti, `data/` klasörünü doldurur. Bağımsız
  çalışır, diğer modüllere bağımlı değildir.
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
  tick yayınlar, her dingil için 10'luk kayan pencere tutar, dolunca 24 dingili tek batch'te
  modele sokar; **tahminden sonra** cevap anahtarıyla eşleştirip çevrimiçi metrik hesaplar.
  Ölçekleme/model yükleme mantığı `rayli_model.py`'den gelir — tahmin scriptiyle birebir aynıdır.

## Web arayüzü (web/)

Next.js 15 (App Router) + React 19, TypeScript, ek UI kütüphanesi yok (grafikler elle yazılmış
SVG). `web/next.config.mjs` içindeki rewrite ile `/api/*` istekleri FastAPI'ye (`:8000`)
proxy'lenir — tarayıcı tarafında CORS/SSE sorunu olmaz. `lib/useAkis.ts` SSE bağlantısını ve
kontrol çağrılarını yönetir; `lib/tipler.ts` sunucu paketlerinin tip tanımıdır (sunucudaki
payload alanlarını değiştirirsen burayı da güncelle). Arayüz metinleri Türkçedir.

## Veri hakkında kritik noktalar

- `data/rayli_sistem_{tum_veri,train,test}.csv` — kolon şeması `docs/rayli_sistem_veri_semasi.md`
  içinde tam olarak açıklanmıştır.
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
- `rail_crack` konuma bağlı bir arızadır; basitlik için 12 km'lik döngüsel bir sanal hat
  (`TRACK_LENGTH_KM`) üzerinden zaman bazlı pencereye entegre edildi, gerçekte mesafe bazlı
  örneklenir.

## Model performansı (referans — `results/` içinde detaylı)

Mevcut eğitilmiş model, test setinde: **accuracy %98.9, macro F1 0.9754** (`results/` içinde
detaylı; `results/egitim_ozeti.json` makine-okunur özet). `rail_crack` 1.000, `normal` 0.993 F1;
en zayıf sınıf `motor_fault` (F1 0.939) — `normal` ile sınırdaki örnekler burada karışıyor.
Canlı akış simülasyonu aynı checkpoint'le uçtan uca ~%98.9 doğruluk / 0.975 macro F1 üretir;
bu iki sayının örtüşmesi canlı hattın (pencereleme + ölçekleme) doğru kurulduğunun kanıtıdır —
akışta ciddi bir sapma görürsen önce pencere/scaler tarafına bak.

Not: daha eski bir çalıştırmada aynı kod %96.9 / 0.9475 üretmişti (motor_fault precision %67);
mimari değişmedi, ortam (torch sürümü) değişince skor yukarı taşındı.

## Sıradaki olası görevler

Canlı akış + dashboard tamamlandı. Sıradaki doğal adımlar:

- Kalıcılık: tahminleri/alarmları bir dosyaya veya SQLite'a yazıp geçmişe dönük sorgulama.
- Arıza şiddeti (severity) tahmini için ikinci bir çıkış başlığı (multi-task).
- Eşik/histerezis: tek tick'lik sınıf sıçramalarını bastırmak için N ardışık tick kuralı
  (şu an alarm günlüğü her sınıf değişiminde kayıt atıyor).
- Gerçek (sentetik olmayan) veriye uyarlama; bkz. "Bilinen basitleştirmeler".

## Diğer notlar

- Rastgelelik `SEED=42` ile sabitlenmiştir (hem `numpy` hem `torch`) — kod değişmediği sürece
  sonuçlar deterministik olarak yeniden üretilebilir. **Tek istisna**: `rayli_veri_uret.py`
  içindeki `START_TIME` (verinin başladığı saat/dakika) artık her çalıştırmada `SEED=42`'den
  bağımsız, ayrı bir üreteçle (`_saat_rng`) rastgele seçiliyor — bu sadece zaman damgası
  etiketini değiştirir, sensör değerlerinin/arıza örüntülerinin deterministik sırasını bozmaz.
- Ortam: PyTorch (CPU), scikit-learn, pandas, numpy, matplotlib — bkz. `requirements.txt`.
- Kod içi yorumlar ve dokümantasyon Türkçedir; yeni kod eklerken bu tutarlılığı koru.
