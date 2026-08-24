"""
Adim 5 — FastAPI servisi.

Egitilmis BERTurk + LoRA modelini REST API olarak sunar. Model surec
basladiginda BIR KEZ yuklenir ve bellekte tutulur; her istekte yeniden
yuklemek 2-3 saniye surerdi.

API ALAN ADLARI INGILIZCE. Projenin geri kalani (config, degisken adlari,
dokumantasyon) Turkce ama dis dunyaya acilan sozlesme REST konvansiyonuna
uyuyor. Kategori KEY'leri (arac_tren, istasyon_mekanik...) zaten ASCII, aynen
korunuyor; her yanitta insan-okunur `label` ve arayuz icin `color` da var.

Uc mekanizma birlikte calisir:
  1. category + confidence   -> normal tahmin
  2. low_confidence          -> guven CONFIDENCE_THRESHOLD (0.70) altindaysa
  3. secondary_category      -> marj (top1-top2) MARGIN_THRESHOLD (0.40)
                                altindaysa; model iki kategori arasinda
                                kararsizsa ikisini birden bildirir
  manual_review = (1) veya (2) tetiklendiyse true -- operatore "bu bildirime
  insan baksin" diyen tek alan.

(2) ve (3) farkli seyler: (2) "model emin degil", (3) "model HANGI iki secenek
arasinda kararsiz". Olculdu (Adim 4): top-1 dogruluk 0.913/0.925 iken top-2
0.963/0.975 -- model yanildiginda dogru cevap cogu zaman ikinci sirada.

Calistirma:
    ./venv/bin/uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import re
import random
import threading
import time
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src import config as C
from src import db
from src import similarity
from src.extract import cikar as yapisal_cikar
from src.evidence import kanit_cikar

# ---------------------------------------------------------------------------
# Model durumu
#
# Modul seviyesinde tek bir sozluk: uygulama acilirken doldurulur, isteklerde
# okunur. PyTorch cikarimi bloklayici; FastAPI async oldugu icin es zamanli
# isteklerde ayni model nesnesine dokunulmasin diye kilit kullaniyoruz.
# (Prototip icin yeterli; gercek yukte birden fazla worker/kuyruk gerekir.)
# ---------------------------------------------------------------------------

STATE: dict = {"model": None, "tokenizer": None, "device": None, "meta": None,
              "corpus": None}
LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.evaluate import model_yukle
    from src.train import cihaz_sec

    t0 = time.perf_counter()
    device = cihaz_sec()
    model, tokenizer, meta = model_yukle(device)

    db.init()   # tablo yoksa olustur, bossa gecmis havuzu (clean.csv) seed'le

    # Benzerlik corpus'u: egitim havuzunun tamami icin embedding, bir kez.
    # Diske onbelleklenmiyor (bkz. src/similarity.py modul notu).
    tc0 = time.perf_counter()
    corpus = similarity.corpus_hazirla(model, tokenizer, device)
    print(f"[backend] benzerlik corpus'u hazir: {len(corpus.metinler)} kayit "
          f"({time.perf_counter() - tc0:.1f} sn)")

    STATE.update(model=model, tokenizer=tokenizer, device=device, meta=meta,
                 corpus=corpus, load_seconds=time.perf_counter() - t0)
    print(f"[backend] model yuklendi ({STATE['load_seconds']:.1f} sn) "
          f"| device={device} | LoRA={meta.get('lora')} "
          f"| best epoch={meta.get('en_iyi_epoch')}")
    yield
    STATE.clear()


app = FastAPI(
    title="Metro İstanbul Arıza Tespit Sınıflandırıcı",
    description=(
        "Serbest metinli arıza bildirimlerini intent + 11 kategori + öncelik "
        "olmak üzere üç boyutta sınıflandırır ve ilgili bakım ekibine "
        "yönlendirir. Düşük güven ve sınırda bildirim durumlarını ayrı ayrı "
        "işaretler."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Arayuz ayri portta calistigi icin CORS gerekiyor. Onceden allow_origins=["*"]
# idi (herhangi bir site tarayici uzerinden bu API'yi cagirabilirdi); artik
# yalnizca config.CORS_ORIGINS listesindeki kaynaklar. Uretimde CORS_ORIGINS
# ortam degiskeniyle gercek alan adi verilir.
_izinli = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", ",".join(C.CORS_ORIGINS)).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_izinli,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
print(f"[backend] CORS izinli kaynaklar: {_izinli}")


# ---------------------------------------------------------------------------
# Semalar — hepsi response_model olarak baglanir ki OpenAPI/Swagger dokumante
# olsun (aksi halde Swagger "string" gosteriyor).
# ---------------------------------------------------------------------------

class PredictRequest(BaseModel):
    text: str = Field(..., description="Arıza bildirimi metni",
                      examples=["Yürüyen merdiven durdu 2. peron"])


class SimilarCategoryShare(BaseModel):
    category: str
    label: str
    color: str
    count: int
    ratio: float


class SimilarExample(BaseModel):
    text: str
    category: str
    similarity: float


class SimilarResult(BaseModel):
    threshold: float
    total_found: int
    shown: int
    distribution: list[SimilarCategoryShare]
    examples: list[SimilarExample]


class PredictResponse(BaseModel):
    category: str = Field(..., description="Kategori anahtarı, örn. istasyon_mekanik")
    label: str = Field(..., description="İnsan okunur ad, örn. İstasyon Mekanik")
    color: str = Field(..., description="Arayüz rozeti için renk kodu")
    confidence: float

    probabilities: dict[str, float] = Field(
        ..., description="Tüm kategoriler için olasılık (kategori anahtarı -> olasılık)"
    )

    # --- yapisal cikarim (Adim 7, kurallı) --------------------------------
    # Bu dort alan MODELDEN gelmiyor, src/extract.py'deki sozluk/desen
    # eslesmesinden geliyor. Bulunamayan alan None doner -- ozellikle `line`
    # cogu zaman None, cunku bildirimlerin sadece ~%6'sinda hat kodu geciyor.
    line: str | None = Field(None, description="Hat kodu, örn. M4")
    station: str | None = Field(None, description="İstasyon adı")
    location: str | None = Field(
        None, description="İstasyon İÇİNDEKİ konum, örn. '2 numaralı giriş'")
    equipment: str | None = Field(None, description="Arızalı ekipman")
    symptom: str | None = Field(None, description="Belirti (kanonik tip)")
    root_cause: str | None = Field(
        None, description="Bildirimde AÇIKÇA belirtilen kök sebep. Kullanıcı "
        "tahmin yürütüyorsa ('galiba motoru yanmış') null döner — model "
        "teknik teşhis uydurmaz.")
    missing_information: list[str] = Field(
        default_factory=list,
        description="İş emri açmak için gereken ama bildirimde bulunmayan "
        "alanlar; arayüz bunları kullanıcıya sorar")

    # --- intent ve oncelik (model basliklari) ------------------------------
    intent: str = Field(..., description="Kullanıcının amacı, örn. fault_report")
    intent_label: str
    intent_confidence: float
    priority: str = Field(..., description="P1 (kritik) - P4 (düşük)")
    priority_label: str
    priority_color: str
    priority_confidence: float
    priority_rule: str | None = Field(
        None, description="P1 kural katmanı tetiklendiyse sebebi, örn. 'yangın'. "
        "Doluysa öncelik modelden değil kuraldan gelmiştir.")
    routing_unit: str = Field(..., description="Yönlendirilecek birim kodu")

    # --- aciklanabilirlik ---------------------------------------------------
    evidence: list[str] = Field(
        default_factory=list,
        description="Karara en çok katkıda bulunan kelimeler (gradient × input). "
        "Modelin duyarlı olduğu token'ları gösterir; sözlük eşleşmesi DEĞİLDİR.")

    # --- tekrar tespiti -----------------------------------------------------
    possible_duplicate: bool = Field(
        False, description="Aynı kategori + istasyon + ekipman son 15 dakikada "
        "zaten bildirilmiş mi")
    duplicate_of: dict | None = None

    low_confidence: bool = Field(..., description="confidence < CONFIDENCE_THRESHOLD")
    manual_review: bool = Field(
        ..., description="low_confidence veya secondary_category varsa true"
    )
    manual_review_message: str | None = None

    secondary_category: str | None = None
    secondary_label: str | None = None
    secondary_confidence: float | None = None
    secondary_message: str | None = None

    margin: float = Field(..., description="top1 - top2 olasılık farkı")
    response_time_ms: float

    # --- log + benzerlik (Adim 8) ------------------------------------------
    log_id: int = Field(..., description="Bu tahminin log veritabanındaki "
                        "kaydı — /logs/verify ile doğrulamak için kullanılır")
    similar: SimilarResult = Field(
        ..., description="Embedding tabanlı yakınlık: eğitim havuzunda "
        "benzer bulunan kayıtların kategori dağılımı"
    )


class VerifyRequest(BaseModel):
    log_id: int
    correct: bool
    corrected_category: str | None = Field(
        None, description="correct=false ise doğru kategori (opsiyonel)"
    )


class VerifyResponse(BaseModel):
    ok: bool


class LogStats(BaseModel):
    total: int
    live: int
    confirmed_correct: int
    confirmed_incorrect: int


class CategoryCount(BaseModel):
    category: str
    label: str
    color: str
    count: int
    live_count: int
    ratio: float


class CategoryInfo(BaseModel):
    category: str
    label: str
    color: str
    scope: str
    excludes: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str


class ModelInfo(BaseModel):
    base_model: str
    lora: bool
    trainable_params: int
    total_params: int
    best_epoch: int
    best_val_macro_f1: float
    epochs: int
    learning_rate: float
    batch_size: int
    max_length: int
    seed: int
    ascii_augmentation: bool
    train_records: int
    device: str
    load_seconds: float
    confidence_threshold: float
    margin_threshold: float
    num_labels: int
    num_intents: int = 0
    num_priorities: int = 0
    tasks: dict = {}


class ExampleItem(BaseModel):
    text: str
    style: str


class RecentLogItem(BaseModel):
    id: int
    text: str
    category: str
    label: str
    color: str
    confidence: float | None = Field(None, description="Geçmiş havuz kayıtlarında null olabilir")
    source: str
    verified: bool | None = Field(None, description="null=henüz onaylanmadı")
    station: str | None = None
    equipment: str | None = None
    intent: str | None = None
    priority: str | None = None
    timestamp: str = Field(..., description="ISO UTC")


# ---------------------------------------------------------------------------
# Cikarim
# ---------------------------------------------------------------------------


# Normalize edilmis metinde P1 kural desenlerini arar. Eslesirse oncelik
# kosulsuz P1 olur -- gerekcesi config.PRIORITY_RULES yorumunda.
_ONCELIK_DESENLERI = [(re.compile(d), ad) for d, ad in C.PRIORITY_RULES]


def oncelik_kurali(metin: str) -> str | None:
    """P1 tetikleyen kural eslesirse sebebini doner, yoksa None."""
    from src.extract import normalize

    n = normalize(metin)
    for desen, ad in _ONCELIK_DESENLERI:
        if desen.search(n):
            return ad
    return None


def kanit_cikar_guvenli(metin: str) -> list[str]:
    """Kanit cikarimi -- hata durumunda BOS liste doner, tahmini cokertmez.

    Gradient hesabi modelin ic yapisina bagli; bir gun model degisirse burasi
    sessizce bosa dusmeli, /predict calismaya devam etmeli. Aciklama guzel
    ama tahminin kendisi kadar kritik degil.
    """
    try:
        with LOCK:
            return kanit_cikar(STATE["model"], STATE["tokenizer"], metin,
                               STATE["device"])
    except Exception:                                          # noqa: BLE001
        return []


def run_prediction(text: str) -> dict:
    model, tokenizer, device = STATE["model"], STATE["tokenizer"], STATE["device"]

    encoded = tokenizer(
        text,
        truncation=True,
        padding="max_length",
        max_length=C.MAX_LENGTH,
        return_tensors="pt",
    )
    encoded = {k: v.to(device) for k, v in encoded.items()}

    # Cok basli model: tek ileri gecis, uc gorevin logiti birden doner.
    with LOCK, torch.no_grad():
        cikti = model(**encoded)
    probs = torch.softmax(cikti["logits"]["kategori"], dim=-1)[0].cpu()
    intent_probs = torch.softmax(cikti["logits"]["intent"], dim=-1)[0].cpu()
    oncelik_probs = torch.softmax(cikti["logits"]["oncelik"], dim=-1)[0].cpu()

    order = torch.argsort(probs, descending=True)
    first, second = int(order[0]), int(order[1])
    confidence = float(probs[first])
    margin = confidence - float(probs[second])

    primary = C.ID2LABEL[first]
    low_confidence = confidence < C.CONFIDENCE_THRESHOLD
    borderline = margin < C.MARGIN_THRESHOLD

    intent_id = int(intent_probs.argmax())
    intent = C.ID2INTENT[intent_id]

    # ONCELIK: once kural katmani. P1 (can guvenligi) kacirmanin bedeli
    # asimetrik oldugu icin belirli desenler modelin tahminini EZER.
    oncelik_id = int(oncelik_probs.argmax())
    oncelik = C.ID2PRIORITY[oncelik_id]
    oncelik_guven = float(oncelik_probs[oncelik_id])
    kural_sebebi = oncelik_kurali(text)
    if kural_sebebi:
        oncelik, oncelik_guven = "P1", 1.0

    yapisal = yapisal_cikar(text, primary)

    result = {
        "category": primary,
        "label": C.DISPLAY_NAME[primary],
        "color": C.CATEGORY_COLOR[primary],
        "confidence": confidence,
        "probabilities": {
            k: float(probs[i]) for i, k in enumerate(C.CATEGORY_KEYS)
        },
        "low_confidence": low_confidence,
        # Operatore tek bir "insan baksin" sinyali: model ya emin degil, ya da
        # iki kategori arasinda kararsiz. Ikisi de manuel incelemeyi gerektirir.
        "manual_review": low_confidence or borderline,
        "manual_review_message": C.LOW_CONFIDENCE_MESSAGE if low_confidence else None,
        "secondary_category": None,
        "secondary_label": None,
        "secondary_confidence": None,
        "secondary_message": None,
        "margin": margin,
        # --- Ikinci boyut: intent ---
        "intent": intent,
        "intent_label": C.INTENT_DISPLAY[intent],
        "intent_confidence": float(intent_probs[intent_id]),
        # --- Ucuncu boyut: oncelik ---
        "priority": oncelik,
        "priority_label": C.PRIORITY_DISPLAY[oncelik],
        "priority_color": C.PRIORITY_COLOR[oncelik],
        "priority_confidence": oncelik_guven,
        "priority_rule": kural_sebebi,
        # --- Yonlendirme ---
        "routing_unit": C.ROUTING_UNIT[primary],
        # Yapisal alanlar siniflandirmadan BAGIMSIZ uretiliyor; biri
        # digerini beslemiyor. Kurallı katman modelden hizli oldugu icin
        # yanit suresine anlamli bir yuk bindirmiyor.
        **yapisal,
        # Modelin karara katkida bulunan kelimeleri (gradient x input).
        "evidence": kanit_cikar_guvenli(text),
    }

    # Marj kucukse model iki kategori arasinda kararsiz demektir. Taksonomide
    # gercekten ortusen bildirimler var (orn. "acil tahliye anonsu duyulmuyor"
    # hem guvenlik hem operasyon kapsaminda) -- tek cevaba zorlamak yerine
    # ikisini birden bildiriyoruz.
    if borderline:
        secondary = C.ID2LABEL[second]
        result.update(
            secondary_category=secondary,
            secondary_label=C.DISPLAY_NAME[secondary],
            secondary_confidence=float(probs[second]),
            secondary_message=C.SECONDARY_CATEGORY_MESSAGE,
        )

    # Benzerlik: modelin ic temsiliyle egitim havuzunda anlamsal olarak yakin
    # kayitlari bulur, kategori dagilimlarini raporlar (bkz. src/similarity.py).
    # similarity.py Turkce anahtarlarla doner (proje ici modul), API sozlesmesi
    # Ingilizce -- burada ceviriyoruz.
    corpus = STATE["corpus"]
    benzer = similarity.benzer_bul(text, model, tokenizer, device, corpus)
    result["similar"] = {
        "threshold": benzer["esik"],
        "total_found": benzer["toplam_bulunan"],
        "shown": benzer["gosterilen"],
        "distribution": [
            {"category": d["kategori"], "label": d["ad"], "color": d["renk"],
             "count": d["sayi"], "ratio": d["oran"]}
            for d in benzer["dagilim"]
        ],
        "examples": [
            {"text": e["metin"], "category": e["kategori"],
             "similarity": e["benzerlik"]}
            for e in benzer["ornekler"]
        ],
    }

    # Loglama: her istek DB'ye yazilir ama ETIKET OLARAK KULLANILMAZ -- bkz.
    # src/db.py modul notu. Ayni metin kisa surede tekrar gelirse (dene-yanila)
    # loglamayi atla, grafik/log tablosu tek kisinin denemesiyle sismesin.
    # Ayni olay kisa sure once bildirilmis mi? (ayni kategori + istasyon +
    # ekipman + son 15 dk). Amac: 30 kisinin ayni arizayi bildirmesi 30 ayri
    # is emri acmasin.
    tekrar = db.olasi_tekrar(primary, yapisal.get("station"),
                             yapisal.get("equipment"))
    result["possible_duplicate"] = tekrar is not None
    result["duplicate_of"] = tekrar

    if not db.son_kayit_tekrar_mi(text):
        result["log_id"] = db.logla(
            text, primary, confidence, kaynak="canli",
            istasyon=yapisal.get("station"), ekipman=yapisal.get("equipment"),
            intent=intent, oncelik=oncelik,
        )
    else:
        result["log_id"] = -1

    return result


# ---------------------------------------------------------------------------
# Uc noktalar
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["system"])
def health():
    """Servis ayakta mi, model yuklendi mi. Yuk dengeleyici/izleme icin."""
    loaded = STATE.get("model") is not None
    return {
        "status": "ok" if loaded else "loading",
        "model_loaded": loaded,
        "device": str(STATE.get("device")),
    }


@app.get("/model-info", response_model=ModelInfo, tags=["system"])
def model_info():
    """Hangi model, hangi egitim, hangi esikler. Raporlanabilirlik icin:
    bir tahminin hangi model surumunden geldigi izlenebilmeli."""
    if STATE.get("model") is None:
        raise HTTPException(503, "Model henüz yüklenmedi.")
    meta = STATE["meta"]
    return {
        "base_model": meta["base_model"],
        "lora": meta["lora"],
        "trainable_params": meta["egitilebilir_parametre"],
        "total_params": meta["toplam_parametre"],
        "best_epoch": meta["en_iyi_epoch"],
        "best_val_macro_f1": meta.get("en_iyi_val_ortalama_f1")
                              or meta.get("en_iyi_val_f1", 0.0),
        "epochs": meta["epochs"],
        "learning_rate": meta["learning_rate"],
        "batch_size": meta["batch_size"],
        "max_length": meta["max_length"],
        "seed": meta["seed"],
        "ascii_augmentation": meta.get("ascii_cogaltma", False),
        "train_records": meta.get("train_kayit", 0),
        "device": str(STATE["device"]),
        "load_seconds": STATE.get("load_seconds", 0.0),
        "confidence_threshold": C.CONFIDENCE_THRESHOLD,
        "margin_threshold": C.MARGIN_THRESHOLD,
        "num_labels": C.NUM_LABELS,
        "num_intents": C.NUM_INTENTS,
        "num_priorities": C.NUM_PRIORITIES,
        "tasks": meta.get("gorevler", {}),
    }


@app.get("/categories", response_model=list[CategoryInfo], tags=["taxonomy"])
def categories():
    """Taksonomi: arayuzun etiket/renk/kapsam gosterebilmesi icin."""
    return [
        {
            "category": k,
            "label": C.DISPLAY_NAME[k],
            "color": C.CATEGORY_COLOR[k],
            "scope": C.CATEGORIES[k]["scope"],
            "excludes": C.CATEGORIES[k]["exclude"],
        }
        for k in C.CATEGORY_KEYS
    ]


@app.get("/intents", tags=["taxonomy"])
def intents():
    """Intent taksonomisi -- arayuz rozet ve aciklama gosterebilsin diye."""
    return [
        {"intent": k, "label": v["display"], "scope": v["scope"]}
        for k, v in C.INTENTS.items()
    ]


@app.get("/priorities", tags=["taxonomy"])
def priorities():
    """Oncelik taksonomisi + P1 kural katmaninin varligi.

    `rule_based_p1` alani, onceligin her zaman modelden gelmedigini arayuze
    bildirir: belirli desenler (yangin, elektrik carpmasi, intihar...) modeli
    ezip kosulsuz P1 verir.
    """
    return {
        "priorities": [
            {"priority": k, "label": v["display"], "color": v["color"],
             "scope": v["scope"]}
            for k, v in C.PRIORITIES.items()
        ],
        "rule_based_p1": [ad for _, ad in C.PRIORITY_RULES],
    }


@app.get("/examples", response_model=list[ExampleItem], tags=["taxonomy"])
def examples(count: int = 8):
    """Arayuzdeki 'tek tikla doldur' listesi.

    Kaynak EXAMPLES_FILE (yeni_gold_deneme.jsonl): kullanicinin BASKA bir
    LLM'den bagimsiz olarak uretip getirdigi, EGITIME HIC GIRMEMIS 80
    kayit. v1'in gold.jsonl'i Taksonomi v2'ye gecince devre disi kaldigi
    icin (bkz. config.py notu) bu dosya onun yerini aliyor -- ustelik
    "egitimde hic kullanilmadi" garantisi burada DAHA GUCLU: farkli bir
    saglayicidan geldigi icin modelin kendi uretim kaliplarini ezberlemis
    olma ihtimali de yok.
    """
    if not C.EXAMPLES_FILE.exists():
        return []
    records = [json.loads(s) for s in C.EXAMPLES_FILE.open(encoding="utf-8") if s.strip()]
    rng = random.Random(C.SEED)
    # Her kategoriden en fazla bir ornek -- liste tek kategoriye yigilmasin
    by_category: dict[str, list[dict]] = {}
    for r in records:
        by_category.setdefault(r["kategori"], []).append(r)
    picked = [rng.choice(v) for v in by_category.values()]
    rng.shuffle(picked)
    return [{"text": r["metin"], "style": r["stil"]} for r in picked[:count]]


@app.post("/predict", response_model=PredictResponse, tags=["inference"])
def predict(request: PredictRequest):
    if STATE.get("model") is None:
        raise HTTPException(503, "Model henüz yüklenmedi.")

    text = " ".join(request.text.split())
    if not text:
        raise HTTPException(400, "Metin boş olamaz.")
    if len(text) > C.MAX_CHARS:
        raise HTTPException(
            400, f"Metin çok uzun ({len(text)} karakter, en fazla {C.MAX_CHARS})."
        )

    t0 = time.perf_counter()
    result = run_prediction(text)
    result["response_time_ms"] = (time.perf_counter() - t0) * 1000
    return result


@app.post("/logs/verify", response_model=VerifyResponse, tags=["logs"])
def logs_verify(req: VerifyRequest):
    """Kullanici arayuzde 'Doğru'/'Yanlış' ile tahmini onaylar.

    SADECE bu uc noktadan gecen kayitlar `dogrulandi` alani doluyor ve
    /logs/export ile disari alinabiliyor -- yani egitime aday olabiliyor.
    Onaylanmayan tahminler veritabaninda kalir ama sonsuza kadar "tahmin"
    olarak isaretli durur, asla otomatik egitime girmez (bkz. src/db.py).
    """
    if req.log_id < 0:
        raise HTTPException(400, "Geçersiz log_id (bu istek tekrar olduğu "
                            "için loglanmamıştı).")
    if not req.correct and not req.corrected_category:
        pass  # duzeltme opsiyonel; bos birakilabilir, sadece "yanlis" isaretlenir
    if req.corrected_category and req.corrected_category not in C.CATEGORY_KEYS:
        raise HTTPException(400, f"Bilinmeyen kategori: {req.corrected_category}")

    bulundu = db.dogrula(req.log_id, req.correct, req.corrected_category)
    if not bulundu:
        raise HTTPException(404, "log_id bulunamadı.")
    return {"ok": True}


@app.get("/logs/stats", response_model=LogStats, tags=["logs"])
def logs_stats():
    """Log veritabaninin ozeti: kac kayit, kaci canli, kaci onaylandi."""
    t = db.toplam_kayit()
    return {
        "total": t["toplam"] or 0,
        "live": t["canli"] or 0,
        "confirmed_correct": t["onayli_dogru"] or 0,
        "confirmed_incorrect": t["onayli_yanlis"] or 0,
    }


@app.get("/logs/export", tags=["logs"])
def logs_export():
    """Kullanici tarafindan ONAYLANMIS kayitlari JSONL olarak dondurur.

    Bu, CLAUDE.md'deki 'orta yol'un somut adimi: sadece elle dogrulanan
    kayitlar buradan alinip data/raw/amplified.jsonl'e KATILABILIR (elle,
    kullanicinin kendi inisiyatifiyle) ve preprocess+train yeniden
    calistirilabilir. Backend bunu OTOMATIK yapmaz.
    """
    from fastapi.responses import PlainTextResponse

    satirlar = db.onayli_kayitlari_disa_aktar()
    icerik = "\n".join(json.dumps(r, ensure_ascii=False) for r in satirlar)
    return PlainTextResponse(
        icerik, media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=onayli_kayitlar.jsonl"},
    )


@app.get("/stats/categories", response_model=list[CategoryCount], tags=["logs"])
def stats_categories():
    """Kategori bazinda TOPLAM kayit sayisi (gecmis havuz + canli istekler
    birlesik) -- arayuzdeki canli guncellenen grafigin veri kaynagi."""
    dagilim = {d["kategori"]: d for d in db.kategori_dagilimi()}
    toplam = sum(d["sayi"] for d in dagilim.values()) or 1
    return [
        {
            "category": k,
            "label": C.DISPLAY_NAME[k],
            "color": C.CATEGORY_COLOR[k],
            "count": dagilim.get(k, {}).get("sayi", 0),
            "live_count": dagilim.get(k, {}).get("yeni_sayi", 0),
            "ratio": dagilim.get(k, {}).get("sayi", 0) / toplam,
        }
        for k in C.CATEGORY_KEYS
    ]


@app.get("/logs/recent", response_model=list[RecentLogItem], tags=["logs"])
def logs_recent(limit: int = 50):
    """Son N bildirim, birlesik dashboard'daki olay akisi icin.

    Sensor tarafinin `/api/gecmis` alarm ozetiyle ayni listede zaman
    damgasina gore siralanabilsin diye eklendi -- rayli_ariza_tespiti ile
    tek platform birlesmesinin bir parcasi.
    """
    kayitlar = db.son_kayitlari_getir(limit)
    return [
        {
            "id": r["id"],
            "text": r["metin"],
            "category": r["kategori"],
            "label": C.DISPLAY_NAME.get(r["kategori"], r["kategori"]),
            "color": C.CATEGORY_COLOR.get(r["kategori"], "#888"),
            "confidence": r["guven"],
            "source": r["kaynak"],
            "verified": bool(r["dogrulandi"]) if r["dogrulandi"] is not None else None,
            "station": r["istasyon"],
            "equipment": r["ekipman"],
            "intent": r["intent"],
            "priority": r["oncelik"],
            "timestamp": r["zaman"],
        }
        for r in kayitlar
    ]


def main() -> None:
    import uvicorn
    uvicorn.run("backend.main:app", host=C.API_HOST, port=C.API_PORT, reload=False)


if __name__ == "__main__":
    main()
