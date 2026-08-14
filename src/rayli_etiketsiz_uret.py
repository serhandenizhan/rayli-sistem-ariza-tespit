"""
Test setinin ETİKETSİZ (kör) halini ve ayrı bir CEVAP ANAHTARI dosyasını üretir.

Neden gerekli?
--------------
Canlı akış simülasyonunda sistemin "gerçek hayattaki" halini taklit etmesi için, akan
verinin içinde etiket (fault_type / fault_severity) BULUNMAMALIDIR — gerçek bir sahada da
sensörden gelen pakette arıza etiketi yoktur. Model zaten etiketi girdi olarak kullanmıyor
(FEATURE_COLS içinde yok), ama etiketi akıştan fiziksel olarak çıkarmak:

  1. Sızıntının (leakage) yapısal olarak imkânsız olduğunu kanıtlar — arayüze giden pakette
     etiket yoksa, "acaba model/dashboard etiketi bir yerden görüyor mu?" sorusu ortadan kalkar.
  2. Doğrulamayı (validation) ayrı bir adıma dönüştürür: tahminler üretildikten SONRA cevap
     anahtarı ile eşleştirilip anlık doğruluk/karmaşıklık matrisi hesaplanır.

Bu yüzden test verisi iki dosyaya ayrılır:
  - data/rayli_sistem_test_akis.csv          -> etiketsiz, akışa verilen veri (sample_id + sensörler)
  - data/rayli_sistem_test_cevap_anahtari.csv -> sample_id -> fault_type / fault_severity

İkisi `sample_id` kolonu üzerinden eşleşir. sample_id, kaynak test CSV'sindeki satır sırasına
göre üretilir (deterministik).

Kullanım (src/ klasöründen):
    python rayli_etiketsiz_uret.py
"""

import os

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

LABEL_COLS = ["fault_type", "fault_severity"]

SRC_CSV = os.path.join(DATA_DIR, "rayli_sistem_test.csv")
STREAM_CSV = os.path.join(DATA_DIR, "rayli_sistem_test_akis.csv")
KEY_CSV = os.path.join(DATA_DIR, "rayli_sistem_test_cevap_anahtari.csv")


def main():
    if not os.path.exists(SRC_CSV):
        raise SystemExit(
            f"Test verisi bulunamadı: {SRC_CSV}\n"
            "Önce 'python rayli_veri_uret.py' çalıştırın."
        )

    df = pd.read_csv(SRC_CSV)
    df.insert(0, "sample_id", range(len(df)))

    stream_df = df.drop(columns=LABEL_COLS)
    key_df = df[["sample_id", "timestamp", "train_id", "wagon_id", "axle_id"] + LABEL_COLS]

    stream_df.to_csv(STREAM_CSV, index=False)
    key_df.to_csv(KEY_CSV, index=False)

    print(f"Etiketsiz akış verisi : {STREAM_CSV}  ({len(stream_df)} satır, "
          f"{len(stream_df.columns)} kolon — etiket yok)")
    print(f"Cevap anahtarı        : {KEY_CSV}  ({len(key_df)} satır)")
    print("Sınıf dağılımı (cevap anahtarı):", key_df["fault_type"].value_counts().to_dict())


if __name__ == "__main__":
    main()
