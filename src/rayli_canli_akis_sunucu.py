"""
Canlı akış (live streaming) simülasyon sunucusu.

Ne yapar?
---------
1. Akış kaynağından (varsayılan: `data/rayli_sistem_test_akis.csv` ETİKETSİZ test verisi)
   zaman damgasına göre "tick"ler halinde veri okur ve gerçekçi bir gecikmeyle yayınlar.
   Kaynak `--kaynak kafka` ile Kafka topic'i de olabilir (bkz. rayli_kafka.py).
2. Her dingil için son WINDOW (=10) örneği kayan pencerede tutar; pencere dolduğunda
   çok görevli CNN+LSTM modeliyle ARIZA TİPİNİ ve ARIZA ŞİDDETİNİ tahmin eder.
3. HİSTEREZİS: bir dingilin "yerleşik" (kararlı) durumu, aynı sınıf üst üste N tick boyunca
   tahmin edilmedikçe değişmez. Tek tick'lik sıçramalar alarm üretmez.
4. Tahmin üretildikten SONRA, ayrı tutulan cevap anahtarıyla eşleştirip anlık doğruluk /
   karmaşıklık matrisi / sınıf bazlı metrikleri hesaplar. Model bu etiketi asla görmez.
5. Sonucu Server-Sent Events (SSE) ile web arayüzüne (Next.js dashboard) yayınlar.

Çalıştırma (src/ klasöründen):
    python rayli_canli_akis_sunucu.py                 # http://127.0.0.1:8000
    python rayli_canli_akis_sunucu.py --hiz 10        # 10x hızlı simülasyon
    python rayli_canli_akis_sunucu.py --kor-mod       # cevap anahtarını arayüze HİÇ gönderme
    python rayli_canli_akis_sunucu.py --histerezis 3  # N ardışık tick kuralı
    python rayli_canli_akis_sunucu.py --kaynak kafka  # veriyi Kafka'dan oku
    python rayli_canli_akis_sunucu.py --konsol        # arayüz olmadan konsola yaz

API:
    GET  /api/meta      -> sınıflar, dingil listesi, toplam tick, eğitim özeti, metro ağı
    GET  /api/ag        -> harita için metro ağı (hatlar, istasyonlar, ray kusurları)
    GET  /api/durum     -> anlık durum (sonradan bağlanan istemci için)
    GET  /api/akis      -> SSE akışı (her tick'te bir olay)
    GET  /api/testler   -> pytest sonuç özeti (results/test_ozeti.json)
    POST /api/kontrol   -> {"action": "play"|"pause"|"reset"|"speed"|"kor_mod"|"histerezis", "value": ...}
"""

import argparse
import asyncio
import json
import os
from collections import deque

import numpy as np
import pandas as pd
import torch

from rayli_model import (FEATURE_COLS, GROUP_COLS, SEVERITY_CLASSES,
                         load_model_checkpoint, rebuild_scaler_and_encoder)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MODEL_DIR = os.path.join(BASE_DIR, "..", "model")
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

STREAM_CSV = os.path.join(DATA_DIR, "rayli_sistem_test_akis.csv")
KEY_CSV = os.path.join(DATA_DIR, "rayli_sistem_test_cevap_anahtari.csv")
MODEL_PATH = os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt")
AG_JSON = os.path.join(DATA_DIR, "istanbul_metro_agi.json")
KUSUR_JSON = os.path.join(DATA_DIR, "ray_kusur_noktalari.json")

TICK_SECONDS = 2.0          # veri örnekleme aralığı: 2 saniye (1x hızda gerçek zamanlı)
MAX_EVENTS = 200            # bellekte tutulan son alarm/olay sayısı
VARSAYILAN_HISTEREZIS = 3   # bir sınıfın "yerleşik" sayılması için gereken ardışık tick


def _axle_key(row):
    return f"{row['train_id']}/{row['wagon_id']}-{row['axle_id']}"


