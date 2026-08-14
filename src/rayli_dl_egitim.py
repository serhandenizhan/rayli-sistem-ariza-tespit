"""
Raylı sistem arıza sınıflandırması için 1D-CNN + LSTM tabanlı sekans modelinin EĞİTİMİ.

Model mimarisi rayli_model.py'de, veri/sekans yardımcı fonksiyonları rayli_veri_utils.py'de
tanımlıdır — bu script sadece eğitim döngüsünü, değerlendirmeyi ve sonuçların kaydedilmesini
yönetir. Eğitilmiş modeli YENİDEN EĞİTMEDEN kullanmak isterseniz rayli_tahmin.py'yi çalıştırın.

Yaklaşım: her dingil (axle) için ardışık 10 pencereyi (2 sn'lik satırlar, toplam 20 saniye)
bir araya getirip dizinin SON adımındaki arıza sınıfını tahmin ediyoruz. Bu, canlı akış
senaryosuna doğrudan uyar: gerçek zamanlı sistemde son 20 saniyelik pencere sürekli güncellenir
ve her yeni örnekte tahmin tazelenir.

Değerlendirme sızıntısını (data leakage) önlemek için:
- Özellik ölçekleyici (StandardScaler) ve LabelEncoder SADECE train verisiyle fit edilir.
- Validation seti, train içindeki her dingilin KENDİ zaman diliminin son %15'inden ayrı
  pencerelerle oluşturulur (train/val sınırını aşan pencere yok).
- Test seti tamamen ayrı, kronolojik olarak sonraki zaman dilimidir (rayli_sistem_test.csv).
"""

import json
import os

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_class_weight
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rayli_model import FEATURE_COLS, CNNLSTM, SeqDataset
from rayli_veri_utils import load_df, build_sequences, build_sequences_with_val_split

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
MODEL_DIR = os.path.join(BASE_DIR, "..", "model")
RESULTS_DIR = os.path.join(BASE_DIR, "..", "results")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

EPOCHS = 15
BATCH_SIZE = 128


def run_epoch(model, loader, criterion, optimizer=None):
    train_mode = optimizer is not None
    model.train() if train_mode else model.eval()
    total_loss, correct, total = 0.0, 0, 0
    context = torch.enable_grad() if train_mode else torch.no_grad()
    with context:
        for xb, yb in loader:
            if train_mode:
                optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out, yb)
            if train_mode:
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * xb.size(0)
            correct += (out.argmax(1) == yb).sum().item()
            total += xb.size(0)
    return total_loss / total, correct / total


