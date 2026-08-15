"use client";

import { useRef, useState } from "react";
import { SINIF_ETIKET, SINIF_RENK } from "@/lib/tipler";

type Nokta = { t: number; s: Record<string, number>; pred?: string };

const GRUPLAR: Record<string, { kolon: string; ad: string; birim: string; renk: string }[]> = {
  "Titreşim (RMS/tepe)": [
    { kolon: "vib_x_rms_g", ad: "vib X", birim: "g", renk: "#4ea8ff" },
    { kolon: "vib_y_rms_g", ad: "vib Y", birim: "g", renk: "#7de2d1" },
    { kolon: "vib_z_rms_g", ad: "vib Z", birim: "g", renk: "#b06cff" },
    { kolon: "vib_peak_g", ad: "tepe", birim: "g", renk: "#ffb020" },
  ],
  "Titreşim karakteri": [
    { kolon: "vib_kurtosis", ad: "kurtosis", birim: "", renk: "#ff7a45" },
    { kolon: "vib_crest_factor", ad: "crest faktör", birim: "", renk: "#4ea8ff" },
    { kolon: "vib_dom_freq_hz", ad: "baskın frek.", birim: "Hz", renk: "#7de2d1" },
    { kolon: "acoustic_rms", ad: "akustik RMS", birim: "", renk: "#ff4d97" },
  ],
  Sıcaklık: [
    { kolon: "axle_box_temp_c", ad: "dingil yatağı", birim: "°C", renk: "#ff7a45" },
    { kolon: "brake_temp_c", ad: "fren", birim: "°C", renk: "#b06cff" },
    { kolon: "motor_temp_c", ad: "motor", birim: "°C", renk: "#ff4d97" },
    { kolon: "ambient_temp_c", ad: "ortam", birim: "°C", renk: "#8798b3" },
  ],
  "Motor & sürüş": [
    { kolon: "motor_current_a", ad: "akım", birim: "A", renk: "#ffb020" },
    { kolon: "motor_voltage_v", ad: "gerilim", birim: "V", renk: "#4ea8ff" },
    { kolon: "speed_kmh", ad: "hız", birim: "km/s", renk: "#7de2d1" },
    { kolon: "load_ton", ad: "yük", birim: "ton", renk: "#8798b3" },
  ],
};

const W = 900, H = 210, PAD_L = 8, PAD_R = 8, PAD_T = 10, PAD_B = 8, BANT = 14;
const CIZIM_ALT = H - PAD_B - BANT - 6;

