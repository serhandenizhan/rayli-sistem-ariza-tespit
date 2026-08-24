"""
Mevcut bildirim havuzunu YENI taksonomiye gore toplu yeniden etiketler.

NEDEN YENIDEN URETIM DEGIL: elde birikmis ~1800 cumlenin dil cesitliligi
(stil varyantlari, yazim hatalari, gercek istasyon adlari) degerli. Taksonomi
degistiginde bu cumleleri atip sifirdan uretmek hem kotayi tuketir hem de
cesitliligi kaybettirir. Cumleler ayni kalir, sadece ETIKETLERI yenilenir.

Model her cumle icin uc boyutu birlikte belirler:
  category  -- konu hangi teknik alana ait (11 kategori)
  intent    -- kullanici ne yapmak istiyor (5 intent)
  priority  -- insan guvenligine ve operasyona etkisi (P1-P4)

Uc boyut TEK cagrida isteniyor; ayri ayri sormak cagri sayisini ucla carpardi
ve model zaten ayni cumleyi okuyor.

Etiketlenemeyen (LLM'in atladigi veya bozuk dondurdugu) kayitlar SESSIZCE
ATILMAZ, `--rapor` ile listelenir; boylece kac kaydin neden dustugu gorulur.

Kullanim:
    python -m src.relabel --dry-run                  # prompt'u yazdir, cik
    python -m src.relabel --provider gemini          # etiketle
    python -m src.relabel --provider gemini --limit 80   # once kucuk parti dene
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from src import config as C
from src.generate_data import Caller

GIRDI = C.RAW_FILE
CIKTI = C.RAW_DIR / "relabeled.jsonl"

# Tek cagrida kac cumle etiketlenecek. Uretimdeki 40'tan dusuk tutuldu:
# burada model her cumle icin UC alan dondurmek zorunda, cikti uzunlugu
# cumle basina daha buyuk.
BATCH = 40


def kategori_kilavuzu() -> str:
    satirlar = []
    for k, v in C.CATEGORIES.items():
        satirlar.append(f"- {k} ({v['display']})\n"
                        f"    KAPSAM: {v['scope']}\n"
                        f"    HARIC : {v['exclude']}")
    return "\n".join(satirlar)


def intent_kilavuzu() -> str:
    return "\n".join(f"- {k}: {v['scope']}" for k, v in C.INTENTS.items())


def oncelik_kilavuzu() -> str:
    return "\n".join(f"- {k} ({v['display']}): {v['scope']}"
                     for k, v in C.PRIORITIES.items())


def prompt_kur(cumleler: list[str]) -> str:
    numarali = "\n".join(f"{i}. {m}" for i, m in enumerate(cumleler, 1))
    return f"""Sen Metro İstanbul'un arıza bildirim sistemini kuran bir veri
uzmanısın. Aşağıdaki bildirimleri üç boyutta sınıflandıracaksın.

KATEGORİLER (bildirimin hangi teknik birime gideceği):
{kategori_kilavuzu()}

INTENT (kullanıcının amacı):
{intent_kilavuzu()}

ÖNCELİK (insan güvenliğine ve operasyona etkisi):
{oncelik_kilavuzu()}

KURALLAR:
1. Her bildirim için SADECE bir kategori, bir intent, bir öncelik seç.
2. Kategori anahtarlarını birebir yukarıdaki gibi yaz (küçük harf, alt çizgi).
3. HARIC satırlarını dikkatle uygula -- sınırdaki durumlar orada yazıyor.
4. Önceliği MERDİVEN gibi sırayla belirle, yukarıdaki ÖNCELİK bölümündeki
   "SORU 1/2/3/4" sırasını izle: can güvenliği tehdidi mi (P1)? Değilse:
   sefer durdu mu / birden fazla ekipman mı / yolcu fiziksel geçemiyor mu
   (P2)? Değilse: tek ekipman arızası var ama yolculuk mümkün mü (P3)?
   Değilse: hiç arıza yok, sadece görünüm/bilgi/öneri mi (P4)? İlk EVET
   cevabında dur, sonraki sorulara bakma.
5. Bildirimin yazım hatası içermesi kategoriyi değiştirmez, anlamına bak.
6. Numaraları ATLAMA, {len(cumleler)} bildirimin HEPSİNİ döndür.

BİLDİRİMLER:
{numarali}

