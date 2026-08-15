"""
Kalıcılık katmanı — tahminleri, alarmları ve metrikleri SQLite'a yazar.

Neden?
------
Canlı akış motoru her şeyi bellekte tutar; sunucu kapandığında geçmiş kaybolur. Gerçek bir
izleme sisteminde ise "bu dingil son bir haftada kaç kez alarm verdi?", "hangi hat en çok
arıza üretiyor?" gibi geçmişe dönük sorulara yanıt verilebilmelidir. Bu modül bunun için
küçük, bağımlılıksız (Python'un yerleşik `sqlite3`'ü) bir kayıt katmanı sağlar.

Tablolar
--------
- `calistirmalar` : her simülasyon oturumu (reset yapıldığında yenisi açılır)
- `alarmlar`      : yerleşik (histerezis sonrası) sınıf değişimleri; alarm süresi de tutulur
- `metrikler`     : periyodik doğruluk anlık görüntüleri (trend analizi için)

Yazma maliyeti düşüktür (tick başına birkaç satır) ve `bir_tick_isle` zaten ayrı bir iş
parçacığında çalıştığı için senkron yazmak olay döngüsünü bloke etmez.

Kullanım (tek başına, teşhis için):
    python rayli_kayit.py --ozet          # dingil/hat bazında alarm özeti
    python rayli_kayit.py --son 20        # son 20 alarm
"""

import argparse
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
VARSAYILAN_DB = os.path.join(DATA_DIR, "rayli_kayit.db")

SEMA = """
CREATE TABLE IF NOT EXISTS calistirmalar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    baslangic    TEXT NOT NULL,
    kaynak       TEXT,
    kor_mod      INTEGER,
    histerezis   INTEGER,
    dingil_sayisi INTEGER,
    hat_sayisi   INTEGER
);

CREATE TABLE IF NOT EXISTS alarmlar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    calistirma_id INTEGER NOT NULL,
    kayit_zamani  TEXT NOT NULL,     -- gerçek dünya zamanı (sorgular için)
    sim_zamani    TEXT,              -- simülasyondaki zaman damgası
    tick          INTEGER,
    axle          TEXT NOT NULL,
    line_id       TEXT,
    onceki        TEXT,
    yeni          TEXT NOT NULL,
    severity      TEXT,
    conf          REAL,
    istasyon      TEXT,
    tip           TEXT,              -- alarm | temizlendi
    sure_sn       REAL,              -- önceki durumun ne kadar sürdüğü
    oncelik       REAL,
    gercek        TEXT,              -- kör mod kapalıysa cevap anahtarı (doğrulama için)
    FOREIGN KEY (calistirma_id) REFERENCES calistirmalar(id)
);

CREATE TABLE IF NOT EXISTS metrikler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    calistirma_id INTEGER NOT NULL,
    kayit_zamani  TEXT NOT NULL,
    tick          INTEGER,
    degerlendirilen INTEGER,
    accuracy      REAL,
    severity_accuracy REAL,
    macro_f1      REAL,
    aktif_alarm   INTEGER,
    FOREIGN KEY (calistirma_id) REFERENCES calistirmalar(id)
);

CREATE INDEX IF NOT EXISTS idx_alarm_axle ON alarmlar(axle);
CREATE INDEX IF NOT EXISTS idx_alarm_hat ON alarmlar(line_id);
CREATE INDEX IF NOT EXISTS idx_alarm_zaman ON alarmlar(kayit_zamani);
"""


