"""
Adim 8 — Embedding tabanli benzerlik tespiti.

Kullanicinin yazdigi bir cumleye, egitim havuzundaki hangi kayitlarin
ANLAMSAL olarak yakin oldugunu bulur ve bunlarin kategori dagilimini
raporlar: "Bu cumleye benzer 18 kayit bulundu: %61 İstasyon Mekanik,
%22 Elektrik/Enerji, %17 Güvenlik/Emniyet".

YONTEM: ayri bir embedding modeli KURULMADI. Zaten yuklu olan BERTurk+LoRA
cok basli siniflandirma modelinin kendi ic temsili (govde'nin [CLS] token
ciktisi -- CokBaslikliSiniflandirici.temsil ile ayni temsil) kullaniliyor.
Bu model siniflandirma icin fine-tune edildigi icin ic temsili kategoriye
gore anlamli sekilde kumelenmis olmasi beklenir -- bu varsayim KOR KOR kabul
edilmedi, olculdu (bkz. config.SIMILARITY_THRESHOLD).

Corpus embedding'leri LIFESPAN SIRASINDA bir kez hesaplanir (bkz.
backend/main.py), diske ONBELLEKLENMEZ: ~1700 kayit icin birkac saniye surer,
ekstra bir dosya/onbellek gecerliligi sorunu yonetmekten daha basit.

Kullanim (programatik, backend tarafindan cagrilir):
    from src import similarity
    corpus = similarity.corpus_hazirla(model, tokenizer, cihaz)
    benzer = similarity.benzer_bul(sorgu_metni, model, tokenizer, cihaz, corpus)
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass

import numpy as np
import torch

from src import config as C


@dataclass
class Corpus:
    metinler: list[str]
    kategoriler: list[str]
    embedding: np.ndarray   # (N, 768), L2-normalize edilmis


def _embed(metinler: list[str], model, tokenizer, cihaz, batch: int = 64) -> np.ndarray:
    """CokBaslikliSiniflandirici.govde'den [CLS] temsili cikarir.

    Eskiden BertForSequenceClassification'in pooler_output'u kullaniliyordu;
    cok basli mimariye gecince siniflandirma basliklarinin kendisi de artik
    pooler yerine dogrudan [CLS] gizli durumunu kullaniyor (bkz.
    CokBaslikliSiniflandirici.temsil) -- benzerlik de ayni temsili kullanmali,
    aksi halde "modelin ic temsili" iddiasi gercegi yansitmaz.
    """
    govde = model.govde
    govde.eval()
    parcalar = []
    with torch.no_grad():
        for i in range(0, len(metinler), batch):
            grup = metinler[i:i + batch]
            enc = tokenizer(grup, truncation=True, padding=True,
                            max_length=C.MAX_LENGTH, return_tensors="pt").to(cihaz)
            cikti = govde(**enc)
            parcalar.append(cikti.last_hidden_state[:, 0].cpu().numpy())
    E = np.concatenate(parcalar).astype(np.float32)
    E /= np.linalg.norm(E, axis=1, keepdims=True).clip(min=1e-8)
    return E


def corpus_hazirla(model, tokenizer, cihaz) -> Corpus:
    """Egitim havuzunun (clean.csv) tamami icin embedding hesaplar.

    clean.csv kullanilir cunku bolunmemis TAM havuzdur (gold DAHIL DEGIL --
    clean.csv preprocess.py'nin cikardigi, gold'un hic girmedigi dosya).
    """
    if not C.CLEAN_FILE.exists():
        return Corpus([], [], np.zeros((0, 768), dtype=np.float32))
    with C.CLEAN_FILE.open(encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    metinler = [r["metin"] for r in satirlar]
    kategoriler = [r["kategori"] for r in satirlar]
    E = _embed(metinler, model, tokenizer, cihaz)
    return Corpus(metinler, kategoriler, E)


def benzer_bul(sorgu: str, model, tokenizer, cihaz, corpus: Corpus) -> dict:
    """Sorguya en yakin kayitlari bulur, kategori dagilimini doner."""
    if not corpus.metinler:
        return {"toplam_bulunan": 0, "gosterilen": 0, "dagilim": [], "ornekler": []}

    q = _embed([sorgu], model, tokenizer, cihaz)[0]        # (768,)
    skorlar = corpus.embedding @ q                          # cosine (L2-normalize)

    esik_ustu = np.where(skorlar >= C.SIMILARITY_THRESHOLD)[0]
    sirali = esik_ustu[np.argsort(-skorlar[esik_ustu])]
    gosterilecek = sirali[:C.SIMILARITY_MAX_SONUC]

    kategori_sayim = Counter(corpus.kategoriler[i] for i in sirali)
    toplam = len(sirali)
    dagilim = [
        {
            "kategori": k,
            "ad": C.DISPLAY_NAME[k],
            "renk": C.CATEGORY_COLOR[k],
            "sayi": n,
            "oran": n / toplam,
        }
        for k, n in kategori_sayim.most_common()
    ]

    ornekler = [
        {
            "metin": corpus.metinler[i],
            "kategori": corpus.kategoriler[i],
            "benzerlik": float(skorlar[i]),
        }
        for i in gosterilecek
    ]

    return {
        "esik": C.SIMILARITY_THRESHOLD,
        "toplam_bulunan": toplam,
        "gosterilen": len(gosterilecek),
        "dagilim": dagilim,
        "ornekler": ornekler,
    }
