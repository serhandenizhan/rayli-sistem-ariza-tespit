"""
Raylı sistem arıza tespiti için sentetik veri üretim scripti.

- Birden fazla tren/vagon/dingil için paralel zaman serileri üretir (2 saniyelik pencereler).
- Sınıf bazlı (normal, wheel_flat, bearing_fault, brake_fault, motor_fault) dingil arızalarını
  zamanla şiddeti artan (mild -> moderate -> severe) bölümler halinde enjekte eder.
- Konuma bağlı (rail_crack) arızaları döngüsel bir hat üzerindeki sabit "kusurlu bölge"lerden
  geçişlerde tekrar tekrar enjekte eder.
- Her arıza tipinin hem train hem test zaman diliminde en az birkaç örnekle temsil edilmesini
  garanti eden "dedicated" (ayrılmış) seriler kullanır; geri kalan serilerde ise arızalar tümüyle
  rastgele yerleştirilir (gerçekçi çeşitlilik için).
- Sonuçta tek bir "wide" tabloya birleştirip zaman bazlı (kronolojik) train/test bölmesi yapar.
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

rng = np.random.default_rng(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Simülasyon ayarları
# ---------------------------------------------------------------------------
# Başlangıç saati her çalıştırmada rastgele seçilir (bilinçli olarak SEED=42'li `rng`den
# TAMAMEN AYRI, sistem entropisiyle beslenen bir üreteç kullanılır) — böylece sensör
# DEĞERLERİNİN (titreşim, sıcaklık, arıza örüntüleri...) çalıştırmalar arası deterministik
# kalması bozulmaz, sadece saatin etiketi değişir. Gün, bugünün tarihi olarak sabitlenir;
# rastgele olan sadece saat/dakikadır.
_saat_rng = np.random.default_rng()
_bugun = datetime.now().date()
START_TIME = datetime(
    _bugun.year, _bugun.month, _bugun.day,
    int(_saat_rng.integers(0, 24)), int(_saat_rng.integers(0, 60)), 0,
)
WINDOW_SEC = 2
DURATION_MIN = 50                        # her seri (dingil) için toplam simülasyon süresi
N_STEPS = int(DURATION_MIN * 60 / WINDOW_SEC)
TRAIN_TEST_SPLIT_FRAC = 0.8              # kronolojik: ilk %80 train, son %20 test

TRAINS = ["T1", "T2", "T3"]
WAGONS_PER_TRAIN = 4
AXLES_PER_WAGON = 2
WHEEL_DIAM_M = 0.92
TRACK_LENGTH_KM = 12.0                   # döngüsel hat uzunluğu (banliyö/loop hattı varsayımı)

# Sabit ray kusuru bölgeleri (döngüsel hat üzerinde km konumu -> her turda tekrar geçilir)
RAIL_DEFECT_SITES = [
    {"km_center": 3.10, "width_km": 0.15, "severity": "moderate"},
    {"km_center": 8.40, "width_km": 0.12, "severity": "severe"},
]

SEVERITY_LEVEL = {"none": 0.0, "mild": 0.3, "moderate": 0.6, "severe": 1.0}
FAULT_TYPES = ["wheel_flat", "bearing_fault", "brake_fault", "motor_fault"]


def base_row(speed_kmh, load_ton):
    """Sağlıklı (normal) durum için gürültülü temel sensör değerleri."""
    return {
        "vib_x_rms_g": rng.normal(0.05, 0.008) + 0.0003 * speed_kmh,
        "vib_y_rms_g": rng.normal(0.05, 0.008) + 0.0003 * speed_kmh,
        "vib_z_rms_g": rng.normal(0.07, 0.010) + 0.0004 * speed_kmh,
        "vib_peak_g": rng.normal(0.15, 0.02) + 0.0006 * speed_kmh,
        "vib_kurtosis": rng.normal(3.0, 0.2),          # Gauss sinyalde ~3
        "vib_crest_factor": rng.normal(2.8, 0.15),
        "vib_dom_freq_hz": rng.normal(2.0, 0.3),
        "acoustic_rms": rng.normal(0.02, 0.004),
        "acoustic_peak_freq_hz": rng.normal(500, 50),
        "axle_box_temp_c": rng.normal(35, 2) + 0.05 * speed_kmh,
        "brake_temp_c": rng.normal(40, 3),
        "motor_temp_c": rng.normal(55, 4) + 0.03 * load_ton,
        "ambient_temp_c": rng.normal(24, 1.5),
        "motor_current_a": rng.normal(120, 8) + 0.4 * load_ton,
        "motor_voltage_v": rng.normal(750, 5),
        "humidity_pct": rng.normal(45, 5),
    }


def apply_fault(row, fault_type, sev, speed_kmh):
    """Verilen arıza tipi ve şiddetine (0-1) göre satırı bozar."""
    if fault_type == "wheel_flat":
        wheel_rot_hz = max(speed_kmh, 1) / 3.6 / (np.pi * WHEEL_DIAM_M)
        row["vib_dom_freq_hz"] = wheel_rot_hz + rng.normal(0, 0.05)
        row["vib_crest_factor"] += sev * rng.uniform(2.5, 4.0)
        row["vib_peak_g"] += sev * rng.uniform(1.0, 1.8)
        row["vib_kurtosis"] += sev * rng.uniform(1.5, 3.0)
    elif fault_type == "bearing_fault":
        row["vib_kurtosis"] += sev * rng.uniform(3.0, 6.0)
        row["vib_dom_freq_hz"] = rng.uniform(800, 1200)
        row["axle_box_temp_c"] += sev * rng.uniform(15, 30)
        row["vib_x_rms_g"] += sev * rng.uniform(0.05, 0.15)
    elif fault_type == "brake_fault":
        row["brake_temp_c"] += sev * rng.uniform(50, 100)
        row["motor_current_a"] += sev * rng.uniform(3, 8)
    elif fault_type == "motor_fault":
        row["motor_current_a"] += sev * rng.choice([-1, 1]) * rng.uniform(20, 45)
        row["motor_voltage_v"] -= sev * rng.uniform(15, 35)
        row["motor_temp_c"] += sev * rng.uniform(15, 35)
    return row


def severity_at(step, fault_start, fault_len):
    """mild -> moderate -> severe -> (onarım varsayımıyla) normale dönüş üçgen profili."""
    rel = (step - fault_start) / fault_len
    if rel < 0.5:
        return min(1.0, rel * 2)          # 0 -> 1 (ilk yarı: kötüleşme)
    return max(0.0, 1 - (rel - 0.5) * 2)   # 1 -> 0 (ikinci yarı: müdahale/azalma varsayımı)


def severity_label(sev_value):
    if sev_value < 0.15:
        return "none"
    if sev_value < 0.45:
        return "mild"
    if sev_value < 0.8:
        return "moderate"
    return "severe"


def build_series_list():
    series = []
    for train_id in TRAINS:
        for wagon_id in range(1, WAGONS_PER_TRAIN + 1):
            for axle_id in range(1, AXLES_PER_WAGON + 1):
                series.append((train_id, f"W{wagon_id}", f"A{axle_id}"))
    return series


def make_dedicated_episodes(series_list):
    """Her arıza tipi için en az bazı serilerde hem train hem test zaman diliminde
    garanti örnek üretecek şekilde (start, len, type) bölümleri atar."""
    dedicated = {s: [] for s in series_list}
    idx_pool = list(range(len(series_list)))
    rng.shuffle(idx_pool)
    ptr = 0
    for f_type in FAULT_TYPES:
        # train zaman diliminde garanti örnek (2 seri)
        for _ in range(2):
            s = series_list[idx_pool[ptr]]
            ptr += 1
            f_len = int(N_STEPS * rng.uniform(0.10, 0.18))
            f_start = rng.integers(0, int(N_STEPS * 0.5) - f_len)
            dedicated[s].append((f_start, f_len, f_type))
        # test zaman diliminde garanti örnek (2 seri) -> split noktasından sonra başlasın
        for _ in range(2):
            s = series_list[idx_pool[ptr]]
            ptr += 1
            f_len = int(N_STEPS * rng.uniform(0.05, 0.10))
            latest_start = N_STEPS - f_len - 1
            earliest_start = int(N_STEPS * TRAIN_TEST_SPLIT_FRAC) + 2
            f_start = rng.integers(earliest_start, max(earliest_start + 1, latest_start))
            dedicated[s].append((f_start, f_len, f_type))
    return dedicated


def generate_series(train_id, wagon_id, axle_id, forced_episodes):
    rows = []
    episodes = list(forced_episodes)

    # ek gerçekçi çeşitlilik için rastgele bölüm(ler) eklenebilir
    if rng.random() < 0.35:
        f_type = rng.choice(FAULT_TYPES)
        f_len = int(N_STEPS * rng.uniform(0.08, 0.20))
        f_start = int(rng.integers(0, max(1, N_STEPS - f_len)))
        episodes.append((f_start, f_len, f_type))

    speed_profile = 60 + 25 * np.sin(np.linspace(0, 3 * np.pi, N_STEPS)) + rng.normal(0, 3, N_STEPS)
    speed_profile = np.clip(speed_profile, 15, 110)
    load_ton = rng.uniform(20, 40)
    cum_distance = rng.uniform(0, TRACK_LENGTH_KM)

    for step in range(N_STEPS):
        speed = float(speed_profile[step])
        cum_distance += speed * (WINDOW_SEC / 3600)
        track_km = cum_distance % TRACK_LENGTH_KM
        ts = START_TIME + timedelta(seconds=step * WINDOW_SEC)

        row = base_row(speed, load_ton)

        active_fault = "normal"
        sev_val = 0.0
        for f_start, f_len, f_type in episodes:
            if f_start <= step < f_start + f_len:
                sev_val = severity_at(step, f_start, f_len)
                if sev_val > 0.1:
                    row = apply_fault(row, f_type, sev_val, speed)
                    active_fault = f_type
                break

        # Konum bazlı ray kusuru kontrolü (döngüsel hat üzerinde tekrar tekrar geçilir)
        for site in RAIL_DEFECT_SITES:
            if abs(track_km - site["km_center"]) <= site["width_km"]:
                site_sev = SEVERITY_LEVEL[site["severity"]]
                row["acoustic_rms"] += site_sev * rng.uniform(0.08, 0.2)
                row["vib_peak_g"] += site_sev * rng.uniform(0.5, 1.2)
                row["acoustic_peak_freq_hz"] += site_sev * rng.uniform(800, 1500)
                if active_fault == "normal":
                    active_fault = "rail_crack"
                    sev_val = site_sev

        row.update({
            "timestamp": ts.isoformat(),
            "train_id": train_id,
            "wagon_id": wagon_id,
            "axle_id": axle_id,
            "track_km": round(track_km, 3),
            "speed_kmh": round(speed, 1),
            "load_ton": round(load_ton, 1),
            "fault_type": active_fault,
            "fault_severity": severity_label(sev_val),
        })
        rows.append(row)
    return rows


def main():
    series_list = build_series_list()
    dedicated = make_dedicated_episodes(series_list)

    all_rows = []
    for s in series_list:
        train_id, wagon_id, axle_id = s
        all_rows.extend(generate_series(train_id, wagon_id, axle_id, dedicated[s]))

    df = pd.DataFrame(all_rows)

    col_order = [
        "timestamp", "train_id", "wagon_id", "axle_id", "track_km", "speed_kmh", "load_ton",
        "vib_x_rms_g", "vib_y_rms_g", "vib_z_rms_g", "vib_peak_g", "vib_kurtosis",
        "vib_crest_factor", "vib_dom_freq_hz", "acoustic_rms", "acoustic_peak_freq_hz",
        "axle_box_temp_c", "brake_temp_c", "motor_temp_c", "ambient_temp_c",
        "motor_current_a", "motor_voltage_v", "humidity_pct", "fault_type", "fault_severity",
    ]
    df = df[col_order]

    float_cols = df.select_dtypes(include=[float]).columns
    df[float_cols] = df[float_cols].round(4)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "train_id", "wagon_id", "axle_id"]).reset_index(drop=True)

    split_time = START_TIME + timedelta(seconds=TRAIN_TEST_SPLIT_FRAC * N_STEPS * WINDOW_SEC)
    train_df = df[df["timestamp"] < split_time].reset_index(drop=True)
    test_df = df[df["timestamp"] >= split_time].reset_index(drop=True)

    df.to_csv(os.path.join(DATA_DIR, "rayli_sistem_tum_veri.csv"), index=False)
    train_df.to_csv(os.path.join(DATA_DIR, "rayli_sistem_train.csv"), index=False)
    test_df.to_csv(os.path.join(DATA_DIR, "rayli_sistem_test.csv"), index=False)

    print(f"Toplam satır: {len(df)}  |  seri sayısı: {len(series_list)}  |  seri başına adım: {N_STEPS}")
    print(f"Train satır : {len(train_df)}  ({train_df['timestamp'].min()} -> {train_df['timestamp'].max()})")
    print(f"Test satır  : {len(test_df)}  ({test_df['timestamp'].min()} -> {test_df['timestamp'].max()})")
    print("\nGenel sınıf dağılımı (fault_type):")
    print(df["fault_type"].value_counts())
    print("\nTrain sınıf dağılımı:")
    print(train_df["fault_type"].value_counts())
    print("\nTest sınıf dağılımı:")
    print(test_df["fault_type"].value_counts())
    print("\nEksik değer sayısı (toplam):", df.isna().sum().sum())
    missing_in_train = set(df["fault_type"].unique()) - set(train_df["fault_type"].unique())
    missing_in_test = set(df["fault_type"].unique()) - set(test_df["fault_type"].unique())
    print("\nTrain'de eksik sınıf:", missing_in_train or "yok")
    print("Test'te eksik sınıf :", missing_in_test or "yok")


if __name__ == "__main__":
    main()
