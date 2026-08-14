"use client";

import { SINIF_ETIKET, SINIF_RENK, type AxleDurum } from "@/lib/tipler";

export default function DingilIzgara({
  axles, secili, onSec, korMod,
}: {
  axles: AxleDurum[];
  secili: string | null;
  onSec: (a: string) => void;
  korMod: boolean;
}) {
  return (
    <div className="panel">
      <header>
        <h2>Dingil Durum Haritası</h2>
        <span className="ipucu">grafiği görmek için bir dingile tıklayın</span>
      </header>

      <div className="dingil-izgara">
        {axles.map((a) => {
          const renk = a.pred ? SINIF_RENK[a.pred] : "var(--muted)";
          const arizali = !!a.pred && a.pred !== "normal";
          const yanlis = !korMod && a.dogru_mu === false;
          return (
            <button
              key={a.axle}
              className={
                "dingil" + (secili === a.axle ? " secili" : "") + (arizali ? " arizali" : "")
              }
              onClick={() => onSec(a.axle)}
            >
              <span className="serit" style={{ background: renk }} />
              {yanlis && <span className="yanlis">yanlış</span>}
              <div className="ad mono">{a.axle}</div>
              <div className="sinif" style={{ color: renk }}>
                {a.hazir ? SINIF_ETIKET[a.pred!] : "pencere doluyor…"}
              </div>
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
  );
}
