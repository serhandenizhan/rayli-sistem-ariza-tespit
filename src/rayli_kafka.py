"""
Kafka adaptörü — canlı akışı bir CSV yerine gerçek bir mesaj kuyruğundan besleme.

Neden?
------
Gerçek bir sahada sensör verisi dosyadan değil, bir mesaj kuyruğundan (Kafka, MQTT, AMQP...)
akar. Bu modül, projenin akış mimarisinin kaynaktan bağımsız olduğunu gösterir: canlı akış
sunucusu `--kaynak kafka` ile aynı veriyi Kafka topic'inden okuyup aynı boru hattını çalıştırır.

İki taraf vardır:
  1. ÜRETİCİ (producer): `data/rayli_sistem_test_akis.csv` içindeki ETİKETSİZ satırları
     zaman damgasına göre tick tick Kafka topic'ine yazar — saha sensörlerini taklit eder.
  2. TÜKETİCİ (consumer): topic'teki mesajları okuyup DataFrame'e çevirir; canlı akış
     sunucusu bunu CSV yerine kullanır.

Not: Etiket (fault_type/fault_severity) Kafka'ya HİÇ gönderilmez — sızıntı ayrımı burada da
korunur; doğrulama yine sunucudaki ayrı cevap anahtarıyla yapılır.

Kurulum ve kullanım:
    pip install kafka-python
    # Kafka broker'ı ayakta olmalı (örn. docker compose ile, bkz. README)
    python rayli_kafka.py --uret                 # CSV -> Kafka (gerçek zamanlı yayın)
    python rayli_kafka.py --uret --hiz 20        # 20x hızlı yayın
    python rayli_kafka.py --dinle --limit 100    # topic'ten örnek mesaj oku (teşhis)
    python rayli_canli_akis_sunucu.py --kaynak kafka   # sunucuyu Kafka'dan besle
"""

import argparse
import json
import os
import time

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
STREAM_CSV = os.path.join(DATA_DIR, "rayli_sistem_test_akis.csv")

VARSAYILAN_SUNUCU = "localhost:9092"
VARSAYILAN_TOPIC = "rayli-sensor"
TICK_SECONDS = 2.0


def _kafka_modulu():
    """kafka-python'u içe aktarır; kurulu değilse anlaşılır bir hata verir."""
    try:
        import kafka  # noqa: F401
        return kafka
    except ImportError as e:
        raise SystemExit(
            "kafka-python kurulu değil. Kurmak için:\n"
            "    pip install kafka-python\n"
            "Kafka kullanmadan çalışmak isterseniz sunucuyu varsayılan (--kaynak csv) modda "
            "başlatmanız yeterlidir."
        ) from e


def uretici_calistir(sunucu=VARSAYILAN_SUNUCU, topic=VARSAYILAN_TOPIC, hiz=10.0, dongu=False):
    """Etiketsiz akış CSV'sini tick tick Kafka'ya yayınlar (saha sensörü taklidi)."""
    kafka = _kafka_modulu()
    if not os.path.exists(STREAM_CSV):
        raise SystemExit(f"Akış verisi yok: {STREAM_CSV}\nÖnce 'python rayli_etiketsiz_uret.py' çalıştırın.")

    df = pd.read_csv(STREAM_CSV, parse_dates=["timestamp"])
    assert "fault_type" not in df.columns, "Kafka'ya etiket gönderilmemeli!"
    ticks = [g for _, g in df.groupby("timestamp", sort=True)]

    producer = kafka.KafkaProducer(
        bootstrap_servers=sunucu,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode("utf-8"),
        key_serializer=lambda k: str(k).encode("utf-8"),
    )
    print(f"Üretici hazır: {sunucu} -> topic '{topic}' | {len(ticks)} tick, hız {hiz}x")

    tur = 0
    while True:
        tur += 1
        for i, g in enumerate(ticks):
            for _, row in g.iterrows():
                mesaj = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                         for k, v in row.to_dict().items()}
                producer.send(topic, key=row["train_id"], value=mesaj)
            producer.flush()
            if (i + 1) % 25 == 0:
                print(f"  tur {tur} | tick {i + 1}/{len(ticks)} yayınlandı")
            time.sleep(TICK_SECONDS / max(hiz, 0.1))
        if not dongu:
            break
    print("Yayın tamamlandı.")


def topic_dataframe_oku(sunucu=VARSAYILAN_SUNUCU, topic=VARSAYILAN_TOPIC, zaman_asimi_ms=8000):
    """Topic'teki mevcut mesajları okuyup DataFrame'e çevirir.

    Canlı akış sunucusu başlangıçta bunu çağırır: topic'te birikmiş veriyi (baştan) okur ve
    kendi tick motoruna verir. Böylece akış kaynağı değişse de boru hattının geri kalanı
    (pencereleme, ölçekleme, model, doğrulama) aynı kalır.
    """
    kafka = _kafka_modulu()
    tuketici = kafka.KafkaConsumer(
        topic,
        bootstrap_servers=sunucu,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=zaman_asimi_ms,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    kayitlar = [m.value for m in tuketici]
    tuketici.close()

    if not kayitlar:
        raise SystemExit(
            f"'{topic}' topic'inde mesaj bulunamadı.\n"
            "Önce üreticiyi çalıştırın: python rayli_kafka.py --uret"
        )
    df = pd.DataFrame(kayitlar)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    sayisal = [c for c in df.columns if c not in
               ("timestamp", "line_id", "train_id", "wagon_id", "axle_id", "next_station", "at_station")]
    for c in sayisal:
        df[c] = pd.to_numeric(df[c], errors="ignore")
    print(f"Kafka'dan {len(df)} satır okundu ({df['timestamp'].nunique()} tick).")
    return df


def main():
    ap = argparse.ArgumentParser(description="Raylı sistem canlı akışı için Kafka adaptörü")
    ap.add_argument("--uret", action="store_true", help="CSV'yi Kafka topic'ine yayınla")
    ap.add_argument("--dinle", action="store_true", help="Topic'ten örnek mesaj oku (teşhis)")
    ap.add_argument("--sunucu", default=VARSAYILAN_SUNUCU)
    ap.add_argument("--topic", default=VARSAYILAN_TOPIC)
    ap.add_argument("--hiz", type=float, default=10.0)
    ap.add_argument("--dongu", action="store_true", help="Yayını sonsuz döngüde tekrarla")
    ap.add_argument("--limit", type=int, default=5, help="--dinle ile gösterilecek mesaj sayısı")
    args = ap.parse_args()

    if args.uret:
        uretici_calistir(args.sunucu, args.topic, args.hiz, args.dongu)
    elif args.dinle:
        df = topic_dataframe_oku(args.sunucu, args.topic)
        print(df.head(args.limit).to_string())
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
