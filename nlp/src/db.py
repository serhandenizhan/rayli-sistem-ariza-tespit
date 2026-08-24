"""
Adim 8 — Log veritabani (SQLite).

Kullanicinin API'ye yazdigi HER cumleyi, mevcut egitim havuzuyla BIRLIKTE
kayit altina alir. Bunun amaci gozlem ve gelecekteki elle egitim turu icin
malzeme biriktirmek -- OTOMATIK egitime sokmak DEGIL.

NEDEN OTOMATIK EGITIM YOK: kullanicinin yazdigi bir cumle icin sistemin kendi
tahmini tek "etiket" adayidir ve bu tahmin YANLIS olabilir. Etiketsiz/dogrulanmamis
veriyle otomatik egitmek, modelin kendi hatalarini dogru sanip pekistirmesi
riskini tasir (confirmation bias). Bu proje boyunca veri kalitesine verilen
onem (elle triyaj, SINIR/YABANCI bayraklari, gold'un bagimsizligi) de ayni
gerekceyle otomatik/denetimsiz veri girisine karsi.

Bunun yerine: her tahmin `dogrulandi` alani NULL olarak loglanir. Kullanici
arayuzde "Dogru" / "Yanlis" ile onaylarsa bu alan 1/0 olur. SADECE onaylanan
(dogrulandi=1) kayitlar `/logs/export` ile disari alinip, kullanicinin kendi
inisiyatifiyle egitim havuzuna elle katilabilir (bkz. CLAUDE.md).

Kullanim:
    from src import db
    db.init()                      # tablo yoksa olustur + gecmis veriyi sec
    db.logla(metin, kategori, guven, kaynak="canli")
    db.kategori_dagilimi()
    db.dogrula(id, dogru=True)
"""

from __future__ import annotations

import csv
import sqlite3
import time
from contextlib import contextmanager

from src import config as C

_SEMA = """
CREATE TABLE IF NOT EXISTS bildirimler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metin TEXT NOT NULL,
    kategori TEXT NOT NULL,
    guven REAL,
    kaynak TEXT NOT NULL,          -- 'gecmis' (mevcut havuz) | 'canli' (API istegi)
    dogrulandi INTEGER,            -- NULL=incelenmedi, 1=dogru, 0=yanlis
    dogru_kategori TEXT,           -- dogrulandi=0 ise kullanicinin duzelttigi kategori
    -- Yapisal alanlar: duplicate tespiti icin gerekli (ayni istasyon + ayni
    -- ekipman + kisa zaman araligi = muhtemelen ayni olay). Tahmin aninda
    -- extract.py'den geliyor, bos olabilir.
    istasyon TEXT,
    ekipman TEXT,
    intent TEXT,
    oncelik TEXT,
    zaman TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bildirim_kategori ON bildirimler(kategori);
CREATE INDEX IF NOT EXISTS idx_bildirim_kaynak ON bildirimler(kaynak);
CREATE INDEX IF NOT EXISTS idx_bildirim_dup ON bildirimler(istasyon, ekipman, zaman);
"""


