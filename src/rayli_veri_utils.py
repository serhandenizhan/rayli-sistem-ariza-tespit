"""Veri yükleme ve pencere (sekans) oluşturma yardımcı fonksiyonları.

Hem eğitim hem tahmin script'i tarafından kullanılır; böylece train sırasında sekansların
nasıl kurulduğu ile tahmin sırasında nasıl kurulduğu arasında fark oluşmaz.
"""
import numpy as np
import pandas as pd

from rayli_model import FEATURE_COLS, GROUP_COLS, WINDOW, STRIDE


def load_df(path):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df.sort_values(GROUP_COLS + ["timestamp"]).reset_index(drop=True)


def build_sequences(df, scaler, encoder, window=WINDOW, stride=STRIDE):
    """Her dingil (axle) grubunda ardışık `window` adımlık kayan pencereler oluşturur.
    Etiket, pencerenin SON adımındaki fault_type'tır (canlı akışta "şu anki durum" tahminine
    karşılık gelir)."""
    X_list, y_list = [], []
    for _, g in df.groupby(GROUP_COLS):
        g = g.sort_values("timestamp")
        feats = scaler.transform(g[FEATURE_COLS].values)
        labels = encoder.transform(g["fault_type"].values)
        n = len(g)
        for start in range(0, n - window + 1, stride):
            X_list.append(feats[start:start + window])
            y_list.append(labels[start + window - 1])
    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int64)


def build_sequences_with_val_split(df, scaler, encoder, window=WINDOW, stride=STRIDE, val_frac=0.15):
    """Her dingilin KENDİ zaman diliminin son val_frac'ini validation için ayırır; train/val
    sınırını aşan pencere oluşturulmaz (sızıntı önlenir)."""
    Xf, yf, Xv, yv = [], [], [], []
    for _, g in df.groupby(GROUP_COLS):
        g = g.sort_values("timestamp").reset_index(drop=True)
        n = len(g)
        split_idx = int(n * (1 - val_frac))
        fit_part, val_part = g.iloc[:split_idx], g.iloc[split_idx:]
        for part, Xs, ys in [(fit_part, Xf, yf), (val_part, Xv, yv)]:
            feats = scaler.transform(part[FEATURE_COLS].values)
            labels = encoder.transform(part["fault_type"].values)
            m = len(part)
            for start in range(0, m - window + 1, stride):
                Xs.append(feats[start:start + window])
                ys.append(labels[start + window - 1])
    return (np.array(Xf, dtype=np.float32), np.array(yf, dtype=np.int64),
            np.array(Xv, dtype=np.float32), np.array(yv, dtype=np.int64))
