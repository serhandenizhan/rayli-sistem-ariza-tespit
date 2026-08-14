"""
Eğitilmiş modeli (model/rayli_cnn_lstm_model.pt) YENİDEN EĞİTMEDEN yükleyip test verisi
üzerinde tahmin üretir. Model çok görevlidir: hem arıza tipi hem arıza şiddeti tahmin edilir.

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

from rayli_model import load_model_checkpoint, rebuild_scaler_and_encoder, SEVERITY_CLASSES
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
    sev_classes = checkpoint.get("severity_classes", SEVERITY_CLASSES)

    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))
    Xt, yt, st = build_sequences(test_df, scaler, encoder,
                                 window=checkpoint["window"], stride=checkpoint["stride"])
    print(f"Model yüklendi: {model_path}")
    print(f"Test sekansı şekli: {Xt.shape}  (adım={checkpoint['window']}, özellik={len(checkpoint['feature_cols'])})")

    with torch.no_grad():
        logit_tip, logit_sev = model(torch.from_numpy(Xt))
        tahmin_tip = logit_tip.argmax(1).numpy()
        tahmin_sev = logit_sev.argmax(1).numpy()

    if args.n:
        print(f"\nİlk {args.n} sekans için gerçek vs tahmin:")
        for i in range(min(args.n, len(yt))):
            gercek, tahmin = classes[yt[i]], classes[tahmin_tip[i]]
            g_sev, t_sev = sev_classes[st[i]], sev_classes[tahmin_sev[i]]
            isaret = "OK" if gercek == tahmin else "X "
            print(f"[{isaret}] tip: gercek={gercek:15s} tahmin={tahmin:15s} | "
                  f"siddet: gercek={g_sev:9s} tahmin={t_sev}")
    else:
        print("\n=== ARIZA TİPİ — sınıflandırma raporu ===")
        print(classification_report(yt, tahmin_tip, target_names=classes, digits=3))

        mevcut = sorted(set(st.tolist()) | set(tahmin_sev.tolist()))
        print("=== ARIZA ŞİDDETİ — sınıflandırma raporu ===")
        print(classification_report(st, tahmin_sev, labels=mevcut,
                                    target_names=[sev_classes[i] for i in mevcut],
                                    digits=3, zero_division=0))
        print(f"Şiddet accuracy: {np.mean(st == tahmin_sev):.4f}")


if __name__ == "__main__":
    main()
