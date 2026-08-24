"""
Adim 2a-3 -- Elle onaylanan duzeltmeleri seed.jsonl / gold.jsonl'e uygular.

Ne yapar:
  - Belirtilen kayitlari kategori+metin eslesmesiyle SILER
  - Belirtilen kayitlarin 'stil' alanini DEGISTIRIR (metne dokunmadan)
  - Belirtilen kayitta metin icinde bir DEGISIKLIK yapar (anlam duzeltmesi)

Her islem oncesi/sonrasi rapor basar, eslesme bulunamazsa uyarir (sessizce
gecmez -- boylece encoding/bosluk farki gibi sorunlar hemen fark edilir).

Kullanim:
    python -m src.apply_review
"""

from __future__ import annotations

import json

from src import config as C

# ---------------------------------------------------------------------------
# Onaylanan degisiklikler (kategori, metin) -> islem
# ---------------------------------------------------------------------------

SEED_DELETE = [
    ("arac_tren", "Makine kabinindeki ana fren manası takılmıyor."),
    ("istasyon_mekanik", "Yürüyen merdiven durdu"),
    ("guvenlik_emniyet", "Acil çıkış kilidi takılı"),
]

SEED_STYLE_FIX = [
    # (kategori, metin, yeni_stil)
    (
        "altyapi_insaat",
        "Yenikapı Marmaray transfer tüneli drenaj pompa havuzu taşması meydana geldi.",
        "standart",
    ),
]

SEED_TEXT_FIX = [
    # (kategori, eski_metin, yeni_metin)
    (
        "yolcu_operasyon",
        "Kadıköy istasyonunda peron yoğunluğu nedeniyle seferler gecikmemiştir.",
        "Kadıköy istasyonunda peron yoğunluğu nedeniyle seferler gecikmiştir.",
    ),
    # "fren manasi" diye bir parca yok; ayni ifadenin 'standart' stilindeki
    # ikizi silinmisti ama bu 'yazim_yanlisi' varyanti gozden kacmisti.
    # Few-shot yemi oldugu icin hatali terimi 1600 ornege tasima riski vardi.
    (
        "arac_tren",
        "makinist kabini fren manasi tikaniyo",
        "makinist kabini fren manivelasi tikaniyo",
    ),
    # Ucuncu tur (19 Agu 2026): elle okumada bulunan, VAR OLMAYAN kelimeler.
    # Olcut stil sozlesmesi: bu uc kayit 'standart'/'devrik' etiketli, config
    # bu stiller icin dogru Turkce yazimi ZORUNLU tutuyor (yazim hatasi sadece
    # 'yazim_yanlisi' stiline ait). Gercekci klavye hatasi ile stil sozlesmesi
    # ihlali farkli seyler.
    (
        "yazilim_sistem",           # "torna" tezgah demek, kastedilen "turnike"
        "İstanbulkart okuyucu yanıt vermiyor, giriş tornası.",
        "İstanbulkart okuyucu yanıt vermiyor, giriş turnikesi.",
    ),
    (
        "guvenlik_emniyet",         # "merkeziyet" boyle bir kullanim yok
        "Acil durum butonu basıldığında merkeziyete sinyal gitmiyor.",
        "Acil durum butonu basıldığında merkeze sinyal gitmiyor.",
    ),
    (
        "altyapi_insaat",           # "kirismak" burusmak demek; betonarme kirilir
        "Taksim M2 viyadukt ray altı betonarme kırışması onarım bekliyor.",
        "Taksim M2 viyadukt ray altı betonarme kırılması onarım bekliyor.",
    ),
]

GOLD_DELETE: list[tuple[str, str]] = [
    # Taksonomiye gore YANLIS KATEGORI: config'de "peron kapisi (PSD)" acikca
    # istasyon_mekanik kapsaminda, guvenlik_emniyet kapsaminda degil. Gold'da
    # yanlis etiket, dogru tahmini yanlis saydirir -- yazim hatasinin aksine
    # tolere edilemez. Silinip yerine yenisi uretildi.
    ("guvenlik_emniyet", "Peron kapısı aralıklı açılıyor, sıkışma riski var."),
]

