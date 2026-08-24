"""
Adim 4a — Model egitimi: BERTurk + LoRA.

dbmdz/bert-base-turkish-cased uzerine PEFT/LoRA ile siniflandirma basligi
egitir. Tam fine-tuning yerine LoRA secildi cunku 1280 ornekle 110M parametreyi
tamamen egitmek asiri ogrenmeye acik; LoRA sadece query/value projeksiyonlarina
dusuk ranklı adaptor ekleyip egitilen parametre sayisini ~%1'e indiriyor.

Apple Silicon notu: MPS backend kullanilir. MPS'te bilinen kisitlar var
(bazi operatorler desteklenmiyor, fp16 sorunlu) -- bu yuzden fp32'de egitiyoruz
ve sorun cikarsa CPU'ya dusuyoruz.

Kullanim:
    python -m src.train
    python -m src.train --epochs 8 --no-lora
    python -m src.train --device cpu
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src import config as C


# ---------------------------------------------------------------------------
# Yeniden uretilebilirlik
# ---------------------------------------------------------------------------

def tohum_ek(seed: int = C.SEED) -> None:
    """Ayni tohumla ayni sonuc. Rapor icin kritik: 'bu skoru nasil aldin'
    sorusunun cevabi tekrar calistirilabilir olmali."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        torch.mps.manual_seed(seed)


def cihaz_sec(tercih: str | None = None) -> torch.device:
    if tercih:
        return torch.device(tercih)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ---------------------------------------------------------------------------
# Veri
# ---------------------------------------------------------------------------

# CSV sutun adi -> modelin bekledigi etiket adi. Sutun yoksa (eski tek
# boyutlu veri) o gorev sessizce atlanir ve kaybina katilmaz; boylece eski
# veriyle de calisabilir.
ETIKET_SUTUNLARI = {
    "label": "kategori",
    "intent_label": "intent",
    "oncelik_label": "oncelik",
}


class BildirimVeriseti(Dataset):
    """Tokenize edilmis ariza bildirimleri; uc gorevin etiketini birlikte tasir."""

    def __init__(self, satirlar: list[dict], tokenizer, max_length: int):
        self.metinler = [r["metin"] for r in satirlar]
        self.etiketler = {
            ad: [int(r[sutun]) for r in satirlar]
            for sutun, ad in ETIKET_SUTUNLARI.items()
            if satirlar and sutun in satirlar[0]
        }
        self.enc = tokenizer(
            self.metinler,
            truncation=True,
            padding="max_length",
            max_length=max_length,
            return_tensors="pt",
        )

    def __len__(self) -> int:
        return len(self.metinler)

    def __getitem__(self, i: int) -> dict:
        parti = {
            "input_ids": self.enc["input_ids"][i],
            "attention_mask": self.enc["attention_mask"][i],
        }
        for ad, degerler in self.etiketler.items():
            parti[ad] = torch.tensor(degerler[i], dtype=torch.long)
        return parti


def csv_oku(path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"HATA: {path} yok. Once calistir: python -m src.preprocess"
        )
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


TR_HARFLER = set("çğıöşüÇĞİÖŞÜ")


def ascii_cogalt(satirlar: list[dict]) -> list[dict]:
    """Aksan iceren kayitlarin ASCII'ye katlanmis kopyalarini ekler.

    Gerekcesi config.AUGMENT_ASCII_FOLD'da olculmus haliyle duruyor: aksan
    kaybolunca dogruluk 6.4 puan dusuyor cunku BERTurk tokenizer'i kelimeyi
    parcaliyor ("asansör" 1 parca, "asansor" 3 parca). Modele iki yazimin da
    ayni sinifa ait oldugunu ogretiyoruz.

    Sadece aksan ICEREN kayitlar cogaltilir; digerlerinin ASCII hali zaten
    kendisiyle ayni olurdu ve birebir tekrar eklemek ogrenmeye katki yapmaz.
    """
    from src.review import _strip_diacritics

    ek = [
        {**r, "metin": _strip_diacritics(r["metin"]), "kaynak": "ascii_fold"}
        for r in satirlar
        if set(r["metin"]) & TR_HARFLER
    ]
    return satirlar + ek


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def model_kur(use_lora: bool):
    """Cok basli modeli kurar ve (model, egitilebilir_parametre) doner.

    Tek baslikli AutoModelForSequenceClassification yerine src/model.py'deki
    CokBaslikliSiniflandirici kullaniliyor: ayni govde uzerinden kategori,
    intent ve oncelik ayri basliklarla ogreniliyor (gerekcesi o dosyada).
    """
    from src.model import CokBaslikliSiniflandirici

    model = CokBaslikliSiniflandirici(C.BASE_MODEL, lora=use_lora)
    egitilen = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return model, egitilen


