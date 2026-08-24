"""
Adim 2a — Seed ve gold veri uretimi.

Gemini veya Claude kullanarak her kategori icin yuksek kaliteli, elle
gozden gecirilecek ornek bildirimler uretir.

  seed.jsonl : few-shot yemi olarak Ollama'ya verilecek  (12/kategori)
  gold.jsonl : few-shot'ta ASLA kullanilmaz, saf test seti (10/kategori)

Ikisi ayri cagrilarla ve birbirini gormeden uretilir; boylece gold seti
seed'lerin varyasyonu olmaz.

Kullanim:
    python -m src.generate_seed                 # ikisini de uret
    python -m src.generate_seed --only seed
    python -m src.generate_seed --only gold
    python -m src.generate_seed --provider claude
    python -m src.generate_seed --provider groq
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

from src import config as C

load_dotenv()


# ---------------------------------------------------------------------------
# Saglayici katmani
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("HATA: GEMINI_API_KEY tanimli degil (.env dosyasina ekle).")

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=C.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=C.LLM_TEMPERATURE,
            response_mime_type="application/json",
        ),
    )
    return resp.text


def _call_claude(prompt: str) -> str:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("HATA: ANTHROPIC_API_KEY tanimli degil (.env dosyasina ekle).")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=C.CLAUDE_MODEL,
        max_tokens=4000,
        temperature=C.LLM_TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def _call_groq(prompt: str) -> str:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("HATA: GROQ_API_KEY tanimli degil (.env dosyasina ekle).")

    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=C.GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=C.LLM_TEMPERATURE,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _call_openrouter(prompt: str) -> str:
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("HATA: OPENROUTER_API_KEY tanimli degil (.env dosyasina ekle).")

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            # OpenRouter bu basliklari rate-limit/izleme icin tavsiye ediyor,
            # zorunlu degil ama iyi pratik.
            "HTTP-Referer": "https://github.com/metro-istanbul-ariza",
            "X-Title": "Metro Istanbul Ariza Tespit",
        },
    )
    resp = client.chat.completions.create(
        model=C.OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=C.LLM_TEMPERATURE,
        max_tokens=8000,   # akil yurutme modelleri (orn. Nemotron Ultra) ic
                           # dusunme adimlarinda token tuketebilir, genis pay
    )
    content = resp.choices[0].message.content
    if not content:
        finish = resp.choices[0].finish_reason
        # Bazi "reasoning" modelleri max_tokens'i tamamen ic dusunmede
        # tuketip asil ciktiya hic sira birakmiyor. Bunu retry edilebilir
        # bir hata olarak isaretliyoruz, cagiran taraf tekrar dener.
        raise RuntimeError(
            f"OpenRouter bos icerik dondu (finish_reason={finish}). "
            f"Model muhtemelen max_tokens'i 'reasoning'de tuketti."
        )
    return content


PROVIDERS = {
    "gemini": _call_gemini,
    "claude": _call_claude,
    "groq": _call_groq,
    "openrouter": _call_openrouter,
}


def call_llm(prompt: str, provider: str) -> str:
    fn = PROVIDERS[provider]
    last_err = None
    for attempt in range(1, C.LLM_MAX_RETRIES + 1):
        try:
            return fn(prompt)
        except Exception as exc:            # noqa: BLE001
            last_err = exc
            msg = str(exc)
            # Kalici hatalarda (model yok / gunluk kota bitti) retry anlamsiz —
            # her deneme kotadan bir istek daha dusuruyor, hemen durup cikalim.
            if "RESOURCE_EXHAUSTED" in msg or "NOT_FOUND" in msg or "429" in msg:
                raise RuntimeError(
                    f"Kalici hata, retry denenmedi: {msg[:200]}"
                ) from exc
            wait = 2 ** attempt
            print(f"    ! deneme {attempt} basarisiz ({exc}); {wait}sn bekleniyor")
            time.sleep(wait)
    raise RuntimeError(f"LLM cagrisi {C.LLM_MAX_RETRIES} denemede basarisiz: {last_err}")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def build_prompt(cat_key: str, n: int, purpose: str) -> str:
    cat = C.CATEGORIES[cat_key]

    other_lines = "\n".join(
        f"  - {C.CATEGORIES[k]['display']}: {C.CATEGORIES[k]['scope'][:110]}..."
        for k in C.CATEGORY_KEYS if k != cat_key
    )

    style_lines = "\n".join(
        f"  - {name}: {desc}" for name, desc in C.STYLE_VARIANTS.items()
    )

    per_style = max(1, n // len(C.STYLE_KEYS))

    extra = ""
    if purpose == "gold":
        extra = (
            "\nBu örnekler bir DEĞERLENDİRME setidir. Kolay ve bariz örnekler "
            "yerine, gerçek hayatta karşılaşılacak zorlukta örnekler üret: "
            "kategori sınırlarına yakın, dolaylı anlatımlı, teknik terim içeren "
            "veya bağlamdan çıkarım gerektiren bildirimler tercih et.\n"
        )

    return f"""Sen Metro İstanbul'da çalışan deneyimli bir operasyon personelisin.
