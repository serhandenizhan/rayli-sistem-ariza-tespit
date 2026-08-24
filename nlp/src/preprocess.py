"""
Adim 3 — On isleme: temizlik, near-duplicate kumeleme, train/val/test bolme.

En kritik kisim KUMELEME. Cogaltilmis veri dogasi geregi birbirine benziyor;
rastgele bolersek ayni cumlenin bir varyasyonu train'e, digeri test'e duser ve
model ezberledigini "genelleme" gibi gosterir -- yani sahte yuksek dogruluk.
Bu yuzden once benzer kayitlar ayni kumeye toplanir, sonra KUMELER bolunur;
bir kumenin tum uyeleri hep ayni tarafta kalir.

Gold seti asla train/val'e karismaz. Ayri gold_test.csv olarak yazilir. Boylece
iki test metrigi raporlanir:
  - normal test  : cogaltilmis veriden ayrilmis, dagilimi train ile ayni
  - gold test    : bagimsiz uretilmis, elle gozden gecirilmis
Aradaki fark "sentetik veri ne kadar gercekci" sorusunun olculebilir cevabidir.

Kullanim:
    python -m src.preprocess
    python -m src.preprocess --include-seed     # seed.jsonl'i de egitime kat
    python -m src.preprocess --report-only      # dosya yazmadan sadece rapor
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict

from src import config as C
from src import review as R


# ---------------------------------------------------------------------------
# Yukleme
# ---------------------------------------------------------------------------

def load_jsonl(path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_pool(include_seed: bool) -> list[dict]:
    """Egitim havuzunu toplar. gold.jsonl BURAYA ASLA GIRMEZ."""
    # Uc boyutlu (kategori + intent + oncelik) havuz varsa o kullanilir.
    # relabeled.jsonl `src/relabel.py` ciktisidir ve yeni taksonomiyi tasir;
    # amplified.jsonl eski tek boyutlu uretimin ciktisidir ve geriye donuk
    # uyumluluk icin duruyor.
    relabel_yolu = C.RAW_DIR / "relabeled.jsonl"
    pool = load_jsonl(relabel_yolu)
    kaynak = "relabeled"
    if not pool:
        pool = load_jsonl(C.RAW_FILE)
        kaynak = "amplified"
    if not pool:
        raise SystemExit(
            f"HATA: egitim havuzu yok ({relabel_yolu} veya {C.RAW_FILE}).\n"
            f"Once calistir: python -m src.generate_data && python -m src.relabel"
        )
    if include_seed:
        # seed few-shot yemi olarak kullanildi, yani cogaltilmis kayitlar
        # onun turevleri olabilir. Kumeleme bu ortusmeyi zaten yakalayip ayni
        # tarafa koyacagi icin havuza katmak guvenli.
        seed = load_jsonl(C.SEED_FILE)
        pool = pool + seed
        kaynak = "amplified + seed"
    print(f"havuz: {len(pool)} kayit ({kaynak})")
    return pool


# ---------------------------------------------------------------------------
# Temizlik
# ---------------------------------------------------------------------------

def temizle(pool: list[dict]) -> tuple[list[dict], Counter]:
    """Bicimsel temizlik ve gecersiz kayitlarin atilmasi."""
    atilan = Counter()
    temiz: list[dict] = []
    gorulen: dict[str, str] = {}       # normalize metin -> kategori

    for r in pool:
        metin = " ".join(str(r.get("metin", "")).split())

        if not metin:
            atilan["bos"] += 1
            continue
        if not (C.MIN_CHARS <= len(metin) <= C.MAX_CHARS):
            atilan["uzunluk_disi"] += 1
            continue
        if r.get("kategori") not in C.CATEGORIES:
            atilan["gecersiz_kategori"] += 1
            continue

        norm = R.normalize(metin)
        if norm in gorulen:
            # Ayni metin iki FARKLI kategoride ise bu bir etiket cakismasidir:
            # model icin celiskili sinyal, ikisini de atmak en guvenlisi.
            if gorulen[norm] != r["kategori"]:
                atilan["etiket_cakismasi"] += 1
            else:
                atilan["birebir_tekrar"] += 1
            continue

        gorulen[norm] = r["kategori"]
        temiz.append({**r, "metin": metin, "_norm": norm})

    return temiz, atilan


# ---------------------------------------------------------------------------
# Near-duplicate kumeleme
# ---------------------------------------------------------------------------

class UnionFind:
    def __init__(self, n: int):
        self.ebeveyn = list(range(n))

    def bul(self, x: int) -> int:
        while self.ebeveyn[x] != x:
            self.ebeveyn[x] = self.ebeveyn[self.ebeveyn[x]]   # yol sikistirma
            x = self.ebeveyn[x]
        return x

    def birlestir(self, a: int, b: int) -> None:
        ka, kb = self.bul(a), self.bul(b)
        if ka != kb:
            self.ebeveyn[kb] = ka


def kumele(kayitlar: list[dict]) -> list[list[int]]:
    """Benzer kayitlari ayni kumeye toplar; kume indeks listeleri doner.

    Karsilastirma kategori ICINDE yapilir: farkli kategorideki iki kayit
    birbirine benzese bile ayni kumeye konmamali, yoksa kumeler kategorileri
    birbirine baglar ve katmanli bolme imkansizlasir. (Birebir ayni metnin
    iki kategoride olmasi zaten temizle() asamasinda elenmis durumda.)

    Olcut review.similarity (uretimle ayni fonksiyon) ama ESIK farkli:
    C.CLUSTER_THRESHOLD (0.80), uretimdeki C.NEAR_DUP_THRESHOLD (0.85) degil.
    Sebep config.py'de detayli: burada kacirmanin bedeli (metrigin sismesi)
    yanlis birlestirmenin bedelinden (kucuk cesitlilik kaybi) cok daha agir.
    """
    uf = UnionFind(len(kayitlar))

    kategori_indeksleri: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(kayitlar):
        kategori_indeksleri[r["kategori"]].append(i)

    for kategori, idxs in kategori_indeksleri.items():
        for a, i in enumerate(idxs):
            for j in idxs[a + 1:]:
                if R.similarity(kayitlar[i]["_norm"], kayitlar[j]["_norm"]) \
                        >= C.CLUSTER_THRESHOLD:
                    uf.birlestir(i, j)

    kumeler: dict[int, list[int]] = defaultdict(list)
    for i in range(len(kayitlar)):
        kumeler[uf.bul(i)].append(i)
    return list(kumeler.values())


# ---------------------------------------------------------------------------
# Bolme
# ---------------------------------------------------------------------------

def bol(kayitlar: list[dict], kumeler: list[list[int]],
        rng: random.Random) -> dict[str, list[int]]:
    """Kume butunlugunu koruyarak katmanli (kategori bazli) bolme.

    Her kategori kendi icinde bolunur, boylece sinif dengesi uc bolmede de
    korunur. Kumeler buyukten kucuge sirayla en "ac" bolmeye verilir: buyuk
    bir kume kucuk bir bolmeye dusup oranlari bozmasin diye.
    """
    hedef_oran = {"train": C.TRAIN_RATIO, "val": C.VAL_RATIO, "test": C.TEST_RATIO}
    bolmeler: dict[str, list[int]] = {"train": [], "val": [], "test": []}

    # Kumeleri kategoriye gore grupla (bir kume tek kategoridendir)
    kategori_kumeleri: dict[str, list[list[int]]] = defaultdict(list)
    for kume in kumeler:
        kategori_kumeleri[kayitlar[kume[0]]["kategori"]].append(kume)

    for kategori in C.CATEGORY_KEYS:
        kume_listesi = kategori_kumeleri.get(kategori, [])
        if not kume_listesi:
            continue

        rng.shuffle(kume_listesi)
        kume_listesi.sort(key=len, reverse=True)      # once buyuk kumeler

        toplam = sum(len(k) for k in kume_listesi)
        hedef = {ad: oran * toplam for ad, oran in hedef_oran.items()}
        mevcut = {ad: 0 for ad in hedef}

        for kume in kume_listesi:
            # Hedefine en cok uzak olan bolmeye ver (agirlikli en ac)
            ad = max(hedef, key=lambda a: hedef[a] - mevcut[a])
            bolmeler[ad].extend(kume)
            mevcut[ad] += len(kume)

    return bolmeler


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------

# label/intent_label/oncelik_label: egitimde kullanilan sayisal karsiliklar.
# Metin karsiliklari da yaziliyor cunku rapor ve hata analizi okunabilir
# olmali; ikisini birlikte tutmak dosyayi biraz buyutuyor ama her okuyan
# tarafta yeniden esleme yapma ihtiyacini kaldiriyor.
SUTUNLAR = ["metin", "kategori", "label", "intent", "intent_label",
            "oncelik", "oncelik_label", "stil", "kaynak"]


def csv_yaz(path, kayitlar: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUTUNLAR)
        w.writeheader()
        for r in kayitlar:
            intent = r.get("intent") or C.INTENT_KEYS[0]
            oncelik = r.get("oncelik") or "P3"
            w.writerow({
                "metin": r["metin"],
                "kategori": r["kategori"],
                "label": C.LABEL2ID[r["kategori"]],
                "intent": intent,
                "intent_label": C.INTENT2ID[intent],
                "oncelik": oncelik,
                "oncelik_label": C.PRIORITY2ID[oncelik],
                "stil": r.get("stil", ""),
                "kaynak": r.get("kaynak", ""),
            })


def gold_hazirla() -> list[dict]:
    gold = load_jsonl(C.GOLD_FILE)
    if not gold:
        print("UYARI: gold.jsonl bulunamadi, gold_test.csv yazilmayacak.")
        return []
    return [{**r, "metin": " ".join(r["metin"].split())} for r in gold]


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------

def rapor(kayitlar, kumeler, bolmeler, atilan, gold) -> None:
    print(f"\n{'=' * 78}\nKUMELEME\n{'=' * 78}")
    boyutlar = Counter(len(k) for k in kumeler)
    coklu = sum(1 for k in kumeler if len(k) > 1)
    en_buyuk = max(kumeler, key=len)
    print(f"{len(kayitlar)} kayit -> {len(kumeler)} kume "
          f"({coklu} kume birden fazla kayit iceriyor)")
    print(f"kume boyut dagilimi: {dict(sorted(boyutlar.items()))}")
    if len(en_buyuk) > 1:
        print(f"en buyuk kume ({len(en_buyuk)} kayit) ornekleri:")
        for i in en_buyuk[:4]:
            print(f"   - {kayitlar[i]['metin']}")

    print(f"\n{'=' * 78}\nBOLME\n{'=' * 78}")
    print(f"{'kategori':<28} {'train':>7} {'val':>6} {'test':>6} {'toplam':>7}")
    toplamlar = Counter()
    for kategori in C.CATEGORY_KEYS:
        satir = {}
        for ad, idxs in bolmeler.items():
            satir[ad] = sum(1 for i in idxs if kayitlar[i]["kategori"] == kategori)
            toplamlar[ad] += satir[ad]
        top = sum(satir.values())
        if not top:
            continue
        print(f"{C.DISPLAY_NAME[kategori]:<28} {satir['train']:>7} "
              f"{satir['val']:>6} {satir['test']:>6} {top:>7}")
    genel = sum(toplamlar.values())
    print(f"{'-' * 56}")
    print(f"{'TOPLAM':<28} {toplamlar['train']:>7} {toplamlar['val']:>6} "
          f"{toplamlar['test']:>6} {genel:>7}")
    print(f"{'oran':<28} {toplamlar['train'] / genel:>7.0%} "
          f"{toplamlar['val'] / genel:>6.0%} {toplamlar['test'] / genel:>6.0%}")

    # Kaynak dagilimi: hangi modelin verisi nereye dustu (rapor icin kullanisli)
    print("\nKAYNAK DAGILIMI (hangi model kac kayit uretti)")
    for ad in ("train", "val", "test"):
        kaynaklar = Counter(kayitlar[i].get("kaynak", "?").split(":")[0]
                            for i in bolmeler[ad])
        print(f"  {ad:<6} {dict(kaynaklar)}")

    if atilan:
        print(f"\nTEMIZLIKTE ATILAN: {dict(atilan)}")

    if gold:
        print(f"\nGOLD TEST (ayri tutuldu, egitime girmedi): {len(gold)} kayit, "
              f"{len(set(r['kategori'] for r in gold))} kategori")

    # Sizinti kontrolu: gold metinleri egitim havuzunda GORUNMEMELI
    if gold:
        havuz_normlari = {r["_norm"] for r in kayitlar}
        sizan = [r for r in gold if R.normalize(r["metin"]) in havuz_normlari]
        if sizan:
            print(f"\n!! UYARI: {len(sizan)} gold kaydi egitim havuzunda da var! "
                  f"Bu test sonucunu gecersiz kilar:")
            for r in sizan[:5]:
                print(f"   - {r['metin']}")
        else:
            print("gold sizinti kontrolu: TEMIZ (hicbir gold metni havuzda yok)")


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 3 -- on isleme ve bolme")
    ap.add_argument("--include-seed", dest="include_seed", action="store_true",
                    default=None,
                    help="seed.jsonl'i egitim havuzuna kat "
                         f"(varsayilan: config.INCLUDE_SEED_IN_TRAINING)")
    ap.add_argument("--no-include-seed", dest="include_seed", action="store_false",
                    help="seed.jsonl'i KATMA (kiyas icin)")
    ap.add_argument("--report-only", action="store_true",
                    help="dosya yazma, sadece raporu goster")
    args = ap.parse_args()

    rng = random.Random(C.SEED)

    include_seed = (C.INCLUDE_SEED_IN_TRAINING if args.include_seed is None
                    else args.include_seed)
    pool = load_pool(include_seed)
    kayitlar, atilan = temizle(pool)
    print(f"temizlik sonrasi: {len(kayitlar)} kayit")

    print("kumeleniyor (near-duplicate) ...", end=" ", flush=True)
    kumeler = kumele(kayitlar)
    print(f"{len(kumeler)} kume")

    bolmeler = bol(kayitlar, kumeler, rng)
    gold = gold_hazirla()

    rapor(kayitlar, kumeler, bolmeler, atilan, gold)

    if args.report_only:
        print("\n(--report-only: dosya yazilmadi)")
        return

    for ad, path in (("train", C.TRAIN_FILE), ("val", C.VAL_FILE),
                     ("test", C.TEST_FILE)):
        csv_yaz(path, [kayitlar[i] for i in bolmeler[ad]])
        print(f"-> {path.name:<16} {len(bolmeler[ad]):>5} kayit")

    if gold:
        csv_yaz(C.GOLD_TEST_FILE, gold)
        print(f"-> {C.GOLD_TEST_FILE.name:<16} {len(gold):>5} kayit")

    # clean.csv: bolunmemis, temizlenmis tam havuz (inceleme/yedek amacli)
    csv_yaz(C.CLEAN_FILE, kayitlar)
    print(f"-> {C.CLEAN_FILE.name:<16} {len(kayitlar):>5} kayit")


if __name__ == "__main__":
    main()
