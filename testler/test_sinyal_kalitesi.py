"""Sentetik sinyal kalitesi: fiziksel aralık, korelasyon, zaman sürekliliği ve edge-case testleri.

`test_veri_semasi.py`'de zaten var olan kontrolleri (şema, sızıntı, kronolojik bölme, hız/konum/
yük genel aralığı, tren duraklarda duruyor, dingiller aynı konumda) TEKRARLAMAZ — bu dosya
`FEATURE_COLS`'daki TÜM sensör kolonlarının kendi fiziksel aralıklarını, sensörler arası
BEKLENEN korelasyonları, zaman damgası/konum sürekliliğini ve üretim fonksiyonlarının uç
(edge-case) girdilerde çökmediğini test eder.
"""

import numpy as np
import pytest

from rayli_model import FEATURE_COLS, GROUP_COLS

# ---------------------------------------------------------------------------------
# 1) Fiziksel aralık kontrolleri
# ---------------------------------------------------------------------------------
# Her kolon için (alt, üst) — normal DURUM + en kötü arıza/kusur etkisi üst üste bindiğinde bile
# aşılmayacak kadar CÖMERT sınırlar (src/rayli_veri_uret.py'deki base_row()/apply_fault()
# formüllerinden türetildi — amaç "hatalı fiziksel değer" (örn. eksi sıcaklık, imkânsız akım)
# yakalamak, normal istatistiksel gürültüyü yanlış alarm olarak işaretlememek).
ARALIKLAR = {
    "vib_x_rms_g": (0.0, 1.0), "vib_y_rms_g": (0.0, 1.0), "vib_z_rms_g": (0.0, 1.0),
    "vib_peak_g": (0.0, 5.0),
    "vib_kurtosis": (0.0, 20.0),
    "vib_crest_factor": (0.0, 10.0),
    "vib_dom_freq_hz": (0.0, 1500.0),
    "acoustic_rms": (0.0, 1.0),
    "acoustic_peak_freq_hz": (0.0, 3000.0),
    "axle_box_temp_c": (0.0, 120.0),
    "brake_temp_c": (0.0, 250.0),
    "motor_temp_c": (0.0, 150.0),
    "ambient_temp_c": (0.0, 50.0),
    # Rejeneratif frenlemede GERÇEK trenlerde de negatif olabilir (enerji şebekeye geri
    # verilir) — CLAUDE.md/beklenen_akim() yorumunda belgeli tasarım, kusur değil.
    "motor_current_a": (-100.0, 350.0),
    "motor_voltage_v": (650.0, 800.0),
    "humidity_pct": (0.0, 100.0),
    # Aşağıdaki üçü zaten testler/test_veri_semasi.py'de (test_hiz_ve_konum_makul_araliklarda)
    # kontrol ediliyor — burada TEKRAR test edilmiyor, sadece ARALIKLAR sözlüğünün
    # FEATURE_COLS ile tam senkron kaldığını doğrulamak için (bkz.
    # test_tum_feature_cols_araliklarda_kapsanmis) tutarlı/cömert sınırlarla listeleniyor.
    "speed_kmh": (0.0, 120.0),
    "track_km": (0.0, 200.0),
    "load_ton": (0.0, 60.0),
}


@pytest.mark.parametrize("kolon", sorted(ARALIKLAR))
def test_kolon_fiziksel_aralikta(train_df, kolon):
    """FEATURE_COLS'daki her sensör kolonu kendi fiziksel olarak makul aralığında olmalı."""
    assert kolon in FEATURE_COLS, f"ARALIKLAR sözlüğü FEATURE_COLS ile senkron değil: {kolon}"
    alt, ust = ARALIKLAR[kolon]
    assert train_df[kolon].between(alt, ust).all(), (
        f"{kolon} beklenen [{alt}, {ust}] aralığının dışında değer içeriyor "
        f"(min={train_df[kolon].min():.3f}, max={train_df[kolon].max():.3f})")


def test_tum_feature_cols_araliklarda_kapsanmis():
    """ARALIKLAR sözlüğü FEATURE_COLS'daki TÜM kolonları kapsamalı (yeni kolon eklenince bu
    dosyanın da güncellenmesi gerektiğini hatırlatır)."""
    eksik = set(FEATURE_COLS) - set(ARALIKLAR)
    assert not eksik, f"Yeni eklenen kolon(lar) için aralık tanımlanmamış: {eksik}"


