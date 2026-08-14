"""
Model mimarisi ve paylaşılan sabitler.

Bu modül hem eğitim (rayli_dl_egitim.py) hem de eğitilmiş modeli yeniden eğitmeden kullanan
tahmin scripti (rayli_tahmin.py) ve canlı akış sunucusu tarafından import edilir. Mimari tanımı
tek bir yerde tutularak eğitim ile tahmin arasında olası bir tutarsızlık (örn. iki yerde farklı
katman boyutu) engellenmiş olur.

Model ÇOK GÖREVLİDİR (multi-task): tek bir gövde (CNN+LSTM) üzerinde iki çıkış başlığı vardır —
(1) arıza tipi (6 sınıf), (2) arıza şiddeti (none/mild/moderate/severe). Şiddet, arıza tipiyle
ilişkili ama ayrı bir bilgidir ve operasyonda "ne kadar acil?" sorusunu yanıtlar.
"""
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset
from sklearn.preprocessing import StandardScaler, LabelEncoder

FEATURE_COLS = [
    "track_km", "speed_kmh", "load_ton",
    "vib_x_rms_g", "vib_y_rms_g", "vib_z_rms_g", "vib_peak_g", "vib_kurtosis", "vib_crest_factor",
    "vib_dom_freq_hz", "acoustic_rms", "acoustic_peak_freq_hz",
    "axle_box_temp_c", "brake_temp_c", "motor_temp_c", "ambient_temp_c",
    "motor_current_a", "motor_voltage_v", "humidity_pct",
]
GROUP_COLS = ["train_id", "wagon_id", "axle_id"]
WINDOW = 10     # 10 x 2 sn = 20 saniyelik geçmiş pencere
STRIDE = 2

# Şiddet sınıfları sıralıdır (ordinal); sabit sırayla tutulur ki eğitim/çıkarım aynı indeksleri
# kullansın ve arayüzde doğal sırada gösterilebilsin.
SEVERITY_CLASSES = ["none", "mild", "moderate", "severe"]


class SeqDataset(Dataset):
    """Sekans veri kümesi: (X, arıza tipi etiketi, şiddet etiketi)."""

    def __init__(self, X, y_tip, y_sev):
        self.X = torch.from_numpy(X)
        self.y_tip = torch.from_numpy(y_tip)
        self.y_sev = torch.from_numpy(y_sev)

    def __len__(self):
        return len(self.y_tip)

    def __getitem__(self, i):
        return self.X[i], self.y_tip[i], self.y_sev[i]


class CNNLSTM(nn.Module):
    """1D-CNN (kısa vadeli/yerel titreşim paternlerini çıkarır) + LSTM (zamansal trendi
    öğrenir) sekans sınıflandırıcısı — çok görevli (arıza tipi + şiddet).

    Girdi şekli : (batch, WINDOW, len(FEATURE_COLS))
    Çıktı       : (tip_logits, siddet_logits) -- ham logit'ler (softmax uygulanmamış)
    """

    def __init__(self, n_features, n_classes, n_severity=len(SEVERITY_CLASSES), hidden=64):
        super().__init__()
        self.conv1 = nn.Conv1d(n_features, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.lstm = nn.LSTM(64, hidden, batch_first=True)
        self.fc1 = nn.Linear(hidden, 32)
        self.drop = nn.Dropout(0.3)
        self.fc_tip = nn.Linear(32, n_classes)          # arıza tipi başlığı
        self.fc_sev = nn.Linear(32, n_severity)         # arıza şiddeti başlığı

    def forward(self, x):
        x = x.permute(0, 2, 1)                 # (batch, features, seq) -> Conv1d için
        x = self.relu(self.conv1(x))
        x = self.relu(self.conv2(x))
        x = x.permute(0, 2, 1)                 # (batch, seq, channels) -> LSTM için
        _, (h, _) = self.lstm(x)
        z = self.relu(self.fc1(h[-1]))
        z = self.drop(z)
        return self.fc_tip(z), self.fc_sev(z)


def load_model_checkpoint(path, map_location="cpu"):
    """Kaydedilmiş .pt dosyasını yükler, ağırlıkları CNNLSTM mimarisine yerleştirir ve
    (model, checkpoint_dict) döndürür. checkpoint_dict içinde sınıf isimleri, özellik
    kolonları ve ölçekleyici (scaler) parametreleri de bulunur."""
    checkpoint = torch.load(path, map_location=map_location, weights_only=False)
    model = CNNLSTM(
        n_features=len(checkpoint["feature_cols"]),
        n_classes=len(checkpoint["classes"]),
        n_severity=len(checkpoint.get("severity_classes", SEVERITY_CLASSES)),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, checkpoint


def rebuild_scaler_and_encoder(checkpoint):
    """Eğitimde kullanılan StandardScaler ve LabelEncoder'ı, checkpoint içine kaydedilmiş
    parametrelerden (ortalama/std ve sınıf isimleri) yeniden kurar — sıfırdan fit etmeye
    gerek kalmaz, eğitimdekiyle birebir aynı ölçekleme uygulanır.

    Tahmin scripti (rayli_tahmin.py) ve canlı akış sunucusu (rayli_canli_akis_sunucu.py)
    aynı fonksiyonu kullanır; iki taraf arasında ölçekleme farkı oluşamaz."""
    scaler = StandardScaler()
    scaler.mean_ = np.array(checkpoint["scaler_mean"])
    scaler.scale_ = np.array(checkpoint["scaler_scale"])
    scaler.var_ = scaler.scale_ ** 2
    scaler.n_features_in_ = len(scaler.mean_)

    encoder = LabelEncoder()
    encoder.classes_ = np.array(checkpoint["classes"])
    return scaler, encoder
