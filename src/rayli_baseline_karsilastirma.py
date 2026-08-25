"""
Mevcut çok görevli CNN+LSTM mimarisinin "neden bu mimari?" sorusuna deneysel cevap verir.

Dört modeli SADECE arıza TİPİ (6 sınıf) görevi üzerinde, aynı train/test bölmesiyle kıyaslar:
  1. Logistic Regression  — pencere (WINDOW=10) özetlenip (mean/std/min/max) düz vektöre çevrilir
  2. Random Forest        — aynı özetlenmiş girdi
  3. 1D-CNN (tek başına)  — CNNLSTM'in konvolüsyon kısmı, LSTM'siz, tek görevli
  4. LSTM (tek başına)    — CNNLSTM'in LSTM kısmı, konvolüsyonsuz, tek görevli
  5. Final CNN+LSTM       — model/rayli_cnn_lstm_model.pt YENİDEN EĞİTİLMEZ, sadece yüklenip
                            test setinde değerlendirilir (adil kıyas + zaman tasarrufu)

Baseline'lar (1D-CNN, LSTM) da tek görevlidir (yalnızca tip başlığı) — çok görevli final modelle
birebir aynı şey ölçülmüyor, ama "aynı girdiden aynı 6 sınıfı ayırt etmek için mimari seçimi ne
kadar fark yaratıyor" sorusuna cevap vermek için yeterli. Her model için test seti üzerinde
toplam/örnek başı çıkarım (inference) süresi de ölçülür.

Kullanım (src/ klasöründen):
    python rayli_baseline_karsilastirma.py

Çıktı: ../results/baseline_karsilastirma.json + ../results/baseline_karsilastirma.md
"""
import json
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import StandardScaler, LabelEncoder

from rayli_model import FEATURE_COLS, WINDOW, STRIDE, SeqDataset, load_model_checkpoint, rebuild_scaler_and_encoder
from rayli_veri_utils import load_df, build_sequences

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MODEL_DIR = os.path.join(BASE_DIR, "..", "model")
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

EPOCHS = 8
BATCH_SIZE = 128


def ozetle(X):
    """(N, WINDOW, F) pencereyi (N, F*4) düz özet vektörüne çevirir: mean/std/min/max.
    Klasik ML modelleri (LogReg/RF) zaman boyutunu doğal olarak işleyemez; bu, sekans
    bilgisini kaybederek basit istatistiklere indirgeyen standart bir yaklaşımdır."""
    return np.concatenate([X.mean(1), X.std(1), X.min(1), X.max(1)], axis=1)


