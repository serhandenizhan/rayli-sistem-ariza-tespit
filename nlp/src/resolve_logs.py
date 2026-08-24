"""
Adim 8 eki -- kategorisiz "Yanlis" kayitlarini egitim oncesi coz.

Kullanici arayuzde bir tahmine "Yanlis" deyip dogru kategoriyi secmeden
"atla"ya basarsa, kayit dogrulandi=0 + dogru_kategori=NULL olarak kalir.
Bu script, egitime/`export`a girmeden once bu kayitlari kapatmak icin:

  1) O metni GUNCEL model ile yeniden tahmin eder (tum olasilik dagilimi).
  2) Kullanicinin zaten reddettigi kategoriyi listeden CIKARIR (aksi halde
     ayni yanlis cevabi tekrar onaya sunmus oluruz).
  3) Kalanlar arasindaki en olasi kategoriyi ONERI olarak gosterir.
  4) Kullaniciya sorar: Enter=oneriyi kabul et, kategori anahtari yaz=elle
     duzelt, s=simdilik atla.

Kabul/duzeltme, digerleriyle ayni yerde (dogru_kategori) saklanir, yani
`GET /logs/export` bu kayitlari da normal sekilde disari alir.

Kullanim:
    python -m src.resolve_logs
"""

from __future__ import annotations

from src import config as C
from src import db
from src.evaluate import model_yukle, tahmin_et
from src.train import cihaz_sec


def _oneri_sirala(olasiliklar: list[float], haric: str) -> list[tuple[str, float]]:
    siralı = sorted(
        ((C.ID2LABEL[i], p) for i, p in enumerate(olasiliklar) if C.ID2LABEL[i] != haric),
        key=lambda x: x[1],
        reverse=True,
    )
    return siralı


def main() -> None:
    db.init()
    kayitlar = db.kategorisiz_yanlislari_getir()
    if not kayitlar:
        print("Cozulecek kategorisiz kayit yok.")
        return

    print(f"{len(kayitlar)} kategorisiz 'Yanlis' kayit bulundu. Model yukleniyor...")
    cihaz = cihaz_sec()
    model, tokenizer, _ = model_yukle(cihaz)

    cozulen, atlanan = 0, 0
    for r in kayitlar:
        reddedilen = r["kategori"]
        _, _, olasiliklar = tahmin_et(
            model, tokenizer, [{"metin": r["metin"], "label": "0"}], cihaz
        )
        siralı = _oneri_sirala(olasiliklar[0], haric=reddedilen)
        oneri_kategori, oneri_olasilik = siralı[0]

        print("\n" + "-" * 60)
        print(f"[{r['id']}] {r['metin']}")
        print(f"  reddedilen (ilk tahmin): {C.DISPLAY_NAME[reddedilen]}")
        print(f"  yeni oneri:              {C.DISPLAY_NAME[oneri_kategori]} "
              f"({oneri_olasilik:.1%})")
        print("  diger secenekler: " + ", ".join(
            f"{C.DISPLAY_NAME[k]} ({p:.1%})" for k, p in siralı[1:4]
        ))

        cevap = input(
            "  [Enter]=oneriyi kabul et | kategori anahtari yaz | s=atla: "
        ).strip()

        if cevap == "s":
            atlanan += 1
            continue
        if cevap == "":
            secilen = oneri_kategori
        elif cevap in C.CATEGORY_KEYS:
            secilen = cevap
        else:
            print(f"  Bilinmeyen kategori '{cevap}', bu kayit atlandi.")
            atlanan += 1
            continue

        db.dogrula(r["id"], dogru=False, duzeltilmis_kategori=secilen)
        cozulen += 1

    print(f"\nBitti: {cozulen} kayit kategorize edildi, {atlanan} kayit hala kategorisiz.")


if __name__ == "__main__":
    main()