def _simdi_utc() -> str:
    """Suanki zamani UTC olarak ISO bicimde doner.

    GERCEK HATA (bulundu 24 Agu 2026): daha once time.strftime() YEREL saat
    dilimini kullaniyordu, ama olasi_tekrar() ve son_kayit_tekrar_mi()
    SQLite'in datetime('now', ...) fonksiyonuyla karsilastiriyor -- o da
    UTC doner. Turkiye UTC+3 oldugu icin her kayit gercekte "3 saat sonraya"
    yazilmis gibi duruyordu; sonuc: 30 saniyelik dene-yanila korumasi ve
    15 dakikalik tekrar-bildirim penceresi fiilen ~3 saate genisliyordu.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


@contextmanager
def _baglanti():
    conn = sqlite3.connect(C.LOG_DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    """Tabloyu olusturur ve BOSSA gecmis egitim havuzunu (clean.csv) tek
    seferlik seed'ler. Idempotent: ikinci cagrida hicbir sey yapmaz."""
    with _baglanti() as conn:
        conn.executescript(_SEMA)
        (zaten_var,) = conn.execute(
            "SELECT COUNT(*) FROM bildirimler WHERE kaynak = 'gecmis'"
        ).fetchone()
        if zaten_var:
            return
        if not C.CLEAN_FILE.exists():
            return
        with C.CLEAN_FILE.open(encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
        simdi = _simdi_utc()
        conn.executemany(
            "INSERT INTO bildirimler (metin, kategori, guven, kaynak, zaman) "
            "VALUES (?, ?, NULL, 'gecmis', ?)",
            [(r["metin"], r["kategori"], simdi) for r in satirlar],
        )
        print(f"[db] gecmis havuz seed'lendi: {len(satirlar)} kayit")


def logla(metin: str, kategori: str, guven: float, kaynak: str = "canli",
          istasyon: str | None = None, ekipman: str | None = None,
          intent: str | None = None, oncelik: str | None = None) -> int:
    with _baglanti() as conn:
        cur = conn.execute(
            "INSERT INTO bildirimler "
            "(metin, kategori, guven, kaynak, istasyon, ekipman, intent, "
            " oncelik, zaman) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (metin, kategori, guven, kaynak, istasyon, ekipman, intent,
             oncelik, _simdi_utc()),
        )
        return cur.lastrowid


# Ayni olayin tekrar bildirilmis sayilmasi icin gereken zaman penceresi.
# 15 dakika: bir arizanin fark edilip birden fazla yolcu/personel tarafindan
# bildirilmesi icin makul bir sure. Daha uzun tutmak farkli olaylari
# birlestirme riskini artirir (ayni merdiven sabah bozulup ogleden sonra
# tekrar bozulabilir ve bu IKI ayri is emridir).
DUPLICATE_PENCERE_DK = 15


def olasi_tekrar(kategori: str, istasyon: str | None, ekipman: str | None,
                 dakika: int = DUPLICATE_PENCERE_DK) -> dict | None:
    """Ayni olayin daha once bildirilip bildirilmedigini kontrol eder.

    Olcut: ayni kategori + ayni istasyon + ayni ekipman + son N dakika.
    Istasyon veya ekipman bilinmiyorsa tekrar KARARI VERILMEZ (None doner) --
    "Kadikoy'de bir sey bozuk" ile "Levent'te bir sey bozuk" ayni olay
    sayilamaz, eksik bilgiyle birlestirme yanlis is emri kapatmaya yol acar.
    """
    if not istasyon or not ekipman:
        return None
    with _baglanti() as conn:
        satir = conn.execute(
            "SELECT id, metin, zaman, COUNT(*) OVER () AS toplam "
            "FROM bildirimler "
            "WHERE kaynak = 'canli' AND kategori = ? AND istasyon = ? "
            "  AND ekipman = ? AND zaman >= datetime('now', ?) "
            "ORDER BY zaman DESC LIMIT 1",
            (kategori, istasyon, ekipman, f"-{dakika} minutes"),
        ).fetchone()
    if not satir:
        return None
    return {"ilk_kayit_id": satir["id"], "ilk_metin": satir["metin"],
            "zaman": satir["zaman"], "sayi": satir["toplam"]}


def son_kayit_tekrar_mi(metin: str, saniye: int = 30) -> bool:
    """Ayni metin son N saniyede zaten loglandi mi (dene-yanila spam koruması)."""
    with _baglanti() as conn:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM bildirimler "
            "WHERE metin = ? AND kaynak = 'canli' "
            "AND zaman >= datetime('now', ?)",
            (metin, f"-{saniye} seconds"),
        ).fetchone()
        return n > 0


def dogrula(id_: int, dogru: bool, duzeltilmis_kategori: str | None = None) -> bool:
    with _baglanti() as conn:
        cur = conn.execute(
            "UPDATE bildirimler SET dogrulandi = ?, dogru_kategori = ? WHERE id = ?",
            (1 if dogru else 0, duzeltilmis_kategori, id_),
        )
        return cur.rowcount > 0


