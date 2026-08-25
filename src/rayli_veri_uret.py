"""
Raylı sistem arıza tespiti için sentetik veri üretim scripti — GERÇEK İSTANBUL METRO AĞI üzerinde.

- Hatlar, istasyonlar ve koordinatlar İBB Açık Veri Portalı'ndan gelen gerçek veridir
  (bkz. `istanbul_metro_agi.py`). Trenler bu gerçek hatlar üzerinde, gerçek istasyon
  dizilerinde hareket eder.
- Tren hareketi gerçekçidir: istasyonlar arasında hızlanma/seyir/frenleme, istasyonda bekleme
  (dwell), terminalde yön değiştirme. Hız profili artık sinüs değil, gerçek bir sefer profilidir.
- Bir trenin tüm dingilleri aynı konumu/hızı paylaşır (aynı araç), yükleri vagona göre değişir.
- Sınıf bazlı (normal, wheel_flat, bearing_fault, brake_fault, motor_fault) dingil arızalarını
  zamanla şiddeti artan (mild -> moderate -> severe) bölümler halinde enjekte eder.
- `rail_crack` artık gerçek hat üzerindeki SABİT ray kusuru noktalarına bağlıdır; tren o
  noktadan her geçtiğinde (her seferde) tekrar tetiklenir. Kusur noktaları hangi istasyonlar
  arasında olduğuyla birlikte `data/ray_kusur_noktalari.json` dosyasına yazılır (harita gösterir).
- Her arıza tipinin hem train hem test zaman diliminde temsil edilmesini garanti eden
  "dedicated" seriler kullanılır.
"""

import json
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import istanbul_metro_agi as ag

rng = np.random.default_rng(42)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Simülasyon ayarları
# ---------------------------------------------------------------------------
# Başlangıç saati her çalıştırmada rastgele seçilir (bilinçli olarak SEED=42'li `rng`den
# TAMAMEN AYRI, sistem entropisiyle beslenen bir üreteç kullanılır) — böylece sensör
# DEĞERLERİNİN çalıştırmalar arası deterministik kalması bozulmaz, sadece saatin etiketi değişir.
# Metro işletme saatleri içinde (06:00-23:00) bir saat seçilir.
_saat_rng = np.random.default_rng()
_bugun = datetime.now().date()
START_TIME = datetime(_bugun.year, _bugun.month, _bugun.day,
                      int(_saat_rng.integers(6, 23)), int(_saat_rng.integers(0, 60)), 0)

WINDOW_SEC = 2
DURATION_MIN = 50
N_STEPS = int(DURATION_MIN * 60 / WINDOW_SEC)
TRAIN_TEST_SPLIT_FRAC = 0.8              # kronolojik: ilk %80 train, son %20 test

WAGONS_PER_TRAIN = 2                     # her tren 2 vagon
AXLES_PER_WAGON = 2                      # her vagon 2 dingil -> tren başına 4 dingil
WHEEL_DIAM_M = 0.92

# Hat başına kaç tren işletilir? Uzun hatlarda gerçekte de daha sık sefer vardır; bu yüzden
# belirli uzunluk eşiklerinin üstündeki hatlara kademeli olarak daha fazla tren konur (tek bir
# "uzun/kısa" ayrımı yerine — önceden sadece 15km üstü hatlara ikinci tren konuyordu, filo
# gerçekçilik için büyütüldü). Trenler hat üzerinde birbirinden uzak noktalardan başlatılır
# (sefer aralığı/headway taklidi). Büyükten küçüğe sıralı: (min km, tren sayısı).
TREN_ESIKLERI = [(30.0, 4), (20.0, 3), (10.0, 2)]
VARSAYILAN_TREN_SAYISI = 1

# --- Canlı/sürekli akış (rayli_canli_akis_sunucu.py --kaynak canli) için segment ayarları ---
# Sabit dosya yerine sunucu bu modülü CANLI çağırır; her segment TAZE rastgele bir arıza
# senaryosu içerir (offline main()'in SEED=42'li deterministik üretiminden bağımsız, ayrı bir
# rng ile). Enjeksiyon ihtimali offline üretimdekinden (0.35) çok daha düşük tutulur — aksi
# hâlde aynı anda gerçekçi olmayan sayıda dingil arızalı görünür (bkz. CLAUDE.md, "10 dakikada
# binlerce alarm" şikâyeti). Süre alt sınırı da kısa "flicker" arızaları önler.
SEGMENT_STEPS = 300                      # bir segment = 300 tick x 2 sn = 10 dakika
SEGMENT_EK_ARIZA_IHTIMALI = 0.03
SEGMENT_DEDICATED_ORAN = 0.02            # segment başına garanti arızalı dingil oranı
SEGMENT_ARIZA_UZUNLUK_ORANI = (0.15, 0.35)   # segment uzunluğunun bu payı kadar sürer

