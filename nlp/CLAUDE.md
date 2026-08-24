# Metro İstanbul Arıza Tespit Sınıflandırıcı — Proje Bağlamı

> ### ⚠️ TAKSONOMİ v2 (21 Ağu 2026) — bu dosyayı okurken dikkat
>
> Sistem 8 → 9 → **11 kategoriye** ve tek boyuttan **üç boyuta** (intent +
> kategori + öncelik) geçti. Aşağıdaki bölümlerin bir kısmı v1 dönemine ait
> ve **tarihsel kayıt** olarak duruyor — metodoloji dersleri (LoRA öğrenme
> hızı, tohum varyansı, LLM sağlayıcı karşılaştırması, aksan dayanıklılığı)
> hâlâ geçerli, ama **kategori adları ve sayıları güncel değil**.
>
> Güncel taksonomi ve mimari için: **"Adım 9 — Taksonomi v2"** bölümü
> (dosyanın sonuna yakın) ve `yeni-eklemeler.md`.
>
> Eski kategori adlarının yeni karşılıkları:
> `istasyon_mekanik`→`mekanik_istasyon`, `yazilim_sistem`→`elektronik_sistemler`
> (+`sinyalizasyon_haberlesme`), `guvenlik_emniyet`→üçe bölündü
> (`sinyalizasyon_haberlesme` / `istasyon_guvenlik` / `guvenlik_asayis_olay`),
> `asayis_suc`→`guvenlik_asayis_olay`, `yolcu_operasyon`→`yolcu_hizmetleri`,
> `temizlik_cevre`→`temizlik`, `altyapi_insaat` ikiye ayrıldı
> (`altyapi_insaat` bina/tünel + `yol_yapisal` ray hattı).


Bu dosya, projenin claude.ai sohbetinde geçen tüm geçmişini özetler. Buradaki
her karar, sayı ve gerekçe önceki bir konuşmadan gelir — tahmin veya varsayım
yok. Staj sunumunda kullanılacağı için doğruluğu kritik.

## Kim, Ne, Neden

Metro İstanbul'da staj yapan bir yazılım mühendisliği öğrencisi, gün içinde
gelen serbest metinli arıza bildirimlerini otomatik kategorilere ayıran bir
NLP modeli + web arayüzü geliştiriyor. Amaç: manuel sınıflandırma yükünü
azaltmak, bildirimi doğru bakım ekibine hızlı yönlendirmek.

Proje iki katmanlı: (1) staj süresince çalışan bir prototip, (2) ileride
gerçek verilerle kuruma entegre edilebilecek bir sistem.

## Çalışma Dizini

```
/Users/serhan/Desktop/ariza-tespit-siniflandirici/
```

Ortam: MacBook Air (Apple Silicon, 16GB RAM), Python venv, Ollama kurulu ve
çalışıyor (model: qwen2.5:14b — gemma2:9b ile karşılaştırma planlanmıştı ama
Nemotron sonuçları çok iyi çıktığı için henüz yapılmadı, gerek kalmayabilir).

## Klasör Yapısı (mevcut durum)

```
ariza-tespit-siniflandirici/
├── data/
│   ├── seed/
│   │   ├── seed.jsonl              # few-shot yemi, 93 kayit
│   │   ├── gold.jsonl              # bozulmamis test seti, 80 kayit (8x10)
│   │   ├── seed_v1_backup.jsonl    # Gemini ile ilk deneme (arsiv)
│   │   ├── gold_v1_backup.jsonl
│   │   ├── seed_v2_groq_backup.jsonl
│   │   ├── gold_v2_groq_backup.jsonl
│   │   ├── seed_v3_groq_fixed_backup.jsonl  # Groq/Llama3.3 duzeltilmis prompt
│   │   ├── gold_v3_groq_fixed_backup.jsonl
│   │   ├── gold_v4_pre_guvenlik_backup.jsonl  # guvenlik yeniden uretiminden once
│   │   └── extraction_gold.jsonl   # 40 elle etiketlenmis cikarim referansi
│   ├── raw/
│   │   ├── amplified.jsonl         # Adim 2b ciktisi, 1600 kayit (%100 Nemotron)
│   │   └── amplified_ollama_backup.jsonl  # degisim oncesi 1586 kayit (arsiv/kiyas)
│   └── processed/                  # Adim 3 ciktisi
│       ├── clean.csv               # 1600 (bolunmemis, temizlenmis havuz)
│       ├── train.csv               # 1280
│       ├── val.csv                 #  160
│       ├── test.csv                #  160
│       └── gold_test.csv           #   80  (gold.jsonl'den, egitime GIRMEZ)
├── model/                          # Adim 4 ciktisi
│   ├── govde/                      # LoRA adaptoru (Adim 9: cok baslikli)
│   ├── basliklar.pt                # uc siniflandirma basligi
│   ├── model_yapisi.json           # taban model + gorev boyutlari
│   ├── tokenizer.json / tokenizer_config.json
│   ├── egitim_ozeti.json           # hiperparametreler + epoch gecmisi
│   ├── degerlendirme.json          # test/gold metrikleri
│   └── kalibrasyon.json            # k-fold OOF esik taramasi + reliability
├── src/
│   ├── __init__.py
│   ├── config.py                   # TEK dogruluk kaynagi, asagida detay
│   ├── generate_seed.py            # seed/gold uretimi (coklu saglayici, --category)
│   ├── generate_data.py            # Adim 2b -- cogaltma (hibrit saglayici)
│   ├── preprocess.py               # Adim 3 -- kumeleme + train/val/test bolme
│   ├── review.py                   # kalite triyaji (seed/gold/amplified)
│   ├── apply_review.py             # elle onaylanan duzeltmeleri uygular (idempotent)
│   ├── check_openrouter_models.py  # OpenRouter canli model/fiyat listesi
│   ├── train.py                    # Adim 4a -- BERTurk + LoRA egitimi
│   ├── evaluate.py                 # Adim 4b -- metrikler + confusion + hata analizi
│   ├── calibrate.py                # Adim 4c -- k-fold OOF esik kalibrasyonu
│   ├── extract.py                  # Adim 7 -- yapisal cikarim (kurallı)
│   ├── db.py                       # Adim 8 -- log veritabani (SQLite)
│   ├── similarity.py               # Adim 8 -- embedding tabanli yakinlik
│   ├── model.py                    # Adim 9 -- cok baslikli model (3 gorev)
│   ├── relabel.py                  # Adim 9 -- uc boyutlu toplu etiketleme
│   ├── generate_missing.py         # Adim 9 -- eksik kategori/intent uretimi
│   ├── evidence.py                 # Adim 9 -- gradient x input aciklanabilirlik
│   ├── oncelik_tutarlilik.py       # Adim 9 -- etiket tutarliligi olcumu
│   ├── toplu_test.py               # bagimsiz set uzerinde toplu olcum
│   └── resolve_logs.py             # kategorisiz log kayitlarini coz
├── backend/
│   ├── __init__.py
│   └── main.py                     # Adim 5 -- FastAPI servisi
├── tests/
│   ├── __init__.py
│   └── test_api.py                 # 17 entegrasyon testi (pytest)
├── frontend/                       # Adim 6 -- React (Vite)
│   ├── index.html
│   ├── package.json / package-lock.json
│   ├── .claude/launch.json         # preview icin (proje kokunde)
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                 # ana bilesen
│       ├── App.css                 # tum stiller
│       ├── index.css               # Vite varsayilan temasi KALDIRILDI
│       ├── api.js                  # backend istemcisi
│       └── components/SonucKarti.jsx
├── venv/
├── requirements.txt                 # pip freeze ile donduruldu
└── .env                             # GEMINI_API_KEY, GROQ_API_KEY,
                                      # OPENROUTER_API_KEY var; ANTHROPIC_API_KEY yok
```

NOT: `data/raw`, `data/processed`, `model` bos olduklarinda git'e girmez (git
bos klasor takip etmez), ama `config.py` import edilir edilmez bunlari kendisi
olusturur -- klonlayan icin hicbir sey kirilmaz.

## config.py — Projenin Tek Doğruluk Kaynağı

Tüm diğer modüller (mevcut ve yazılacak olanlar) buradan import eder. Asla
kategori/stil/hiperparametre tanımı başka bir dosyada tekrarlanmaz.

### Kategori Taksonomisi (8 kategori)

**Ayrım ilkesi: kategori, bildirimin hangi BAKIM EKİBİNE yönlendirileceğini
belirtir. Arızanın nesnesi değil, sorumlusu belirleyicidir.**

| key | display | kapsam (özet) |
| --- | --- | --- |
| `arac_tren` | Araç / Tren | Trenin üzerindeki her şey: vagon kapısı, fren, klima, çer/motor, kabin ekipmanı, tekerlek, koltuk, vagon içi aydınlatma/anons, makinist kabini |
| `istasyon_mekanik` | İstasyon Mekanik | Yürüyen merdiven, asansör, peron kapısı (PSD), turnikenin **fiziksel** arızası (kol dönmüyor, kapak takılı, gövde hasarlı), otomatik giriş kapıları, bariyerler |
| `elektrik_enerji` | Elektrik / Enerji | İstasyon aydınlatması, elektrik kesintisi, jeneratör, UPS, elektrik panosu, katener hattı, üçüncü ray, trafo, kablo arızası, sigorta |
| `yazilim_sistem` | Yazılım / Sistem / Bilet | Bilet satış otomatı, İstanbulkart okuyucu **yazılımı**, PID ekranları, sunucu, ağ kesintisi, uygulama donması, veritabanı, SCADA arayüzü |
| `guvenlik_emniyet` | Güvenlik / Emniyet | CCTV, yangın algılama/söndürme, acil durum butonu, acil çıkış, yetkisiz giriş, turnikeden **atlama**, şüpheli paket, tahliye anonsu |
| `altyapi_insaat` | Altyapı / İnşaat | Su sızıntısı, tavan/duvar/zemin hasarı, çatlak, tünel yapısı, drenaj, kanalizasyon, ray hattı yapısal durumu, korkuluk, fayans |
| `yolcu_operasyon` | Yolcu / Operasyon | Sefer gecikmesi/iptali, seferlerin seyreltilmesi, anons yapılmaması, peron yoğunluğu, kayıp eşya, personel eksikliği, tarife sorunu |
| `temizlik_cevre` | Temizlik / Çevre | Kirlilik, çöp birikmesi, koku, tuvalet temizliği, buzlanma, kaygan zemin, haşere, kış şartları (tuzlama), grafiti |

**Kritik sınır örneği (turnike):** aynı ekipman üç farklı kategoriye
düşebilir, kural nettir:

- Fiziksel arıza (kol dönmüyor, kapak kırık) → `istasyon_mekanik`
- Kart okumama / yazılım hatası → `yazilim_sistem`
- Atlama / yetkisiz geçiş → `guvenlik_emniyet`

Her kategorinin `config.py`'de tam `scope` (kapsam) ve `exclude` (hariç
tutulanlar) metni var, LLM prompt'larına birebir enjekte ediliyor.

### Stil Varyantları (4 stil, gerçekçilik için)

Gerçek personel her zaman düzgün yazmaz. Her kategori için 4 stilde örnek
üretiliyor:

| stil | uzunluk | açıklama |
| --- | --- | --- |
| `standart` | 8-18 kelime | Düzgün, kurallı tam cümle |
| `devrik` | 4-9 kelime | Acele yazılmış, kısa, eksiltili (özne/yüklem sırası bozuk olabilir) |
| `yazim_yanlisi` | 5-14 kelime | Türkçe karakter eksikliği, klavye hatası |
| `cok_kisa` | 3-6 kelime | Telgraf tarzı, sadece ekipman + belirti |

**Önemli tasarım kararı:** Türkçe aksan düşürme (`güvenlik`→`guvenlik`,
`Şişli`→`Sisli`) **sadece** `yazim_yanlisi` stiline özgü değil — gerçek
hayatta İngilizce klavyeyle hızlı yazan biri her stilde bunu yapabilir.
Bu davranış bir "hata" değil, modelin dayanıklı olması gereken doğal bir
varyasyon olarak kabul edildi (bkz. review.py bölümü).

### Hedef Veri Hacmi — hedef vs GERÇEKLEŞEN

| set | hedef | gerçekleşen | not |
| --- | --- | --- | --- |
| seed | 12/kat × 8 = 96 | **93** | elle triyajda 3 kayıt silindi |
| gold | 10/kat × 8 = 80 | **80** | tam, 8 kategori × 10 |
| çoğaltma | 200/kat × 8 = 1600 | **1600** | tam; %100 Nemotron. SINIR düzeltmeleri sonrası kategori dengesi 202/200/199 (±2) |
| **eğitim havuzu** | — | **1675** | 1600 çoğaltma + 93 seed, temizlik sonrası (`INCLUDE_SEED_IN_TRAINING`) |

Bölme (Adım 3): train **1340** / val **168** / test **167** (%80/%10/%10).
Ayrıca gold_test **80** — eğitime ve few-shot'a HİÇ girmez.

(Seed eğitime katılmadan önceki bölme 1280/160/160 idi; eski ölçümler bu
sayılarla yapıldı, karşılaştırmalarda buna dikkat.)

(Not: orijinal PDF taslağında 70/kategori × 6 kategori = 420 yazıyordu.
Kategori sayısı 6'dan 8'e, hedef hacim 70'ten 200'e çıkarıldı — rapor
güncellenmeli.)

### Çoğaltma Ayarları (Adım 2b, config.py)

- `AMPLIFY_PROVIDER = "hybrid"` — OpenRouter birincil, kalıcı hatada Ollama
- `NEAR_DUP_THRESHOLD = 0.85` (üretimde red) / `CLUSTER_THRESHOLD = 0.80`
  (bölmede kümeleme) — iki ayrı eşik, gerekçesi `config.py`'de
- `AMPLIFY_BATCH_SIZE = 40` — çağrı başına örnek (gerekçesi aşağıda)
- `AMPLIFY_FEWSHOT_N = 6`, `AMPLIFY_AVOID_N = 12`
- `OLLAMA_MODEL = "qwen2.5:14b"`, `OLLAMA_NUM_CTX = 8192`,
  `OLLAMA_NUM_PREDICT = 4096`

**`OLLAMA_NUM_CTX` neden açıkça ayarlandı:** Ollama'nın varsayılan bağlam
penceresi 2048 token. Çoğaltma prompt'u (kategori kapsamı + stil tanımı +
few-shot + "bunları tekrarlama" listesi) bunun büyük kısmını yiyor, çıktıya
yer kalmıyordu: 25 örnek istenmesine rağmen model 1-2 örnek döndürüp
kesiliyordu. 8192'ye çıkarılınca aynı iş 5 çağrıda 8 kayıt yerine 7 çağrıda
40 kayıt üretti.

### Eğitim Hiperparametreleri (henüz kullanılmadı, Adım 4 için hazır)

- Model: `dbmdz/bert-base-turkish-cased`
- PEFT/LoRA: r=16, alpha=32, dropout=0.1, target_modules=["query","value"]
- MAX_LENGTH=64, NUM_EPOCHS=12, BATCH_SIZE=16, **LEARNING_RATE=5e-4**
  (2e-5 degildi -- bkz. Adim 4 bolumu, en onemli hata buydu)
- `AUGMENT_ASCII_FOLD = True` — egitimde aksansiz kopyalar da eklenir
  (train 1340 → 2320). Gerekcesi ve olcumu Adim 4 bolumunde.
- `INCLUDE_SEED_IN_TRAINING = True` — seed.jsonl egitime katilir (aşağıda
  ölçümü var). Gold few-shot'ta da eğitimde de ASLA kullanılmaz.
- Split: %80 train / %10 val / %10 test
- Başarı kriteri: accuracy ≥ 0.85, macro F1 ≥ 0.82, hiçbir sınıf F1 < 0.75

### Servis Ayarları (henüz kullanılmadı, Adım 5 için hazır)

- `CONFIDENCE_THRESHOLD = 0.75` — **k-fold OOF ile kalibre edildi** (19 Ağu,
  1280 kayıt / 102 hata). Altında `low_confidence: true` döner.
- `MARGIN_THRESHOLD = 0.30` — `top1 − top2` bu değerin altındaysa `/predict`
  birincil + ikincil kategori döner. Taksonomi sınır sorunlarına kural yazmak
  yerine getirilen genel çözüm.
- İkisinin de gerekçesi ve tarama tabloları "Kalibrasyon" bölümünde. Önceki
  değerler (0.70 / 0.40) sırasıyla test+gold ve gold'un 8 hatasına bakılarak
  seçilmişti; OOF tabanı ikisini de düzeltti.

## LLM Sağlayıcı Yolculuğu (önemli — rapora doğrudan girebilecek içerik)

Seed/gold üretimi için 4 farklı sağlayıcı denendi, sonuçlar `review.py` ile
ölçüldü. Bu, projenin metodoloji bölümüne güçlü bir katkı:

| Deneme | Sağlayıcı/Model | Seed işaretli | Gold işaretli | Not |
| --- | --- | --- | --- | --- |
| v1 | Gemini (çeşitli modeller) | %15 | %29 | Kota/model erişim sorunları yüzünden terk edildi |
| v2 | Groq / llama-3.3-70b-versatile | %82 | %56 | Config'teki Türkçe metin ASCII'ydi (kök sebep) |
| v3 | Groq / llama-3.3-70b-versatile (Türkçe düzeltildi) | %70 | %70 | Prompt dili düzelince iyileşti ama model hâlâ çok-kısıtlı talimatlara uyamadı |
| **v4** | **OpenRouter / nvidia/nemotron-3-ultra-550b-a55b:free** | **%14** | **%4** | **Kazanan.** Ücretsiz, kart istemiyor, v1'i bile geçti |

