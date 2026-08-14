"use client";

import { SINIF_ETIKET, type Olay } from "@/lib/tipler";

export default function OlayGunlugu({ olaylar }: { olaylar: Olay[] }) {
  return (
    <div className="panel">
      <header>
        <h2>Alarm / Olay Günlüğü</h2>
        <span className="ipucu">{olaylar.length} kayıt</span>
      </header>

      {olaylar.length === 0 ? (
        <div className="aciklama-kutu">Henüz sınıf değişimi yok. Model bir dingilin sınıfını değiştirdiğinde burada listelenir.</div>
      ) : (
        <div className="olay-liste">
          {olaylar.map((o, i) => (
            <div key={`${o.ts}-${o.axle}-${i}`} className={`olay ${o.tip}`}>
              <span className="saat mono">{o.ts.slice(11, 19)}</span>
              <span className="aciklama">
                <b className="mono">{o.axle}</b>{" "}
                {o.tip === "alarm" ? (
                  <>→ <b style={{ color: "var(--bad)" }}>{SINIF_ETIKET[o.yeni]}</b></>
                ) : (
                  <>→ <b style={{ color: "var(--ok)" }}>normale döndü</b></>
                )}
                {o.gercek && o.gercek !== o.yeni && (
                  <span style={{ color: "var(--warn)" }}> · gerçek: {SINIF_ETIKET[o.gercek]}</span>
                )}
              </span>
              <span className="sag mono">%{(o.conf * 100).toFixed(0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
