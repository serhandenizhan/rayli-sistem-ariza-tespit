"use client";

import { useEffect, useState } from "react";

export type Sekme = "izleme" | "dingiller" | "dogrulama" | "bildirimler" | "gecmis";

export const SEKMELER: { id: Sekme; ad: string; ikon: string }[] = [
  { id: "izleme", ad: "Canlı İzleme", ikon: "🗺" },
  { id: "dingiller", ad: "Dingiller", ikon: "🔧" },
  { id: "dogrulama", ad: "Doğrulama", ikon: "🎯" },
  { id: "bildirimler", ad: "Metin Bildirimleri", ikon: "📝" },
  { id: "gecmis", ad: "Geçmiş", ikon: "🗄" },
];

const DEPOLAMA_ANAHTARI = "kenar-cubugu-daraltilmis";

/** Dikey sekme navigasyonu — eskiden üst barda yatay yer kaplayan sekmeler buraya taşındı.
 *  Daraltma tercihi localStorage'da tutulur, sayfa yenilendiğinde korunur. */
export default function KenarCubugu({
  sekme, onSekme, alarmSayisi,
}: {
  sekme: Sekme;
  onSekme: (s: Sekme) => void;
  alarmSayisi: number;
}) {
  const [daraltilmis, setDaraltilmis] = useState(false);

  useEffect(() => {
    setDaraltilmis(localStorage.getItem(DEPOLAMA_ANAHTARI) === "1");
  }, []);

  const degistir = () => {
    setDaraltilmis((d) => {
      localStorage.setItem(DEPOLAMA_ANAHTARI, d ? "0" : "1");
      return !d;
    });
  };

  return (
    <aside className={"kenar-cubugu" + (daraltilmis ? " daralt" : "")}>
      <div className="kenar-marka">
        <span className="kenar-marka-ikon">🚇</span>
        <span className="kenar-marka-ad">Raylı Sistem</span>
        <button className="kenar-daralt-dugme" onClick={degistir}
                title={daraltilmis ? "Kenar çubuğunu genişlet" : "Kenar çubuğunu daralt"}>
          {daraltilmis ? "»" : "«"}
        </button>
      </div>
      <nav className="sekmeler-dikey">
        {SEKMELER.map((s) => (
          <button key={s.id} className={"sekme" + (sekme === s.id ? " aktif" : "")}
                  onClick={() => onSekme(s.id)} title={daraltilmis ? s.ad : undefined}>
            <span className="sekme-ikon">{s.ikon}</span>
            <span className="sekme-ad">{s.ad}</span>
            {s.id === "izleme" && alarmSayisi > 0 && (
              <span className="sekme-rozet">{alarmSayisi}</span>
            )}
          </button>
        ))}
      </nav>
    </aside>
  );
}
