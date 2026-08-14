"use client";

import { useState } from "react";
import { SINIF_ETIKET, SINIF_RENK } from "@/lib/tipler";

type Nokta = { t: number; s: Record<string, number>; pred?: string };

const GRUPLAR: Record<string, { kolon: string; ad: string; renk: string }[]> = {
  "Titreşim (RMS/tepe)": [
    { kolon: "vib_x_rms_g", ad: "vib X", renk: "#4ea8ff" },
    { kolon: "vib_y_rms_g", ad: "vib Y", renk: "#7de2d1" },
    { kolon: "vib_z_rms_g", ad: "vib Z", renk: "#b06cff" },
    { kolon: "vib_peak_g", ad: "tepe", renk: "#ffb020" },
  ],
  "Titreşim karakteri": [
    { kolon: "vib_kurtosis", ad: "kurtosis", renk: "#ff7a45" },
    { kolon: "vib_crest_factor", ad: "crest faktör", renk: "#4ea8ff" },
    { kolon: "vib_dom_freq_hz", ad: "baskın frek.", renk: "#7de2d1" },
    { kolon: "acoustic_rms", ad: "akustik RMS", renk: "#ff4d97" },
  ],
  Sıcaklık: [
    { kolon: "axle_box_temp_c", ad: "dingil yatağı", renk: "#ff7a45" },
    { kolon: "brake_temp_c", ad: "fren", renk: "#b06cff" },
    { kolon: "motor_temp_c", ad: "motor", renk: "#ff4d97" },
    { kolon: "ambient_temp_c", ad: "ortam", renk: "#8798b3" },
  ],
  "Motor & sürüş": [
    { kolon: "motor_current_a", ad: "akım (A)", renk: "#ffb020" },
    { kolon: "motor_voltage_v", ad: "gerilim (V)", renk: "#4ea8ff" },
    { kolon: "speed_kmh", ad: "hız (km/s)", renk: "#7de2d1" },
    { kolon: "load_ton", ad: "yük (ton)", renk: "#8798b3" },
  ],
};

const W = 900, H = 210, PAD_L = 8, PAD_R = 8, PAD_T = 10, PAD_B = 8, BANT = 14;

export default function SensorGrafik({ axle, gecmis }: { axle: string | null; gecmis: Nokta[] }) {
  const [grup, setGrup] = useState<string>(Object.keys(GRUPLAR)[0]);
  const seriler = GRUPLAR[grup];

  const n = gecmis.length;
  const x = (i: number) => PAD_L + (n <= 1 ? 0 : (i * (W - PAD_L - PAD_R)) / (n - 1));

  const yol = (kolon: string) => {
    const vals = gecmis.map((p) => p.s?.[kolon] ?? 0);
    const min = Math.min(...vals), max = Math.max(...vals);
    const araliık = max - min || 1;
    return vals
      .map((v, i) => {
        const y = PAD_T + (1 - (v - min) / araliık) * (H - PAD_T - PAD_B - BANT - 6);
        return `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  };

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
        <div className="aciklama-kutu">Veri bekleniyor… (akış başladığında son {90} tick burada çizilir)</div>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
          {[0.25, 0.5, 0.75].map((f) => (
            <line key={f} x1={PAD_L} x2={W - PAD_R}
              y1={PAD_T + f * (H - PAD_T - PAD_B - BANT - 6)} y2={PAD_T + f * (H - PAD_T - PAD_B - BANT - 6)}
              stroke="var(--line)" strokeWidth={1} strokeDasharray="3 5" />
          ))}

          {seriler.map((s) => (
            <path key={s.kolon} d={yol(s.kolon)} fill="none" stroke={s.renk} strokeWidth={1.7}
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
        </svg>
      )}

      <div className="efsane" style={{ marginTop: 8 }}>
        {seriler.map((s) => {
          const son = gecmis.length ? gecmis[gecmis.length - 1].s?.[s.kolon] : undefined;
          return (
            <span key={s.kolon}>
              <i style={{ background: s.renk }} />
              {s.ad}: <b className="mono" style={{ color: "var(--text)" }}>{son?.toFixed(2) ?? "—"}</b>
            </span>
          );
        })}
        <span style={{ marginLeft: "auto" }}>alt şerit = modelin o andaki tahmini</span>
      </div>
      <div className="aciklama-kutu" style={{ marginTop: 8 }}>
        Seriler ortak eksende görünsün diye pencere içi <b>min–max normalize</b> edilmiştir; gerçek
        değerler açıklamada anlık olarak gösterilir.
      </div>
    </div>
  );
}
