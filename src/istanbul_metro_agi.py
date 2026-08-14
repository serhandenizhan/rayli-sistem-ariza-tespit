"""
İstanbul raylı sistem ağı — İBB Açık Veri Portalı'ndaki RESMİ veriden ağ modeli kurar.

Kaynak (Metro İstanbul / İBB Açık Veri Portalı, açık lisans):
  - Raylı Sistem İstasyon Noktaları Verisi (GeoJSON) -> istasyon adı + gerçek koordinat
  - Raylı Sistem Hatları Vektör Verisi (GeoJSON)     -> hat güzergâh geometrisi

Ne üretir?
----------
`data/istanbul_metro_agi.json`: her işletmedeki hat için hat kodu (M2, T1, F1...), adı, türü,
rengi, gerçek istasyon dizisi (koordinat + hat başından itibaren km) ve haritada çizilecek
sadeleştirilmiş güzergâh parçaları.

İstasyon sırası neden hesaplanıyor?
-----------------------------------
Kaynak veride istasyonlar sırasız bir nokta bulutu olarak gelir (hat üzerindeki sıra bilgisi
yoktur). Metro hatları coğrafi olarak neredeyse doğrusal olduğu için sıra, "en uzak iki istasyon
= iki terminal" varsayımıyla bir uçtan başlayıp her adımda en yakın ziyaret edilmemiş istasyona
giden açgözlü (greedy) bir zincirle çıkarılır. Sonuç, gerçek istasyon sırasıyla örtüşür;
kilometreler ardışık istasyonlar arası haversine mesafesinin kümülatifidir.

Kullanım:
    python istanbul_metro_agi.py            # önbellekteki ham veriden ağı kur
    python istanbul_metro_agi.py --indir    # ham veriyi İBB'den yeniden indir
"""

import argparse
import json
import math
import os
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
HAM_DIR = os.path.join(DATA_DIR, "harici")
AG_JSON = os.path.join(DATA_DIR, "istanbul_metro_agi.json")

ISTASYON_URL = ("https://data.ibb.gov.tr/dataset/04ec9805-2483-46c7-914f-30c50857a846/resource/"
                "3dc8203f-3613-48a8-85e9-24fffb7821ad/download/rayli_sistem_istasyon_poi_verisi.geojson")
HAT_URL = ("https://data.ibb.gov.tr/dataset/8b8603dd-2642-4789-a891-4bb7cb2c94e8/resource/"
           "fe4ec165-9d11-4b83-b031-caea3cfaae55/download/rayli_sistem_hat_verisi.geojson")

ISTASYON_HAM = os.path.join(HAM_DIR, "ibb_rayli_istasyon.geojson")
HAT_HAM = os.path.join(HAM_DIR, "ibb_rayli_hat.geojson")

# --- Harita zemini (kara parçası / kıyı çizgisi) ---
# geoBoundaries ADM2 (ilçe) sınırları — ODbL 1.0 lisanslı, yeniden dağıtılabilir açık veri.
# Bu katman haritada karayı çizmek içindir: ilçe poligonları birlikte çizilince Boğaz, Haliç,
# Marmara ve Karadeniz kıyıları ile Adalar doğal olarak ortaya çıkar.
COGRAFYA_URL = ("https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/"
                "TUR/ADM2/geoBoundaries-TUR-ADM2.geojson")
COGRAFYA_HAM = os.path.join(HAM_DIR, "geoboundaries_tur_adm2.geojson")
COGRAFYA_JSON = os.path.join(DATA_DIR, "istanbul_cografya.json")
COGRAFYA_KAYNAK = ("geoBoundaries (geoboundaries.org) TUR ADM2 — Open Data Commons Open "
                   "Database License (ODbL) 1.0")
# Ağ sınırlarının çevresine bırakılan pay (derece) — harita kenarlarında kara görünsün diye
COGRAFYA_PAY = 0.09
# Kaynak veride birkaç ilçe adı İngilizce geçiyor; harita ipuçlarında Türkçe görünsün diye
AD_DUZELTME = {"Prince Islands": "Adalar"}

# Metro İstanbul hat renkleri (resmi hat renklerine yakın; harita okunabilirliği için seçildi)
HAT_RENK = {
    "M1A": "#e30613", "M1B": "#a11f6b", "M2": "#00a55b", "M3": "#00b0e6", "M4": "#e5007d",
    "M5": "#7b3f98", "M6": "#a9915c", "M7": "#e94f8b", "M8": "#00857d", "M9": "#f0b323",
    "M11": "#8c6239", "T1": "#005baa", "T2": "#8b1f2f", "T3": "#5f2d8c", "T4": "#f47b20",
    "T5": "#00693c", "F1": "#7a7a7a", "F2": "#7a7a7a", "F4": "#7a7a7a",
    "TF1": "#9a9a9a", "TF2": "#9a9a9a", "MARMARAY": "#0b6ab0",
}

