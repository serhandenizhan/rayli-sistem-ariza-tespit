# Metro İstanbul Arıza Tespit Sınıflandırıcı

Serbest metinli arıza bildirimlerini (örn. *"Yürüyen merdiven durdu 2. peron"*)
otomatik olarak analiz eden bir NLP sistemi. Tek bir cümleden **üç boyutu
birden** çıkarır — bildirimin amacı, teknik kategorisi ve önceliği — ve
yapısal alanlarla birlikte ilgili bakım ekibine yönlendirir.

Metro İstanbul'da yapılan bir staj kapsamında geliştirilmiştir. Proje
kararlarının, ölçümlerin ve gerekçelerin tam dökümü için [`CLAUDE.md`](CLAUDE.md);
taksonomi ve çıktı sözleşmesi için [`yeni-eklemeler.md`](yeni-eklemeler.md).

> **24 Ağu 2026 — tek platforma taşındı.** Bu proje artık `rayli_ariza_tespiti`
> deposunun `nlp/` alt dizininde, sensör tabanlı arıza tespit sistemiyle aynı
> Next.js dashboard'u (`../web/`, "Metin Bildirimleri" sekmesi) paylaşıyor —
> ayrı bir FastAPI servisi (`:8001`) olarak; eski bağımsız Vite arayüzü
> kaldırıldı. Bu README'nin geri kalanı güncel talimatları içerir. Entegrasyon
> özeti için üst dizindeki `../CLAUDE.md` → "NLP metin sınıflandırma modülü"
> bölümüne bakın; uçtan uca başlatmak için `../calistir.sh`.

## Mimari

```
KULLANICI METNİ
      │
      ▼
┌─────────────────────────────────────────┐
│  BERTurk + LoRA  (tek gövde, üç başlık) │
│    ├── INTENT      5 sınıf              │
│    ├── CATEGORY   11 sınıf              │
│    └── PRIORITY    4 sınıf              │
└─────────────────────────────────────────┘
      │
      ├──► kurallı çıkarım: hat, istasyon, konum, ekipman, belirti, kök sebep
      ├──► P1 kural katmanı (yangın, elektrik çarpması… → koşulsuz P1)
      ├──► gradient × input → evidence
      ├──► eksik bilgi tespiti → kullanıcıya soru
      └──► tekrar tespiti (aynı istasyon + ekipman + 15 dk)
      │
      ▼
  FastAPI (:8001) ──► ../web/ Next.js dashboard (:3000, "Metin Bildirimleri" sekmesi)
```

**Model:** `dbmdz/bert-base-turkish-cased` + LoRA (PEFT). Üç sınıflandırma
başlığı ortak gövdeyi paylaşır; eğitilen parametre 605K (%0.54), adaptör
**2.3 MB**. Ayrı üç model eğitmek yerine multi-task seçildi — gerekçesi
`src/model.py` modül notunda.

**Eğitim:** cross-entropy + L2 (AdamW `weight_decay`) + gradient clipping,
ve validation loss'a dayalı **early stopping** (`EARLY_STOPPING_PATIENCE`,
varsayılan 3 epoch). En iyi checkpoint val loss'a değil, üç görevin ortalama
macro-F1'ine göre seçilir — iki sinyal bilinçli olarak ayrı tutuluyor. Eğitim
sırasında `model/canli_kayip.json` canlı güncellenir; `dev/canli_kayip.html`
sayfası (`http.server` ile `:8799`) bunu tarayıcıda grafik olarak gösterir.

**Doğrulama:** model, eğitim verisini üreten LLM'den **bağımsız** başka bir
kaynaktan gelen 80 kayıtlık elle etiketlenmiş bir test setiyle de ayrıca
sınanıyor (`python -m src.toplu_test <dosya.jsonl>`), ezber riskine karşı.
Güncel sonuç: bağımsız sette kategori doğruluğu **%96.2** (F1 0.9616),
öncelik doğruluğu **%82.5** (F1 0.8241) — bkz. `CLAUDE.md` Adım 12.

**Hard-negative örnekler:** kategori sınırının kelimelere değil anlama göre
çizilmesini öğretmek için kasıtlı zıt-ikili (contrastive pair) örnekler
kullanıldı — aynı yüzeysel senaryo (ör. "ekran karanlık"), iki farklı kök
sebeple (donanım fiziksel bozuk ↔ donanım sağlam ama içerik yanlış/eksik)
iki farklı kategoriye veriliyor. Bu yöntemle `sinyalizasyon_haberlesme` /
`yolcu_hizmetleri` ve `sinyalizasyon_haberlesme` / `mekanik_istasyon` /
`arac_tren` (kapı arızaları) sınırlarındaki karışma giderildi.

## Güncel sonuçlar