COL_ORDER = [
    "timestamp", "line_id", "train_id", "wagon_id", "axle_id",
    "track_km", "speed_kmh", "load_ton", "lat", "lon", "next_station", "at_station",
    "vib_x_rms_g", "vib_y_rms_g", "vib_z_rms_g", "vib_peak_g", "vib_kurtosis",
    "vib_crest_factor", "vib_dom_freq_hz", "acoustic_rms", "acoustic_peak_freq_hz",
    "axle_box_temp_c", "brake_temp_c", "motor_temp_c", "ambient_temp_c",
    "motor_current_a", "motor_voltage_v", "humidity_pct", "fault_type", "fault_severity",
]

# --- Tren hareket profili (gerçekçi metro seferi) ---
MAX_HIZ_KMH = {"Metro": 80.0, "Tramvay": 45.0, "Banliyö": 90.0, "Füniküler": 30.0}
IVME_MS2 = 1.0                           # kalkış ivmesi
FREN_MS2 = 1.1                           # servis freni yavaşlaması
DURAK_BEKLEME_SN = 25                    # istasyonda bekleme
TERMINAL_BEKLEME_SN = 90                 # terminalde yön değiştirme

SEVERITY_LEVEL = {"none": 0.0, "mild": 0.3, "moderate": 0.6, "severe": 1.0}
FAULT_TYPES = ["wheel_flat", "bearing_fault", "brake_fault", "motor_fault"]


# ---------------------------------------------------------------------------
# Tren hareketi (gerçek hat üzerinde)
# ---------------------------------------------------------------------------
# Ağ genelinde kaç ray kusuru bulunur? Bakımlı bir metro ağında aynı anda çok sayıda aktif
# ray kusuru olmaz; tespit edilenler kısa sürede onarılır. Bu yüzden kusur yalnızca belirli
# uzunluğun üstündeki hatlara ve hat başına BİR tane konur (önceden hat başına 2'ye kadar
# çıkıyordu ve ağda 23 kusur oluşuyordu — bu, rail_crack'in diğer sınıflardan kat kat fazla
# alarm üretmesine yol açan gerçekçi olmayan bir yoğunluktu).
KUSURLU_HAT_MIN_KM = 10.0


def ray_kusurlari_uret(hatlar):
    """Ağ üzerinde sabit ray kusuru noktaları belirler ve hangi istasyonlar arasında
    olduklarını çözer. Tren bu noktadan her geçişinde rail_crack örüntüsü tetiklenir;
    aynı kusur tekrar tekrar tespit edilir (gerçek hayatta olduğu gibi)."""
    kusurlar = []
    for kod, hat in hatlar.items():
        uzunluk = hat["uzunluk_km"]
        if uzunluk < KUSURLU_HAT_MIN_KM:
            continue
        for i, oran in enumerate([0.42]):        # hat ortasına yakın tek kusur
            km = round(uzunluk * oran, 3)
            onceki, sonraki = hat["istasyonlar"][0], hat["istasyonlar"][-1]
            for a, b in zip(hat["istasyonlar"], hat["istasyonlar"][1:]):
                if a["km"] <= km <= b["km"]:
                    onceki, sonraki = a, b
                    break
            oran_ic = ((km - onceki["km"]) / (sonraki["km"] - onceki["km"])
                       if sonraki["km"] > onceki["km"] else 0.0)
            kusurlar.append({
                "hat": kod,
                "km": km,
                "kusur_id": f"{kod}@{km:.2f}",
                "genislik_km": 0.12,
                "siddet": "severe" if kod in ("M4", "M1A") else "moderate",
                "arasi": f"{onceki['ad']} – {sonraki['ad']}",
                "lat": round(onceki["lat"] + (sonraki["lat"] - onceki["lat"]) * oran_ic, 6),
                "lon": round(onceki["lon"] + (sonraki["lon"] - onceki["lon"]) * oran_ic, 6),
            })
    return kusurlar


