"use client";

import { useMemo, useState } from "react";
import { SINIF_ETIKET, SINIF_RENK, type AxleDurum, type MetroAgi } from "@/lib/tipler";

/**
 * İstanbul raylı sistem ağı haritası.
 *
 * Hat güzergâhları ve istasyon konumları İBB Açık Veri Portalı'ndan gelen GERÇEK
 * koordinatlardır (WGS84). Koordinatlar basit bir eşdikdörtgen (equirectangular) izdüşümle
 * ekrana taşınır; İstanbul'un enleminde (~41°) boylam ölçeği cos(41°) ile çarpılarak
 * en-boy oranı korunur — aksi hâlde harita yatayda gerilmiş görünürdü.
 */

const KENAR = 16;

export default function MetroHarita({
  ag, axles, secili, onSec,
}: {
  ag: MetroAgi | null;
  axles: AxleDurum[];
  secili: string | null;
  onSec: (axle: string) => void;
}) {
  const [tumHatlar, setTumHatlar] = useState(true);
  const [vurgu, setVurgu] = useState<string | null>(null);

  const gorunum = useMemo(() => {
    if (!ag?.hatlar) return null;
    const hatlar = Object.values(ag.hatlar);
    const gosterilecek = tumHatlar
      ? hatlar
      : hatlar.filter((h) => ag.simulasyon_hatlari.includes(h.kod));

    // sınırlar: gösterilen tüm istasyon ve güzergâh noktaları
    let lonMin = 180, lonMax = -180, latMin = 90, latMax = -90;
    for (const h of gosterilecek) {
      for (const i of h.istasyonlar) {
        lonMin = Math.min(lonMin, i.lon); lonMax = Math.max(lonMax, i.lon);
        latMin = Math.min(latMin, i.lat); latMax = Math.max(latMax, i.lat);
      }
    }
    const lat0 = ((latMin + latMax) / 2) * (Math.PI / 180);
    const kx = Math.cos(lat0);                       // boylam sıkıştırma katsayısı
    const g = (lonMax - lonMin) * kx, y = latMax - latMin;

    // Yükseklik sınırlandırılır ki harita sayfayı boydan boya kaplamasın; ölçek iki eksenin
    // küçüğüne göre seçilip içerik yatayda ortalanır (en-boy oranı korunur).
    const W = 1000;
    const H = Math.min(560, Math.max(340, Math.round((W - 2 * KENAR) * (y / g)) + 2 * KENAR));
    const olcek = Math.min((W - 2 * KENAR) / g, (H - 2 * KENAR) / y);
    const kaydirX = (W - g * olcek) / 2;
    const kaydirY = (H - y * olcek) / 2;

    const X = (lon: number) => kaydirX + (lon - lonMin) * kx * olcek;
    const Y = (lat: number) => H - kaydirY - (lat - latMin) * olcek;
    return { W, H, X, Y, gosterilecek };
  }, [ag, tumHatlar]);

  if (!ag || !gorunum) {
    return (
      <div className="panel">
        <header><h2>Ağ Haritası</h2></header>
        <div className="aciklama-kutu">Metro ağı yükleniyor…</div>
      </div>
    );
  }

  const { W, H, X, Y, gosterilecek } = gorunum;
  const simHatlari = new Set(ag.simulasyon_hatlari);

  // Trenleri grupla: aynı trenin 4 dingili tek ikon; en kötü durumdaki dingil rengi kazanır
  const trenler = new Map<string, { axles: AxleDurum[]; lat: number; lon: number }>();
  for (const a of axles) {
    if (a.konum?.lat == null || a.konum?.lon == null) continue;
    const g = trenler.get(a.train_id) ?? { axles: [], lat: a.konum.lat, lon: a.konum.lon };
    g.axles.push(a);
    trenler.set(a.train_id, g);
  }

  return (
    <div className="panel">
      <header>
        <h2>İstanbul Raylı Sistem Ağı — Canlı Konum</h2>
        <div className="sekme-grup">
          <button className={tumHatlar ? "aktif" : ""} onClick={() => setTumHatlar(true)}>Tüm ağ</button>
          <button className={!tumHatlar ? "aktif" : ""} onClick={() => setTumHatlar(false)}>
            Sadece işletilen hatlar
          </button>
        </div>
      </header>

      <div style={{ overflowX: "auto" }}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%"
             style={{ display: "block", minWidth: 520, background: "var(--deniz)", borderRadius: 8 }}>
          {/* --- zemin: kara parçası (ilçe poligonları). Çizilmeyen yer denizdir:
                  Boğaz, Haliç, Marmara ve Karadeniz kıyıları böyle ortaya çıkar. --- */}
          <g>
            {ag.cografya?.ilceler.map((ilce, i) => (
              <path
                key={`${ilce.ad}-${i}`}
                d={ilce.poligonlar
                  .map((parca) =>
                    parca
                      .map((halka) =>
                        halka
                          .map(([lon, lat], j) =>
                            `${j === 0 ? "M" : "L"}${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`)
                          .join(" ") + " Z")
                      .join(" "))
                  .join(" ")}
                fillRule="evenodd"
                fill="var(--kara)"
                stroke="var(--kara-sinir)"
                strokeWidth={0.6}
              >
                <title>{ilce.ad}</title>
              </path>
            ))}
          </g>

          {/* --- hat güzergâhları (gerçek geometri) --- */}
          {gosterilecek.map((h) => {
            const sim = simHatlari.has(h.kod);
            return (
              <g key={h.kod} opacity={vurgu && vurgu !== h.kod ? 0.18 : 1}>
                {h.cizim.map((parca, i) => (
                  <polyline
                    key={i}
                    points={parca.map(([lon, lat]) => `${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`).join(" ")}
                    fill="none"
                    stroke={h.renk}
                    strokeWidth={sim ? 3 : 1.6}
                    strokeOpacity={sim ? 0.95 : 0.4}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
              </g>
            );
          })}

          {/* --- istasyonlar --- */}
          {gosterilecek.map((h) => (
            <g key={`i-${h.kod}`} opacity={vurgu && vurgu !== h.kod ? 0.15 : 1}>
              {h.istasyonlar.map((ist) => (
                <circle
                  key={ist.ad}
                  cx={X(ist.lon)} cy={Y(ist.lat)}
                  r={simHatlari.has(h.kod) ? 2.6 : 1.6}
                  fill="var(--bg)" stroke={h.renk}
                  strokeWidth={simHatlari.has(h.kod) ? 1.4 : 0.9}
                >
                  <title>{`${h.kod} · ${ist.ad} (${ist.km.toFixed(1)} km)`}</title>
                </circle>
              ))}
            </g>
          ))}

          {/* --- ray kusuru noktaları (sabit hat arızaları) --- */}
          {ag.ray_kusurlari?.map((k, i) => (
            <g key={`k-${i}`}>
              <path
                d={`M ${X(k.lon)} ${Y(k.lat) - 6} L ${X(k.lon) + 5.5} ${Y(k.lat) + 3.5} L ${X(k.lon) - 5.5} ${Y(k.lat) + 3.5} Z`}
                fill="var(--bad)" opacity={0.85} stroke="var(--bg)" strokeWidth={0.8}
              >
                <title>{`Ray kusuru · ${k.hat} · ${k.arasi} (${k.siddet}, km ${k.km})`}</title>
              </path>
            </g>
          ))}

          {/* --- trenler (canlı konum, tahmin rengiyle) --- */}
          {[...trenler.entries()].map(([trainId, g]) => {
            const arizali = g.axles.filter((a) => a.yerlesik && a.yerlesik !== "normal");
            const enKotu = arizali[0];
            const renk = enKotu ? SINIF_RENK[enKotu.yerlesik!] : "var(--ok)";
            const seciliTren = g.axles.some((a) => a.axle === secili);
            const cx = X(g.lon), cy = Y(g.lat);
            const durakta = g.axles[0]?.konum?.durakta;
            return (
              <g key={trainId} style={{ cursor: "pointer" }}
                 onClick={() => onSec(g.axles[0].axle)}
                 onMouseEnter={() => setVurgu(g.axles[0].line_id ?? null)}
                 onMouseLeave={() => setVurgu(null)}>
                {arizali.length > 0 && (
                  <circle cx={cx} cy={cy} r={11} fill={renk} opacity={0.22}>
                    <animate attributeName="r" values="8;15;8" dur="1.8s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.30;0;0.30" dur="1.8s" repeatCount="indefinite" />
                  </circle>
                )}
                <rect
                  x={cx - 6} y={cy - 4.5} width={12} height={9} rx={2.5}
                  fill={renk} stroke={seciliTren ? "var(--text)" : "var(--bg)"}
                  strokeWidth={seciliTren ? 2 : 1.2}
                />
                {durakta && <circle cx={cx} cy={cy} r={1.6} fill="var(--bg)" />}
                <title>
                  {`${trainId} · ${g.axles[0].line_id}\n` +
                   `${g.axles[0].konum.durakta ? "İstasyonda: " : "Sonraki: "}${g.axles[0].konum.istasyon ?? "-"}\n` +
                   `km ${g.axles[0].konum.km.toFixed(2)}\n` +
                   (arizali.length
                     ? arizali.map((a) => `⚠ ${a.axle}: ${SINIF_ETIKET[a.yerlesik!]}`).join("\n")
                     : "Tüm dingiller normal")}
                </title>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="efsane" style={{ marginTop: 10 }}>
        {gosterilecek.filter((h) => simHatlari.has(h.kod)).map((h) => (
          <span key={h.kod}
                onMouseEnter={() => setVurgu(h.kod)} onMouseLeave={() => setVurgu(null)}
                style={{ cursor: "default" }}>
            <i style={{ background: h.renk }} /> <b style={{ color: "var(--text)" }}>{h.kod}</b> {h.kisa_ad}
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>
          ▲ ray kusuru · ▮ tren (renk = arıza durumu) · ince çizgi = tren işletilmeyen hat ·
          koyu alan = deniz
        </span>
      </div>

      <div className="aciklama-kutu" style={{ marginTop: 8 }}>
        Hat güzergâhları, istasyon konumları ve adları <b>İBB Açık Veri Portalı</b>'ndaki gerçek
        veriden gelir. Harita zemini (kara parçası ve kıyı çizgisi) <b>geoBoundaries</b> ilçe
        sınırlarından çizilir (ODbL 1.0); denizler ayrı bir veri değildir — karanın olmadığı
        yerdir, Boğaz ve Haliç böyle görünür. Trenler bu gerçek hatlar üzerinde, gerçek istasyon
        dizisinde hareket eder; ikon rengi modelin o trendeki dingiller için verdiği
        <b>yerleşik</b> (histerezis sonrası) tahmindir.
      </div>
    </div>
  );
}
