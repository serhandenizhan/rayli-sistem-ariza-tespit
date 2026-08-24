"""
Adim 7 — Yapisal cikarim (incident parsing).

Siniflandirmayi tek bir kategoriden yapisal bir kayda cikarir:

    "M4 Ünalan'da yürüyen merdiven çok ses yapıyor"
    -> {line: "M4", station: "Ünalan", equipment: "yürüyen merdiven",
        symptom: "anormal ses"}

ILK SURUM KURALLI. Plandaki sira: (1) kurallı extraction, (2) NER/token
classification, (3) gerekirse LLM fallback. Kurallı katmanla baslanmasinin
sebebi: istasyon adlari ve ekipman terimleri zaten config'de sayili, yani
tanima probleminin buyuk kismi sozluk eslesmesi. Kurallı katmanin nerede
yetersiz kaldigini OLCMEDEN NER/LLM'e gecmek, cozulup cozulmedigini
bilmedigimiz bir soruna model atmak olurdu.

Eslesme aksana duyarsiz: veride hem "asansör" hem "asansor" var (yazim_yanlisi
stili), ikisi de ayni ekipmana isaret ediyor.

Kullanim:
    python -m src.extract "M4 Ünalan'da yürüyen merdiven ses yapıyor"
    python -m src.extract --degerlendir      # alan bazli precision/recall
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata

from src import config as C

# ---------------------------------------------------------------------------
# Normalizasyon
# ---------------------------------------------------------------------------

_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def normalize(metin: str) -> str:
    """Kucuk harf + aksansiz. Eslesme bunun uzerinden yapilir."""
    t = metin.translate(_ASCII).lower()
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch))


# Sozlukleri bir kez normalize edip hazir tut. Uzun ifadeler once denenecek
# ("peron kapisi" -> "kapi"dan once), yoksa kisa terim uzunu golgeler.
_ISTASYON = sorted(
    ((normalize(s), s) for s in C.STATIONS), key=lambda x: -len(x[0])
)
# Ekipman eslesme tablosu: (aranan_normalize_hali, dondurulecek_kanonik_ad).
# Hem kanonik adlarin kendisi hem takma adlar aranir; ikisi de KANONIK ada
# cozulur, boylece "trensformatörü" ve "trafo" ayni cikti verir.
_EKIPMAN = sorted(
    [(normalize(e), e) for e in C.EQUIPMENT]
    + [(normalize(v), k) for v, k in C.EQUIPMENT_ALIASES.items()],
    key=lambda x: -len(x[0]),
)
_HAT = re.compile(C.LINE_PATTERN, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Alan cikarimi
# ---------------------------------------------------------------------------

def hat_bul(metin: str) -> str | None:
    """Hat kodu (M4, T1, Marmaray...).

    DIKKAT yanlis pozitif kaynagi: "T3 trensformatörü" gibi ifadelerde T3 hat
    degil ekipman etiketi. Bu yuzden T/F kodlarinin ardindan ekipman kelimesi
    geliyorsa hat sayilmiyor.
    """
    for m in _HAT.finditer(metin):
        kod = m.group(0)
        if kod[0].upper() in "TF" and len(kod) <= 2:
            kalan = normalize(metin[m.end():m.end() + 20])
            if re.match(r"\s*(trafo|transformator|trensformator|pano)", kalan):
                continue
        return "Marmaray" if kod.lower() == "marmaray" else kod.upper()
    return None


def istasyon_bul(metin: str) -> str | None:
    n = normalize(metin)
    for norm_ad, ad in _ISTASYON:
        if norm_ad in n:
            return ad
    return None


def ekipman_bul(metin: str, konumu_disla: bool = True) -> str | None:
    n = _konumu_maskele(metin) if konumu_disla else normalize(metin)
    for norm_ad, ad in _EKIPMAN:
        if norm_ad in n:
            return ad
    return None


def belirti_bul(metin: str) -> str | None:
    n = normalize(metin)
    for desen, kanonik in C.SYMPTOMS:
        if re.search(desen, n):
            return kanonik
    return None


def konum_bul(metin: str) -> str | None:
    """Istasyon ICINDEKI konum: "2 numarali giris", "turnike kati", "1. peron".

    Istasyon adindan AYRIDIR ve onunla birlikte anlam kazanir: Metro
    Istanbul'un kendi ariza kayitlarinda da hat + istasyon + konum + ekipman
    ayri alanlar olarak tutuluyor, cunku "Kadikoy'deki merdiven" yeterli bir
    is emri degil -- hangi merdiven oldugu gerekiyor.

    Numarali kaliplar once denenir ("2 numarali giris"), cunku daha spesifik
    ve daha bilgilendiricidirler.
    """
    n = normalize(metin)
    for desen, bicim in C.LOCATION_PATTERNS:
        m = re.search(desen, n)
        if m:
            try:
                # Yakalanan gruplar normalize edilmis metinden geliyor, yani
                # aksansiz. Ciktida dogru Turkce yazim gosterilsin diye geri
                # ceviriliyor ("giris" -> "giriş").
                gruplar = [C.LOCATION_KELIME_DUZELT.get(g, g) for g in m.groups()]
                return bicim.format(*gruplar) if gruplar else bicim
            except (IndexError, KeyError):
                return bicim
    return None


def _konumu_maskele(metin: str) -> str:
    """Konum ifadesini metinden cikarir.

    Gerekce: "turnikelerin oradaki merdiven calismiyor" cumlesinde ekipman
    MERDIVEN, turnike ise konum belirtiyor. Ekipman aramasi ham metinde
    yapilirsa "turnike" once eslesir ve yanlis ekipman doner. Once konumu
    bulup o parcayi maskeleyerek bu karisiklik onlenir.
    """
    n = normalize(metin)
    for desen, _ in C.LOCATION_PATTERNS:
        m = re.search(desen, n)
        if m:
            return n[:m.start()] + " " + n[m.end():]
    return n


# Sebep bildiren baglaclar. Bunlardan biri gecmezse root_cause DOLDURULMAZ --
# halusinasyon engelleyici kuralin uygulanisi budur: kullanici "galiba motoru
# yanmis" dediginde model buna teknik teshis koymamali, cunku bu kullanicinin
# TAHMINI. Sadece cumlede acikca "X yuzunden Y" yapisi varsa sebep yazilir.
_SEBEP_DESENI = re.compile(
    r"([^,.;:]{3,60}?)\s*(?:yuzunden|nedeniyle|sebebiyle|dolayi|kaynakli|"
    r"oldugu icin|kesildigi icin|olmadigi icin)"
)

# "galiba", "sanirim" gibi ifadeler kullanicinin emin OLMADIGINI gosterir;
# bunlar varsa sebep cikarilmaz.
_SPEKULASYON = re.compile(
    r"galiba|sanirim|herhalde|belki|olabilir|gibi geldi|zannedersem|heralde"
)


def sebep_bul(metin: str) -> str | None:
    """Bildirimde ACIKCA belirtilen kok sebebi doner, yoksa None.

    Model teknik teshis UYDURMAZ. "Yuruyen merdiven calismiyor" -> None
    (kullanici sebebi bilmiyor). "Elektrik kesildigi icin merdiven
    calismiyor" -> "elektrik kesildigi" (kullanici sebebi soyluyor).
    """
    n = normalize(metin)
    if _SPEKULASYON.search(n):
        return None
    m = _SEBEP_DESENI.search(n)
    if not m:
        return None
    sebep = m.group(1).strip(" ,.;:")
    # Cok kisa veya cok uzun yakalamalar guvenilir degil
    if not 3 <= len(sebep) <= 60:
        return None
    return sebep


def eksik_bilgi(alanlar: dict, kategori: str | None = None) -> list[str]:
    """Is emri acmak icin gereken ama bildirimde bulunmayan alanlar.

    Arayuz bunu kullanip kullaniciya soru sorar ("Hangi istasyondaki
    asansorde sorun var?"). Hangi alanin gerekli oldugu KATEGORIYE gore
    degisir: tren arizasinda istasyon zorunlu degil (tren hareket halinde),
    ama hat/sefer bilgisi onemli; istasyon ekipmaninda istasyon sart.
    """
    eksik = []
    if not alanlar.get("station"):
        eksik.append("station")
    if not alanlar.get("equipment"):
        eksik.append("equipment")
    # Konum sadece istasyon ekipmani icin anlamli: bir istasyonda ayni
    # ekipmandan birden fazla var ("hangi merdiven?"), trende yok.
    if kategori in ("mekanik_istasyon", "elektronik_sistemler") \
            and not alanlar.get("location"):
        eksik.append("location")
    if kategori == "arac_tren" and not alanlar.get("line"):
        eksik.append("line")
    return eksik


def cikar(metin: str, kategori: str | None = None) -> dict:
    """Bir bildirimden yapisal alanlari cikarir (kategori HARIC -- o modelden
    geliyor, bkz. backend/main.py)."""
    alanlar = {
        "line": hat_bul(metin),
        "station": istasyon_bul(metin),
        "location": konum_bul(metin),
        "equipment": ekipman_bul(metin),
        "symptom": belirti_bul(metin),
        "root_cause": sebep_bul(metin),
    }
    alanlar["missing_information"] = eksik_bilgi(alanlar, kategori)
    return alanlar


# ---------------------------------------------------------------------------
# Degerlendirme
# ---------------------------------------------------------------------------

EXTRACTION_GOLD = C.SEED_DIR / "extraction_gold.jsonl"
ALANLAR = ("line", "station", "equipment", "symptom")


def _ortusuyor(tahmin: str | None, gercek: str | None) -> bool:
    """Iki alan degeri "ayni seyi soyluyor mu".

    Birebir string esitligi fazla kati: gold "vagon kapısı" derken sistem
    "kapı" cikarabiliyor ve bu pratikte dogru cevap. Olcut: normalize edilmis
    hallerinden biri digerini iceriyorsa VEYA kelime ortusmesi varsa dogru.
    Bu olcut GEVSEK -- raporda bu acikca belirtilmeli.
    """
    if tahmin is None or gercek is None:
        return tahmin is None and gercek is None
    a, b = normalize(tahmin), normalize(gercek)
    if a in b or b in a:
        return True
    return bool(set(a.split()) & set(b.split()))


def degerlendir() -> dict:
    if not EXTRACTION_GOLD.exists():
        raise SystemExit(f"HATA: referans dosyasi yok: {EXTRACTION_GOLD}")

    kayitlar = [json.loads(s) for s in EXTRACTION_GOLD.open(encoding="utf-8")
                if s.strip()]
    print(f"Yapisal cikarim degerlendirmesi — {len(kayitlar)} elle etiketlenmis "
          f"bildirim\n")
    print("NOT: referans etiketler kurallar YAZILMADAN ONCE, sadece cumleler")
    print("okunarak olusturuldu. Tek etiketleyici -- mutlak degil, yon gosterir.\n")

    sonuc = {}
    print(f"{'alan':<12} {'destek':>7} {'TP':>4} {'FP':>4} {'FN':>4} "
          f"{'precision':>10} {'recall':>8} {'F1':>7}")

    for alan in ALANLAR:
        tp = fp = fn = 0
        for k in kayitlar:
            t = cikar(k["metin"])[alan]
            g = k[alan]
            if g is None and t is None:
                continue                      # dogru negatif, sayilmaz
            if g is not None and t is not None:
                if _ortusuyor(t, g):
                    tp += 1
                else:
                    fp += 1
                    fn += 1                   # yanlis deger: hem FP hem FN
            elif t is not None:               # gold bos, sistem uydurdu
                fp += 1
            else:                             # gold dolu, sistem kacirdi
                fn += 1

        destek = sum(1 for k in kayitlar if k[alan] is not None)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        sonuc[alan] = {"destek": destek, "tp": tp, "fp": fp, "fn": fn,
                       "precision": p, "recall": r, "f1": f1}
        not_ = "  <-- referansta hic ornek yok" if destek == 0 else ""
        print(f"{alan:<12} {destek:>7} {tp:>4} {fp:>4} {fn:>4} "
              f"{p:>10.3f} {r:>8.3f} {f1:>7.3f}{not_}")

    print("\nHATALAR (alan bazinda, en fazla 5):")
    for alan in ALANLAR:
        hatali = [
            (k["metin"], k[alan], cikar(k["metin"])[alan])
            for k in kayitlar
            if not _ortusuyor(cikar(k["metin"])[alan], k[alan])
        ]
        if not hatali:
            continue
        print(f"\n  {alan} ({len(hatali)} hata):")
        for metin, g, t in hatali[:5]:
            print(f"    gold={g!r}  tahmin={t!r}")
            print(f"      {metin[:72]}")

    return sonuc


def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 7 -- yapisal cikarim")
    ap.add_argument("metin", nargs="?", help="tek bir bildirim")
    ap.add_argument("--degerlendir", action="store_true",
                    help="alan bazli precision/recall raporu")
    args = ap.parse_args()

    if args.degerlendir:
        sonuc = degerlendir()
        yol = C.MODEL_DIR / "extraction_degerlendirme.json"
        yol.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n-> {yol}")
    elif args.metin:
        print(json.dumps(cikar(args.metin), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