class AkisSimulatoru:
    """Etiketsiz akış verisini tick tick yayınlayan, her tick'te model tahmini üretip
    cevap anahtarıyla skorlayan simülasyon motoru.

    Durum (state) tek bir örnekte tutulur; SSE ile bağlanan tüm istemciler aynı akışı görür.
    """

    def __init__(self, kor_mod=False, baslangic_hizi=5.0, histerezis=VARSAYILAN_HISTEREZIS,
                 kaynak="csv", kafka_sunucu=None, kafka_topic=None):
        if not os.path.exists(MODEL_PATH):
            raise SystemExit(f"Model bulunamadı: {MODEL_PATH}\nÖnce 'python rayli_dl_egitim.py' çalıştırın.")

        self.model, self.checkpoint = load_model_checkpoint(MODEL_PATH)
        self.scaler, self.encoder = rebuild_scaler_and_encoder(self.checkpoint)
        self.classes = list(self.checkpoint["classes"])
        self.sev_classes = list(self.checkpoint.get("severity_classes", SEVERITY_CLASSES))
        self.window = int(self.checkpoint["window"])
        self.kor_mod = kor_mod
        self.histerezis = max(1, int(histerezis))
        self.kaynak = kaynak

        df = self._akis_verisi_oku(kaynak, kafka_sunucu, kafka_topic)
        assert "fault_type" not in df.columns, "Akış verisinde etiket kolonu bulunmamalı!"
        df["axle_key"] = df.apply(_axle_key, axis=1)
        df = df.sort_values(["timestamp", "axle_key"]).reset_index(drop=True)
        self.ticks = [g for _, g in df.groupby("timestamp", sort=True)]
        self.timestamps = [str(g["timestamp"].iloc[0]) for g in self.ticks]
        self.axles = sorted(df["axle_key"].unique().tolist())
        self.axle_hat = {r["axle_key"]: r.get("line_id") for _, r in
                         df.drop_duplicates("axle_key").iterrows()}

        # --- Cevap anahtarı: SADECE sunucu tarafında, tahminden SONRA skorlamak için ---
        key_df = pd.read_csv(KEY_CSV)
        self.answer_key = dict(zip(key_df["sample_id"], key_df["fault_type"]))
        self.severity_key = dict(zip(key_df["sample_id"], key_df["fault_severity"]))

        self.hiz = baslangic_hizi
        self.oynatiliyor = True
        self.reset()

    def _akis_verisi_oku(self, kaynak, kafka_sunucu, kafka_topic):
        """Akış verisini seçilen kaynaktan okur (csv | kafka)."""
        if kaynak == "kafka":
            import rayli_kafka
            print(f"Kafka'dan okunuyor: {kafka_sunucu} / {kafka_topic}")
            return rayli_kafka.topic_dataframe_oku(kafka_sunucu, kafka_topic)
        if not os.path.exists(STREAM_CSV):
            raise SystemExit(f"Akış verisi bulunamadı: {STREAM_CSV}\n"
                             "Önce 'python rayli_etiketsiz_uret.py' çalıştırın.")
        return pd.read_csv(STREAM_CSV, parse_dates=["timestamp"])

    # ------------------------------------------------------------------ durum
    def reset(self):
        self.tick_index = 0
        self.buffers = {a: deque(maxlen=self.window) for a in self.axles}
        self.yerlesik_sinif = {a: None for a in self.axles}      # histerezis sonrası kararlı sınıf
        self.aday_sinif = {a: None for a in self.axles}          # üst üste sayılan aday
        self.aday_sayac = {a: 0 for a in self.axles}
        self.dogru = 0
        self.degerlendirilen = 0
        self.sev_dogru = 0
        n = len(self.classes)
        self.confusion = np.zeros((n, n), dtype=int)      # satır=gerçek, sütun=tahmin
        self.olaylar = deque(maxlen=MAX_EVENTS)
        self.gecmis = deque(maxlen=120)                   # doğruluk trendi için
        self.son_payload = None

    # -------------------------------------------------------------- tick işle
    def bir_tick_isle(self):
        """Sıradaki zaman damgasındaki tüm dingil satırlarını işler, payload döndürür.
        Akış bittiyse None döner."""
        if self.tick_index >= len(self.ticks):
            return None

        g = self.ticks[self.tick_index]
        ts = self.timestamps[self.tick_index]

        hazir_axles, batch = [], []
        satirlar = {}

        for _, row in g.iterrows():
            key = row["axle_key"]
            feats = row[FEATURE_COLS].values.astype(np.float64)
            self.buffers[key].append(feats)
            satirlar[key] = row
            if len(self.buffers[key]) == self.window:
                hazir_axles.append(key)
                batch.append(np.stack(self.buffers[key]))

        tahminler = {}
        if batch:
            X = np.stack(batch)                                   # (n_axle, window, n_feat)
            flat = self.scaler.transform(X.reshape(-1, X.shape[-1]))
            X = flat.reshape(X.shape).astype(np.float32)
            with torch.no_grad():
                logit_tip, logit_sev = self.model(torch.from_numpy(X))
                probs = torch.softmax(logit_tip, dim=1).numpy()
                sev_probs = torch.softmax(logit_sev, dim=1).numpy()
            for i, key in enumerate(hazir_axles):
                p, sp = probs[i], sev_probs[i]
                idx, sidx = int(p.argmax()), int(sp.argmax())
                tahminler[key] = {
                    "pred": self.classes[idx], "conf": float(p[idx]),
                    "probs": [round(float(v), 4) for v in p],
                    "severity": self.sev_classes[sidx], "sev_conf": float(sp[sidx]),
                    "sev_probs": [round(float(v), 4) for v in sp],
                }

        yeni_olaylar = []
        axle_payload = []
        for key in self.axles:
            row = satirlar.get(key)
            if row is None:
                continue
            sample_id = int(row["sample_id"])
            t = tahminler.get(key)
            item = {
                "axle": key,
                "line_id": row.get("line_id"),
                "train_id": row["train_id"], "wagon_id": row["wagon_id"], "axle_id": row["axle_id"],
                "hazir": t is not None,
                "doluluk": len(self.buffers[key]),
                "sensors": {c: round(float(row[c]), 4) for c in FEATURE_COLS},
                "konum": {
                    "lat": float(row["lat"]) if "lat" in row and pd.notna(row["lat"]) else None,
                    "lon": float(row["lon"]) if "lon" in row and pd.notna(row["lon"]) else None,
                    "km": float(row["track_km"]),
                    "istasyon": row.get("next_station"),
                    "durakta": bool(row.get("at_station", False)),
                },
            }

            if t is not None:
                item.update(pred=t["pred"], conf=round(t["conf"], 4), probs=t["probs"],
                            severity=t["severity"], sev_conf=round(t["sev_conf"], 4),
                            sev_probs=t["sev_probs"])

                # --- HİSTEREZİS: aynı sınıf N ardışık tick gelmeden yerleşik durum değişmez ---
                if t["pred"] == self.aday_sinif[key]:
                    self.aday_sayac[key] += 1
                else:
                    self.aday_sinif[key] = t["pred"]
                    self.aday_sayac[key] = 1

                onceki_yerlesik = self.yerlesik_sinif[key]
                degisti = False
                if (self.aday_sayac[key] >= self.histerezis and t["pred"] != onceki_yerlesik):
                    self.yerlesik_sinif[key] = t["pred"]
                    degisti = True
                item["yerlesik"] = self.yerlesik_sinif[key]
                item["kararli"] = self.aday_sayac[key] >= self.histerezis

                # --- DOĞRULAMA: tahmin üretildikten SONRA cevap anahtarıyla eşleştirme ---
                gercek = self.answer_key.get(sample_id)
                if gercek is not None:
                    self.degerlendirilen += 1
                    dogru_mu = (gercek == t["pred"])
                    self.dogru += int(dogru_mu)
                    self.confusion[self.classes.index(gercek), self.classes.index(t["pred"])] += 1
                    g_sev = self.severity_key.get(sample_id)
                    self.sev_dogru += int(g_sev == t["severity"])
                    if not self.kor_mod:
                        item["gercek"] = gercek
                        item["gercek_severity"] = g_sev
                        item["dogru_mu"] = bool(dogru_mu)

                # --- Alarm/olay günlüğü: yalnızca YERLEŞİK sınıf değişimlerinde ---
                # (akış başındaki "ilk kez normale yerleşti" durumu olay sayılmaz)
                ilk_yerlesme_normal = onceki_yerlesik is None and t["pred"] == "normal"
                if degisti and not ilk_yerlesme_normal:
                    olay = {
                        "ts": ts, "axle": key, "line_id": row.get("line_id"),
                        "onceki": onceki_yerlesik, "yeni": t["pred"],
                        "conf": round(t["conf"], 3), "severity": t["severity"],
                        "istasyon": row.get("next_station"),
                        "tip": "alarm" if t["pred"] != "normal" else "temizlendi",
                    }
                    if not self.kor_mod and gercek is not None:
                        olay["gercek"] = gercek
                    yeni_olaylar.append(olay)
                    self.olaylar.appendleft(olay)

            axle_payload.append(item)

        acc = (self.dogru / self.degerlendirilen) if self.degerlendirilen else None
        self.gecmis.append({"tick": self.tick_index, "acc": acc})

        payload = {
            "tick": self.tick_index,
            "toplam_tick": len(self.ticks),
            "timestamp": ts,
            "hiz": self.hiz,
            "oynatiliyor": self.oynatiliyor,
            "kor_mod": self.kor_mod,
            "histerezis": self.histerezis,
            "bitti": self.tick_index + 1 >= len(self.ticks),
            "axles": axle_payload,
            "yeni_olaylar": yeni_olaylar,
            "sayaclar": self._sinif_sayaclari(axle_payload),
            "metrikler": self._metrikler(),
        }
        self.tick_index += 1
        self.son_payload = payload
        return payload

    def _sinif_sayaclari(self, axle_payload):
        c = {k: 0 for k in self.classes}
        for a in axle_payload:
            if a.get("pred"):
                c[a["pred"]] += 1
        return c

    def _metrikler(self):
        """Canlı doğrulama metrikleri (cevap anahtarına karşı, çevrimiçi hesaplanır)."""
        if self.kor_mod or self.degerlendirilen == 0:
            return {"kor_mod": self.kor_mod, "degerlendirilen": self.degerlendirilen}

        cm = self.confusion
        per_class = {}
        f1s = []
        for i, c in enumerate(self.classes):
            tp = int(cm[i, i]); fn = int(cm[i].sum() - tp); fp = int(cm[:, i].sum() - tp)
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            rec = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
            per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4),
                            "f1": round(f1, 4), "support": int(cm[i].sum())}
            if cm[i].sum() > 0:
                f1s.append(f1)
        return {
            "kor_mod": False,
            "degerlendirilen": self.degerlendirilen,
            "dogru": self.dogru,
            "accuracy": round(self.dogru / self.degerlendirilen, 4),
            "severity_accuracy": round(self.sev_dogru / self.degerlendirilen, 4),
            "macro_f1": round(float(np.mean(f1s)), 4) if f1s else 0.0,
            "confusion": cm.tolist(),
            "per_class": per_class,
            "trend": list(self.gecmis),
        }

    # ------------------------------------------------------------------- meta
    def ag_verisi(self):
        """Harita için metro ağı + ray kusuru noktaları."""
        ag = {}
        if os.path.exists(AG_JSON):
            with open(AG_JSON, encoding="utf-8") as f:
                ag = json.load(f)
        kusurlar = []
        if os.path.exists(KUSUR_JSON):
            with open(KUSUR_JSON, encoding="utf-8") as f:
                kusurlar = json.load(f)
        # Yalnızca tren işletilen hatları gönder (harita bunları vurgular), diğerleri arka plan
        return {
            "hatlar": ag.get("hatlar", {}),
            "simulasyon_hatlari": sorted({h for h in self.axle_hat.values() if h}),
            "ray_kusurlari": kusurlar,
            "kaynak": ag.get("kaynak"),
        }

    def meta(self):
        egitim = None
        ozet_path = os.path.join(RESULTS_DIR, "egitim_ozeti.json")
        if os.path.exists(ozet_path):
            with open(ozet_path) as f:
                egitim = json.load(f)
        return {
            "classes": self.classes,
            "severity_classes": self.sev_classes,
            "axles": self.axles,
            "axle_hat": self.axle_hat,
            "feature_cols": FEATURE_COLS,
            "group_cols": GROUP_COLS,
            "window": self.window,
            "tick_seconds": TICK_SECONDS,
            "toplam_tick": len(self.ticks),
            "kor_mod": self.kor_mod,
            "histerezis": self.histerezis,
            "kaynak": self.kaynak,
            "baslangic": self.timestamps[0],
            "bitis": self.timestamps[-1],
            "egitim": egitim,
        }