def tren_hareketi(hat, n_steps, rng_local, baslangic_orani=None, baslangic_durumu=None):
    """Gerçek istasyon dizisi üzerinde bir seferin hız/konum profilini üretir.

    Dönen diziler adım bazlıdır: konum (km), hız (km/sa), yön (+1/-1), istasyonda mı,
    son geçilen ve sonraki istasyon indeksi — ve son olarak bir "bitiş durumu" dict'i
    (`{hedef_idx, yon, konum_m, hiz, bekleme}`). Bu son eleman, canlı/sürekli akışta bir
    sonraki segmentin `baslangic_durumu` olarak verilip trenin fiziksel olarak kaldığı yerden
    (konum/hız/istasyonda bekleme dahil) devam etmesini sağlar — aksi hâlde her segment
    trenleri rastgele bir noktaya "ışınlardı".

    `baslangic_durumu` verilirse `baslangic_orani`/rastgele başlangıç YOK SAYILIR.
    """
    istasyonlar = hat["istasyonlar"]
    n_ist = len(istasyonlar)
    hat_uzunluk = istasyonlar[-1]["km"]
    v_max = MAX_HIZ_KMH.get(hat["tur"], 70.0) / 3.6          # m/s

    km_arr = np.zeros(n_steps)
    hiz_arr = np.zeros(n_steps)
    yon_arr = np.ones(n_steps, dtype=int)
    duruyor_arr = np.zeros(n_steps, dtype=bool)
    sonraki_ist = np.zeros(n_steps, dtype=int)

    if baslangic_durumu is not None:
        hedef_idx = baslangic_durumu["hedef_idx"]
        yon = baslangic_durumu["yon"]
        konum_m = baslangic_durumu["konum_m"]
        hiz = baslangic_durumu["hiz"]
        bekleme = baslangic_durumu["bekleme"]
    else:
        # Başlangıç istasyonu: tek trenli hatta rastgele, çok trenli hatta hat boyunca eşit
        # aralıklı (trenler birbirinin üstünde başlamasın, sefer aralığı gerçekçi olsun).
        if baslangic_orani is None:
            # n_ist=1 (tek istasyonlu, gerçekte olmayan ama edge-case testlerinde denenen bir
            # hat) için integers(1,1) boş aralık hatası verirdi — savunmacı olarak 1'e sabitlenir.
            hedef_idx = int(rng_local.integers(1, n_ist)) if n_ist > 1 else 0
        else:
            hedef_idx = max(1, min(n_ist - 1, int(round(baslangic_orani * (n_ist - 1))) or 1))
        yon = 1
        konum_m = istasyonlar[hedef_idx - 1]["km"] * 1000.0
        hiz = 0.0
        bekleme = 0.0

    for t in range(n_steps):
        hedef_m = istasyonlar[hedef_idx]["km"] * 1000.0
        kalan = (hedef_m - konum_m) * yon

        if bekleme > 0:
            hiz = 0.0
            bekleme -= WINDOW_SEC
        else:
            # frenleme mesafesi: v^2 / (2a)
            fren_mesafe = (hiz ** 2) / (2 * FREN_MS2) if hiz > 0 else 0.0
            if kalan <= fren_mesafe + 1.0:
                hiz = max(0.0, hiz - FREN_MS2 * WINDOW_SEC)
            else:
                hiz = min(v_max, hiz + IVME_MS2 * WINDOW_SEC)
            konum_m += yon * hiz * WINDOW_SEC

            # istasyona varış
            if (hedef_m - konum_m) * yon <= 2.0:
                konum_m = hedef_m
                hiz = 0.0
                terminal = hedef_idx in (0, n_ist - 1)
                bekleme = TERMINAL_BEKLEME_SN if terminal else DURAK_BEKLEME_SN
                if terminal:
                    yon *= -1
                hedef_idx = min(max(hedef_idx + yon, 0), n_ist - 1)

        km_arr[t] = np.clip(konum_m / 1000.0, 0, hat_uzunluk)
        hiz_arr[t] = hiz * 3.6
        yon_arr[t] = yon
        duruyor_arr[t] = hiz < 0.5
        sonraki_ist[t] = hedef_idx

    bitis_durumu = {"hedef_idx": hedef_idx, "yon": yon, "konum_m": konum_m,
                    "hiz": hiz, "bekleme": bekleme}
    return km_arr, hiz_arr, yon_arr, duruyor_arr, sonraki_ist, bitis_durumu


def km_den_konuma(hat, km):
    """Hat üzerindeki km konumunu, istasyon koordinatları arasında enterpolasyonla
    gerçek enlem/boylama çevirir (harita üzerinde tren ikonu için)."""
    istasyonlar = hat["istasyonlar"]
    if km <= istasyonlar[0]["km"]:
        return istasyonlar[0]["lat"], istasyonlar[0]["lon"]
    for a, b in zip(istasyonlar, istasyonlar[1:]):
        if a["km"] <= km <= b["km"]:
            o = (km - a["km"]) / (b["km"] - a["km"]) if b["km"] > a["km"] else 0.0
            return a["lat"] + (b["lat"] - a["lat"]) * o, a["lon"] + (b["lon"] - a["lon"]) * o
    return istasyonlar[-1]["lat"], istasyonlar[-1]["lon"]


