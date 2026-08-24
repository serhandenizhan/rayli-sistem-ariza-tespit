"""
Adim 2b — Cogaltma (amplification).

seed.jsonl'i few-shot yemi olarak kullanip her kategori icin TARGET_PER_CATEGORY
(200) ornege cikarir. Cikti: data/raw/amplified.jsonl

  KURAL: gold.jsonl bu dosyada HIC okunmaz. Gold saf test seti olarak kalmali;
  few-shot'ta gorunmesi test sonucunu gecersiz kilardi.

Saglayici stratejisi (HIBRIT, bkz. config.AMPLIFY_PROVIDER):
  Birincil OpenRouter/Nemotron -- kaliteyi bu model belirledi. Ucretsiz katman
  ~50 istek/gun oldugu icin 1600 ornek tek saglayiciyla bitmiyor; KALICI hata
  (kota/429/401) gelir gelmez kalan is yerel Ollama'ya devredilir. Gecici hata
  (bozuk JSON, tek seferlik kopukluk) saglayici degistirmez, sadece yeniden
  denenir.

Her cagri TEK (kategori, stil) ikilisi icindir. Boylece model ayni anda dort
farkli uzunluk araligini yonetmek zorunda kalmaz -- Adim 2a'da en sik gorulen
sorun uzunluk kuralina uymamakti.

Cesitlilik prompt seviyesinde zorlanir:
  - her cagrida SLOT_VALUES'tan rastgele istasyon/konum/zaman/aciliyet secilir
  - halihazirda uretilmis orneklerden bir orneklem "bunlari tekrarlama" diye
    prompt'a konur
  - eklenmeden once near-duplicate kontrolu yapilir (review.similarity)

Kullanim:
    python -m src.generate_data                     # hibrit, hedefe kadar
    python -m src.generate_data --provider ollama   # sadece yerel
    python -m src.generate_data --category arac_tren --target 20
    python -m src.generate_data --dry-run           # LLM cagirmadan prompt'u goster
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv

from src import config as C
from src import review as R
from src.generate_seed import _call_openrouter, parse_response

load_dotenv()


# ---------------------------------------------------------------------------
# Saglayici katmani
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> str:
    """Ollama'ya sorar (yerel veya `<model>:cloud` bulut modeli).

    Model gemma4:cloud -- uretim VE etiketleme rolunde qwen2.5:14b'ye karsi
    olculup kazandi, ayrintili gerekce config.OLLAMA_MODEL yorumunda."""
    try:
        resp = requests.post(
            f"{C.OLLAMA_HOST}/api/chat",
            json={
                "model": C.OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": C.LLM_TEMPERATURE,
                    "num_ctx": C.OLLAMA_NUM_CTX,
                    "num_predict": C.OLLAMA_NUM_PREDICT,
                },
            },
            timeout=C.OLLAMA_TIMEOUT,
        )
    except requests.exceptions.ConnectionError as exc:
        # Ollama servisi kapali: bu KALICI bir hata, retry anlamsiz.
        raise RuntimeError(
            f"OLLAMA_BAGLANTI_YOK: {C.OLLAMA_HOST} adresine ulasilamiyor. "
            f"'ollama serve' calisiyor mu? ({exc})"
        ) from exc

    if resp.status_code == 404:
        raise RuntimeError(
            f"OLLAMA_MODEL_YOK: '{C.OLLAMA_MODEL}' bulunamadi. "
            f"'ollama pull {C.OLLAMA_MODEL}' ile indir."
        )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


from src.generate_seed import _call_gemini, _call_groq  # noqa: E402

PROVIDERS = {
    "openrouter": _call_openrouter,
    "gemini": _call_gemini,
    "groq": _call_groq,
    "ollama": _call_ollama,
}

# Bu ifadeler gecerse hata KALICIDIR: ayni saglayiciyi tekrar denemek bos yere
# kota harcar. Hibrit modda bunlar saglayici degistirmeyi tetikler.
PERMANENT_MARKERS = (
    "RESOURCE_EXHAUSTED", "NOT_FOUND", "429", "UNAUTHENTICATED", "401",
    "quota", "rate limit", "OLLAMA_BAGLANTI_YOK", "OLLAMA_MODEL_YOK",
)


def is_permanent(msg: str) -> bool:
    low = msg.lower()
    return any(m.lower() in low for m in PERMANENT_MARKERS)


class Caller:
    """Saglayici secimini ve hibrit devri yoneten kucuk durum makinesi.

    Hibrit modda birincil saglayicidan KALICI hata gelirse (kota bitti gibi)
    yedege gecilir ve bir daha birincile donulmez -- kota gun icinde geri
    gelmeyecegi icin her kategoride tekrar denemek bos yere zaman kaybi olur.
    """

    def __init__(self, mode: str):
        self.mode = mode
        if mode == "hybrid":
            self.chain = ["openrouter", "ollama"]
        else:
            self.chain = [mode]
        self.idx = 0
        self.calls = Counter()      # saglayici -> basarili cagri sayisi

    @property
    def current(self) -> str:
        return self.chain[self.idx]

    def _switch(self) -> bool:
        """Yedege gecer. Gecilecek saglayici kalmadiysa False doner."""
        if self.idx + 1 >= len(self.chain):
            return False
        eski, self.idx = self.current, self.idx + 1
        print(f"\n  >>> {eski} KALICI hata verdi, kalan is '{self.current}' "
              f"saglayicisina devrediliyor.\n")
        return True

    def ask(self, prompt: str) -> tuple[str, str]:
        """(yanit, kullanilan_saglayici) doner. Tum saglayicilar biterse yukselir."""
        while True:
            provider = self.current
            fn = PROVIDERS[provider]
            last_err: Exception | None = None

            for attempt in range(1, C.LLM_MAX_RETRIES + 1):
                try:
                    out = fn(prompt)
                    self.calls[provider] += 1
                    return out, provider
                except Exception as exc:                      # noqa: BLE001
                    last_err = exc
                    if is_permanent(str(exc)):
                        break                                  # retry anlamsiz
                    wait = 2 ** attempt
                    print(f"    ! {provider} deneme {attempt} basarisiz "
                          f"({str(exc)[:90]}); {wait}sn bekleniyor")
                    time.sleep(wait)

            # Buraya dustuysek: ya kalici hata, ya da retry'lar tukendi.
            if not self._switch():
                raise RuntimeError(
                    f"Tum saglayicilar tukendi. Son hata ({provider}): {last_err}"
                )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def load_seed_examples() -> dict[tuple[str, str], list[str]]:
    """seed.jsonl'i (kategori, stil) -> metin listesi olarak gruplar.

    gold.jsonl BILEREK okunmaz -- saf test setinin few-shot'a sizmamasi
    projenin temel kurallarindan biri.
    """
    if not C.SEED_FILE.exists():
        sys.exit(f"HATA: seed dosyasi yok: {C.SEED_FILE}")

    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    with C.SEED_FILE.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            by_key[(r["kategori"], r["stil"])].append(r["metin"])
    return by_key


def pick_fewshot(seed_by_key, cat_key: str, style: str,
                 rng: random.Random) -> tuple[list[str], list[str]]:
    """(stil_ornekleri, konu_ornekleri) doner.

    Ikisi prompt'ta AYRI basliklar altinda gosterilir. Sebep: tek cagride tek
    stil istiyoruz ve en sik hata uzunluk kuralina uymamak. Farkli stildeki
    ornekleri ayni listede gostermek modele yanlis uzunluk sinyali veriyordu
    (orn. 'standart' isterken few-shot'ta 'cok_kisa' ornegi gormek). Ayni stil
    ornekleri UZUNLUGU, diger stiller ise sadece KONU alanini ogretiyor.
    """
    ayni_stil = list(seed_by_key.get((cat_key, style), []))
    rng.shuffle(ayni_stil)

    diger = [m for (c, s), lst in seed_by_key.items() if c == cat_key and s != style
             for m in lst]
    rng.shuffle(diger)

    pay = max(2, C.AMPLIFY_FEWSHOT_N // 2)
    return ayni_stil[:pay], diger[:C.AMPLIFY_FEWSHOT_N - pay]


def build_prompt(cat_key, style, n, fewshot, avoid, rng) -> str:
    cat = C.CATEGORIES[cat_key]
    stil_ornek, konu_ornek = fewshot

    slots = {ad: rng.sample(vals, min(4, len(vals)))
             for ad, vals in C.SLOT_VALUES.items()}
    slot_lines = "\n".join(f"  - {ad}: {', '.join(v)}" for ad, v in slots.items())

    stil_lines = "\n".join(f"  - {m}" for m in stil_ornek) or "  (ornek yok)"
    konu_block = ""
    if konu_ornek:
        konu_lines = "\n".join(f"  - {m}" for m in konu_ornek)
        konu_block = (
            f"\nAYNI KATEGORIDEN KONU ORNEKLERI — bunlar BASKA stilde yazilmis, "
            f"sadece hangi konularin bu kategoriye girdigini gormen icin. "
            f"UZUNLUKLARINI TAKLIT ETME:\n{konu_lines}\n"
        )

    avoid_block = ""
    if avoid:
        avoid_lines = "\n".join(f"  - {m}" for m in avoid)
        avoid_block = (
            f"\nBUNLAR ZATEN URETILDI — aynisini veya cok benzerini YAZMA:\n"
            f"{avoid_lines}\n"
        )

    return f"""Sen Metro İstanbul'da çalışan deneyimli bir operasyon personelisin.
İstasyonlardan ve trenlerden gelen arıza bildirimlerini günlük olarak yazıyorsun.

GÖREV: Aşağıdaki kategori ve YAZIM STİLİNE uygun {n} adet GERÇEKÇİ Türkçe arıza
bildirimi üret.

HEDEF KATEGORİ: {cat['display']}
Kapsam: {cat['scope']}
Bu kategoriye GİRMEYENLER: {cat['exclude']}

YAZIM STİLİ — hepsi bu stilde olacak: {style}
{C.STYLE_VARIANTS[style]}

STİL ÖRNEKLERİ — hedef stil ve uzunluk BUNLAR gibi olacak (kopyalama, taklit et):
{stil_lines}
{konu_block}{avoid_block}
ÇEŞİTLİLİK İÇİN MALZEME — bunlardan yararlan, hepsini kullanmak zorunda değilsin:
{slot_lines}

KURALLAR:
1. Her bildirim tek bir cümle veya en fazla iki kısa cümle olsun.
2. Bildirimler birbirinden AÇIKÇA farklı olsun: farklı ekipman, farklı konum,
   farklı belirti. Aynı cümlenin kelime değiştirilmiş hali OLMASIN.
3. Ekipman kodu (YM-03, PSD-08, BSO-02 gibi) en fazla ÜÇTE BİRİNDE geçsin.
4. İstasyon adı kullanacaksan YALNIZCA gerçekten var olan İstanbul metro
   istasyonlarını kullan; yukarıdaki listeden seçmen en iyisi. İSİM UYDURMA
   ve iki istasyon adını birbirine YAPIŞTIRMA. Aynı istasyonu ikiden fazla
   kullanma.
4b. Teknik terim de uydurma: emin olmadığın bir parça adı yerine günlük dille
   anlat ("motor sesi geliyor", "kapı kilitlenmiyor" gibi).
5. Bildirim kategorinin kapsamına KESİN olarak girsin; sınırda örnek üretme.
6. En fazla dörtte birinde kategori adını çağrıştıran kelime (yazılım,
   elektrik, güvenlik, temizlik, mekanik) geçsin. Kalanlarda sadece BELİRTİYİ
   anlat.
7. Sadece bildirim metnini yaz; numara, tire, açıklama ekleme.
8. STİLİN KELİME SAYISI ARALIĞINA harfiyen uy. Bu kurala uymamak en sık
   yapılan hatadır, {n} bildirimin HEPSİ aralıkta olmalı.
9. "{style}" stili "yazim_yanlisi" DEĞİLSE doğru Türkçe yazım ZORUNLUDUR
   (ç, ğ, ı, ö, ş, ü harflerini doğru kullan).

ÇIKTI FORMATI — yalnızca geçerli JSON, başka hiçbir şey yazma:
{{"bildirimler": [{{"metin": "..."}}, ...]}}

Toplam {n} adet üret."""


# ---------------------------------------------------------------------------
# Veri yonetimi
# ---------------------------------------------------------------------------

def load_existing() -> list[dict]:
    if not C.RAW_FILE.exists():
        return []
    with C.RAW_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_all(records: list[dict]) -> None:
    with C.RAW_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def is_near_dup(yeni_norm: str, mevcut_norms: list[str]) -> bool:
    """review.py'nin benzerlik olcusunu yeniden kullanir -- Adim 3'teki
    kumeleme ile ayni olcut, boylece burada gecen bir kayit orada surpriz
    yapmaz."""
    return any(R.similarity(yeni_norm, m) >= C.NEAR_DUP_THRESHOLD
               for m in mevcut_norms)


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def amplify(mode: str, hedef: int, kategoriler: list[str], dry_run: bool,
            replace_source: str | None = None) -> None:
    rng = random.Random(C.SEED)
    seed_by_key = load_seed_examples()
    caller = Caller(mode)

    records = load_existing()

    if replace_source:
        # Belirli bir saglayicidan gelen kayitlari atip yerine yenisini
        # urettirmek icin. Kategoriyi tamamen sifirlayan bir secenege gore
        # avantaji: karisik kategorilerde (orn. altyapi_insaat = 86 Nemotron +
        # 100 Ollama) IYI kayitlar korunur, sadece hedeflenen kaynak degisir.
        # Silinen kayitlar near-dup havuzundan da cikar, boylece yeni model
        # ayni konulari serbestce yeniden yazabilir.
        onceki = len(records)
        silinenler = Counter(
            r["kategori"] for r in records
            if r["kategori"] in kategoriler
            and r.get("kaynak", "").startswith(replace_source)
        )
        records = [
            r for r in records
            if not (r["kategori"] in kategoriler
                    and r.get("kaynak", "").startswith(replace_source))
        ]
        print(f"--replace-source {replace_source}: {onceki - len(records)} kayit "
              f"silindi, yerine yenisi uretilecek")
        for k, n in silinenler.items():
            print(f"    {C.DISPLAY_NAME[k]:<26} -{n}")
        print()
    # (kategori, stil) -> o gruptaki metinler ve normalize hallleri
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    norms_by_cat: dict[str, list[str]] = defaultdict(list)
    for r in records:
        by_key[(r["kategori"], r["stil"])].append(r)
        norms_by_cat[r["kategori"]].append(R.normalize(r["metin"]))

    stil_hedef = max(1, hedef // len(C.STYLE_KEYS))

    print(f"=== COGALTMA ({mode}) ===")
    print(f"hedef: {hedef}/kategori ({stil_hedef}/stil) x {len(kategoriler)} "
          f"kategori = {hedef * len(kategoriler)} ornek")
    if records:
        print(f"(devam ediliyor: diskte {len(records)} kayit var)")
    print()

    reddedilen = Counter()

    for cat_key in kategoriler:
        for style in C.STYLE_KEYS:
            key = (cat_key, style)
            while len(by_key[key]) < stil_hedef:
                eksik = stil_hedef - len(by_key[key])
                n = min(C.AMPLIFY_BATCH_SIZE, max(5, eksik + 5))  # biraz fazla iste

                fewshot = pick_fewshot(seed_by_key, cat_key, style, rng)
                mevcut = [r["metin"] for r in by_key[key]]
                avoid = rng.sample(mevcut, min(C.AMPLIFY_AVOID_N, len(mevcut)))
                prompt = build_prompt(cat_key, style, n, fewshot, avoid, rng)

                if dry_run:
                    print("=" * 78)
                    print(f"DRY-RUN prompt ornegi: {cat_key} / {style} / {n} adet")
                    print("=" * 78)
                    print(prompt)
                    return

                etiket = f"{C.DISPLAY_NAME[cat_key]:<26} {style:<14}"
                print(f"{etiket} {len(by_key[key]):>3}/{stil_hedef} ...",
                      end=" ", flush=True)

                try:
                    raw, provider = caller.ask(prompt)
                    items = parse_response(raw)
                except RuntimeError as exc:
                    print(f"DURDURULDU: {exc}")
                    save_all(records)
                    _rapor(records, caller, reddedilen, hedef, kategoriler)
                    return
                except (ValueError, json.JSONDecodeError) as exc:
                    # Bozuk JSON tek seferlik bir talihsizlik -- tum calistirmayi
                    # cokertmek yerine bu partiyi atlayip devam ediyoruz.
                    print(f"JSON hatasi, parti atlandi: {str(exc)[:60]}")
                    reddedilen["json"] += 1
                    continue

                eklendi = 0
                for it in items:
                    if len(by_key[key]) >= stil_hedef:
                        break
                    metin = " ".join(it["metin"].split())
                    if not (C.MIN_CHARS <= len(metin) <= C.MAX_CHARS):
                        reddedilen["uzunluk_sinir"] += 1
                        continue
                    norm = R.normalize(metin)
                    if is_near_dup(norm, norms_by_cat[cat_key]):
                        reddedilen["near_dup"] += 1
                        continue

                    kayit = {
                        "metin": metin,
                        "kategori": cat_key,
                        "stil": style,
                        "kaynak": f"{provider}:amplify",
                    }
                    records.append(kayit)
                    by_key[key].append(kayit)
                    norms_by_cat[cat_key].append(norm)
                    eklendi += 1

                print(f"+{eklendi} ({provider})")
                save_all(records)          # her partiden sonra diske yaz

                if eklendi == 0:
                    # Model bu (kategori, stil) icin yeni bir sey uretemiyor;
                    # sonsuz donguye girmemek icin bu grubu birakiyoruz.
                    print(f"{' ' * 45}-> yeni ornek gelmiyor, bu grup birakildi")
                    reddedilen["doygun"] += 1
                    break

    save_all(records)
    _rapor(records, caller, reddedilen, hedef, kategoriler)


def _rapor(records, caller, reddedilen, hedef, kategoriler) -> None:
    print(f"\n-> {len(records)} kayit diskte: {C.RAW_FILE}")

    by_cat = Counter(r["kategori"] for r in records)
    print(f"\n{'kategori':<28} {'adet':>5}  stil dagilimi")
    for k in C.CATEGORY_KEYS:
        if k not in kategoriler and not by_cat[k]:
            continue
        stiller = Counter(r["stil"] for r in records if r["kategori"] == k)
        dag = " ".join(f"{s[:4]}:{stiller.get(s, 0)}" for s in C.STYLE_KEYS)
        flag = "" if by_cat[k] >= hedef else f"   <-- {hedef - by_cat[k]} eksik"
        print(f"{C.DISPLAY_NAME[k]:<28} {by_cat[k]:>5}  {dag}{flag}")

    print(f"\nsaglayici katkisi (basarili cagri): {dict(caller.calls) or '-'}")
    kaynaklar = Counter(r["kaynak"] for r in records)
    print(f"kayit kaynagi: {dict(kaynaklar)}")
    if reddedilen:
        print(f"reddedilen: {dict(reddedilen)}")

    eksik = [k for k in kategoriler if by_cat[k] < hedef]
    if eksik:
        print(f"\n{len(eksik)} kategori hedefin altinda. Ayni komutu tekrar "
              f"calistir, kaldigi yerden devam eder.")
    else:
        print("\nHedefe ulasildi. Sonraki adim: python -m src.review --file amplified")


def main() -> None:
    ap = argparse.ArgumentParser(description="Adim 2b -- seed'den cogaltma")
    ap.add_argument("--provider",
                    choices=["hybrid", "openrouter", "gemini", "groq", "ollama"],
                    default=C.AMPLIFY_PROVIDER)
    ap.add_argument("--target", type=int, default=C.TARGET_PER_CATEGORY,
                    help="kategori basina hedef ornek sayisi")
    ap.add_argument("--category", nargs="+", choices=list(C.CATEGORY_KEYS),
                    metavar="KEY", help="sadece bu kategori(ler)")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM cagirmadan ilk prompt'u yazdirip cik")
    ap.add_argument("--replace-source", choices=["ollama", "openrouter"],
                    metavar="SAGLAYICI",
                    help="bu saglayicidan gelen mevcut kayitlari silip yerine "
                         "yenisini uret (kategori suzgeci varsa sadece onlarda)")
    args = ap.parse_args()

    amplify(
        mode=args.provider,
        hedef=args.target,
        kategoriler=args.category or list(C.CATEGORY_KEYS),
        dry_run=args.dry_run,
        replace_source=args.replace_source,
    )


if __name__ == "__main__":
    main()