# ====================================================================== FastAPI
def create_app(sim: AkisSimulatoru):
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="Raylı Sistem Canlı Akış API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    aboneler: "set[asyncio.Queue]" = set()

    async def dongu():
        """Arka plan görevi: hız çarpanına göre tick üretip abonelere yayınlar."""
        while True:
            if not sim.oynatiliyor or sim.tick_index >= len(sim.ticks):
                await asyncio.sleep(0.2)
                continue
            payload = await asyncio.to_thread(sim.bir_tick_isle)
            if payload is None:
                continue
            # Kuyruğa her zaman yaz — akış sonlu olduğu için paket düşürmek (tick'in sona
            # ulaşmaması) istenmeyen bir davranış olurdu.
            for q in list(aboneler):
                q.put_nowait(payload)
            await asyncio.sleep(TICK_SECONDS / max(sim.hiz, 0.1))

    @app.on_event("startup")
    async def _basla():
        app.state.task = asyncio.create_task(dongu())

    @app.get("/api/meta")
    async def meta():
        return sim.meta()

    @app.get("/api/ag")
    async def ag():
        return sim.ag_verisi()

    @app.get("/api/durum")
    async def durum():
        return sim.son_payload or {"tick": 0, "toplam_tick": len(sim.ticks), "axles": [],
                                   "metrikler": sim._metrikler(), "olaylar": []}

    @app.get("/api/olaylar")
    async def olaylar():
        return {"olaylar": list(sim.olaylar)}

    @app.get("/api/testler")
    async def testler():
        """pytest sonuç özeti (results/test_ozeti.json) — arayüzdeki test panelini besler."""
        yol = os.path.join(RESULTS_DIR, "test_ozeti.json")
        if not os.path.exists(yol):
            return {"var": False, "mesaj": "Test özeti yok. './testleri_calistir.sh' çalıştırın."}
        with open(yol, encoding="utf-8") as f:
            return {"var": True, **json.load(f)}

    @app.post("/api/kontrol")
    async def kontrol(request: Request):
        body = await request.json()
        action = body.get("action")
        if action == "play":
            sim.oynatiliyor = True
        elif action == "pause":
            sim.oynatiliyor = False
        elif action == "reset":
            sim.reset()
            sim.oynatiliyor = True   # "Baştan" her zaman oynatarak başlar
        elif action == "speed":
            sim.hiz = float(body.get("value", 1))
        elif action == "kor_mod":
            sim.kor_mod = bool(body.get("value", False))
        elif action == "histerezis":
            sim.histerezis = max(1, int(body.get("value", VARSAYILAN_HISTEREZIS)))
        return {"oynatiliyor": sim.oynatiliyor, "hiz": sim.hiz, "tick": sim.tick_index,
                "kor_mod": sim.kor_mod, "histerezis": sim.histerezis}

    @app.get("/api/akis")
    async def akis(request: Request):
        q: asyncio.Queue = asyncio.Queue()
        aboneler.add(q)

        async def gen():
            try:
                if sim.son_payload:      # sonradan bağlanan istemciye anlık durumu ver
                    yield f"data: {json.dumps(sim.son_payload, ensure_ascii=False)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                aboneler.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def konsol_modu(sim: AkisSimulatoru):
    """Arayüz olmadan, konsola satır satır akış (hızlı doğrulama için)."""
    import time
    while True:
        p = sim.bir_tick_isle()
        if p is None:
            break
        m = p["metrikler"]
        acc = m.get("accuracy")
        arizali = [a for a in p["axles"] if a.get("yerlesik") and a["yerlesik"] != "normal"]
        ozet = ", ".join("{}:{}({})".format(a["axle"], a["yerlesik"], a.get("severity", "-"))
                         for a in arizali[:3])
        print(f"[{p['timestamp']}] tick {p['tick']+1}/{p['toplam_tick']} "
              f"| arizali dingil: {len(arizali):2d} "
              f"| canli acc: {acc if acc is not None else '-'} "
              f"| {ozet}")
        time.sleep(TICK_SECONDS / max(sim.hiz, 0.1))
    m = sim._metrikler()
    print("\n=== Akış bitti ===")
    print(f"Değerlendirilen sekans: {m['degerlendirilen']} | tip accuracy: {m['accuracy']} "
          f"| şiddet accuracy: {m['severity_accuracy']} | macro F1: {m['macro_f1']}")