İstasyonlardan ve trenlerden gelen arıza bildirimlerini günlük olarak yazıyorsun.

GÖREV: Aşağıdaki kategoriye ait {n} adet GERÇEKÇİ Türkçe arıza bildirimi üret.

HEDEF KATEGORİ: {cat['display']}
Kapsam: {cat['scope']}
Bu kategoriye GİRMEYENLER: {cat['exclude']}

DİĞER KATEGORİLER (bunlara ait örnek ÜRETME, sadece sınırları bilmek için):
{other_lines}

YAZIM STİLLERİ — her stilden yaklaşık {per_style} adet üret:
{style_lines}
{extra}
KURALLAR:
1. Her bildirim tek bir cümle veya en fazla iki kısa cümle olsun.
2. Bildirimler birbirinden AÇIKÇA farklı olsun: farklı ekipman, farklı konum,
   farklı belirti. Aynı cümlenin kelime değiştirilmiş hali OLMASIN.
3. Ekipman kodu (YM-03, PSD-08, BSO-02, Turnike-05 gibi) sadece
   üreteceğin bildirimlerin EN FAZLA ÜÇTE BİRİNDE geçsin. Kalanlar sade
   günlük dille yazılsın: "asansör", "3 numaralı turnike", "peron kapısı".
4. İstasyon adı kullanacaksan gerçek İstanbul metro istasyonlarını kullan,
   doğru Türkçe yazımıyla (Mecidiyeköy, Şişli, Kadıköy gibi -- Mecidiyekoy
   veya Sisli DEĞİL). Aynı istasyon adını ikiden fazla kullanma.
5. Bildirim, kategorinin kapsamına KESİN olarak girsin; sınırda kalan
   belirsiz örnek üretme.
6. Bildirimlerin en fazla dörtte birinde kategori adını çağrıştıran kelime
   (yazılım, elektrik, güvenlik, temizlik, mekanik) geçebilir. Kalanlarda
   sadece BELİRTİYİ anlat.
7. Sadece bildirim metnini yaz; numara, tire, açıklama ekleme.
8. Her stil için verilen KELİME SAYISI aralığına harfiyen uy. Uzunluk
   çeşitliliği bu projede kritik; bu kurala uymamak en sık yapılan hatadır.
9. TÜM bildirimlerde doğru Türkçe yazım kullan (ç, ğ, ı, ö, ş, ü harflerini
   doğru yerlerde kullan) -- SADECE "yazim_yanlisi" stilinde bilinçli olarak
   bu harfleri düşür. Diğer üç stilde ("standart", "devrik", "cok_kisa")
   doğru Türkçe yazım ZORUNLUDUR, bu kural en az kural 8 kadar önemlidir.

ÇIKTI FORMATI — yalnızca geçerli JSON, başka hiçbir şey yazma:
{{"bildirimler": [{{"metin": "...", "stil": "standart"}}, ...]}}

"stil" alanı şu değerlerden biri olmalı: {", ".join(C.STYLE_KEYS)}
Toplam {n} adet üret."""


# ---------------------------------------------------------------------------
# Ayristirma
# ---------------------------------------------------------------------------

def parse_response(text: str) -> list[dict]:
    """LLM ciktisindan bildirim listesini cikarir. Kod bloklarina toleranslidir."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Yanitta JSON bulunamadi.")
        data = json.loads(match.group(0))

    items = data.get("bildirimler", data if isinstance(data, list) else [])
    out = []
    for it in items:
        if isinstance(it, str):
            out.append({"metin": it.strip(), "stil": "standart"})
        elif isinstance(it, dict) and it.get("metin"):
            out.append({
                "metin": str(it["metin"]).strip(),
                "stil": it.get("stil", "standart"),
            })
    return out


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def normalize_key(metin: str) -> str:
    return " ".join(metin.split()).lower()