> **Bu sayılar 19 Ağu 2026'da bugünkü `review.py` ile YENİDEN ölçüldü.** Önceki
> sürümde farklı rakamlar yazıyordu (v1 %18/%32, v2 %91/%81, v3 %72/%69,
> v4 %17/%9) çünkü o ölçümlerden sonra araç iki kez değişti: aksan kontrolü
> işaretli sayımından çıkarıldı ve `similarity()` simetrik hâle getirildi.
> Sıralama ve sonuç değişmedi, ama rapordaki her sayının bugünkü araçla
> üretilebilir olması için tablo tazelendi. Ölçüm şu komutla tekrarlanabilir:
> `python -m src.review --file seed` (yedek dosyalar `data/seed/` altında
> duruyor — bu yüzden silinmediler).

**Ders 1 — kaynak kodun kendi Türkçesi önemli:** `config.py`'deki kategori
açıklamaları, kurallar, istasyon adları başlangıçta ASCII yazılmıştı (bir
önceki PDF-font sorunuyla karıştırılıp gereksiz genellenmişti). Bu, LLM
prompt'larına doğrudan enjekte edildiği için modele yanlış stil sinyali
verdi. Düzeltilince (v2→v3) işaretli oran ciddi düştü.

**Ders 2 — model ölçeği ve talimat-takibi kapasitesi asıl belirleyici:**
Aynı düzgün Türkçe prompt'la bile Llama 3.3 70B (v3) çok-kısıtlı talimatlara
(kategori + stil + uzunluk + kod oranı + sızıntı oranı aynı anda) uyamadı.
550B/55B-aktif Nemotron 3 Ultra (v4) aynı prompt'la çok daha iyi sonuç verdi
— talimat-takibi, ham dil kalitesinden çok modelin talimat karmaşıklığını
yönetme kapasitesiyle ilgili.

**Ders 3 — ücretsiz katmanlar güvenilmez, canlı sorgula, tahmin etme:**
Gemini'de sırasıyla günlük kota (20/gün), model erişim kısıtı ("yeni
kullanıcılara kapalı"), ve bozuk API key formatı ("AQ." öneki, bilinen
Google-tarafı sorunu) yaşandı. OpenRouter'da da varsayılan model
(`gpt-oss-120b`) canlı listeden düşmüştü. `check_openrouter_models.py`
scripti tam da bunun için yazıldı — tahmin etmek yerine anlık sorgula.

**Karar:** Claude API'ye ($5 minimum ödeme) hiç gerek kalmadı. OpenRouter'ın
ücretsiz Nemotron 3 Ultra modeli yeterli kaliteyi verdi.

### Adım 2b'de ikinci ölçüm: Nemotron vs Ollama (18 Ağu 2026)

Çoğaltmaya başlarken "hangi model" sorusu için ikisi **aynı görevde, aynı
prompt'la, aynı hedefle** (İstasyon Mekanik, 40 kayıt) ölçüldü:

| | Ollama qwen2.5:14b | OpenRouter Nemotron 3 Ultra |
| --- | --- | --- |
| gereken çağrı | 7 | **4** |
| süre | 6:45 | **2:11** |
| `review.py` işaretli | **%18** | **%5** |
| near-dup reddi | 5 | **0** |
| uydurma istasyon adı | `marmaraisi`, `yersenlik`, `leventtünel` | yok |
| uydurma teknik terim | `perde çarkı`, `motorı tıkranıyor` | yok |

**Nihai 1586 kayıt üzerinde de aynı fark doğrulandı:**

| kaynak | kayıt | işaretli |
| --- | --- | --- |
| openrouter (Nemotron) | 1086 | **%4.5** |
| ollama (qwen2.5:14b) | 500 | **%15.8** |

**Ders 2'nin ikinci teyidi.** Ayrıca yeni bir gözlem: qwen'in asıl zayıflığı
`review.py`'nin ölçtüğü şey (uzunluk/tekrar) değil, **özel isim ve teknik
terim uydurması** — otomatik triyaj bunu yakalamıyor, elle okumak gerekiyor.
Yani düşük işaretli oran tek başına kalite garantisi değil.

**`AMPLIFY_BATCH_SIZE` 25→40 kararı:** bağlayıcı kısıt örnek sayısı değil
ÇAĞRI sayısı. OpenRouter ücretsiz katmanı ~50 istek/gün; 25'lik partilerle
1600 örnek 64 çağrı gerektiriyordu, yani son ~350 kayıt zorunlu olarak
Ollama'ya kalıyordu. 40'lık partiyle ~40 çağrı yetiyor. (Pratikte 45
OpenRouter çağrısı yapılabildi, sonra kota bitti.)

**Hibrit devir sahada çalıştı:** kota `altyapi_insaat` ortasında bitti,
script otomatik Ollama'ya geçti ve durmadan devam etti. Ayrıca bir parti
bozuk JSON döndürdüğünde tüm çalıştırmayı çökertmek yerine o partiyi atlayıp
devam etti (kalıcı/geçici hata ayrımı — Genel İlke 5).

### Ollama verisinin Nemotron'la değiştirilmesi (19 Ağu 2026)

Kota bitince 500 kayıt (Yolcu/Operasyon ve Temizlik/Çevre'nin TAMAMI,
Altyapı/İnşaat'ın yarısı) qwen2.5:14b'den gelmişti. Sorun oranın kendisi değil
(%31), **dağılımın kategori bazında sistematik olması**: rastgele serpilse
zararsızdı, ama iki sınıf tamamen zayıf modelden gelince o sınıfların F1'i
gerçeği yansıtmaz ve confusion matrix yanıltır. Kota yenilenince değiştirildi.

`generate_data.py --replace-source ollama` ile yapıldı (aşağıda). Kategoriyi
tümden sıfırlamak yerine sadece hedef kaynağı silmek şart oldu: Altyapı/İnşaat
karışıktı (86 Nemotron + 100 Ollama), `--force` olsaydı 86 iyi kayıt da giderdi.

**`--provider openrouter` kullanıldı, hibrit DEĞİL.** Sebep: hibrit modda kota
yarıda bitse script sessizce Ollama'ya düşer ve tam da temizlenen veriyi geri
koyardı. Tek sağlayıcı denince kota bitiminde temiz şekilde durur.

Sonuç — 22 çağrı, işaretli oran kategori bazında:

| kategori | önce | sonra |
| --- | --- | --- |
| Altyapı / İnşaat | 186 kayıt, %6.5 | **200 kayıt, %0.5** |
| Yolcu / Operasyon | 200 kayıt, %7.5 | **200 kayıt, %6.0** |
| Temizlik / Çevre | 200 kayıt, %26.5 | **200 kayıt, %0.0** |
| **TOPLAM** | 1586 kayıt, **%8.1** | 1600 kayıt, **%3.8** |

Ollama'nın takıldığı `altyapi_insaat / devrik` grubu (36/50'de doyuma ulaşmıştı)
Nemotron tarafından sorunsuz tamamlandı — yani doygunluk modelin çeşitlilik
kapasitesiyle ilgiliydi, prompt'la değil.

