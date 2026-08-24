"""
Modelin kararina hangi kelimelerin katkida bulundugunu gosterir.

YONTEM: gradient x input (saliency). Modelin tahmin ettigi sinifin skorunun,
girdi gomme (embedding) vektorlerine gore turevini alir ve bu turevi gomme
degerinin kendisiyle carpar. Sonucun normu, o token'in karara katkisidir.

NEDEN BU YONTEM:
  - Sozluk eslesmesi (metinde "elektrik" geciyor mu?) modelin kararini DEGIL,
    sadece kelimelerin varligini gosterir. Model baska bir sebeple karar vermis
    olabilir ve sozluk bunu goremez -- yani "aciklama" degil, tahmindir.
  - Integrated Gradients daha saglam bir yontemdir ama bir tahmin icin ~20
    ileri gecis gerektirir; cikarim suresi 14 ms'den ~280 ms'ye cikardi.
  - gradient x input TEK geri yayilimla calisir (~15 ms ek maliyet) ve gercek
    model sinyalini kullanir. Bu proje icin dogru denge.

SINIRI (rapora yazilmali): gradient tabanli aciklamalar yerel dogrusal bir
yaklasikliktir; "model bu token'a duyarli" der, "model bu yuzden karar verdi"
demez. Yine de sozluk eslesmesinden nitelik olarak farklidir ve yanlis
siniflandirmalarin sebebini aramak icin gercekten kullanislidir.
"""

from __future__ import annotations

import re

import torch

from src import config as C

# Katkisi olculse de aciklama olarak gosterilmesi anlamsiz olan token'lar.
OZEL_TOKENLAR = {"[CLS]", "[SEP]", "[PAD]", "[UNK]"}

# Tek basina bilgi tasimayan kisa kelimeler; listede olmalari katkilarinin
# olculmedigi anlamina gelmez, sadece kullaniciya gosterilmezler.
ETKISIZ = {
    "ve", "ile", "de", "da", "bir", "bu", "su", "o", "icin", "gibi", "ama",
    "cok", "daha", "en", "ki", "mi", "mu", "ne", "var", "yok",
}


def _birlestir(parcalar: list[str], skorlar: list[float]) -> list[tuple[str, float]]:
    """WordPiece parcalarini kelimelere birlestirir, skorlari toplar.

    BERTurk 'asansor'u ['asa','##ns','##or'] diye bolebiliyor; kullaniciya
    parca degil kelime gostermek gerekiyor. Kelimenin skoru parcalarinin
    toplamidir -- ortalama alsaydik cok parcali (yani modelin zorlandigi)
    kelimeler haksiz yere zayif gorunurdu.
    """
    kelimeler: list[tuple[str, float]] = []
    for parca, skor in zip(parcalar, skorlar):
        if parca in OZEL_TOKENLAR:
            continue
        if parca.startswith("##") and kelimeler:
            onceki_ad, onceki_skor = kelimeler[-1]
            kelimeler[-1] = (onceki_ad + parca[2:], onceki_skor + skor)
        else:
            kelimeler.append((parca, skor))
    return kelimeler


def kanit_cikar(model, tokenizer, metin: str, cihaz,
                gorev: str = "kategori", ust_n: int = 5) -> list[str]:
    """Karara en cok katkida bulunan kelimeleri (yuksekten dusuge) doner."""
    model.eval()
    enc = tokenizer(metin, truncation=True, padding="max_length",
                    max_length=C.MAX_LENGTH, return_tensors="pt").to(cihaz)

    # Gomme katmanina erisim: LoRA sarmalamasi altinda govde bir PeftModel
    # olabilir, o yuzden dogrudan modulu ariyoruz.
    govde = model.govde
    gomme_katmani = govde.get_input_embeddings()
    gomme = gomme_katmani(enc["input_ids"]).detach().clone().requires_grad_(True)

    cikti = govde(inputs_embeds=gomme, attention_mask=enc["attention_mask"])
    havuz = cikti.last_hidden_state[:, 0]
    logitler = model.basliklar[gorev](model.dropout(havuz))

    hedef = logitler.argmax(dim=-1)
    skor = logitler[0, hedef]
    model.zero_grad(set_to_none=True)
    skor.backward()

    if gomme.grad is None:                       # beklenmedik durum: sessiz kal
        return []

    # gradient x input, token basina L2 normu
    katki = (gomme.grad * gomme).sum(dim=-1).abs()[0].detach().cpu().tolist()
    parcalar = tokenizer.convert_ids_to_tokens(enc["input_ids"][0])

    kelimeler = _birlestir(parcalar, katki)
    kelimeler = [(k, s) for k, s in kelimeler
                 if k.lower() not in ETKISIZ and re.search(r"\w", k)]
    kelimeler.sort(key=lambda x: x[1], reverse=True)

    # Sadece ortalamanin ustunde katki yapanlari goster: her cumleden sabit
    # sayida kelime dondurmek, katkisi olmayanlari da "kanit" gibi gosterirdi.
    if not kelimeler:
        return []
    ortalama = sum(s for _, s in kelimeler) / len(kelimeler)
    secilen = [k for k, s in kelimeler[:ust_n] if s > ortalama]
    return secilen or [kelimeler[0][0]]
