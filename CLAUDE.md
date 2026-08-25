# CLAUDE.md

Bu dosya, bu depo üzerinde çalışan bir Claude ajanı (Claude Code vb.) için bağlam sağlar.

## Proje özeti

Raylı sistemlerde arıza tespiti için **tek entegre platform**, iki bağımsız tespit yolunu
ortak bir Next.js dashboard'da birleştirir:

1. **Sensör tabanlı otomatik tespit** (`src/`, bu proje): tren/vagon/dingil sensör
   verilerinden **gerçek İstanbul metro ağı** üzerinde sentetik veri üretimi + **çok görevli**
   (arıza tipi + şiddet) 1D-CNN/LSTM modeli + **denetimsiz anomali tespiti** (autoencoder,
   tamamlayıcı katman) + **canlı akış simülasyonu** (FastAPI/SSE, histerezisli).
2. **Metin bildirimi sınıflandırma** (`nlp/`, ayrı bir FastAPI servisi): personelin/yolcunun
   yazdığı serbest metin arıza bildirimlerinden BERTurk+LoRA ile intent + 11 kategori + öncelik
   çıkarımı. Kendi `CLAUDE.md`'si var (`nlp/CLAUDE.md`) — tüm proje geçmişi, kararlar, ölçümler
   orada; bu dosyadaki "NLP metin sınıflandırma modülü" bölümü sadece entegrasyon özetidir.

İkisi ortak `web/` (Next.js) dashboard'unda ayrı sekmelerde yaşar, pytest + **hafif Docker
Compose** (üç servis: sensör API, NLP API, web) ile tamamlanır. Tek komutla çalışır:
`./calistir.sh` (kurulum → eğitim → etiketsiz akış → sensör API + NLP API → arayüz).
Docker ile de çalışır: `docker compose up --build`.

## Kurulum ve sık kullanılan komutlar

