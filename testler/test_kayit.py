"""SQLite kalıcılık katmanının (rayli_kayit.py) testleri."""

import os
import tempfile

import pytest

from rayli_kayit import Kayitci


@pytest.fixture()
def kayitci():
    """Geçici bir veritabanı — gerçek kayıt dosyasına dokunulmaz."""
    with tempfile.TemporaryDirectory() as d:
        k = Kayitci(os.path.join(d, "test.db"))
        yield k
        k.kapat()


def test_semasi_kurulur(kayitci):
    """Veritabanı açıldığında gerekli tablolar oluşmalı."""
    tablolar = {r["name"] for r in kayitci._sorgu(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"calistirmalar", "alarmlar", "metrikler"} <= tablolar


def test_calistirma_ve_alarm_yazilir(kayitci):
    """Açılan çalıştırmaya alarm yazılıp geri okunabilmeli."""
    cid = kayitci.calistirma_basla("csv", False, 3, 68, 17)
    assert cid > 0
    kayitci.alarm_yaz({
        "ts": "2026-08-15 10:00:00", "tick": 42, "axle": "M4-01/V1-A1", "line_id": "M4",
        "onceki": "normal", "yeni": "bearing_fault", "severity": "severe", "conf": 0.97,
        "istasyon": "Kartal", "tip": "alarm", "sure_sn": 30.0, "oncelik": 0.8, "gercek": "bearing_fault",
    })
    son = kayitci.son_alarmlar(5)
    assert len(son) == 1
    assert son[0]["axle"] == "M4-01/V1-A1"
    assert son[0]["yeni"] == "bearing_fault"
    assert son[0]["calistirma_id"] == cid


def test_calistirma_olmadan_yazma_sessizce_atlanir(kayitci):
    """Çalıştırma açılmadan gelen alarm kaydı hata vermemeli (savunmacı davranış)."""
    kayitci.alarm_yaz({"axle": "X", "yeni": "normal", "tip": "alarm"})
    assert kayitci.son_alarmlar(5) == []


def test_dingil_ve_hat_ozeti(kayitci):
    """Özet sorguları alarm sayılarını doğru gruplamalı."""
    kayitci.calistirma_basla("csv", False, 3, 4, 1)
    for i in range(3):
        kayitci.alarm_yaz({"axle": "M4-01/V1-A1", "line_id": "M4", "yeni": "wheel_flat",
                           "severity": "mild", "tip": "alarm", "sure_sn": 10.0 * (i + 1)})
    kayitci.alarm_yaz({"axle": "M2-01/V1-A1", "line_id": "M2", "yeni": "motor_fault",
                       "severity": "severe", "tip": "alarm", "sure_sn": 20.0})
    dingiller = kayitci.dingil_ozeti()
    assert dingiller[0]["axle"] == "M4-01/V1-A1"
    assert dingiller[0]["alarm_sayisi"] == 3
    hatlar = {h["line_id"]: h["alarm_sayisi"] for h in kayitci.hat_ozeti()}
    assert hatlar == {"M4": 3, "M2": 1}
    siniflar = {s["sinif"]: s["adet"] for s in kayitci.sinif_ozeti()}
    assert siniflar == {"wheel_flat": 3, "motor_fault": 1}


def test_temizlenme_kayitlari_alarm_sayilmaz(kayitci):
    """'temizlendi' tipi kayıtlar alarm sayısına dahil edilmemeli."""
    kayitci.calistirma_basla("csv", False, 3, 4, 1)
    kayitci.alarm_yaz({"axle": "A", "line_id": "M1A", "yeni": "brake_fault", "tip": "alarm"})
    kayitci.alarm_yaz({"axle": "A", "line_id": "M1A", "yeni": "normal", "tip": "temizlendi"})
    assert kayitci.genel_ozet()["toplam_alarm"] == 1


def test_metrik_anlik_goruntusu(kayitci):
    """Periyodik metrik kaydı yazılabilmeli."""
    kayitci.calistirma_basla("csv", False, 3, 4, 1)
    kayitci.metrik_yaz(25, {"degerlendirilen": 100, "accuracy": 0.99,
                            "severity_accuracy": 0.96, "macro_f1": 0.97}, aktif_alarm=2)
    satir = kayitci._sorgu("SELECT * FROM metrikler")[0]
    assert satir["tick"] == 25 and satir["aktif_alarm"] == 2
