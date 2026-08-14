"use client";

import type { Meta, TickPaketi } from "@/lib/tipler";

const HIZLAR = [1, 2, 5, 10, 25, 50];

export default function Kontroller({
  meta, tick, bagli, kontrol, oynatiliyor,
}: {
  meta: Meta | null;
  tick: TickPaketi | null;
  bagli: boolean;
  kontrol: (action: string, value?: number) => void;
  oynatiliyor: boolean;
}) {
  const toplam = tick?.toplam_tick ?? meta?.toplam_tick ?? 0;
  const simdi = tick ? tick.tick + 1 : 0;
  const yuzde = toplam ? (simdi / toplam) * 100 : 0;
  const hiz = tick?.hiz ?? 5;
  const saat = tick?.timestamp?.slice(11, 19) ?? "--:--:--";

  return (
    <div className="ust-bar">
      <div>
        <h1>🚄 Raylı Sistem — Canlı Arıza İzleme</h1>
        <div className="alt">
          CNN + LSTM · {meta?.window ?? 10} adımlık pencere (20 sn) · {meta?.axles.length ?? 0} dingil ·
          etiketsiz test akışı
        </div>
      </div>

      <div className="rozet">
        <span className={"nokta" + (bagli && oynatiliyor ? " canli" : "")} />
        {bagli ? (oynatiliyor ? "CANLI" : "DURAKLADI") : "BAĞLANTI YOK"}
      </div>

      <div className="rozet mono">🕑 {saat}</div>
      <div className="rozet mono">tick {simdi}/{toplam}</div>

      <div className="ilerleme"><div style={{ width: `${yuzde}%` }} /></div>

      <div className="bosluk" />

      <button className="ikon" onClick={() => kontrol("pause")} disabled={!oynatiliyor}>
        ⏸ Duraklat
      </button>
      <button className="ikon" onClick={() => kontrol("play")} disabled={oynatiliyor}>
        ▶ Devam
      </button>
      <button className="ikon" onClick={() => kontrol("reset")}>⟲ Baştan</button>

      <div className="hiz-grup">
        {HIZLAR.map((h) => (
          <button key={h} className={hiz === h ? "aktif" : ""} onClick={() => kontrol("speed", h)}>
            {h}x
          </button>
        ))}
      </div>
    </div>
  );
}