```bash
./calistir.sh                   # UÇTAN UCA: kurulum + eğitim + iki API + dashboard
API_PORT=8001 WEB_PORT=3001 NLP_API_PORT=8002 ./calistir.sh   # portlar meşgulse alternatif port
./calistir.sh --egitmeden       # eğitimi atla, mevcut checkpoint ile başlat
./calistir.sh --hiz 10          # simülasyon hız çarpanı (1x = gerçek zaman, 2 sn/tick)
./calistir.sh --kor-mod         # cevap anahtarını arayüze hiç gönderme
./calistir.sh --nlpsiz          # NLP metin sınıflandırma servisini başlatma

pip install -r requirements.txt

cd src
python rayli_veri_uret.py       # sentetik veriyi (yeniden) üretir -> ../data/*.csv
python rayli_dl_egitim.py       # modeli SIFIRDAN eğitir, test eder -> ../model, ../results
python rayli_tahmin.py          # kayıtlı modeli RETRAIN ETMEDEN yükler, test setini değerlendirir
python rayli_tahmin.py --n 20   # ilk 20 sekans için satır satır gerçek/tahmin karşılaştırması
python rayli_etiketsiz_uret.py  # test setini etiketsiz akış + cevap anahtarı olarak ayırır
python rayli_canli_akis_sunucu.py            # VARSAYILAN: sürekli/rastgele canlı üretim
python rayli_canli_akis_sunucu.py --kaynak csv  # eski davranış: sabit/tekrar üretilebilir dosya
python rayli_canli_akis_sunucu.py --konsol   # canlı akışı arayüzsüz, konsolda izle
python rayli_canli_akis_sunucu.py --histerezis 5   # N ardışık tick kuralı
python rayli_canli_akis_sunucu.py --otomatik-basla # duraklatılmış değil, oynatarak başla
python istanbul_metro_agi.py    # İBB açık verisinden metro ağı modelini kurar
python istanbul_metro_agi.py --indir   # ham GeoJSON'ları İBB'den yeniden indir
python rayli_kafka.py --uret    # etiketsiz akışı Kafka topic'ine yayınla (broker gerekir)

./testleri_calistir.sh          # pytest (94 test) + results/test_ozeti.json üretir
python rayli_kayit.py --ozet    # SQLite'daki alarm geçmişini terminalden sorgula
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
  `SIMULASYON_HATLARI` sabiti, tren işletilen hatları belirler — **Metro İstanbul
  işletmesindeki tüm yolcu hatları** dahildir (17 hat: M1A, M1B, M2, M3, M4, M5, M6, M7, M8,
  M9, T1, T3, T4, T5, F1, F2, F4). Teleferikler (TF1, TF2) hariçtir: kabinli sistemlerde
  dingil/boji yoktur, projenin sensör modeli onlara uymaz.
  `HARIC_MUDURLUKLER` ise **Metro İstanbul dışındaki işletmecilerin** hatlarını ağa hiç almaz;
  ayrım isimle değil kaynak verinin `MUDURLUK` alanıyla, hattın **baskın** müdürlüğüne bakılarak
  yapılır (M4'ün Sabiha Gökçen uzantısındaki birkaç istasyon "AYGM" görünür ama hattın
  işletmecisi Metro İstanbul'dur — bu yüzden tek tek istasyona bakılmaz). Şu an bu kural
  **Marmaray** ve **M11**'i (ikisi de "Ulaştırma Bakanlığı") kapsam dışı bırakır. `ISLETMEDEKI_INSAAT_HATLARI` ise kaynak veride
  "İnşaat Aşamasında" görünmesine rağmen fiilen işletmede olan hatları dahil eder — şu an
  yalnızca **F4** (Rumelihisarüstü–Aşiyan, 2022'de açıldı; İBB anlık görüntüsü kendi içinde
  tutarsız: hat geometrisi "Mevcut", istasyonları "İnşaat").
  Ayrıca `cografya_kur()` ile **harita zemini** (`data/istanbul_cografya.json`) üretilir:
  geoBoundaries ADM2 ilçe sınırlarından (ODbL 1.0) ağın çevresine düşen 43 ilçe alınıp
  sadeleştirilir (76 KB). Haritada bu poligonlar dolu çizilir; **deniz ayrı bir veri değildir**,
  karanın çizilmediği yerdir — Boğaz, Haliç, Marmara ve Karadeniz böyle ortaya çıkar.
  Not: kaynak veride Adalar ilçesi "Prince Islands" adıyla geçtiği için `AD_DUZELTME` ile
  Türkçeleştirilir.
- `rayli_veri_uret.py` — sentetik veri üretim scripti, `data/` klasörünü doldurur. Ağ modelini
  (`istanbul_metro_agi`) kullanır: trenler gerçek hatlarda, gerçek istasyon dizisinde,
  gerçekçi sefer profiliyle (hızlanma/frenleme/istasyonda bekleme/terminalde dönüş) hareket eder.
  `main()` (offline, `python rayli_veri_uret.py`) SEED=42 ile deterministik train/test CSV'leri
  üretir — model eğitimi için, DEĞİŞMEDİ. **Ayrıca** canlı akış sunucusu için "segment" üretim
  katmanı eklendi (25 Ağu 2026): `bir_segment_uret(hatlar, rng, baslangic_zamani,
  hareket_durumlari, kusurlar, n_steps=SEGMENT_STEPS)` — `tren_hareketi()`'nin `baslangic_durumu`
  parametresiyle (bir önceki segmentin bitiş durumu: konum/hız/yön/bekleme) chunk'lanabilir hale
  getirilmiş hâlini ve `segment_dedicated_episodes()`'i (düşük yoğunluklu garanti arıza) kullanır.
  Segment üretimi çağıranın verdiği (seedsiz) `rng` ile çalışır — offline `main()`'in SEED=42'li
  `rng`'sinden bağımsız, HER ÇAĞRIDA taze rastgele. `hat_tren_sayisi()` artık kademeli bir eşik
  tablosuna (`TREN_ESIKLERI`) göre çalışır (<10km→1, 10-20km→2, 20-30km→3, ≥30km→4 tren) —
  eskiden tek eşik (15km→2) vardı, filo gerçekçilik için büyütüldü.
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
  tick yayınlar, her dingil için 10'luk kayan pencere tutar, dolunca tüm dingilleri tek batch'te
  modele sokar; **tahminden sonra** cevap anahtarıyla eşleştirip çevrimiçi metrik hesaplar.
  Ölçekleme/model yükleme mantığı `rayli_model.py`'den gelir — tahmin scriptiyle birebir aynıdır.
  **`--kaynak canli` (VARSAYILAN, 25 Ağu 2026):** sabit dosya yerine `rayli_veri_uret.
  bir_segment_uret()` bellek içinde çağrılır — saat hiç durmadan ilerler, her `SEGMENT_STEPS`
  (300) tick'te bir yeni segment üretilir; `dongu()` segment sonuna geldiğinde `reset()`
  ÇAĞIRMAZ, `_segment_ekle()` ile devam eder — pencere/histerezis state'i ve DB `calistirma`
  oturumu KORUNUR ("kaldığı yerden devam"). Kullanıcının "Sıfırla"sı (`reset()`) hâlâ tam
  sıfırlama yapar ama sabit `START_TIME`'a dönüp TAZE rastgele bir ilk segment üretir — her
  "Sıfırla" aynı saatten başlar, farklı bir senaryo oynatır. Cevap anahtarı artık dosyadan değil
  `_segment_ekle()` içinde segment üretimiyle eşzamanlı doldurulur (`sample_id` sırayla
  atanır). `--kaynak csv` ile eski (sabit dosya, tekrar üretilebilir) davranışa dönülebilir —
  **sınıfın kendi `kaynak` varsayılanı bilinçli olarak `"csv"` bırakıldı** (testler buna
  güveniyor), `"canli"` varsayılanı yalnızca CLI (`main()`'deki argparse) seviyesinde.
  `payload["tick"]`/`["toplam_tick"]`/`["bitti"]` canlı modda segment-içi anlama çekilir
  (`tick_index % SEGMENT_STEPS`), `bitti` her zaman `False` (akış sonsuz); yeni `segment_no`
  alanı kaçıncı bölümde olunduğunu gösterir. `testler/test_canli_akis.py`'deki `canli_sim`
  fixture'ı bu modu ayrıca test eder (segment geçişinde state korunuyor mu, iki "Sıfırla" farklı
  senaryo mu üretiyor, arızalı dingil oranı gerçekçi mi vb.).
  **Histerezis**: bir sınıf N ardışık tick tahmin edilmeden "yerleşik" olmaz (`yerlesik` alanı);
  alarm günlüğü yalnızca yerleşik değişimlerde kayıt atar.
  **Belirsizlik**: her tahmin için softmax dağılımının normalize entropisi hesaplanır
  (`normalize_entropi`, 0 = tam güven, 1 = tam kararsız). Eşiğin (varsayılan 0.35) üstündeki
  tahminler `belirsiz` işaretlenir ve **histerezis sayacını ilerletmez** — yani modelin kararsız
  kaldığı anlar alarm üretemez. Eşik `/api/kontrol` ile çalışma anında değiştirilebilir
  (1.0 = kapalı).
  **Akış duraklatılmış başlar** (`otomatik_basla=False`): demoyu arayüzdeki "Başlat" düğmesi
  çalıştırır. `reset` YALNIZCA veriyi temizler, akışı kendiliğinden başlatmaz — başlatmak tek
  bir düğmenin işidir. SSE üreteci bağlanır bağlanmaz `: baglandi` yorumu yazar; aksi hâlde
  duraklatılmış akışta ilk bayt gelmediği için tarayıcının EventSource'u "bağlanıyor"da takılır.
  **Ray kusuru tekrarları**: rail_crack konuma bağlıdır ve kusur onarılana kadar HER tren
  geçişinde yeniden tespit edilir. Alarm, hat üzerindeki sabit kusur noktasıyla eşleştirilip
  (`_kusur_bul`) `kusur_id` ve `tekrar_no` ile etiketlenir; böylece tekrarlı tespitler ayrı
  arızalar gibi değil, tek bir kusur kaydının tekrarı olarak izlenir.
  **Alarm süresi ve önceliği**: her dingilin yerleşik durumunun ne zaman başladığı tutulur;
  `oncelik_hesapla()` şiddet (%50) + süre (%30, 2 dakikada doygunlaşır) + güven (%20)
  birleşimiyle 0-1 arası skor üretir, `oncelik_seviyesi()` bunu kritik/yüksek/orta/düşük'e
  çevirir. Payload'daki `aktif_alarmlar` listesi önceliğe göre sıralıdır. Kör mod ve histerezis çalışma anında
  `/api/kontrol` ile değiştirilebilir. Uç noktalar: `/api/meta`, `/api/ag` (harita için ağ +
  ray kusurları), `/api/durum`, `/api/olaylar`, `/api/testler` (+ `POST /api/testler/calistir`), `/api/gecmis` (SQLite özeti),
  `/api/akis` (SSE), `/api/kontrol`.
  **Anomali entegrasyonu**: `model/rayli_anomali_model.pt` varsa her tick'te aynı X batch'i
  autoencoder'dan da geçirir; her dingile `anomali`, `anomali_skor` (0-1 normalize) ve
  `bilinmeyen_anomali` (= denetimli model "normal" diyor AMA autoencoder aynı fikirde değil —
  kullanıcının "ne olduğunu bilmiyorum" senaryosu) ekler. Model yoksa özellik sessizce devre
  dışı kalır, ana sistem etkilenmez. Kör mod ve histerezis çalışma anında
  `/api/kontrol` ile değiştirilebilir. Uç noktalar: `/api/meta`, `/api/ag` (harita için ağ +
  ray kusurları), `/api/durum`, `/api/olaylar`, `/api/testler` (+ `POST /api/testler/calistir`), `/api/gecmis` (SQLite özeti),
  `/api/akis` (SSE), `/api/kontrol`.
  Testler ayrı bir iş parçacığında çalıştırılır (~12 sn); senkron çalıştırmak SSE akışını
  bloke ederdi. Arayüz `calisiyor`/`gecen_sn` alanlarını yoklayıp ilerlemeyi canlı gösterir.
- `rayli_kayit.py` — **kalıcılık (SQLite)**. `data/rayli_kayit.db` içinde üç tablo:
  `calistirmalar` (her reset yeni oturum açar), `alarmlar` (yerleşik sınıf değişimleri, süre ve
  öncelikle birlikte), `metrikler` (25 tick'te bir doğruluk anlık görüntüsü). Sorgular:
  dingil/hat/sınıf bazında alarm özeti. Yazma `bir_tick_isle` içinde senkron yapılır — o zaten
  `asyncio.to_thread` ile ayrı bir iş parçacığında çalıştığı için olay döngüsü bloke olmaz.
  Veritabanı git'e girmez (`.gitignore`), CLI ile de sorgulanabilir.
- `rayli_kafka.py` — Kafka adaptörü. Üretici etiketsiz akışı topic'e yayınlar, tüketici topic'i
  DataFrame'e çevirir; sunucu `--kaynak kafka` ile aynı boru hattını mesaj kuyruğundan besler.
  `kafka-python` kurulu değilse anlaşılır bir hata verir (varsayılan akış CSV'dir).
- `rayli_anomali.py` — **denetimsiz anomali tespiti** (autoencoder), 6 sınıflık denetimli
  modeli TAMAMLAR, yerine geçmez. `SekansAutoencoder`, WINDOW×FEATURE_COLS'u düzleştirip
  sıkıştıran/geri açan küçük tam bağlı bir ağdır. Gerekçe: denetimli model dağılım dışı
  (out-of-distribution) bir girdide bile yüksek güvenle YANLIŞ sınıf söyleyebilir (bilinen bir
  sinir ağı problemi); belirsizlik/entropi eşiği bunu her zaman yakalayamaz. Autoencoder farklı
  bir soru sorar: "bu pencereyi normal örüntülerden öğrendiğim gibi yeniden üretebiliyor muyum?"
  **Dürüstlük notu**: bu sentetik veri setinde yalnızca 6 belgelenmiş arıza tipi var, gerçekten
  "bilinmeyen" bir arıza örneği yok — `rayli_anomali_egitim.py`'deki değerlendirme, autoencoder'ın
  bilinen 6 sınıfı da normalden ayırabildiğini (mekanizmanın çalıştığını) doğrular; asıl değeri
  gerçek dünyada veri setinde hiç bulunmayan GERÇEKTEN yeni bir arıza tipiyle karşılaşıldığında
  ortaya çıkar.
- `rayli_anomali_egitim.py` — autoencoder'ı SADECE `fault_type=normal` pencerelerle eğitir;
  eşik, ayrılan bir validation biriminin yeniden yapılandırma hatasının 99. yüzdelik dilimidir.
  Mevcut sonuç: normal pencerelerde %1.4 yanlış alarm, bilinen 6 arıza tipini ortalama %86.6
  oranında "anomali" olarak yakalıyor. Çıktı: `model/rayli_anomali_model.pt` +
  `results/anomali_egitim_ozeti.json`.

## NLP metin sınıflandırma modülü (nlp/)

Personelin/yolcunun yazdığı **serbest metin arıza bildirimlerinden** BERTurk+LoRA ile
sınıflandırma yapan, sensör tarafından bağımsız geliştirilmiş ayrı bir proje
(`ariza-tespit-siniflandirici`) — 24 Ağu 2026'da tek platform hâline getirilirken `nlp/`
altında kendi iç yapısını (src/, backend/, data/, model/, tests/) koruyarak taşındı. Detaylı
proje geçmişi (taksonomi kararları, LLM sağlayıcı karşılaştırmaları, kalibrasyon, hard-negative
örnekler, ölçüm tabloları) **`nlp/CLAUDE.md`**'de — bu bölüm sadece iki projenin nasıl bir araya
geldiğini özetler.

**Neden ayrı bir FastAPI servisi (tek app'e mount edilmedi):** ağır bağımlılıkları
(transformers, peft, torch) sensör tarafının hafif `requirements.txt`'sine karışmasın —
`nlp/requirements.txt` tamamen ayrı, kendi sanal ortamında kurulur (`nlp/venv/`).

- **Port ve CORS:** `nlp/src/config.py`'deki `API_PORT` artık `API_PORT` ortam değişkeniyle
  ayarlanabilir (varsayılan **8001**, sensör tarafının 8000'iyle çakışmasın diye).
  `CORS_ORIGINS` varsayılanı eski Vite frontend'i (`:5173`) yerine ortak Next.js dashboard'una
  (`:3000`) işaret eder — Vite frontend birleşmede kaldırıldı.
- **`GET /logs/recent?limit=N`** — bu birleşme sırasında eklenen tek yeni endpoint. `bildirimler`
  tablosundan en son N kaydı zamana göre azalan sırada döner; dashboard'daki "Son Metin
  Bildirimleri" panelinin veri kaynağı (`src/db.py:son_kayitlari_getir`).
- **`NLP_LOG_DB`** ortam değişkeni eklendi (`nlp/src/config.py`) — Docker'da `logs.db`'yi kalıcı
  bir volume'e yönlendirmek için, sensör tarafındaki `RAYLI_KAYIT_DB` deseniyle tutarlı.
- Çalıştırma: `cd nlp && ./venv/bin/uvicorn backend.main:app --port 8001` (veya
  `./calistir.sh` bunu otomatik yapar — bkz. "Kurulum" bölümü, `--nlpsiz` ile atlanabilir).
- Testler: `cd nlp && ./venv/bin/pytest tests/ -v` (31 test, sensör tarafının
  `./testleri_calistir.sh`'inden bağımsız).

## Web arayüzü (web/)

Next.js 15 (App Router) + React 19, TypeScript, ek UI kütüphanesi yok (grafikler ve harita elle
yazılmış SVG). `web/next.config.mjs` içindeki rewrite ile `/api/*` istekleri sensör API'sine
(`:8000`) proxy'lenir; `/api/nlp/*` ise **ayrı bir rewrite kuralıyla** NLP API'sine (`:8001`)
proxy'lenir (prefix kesilerek) — tarayıcı tarafında CORS/SSE sorunu olmaz, iki backend de aynı
origin üzerinden görünür. `/api/nlp/:path*` kuralı genel `/api/:path*` kuralından ÖNCE gelir
(Next.js ilk eşleşeni kullanır). `lib/useAkis.ts` sensör SSE bağlantısını, `lib/useNlp.ts` ise
NLP tarafının düz request/response çağrılarını (predict/categories/examples/logs) yönetir;
`lib/tipler.ts` her iki tarafın da payload tip tanımlarını taşır (sunucu tarafında alan
değiştirirsen burayı da güncelle). Arayüz metinleri Türkçedir.

**Gezinme (24 Ağu 2026'dan itibaren sidebar):** sekmeler eskiden üst barda yatay duruyordu,
şimdi solda dikey bir **kenar çubuğu**nda (`components/KenarCubugu.tsx` — `Sekme` tipi ve
`SEKMELER` dizisi de burada, eskiden `Kontroller.tsx`'teydi). `Kontroller.tsx` artık sadece üst
bar durumunu (başlık, bağlantı rozeti, play/duraklat/sıfırla, hız/histerezis/belirsizlik, kör
mod) render ediyor. `page.tsx`'te `.uygulama` (flex sarmalayıcı) → `KenarCubugu` + `.ana-icerik`
(eski `.sayfa`) yapısı. Dar ekranda (`≤720px`) kenar çubuğu yatay bir şeride döner. **Birim
Testleri sekmesi kaldırıldı** (demoda anlamsız duruyordu) — `TestPaneli.tsx` ve `useAkis.ts`
içindeki `testler`/`testleriCalistir` state'i hâlâ dursun diye silinmedi, sadece `page.tsx`'ten
bağlantısı kesildi; backend'deki `/api/testler` da dokunulmadı. Üst bardaki mimari ismi
("CNN+LSTM") kaldırıldı, yerine nötr "Çok görevli model" ifadesi geldi (`layout.tsx` meta
description'ından da aynı ifade çıkarıldı) — daha profesyonel görünmesi için.

**İkinci tur toparlama (aynı gün):** kenar çubuğu artık daraltılabilir (üstteki «/» butonu,
tercih `localStorage`'da kalıcı — `KenarCubugu.tsx`); daraltılmışken sadece ikonlar görünür.
Kör mod eskiden `.kontrol-grup` içinde ayrı bir `<label>` + buton olarak render ediliyordu; bu,
sütunun kendi yüksekliği yüzünden butonun satırdaki diğer butonlara göre daha aşağıda
görünmesine yol açıyordu — düzeltme: artık diğerleri gibi tek bir `<button className="ikon">`,
açıklama `title` tooltip'ine taşındı. **Hız butonlarındaki gerçek bug**: `Kontroller.tsx` hızı
`tick?.hiz ?? 5` ile SSE paketinden okuyordu; akış DURAKLATILMIŞKEN yeni paket gelmediği için
`/api/kontrol` ile hız değiştirilse bile hangi butonun "aktif" olduğu güncellenmiyordu (akış
tekrar oynatılana kadar). Düzeltme: `useAkis.ts`'e `histerezis`/`belirsizlikEsigi` ile aynı
desende bağımsız bir `hiz` state'i eklendi, hem SSE paketinden hem `kontrol()` yanıtından
güncelleniyor. **Harita**: istasyon noktaları büyütüldü (hedeflemesi zordu), trenlere de
istasyonlarla aynı `.harita-ipucu` deseninde özel bir tooltip eklendi (`Ipucu` ayrık birleşim
tipi, `tur: "istasyon" | "tren"`) — tooltip artık `ipucuStil()` ile imlecin ekranın hangi
çeyreğinde olduğuna göre konumlanıyor (sağ/alt kenara taşmasın diye).

Paneller: üst kontrol barı (play/duraklat/baştan, hız, **histerezis**, **kör mod** — hepsi
çalışma anında), KPI kartları, **MetroHarita** (gerçek koordinatlarla İstanbul ağı; kara/deniz
zemini ilçe poligonlarından çizilir, trenler tahmin rengiyle hareket eder, ray kusurları üçgenle
işaretlidir; `--deniz`/`--kara`/`--kara-sinir` CSS değişkenleriyle renklendirilir; **istasyonların
üzerine gelince özel bir tooltip** — hat/istasyon/km + o istasyonda `olaylar` listesinden son ≤5
arıza, başladı/giderildi durumuyla; `position: fixed` kullanır çünkü harita zoom/pan transform'lu,
viewBox yüzdesi işe yaramaz — bkz. `.harita-ipucu` CSS), hat bazında gruplanmış dingil kartları
(şiddet rozeti + histerezis bekleme göstergesi), sensör akış grafiği, iki başlıklı model çıktısı
(tip + şiddet), alarm günlüğü, canlı doğrulama, eğitim özeti, ve **NlpBildirimPaneli** ("Metin
Bildirimleri" sekmesi — serbest metin girişi, intent/kategori/öncelik rozetleri, yapısal alanlar,
kanıt (gradient×input), kategori dağılım grafiği, son bildirimler listesi; NLP tarafı sensörden
tamamen bağımsız, ortak veritabanı YOK — iki kaynak yalnızca dashboard seviyesinde, zaman
damgasına göre yan yana gösteriliyor). **Doğru/Yanlış onay butonları**: `SonucKarti` bileşeni
her tahminde `key={sonuc.log_id + sonuc.response_time_ms}` ile yeniden kurulur — bu olmadan bir
kez "Yanlış"a basınca `duzeltmeAcik` state'i bir sonraki tahmine sızıp butonları sonsuza kadar
gizliyordu (bu proje ailesinde ikinci kez yaşanan aynı hata, bkz. `nlp/CLAUDE.md` Adım 8). Onay
başarılı olunca "✓ Teşekkürler, kaydedildi." / "✓ Düzeltme kaydedildi." gösterilir.

Kontrol durumları (play/pause, kör mod, histerezis) SSE paketinden DEĞİL, her kontrol çağrısının
kendi yanıtından güncellenir — aksi hâlde duraklatınca yeni paket gelmediği için butonlar donmuş
görünüyordu.

## Veri hakkında kritik noktalar

- `data/rayli_sistem_{train,test}.csv` — kolon şeması `docs/rayli_sistem_veri_semasi.md`
  içinde tam olarak açıklanmıştır. `rayli_sistem_tum_veri.csv` (train+test birleşimi) hiçbir
  modül tarafından okunmaz ve depo boyutu için **git'e girmez**; veri üretilince oluşur.
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
- Canlı akışta (`--kaynak csv` modunda) kullanılan `rayli_sistem_test_akis.csv` dosyasında
  **etiket kolonu yoktur**; etiketler ayrı cevap anahtarında tutulur ve yalnızca tahmin
  üretildikten SONRA skorlamak için okunur. Bu ayrımı bozma — akış dosyasına etiket geri
  eklemek sızıntı demektir. Varsayılan `--kaynak canli` modunda aynı ilke bellek içinde
  korunur: `_segment_ekle()` üretilen satırlardan `fault_type`/`fault_severity`'yi ayrı bir
  cevap anahtarı sözlüğüne taşıyıp `self.ticks`'e eklemeden ÖNCE düşürür.
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
- `rail_crack` konuma bağlı bir arızadır; gerçek hat üzerinde sabit km noktalarına bağlıdır
  (tren her geçişte tetikler), ancak hâlâ zaman bazlı pencereye örnekleniyor.
  **Kusur yoğunluğu**: `KUSURLU_HAT_MIN_KM` ile yalnızca 10 km üstü hatlara ve hat başına BİR
  kusur konur (9 kusur). Önceden hat başına 2'ye kadar çıkıyordu (23 kusur) ve rail_crack
  diğer sınıflardan kat kat fazla alarm üretiyordu: satır sayısı en az olduğu hâlde **324
  bölüm** oluşuyordu (diğer sınıflar ~20), çünkü her tren geçişi ~12 saniyelik yeni bir olay
  demekti. Bakımlı bir ağda bu kadar aktif kusur bulunmaz; yoğunluk düşürülünce bölüm sayısı
  75'e indi ve alarm dağılımı dengelendi.
- İstasyon sırası kaynak veriden değil, coğrafi konumlardan türetiliyor (bkz.
  `istanbul_metro_agi.py`); şubeli hatlarda (M2'nin Seyrantepe kolu) şube, ana hattın
  arasına yerleşiyor.
- Hat uzunluğuna göre kademeli sayıda tren var (`TREN_ESIKLERI`, 25 Ağu 2026'da 1→2/3/4'e
  çıkarıldı) ama trenler birbirini HÂLÂ etkilemiyor — gerçek bir sinyalizasyon/takip mesafesi
  (headway) modeli yok; bu, "Sıradaki olası görevler"de ayrı bir madde olarak duruyor.

## Model performansı (referans — `results/` içinde detaylı)

Model **çok görevlidir**: tek gövde (CNN+LSTM), iki başlık — arıza tipi (6 sınıf) ve arıza
şiddeti (none/mild/moderate/severe). Toplam kayıp = tip + `SEVERITY_AGIRLIK`(0.4) × şiddet.

Gerçek metro ağı verisiyle eğitilen mevcut model, test setinde:
- **Arıza tipi: accuracy %99.2, macro F1 0.9804** (`bearing_fault` ve `rail_crack` 1.000,
  `normal` 0.995; en zayıf `motor_fault` F1 0.943)
- **Arıza şiddeti: accuracy %96.5, macro F1 0.85** (mild/moderate sınırları doğası gereği bulanık)

**Sınıf ağırlığı yumuşatma (`AGIRLIK_YUMUSATMA = 0.5`)**: veri %85 `normal` olduğu için tam
"balanced" ters frekans ağırlığı nadir sınıflara ~35 kat ağırlık verip modeli "arıza de" yönünde
aşırı zorluyordu — recall yükseliyor ama precision çöküyordu (`motor_fault` precision 0.61,
macro F1 0.937). Ağırlıkların karekökü alınıp ortalaması 1'e ölçeklenince precision 0.94'e,
macro F1 0.9764'e çıktı. Bu değeri değiştirirsen precision/recall dengesinin nasıl kaydığına bak.

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

`./testleri_calistir.sh` → pytest (şu an **94 test**, hepsi geçiyor) + `results/test_ozeti.json`.
Özet dosyasını `testler/conftest.py` içindeki küçük eklenti üretir (ek bağımlılık yok) ve
dashboard'daki **Birim Testleri** paneli `/api/testler` üzerinden bunu gösterir. Testlerin Türkçe
docstring'i arayüzde açıklama olarak görünür — yeni test yazarken docstring'i anlamlı yaz.

- `test_veri_semasi.py` — şema, eksik değer, kronolojik bölme, **sızıntı korumaları** (akış
  dosyasında etiket olmaması), fiziksel akıl kontrolleri (trenler duraklarda duruyor mu vb.)
- `test_metro_agi.py` — ağ modeli: koordinatlar İstanbul içinde mi, km sırası artıyor mu,
  bilinen hat terminalleri (M4/T1/M2) doğru mu, M4'ün ilk 5 istasyonu gerçek sırayla mı;
  coğrafya katmanı: ilçelerin varlığı, poligon geçerliliği, lisans bilgisinin korunması;
  kapsam: işletmedeki her hatta tren olması, füniküllerin dahil, teleferiklerin ve Metro
  İstanbul dışı hatların (Marmaray, M11) hariç olması
- `test_model.py` — iki başlıklı çıktı, checkpoint alanları, scaler yeniden kurulumu, sekans
  hizası, **doğruluk regresyon eşiği**
- `test_canli_akis.py` — pencere dolmadan tahmin yok, histerezis davranışı, kör modda sızıntı
  olmaması, reset, canlı doğruluk eşiği, akışın 300/300 tamamlanması (CSV modu), **belirsizlik**
  (entropi hesabı, belirsiz tahminlerin alarm üretmemesi), **alarm süresi/önceliği**.
  **`canli_sim` fixture'ı** (`--kaynak canli`) ayrıca: segment geçişinde pencere/histerezis
  state'inin korunduğu, iki "Sıfırla"nın aynı saatten ama FARKLI arıza senaryosu ürettiği,
  `bitti`'nin hep `False` olduğu, arızalı dingil oranının gerçekçi (%15 altı) kaldığı, tren
  sayısının kademeli eşiğe uyduğu, `bir_segment_uret()`'in segment sınırında treni
  "ışınlamadığı" (fiziksel süreklilik).
- `test_kayit.py` — SQLite şeması, alarm/metrik yazma, dingil/hat/sınıf özet sorguları
- `test_anomali.py` — autoencoder şekli/hata hesabı, checkpoint yükleme, normal pencerelerde
  düşük yanlış alarm, bilinen arızaların normalden anlamlı ayrışması (mekanizma doğrulaması);
  `test_canli_akis.py` içinde ayrıca: anomali alanlarının pakete eklenmesi, "bilinmeyen anomali"
  tanımının doğruluğu, anomali modeli olmadan sistemin sorunsuz çalışması

## Docker (hafif docker-compose)

`docker-compose.yml` + `docker/Dockerfile.api` + `docker/Dockerfile.nlp` + `docker/Dockerfile.web`
— bilinçli olarak **mikroservis DEĞİL**: üç servis (sensör API, NLP API, web), Kafka/Redis/Celery
yok. `api-nlp`'nin ayrı bir servis olması aynı "gereksiz ayrım yapma" ilkesiyle çelişmiyor: burada
gerçek bir ihtiyaç var (transformers/peft gibi ağır bağımlılıkların sensör imajına karışmaması),
teorik bir ölçeklenme beklentisi değil. SQLite kayıtları (`data/rayli_kayit.db`,
`nlp/data/logs.db`) sırasıyla `RAYLI_KAYIT_DB`/`NLP_LOG_DB` ortam değişkenleriyle
`/app/data_kalici/` altına yönlendirilip ayrı volume'lere bağlanır — `/app/data` üzerine volume
bağlamak, imaja gömülü eğitim/ağ verilerini gizlerdi.
**Not**: bu geliştirme ortamında Docker kurulu değildi; Dockerfile/compose dosyaları dikkatle
yazıldı ve mantık gözden geçirildi ama gerçek `docker compose build` ile doğrulanamadı — ilk
çalıştırmada küçük bir sorun çıkarsa (ör. Next.js `output` modu, healthcheck zamanlaması)
şaşırtıcı olmaz.

## Sıradaki olası görevler

- Sıcaklık sensörlerine otokorelasyon (şu an bağımsız gürültü; gerçekte yumuşak trend gösterir).
- Kaynak veri tazeliği: İBB anlık görüntüsü bazı hatlarda eski etapları gösteriyor
  (M9 yalnızca 4 istasyon, M3 Bakırköy uzatması yok, M11 Halkalı etabı "inşaat").
  Güncel istasyon listeleri elde edilirse ağ modeli tazelenebilir. İstasyon SIRA mantığının
  (2-opt TSP türetimi) tüm hatlarda gerçek sırayla örtüştüğü ek doğrulama ile teyit edilebilir
  (şu an sadece M4/M2/T1 testlerle doğrulanmış).
- Trenler arası **takip mesafesi (headway)** modeli — şu an hat başına birden fazla tren olsa
  bile trenler birbirini etkilemiyor, gerçek sinyalizasyonun sağladığı asgari ayrım mesafesi
  temsil edilmiyor. **Sinyalizasyon etkisi** de en azından basit bir operasyonel değişken
  olarak (ör. rastgele "sinyal arızası" dönemlerinde hat genelinde hız/gecikme) eklenebilir.
- Sentetik veri üretim modülü için doğrulama paketi: fiziksel aralık kontrolleri, sensörler
  arası korelasyon kontrolleri, zaman sürekliliği kontrolleri, edge-case testleri.
- Mevcut CNN+LSTM mimarisinin gerekçesini deneysel olarak göstermek üzere baseline
  karşılaştırması (Logistic/RandomForest → 1D-CNN → LSTM → final CNN+LSTM; accuracy/macro
  F1/inference süresi tek tabloda).
- Gerçek (sentetik olmayan) veriye uyarlama; bkz. "Bilinen basitleştirmeler".

## Diğer notlar

- Rastgelelik `SEED=42` ile sabitlenmiştir (hem `numpy` hem `torch`) — kod değişmediği sürece
  sonuçlar deterministik olarak yeniden üretilebilir; **bu yalnızca offline üretim/eğitim için
  geçerlidir** (`python rayli_veri_uret.py`, `rayli_dl_egitim.py`). `rayli_veri_uret.py`
  içindeki `START_TIME` (verinin başladığı saat/dakika) her çalıştırmada `SEED=42`'den bağımsız,
  ayrı bir üreteçle (`_saat_rng`) rastgele seçiliyor — bu sadece zaman damgası etiketini
  değiştirir, sensör değerlerinin/arıza örüntülerinin deterministik sırasını bozmaz.
  **Canlı akış sunucusu (`--kaynak canli`, varsayılan) BİLİNÇLİ OLARAK deterministik DEĞİLDİR**:
  `AkisSimulatoru._canli_kurulum()` modülün global `rng`'sini kendi seedsiz üretecine bağlar
  (`veri_uret.rng = np.random.default_rng()`) — her segment/her "Sıfırla" taze rastgele bir
  senaryo üretsin diye, bu proje boyunca geçerli "tekrar üretilebilirlik" ilkesinin BİLİNÇLİ bir
  istisnasıdır. Tekrar üretilebilir/test edilebilir davranış gerekiyorsa `--kaynak csv`
  kullanılır (o modda SEED=42'li offline üretimden gelen sabit dosya okunur).
- Ortam: PyTorch (CPU), scikit-learn, pandas, numpy, matplotlib, FastAPI/uvicorn, pytest —
  bkz. `requirements.txt`. Python 3.9 kullanılıyor: **f-string içinde iç içe aynı tırnak
  kullanılamaz** (`f"{d['k']}"` hata verir), `"{}".format(...)` ile yaz.
- Kod içi yorumlar ve dokümantasyon Türkçedir; yeni kod eklerken bu tutarlılığı koru.
- **Yeni özellik eklendiğinde bu dosya (CLAUDE.md) güncellenmelidir** — proje hafızası burasıdır.
- Git: tamamlanan her özellikten sonra commit + push atılır (kullanıcının kalıcı tercihi).
- `calistir.sh` başlamadan önce **8000/3000 portlarını kontrol eder** ve doluysa PID'i ve
  çözüm komutlarını yazıp çıkar. Bu kontrol bilinçli olarak eğitimden ÖNCE yapılır. Ayrıca
  sunucuların hazır olup olmadığı yalnızca porta `curl` atarak değil, **başlatılan sürecin
  yaşadığı** (`kill -0 $PID`) da kontrol edilerek anlaşılır — aksi hâlde port doluyken uvicorn
  ölse bile eski sunucu cevap verdiği için script "API hazır" deyip bayat sunucuya bağlanıyordu.
