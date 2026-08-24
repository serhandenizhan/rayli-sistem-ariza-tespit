"use client";

export type Sekme = "izleme" | "dingiller" | "dogrulama" | "bildirimler" | "gecmis";

export const SEKMELER: { id: Sekme; ad: string; ikon: string }[] = [
  { id: "izleme", ad: "Canlı İzleme", ikon: "🗺" },
  { id: "dingiller", ad: "Dingiller", ikon: "🔧" },
  { id: "dogrulama", ad: "Doğrulama", ikon: "🎯" },
  { id: "bildirimler", ad: "Metin Bildirimleri", ikon: "📝" },
  { id: "gecmis", ad: "Geçmiş", ikon: "🗄" },
];

/** Dikey sekme navigasyonu — eskiden üst barda yatay yer kaplayan sekmeler buraya taşındı. */
export default function KenarCubugu({
  sekme, onSekme, alarmSayisi,
}: {
  sekme: Sekme;
  onSekme: (s: Sekme) => void;
  alarmSayisi: number;
}) {
  return (
    <aside className="kenar-cubugu">
      <div className="kenar-marka">
        <span className="kenar-marka-ikon">🚇</span>
        <span className="kenar-marka-ad">Raylı Sistem</span>
      </div>
      <nav className="sekmeler-dikey">
        {SEKMELER.map((s) => (
          <button key={s.id} className={"sekme" + (sekme === s.id ? " aktif" : "")}
                  onClick={() => onSekme(s.id)}>
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