# Simülasyonda tren işletilen hatlar (her biri için ayrı tren seti kurulur).
# Avrupa + Anadolu yakası, metro + tramvay karışımı olacak şekilde seçildi.
SIMULASYON_HATLARI = ["M2", "M4", "M1A", "M5", "M7", "M3", "M8", "T1"]

DUNYA_YARICAP_KM = 6371.0088


# --------------------------------------------------------------------- yardımcılar
def haversine_km(lon1, lat1, lon2, lat2):
    """İki WGS84 noktası arasındaki büyük daire mesafesi (km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * DUNYA_YARICAP_KM * math.asin(math.sqrt(a))


def hat_kodu(proje_adi):
    """"M4 Kadıköy - SGH Metro Hattı" -> "M4"; Marmaray gibi kodsuz hatlar için MARMARAY."""
    if not proje_adi:
        return None
    ad = proje_adi.strip()
    ilk = ad.split()[0].upper()
    if ilk.startswith(("M", "T", "F")) and any(ch.isdigit() for ch in ilk):
        return ilk
    if "MARMARAY" in ad.upper():
        return "MARMARAY"
    return None


def _dik_mesafe(nokta, bas, son):
    """Douglas-Peucker için nokta-doğru mesafesi (derece uzayında, sadeleştirme amaçlı)."""
    (x, y), (x1, y1), (x2, y2) = nokta, bas, son
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def sadelestir(nokta_listesi, tolerans=0.00035):
    """Douglas-Peucker: harita çiziminde gereksiz noktaları atar (dosya boyutu için)."""
    if len(nokta_listesi) < 3:
        return nokta_listesi
    en_uzak, indeks = 0.0, 0
    for i in range(1, len(nokta_listesi) - 1):
        d = _dik_mesafe(nokta_listesi[i], nokta_listesi[0], nokta_listesi[-1])
        if d > en_uzak:
            en_uzak, indeks = d, i
    if en_uzak <= tolerans:
        return [nokta_listesi[0], nokta_listesi[-1]]
    sol = sadelestir(nokta_listesi[:indeks + 1], tolerans)
    sag = sadelestir(nokta_listesi[indeks:], tolerans)
    return sol[:-1] + sag


def istasyonlari_sirala(istasyonlar):
    """Sırasız istasyon noktalarını hat boyunca gerçek sıraya yakın bir diziye sokar.

    Yaklaşım: istasyon dizisi, toplam uzunluğu en kısa olan "açık gezgin satıcı yolu"dur —
    çünkü bir metro hattı coğrafi olarak doğrusala yakındır ve gerçek sıra, ardışık
    istasyonlar arası mesafe toplamını minimize eder.

    1) Her olası başlangıçtan açgözlü (en yakın komşu) bir yol kurulur, en kısası seçilir.
    2) 2-opt ile yol iyileştirilir — bu, açgözlü zincirin bıraktığı "zikzak" sapmalarını
       (özellikle Y şeklinde şubeli hatlarda) düzeltir.
    """
    n = len(istasyonlar)
    if n < 3:
        return list(istasyonlar)

    d = [[haversine_km(a["lon"], a["lat"], b["lon"], b["lat"]) for b in istasyonlar]
         for a in istasyonlar]

    def yol_uzunlugu(y):
        return sum(d[y[i]][y[i + 1]] for i in range(len(y) - 1))

    # 1) her başlangıç için açgözlü yol, en kısasını al
    en_iyi = None
    for bas in range(n):
        sira, kalan = [bas], set(range(n)) - {bas}
        while kalan:
            son = sira[-1]
            yakin = min(kalan, key=lambda k: d[son][k])
            sira.append(yakin)
            kalan.discard(yakin)
        if en_iyi is None or yol_uzunlugu(sira) < yol_uzunlugu(en_iyi):
            en_iyi = sira

    # 2) 2-opt: yolun bir parçasını ters çevirmek toplamı kısaltıyorsa uygula
    gelisme = True
    while gelisme:
        gelisme = False
        for i in range(n - 1):
            for j in range(i + 2, n):
                a, b = en_iyi[i], en_iyi[i + 1]
                c = en_iyi[j]
                e = en_iyi[j + 1] if j + 1 < n else None
                mevcut = d[a][b] + (d[c][e] if e is not None else 0.0)
                yeni = d[a][c] + (d[b][e] if e is not None else 0.0)
                if yeni < mevcut - 1e-9:
                    en_iyi[i + 1:j + 1] = reversed(en_iyi[i + 1:j + 1])
                    gelisme = True
    return [istasyonlar[i] for i in en_iyi]


# ------------------------------------------------------------------------- indirme
def indir(zorla=False):
    os.makedirs(HAM_DIR, exist_ok=True)
    for url, hedef in ((ISTASYON_URL, ISTASYON_HAM), (HAT_URL, HAT_HAM),
                       (COGRAFYA_URL, COGRAFYA_HAM)):
        if os.path.exists(hedef) and not zorla:
            print(f"Önbellekte var, atlanıyor: {os.path.basename(hedef)}")
            continue
        print(f"İndiriliyor: {os.path.basename(hedef)} …")
        with urllib.request.urlopen(url, timeout=180) as r, open(hedef, "wb") as f:
            f.write(r.read())
        print(f"  -> {os.path.getsize(hedef) // 1024} KB")


# --------------------------------------------------------------------------- kurma
def ag_kur():
    """Ham GeoJSON'lardan ağ modelini kurar ve data/istanbul_metro_agi.json'a yazar."""
    with open(ISTASYON_HAM, encoding="utf-8") as f:
        istasyon_gj = json.load(f)
    with open(HAT_HAM, encoding="utf-8") as f:
        hat_gj = json.load(f)

    # --- İstasyonlar: yalnızca işletmedeki (mevcut) hatlar, hat koduna göre grupla ---
    kod_istasyon = {}
    kod_meta = {}
    for f in istasyon_gj["features"]:
        p = f["properties"]
        if "Mevcut" not in str(p.get("PROJE_ASAMA", "")):
            continue
        kod = hat_kodu(p.get("PROJE_ADI"))
        if kod is None:
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        kod_istasyon.setdefault(kod, []).append({
            "ad": (p.get("ISTASYON") or "").strip(),
            "lon": round(float(lon), 6),
            "lat": round(float(lat), 6),
        })
        kod_meta.setdefault(kod, {"ad": p.get("PROJE_ADI"), "tur": p.get("HAT_TURU")})

    # --- Hat geometrileri (harita çizimi için), aynı koda ait parçalar birleştirilir ---
    kod_cizim = {}
    kod_uzunluk = {}
    for f in hat_gj["features"]:
        p = f["properties"]
        if p.get("PROJE_ASAMA") not in ("Mevcut", "Marmaray"):
            continue
        kod = hat_kodu(p.get("PROJE_AD_KISA") or p.get("PROJE_ADI"))
        if kod is None or kod not in kod_istasyon:
            continue
        g = f["geometry"]
        parcalar = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for parca in parcalar:
            nokta = [[round(float(c[0]), 5), round(float(c[1]), 5)] for c in parca if len(c) >= 2]
            if len(nokta) >= 2:
                kod_cizim.setdefault(kod, []).append(sadelestir(nokta))
        if p.get("UZUNLUK"):
            kod_uzunluk[kod] = max(kod_uzunluk.get(kod, 0), float(p["UZUNLUK"]))

    # --- Hatları kur: istasyonları sırala, kümülatif km hesapla ---
    hatlar = {}
    for kod, istasyonlar in kod_istasyon.items():
        # aynı isimli mükerrer noktaları ele (bazı istasyonlar birden çok POI ile gelir)
        benzersiz, gorulen = [], set()
        for s in istasyonlar:
            if s["ad"] and s["ad"] not in gorulen:
                gorulen.add(s["ad"])
                benzersiz.append(s)
        if len(benzersiz) < 2:
            continue

        sirali = istasyonlari_sirala(benzersiz)
        km = 0.0
        for i, s in enumerate(sirali):
            if i > 0:
                km += haversine_km(sirali[i - 1]["lon"], sirali[i - 1]["lat"], s["lon"], s["lat"])
            s["km"] = round(km, 3)

        meta = kod_meta[kod]
        hatlar[kod] = {
            "kod": kod,
            "ad": meta["ad"],
            "kisa_ad": f"{sirali[0]['ad']} – {sirali[-1]['ad']}",
            "tur": meta["tur"],
            "renk": HAT_RENK.get(kod, "#8798b3"),
            "uzunluk_km": round(km, 2),
            "resmi_uzunluk_km": kod_uzunluk.get(kod),
            "istasyon_sayisi": len(sirali),
            "istasyonlar": sirali,
            "cizim": kod_cizim.get(kod, []),
        }

    cikti = {
        "kaynak": "İBB Açık Veri Portalı (data.ibb.gov.tr) — Metro İstanbul raylı sistem "
                  "istasyon noktaları ve hat vektör verisi",
        "not": "İstasyon sırası, kaynak veride bulunmadığı için coğrafi konumlardan "
               "(en uzak iki istasyon = terminaller varsayımıyla) türetilmiştir.",
        "simulasyon_hatlari": SIMULASYON_HATLARI,
        "hatlar": hatlar,
    }
    with open(AG_JSON, "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Ağ kuruldu: {AG_JSON}  ({os.path.getsize(AG_JSON) // 1024} KB)")
    print(f"Hat sayısı: {len(hatlar)} | toplam istasyon: {sum(h['istasyon_sayisi'] for h in hatlar.values())}")
    for kod in sorted(hatlar, key=lambda k: (len(k), k)):
        h = hatlar[kod]
        print(f"  {kod:9s} {h['istasyon_sayisi']:3d} istasyon  {h['uzunluk_km']:6.2f} km  "
              f"{h['tur']:10s} {h['kisa_ad']}")
    return cikti


def _halka_bbox(koordinatlar):
    """İç içe koordinat listesinden (Polygon/MultiPolygon) bbox çıkarır."""
    xs, ys = [], []

    def yur(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for alt in c:
                yur(alt)

    yur(koordinatlar)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def cografya_kur(hatlar):
    """İlçe sınırlarından harita zemini (kara parçası) katmanını üretir.

    Ağın kapladığı alanın biraz dışına taşan tüm ilçeler alınır, poligonlar sadeleştirilir ve
    `data/istanbul_cografya.json` dosyasına yazılır. Haritada bu poligonlar dolu çizilir; deniz
    ayrı bir veri değildir — karanın çizilmediği yer denizdir (Boğaz, Haliç, Marmara).
    """
    if not os.path.exists(COGRAFYA_HAM):
        print("Coğrafya ham verisi yok, atlanıyor (indirmek için: --indir)")
        return None

    # Ağın sınırları -> ilgi alanı
    lon_min, lat_min = 180.0, 90.0
    lon_max, lat_max = -180.0, -90.0
    for hat in hatlar.values():
        for ist in hat["istasyonlar"]:
            lon_min = min(lon_min, ist["lon"]); lon_max = max(lon_max, ist["lon"])
            lat_min = min(lat_min, ist["lat"]); lat_max = max(lat_max, ist["lat"])
    alan = (lon_min - COGRAFYA_PAY, lat_min - COGRAFYA_PAY,
            lon_max + COGRAFYA_PAY, lat_max + COGRAFYA_PAY)

    with open(COGRAFYA_HAM, encoding="utf-8") as f:
        gj = json.load(f)

    ilceler = []
    for feature in gj["features"]:
        geom = feature["geometry"]
        kutu = _halka_bbox(geom["coordinates"])
        if not kutu:
            continue
        # ilgi alanıyla kesişmiyorsa atla
        if kutu[2] < alan[0] or kutu[0] > alan[2] or kutu[3] < alan[1] or kutu[1] > alan[3]:
            continue

        parcalar = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        poligonlar = []
        for poligon in parcalar:
            halkalar = []
            for halka in poligon:      # ilk halka dış sınır, sonrakiler delik
                nokta = [[round(float(c[0]), 5), round(float(c[1]), 5)] for c in halka]
                sade = sadelestir(nokta, tolerans=0.0009)
                if len(sade) >= 4:     # çok küçük adacıkları ele
                    halkalar.append(sade)
            if halkalar:
                poligonlar.append(halkalar)
        if poligonlar:
            ad = feature["properties"].get("shapeName", "")
            ilceler.append({"ad": AD_DUZELTME.get(ad, ad), "poligonlar": poligonlar})

    cikti = {"kaynak": COGRAFYA_KAYNAK, "ilce_sayisi": len(ilceler), "ilceler": ilceler}
    with open(COGRAFYA_JSON, "w", encoding="utf-8") as f:
        json.dump(cikti, f, ensure_ascii=False, separators=(",", ":"))

    nokta_sayisi = sum(len(h) for i in ilceler for p in i["poligonlar"] for h in p)
    print(f"Coğrafya katmanı: {COGRAFYA_JSON}  ({os.path.getsize(COGRAFYA_JSON) // 1024} KB)")
    print(f"  {len(ilceler)} ilçe, {nokta_sayisi} nokta (sadeleştirilmiş)")
    return cikti


def yukle():
    """Kurulmuş ağ modelini okur (diğer modüller bunu kullanır)."""
    if not os.path.exists(AG_JSON):
        raise SystemExit(
            f"Ağ modeli bulunamadı: {AG_JSON}\n"
            "Önce 'python istanbul_metro_agi.py' çalıştırın."
        )
    with open(AG_JSON, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="İBB açık verisinden İstanbul raylı sistem ağını kurar")
    ap.add_argument("--indir", action="store_true", help="Ham GeoJSON'ları İBB'den yeniden indir")
    args = ap.parse_args()

    indir(zorla=args.indir)
    ag = ag_kur()
    cografya_kur(ag["hatlar"])


if __name__ == "__main__":
    main()
