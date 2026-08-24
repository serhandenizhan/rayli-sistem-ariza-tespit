"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { SINIF_ETIKET, SINIF_RENK, type AxleDurum, type Hat, type Istasyon, type MetroAgi, type Olay } from "@/lib/tipler";

/**
 * İstanbul raylı sistem ağı haritası — yakınlaştırma / kaydırma destekli.
 *
 * Hat güzergâhları ve istasyon konumları İBB Açık Veri Portalı'ndan gelen GERÇEK
 * koordinatlardır (WGS84). Koordinatlar basit bir eşdikdörtgen (equirectangular) izdüşümle
 * ekrana taşınır; İstanbul'un enleminde (~41°) boylam ölçeği cos(41°) ile çarpılarak
 * en-boy oranı korunur — aksi hâlde harita yatayda gerilmiş görünürdü.
 *
 * Yakınlaştırma/kaydırma, projeksiyonu değiştirmek yerine tek bir SVG <g> katmanına
 * `translate(x,y) scale(k)` uygulanarak yapılır; böylece izdüşüm hesabı ve yol (path)
 * dizgileri bir kez hesaplanıp önbelleğe alınabilir.
 */

const KENAR = 16;
const MIN_OLCEK = 1;
const MAKS_OLCEK = 14;

type Donusum = { k: number; x: number; y: number };

const sinirla = (v: number, alt: number, ust: number) => Math.min(ust, Math.max(alt, v));

/** Poligon halkasının alan ağırlıklı ağırlık merkezi (etiketi doğru yere koymak için). */
function agirlikMerkezi(halka: number[][]): [number, number] {
  let alan = 0, cx = 0, cy = 0;
  for (let i = 0; i < halka.length - 1; i++) {
    const [x0, y0] = halka[i];
    const [x1, y1] = halka[i + 1];
    const c = x0 * y1 - x1 * y0;
    alan += c;
    cx += (x0 + x1) * c;
    cy += (y0 + y1) * c;
  }
  if (Math.abs(alan) < 1e-12) {
    const n = halka.length;
    return [halka.reduce((a, p) => a + p[0], 0) / n, halka.reduce((a, p) => a + p[1], 0) / n];
  }
  alan *= 0.5;
  return [cx / (6 * alan), cy / (6 * alan)];
}

type Ipucu =
  | { tur: "istasyon"; ist: Istasyon; hat: Hat; x: number; y: number }
  | { tur: "tren"; trainId: string; axles: AxleDurum[]; x: number; y: number };

/** Tooltip'i imlecin hangi çeyrekte olduğuna göre konumlandırır — ekran kenarından taşmasın diye
 *  (tooltip büyüklüğünü tam bilmeden basit ama sağlam bir çözüm). */
function ipucuStil(x: number, y: number): CSSProperties {
  const sagYarim = x > window.innerWidth / 2;
  const altYarim = y > window.innerHeight / 2;
  return {
    left: sagYarim ? undefined : x + 16,
    right: sagYarim ? window.innerWidth - x + 16 : undefined,
    top: altYarim ? undefined : y + 16,
    bottom: altYarim ? window.innerHeight - y + 16 : undefined,
  };
}