def main():
    train_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_train.csv"))
    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))

    scaler = StandardScaler().fit(train_df[FEATURE_COLS].values)
    encoder = LabelEncoder().fit(sorted(train_df["fault_type"].unique()))
    classes = list(encoder.classes_)
    print("Sınıflar:", classes)

    Xf, yf, Xv, yv = build_sequences_with_val_split(train_df, scaler, encoder)
    Xt, yt = build_sequences(test_df, scaler, encoder)
    print(f"Fit dizisi: {Xf.shape} | Val dizisi: {Xv.shape} | Test dizisi: {Xt.shape}")

    train_loader = DataLoader(SeqDataset(Xf, yf), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(SeqDataset(Xv, yv), batch_size=256, shuffle=False)
    test_loader = DataLoader(SeqDataset(Xt, yt), batch_size=256, shuffle=False)

    class_weights = compute_class_weight("balanced", classes=np.arange(len(classes)), y=yf)
    class_weights_t = torch.tensor(class_weights, dtype=torch.float32)
    print("Sınıf ağırlıkları:", dict(zip(classes, np.round(class_weights, 2))))

    model = CNNLSTM(n_features=len(FEATURE_COLS), n_classes=len(classes))
    criterion = nn.CrossEntropyLoss(weight=class_weights_t)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    history = []
    for epoch in range(1, EPOCHS + 1):
        tr_loss, tr_acc = run_epoch(model, train_loader, criterion, optimizer)
        val_loss, val_acc = run_epoch(model, val_loader, criterion, optimizer=None)
        history.append(dict(epoch=epoch, train_loss=tr_loss, train_acc=tr_acc,
                             val_loss=val_loss, val_acc=val_acc))
        print(f"Epoch {epoch:2d}/{EPOCHS} | train_loss {tr_loss:.4f} acc {tr_acc:.3f} "
              f"| val_loss {val_loss:.4f} acc {val_acc:.3f}")

    # --- Final test değerlendirmesi ---
    model.eval()
    all_preds, all_true = [], []
    with torch.no_grad():
        for xb, yb in test_loader:
            preds = model(xb).argmax(1)
            all_preds.extend(preds.tolist())
            all_true.extend(yb.tolist())

    report = classification_report(all_true, all_preds, target_names=classes, digits=3)
    report_dict = classification_report(all_true, all_preds, target_names=classes,
                                        output_dict=True, zero_division=0)
    macro_f1 = f1_score(all_true, all_preds, average="macro")
    print("\n=== TEST SETİ SONUÇLARI ===")
    print(report)
    print("Macro F1:", round(macro_f1, 4))

    cm = confusion_matrix(all_true, all_preds)
    cm_df = pd.DataFrame(cm, index=[f"gercek_{c}" for c in classes], columns=[f"tahmin_{c}" for c in classes])
    cm_df.to_csv(os.path.join(RESULTS_DIR, "confusion_matrix.csv"))
    print("\nConfusion matrix (satır=gerçek, sütun=tahmin):")
    print(cm_df)

    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes))); ax.set_xticklabels(classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes))); ax.set_yticklabels(classes)
    ax.set_xlabel("Tahmin"); ax.set_ylabel("Gerçek")
    ax.set_title("Confusion Matrix (Test Seti)")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=8)
    fig.colorbar(im)
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS_DIR, "confusion_matrix.png"), dpi=150)

    hist_df = pd.DataFrame(history)
    fig2, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(hist_df.epoch, hist_df.train_loss, label="train")
    axes[0].plot(hist_df.epoch, hist_df.val_loss, label="val")
    axes[0].set_title("Loss"); axes[0].set_xlabel("Epoch"); axes[0].legend()
    axes[1].plot(hist_df.epoch, hist_df.train_acc, label="train")
    axes[1].plot(hist_df.epoch, hist_df.val_acc, label="val")
    axes[1].set_title("Accuracy"); axes[1].set_xlabel("Epoch"); axes[1].legend()
    fig2.tight_layout()
    fig2.savefig(os.path.join(RESULTS_DIR, "training_curves.png"), dpi=150)

    torch.save({
        "model_state_dict": model.state_dict(),
        "classes": classes,
        "feature_cols": FEATURE_COLS,
        "window": Xf.shape[1],
        "stride": 2,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
    }, os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt"))

    with open(os.path.join(RESULTS_DIR, "test_classification_report.txt"), "w") as f:
        f.write(report)
        f.write(f"\nMacro F1: {macro_f1:.4f}\n")

    # Dashboard'ın (web arayüzü) "Eğitim" panelinde gösterebilmesi için makine-okunur özet.
    with open(os.path.join(RESULTS_DIR, "egitim_ozeti.json"), "w") as f:
        json.dump({
            "classes": classes,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "seed": SEED,
            "n_features": len(FEATURE_COLS),
            "window": int(Xf.shape[1]),
            "n_fit_seq": int(len(yf)), "n_val_seq": int(len(yv)), "n_test_seq": int(len(yt)),
            "history": history,
            "macro_f1": float(macro_f1),
            "accuracy": float(report_dict["accuracy"]),
            "report": report_dict,
            "confusion_matrix": cm.tolist(),
        }, f, ensure_ascii=False, indent=2)

    print("\nModel (model/rayli_cnn_lstm_model.pt) ve grafikler (results/) kaydedildi.")
    print("Modeli yeniden eğitmeden kullanmak için: python rayli_tahmin.py")


if __name__ == "__main__":
    main()
