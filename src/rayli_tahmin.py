"""
Eğitilmiş modeli (model/rayli_cnn_lstm_model.pt) YENİDEN EĞİTMEDEN yükleyip test verisi
üzerinde tahmin üretir.

Projeyi sıfırdan eğitmeden hızlıca çalıştırıp sonuç görmek isterseniz bu script yeterlidir —
rayli_dl_egitim.py'yi tekrar çalıştırmanıza gerek yoktur.

Kullanım (src/ klasöründen):
    python rayli_tahmin.py            # test setinin tamamı için sınıflandırma raporu
    python rayli_tahmin.py --n 20     # ilk 20 sekans için satır satır gerçek/tahmin karşılaştırması
"""

import argparse
import os

import numpy as np
import torch
from sklearn.metrics import classification_report

from rayli_model import load_model_checkpoint, rebuild_scaler_and_encoder
from rayli_veri_utils import load_df, build_sequences

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MODEL_DIR = os.path.join(BASE_DIR, "..", "model")


def main():
    parser = argparse.ArgumentParser(description="Eğitilmiş model ile test verisi üzerinde tahmin üretir.")
    parser.add_argument("--n", type=int, default=None,
                         help="Sadece ilk N sekansı satır satır (gerçek vs tahmin) göster")
    args = parser.parse_args()

    model_path = os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt")
    if not os.path.exists(model_path):
        raise SystemExit(
            f"Model dosyası bulunamadı: {model_path}\n"
            "Önce 'python rayli_dl_egitim.py' çalıştırıp modeli eğitmeniz gerekiyor."
        )

    model, checkpoint = load_model_checkpoint(model_path)
    scaler, encoder = rebuild_scaler_and_encoder(checkpoint)
    classes = checkpoint["classes"]

    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))
    Xt, yt = build_sequences(test_df, scaler, encoder,
                              window=checkpoint["window"], stride=checkpoint["stride"])
    print(f"Model yüklendi: {model_path}")
    print(f"Test sekansı şekli: {Xt.shape}  (adım={checkpoint['window']}, özellik={len(checkpoint['feature_cols'])})")

    with torch.no_grad():
        logits = model(torch.from_numpy(Xt))
        preds = logits.argmax(1).numpy()

    if args.n:
        print(f"\nİlk {args.n} sekans için gerçek vs tahmin:")
        for i in range(min(args.n, len(yt))):
            gercek, tahmin = classes[yt[i]], classes[preds[i]]
            isaret = "OK" if gercek == tahmin else "X "
            print(f"[{isaret}] gercek={gercek:15s} tahmin={tahmin}")
    else:
        print("\n=== Tüm test seti için sınıflandırma raporu ===")
        print(classification_report(yt, preds, target_names=classes, digits=3))


if __name__ == "__main__":
    main()