export default function MetroHarita({
  ag, axles, secili, onSec, olaylar = [],
}: {
  ag: MetroAgi | null;
  axles: AxleDurum[];
  secili: string | null;
  onSec: (axle: string) => void;
  olaylar?: Olay[];
}) {
  const [tumHatlar, setTumHatlar] = useState(true);
  const [ilceAdlari, setIlceAdlari] = useState(true);
  const [vurgu, setVurgu] = useState<string | null>(null);
  const [don, setDon] = useState<Donusum>({ k: 1, x: 0, y: 0 });
  const [ipucu, setIpucu] = useState<Ipucu | null>(null);

  // İstasyon adına göre gruplanmış son olaylar — "bu durakta son saatlerde ne oldu, çözüldü mü"
  // sorusuna cevap vermek için. Ekstra backend çağrısı gerekmiyor: olaylar zaten useAkis'ten
  // en yeniden en eskiye sıralı geliyor.
  const olaylarIstasyonda = useMemo(() => {
    const m = new Map<string, Olay[]>();
    for (const o of olaylar) {
      if (!o.istasyon) continue;
      const arr = m.get(o.istasyon) ?? [];
      arr.push(o);
      m.set(o.istasyon, arr);
    }
    return m;
  }, [olaylar]);

  const [bilgiAcik, setBilgiAcik] = useState(false);
  // SVG'nin ekrana çizilirkenki ölçeği (letterbox nedeniyle 1'den küçük olabilir).
  // Yazı boyutlarını GERÇEK piksel cinsinden sabitlemek için gerekli: viewBox birimi
  // doğrudan piksel değildir, bu ölçekle çarpılır.
  const [ekranOlcek, setEkranOlcek] = useState(1);

  const svgRef = useRef<SVGSVGElement>(null);
  const surukleRef = useRef<{ aktif: boolean; x: number; y: number; kaydi: boolean }>(
    { aktif: false, x: 0, y: 0, kaydi: false });

  /** Ekran (client) koordinatını viewBox koordinatına çevirir.
   *  SVG'ye `max-height` verildiği için içerik `preserveAspectRatio` ile ORTALANIR ve kenarlarda
   *  boşluk (letterbox) kalır; bu yüzden basit oranlama yetmez, ölçek ve kaydırma payı
   *  hesaba katılmalıdır — aksi hâlde fare tekerleği yanlış noktaya yakınlaşır. */
  const ekranToViewBox = useCallback((cx: number, cy: number, kutu: DOMRect, W: number, H: number) => {
    const olcek = Math.min(kutu.width / W, kutu.height / H);
    return {
      x: (cx - kutu.left - (kutu.width - W * olcek) / 2) / olcek,
      y: (cy - kutu.top - (kutu.height - H * olcek) / 2) / olcek,
      olcek,
    };
  }, []);

  // ---------------------------------------------------------------- izdüşüm
  const gorunum = useMemo(() => {
    if (!ag?.hatlar) return null;
    const hatlar = Object.values(ag.hatlar);
    const gosterilecek = tumHatlar
      ? hatlar
      : hatlar.filter((h) => ag.simulasyon_hatlari.includes(h.kod));

    let lonMin = 180, lonMax = -180, latMin = 90, latMax = -90;
    for (const h of gosterilecek) {
      for (const i of h.istasyonlar) {
        lonMin = Math.min(lonMin, i.lon); lonMax = Math.max(lonMax, i.lon);
        latMin = Math.min(latMin, i.lat); latMax = Math.max(latMax, i.lat);
      }
    }
    const lat0 = ((latMin + latMax) / 2) * (Math.PI / 180);
    const kx = Math.cos(lat0);
    const g = (lonMax - lonMin) * kx, y = latMax - latMin;

    const W = 1000;
    const H = Math.min(560, Math.max(340, Math.round((W - 2 * KENAR) * (y / g)) + 2 * KENAR));
    const olcek = Math.min((W - 2 * KENAR) / g, (H - 2 * KENAR) / y);
    const kaydirX = (W - g * olcek) / 2;
    const kaydirY = (H - y * olcek) / 2;

    const X = (lon: number) => kaydirX + (lon - lonMin) * kx * olcek;
    const Y = (lat: number) => H - kaydirY - (lat - latMin) * olcek;
    return { W, H, X, Y, gosterilecek };
  }, [ag, tumHatlar]);

  // --------------------------------------------------- coğrafya yolları (önbellek)
  const cografyaYollari = useMemo(() => {
    if (!ag?.cografya || !gorunum) return [];
    const { X, Y } = gorunum;
    return ag.cografya.ilceler.map((ilce) => {
      let enBuyuk: number[][] = [], enCok = 0;
      const d = ilce.poligonlar
        .map((parca) =>
          parca
            .map((halka) => {
              if (halka.length > enCok) { enCok = halka.length; enBuyuk = halka; }
              return halka
                .map(([lon, lat], j) => `${j === 0 ? "M" : "L"}${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`)
                .join(" ") + " Z";
            })
            .join(" "))
        .join(" ");
      const [clon, clat] = enBuyuk.length ? agirlikMerkezi(enBuyuk) : [0, 0];
      return { ad: ilce.ad, d, cx: X(clon), cy: Y(clat), buyukluk: enCok };
    });
  }, [ag, gorunum]);

  // ------------------------------------------- çizim ölçeğini ölç (yazı boyutu için)
  useEffect(() => {
    const el = svgRef.current;
    if (!el || !gorunum) return;
    const guncelle = () => {
      const r = el.getBoundingClientRect();
      if (r.width && r.height) {
        setEkranOlcek(Math.min(r.width / gorunum.W, r.height / gorunum.H) || 1);
      }
    };
    guncelle();
    const gozlemci = new ResizeObserver(guncelle);
    gozlemci.observe(el);
    return () => gozlemci.disconnect();
  }, [gorunum]);

  // --------------------------------------------------------- fare tekerleği (zoom)
  useEffect(() => {
    const el = svgRef.current;
    if (!el || !gorunum) return;
    const { W, H } = gorunum;

    const tekerlek = (e: WheelEvent) => {
      e.preventDefault();                       // sayfa kaymasın, harita yakınlaşsın
      const { x: sx, y: sy } = ekranToViewBox(e.clientX, e.clientY, el.getBoundingClientRect(), W, H);
      setDon((t) => {
        const yeniK = sinirla(t.k * (e.deltaY < 0 ? 1.18 : 1 / 1.18), MIN_OLCEK, MAKS_OLCEK);
        if (yeniK === t.k) return t;
        // imlecin altındaki coğrafi nokta yerinde kalsın
        return { k: yeniK, x: sx - ((sx - t.x) * yeniK) / t.k, y: sy - ((sy - t.y) * yeniK) / t.k };
      });
    };
    el.addEventListener("wheel", tekerlek, { passive: false });
    return () => el.removeEventListener("wheel", tekerlek);
  }, [gorunum, ekranToViewBox]);

  // ------------------------------------------------------------- sürükleme (pan)
  const bas = useCallback((e: React.PointerEvent) => {
    surukleRef.current = { aktif: true, x: e.clientX, y: e.clientY, kaydi: false };
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
  }, []);

  const hareket = useCallback((e: React.PointerEvent) => {
    const s = surukleRef.current;
    if (!s.aktif || !gorunum) return;
    const kutu = (e.currentTarget as Element).getBoundingClientRect();
    const { olcek } = ekranToViewBox(e.clientX, e.clientY, kutu, gorunum.W, gorunum.H);
    const dx = (e.clientX - s.x) / olcek;
    const dy = (e.clientY - s.y) / olcek;
    if (Math.abs(e.clientX - s.x) + Math.abs(e.clientY - s.y) > 3) s.kaydi = true;
    s.x = e.clientX; s.y = e.clientY;
    setDon((t) => ({ ...t, x: t.x + dx, y: t.y + dy }));
  }, [gorunum, ekranToViewBox]);

  const birak = useCallback((e: React.PointerEvent) => {
    surukleRef.current.aktif = false;
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
  }, []);

  const yakinlas = (carpan: number) => setDon((t) => {
    if (!gorunum) return t;
    const { W, H } = gorunum;
    const yeniK = sinirla(t.k * carpan, MIN_OLCEK, MAKS_OLCEK);
    // ekran merkezini sabit tutarak yakınlaş
    return { k: yeniK, x: W / 2 - ((W / 2 - t.x) * yeniK) / t.k, y: H / 2 - ((H / 2 - t.y) * yeniK) / t.k };
  });

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
  const k = don.k;

  // Trenleri grupla: aynı trenin dingilleri tek ikon; arızalı dingil varsa rengi o belirler
  const trenler = new Map<string, { axles: AxleDurum[]; lat: number; lon: number }>();
  for (const a of axles) {
    if (a.konum?.lat == null || a.konum?.lon == null) continue;
    const g = trenler.get(a.train_id) ?? { axles: [], lat: a.konum.lat, lon: a.konum.lon };
    g.axles.push(a);
    trenler.set(a.train_id, g);
  }

  // Ölçekten bağımsız görünsün diye çizgi kalınlıkları k'ye bölünür
  const kal = (v: number) => v / k;
  // Yazılar GERÇEK piksel cinsinden sabit kalsın: hem yakınlaştırma (k) hem de SVG'nin
  // ekrana çizilme ölçeği (ekranOlcek) geri alınır. Aksi hâlde letterbox yüzünden
  // etiketler okunamayacak kadar küçülüyordu (9 birim ≈ 5.5 piksel).
  const px = (hedefPiksel: number) => hedefPiksel / (ekranOlcek * k);

  return (
    <div className="panel">
      <header>
        <h2>İstanbul Raylı Sistem Ağı — Canlı Konum</h2>
        <div className="harita-arac">
          <div className="sekme-grup">
            <button className={tumHatlar ? "aktif" : ""} onClick={() => setTumHatlar(true)}>Tüm ağ</button>
            <button className={!tumHatlar ? "aktif" : ""} onClick={() => setTumHatlar(false)}>İşletilen</button>
          </div>
          <button className={ilceAdlari ? "aktif" : ""} onClick={() => setIlceAdlari(!ilceAdlari)}
                  title="İlçe adlarını göster/gizle">İlçeler</button>
          <div className="sekme-grup">
            <button onClick={() => yakinlas(1.4)} title="Yakınlaştır">+</button>
            <button onClick={() => yakinlas(1 / 1.4)} title="Uzaklaştır">−</button>
            <button onClick={() => setDon({ k: 1, x: 0, y: 0 })} title="Görünümü sıfırla">⟲</button>
          </div>
          <span className="ipucu mono">{k.toFixed(1)}x</span>
          <button className={bilgiAcik ? "aktif" : ""} onClick={() => setBilgiAcik(!bilgiAcik)}
                  title="Kaynak ve kullanım bilgisi">ⓘ</button>
        </div>
      </header>

      <div style={{ overflow: "hidden", borderRadius: 8 }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          onPointerDown={bas}
          onPointerMove={hareket}
          onPointerUp={birak}
          onPointerLeave={birak}
          preserveAspectRatio="xMidYMid meet"
          className="harita-svg"
          style={{ cursor: surukleRef.current.aktif ? "grabbing" : "grab" }}
        >
          <g transform={`translate(${don.x},${don.y}) scale(${k})`}>
            {/* --- zemin: kara parçası (ilçe poligonları). Çizilmeyen yer denizdir:
                    Boğaz, Haliç, Marmara ve Karadeniz kıyıları böyle ortaya çıkar. --- */}
            {cografyaYollari.map((i, idx) => (
              <path key={`c-${idx}`} d={i.d} fillRule="evenodd"
                    fill="var(--kara)" stroke="var(--kara-sinir)" strokeWidth={kal(0.6)}>
                <title>{i.ad}</title>
              </path>
            ))}

            {/* --- ilçe adları (ölçekten bağımsız punto) --- */}
            {ilceAdlari && cografyaYollari.filter((i) => i.buyukluk > 12 || k > 3).map((i, idx) => (
              <text key={`t-${idx}`} x={i.cx} y={i.cy}
                    fontSize={px(Math.min(12 + (k - 1) * 1.5, 17))}
                    fill="var(--ilce-yazi)" textAnchor="middle"
                    stroke="var(--deniz)" strokeWidth={px(2.5)} paintOrder="stroke"
                    style={{ pointerEvents: "none", fontWeight: 600 }}>
                {i.ad}
              </text>
            ))}

            {/* --- hat güzergâhları (gerçek geometri) --- */}
            {gosterilecek.map((h) => {
              const sim = simHatlari.has(h.kod);
              return (
                <g key={h.kod} opacity={vurgu && vurgu !== h.kod ? 0.18 : 1}>
                  {h.cizim.map((parca, i) => (
                    <polyline
                      key={i}
                      points={parca.map(([lon, lat]) => `${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`).join(" ")}
                      fill="none" stroke={h.renk}
                      strokeWidth={kal(sim ? 3 : 1.6)}
                      strokeOpacity={sim ? 0.95 : 0.4}
                      strokeLinecap="round" strokeLinejoin="round"
                    />
                  ))}
                </g>
              );
            })}

            {/* --- istasyonlar --- */}
            {gosterilecek.map((h) => (
              <g key={`i-${h.kod}`} opacity={vurgu && vurgu !== h.kod ? 0.15 : 1}>
                {h.istasyonlar.map((ist) => (
                  <circle key={ist.ad} cx={X(ist.lon)} cy={Y(ist.lat)}
                          r={kal(simHatlari.has(h.kod) ? 4.2 : 2.4)}
                          fill="var(--bg)" stroke={h.renk}
                          strokeWidth={kal(simHatlari.has(h.kod) ? 1.8 : 1.1)}
                          style={{ cursor: "default" }}
                          onMouseEnter={(e) => setIpucu({ tur: "istasyon", ist, hat: h, x: e.clientX, y: e.clientY })}
                          onMouseMove={(e) => setIpucu((p) => p && p.tur === "istasyon" && p.ist.ad === ist.ad
                            ? { ...p, x: e.clientX, y: e.clientY } : p)}
                          onMouseLeave={() => setIpucu(null)} />
                ))}
              </g>
            ))}

            {/* --- istasyon adları: yalnızca yeterince yakınlaşınca --- */}
            {k > 4 && gosterilecek.filter((h) => simHatlari.has(h.kod)).map((h) => (
              <g key={`ia-${h.kod}`} opacity={vurgu && vurgu !== h.kod ? 0.15 : 0.9}>
                {h.istasyonlar.map((ist) => (
                  <text key={ist.ad} x={X(ist.lon) + kal(4)} y={Y(ist.lat) - kal(3)}
                        fontSize={px(10)} fill="var(--text)"
                        stroke="var(--deniz)" strokeWidth={px(2)} paintOrder="stroke"
                        style={{ pointerEvents: "none" }}>
                    {ist.ad}
                  </text>
                ))}
              </g>
            ))}

            {/* --- ray kusuru noktaları (sabit hat arızaları) --- */}
            {ag.ray_kusurlari?.map((kusur, i) => (
              <path key={`k-${i}`}
                    d={`M ${X(kusur.lon)} ${Y(kusur.lat) - kal(6)} L ${X(kusur.lon) + kal(5.5)} ${Y(kusur.lat) + kal(3.5)} L ${X(kusur.lon) - kal(5.5)} ${Y(kusur.lat) + kal(3.5)} Z`}
                    fill="var(--bad)" opacity={0.85} stroke="var(--bg)" strokeWidth={kal(0.8)}>
                <title>{`Ray kusuru · ${kusur.hat} · ${kusur.arasi} (${kusur.siddet}, km ${kusur.km})`}</title>
              </path>
            ))}

            {/* --- trenler (canlı konum, tahmin rengiyle) --- */}
            {[...trenler.entries()].map(([trainId, g]) => {
              const arizali = g.axles.filter((a) => a.yerlesik && a.yerlesik !== "normal");
              const renk = arizali[0] ? SINIF_RENK[arizali[0].yerlesik!] : "var(--ok)";
              const seciliTren = g.axles.some((a) => a.axle === secili);
              const cx = X(g.lon), cy = Y(g.lat);
              return (
                <g key={trainId} style={{ cursor: "pointer" }}
                   onClick={() => { if (!surukleRef.current.kaydi) onSec(g.axles[0].axle); }}
                   onMouseEnter={(e) => {
                     setVurgu(g.axles[0].line_id ?? null);
                     setIpucu({ tur: "tren", trainId, axles: g.axles, x: e.clientX, y: e.clientY });
                   }}
                   onMouseMove={(e) => setIpucu((p) => p && p.tur === "tren" && p.trainId === trainId
                     ? { ...p, x: e.clientX, y: e.clientY } : p)}
                   onMouseLeave={() => { setVurgu(null); setIpucu(null); }}>
                  {arizali.length > 0 && (
                    <circle cx={cx} cy={cy} r={kal(11)} fill={renk} opacity={0.22}>
                      <animate attributeName="opacity" values="0.35;0;0.35" dur="1.8s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <rect x={cx - kal(6)} y={cy - kal(4.5)} width={kal(12)} height={kal(9)} rx={kal(2.5)}
                        fill={renk} stroke={seciliTren ? "var(--text)" : "var(--bg)"}
                        strokeWidth={kal(seciliTren ? 2 : 1.2)} />
                  {g.axles[0]?.konum?.durakta && <circle cx={cx} cy={cy} r={kal(1.6)} fill="var(--bg)" />}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {ipucu?.tur === "istasyon" && (() => {
        const olaylarBurada = (olaylarIstasyonda.get(ipucu.ist.ad) ?? []).slice(0, 5);
        const fazlaSayi = (olaylarIstasyonda.get(ipucu.ist.ad)?.length ?? 0) - olaylarBurada.length;
        return (
          <div className="harita-ipucu" style={ipucuStil(ipucu.x, ipucu.y)}>
            <div className="ipucu-baslik">{ipucu.hat.kod} · {ipucu.ist.ad}</div>
            <div className="ipucu-alt">km {ipucu.ist.km.toFixed(1)}</div>
            {olaylarBurada.length === 0 ? (
              <div className="olay-yok">Bu istasyonda kayıtlı arıza yok.</div>
            ) : (
              <>
                {olaylarBurada.map((o, i) => (
                  <div key={i} className="olay-satir">
                    <i style={{ background: SINIF_RENK[o.yeni] }} />
                    <span>
                      {SINIF_ETIKET[o.yeni]} · {o.tip === "alarm" ? "başladı" : "giderildi"}
                    </span>
                    <span className="saat mono">{o.ts?.slice(11, 19)}</span>
                  </div>
                ))}
                {fazlaSayi > 0 && <div className="olay-yok">+{fazlaSayi} daha</div>}
              </>
            )}
          </div>
        );
      })()}

      {ipucu?.tur === "tren" && (() => {
        const ilk = ipucu.axles[0];
        const arizali = ipucu.axles.filter((a) => a.yerlesik && a.yerlesik !== "normal");
        return (
          <div className="harita-ipucu" style={ipucuStil(ipucu.x, ipucu.y)}>
            <div className="ipucu-baslik">{ipucu.trainId} · {ilk.line_id}</div>
            <div className="ipucu-alt">
              {ilk.konum.durakta ? "İstasyonda: " : "Sonraki: "}{ilk.konum.istasyon ?? "—"}
              {" "}· km {ilk.konum.km.toFixed(2)}
            </div>
            {arizali.length === 0 ? (
              <div className="olay-yok">Tüm dingiller normal.</div>
            ) : (
              arizali.map((a) => (
                <div key={a.axle} className="olay-satir">
                  <i style={{ background: SINIF_RENK[a.yerlesik!] }} />
                  <span className="mono">{a.axle}</span>
                  <span>{SINIF_ETIKET[a.yerlesik!]}</span>
                </div>
              ))
            )}
          </div>
        );
      })()}

      <div className="hat-rozetleri">
        {gosterilecek.filter((h) => simHatlari.has(h.kod)).map((h) => (
          <span key={h.kod} className="hat-rozet" title={`${h.kod} · ${h.kisa_ad}`}
                onMouseEnter={() => setVurgu(h.kod)} onMouseLeave={() => setVurgu(null)}
                style={{ borderColor: h.renk }}>
            <i style={{ background: h.renk }} />{h.kod}
          </span>
        ))}
        <span className="ipucu" style={{ marginLeft: "auto" }}>
          ▲ ray kusuru · ▮ tren · tekerlek: zoom, sürükle: kaydır
        </span>
      </div>

      {bilgiAcik && (
        <div className="aciklama-kutu" style={{ marginTop: 8 }}>
          <b>Kullanım:</b> fare tekerleğiyle yakınlaş/uzaklaş, basılı tutup sürükleyerek kaydır,
          trene tıklayarak o dingili seç. 4x üzerinde istasyon adları görünür.
          {" "}<b>Kaynak:</b> hat güzergâhları, istasyon konumları ve adları <b>İBB Açık Veri
          Portalı</b>'ndaki gerçek veridir; harita zemini <b>geoBoundaries</b> ilçe sınırlarıdır
          (ODbL 1.0). Denizler ayrı bir veri değildir — karanın olmadığı yerdir, Boğaz ve Haliç
          böyle görünür. Ağda yalnızca <b>Metro İstanbul işletmesindeki</b> hatlar vardır;
          Marmaray ve M11 (Ulaştırma Bakanlığı) kapsam dışıdır.
        </div>
      )}
    </div>
  );
}
