"use client";

import type { AxleDurum, Meta } from "@/lib/tipler";

/**
 * Denetimsiz anomali tespiti (autoencoder) — 6 sınıflık denetimli modeli TAMAMLAYAN
 * ayrı bir katman. Normal verilerle eğitilmiştir; bir pencereyi "normal örüntü" olarak
 * yeniden üretemiyorsa (yüksek yeniden yapılandırma hatası) bunu anomali işaretler.
 *
 * En ilginç durum: denetimli model "normal" diyor AMA bu katman aynı fikirde değil —
 * "bu normal değil, ama ne olduğunu da bilmiyorum" sinyali. Bu, kullanıcının kendi
 * kelimeleriyle istediği tam olarak budur: bilinmeyen anomali tespiti.
 */
export default function AnomaliPaneli({ axles, meta, bilinmeyenler }: {
  axles: AxleDurum[];
  meta: Meta | null;
  bilinmeyenler: string[];
}) {
  if (!meta?.anomali_modeli_var) {
    return (
      <div className="panel">
        <header><h2>Anomali Tespiti (Denetimsiz)</h2></header>
        <div className="aciklama-kutu">
          Anomali modeli eğitilmemiş. Çalıştırmak için:{" "}
          <span className="mono">python src/rayli_anomali_egitim.py</span>
        </div>
      </div>
    );
  }

  const hazirlar = axles.filter((a) => a.anomali_skor != null);
  const anomaliler = hazirlar.filter((a) => a.anomali).sort((a, b) => (b.anomali_skor ?? 0) - (a.anomali_skor ?? 0));

  return (
    <div className="panel">
      <header>
        <h2>Anomali Tespiti (Denetimsiz)</h2>
        <span className="ipucu">eşik: {meta.anomali_esik?.toFixed(3)} · {anomaliler.length} işaretli</span>
      </header>

      <div className="aciklama-kutu" style={{ marginBottom: 12 }}>
        Bu katman <b>sadece normal verilerle eğitilmiş bir autoencoder</b>'dır; 6 bilinen sınıfı
        değil, "bu örüntü sağlıklı bir dingile benziyor mu?" sorusunu yanıtlar. Denetimli modelin
        <b> gözden kaçırabileceği</b> — hiçbir bilinen sınıfa net biçimde benzemeyen — sapmaları
        yakalamak için tasarlandı.
      </div>

      {bilinmeyenler.length > 0 && (
        <div className="bilinmeyen-kutu">
          <b>🔍 {bilinmeyenler.length} dingilde "bilinmeyen anomali":</b> denetimli model
          bunları <b>normal</b> sınıflandırıyor ama bu katman aynı fikirde değil.
          <div className="mono" style={{ marginTop: 6, fontSize: 11 }}>{bilinmeyenler.join(", ")}</div>
        </div>
      )}

      {anomaliler.length === 0 ? (
        <div className="aciklama-kutu">Şu an eşiği aşan pencere yok.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {anomaliler.slice(0, 10).map((a) => (
            <div key={a.axle} style={{ display: "grid", gridTemplateColumns: "140px 1fr 70px", gap: 8, alignItems: "center" }}>
              <span className="mono" style={{ fontSize: 11 }}>{a.line_id} {a.axle}</span>
              <div className="mini-bar" style={{ height: 8, marginTop: 0 }}>
                <div style={{ width: `${(a.anomali_skor ?? 0) * 100}%`,
                             background: a.bilinmeyen_anomali ? "var(--warn)" : "var(--muted)" }} />
              </div>
              <span className="mono" style={{ fontSize: 10, textAlign: "right", color: "var(--muted)" }}>
                {a.anomali_skor?.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