# ---------------------------------------------------------------------------
# Sensör üretimi
# ---------------------------------------------------------------------------
def beklenen_akim(speed_kmh, load_ton, ivme_ms2):
    """Sağlıklı bir çekiş motorunun o anki çalışma noktasında çekmesi BEKLENEN akım (A).

    Gerçek bir metro aracında akım sürüş dinamiğine bağlıdır: kalkışta yüksek (yükle orantılı),
    sabit hızda yalnızca yuvarlanma direncini yenecek kadar, frenlemede ise rejeneratif fren
    nedeniyle düşüktür. Model bu ilişkiyi (hız/yük özelliklerinden) öğrenip sapmayı arıza olarak
    ayırt edebilsin diye böyle kuruldu.
    """
    hizlanma = max(ivme_ms2, 0.0)
    frenleme = max(-ivme_ms2, 0.0)
    return 40.0 + 95.0 * hizlanma * (load_ton / 30.0) + 0.55 * speed_kmh - 25.0 * frenleme


def base_row(speed_kmh, load_ton, ivme_ms2=0.0, fren_aktivite=0.0):
    """Sağlıklı (normal) durum için gürültülü temel sensör değerleri.
    Titreşim/akustik büyüklükler hızla artar — duran trende titreşim yok denecek kadar azdır.

    RMS/tepe/frekans büyüklükleri (vib_*, acoustic_rms, vib_dom_freq_hz) FİZİKSEL OLARAK
    negatif olamaz; ortalaması sıfıra yakın gürültü terimleri (`rng.normal`) nadiren küçük
    negatif değerler üretebiliyordu — `max(0.0, ...)` ile kırpılır (bkz.
    `testler/test_sinyal_kalitesi.py`, bu kırpma olmadan bulunan gerçek bir kusurdu).
    `motor_current_a` BİLEREK kırpılmıyor — rejeneratif frenlemede gerçek trenlerde de negatif
    (enerji şebekeye geri veriliyor) olabilir, bu tasarım gereği."""
    hiz_faktor = speed_kmh / 80.0
    return {
        "vib_x_rms_g": max(0.0, rng.normal(0.02, 0.005) + 0.045 * hiz_faktor),
        "vib_y_rms_g": max(0.0, rng.normal(0.02, 0.005) + 0.045 * hiz_faktor),
        "vib_z_rms_g": max(0.0, rng.normal(0.03, 0.006) + 0.060 * hiz_faktor),
        "vib_peak_g": max(0.0, rng.normal(0.06, 0.012) + 0.130 * hiz_faktor),
        "vib_kurtosis": rng.normal(3.0, 0.2),
        "vib_crest_factor": rng.normal(2.8, 0.15),
        "vib_dom_freq_hz": max(0.0, rng.normal(2.0, 0.3) + 0.02 * speed_kmh),
        "acoustic_rms": max(0.0, rng.normal(0.008, 0.002) + 0.020 * hiz_faktor),
        "acoustic_peak_freq_hz": rng.normal(500, 50),
        "axle_box_temp_c": rng.normal(35, 2) + 0.05 * speed_kmh,
        # fren sıcaklığı fren kullanımıyla ısınır, sonra yavaşça soğur
        "brake_temp_c": rng.normal(40, 3) + 22.0 * fren_aktivite,
        "motor_temp_c": rng.normal(55, 4) + 0.03 * load_ton + 8.0 * max(ivme_ms2, 0.0),
        "ambient_temp_c": rng.normal(24, 1.5),
        "motor_current_a": rng.normal(beklenen_akim(speed_kmh, load_ton, ivme_ms2), 6),
        "motor_voltage_v": rng.normal(750, 5),
        "humidity_pct": rng.normal(45, 5),
    }


