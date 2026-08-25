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


def test_kor_modda_akis_bitince_sonuclar_acilir():
    """Kör modda akış SÜRERKEN metrikler gizli kalmalı; akış TAMAMLANDIĞINDA (son tick),
    kullanıcının sonunda sonucu görebilmesi için toplu doğruluk/karmaşıklık matrisi bir
    kerelik açığa çıkmalı — ama tekil dingil paketlerinde 'gercek' etiketi hâlâ sızmamalı."""
    try:
        s = sunucu.AkisSimulatoru(kor_mod=True, baslangic_hizi=1000)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")
    son = None
    while True:
        p = s.bir_tick_isle()
        if p is None:
            break
        son = p
    assert son["bitti"] is True
    assert son["metrikler"]["kor_mod"] is False
    assert son["metrikler"]["kor_mod_sonu_acildi"] is True
    assert son["metrikler"]["accuracy"] is not None
    assert "confusion" in son["metrikler"]
    for a in son["axles"]:
        assert "gercek" not in a
        assert "gercek_severity" not in a
        assert "dogru_mu" not in a


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


# ------------------------------------------------------- ray kusuru tekrarları
def test_ray_kusuru_yogunlugu_makul(veri_dizini):
    """Ağdaki aktif ray kusuru sayısı gerçekçi olmalı: bakımlı bir metro ağında aynı anda
    onlarca aktif kusur bulunmaz (hat başına en fazla bir tane)."""
    import json
    import os
    yol = os.path.join(veri_dizini, "ray_kusur_noktalari.json")
    if not os.path.exists(yol):
        pytest.skip("Ray kusuru dosyası yok")
    with open(yol, encoding="utf-8") as f:
        kusurlar = json.load(f)
    hatlar = [k["hat"] for k in kusurlar]
    assert len(kusurlar) <= 12, f"ağda çok fazla aktif ray kusuru var: {len(kusurlar)}"
    assert len(hatlar) == len(set(hatlar)), "bir hatta birden fazla kusur tanımlanmış"


def test_ray_catlagi_alarmi_kusura_baglanir(sim):
    """Ray çatlağı alarmı, hat üzerindeki SABİT kusur noktasıyla eşleştirilmeli ve
    aynı kusurun kaçıncı tespiti olduğu sayılmalı (tekrar eden kusur takibi)."""
    sim.reset()
    ray_olaylari = []
    for _ in range(300):
        p = sim.bir_tick_isle()
        if p is None:
            break
        ray_olaylari += [o for o in p["yeni_olaylar"] if o["yeni"] == "rail_crack"]
    if not ray_olaylari:
        pytest.skip("bu akışta ray çatlağı alarmı oluşmadı")
    eslesen = [o for o in ray_olaylari if o.get("kusur_id")]
    assert eslesen, "hiçbir ray çatlağı alarmı kusur noktasıyla eşleşmedi"
    for o in eslesen:
        assert o["tekrar_no"] >= 1
        assert "@" in o["kusur_id"]


def test_ray_catlagi_alarm_sayisi_dengeli(sim):
    """Ray çatlağı, konuma bağlı olduğu için doğal olarak tekrar eder; yine de tek bir sınıf
    diğerlerinin toplamını aşacak kadar baskın olmamalı (kusur yoğunluğu gerçekçi olmalı)."""
    sim.reset()
    sayac = {}
    for _ in range(300):
        p = sim.bir_tick_isle()
        if p is None:
            break
        for o in p["yeni_olaylar"]:
            if o["tip"] == "alarm":
                sayac[o["yeni"]] = sayac.get(o["yeni"], 0) + 1
    if not sayac:
        pytest.skip("alarm oluşmadı")
    ray = sayac.get("rail_crack", 0)
    digerleri = sum(v for k, v in sayac.items() if k != "rail_crack")
    assert ray <= max(digerleri, 5), f"rail_crack aşırı baskın: {ray} vs diğerleri {digerleri}"


# ------------------------------------------------------- anomali (unsupervised) katmanı
def test_anomali_katmani_paketlere_ekleniyor(sim):
    """Anomali modeli yüklüyse her hazır tahmine anomali skoru ve bayrağı eklenmeli."""
    if sim.anomali_model is None:
        pytest.skip("Anomali modeli eğitilmemiş")
    sim.reset()
    for _ in range(sim.window):
        p = sim.bir_tick_isle()
    for a in p["axles"]:
        assert "anomali_skor" in a
        assert 0.0 <= a["anomali_skor"] <= 1.0
        assert isinstance(a["anomali"], bool)
        assert isinstance(a["bilinmeyen_anomali"], bool)


