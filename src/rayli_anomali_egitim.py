"""
Anomali tespiti (autoencoder) EĞİTİMİ — mevcut denetimli modeli (rayli_dl_egitim.py) TAMAMLAYAN
ayrı, küçük bir eğitim. Bkz. rayli_anomali.py için gerekçe.

Yaklaşım:
- Aynı sekans/ölçekleme mantığı (rayli_veri_utils.build_sequences) kullanılır ki canlı akışla
  birebir tutarlı olsun.
- SADECE `fault_type == normal` olan pencerelerle eğitilir (autoencoder yalnızca "sağlıklı"
  örüntüyü öğrenir).
- Eşik (threshold), normal pencerelerin bir kısmı ayrılarak (validation) o kısımdaki
  yeniden yapılandırma hatasının 99. yüzdelik dilimi olarak belirlenir — normal pencerelerin
  ~%1'i "sınırda" sayılıp yanlış alarm üretebilir, bu kabul edilebilir bir dengedir.
- Test setinde (TÜM sınıflar dahil) autoencoder'ın bilinen 6 arıza tipini de normalden
  ayırabildiği doğrulanır (mekanizmanın çalıştığının kanıtı — bkz. rayli_anomali.py docstring).

Kullanım (src/ klasöründen):
    python rayli_anomali_egitim.py
"""

import json
import os

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split

from rayli_model import FEATURE_COLS, WINDOW
from rayli_veri_utils import load_df, build_sequences
from rayli_anomali import SekansAutoencoder, yeniden_yapilandirma_hatasi

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MODEL_DIR = os.path.join(BASE_DIR, "..", "model")
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

EPOCHS = 25
BATCH_SIZE = 256
GIZLI_BOYUT = 16
ESIK_YUZDELIK = 99.0     # validation'daki normal hataların bu yüzdelik dilimi eşik olur


def main():
    train_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_train.csv"))
    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))

    scaler = StandardScaler().fit(train_df[FEATURE_COLS].values)
    encoder = LabelEncoder().fit(sorted(train_df["fault_type"].unique()))
    classes = list(encoder.classes_)
    normal_idx = int(encoder.transform(["normal"])[0])

    Xt, yt, _ = build_sequences(train_df, scaler, encoder)
    X_normal = Xt[yt == normal_idx]
    print(f"Toplam eğitim penceresi: {len(Xt)} | normal: {len(X_normal)} "
          f"(%{100 * len(X_normal) / len(Xt):.1f})")

    X_fit, X_val = train_test_split(X_normal, test_size=0.15, random_state=SEED)

    model = SekansAutoencoder(n_features=len(FEATURE_COLS), window=WINDOW, gizli=GIZLI_BOYUT)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    kriter = nn.MSELoss()

    fit_loader = DataLoader(torch.from_numpy(X_fit), batch_size=BATCH_SIZE, shuffle=True)
    for epoch in range(1, EPOCHS + 1):
        model.train()
        toplam_kayip = 0.0
        for xb in fit_loader:
            optimizer.zero_grad()
            cikti = model(xb)
            kayip = kriter(cikti, xb)
            kayip.backward()
            optimizer.step()
            toplam_kayip += kayip.item() * xb.size(0)
        if epoch % 5 == 0 or epoch == EPOCHS:
            print(f"Epoch {epoch:2d}/{EPOCHS} | eğitim MSE: {toplam_kayip / len(X_fit):.5f}")

    # --- Eşik: validation'daki (görülmemiş normal) hataların 99. yüzdelik dilimi ---
    val_hata = yeniden_yapilandirma_hatasi(model, X_val)
    esik = float(np.percentile(val_hata, ESIK_YUZDELIK))
    print(f"\nValidation normal MSE: ort {val_hata.mean():.5f} | eşik (%{ESIK_YUZDELIK}): {esik:.5f}")

    # --- Test setinde mekanizmayı doğrula: bilinen arızalar da normalden ayrılabiliyor mu? ---
    Xtest, ytest, _ = build_sequences(test_df, scaler, encoder)
    test_hata = yeniden_yapilandirma_hatasi(model, Xtest)
    test_anomali = test_hata > esik

    print("\n=== Test setinde anomali bayrağı oranı (sınıf bazında) ===")
    ozet_sinif = {}
    for i, sinif in enumerate(classes):
        maske = ytest == i
        if maske.sum() == 0:
            continue
        oran = float(test_anomali[maske].mean())
        ozet_sinif[sinif] = {"pencere": int(maske.sum()), "anomali_orani": round(oran, 4)}
        print(f"  {sinif:15s} {maske.sum():5d} pencere | anomali işaretlenen: %{oran * 100:.1f}")

    yanlis_alarm = ozet_sinif.get("normal", {}).get("anomali_orani", 0.0)
    ariza_yakalama = np.mean([v["anomali_orani"] for k, v in ozet_sinif.items() if k != "normal"])
    print(f"\nYanlış alarm oranı (normal pencerelerde): %{yanlis_alarm * 100:.1f}")
    print(f"Bilinen arızaları 'anomali' olarak yakalama oranı (ortalama): %{ariza_yakalama * 100:.1f}")

    torch.save({
        "model_state_dict": model.state_dict(),
        "feature_cols": FEATURE_COLS,
        "window": WINDOW,
        "gizli_boyut": GIZLI_BOYUT,
        "esik": esik,
        "esik_yuzdelik": ESIK_YUZDELIK,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "classes": classes,
    }, os.path.join(MODEL_DIR, "rayli_anomali_model.pt"))

    with open(os.path.join(RESULTS_DIR, "anomali_egitim_ozeti.json"), "w") as f:
        json.dump({
            "epochs": EPOCHS, "gizli_boyut": GIZLI_BOYUT, "esik": esik,
            "esik_yuzdelik": ESIK_YUZDELIK,
            "n_normal_egitim": int(len(X_fit)), "n_normal_val": int(len(X_val)),
            "yanlis_alarm_orani": round(yanlis_alarm, 4),
            "ariza_yakalama_orani": round(float(ariza_yakalama), 4),
            "sinif_bazinda": ozet_sinif,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nModel kaydedildi: {os.path.join(MODEL_DIR, 'rayli_anomali_model.pt')}")
    print(f"Özet kaydedildi : {os.path.join(RESULTS_DIR, 'anomali_egitim_ozeti.json')}")


if __name__ == "__main__":
    main()