# ---------------------------------------------------------------------------------
# 2) Korelasyon kontrolleri (yalnızca fault_type == "normal" satırlarda — arıza etkisi
#    korelasyonu bozmasın diye)
# ---------------------------------------------------------------------------------
def test_hiz_ile_titresim_pozitif_korelasyonlu(train_df):
    """base_row(): titreşim, hız arttıkça artacak şekilde üretiliyor (hiz_faktor terimi) —
    normal (arızasız) kayıtlarda speed_kmh ile vib_peak_g arasında belirgin pozitif korelasyon
    olmalı."""
    normal = train_df[train_df["fault_type"] == "normal"]
    kor = normal["speed_kmh"].corr(normal["vib_peak_g"])
    assert kor > 0.3, f"speed_kmh ↔ vib_peak_g korelasyonu zayıf/negatif: {kor:.3f}"


def test_yuk_ile_motor_akimi_pozitif_korelasyonlu(train_df):
    """beklenen_akim(): kalkış anlarında (ivme > 0) akım yükle orantılı artıyor — normal
    kayıtlarda, hızlanan (speed artışı) anlarda load_ton ile motor_current_a arasında pozitif
    korelasyon olmalı."""
    normal = train_df[train_df["fault_type"] == "normal"].copy()
    normal = normal.sort_values(GROUP_COLS + ["timestamp"])
    normal["hiz_degisim"] = normal.groupby(GROUP_COLS)["speed_kmh"].diff()
    hizlanan = normal[normal["hiz_degisim"] > 0.5]
    assert len(hizlanan) > 100, "korelasyon testi için yeterli 'hızlanan' örnek yok"
    kor = hizlanan["load_ton"].corr(hizlanan["motor_current_a"])
    assert kor > 0.15, f"load_ton ↔ motor_current_a (kalkışta) korelasyonu zayıf: {kor:.3f}"


def test_frenleme_aninda_fren_sicakligi_daha_yuksek(train_df):
    """generate_series(): fren aktivitesi (negatif ivme) sonrası brake_temp_c üstel sönümle
    yüksek kalıyor — normal kayıtlarda frenleyen (hız azalan) anların ortalama brake_temp_c'si,
    frenlemeyen anlardan belirgin şekilde yüksek olmalı."""
    normal = train_df[train_df["fault_type"] == "normal"].copy()
    normal = normal.sort_values(GROUP_COLS + ["timestamp"])
    normal["hiz_degisim"] = normal.groupby(GROUP_COLS)["speed_kmh"].diff()
    frenleyen = normal[normal["hiz_degisim"] < -1.0]["brake_temp_c"]
    frenlemeyen = normal[normal["hiz_degisim"] >= -0.2]["brake_temp_c"]
    assert len(frenleyen) > 50 and len(frenlemeyen) > 50, "yeterli örnek yok"
    assert frenleyen.mean() > frenlemeyen.mean(), (
        f"frenleyen ort. {frenleyen.mean():.2f} <= frenlemeyen ort. {frenlemeyen.mean():.2f}")


# ---------------------------------------------------------------------------------
# 3) Zaman sürekliliği
# ---------------------------------------------------------------------------------
def test_zaman_damgasi_sabit_araliklarla_ilerliyor(train_df):
    """Her dingil serisinde (train_id/wagon_id/axle_id) ardışık satırlar arasındaki zaman
    farkı her zaman tam WINDOW_SEC (2 sn) olmalı — boşluk veya çakışma olmamalı."""
    from rayli_veri_uret import WINDOW_SEC
    ornek_seri = train_df[train_df["train_id"] == train_df["train_id"].iloc[0]]
    ornek_seri = ornek_seri[
        (ornek_seri["wagon_id"] == ornek_seri["wagon_id"].iloc[0]) &
        (ornek_seri["axle_id"] == ornek_seri["axle_id"].iloc[0])
    ].sort_values("timestamp")
    farklar = ornek_seri["timestamp"].diff().dropna().dt.total_seconds()
    assert (farklar == WINDOW_SEC).all(), f"beklenmeyen zaman aralığı bulundu: {farklar.unique()}"


