"""İBB açık verisinden kurulan İstanbul metro ağı modelinin doğruluk testleri."""

import json
import os

import pytest

import istanbul_metro_agi as ag

# İstanbul'un kabaca coğrafi sınırları (WGS84) — koordinat akıl kontrolü için
ISTANBUL_BBOX = {"lon_min": 28.3, "lon_max": 29.7, "lat_min": 40.7, "lat_max": 41.5}


def test_ag_hatlari_yuklendi(metro_agi):
    """Ağ modeli yüklenmeli ve makul sayıda (en az 15) işletmedeki hat içermeli."""
    assert len(metro_agi["hatlar"]) >= 15


def test_simulasyon_hatlari_agda_var(metro_agi):
    """Simülasyonda tren işletilen tüm hatlar ağ modelinde tanımlı olmalı."""
    for kod in ag.SIMULASYON_HATLARI:
        assert kod in metro_agi["hatlar"], f"ağda yok: {kod}"


def test_isletmedeki_tum_hatlarda_tren_var(metro_agi):
    """İşletmedeki her yolcu hattında (teleferikler hariç) tren çalışmalı — metro, tramvay,
    füniküler ve banliyö hatlarının hiçbiri simülasyon dışında kalmamalı."""
    teleferikler = {kod for kod, h in metro_agi["hatlar"].items() if h["tur"] == "Teleferik"}
    kapsam_disi = set(metro_agi["hatlar"]) - set(ag.SIMULASYON_HATLARI) - teleferikler
    assert not kapsam_disi, f"tren işletilmeyen hat kaldı: {sorted(kapsam_disi)}"


def test_funikuler_hatlari_dahil(metro_agi):
    """Füniküler hatları (F1 Taksim–Kabataş, F2 Tünel, F4 Rumelihisarüstü–Aşiyan) ağda olmalı.
    F4 kaynak veride 'İnşaat Aşamasında' işaretlidir ama fiilen işletmededir; bu yüzden
    ISLETMEDEKI_INSAAT_HATLARI ile bilinçli olarak dahil edilir."""
    for kod in ("F1", "F2", "F4"):
        assert kod in metro_agi["hatlar"], f"füniküler eksik: {kod}"
        assert kod in ag.SIMULASYON_HATLARI
    f4 = metro_agi["hatlar"]["F4"]
    assert {i["ad"] for i in f4["istasyonlar"]} == {"Rumeli Hisarüstü", "Aşiyan"}


def test_metro_istanbul_disi_hatlar_agda_yok(metro_agi):
    """Metro İstanbul işletmesinde olmayan hatlar (Marmaray, M11 — Ulaştırma Bakanlığı)
    ağ modeline hiç alınmamalı. Ayrım isimle değil, kaynak verinin MUDURLUK alanıyla yapılır."""
    assert "MARMARAY" not in metro_agi["hatlar"]
    assert "M11" not in metro_agi["hatlar"]
    assert "Ulaştırma Bakanlığı" in ag.HARIC_MUDURLUKLER


def test_teleferikler_simulasyon_disinda():
    """Teleferiklerde dingil/boji yoktur — bu projenin sensör modeli onlara uymaz,
    simülasyona dahil edilmemeliler."""
    assert "TF1" not in ag.SIMULASYON_HATLARI
    assert "TF2" not in ag.SIMULASYON_HATLARI


def test_istasyon_koordinatlari_istanbulda(metro_agi):
    """Tüm istasyon koordinatları İstanbul sınırları içinde olmalı."""
    for kod, hat in metro_agi["hatlar"].items():
        for ist in hat["istasyonlar"]:
            assert ISTANBUL_BBOX["lon_min"] <= ist["lon"] <= ISTANBUL_BBOX["lon_max"], f"{kod}/{ist['ad']}"
            assert ISTANBUL_BBOX["lat_min"] <= ist["lat"] <= ISTANBUL_BBOX["lat_max"], f"{kod}/{ist['ad']}"


def test_istasyon_km_degerleri_artan(metro_agi):
    """Her hatta istasyonların km değerleri hat boyunca kesintisiz artmalı (sıralama tutarlılığı)."""
    for kod, hat in metro_agi["hatlar"].items():
        kmler = [i["km"] for i in hat["istasyonlar"]]
        assert kmler == sorted(kmler), f"{kod} hattında km sırası bozuk"
        assert kmler[0] == 0.0


def test_istasyon_adlari_benzersiz(metro_agi):
    """Bir hat üzerinde aynı istasyon adı iki kez geçmemeli."""
    for kod, hat in metro_agi["hatlar"].items():
        adlar = [i["ad"] for i in hat["istasyonlar"]]
        assert len(adlar) == len(set(adlar)), f"{kod} hattında mükerrer istasyon"


def test_bilinen_hat_uclari_dogru(metro_agi):
    """Sıralama algoritması gerçek terminalleri bulmalı — bilinen hatlarla doğrulama."""
    beklenen = {
        "M4": {"Kadıköy", "Sabiha Gökçen"},
        "T1": {"Kabataş", "Bağcılar"},
        "M2": {"Yenikapı", "Hacıosman"},
    }
    for kod, uclar in beklenen.items():
        if kod not in metro_agi["hatlar"]:
            pytest.skip(f"{kod} ağda yok")
        istasyonlar = metro_agi["hatlar"][kod]["istasyonlar"]
        assert {istasyonlar[0]["ad"], istasyonlar[-1]["ad"]} == uclar, f"{kod} terminalleri yanlış"


