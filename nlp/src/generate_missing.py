"""
Yeni taksonomide EKSIK kalan (kategori, intent) kombinasyonlarini uretir.

NEDEN AYRI BIR SCRIPT: `generate_data.py` eski tek boyutlu tasarimdan geliyor
-- sadece (kategori, stil) uretiyor ve intent/oncelik bilmiyor. Relabel turu
mevcut havuzu yeni taksonomiye tasidi ama iki kategori (yol_yapisal,
personel_bilgi) ile iki intent (information_request, suggestion) bos kaldi:
eski veri bu kavramlari hic icermiyordu, cunku eski taksonomide yoktular.
Buradaki uretim tam da o bosluklari kapatir.

Cikti dogrudan relabel formatindadir (metin + kategori + intent + oncelik),
yani `relabeled.jsonl`'e eklenir; ayri bir birlestirme adimi gerekmez.

Oncelik etiketini LLM'e SORMUYORUZ, uretimde ISTEMIYORUZ: model hem cumleyi
uretip hem kendi urettigine oncelik bicerse iki hata birbirini besler. Uretim
bittikten sonra `relabel.py` ayni cumleleri bagimsizca etiketler.

Kullanim:
    python -m src.generate_missing --dry-run
    python -m src.generate_missing --provider gemini
    python -m src.generate_missing --plan kategori --provider openrouter
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter

from src import config as C
from src import review
from src.generate_data import Caller

CIKTI = C.RAW_DIR / "relabeled.jsonl"

# Hangi bosluklarin doldurulacagi. (kategori, intent, adet) ucluleri.
#
# Kategori bosluklari agirlikli fault_report'tur -- bunlar teknik ariza
# kategorileri. Intent bosluklari ise KATEGORIYE YAYILIR: "ne zaman
# duzelecek" sorusu her kategoride sorulabilir, tek bir kategoriye
# hapsedilirse model intent'i kategoriyle karistirmayi ogrenir.
PLANLAR = {
    "kategori": [
        ("yol_yapisal", "fault_report", 150),
        ("yol_yapisal", "incident_report", 50),
        ("personel_bilgi", "information_request", 80),
        ("personel_bilgi", "complaint", 70),
        ("personel_bilgi", "fault_report", 50),
    ],
    "intent": [
        ("mekanik_istasyon", "information_request", 30),
        ("arac_tren", "information_request", 30),
        ("yolcu_hizmetleri", "information_request", 30),
        ("elektronik_sistemler", "information_request", 25),
        ("altyapi_insaat", "information_request", 20),
        ("mekanik_istasyon", "suggestion", 30),
        ("istasyon_guvenlik_temizlik", "suggestion", 30),
        ("yolcu_hizmetleri", "suggestion", 30),
        ("elektrik_enerji", "suggestion", 20),
        ("guvenlik_asayis_olay", "suggestion", 20),
    ],
}

BATCH = 25


def mevcut_oku() -> list[dict]:
    if not CIKTI.exists():
        return []
    with CIKTI.open(encoding="utf-8") as f:
        return [json.loads(s) for s in f if s.strip()]


def prompt_kur(kategori: str, intent: str, n: int, kacinilacak: list[str]) -> str:
    kat, nyt = C.CATEGORIES[kategori], C.INTENTS[intent]
    stil_satiri = "\n".join(f"  - {ad}: {tanim}"
                            for ad, tanim in C.STYLE_VARIANTS.items())
    slotlar = "\n".join(
        f"  {ad}: {', '.join(random.sample(deger, min(6, len(deger))))}"
        for ad, deger in C.SLOT_VALUES.items()
    )
    kacin = ""
    if kacinilacak:
        ornekler = random.sample(kacinilacak, min(12, len(kacinilacak)))
        kacin = ("\nBUNLARA BENZER CUMLE URETME (zaten var):\n"
                 + "\n".join(f"  - {m}" for m in ornekler))

    return f"""Sen Metro İstanbul'da çalışan deneyimli bir operasyon personelisin.

GÖREV: Aşağıdaki kategoriye ve amaca uygun {n} adet gerçekçi Türkçe bildirim üret.

KATEGORİ: {kat['display']}
Kapsam: {kat['scope']}
Bu kategoriye GİRMEYENLER: {kat['exclude']}

BİLDİRİMİN AMACI (intent): {nyt['display']}
{nyt['scope']}

YAZIM STİLLERİ -- üretilen cümleleri bu dört stile eşit dağıt:
{stil_satiri}

Gerçekçilik için kullanabileceğin değerler (zorunlu değil):
{slotlar}
{kacin}

KURALLAR:
1. Her cümle "{nyt['display']}" amacına UYMALI -- bu çok önemli, sadece
   kategori değil AMAÇ da doğru olmalı.
2. Cümleler birbirinden farklı konuları ele alsın, tekrar etme.
3. Sadece `yazim_yanlisi` stilinde harf düşür; diğer üç stilde doğru
   Türkçe yazım zorunludur.
4. Uydurma istasyon adı veya teknik terim KULLANMA.
5. Her cümle için hangi stilde yazdığını belirt.