def kategori_dagilimi() -> list[dict]:
    """Tum kaynaklar (gecmis + canli) birlesik kategori sayimi."""
    with _baglanti() as conn:
        satirlar = conn.execute(
            "SELECT kategori, COUNT(*) AS sayi, "
            "SUM(CASE WHEN kaynak = 'canli' THEN 1 ELSE 0 END) AS yeni_sayi "
            "FROM bildirimler GROUP BY kategori"
        ).fetchall()
    return [dict(r) for r in satirlar]


def toplam_kayit() -> dict:
    with _baglanti() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS toplam, "
            "SUM(CASE WHEN kaynak = 'canli' THEN 1 ELSE 0 END) AS canli, "
            "SUM(CASE WHEN dogrulandi = 1 THEN 1 ELSE 0 END) AS onayli_dogru, "
            "SUM(CASE WHEN dogrulandi = 0 THEN 1 ELSE 0 END) AS onayli_yanlis "
            "FROM bildirimler"
        ).fetchone()
    return dict(r)


def kategorisiz_yanlislari_getir() -> list[dict]:
    """dogrulandi=0 ama dogru_kategori hala bos olan kayitlar.

    Kullanici arayuzde "Yanlis" deyip kategori secmeden "atla"yi tikladiginda
    boyle bir kayit olusur. `src/resolve_logs.py` ile egitimden once
    kategorize edilmeleri gerekir -- yoksa `onayli_kayitlari_disa_aktar()`
    bunlari dislar (asagida)."""
    with _baglanti() as conn:
        satirlar = conn.execute(
            "SELECT * FROM bildirimler WHERE dogrulandi = 0 AND dogru_kategori IS NULL "
            "ORDER BY zaman"
        ).fetchall()
    return [dict(r) for r in satirlar]


def son_kayitlari_getir(limit: int = 50) -> list[dict]:
    """En son N bildirim, zamana gore azalan sirada.

    Birlesik dashboard'daki olay akisi icin: sensor tarafinin alarm ozetiyle
    (rayli_kayit.db) zaman damgasina gore ayni listede gosterilebilsin diye.
    """
    with _baglanti() as conn:
        satirlar = conn.execute(
            "SELECT id, metin, kategori, guven, kaynak, dogrulandi, "
            "dogru_kategori, istasyon, ekipman, intent, oncelik, zaman "
            "FROM bildirimler ORDER BY zaman DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in satirlar]


def onayli_kayitlari_disa_aktar() -> list[dict]:
    """dogrulandi IS NOT NULL olan (kullanici tarafindan incelenmis) kayitlar.

    generate_data.py'nin urettigi jsonl semasiyla uyumlu alanlar dondurur ki
    elle data/raw'a katilabilsin: metin + kategori (dogru_kategori varsa o,
    yoksa orijinal tahmin) + kaynak izi.

    "Yanlis" + kategorisiz (dogru_kategori NULL) kayitlar DISLANIR -- kategori
    alani None ile disari cikip egitim verisini bozmasin diye. Bunlari
    kapatmak icin once `python -m src.resolve_logs` calistirilmali.
    """
    with _baglanti() as conn:
        satirlar = conn.execute(
            "SELECT * FROM bildirimler WHERE dogrulandi IS NOT NULL "
            "AND NOT (dogrulandi = 0 AND dogru_kategori IS NULL) "
            "ORDER BY zaman"
        ).fetchall()
    cikti = []
    for r in satirlar:
        kategori = r["dogru_kategori"] if r["dogrulandi"] == 0 else r["kategori"]
        cikti.append({
            "metin": r["metin"],
            "kategori": kategori,
            "stil": None,
            "kaynak": f"api_onayli:{'dogru' if r['dogrulandi'] else 'duzeltildi'}",
            "orijinal_tahmin": r["kategori"],
            "guven": r["guven"],
            "zaman": r["zaman"],
        })
    return cikti