class TekBasinaCNN(nn.Module):
    """CNNLSTM'in konvolüsyon kısmı; LSTM YOK, global average pooling ile özetlenir.
    Zamansal sırayı (hangi adımın önce/sonra geldiğini) modellemez."""

    def __init__(self, n_features, n_classes):
        super().__init__()
        self.conv1 = nn.Conv1d(n_features, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.fc = nn.Linear(64, n_classes)

    def forward(self, x):
        x = x.permute(0, 2, 1)
        x = self.relu(self.conv1(x))
        x = self.relu(self.conv2(x))
        x = x.mean(dim=2)          # global average pooling (zaman boyutunu düzleştirir)
        return self.fc(x)


class TekBasinaLSTM(nn.Module):
    """CNNLSTM'in LSTM kısmı; konvolüsyon YOK, ham özellikler doğrudan LSTM'e girer.
    Yerel (kısa vadeli) titreşim paternlerini çıkaran evrişim katmanı yok."""

    def __init__(self, n_features, n_classes, hidden=64):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.fc = nn.Linear(hidden, n_classes)

    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return self.fc(h[-1])


def egit_basit_model(model, train_loader, epochs=EPOCHS):
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    kriter = nn.CrossEntropyLoss()
    model.train()
    for _ in range(epochs):
        for xb, yb, _ in train_loader:
            opt.zero_grad()
            out = model(xb)
            loss = kriter(out, yb)
            loss.backward()
            opt.step()
    model.eval()
    return model


def torch_degerlendir(model, Xt, yt):
    with torch.no_grad():
        t0 = time.perf_counter()
        logit = model(torch.from_numpy(Xt))
        sure = time.perf_counter() - t0
        tahmin = logit.argmax(1).numpy()
    return tahmin, sure


def sklearn_degerlendir(model, Xt):
    t0 = time.perf_counter()
    tahmin = model.predict(Xt)
    sure = time.perf_counter() - t0
    return tahmin, sure


def main():
    print("Veri yükleniyor ve pencereler oluşturuluyor...")
    train_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_train.csv"))
    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))

    scaler = StandardScaler().fit(train_df[FEATURE_COLS].values)
    encoder = LabelEncoder().fit(train_df["fault_type"].values)
    classes = list(encoder.classes_)

    Xf, yf, _ = build_sequences(train_df, scaler, encoder, window=WINDOW, stride=STRIDE)
    Xt, yt, _ = build_sequences(test_df, scaler, encoder, window=WINDOW, stride=STRIDE)
    print(f"Train sekans: {Xf.shape}  Test sekans: {Xt.shape}")

    sonuclar = []

    # --- 1-2. Logistic Regression / Random Forest (özetlenmiş pencere girdisi) ---
    # Özet vektör (mean/std/min/max) kendi içinde farklı ölçeklerde olduğu için LogReg'e
    # girmeden önce AYRICA standardize edilir; RF ağaç tabanlı olduğundan ölçekten etkilenmez
    # ama aynı özet girdiyi paylaşarak kıyası basit tutmak için o da aynı ozetle() çıktısını kullanır.
    Xf_ozet_ham, Xt_ozet_ham = ozetle(Xf), ozetle(Xt)
    ozet_scaler = StandardScaler().fit(Xf_ozet_ham)
    Xf_ozet, Xt_ozet = ozet_scaler.transform(Xf_ozet_ham), ozet_scaler.transform(Xt_ozet_ham)
    for ad, model, girdi_f, girdi_t in [
        # C=0.1: veri neredeyse ayrıştırılabilir olduğu için (bazı sınıflar özet uzayda net
        # ayrılıyor) varsayılan C=1.0 ağırlıkları ıraksatıp overflow'a yol açıyordu; daha güçlü
        # L2 düzenlileştirme bunu bastırır.
        ("Logistic Regression", LogisticRegression(max_iter=2000, C=0.1, random_state=SEED), Xf_ozet, Xt_ozet),
        ("Random Forest", RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=-1),
         Xf_ozet_ham, Xt_ozet_ham),
    ]:
        print(f"\n{ad} eğitiliyor...")
        model.fit(girdi_f, yf)
        tahmin, sure = sklearn_degerlendir(model, girdi_t)
        acc = accuracy_score(yt, tahmin)
        f1 = f1_score(yt, tahmin, average="macro")
        sonuclar.append({
            "model": ad, "accuracy": acc, "macro_f1": f1,
            "toplam_inference_sn": sure, "ornek_basi_ms": sure / len(Xt) * 1000,
            "n_test": len(Xt),
        })
        print(f"  accuracy={acc:.4f} macro_f1={f1:.4f} inference={sure:.3f}sn")

    # --- 3. Tek başına 1D-CNN ---
    train_loader = DataLoader(SeqDataset(Xf, yf, np.zeros_like(yf)), batch_size=BATCH_SIZE, shuffle=True)
    for ad, model in [
        ("1D-CNN (tek başına)", TekBasinaCNN(len(FEATURE_COLS), len(classes))),
        ("LSTM (tek başına)", TekBasinaLSTM(len(FEATURE_COLS), len(classes))),
    ]:
        print(f"\n{ad} eğitiliyor ({EPOCHS} epoch)...")
        model = egit_basit_model(model, train_loader)
        tahmin, sure = torch_degerlendir(model, Xt, yt)
        acc = accuracy_score(yt, tahmin)
        f1 = f1_score(yt, tahmin, average="macro")
        sonuclar.append({
            "model": ad, "accuracy": acc, "macro_f1": f1,
            "toplam_inference_sn": sure, "ornek_basi_ms": sure / len(Xt) * 1000,
            "n_test": len(Xt),
        })
        print(f"  accuracy={acc:.4f} macro_f1={f1:.4f} inference={sure:.3f}sn")

    # --- 5. Final CNN+LSTM (yeniden eğitilmez, kayıtlı checkpoint yüklenir) ---
    model_path = os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt")
    if os.path.exists(model_path):
        print("\nFinal CNN+LSTM checkpoint yükleniyor (yeniden eğitilmiyor)...")
        final_model, checkpoint = load_model_checkpoint(model_path)
        final_scaler, final_encoder = rebuild_scaler_and_encoder(checkpoint)
        Xt_final, yt_final, _ = build_sequences(
            test_df, final_scaler, final_encoder,
            window=checkpoint["window"], stride=checkpoint["stride"],
        )
        with torch.no_grad():
            t0 = time.perf_counter()
            logit_tip, _ = final_model(torch.from_numpy(Xt_final))
            sure = time.perf_counter() - t0
            tahmin = logit_tip.argmax(1).numpy()
        acc = accuracy_score(yt_final, tahmin)
        f1 = f1_score(yt_final, tahmin, average="macro")
        sonuclar.append({
            "model": "Final CNN+LSTM (çok görevli, kayıtlı checkpoint)",
            "accuracy": acc, "macro_f1": f1,
            "toplam_inference_sn": sure, "ornek_basi_ms": sure / len(Xt_final) * 1000,
            "n_test": len(Xt_final),
        })
        print(f"  accuracy={acc:.4f} macro_f1={f1:.4f} inference={sure:.3f}sn")
    else:
        print(f"\nUyarı: {model_path} bulunamadı, final model kıyasa dahil edilmedi.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "baseline_karsilastirma.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "epochs_basit_modeller": EPOCHS, "sonuclar": sonuclar}, f,
                   ensure_ascii=False, indent=2)

    md_lines = [
        "# Baseline Model Karşılaştırması",
        "",
        "Mevcut çok görevli CNN+LSTM mimarisinin gerekçesini deneysel olarak gösterir. "
        "Baseline'lar (LogReg/RF/tek başına CNN/tek başına LSTM) yalnızca arıza TİPİ görevi "
        "üzerinde, aynı train/test bölmesiyle eğitilmiştir; final model kayıtlı checkpoint'ten "
        "yüklenip yeniden eğitilmeden değerlendirilmiştir.",
        "",
        "| Model | Accuracy | Macro F1 | Toplam Inference (sn) | Örnek Başı (ms) | Test Örneği |",
        "|---|---|---|---|---|---|",
    ]
    for s in sonuclar:
        md_lines.append(
            f"| {s['model']} | {s['accuracy']:.4f} | {s['macro_f1']:.4f} | "
            f"{s['toplam_inference_sn']:.3f} | {s['ornek_basi_ms']:.4f} | {s['n_test']} |"
        )
    with open(os.path.join(RESULTS_DIR, "baseline_karsilastirma.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print("\nSonuçlar yazıldı: results/baseline_karsilastirma.json, results/baseline_karsilastirma.md")


if __name__ == "__main__":
    main()
