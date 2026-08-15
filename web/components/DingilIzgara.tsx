"use client";

import { SIDDET_ETIKET, SIDDET_RENK, SINIF_ETIKET, SINIF_RENK, type AxleDurum } from "@/lib/tipler";

export default function DingilIzgara({
  axles, secili, onSec, korMod,
}: {
  axles: AxleDurum[];
  secili: string | null;
  onSec: (a: string) => void;
  korMod: boolean;
}) {
  // Hat bazında grupla — gerçek metro ağında her tren bir hatta ait
  const hatlar = new Map<string, AxleDurum[]>();
  for (const a of axles) {
    const k = a.line_id ?? "?";
    hatlar.set(k, [...(hatlar.get(k) ?? []), a]);
  }

  return (
    <div className="panel">
      <header>
        <h2>Dingil Durum Haritası</h2>
        <span className="ipucu">grafiği görmek için bir dingile tıklayın · rozet = şiddet</span>
      </header>

      {[...hatlar.entries()].map(([hat, liste]) => (
        <div key={hat} className="hat-blok">
          <div className="hat-baslik">
            <span className="hat-kod">{hat}</span>
            <span className="mono">{liste[0]?.train_id}</span>
            <span className="ipucu">
              {liste[0]?.konum?.durakta ? "🚉 istasyonda" : "→"} {liste[0]?.konum?.istasyon ?? ""}
              {" · "}km {liste[0]?.konum?.km?.toFixed(2)}
            </span>
          </div>

          <div className="dingil-izgara">
            {liste.map((a) => {
              const gosterilen = a.yerlesik ?? a.pred;
              const renk = gosterilen ? SINIF_RENK[gosterilen] : "var(--muted)";
              const arizali = !!gosterilen && gosterilen !== "normal";
              const yanlis = !korMod && a.dogru_mu === false;
              return (
                <button
                  key={a.axle}
                  className={"dingil" + (secili === a.axle ? " secili" : "") + (arizali ? " arizali" : "")}
                  onClick={() => onSec(a.axle)}
                >
                  <span className="serit" style={{ background: renk }} />
                  {yanlis && <span className="yanlis">yanlış</span>}
                  <div className="ad mono">{a.wagon_id}-{a.axle_id}</div>
                  <div className="sinif" style={{ color: renk }}>
                    {a.hazir ? SINIF_ETIKET[gosterilen!] : "pencere doluyor…"}
                    {!a.kararli && a.hazir && <span className="bekliyor" title="histerezis bekleniyor">⏳</span>}
                    {a.belirsiz && (
                      <span className="bekliyor"
                            title={`Model kararsız (entropi ${a.entropi?.toFixed(2)}) — bu tahmin alarm üretmez`}>❔</span>
                    )}
                  </div>
                  {a.hazir && a.severity && a.severity !== "none" && (
                    <span className="siddet-rozet" style={{ color: SIDDET_RENK[a.severity],
                                                            borderColor: SIDDET_RENK[a.severity] }}>
                      {SIDDET_ETIKET[a.severity]}
                    </span>
                  )}
                  <div className="conf mono">
                    {a.hazir
                      ? `güven %${((a.conf ?? 0) * 100).toFixed(1)}${
                          !korMod && a.gercek ? ` · gerçek: ${SINIF_ETIKET[a.gercek]}` : ""
                        }`
                      : `${a.doluluk}/10 örnek`}
                  </div>
                  <div className="mini-bar">
                    <div style={{ width: `${(a.hazir ? (a.conf ?? 0) : a.doluluk / 10) * 100}%`, background: renk }} />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
