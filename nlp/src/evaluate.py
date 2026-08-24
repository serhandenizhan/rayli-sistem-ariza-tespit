"""
Adim 4b — Degerlendirme: metrikler, confusion matrix, hata analizi, kalibrasyon.

Amac "accuracy iyi" demek degil, modelin NEREDE hata yaptigini gostermek.

IKI AYRI TEST raporlanir ve aradaki FARK asil bulgudur:
  test.csv       cogaltilmis veriden ayrilmis; train ile ayni dagilimdan gelir
  gold_test.csv  bagimsiz uretilmis, elle gozden gecirilmis, few-shot'ta hic
                 kullanilmamis; zor ve sinirda ornekler icerir

KALIBRASYON VALIDATION SETI UZERINDEN yapilir, test/gold uzerinden DEGIL.
Esigi test setine bakarak secmek test setini karar surecine sokar ve raporlanan
skoru iyimser hale getirir. val.csv bu is icin ayrilmisti (egitimde zaten
epoch secimi icin kullanildi, yani "kirli" olmasi sorun degil).

Kullanim:
    python -m src.evaluate
    python -m src.evaluate --hatalari-goster       # sinif bazli hata ornekleri
    python -m src.evaluate --kalibrasyon           # validation + reliability
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from torch.utils.data import DataLoader
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src import config as C
from src.train import BildirimVeriseti, cihaz_sec, csv_oku


# ---------------------------------------------------------------------------
# Model yukleme
# ---------------------------------------------------------------------------

def model_yukle(cihaz):
    """Cok basli modeli yukler. (model, tokenizer, egitim_ozeti) doner."""
    if not (C.MODEL_DIR / "egitim_ozeti.json").exists():
        raise SystemExit(
            f"HATA: egitilmis model yok ({C.MODEL_DIR}).\n"
            f"Once calistir: python -m src.train"
        )
    ozet = json.loads((C.MODEL_DIR / "egitim_ozeti.json").read_text(encoding="utf-8"))

    from src.model import CokBaslikliSiniflandirici

    tokenizer = AutoTokenizer.from_pretrained(C.MODEL_DIR)
    model = CokBaslikliSiniflandirici.yukle(C.MODEL_DIR)
    model.to(cihaz).eval()
    return model, tokenizer, ozet


def tahmin_et(model, tokenizer, satirlar, cihaz, gorev: str = "kategori"):
    """Tek bir gorev icin (tahminler, guvenler, tum_olasiliklar) doner.

    Varsayilan `kategori` -- raporun buyuk kismi kategoriye odakli ve mevcut
    cagiranlar (calibrate, toplu_test, resolve_logs) bu imzayi bekliyor.
    Uc gorevin hepsi birden gerekiyorsa `tum_gorevleri_tahmin_et` kullanilir.
    """
    hepsi = tum_gorevleri_tahmin_et(model, tokenizer, satirlar, cihaz)
    olasi = hepsi[gorev]
    guven, tahmin = olasi.max(dim=-1)
    return tahmin.tolist(), guven.tolist(), olasi.tolist()


def tum_gorevleri_tahmin_et(model, tokenizer, satirlar, cihaz):
    """{gorev: (N, sinif) olasilik tensoru} doner."""
    from src.model import tahmin_dagilimlari

    metinler = [r["metin"] for r in satirlar]
    return tahmin_dagilimlari(model, tokenizer, metinler, cihaz)


# ---------------------------------------------------------------------------
# Raporlama yardimcilari
# ---------------------------------------------------------------------------

def kisa_ad(kategori_key: str, genislik: int = 12) -> str:
    return C.DISPLAY_NAME[kategori_key][:genislik]


def matris_yazdir(gercek, tahmin):
    cm = confusion_matrix(gercek, tahmin, labels=range(C.NUM_LABELS))
    basliklar = [kisa_ad(k, 6) for k in C.CATEGORY_KEYS]
    print(f"\n{'gercek \\ tahmin':<22}" + "".join(f"{b:>8}" for b in basliklar))
    for i, k in enumerate(C.CATEGORY_KEYS):
        satir = "".join(
            f"{cm[i][j]:>8}" if i != j else f"{'[' + str(cm[i][j]) + ']':>8}"
            for j in range(C.NUM_LABELS)
        )
        print(f"{kisa_ad(k, 20):<22}{satir}")
    print("  (kosegen [] = dogru tahmin)")
    return cm


def karisan_ciftler(cm, ust: int = 6) -> list[tuple[str, str, int]]:
    ciftler = [
        (g, t, int(cm[i][j]))
        for i, g in enumerate(C.CATEGORY_KEYS)
        for j, t in enumerate(C.CATEGORY_KEYS)
        if i != j and cm[i][j] > 0
    ]
    ciftler.sort(key=lambda x: -x[2])
    return ciftler[:ust]


def ikincil_kategori_analizi(gercek, tahmin, olasiliklar) -> dict:
    """Ikincil kategori mekanizmasinin olculmesi.

    Taksonomi sinir sorunlarina kural yazmak yerine modelin kendi olasilik
    dagilimini kullaniyoruz: marj (top1-top2) kucukse model iki kategori
    arasinda kararsiz demektir ve ikisini birden dondurmek dogru davranis.
    """
    olasi = np.array(olasiliklar)
    gercek_np = np.array(gercek)
    sirali = np.sort(olasi, axis=1)
    marj = sirali[:, -1] - sirali[:, -2]
    top2 = np.argsort(olasi, axis=1)[:, -2:]

    dogru = np.array(tahmin) == gercek_np
    top2_dogru = np.array([g in t2 for g, t2 in zip(gercek_np, top2)])
    isaretli = marj < C.MARGIN_THRESHOLD

    return {
        "top1_accuracy": float(dogru.mean()),
        "top2_accuracy": float(top2_dogru.mean()),
        "marj_dogru": float(marj[dogru].mean()),
        "marj_yanlis": float(marj[~dogru].mean()) if (~dogru).any() else None,
        "cift_kategorili": int(isaretli.sum()),
        "kurtarilan_hata": int((isaretli & ~dogru & top2_dogru).sum()),
        "toplam_hata": int((~dogru).sum()),
        "bosuna_isaretlenen": int((isaretli & dogru).sum()),
    }


def hata_ornekleri_yazdir(satirlar, gercek, tahmin, guven, ust: int = 20) -> None:
    """Hatalari SINIF BAZINDA gruplayip yazdirir.

    Duz liste yerine gruplamanin sebebi: "model nerede hata yapiyor" sorusunun
    cevabi tek tek hatalar degil, hangi sinifin hangi sinifla karistigi. Grup
    icinde en DUSUK guvenli hata once gelir -- onlar modelin zaten tereddut
    ettikleri, yani en ogretici olanlar.
    """
    gruplar: dict[tuple[str, str], list] = defaultdict(list)
    for r, g, t, gv in zip(satirlar, gercek, tahmin, guven):
        if g != t:
            gruplar[(C.ID2LABEL[g], C.ID2LABEL[t])].append((gv, r))

    if not gruplar:
        print("\nHATA YOK.")
        return

    toplam = sum(len(v) for v in gruplar.values())
    print(f"\nHATA ORNEKLERI — {toplam} hata, sinif bazinda gruplu "
          f"(en fazla {ust} ornek):")

    yazilan = 0
    for (g, t), kayitlar in sorted(gruplar.items(), key=lambda x: -len(x[1])):
        if yazilan >= ust:
            break
        print(f"\n  {C.DISPLAY_NAME[g]} -> {C.DISPLAY_NAME[t]}  ({len(kayitlar)} hata)")
        for gv, r in sorted(kayitlar)[: max(1, ust - yazilan)]:
            if yazilan >= ust:
                break
            print(f"    guven {gv:.2f} [{r.get('stil', '?'):<13}] {r['metin']}")
            yazilan += 1


def contamination_kontrolu() -> dict:
    """train <-> test/gold arasinda sizinti var mi?

    preprocess.py bunu bolme aninda garanti ediyor, ama DEGERLENDIRME raporunda
    da olmasi gerekiyor: raporlanan skorun gecerli olmasi bu kontrole bagli.
    Bagimsiz olarak, diskteki nihai dosyalar uzerinden yeniden dogruluyoruz.
    """
    from src import review as R

    def norm_kume(path):
        # Gold opsiyoneldir (taksonomi degisiminde yeniden hazirlanana kadar
        # bulunmayabilir); yoksa bos kume donulur ve ilgili kesisimler 0 cikar.
        if not path.exists():
            return set()
        return {R.normalize(r["metin"]) for r in csv_oku(path)}

    train, val = norm_kume(C.TRAIN_FILE), norm_kume(C.VAL_FILE)
    test, gold = norm_kume(C.TEST_FILE), norm_kume(C.GOLD_TEST_FILE)

    sonuc = {
        "birebir_train_test": len(train & test),
        "birebir_train_val": len(train & val),
        "birebir_val_test": len(val & test),
        "birebir_train_gold": len(train & gold),
        "birebir_test_gold": len(test & gold),
    }

    # Near-duplicate sizinti. KRITIK AYRIM: benzer iki kaydin AYNI kategoride
    # olmasi gercek sizintidir (model train'de gordugu cevabi ezberleyip
    # test'te tekrarlayabilir, skor siser). FARKLI kategoride olmasi sizinti
    # DEGIL, taksonomi belirsizligidir -- etiketler farkli oldugu icin ezber
    # ise yaramaz, aksine model zorlanir. Ikisini ayirmadan raporlamak
    # "skorlar iyimser" diye yanlis uyari uretir.
    train_kayit = [(R.normalize(r["metin"]), r["kategori"]) for r in csv_oku(C.TRAIN_FILE)]
    ayni_kat, farkli_kat = 0, 0
    for r in csv_oku(C.TEST_FILE):
        tn, tk = R.normalize(r["metin"]), r["kategori"]
        for xn, xk in train_kayit:
            if R.similarity(tn, xn) >= C.CLUSTER_THRESHOLD:
                if tk == xk:
                    ayni_kat += 1
                else:
                    farkli_kat += 1
                break
    sonuc["near_dup_train_test_AYNI_kategori"] = ayni_kat
    sonuc["near_dup_train_test_farkli_kategori"] = farkli_kat
    return sonuc


# ---------------------------------------------------------------------------
# Set degerlendirme
# ---------------------------------------------------------------------------

def set_degerlendir(ad: str, satirlar, model, tokenizer, cihaz,
                    hatalari_goster: bool) -> dict:
    gercek = [int(r["label"]) for r in satirlar]
    tahmin, guven, olasiliklar = tahmin_et(model, tokenizer, satirlar, cihaz)

    acc = accuracy_score(gercek, tahmin)
    macro = f1_score(gercek, tahmin, average="macro", zero_division=0)
    weighted = f1_score(gercek, tahmin, average="weighted", zero_division=0)
    p_macro, r_macro, _, _ = precision_recall_fscore_support(
        gercek, tahmin, average="macro", zero_division=0
    )
    p_w, r_w, _, _ = precision_recall_fscore_support(
        gercek, tahmin, average="weighted", zero_division=0
    )
    prec, rec, f1s, destek = precision_recall_fscore_support(
        gercek, tahmin, labels=range(C.NUM_LABELS), zero_division=0
    )

    print(f"\n{'=' * 78}\n{ad}  —  {len(satirlar)} kayit\n{'=' * 78}")
    print("\nGENEL METRIKLER")
    print(f"  accuracy            {acc:.4f}   (hedef {C.TARGET_ACCURACY})   "
          f"{'GECTI' if acc >= C.TARGET_ACCURACY else 'KALDI'}")
    print(f"  macro F1            {macro:.4f}   (hedef {C.TARGET_MACRO_F1})   "
          f"{'GECTI' if macro >= C.TARGET_MACRO_F1 else 'KALDI'}")
    print(f"  weighted F1         {weighted:.4f}")
    print(f"  macro precision     {p_macro:.4f}      macro recall     {r_macro:.4f}")
    print(f"  weighted precision  {p_w:.4f}      weighted recall  {r_w:.4f}")
    en_dusuk = f1s.min()
    print(f"  en dusuk sinif F1   {en_dusuk:.4f}   (hedef {C.MIN_PER_CLASS_F1})   "
          f"{'GECTI' if en_dusuk >= C.MIN_PER_CLASS_F1 else 'KALDI'}")

    print(f"\nSINIF BAZLI METRIKLER")
    print(f"{'kategori':<28} {'precision':>10} {'recall':>8} {'F1':>8} {'destek':>7}")
    for i, k in enumerate(C.CATEGORY_KEYS):
        uyari = "  <-- hedefin altinda" if f1s[i] < C.MIN_PER_CLASS_F1 else ""
        print(f"{C.DISPLAY_NAME[k]:<28} {prec[i]:>10.4f} {rec[i]:>8.4f} "
              f"{f1s[i]:>8.4f} {destek[i]:>7}{uyari}")

    cm = matris_yazdir(gercek, tahmin)

    ciftler = karisan_ciftler(cm)
    if ciftler:
        print("\nEN COK KARISAN CIFTLER (gercek -> tahmin):")
        for g, t, n in ciftler:
            print(f"  {n:>3}x  {C.DISPLAY_NAME[g]:<26} -> {C.DISPLAY_NAME[t]}")

    if satirlar and satirlar[0].get("stil"):
        stil_dogru: dict[str, list[int]] = defaultdict(list)
        for r, g, t in zip(satirlar, gercek, tahmin):
            stil_dogru[r["stil"]].append(1 if g == t else 0)
        print("\nSTIL BAZLI DOGRULUK:")
        for stil in C.STYLE_KEYS:
            v = stil_dogru.get(stil, [])
            if v:
                print(f"  {stil:<16} {sum(v) / len(v):.4f}  ({sum(v)}/{len(v)})")

    ik = ikincil_kategori_analizi(gercek, tahmin, olasiliklar)
    print(f"\nIKINCIL KATEGORI (MARGIN_THRESHOLD={C.MARGIN_THRESHOLD}):")
    print(f"  top-1 dogruluk {ik['top1_accuracy']:.4f}  ->  "
          f"TOP-2 dogruluk {ik['top2_accuracy']:.4f}")
    print(f"  {ik['cift_kategorili']} kayit cift kategorili donerdi "
          f"(%{100 * ik['cift_kategorili'] / len(satirlar):.1f} trafik): "
          f"{ik['kurtarilan_hata']}/{ik['toplam_hata']} hatada dogru cevap "
          f"ikinci etikette, {ik['bosuna_isaretlenen']} dogru bosuna isaretlenir")

    dusuk = sum(1 for g in guven if g < C.CONFIDENCE_THRESHOLD)
    yakalanan = sum(1 for g, gc, t in zip(guven, gercek, tahmin)
                    if g < C.CONFIDENCE_THRESHOLD and gc != t)
    print(f"\nMANUAL REVIEW (CONFIDENCE_THRESHOLD={C.CONFIDENCE_THRESHOLD}):")
    print(f"  {dusuk} kayit manuel incelemeye gonderilirdi "
          f"(%{100 * dusuk / len(satirlar):.1f}), "
          f"{yakalanan}/{ik['toplam_hata']} hatayi yakalar")

    if hatalari_goster:
        hata_ornekleri_yazdir(satirlar, gercek, tahmin, guven)

    return {
        "ad": ad, "n": len(satirlar),
        "accuracy": acc, "macro_f1": macro, "weighted_f1": weighted,
        "macro_precision": float(p_macro), "macro_recall": float(r_macro),
        "weighted_precision": float(p_w), "weighted_recall": float(r_w),
        "min_sinif_f1": float(en_dusuk),
        "sinif_metrikleri": {
            k: {"precision": float(prec[i]), "recall": float(rec[i]),
                "f1": float(f1s[i]), "destek": int(destek[i])}
            for i, k in enumerate(C.CATEGORY_KEYS)
        },
        "karisan_ciftler": ciftler,
        "ikincil_kategori": ik,
        "manual_review_sayisi": dusuk,
    }


# ---------------------------------------------------------------------------
# Kalibrasyon — VALIDATION seti uzerinden
# ---------------------------------------------------------------------------

def kalibrasyon_raporu(model, tokenizer, cihaz) -> dict:
    """Guven esigini VALIDATION seti uzerinden kalibre eder + reliability diagram.

    Neden validation: esigi test'e bakarak secmek test setini karar surecine
    sokar ve raporlanan skoru iyimser yapar. val.csv zaten epoch seciminde
    kullanildi, yani bu is icin dogru set.
    """
    satirlar = csv_oku(C.VAL_FILE)
    gercek = [int(r["label"]) for r in satirlar]
    tahmin, guven, _ = tahmin_et(model, tokenizer, satirlar, cihaz)

    guven_np = np.array(guven)
    dogru = np.array(tahmin) == np.array(gercek)
    n_hata = int((~dogru).sum())

    print(f"\n{'=' * 78}\nKALIBRASYON — validation seti ({len(satirlar)} kayit, "
          f"{n_hata} hata)\n{'=' * 78}")
    print(f"  dogru tahminlerde ortalama guven  {guven_np[dogru].mean():.4f}")
    if n_hata:
        print(f"  YANLIS tahminlerde ortalama guven {guven_np[~dogru].mean():.4f}")

    print(f"\nESIK TARAMASI (manual_review'e gidecek kayitlar)")
    print(f"{'esik':>6} {'manuel':>8} {'trafik':>8} {'yakalanan hata':>16} "
          f"{'bosuna':>8} {'precision':>10}")
    taramalar = []
    for esik in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        altinda = guven_np < esik
        yakalanan = int((altinda & ~dogru).sum())
        bosuna = int((altinda & dogru).sum())
        # precision = isaretlenenlerin kaci gercekten hataliydi
        prec = yakalanan / altinda.sum() if altinda.sum() else 0.0
        taramalar.append({"esik": esik, "manuel": int(altinda.sum()),
                          "yakalanan": yakalanan, "bosuna": bosuna,
                          "precision": prec})
        isaret = "  <-- aktif" if abs(esik - C.CONFIDENCE_THRESHOLD) < 1e-9 else ""
        print(f"{esik:>6.2f} {altinda.sum():>8} {100 * altinda.mean():>7.1f}% "
              f"{yakalanan:>10}/{n_hata:<5} {bosuna:>8} {prec:>10.3f}{isaret}")

    # Reliability diagram: guven kovalarinda tahmin edilen vs gercek dogruluk.
    # Iyi kalibre bir modelde "0.9 guvenle soyledigim seylerin %90'i dogru".
    print(f"\nRELIABILITY DIAGRAM (guven kovasi -> gercek dogruluk)")
    print(f"{'kova':>12} {'kayit':>7} {'ort. guven':>11} {'gercek dogruluk':>16}  sapma")
    kovalar = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9),
               (0.9, 0.95), (0.95, 1.01)]
    ece, toplam = 0.0, len(guven_np)
    reliability = []
    for lo, hi in kovalar:
        maske = (guven_np >= lo) & (guven_np < hi)
        if not maske.any():
            print(f"  [{lo:.2f}-{hi:.2f})       0           -                -")
            continue
        ort_guven = float(guven_np[maske].mean())
        gercek_dog = float(dogru[maske].mean())
        sapma = gercek_dog - ort_guven
        ece += maske.sum() / toplam * abs(sapma)
        reliability.append({"bant": f"{lo:.2f}-{hi:.2f}", "n": int(maske.sum()),
                            "ort_guven": ort_guven, "dogruluk": gercek_dog})
        cubuk = "#" * int(round(gercek_dog * 20))
        print(f"  [{lo:.2f}-{hi:.2f}) {maske.sum():>7} {ort_guven:>11.3f} "
              f"{gercek_dog:>16.3f}  {sapma:+.3f} {cubuk}")

    print(f"\n  ECE (Expected Calibration Error) = {ece:.4f}")
    print("  (0'a yakin = model guven skoru gercek dogrulukla ortusuyor)")

    return {"n": len(satirlar), "hata": n_hata, "esik_taramasi": taramalar,
            "reliability": reliability, "ece": float(ece)}


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def ek_gorev_raporu(satirlar, model, tokenizer, cihaz) -> None:
    """Intent ve oncelik basliklarinin metrikleri.

    Kategori raporu yukarida ayrintili veriliyor; burada diger iki gorev
    ozetleniyor. Oncelik ozellikle izlenmeli: metinden cikarilmasi en zor
    boyut, cunku ayni ekipman arizasi kapsamina gore P1 de P3 de olabilir
    ("bir merdiven durdu" P3, "butun merdivenler durdu" P2).
    """
    from src.model import GOREVLER

    dagilimlar = tum_gorevleri_tahmin_et(model, tokenizer, satirlar, cihaz)
    sutunlar = {"intent": ("intent_label", C.ID2INTENT, C.INTENT_DISPLAY),
                "oncelik": ("oncelik_label", C.ID2PRIORITY, C.PRIORITY_DISPLAY)}

    for gorev, (sutun, id2ad, gorunen) in sutunlar.items():
        if sutun not in satirlar[0]:
            continue
        gercek = [int(r[sutun]) for r in satirlar]
        tahmin = dagilimlar[gorev].argmax(dim=-1).tolist()

        print(f"\n{'=' * 78}\n{gorev.upper()} BASLIGI  —  {len(gercek)} kayit\n{'=' * 78}")
        print(f"  accuracy   {accuracy_score(gercek, tahmin):.4f}")
        print(f"  macro F1   {f1_score(gercek, tahmin, average='macro', zero_division=0):.4f}")

        p, r, f, d = precision_recall_fscore_support(
            gercek, tahmin, labels=range(len(id2ad)), zero_division=0)
        print(f"\n{'sinif':<26} {'precision':>10} {'recall':>8} {'F1':>8} {'destek':>7}")
        for i in range(len(id2ad)):
            ad = gorunen[id2ad[i]]
            print(f"{ad:<26} {p[i]:>10.4f} {r[i]:>8.4f} {f[i]:>8.4f} {d[i]:>7}")

        karisan = Counter()
        for g, t in zip(gercek, tahmin):
            if g != t:
                karisan[(id2ad[g], id2ad[t])] += 1
        if karisan:
            print("\n  en cok karisan ciftler:")
            for (g, t), n in karisan.most_common(5):
                print(f"    {gorunen[g]:<24} -> {gorunen[t]:<24} {n}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 4b -- degerlendirme")
    ap.add_argument("--hatalari-goster", action="store_true",
                    help="sinif bazinda gruplu hata ornekleri yazdir")
    ap.add_argument("--kalibrasyon", action="store_true",
                    help="validation uzerinden esik taramasi + reliability diagram")
    ap.add_argument("--device", choices=["mps", "cpu"])
    args = ap.parse_args()

    cihaz = cihaz_sec(args.device)
    model, tokenizer, ozet = model_yukle(cihaz)
    print(f"cihaz: {cihaz} | LoRA: {ozet.get('lora')} | "
          f"en iyi epoch: {ozet.get('en_iyi_epoch')} | "
          f"ASCII cogaltma: {ozet.get('ascii_cogaltma')}")

    # Sizinti kontrolu EN BASTA: raporlanan skorun gecerliligi buna bagli.
    kirlilik = contamination_kontrolu()
    print(f"\n{'=' * 78}\nCONTAMINATION KONTROLU\n{'=' * 78}")
    # Sadece AYNI kategorideki ortusme gercek sizintidir (bkz. fonksiyon notu).
    zararli = [k for k, v in kirlilik.items()
               if v > 0 and not k.endswith("farkli_kategori")]
    for anahtar, deger in kirlilik.items():
        if anahtar.endswith("farkli_kategori"):
            durum = "bilgi (sizinti DEGIL, taksonomi belirsizligi)" if deger else "TEMIZ"
        else:
            durum = "TEMIZ" if deger == 0 else "!! SIZINTI"
        print(f"  {anahtar:<38} {deger:>4}   {durum}")
    if zararli:
        print("\n  !! UYARI: sizinti var, asagidaki skorlar iyimser olabilir.")
    else:
        print("\n  Sonuc: zararli sizinti YOK, skorlar gecerli.")

    # Gold seti opsiyoneldir: taksonomi degistiginde eski gold gecersiz kalir
    # ve yenisi hazirlanana kadar dosya bulunmayabilir. Rapor bu durumda
    # sadece test seti uzerinden uretilir, cokmez.
    setler = [("TEST (cogaltilmis dagilim)", C.TEST_FILE)]
    if C.GOLD_TEST_FILE.exists():
        setler.append(("GOLD TEST (bagimsiz, elle gozden gecirilmis)",
                       C.GOLD_TEST_FILE))
    else:
        print(f"\n(NOT: {C.GOLD_TEST_FILE.name} yok -- bagimsiz gold "
              f"degerlendirmesi atlaniyor.)")

    sonuclar = [
        set_degerlendir(ad, csv_oku(path), model, tokenizer, cihaz,
                        args.hatalari_goster)
        for ad, path in setler
    ]

    ek_gorev_raporu(csv_oku(C.TEST_FILE), model, tokenizer, cihaz)

    kalibrasyon = kalibrasyon_raporu(model, tokenizer, cihaz) if args.kalibrasyon else None

    if len(sonuclar) < 2:
        cikti = {"contamination": kirlilik, "setler": sonuclar,
                 "kalibrasyon": kalibrasyon}
        (C.MODEL_DIR / "degerlendirme.json").write_text(
            json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {C.MODEL_DIR / 'degerlendirme.json'}")
        return

    t, g = sonuclar[0], sonuclar[1]
    print(f"\n{'=' * 78}\nTEST vs GOLD — sentetik veri ne kadar gercekci?\n{'=' * 78}")
    print(f"{'metrik':<18} {'test':>9} {'gold':>9} {'fark':>9}")
    for anahtar, etiket in (("accuracy", "accuracy"), ("macro_f1", "macro F1"),
                            ("weighted_f1", "weighted F1")):
        print(f"{etiket:<18} {t[anahtar]:>9.4f} {g[anahtar]:>9.4f} "
              f"{g[anahtar] - t[anahtar]:>+9.4f}")

    fark = g["macro_f1"] - t["macro_f1"]
    if fark > -0.05:
        print("\nYORUM: gold skoru test'e cok yakin. Sentetik veri gercek "
              "bildirimlere yakin duruyor; model kaliplari degil sinifi ogrenmis.")
    elif fark > -0.15:
        print("\nYORUM: gold skoru olculu sekilde dusuk. Beklenen bir fark — "
              "gold bilerek daha zor ve sinirda ornekler iceriyor.")
    else:
        print("\nYORUM: gold skoru belirgin dusuk. Model cogaltmanin kendine "
              "ozgu kaliplarini ogrenmis olabilir; veri cesitliligi artirilmali.")

    cikti = {"contamination": kirlilik, "setler": sonuclar,
             "kalibrasyon": kalibrasyon}
    (C.MODEL_DIR / "degerlendirme.json").write_text(
        json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n-> {C.MODEL_DIR / 'degerlendirme.json'}")


if __name__ == "__main__":
    main()