def apply_fault(row, fault_type, sev, speed_kmh):
    """Verilen arıza tipi ve şiddetine (0-1) göre satırı bozar."""
    if fault_type == "wheel_flat":
        # düzlük darbesi tekerlek dönüş frekansında; hız arttıkça darbe şiddeti artar
        wheel_rot_hz = max(speed_kmh, 1) / 3.6 / (np.pi * WHEEL_DIAM_M)
        hiz_kat = 0.3 + 0.7 * min(speed_kmh / 60.0, 1.0)
        row["vib_dom_freq_hz"] = max(0.0, wheel_rot_hz + rng.normal(0, 0.05))
        row["vib_crest_factor"] += sev * hiz_kat * rng.uniform(2.5, 4.0)
        row["vib_peak_g"] += sev * hiz_kat * rng.uniform(1.0, 1.8)
        row["vib_kurtosis"] += sev * hiz_kat * rng.uniform(1.5, 3.0)
    elif fault_type == "bearing_fault":
        row["vib_kurtosis"] += sev * rng.uniform(3.0, 6.0)
        row["vib_dom_freq_hz"] = rng.uniform(800, 1200)
        row["axle_box_temp_c"] += sev * rng.uniform(15, 30)
        row["vib_x_rms_g"] += sev * rng.uniform(0.05, 0.15)
    elif fault_type == "brake_fault":
        row["brake_temp_c"] += sev * rng.uniform(50, 100)
        row["motor_current_a"] += sev * rng.uniform(3, 8)
    elif fault_type == "motor_fault":
        # Motor arızası, o anki ÇALIŞMA NOKTASINA göre orantısal bir akım sapmasıdır
        # (sargı dengesizliği / sürücü arızası): sabit bir offset değil, beklenenin %25-55'i
        # kadar sapma. Böylece hem duran hem seyir hâlindeki araçta tespit edilebilir kalır.
        row["motor_current_a"] *= 1 + sev * rng.choice([-1, 1]) * rng.uniform(0.25, 0.55)
        row["motor_voltage_v"] -= sev * rng.uniform(15, 35)
        row["motor_temp_c"] += sev * rng.uniform(15, 35)
    return row


def severity_at(step, fault_start, fault_len):
    """mild -> moderate -> severe -> (onarım varsayımıyla) normale dönüş üçgen profili.

    `fault_len<=0` normalde üretilmez (segment/offline üretimde f_len her zaman pozitif
    hesaplanır) ama savunmacı bir asgari değer uygulanır — çok küçük `n_steps` (test/edge-case)
    ile çağrıldığında sıfıra bölme çökmesini önler."""
    fault_len = max(1, fault_len)
    rel = (step - fault_start) / fault_len
    if rel < 0.5:
        return min(1.0, rel * 2)
    return max(0.0, 1 - (rel - 0.5) * 2)


def severity_label(sev_value):
    if sev_value < 0.15:
        return "none"
    if sev_value < 0.45:
        return "mild"
    if sev_value < 0.8:
        return "moderate"
    return "severe"


# ---------------------------------------------------------------------------
# Seri (dingil) listesi ve arıza bölümleri
# ---------------------------------------------------------------------------
def hat_tren_sayisi(hat):
    """Bir hatta kaç tren işletileceği — kademeli eşik tablosuna (`TREN_ESIKLERI`) göre."""
    uzunluk = hat["uzunluk_km"]
    for esik_km, sayi in TREN_ESIKLERI:
        if uzunluk >= esik_km:
            return sayi
    return VARSAYILAN_TREN_SAYISI


def build_series_list(hatlar):
    """Her simülasyon hattına bir veya daha fazla tren; her trene 2 vagon x 2 dingil."""
    series = []
    for kod in ag.SIMULASYON_HATLARI:
        if kod not in hatlar:
            continue
        for tren_no in range(1, hat_tren_sayisi(hatlar[kod]) + 1):
            train_id = f"{kod}-{tren_no:02d}"
            for wagon in range(1, WAGONS_PER_TRAIN + 1):
                for axle in range(1, AXLES_PER_WAGON + 1):
                    series.append((kod, train_id, f"V{wagon}", f"A{axle}"))
    return series


