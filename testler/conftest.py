"""
pytest ortak yapılandırması + test sonuçlarını makine-okunur özete yazan küçük eklenti.

Neden kendi eklentimiz var? Dashboard'daki "Testler" paneli, testlerin ne yaptığını ve
sonucunu okuyabilsin diye `results/test_ozeti.json` üretiyoruz. Ek bir bağımlılık
(pytest-json-report vb.) kurmamak için bu iş birkaç satırlık iki kanca (hook) ile yapılıyor.
Testin Türkçe docstring'i, arayüzde testin açıklaması olarak gösterilir.
"""

import json
import os
import sys
from datetime import datetime

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "model")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# src/ içindeki modüller (rayli_model, istanbul_metro_agi ...) doğrudan import edilebilsin
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

_sonuclar = {}


def pytest_runtest_logreport(report):
    """Her testin 'call' aşamasındaki sonucunu topla (setup/teardown hatalarını da yakala)."""
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        kayit = _sonuclar.setdefault(report.nodeid, {})
        kayit.update({
            "nodeid": report.nodeid,
            "dosya": report.nodeid.split("::")[0],
            "ad": report.nodeid.split("::")[-1],
            "sonuc": report.outcome,
            "sure": round(report.duration, 4),
        })
        if report.outcome == "failed":
            kayit["hata"] = str(report.longrepr)[-1200:]


def pytest_collection_modifyitems(items):
    """Testlerin Türkçe docstring'lerini açıklama olarak sakla."""
    for item in items:
        belge = (item.function.__doc__ or "").strip()
        _sonuclar.setdefault(item.nodeid, {})["aciklama"] = " ".join(belge.split())


def pytest_sessionfinish(session, exitstatus):
    """Oturum sonunda results/test_ozeti.json dosyasını yaz."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    testler = [k for k in _sonuclar.values() if "sonuc" in k]
    ozet = {
        "calistirma_zamani": datetime.now().isoformat(timespec="seconds"),
        "cikis_kodu": int(exitstatus),
        "toplam": len(testler),
        "gecti": sum(1 for t in testler if t["sonuc"] == "passed"),
        "kaldi": sum(1 for t in testler if t["sonuc"] == "failed"),
        "atlandi": sum(1 for t in testler if t["sonuc"] == "skipped"),
        "toplam_sure": round(sum(t.get("sure", 0) for t in testler), 3),
        "testler": sorted(testler, key=lambda t: t["nodeid"]),
    }
    with open(os.path.join(RESULTS_DIR, "test_ozeti.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ ortak fixture'lar
@pytest.fixture(scope="session")
def veri_dizini():
    return DATA_DIR


@pytest.fixture(scope="session")
def train_df():
    import pandas as pd
    yol = os.path.join(DATA_DIR, "rayli_sistem_train.csv")
    if not os.path.exists(yol):
        pytest.skip("Train verisi yok — önce 'python src/rayli_veri_uret.py' çalıştırın.")
    return pd.read_csv(yol, parse_dates=["timestamp"])


@pytest.fixture(scope="session")
def test_df():
    import pandas as pd
    yol = os.path.join(DATA_DIR, "rayli_sistem_test.csv")
    if not os.path.exists(yol):
        pytest.skip("Test verisi yok — önce 'python src/rayli_veri_uret.py' çalıştırın.")
    return pd.read_csv(yol, parse_dates=["timestamp"])


@pytest.fixture(scope="session")
def akis_df():
    import pandas as pd
    yol = os.path.join(DATA_DIR, "rayli_sistem_test_akis.csv")
    if not os.path.exists(yol):
        pytest.skip("Akış verisi yok — önce 'python src/rayli_etiketsiz_uret.py' çalıştırın.")
    return pd.read_csv(yol, parse_dates=["timestamp"])


@pytest.fixture(scope="session")
def cevap_anahtari():
    import pandas as pd
    yol = os.path.join(DATA_DIR, "rayli_sistem_test_cevap_anahtari.csv")
    if not os.path.exists(yol):
        pytest.skip("Cevap anahtarı yok — önce 'python src/rayli_etiketsiz_uret.py' çalıştırın.")
    return pd.read_csv(yol)


@pytest.fixture(scope="session")
def metro_agi():
    import istanbul_metro_agi as ag
    yol = os.path.join(DATA_DIR, "istanbul_metro_agi.json")
    if not os.path.exists(yol):
        pytest.skip("Ağ modeli yok — önce 'python src/istanbul_metro_agi.py' çalıştırın.")
    return ag.yukle()


@pytest.fixture(scope="session")
def checkpoint_yolu():
    yol = os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt")
    if not os.path.exists(yol):
        pytest.skip("Eğitilmiş model yok — önce 'python src/rayli_dl_egitim.py' çalıştırın.")
    return yol
