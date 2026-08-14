"use client";

import { SINIF_ETIKET, type Meta, type Metrikler } from "@/lib/tipler";

/** Canlı doğrulama: tahminler üretildikten SONRA cevap anahtarıyla eşleştirilerek
 *  hesaplanan karmaşıklık matrisi, sınıf bazlı metrikler ve doğruluk trendi. */
export default function DogrulamaPaneli({ metrikler, meta }: { metrikler?: Metrikler; meta: Meta | null }) {
  const classes = meta?.classes ?? [];
  const cm = metrikler?.confusion;
  const trend = (metrikler?.trend ?? []).filter((p) => p.acc != null) as { tick: number; acc: number }[];

  if (metrikler?.kor_mod) {
    return (
      <div className="panel">
        <header><h2>Canlı Doğrulama</h2></header>
        <div className="aciklama-kutu">
          <b>Kör mod açık.</b> Cevap anahtarı sunucudan hiç gönderilmiyor; ekranda yalnızca modelin
          tahminleri var. Doğrulamayı kapatmak/açmak için sunucuyu <code>--kor-mod</code> olmadan başlatın.
        </div>
      </div>
    );
  }

  const maks = cm ? Math.max(...cm.flat()) : 0;
  const W = 320, H = 60;

  return (
    <div className="panel">
      <header>
        <h2>Canlı Doğrulama (cevap anahtarına karşı)</h2>
        <span className="ipucu">{metrikler?.degerlendirilen ?? 0} sekans</span>
      </header>

      <div className="aciklama-kutu" style={{ marginBottom: 12 }}>
        Akan pakette etiket <b>yoktur</b>; model tahmini ürettikten sonra sunucu tarafında ayrı tutulan
        <b> cevap anahtarı</b> (<span className="mono">rayli_sistem_test_cevap_anahtari.csv</span>) ile
        eşleştirilip skor hesaplanır. Yani doğrulama, tahmini hiçbir şekilde etkilemez.
      </div>

      {trend.length > 1 && (
        <>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
            Doğruluk trendi (son {trend.length} tick)
          </div>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" style={{ marginBottom: 12 }}>
            <line x1={0} x2={W} y1={H * 0.1} y2={H * 0.1} stroke="var(--line)" strokeDasharray="3 4" />
            <path
              d={trend
                .map((p, i) => {
                  const x = (i * W) / (trend.length - 1);
                  const y = H - Math.min(Math.max((p.acc - 0.8) / 0.2, 0), 1) * (H - 6) - 3;
                  return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
                })
                .join(" ")}
              fill="none" stroke="var(--ok)" strokeWidth={1.8} />
          </svg>
        </>
      )}

      {cm && (
        <>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
            Karmaşıklık matrisi — satır: gerçek, sütun: tahmin
          </div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th></th>
                  {classes.map((c) => <th key={c} style={{ textAlign: "center" }}>{c.slice(0, 5)}</th>)}
                </tr>
              </thead>
              <tbody>
                {cm.map((satir, i) => (
                  <tr key={i}>
                    <td className="mono" style={{ fontSize: 11 }}>{classes[i]}</td>
                    {satir.map((v, j) => (
                      <td key={j} className="cm-hucre mono"
                        style={{
                          background: v === 0 ? "transparent"
                            : i === j ? `rgba(47,191,113,${0.15 + 0.6 * (v / (maks || 1))})`
                            : `rgba(255,77,94,${0.2 + 0.6 * (v / (maks || 1))})`,
                          color: v === 0 ? "var(--muted)" : "var(--text)",
                        }}>
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {metrikler?.per_class && (
        <table style={{ marginTop: 14 }}>
          <thead>
            <tr><th>Sınıf</th><th>Precision</th><th>Recall</th><th>F1</th><th>Örnek</th></tr>
          </thead>
          <tbody>
            {classes.map((c) => {
              const s = metrikler.per_class![c];
              if (!s) return null;
              return (
                <tr key={c}>
                  <td>{SINIF_ETIKET[c]}</td>
                  <td className="mono">{s.precision.toFixed(3)}</td>
                  <td className="mono">{s.recall.toFixed(3)}</td>
                  <td className="mono" style={{ color: s.f1 >= 0.9 ? "var(--ok)" : s.f1 >= 0.75 ? "var(--warn)" : "var(--bad)" }}>
                    {s.f1.toFixed(3)}
                  </td>
                  <td className="mono">{s.support}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