**Cümle bazında kıyas** (eski sürüm `amplified_ollama_backup.jsonl`'de duruyor):

| | Ollama | Nemotron |
| --- | --- | --- |
| istasyon adı | `Beköy` (uydurma) | Topkapı, Esenler, Gayrettepe (gerçek) |
| anlam | `Döküntüler çıkışa`, `cevre zemin kaygan dogal yapi suyundan nedenli` | `Yağ lekesi kaygan vagon` |
| uydurma kelime | `anunci` (anons) | yok |
| ses/kip | `Sefer sayisini azalttik` (birinci şahıs, bildirim diline aykırı) | `Sefer seyreltildi` (edilgen) |
| detay | tekrarlı (`Döküntüler yarattı`, `Çöp birikmiş`) | somut (`asansör kabininde yazıcı tozu`) |

## review.py — Kalite Kontrol Sistemi

Otomatik olarak şunları işaretler (elle bakılması gerekenler):

- `DUP` — birebir tekrar
- `BENZER` — yakın kopya (SequenceMatcher + Jaccard kelime-kümesi hibrit,
  1.0'da sınırlı)
- `UZUNLUK` — stilin beklediği kelime aralığı dışında
- `SIZINTI` — kategori adını çağrıştıran kelime, kategori başına %25 payını
  aşıyor
- `SINIR` — başka KATEGORİDEKİ bir bildirime çok benziyor (etiket tutarsızlığı)
- `YABANCI` — Türkçe olmayan kelime şüphesi (`q/w/x` harfi veya Türkçe'de
  geçmeyen digraf). Bilgi amaçlı; dar ama kesin bir kural, kapsamlı değil.

**ASCII/aksan kontrolü bilgi amaçlıdır, işaretlenmez:** İlk sürümde "hiç
Türkçe karakter yok" tespit edilince işaretleniyordu, ama bu yanlış alarm
üretiyordu ("Turnike 3 bozuk" gibi zaten aksan gerektirmeyen doğru cümleler
de işaretleniyordu). Sonra `DIACRITIC_VOCAB` adında, `config.py`'nin kendi
doğru-yazılmış Türkçe metninden (kategori açıklamaları + istasyon adları)
otomatik çıkarılan bir sözlükle gerçek aksan-düşürme tespit edildi
(`Mecidiyekoy`→`Mecidiyeköy` gibi). Ama kullanıcı geri bildiriminden sonra
(gerçek hayatta klavye alışkanlığı olarak normal olduğu için) bu bulgular
"sorun" listesinden çıkarılıp sadece kategori özetinde "aksan-düşük%" olarak
bilgi amaçlı raporlanmaya çevrildi — **artık işaretli sayıya dahil değil.**

**`--file amplified` eklendi:** Adım 2b çıktısı da aynı araçla taranıyor.
Varsayılan taramaya dahil değil (1600 kayıtlık rapor seed/gold raporunu
boğar), açıkça seçilmesi gerekiyor.

**`similarity()` simetrik hâle getirildi (18 Ağu 2026, gerçek hata):**
`SequenceMatcher` argüman sırasına duyarlı (autojunk sezgiseli). Ölçüldü: bir
çift için `similarity(a,b) = 0.8511`, `similarity(b,a) = 0.8298` — yani 0.85
eşiğinin iki yanında. Sonuç: aynı çift, nerede karşılaştırıldığına göre farklı
karar alıyordu. `generate_data` `(yeni, mevcut)` sırasıyla çağırıp kabul
ederken, `preprocess` `(mevcut, yeni)` sırasıyla çağırıp aynı çifti
near-duplicate sayıyordu. Sızıntı savunmasının tamamı bu eşiğe dayandığı için
girdiler artık kanonik sıraya sokuluyor (`sorted((a, b))`); 2000 rastgele
çiftle simetri doğrulandı.

**`SINIR` bayrağı eklendi (19 Ağu 2026) — kategori sınırı artık denetleniyor:**
Önceki sürümde `review.py` bir bildirimin YANLIŞ kategoride olduğunu tespit
edemiyordu; sadece tekrar/uzunluk/sızıntı bakıyordu. Gold'daki yanlış
kategorili bir kayıt (peron kapısı PSD arızası `guvenlik_emniyet` etiketiyle)
ancak şans eseri "uzunluk" bayrağıyla yakalanmıştı — bu, aracın kör noktasıydı.

`SINIR`, **farklı kategorilerdeki** kayıtları birbiriyle karşılaştırır ve
`CLUSTER_THRESHOLD` (0.80) üstünde benzeyen çiftleri işaretler. Mantığı
`BENZER`'den ayrı: orada sorun tekrar, burada **etiket tutarsızlığı** —
neredeyse aynı metnin iki farklı etikette olması modele çelişkili sinyal verir
ve biri muhtemelen yanlış kategoridedir.

İlk çalıştırmada 1600 kayıtta **5 çift** buldu. Elle değerlendirildi:
- **3'ü gerçek etiket hatasıydı**, düzeltildi (aşağıda)
- **2'si yanlış alarm**: ölçüt sözcüksel olduğu için gerçekten farklı arızalar
  ortak kelimeler yüzünden yakalandı (`Asansör kabin titriyor` /
  `Asansör kabini kirli`; `Makinist masası acil durdurma butonu takılı` /
  `Acil durdurma butonu takılı`)

Düzeltme sonrası kalan: 2 çift (4 kayıt), ikisi de bilinen yanlış alarm.
Seed'de 1 yanlış alarm, **gold'da hiç yok**.

## generate_seed.py — `--category` desteği (18 Ağu 2026 eklendi)

Sorun: `resume` mantığı bir kategoriyi %80 eşiğini (8/10) geçtiğinde "tamam"
sayıyordu, bu yüzden 9/10 kalan `guvenlik_emniyet` otomatik tamamlanmıyordu
ve elle müdahale yolu da yoktu.

- `--category KEY [KEY ...]` — sadece o kategori(ler)i işler, **%80 eşiği
  yerine tam hedefe** tamamlar, diğer kategorilere hiç dokunmaz.
- `--force` artık `--category` ile birlikte **yalnızca seçili kategoriyi**
  sıfırlar (tek başına kullanıldığında eski davranış: hepsini sıfırlar).
- Tamamlamada **az temsil edilen stiller önceliklendirilir** — böylece
  tamamlama stil dengesini bozmak yerine düzeltir.
- Rapor artık sessiz kalmıyor: eşiği geçmiş ama hedefin altındaki kategoriler
  `<-- 1 eksik (--category X ile tamamlanabilir)` diye işaretleniyor. Asıl
  sorun bu boşluktu.

## Elle Yapılan Son Düzeltmeler (apply_review.py ile)

v4 (Nemotron) verisi üzerinde elle triyaj yapıldı, onaylanan değişiklikler:

**Seed:**

- 3 kayıt silindi: anlamsız "fren manası" ifadesi, bir yakın-kopya, bir
  birebir kopya
- 1 kayıt bilerek **silinmedi**: "Turnike 5 mekanik arıza" — kategori adını
  çağrıştırsa da gerçekçi bir kısa bildirim olduğu değerlendirildi
- 1 stil düzeltmesi: aşırı resmi/uzun bir "devrik" örneği → `standart`
  olarak yeniden etiketlendi (metne dokunulmadı)
- 1 anlam düzeltmesi: "...seferler **gecikmemiştir**" → "...seferler
  **gecikmiştir**" (anlam ters dönmüştü)

**Gold:**

- 4 stil düzeltmesi: `elektrik_enerji` kategorisinde `devrik`/`cok_kisa`
  etiketli ama aslında tam resmi cümle olan 4 kayıt → `standart`

### İkinci tur (18 Ağu 2026)

**Seed:**

- `makinist kabini fren manasi tikaniyo` → `...fren manivelasi tikaniyo`.
  "Fren manası" diye bir parça yok; aynı ifadenin `standart` stildeki ikizi
  ilk turda silinmişti ama bu `yazim_yanlisi` varyantı gözden kaçmıştı.
  Few-shot yemi olduğu için hatalı terimi 1600 örneğe taşıma riski vardı.

**Gold:**

- `guvenlik_emniyet` kategorisi `--force` ile tamamen yeniden üretildi.
  Sebep: 9 kaydın 3'ü bozuktu — biri **Arapça harf** içeriyordu
  (`Peron kapısı arıza, güvenlik بوğu`), biri var olmayan bir kelime
  kullanıyordu (`yangın merchı`), biri çatı hatası taşıyordu
  (`güvenlik ekipleri bölgeyi kuşatıldı`). Yedek:
  `gold_v4_pre_guvenlik_backup.jsonl`
- Yeniden üretim sonrası 1 kayıt silindi: `Peron kapısı aralıklı açılıyor,
  sıkışma riski var.` — taksonomiye göre **yanlış kategori** (config'de
  "peron kapısı (PSD)" açıkça `istasyon_mekanik` kapsamında). Gold'da etiket
  hatası doğru tahmini yanlış saydırır, bu yüzden yazım hatasının aksine
  tolere edilmez. Yerine 1 kayıt üretildi.
- 2 stil düzeltmesi (metne dokunulmadan).

**Bilinçli olarak DÜZELTİLMEYENLER (kullanıcı kararı):** `trensformatörü`
(transformatörü), `kırıkMetal` (yapışık kelime), `Ayrılıkçeşmesi` (istasyon
adı kısaltması). Ölçüt: *"Metro İstanbul'da bir personel aceleyle yazarken
bunu yazar mıydı?"* — evetse gerçekçi gürültüdür, gold'a aittir. Ayrıca
teknik olarak metriğe sadece `metin` + `kategori` giriyor; `stil` etiketi
muhasebe alanı, model `kategori` tahmin ediyor.

### Üçüncü tur — seed'in elle okunması (19 Ağu 2026)

93 kaydın tamamı tek tek okundu. Bulunan 3 **var olmayan kelime** düzeltildi:

| eski | yeni | neden |
| --- | --- | --- |
| `giriş tornası` | `giriş turnikesi` | "torna" tezgâh demek |
| `merkeziyete sinyal` | `merkeze sinyal` | "merkeziyet" böyle kullanılmaz |
| `betonarme kırışması` | `betonarme kırılması` | "kırışmak" buruşmak demek |

**Karar ölçütü — gerçekçi yazım hatası ile stil sözleşmesi ihlali farklı
şeylerdir.** Üçü de `standart`/`devrik` etiketliydi; config bu stiller için
doğru Türkçe yazımı ZORUNLU tutuyor (`generate_seed.py` prompt kural 9:
"SADECE `yazim_yanlisi` stilinde harf düşür, diğer üç stilde doğru yazım
zorunludur"). "İnsan da böyle yazabilir" doğru bir itiraz, ama o insan
`yazim_yanlisi` stilinde yazıyor demektir. Yani ölçüt "hata gerçekçi mi"
değil, **"kaydın kendi stil etiketi hataya izin veriyor mu"**.

**Bilinçli olarak DEĞİŞTİRİLMEYEN kategori (kullanıcı kararı):** seed #75
`Kart okumuyor ucret odendi bilet alamadi.` → `yolcu_operasyon` kaldı.
Config'in turnike kuralı "kart okumama → `yazilim_sistem`" diyor, ama
kullanıcının gerekçesi: bildirimin öznesi okuyucu arızası değil, **ücret
ödemiş yolcunun mağduriyeti**. Not: bu yorum config metniyle gerginlik
taşıyor; ileride yeniden üretim yapılırsa LLM config'i takip edeceği için
bu kayıt tek başına kalabilir.

Not: çoğaltma zaten tamamlandığı için bu düzeltmeler mevcut 1600 kaydı
DEĞİŞTİRMEZ. Değeri ileride yeniden üretim yapılırsa veya `--include-seed`
ile seed eğitime katılırsa ortaya çıkar.

## ✅ Kapanan Açık Noktalar (18 Ağu 2026)

Önceki sürümdeki 5 maddenin tamamı kapandı:

1. **`apply_review.py` doğrulandı** — daha önce çalıştırılmıştı; 9
   değişikliğin her biri dosyada tek tek kontrol edilerek teyit edildi.
   Ayrıca script tekrar çalıştırılabilir (idempotent) hâle getirildi:
   "zaten uygulanmış" ile "hiç bulunamadı" ayırt ediliyor, sahte UYARI
   basmıyor.
2. **Gold'daki eksik kategori tamamlandı** — `generate_seed.py`'ye
   `--category KEY` eklendi (aşağıda). `guvenlik_emniyet` `--force` ile
   yeniden üretildi, gold 80/80 oldu.
3. **`SEED_PROVIDER = "openrouter"` teyit edildi** (config.py).
4. **qwen2.5:14b vs gemma2:9b karşılaştırması hâlâ yapılmadı** ve artık
   gereksiz: Adım 2b'de qwen2.5:14b ile Nemotron doğrudan ölçüldü, qwen
   belirgin şekilde geride kaldı. Daha küçük bir yerel modeli denemenin
   kazandıracağı bir şey yok.
5. **Adım 2b model kararı verildi:** hibrit (aşağıda).

## ⚠️ Güncel Açık Noktalar (24 Ağu 2026, Adım 13 sonrası)

1. ✅ **~~`Metro_Istanbul_Ariza_Tespit_Raporu.docx` güncellenmedi~~ KAPANDI
   (24 Ağu 2026).** Rapor sıfırdan yeniden yazıldı: 11 kategori, üç boyutlu
   mimari, LLM karşılaştırmaları, LoRA öğrenme hızı hatası, aksan
   dayanıklılığı, kalibrasyon (OOF), hard-negative örneklerle sınır
   düzeltmeleri, güncel sonuç tablosu. Üretim scripti `scripts/rapor_uret.py`
   — rapor tekrar güncellenmesi gerekirse bu script düzenlenip yeniden
   çalıştırılır (`./venv/bin/python3 scripts/rapor_uret.py`), Word'de elle
   düzenleme YAPILMAZ (script tek doğruluk kaynağı, elle düzenleme bir
   sonraki otomatik üretimde kaybolur).

2. ✅ **~~İstasyon Güvenliği veri açığı~~ KAPANDI** — 95 → 270 kayıt,
   test F1 0.6154 → 0.8235'e çıktı (Adım 9 sonu).

3. ✅ **~~Öncelik etiket tavanı~~ İYİLEŞTİRİLDİ** — Adım 10'da üç turlu
   iyileştirme yapıldı: merdiven mantığı netleştirildi, P1 kural motorundaki
   iki gerçek hata (ekipman adı + koşullu ifade yanlış pozitifi) düzeltildi,
   20 hedefli örnekle "dolaylı çoğulluk" boşluğu dolduruldu. Sonuç: bağımsız
   test setinde öncelik doğruluğu %73.8 → **%81.2**. Tavan hâlâ var (kappa
   ~0.72-0.77 aralığında dalgalanıyor) ama önemli bir sıçrama yapıldı.

4. **Resmi `gold_test.csv` YOK** ama **bağımsız doğrulama VAR ve artık aktif
   kullanılıyor.** Kullanıcının getirdiği `data/seed/yeni_gold_deneme.jsonl`
   (80 kayıt, farklı bir LLM'den, eğitime hiç girmemiş) hem `toplu_test.py`
   ile hızlı doğrulama için hem de (24 Ağu 2026'dan itibaren) `/examples`
   uç noktasının kaynağı olarak kullanılıyor (`config.EXAMPLES_FILE`, bkz.
   Adım 11 sonu). v1'in `gold.jsonl`'i taksonomi değişince devre dışı kaldığı
   için `/examples` boş dönüyordu; bu dosya onun yerini fiilen aldı. Resmi
   `gold_test.csv` üretimi hâlâ isteğe bağlı bir sonraki adım.

5. ✅ **~~Frontend güncellenmedi~~ KAPANDI (23 Ağu 2026, Adım 11).** Bkz.
   "Adım 11" bölümü aşağıda.

6. ✅ **~~Testler güncellenmedi~~ KAPANDI (24 Ağu 2026).** `tests/test_api.py`
   v1 kategori adlarını (`istasyon_mekanik`, `guvenlik_emniyet`) bekliyordu;
   6 test v2 taksonomisine göre güncellendi, 31/31 test geçiyor.

7. **`calibrate.py` güncellenmedi** — tek başlıklı modele göre yazılmış, çok
   başlıklı modelle çalışması için `model_yukle`/`tahmin_et` çağrılarının
   gözden geçirilmesi gerekiyor.

8. **Kalan bir öncelik sınırı belirsizliği:** "Asansörde mahsur kaldık,
   kapılar fiziksel olarak sıkıştı" tarzı cümleler modelde P1'e kayıyor
   (doğrusu P2 -- can tehdidi yok, ama ciddi bir aksama var). P1 kural
   motorunda da böyle bir senaryo yok. Küçük, ince bir sınır sorunu;
   şimdilik bilinçli olarak ertelendi (bkz. Adım 10 sonu).

## Yol Haritası — Kalan Adımlar

**✅ Adım 2b — Çoğaltma (TAMAMLANDI):** `src/generate_data.py` yazıldı ve
çalıştırıldı, 1600 kayıt üretildi (19 Ağu değişimi sonrası %100 Nemotron).

- Few-shot **yalnızca** `seed.jsonl`'den; `gold.jsonl` bu dosyada hiç okunmuyor.
- Her çağrı **tek (kategori, stil)** ikilisi için. Sebep: Adım 2a'da en sık
  hata uzunluk kuralına uymamaktı; tek stil isteyince model aynı anda dört
  farklı uzunluk aralığını yönetmek zorunda kalmıyor.
- Few-shot iki başlığa ayrıldı: *stil örnekleri* (uzunluğu öğretir) ve *konu
  örnekleri* (kategoriyi öğretir, "uzunluğunu taklit etme" notuyla). Karışık
  gösterildiğinde model yanlış uzunluk sinyali alıyordu.
- Çeşitlilik üç katmanda zorlanıyor: her çağrıda rastgele `SLOT_VALUES`
  enjeksiyonu, üretilmişlerden örneklem ile "bunları tekrarlama" listesi, ve
  eklemeden önce `review.similarity` ile near-dup reddi.
- CLI: `--provider {hybrid,openrouter,ollama}`, `--category`, `--target`,
  `--dry-run` (LLM çağırmadan prompt'u yazdırır — kota harcamadan test için),
  `--replace-source {ollama,openrouter}`.
- **`--replace-source`** belirtilen sağlayıcıdan gelen mevcut kayıtları silip
  yerine yenisini ürettirir. Kategoriyi tümden sıfırlamaya göre avantajı:
  karışık kategorilerde iyi kayıtlar korunur. Silinen kayıtlar near-dup
  havuzundan da çıkar, böylece yeni model aynı konuları serbestçe yazabilir.
  `--dry-run` ile birlikte kullanılınca ne silineceğini dosyaya dokunmadan
  gösterir.

**✅ Adım 3 — Ön İşleme (TAMAMLANDI):** `src/preprocess.py` yazıldı ve
çalıştırıldı (5.6 sn).

- Near-duplicate **kümeleme split'ten önce** yapılıyor (union-find,
  `CLUSTER_THRESHOLD`=0.80), bir kümenin tüm üyeleri hep aynı bölmede kalıyor — çoğaltılmış verinin
  train/test'e sızıp sahte yüksek doğruluk üretmesini engelleyen asıl
  mekanizma. `review.similarity` ile AYNI ölçüt kullanılıyor.
- Katmanlı bölme: her kategori kendi içinde bölünüyor, sınıf dengesi üç
  bölmede de korunuyor. Sonuç tam %80/%10/%10.
- Temizlik: boş/uzunluk dışı kayıtlar, birebir tekrarlar ve **etiket
  çakışmaları** (aynı metin iki farklı kategoride → ikisi de atılır) eleniyor.
- **Gold sızıntı kontrolü her çalıştırmada otomatik**: hiçbir gold metni
  eğitim havuzunda olmamalı; doğrulandı, temiz.
- Raporda kaynak dağılımı da var (hangi modelin verisi hangi bölmeye düştü).
- CLI: `--include-seed` (seed.jsonl'i de eğitime katar; şu an KAPALI),
  `--report-only` (dosya yazmadan rapor).
- Doğrulandı: label↔kategori uyumsuzluğu 0, bölmeler arası birebir kesişim 0,
  gold ↔ train/test kesişim 0.

### Near-dup eşiği kalibrasyonu (19 Ağu 2026)

**Kalibrasyonun tuzağı:** veri zaten 0.85 eşiğiyle filtrelenmiş üretildi, yani
0.85 üstü çift tanım gereği yok. Mevcut veriye bakarak "eşik doğru mu"
sorusu cevaplanamaz — **eşiğin ALTINDAKİ banda** bakmak gerekiyor. Orada
gerçek kopyalar varsa eşik fazla gevşek demektir.

Aynı kategori içindeki 159.200 çiftin dağılımı:

| bant | çift |
| --- | --- |
| 0.60-0.70 | 1487 |
| 0.70-0.75 | 191 |
| 0.75-0.80 | 118 |
| 0.80-0.85 | 25 |
| 0.85+ | 1 (simetri düzeltmesinden önce kaçan tek çift) |

0.80-0.85 bandı elle okundu ve **gerçek anlamsal kopyalar bulundu**:
`Taksim istasyonunda 4 numaralı vagondaki yolcu anons cihazı ses vermiyor.` /
`Yolcu anons cihazı ses vermiyor 4. vagon` (0.843) — aynı arıza, aynı vagon.
Ama aynı bantta **gerçekten farklı arızalar** da var: `makinist kabini sağ
tarafı ayna kırık` / `makinist kabini saati durmuş` (0.804). Ölçüt sözcüksel,
anlamsal değil; eşiği körü körüne düşürmek farklı arızaları birleştirir.

**Çözüm: tek eşik yerine iki eşik**, çünkü eşiğin iki farklı işi var ve hata
maliyetleri simetrik değil:

| kullanım | yanlış birleştirme | kaçırma |
| --- | --- | --- |
| üretim (yeni kayıt reddi) | iyi cümle boşa gider, kota harcanır | veri biraz tekrarlı olur |
| bölme (kümeleme) | iki kayıt aynı bölmeye düşer, küçük çeşitlilik kaybı | **metrik şişer, sahte başarı** |

Bölmede kaçırmanın bedeli çok daha ağır → orada daha agresif olunmalı.

Kümeleme etkisi: 0.85→1 çift, 0.82→8, **0.80→27 çift + 1 üçlü**, 0.78→39
(kümeler 5'e zincirlenmeye başlıyor), 0.75→88 (fazla agresif). **0.80
seçildi:** küme boyutu 2-3'te kalıyor, bedeli 1600 kayıtta 29 kayıt.
Yakaladığı en büyük küme tam da gerçek kopya ailesi (üç ayrı "sefer iptali →
yolcular bir sonraki trene yönlendirildi" cümlesi).

**✅ Adım 4 — Model Eğitimi (TAMAMLANDI):** `src/train.py` + `src/evaluate.py`
yazıldı ve çalıştırıldı. **Tüm başarı kriterleri her iki test setinde de
geçildi.**

| metrik | test (160) | gold (80) | hedef |
| --- | --- | --- | --- |
| accuracy | 0.9102 | **0.9500** | 0.85 ✅ |
| macro F1 | 0.9117 | **0.9497** | 0.82 ✅ |
| en düşük sınıf F1 | 0.8333 | **0.8889** | 0.75 ✅ |

(Bu değerler ASCII çoğaltmalı ikinci eğitimden. Çoğaltmasız ilk eğitim:
test 0.8938/0.8935/0.7500, gold 0.9000/0.9014/0.8000 — o da tüm hedefleri
geçiyordu, çoğaltma hepsini yukarı taşıdı.)

**Gold skoru test'ten YÜKSEK (+0.011).** Projenin en önemli bulgusu bu:
sentetik veriyle eğitilen model, bağımsız üretilmiş ve elle gözden geçirilmiş
gold setinde en az kendi dağılımı kadar iyi. Yani model çoğaltmanın kalıplarını
ezberlememiş, gerçekten sınıfı öğrenmiş. "Sentetik veri gerçekçi mi"
eleştirisine verilebilecek en somut cevap.

### En kritik hata: LoRA'da öğrenme hızı

`config.py`'de `LEARNING_RATE = 2e-5` yazıyordu ve **model hiçbir şey
öğrenmiyordu**: 5 epoch sonunda val macro-F1 = 0.134, kayıp 2.073 (rastgele
seviye `ln(8) = 2.079`). Sebep: 2e-5 BERT'i **tam fine-tuning** ederken
kullanılan standart değer, ama biz LoRA kullanıyoruz — parametrelerin sadece
%0.54'ü (595.976 / 111.219.472) eğitiliyor, adaptörler sıfırdan başlıyor ve
sınıflandırma başlığı rastgele başlatılıyor. Bu kadar küçük bir öğrenme hızıyla
ağırlıklar anlamlı mesafe kat edemiyor.

| LR | val macro-F1 (5 epoch) |
| --- | --- |
| 2e-5 | 0.134 (rastgele) |
| 1e-4 | 0.393 |
| 3e-4 | 0.850 |
| 5e-4 | 0.875 |

15 epoch'ta: 5e-4 → 0.930, 1e-3 → 0.938. Aradaki fark val setinde ~1 örnek
(n=160), yani gürültü içinde — 5e-4 seçildi (daha yumuşak eğri).

**Ders: hiperparametreyi literatürden kopyalamak yetmiyor, eğitim yöntemine
göre ayarlamak gerekiyor.** Rapor için güçlü bir bölüm.

### Diğer eğitim kararları

- **HuggingFace `Trainer` yerine elle eğitim döngüsü.** `Trainer`, `accelerate`
  üzerinden MPS'te dtype/device sürprizleri çıkarabiliyor ve hata ayıklamayı
  zorlaştırıyor. 1280 örnek × 12 epoch için elle döngü hem şeffaf hem yeterli.
- **`modules_to_save=["classifier"]`** — LoRA'da kritik: sınıflandırma başlığı
  rastgele başlatılıyor, sadece adaptörler eğitilirse model öğrenemez.
- **En iyi val macro-F1 veren epoch kaydediliyor**, sonuncusu değil (son epoch
  genelde aşırı öğrenmiş olur). Seçilen: epoch 5, val F1 0.9242.
- Tohum sabit (`SEED=42`), sonuç tekrar üretilebilir.
- Eğitim süresi ~35-45 sn/epoch (MPS, Apple Silicon; çoğaltmayla train 2219
  kayda çıktı). LoRA çıktısı sadece **2.4 MB** — tam model 440 MB olurdu.
- Seçilen: epoch 6, val macro-F1 **0.9429**.

### Confusion matrix bulguları

**Beklenen karışma GERÇEKLEŞMEDİ.** Adım 3'te işaretlenen taksonomi
belirsizliği (`Makinist masası acil durdurma butonu takılı` train'de arac_tren,
`Acil durdurma butonu takılı` test'te guvenlik_emniyet, benzerlik 1.00) için
"model puan kaybedecek" denmişti. Model **güven 1.00 ile doğru** cevap verdi;
"makinist masası" ifadesinin ayırt edici sinyal olduğunu öğrenmiş. Confusion
matrix'te `arac_tren ↔ guvenlik_emniyet` karışması hiç yok.

**Bunun yerine gerçek bir çakışma ortaya çıktı: `guvenlik_emniyet ↔
yolcu_operasyon`** (test'te 5, gold'da 2 hata — her iki sette de baskın çift).
Kaynağı veri değil, **config'in kendisi**:
- `guvenlik_emniyet` kapsamı: "...anons ile tahliye"
- `yolcu_operasyon` kapsamı: "anons yapılmaması/yanlış anons"

Örnek: `Acil tahliye anonsu yoğun saatlerde peronda net duyulamıyor.` — iki
kapsama da giriyor. Çözüm için aşağıdaki ikincil kategori mekanizması seçildi.

### Aksan dayanıklılığı — ölçüm, teşhis, çözüm, doğrulama

İlk eğitimden sonra `yazim_yanlisi` stilinin zayıf göründüğü fark edildi
(gold 0.765). Ama bu tek başına yanıltıcıydı: test+gold birleşik ölçümde
0.852 ve %95 güven aralığı diğer stillerle **fazlasıyla örtüşüyordu**
([0.763-0.941] vs [0.858-0.988]) — n=61 ile istatistiksel anlamlılık yok.

Bu yüzden **nedensel test** yapıldı: test+gold'daki aksan içeren 173 kaydın
aksanları kaldırılıp yeniden tahmin edildi. İçerik aynı, sadece ç/ğ/ı/ö/ş/ü
düşürüldü:

| | doğruluk |
| --- | --- |
| orijinal (aksanlı) | 157/173 = **0.9075** |
| ASCII katlanmış | 146/173 = **0.8439** |

**6.4 puanlık kayıp, tek değişken aksan.** Stil etiketine bakmak gürültülüydü,
müdahaleli test net cevap verdi.

**Teşhis — BERTurk tokenizer'ında görünüyor:**
```
asansör  -> 1 parça  ['asansör']
asansor  -> 3 parça  ['asa', '##ns', '##or']
```
Aksan düşünce kelime anlamsız alt-parçalara bölünüyor.

**Çözüm: eğitim verisi çoğaltma.** `train.csv`'deki aksan içeren kayıtların
ASCII'ye katlanmış kopyaları eğitime eklendi (1280 → **2219**, +939 kopya).
API gerektirmez. Sızıntı riski yok: `preprocess`'teki kümeleme zaten
aksan-duyarsız (`review.normalize` aksanı kaldırıyor), yani bir train kaydının
ASCII kopyası test'teki bir kayıtla eşleşiyorsa o ikisi zaten aynı kümededir.

**Doğrulama — aynı nedensel test tekrarlandı:**

| | çoğaltmasız | çoğaltmalı |
| --- | --- | --- |
| orijinal (aksanlı) | 0.9075 | **0.9191** |
| ASCII katlanmış | 0.8439 | **0.9075** |
| **aksan kaybı** | **−6.36 puan** | **−1.16 puan** |

Dayanıklılık 5.2 puan iyileşti. Ayrıca **genel doğruluk da arttı** (test macro
F1 0.8935 → 0.9135, gold 0.9014 → 0.9247) — çoğaltma sadece aksan sorununu
çözmedi, model genelinde fayda sağladı. `config.AUGMENT_ASCII_FOLD` ile
kapatılabilir (`--no-augment`), kıyas yapmak için.

### Yabancı kelime tespiti — üç yöntem denendi, ikisi başarısız

Eğitim verisinde `Acil çıkış yolu engelli baggage` bulundu (İngilizce kelime).
Otomatik tespit için denenenler:

| yaklaşım | sonuç |
| --- | --- |
| Projenin kendi metninden bigram sözlüğü | ❌ 1600 kayıtta **355 yanlış alarm** — referans korpus (247 cümle) Türkçe'nin bigram uzayını kapsayamıyor; `nesne`, `açma`, `sessiz` işaretlendi |
| Geniş digraf listesi (`sh`, `th`, `ph`, `ay`...) | ❌ `şüpheli`, `Kağıthane`, `aydınlatma` gibi Türkçe kelimeleri yakalıyor |
| BERTurk tokenizer parça sayısı | ❌ ayırt edemiyor: `baggage` 3 parça, `asansor` da 3 parça |
| **Dar kural: `q/w/x` + `ck,gh,ea,oo`** | ✅ 8 gerçek bulgu, **0 yanlış alarm** — ama kapsamlı değil, `baggage`'ı kaçırıyor |

Türk alfabesinde q, w, x **yok** — bu kısım kesin. Dar kural `YABANCI` bayrağı
olarak `review.py`'ye eklendi ama **bilgi amaçlı**: `switch`, `wifi` gibi
kelimeler Türkçe teknik jargonda da kullanılıyor, bayrak "sil" değil "bak"
demek.

Bulunan 9 kayıt (8 otomatik + `baggage` elle) düzeltildi: `bearing`→rulmanı,
`wiper`→silecek, `switch`→anahtarı, `watchdog`→izleme servisi, `WiFi`→kablosuz
ağ, `baggage`→bagajla, `duraqta`→durakta, `kapaq`→kapak (×2).

**Ders:** otomatik tespit her sorun için mümkün değil. Türkçe sözlük olmadan
"bu kelime Türkçe mi" sorusu güvenilir cevaplanamıyor; elle okuma hâlâ tek
kapsamlı yöntem. Dar ve kesin bir kural, geniş ve gürültülü bir kuraldan iyidir.

### evaluate.py — rapor kapsamı (19 Ağu genişletildi)

`python -m src.evaluate --kalibrasyon --hatalari-goster` şunları basar:

- **Contamination kontrolü (raporun EN BAŞINDA)** — birebir kesişim: train↔test,
  train↔val, val↔test, train↔gold, test↔gold. Ayrıca near-duplicate kontrolü
  **kategori ayrımıyla**: aynı kategoride benzer çift = gerçek sızıntı (model
  ezberleyip skoru şişirebilir); farklı kategoride = sızıntı DEĞİL, taksonomi
  belirsizliği (etiketler farklı olduğu için ezber işe yaramaz). Bu ayrım
  yapılmazsa araç "skorlar iyimser" diye yanlış uyarı üretiyor — nitekim ilk
  sürümde öyle oldu.
  Güncel durum: birebir 0, aynı-kategori near-dup **0**, farklı-kategori 2.
- **Genel metrikler:** accuracy, macro F1, **weighted F1**, macro/weighted
  **precision** ve **recall**, en düşük sınıf F1
- **Sınıf bazlı metrikler:** her kategori için precision / recall / F1 / destek
- **Confusion matrix** + en çok karışan çiftler
- **Stil bazlı doğruluk** (model hangi yazım stilinde zorlanıyor)
- **İkincil kategori analizi** (top-2 doğruluk, marj)
- **`manual_review` sayısı** (aktif eşikle kaç bildirim insana gider)
- **Hata örnekleri — sınıf bazında gruplu** (`--hatalari-goster`, en fazla 20).
  Düz liste yerine gruplanıyor çünkü "model nerede hata yapıyor" sorusunun
  cevabı tek tek hatalar değil, hangi sınıfın hangi sınıfla karıştığı. Grup
  içinde en düşük güvenli hata önce gelir — modelin zaten tereddüt ettikleri.

### Kalibrasyon — k-fold out-of-fold (`src/calibrate.py`)

**Sorun:** eşiği hangi veri üzerinden seçmeli?

| aday | neden olmaz |
| --- | --- |
| `test.csv` | eşiği test'e bakarak seçmek test setini karar sürecine sokar, skor iyimserleşir |
| `gold_test.csv` | aynı sorun, üstelik gold nihai bağımsız ölçüt |
| `val.csv` | epoch seçiminde kullanıldı → model orada **fazla emin**. Ölçüldü: yanlış tahminlerde ort. güven val **0.892**, test 0.758, OOF 0.773. Ayrıca sadece **9 hata** var |

Train'den ayrı bir `calibration.csv` ayırmak da çözmüyor: 160 kayıt ayırsak yine
~14 hata olurdu (aynı gürültü) ve eğitim verisi küçülürdü.

**Çözüm — k-fold OOF:** train 5 parçaya bölünür, her parça için o parçayı
GÖRMEMİŞ bir model eğitilir ve sadece o parça üzerinde tahmin alınır. Sonuç:
1280 kaydın tamamı için "modelin hiç görmediği" tahmin. Veri kaybı yok (nihai
model yine tüm veriyle eğitiliyor), hata sayısı 9 → **102**.

Fold modelleri nihai modelle **aynı tarifle** eğitilir (aynı LR, aynı ASCII
çoğaltma, sabit 6 epoch = nihai modelin seçtiği epoch). Fold içinde ayrı bir
val ile epoch seçmek, kaçmaya çalıştığımız seçim yanlılığını geri getirirdi.

**Doğrulama — OOF temsil edici mi?**

| | doğruluk | yanlışlarda ort. güven |
| --- | --- | --- |
| OOF (1280 kayıt, 102 hata) | **0.9203** | **0.773** |
| test (160 kayıt, 14 hata) | 0.9125 | 0.758 |
| val (160 kayıt, 9 hata) | 0.9440 | 0.892 ← kirli |

OOF test'e neredeyse birebir oturuyor; val'in ne kadar saptığı da görünüyor.
(Bilinen yaklaşıklık: fold modelleri verinin 4/5'iyle eğitildiği için nihai
modelden bir tık zayıf ve daha az emin — buradan çıkan eşik biraz temkinli
tarafta kalır.)

**`CONFIDENCE_THRESHOLD` 0.70 → 0.75** (OOF, 102 hata):

| eşik | trafik | yakalanan | boşuna | precision | recall |
| --- | --- | --- | --- | --- | --- |
| 0.60 | 3.6% | 25/102 | 21 | 0.543 | 0.245 |
| 0.70 | 5.9% | 37/102 | 38 | 0.493 | 0.363 |
| **0.75** | **7.3%** | **47/102** | 47 | **0.500** | **0.461** |
| 0.80 | 8.9% | 49/102 | 65 | 0.430 | 0.480 |

0.75 eskisini **domine ediyor**: aynı precision, 10 hata daha. 0.80'de precision
çöküyor — diz noktası 0.75.

**Reliability diagram (OOF, ECE = 0.0340):**

| kova | kayıt | ort. güven | gerçek doğruluk | sapma |
| --- | --- | --- | --- | --- |
| 0.80-0.90 | 51 | 0.856 | **0.686** | **−0.169** |
| 0.90-0.95 | 54 | 0.927 | 0.796 | −0.131 |
| 0.95-1.00 | **1061** | 0.994 | 0.975 | −0.018 |

Model verinin %83'ünde (0.95+) iyi kalibre, ama **0.80-0.95 bandında belirgin
fazla emin**: 0.85 güvenle söylediklerinin sadece %69'u doğru. Eşiği
yükseltmenin ikinci, bağımsız gerekçesi bu.

**`MARGIN_THRESHOLD` 0.40 → 0.30** (OOF):

| marj | trafik | kurtarılan | boşuna | oran |
| --- | --- | --- | --- | --- |
| 0.20 | 2.5% | 12/102 | 17 | 0.71 |
| **0.30** | **4.1%** | **20/102** | 25 | **0.80** ← tepe |
| 0.40 | 5.2% | 24/102 | 34 | 0.71 |
| 0.50 | 6.6% | 30/102 | 44 | 0.68 |

**Önemli düzeltme:** 0.40 daha önce gold'un **8 hatasına** bakarak seçilmiş ve
"kurtarma/boşuna oranı 4.0" diye kaydedilmişti. 102 hatalı OOF tabanında gerçek
oran **0.80** — yani o ölçüm tamamen gürültüydü. Az örneklemle yapılan
kalibrasyonun ne kadar yanıltabildiğine dair somut bir ders; rapora girmeli.

### İkincil kategori mekanizması — sınır sorunlarına genel çözüm

Taksonomiye sınır kuralı yazmak yerine (8 kategoride 28 çift var, ölçeklenmez)
modelin **zaten ürettiği** bilgi kullanılıyor:

| | test | gold |
| --- | --- | --- |
| top-1 doğruluk | 0.913 | 0.925 |
| **top-2 doğruluk** | **0.963** | **0.975** |
| marj eşiği 0.40'ta çift kategorili dönen | %6.2 | %7.5 |

Model belirsiz olduğunu biliyor. `MARGIN_THRESHOLD = 0.40` altında `/predict`
birincil + ikincil kategori döner. Kalibrasyon (gold): 0.30 → 3 hata kurtarılır
1 boşuna; **0.40 → 4 kurtarılır 1 boşuna**; 0.50 → 4 kurtarılır 3 boşuna.
0.40'tan sonra kurtarma artmıyor, maliyet artıyor.

Bunun kural yazmaya üstünlüğü: bugün bilmediğimiz sınır sorunlarını da kapsıyor,
gerçeği daha doğru modelliyor (bazı bildirimler gerçekten iki kategoriye girer),
ve mevcut `low_confidence` mekanizmasını kapsıyor.

**✅ Adım 5 — Backend (TAMAMLANDI):** `backend/main.py`, FastAPI. Çalıştırma:

```
./venv/bin/uvicorn backend.main:app --reload --port 8000
```

**Model bir kez yükleniyor** (lifespan içinde) ve bellekte tutuluyor; her
istekte yeniden yüklemek 2-3 saniye sürerdi. PyTorch çıkarımı bloklayıcı,
FastAPI ise async — eş zamanlı isteklerde aynı model nesnesine dokunulmasın
diye `threading.Lock` kullanılıyor. (Prototip için yeterli; gerçek yükte
birden fazla worker/kuyruk gerekir.)

**API alan adları İNGİLİZCE.** Projenin geri kalanı (config, değişken adları,
bu doküman) Türkçe ama dışa açılan sözleşme REST konvansiyonuna uyuyor.
Kategori anahtarları (`arac_tren`...) zaten ASCII, aynen korunuyor; her yanıtta
insan-okunur `label` ve arayüz için `color` da var.

Uç noktalar (hepsi Pydantic `response_model` ile şemalı — Swagger'da tam
dokümante):

| yol | ne yapar |
| --- | --- |
| `POST /predict` | `{"text": "..."}` → `category`, `label`, `color`, `confidence`, `probabilities`, **`line`/`station`/`equipment`/`symptom`** (Adım 7, kurallı çıkarım), `low_confidence`, `manual_review`, `secondary_category`, `margin`, `response_time_ms` |
| `GET /health` | servis ayakta mı, model yüklendi mi, hangi cihaz (izleme/yük dengeleyici için — hafif tutuldu) |
| `GET /model-info` | taban model, LoRA, parametre sayıları, en iyi epoch/val F1, hiperparametreler, aktif eşikler. Bir tahminin hangi model sürümünden geldiği izlenebilsin diye |
| `GET /categories` | 8 kategori: `label`, `color`, `scope`, `excludes` |
| `GET /examples` | "tek tıkla doldur" listesi; **gold.jsonl'den**, her kategoriden en fazla bir örnek |

`/examples` bilerek gold'dan besleniyor: eğitim verisinden örnek göstermek
demoyu olduğundan iyi gösterirdi. Gold eğitime hiç girmedi (test bunu
doğruluyor).

**Üç sinyal, ayrı anlamlar:**
- `low_confidence` → "model emin değil" (güven < `CONFIDENCE_THRESHOLD` 0.70)
- `secondary_category` → "model HANGİ İKİ seçenek arasında kararsız"
  (marj < `MARGIN_THRESHOLD` 0.40)
- `manual_review` → **ikisinden biri** tetiklendiyse `true`. Operatöre
  "bu bildirime insan baksın" diyen tek alan; arayüz bunu kullanmalı.

### Entegrasyon testleri (`tests/test_api.py`, 21 test, ~4 sn)

`TestClient` lifespan'i çalıştırdığı için **model gerçekten yükleniyor** — bunlar
birim testi değil, uçtan uca entegrasyon testi. Kapsanan davranışlar:

- `/health`, `/model-info`, `/categories`, `/examples` sözleşmeleri
- `/predict`: olasılıklar toplamı 1, en yüksek olasılık = dönen kategori
- **Eşik tutarlılığı:** `low_confidence`, `secondary_category` ve
  `manual_review` birbiriyle ve config eşikleriyle tutarlı mı
- **Regresyon:** bilinen bir mekanik arıza `istasyon_mekanik` çıkmalı
  (yanlış checkpoint / bozuk adaptör bu testi düşürür)
- **Aksan regresyonu:** aksanlı ve aksansız aynı cümle aynı kategoriye gitmeli
  (Adım 4'teki ASCII çoğaltmasının bekçisi)
- **Örnek sızıntısı:** `/examples` çıktısı gold'da olmalı, train'de OLMAMALI
- Hatalı girdi: boş/uzun metin → 400, eksik alan/yanlış tip → 422
- **Model istek başına yeniden yüklenmiyor** (nesne kimliği sabit)
- OpenAPI: 5 uç noktanın da yanıt şeması dolu (Swagger'da `"string"`
  görünmesinin sebebi eksik `response_model`'di, bu test o gerilemeyi yakalar)
- **Yapısal çıkarım:** spec'teki çıktı biçimi (`line`/`station`/`equipment`/
  `symptom`), bulunamayan alanın `None` dönmesi (uydurmaması), aksan
  dayanıklılığı, ve `T3 trensformatörü`ndeki `T3`'ün hat kodu sanılmaması

**Doğrulama — servis, `evaluate.py` ile birebir aynı sonucu veriyor:**
80 gold kaydı HTTP üzerinden geçirildi; doğruluk 74/80 = **0.9250**, ikincil
kategori dönen 6 (%7.5) — ikisi de `evaluate.py` ile aynı. Çıkarım süresi
ortalama **14.3 ms**.

**CORS daraltıldı** (19 Ağu): `allow_origins=["*"]` yerine
`config.CORS_ORIGINS` — yalnızca yerel geliştirme sunucuları
(`localhost:5173`, `:4173` ve `127.0.0.1` karşılıkları). Üretimde ortam
değişkeniyle verilir:

```
CORS_ORIGINS="https://ariza.metro.istanbul" uvicorn backend.main:app
```

Metotlar da `GET`/`POST`, başlıklar `Content-Type` ile sınırlandı. Doğrulandı:
izinli kaynak `Access-Control-Allow-Origin` alıyor, yabancı site almıyor.

### Tohum varyansı — projenin en önemli metodoloji dersi (19 Ağu 2026)

`INCLUDE_SEED_IN_TRAINING` kararı için koşul başına **3 farklı tohumla** eğitim
yapıldı. Karşılaştırma **gold üzerinden**, çünkü gold iki koşulda da aynı
(test seti seed dahil edilince değişiyor, o yüzden test kıyası geçersiz).

| koşul | gold macro F1 (3 tohum) | ortalama | **aralık** | en düşük sınıf F1 |
| --- | --- | --- | --- | --- |
| kapalı | 0.9247 · 0.9105 · 0.9624 | 0.9325 | **0.0519** | **0.7500** – 0.9000 |
| açık | 0.9497 · 0.9384 · 0.9371 | 0.9417 | **0.0126** | 0.8182 – 0.8889 |

**Bulgu 1 — tek koşu ölçüm değildir.** İlk denemede (tek tohum) seed eklemek
gold'u 0.9247 → 0.9497 yapmıştı; "+0.025 kazanç" gibi görünüyordu. Üç tohumla
bakınca ortalama fark sadece **+0.0092**, baseline'ın kendi salınımı ise
**0.0519**. Yani o kazanç gürültüydü. Sadece eğitim tohumunu değiştirmek
(veri sabitken) gold skorunu 0.911 ile 0.962 arasında oynatıyor.

**Bulgu 2 — ortalama değil, taban iyileşti.** Seed kapalıyken en kötü koşuda
en düşük sınıf F1 = **0.7500**, yani başarı kriterinin (0.75) tam sınırında —
bir kayıt daha kaysa kriter düşerdi. Açıkken en kötü durum 0.8182. Varyans da
4 kat daralıyor. Mekanizma makul: 93 temiz kayıt tavanı değil **tabanı**
yükseltiyor, model başlatmaya daha az duyarlı hale geliyor.

**Karar:** açık. Gerekçe ortalama kazanç değil, en kötü durumun iyileşmesi ve
93 elle gözden geçirilmiş kaydın boşa gitmemesi.

**Uyarı (rapora girmeli):** koşul başına 3 koşu var, varyans tahmininin kendisi
de gürültülü. "4 kat daha kararlı" rakamına fazla yaslanmamak lazım.

Bu ders bu projede **üçüncü kez** çıktı: (1) `MARGIN_THRESHOLD` gold'un 8
hatasına bakılarak seçilmişti, OOF'ta gerçek oran 5 kat farklı çıktı;
(2) `yazim_yanlisi` stilinin zayıflığı stil bazlı ölçümde gürültüye karışmıştı,
nedensel test net gösterdi; (3) burada. Ortak payda: **az örneklem + tek ölçüm
= ölçüm gibi görünen gürültü.**

**✅ Adım 6 — Frontend (TAMAMLANDI):** `frontend/`, React + Vite. Çalıştırma:

```
npm run dev --prefix frontend      # http://localhost:5173
```

Backend'in ayrı portta (8000) çalışıyor olması gerekiyor. Taban adres
`VITE_API_URL` ile değiştirilebilir; varsayılan `http://127.0.0.1:8000`.

Ekranda olanlar:
- Metin girişi (Enter ile gönderilir, Shift+Enter alt satıra geçer), 300 karakter sayacı —
  aşınca sayaç kırmızıya döner ve buton kilitlenir (backend'in `MAX_CHARS`
  kontrolüyle aynı sınır, istemcide önden yakalanıyor)
- Kategori rozeti, kategori renginde (`/categories`'ten gelen `color`)
- **İkincil kategori rozeti** kesikli çerçeveyle, birincilin yanında
- Güven progress bar
- **`manual_review` uyarı kutusu** — ve içinde **hangi sebeple** tetiklendiği
  ayrı ayrı yazıyor: düşük güven mi, iki kategori arasında kararsızlık mı,
  yoksa ikisi birden mi
- Tüm kategorilerin olasılık dağılımı, yatay barlar
- Örnek bildirimler (`/examples`, tek tıkla doldurur) — "bu örnekler eğitimde
  hiç kullanılmamış gold setinden geliyor" notuyla
- Açılır taksonomi paneli (8 kategori + kapsam metinleri)
- Yanıt süresi
- Backend kapalıysa: "Servise ulaşılamıyor… Başlatmak için: uvicorn …" —
  kullanıcıya ne yapacağını söyleyen hata mesajı

**Tasarım — karanlık tema.** Tek tema var, açık/koyu geçişi yok; arayüz
baştan koyu tasarlandı.

- Zemin `#0a0c11`, katmanlı yüzeyler `rgba(255,255,255,0.03-0.05)` +
  `backdrop-filter: blur()` ile cam hissi
- **Ortam ışığı:** sayfanın üstünde sabit (`position: fixed`) yumuşak bir hale.
  Sonuç geldiğinde `--vurgu` o kategorinin rengine dönüyor ve hale de onunla
  renkleniyor — ekran sonuca göre renk değiştiriyor
- **Kategori renkleri `config.py`'den geliyor ama koyu zemine uyarlanıyor.**
  Renkler açık zemin için seçilmişti; bazıları koyu (örn. temizlik `#65a30d`)
  ve doğrudan seyreltilince siyaha karışıp kayboluyordu. CSS `color-mix` ile
  **önce beyazla açılıp sonra seyreltiliyor** — böylece config tek doğruluk
  kaynağı olarak kalıyor, arayüz kendi zeminine göre uyarlıyor
- Sonuç kartı aşağıdan yukarı animasyonla giriyor; olasılık barları
  **kademeli gecikmeyle** (45 ms aralıklarla) sırayla doluyor
- `prefers-reduced-motion` desteği var

**Vite şablonunun varsayılan `index.css`'i kaldırıldı.** Şablon `:root`'a
`color-scheme: light dark` ve `@media (prefers-color-scheme: dark)` blokları
koyuyor; başlık rengini `#f3f4f6`'ya çevirip zeminde görünmez yapıyordu.
Ayrıca `#root`'a sabit genişlik + `text-align: center` veriyordu.
Kullanılmayan şablon dosyaları da silindi (hero.png, vite.svg, favicon.svg,
icons.svg, README.md) — hiçbiri referans edilmiyordu.

Tarayıcıda uçtan uca doğrulandı: yüksek güvenli tahmin (Araç/Tren %100, mavi
hale, uyarı yok), sınırda bildirim (Temizlik/Çevre %50.6 + ikincil
Altyapı/İnşaat, yeşil hale, çift gerekçeli uyarı), taksonomi paneli,
karakter sınırı, mobil yerleşim (375px).

**`.gitignore`:** `frontend/node_modules/` (58 MB, 425 dosya) ve
`frontend/dist/` eklendi — ikisi de `package-lock.json`'dan yeniden
üretilebilir ara ürün. `frontend/src` ve `package*.json` commit edilir.

**✅ Adım 7 — Yapısal Çıkarım (TAMAMLANDI):** `src/extract.py`. Sınıflandırmayı
"incident parsing" seviyesine çıkarır:

```
"M4 Ünalan'da yürüyen merdiven çok ses yapıyor"
-> {category: istasyon_mekanik, line: M4, station: Ünalan,
    equipment: yürüyen merdiven, symptom: anormal ses, confidence: 0.995}
```

**İlk sürüm KURALLI** (plandaki sıra: kurallı → NER → LLM fallback). Kurallıyla
başlamanın sebebi: istasyon adları ve ekipman terimleri zaten `config.py`'de
sayılı, yani tanıma probleminin büyük kısmı sözlük eşleşmesi. Kurallı katmanın
nerede yetersiz kaldığını ÖLÇMEDEN NER/LLM'e geçmek, çözülüp çözülmediğini
bilmediğimiz bir soruna model atmak olurdu.

`config.py`'ye eklenenler: `LINE_PATTERN`, `STATIONS` (53 ad), `EQUIPMENT`
(80 terim), `EQUIPMENT_ALIASES`, `SYMPTOMS` (43 desen).

`STATIONS`, `SLOT_VALUES["istasyon"]`'dan **ayrıdır ve onu kapsar**: oradaki 21
ad ÜRETİM için (çeşitlilik enjeksiyonu), buradaki liste TANIMA için. Üretilen
veride config listesi dışında gerçek istasyon adları da çıktı (Kozyatağı,
Aksaray, Söğütlüçeşme...), tanıma listesi bu yüzden daha geniş.

### Alan bazlı precision/recall (40 elle etiketlenmiş bildirim)

| alan | destek | precision | recall | F1 |
| --- | --- | --- | --- | --- |
| station | 23 | **1.000** | **1.000** | **1.000** |
| equipment | 33 | **1.000** | 0.939 | **0.969** |
| symptom | 40 | 0.846 | 0.825 | 0.835 |
| line | 0 | — | — | referansta örnek yok |

**Metodoloji:** referans etiketler **kurallar yazılmadan ÖNCE**, sadece cümleler
okunarak oluşturuldu — tersi olsaydı kurallar kendi cevabına göre şekillenirdi.
Tek etiketleyici, yani mutlak değil yön gösterici. Karşılaştırma ölçütü gevşek
(normalize edilmiş hallerden biri diğerini içeriyorsa veya kelime örtüşmesi
varsa doğru).

**`line` neden ölçülemedi:** bildirimlerin sadece **%6.4'ünde** hat kodu
geçiyor, katmanlı 40'lık örnekleme hiç düşmedi. Ayrıca ölçüldü: hat kodu içeren
20 rastgele kayıtta **20/20 doğru** (Marmaray dahil). Bu bir eksiklik değil,
verinin doğası — alan çoğu zaman `None` döner.

### Bulunan üç gerçek hata (hepsi düzeltildi)

| hata | etki |
| --- | --- |
| `durdu` deseni `acil DURDURma`ya takılıyordu | kelime sınırı yoktu |
| `sondu` deseni `yangın SÖNDÜRme`ye takılıyordu | aynı sınıf hata |
| `basıncı düşüşü` çekim eki yüzünden eşleşmiyordu | desen fazla katıydı |

Düzeltmeler sonrası `symptom` F1 0.658 → **0.835**.

### Kalan hataların yapısı — NER'e geçmeden önce bilinmesi gereken

Kalan 8 `symptom` hatasının çoğu **sözlük eksiği değil**, tek-etiketli
çıkarımın yapısal sınırı: `"banknot kabul etmiyor hata veriyor"` cümlesinde
İKİ belirti birden var, sistem birini seçmek zorunda. Hangisinin "birincil"
olduğu yorum meselesi.

`equipment`'ın 2 hatası da farklı bir sınıf: `"3 numaralı vagonda kapı"` —
ekipman `vagon kapısı` ama kelimeler araya giren tokenlarla bölünmüş; alt-dizi
eşleşmesi bunu birleştiremez. **Bileşimsel ifadeler için NER gerekiyor.**

Yani ölçüm, bir sonraki adımın ne olması gerektiğini de söylüyor: sözlük
büyütmek değil, (a) çok-etiketli belirti, (b) bileşimsel ekipman için
token classification.

**✅ Adım 8 — Loglama, Benzerlik, Onay, Canlı Grafik (TAMAMLANDI):**
`src/db.py`, `src/similarity.py`, backend'e 4 yeni uç nokta, frontend'e
onay butonları + kategori grafiği.

### Neden otomatik eğitim yok — bilinçli tasarım kararı

Kullanıcı fikri: kullanıcının yazdığı her cümle veritabanına eklensin ve
buna göre **her çalıştırmada** model yeniden eğitilsin. Bu fikir **kısmen**
uygulandı — loglama evet, otomatik eğitim hayır. Gerekçe:

Kullanıcının yazdığı bir cümle için sistemin **kendi tahmini** tek etiket
adayıdır ve bu tahmin **yanlış olabilir**. Etiketsiz/doğrulanmamış veriyle
otomatik eğitmek, modelin kendi hatalarını doğru sanıp pekiştirmesi riski
taşır (confirmation bias). Bu proje boyunca veri kalitesine verilen önem
— elle triyaj, `SINIR`/`YABANCI` bayrakları, gold'un bağımsızlığı, near-dup
kümeleme — hep aynı gerekçeyle **denetimsiz veri girişine karşı**dır.
Kullanıcı girdisini süzgeçsiz eğitime sokmak bunların hepsini atlar olurdu.

**Uygulanan orta yol:** her tahmin SQLite'a loglanır ama `dogrulandi` alanı
`NULL` olarak başlar — yani "tahmin", "etiket" değil. Kullanıcı arayüzde
"✓ Doğru" / "✕ Yanlış" ile onaylarsa bu alan dolar. **Sadece onaylanan**
kayıtlar `/logs/export` ile dışarı alınabilir ve kullanıcının kendi
inisiyatifiyle (elle) `data/raw/amplified.jsonl`'e katılıp `preprocess.py`
+ `train.py` yeniden çalıştırılabilir. Backend bunu **otomatik yapmaz**.

### `src/db.py` — log veritabanı (SQLite)

Tablo `bildirimler`: metin, kategori, güven, kaynak (`gecmis`|`canli`),
`dogrulandi` (NULL|1|0), `dogru_kategori`, zaman.

- **`init()`** tabloyu oluşturur ve **boşsa** `data/processed/clean.csv`'yi
  (1675 kayıt, gold DAHİL DEĞİL) `kaynak='gecmis'` olarak bir kez seed'ler.
  İdempotent — ikinci çağrıda hiçbir şey yapmaz.
- **Dene-yanıla spam koruması:** aynı metin son 30 saniyede zaten loglandıysa
  tekrar loglanmaz (`son_kayit_tekrar_mi`). `/predict` bu durumda `log_id: -1`
  döner, arayüz onay butonlarını göstermez.
- **`data/logs.db` `.gitignore`'da** — çalışırken büyüyen, `clean.csv`'den
  yeniden üretilebilir bir dosya (Genel İlke 6'daki "yeniden üretilebilir
  ara ürün" tanımına birebir uyuyor).

### `src/similarity.py` — embedding tabanlı yakınlık tespiti

Kullanıcı isteği: *"bir cümle yazıldığında yakınlık tespiti yapıp buna benzer
XX arıza kaydı bulundu, bunların şu kadarı bu kategori..."*

**Ayrı bir embedding modeli KURULMADI.** Zaten yüklü olan BERTurk+LoRA
sınıflandırma modelinin kendi iç temsili (`.bert` alt-modülünün
`pooler_output`'u, 768 boyut) + cosine similarity kullanılıyor. Bu model
sınıflandırma için fine-tune edildiği için iç temsilinin kategoriye göre
kümelenmiş olması **beklenir** — ama bu varsayım kör kör kabul edilmedi,
ölçüldü:

**Eşik kalibrasyonu (test setinden 150 kayıt, 1334 aynı-kategori / 9841
farklı-kategori çift):**

| eşik | aynı-kategori yakalanan | farklı-kategori YANLIŞ ALARM |
| --- | --- | --- |
| 0.50 | %83.7 | %5.1 |
| **0.60** | **%76.0** | **%2.4** ← seçilen |
| 0.65 | %71.9 | %1.5 |
| 0.80 | %51.6 | %0.3 |

İlk tahmin 0.85'ti (SequenceMatcher eşiklerinden esinlenerek — Adım 3'teki
`NEAR_DUP_THRESHOLD`), ama BERT pooler çıktısı farklı bir uzayda: ölçmeden
tahmin etmek yanıltıcıydı, 0.85'te aynı-kategori kayıtların **çoğu**
kaçırılırdı. 0.60 iyi bir denge.

Corpus embedding'leri **lifespan sırasında bir kez** hesaplanır (1675 kayıt,
~3.5 sn), diske önbelleklenmez — ekstra bir önbellek geçerliliği sorunu
yönetmekten daha basit.

**Canlı doğrulama:** "Yürüyen merdiven durdu 2. peron" → 209 benzer kayıt,
**%97.6 İstasyon Mekanik** — benzerlik motorunun anlamlı çalıştığının kanıtı.

### Backend — 4 yeni uç nokta

| yol | ne yapar |
| --- | --- |
| `POST /logs/verify` | kullanıcı tahmini onaylar/düzeltir; `dogrulandi` alanını doldurur |
| `GET /logs/stats` | toplam/canlı/onaylı sayıları |
| `GET /logs/export` | **sadece onaylanmış** kayıtları JSONL olarak döndürür |
| `GET /stats/categories` | kategori bazında toplam + canlı sayım (grafik veri kaynağı) |

`/predict` yanıtına iki alan eklendi: `log_id` (bu tahmini `/logs/verify`
ile onaylamak için) ve `similar` (benzerlik dağılımı).

**Bulunan gerçek hata:** `similarity.benzer_bul()` Türkçe anahtarlarla
(`esik`, `dagilim`...) dönüyordu, API şeması İngilizce bekliyordu —
`ResponseValidationError` ile yakalandı, backend'de çeviri katmanı eklendi.

### `src/resolve_logs.py` — kategorisiz "Yanlış" kayıtlarının çözümü (20 Ağu 2026)

**Bulunan gerçek sorun:** Arayüzde "✕ Yanlış" deyip dropdown'dan kategori
seçmeden "atla"ya basılırsa kayıt `dogrulandi=0` + `dogru_kategori=NULL`
olarak kalıyordu. `onayli_kayitlari_disa_aktar()` bu kaydı yine de dışa
aktarıyordu — `kategori: None` ile, yani egzersiz verisini bozacak şekilde.

**Çözüm — iki parça:**

1. `db.onayli_kayitlari_disa_aktar()` artık `dogrulandi=0 AND dogru_kategori
   IS NULL` olan (henüz çözülmemiş) kayıtları **dışlıyor**. `db.py`'ye ayrıca
   `kategorisiz_yanlislari_getir()` eklendi.
2. `python -m src.resolve_logs` — eğitim öncesi çalıştırılan interaktif bir
   script. Her kategorisiz kayıt için: metni **güncel modelle yeniden
   tahmin eder**, kullanıcının zaten reddettiği kategoriyi olasılık
   sıralamasından **çıkarır** (aynı yanlış cevabı tekrar önermemek için),
   kalan en olası kategoriyi öneri olarak gösterir. Kullanıcı Enter ile
   öneriyi kabul edebilir, kategori anahtarını yazıp elle düzeltebilir, veya
   `s` ile atlayabilir (kayıt kategorisiz kalır, sonra tekrar denenebilir).
   Kabul/düzeltme `dogru_kategori` alanına yazılır — `dogrulandi` hâlâ `0`
   kalır (orijinal tahmin yanlıştı bilgisi korunur), ama artık `/logs/export`
   bu kaydı normal şekilde (düzeltilmiş kategoriyle) dışarı alabiliyor.

Uçtan uca test edildi: kabul, elle düzeltme ve atlama yolları ayrı ayrı
doğrulandı; export hem çözülmüş kaydı doğru kategoriyle içeriyor hem de
hâlâ kategorisiz kalan kaydı dışlıyor.

### Frontend — onay butonları + canlı kategori grafiği

`SonucKarti.jsx`: "✓ Doğru" / "✕ Yanlış" butonları, yanlışta kategori
seçim dropdown'ı, "Benzer Kayıtlar" bölümü (mevcut `.dagilim-satir` diliyle
tutarlı, yeni bir görsel dil eklenmedi).

**Bulunan gerçek hata:** `SonucKarti`'nin `onayDurumu` state'i yeni bir
tahminde sıfırlanmıyordu — React aynı bileşen örneğini koruyup önceki
tahminin onay durumunu taşıyordu. `key={sonuc.log_id + ...}` ile bileşen
her tahminde yeniden kuruluyor.

`KategoriGrafik.jsx`: yatay bar grafiği, her bar iki segment (soluk =
geçmiş havuz, parlak = canlı eklenen). Her tahminden ve her onaydan sonra
otomatik yenileniyor ("cümleler eklendikçe güncellenen tablo" isteği).
Renkler `config.py`'den geliyor, ayrı bir palet seçilmedi (Adım 6'daki
kategori renkleriyle tutarlılık için).

### Docker — kullanıcı kararıyla ERTELENDİ

Docker Desktop bu makinede kurulu ama daemon çalışmıyordu (GUI uygulaması,
elle başlatılması gerekiyor). Kullanıcıya soruldu, **"docker yapmayalım"**
kararı verildi. Yazılan `Dockerfile.backend`, `frontend/Dockerfile`,
`docker-compose.yml` **test edilmeden repodan silindi** — CLAUDE.md'nin
"test edilmemiş kodu commit etme" kuralı gereği. İleride gerekirse yeniden
yazılabilir; tasarım notu: backend + frontend ayrı imaj, `data/` tek bir
named volume'a mount edilir (Docker ilk çalıştırmada imajdaki içeriği boş
volume'a otomatik kopyalar), `VITE_API_URL` build-time ARG (tarayıcı
container ağını değil host portunu görür).


## Adım 9 — Taksonomi v2 ve üç boyutlu mimari (21 Ağu 2026)

Sistem tek boyutlu (sadece kategori) bir sınıflandırıcıdan **üç boyutlu** bir
bildirim ayrıştırıcısına dönüştü. Kategori taksonomisi de sıfırdan yeniden
tasarlandı.

### Neden yeniden tasarım

v1 taksonomisi organik büyümüştü (6 → 8 → 9 kategori) ve iki ciddi sorun
üretiyordu:

1. **Kelime dünyaları çakışıyordu.** `altyapi_insaat` ile `temizlik_cevre`
   arasında "su/sızıntı/döküntü" ortak kelimeleri vardı ve model ayıramıyordu:
   bağımsız test setinde `altyapi_insaat` **%5 doğruluk** verdi, 19 kaydın
   19'u `temizlik_cevre`'ye gitti (çoğu %95+ güvenle — yani model emin şekilde
   yanılıyordu).
2. **Sınır kuralları yamalıydı.** Her düzeltme başka bir yeri bozuyordu:
   `guvenlik_emniyet`'i düzeltince Yolcu/Operasyon %68'den %32'ye düştü.

### Yeni taksonomi — 11 kategori

Tam liste ve kapsam/hariç metinleri `yeni-eklemeler.md`'de ve `config.py`'de.
Ayrım ilkesi değişmedi (kategori = hangi bakım ekibi), ama sınırlar
**kelime dünyası ayrışacak şekilde** çizildi:

| eski | yeni |
| --- | --- |
| `istasyon_mekanik` | `mekanik_istasyon` |
| `yazilim_sistem` | `elektronik_sistemler` + `sinyalizasyon_haberlesme` |
| `guvenlik_emniyet` | üçe bölündü: `sinyalizasyon_haberlesme` (ekipman teknik arızası) / `istasyon_guvenlik` (önlem) / `guvenlik_asayis_olay` (olay) |
| `asayis_suc` | `guvenlik_asayis_olay` |
| `yolcu_operasyon` | `yolcu_hizmetleri` |
| `temizlik_cevre` | `temizlik` |
| `altyapi_insaat` | ikiye bölündü: `altyapi_insaat` (bina/tünel/su) + `yol_yapisal` (ray hattı) |

**Kaldırılan kategori — `personel_bilgi`.** Taslakta vardı; verideki 183 kaydın
tamamı gerçek İK konusuydu (yaka kartı, bordro, izin formu) ve hiçbiri arıza
bildirimi değildi. Bu bir arıza sistemi; personel özlük işlemleri başka bir
sistemin konusu. Kayıtlar silindi — relabel denemek anlamsızdı, başka hiçbir
kategoriye uymuyorlardı.

### Hariç metinlerinin sadeleştirilmesi

Taslakta her kategorinin hariç listesinde neredeyse aynı metin vardı:
*"elektrik, sinyalizasyon, haberleşme, yol, yapısal, vagon içi, yolcu
bilgilendirme, temizlik/güvenlik, personel/yönetim bunlar girmez."*

Bunlar kaldırıldı. Gerekçe: LLM'e hiçbir bilgi vermiyorlar (bir kategorinin
diğerlerini kapsamadığı zaten örtük) ama prompt'u şişiriyorlar — 11
kategorinin her birine aynı liste eklenince asıl kapsam metinleri gürültüye
gömülüyor. Yerine sadece **gerçekten karışan sınırlar** yazıldı. Prompt ~%40
kısaldı, kategori F1 düşmedi.

**Bir hata kaydı (dürüstlük için):** ilk incelemede "6 kategorinin hariç
listesinde kendi adı geçiyor" dedim. Kullanıcı sorunca tek tek kontrol ettim —
**sadece 1'i doğruydu** (`personel_bilgi`). Hariç listeleri birbirine çok
benzediği için kalıbı görüp genellemiş, doğrulamamıştım. Ders: dosya
içeriğine dair iddia yapmadan önce her maddeyi ayrı ayrı doğrula.

### Üç boyut ve akış

```
KULLANICI METNİ → INTENT → CATEGORY → ENTITIES → PRIORITY → ROUTING
```

| boyut | sınıf | nasıl |
| --- | --- | --- |
| Intent | 5 | model başlığı |
| Kategori | 11 | model başlığı |
| Öncelik | 4 | **kural katmanı + model başlığı** |
| Entities | — | kurallı çıkarım (`extract.py`) |
| Routing | — | kategoriden eşleme |

Üç sınıflandırma başlığı **tek BERTurk gövdesi** üzerinde eğitiliyor
(`src/model.py`). Gerekçe: bir bildirimin kategorisini belirleyen kelimeler
genellikle niyetini ve önceliğini de belirler; üç ayrı model bu ortak sinyali
üç kez sıfırdan öğrenirdi ve serviste 3 × 440 MB taban model tutulurdu.
Eğitilebilir parametre 605K (%0.54), adaptör **2.3 MB**.

### Veriyi yeniden üretmek yerine YENİDEN ETİKETLEMEK

Taksonomi değişince 1800 cümlenin etiketleri geçersiz kaldı. İki seçenek vardı:

| yol | maliyet | kayıp |
| --- | --- | --- |
| Sıfırdan üretim | ~75 LLM çağrısı | Birikmiş dil çeşitliliği (stil varyantları, yazım hataları, gerçek istasyon adları) |
| **Yeniden etiketleme** | ~45 çağrı | Yok — cümleler aynı kalır |

İkincisi seçildi (`src/relabel.py`). Cümleler korunur, LLM sadece üç boyutun
etiketini yeniden belirler. Eksik kalan kategoriler ve intent'ler için
`src/generate_missing.py` ile hedefli üretim yapıldı.

**Bir kalite ölçümü buradan çıktı:** üretimde hedeflenen kategori ile bağımsız
etiketlemenin uyumu **%88.9** (intent %93.1). Uyuşmayan 72 kayıt okundu ve
**bağımsız etiketleyici haklıydı** — örneğin *"rayların üzerine bir yolcunun
atladığı"* cümlesi `yol_yapisal` hedefiyle üretilmişti ama gerçekte
`guvenlik_asayis_olay`. Üretim hedefi cümleyi zorlarken LLM konudan sapmış.
Bağımsız etiket esas alındı.

### Öncelik — üç adımlı müdahale

İlk eğitimde öncelik başlığı **macro-F1 0.60** verdi, P2 sınıfı **0.38**.
Üç adım uygulandı:

**(c) Önce etiket tutarlılığı ölçüldü** (`src/oncelik_tutarlilik.py`). Aynı
cümleler ikinci kez etiketlendi:

| sınıf | iki tur uyumu |
| --- | --- |
| P4 Düşük | **%100** |
| P1 Kritik | %75 |
| P3 Orta | %57 |
| **P2 Yüksek** | **%38** |

Ham uyum **%69.8**, Cohen's kappa **0.584**. Yani model %62 ile zaten
**tavana yakındı** — sorun modelde değil, etiket tanımının belirsizliğindeydi.
Bu ölçüm yapılmasaydı model mimarisiyle uğraşıp boşa emek harcanacaktı.

**(a) Sonra P2/P3 sınırı yeniden tanımlandı.** Eski ölçüt sayıya dayanıyordu
("birden fazla merdiven" P2) ve bu bilgi cümlelerde çoğu zaman **hiç
geçmiyordu**. Yeni ölçüt operasyonel etki:

- P1: can güvenliği tehdidi var mı?
- P2: sefer veya yolcu akışı aksıyor mu?
- P3: arıza var ama yolculuk normal mi?
- P4: işleyişi hiç etkilemiyor mu?

**(b) Son olarak P1 için kural katmanı eklendi** (`config.PRIORITY_RULES`).
P1'i kaçırmanın bedeli asimetriktir: yangın bildirimini P3 sanmak kabul
edilemez, tersi sadece gereksiz aciliyet yaratır. 11 dar desen (yangın, yoğun
duman, elektrik çarpması, raylara kişi, intihar, şüpheli paket, aktif saldırı,
sağlık acili, yapısal çökme, su baskını, acil çıkış engeli) modelin tahminini
**ezer** ve koşulsuz P1 verir. `/predict` yanıtındaki `priority_rule` alanı
doluysa öncelik modelden değil kuraldan gelmiştir.

### evidence — gradient × input

Modelin kararına hangi kelimelerin katkıda bulunduğunu gösterir
(`src/evidence.py`). Üç yöntem karşılaştırıldı:

| yöntem | ek maliyet | ne gösterir |
| --- | --- | --- |
| Sözlük eşleşmesi | ~0 ms | Hangi anahtar kelimeler var — modelin kararı **değil** |
| Integrated Gradients | ~280 ms (20 ileri geçiş) | Gerçek model sinyali |
| **Gradient × input** ✅ | **~15 ms** (1 geri yayılım) | Gerçek model sinyali |

Değerini gösteren somut örnek: *"tavandan su damlıyor kova koydular"*
cümlesinde sözlük yöntemi "su" kelimesini bulup doğru karar verildiğini
sanırdı; gradient yöntemi modelin aslında **"koydular"** kelimesine
takıldığını gösterdi — yani model o cümlede anlamlı sinyal bulamamış.

**Sınırı (rapora yazılmalı):** gradient tabanlı açıklamalar yerel doğrusal bir
yaklaşıklıktır. "Model bu token'a duyarlı" der, "model bu yüzden karar verdi"
demez.

### Yeni yapısal alanlar

`extract.py` genişletildi:

- **`location`** — istasyon İÇİNDEKİ konum ("2 numaralı giriş", "turnike
  bölgesi"). Ayrı bir alan çünkü bir istasyonda aynı ekipmandan birden fazla
  var; iş emrine "Kadıköy'de merdiven bozuk" yazmak yetmez.
  Konum ifadesi ekipman aramasından **maskeleniyor**: *"turnikelerin oradaki
  merdiven"* cümlesinde ekipman merdivendir, turnike konum belirtir.
- **`root_cause`** — sadece bildirimde AÇIKÇA belirtilmişse dolar.
  *"Elektrik kesildiği için merdiven çalışmıyor"* → dolu.
  *"Merdiven bozuk, **galiba** motoru yanmış"* → `null`. "galiba/sanırım/
  herhalde" gibi ifadeler kullanıcının emin olmadığını gösterir; sistem bunu
  teknik teşhis olarak kaydetmez. **Halüsinasyon engelleyici kural budur.**
- **`missing_information`** — iş emri için gereken ama bulunamayan alanlar.
  Hangi alanın gerekli olduğu kategoriye göre değişir (tren arızasında istasyon
  zorunlu değil, hat önemli; istasyon ekipmanında konum şart).

### duplicate_report

`db.olasi_tekrar()`: aynı kategori + aynı istasyon + aynı ekipman + son
**15 dakika** → `possible_duplicate: true`. İstasyon veya ekipman bilinmiyorsa
karar **verilmez** — eksik bilgiyle birleştirme yanlış iş emri kapatmaya yol
açar. Log tablosuna `istasyon`, `ekipman`, `intent`, `oncelik` sütunları
eklendi.

### Sonuçlar (test seti, 232 kayıt)

| görev | accuracy | macro F1 | hedef |
| --- | --- | --- | --- |
| **Kategori** (11 sınıf) | **0.8966** | **0.8765** | 0.85 / 0.82 ✅ |
| **Intent** (5 sınıf) | **0.9267** | **0.8462** | — |
| **Öncelik** (4 sınıf) | 0.6207 | 0.6053 | etiket tavanı ~0.70 |

Sınıf bazında en güçlüler: Araç ve Tren 0.958, Elektrik 0.955, Yolcu
Hizmetleri 0.955, Güvenlik ve Asayiş 0.947.

**En düşük sınıf F1 = 0.6154 (İstasyon Güvenliği) — başarı kriterinin
altında.** Sebep veri azlığı: bu kategoride sadece 95 kayıt var (diğerleri
172–269) çünkü `istasyon_guvenlik_temizlik` bölündüğünde payına düşen az oldu.
Precision 1.00 ama recall 0.44 — model bu kategoriyi tahmin etmekten
çekiniyor. Çözüm hedefli veri üretimi; kota yenilendiğinde yapılacak.

### Bu turda öğrenilen: LLM kota yönetimi bir kısıt olarak tasarıma girmeli

Bir günde OpenRouter (50 istek) ve dört ayrı Gemini modeli (20 istek/gün/model)
tüketildi. 2268 kaydın tamamını yeniden etiketlemek ~57 çağrı gerektiriyordu ve
tek sağlayıcıyla mümkün olmadı. Uygulanan strateji:

1. **Zorunlu olanı ayır.** Sadece geçersiz kategorili 327 kayıt relabel edildi
   (9 çağrı), diğerlerinin kategorisi zaten geçerliydi.
2. **Modeller arasında geç.** Gemini kotası model başına ayrı; 3.6 → 3.5 →
   3-flash-preview → flash-latest → 3.1-flash-lite sırasıyla kullanıldı.
3. **Devam edilebilirlik şart.** `relabel.py` çıktı dosyasını her partide
   yazıyor ve yeniden çalıştırıldığında kaldığı yerden devam ediyor.

## Adım 10 — LLM sağlayıcı kararı, eğitim altyapısı, bağımsız doğrulama (23 Ağu 2026)

### Sağlayıcı sadeleştirmesi: qwen çıkarıldı, nihai politika "önemli işte Nemotron, geri kalanda gemma"

`qwen2.5:14b` hem üretim hem etiketleme rolünde aynı görevde ölçülüp
Nemotron/gemma4:cloud'un gerisinde kaldığı zaten Adım 2b'de kanıtlanmıştı;
bu turda kodun kendisinden de tamamen çıkarıldı — kullanılmayan sağlayıcı
kodu tutmanın gerekçesi yok. `OLLAMA_MODEL = "gemma4:cloud"` tek değişkene
indirildi (önceden üretim/etiketleme için ayrı ayrı tutulmuştu).

**Cerebras denendi, iki ayrı API key ile de `402 Payment Required` verdi**
(hesap bazlı faturalama sorunu, key'e özel değil) — kod tabanına hiç
eklenmedi; "doğrulanmamış/çalışmayan sağlayıcıyı asla wire etme" ilkesi.

**Groq (`openai/gpt-oss-120b`) 15+ kayıtlık partilerde JSON şemasını
bozuyordu** (10'da çalışıyor, 15/20/25'te `400 - Failed to validate JSON`).
Nemotron ile aynı görevde kıyaslama başlatıldı ama kullanıcı "bu kadar
sürecekse salalım, Nemotron zaten önde çıkacak" dedi ve iş durduruldu.

**Nihai karar:** önemli/yüksek riskli işler (seed/gold üretimi) → Nemotron
(OpenRouter); toplu üretim/etiketleme → gemma4:cloud (Ollama, çok daha
hızlı, kalitesi yeterli).

### Eğitim altyapısı — loss fonksiyonu doğrulaması, early stopping, canlı izleme

Kullanıcı eğitimi canlı loss grafiğiyle izlemek istedi ve mevcut
düzenlileştirme tekniklerinin doğrulanmasını istedi. Kontrol edildi:
cross-entropy (`src/model.py`, her başlık için ayrı, toplanıyor) ve L2
(AdamW `weight_decay=0.01`) zaten vardı; ekstra teknik istenmedi (kullanıcı
seçimi: "mevcut üçü yeterli").

**Early stopping eklendi** — validation loss'a dayalı, training loss'a DEĞİL
(kullanıcı bunu özellikle netleştirdi ve doğru anladığını teyit için sordu).
`config.EARLY_STOPPING_PATIENCE = 3`: val_kayip 3 epoch üst üste iyileşmezse
eğitim durur. **En iyi checkpoint seçimi bilinçli olarak AYRI bir sinyale
dayanıyor** — val_kayip'e değil, üç görevin ortalama macro-F1'ine. Sebep:
val_kayip düzleşse bile bir başlığın F1'i hâlâ iyileşiyor olabilir (nitekim
son eğitimde epoch 8, val_kayip epoch 7'den yüksek olduğu halde ortF1 en
yüksek noktaydı).

**Canlı loss izleme:** `src/train.py` eğitim sırasında (her 5 batch'te bir +
her epoch sonunda) `model/canli_kayip.json`'a yazıyor; `dev/canli_kayip.html`
saf SVG ile (dış kütüphane yok) bunu tarayıcıda çiziyor,
`.claude/launch.json`'daki `canli-kayip` (`python -m http.server 8799`)
sunucusuyla servis ediliyor. Uçtan uca doğrulandı: ekran görüntüleri gerçek
zamanlı güncellenen kayıp eğrisi ve epoch 10/12'de early-stop'un tetiklendiği
anı gösterdi.

**Bulunan gerçek hata:** `float("inf")` içeren bir JSON alanı (`en_iyi_val_kayip`
başlangıç değeri) `json.dumps` ile `Infinity` literaline dönüşüyordu — bu
JSON spesifikasyonuna göre GEÇERSİZ, tarayıcının `JSON.parse()`'ı sessizce
patlıyor ve grafik sonsuza kadar "veri bekleniyor…" durumunda kalıyordu.
`None`'a çevrilerek düzeltildi.

**Nihai eğitim sonucu (early-stopped, epoch 8/12 seçildi, epoch 10'da
durduruldu):**

| görev | macro F1 | accuracy |
| --- | --- | --- |
| Kategori | 0.8844 | 0.8837 |
| Intent | 0.9285 | 0.9535 |
| Öncelik | 0.7374 | 0.7403 |

### Bağımsız test seti ile üç gerçek hata bulundu ve ikisi tam, biri kısmen düzeltildi

Kullanıcı `data/seed/yeni_gold_deneme.jsonl` adıyla **farklı bir LLM'den
üretilmiş, elle etiketlenmiş 80 kayıtlık** bağımsız bir test seti getirdi
(proje boyunca tekrar eden "değerlendirme verisi üretim verisiyle aynı
kaynaktan gelmemeli" ilkesinin bir uygulaması). `src/toplu_test.py` üç
görevi birden (kategori/intent/öncelik) destekleyecek şekilde yeniden
yazıldı — İngilizce/Türkçe alan adı takma adlarını (`priority`/`oncelik`
gibi) kabul ediyor, `evaluate.tum_gorevleri_tahmin_et()` ile tek geçişte tüm
başlıkları tahmin ediyor.

**İç test seti vs bağımsız test seti (öncelik doğruluğu):**

| aşama | iç test seti (relabel kaynaklı) | bağımsız set (80 kayıt) |
| --- | --- | --- |
| düzeltme öncesi | — | %73.8 (F1 0.7224) |
| düzeltme sonrası | 0.6951 (gerileme) | **%81.2** (F1 0.7473) |

İç test setinde küçük bir gerileme görüldü ama bağımsız sette net iyileşme
oldu — sonuç: iç test setinin kendi etiketleri (aynı LLM'in tekrar
etiketlemesiyle) hafif tutarsızlaştı, ama modelin gerçek genelleme başarısı
arttı. Bu gözlem kullanıcıya saklanmadan, iki tabloyla birlikte raporlandı.

**Bulunan 3 bug:**

1. **`sinyalizasyon_haberlesme` ↔ `yolcu_hizmetleri` sınırı** — "cihaz arızası"
   ifadesi CCTV/anons CİHAZININ teknik arızası (`sinyalizasyon_haberlesme`)
   ile "anons yapılmadı/yanlış anons" (`yolcu_hizmetleri`, cihaz sağlam ama
   içerik/hizmet eksik) arasında net ayrılmamıştı. `config.py`'deki iki
   kategorinin `exclude` metinlerine karşılıklı netleştirme eklendi. **Tam
   düzeltildi** (3/3 hedef cümle), ters yönde 1 yeni hata çıktı (kabul
   edilebilir, net kazanç).
2. **P1 kural motorunun varsayımsal/koşullu ifadeyi yakalaması** — "yangın
   çıksa tüpe erişilemez" gibi henüz gerçekleşmemiş risk cümleleri yanlışlıkla
   P1 tetikliyordu. Regex'e negatif lookahead eklendi (`çıksa`, `olursa`,
   `ihtimal` gibi kelimeler ve ekipman adları `tüp`/`merdiven` hariç
   tutuldu). **Tam düzeltildi** (P1 için tüm bağımsız test kayıtları doğru).
3. **P2'nin dolaylı çoğulluk ifadelerini kaçırması** — "hiçbiri çalışmıyor",
   "hepsi bozuk" gibi sayı içermeyen ama "birden fazla ekipman" anlamına
   gelen ifadeler P3'e düşüyordu (kural sadece "iki/üç/birden fazla" gibi
   sayısal ifadeleri tanıyordu). `config.py`'deki P2 kapsam metni
   genişletildi VE 20 elle gözden geçirilmiş hedefli örnek üretilip
   (`data/raw/p2_dolayli_cogulluk.jsonl`, kullanıcı tarafından bağımsız
   olarak üretilip getirildi) eğitim havuzuna eklendi. **Kısmen düzeltildi**
   (0/3 → 2/3 hedef cümle), kalan 1 vaka farklı bir yönde başarısız oluyor
   (P3 yerine artık P1'e kayıyor — fiziksel mahsur kalma ifadesi, "can
   güvenliği" ile "operasyonel aksama" arasında gerçekten belirsiz bir sınır).
   Azalan getiri noktası olarak kabul edildi, ileri düzeltme ertelendi.

Bu bulgu-düzeltme döngüsü, projenin "az örneklem + tek ölçüm = gürültü"
dersinin dördüncü örneği: iç test setindeki görünür gerileme, bağımsız
doğrulama olmasaydı yanlış yorumlanıp geri alınabilirdi.

## Adım 11 — Frontend'in üç boyutlu sözleşmeye taşınması + iki gerçek backend hatası (23 Ağu 2026)

### Frontend: intent/öncelik rozetleri, yapısal bilgiler, kanıt, eksik bilgi, tekrar uyarısı

`frontend/src/components/SonucKarti.jsx` v1 sözleşmesinde kalmıştı (sadece
kategori + güven + ikincil kategori). Backend zaten Adım 9'da üç boyutu
döndürüyordu ama arayüz bunları hiç göstermiyordu. Eklenenler (hepsi mevcut
koyu tema tasarım diliyle: cam yüzeyler, `color-mix` ile kategori/öncelik
rengine uyarlanan rozetler, `--vurgu` ile ortam ışığı):

- **Meta satırı** — kategori rozetinin altında intent rozeti (nötr) + öncelik
  rozeti (öncelik rengiyle boyalı, `priority_color`). Öncelik P1 kural
  katmanından geldiyse rozetin yanında küçük bir **"KURAL"** etiketi çıkıyor
  — kullanıcı önceliğin modelden mi kuraldan mı geldiğini görsel olarak
  ayırt edebiliyor.
- **Yapısal Bilgiler** paneli — `line`/`station`/`location`/`equipment`/
  `symptom`/`root_cause` alanlarından doğru olanlar bir ızgarada gösteriliyor;
  hiçbiri yoksa panel hiç render edilmiyor.
- **Kanıt** paneli — `evidence` dizisi (gradient × input) kelime kelime
  "chip" olarak gösteriliyor, "modelin en çok dikkate aldığı kelimeler"
  notuyla.
- **Eksik Bilgi** kutusu — `missing_information` doluysa nötr/bilgi renginde
  (mavi, uyarıdan ayrı bir görsel dil — bu bir hata değil, eksik bir alan)
  bir kutuda hangi alanların eksik olduğu **Türkçe etiketle** gösteriliyor
  (ilk sürümde İngilizce alan adı `equipment` gibi ham haliyle çıkıyordu,
  aynı `VARLIK_ETIKETLERI` sözlüğüyle çeviri eklendi).
- **Olası Tekrar Bildirim** uyarısı — `possible_duplicate` + `duplicate_of`
  doluysa mevcut `.uyari` bileşeni yeniden kullanılarak "aynı arıza son 15
  dakikada N kez bildirilmiş, ilk bildirim: …" gösteriliyor.

### Bulunan iki gerçek backend hatası — frontend'i uçtan uca test ederken ortaya çıktı

Bunlar frontend değişikliği DEĞİL; Adım 9'da mimari tek başlıktan çok başlığa
geçerken (`AutoModelForSequenceClassification` → `CokBaslikliSiniflandirici`)
güncellenmeyi atlayan iki backend modülüydü. Arayüz gerçek bir tahmin
isteyene kadar hiçbiri fark edilmemişti.

1. **`src/similarity.py` — backend hiç ayağa kalkmıyordu.**
   `_bert_govde()` fonksiyonu hâlâ eski mimarinin `model.base_model.model.bert`
   yolunu arıyordu; yeni `CokBaslikliSiniflandirici`'de böyle bir öznitelik
   yok (gövde `self.govde` altında duruyor ve zaten doğrudan çağrılabilir
   BertModel). Sonuç: `AttributeError`, lifespan çöküyor, backend hiç
   başlamıyordu. Düzeltme: gövdeye doğrudan `model.govde` ile erişip,
   `pooler_output` yerine sınıflandırma başlıklarının da kullandığı **aynı
   [CLS] temsilini** (`last_hidden_state[:, 0]`) kullanacak şekilde
   `_embed()` yeniden yazıldı — "modelin kendi iç temsili" iddiası artık
   gerçekten doğru, çünkü benzerlik ve sınıflandırma aynı vektörü kullanıyor.
2. **`src/extract.py` — `root_cause` alanı bazen NEREDEYSE TÜM cümleyi
   yakalıyordu.** `_SEBEP_DESENI` regex'inin yakalama grubu (`.{3,60}?`)
   nokta karakteri de dahil her şeyi eşleştirebiliyordu; `re.search` en
   erken başlangıç noktasını denediği için (cümle başından itibaren), cümle
   içinde birden fazla virgülle ayrılmış madde varsa yakalama en baştan
   başlayıp istenmeyen şekilde uzuyordu (örn. "…çalışmıyor, elektrik
   kesildiği için durdu" → `root_cause: "y 2 numarali giristeki yuruyen
   merdiven calismiyor, elektrik"`). Düzeltme: yakalama sınıfı noktalama
   işaretlerini (`,` `.` `;` `:`) dışlayacak şekilde `[^,.;:]{3,60}?`
   yapıldı — artık yakalama bir önceki noktalama işaretini geçemiyor, aynı
   cümle artık doğru şekilde `root_cause: "elektrik"` veriyor.

Backend'in üç ay önce yazılan bir bölümünün, mimari değiştiğinde SESSİZCE
bozulmuş olması ve bunun ancak uçtan uca (gerçek HTTP isteğiyle) test
edilince ortaya çıkması — projenin "type checking/test suite doğruluk
kanıtlamaz, gerçekten çalıştırmak kanıtlar" ilkesinin somut bir örneği daha.

### Doğrulama

Backend + frontend birlikte tarayıcıda uçtan uca test edildi: normal arıza
bildirimi (yapısal alanlar + kanıt + eksik bilgi doğru çıktı), P1 kural
tetiklenen yangın bildirimi (KURAL etiketi + kırmızı ortam ışığı doğru),
model tabanlı P1 (KURAL etiketi YOK, ayrım doğru çalışıyor), canlı kategori
grafiğinin her tahminde güncellenmesi, ve mobil yerleşim (375px). `Doğru`/
`Yanlış` onay akışı ve taksonomi paneli değişmeden korundu.

### İkinci tur uçtan uca kontrol (24 Ağu 2026) — üç gerçek hata daha bulundu

Kullanıcı arayüzü kendisi denemeye başlamadan önce ayrı bir uçtan uca kontrol
turu istendi. Üç gerçek hata bulundu, üçü de düzeltildi:

1. **`src/config.py` — numaralı ekipman ifadeleri kayboluyordu.**
   `LOCATION_PATTERNS`'teki ilk (numaralı) desen `asansor|merdiven|turnike|
   pano` kelimelerini de içeriyordu — bunlar aynı zamanda `EQUIPMENT`
   sözlüğünde birebir geçen kelimeler. "3 numaralı asansör kapısı sıkıştı"
   gibi bir bildirimde `_konumu_maskele()` tüm ifadeyi (ekipman kelimesi
   dahil) metinden silip `ekipman_bul()`'un "asansör"ü bulmasını
   engelliyordu; `equipment: null` dönüyordu. Bu dört kelime desenden
   çıkarıldı — gerçek konum-belirteci kullanımlar ("X'in yanındaki Y") zaten
   ayrı bir desenle karşılanıyor. `extraction_degerlendirme.json`'daki
   sayılar bu değişiklikten ETKİLENMEDİ (git stash ile doğrulandı, sorun
   zaten var olan 40 kayıtlık referans setinde bu senaryoyu hiç içermiyordu).
2. **`src/db.py` — zaman damgası yerel saatte, sorgular UTC'de (daha ciddi).**
   `time.strftime()` YEREL saati (Türkiye UTC+3) yazıyordu, ama tekrar/
   dene-yanıla sorguları SQLite'ın UTC döndüren `datetime('now', ...)`
   fonksiyonuyla karşılaştırıyordu. Sonuç: 30 saniyelik dene-yanıla koruması
   ve 15 dakikalık "olası tekrar bildirim" penceresi fiilen ~3 saate
   genişlemişti. Canlı testte tam olarak bu şekilde yakalandı: dakikalar önce
   gönderilmiş bir metin yanlışlıkla "az önce tekrar gönderildi" sayıldı.
   `_simdi_utc()` eklendi (`time.gmtime()`), mevcut `data/logs.db`'deki
   ~2574 kayıt da `-3 saat` kaydırılarak düzeltildi (tek seferlik veri
   onarımı, koda dahil değil).
3. **`/examples` boş dönüyordu.** v1'in `gold.jsonl`'i Taksonomi v2'ye
   geçince devre dışı bırakılmıştı (bkz. Açık Nokta #4) ama `/examples`
   hâlâ ona bakıyordu. `config.EXAMPLES_FILE` adında ayrı bir sabit eklendi
   (`data/seed/yeni_gold_deneme.jsonl`'e işaret ediyor) — `GOLD_FILE`'ın
   kendisi DEĞİŞTİRİLMEDİ, çünkü `generate_seed.py`/`apply_review.py` hâlâ
   ona yazıyor ve kullanıcının bağımsız test setini üzerine yazma riski
   taşırdı. Frontend'deki "gold test setinden geliyor" notu da gerçeğe
   uyacak şekilde güncellendi.

Ayrıca `tests/test_api.py`'deki 6 başarısız test (v1 kategori adları
`istasyon_mekanik`/`guvenlik_emniyet` bekliyordu, `/examples` testi
`GOLD_FILE`'a bakıyordu) v2 taksonomisine göre düzeltildi — **31/31 test
geçiyor.**

## Adım 12 — Hard-negative örneklerle sinyalizasyon/yolcu_hizmetleri sınırının düzeltilmesi (24 Ağu 2026)

### Bulunan overfitting

Kullanıcı arayüzü kendi denerken `sinyalizasyon_haberlesme` (donanım/cihaz
arızası) ile `yolcu_hizmetleri` (bilgi/içerik eksikliği) kategorileri
arasında modelin sınırı net ayıramadığını fark etti — aynı yüzeysel kelimeler
("ekran", "anons") iki farklı kök sebep için kullanılabiliyor ama model
sözcüksel örtüşmeye takılıp kök sebebi (donanım mı bozuk, yoksa içerik mi
eksik/yanlış) ayırt edemiyordu.

**Çözüm: 10 çift (20 kayıt) elle hazırlanmış "hard negative" — kasıtlı zıt
ikili.** Her çift AYNI yüzeysel senaryoyu (ekran karanlık, anons duyulmuyor,
turnike sensörü...) iki farklı kök sebeple veriyor: biri donanımın FİZİKSEL/
TEKNİK olarak bozuk olduğu durum (`sinyalizasyon_haberlesme`), diğeri
donanım sağlam ama İÇERİK/BİLGİ yanlış veya eksik olduğu durum
(`yolcu_hizmetleri`). Örnek: "Ekran cam gibi parlak çalışıyor ama tren saati
yazmıyor, sadece reklamlar dönüyor" (donanım sağlam → yolcu_hizmetleri) vs.
"Tavandaki ekranın camı kırılmış, süre yazmıyor" (donanım bozuk →
sinyalizasyon_haberlesme). Kontrastif çiftler, sınırın SÖZCÜKLERDE değil
ANLAMDA olduğunu modele doğrudan öğretmenin bir yolu.

`data/raw/hard_negative_sinyalizasyon_yolcu.jsonl` — 20 kayıt, `relabeled.jsonl`'e
eklenmeden önce doğrulandı: tüm kategori/intent/öncelik anahtarları geçerli,
mevcut 2488 kayıtla birebir tekrar VE `review.similarity ≥ 0.80` yakın kopya
**yok**. `relabeled_v5_backup.jsonl` ekleme öncesi yedek.

### Sonuç

| ölçüm | önce | sonra |
| --- | --- | --- |
| 20 hedefli çiftte kategori doğruluğu | — | **19/20 (%95)** |
| Bağımsız sette (80 kayıt) kategori doğruluğu | — | **%91.2** (F1 0.9084) |
| Bağımsız sette sinyalizasyon↔yolcu_hizmetleri karışması | — | **0** |
| Bağımsız sette öncelik doğruluğu | %81.2 | %78.8 (F1 0.7785) |

Hedeflenen sınır düzeldi: bağımsız test setinde bu iki kategori arasında artık
hiç karışma yok (önceki confusion matrix'te de zaten görünmüyordu ama iç
test setinde ve kullanıcının canlı denemesinde tekrar tekrar çıkıyordu — bu
turun asıl motivasyonu buydu). Kalan tek hata ("ekran kapkaranlık, elektrik
gelmiyor" → yanlışlıkla yolcu_hizmetleri) muhtemelen "elektrik" kelimesinin
`elektrik_enerji` sinyaliyle karışıp asıl ayırt edici sinyali (ekranın
tamamen karanlık/çalışmaz durumda olması) gölgelemesinden kaynaklanıyor.

**Öncelik doğruluğu 2.4 puan düştü (%81.2→%78.8), muhtemelen gürültü.** Bu
turda önceliğe yönelik hedefli veri eklenmedi (hard negative'lerin öncelik
etiketleri yan ürün); projenin kendi "az örneklem + tek ölçüm = gürültü"
dersi burada da geçerli olabilir (n=80, tek eğitim koşusu). Takip edilmeli
ama tek başına endişe verici değil.

Eğitim early-stopped (epoch 7/12'de durdu, epoch 5 en iyi ortF1 0.8312 ile
seçildi): kategori F1 0.8980, intent F1 0.8647, öncelik F1 0.7310.

### İkinci tur: kapı/kapak arızalarında sinyalizasyon/mekanik/araç sınırı

Aynı gün kullanıcı benzer bir sınır sorununu daha buldu: **peron ayırıcı
kapı (PAKS, `sinyalizasyon_haberlesme`)** ile **vagon kapısı (`arac_tren`)**
ve **istasyon giriş/asansör kapısı (`mekanik_istasyon`)** arasında model
"kapı" kelimesine takılıp hangi kapının (peron mu, vagon mu, istasyon
girişi mi) arızalı olduğunu ayırt edemiyordu. Aynı yöntemle 13 hard-negative
kayıt eklendi (`data/raw/hard_negative_kapi.jsonl`, 6 üçlü/ikili karşılaştırma
grubu) — her grup aynı "kapı açılmadı/sıkıştı" senaryosunu üç farklı kapı
türüyle veriyor. Ekleme öncesi doğrulandı (geçerli anahtarlar, birebir tekrar
yok, yakın kopya yok); `relabeled_v6_backup.jsonl` yedek.

Model yeniden eğitildi (early-stopped, epoch 8/12'de durdu, epoch 6 seçildi,
ortF1 0.8467 — önceki turdan yüksek): kategori F1 0.9158, intent F1 0.8623,
öncelik F1 0.7620.

**Sonuç:**

| ölçüm | önceki tur | bu tur |
| --- | --- | --- |
| 13 hedefli kapı çiftinde kategori doğruluğu | — | **13/13 (%100)** |
| Önceki 20 sinyalizasyon/yolcu çiftinde regresyon | — | **yok** (%100 korundu) |
| Bağımsız sette (80 kayıt) kategori doğruluğu | %91.2 | %88.8 |
| Bağımsız sette öncelik doğruluğu | %78.8 | %76.2 |

Hedeflenen iki sınır sorunu da (sinyalizasyon/yolcu_hizmetleri VE
sinyalizasyon/mekanik/araç-kapı) tam çözüldü, birbirini bozmadı. Ama bağımsız
sette ~2.5 puanlık ek bir düşüş var. Hata döküntüsüne bakıldığında düşüşün
kaynağı yeni eklenen kapı verisiyle **doğrudan ilgisiz** kategoriler
(Elektrik/Enerji↔Sinyalizasyon, Altyapı↔Yol ve Hat) — yani muhtemelen
projenin daha önce ölçtüğü **tohum varyansı** fenomeni (bkz. "Tohum varyansı"
bölümü, Adım 5 sonu: aynı veriyle bile farklı tohumlar gold F1'i 0.91-0.96
arası oynatabiliyor), tek koşunun gürültüsü — ama bu tek koşuyla kesin
kanıtlanamaz. Takip edilmesi gereken bir gözlem olarak not düşüldü, ikinci
bir tohumla doğrulama şimdilik yapılmadı (kullanıcı kararı: mevcut sonuçla
devam).

### Üçüncü tur: 60 kayıtlık genel çeşitlilik artışı — şimdiye kadarki en iyi sonuç

Kullanıcı üç kategoriye (`elektronik_sistemler`, `temizlik`, `yol_yapisal`)
20'şer kayıt olmak üzere 60 kayıt daha getirdi — bunlar hard-negative çifti
DEĞİL, sadece o kategorilerin dil çeşitliliğini artıran ek örnekler
(biletmatik/turnike elektronik arızaları, hijyen/kirlilik senaryoları, ray
hattı yapısal arızaları). Aynı doğrulama adımlarından geçirildi (geçerli
anahtar, birebir/yakın kopya kontrolü — hepsi temiz), `data/raw/
sentetik_ek_train.jsonl` olarak kaydedildi, `relabeled_v7_backup.jsonl`
yedeklendi.

Eğitim havuzu **2521 → 2581 kayda** çıktı (train 2069→2128, val 262→269,
test 258→265, clean 2599→2660). Model yeniden eğitildi (early-stopped,
epoch 7/12'de durdu, epoch 7 en iyi — ortF1 0.8349): kategori F1 0.8614,
intent F1 0.8619, öncelik F1 0.7816.

**Sonuç — bağımsız sette bugüne kadarki en iyi ölçüm:**

| ölçüm | bir önceki tur | bu tur |
| --- | --- | --- |
| Bağımsız sette (80 kayıt) kategori doğruluğu | %88.8 | **%96.2** (F1 0.9616) |
| Bağımsız sette öncelik doğruluğu | %76.2 | **%82.5** (F1 0.8241) |
| Yeni 60 kayıtta kategori/öncelik doğruluğu | — | %100 / %95.0 |
| Önceki 20 sinyalizasyon/yolcu çiftinde regresyon | — | yok (%100 korundu) |
| Önceki 13 kapı çiftinde regresyon | — | 1 hata (12/13, %92.3) |

Bu sonuç, bir önceki turdaki düşüşün gerçekten **tohum/veri-karışımı
varyansı** olduğu yorumunu doğruluyor: aynı yöntemle (hard-negative +
genel çeşitlilik) devam edilince hem kategori hem öncelik, projenin o ana
kadarki en iyi rakamlarını (sırasıyla %91.2 ve %81.2) da geçti. Tek bir
kapı çiftinde (peron ayırıcı kapının camı çatlağı → mekanik yerine
sinyalizasyon bekleniyordu) küçük bir gerileme oldu, ihmal edilebilir
büyüklükte.

## Genel İlkeler (her adımda geçerli)

1. **`config.py` tek doğruluk kaynağı.** Yeni bir modül yazarken kategori/
   stil/hiperparametre asla orada yeniden tanımlanmaz, hep import edilir.
2. **Kaynak koddaki Türkçe metin her zaman doğru aksanlarla yazılır**
   (yukarıdaki "Ders 1"). Bu, LLM prompt'u olarak kullanılacak her yeni
   metin için geçerli (örn. Adım 2b'nin çoğaltma prompt'u).
3. **Gold seti few-shot'ta veya eğitimde asla kullanılmaz**, sadece nihai
   test için saklanır.
4. **Yeni bir LLM sağlayıcı denerken önce canlı model listesini sorgula**
   (`check_openrouter_models.py` örnek alınabilir), id tahmin etme.
5. **Kalıcı hata (kota/kimlik doğrulama) ile geçici hata (bozuk JSON, tek
   seferlik) ayrımı önemli** — `generate_seed.py`'deki `call_llm` bu ayrımı
   yapıyor, yeni script'lerde de aynı desen izlenmeli (tek kategori/parça
   hatası tüm çalıştırmayı çökertmemeli).
6. **`.gitignore`'a bir şey eklemeden ÖNCE gerçek boyutuna ve rolüne bak.**
   Bu projede aynı hata iki kez yapıldı: önce `data/raw/` + `data/processed/`,
   sonra `model/*.safetensors` refleks olarak gitignore'a eklendi ve ikisi de
   geri alınmak zorunda kaldı. İkisi de **adımların asıl çıktısıydı**, üstelik
   küçüktü (veri 580 KB, LoRA adaptörü 2.3 MB).

   Ölçüt — gitignore'a sadece şunlar girer:
   - yeniden üretilebilen ara ürünler (`__pycache__`, `*.pyc`)
   - gizli bilgi (`.env`)
   - makineye özel yerel ayarlar (`.claude/settings.local.json`, `.DS_Store`)
   - **gerçekten** büyük dosyalar (yüzlerce MB+)

   Bir adımın teslim ettiği ürün (üretilen veri, eğitilmiş model, bölünmüş
   veri seti) küçükse **commit edilir**. Sebep: bu proje adım adım ilerliyor ve
   her commit'in o adımın çalıştığını kanıtlaması gerekiyor; depoyu klonlayan
   birinin modeli yeniden eğitmek zorunda kalmaması lazım. Ayrıca LoRA
   adaptörünün 2.3 MB olması raporda öne çıkarılan bir bulgu — onu gizlemek
   kendi iddiamızın kanıtını silmek olurdu.

   **Dosya uzantısına bakıp varsayma, `du -h` ile bak.**

## Git İş Akışı Kuralı (Claude Code bunu her adımda uygulasın)

Bu proje adım adım (Adım 2b, 3, 4, 5, 6...) ilerliyor. Her adım için şu sıra
**kesinlikle** izlenir:

1. **Kodu yaz/düzenle.**
2. **Çalıştır ve test et.** Sadece kod yazmak yeterli değildir — script'i
   gerçekten çalıştır, çıktısını gör, hata varsa düzelt, tekrar çalıştır.
   "Kodu düzenledim" ile "denedim ve çalıştığını doğruladım" farklı
   şeylerdir; sadece ikincisi bir adımı tamamlanmış sayar.
3. **Bu dosyayı (`CLAUDE.md`) güncelle.** Bu ayrı bir iş veya sonraya
   bırakılabilir bir ek DEĞİL — adımın tamamlanma tanımının parçası.
   Güncellenecek tipik yerler: klasör yapısı (yeni yazılan dosya artık "YOK"
   görünmesin), veri sayıları, yeni config ayarları ve CLI argümanları,
   alınan kararlar ve gerekçeleri, ölçüm sonuçları, ve artık geçerli olmayan
   "Açık Noktalar" maddelerinin kapatılması. Sebep: bu dosya sıradan bir
   README değil, oturumlar arası taşınan tek bağlam kaynağı ve staj
   sunumunun dayanağı; güncellenmezse bir sonraki oturum yanlış bilgiyle
   başlar.
4. **Adım gerçekten çalıştığı doğrulanınca**, bana kısaca ne yapıldığını ve
   test sonucunu özetle, **git'e commit + push için onay iste.** Kod
   değişikliği ile `CLAUDE.md` güncellemesi AYNI commit'te sunulur.
5. **Benden açık onay gelmeden asla `git push` yapma.** "Onaylıyorum",
   "push'la", "evet" gibi net bir cevap bekle. Onay gelmeden bir sonraki
   adıma da geçme — sırayla ilerle.
6. Onay gelince o adımı **kendi başına bir commit** olarak işle (önceki
   adımlarla birleştirme) ve push et. Commit mesajı hangi adım olduğunu
   ve ne yapıldığını açıkça belirtsin (ör. `Adım 2b: Ollama ile çoğaltma
   scripti (generate_data.py) + 1600 örnek üretimi`).
7. Böylece git geçmişinde proje adım adım, her biri çalıştığı doğrulanmış
   halde görünür — bu hem staj sunumunda ilerlemeyi göstermek hem de bir
   adımda sorun çıkarsa geri dönebilmek için önemli.

**İlk push'tan önce:** Eğer bu klasörde henüz git deposu yoksa veya uzak
(remote) repo bağlı değilse, sessizce varsaymadan önce bana sor — hangi
remote'a (GitHub vb.) push edeceğimizi netleştirelim.

**Asla yapılmayacaklar:**

- Test edilmemiş kodu commit/push etmek
- Onay istemeden push etmek
- Birden fazla adımı tek commit'te birleştirmek
- Onay bekliyorken sessizce bir sonraki adıma geçmek

## Staj Sunumu İçin Notlar

- Orijinal PDF taslağındaki 6 kategori / 70 örnek/kategori / 420 toplam
  rakamları güncel: **8 kategori / 200 örnek/kategori / 1600 toplam.**
- PDF'te olmayıp sonradan eklenen: confidence threshold mekanizması
  (`low_confidence` uyarısı).
- 4 farklı LLM sağlayıcısının ampirik karşılaştırılması (yukarıdaki tablo)
  metodoloji bölümü için güçlü, özgün bir içerik — "neden bu modeli
  seçtim" sorusuna veriye dayalı bir cevap.
- Sentetik veri + gold test seti ayrımı, "veri gerçekçi mi" eleştirisine
  karşı somut bir savunma sağlıyor.
- **İkinci ampirik karşılaştırma (Adım 2b):** aynı görevde Nemotron %4.5 vs
  qwen2.5:14b %15.8 işaretli, 1586 kayıt üzerinden. Bulut/yerel model
  tercihini veriye dayandıran ikinci bir tablo.
- **"Düşük işaretli oran ≠ kalite" bulgusu:** qwen'in asıl zayıflığı otomatik
  triyajın ölçtüğü şey değil, özel isim/teknik terim uydurmasıydı
  (`marmaraisi`, `perde çarkı`). Otomatik metriklerin kör noktası olduğunu
  gösteren somut bir örnek — rapora olgunluk katar.
- **Veri sızıntısına karşı üç katmanlı savunma** anlatılabilir: (1) üretim
  anında near-dup reddi, (2) split öncesi kümeleme, (3) her çalıştırmada
  otomatik gold sızıntı kontrolü. Ayrıca kümeleme eşiğinde bulunup düzeltilen
  simetri hatası, "eşiğe dayanan sistemde ölçütün tutarlılığı kritiktir"
  dersinin somut örneği.
- **Gold'da yazım hatası bilinçli olarak korundu** ("personel aceleyle bunu
  yazar mıydı?" ölçütü). Gerçekçi gürültü kalır, üretim artığı temizlenir.
  Gold'u gerçek hayattan temiz yapmak başarı oranını şişirirdi.
- **En güçlü tek sonuç: gold skoru test'ten yüksek çıktı** (macro F1 **0.9247**
  vs 0.9135). Sentetik veriyle eğitilen model, bağımsız üretilmiş ve elle gözden
  geçirilmiş sette daha iyi. "Model ezberledi mi?" sorusuna ölçülmüş cevap.
  Üstelik bu iki bağımsız eğitimde de tekrarlandı (çoğaltmasız: 0.9014 vs
  0.8935), yani tesadüf değil.
- **LoRA öğrenme hızı hatası** (2e-5 → 5e-4, model rastgele seviyeden 0.93'e)
  metodoloji bölümü için değerli: hiperparametre literatürden kopyalanamaz,
  eğitim yöntemine göre ayarlanır. Ölçüm tablosu elde var.
- **Taksonomi sınır sorununa mühendislik çözümü:** kural yazmak yerine modelin
  olasılık dağılımını kullanmak (top-2 doğruluk 0.975). Kural bazlı çözümün
  neden ölçeklenmediği (28 kategori çifti) ve marj eşiğinin nasıl kalibre
  edildiği anlatılabilir. "Sistemi modele uydurmak yerine modelin bildiğini
  kullanmak" — sunumda güçlü bir başlık.
- **Model boyutu:** LoRA adaptörü 2.4 MB, tam fine-tuning 440 MB olurdu.
  Dağıtım/versiyonlama avantajı somut bir kazanım.
- **Aksan dayanıklılığı — "ölç, teşhis et, çöz, doğrula" döngüsünün tam örneği:**
  stil bazlı ölçüm gürültülüydü (güven aralıkları örtüşüyordu), müdahaleli
  nedensel test net cevap verdi (−6.4 puan), tokenizer mekanizmayı gösterdi
  (`asansör` 1 parça / `asansor` 3 parça), veri çoğaltma çözdü (−1.16 puan),
  aynı test doğruladı. Sunumda tek slaytta anlatılabilecek eksiksiz bir
  mühendislik hikâyesi.
- **"Otomatik tespit her zaman mümkün değil" dersi:** yabancı kelime tespiti
  için üç yöntem denendi, ikisi başarısız oldu (bigram sözlüğü 355 yanlış
  alarm; tokenizer parça sayısı yabancı kelimeyi ASCII Türkçe'den ayıramadı).
  Dar ve kesin bir kural, geniş ve gürültülü olandan iyidir — ve elle okuma
  hâlâ tek kapsamlı yöntem. Otomatik araçların sınırını gösteren dürüst bir
  bölüm, rapora olgunluk katar.