def main():
    ap = argparse.ArgumentParser(description="Raylı sistem canlı akış simülasyon sunucusu")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--hiz", type=float, default=5.0, help="Simülasyon hız çarpanı (1 = gerçek zamanlı)")
    ap.add_argument("--kor-mod", action="store_true",
                    help="Cevap anahtarını arayüze hiç gönderme (tam kör demo)")
    ap.add_argument("--histerezis", type=int, default=VARSAYILAN_HISTEREZIS,
                    help="Yerleşik sınıf değişimi için gereken ardışık tick sayısı")
    ap.add_argument("--kaynak", choices=["csv", "kafka"], default="csv", help="Akış veri kaynağı")
    ap.add_argument("--kafka-sunucu", default="localhost:9092")
    ap.add_argument("--kafka-topic", default="rayli-sensor")
    ap.add_argument("--konsol", action="store_true", help="Web sunucusu yerine konsola yaz")
    args = ap.parse_args()

    sim = AkisSimulatoru(kor_mod=args.kor_mod, baslangic_hizi=args.hiz, histerezis=args.histerezis,
                         kaynak=args.kaynak, kafka_sunucu=args.kafka_sunucu,
                         kafka_topic=args.kafka_topic)
    print(f"Model yüklendi   : {MODEL_PATH}")
    print(f"Akış kaynağı     : {args.kaynak} ({len(sim.ticks)} tick x {len(sim.axles)} dingil)")
    print(f"Histerezis       : {sim.histerezis} ardışık tick")
    print(f"Cevap anahtarı   : {'KULLANILMIYOR (kör mod)' if args.kor_mod else KEY_CSV}")

    if args.konsol:
        konsol_modu(sim)
        return

    import uvicorn
    print(f"API hazır        : http://{args.host}:{args.port}/api/meta")
    uvicorn.run(create_app(sim), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
