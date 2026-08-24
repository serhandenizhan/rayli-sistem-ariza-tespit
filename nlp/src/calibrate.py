"""
Adim 4c — Guven esigi kalibrasyonu: k-fold out-of-fold tahminlerle.

SORUN. Esigi hangi veri uzerinden secelim?
  - test.csv  -> esigi test'e bakarak secmek test setini karar surecine sokar,
                 raporlanan skor iyimser olur.
  - gold      -> ayni sorun, ustelik gold nihai bagimsiz olcut.
  - val.csv   -> epoch secimi icin kullanildi, model orada fazla emin
                 (olculdu: yanlis tahminlerde ort. guven val 0.892 / test 0.758).
                 Ayrica sadece 160 kayit ve 9 hata var -- bu kadar az hatayla
                 esik taramasi yapmak gurultuyu kalibrasyon sanmaktir.

Train'den ayri bir calibration.csv ayirmak da cozmuyor: 160 kayit ayirsak yine
~14 hata olur (ayni gurultu) ve ustelik egitim verisi kuculur.

COZUM. k-fold out-of-fold (OOF) tahmin:
  train 5 parcaya bolunur; her parca icin o parcayi GORMEMIS bir model egitilir
  ve sadece o parca uzerinde tahmin alinir. Sonuc: 1280 kaydin tamami icin
  "modelin hic gormedigi" tahmin. Veri kaybi yok (nihai model yine tum veriyle
  egitiliyor), hata sayisi ~10 kat artiyor, ve tahminler gercekten temiz.

Fold modelleri nihai modelle AYNI TARIFLE egitilir (ayni LR, ayni cogaltma,
sabit epoch = nihai modelin sectigi epoch). Fold icinde ayri bir val ile epoch
secmek, kacmaya calistigimiz secim yanliligini geri getirirdi.

Bilinen yaklasiklik: fold modelleri verinin 4/5'iyle egitildigi icin nihai
modelden bir tik zayif ve bir tik daha az emin olur. Yani buradan cikan esik
biraz TEMKINLI tarafta kalir -- kabul edilebilir, cunku alternatifi olculemeyen
bir esik.

Kullanim:
    python -m src.calibrate
    python -m src.calibrate --folds 5 --epochs 6
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import torch
from sklearn.model_selection import StratifiedKFold
from torch.utils.data import DataLoader

from src import config as C
from src.train import (
    BildirimVeriseti,
    ascii_cogalt,
    cihaz_sec,
    csv_oku,
    model_kur,
    tohum_ek,
)


# ---------------------------------------------------------------------------
# Tek bir fold egitimi
# ---------------------------------------------------------------------------

def fold_egit(train_satir, epochs, cihaz, tokenizer):
    """Verilen kayitlarla sifirdan bir model egitir, egitilmis modeli doner.

    Nihai modelle ayni tarif: ayni LR, ayni scheduler, ayni cogaltma, ayni
    LoRA ayarlari. Tek fark egitim verisinin 4/5 olmasi ve epoch sayisinin
    sabit olmasi (fold icinde epoch secimi yapilmiyor -- bkz. modul notu).
    """
    if C.AUGMENT_ASCII_FOLD:
        train_satir = ascii_cogalt(train_satir)

    ds = BildirimVeriseti(train_satir, tokenizer, C.MAX_LENGTH)
    dl = DataLoader(ds, batch_size=C.BATCH_SIZE, shuffle=True)

    model, _ = model_kur(C.USE_LORA)
    model.to(cihaz)

    optim = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=C.LEARNING_RATE,
        weight_decay=C.WEIGHT_DECAY,
    )
    plan = torch.optim.lr_scheduler.OneCycleLR(
        optim,
        max_lr=C.LEARNING_RATE,
        total_steps=len(dl) * epochs,
        pct_start=C.WARMUP_RATIO,
        anneal_strategy="linear",
    )

    model.train()
    for _ in range(epochs):
        for parti in dl:
            parti = {k: v.to(cihaz) for k, v in parti.items()}
            cikti = model(**parti)
            cikti.loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0
            )
            optim.step()
            plan.step()
            optim.zero_grad()
    return model


def fold_tahmin(model, satirlar, cihaz, tokenizer):
    ds = BildirimVeriseti(satirlar, tokenizer, C.MAX_LENGTH)
    dl = DataLoader(ds, batch_size=C.BATCH_SIZE)
    olasiliklar = []
    model.eval()
    with torch.no_grad():
        for parti in dl:
            girdi = {k: v.to(cihaz) for k, v in parti.items() if k != "labels"}
            olasi = torch.softmax(model(**girdi).logits, dim=-1).cpu()
            olasiliklar.extend(olasi.tolist())
    return np.array(olasiliklar)


# ---------------------------------------------------------------------------
# Kalibrasyon analizi
# ---------------------------------------------------------------------------

def esik_taramasi(guven, dogru, n_hata: int) -> list[dict]:
    print(f"\nESIK TARAMASI — manual_review'e gidecek kayitlar")
    print(f"{'esik':>6} {'manuel':>8} {'trafik':>8} {'yakalanan':>14} "
          f"{'bosuna':>8} {'precision':>10} {'recall':>8}")
    satirlar = []
    for esik in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95):
        altinda = guven < esik
        yakalanan = int((altinda & ~dogru).sum())
        bosuna = int((altinda & dogru).sum())
        prec = yakalanan / altinda.sum() if altinda.sum() else 0.0
        rec = yakalanan / n_hata if n_hata else 0.0
        satirlar.append({"esik": esik, "manuel": int(altinda.sum()),
                         "trafik": float(altinda.mean()), "yakalanan": yakalanan,
                         "bosuna": bosuna, "precision": prec, "recall": rec})
        isaret = "  <-- aktif" if abs(esik - C.CONFIDENCE_THRESHOLD) < 1e-9 else ""
        print(f"{esik:>6.2f} {altinda.sum():>8} {100 * altinda.mean():>7.1f}% "
              f"{yakalanan:>8}/{n_hata:<5} {bosuna:>8} {prec:>10.3f} "
              f"{rec:>8.3f}{isaret}")
    return satirlar


def reliability(guven, dogru) -> tuple[list[dict], float]:
    print(f"\nRELIABILITY DIAGRAM — guven kovasi vs gercek dogruluk")
    print(f"{'kova':>13} {'kayit':>7} {'ort. guven':>11} {'dogruluk':>10} "
          f"{'sapma':>8}")
    kovalar = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9),
               (0.9, 0.95), (0.95, 1.01)]
    ece, toplam, cikti = 0.0, len(guven), []
    for lo, hi in kovalar:
        maske = (guven >= lo) & (guven < hi)
        if not maske.any():
            print(f"  [{lo:.2f}-{hi:.2f})       0           -          -")
            continue
        og, gd = float(guven[maske].mean()), float(dogru[maske].mean())
        sapma = gd - og
        ece += maske.sum() / toplam * abs(sapma)
        cikti.append({"bant": f"{lo:.2f}-{hi:.2f}", "n": int(maske.sum()),
                      "ort_guven": og, "dogruluk": gd, "sapma": sapma})
        print(f"  [{lo:.2f}-{hi:.2f}) {maske.sum():>7} {og:>11.3f} {gd:>10.3f} "
              f"{sapma:>+8.3f} {'#' * int(round(gd * 20))}")
    print(f"\n  ECE (Expected Calibration Error) = {ece:.4f}")
    print("  (0'a yakin = guven skoru gercek dogrulukla ortusuyor)")
    return cikti, float(ece)


def marj_taramasi(olasi, gercek, tahmin) -> list[dict]:
    """Ikincil kategori esigi (MARGIN_THRESHOLD) icin ayni tarama."""
    sirali = np.sort(olasi, axis=1)
    marj = sirali[:, -1] - sirali[:, -2]
    top2 = np.argsort(olasi, axis=1)[:, -2:]
    dogru = tahmin == gercek
    top2_dogru = np.array([g in t2 for g, t2 in zip(gercek, top2)])
    n_hata = int((~dogru).sum())

    print(f"\nMARJ TARAMASI — ikincil kategori dondurulecek kayitlar")
    print(f"{'marj':>6} {'cift':>7} {'trafik':>8} {'kurtarilan':>14} {'bosuna':>8} "
          f"{'oran':>7}")
    satirlar = []
    for m in (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70):
        isaretli = marj < m
        kurtarilan = int((isaretli & ~dogru & top2_dogru).sum())
        bosuna = int((isaretli & dogru).sum())
        oran = kurtarilan / bosuna if bosuna else float("inf")
        satirlar.append({"marj": m, "cift": int(isaretli.sum()),
                         "kurtarilan": kurtarilan, "bosuna": bosuna,
                         "oran": oran if bosuna else None})
        isaret = "  <-- aktif" if abs(m - C.MARGIN_THRESHOLD) < 1e-9 else ""
        print(f"{m:>6.2f} {isaretli.sum():>7} {100 * isaretli.mean():>7.1f}% "
              f"{kurtarilan:>8}/{n_hata:<5} {bosuna:>8} {oran:>7.2f}{isaret}")
    return satirlar


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 4c -- k-fold OOF kalibrasyon")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--epochs", type=int, default=None,
                    help="fold basina epoch; varsayilan: nihai modelin sectigi")
    ap.add_argument("--device", choices=["mps", "cpu"])
    args = ap.parse_args()

    tohum_ek()
    cihaz = cihaz_sec(args.device)

    # Nihai modelin sectigi epoch'u kullan: fold modelleri ayni tarifle egitilsin
    epochs = args.epochs
    ozet_yolu = C.MODEL_DIR / "egitim_ozeti.json"
    if epochs is None:
        if not ozet_yolu.exists():
            raise SystemExit("HATA: once 'python -m src.train' calistir.")
        epochs = json.loads(ozet_yolu.read_text(encoding="utf-8"))["en_iyi_epoch"]

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(C.BASE_MODEL)

    satirlar = csv_oku(C.TRAIN_FILE)
    etiketler = np.array([int(r["label"]) for r in satirlar])
    print(f"k-fold OOF kalibrasyon | {len(satirlar)} train kaydi | "
          f"{args.folds} fold | fold basina {epochs} epoch | cihaz {cihaz}")
    print(f"(fold modelleri nihai modelle ayni tarif: LR={C.LEARNING_RATE}, "
          f"ASCII cogaltma={C.AUGMENT_ASCII_FOLD})")

    oof = np.zeros((len(satirlar), C.NUM_LABELS))
    skf = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=C.SEED)

    t0 = time.time()
    for i, (tr_idx, va_idx) in enumerate(skf.split(satirlar, etiketler), 1):
        tf = time.time()
        model = fold_egit([satirlar[j] for j in tr_idx], epochs, cihaz, tokenizer)
        oof[va_idx] = fold_tahmin(model, [satirlar[j] for j in va_idx],
                                  cihaz, tokenizer)
        del model
        if cihaz.type == "mps":
            torch.mps.empty_cache()
        dogru_fold = (oof[va_idx].argmax(1) == etiketler[va_idx]).mean()
        print(f"  fold {i}/{args.folds}: egitim {len(tr_idx)}, tahmin "
              f"{len(va_idx)} | fold dogrulugu {dogru_fold:.4f} "
              f"| {time.time() - tf:.0f} sn")

    print(f"\ntoplam {time.time() - t0:.0f} sn")

    tahmin = oof.argmax(axis=1)
    guven = oof.max(axis=1)
    dogru = tahmin == etiketler
    n_hata = int((~dogru).sum())

    print(f"\n{'=' * 78}")
    print(f"OUT-OF-FOLD SONUC — {len(satirlar)} kayit, {n_hata} hata, "
          f"dogruluk {dogru.mean():.4f}")
    print(f"{'=' * 78}")
    print(f"  dogru tahminlerde ortalama guven  {guven[dogru].mean():.4f}")
    print(f"  YANLIS tahminlerde ortalama guven {guven[~dogru].mean():.4f}")
    print(f"\n  (kiyas — validation seti, n=160: 9 hata. OOF {n_hata} hata ile "
          f"{n_hata / 9:.0f} kat daha saglam bir taban.)")

    esikler = esik_taramasi(guven, dogru, n_hata)
    kovalar, ece = reliability(guven, dogru)
    marjlar = marj_taramasi(oof, etiketler, tahmin)

    cikti = {
        "yontem": f"{args.folds}-fold out-of-fold",
        "n": len(satirlar), "hata": n_hata,
        "oof_dogruluk": float(dogru.mean()),
        "fold_epochs": epochs,
        "ort_guven_dogru": float(guven[dogru].mean()),
        "ort_guven_yanlis": float(guven[~dogru].mean()),
        "esik_taramasi": esikler,
        "marj_taramasi": marjlar,
        "reliability": kovalar,
        "ece": ece,
        "aktif_confidence_threshold": C.CONFIDENCE_THRESHOLD,
        "aktif_margin_threshold": C.MARGIN_THRESHOLD,
    }
    yol = C.MODEL_DIR / "kalibrasyon.json"
    yol.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {yol}")


if __name__ == "__main__":
    main()
