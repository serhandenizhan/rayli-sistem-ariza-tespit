"use client";

import { SIDDET_ETIKET, SIDDET_RENK, SINIF_ETIKET, SINIF_RENK,
         type AxleDurum, type Meta } from "@/lib/tipler";

function Cubuklar({ etiketler, olasiliklar, secilen, renkler }: {
  etiketler: string[]; olasiliklar: number[]; secilen?: string;
  renkler: Record<string, string>;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {etiketler.map((c, i) => {
        const p = olasiliklar[i] ?? 0;
        const aktif = c === secilen;
        return (
          <div key={c} style={{ display: "grid", gridTemplateColumns: "112px 1fr 50px", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: aktif ? "var(--text)" : "var(--muted)", fontWeight: aktif ? 600 : 400 }}>
              {c}
            </span>
            <div className="mini-bar" style={{ height: 9, marginTop: 0 }}>
              <div style={{ width: `${p * 100}%`, background: renkler[c] ?? "var(--accent)", opacity: aktif ? 1 : 0.45 }} />
            </div>
            <span className="mono" style={{ fontSize: 11, textAlign: "right", color: aktif ? "var(--text)" : "var(--muted)" }}>
              %{(p * 100).toFixed(1)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Seçili dingil için modelin iki başlığının (arıza tipi + şiddet) softmax dağılımı. */
export default function OlasilikCubuk({ axle, meta }: { axle: AxleDurum | null; meta: Meta | null }) {
  const classes = meta?.classes ?? [];
  const sevClasses = meta?.severity_classes ?? [];

  return (
    <div className="panel">
      <header>
        <h2>Model Çıktısı — <span className="mono" style={{ color: "var(--accent)" }}>{axle?.axle ?? "—"}</span></h2>
        {axle?.gercek && (
          <span className="ipucu">
            cevap anahtarı: <b style={{ color: SINIF_RENK[axle.gercek] }}>{SINIF_ETIKET[axle.gercek]}</b>
            {axle.gercek_severity && axle.gercek_severity !== "none"
              ? ` / ${SIDDET_ETIKET[axle.gercek_severity]}` : ""}
          </span>
        )}
      </header>

      {!axle?.probs ? (
        <div className="aciklama-kutu">Kayan pencere henüz dolmadı ({axle?.doluluk ?? 0}/10 örnek).</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
          <div>
            <div className="alt-baslik">Arıza tipi</div>
            <Cubuklar
              etiketler={classes.map((c) => SINIF_ETIKET[c])}
              olasiliklar={axle.probs}
              secilen={axle.pred ? SINIF_ETIKET[axle.pred] : undefined}
              renkler={Object.fromEntries(classes.map((c) => [SINIF_ETIKET[c], SINIF_RENK[c]]))}
            />
          </div>
          <div>
            <div className="alt-baslik">Arıza şiddeti</div>
            <Cubuklar
              etiketler={sevClasses.map((s) => SIDDET_ETIKET[s])}
              olasiliklar={axle.sev_probs ?? []}
              secilen={axle.severity ? SIDDET_ETIKET[axle.severity] : undefined}
              renkler={Object.fromEntries(sevClasses.map((s) => [SIDDET_ETIKET[s], SIDDET_RENK[s]]))}
            />
            <div className="aciklama-kutu" style={{ marginTop: 10 }}>
              Şiddet, modelin <b>ikinci çıkış başlığıdır</b> (multi-task): aynı gövde hem "hangi
              arıza" hem "ne kadar ciddi" sorusunu yanıtlar.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