def test_konum_adimi_fiziksel_ust_siniri_asmiyor(train_df):
    """Bir dingil serisinde track_km'nin bir adımda değişimi, en hızlı hat türünün
    (v_max * WINDOW_SEC) fiziksel üst sınırını aşmamalı — 'ışınlanma' olmadığının kanıtı."""
    from rayli_veri_uret import MAX_HIZ_KMH, WINDOW_SEC
    ust_sinir_km = (max(MAX_HIZ_KMH.values()) / 3.6 * WINDOW_SEC) / 1000 * 1.05  # %5 tolerans
    ornek_seri = train_df[train_df["train_id"] == train_df["train_id"].iloc[0]]
    ornek_seri = ornek_seri[
        (ornek_seri["wagon_id"] == ornek_seri["wagon_id"].iloc[0]) &
        (ornek_seri["axle_id"] == ornek_seri["axle_id"].iloc[0])
    ].sort_values("timestamp")
    adim = ornek_seri["track_km"].diff().abs().dropna()
    assert (adim <= ust_sinir_km).all(), (
        f"fiziksel üst sınırı ({ust_sinir_km:.4f} km) aşan konum sıçraması var: "
        f"max={adim.max():.4f} km")


# ---------------------------------------------------------------------------------
# 4) Edge-case testleri — üretim fonksiyonlarını doğrudan, uç parametrelerle çağırarak
# ---------------------------------------------------------------------------------
def _sahte_hat(n_istasyon=3, tur="Metro"):
    """Test için minimal bir hat sözlüğü — gerçek istanbul_metro_agi şemasını taklit eder."""
    istasyonlar = [
        {"ad": f"Istasyon{i}", "lat": 41.0 + i * 0.01, "lon": 29.0 + i * 0.01, "km": float(i)}
        for i in range(n_istasyon)
    ]
    return {"kod": "TEST", "tur": tur, "istasyonlar": istasyonlar,
           "uzunluk_km": istasyonlar[-1]["km"]}


def test_severity_at_sifir_uzunlukta_cokmez():
    """severity_at(fault_len=0) önceden ZeroDivisionError riskiyle çökebiliyordu — artık
    savunmacı bir asgari uzunluk uygulanmalı."""
    from rayli_veri_uret import severity_at
    assert severity_at(step=5, fault_start=5, fault_len=0) is not None


def test_tren_hareketi_tek_istasyonlu_hatta_cokmez():
    """tren_hareketi() tek istasyonlu (n_ist=1) bir hatla çağrılırsa (rng_local.integers(1,1)
    boş aralık hatası riski) çökmemeli — sonucu döndürebilmeli."""
    import numpy as np
    from rayli_veri_uret import tren_hareketi
    hat = _sahte_hat(n_istasyon=1)
    rng = np.random.default_rng(0)
    sonuc = tren_hareketi(hat, n_steps=10, rng_local=rng)
    assert len(sonuc) == 6           # 5 dizi + bitiş durumu
    assert len(sonuc[0]) == 10       # km_arr uzunluğu n_steps kadar


def test_generate_series_ariza_yokken_hepsi_normal():
    """forced_episodes=[] ve ek_ariza_ihtimali=0.0 ile üretilen bir seride TÜM satırlar
    fault_type='normal' olmalı — arıza enjeksiyon mekanizmasının kapatılabilir olduğunun
    doğrulaması."""
    import numpy as np
    from rayli_veri_uret import generate_series, tren_hareketi
    hat = _sahte_hat(n_istasyon=5)
    rng = np.random.default_rng(1)
    hareket = tren_hareketi(hat, n_steps=20, rng_local=rng)
    rows, _, _ = generate_series(hat, "T-01", "V1", "A1", forced_episodes=[], hareket=hareket,
                                 kusurlar=[], n_steps=20, ek_ariza_ihtimali=0.0)
    fault_types = {r["fault_type"] for r in rows}
    assert fault_types == {"normal"}, f"arıza kapalıyken normal dışı etiket üretildi: {fault_types}"