GOLD_STYLE_FIX = [
    (
        "elektrik_enerji",
        "Katener hattı gerilimi ani düşüş gösterdi, seferler manuel modda sürülüyor.",
        "standart",
    ),
    (
        "elektrik_enerji",
        "Jeneratör test çalışması sırasında aktarma anahtarı takılmadı, istasyon enerjisiz kaldı.",
        "standart",
    ),
    (
        "elektrik_enerji",
        "Ana dağıtım panosunda sigorta atması, B blok aydınlatması yok.",
        "standart",
    ),
    (
        "elektrik_enerji",
        "Peron kenarı acil durdurma kutusu enerjisiz, led yanmıyor.",
        "standart",
    ),
    # guvenlik_emniyet yeniden uretimi (--force) sonrasi: iki kayit etiketinden
    # daha uzun cikti. Metin dogru ve gercekci, sadece stil etiketi yanlis --
    # metne dokunmadan etiket duzeltiliyor.
    (
        "guvenlik_emniyet",
        "CCTV kayıt cihazı görüntü vermiyor, kamera 12 görüntüsü donmuş durumda.",
        "standart",     # 10 kelime: devrik(4-9) degil, standart(8-18)
    ),
    (
        "guvenlik_emniyet",
        "Kamera 07 kör nokta oluştu, görüntü gelmiyor.",
        "devrik",       # 7 kelime: cok_kisa(3-6) degil, devrik(4-9)
    ),
]

GOLD_TEXT_FIX: list[tuple[str, str, str]] = []


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------

def load(path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save(path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def apply_changes(
    name: str,
    path,
    deletes: list[tuple[str, str]],
    style_fixes: list[tuple[str, str, str]],
    text_fixes: list[tuple[str, str, str]],
) -> None:
    records = load(path)
    before = len(records)
    print(f"\n=== {name} ({path.name}) -- baslangic: {before} kayit ===")

    # Bu script birden fazla kez calistirilabilir: liste birikimli bir
    # "uygulanan duzeltmeler" kaydidir, her yeni triyaj turunda altina ekleniyor.
    # Bu yuzden "eslesme yok" iki farkli anlama gelir ve ayirt edilmesi sart:
    #   - duzeltme zaten uygulanmis (onceki calistirmada)  -> normal, sessiz gec
    #   - hicbir izi yok                                    -> gercek UYARI
    #     (encoding/bosluk farki ya da yanlis yazilmis hedef metin)
    applied_before = 0

    # Silme
    to_delete = set(deletes)
    found_delete = set()
    kept = []
    for r in records:
        key = (r["kategori"], r["metin"])
        if key in to_delete:
            found_delete.add(key)
            print(f"  SILINDI [{r['kategori']}] {r['metin'][:60]}")
        else:
            kept.append(r)
    records = kept
    # Silmede "zaten uygulanmis" ile "hic bulunamadi" ayirt edilemez (silinen
    # kaydin geride izi kalmaz). Bu yuzden bilgi notu olarak basiyoruz.
    for k in to_delete - found_delete:
        applied_before += 1
        print(f"  (zaten silinmis) {k[1][:60]}")

    # Stil duzeltme
    style_map = {(cat, txt): new_style for cat, txt, new_style in style_fixes}
    found_style = set()
    for r in records:
        key = (r["kategori"], r["metin"])
        if key in style_map:
            old = r["stil"]
            found_style.add(key)
            if old == style_map[key]:
                applied_before += 1
                print(f"  (stil zaten dogru) [{r['kategori']}] {old}  "
                      f"({r['metin'][:50]})")
                continue
            r["stil"] = style_map[key]
            print(f"  STIL DEGISTI [{r['kategori']}] {old} -> {r['stil']}  "
                  f"({r['metin'][:50]})")
    for k in set(style_map) - found_style:
        print(f"  UYARI: stil duzeltilecek kayit bulunamadi -> {k}")

    # Metin duzeltme
    text_map = {(cat, old): new for cat, old, new in text_fixes}
    present = {(r["kategori"], r["metin"]) for r in records}
    found_text = set()
    for r in records:
        key = (r["kategori"], r["metin"])
        if key in text_map:
            new_text = text_map[key]
            print(f"  METIN DUZELTILDI [{r['kategori']}]\n"
                  f"    eski: {r['metin']}\n    yeni: {new_text}")
            r["metin"] = new_text
            found_text.add(key)
    for cat, old, new in text_fixes:
        if (cat, old) in found_text:
            continue
        # Eski metin yok ama yenisi duruyorsa duzeltme onceden uygulanmistir.
        if (cat, new) in present:
            applied_before += 1
            print(f"  (metin zaten duzeltilmis) [{cat}] {new[:55]}")
        else:
            print(f"  UYARI: metni duzeltilecek kayit bulunamadi -> {(cat, old)}")

    save(path, records)
    print(f"-> {len(records)} kayit yazildi ({before - len(records)} silindi, "
          f"{applied_before} duzeltme zaten uygulanmisti)")


def main() -> None:
    apply_changes("SEED", C.SEED_FILE, SEED_DELETE, SEED_STYLE_FIX, SEED_TEXT_FIX)
    apply_changes("GOLD", C.GOLD_FILE, GOLD_DELETE, GOLD_STYLE_FIX, GOLD_TEXT_FIX)
    print("\nBitti. Kontrol icin: python -m src.review --only-flagged")


if __name__ == "__main__":
    main()