# ---------------------------------------------------------------------------
# Egitim dongusu
#
# HuggingFace Trainer yerine elle dongu yaziyoruz: Trainer accelerate uzerinden
# MPS'te zaman zaman dtype/device surprizleri cikariyor ve ne oldugunu gormek
# zorlasiyor. Bu boyutta bir is (1280 ornek, 5 epoch) icin elle dongu hem
# seffaf hem yeterli.
# ---------------------------------------------------------------------------

def degerlendir(model, yukleyici, cihaz) -> tuple[float, dict]:
    """(ortalama_kayip, {gorev: {acc, f1}}) doner.

    Validation KAYBI da olculuyor: accuracy/F1 plato yaparken kayip yukselmeye
    baslarsa model asiri ogrenmeye gecmis demektir. Bu, sadece F1'e bakarak
    goremeyecegimiz bir sinyal.
    """
    from src.model import GOREVLER

    model.eval()
    tahmin = {ad: [] for ad, _ in GOREVLER}
    gercek = {ad: [] for ad, _ in GOREVLER}
    kayip_top = 0.0
    with torch.no_grad():
        for parti in yukleyici:
            parti = {k: v.to(cihaz) for k, v in parti.items()}
            cikti = model(**parti)
            kayip_top += cikti["loss"].item()
            for ad, _ in GOREVLER:
                if ad not in parti:
                    continue
                tahmin[ad].extend(cikti["logits"][ad].argmax(dim=-1).cpu().tolist())
                gercek[ad].extend(parti[ad].cpu().tolist())

    metrikler = {}
    for ad, _ in GOREVLER:
        if not gercek[ad]:
            continue
        metrikler[ad] = {
            "acc": accuracy_score(gercek[ad], tahmin[ad]),
            "f1": f1_score(gercek[ad], tahmin[ad], average="macro", zero_division=0),
        }
    return kayip_top / len(yukleyici), metrikler


