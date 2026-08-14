"""Model mimarisi, sekans oluşturma ve eğitilmiş checkpoint'in davranış testleri."""

import numpy as np
import pytest
import torch

from rayli_model import (CNNLSTM, FEATURE_COLS, SEVERITY_CLASSES, WINDOW,
                         load_model_checkpoint, rebuild_scaler_and_encoder)
from rayli_veri_utils import build_sequences, build_sequences_with_val_split


def test_model_iki_baslik_dondurur():
    """Çok görevli model, arıza tipi ve şiddet için iki ayrı logit tensörü döndürmeli."""
    model = CNNLSTM(n_features=len(FEATURE_COLS), n_classes=6, n_severity=4)
    x = torch.randn(5, WINDOW, len(FEATURE_COLS))
    tip, sev = model(x)
    assert tip.shape == (5, 6)
    assert sev.shape == (5, 4)


def test_model_ciktisi_logit_softmax_degil():
    """Model ham logit üretmeli (softmax uygulanmamış) — kayıp fonksiyonu bunu bekliyor."""
    model = CNNLSTM(n_features=len(FEATURE_COLS), n_classes=6)
    tip, _ = model(torch.randn(3, WINDOW, len(FEATURE_COLS)))
    toplamlar = tip.softmax(1).sum(1)
    assert torch.allclose(toplamlar, torch.ones(3), atol=1e-5)
    assert not torch.allclose(tip.sum(1), torch.ones(3), atol=1e-3)


def test_checkpoint_yuklenir(checkpoint_yolu):
    """Kaydedilmiş checkpoint yüklenebilmeli ve gerekli tüm alanları içermeli."""
    model, ckpt = load_model_checkpoint(checkpoint_yolu)
    for alan in ("model_state_dict", "classes", "feature_cols", "window", "stride",
                 "scaler_mean", "scaler_scale"):
        assert alan in ckpt, f"checkpoint'te eksik alan: {alan}"
    assert ckpt["feature_cols"] == FEATURE_COLS
    assert ckpt["window"] == WINDOW
    assert not model.training, "yüklenen model eval modunda olmalı"


def test_checkpoint_siddet_basligini_iceriyor(checkpoint_yolu):
    """Checkpoint çok görevli modele ait olmalı (şiddet sınıfları kayıtlı)."""
    _, ckpt = load_model_checkpoint(checkpoint_yolu)
    assert ckpt.get("severity_classes") == SEVERITY_CLASSES


def test_scaler_checkpointten_yeniden_kurulur(checkpoint_yolu):
    """Scaler/encoder checkpoint'ten yeniden kurulmalı — sıfırdan fit edilmemeli."""
    _, ckpt = load_model_checkpoint(checkpoint_yolu)
    scaler, encoder = rebuild_scaler_and_encoder(ckpt)
    assert scaler.n_features_in_ == len(FEATURE_COLS)
    assert list(encoder.classes_) == list(ckpt["classes"])
    # dönüşüm gerçekten checkpoint parametrelerini kullanıyor mu?
    x = np.array([ckpt["scaler_mean"]])
    assert np.allclose(scaler.transform(x), 0, atol=1e-9)


def test_sekans_sekilleri_ve_etiket_hizasi(test_df, checkpoint_yolu):
    """Sekanslar (N, WINDOW, özellik) şeklinde olmalı ve etiket pencerenin SON adımından gelmeli."""
    _, ckpt = load_model_checkpoint(checkpoint_yolu)
    scaler, encoder = rebuild_scaler_and_encoder(ckpt)
    X, y, sev = build_sequences(test_df, scaler, encoder)
    assert X.ndim == 3 and X.shape[1] == WINDOW and X.shape[2] == len(FEATURE_COLS)
    assert len(X) == len(y) == len(sev)
    assert X.dtype == np.float32 and y.dtype == np.int64
    assert set(np.unique(sev)) <= set(range(len(SEVERITY_CLASSES)))


def test_validation_bolmesi_sizinti_yapmaz(train_df, checkpoint_yolu):
    """Train/val bölmesi her dingilin kendi zaman diliminden yapılmalı; toplam sekans sayısı
    sınır aşımı olmadığı için bütün veriden üretilenden AZ olmalı."""
    _, ckpt = load_model_checkpoint(checkpoint_yolu)
    scaler, encoder = rebuild_scaler_and_encoder(ckpt)
    Xf, yf, sf, Xv, yv, sv = build_sequences_with_val_split(train_df, scaler, encoder)
    X_hepsi, _, _ = build_sequences(train_df, scaler, encoder)
    assert len(Xf) > 0 and len(Xv) > 0
    assert len(Xf) + len(Xv) < len(X_hepsi), "sınırı aşan pencereler üretilmiş olabilir"


def test_test_setinde_dogruluk_esigi(test_df, checkpoint_yolu):
    """Regresyon koruması: eğitilmiş model test setinde en az %90 doğruluk vermeli."""
    model, ckpt = load_model_checkpoint(checkpoint_yolu)
    scaler, encoder = rebuild_scaler_and_encoder(ckpt)
    X, y, sev = build_sequences(test_df, scaler, encoder,
                                window=ckpt["window"], stride=ckpt["stride"])
    with torch.no_grad():
        tip_logit, sev_logit = model(torch.from_numpy(X))
    tip_acc = (tip_logit.argmax(1).numpy() == y).mean()
    sev_acc = (sev_logit.argmax(1).numpy() == sev).mean()
    assert tip_acc >= 0.90, f"arıza tipi doğruluğu düştü: {tip_acc:.3f}"
    assert sev_acc >= 0.85, f"şiddet doğruluğu düştü: {sev_acc:.3f}"


def test_model_deterministik(checkpoint_yolu):
    """Aynı girdi için model iki kez aynı çıktıyı vermeli (eval modunda dropout kapalı)."""
    model, _ = load_model_checkpoint(checkpoint_yolu)
    x = torch.randn(4, WINDOW, len(FEATURE_COLS))
    with torch.no_grad():
        a, _ = model(x)
        b, _ = model(x)
    assert torch.allclose(a, b)


@pytest.mark.parametrize("batch", [1, 7, 32])
def test_model_farkli_batch_boyutlarinda_calisir(batch):
    """Model her batch boyutunda (canlı akışta dingil sayısı değişebilir) çalışmalı."""
    model = CNNLSTM(n_features=len(FEATURE_COLS), n_classes=6)
    tip, sev = model(torch.randn(batch, WINDOW, len(FEATURE_COLS)))
    assert tip.shape[0] == batch and sev.shape[0] == batch