class Kayitci:
    """SQLite kayıt katmanı. Bağlantı tek iş parçacığından kullanılır (tick döngüsü)."""

    def __init__(self, db_yolu=VARSAYILAN_DB):
        self.db_yolu = db_yolu
        os.makedirs(os.path.dirname(db_yolu), exist_ok=True)
        # check_same_thread=False: tick döngüsü asyncio.to_thread ile farklı iş parçacıklarında
        # çalışabiliyor; yazmalar sırayla olduğu için yarış durumu oluşmaz.
        self.baglanti = sqlite3.connect(db_yolu, check_same_thread=False)
        self.baglanti.executescript(SEMA)
        self.baglanti.commit()
        self.calistirma_id = None

    # ------------------------------------------------------------------ yazma
    def calistirma_basla(self, kaynak, kor_mod, histerezis, dingil_sayisi, hat_sayisi):
        """Yeni bir simülasyon oturumu açar (akış sıfırlandığında çağrılır)."""
        cur = self.baglanti.execute(
            "INSERT INTO calistirmalar (baslangic, kaynak, kor_mod, histerezis, dingil_sayisi, hat_sayisi)"
            " VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), kaynak, int(kor_mod),
             int(histerezis), int(dingil_sayisi), int(hat_sayisi)),
        )
        self.baglanti.commit()
        self.calistirma_id = cur.lastrowid
        return self.calistirma_id

    def alarm_yaz(self, olay):
        """Yerleşik sınıf değişimini (alarm veya temizlenme) kaydeder."""
        if self.calistirma_id is None:
            return
        self.baglanti.execute(
            "INSERT INTO alarmlar (calistirma_id, kayit_zamani, sim_zamani, tick, axle, line_id,"
            " onceki, yeni, severity, conf, istasyon, tip, sure_sn, oncelik, gercek)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.calistirma_id, datetime.now().isoformat(timespec="seconds"),
             olay.get("ts"), olay.get("tick"), olay.get("axle"), olay.get("line_id"),
             olay.get("onceki"), olay.get("yeni"), olay.get("severity"), olay.get("conf"),
             olay.get("istasyon"), olay.get("tip"), olay.get("sure_sn"), olay.get("oncelik"),
             olay.get("gercek")),
        )
        self.baglanti.commit()

    def metrik_yaz(self, tick, metrikler, aktif_alarm):
        """Periyodik doğruluk anlık görüntüsü (her N tick'te bir çağrılır)."""
        if self.calistirma_id is None:
            return
        self.baglanti.execute(
            "INSERT INTO metrikler (calistirma_id, kayit_zamani, tick, degerlendirilen,"
            " accuracy, severity_accuracy, macro_f1, aktif_alarm) VALUES (?,?,?,?,?,?,?,?)",
            (self.calistirma_id, datetime.now().isoformat(timespec="seconds"), tick,
             metrikler.get("degerlendirilen"), metrikler.get("accuracy"),
             metrikler.get("severity_accuracy"), metrikler.get("macro_f1"), aktif_alarm),
        )
        self.baglanti.commit()

    # ---------------------------------------------------------------- sorgular
    def _sorgu(self, sql, params=()):
        self.baglanti.row_factory = sqlite3.Row
        satirlar = [dict(r) for r in self.baglanti.execute(sql, params).fetchall()]
        self.baglanti.row_factory = None
        return satirlar

    def son_alarmlar(self, limit=50):
        """En son kaydedilen alarmlar (tüm çalıştırmalar boyunca)."""
        return self._sorgu(
            "SELECT * FROM alarmlar WHERE tip='alarm' ORDER BY id DESC LIMIT ?", (limit,))

    def dingil_ozeti(self, limit=15):
        """En çok alarm üreten dingiller — 'bu dingil kaç kez arıza verdi' sorusu."""
        return self._sorgu(
            "SELECT axle, line_id, COUNT(*) AS alarm_sayisi,"
            " SUM(CASE WHEN severity='severe' THEN 1 ELSE 0 END) AS agir_sayisi,"
            " ROUND(AVG(sure_sn), 1) AS ort_sure_sn, MAX(kayit_zamani) AS son_alarm"
            " FROM alarmlar WHERE tip='alarm'"
            " GROUP BY axle, line_id ORDER BY alarm_sayisi DESC LIMIT ?", (limit,))

    def hat_ozeti(self):
        """Hat bazında alarm dağılımı — hangi hat daha çok arıza üretiyor."""
        return self._sorgu(
            "SELECT line_id, COUNT(*) AS alarm_sayisi, COUNT(DISTINCT axle) AS dingil_sayisi"
            " FROM alarmlar WHERE tip='alarm' AND line_id IS NOT NULL"
            " GROUP BY line_id ORDER BY alarm_sayisi DESC")

    def sinif_ozeti(self):
        """Arıza tipi bazında toplam alarm sayısı."""
        return self._sorgu(
            "SELECT yeni AS sinif, COUNT(*) AS adet, ROUND(AVG(sure_sn), 1) AS ort_sure_sn"
            " FROM alarmlar WHERE tip='alarm' GROUP BY yeni ORDER BY adet DESC")

    def calistirma_listesi(self, limit=10):
        return self._sorgu(
            "SELECT c.*, (SELECT COUNT(*) FROM alarmlar a WHERE a.calistirma_id=c.id AND a.tip='alarm')"
            " AS alarm_sayisi FROM calistirmalar c ORDER BY c.id DESC LIMIT ?", (limit,))

    def genel_ozet(self):
        """Dashboard'daki geçmiş paneli için toplu özet."""
        toplam = self._sorgu("SELECT COUNT(*) AS n FROM alarmlar WHERE tip='alarm'")[0]["n"]
        calistirma = self._sorgu("SELECT COUNT(*) AS n FROM calistirmalar")[0]["n"]
        return {
            "toplam_alarm": toplam,
            "calistirma_sayisi": calistirma,
            "dingiller": self.dingil_ozeti(),
            "hatlar": self.hat_ozeti(),
            "siniflar": self.sinif_ozeti(),
            "calistirmalar": self.calistirma_listesi(),
            "son_alarmlar": self.son_alarmlar(30),
        }

    def kapat(self):
        self.baglanti.close()


