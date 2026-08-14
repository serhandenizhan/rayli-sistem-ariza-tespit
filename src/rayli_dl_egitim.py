"""
Raylı sistem arıza sınıflandırması için 1D-CNN + LSTM tabanlı ÇOK GÖREVLİ sekans modelinin
EĞİTİMİ.

Model mimarisi rayli_model.py'de, veri/sekans yardımcı fonksiyonları rayli_veri_utils.py'de
tanımlıdır — bu script sadece eğitim döngüsünü, değerlendirmeyi ve sonuçların kaydedilmesini
yönetir. Eğitilmiş modeli YENİDEN EĞİTMEDEN kullanmak isterseniz rayli_tahmin.py'yi çalıştırın.

Çok görevli (multi-task) yapı: tek gövde, iki çıkış başlığı —
  1) arıza tipi   (normal, wheel_flat, bearing_fault, brake_fault, motor_fault, rail_crack)
  2) arıza şiddeti (none, mild, moderate, severe)
Toplam kayıp = tip kaybı + SEVERITY_AGIRLIK * şiddet kaybı. Şiddet ikincil görevdir; ağırlığı
1'den küçük tutulur ki asıl görev olan tip sınıflandırması bozulmasın.

Yaklaşım: her dingil (axle) için ardışık 10 pencereyi (2 sn'lik satırlar, toplam 20 saniye)
bir araya getirip dizinin SON adımındaki arıza sınıfını tahmin ediyoruz. Bu, canlı akış
senaryosuna doğrudan uyar.

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

from rayli_model import FEATURE_COLS, CNNLSTM, SeqDataset, SEVERITY_CLASSES
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
SEVERITY_AGIRLIK = 0.4      # ikincil görevin toplam kayıptaki ağırlığı


def run_epoch(model, loader, kriter_tip, kriter_sev, optimizer=None):
    """Bir epoch çalıştırır. optimizer verilirse eğitim, verilmezse değerlendirme modudur."""
    train_mode = optimizer is not None
    model.train() if train_mode else model.eval()
    total_loss, correct_tip, correct_sev, total = 0.0, 0, 0, 0
    context = torch.enable_grad() if train_mode else torch.no_grad()
    with context:
        for xb, yb_tip, yb_sev in loader:
            if train_mode:
                optimizer.zero_grad()
            out_tip, out_sev = model(xb)
            loss = kriter_tip(out_tip, yb_tip) + SEVERITY_AGIRLIK * kriter_sev(out_sev, yb_sev)
            if train_mode:
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * xb.size(0)
            correct_tip += (out_tip.argmax(1) == yb_tip).sum().item()
            correct_sev += (out_sev.argmax(1) == yb_sev).sum().item()
            total += xb.size(0)
    return total_loss / total, correct_tip / total, correct_sev / total


def main():
    train_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_train.csv"))
    test_df = load_df(os.path.join(DATA_DIR, "rayli_sistem_test.csv"))

    scaler = StandardScaler().fit(train_df[FEATURE_COLS].values)
    encoder = LabelEncoder().fit(sorted(train_df["fault_type"].unique()))
    classes = list(encoder.classes_)
    print("Arıza sınıfları:", classes)
    print("Şiddet sınıfları:", SEVERITY_CLASSES)

    Xf, yf, sf, Xv, yv, sv = build_sequences_with_val_split(train_df, scaler, encoder)
    Xt, yt, st = build_sequences(test_df, scaler, encoder)
    print(f"Fit dizisi: {Xf.shape} | Val dizisi: {Xv.shape} | Test dizisi: {Xt.shape}")

    train_loader = DataLoader(SeqDataset(Xf, yf, sf), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(SeqDataset(Xv, yv, sv), batch_size=256, shuffle=False)
    test_loader = DataLoader(SeqDataset(Xt, yt, st), batch_size=256, shuffle=False)

    # Sınıf dengesizliği: her iki başlık için de ters frekans ağırlıklandırması
    tip_agirlik = compute_class_weight("balanced", classes=np.arange(len(classes)), y=yf)
    sev_mevcut = np.unique(sf)
    sev_agirlik = np.ones(len(SEVERITY_CLASSES))
    sev_agirlik[sev_mevcut] = compute_class_weight("balanced", classes=sev_mevcut, y=sf)
    print("Sınıf ağırlıkları (tip):", dict(zip(classes, np.round(tip_agirlik, 2))))
    print("Sınıf ağırlıkları (şiddet):", dict(zip(SEVERITY_CLASSES, np.round(sev_agirlik, 2))))

    model = CNNLSTM(n_features=len(FEATURE_COLS), n_classes=len(classes),
                    n_severity=len(SEVERITY_CLASSES))
    kriter_tip = nn.CrossEntropyLoss(weight=torch.tensor(tip_agirlik, dtype=torch.float32))
    kriter_sev = nn.CrossEntropyLoss(weight=torch.tensor(sev_agirlik, dtype=torch.float32))
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    history = []
    for epoch in range(1, EPOCHS + 1):
        tr_loss, tr_acc, tr_sev = run_epoch(model, train_loader, kriter_tip, kriter_sev, optimizer)
        val_loss, val_acc, val_sev = run_epoch(model, val_loader, kriter_tip, kriter_sev)
        history.append(dict(epoch=epoch, train_loss=tr_loss, train_acc=tr_acc, train_sev_acc=tr_sev,
                            val_loss=val_loss, val_acc=val_acc, val_sev_acc=val_sev))
        print(f"Epoch {epoch:2d}/{EPOCHS} | train_loss {tr_loss:.4f} tip {tr_acc:.3f} sev {tr_sev:.3f} "
              f"| val_loss {val_loss:.4f} tip {val_acc:.3f} sev {val_sev:.3f}")

    # --- Final test değerlendirmesi ---
    model.eval()
    tahmin_tip, gercek_tip, tahmin_sev, gercek_sev = [], [], [], []
    with torch.no_grad():
        for xb, yb_tip, yb_sev in test_loader:
            o_tip, o_sev = model(xb)
            tahmin_tip.extend(o_tip.argmax(1).tolist())
            tahmin_sev.extend(o_sev.argmax(1).tolist())
            gercek_tip.extend(yb_tip.tolist())
            gercek_sev.extend(yb_sev.tolist())

    report = classification_report(gercek_tip, tahmin_tip, target_names=classes, digits=3)
    report_dict = classification_report(gercek_tip, tahmin_tip, target_names=classes,
                                        output_dict=True, zero_division=0)
    macro_f1 = f1_score(gercek_tip, tahmin_tip, average="macro")

    sev_mevcut_test = sorted(set(gercek_sev) | set(tahmin_sev))
    sev_adlar = [SEVERITY_CLASSES[i] for i in sev_mevcut_test]
    sev_report = classification_report(gercek_sev, tahmin_sev, labels=sev_mevcut_test,
                                       target_names=sev_adlar, digits=3, zero_division=0)
    sev_report_dict = classification_report(gercek_sev, tahmin_sev, labels=sev_mevcut_test,
                                            target_names=sev_adlar, output_dict=True, zero_division=0)
    sev_macro_f1 = f1_score(gercek_sev, tahmin_sev, average="macro", zero_division=0)
    sev_acc = float(np.mean(np.array(gercek_sev) == np.array(tahmin_sev)))

    print("\n=== TEST SETİ — ARIZA TİPİ ===")
    print(report)
    print("Macro F1 (tip):", round(macro_f1, 4))
    print("\n=== TEST SETİ — ARIZA ŞİDDETİ ===")
    print(sev_report)
    print(f"Şiddet accuracy: {sev_acc:.4f} | macro F1: {sev_macro_f1:.4f}")

    cm = confusion_matrix(gercek_tip, tahmin_tip)
    cm_df = pd.DataFrame(cm, index=[f"gercek_{c}" for c in classes],
                         columns=[f"tahmin_{c}" for c in classes])
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
    fig2, axes = plt.subplots(1, 3, figsize=(15, 4))
    axes[0].plot(hist_df.epoch, hist_df.train_loss, label="train")
    axes[0].plot(hist_df.epoch, hist_df.val_loss, label="val")
    axes[0].set_title("Toplam Loss"); axes[0].set_xlabel("Epoch"); axes[0].legend()
    axes[1].plot(hist_df.epoch, hist_df.train_acc, label="train")
    axes[1].plot(hist_df.epoch, hist_df.val_acc, label="val")
    axes[1].set_title("Arıza tipi accuracy"); axes[1].set_xlabel("Epoch"); axes[1].legend()
    axes[2].plot(hist_df.epoch, hist_df.train_sev_acc, label="train")
    axes[2].plot(hist_df.epoch, hist_df.val_sev_acc, label="val")
    axes[2].set_title("Şiddet accuracy"); axes[2].set_xlabel("Epoch"); axes[2].legend()
    fig2.tight_layout()
    fig2.savefig(os.path.join(RESULTS_DIR, "training_curves.png"), dpi=150)

    torch.save({
        "model_state_dict": model.state_dict(),
        "classes": classes,
        "severity_classes": SEVERITY_CLASSES,
        "feature_cols": FEATURE_COLS,
        "window": Xf.shape[1],
        "stride": 2,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
    }, os.path.join(MODEL_DIR, "rayli_cnn_lstm_model.pt"))

    with open(os.path.join(RESULTS_DIR, "test_classification_report.txt"), "w") as f:
        f.write("=== ARIZA TİPİ ===\n")
        f.write(report)
        f.write(f"\nMacro F1: {macro_f1:.4f}\n\n=== ARIZA ŞİDDETİ ===\n")
        f.write(sev_report)
        f.write(f"\nŞiddet accuracy: {sev_acc:.4f} | Macro F1: {sev_macro_f1:.4f}\n")

    # Dashboard'ın (web arayüzü) "Eğitim" panelinde gösterebilmesi için makine-okunur özet.
    with open(os.path.join(RESULTS_DIR, "egitim_ozeti.json"), "w") as f:
        json.dump({
            "classes": classes,
            "severity_classes": SEVERITY_CLASSES,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "seed": SEED,
            "severity_agirlik": SEVERITY_AGIRLIK,
            "n_features": len(FEATURE_COLS),
            "window": int(Xf.shape[1]),
            "n_fit_seq": int(len(yf)), "n_val_seq": int(len(yv)), "n_test_seq": int(len(yt)),
            "history": history,
            "macro_f1": float(macro_f1),
            "accuracy": float(report_dict["accuracy"]),
            "report": report_dict,
            "confusion_matrix": cm.tolist(),
            "severity": {
                "accuracy": sev_acc,
                "macro_f1": float(sev_macro_f1),
                "report": sev_report_dict,
            },
        }, f, ensure_ascii=False, indent=2)

    print("\nModel (model/rayli_cnn_lstm_model.pt) ve grafikler (results/) kaydedildi.")
    print("Modeli yeniden eğitmeden kullanmak için: python rayli_tahmin.py")


if __name__ == "__main__":
    main()