| görev | iç test seti | bağımsız test seti (80 kayıt, farklı LLM) |
| --- | --- | --- |
| Kategori (11 sınıf) | acc %85.8 · F1 0.8614 | acc **%96.2** · F1 0.9616 |
| Intent (5 sınıf) | acc %91.8 · F1 0.8619 | — |
| Öncelik (4 sınıf) | acc %78.7 · F1 0.7816 | acc **%82.5** · F1 0.8241 |

Bağımsız test seti eğitim verisini üreten LLM'den tamamen farklı bir
kaynaktan geldiği ve eğitime hiç girmediği için asıl güvenilir ölçüt bu —
iç test setinden daha yüksek çıkması modelin ezberlemediğinin, kalıbı değil
kategoriyi öğrendiğinin somut kanıtı.

## Kategoriler (11)

| kategori | kapsam (özet) |
| --- | --- |
| Mekanik ve İstasyon | yürüyen merdiven, asansör, turnikenin mekanik arızası, kayar kapılar |
| Elektrik ve Enerji | aydınlatma, jeneratör, katener, üçüncü ray, trafo, pano, sigorta |
| Araç ve Tren | tren kapısı, HVAC, fren/cer, vagon camı ve koltuğu, araç içi anons |
| Sinyalizasyon ve Haberleşme | sinyal arızası, PAKS/PSD, CCTV ve sensörlerin teknik arızası, telsiz |
| Elektronik Sistemler | biletmatik, kart okuyucu, QR, para sıkışması, turnike elektroniği |
| Yol ve Hat | ray kırılması, makas, travers, balast, hat üzerinde cisim |
| İstasyon Güvenliği | güvenlik personeli, kamera görüşünün engellenmesi, yangın/duman |
| Temizlik | çöp, hijyen, kirli zemin, koku, haşere, grafiti |
| Yolcu Hizmetleri | anons içeriği, bilgi ekranları, sefer bilgisi, yönlendirme, yoğunluk |
| Güvenlik ve Asayiş Olayı | saldırı, kavga, hırsızlık, hasta yolcu, şüpheli paket |
| Altyapı ve İnşaat | su sızıntısı, çatlak, tünel yapısı, drenaj, inşaat faaliyeti |

Tam kapsam/istisna metinleri `src/config.py` içindeki `CATEGORIES` sözlüğünde
— tek doğruluk kaynağı orasıdır.

## Boyutlar

**Intent (5):** `fault_report`, `incident_report`, `information_request`,
`complaint`, `suggestion`

**Öncelik (4):** P1 Kritik · P2 Yüksek · P3 Orta · P4 Düşük

P1 için **kural katmanı** modelin önünde çalışır: yangın, elektrik çarpması,
raylara kişi düşmesi, intihar riski, şüpheli paket gibi desenler tahmini ezip
koşulsuz P1 verir. Gerekçe: P1'i kaçırmanın bedeli asimetriktir.

## Gereksinimler

- Python 3.12+ (Apple Silicon'da MPS backend kullanılır, yoksa CPU'ya düşer)
- macOS, Linux veya Windows (WSL önerilir)
- Arayüz artık ayrı bir Vite projesi değil — üst dizindeki `../web/` (Next.js) dashboard'unun
  "Metin Bildirimleri" sekmesi; bu yüzden Node.js sadece orada gerekir.

## Kurulum

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Veri üretimi/etiketleme yapacaksanız `.env` gerekir (çalışan sistemi kullanmak
için gerekmez — model ve veri repoda hazır):

```bash
# .env
OPENROUTER_API_KEY=...
GEMINI_API_KEY=...
```

## Çalıştırma

Tek başına (sadece bu servisi denemek için):

```bash
./venv/bin/uvicorn backend.main:app --reload --port 8001
```

Swagger: http://localhost:8001/docs

Dashboard'la birlikte uçtan uca çalıştırmak için üst dizinden `../calistir.sh`
kullanılır (bu servisi `--nlpsiz` ile atlayabilir) — arayüz
http://localhost:3000 adresindeki "Metin Bildirimleri" sekmesinde açılır.

## Proje adımları (uçtan uca yeniden üretmek için)

