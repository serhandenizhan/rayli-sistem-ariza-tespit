"""
Oncelik etiketlerinin TUTARLILIGINI olcer -- modelin ulasabilecegi tavani verir.

NEDEN GEREKLI: oncelik basligi ilk egitimde macro-F1 0.60 verdi ve hatalarin
cogu P2<->P3 arasindaydi. Iki olasilik var:
  (a) model ogrenemiyor -> mimari/veri sorunu, cozulebilir
  (b) etiketlerin kendisi tutarsiz -> hicbir model bu tavani asamaz

Ayirt etmenin yolu: ayni cumleleri IKINCI KEZ etiketletip iki turun ne kadar
uyustuguna bakmak. Uyum %70 ise model %70'in cok uzerine cikamaz; bu durumda
modeli iyilestirmeye calismak bosa emek olur, once etiket tanimi duzelmeli.

Bu olcum bu projede ucuncu kez ayni dersi test ediyor: "az orneklem + tek
olcum = olcum gibi gorunen gurultu" (bkz. CLAUDE.md, Tohum varyansi).

Kullanim:
    python -m src.oncelik_tutarlilik --n 120 --provider gemini
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter

from src import config as C
from src.generate_data import Caller
from src.relabel import BATCH, oncelik_kilavuzu

KAYNAK = C.RAW_DIR / "relabeled.jsonl"


def prompt_kur(cumleler: list[str]) -> str:
    """Sadece ONCELIK soran, sadelestirilmis prompt.

    Kategori ve intent bilerek sorulmuyor: olcmek istedigimiz sey onceligin
    kendi tutarliligi, diger boyutlarin gurultusu karismasin.
    """
    numarali = "\n".join(f"{i}. {m}" for i, m in enumerate(cumleler, 1))
    return f"""Metro İstanbul arıza bildirimlerine ÖNCELİK atayacaksın.

{oncelik_kilavuzu()}

KURALLAR:
1. Her bildirim için tam olarak bir öncelik seç: P1, P2, P3 veya P4.
2. Öncelik konudan değil ETKİDEN belirlenir.
3. Merdiven mantığıyla sırayla sor: can güvenliği tehdidi mi (P1)? Değilse
   sefer durdu mu / birden fazla ekipman mı / yolcu fiziksel geçemiyor mu
   (P2)? Değilse tek ekipman arızası var ama yolculuk mümkün mü (P3)?
   Değilse hiç arıza yok mu, sadece görünüm/bilgi/öneri mi (P4)?
4. {len(cumleler)} bildirimin HEPSİNİ döndür, numara atlama.

BİLDİRİMLER:
{numarali}

SADECE şu JSON'u döndür:
{{"etiketler": [{{"no": 1, "category": "mekanik_istasyon", "intent": "fault_report", "priority": "P3"}}]}}

NOT: category ve intent alanlarini yok sayabilirsin, sadece priority onemli --
ama sema bozulmasin diye yine de doldur."""



def yanit_coz_gevsek(ham: str, n: int) -> dict[int, str]:
    """{no: priority} doner -- SADECE priority alanini dogrular.

    src.relabel.yanit_coz() uc alanin (category/intent/priority) da gecerli
    olmasini sart kosuyor; bu olcum SADECE onceligin tutarliligina bakiyor,
    modelin bazen kisaltilmis kategori adi dondurmesi (orn. "guvenlik_"
    "asayis_olay" yerine "guvenlik") yuzunden gecerli bir priority'yi
    atmak yanlis olur -- ornek boyutunu gereksiz kucultup olcumu gurultuye
    cevirir (bkz. CLAUDE.md, "az orneklem = gurultu" dersi).
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

    sonuc: dict[int, str] = {}
    for e in veri.get("etiketler", []):
        try:
            no = int(e["no"])
        except (KeyError, TypeError, ValueError):
            continue
        onc = e.get("priority")
        if onc in C.PRIORITY_KEYS and 1 <= no <= n:
            sonuc[no] = onc
    return sonuc