export default function SensorGrafik({ axle, gecmis }: { axle: string | null; gecmis: Nokta[] }) {
  const [grup, setGrup] = useState<string>(Object.keys(GRUPLAR)[0]);
  const [imlec, setImlec] = useState<number | null>(null);   // imlecin gösterdiği tick indeksi
  const sarmalRef = useRef<HTMLDivElement>(null);
  const seriler = GRUPLAR[grup];

  const n = gecmis.length;
  const x = (i: number) => PAD_L + (n <= 1 ? 0 : (i * (W - PAD_L - PAD_R)) / (n - 1));

  // Her seri kendi min-max'ine göre normalize edilir; ölçekleri de saklıyoruz ki
  // imleç konumundaki noktayı doğru y'de işaretleyebilelim.
  const olcekler = seriler.map((s) => {
    const vals = gecmis.map((p) => p.s?.[s.kolon] ?? 0);
    const min = Math.min(...vals), max = Math.max(...vals);
    return { min, aralik: max - min || 1, vals };
  });

  const y = (deger: number, i: number) =>
    PAD_T + (1 - (deger - olcekler[i].min) / olcekler[i].aralik) * (CIZIM_ALT - PAD_T);

  const yol = (i: number) =>
    olcekler[i].vals
      .map((v, j) => `${j === 0 ? "M" : "L"}${x(j).toFixed(1)},${y(v, i).toFixed(1)}`)
      .join(" ");

  /** Fare hareketinde en yakın tick indeksini bul (grafik preserveAspectRatio="none"
   *  olduğu için x ekseni doğrusal eşlenir). */
  const fareHareket = (e: React.MouseEvent<SVGSVGElement>) => {
    if (n < 2) return;
    const kutu = e.currentTarget.getBoundingClientRect();
    const vbX = ((e.clientX - kutu.left) / kutu.width) * W;
    const oran = (vbX - PAD_L) / (W - PAD_L - PAD_R);
    setImlec(Math.max(0, Math.min(n - 1, Math.round(oran * (n - 1)))));
  };

  const secilen = imlec != null ? gecmis[imlec] : null;
  // Son değer varsayılan; imleç varken imlecin gösterdiği an
  const gosterilen = secilen ?? (n ? gecmis[n - 1] : null);

  return (
    <div className="panel">
      <header>
        <h2>Sensör Akışı — <span className="mono" style={{ color: "var(--accent)" }}>{axle ?? "—"}</span></h2>
        <div className="sekme-grup">
          {Object.keys(GRUPLAR).map((g) => (
            <button key={g} className={g === grup ? "aktif" : ""} onClick={() => setGrup(g)}>{g}</button>
          ))}
        </div>
      </header>

      {n < 2 ? (
        <div className="aciklama-kutu">Veri bekleniyor… (akış başladığında son 90 tick burada çizilir)</div>
      ) : (
        <div className="grafik-sarmal" ref={sarmalRef}>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none"
               onMouseMove={fareHareket} onMouseLeave={() => setImlec(null)}
               style={{ cursor: "crosshair" }}>
            {[0.25, 0.5, 0.75].map((f) => (
              <line key={f} x1={PAD_L} x2={W - PAD_R}
                y1={PAD_T + f * (CIZIM_ALT - PAD_T)} y2={PAD_T + f * (CIZIM_ALT - PAD_T)}
                stroke="var(--line)" strokeWidth={1} strokeDasharray="3 5" />
            ))}

            {seriler.map((s, i) => (
              <path key={s.kolon} d={yol(i)} fill="none" stroke={s.renk} strokeWidth={1.7}
                strokeLinejoin="round" strokeLinecap="round" opacity={0.95} />
            ))}

            {/* Model tahmini şeridi: her tick'te modelin o dingil için verdiği sınıf */}
            {gecmis.map((p, i) => (
              <rect key={i} x={x(i) - (W - PAD_L - PAD_R) / (2 * (n - 1))}
                width={Math.max((W - PAD_L - PAD_R) / (n - 1), 1.5)}
                y={H - BANT} height={BANT - 2}
                fill={p.pred ? SINIF_RENK[p.pred] : "var(--line)"}
                opacity={p.pred === "normal" ? 0.28 : 0.95} />
            ))}

            {/* İmleç: dikey kılavuz + o andaki değerlerin üzerinde nokta */}
            {imlec != null && (
              <g pointerEvents="none">
                <line x1={x(imlec)} x2={x(imlec)} y1={PAD_T} y2={H - 2}
                      stroke="var(--text)" strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
                {seriler.map((s, i) => (
                  <circle key={s.kolon} cx={x(imlec)} cy={y(olcekler[i].vals[imlec], i)} r={3}
                          fill={s.renk} stroke="var(--panel)" strokeWidth={1.5} />
                ))}
              </g>
            )}
          </svg>

          {/* İmleç kutusu: o andaki gerçek (normalize edilmemiş) değerler */}
          {imlec != null && secilen && (
            <div className="grafik-ipucu"
                 style={{
                   left: `${(x(imlec) / W) * 100}%`,
                   transform: x(imlec) > W * 0.6 ? "translateX(-104%)" : "translateX(4%)",
                 }}>
              <div className="ipucu-baslik">
                tick {secilen.t + 1}
                {secilen.pred && (
                  <span style={{ color: SINIF_RENK[secilen.pred] }}> · {SINIF_ETIKET[secilen.pred]}</span>
                )}
              </div>
              {seriler.map((s) => (
                <div key={s.kolon} className="ipucu-satir">
                  <i style={{ background: s.renk }} />
                  <span className="ad">{s.ad}</span>
                  <span className="mono deger">
                    {(secilen.s?.[s.kolon] ?? 0).toFixed(2)}{s.birim && ` ${s.birim}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="efsane" style={{ marginTop: 8 }}>
        {seriler.map((s) => (
          <span key={s.kolon}>
            <i style={{ background: s.renk }} />
            {s.ad}: <b className="mono" style={{ color: "var(--text)" }}>
              {gosterilen?.s?.[s.kolon]?.toFixed(2) ?? "—"}
            </b>{s.birim && <span style={{ color: "var(--muted)" }}> {s.birim}</span>}
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>
          {imlec != null ? "imleçteki an" : "son değer"} · alt şerit = model tahmini
        </span>
      </div>
      <div className="aciklama-kutu" style={{ marginTop: 8 }}>
        Seriler ortak eksende görünsün diye pencere içi <b>min–max normalize</b> edilmiştir;
        gerçek değerler yukarıda ve imleç kutusunda gösterilir. Grafiğin üzerine gelerek
        herhangi bir andaki değerleri okuyabilirsiniz.
      </div>
    </div>
  );
}
