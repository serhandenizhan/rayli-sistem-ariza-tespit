"""Denetimsiz anomali tespiti (autoencoder, rayli_anomali.py) testleri.

Bu katman, 6 sınıflık denetimli modeli TAMAMLAR — yerine geçmez. Testler hem model
mekanizmasını (yeniden yapılandırma) hem de eğitilmiş checkpoint'in gerçekten normali
arızadan ayırabildiğini doğrular.
"""

import os

import numpy as np
import pytest
import torch

from rayli_anomali import (SekansAutoencoder, anomali_skoru_normalize,
                           load_anomali_checkpoint, yeniden_yapilandirma_hatasi)
from rayli_model import FEATURE_COLS, WINDOW

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANOMALI_MODEL = os.path.join(BASE_DIR, "model", "rayli_anomali_model.pt")


def test_autoencoder_girdiyle_ayni_sekli_uretir():
    """Çıktı, girdiyle birebir aynı (batch, WINDOW, n_features) şeklinde olmalı."""
    model = SekansAutoencoder(n_features=len(FEATURE_COLS), window=WINDOW)
    x = torch.randn(5, WINDOW, len(FEATURE_COLS))
    assert model(x).shape == x.shape


def test_yeniden_yapilandirma_hatasi_negatif_olamaz():
    """MSE tanımı gereği her zaman >= 0 olmalı."""
    model = SekansAutoencoder(n_features=len(FEATURE_COLS), window=WINDOW)
    x = np.random.randn(8, WINDOW, len(FEATURE_COLS)).astype(np.float32)
    hata = yeniden_yapilandirma_hatasi(model, x)
    assert hata.shape == (8,)
    assert (hata >= 0).all()


def test_anomali_skoru_normalize_sinirlari():
    """Normalize skor her zaman [0, 1] aralığında olmalı, eşik altı düşük, üstü doygun kalmalı."""
    assert anomali_skoru_normalize(0.0, esik=0.5) == 0.0
    assert anomali_skoru_normalize(0.5, esik=0.5) == pytest.approx(0.5)
    assert anomali_skoru_normalize(100.0, esik=0.5) == 1.0   # doygunlaşma
    assert anomali_skoru_normalize(0.1, esik=0.0) == 0.0     # eşik 0 -> bölme koruması


@pytest.fixture(scope="module")
def anomali_checkpoint():
    if not os.path.exists(ANOMALI_MODEL):
        pytest.skip("Anomali modeli eğitilmemiş — 'python src/rayli_anomali_egitim.py' çalıştırın.")
    return load_anomali_checkpoint(ANOMALI_MODEL)


def test_checkpoint_yuklenir(anomali_checkpoint):
    """Eğitilmiş checkpoint yüklenebilmeli ve gerekli alanları içermeli."""
    model, ckpt = anomali_checkpoint
    for alan in ("model_state_dict", "feature_cols", "window", "esik", "scaler_mean", "scaler_scale"):
        assert alan in ckpt
    assert ckpt["feature_cols"] == FEATURE_COLS
    assert ckpt["window"] == WINDOW
    assert ckpt["esik"] > 0
    assert not model.training


def test_normal_pencere_dusuk_hata_uretir(anomali_checkpoint, test_df):
    """DOĞRULAMA: gerçek 'normal' pencerelerin hatası, eğitilirken belirlenen eşiğin
    büyük çoğunlukla ALTINDA kalmalı (yanlış alarm oranı düşük olmalı)."""
    from rayli_veri_utils import build_sequences
    from sklearn.preprocessing import StandardScaler, LabelEncoder

    model, ckpt = anomali_checkpoint
    # anomali checkpoint kendi scaler'ını taşır (ana modelden bağımsız, kendi kendine yeterli)
    scaler = StandardScaler()
    scaler.mean_ = np.array(ckpt["scaler_mean"])
    scaler.scale_ = np.array(ckpt["scaler_scale"])
    scaler.var_ = scaler.scale_ ** 2
    scaler.n_features_in_ = len(scaler.mean_)

    encoder = LabelEncoder()
    encoder.classes_ = np.array(ckpt["classes"])

    X, y, _ = build_sequences(test_df, scaler, encoder, window=ckpt["window"])
    normal_idx = int(encoder.transform(["normal"])[0])
    X_normal = X[y == normal_idx]
    hata = yeniden_yapilandirma_hatasi(model, X_normal)
    yanlis_alarm_orani = float((hata > ckpt["esik"]).mean())
    assert yanlis_alarm_orani < 0.10, f"yanlış alarm oranı çok yüksek: {yanlis_alarm_orani:.3f}"


def test_bilinen_arizalar_normalden_daha_cok_anomali_isaretlenir(anomali_checkpoint, test_df):
    """MEKANİZMA DOĞRULAMASI: autoencoder yalnızca normalle eğitildiği için, bilinen 6 arıza
    tipi de normalden anlamlı ölçüde daha fazla anomali işaretlenmeli — aksi hâlde model
    hiçbir şey öğrenmemiş demektir."""
    from rayli_veri_utils import build_sequences
    from sklearn.preprocessing import StandardScaler, LabelEncoder

    model, ckpt = anomali_checkpoint
    scaler = StandardScaler()
    scaler.mean_ = np.array(ckpt["scaler_mean"])
    scaler.scale_ = np.array(ckpt["scaler_scale"])
    scaler.var_ = scaler.scale_ ** 2
    scaler.n_features_in_ = len(scaler.mean_)
    encoder = LabelEncoder()
    encoder.classes_ = np.array(ckpt["classes"])

    X, y, _ = build_sequences(test_df, scaler, encoder, window=ckpt["window"])
    normal_idx = int(encoder.transform(["normal"])[0])
    hata = yeniden_yapilandirma_hatasi(model, X)
    anomali = hata > ckpt["esik"]

    normal_orani = float(anomali[y == normal_idx].mean())
    ariza_orani = float(anomali[y != normal_idx].mean())
    assert ariza_orani > normal_orani + 0.3, (
        f"arıza pencereleri normalden yeterince ayrışmıyor: ariza={ariza_orani:.3f} "
        f"normal={normal_orani:.3f}")