SADECE şu JSON'u döndür, başka hiçbir şey yazma:
{{"etiketler": [{{"no": 1, "category": "...", "intent": "...", "priority": "P3"}}]}}"""


def yanit_coz(ham: str, n: int) -> dict[int, dict]:
    """LLM yanitindan {no: {category, intent, priority}} cikarir.

    Gecersiz anahtar donduren kayitlar atlanir -- uydurma bir kategori adini
    veriye sokmaktansa o cumleyi etiketsiz birakip raporlamak dogru.
    """
    ham = ham.strip()
    if ham.startswith("```"):
        ham = ham.split("```")[1].removeprefix("json").strip()
    try:
        veri = json.loads(ham)
    except json.JSONDecodeError:
        bas, son = ham.find("{"), ham.rfind("}")
        if bas < 0 or son < 0:
            raise
        veri = json.loads(ham[bas:son + 1])

    sonuc: dict[int, dict] = {}
    for e in veri.get("etiketler", []):
        try:
            no = int(e["no"])
        except (KeyError, TypeError, ValueError):
            continue
        kat, nyt, onc = e.get("category"), e.get("intent"), e.get("priority")
        if kat not in C.CATEGORY_KEYS:
            continue
        if nyt not in C.INTENT_KEYS:
            continue
        if onc not in C.PRIORITY_KEYS:
            continue
        if 1 <= no <= n:
            sonuc[no] = {"kategori": kat, "intent": nyt, "oncelik": onc}
    return sonuc


def _yol_coz(deger: str | None, varsayilan):
    """CLI'dan gelen dosya adini Path'e cevirir; cıplak ad data/raw altinda aranir."""
    if not deger:
        return varsayilan
    p = Path(deger)
    return p if p.is_absolute() or len(p.parts) > 1 else C.RAW_DIR / deger


def kayitlari_oku(path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"HATA: {path} yok.")
    with path.open(encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Havuzu yeni taksonomiye gore etiketle")
    # Varsayilan ollama: gemma4:cloud, 120 kayitlik olcumde en iyi sonuc +
    # kota yok (bkz. config.OLLAMA_MODEL yorumu). Bulut saglayicilar farkli
    # bir model denemek icin secilebilir.
    ap.add_argument("--provider", default="ollama",
                    choices=["hybrid", "openrouter", "gemini", "groq",
                             "ollama"])
    ap.add_argument("--limit", type=int, help="sadece ilk N kaydi isle (deneme icin)")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM cagirmadan ilk prompt'u yazdir ve cik")
    ap.add_argument("--rapor", action="store_true",
                    help="mevcut ciktiyi ozetle, yeni cagri yapma")
    ap.add_argument("--girdi", help=f"etiketlenecek jsonl (varsayilan: {GIRDI.name})")
    ap.add_argument("--cikti", help=f"sonuc dosyasi (varsayilan: {CIKTI.name})")
    args = ap.parse_args()

    girdi = _yol_coz(args.girdi, GIRDI)
    cikti = _yol_coz(args.cikti, CIKTI)

    kayitlar = kayitlari_oku(girdi)
    if args.limit:
        kayitlar = kayitlar[:args.limit]

    # Devam edilebilirlik: daha once etiketlenmis metinler atlanir.
    onceki: dict[str, dict] = {}
    if cikti.exists():
        for r in kayitlari_oku(cikti):
            onceki[r["metin"]] = r

    if args.rapor:
        if not onceki:
            print("Henuz cikti yok.")
            return
        print(f"{len(onceki)} kayit etiketlenmis.\n")
        for alan, baslik in (("kategori", "KATEGORI"), ("intent", "INTENT"),
                             ("oncelik", "ONCELIK")):
            print(baslik)
            for k, n in Counter(r[alan] for r in onceki.values()).most_common():
                print(f"  {k:<28} {n}")
            print()
        return

    kalan = [r for r in kayitlar if r["metin"] not in onceki]
    print(f"{len(kayitlar)} kayit | {len(onceki)} zaten etiketli | "
          f"{len(kalan)} islenecek")
    if not kalan:
        print("Yapilacak is yok.")
        return

    if args.dry_run:
        print("\n" + "=" * 70)
        print(prompt_kur([r["metin"] for r in kalan[:BATCH]]))
        return

    caller = Caller(args.provider)
    etiketli = dict(onceki)
    atlanan: list[str] = []
    basla = time.time()

    for i in range(0, len(kalan), BATCH):
        parti = kalan[i:i + BATCH]
        cumleler = [r["metin"] for r in parti]
        print(f"  [{i + len(parti)}/{len(kalan)}] ...", end=" ", flush=True)
        try:
            ham, saglayici = caller.ask(prompt_kur(cumleler))
        except RuntimeError as exc:
            print(f"DURDURULDU: {exc}")
            break
        try:
            cozum = yanit_coz(ham, len(parti))
        except Exception as exc:                              # noqa: BLE001
            print(f"JSON hatasi, parti atlandi ({str(exc)[:60]})")
            atlanan.extend(cumleler)
            continue

        for j, r in enumerate(parti, 1):
            e = cozum.get(j)
            if not e:
                atlanan.append(r["metin"])
                continue
            etiketli[r["metin"]] = {
                "metin": r["metin"],
                "kategori": e["kategori"],
                "intent": e["intent"],
                "oncelik": e["oncelik"],
                "stil": r.get("stil"),
                "kaynak": f"relabel:{saglayici}",
                "eski_kategori": r.get("kategori"),
            }
        print(f"+{len(cozum)} ({saglayici})")

        with cikti.open("w", encoding="utf-8") as f:          # her partide kaydet
            for r in etiketli.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sure = time.time() - basla
    print(f"\n-> {len(etiketli)} kayit: {cikti}  ({sure/60:.1f} dk)")
    if atlanan:
        print(f"   {len(atlanan)} kayit etiketlenemedi (tekrar calistir).")

    print("\nKATEGORI DAGILIMI")
    for k, n in Counter(r["kategori"] for r in etiketli.values()).most_common():
        print(f"  {C.DISPLAY_NAME[k]:<32} {n}")
    print("\nINTENT DAGILIMI")
    for k, n in Counter(r["intent"] for r in etiketli.values()).most_common():
        print(f"  {C.INTENT_DISPLAY[k]:<32} {n}")
    print("\nONCELIK DAGILIMI")
    for k, n in Counter(r["oncelik"] for r in etiketli.values()).most_common():
        print(f"  {k} {C.PRIORITY_DISPLAY[k]:<30} {n}")

    # Eski -> yeni kategori gecis matrisi: taksonominin nasil yeniden
    # dagildigini gosterir, hangi eski kategorinin bolundugu goruilur.
    gecis = Counter((r.get("eski_kategori"), r["kategori"])
                    for r in etiketli.values() if r.get("eski_kategori"))
    if gecis:
        print("\nESKI -> YENI (en sik 15)")
        for (eski, yeni), n in gecis.most_common(15):
            print(f"  {eski:<24} -> {yeni:<28} {n}")


if __name__ == "__main__":
    main()