def test_bilinmeyen_anomali_sadece_normal_tahminde_olur(sim):
    """'bilinmeyen_anomali' TANIM GEREĞİ yalnızca denetimli model 'normal' derken
    anomali bayrağı da True olan dingillerde işaretlenmeli."""
    if sim.anomali_model is None:
        pytest.skip("Anomali modeli eğitilmemiş")
    sim.reset()
    for _ in range(80):
        p = sim.bir_tick_isle()
        if p is None:
            break
    for a in p["axles"]:
        if a.get("bilinmeyen_anomali"):
            assert a["pred"] == "normal"
            assert a["anomali"] is True


def test_anomali_modeli_olmadan_sunucu_calisir():
    """Anomali checkpoint'i olmasa bile ana sistem hiçbir hata vermeden çalışmalı
    (özellik TAMAMEN opsiyonel, ana sınıflandırmayı etkilememeli)."""
    import rayli_canli_akis_sunucu as modul
    eski_yol = modul.ANOMALI_MODEL_PATH
    try:
        modul.ANOMALI_MODEL_PATH = "/olmayan/bir/yol.pt"
        s = modul.AkisSimulatoru(baslangic_hizi=1000, kayit=False)
        assert s.anomali_model is None
        p = s.bir_tick_isle()
        assert p is not None
        assert "anomali_skor" not in p["axles"][0] or p["axles"][0].get("anomali_skor") is None
    finally:
        modul.ANOMALI_MODEL_PATH = eski_yol


# ------------------------------------------------------- canlı/sürekli üretim (--kaynak canli)
# NOT: `sim` fixture'ı (ve dosyadaki diğer tüm testler) CSV kaynağını kullanır — sınıfın
# varsayılanı bilinçli olarak "csv" bırakıldı (bkz. rayli_canli_akis_sunucu.py:AkisSimulatoru
# docstring notu). Bu bölümdeki testler `kaynak="canli"`yi AÇIKÇA istiyor, ayrı bir fixture
# kullanıyor — modül seviyesinde (`scope="module"`) çünkü segment üretimi (ağ okuma + model
# yükleme) pahalı, testler arası paylaşılabilir.
@pytest.fixture(scope="module")
def canli_sim():
    try:
        return sunucu.AkisSimulatoru(baslangic_hizi=1000, histerezis=3, kaynak="canli", kayit=False)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")


def test_canli_modda_ilk_segment_uretilir(canli_sim):
    """Kurulum sonrası (constructor içindeki reset()) en az bir segment hazır olmalı."""
    assert len(canli_sim.ticks) >= sunucu.veri_uret.SEGMENT_STEPS
    assert len(canli_sim.axles) > 0


def test_canli_modda_segment_gecisinde_state_korunur(canli_sim):
    """Segment sonuna gelindiğinde `_segment_ekle()` çağrılınca pencere/histerezis state'i
    SIFIRLANMAMALI (`reset()` çağrılmamalı) — 'kaldığı yerden devam' bunun üzerine kurulu."""
    canli_sim.reset()
    for _ in range(canli_sim.window + 5):
        canli_sim.bir_tick_isle()
    dolu_axle = next(a for a in canli_sim.axles if len(canli_sim.buffers[a]) == canli_sim.window)

    # Segment sonuna kadar ilerlet, sınırı `_segment_ekle()` ile geç (dongu()'nun yaptığı gibi)
    while canli_sim.tick_index < len(canli_sim.ticks):
        canli_sim.bir_tick_isle()
    tick_index_sinirda = canli_sim.tick_index
    canli_sim._segment_ekle()
    canli_sim.bir_tick_isle()

    # reset() çağrılsaydı tick_index 0'a döner ve pencere boşalırdı — ikisi de OLMAMALI
    assert tick_index_sinirda >= sunucu.veri_uret.SEGMENT_STEPS
    assert canli_sim.tick_index > tick_index_sinirda
    assert len(canli_sim.buffers[dolu_axle]) == canli_sim.window