SADECE şu JSON'u döndür:
{{"ornekler": [{{"metin": "...", "stil": "standart"}}]}}"""


def yanit_coz(ham: str) -> list[dict]:
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
    cikti = []
    for o in veri.get("ornekler", []):
        metin = (o.get("metin") or "").strip()
        if not metin:
            continue
        stil = o.get("stil")
        cikti.append({"metin": metin,
                      "stil": stil if stil in C.STYLE_KEYS else None})
    return cikti


def main() -> None:
    ap = argparse.ArgumentParser(description="Eksik kategori/intent bosluklarini uret")
    # Varsayilan ollama: gemma4:cloud, hem uretim hem etiketleme rolunde
    # kalitesi olculdu (bkz. config.OLLAMA_MODEL), kota siniri yok.
    ap.add_argument("--provider", default="ollama",
                    choices=["hybrid", "openrouter", "gemini", "groq", "ollama"])
    ap.add_argument("--plan", choices=["kategori", "intent", "hepsi"], default="hepsi")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    planlar = (PLANLAR["kategori"] + PLANLAR["intent"] if args.plan == "hepsi"
               else PLANLAR[args.plan])

    mevcut = mevcut_oku()
    gorulen = {r["metin"] for r in mevcut}
    sayim = Counter((r["kategori"], r["intent"]) for r in mevcut)

    if args.dry_run:
        kat, nyt, _ = planlar[0]
        print(prompt_kur(kat, nyt, BATCH, [r["metin"] for r in mevcut[:40]]))
        return

    caller = Caller(args.provider)
    yeni_toplam, red = 0, Counter()
    basla = time.time()

    for kategori, intent, hedef in planlar:
        var = sayim[(kategori, intent)]
        if var >= hedef:
            print(f"{C.DISPLAY_NAME[kategori]:<32} {intent:<20} "
                  f"{var}/{hedef} atlandi")
            continue

        # Near-dup karsilastirmasi ayni KATEGORIDEKI cumlelerle yapilir;
        # farkli kategorideki benzerlik zaten taksonomi sinyali, kirlilik degil.
        havuz = [r["metin"] for r in mevcut if r["kategori"] == kategori]

        while var < hedef:
            istenen = min(BATCH, hedef - var)
            print(f"{C.DISPLAY_NAME[kategori]:<32} {intent:<20} "
                  f"{var}/{hedef} ...", end=" ", flush=True)
            try:
                ham, saglayici = caller.ask(
                    prompt_kur(kategori, intent, istenen, havuz))
            except RuntimeError as exc:
                print(f"DURDURULDU: {exc}")
                return _kaydet_ve_ozetle(mevcut, yeni_toplam, red, basla)
            try:
                ornekler = yanit_coz(ham)
            except Exception as exc:                          # noqa: BLE001
                print(f"JSON hatasi, atlandi ({str(exc)[:50]})")
                red["json"] += 1
                continue

            eklendi = 0
            for o in ornekler:
                metin = o["metin"]
                if metin in gorulen:
                    red["birebir"] += 1
                    continue
                if any(review.similarity(metin, m) >= C.NEAR_DUP_THRESHOLD
                       for m in havuz):
                    red["near_dup"] += 1
                    continue
                kayit = {
                    "metin": metin,
                    "kategori": kategori,
                    "intent": intent,
                    "oncelik": None,          # relabel turunda doldurulacak
                    "stil": o["stil"],
                    "kaynak": f"missing:{saglayici}",
                    "eski_kategori": None,
                }
                mevcut.append(kayit)
                gorulen.add(metin)
                havuz.append(metin)
                eklendi += 1
                var += 1
                yeni_toplam += 1
                if var >= hedef:
                    break

            print(f"+{eklendi} ({saglayici})")
            if eklendi == 0:                  # doyum: model yeni sey uretemiyor
                print("    (yeni ornek gelmedi, bu kombinasyon birakildi)")
                break

            _yaz(mevcut)

    _kaydet_ve_ozetle(mevcut, yeni_toplam, red, basla)


def _yaz(kayitlar: list[dict]) -> None:
    with CIKTI.open("w", encoding="utf-8") as f:
        for r in kayitlar:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _kaydet_ve_ozetle(kayitlar, yeni, red, basla) -> None:
    _yaz(kayitlar)
    print(f"\n-> {len(kayitlar)} kayit ({yeni} yeni), "
          f"{(time.time() - basla) / 60:.1f} dk: {CIKTI}")
    if red:
        print(f"   reddedilen: {dict(red)}")
    print("\nKATEGORI")
    kat = Counter(r["kategori"] for r in kayitlar)
    for k in C.CATEGORY_KEYS:
        print(f"  {C.DISPLAY_NAME[k]:<34} {kat.get(k, 0)}")
    print("\nINTENT")
    ntn = Counter(r["intent"] for r in kayitlar)
    for k in C.INTENT_KEYS:
        print(f"  {C.INTENT_DISPLAY[k]:<34} {ntn.get(k, 0)}")
    eksik_oncelik = sum(1 for r in kayitlar if not r.get("oncelik"))
    if eksik_oncelik:
        print(f"\n{eksik_oncelik} kaydin onceligi bos -- "
              f"'python -m src.relabel' ile tamamlanacak.")


if __name__ == "__main__":
    main()