def test_m4_istasyon_sirasi_gercekle_uyumlu(metro_agi):
    """M4 hattının ilk istasyonları gerçek sırayla birebir örtüşmeli (Kadıköy'den itibaren)."""
    if "M4" not in metro_agi["hatlar"]:
        pytest.skip("M4 ağda yok")
    adlar = [i["ad"] for i in metro_agi["hatlar"]["M4"]["istasyonlar"]]
    assert adlar[:5] == ["Kadıköy", "Ayrılık Çeşmesi", "Acıbadem", "Ünalan", "Göztepe"]


def test_hat_uzunlugu_resmi_degere_yakin(metro_agi):
    """Hesaplanan (kuş uçuşu) hat uzunluğu, resmi hat uzunluğunu aşmamalı —
    ardışık istasyonlar arası düz çizgi toplamı, gerçek güzergâhtan uzun olamaz."""
    for kod, hat in metro_agi["hatlar"].items():
        resmi = hat.get("resmi_uzunluk_km")
        if not resmi or hat["istasyon_sayisi"] < 5:
            continue
        # %25 tolerans: resmi uzunluk bazı hatlarda eski/kısmi etaplara ait olabiliyor
        assert hat["uzunluk_km"] <= resmi * 1.25, f"{kod}: {hat['uzunluk_km']} > resmi {resmi}"


def test_ray_kusurlari_gercek_istasyon_araliginda(veri_dizini, metro_agi):
    """Ray kusuru noktaları, gerçek bir istasyon aralığında ve hat uzunluğu içinde olmalı."""
    yol = os.path.join(veri_dizini, "ray_kusur_noktalari.json")
    if not os.path.exists(yol):
        pytest.skip("Ray kusuru dosyası yok")
    with open(yol, encoding="utf-8") as f:
        kusurlar = json.load(f)
    assert kusurlar, "hiç ray kusuru tanımlanmamış"
    for k in kusurlar:
        hat = metro_agi["hatlar"][k["hat"]]
        assert 0 < k["km"] < hat["uzunluk_km"]
        assert " – " in k["arasi"], "kusur hangi istasyonlar arasında olduğunu belirtmeli"
        adlar = {i["ad"] for i in hat["istasyonlar"]}
        for ad in k["arasi"].split(" – "):
            assert ad in adlar, f"bilinmeyen istasyon: {ad}"


def _cografya(veri_dizini):
    yol = os.path.join(veri_dizini, "istanbul_cografya.json")
    if not os.path.exists(yol):
        pytest.skip("Coğrafya katmanı yok — 'python src/istanbul_metro_agi.py' çalıştırın")
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def test_cografya_katmani_ilceleri_iceriyor(veri_dizini):
    """Harita zemini (kara parçası) katmanı, ağı çevreleyen ilçeleri içermeli."""
    c = _cografya(veri_dizini)
    assert c["ilce_sayisi"] >= 30
    adlar = {i["ad"] for i in c["ilceler"]}
    for beklenen in ["Kadıköy", "Beşiktaş", "Üsküdar", "Bakırköy", "Adalar"]:
        assert beklenen in adlar, f"ilçe eksik: {beklenen}"


def test_cografya_poligonlari_kapali_ve_istanbulda(veri_dizini):
    """Poligon halkaları en az 4 noktadan oluşmalı ve koordinatlar İstanbul çevresinde olmalı."""
    c = _cografya(veri_dizini)
    for ilce in c["ilceler"]:
        for parca in ilce["poligonlar"]:
            for halka in parca:
                assert len(halka) >= 4, f"{ilce['ad']}: geçersiz halka"
                for lon, lat in halka:
                    assert 27.5 <= lon <= 30.5, f"{ilce['ad']}: boylam dışarıda ({lon})"
                    assert 40.3 <= lat <= 41.8, f"{ilce['ad']}: enlem dışarıda ({lat})"


def test_cografya_lisans_bilgisi_var(veri_dizini):
    """Yeniden dağıtılan açık veri için kaynak/lisans bilgisi katmanda saklanmalı."""
    c = _cografya(veri_dizini)
    assert "geoBoundaries" in c["kaynak"]
    assert "ODbL" in c["kaynak"] or "Open Database License" in c["kaynak"]


def test_haversine_bilinen_mesafe():
    """Haversine hesabı doğru olmalı: Kadıköy-Üsküdar arası ~3 km."""
    d = ag.haversine_km(29.0257, 40.9903, 29.0154, 41.0255)
    assert 3.0 < d < 4.5


def test_hat_kodu_ayikla():
    """Hat kodu çıkarımı İBB'nin adlandırma biçimlerini doğru ayrıştırmalı."""
    assert ag.hat_kodu("M4 Kadıköy - SGH Metro Hattı") == "M4"
    assert ag.hat_kodu("T1 Kabataş - Bağcılar Tramvay Hattı") == "T1"
    assert ag.hat_kodu("M1A Yenikapı - Atatürk Havalimanı Metro Hattı") == "M1A"
    assert ag.hat_kodu("Halkalı - Gebze Marmaray Yüzeysel Raylı Sistem Hattı") == "MARMARAY"
    assert ag.hat_kodu("Bilinmeyen Hat") is None


def test_istasyon_siralama_dogrusal_dizide_calisir():
    """Sıralama algoritması, karıştırılmış doğrusal bir istasyon dizisini geri kurmalı."""
    gercek = [{"ad": f"S{i}", "lon": 28.9 + i * 0.01, "lat": 41.0 + i * 0.002} for i in range(8)]
    karisik = [gercek[i] for i in [3, 0, 7, 2, 5, 1, 6, 4]]
    sirali = [s["ad"] for s in ag.istasyonlari_sirala(karisik)]
    assert sirali in ([f"S{i}" for i in range(8)], [f"S{i}" for i in reversed(range(8))])
