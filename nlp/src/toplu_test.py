"""
Elle hazirlanmis / bagimsiz kaynaktan gelen test kumeleri icin toplu tahmin.

Egitim/gold gibi resmi bir set degil -- kullanicinin (Gemini vb.) uretip
elle etiketledigi cumleleri MEVCUT modelle hizlica tarayip nerede zayif
oldugunu gormek icin.

jsonl formati (kategori sart, intent/oncelik opsiyonel -- hangisi varsa o
olculur):
    {"metin": "...", "kategori": "mekanik_istasyon", "intent": "fault_report", "oncelik": "P3"}

Kullanim:
    python -m src.toplu_test data/raw/manuel_test_v1.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

from src import config as C
from src.evaluate import model_yukle, tum_gorevleri_tahmin_et
from src.train import cihaz_sec

# gorev adi -> (bu gorevi tasiyabilecek jsonl alan adlari, ID2ad esleme,
# goruntu adi eslemesi). Birden fazla alan adi kabul edilir cunku kullanicilar
# Turkce (oncelik) veya Ingilizce (priority/category) yazabiliyor -- API
# sozlesmesi zaten Ingilizce (bkz. backend/main.py), test dosyalarinda da
# gorulmesi dogal.
GOREVLER = {
    "kategori": (("kategori", "category"), C.ID2LABEL, C.DISPLAY_NAME),
    "intent": (("intent",), C.ID2INTENT, C.INTENT_DISPLAY),
    "oncelik": (("oncelik", "priority"), C.ID2PRIORITY, C.PRIORITY_DISPLAY),
}


def _alan_bul(satir: dict, adaylar: tuple[str, ...]) -> str | None:
    return next((a for a in adaylar if a in satir), None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dosya")
    ap.add_argument("--hatalari-goster", action="store_true",
                    help="her gorev icin en fazla 20 hatayi tek tek listele")
    args = ap.parse_args()

    satirlar = []
    with open(args.dosya, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if satir:
                satirlar.append(json.loads(satir))

    mevcut_gorevler = {
        gorev: alan for gorev, (adaylar, *_) in GOREVLER.items()
        if (alan := _alan_bul(satirlar[0], adaylar))
    }
    if not mevcut_gorevler:
        raise SystemExit(
            "HATA: dosyada 'kategori'/'category', 'intent' veya "
            "'oncelik'/'priority' alanlarindan hicbiri yok. En azindan "
            "kategori gerekli."
        )

    print(f"{len(satirlar)} kayit yuklendi. Olculecek gorevler: "
          f"{', '.join(mevcut_gorevler)}. Model yukleniyor...")
    cihaz = cihaz_sec()
    model, tokenizer, _ = model_yukle(cihaz)

    dagilimlar = tum_gorevleri_tahmin_et(model, tokenizer, satirlar, cihaz)

    for gorev, alan in mevcut_gorevler.items():
        _, id2ad, goruntu = GOREVLER[gorev]
        gecerli_anahtarlar = set(id2ad.values())

        gercek_ad, gercek_id, tahmin_id, metinler = [], [], [], []
        for i, r in enumerate(satirlar):
            deger = r.get(alan)
            if deger not in gecerli_anahtarlar:
                continue  # bos veya bilinmeyen etiket -- bu kayit bu gorevden atlanir
            ters = {v: k for k, v in id2ad.items()}
            gercek_ad.append(deger)
            gercek_id.append(ters[deger])
            tahmin_id.append(int(dagilimlar[gorev][i].argmax()))
            metinler.append(r["metin"])

        if not gercek_id:
            print(f"\n({gorev}: hicbir kayitta gecerli etiket yok, atlandi)")
            continue

        tahmin_ad = [id2ad[t] for t in tahmin_id]
        acc = accuracy_score(gercek_id, tahmin_id)
        f1 = f1_score(gercek_id, tahmin_id, average="macro", zero_division=0)

        print(f"\n{'=' * 70}\n{gorev.upper()}  —  {len(gercek_id)} kayit\n{'=' * 70}")
        print(f"  doğruluk   {acc:.1%}")
        print(f"  macro F1   {f1:.4f}")

        etiketler = sorted(set(gercek_id) | set(tahmin_id))
        p, r_, f, d = precision_recall_fscore_support(
            gercek_id, tahmin_id, labels=etiketler, zero_division=0)
        print(f"\n  {'sinif':<26} {'precision':>10} {'recall':>8} {'F1':>8} {'destek':>7}")
        for i, etiket_id in enumerate(etiketler):
            print(f"  {goruntu[id2ad[etiket_id]]:<26} {p[i]:>10.4f} {r_[i]:>8.4f} "
                  f"{f[i]:>8.4f} {d[i]:>7}")

        karisan = Counter()
        hatalar = []
        for m, g, t in zip(metinler, gercek_ad, tahmin_ad):
            if g != t:
                karisan[(g, t)] += 1
                hatalar.append((m, g, t))

        if karisan:
            print("\n  en çok karışan çiftler:")
            for (g, t), n in karisan.most_common(8):
                print(f"    {goruntu[g]:<24} -> {goruntu[t]:<24} {n}")

        if args.hatalari_goster and hatalar:
            print(f"\n  hatalar (ilk 20/{len(hatalar)}):")
            for m, g, t in hatalar[:20]:
                print(f"    [{goruntu[g]} -> {goruntu[t]}] {m[:80]}")


if __name__ == "__main__":
    main()
