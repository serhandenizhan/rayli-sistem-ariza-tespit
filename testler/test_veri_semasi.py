"""Veri seti şeması, bütünlüğü ve SIZINTI (leakage) korumaları için testler."""

import numpy as np
import pytest

from rayli_model import FEATURE_COLS

ETIKET_KOLONLARI = ["fault_type", "fault_severity"]
BEKLENEN_SINIFLAR = {"normal", "wheel_flat", "bearing_fault", "brake_fault", "motor_fault", "rail_crack"}


def test_train_test_kolonlari_ayni(train_df, test_df):
    """Train ve test setleri birebir aynı kolon şemasına sahip olmalı."""
    assert list(train_df.columns) == list(test_df.columns)


def test_ozellik_kolonlari_mevcut_ve_sayisal(train_df):
    """Modelin kullandığı tüm FEATURE_COLS kolonları veride var ve sayısal olmalı."""
    for kolon in FEATURE_COLS:
        assert kolon in train_df.columns, f"eksik özellik kolonu: {kolon}"
        assert np.issubdtype(train_df[kolon].dtype, np.number), f"sayısal değil: {kolon}"


def test_eksik_deger_yok(train_df, test_df):
    """Veri setlerinde hiç eksik (NaN) değer bulunmamalı."""
    assert train_df.isna().sum().sum() == 0
    assert test_df.isna().sum().sum() == 0


def test_train_test_kronolojik_ayrilmis(train_df, test_df):
    """Train/test bölmesi kronolojik olmalı: test verisi train'in tamamından SONRA başlar
    (rastgele bölme veri sızıntısına yol açardı)."""
    assert train_df["timestamp"].max() < test_df["timestamp"].min()


def test_tum_siniflar_her_iki_sette_var(train_df, test_df):
    """6 arıza sınıfının tamamı hem train hem test setinde temsil edilmeli."""
    assert set(train_df["fault_type"]) == BEKLENEN_SINIFLAR
    assert set(test_df["fault_type"]) == BEKLENEN_SINIFLAR


def test_siddet_etiketi_ozellik_degil():
    """fault_severity hedef değişkenle ilişkili olduğu için model girdisi (feature) OLMAMALI."""
    assert "fault_severity" not in FEATURE_COLS
    assert "fault_type" not in FEATURE_COLS


def test_akis_verisinde_etiket_yok(akis_df):
    """SIZINTI KORUMASI: canlı akışa verilen dosyada etiket kolonu kesinlikle bulunmamalı."""
    for kolon in ETIKET_KOLONLARI:
        assert kolon not in akis_df.columns, f"akış verisinde etiket sızıntısı: {kolon}"


def test_cevap_anahtari_akisla_eslesiyor(akis_df, cevap_anahtari):
    """Cevap anahtarı, akış verisiyle sample_id üzerinden birebir eşleşmeli."""
    assert len(akis_df) == len(cevap_anahtari)
    assert set(akis_df["sample_id"]) == set(cevap_anahtari["sample_id"])
    assert cevap_anahtari["sample_id"].is_unique


def test_cevap_anahtari_siniflari_gecerli(cevap_anahtari):
    """Cevap anahtarındaki tüm etiketler bilinen sınıflardan olmalı."""
    assert set(cevap_anahtari["fault_type"]) <= BEKLENEN_SINIFLAR
    assert set(cevap_anahtari["fault_severity"]) <= {"none", "mild", "moderate", "severe"}


def test_normal_kayitlarin_siddeti_none(train_df):
    """Arızasız (normal) kayıtların şiddeti 'none' olmalı — etiket tutarlılığı."""
    normaller = train_df[train_df["fault_type"] == "normal"]
    assert (normaller["fault_severity"] == "none").all()


def test_hiz_ve_konum_makul_araliklarda(train_df):
    """Fiziksel akıl kontrolü: hız 0-120 km/sa, konum hat uzunluğu içinde, yük pozitif."""
    assert train_df["speed_kmh"].between(0, 120).all()
    assert train_df["track_km"].ge(0).all()
    assert train_df["load_ton"].gt(0).all()


def test_tren_duraklarda_duruyor(train_df):
    """Gerçekçilik kontrolü: trenler istasyonlarda duruyor olmalı (hızın bir kısmı ~0)."""
    duran_oran = (train_df["speed_kmh"] < 0.5).mean()
    assert 0.05 < duran_oran < 0.6, f"duran zaman oranı gerçekçi değil: {duran_oran:.2f}"


def test_ayni_trenin_dingilleri_ayni_konumda(train_df):
    """Aynı trene ait tüm dingiller aynı anda aynı konumda olmalı (tek araç)."""
    ornek = train_df[train_df["train_id"] == train_df["train_id"].iloc[0]]
    ilk_an = ornek[ornek["timestamp"] == ornek["timestamp"].iloc[0]]
    assert ilk_an["track_km"].nunique() == 1
    assert ilk_an["speed_kmh"].nunique() == 1


@pytest.mark.parametrize("kolon", ["line_id", "train_id", "wagon_id", "axle_id", "next_station"])
def test_metro_ag_kolonlari_var(train_df, kolon):
    """Gerçek metro ağı bağlamı (hat, tren, vagon, dingil, sonraki istasyon) veride bulunmalı."""
    assert kolon in train_df.columns
    assert train_df[kolon].notna().all()