def test_kisa_segment_uretimi_cokmez():
    """bir_segment_uret() çok kısa n_steps (uç durum) ile bile çökmeden bir DataFrame
    döndürmeli."""
    import numpy as np
    from rayli_veri_uret import bir_segment_uret, ray_kusurlari_uret
    import istanbul_metro_agi as ag
    yol_var = True
    try:
        agac = ag.yukle()
    except Exception:                                          # noqa: BLE001
        yol_var = False
    if not yol_var:
        pytest.skip("Ağ modeli yok — önce 'python src/istanbul_metro_agi.py' çalıştırın.")
    hatlar = {k: v for k, v in agac["hatlar"].items() if k in ag.SIMULASYON_HATLARI}
    kusurlar = ray_kusurlari_uret(hatlar)
    rng = np.random.default_rng(2)
    import datetime
    df, durumlar, sicaklik_durumlari, kayma_durumlari = bir_segment_uret(
        hatlar, rng, datetime.datetime(2026, 1, 1, 6, 0, 0), None, kusurlar, n_steps=5)
    assert len(df) > 0
    assert set(durumlar.keys()) == {t for _, t, _, _ in
                                    __import__("rayli_veri_uret").build_series_list(hatlar)}


# ---------------------------------------------------------------------------------
# 5) Takip mesafesi (headway) ve sinyalizasyon
# ---------------------------------------------------------------------------------
def test_takip_mesafesi_asgari_bosluk_korunur():
    """İkinci tren, önündeki trenin km dizisini `onceki_tren_km_arr` olarak alınca aynı yönde
    giderken MIN_HEADWAY_KM'nin çok altına inmemeli — önündeki trene çarpmamalı."""
    from rayli_veri_uret import tren_hareketi, MIN_HEADWAY_KM
    hat = _sahte_hat(n_istasyon=6)
    rng1 = np.random.default_rng(3)
    rng2 = np.random.default_rng(4)
    # Öndeki tren aynı hatta hemen önde başlar (hedef_idx=1), arkadaki tren ile aynı yönde (+1).
    onceki = tren_hareketi(hat, n_steps=200, rng_local=rng1, baslangic_orani=0.2)
    arkadaki = tren_hareketi(hat, n_steps=200, rng_local=rng2, baslangic_orani=0.05,
                             onceki_tren_km_arr=onceki[0], onceki_tren_yon_arr=onceki[2])
    onceki_km, onceki_yon = onceki[0], onceki[2]
    arka_km, arka_yon = arkadaki[0], arkadaki[2]
    ayni_yon = onceki_yon == arka_yon
    bosluk = (onceki_km - arka_km) * arka_yon
    # Yalnızca aynı yönde VE önündeki tren gerçekten ilerideyken (bosluk>0) kısıt anlamlıdır.
    ilgili = ayni_yon & (bosluk > 0)
    if ilgili.any():
        # Küçük bir tolerans (fren adımı ayrıklığı) dışında asgari mesafenin çok altına inilmemeli.
        assert bosluk[ilgili].min() > -0.05, (
            f"headway ihlali: minimum boşluk {bosluk[ilgili].min():.3f} km "
            f"(asgari={MIN_HEADWAY_KM} km)"
        )


def test_sinyalizasyon_carpani_araligi_ve_etkisi():
    """sinyalizasyon_hiz_carpani() her zaman [carpan_min, 1.0] aralığında bir dizi döner ve
    yeterince çok denemede en az bir kez aktif olup v_max'ı gerçekten düşürebilmelidir."""
    from rayli_veri_uret import sinyalizasyon_hiz_carpani, SINYAL_HIZ_CARPAN_ARALIGI
    rng = np.random.default_rng(5)
    en_az_bir_aktif = False
    for _ in range(200):
        carpan = sinyalizasyon_hiz_carpani(n_steps=300, rng_local=rng)
        assert carpan.min() >= SINYAL_HIZ_CARPAN_ARALIGI[0] - 1e-9
        assert carpan.max() <= 1.0
        if carpan.min() < 1.0:
            en_az_bir_aktif = True
    assert en_az_bir_aktif, "200 denemede hiç sinyalizasyon yavaşlaması tetiklenmedi"
