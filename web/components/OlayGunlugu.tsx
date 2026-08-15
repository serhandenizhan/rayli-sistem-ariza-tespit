"use client";

import { SIDDET_ETIKET, SIDDET_RENK, SINIF_ETIKET, type Olay } from "@/lib/tipler";

export default function OlayGunlugu({ olaylar, histerezis }: { olaylar: Olay[]; histerezis: number }) {
  return (
    <div className="panel">
      <header>
        <h2>Alarm / Olay Günlüğü</h2>
        <span className="ipucu">{olaylar.length} kayıt · histerezis {histerezis} tick</span>
      </header>

      {olaylar.length === 0 ? (
        <div className="aciklama-kutu">
          Henüz yerleşik sınıf değişimi yok. Bir dingilin sınıfı <b>{histerezis} ardışık tick</b>
          {" "}boyunca değişik kalırsa buraya alarm düşer.
        </div>
      ) : (
        <div className="olay-liste">
          {olaylar.map((o, i) => (
            <div key={`${o.ts}-${o.axle}-${i}`} className={`olay ${o.tip}`}>
              <span className="saat mono">{o.ts.slice(11, 19)}</span>
              <span className="aciklama">
                <b className="mono">{o.line_id ? `${o.line_id} ` : ""}{o.axle}</b>{" "}
                {o.tip === "alarm" ? (
                  <>→ <b style={{ color: "var(--bad)" }}>{SINIF_ETIKET[o.yeni]}</b>
                    {o.severity && o.severity !== "none" && (
                      <span style={{ color: SIDDET_RENK[o.severity] }}> ({SIDDET_ETIKET[o.severity]})</span>
                    )}</>
                ) : (
                  <>→ <b style={{ color: "var(--ok)" }}>normale döndü</b></>
                )}
                {o.istasyon && <span className="ipucu"> · {o.istasyon}</span>}
                {o.tekrar_no && o.tekrar_no > 1 && (
                  <span className="tekrar-rozet"
                        title={`Aynı sabit kusur (${o.kusur_arasi ?? o.kusur_id}) yeniden tespit edildi`}>
                    ↻ {o.tekrar_no}. tespit
                  </span>
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
