"use client";

import { useEffect } from "react";
import { SIDDET_ETIKET, SINIF_ETIKET, SINIF_RENK, type GecmisOzet } from "@/lib/tipler";

/**
 * Geçmiş kayıtlar — SQLite'a (data/rayli_kayit.db) yazılan alarmların özeti.
 *
 * Canlı akış paneli yalnızca "şu an"ı gösterir; bu panel oturumlar arası kalıcı veriye bakar:
 * hangi dingil kaç kez alarm verdi, hangi hat daha çok arıza üretti, hangi arıza tipi baskın.
 */
export default function GecmisPaneli({ gecmis, yenile }: {
  gecmis: GecmisOzet | null;
  yenile: () => void;
}) {
  // Sekmeye her girildiğinde tazele (canlı akış sürerken veritabanı büyüyor)
  useEffect(() => { yenile(); }, [yenile]);

  if (!gecmis?.var) {
    return (
      <div className="panel">
        <header><h2>Geçmiş Kayıtlar</h2></header>
        <div className="aciklama-kutu">
          {gecmis?.mesaj ?? "Kayıt verisi yükleniyor…"}
        </div>
      </div>
    );
  }

  const enCok = Math.max(1, ...(gecmis.hatlar ?? []).map((h) => h.alarm_sayisi));

  return (
    <>
      <div className="kpi-satir" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="kpi">
          <div className="baslik">Toplam Kayıtlı Alarm</div>
          <div className="deger">{gecmis.toplam_alarm?.toLocaleString("tr-TR")}</div>
          <div className="alt">tüm çalıştırmalar boyunca</div>
        </div>
        <div className="kpi">
          <div className="baslik">Çalıştırma Sayısı</div>
          <div className="deger">{gecmis.calistirma_sayisi}</div>
          <div className="alt">her sıfırlama yeni bir oturum açar</div>
        </div>
        <div className="kpi">
          <div className="baslik">İzlenen Dingil</div>
          <div className="deger">{gecmis.dingiller?.length ?? 0}</div>
          <div className="alt">en az bir alarm üretmiş dingil</div>
        </div>
      </div>

      <div className="izgara">
        <div className="sutun">
          <div className="panel">
            <header>
              <h2>En Çok Alarm Üreten Dingiller</h2>
              <button style={{ fontSize: 11, padding: "4px 9px" }} onClick={yenile}>⟳ Yenile</button>
            </header>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr><th>Hat</th><th>Dingil</th><th>Alarm</th><th>Ağır</th><th>Ort. süre</th></tr>
                </thead>
                <tbody>
                  {(gecmis.dingiller ?? []).map((d) => (
                    <tr key={d.axle}>
                      <td><span className="hat-kod">{d.line_id}</span></td>
                      <td className="mono" style={{ fontSize: 11 }}>{d.axle}</td>
                      <td className="mono">{d.alarm_sayisi}</td>
                      <td className="mono" style={{ color: d.agir_sayisi ? "var(--bad)" : "var(--muted)" }}>
                        {d.agir_sayisi}
                      </td>
                      <td className="mono">{d.ort_sure_sn ?? "—"} sn</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <header><h2>Son Alarmlar (kalıcı kayıt)</h2></header>
            <div className="olay-liste">
              {(gecmis.son_alarmlar ?? []).map((a, i) => (
                <div key={i} className="olay alarm">
                  <span className="saat mono">{a.kayit_zamani?.slice(11, 19)}</span>
                  <span className="aciklama">
                    <b className="mono">{a.line_id} {a.axle}</b>{" "}
                    → <b style={{ color: SINIF_RENK[a.yeni] }}>{SINIF_ETIKET[a.yeni] ?? a.yeni}</b>
                    {a.severity && a.severity !== "none" && ` (${SIDDET_ETIKET[a.severity]})`}
                    {a.istasyon && <span className="ipucu"> · {a.istasyon}</span>}
                  </span>
                  <span className="sag mono">{a.oncelik != null ? a.oncelik.toFixed(2) : ""}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="sutun">
          <div className="panel">
            <header><h2>Hat Bazında Alarm Dağılımı</h2></header>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {(gecmis.hatlar ?? []).map((h) => (
                <div key={h.line_id} style={{ display: "grid", gridTemplateColumns: "48px 1fr 62px", gap: 8, alignItems: "center" }}>
                  <span className="hat-kod">{h.line_id}</span>
                  <div className="mini-bar" style={{ height: 9, marginTop: 0 }}>
                    <div style={{ width: `${(h.alarm_sayisi / enCok) * 100}%`, background: "var(--accent)" }} />
                  </div>
                  <span className="mono" style={{ fontSize: 11, textAlign: "right" }}>
                    {h.alarm_sayisi} / {h.dingil_sayisi} dgl
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <header><h2>Arıza Tipi Dağılımı</h2></header>
            <table>
              <thead><tr><th>Arıza tipi</th><th>Adet</th><th>Ort. süre</th></tr></thead>
              <tbody>
                {(gecmis.siniflar ?? []).map((s) => (
                  <tr key={s.sinif}>
                    <td style={{ color: SINIF_RENK[s.sinif] }}>{SINIF_ETIKET[s.sinif] ?? s.sinif}</td>
                    <td className="mono">{s.adet}</td>
                    <td className="mono">{s.ort_sure_sn ?? "—"} sn</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="panel">
            <header><h2>Çalıştırma Geçmişi</h2></header>
            <table>
              <thead><tr><th>#</th><th>Başlangıç</th><th>Dingil</th><th>Histerezis</th><th>Alarm</th></tr></thead>
              <tbody>
                {(gecmis.calistirmalar ?? []).map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.id}</td>
                    <td className="mono" style={{ fontSize: 11 }}>{c.baslangic?.replace("T", " ")}</td>
                    <td className="mono">{c.dingil_sayisi}</td>
                    <td className="mono">{c.histerezis}</td>
                    <td className="mono">{c.alarm_sayisi}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="aciklama-kutu" style={{ marginTop: 10 }}>
              Kayıtlar <span className="mono">data/rayli_kayit.db</span> (SQLite) dosyasında tutulur.
              Terminalden de sorgulanabilir:{" "}
              <span className="mono">python src/rayli_kayit.py --ozet</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
