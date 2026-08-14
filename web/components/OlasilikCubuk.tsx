"use client";

import { SINIF_ETIKET, SINIF_RENK, type AxleDurum, type Meta } from "@/lib/tipler";

/** Seçili dingil için modelin softmax olasılık dağılımı + (kör mod kapalıysa) gerçek etiket. */
export default function OlasilikCubuk({ axle, meta }: { axle: AxleDurum | null; meta: Meta | null }) {
  const classes = meta?.classes ?? [];

  return (
    <div className="panel">
      <header>
        <h2>Model Çıktısı — <span className="mono" style={{ color: "var(--accent)" }}>{axle?.axle ?? "—"}</span></h2>
        {axle?.gercek && (
          <span className="ipucu">
            cevap anahtarı: <b style={{ color: SINIF_RENK[axle.gercek] }}>{SINIF_ETIKET[axle.gercek]}</b>
            {axle.severity && axle.severity !== "none" ? ` (${axle.severity})` : ""}
          </span>
        )}
      </header>

      {!axle?.probs ? (
        <div className="aciklama-kutu">Kayan pencere henüz dolmadı ({axle?.doluluk ?? 0}/10 örnek).</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          {classes.map((c, i) => {
            const p = axle.probs![i] ?? 0;
            const secilen = c === axle.pred;
            return (
              <div key={c} style={{ display: "grid", gridTemplateColumns: "120px 1fr 52px", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: secilen ? "var(--text)" : "var(--muted)", fontWeight: secilen ? 600 : 400 }}>
                  {SINIF_ETIKET[c]}
                </span>
                <div className="mini-bar" style={{ height: 9, marginTop: 0 }}>
                  <div style={{ width: `${p * 100}%`, background: SINIF_RENK[c], opacity: secilen ? 1 : 0.45 }} />
                </div>
                <span className="mono" style={{ fontSize: 11, textAlign: "right", color: secilen ? "var(--text)" : "var(--muted)" }}>
                  %{(p * 100).toFixed(1)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