def load_existing(out_path) -> dict[str, list[dict]]:
    """Diskteki mevcut kayitlari kategoriye gore gruplar (resume icin)."""
    by_cat: dict[str, list[dict]] = {k: [] for k in C.CATEGORY_KEYS}
    if not out_path.exists():
        return by_cat
    with out_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kategori") in by_cat:
                by_cat[r["kategori"]].append(r)
    return by_cat


def save_all(out_path, by_cat: dict[str, list[dict]]) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        for cat_key in C.CATEGORY_KEYS:
            for r in by_cat[cat_key]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def generate(
    purpose: str,
    provider: str,
    force: bool = False,
    categories: list[str] | None = None,
) -> None:
    n = C.SEED_PER_CATEGORY if purpose == "seed" else C.GOLD_PER_CATEGORY
    out_path = C.SEED_FILE if purpose == "seed" else C.GOLD_FILE
    min_ok = int(n * 0.8)   # bu kadari varsa kategori "tamam" sayilir

    # Kategori suzgeci verildiyse "tamamlama modu"ndayiz: %80 esigi devre disi,
    # hedef tam n. Boylece 9/10 gibi esigi gecmis ama eksik kalan bir kategori
    # elle tamamlanabilir (esik mantigi bunu otomatik tetiklemiyor).
    targets = categories or list(C.CATEGORY_KEYS)
    topup_mode = categories is not None
    threshold = n if topup_mode else min_ok

    print(f"\n=== {purpose.upper()} uretimi ({provider} / {n} adet/kategori) ===")
    if topup_mode:
        print(f"(tamamlama modu: sadece {', '.join(targets)} — hedef tam {n})")

    # Kategori suzgeciyle calisirken diskteki DIGER kategorilere asla
    # dokunulmaz; --force yalnizca secili kategoriyi sifirlar.
    by_cat = load_existing(out_path)
    if force:
        for k in targets:
            if by_cat[k]:
                print(f"(--force: {C.DISPLAY_NAME[k]} icin {len(by_cat[k])} kayit silindi)")
            by_cat[k] = []
    already = sum(len(v) for v in by_cat.values())
    if already and not force:
        print(f"(devam ediliyor: diskte {already} kayit var, yeterli kategoriler atlanacak)")

    quota_stopped = False
    failed_categories = []
    for i, cat_key in enumerate(C.CATEGORY_KEYS, 1):
        display = C.DISPLAY_NAME[cat_key]

        if cat_key not in targets:
            continue

        if len(by_cat[cat_key]) >= threshold:
            sources = {r.get("kaynak", "?").split(":")[0] for r in by_cat[cat_key]}
            src_note = f" [kaynak: {', '.join(sources)}]" if sources - {provider} else ""
            print(f"[{i}/{C.NUM_LABELS}] {display} ... atlandi "
                  f"(zaten {len(by_cat[cat_key])} adet{src_note})")
            continue

        print(f"[{i}/{C.NUM_LABELS}] {display} ...", end=" ", flush=True)

        try:
            raw = call_llm(build_prompt(cat_key, n, purpose), provider)
            items = parse_response(raw)
        except RuntimeError as exc:
            msg = str(exc)
            # Kota/kimlik dogrulama/model bulunamadi gibi KALICI hatalar tum
            # kategorileri etkiler, durmak mantikli. Diger hatalar (bozuk
            # JSON, bos icerik) muhtemelen o kategoriye ozgu bir talihsizlik
            # -- tum calistirmayi iptal etmek yerine bu kategoriyi atlayip
            # devam ediyoruz, ilerlemeyi kaybetmiyoruz.
            is_permanent = any(
                s in msg for s in ("RESOURCE_EXHAUSTED", "NOT_FOUND", "429",
                                    "UNAUTHENTICATED", "401")
            )
            if is_permanent:
                print(f"DURDURULDU ({exc})")
                quota_stopped = True
                break
            print(f"ATLANDI, hata: {exc}")
            failed_categories.append(display)
            time.sleep(1.5)
            continue
        except (ValueError, json.JSONDecodeError) as exc:
            # parse_response'un kendi hatasi (bozuk JSON, retry'siz).
            print(f"ATLANDI, JSON hatasi: {exc}")
            failed_categories.append(display)
            time.sleep(1.5)
            continue

        seen_local = {normalize_key(r["metin"]) for r in by_cat[cat_key]}

        # Gecerli, tekrar olmayan adaylari topla
        adaylar = []
        for it in items:
            metin = " ".join(it["metin"].split())
            key = normalize_key(metin)
            if key in seen_local or not (C.MIN_CHARS <= len(metin) <= C.MAX_CHARS):
                continue
            seen_local.add(key)
            adaylar.append({
                "metin": metin,
                "kategori": cat_key,
                "stil": it["stil"],
                "kaynak": f"{provider}:{purpose}",
            })

        # Tamamlama modunda LLM'den tam n adet istiyoruz ama sadece eksik kadari
        # gerekiyor. Hangilerini alacagimizi rastgele birakmak yerine, kategoride
        # AZ TEMSIL EDILEN stilleri once aliyoruz -- boylece tamamlama, stil
        # dengesini bozmak yerine duzeltiyor. Her secimden sonra sayim
        # guncellendigi icin birden fazla eklemede de denge korunur.
        stil_sayim = collections.Counter(r["stil"] for r in by_cat[cat_key])
        aday_sayisi = len(adaylar)
        kalan = max(0, n - len(by_cat[cat_key]))
        added = 0
        while adaylar and added < kalan:
            adaylar.sort(key=lambda r: stil_sayim[r["stil"]])   # stabil: esitlikte LLM sirasi
            r = adaylar.pop(0)
            by_cat[cat_key].append(r)
            stil_sayim[r["stil"]] += 1
            added += 1
        if aday_sayisi > added:
            print(f"({aday_sayisi - added} fazla aday kullanilmadi) ", end="")

        print(f"{added} yeni adet (toplam {len(by_cat[cat_key])})")
        save_all(out_path, by_cat)     # her kategoriden sonra diske yaz — guvenli
        time.sleep(1.5)     # ucretsiz katman hiz limitine saygi

    # Rapor icin diskten yeniden oku — eger bu calistirma hic basarili kategori
    # uretemediyse (ornegin ilk kategoride kalici hata aldiysa), by_cat bellekte
    # bos kalir ama disk hala onceki basarili calistirmanin verisini tasiyor
    # olabilir. Yanlis "0 kayit" raporu vermemek icin gercek dosya durumunu
    # kontrol ediyoruz.
    on_disk = load_existing(out_path)
    total = sum(len(v) for v in on_disk.values())
    print(f"\n-> {total} kayit diskte: {out_path}")

    for k in C.CATEGORY_KEYS:
        got = len(on_disk[k])
        if got >= n:
            flag = ""
        elif got >= min_ok:
            # Esigi geciyor ama hedefin altinda: otomatik tamamlanmaz, elle
            # --category ile doldurulabilir. Sessiz kalmamasi onemli.
            flag = f"   <-- {n - got} eksik (--category {k} ile tamamlanabilir)"
        else:
            flag = "   <-- EKSIK"
        print(f"   {C.DISPLAY_NAME[k]:<28} {got:>3}{flag}")

    if quota_stopped:
        print(
            "\nKOTA/HATA NEDENIYLE DURDURULDU. Ilerleme diske kaydedildi.\n"
            "Ayni komutu tekrar calistirdiginda kaldigi yerden devam eder.\n"
            "Farkli saglayici denemek icin: --provider claude"
        )
    elif failed_categories:
        print(
            f"\n{len(failed_categories)} kategori gecici hatayla atlandi: "
            f"{', '.join(failed_categories)}\n"
            "Ilerleme diske kaydedildi. Ayni komutu tekrar calistir, sadece "
            "eksik kategoriler yeniden denenir."
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed ve gold veri uretimi")
    ap.add_argument("--only", choices=["seed", "gold"], help="sadece birini uret")
    ap.add_argument("--provider", choices=list(PROVIDERS), default=C.SEED_PROVIDER)
    ap.add_argument(
        "--force", action="store_true",
        help="diskteki mevcut veriyi yok sayip bastan uret "
             "(--category ile birlikte: sadece o kategoriyi sifirlar)"
    )
    ap.add_argument(
        "--category", nargs="+", choices=list(C.CATEGORY_KEYS), metavar="KEY",
        help="sadece bu kategori(ler)i isle; %%80 esigi yerine tam hedefe "
             "tamamlar. Diger kategorilere dokunulmaz."
    )
    args = ap.parse_args()

    targets = [args.only] if args.only else ["seed", "gold"]
    for t in targets:
        generate(t, args.provider, force=args.force, categories=args.category)

    print(
        "\nSONRAKI ADIM: uretilen dosyalari ELLE gozden gecir.\n"
        "  - Yanlis kategoriye dusmus bildirim var mi?\n"
        "  - Turkcesi bozuk veya yapay duran cumle var mi?\n"
        "  - Ayni seyi soyleyen iki cumle var mi?\n"
        "Bu 176 cumlenin kalitesi, sonraki 1600 cumlenin tavanini belirliyor."
    )


if __name__ == "__main__":
    main()