def main() -> None:
    ap = argparse.ArgumentParser(description="Oncelik etiket tutarliligi olcumu")
    ap.add_argument("--n", type=int, default=120, help="kac kayit orneklenecek")
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--seed", type=int, default=C.SEED)
    args = ap.parse_args()

    kayitlar = [json.loads(s) for s in KAYNAK.open(encoding="utf-8") if s.strip()]
    kayitlar = [r for r in kayitlar if r.get("oncelik")]

    # Katmanli ornekleme: her onceligten esit sayida al, yoksa P3 baskin gelir
    # ve nadir siniflarin tutarliligi hic olculmez.
    hedef = max(1, args.n // len(C.PRIORITY_KEYS))
    rng = random.Random(args.seed)
    ornek = []
    for p in C.PRIORITY_KEYS:
        havuz = [r for r in kayitlar if r["oncelik"] == p]
        ornek.extend(rng.sample(havuz, min(hedef, len(havuz))))
    rng.shuffle(ornek)
    print(f"{len(ornek)} kayit orneklendi ({hedef}/oncelik hedefiyle)")

    caller = Caller(args.provider)
    ikinci: dict[str, str] = {}
    for i in range(0, len(ornek), BATCH):
        parti = ornek[i:i + BATCH]
        print(f"  [{i + len(parti)}/{len(ornek)}] ...", end=" ", flush=True)
        try:
            ham, saglayici = caller.ask(prompt_kur([r["metin"] for r in parti]))
            cozum = yanit_coz_gevsek(ham, len(parti))
        except Exception as exc:                                  # noqa: BLE001
            print(f"atlandi ({str(exc)[:60]})")
            continue
        for j, r in enumerate(parti, 1):
            if j in cozum:
                ikinci[r["metin"]] = cozum[j]
        print(f"+{len(cozum)} ({saglayici})")

    ortak = [r for r in ornek if r["metin"] in ikinci]
    if not ortak:
        print("Karsilastirilacak kayit yok.")
        return

    uyusan = sum(1 for r in ortak if r["oncelik"] == ikinci[r["metin"]])
    oran = uyusan / len(ortak)
    print(f"\n{'=' * 70}\nTUTARLILIK\n{'=' * 70}")
    print(f"  {uyusan}/{len(ortak)} kayitta iki tur ayni onceligi verdi = {oran:.1%}")

    # Cohen's kappa: sansa bagli uyumu duser. Ham uyum orani yaniltici olabilir
    # (4 sinifta rastgele bile %25 uyusur), kappa bunu duzeltir.
    n = len(ortak)
    p_gozlenen = oran
    sayim1 = Counter(r["oncelik"] for r in ortak)
    sayim2 = Counter(ikinci[r["metin"]] for r in ortak)
    p_sans = sum((sayim1[k] / n) * (sayim2[k] / n) for k in C.PRIORITY_KEYS)
    kappa = (p_gozlenen - p_sans) / (1 - p_sans) if p_sans < 1 else 0.0
    print(f"  Cohen's kappa = {kappa:.3f}  "
          f"({'zayif' if kappa < 0.4 else 'orta' if kappa < 0.6 else 'iyi' if kappa < 0.8 else 'cok iyi'})")

    print(f"\n{'sinif':<8} {'1.tur':>7} {'2.tur':>7} {'uyum':>8}")
    for p in C.PRIORITY_KEYS:
        alt = [r for r in ortak if r["oncelik"] == p]
        u = sum(1 for r in alt if ikinci[r["metin"]] == p)
        oran_p = f"{u/len(alt):.0%}" if alt else "-"
        print(f"{p:<8} {sayim1[p]:>7} {sayim2[p]:>7} {oran_p:>8}")

    gecis = Counter((r["oncelik"], ikinci[r["metin"]])
                    for r in ortak if r["oncelik"] != ikinci[r["metin"]])
    if gecis:
        print("\nen sik uyusmazliklar (1.tur -> 2.tur):")
        for (a, b), k in gecis.most_common(6):
            print(f"  {a} -> {b}: {k}")

    print(f"\nYORUM: model bu etiketlerle en fazla ~{oran:.0%} dogruluk "
          f"beklenebilir; ustu gurultuye ezberleme olur.")

    cikti = {"n": len(ortak), "ham_uyum": oran, "kappa": kappa,
             "sinif_uyumu": {p: sayim1[p] for p in C.PRIORITY_KEYS}}
    (C.MODEL_DIR / "oncelik_tutarlilik.json").write_text(
        json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {C.MODEL_DIR / 'oncelik_tutarlilik.json'}")


if __name__ == "__main__":
    main()