def make_dedicated_episodes(series_list):
    """Her arıza tipi için hem train hem test zaman diliminde garanti örnek üretecek
    şekilde (start, len, type) bölümleri atar.

    Bölüm sayısı seri (dingil) sayısıyla ORANTILIDIR — yeni hat/tren eklendiğinde arıza
    yoğunluğu sabit kalsın, sınıf dengesi bozulmasın diye.
    """
    dedicated = {s: [] for s in series_list}
    idx_pool = list(range(len(series_list)))
    rng.shuffle(idx_pool)
    ptr = 0
    n_seri = len(series_list)
    train_bolum = max(2, round(n_seri * 0.125))   # 32 dingilde 4 idi -> aynı yoğunluk
    test_bolum = max(2, round(n_seri * 0.094))    # 32 dingilde 3 idi
    for f_type in FAULT_TYPES:
        for _ in range(train_bolum):      # train zaman diliminde
            s = series_list[idx_pool[ptr % len(idx_pool)]]
            ptr += 1
            f_len = int(N_STEPS * rng.uniform(0.10, 0.18))
            f_start = int(rng.integers(0, int(N_STEPS * 0.5) - f_len))
            dedicated[s].append((f_start, f_len, f_type))
        for _ in range(test_bolum):      # test zaman diliminde (split noktasından sonra)
            s = series_list[idx_pool[ptr % len(idx_pool)]]
            ptr += 1
            f_len = int(N_STEPS * rng.uniform(0.05, 0.10))
            latest_start = N_STEPS - f_len - 1
            earliest_start = int(N_STEPS * TRAIN_TEST_SPLIT_FRAC) + 2
            f_start = int(rng.integers(earliest_start, max(earliest_start + 1, latest_start)))
            dedicated[s].append((f_start, f_len, f_type))
    return dedicated


def generate_series(hat, train_id, wagon_id, axle_id, forced_episodes, hareket, kusurlar,
                    n_steps=None, baslangic_zamani=None, ek_ariza_ihtimali=0.35):
    """Bir dingil için tüm zaman serisini üretir. Hareket (konum/hız) tren geneliyle paylaşılır.

    `n_steps`/`baslangic_zamani` verilmezse offline üretimin (main()) global sabitleri
    (`N_STEPS`/`START_TIME`) kullanılır — mevcut davranış değişmez. Canlı/sürekli akış
    (`bir_segment_uret`) kendi segment uzunluğunu ve o anki segment saatini geçirir.
    `hareket` 5 (eski) veya 6 (bitiş durumu dahil, `tren_hareketi`'nin güncel dönüşü) elemanlı
    olabilir — burada yalnızca ilk 5'i kullanılır.
    """
    n_steps = n_steps or N_STEPS
    baslangic_zamani = baslangic_zamani or START_TIME
    km_arr, hiz_arr, yon_arr, duruyor_arr, sonraki_ist = hareket[:5]
    istasyonlar = hat["istasyonlar"]
    hat_kusurlari = [k for k in kusurlar if k["hat"] == hat["kod"]]

    rows = []
    episodes = list(forced_episodes)
    if rng.random() < ek_ariza_ihtimali:
        f_type = rng.choice(FAULT_TYPES)
        f_len = int(n_steps * rng.uniform(0.08, 0.20))
        f_start = int(rng.integers(0, max(1, n_steps - f_len)))
        episodes.append((f_start, f_len, f_type))

    # vagon yükü: yolcu yüküne göre sefer boyunca yavaşça değişir
    temel_yuk = rng.uniform(20, 40)

    # ivme (m/s²) ve fren aktivitesi: hız profilinin türevinden — sürüş dinamiğini sensörlere
    # bağlamak için (kalkışta akım/motor sıcaklığı artar, frenlemede fren sıcaklığı yükselir)
    ivme_arr = np.gradient(hiz_arr / 3.6, WINDOW_SEC)
    fren_arr = np.clip(-ivme_arr / FREN_MS2, 0, 1)
    # frenden sonra sıcaklık bir süre yüksek kalır (üstel sönüm)
    fren_aktivite = np.zeros_like(fren_arr)
    birikim = 0.0
    for i, f in enumerate(fren_arr):
        birikim = max(f, birikim * 0.88)
        fren_aktivite[i] = birikim

    for step in range(n_steps):
        speed = float(hiz_arr[step])
        track_km = float(km_arr[step])
        load_ton = temel_yuk + 4.0 * np.sin(step / 180.0) + rng.normal(0, 0.4)
        ts = baslangic_zamani + timedelta(seconds=step * WINDOW_SEC)

        row = base_row(speed, load_ton, float(ivme_arr[step]), float(fren_aktivite[step]))

        active_fault = "normal"
        sev_val = 0.0
        for f_start, f_len, f_type in episodes:
            if f_start <= step < f_start + f_len:
                sev_val = severity_at(step, f_start, f_len)
                if sev_val > 0.1:
                    row = apply_fault(row, f_type, sev_val, speed)
                    active_fault = f_type
                break

        # Gerçek hat üzerindeki sabit ray kusuru noktasından geçiş (her seferde tekrar eder)
        for kusur in hat_kusurlari:
            if abs(track_km - kusur["km"]) <= kusur["genislik_km"] and speed > 5:
                site_sev = SEVERITY_LEVEL[kusur["siddet"]] * min(speed / 50.0, 1.0)
                row["acoustic_rms"] += site_sev * rng.uniform(0.08, 0.2)
                row["vib_peak_g"] += site_sev * rng.uniform(0.5, 1.2)
                row["acoustic_peak_freq_hz"] += site_sev * rng.uniform(800, 1500)
                if active_fault == "normal":
                    active_fault = "rail_crack"
                    sev_val = site_sev

        lat, lon = km_den_konuma(hat, track_km)
        idx = int(sonraki_ist[step])
        row.update({
            "timestamp": ts.isoformat(),
            "line_id": hat["kod"],
            "train_id": train_id,
            "wagon_id": wagon_id,
            "axle_id": axle_id,
            "track_km": round(track_km, 3),
            "speed_kmh": round(speed, 1),
            "load_ton": round(load_ton, 1),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "next_station": istasyonlar[idx]["ad"],
            "at_station": bool(duruyor_arr[step]),
            "fault_type": active_fault,
            "fault_severity": severity_label(sev_val),
        })
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Canlı/sürekli akış — segment üretimi (rayli_canli_akis_sunucu.py --kaynak canli)
# ---------------------------------------------------------------------------
def segment_dedicated_episodes(series_list, rng_local, n_steps,
                                hedef_oran=SEGMENT_DEDICATED_ORAN,
                                uzunluk_araligi=SEGMENT_ARIZA_UZUNLUK_ORANI):
    """`make_dedicated_episodes()`'in segment-ölçekli kardeşi: train/test zaman dilimi ayrımı
    yoktur (segmentin tamamı "canlı"dır), oran çok daha düşüktür (gerçekçi arıza sıklığı için
    — bkz. modül başındaki `SEGMENT_*` sabitleri) ve süre segmentin görece büyük bir payını
    kaplar (kısa "flicker" arızalar yerine birkaç dakika sürüp fark edilebilir arızalar)."""
    dedicated = {s: [] for s in series_list}
    n_seri = len(series_list)
    n_bolum = max(1, round(n_seri * hedef_oran))
    idx_pool = list(range(n_seri))
    rng_local.shuffle(idx_pool)
    for i in range(min(n_bolum, n_seri)):
        s = series_list[idx_pool[i]]
        f_type = rng_local.choice(FAULT_TYPES)
        f_len = min(int(n_steps * rng_local.uniform(*uzunluk_araligi)), n_steps - 1)
        f_start = int(rng_local.integers(0, max(1, n_steps - f_len)))
        dedicated[s].append((f_start, f_len, f_type))
    return dedicated


