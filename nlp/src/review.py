"""
Adim 2a-2 — Seed / gold kalite triyaji.

Uretilen bildirimleri otomatik tarar ve SUPHELI olanlari isaretler. Amac
176 satiri sirayla okumak yerine sadece sorunlu olanlara bakmaktir.

Kontroller:
  DUP     birebir tekrar
  BENZER  baska bir bildirime cok benziyor (near-duplicate, AYNI kategoride)
  SINIR   baska KATEGORIDEKI bir bildirime cok benziyor -- etiket tutarsizligi,
          biri muhtemelen yanlis kategoride (taksonomi sinir sorunu)
  UZUNLUK stilin kelime araligi disinda
  KOD     ekipman kodu yogunlugu kategori genelinde fazla
  SIZINTI kategori adini acikca soyluyor
  YABANCI Turkce olmayan kelime supheli (q/w/x harfi veya Turkce'de gecmeyen
          digraf). Dar bir kural -- kapsamli degil, bkz. koddaki not.
  (aksan-dusuk oranı artik isaretli SAYILMIYOR, sadece kategori ozetinde
   bilgi amacli raporlanir — klavye aliskanligi gercek hayatta normaldir)
  ISTASYON  ayni istasyon adi kategoride cok tekrar ediyor

Kullanim:
    python -m src.review                    # ikisini de tara
    python -m src.review --file gold
    python -m src.review --only-flagged     # sadece isaretlileri yazdir
    python -m src.review --csv              # review.csv olarak da kaydet
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from src import config as C

# Stil basina beklenen kelime araligi (config'teki tanimlarla uyumlu)
STYLE_WORD_RANGE = {
    "standart": (8, 18),
    "devrik": (4, 9),
    "devrik_kisa": (4, 9),      # eski isim, geriye donuk uyum
    "yazim_yanlisi": (5, 14),
    "cok_kisa": (3, 6),
}

# Kategori adini ele veren kelimeler
LEAK_WORDS = {
    "arac_tren": ["tren arizasi", "arac arizasi"],
    "istasyon_mekanik": ["mekanik ariza", "mekanik sorun"],
    "elektrik_enerji": ["elektrik arizasi", "enerji arizasi"],
    "yazilim_sistem": ["yazilim", "sistem arizasi", "yazilimsal"],
    "guvenlik_emniyet": ["guvenlik arizasi", "guvenlik sorunu", "emniyet sorunu"],
    "altyapi_insaat": ["altyapi sorunu", "insaat sorunu"],
    "yolcu_operasyon": ["operasyonel sorun", "operasyon arizasi"],
    "temizlik_cevre": ["temizlik sorunu", "temizlik problemi"],
}

EQUIP_CODE = re.compile(r"\b[A-ZĞÜŞİÖÇ]{2,4}[-\s]?\d{1,3}\b")

# --- YABANCI kelime tespiti ---------------------------------------------------
# Turk alfabesinde q, w, x YOKTUR -- bu harfleri iceren kelime ya yabanci ya da
# yazim artigi. Ek olarak Turkce yaziminda pratikte gecmeyen birkac digraf.
#
# NOT (19 Agu 2026): bu DAR kural bilincli bir tercih. Once daha genel iki
# yontem denendi ve ikisi de basarisiz oldu:
#   - Projenin kendi metninden bigram sozlugu cikarmak: 1600 kayitta 355 yanlis
#     alarm (referans korpus Turkce'nin bigram uzayini kapsayamiyor; "nesne",
#     "açma", "sessiz" gibi dogru kelimeler isaretlendi).
#   - Genis digraf listesi (sh, th, ph, ay...): "şüpheli", "Kağıthane",
#     "aydınlatma" gibi Turkce kelimeleri yakaliyor.
#   - BERTurk tokenizer parca sayisi: yabanci kelimeyi ASCII'ye katlanmis
#     Turkce'den ayirt edemiyor ("baggage" 3 parca, "asansor" da 3 parca).
# Dar kural 1600 kayitta 0 yanlis alarm veriyor ama KAPSAMLI DEGIL -- orn.
# "baggage" bu kurala takilmaz, elle okumayla bulundu. Bayrak "sil" degil
# "bak" anlamindadir: "switch", "wifi" gibi kelimeler Turkce teknik jargonda
# da kullanilabiliyor.
TR_DISI_HARF = set("qwxQWX")
YABANCI_DIGRAF = ("ck", "gh", "ea", "oo")


def yabanci_kelimeler(metin: str) -> list[str]:
    bulunan = []
    for kelime in re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜ]+", metin):
        if len(kelime) < 4:
            continue
        low = kelime.lower()
        if set(kelime) & TR_DISI_HARF or any(d in low for d in YABANCI_DIGRAF):
            bulunan.append(kelime)
    return bulunan

TR_CHARS = set("çğıöşüÇĞİÖŞÜ")

_ASCII_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _strip_diacritics(word: str) -> str:
    return word.translate(_ASCII_MAP)


def _build_diacritic_vocab() -> dict[str, str]:
    """Projenin kendi Turkce metninden (kategori aciklamalari + istasyon
    adlari) 'dogru yazim' sozlugu cikarir: ascii_hali -> doğru_hali.

    Boylece sabit bir Turkce sozluk elle bakim gerektirmez; proje buyudukce
    kendi kendine genisler. Sadece 4+ harfli ve en az bir aksanli harf iceren
    kelimeler alinir (kisa kelimelerde yanlis eslesme riski yuksek).
    """
    vocab: dict[str, str] = {}
    texts = list(C.SLOT_VALUES.get("istasyon", []))
    for cat in C.CATEGORIES.values():
        texts.append(cat["scope"])
        texts.append(cat["exclude"])
        texts.append(cat["display"])

    for text in texts:
        for word in re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜ]+", text):
            if len(word) < 4 or not (set(word) & TR_CHARS):
                continue
            ascii_form = _strip_diacritics(word).lower()
            if ascii_form != word.lower():
                vocab.setdefault(ascii_form, word)
    return vocab


DIACRITIC_VOCAB = _build_diacritic_vocab()


def normalize(text: str) -> str:
    """Karsilastirma icin: kucult, aksani kaldir, noktalamayi at."""
    t = text.lower()
    t = t.translate(str.maketrans("çğıöşü", "cgiosu"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return " ".join(t.split())


def similarity(a: str, b: str) -> float:
    """Iki normalize metnin benzerligi. SIMETRIKTIR: similarity(a,b) her zaman
    similarity(b,a) ile aynidir.

    SequenceMatcher tek basina uzunluk farkini fazla cezalandiriyor: ayni
    seyi soyleyen kisa ve uzun iki cumle dusuk skor aliyor. Kelime kumesi
    ortusmesini (Jaccard) de olcup ikisinin buyugunu aliyoruz.

    NOT: SequenceMatcher argüman sirasina duyarlidir (autojunk sezgiseli
    nedeniyle) -- olculdu: bir cift icin (a,b) 0.8511, (b,a) 0.8298 veriyordu,
    yani 0.85 esiginin iki yaninda. Bu, ayni ciftin nerede karsilastirildigina
    gore farkli karar almasina yol aciyordu: generate_data (yeni, mevcut)
    sirasiyla cagirip kabul ederken, preprocess (mevcut, yeni) sirasiyla
    cagirip ayni cifti near-duplicate sayiyordu. Sizinti savunmasinin tamami
    bu esige dayandigi icin girdileri once kanonik siraya sokuyoruz.
    """
    a, b = sorted((a, b))
    seq = SequenceMatcher(None, a, b).ratio()
    wa, wb = set(a.split()), set(b.split())
    jac = len(wa & wb) / max(1, len(wa | wb))
    return min(1.0, max(seq, jac / C.NEAR_DUP_JACCARD * C.NEAR_DUP_THRESHOLD))


def load(path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def analyze(records: list[dict]) -> tuple[list[dict], dict]:
    norms = [normalize(r["metin"]) for r in records]

    # birebir tekrar
    norm_count = Counter(norms)

    # near-duplicate: ayni kategori icinde karsilastir
    by_cat: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        by_cat[r["kategori"]].append(i)

    similar_to: dict[int, tuple[int, float]] = {}
    for idxs in by_cat.values():
        for a_pos, i in enumerate(idxs):
            for j in idxs[a_pos + 1:]:
                ratio = similarity(norms[i], norms[j])
                if ratio >= C.NEAR_DUP_THRESHOLD:
                    if ratio > similar_to.get(j, (0, 0.0))[1]:
                        similar_to[j] = (i, ratio)

    # SINIR: kategoriler ARASI near-duplicate. Neredeyse ayni metnin iki farkli
    # etikette olmasi modele celiskili sinyal verir; biri muhtemelen yanlis
    # kategoride. Bu kontrol olmadan araç bu hata turunu hic goremiyordu --
    # gold'da yanlis kategorili bir kayit ancak sans eseri "uzunluk" bayragiyla
    # yakalanmisti. Kategori ICI karsilastirmadan ayri tutuluyor cunku burada
    # sorun tekrar degil, ETIKET TUTARSIZLIGI.
    conflict_with: dict[int, tuple[int, float]] = {}
    kategoriler = list(by_cat)
    for a_pos, cat_a in enumerate(kategoriler):
        for cat_b in kategoriler[a_pos + 1:]:
            for i in by_cat[cat_a]:
                for j in by_cat[cat_b]:
                    ratio = similarity(norms[i], norms[j])
                    if ratio >= C.CLUSTER_THRESHOLD:
                        for x, y in ((i, j), (j, i)):
                            if ratio > conflict_with.get(x, (0, 0.0))[1]:
                                conflict_with[x] = (y, ratio)

    # kategori bazli kod ve istasyon istatistigi
    code_share: dict[str, float] = {}
    station_top: dict[str, tuple[str, int]] = {}
    for cat, idxs in by_cat.items():
        with_code = sum(1 for i in idxs if EQUIP_CODE.search(records[i]["metin"]))
        code_share[cat] = with_code / max(1, len(idxs))

        st_counter: Counter = Counter()
        for i in idxs:
            low = records[i]["metin"].lower()
            for st in C.SLOT_VALUES["istasyon"]:
                if st.lower() in low:
                    st_counter[st] += 1
        station_top[cat] = st_counter.most_common(1)[0] if st_counter else ("-", 0)

    rows = []
    for i, r in enumerate(records):
        metin, cat, stil = r["metin"], r["kategori"], r.get("stil", "standart")
        flags = []

        if norm_count[norms[i]] > 1:
            flags.append("DUP")

        if i in similar_to:
            j, ratio = similar_to[i]
            flags.append(f"BENZER({ratio:.2f}->#{j})")

        if i in conflict_with:
            j, ratio = conflict_with[i]
            flags.append(f"SINIR({ratio:.2f}->#{j} {records[j]['kategori']})")

        nwords = len(metin.split())
        lo, hi = STYLE_WORD_RANGE.get(stil, (3, 25))
        if not (lo <= nwords <= hi):
            flags.append(f"UZUNLUK({nwords}, beklenen {lo}-{hi})")

        low_norm = normalize(metin)
        for w in LEAK_WORDS.get(cat, []):
            if normalize(w) in low_norm:
                flags.append("SIZINTI")
                break

        yabanci = yabanci_kelimeler(metin)
        if yabanci:
            flags.append(f"YABANCI({','.join(yabanci)})")

        # NOT: Aksan dusurme (guvenlik->guvenlik, Sisli->Sisli) gercek hayatta
        # cok yaygin bir klavye/yazim aliskanligidir, sadece "yazim_yanlisi"
        # stiline ozgu degildir. Bunu "hata" olarak isaretlemek yerine sadece
        # bilgi amacli sayiyoruz (asagida kategori ozetinde raporlanir),
        # isaretli listesine dahil etmiyoruz.
        ascii_words = []
        for word in re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜ]+", metin):
            ascii_form = _strip_diacritics(word).lower()
            correct = DIACRITIC_VOCAB.get(ascii_form)
            if correct and word != correct and word.lower() != correct.lower():
                ascii_words.append(word)

        rows.append({
            "no": i,
            "kategori": cat,
            "stil": stil,
            "kelime": nwords,
            "kod": "E" if EQUIP_CODE.search(metin) else "",
            "bayrak": " ".join(flags),
            "metin": metin,
            "aksan_dusuk": ",".join(ascii_words),   # bilgi amacli, isaretli sayilmiyor
        })

    # kategori bazli aksan-dusurme orani (bilgi amacli, "sorun" degil)
    ascii_share: dict[str, float] = {}
    for cat, idxs in by_cat.items():
        with_drop = sum(1 for i in idxs if rows[i]["aksan_dusuk"])
        ascii_share[cat] = with_drop / max(1, len(idxs))

    stats = {
        "code_share": code_share, "station_top": station_top, "by_cat": by_cat,
        "ascii_share": ascii_share,
    }
    return rows, stats


def report(name: str, rows: list[dict], stats: dict, only_flagged: bool) -> None:
    total = len(rows)
    flagged = [r for r in rows if r["bayrak"]]

    print(f"\n{'=' * 78}")
    print(f"{name.upper()}  —  {total} kayit, {len(flagged)} isaretli "
          f"(%{100 * len(flagged) / max(1, total):.0f})")
    print("=" * 78)

    print("\nKATEGORI SAGLIGI")
    print(f"{'kategori':<28} {'adet':>5} {'kod%':>6} {'aksan-dusuk%':>13} {'en cok istasyon':>28}")
    for cat in C.CATEGORY_KEYS:
        idxs = stats["by_cat"].get(cat, [])
        if not idxs:
            continue
        share = stats["code_share"][cat]
        ascii_pct = stats["ascii_share"][cat]
        st, cnt = stats["station_top"][cat]
        warn = "  <-- KOD FAZLA" if share > 0.40 else ""
        print(f"{C.DISPLAY_NAME[cat]:<28} {len(idxs):>5} {share * 100:>5.0f}% "
              f"{ascii_pct * 100:>12.0f}% {st + ' x' + str(cnt):>28}{warn}")
    print("(aksan-dusuk%: 'guvenlik' gibi klavye aliskanligiyla dusen Turkce "
          "harfler — gercek hayatta normal, sorun DEGIL, sadece bilgi amacli)")

    shown = flagged if only_flagged else rows
    print(f"\n{'BILDIRIMLER' if not only_flagged else 'ISARETLI BILDIRIMLER'}")
    current = None
    for r in shown:
        if r["kategori"] != current:
            current = r["kategori"]
            print(f"\n--- {C.DISPLAY_NAME[current]} ---")
        mark = "!!" if r["bayrak"] else "  "
        print(f"{mark} #{r['no']:<3} [{r['stil']:<13}] {r['metin']}")
        if r["bayrak"]:
            print(f"       -> {r['bayrak']}")

    if flagged:
        print(f"\nOZET: {len(flagged)} kayda bakman yeterli. Gerisi temiz gorunuyor.")
    else:
        print("\nOZET: otomatik kontroller temiz. Gold setini yine de elle oku.")


# Taranabilir dosyalar. Yollar config'ten gelir, burada yeniden tanimlanmaz.
FILES = {
    "seed": C.SEED_FILE,
    "gold": C.GOLD_FILE,
    "amplified": C.RAW_FILE,     # Adim 2b cikti dosyasi
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed/gold/amplified kalite triyaji")
    ap.add_argument("--file", choices=list(FILES), help="sadece birini tara")
    ap.add_argument("--only-flagged", action="store_true")
    ap.add_argument("--csv", action="store_true", help="review_<ad>.csv olarak kaydet")
    args = ap.parse_args()

    # amplified (Adim 2b ciktisi) varsayilan taramaya girmez: 1600 kayitlik
    # dosyanin raporu seed/gold raporunu bogar, istenince acikca secilir.
    targets = [args.file] if args.file else ["seed", "gold"]
    for name in targets:
        path = FILES[name]
        records = load(path)
        if not records:
            print(f"\n{name}: dosya bulunamadi veya bos ({path})")
            continue

        rows, stats = analyze(records)
        report(name, rows, stats, args.only_flagged)

        if args.csv:
            out = C.SEED_DIR / f"review_{name}.csv"
            with out.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(
                    f, fieldnames=["no", "kategori", "stil", "kelime", "kod",
                                   "bayrak", "metin", "karar"]
                )
                w.writeheader()
                for r in rows:
                    w.writerow({**r, "karar": ""})
            print(f"\n-> CSV yazildi: {out}  ('karar' sutununa tut/duzelt/sil yaz)")


if __name__ == "__main__":
    main()
