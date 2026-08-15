"use client";

import type { Meta, TickPaketi } from "@/lib/tipler";

const HIZLAR = [1, 2, 5, 10, 25, 50];
const HISTEREZIS_SECENEK = [1, 2, 3, 5, 8];
// Normalize entropi eşiği: düşük = katı (çok tahmini belirsiz say), yüksek = gevşek
const BELIRSIZLIK_SECENEK = [0.2, 0.35, 0.5, 1.0];

export type Sekme = "izleme" | "dingiller" | "dogrulama" | "gecmis" | "testler";

export const SEKMELER: { id: Sekme; ad: string; ikon: string }[] = [
  { id: "izleme", ad: "Canlı İzleme", ikon: "🗺" },
  { id: "dingiller", ad: "Dingiller & Sensörler", ikon: "🔧" },
  { id: "dogrulama", ad: "Doğrulama & Model", ikon: "🎯" },
  { id: "gecmis", ad: "Geçmiş", ikon: "🗄" },
  { id: "testler", ad: "Testler", ikon: "🧪" },
];

export default function Kontroller({
  meta, tick, bagli, kontrol, oynatiliyor, korMod, histerezis, sekme, onSekme, alarmSayisi,
  belirsizlikEsigi,
}: {
  meta: Meta | null;
  tick: TickPaketi | null;
  bagli: boolean;
  kontrol: (action: string, value?: number | boolean) => void;
  oynatiliyor: boolean;
  korMod: boolean;
  histerezis: number;
  sekme: Sekme;
  onSekme: (s: Sekme) => void;
  alarmSayisi: number;
  belirsizlikEsigi: number;
}) {
  const toplam = tick?.toplam_tick ?? meta?.toplam_tick ?? 0;
  const simdi = tick ? tick.tick + 1 : 0;
  const yuzde = toplam ? (simdi / toplam) * 100 : 0;
  const hiz = tick?.hiz ?? 5;
  const saat = tick?.timestamp?.slice(11, 19) ?? "--:--:--";

  return (
    <div className="ust-bar">
      {/* --- 1. satır: kimlik, durum, akış kontrolü --- */}
      <div className="ust-satir">
        <div className="baslik-blok">
          <h1>🚇 İstanbul Raylı Sistem — Canlı Arıza İzleme</h1>
          <div className="alt">
            CNN+LSTM · tip + şiddet · {meta?.axles.length ?? 0} dingil · etiketsiz akış
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

        {/* Oynat düğmesinin etiketi duruma göre değişir: akış hiç ilerlememişse "Başlat",
            duraklatılmış bir akışta ise "Devam". Sıfırla, akışı baştan alır. */}
        <button className="ikon" onClick={() => kontrol("pause")} disabled={!oynatiliyor}>
          ⏸ Duraklat
        </button>
        <button className="ikon" onClick={() => kontrol("play")} disabled={oynatiliyor}>
          ▶ {simdi <= 1 ? "Başlat" : "Devam"}
        </button>
        <button className="ikon" onClick={() => kontrol("reset")}>⟲ Sıfırla</button>
      </div>

      {/* --- 2. satır: sekmeler (sol) + simülasyon ayarları (sağ) --- */}
      <div className="ust-satir alt-satir">
        <nav className="sekmeler">
          {SEKMELER.map((s) => (
            <button key={s.id} className={"sekme" + (sekme === s.id ? " aktif" : "")}
                    onClick={() => onSekme(s.id)}>
              <span className="sekme-ikon">{s.ikon}</span> {s.ad}
              {s.id === "izleme" && alarmSayisi > 0 && (
                <span className="sekme-rozet">{alarmSayisi}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="bosluk" />

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
          <label title="Normalize entropi eşiği: bu değerin üstündeki tahminler 'belirsiz' sayılır ve alarm üretemez. 1.0 = kapalı">
            Belirsizlik
          </label>
          <div className="hiz-grup">
            {BELIRSIZLIK_SECENEK.map((b) => (
              <button key={b} className={Math.abs(belirsizlikEsigi - b) < 0.01 ? "aktif" : ""}
                      onClick={() => kontrol("belirsizlik", b)}>
                {b === 1.0 ? "kapalı" : b.toFixed(2)}
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
    </div>
  );
}