def bir_segment_uret(hatlar, rng_local, baslangic_zamani, hareket_durumlari, kusurlar,
                      n_steps=SEGMENT_STEPS):
    """Canlı/sürekli akış modu için bir segment (varsayılan 300 tick = 10 dk) sentetik veri
    üretir. `hareket_durumlari` (önceki segmentin `tren_hareketi` bitiş durumları, train_id'ye
    göre) `None` ise (ilk segment) trenler rastgele/eşit-aralıklı başlar; sonraki çağrılarda
    her tren bir önceki segmentin bittiği fiziksel konum/hız/bekleme durumundan devam eder —
    "ışınlanmaz". Arıza senaryosu HER ÇAĞRIDA taze rastgele seçilir: offline `main()`'in
    SEED=42'li deterministik `rng`'si değil, çağıranın verdiği (seedsiz) `rng_local` kullanılır
    — bu yüzden her segment farklıdır, aynı script asla tekrar etmez.

    Döner: `(segment_df, yeni_hareket_durumlari)`.
    """
    series_list = build_series_list(hatlar)
    dedicated = segment_dedicated_episodes(series_list, rng_local, n_steps)

    hat_tren_listesi = {}
    for kod, train_id, _, _ in series_list:
        if train_id not in hat_tren_listesi.setdefault(kod, []):
            hat_tren_listesi[kod].append(train_id)

    hareketler = {}
    yeni_durumlar = {}
    for kod, trenler in hat_tren_listesi.items():
        for i, train_id in enumerate(trenler):
            onceki_durum = (hareket_durumlari or {}).get(train_id)
            oran = None if (onceki_durum is not None or len(trenler) == 1) else (i + 0.5) / len(trenler)
            sonuc = tren_hareketi(hatlar[kod], n_steps, rng_local, baslangic_orani=oran,
                                  baslangic_durumu=onceki_durum)
            hareketler[train_id] = sonuc[:5]
            yeni_durumlar[train_id] = sonuc[5]

    rows = []
    for s in series_list:
        kod, train_id, wagon_id, axle_id = s
        rows.extend(generate_series(hatlar[kod], train_id, wagon_id, axle_id,
                                    dedicated[s], hareketler[train_id], kusurlar,
                                    n_steps=n_steps, baslangic_zamani=baslangic_zamani,
                                    ek_ariza_ihtimali=SEGMENT_EK_ARIZA_IHTIMALI))

    df = pd.DataFrame(rows)[COL_ORDER]
    float_cols = df.select_dtypes(include=[float]).columns
    df[float_cols] = df[float_cols].round(4)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "train_id", "wagon_id", "axle_id"]).reset_index(drop=True)
    return df, yeni_durumlar


