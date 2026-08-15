"""Canlı akış motoru: tick işleme, histerezis, kör mod ve doğrulama tutarlılığı testleri."""

import pytest

import rayli_canli_akis_sunucu as sunucu


@pytest.fixture(scope="module")
def sim():
    """Canlı akış simülatörü (CSV kaynaklı). Veri/model yoksa test atlanır."""
    try:
        return sunucu.AkisSimulatoru(baslangic_hizi=1000, histerezis=3)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")


def test_akis_verisinde_etiket_yok(sim):
    """SIZINTI KORUMASI: simülatörün okuduğu akış verisinde etiket kolonu olmamalı."""
    ornek = sim.ticks[0]
    assert "fault_type" not in ornek.columns
    assert "fault_severity" not in ornek.columns


def test_tick_yapisi_ve_dingil_sayisi(sim):
    """Her tick'te tüm dingiller için birer satır bulunmalı."""
    assert len(sim.ticks) > 0
    assert len(sim.axles) > 0
    assert len(sim.ticks[0]) == len(sim.axles)


def test_pencere_dolmadan_tahmin_yok(sim):
    """Kayan pencere dolmadan (ilk WINDOW-1 tick) tahmin üretilmemeli."""
    sim.reset()
    p = sim.bir_tick_isle()
    assert all(not a["hazir"] for a in p["axles"])
    assert all(a.get("pred") is None for a in p["axles"])


def test_pencere_dolunca_tahmin_uretilir(sim):
    """Pencere dolduğunda (WINDOW tick sonra) her dingil için tip ve şiddet tahmini gelmeli."""
    sim.reset()
    for _ in range(sim.window):
        p = sim.bir_tick_isle()
    for a in p["axles"]:
        assert a["hazir"]
        assert a["pred"] in sim.classes
        assert a["severity"] in sim.sev_classes
        assert 0.0 <= a["conf"] <= 1.0
        assert len(a["probs"]) == len(sim.classes)


def test_olasiliklar_toplami_bir(sim):
    """Softmax olasılıkları 1'e toplanmalı."""
    sim.reset()
    for _ in range(sim.window):
        p = sim.bir_tick_isle()
    for a in p["axles"]:
        assert abs(sum(a["probs"]) - 1.0) < 0.01
        assert abs(sum(a["sev_probs"]) - 1.0) < 0.01


def test_histerezis_yerlesik_sinifi_geciktirir(sim):
    """HİSTEREZİS: bir sınıf üst üste N tick gelmeden 'yerleşik' duruma geçmemeli."""
    sim.reset()
    sim.histerezis = 5
    for _ in range(sim.window):
        p = sim.bir_tick_isle()
    ilk = p["axles"][0]
    # pencere yeni dolduğu için hiçbir dingil henüz 5 ardışık tick biriktiremez
    assert ilk["yerlesik"] is None
    assert not ilk["kararli"]
    for _ in range(5):
        p = sim.bir_tick_isle()
    assert any(a["yerlesik"] is not None for a in p["axles"]), "yeterli tick sonrası yerleşmeli"


def test_histerezis_tek_ticklik_sicramayi_bastirir(sim):
    """Histerezis=1 ile her değişim anında yerleşirken, yüksek histerezisde olay sayısı azalmalı."""
    def olay_sayisi(h):
        sim.reset()
        sim.histerezis = h
        toplam = 0
        for _ in range(120):
            p = sim.bir_tick_isle()
            if p is None:
                break
            toplam += len(p["yeni_olaylar"])
        return toplam

    az_filtreli = olay_sayisi(1)
    cok_filtreli = olay_sayisi(6)
    assert cok_filtreli <= az_filtreli, "histerezis arttıkça alarm sayısı azalmalı"


def test_reset_durumu_temizler(sim):
    """Reset sonrası sayaçlar, pencereler ve metrikler sıfırlanmalı."""
    sim.reset()
    for _ in range(sim.window + 3):
        sim.bir_tick_isle()
    assert sim.degerlendirilen > 0
    sim.reset()
    assert sim.tick_index == 0
    assert sim.degerlendirilen == 0
    assert sim.dogru == 0
    assert sim.confusion.sum() == 0
    assert all(len(b) == 0 for b in sim.buffers.values())


def test_kor_modda_cevap_anahtari_sizmaz():
    """KÖR MOD: paketlerde gerçek etiket, şiddet ve doğruluk bilgisi hiç bulunmamalı."""
    try:
        s = sunucu.AkisSimulatoru(kor_mod=True, baslangic_hizi=1000)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")
    for _ in range(s.window + 2):
        p = s.bir_tick_isle()
    for a in p["axles"]:
        assert "gercek" not in a
        assert "gercek_severity" not in a
        assert "dogru_mu" not in a
    assert p["metrikler"]["kor_mod"] is True
    assert "accuracy" not in p["metrikler"]
    assert "confusion" not in p["metrikler"]


def test_kor_modda_da_sunucu_ici_skor_hesaplanir():
    """Kör modda arayüze gitmese de sunucu içinde skorlama sürmeli (log/teşhis için)."""
    try:
        s = sunucu.AkisSimulatoru(kor_mod=True, baslangic_hizi=1000)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")
    for _ in range(s.window + 5):
        s.bir_tick_isle()
    assert s.degerlendirilen > 0
    assert s.dogru > 0