def egit(args) -> None:
    tohum_ek(args.seed if args.seed is not None else C.SEED)
    cihaz = cihaz_sec(args.device)
    print(f"cihaz: {cihaz}  |  model: {C.BASE_MODEL}  |  LoRA: {not args.no_lora}")

    tokenizer = AutoTokenizer.from_pretrained(C.BASE_MODEL)
    train_satir = csv_oku(C.TRAIN_FILE)
    val_satir = csv_oku(C.VAL_FILE)

    cogalt = C.AUGMENT_ASCII_FOLD and not args.no_augment
    if cogalt:
        onceki = len(train_satir)
        train_satir = ascii_cogalt(train_satir)
        print(f"train {onceki} -> {len(train_satir)} "
              f"(+{len(train_satir) - onceki} ASCII katlanmis kopya) | "
              f"val {len(val_satir)}")
    else:
        print(f"train {len(train_satir)} | val {len(val_satir)}  (cogaltma KAPALI)")

    train_ds = BildirimVeriseti(train_satir, tokenizer, C.MAX_LENGTH)
    val_ds = BildirimVeriseti(val_satir, tokenizer, C.MAX_LENGTH)
    train_dl = DataLoader(train_ds, batch_size=C.BATCH_SIZE, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=C.BATCH_SIZE)

    model, egitilen = model_kur(not args.no_lora)
    toplam = sum(p.numel() for p in model.parameters())
    print(f"parametre: {toplam:,} toplam | {egitilen:,} egitilebilir "
          f"(%{100 * egitilen / toplam:.2f})")
    model.to(cihaz)

    epochs = args.epochs or C.NUM_EPOCHS
    optim = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr or C.LEARNING_RATE,
        weight_decay=C.WEIGHT_DECAY,
    )
    toplam_adim = len(train_dl) * epochs
    plan = torch.optim.lr_scheduler.OneCycleLR(
        optim,
        max_lr=args.lr or C.LEARNING_RATE,
        total_steps=toplam_adim,
        pct_start=C.WARMUP_RATIO,
        anneal_strategy="linear",
    )

    print(f"\n{'epoch':>5} {'train':>8} {'val':>8} | {'kategori':>9} "
          f"{'intent':>8} {'oncelik':>8} | {'ortF1':>7} {'sure':>7}")
    en_iyi_f1, en_iyi_epoch = -1.0, -1
    en_iyi_val_kayip, sabir_sayaci = float("inf"), 0   # early stopping takibi
    gecmis = []
    batch_gecmisi = []          # canli grafik icin: epoch'un ortasinda da veri

    def _canli_yaz(durum: str) -> None:
        """Canli izleme dosyasi -- CANLI_KAYIP_FILE. Web sayfasi bunu her
        1-2 saniyede bir okuyup grafigi gunceller (bkz. dev/canli_kayip.html).
        Epoch basina bir kez yazmak grafigi 55-70 saniyede bir zıplatirdi;
        birkac batch'te bir yazmak akici bir egri verir."""
        (C.MODEL_DIR / "canli_kayip.json").write_text(json.dumps({
            "durum": durum, "guncel_epoch": epoch, "toplam_epoch": epochs,
            "adim_epoch_basina": len(train_dl),
            "en_iyi_f1": en_iyi_f1, "en_iyi_epoch": en_iyi_epoch,
            # inf JSON'da GECERSIZ (JS JSON.parse patlar) -- ilk epoch
            # bitmeden bu deger hala sonsuz, null'a cevriliyor.
            "en_iyi_val_kayip": None if en_iyi_val_kayip == float("inf") else en_iyi_val_kayip,
            "sabir_sayaci": sabir_sayaci,
            "early_stopping_patience": C.EARLY_STOPPING_PATIENCE,
            "epoch_gecmisi": gecmis, "batch_gecmisi": batch_gecmisi[-300:],
        }, ensure_ascii=False), encoding="utf-8")

    for epoch in range(1, epochs + 1):
        model.train()
        t0, kayip_top = time.time(), 0.0
        for adim, parti in enumerate(train_dl, 1):
            parti = {k: v.to(cihaz) for k, v in parti.items()}
            cikti = model(**parti)
            cikti["loss"].backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0
            )
            optim.step()
            plan.step()
            optim.zero_grad()
            kayip = cikti["loss"].item()
            kayip_top += kayip

            if adim % 5 == 0:
                batch_gecmisi.append({
                    "epoch": epoch, "adim": adim, "toplam_adim": len(train_dl),
                    "kayip": kayip,
                })
                _canli_yaz("egitiliyor")

        train_kayip = kayip_top / len(train_dl)
        val_kayip, metrikler = degerlendir(model, val_dl, cihaz)
        sure = time.time() - t0

        # Model secimi UC GOREVIN ORTALAMA macro-F1'ine gore yapilir. Tek bir
        # goreve (orn. kategori) gore secmek digerlerini kurban ederdi; ortalama
        # uc basligin birlikte iyi oldugu noktayi bulur.
        ort_f1 = sum(m["f1"] for m in metrikler.values()) / len(metrikler)
        gecmis.append({
            "epoch": epoch, "train_kayip": train_kayip, "val_kayip": val_kayip,
            "ortalama_f1": ort_f1,
            **{f"{ad}_f1": m["f1"] for ad, m in metrikler.items()},
            **{f"{ad}_acc": m["acc"] for ad, m in metrikler.items()},
        })

        isaret = ""
        if ort_f1 > en_iyi_f1:
            en_iyi_f1, en_iyi_epoch = ort_f1, epoch
            model.kaydet(C.MODEL_DIR)
            tokenizer.save_pretrained(C.MODEL_DIR)
            isaret = "  <- kaydedildi"
        # Early stopping: val_kayip DUZELDIYSE sabir sifirlanir, DUZELMEDIYSE
        # sayac artar. F1 secimiyle (yukarida) kasten AYRI -- gerekcesi
        # config.EARLY_STOPPING_PATIENCE yorumunda.
        if val_kayip < en_iyi_val_kayip:
            en_iyi_val_kayip, sabir_sayaci = val_kayip, 0
        else:
            sabir_sayaci += 1
            isaret += f"  (val_kayip {sabir_sayaci}/{C.EARLY_STOPPING_PATIENCE} epoch iyilesmedi)"

        print(f"{epoch:>5} {train_kayip:>8.4f} {val_kayip:>8.4f} | "
              f"{metrikler['kategori']['f1']:>9.4f} "
              f"{metrikler['intent']['f1']:>8.4f} "
              f"{metrikler['oncelik']['f1']:>8.4f} | "
              f"{ort_f1:>7.4f} {sure:>6.1f}s{isaret}")
        _canli_yaz("egitiliyor")

        if sabir_sayaci >= C.EARLY_STOPPING_PATIENCE:
            print(f"\nEARLY STOPPING: val_kayip {C.EARLY_STOPPING_PATIENCE} "
                  f"epoch boyunca iyilesmedi, epoch {epoch}/{epochs}'te durduruldu.")
            break

    _canli_yaz("tamamlandi")

    # En iyi val F1'i veren epoch kaydedilir, sonuncusu degil: son epoch
    # genelde asiri ogrenmis olur ve test skoru dusuk cikar.
    print(f"\nen iyi: epoch {en_iyi_epoch}, uc gorev ortalama val macro-F1 "
          f"{en_iyi_f1:.4f}")
    en_iyi_kayit = next(g for g in gecmis if g["epoch"] == en_iyi_epoch)
    for ad in ("kategori", "intent", "oncelik"):
        print(f"    {ad:<10} macro-F1 {en_iyi_kayit[f'{ad}_f1']:.4f}  "
              f"acc {en_iyi_kayit[f'{ad}_acc']:.4f}")
    print(f"model kaydedildi: {C.MODEL_DIR}")

    ozet = {
        "base_model": C.BASE_MODEL,
        "lora": not args.no_lora,
        "epochs": epochs,
        "calisan_epoch": gecmis[-1]["epoch"],
        "early_stopped": sabir_sayaci >= C.EARLY_STOPPING_PATIENCE,
        "batch_size": C.BATCH_SIZE,
        "learning_rate": args.lr or C.LEARNING_RATE,
        "max_length": C.MAX_LENGTH,
        "seed": args.seed if args.seed is not None else C.SEED,
        "cihaz": str(cihaz),
        "ascii_cogaltma": cogalt,
        "train_kayit": len(train_satir),
        "egitilebilir_parametre": egitilen,
        "toplam_parametre": toplam,
        "en_iyi_epoch": en_iyi_epoch,
        "en_iyi_val_ortalama_f1": en_iyi_f1,
        "gorevler": {"kategori": C.NUM_LABELS, "intent": C.NUM_INTENTS, "oncelik": C.NUM_PRIORITIES},
        "gecmis": gecmis,
    }
    (C.MODEL_DIR / "egitim_ozeti.json").write_text(
        json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nSONRAKI ADIM: python -m src.evaluate")


def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 4a -- BERTurk + LoRA egitimi")
    ap.add_argument("--epochs", type=int, help=f"varsayilan {C.NUM_EPOCHS}")
    ap.add_argument("--lr", type=float, help=f"varsayilan {C.LEARNING_RATE}")
    ap.add_argument("--no-lora", action="store_true", help="tam fine-tuning yap")
    ap.add_argument("--seed", type=int,
                    help=f"tohum; varsayilan {C.SEED}. Varyans olcumu icin "
                         f"farkli tohumlarla tekrar calistirilir.")
    ap.add_argument("--no-augment", action="store_true",
                    help="ASCII katlanmis kopyalari EKLEME (kiyas icin)")
    ap.add_argument("--device", choices=["mps", "cpu"], help="varsayilan: varsa mps")
    egit(ap.parse_args())


if __name__ == "__main__":
    main()