def main():
    agac = ag.yukle()
    hatlar = agac["hatlar"]

    kusurlar = ray_kusurlari_uret({k: hatlar[k] for k in ag.SIMULASYON_HATLARI if k in hatlar})
    with open(os.path.join(DATA_DIR, "ray_kusur_noktalari.json"), "w", encoding="utf-8") as f:
        json.dump(kusurlar, f, ensure_ascii=False, indent=2)

    series_list = build_series_list(hatlar)
    dedicated = make_dedicated_episodes(series_list)

    # Aynı trenin tüm dingilleri aynı hareketi paylaşır (aynı araç!)
    hareketler = {}
    hat_tren_listesi = {}
    for kod, train_id, _, _ in series_list:
        hat_tren_listesi.setdefault(kod, [])
        if train_id not in hat_tren_listesi[kod]:
            hat_tren_listesi[kod].append(train_id)
    for kod, trenler in hat_tren_listesi.items():
        for i, train_id in enumerate(trenler):
            oran = None if len(trenler) == 1 else (i + 0.5) / len(trenler)
            hareketler[train_id] = tren_hareketi(hatlar[kod], N_STEPS, rng, oran)

    all_rows = []
    for s in series_list:
        kod, train_id, wagon_id, axle_id = s
        all_rows.extend(generate_series(hatlar[kod], train_id, wagon_id, axle_id,
                                        dedicated[s], hareketler[train_id], kusurlar))

    df = pd.DataFrame(all_rows)
    df = df[COL_ORDER]

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

    cok_trenli = [f"{k}({hat_tren_sayisi(hatlar[k])})" for k in ag.SIMULASYON_HATLARI
                  if k in hatlar and hat_tren_sayisi(hatlar[k]) > 1]
    print(f"Ağ: {len(ag.SIMULASYON_HATLARI)} hat | tren: {len(hareketler)} | dingil: {len(series_list)}")
    print(f"Çok trenli hatlar (kademeli eşik {TREN_ESIKLERI}): {', '.join(cok_trenli)}")
    hat_ozet = ", ".join("{} ({})".format(k, hatlar[k]["kisa_ad"])
                         for k in ag.SIMULASYON_HATLARI if k in hatlar)
    print(f"Hatlar: {hat_ozet}")
    print(f"Ray kusuru noktası: {len(kusurlar)}")
    for k in kusurlar:
        print(f"  {k['hat']:4s} km {k['km']:6.2f}  ({k['siddet']:8s})  {k['arasi']}")
    print(f"\nToplam satır: {len(df)}  |  seri sayısı: {len(series_list)}  |  seri başına adım: {N_STEPS}")
    print(f"Train satır : {len(train_df)}  ({train_df['timestamp'].min()} -> {train_df['timestamp'].max()})")
    print(f"Test satır  : {len(test_df)}  ({test_df['timestamp'].min()} -> {test_df['timestamp'].max()})")
    print(f"Hız aralığı : {df['speed_kmh'].min():.1f} - {df['speed_kmh'].max():.1f} km/sa "
          f"(duran: %{100 * (df['speed_kmh'] < 0.5).mean():.1f})")
    print("\nGenel sınıf dağılımı (fault_type):")
    print(df["fault_type"].value_counts())
    print("\nŞiddet dağılımı (fault_severity):")
    print(df["fault_severity"].value_counts())
    print("\nTrain sınıf dağılımı:")
    print(train_df["fault_type"].value_counts())
    print("\nTest sınıf dağılımı:")
    print(test_df["fault_type"].value_counts())
    print("\nEksik değer sayısı (toplam):", df.isna().sum().sum())
    missing_in_train = set(df["fault_type"].unique()) - set(train_df["fault_type"].unique())
    missing_in_test = set(df["fault_type"].unique()) - set(test_df["fault_type"].unique())
    print("Train'de eksik sınıf:", missing_in_train or "yok")
    print("Test'te eksik sınıf :", missing_in_test or "yok")


if __name__ == "__main__":
    main()