def test_canli_modda_reset_farkli_senaryo_uretir():
    """İki ayrı 'Sıfırla', AYNI saatten başlayıp FARKLI bir arıza senaryosu üretmeli —
    kullanıcının 'her bastığımda farklı dingillerde farklı arızalar çıksın' isteği."""
    try:
        s = sunucu.AkisSimulatoru(baslangic_hizi=1000, kaynak="canli", kayit=False)
    except SystemExit as e:
        pytest.skip(f"Simülatör kurulamadı: {e}")

    # sample_id'ler her reset'te 0'dan başlar (aynı üretim sırasıyla), bu yüzden "hangi
    # sample_id'ler arızalı" kümesi iki reset arasında pozisyonel olarak karşılaştırılabilir.
    # Arıza yoğunluğu artık düşük olduğu için (gerçekçilik — bkz. madde 7) sadece ilk birkaç
    # örneğe bakmak yanıltıcı olur (ikisi de "hepsi normal" çıkabilir); TÜM segmentteki
    # arızalı örnek kümesi karşılaştırılır.
    s.reset()
    arizali_1 = frozenset(sid for sid, v in s.answer_key.items() if v != "normal")
    baslangic_1 = s.timestamps[0]
    s.reset()
    arizali_2 = frozenset(sid for sid, v in s.answer_key.items() if v != "normal")
    baslangic_2 = s.timestamps[0]

    assert baslangic_1 == baslangic_2, "Sabit başlangıç saati korunmalı"
    assert arizali_1 != arizali_2, "İki 'Sıfırla' birebir aynı arıza senaryosunu üretmemeli"


def test_canli_modda_akis_hic_bitmez(canli_sim):
    """`bitti` alanı canlı modda her zaman False olmalı — akış sonsuz, UI ilerleme çubuğu
    segment-içi pozisyonu göstermeli."""
    canli_sim.reset()
    p = None
    for _ in range(canli_sim.window + 2):
        p = canli_sim.bir_tick_isle()
    assert p is not None
    assert p["bitti"] is False
    assert p["toplam_tick"] == sunucu.veri_uret.SEGMENT_STEPS
    assert 0 <= p["tick"] < sunucu.veri_uret.SEGMENT_STEPS


def test_tren_sayisi_kademeli_esige_gore_artar():
    """Uzun hatlarda kısa hatlara göre daha çok tren olmalı (kademeli eşik tablosu)."""
    import istanbul_metro_agi as metro_ag
    agac = metro_ag.yukle()
    hatlar = agac["hatlar"]
    uzun_hatlar = [k for k in metro_ag.SIMULASYON_HATLARI
                  if k in hatlar and hatlar[k]["uzunluk_km"] >= 30.0]
    kisa_hatlar = [k for k in metro_ag.SIMULASYON_HATLARI
                  if k in hatlar and hatlar[k]["uzunluk_km"] < 10.0]
    assert uzun_hatlar, "Test verisi: en az bir 30km+ hat bekleniyor"
    for k in uzun_hatlar:
        assert sunucu.veri_uret.hat_tren_sayisi(hatlar[k]) >= 4
    for k in kisa_hatlar:
        assert sunucu.veri_uret.hat_tren_sayisi(hatlar[k]) == 1


def test_segment_uretimi_fiziksel_sureklilik():
    """`bir_segment_uret()` art arda çağrıldığında bir trenin konumu/hızı segment sınırında
    SIÇRAMAMALI (ışınlanmamalı) — bir önceki segmentin bitiş durumundan devam etmeli."""
    import numpy as np
    import istanbul_metro_agi as metro_ag
    import rayli_veri_uret as vu

    agac = metro_ag.yukle()
    hatlar = {k: v for k, v in agac["hatlar"].items() if k in metro_ag.SIMULASYON_HATLARI}
    kusurlar = vu.ray_kusurlari_uret(hatlar)
    rng_local = np.random.default_rng(999)

    df1, durumlar = vu.bir_segment_uret(hatlar, rng_local, vu.START_TIME, None, kusurlar, n_steps=50)
    baslangic_2 = df1["timestamp"].max() + __import__("datetime").timedelta(seconds=vu.WINDOW_SEC)
    df2, _ = vu.bir_segment_uret(hatlar, rng_local, baslangic_2, durumlar, kusurlar, n_steps=50)

    ortak_tren = df1["train_id"].iloc[0]
    son_1 = df1[df1.train_id == ortak_tren].sort_values("timestamp").iloc[-1]
    ilk_2 = df2[df2.train_id == ortak_tren].sort_values("timestamp").iloc[0]
    assert abs(ilk_2.track_km - son_1.track_km) < 0.5, "Tren segment sınırında ışınlanmamalı"


def test_arizali_dingil_orani_gercekci(canli_sim):
    """Aynı anda arızalı (yerleşik, normal olmayan) dingil oranı düşük olmalı — eskiden
    (~%20+) kullanıcının 'gerçekçi değil' dediği yoğunluğun düzeldiğini doğrular."""
    canli_sim.reset()
    p = None
    for _ in range(canli_sim.window + 30):
        p = canli_sim.bir_tick_isle()
    arizali = [a for a in p["axles"] if a.get("yerlesik") and a["yerlesik"] != "normal"]
    oran = len(arizali) / len(p["axles"])
    assert oran < 0.15, f"Aynı anda arızalı dingil oranı çok yüksek: %{oran*100:.1f}"