def test_canli_dogruluk_makul(sim):
    """Canlı akış doğruluğu, offline test skoruna yakın (>= %90) olmalı —
    pencereleme/ölçekleme hattının doğru kurulduğunun uçtan uca kanıtı."""
    sim.reset()
    sim.histerezis = 3
    for _ in range(400):
        if sim.bir_tick_isle() is None:
            break
    m = sim._metrikler()
    assert m["degerlendirilen"] > 100
    assert m["accuracy"] >= 0.90, f"canlı doğruluk düştü: {m['accuracy']}"


def test_konum_bilgisi_haritaya_uygun(sim):
    """Her dingil paketi haritada çizilebilecek konum bilgisi taşımalı."""
    sim.reset()
    p = sim.bir_tick_isle()
    for a in p["axles"]:
        k = a["konum"]
        assert 40.7 <= k["lat"] <= 41.5
        assert 28.3 <= k["lon"] <= 29.7
        assert k["km"] >= 0
        assert a["line_id"]


def test_akis_sonuna_kadar_tamamlanir(sim):
    """Akış, son tick'e kadar kesintisiz ilerlemeli ve sonunda 'bitti' işaretlenmeli."""
    sim.reset()
    son = None
    while True:
        p = sim.bir_tick_isle()
        if p is None:
            break
        son = p
    assert son["tick"] + 1 == son["toplam_tick"]
    assert son["bitti"] is True


# ---------------------------------------------------------------- belirsizlik
def test_entropi_hesabi_dogru():
    """Normalize entropi: tek sınıfa tam güvende ~0, tüm sınıflar eşitken 1 olmalı."""
    import numpy as np
    assert sunucu.normalize_entropi(np.array([1.0, 0, 0, 0, 0, 0])) < 1e-6
    assert abs(sunucu.normalize_entropi(np.ones(6) / 6) - 1.0) < 1e-9


def test_belirsiz_tahmin_isaretlenir(sim):
    """Her hazır tahmin bir entropi ve belirsizlik bayrağı taşımalı."""
    sim.reset()
    for _ in range(sim.window):
        p = sim.bir_tick_isle()
    for a in p["axles"]:
        assert 0.0 <= a["entropi"] <= 1.0
        assert a["belirsiz"] == (a["entropi"] > sim.belirsizlik_esigi)


def test_belirsiz_tahmin_alarm_uretmez(sim):
    """BELİRSİZLİK KORUMASI: eşik 0 yapılırsa her tahmin belirsiz sayılır ve
    hiçbir sınıf yerleşemez — dolayısıyla alarm da üretilmez."""
    sim.reset()
    sim.belirsizlik_esigi = 0.0        # her şey belirsiz
    for _ in range(sim.window + 12):
        p = sim.bir_tick_isle()
    assert all(a.get("yerlesik") is None for a in p["axles"])
    assert p["aktif_alarmlar"] == []
    sim.belirsizlik_esigi = sunucu.VARSAYILAN_BELIRSIZLIK_ESIGI


# ------------------------------------------------------- alarm süresi/önceliği
def test_oncelik_siddet_ve_sureyle_artar():
    """Öncelik skoru şiddet ve süreyle birlikte artmalı (0-1 aralığında)."""
    dusuk = sunucu.oncelik_hesapla("mild", 0.0, 0.9)
    sureli = sunucu.oncelik_hesapla("mild", 120.0, 0.9)
    agir = sunucu.oncelik_hesapla("severe", 120.0, 0.9)
    assert 0.0 <= dusuk < sureli < agir <= 1.0
    assert sunucu.oncelik_seviyesi(agir) == "kritik"
    assert sunucu.oncelik_seviyesi(0.1) == "dusuk"


def test_alarm_suresi_artiyor(sim):
    """Yerleşik durum sürdükçe süre sayacı büyümeli."""
    sim.reset()
    for _ in range(sim.window + 6):
        p1 = sim.bir_tick_isle()
    sureler1 = {a["axle"]: a.get("yerlesik_sure_sn") for a in p1["axles"]}
    for _ in range(5):
        p2 = sim.bir_tick_isle()
    degismeyen = [a for a in p2["axles"]
                  if a.get("yerlesik") is not None
                  and a["yerlesik"] == next(x["yerlesik"] for x in p1["axles"] if x["axle"] == a["axle"])]
    assert degismeyen, "en az bir dingilin durumu sabit kalmalı"
    for a in degismeyen:
        assert a["yerlesik_sure_sn"] > (sureler1[a["axle"]] or 0)


def test_aktif_alarmlar_oncelige_gore_sirali(sim):
    """Aktif alarm listesi öncelik skoruna göre azalan sırada olmalı."""
    sim.reset()
    for _ in range(150):
        p = sim.bir_tick_isle()
        if p is None:
            break
    skorlar = [a["oncelik"] for a in p["aktif_alarmlar"]]
    assert skorlar == sorted(skorlar, reverse=True)
