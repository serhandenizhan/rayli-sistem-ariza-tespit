"use client";

import type { Meta, TickPaketi } from "@/lib/tipler";

const HIZLAR = [1, 2, 5, 10, 25, 50];
const HISTEREZIS_SECENEK = [1, 2, 3, 5, 8];

export default function Kontroller({
  meta, tick, bagli, kontrol, oynatiliyor, korMod, histerezis,
}: {
  meta: Meta | null;
  tick: TickPaketi | null;
  bagli: boolean;
  kontrol: (action: string, value?: number | boolean) => void;
  oynatiliyor: boolean;
  korMod: boolean;
  histerezis: number;
}) {
  const toplam = tick?.toplam_tick ?? meta?.toplam_tick ?? 0;
  const simdi = tick ? tick.tick + 1 : 0;
  const yuzde = toplam ? (simdi / toplam) * 100 : 0;
  const hiz = tick?.hiz ?? 5;
  const saat = tick?.timestamp?.slice(11, 19) ?? "--:--:--";

  return (
    <div className="ust-bar">
      <div className="baslik-blok">
        <h1>🚇 İstanbul Raylı Sistem — Canlı Arıza İzleme</h1>
        <div className="alt">
          CNN + LSTM (çok görevli: tip + şiddet) · {meta?.window ?? 10} adımlık pencere (20 sn) ·
          {" "}{meta?.axles.length ?? 0} dingil · etiketsiz akış · kaynak: {meta?.kaynak ?? "csv"}
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

      <button className="ikon" onClick={() => kontrol("pause")} disabled={!oynatiliyor}>⏸ Duraklat</button>
      <button className="ikon" onClick={() => kontrol("play")} disabled={oynatiliyor}>▶ Devam</button>
      <button className="ikon" onClick={() => kontrol("reset")}>⟲ Baştan</button>

      <div className="kontrol-grup">
        <label>Hız</label>
        <div className="hiz-grup">
          {HIZLAR.map((h) => (
            <button key={h} className={hiz === h ? "aktif" : ""} onClick={() => kontrol("speed", h)}>
              {h}x
            </button>
          ))}
        </div>
      </div>

      <div className="kontrol-grup">
        <label title="Bir sınıfın 'yerleşik' sayılması için gereken ardışık tick sayısı — tek tick'lik sıçramaları bastırır">
          Histerezis
        </label>
        <div className="hiz-grup">
          {HISTEREZIS_SECENEK.map((h) => (
            <button key={h} className={histerezis === h ? "aktif" : ""}
                    onClick={() => kontrol("histerezis", h)}>
              {h}
            </button>
          ))}
        </div>
      </div>

      <div className="kontrol-grup">
        <label title="Açıkken cevap anahtarı arayüze hiç gönderilmez — tam kör demo">Kör mod</label>
        <button className={korMod ? "aktif" : ""} onClick={() => kontrol("kor_mod", !korMod)}>
          {korMod ? "🙈 Açık" : "👁 Kapalı"}
        </button>
      </div>
    </div>
  );
}