def main():
    ap = argparse.ArgumentParser(description="Raylı sistem kayıt veritabanı (SQLite) sorguları")
    ap.add_argument("--db", default=VARSAYILAN_DB)
    ap.add_argument("--ozet", action="store_true", help="Dingil/hat/sınıf bazında alarm özeti")
    ap.add_argument("--son", type=int, help="Son N alarmı listele")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        raise SystemExit(f"Kayıt veritabanı yok: {args.db}\n"
                         "Canlı akış sunucusu bir kez çalıştığında oluşur.")
    k = Kayitci(args.db)
    if args.son:
        print(f"=== Son {args.son} alarm")
        for a in k.son_alarmlar(args.son):
            print(f"  {a['kayit_zamani']}  {a['line_id'] or '-':5s} {a['axle']:16s} "
                  f"{a['yeni']:14s} {a['severity'] or '-':9s} {a['istasyon'] or ''}")
    else:
        o = k.genel_ozet()
        print(f"Toplam alarm: {o['toplam_alarm']} | çalıştırma: {o['calistirma_sayisi']}")
        print("\n=== En çok alarm üreten dingiller")
        for d in o["dingiller"]:
            print(f"  {d['line_id'] or '-':5s} {d['axle']:16s} {d['alarm_sayisi']:4d} alarm "
                  f"({d['agir_sayisi']} ağır)  ort. süre {d['ort_sure_sn']}s")
        print("\n=== Hat bazında")
        for h in o["hatlar"]:
            print(f"  {h['line_id']:6s} {h['alarm_sayisi']:4d} alarm / {h['dingil_sayisi']} dingil")
        print("\n=== Arıza tipi bazında")
        for s in o["siniflar"]:
            print(f"  {s['sinif']:15s} {s['adet']:4d} alarm  ort. süre {s['ort_sure_sn']}s")
    k.kapat()


if __name__ == "__main__":
    main()