| adım | komut | çıktı |
| --- | --- | --- |
| 1 — seed üretimi | `python -m src.generate_seed` | `data/seed/seed.jsonl` |
| 2 — kalite triyajı | `python -m src.review` | konsol raporu |
| 2b — çoğaltma | `python -m src.generate_data` | `data/raw/amplified.jsonl` |
| 2c — üç boyutlu etiketleme | `python -m src.relabel` | `data/raw/relabeled.jsonl` |
| 2d — eksik kategori/intent üretimi | `python -m src.generate_missing` | `data/raw/relabeled.jsonl` (ekler) |
| 3 — ön işleme | `python -m src.preprocess` | `data/processed/*.csv` |
| 4a — eğitim (multi-task, early stopping + canlı loss) | `python -m src.train` | `model/govde/` + `model/basliklar.pt` |
| 4b — değerlendirme | `python -m src.evaluate --hatalari-goster` | `model/degerlendirme.json` |
| 4c — eşik kalibrasyonu | `python -m src.calibrate` | `model/kalibrasyon.json` |
| 4d — öncelik etiket tutarlılığı | `python -m src.oncelik_tutarlilik` | `model/oncelik_tutarlilik.json` |
| 5 — bağımsız set üzerinde test | `python -m src.toplu_test <dosya.jsonl>` | konsol raporu |
| 7 — yapısal çıkarım değerlendirmesi | `python -m src.extract --degerlendir` | `model/extraction_degerlendirme.json` |
| 8 — kategorisiz log kayıtlarını çöz | `python -m src.resolve_logs` | `data/logs.db` güncellenir |

Testler:

```bash
./venv/bin/pytest tests/ -v
```

## API özeti

| yol | ne yapar |
| --- | --- |
| `POST /predict` | metin → intent, kategori, öncelik, yapısal alanlar, evidence, eksik bilgi, tekrar tespiti |
| `GET /health` | servis durumu |
| `GET /model-info` | aktif model, üç görevin boyutları, hiperparametreler, eşikler |
| `GET /categories` | 11 kategori + kapsam/istisna metinleri |
| `GET /intents` | 5 intent + tanımları |
| `GET /priorities` | P1–P4 + kural katmanının tetikleyicileri |
| `GET /examples` | örnek bildirimler (gold setinden, eğitimde hiç kullanılmamış) |
| `POST /logs/verify` | tahmini onayla/düzelt |
| `GET /logs/stats` | log veritabanı özeti |
| `GET /logs/export` | onaylanmış kayıtları JSONL olarak indir |
| `GET /stats/categories` | kategori bazında toplam + canlı sayım |

Örnek istek:

```bash
curl -X POST http://localhost:8001/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "M4 Kadıköy 2 numaralı girişteki yürüyen merdiven çalışmıyor"}'
```

Örnek yanıttan bir kesit:

```json
{
  "intent": "fault_report",
  "category": "mekanik_istasyon",
  "priority": "P3",
  "line": "M4",
  "station": "Kadıköy",
  "location": "2 numaralı giriş",
  "equipment": "yürüyen merdiven",
  "symptom": "çalışmıyor",
  "root_cause": null,
  "evidence": ["merdiven", "yürüyen"],
  "missing_information": [],
  "possible_duplicate": false,
  "routing_unit": "MEKANIK_ISTASYON"
}
```

## Proje yapısı

```
├── data/
│   ├── seed/           # few-shot yemi + gold test seti
│   ├── raw/            # LLM çoğaltma ve etiketleme çıktıları
│   └── processed/      # train/val/test csv
├── model/              # LoRA gövdesi + üç başlık + değerlendirme raporları
├── src/
│   ├── config.py       # TEK doğruluk kaynağı: taksonomi, boyutlar, eşikler
│   ├── model.py        # çok başlıklı sınıflandırıcı
│   ├── relabel.py      # üç boyutlu toplu etiketleme
│   ├── evidence.py     # gradient × input açıklanabilirlik
│   ├── extract.py      # kurallı yapısal çıkarım
│   └── …               # üretim, ön işleme, eğitim, değerlendirme
├── backend/            # FastAPI servisi (:8001, ../web/ dashboard'una proxy'lenir)
├── tests/              # backend entegrasyon testleri
├── scripts/
│   └── rapor_uret.py   # Word raporunu sıfırdan üretir (python-docx gerekir)
├── CLAUDE.md           # tüm proje geçmişi, kararlar, ölçümler
├── yeni-eklemeler.md   # taksonomi ve çıktı sözleşmesi
└── Metro_Istanbul_Ariza_Tespit_Raporu.docx   # staj raporu
```

Raporu güncellemek gerekirse `scripts/rapor_uret.py` düzenlenip yeniden
çalıştırılır — dosya Word'de elle düzenlenmez, script tek doğruluk kaynağıdır:

```bash
./venv/bin/pip install python-docx   # sadece rapor üretimi için, runtime bağımlılığı değil
./venv/bin/python3 scripts/rapor_uret.py
```

## Lisans / kullanım

Bu bir staj projesi prototipidir; gerçek üretim verisiyle entegrasyon
yapılmamıştır. Kategori taksonomisi ve veri seti Metro İstanbul'un gerçek
operasyonel yapısını temsil etme iddiasında değildir.
