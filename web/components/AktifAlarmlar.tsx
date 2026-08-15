"use client";

import { ONCELIK_ETIKET, ONCELIK_RENK, SIDDET_ETIKET, SINIF_ETIKET, SINIF_RENK,
         type AktifAlarm } from "@/lib/tipler";

/** Süreyi okunur biçime çevirir: 45 sn, 2 dk 10 sn */
function sureMetni(sn: number) {
  if (sn < 60) return `${Math.round(sn)} sn`;
  const dk = Math.floor(sn / 60);
  const kalan = Math.round(sn % 60);
  return kalan ? `${dk} dk ${kalan} sn` : `${dk} dk`;
}

/**
 * Aktif (yerleşik) arızalar — ÖNCELİĞE göre sıralı.
 *
 * Öncelik skoru sunucuda hesaplanır: şiddet %50 + süre %30 + model güveni %20.
 * Böylece "3 dakikadır süren ağır rulman arızası" ile "10 saniyedir hafif" ayrışır;
 * operatör listenin en üstündekine bakarak müdahale sırasını belirleyebilir.
 */
export default function AktifAlarmlar({
  alarmlar, onSec,
}: {
  alarmlar: AktifAlarm[];
  onSec: (axle: string) => void;
}) {
  return (
    <div className="panel">
      <header>
        <h2>Aktif Arızalar — Öncelik Sırası</h2>
        <span className="ipucu">{alarmlar.length} açık arıza</span>
      </header>

      {alarmlar.length === 0 ? (
        <div className="aciklama-kutu">
          Şu an açık arıza yok — tüm dingiller <b>normal</b> durumda yerleşik.
        </div>
      ) : (
        <div className="alarm-liste">
          {alarmlar.map((a) => (
            <button key={a.axle} className="alarm-satir" onClick={() => onSec(a.axle)}>
              <span className="oncelik-bant" style={{ background: ONCELIK_RENK[a.oncelik_seviye] }} />
              <div className="alarm-ana">
                <div className="ust">
                  <span className="hat-kod">{a.line_id}</span>
                  <span className="mono axle">{a.axle}</span>
                  <span className="oncelik-etiket"
                        style={{ color: ONCELIK_RENK[a.oncelik_seviye],
                                 borderColor: ONCELIK_RENK[a.oncelik_seviye] }}>
                    {ONCELIK_ETIKET[a.oncelik_seviye]}
                  </span>
                </div>
                <div className="alt">
                  <b style={{ color: SINIF_RENK[a.yerlesik] }}>{SINIF_ETIKET[a.yerlesik]}</b>
                  {a.severity && a.severity !== "none" && ` · ${SIDDET_ETIKET[a.severity]}`}
                  {a.istasyon && <span className="ipucu"> · {a.istasyon}</span>}
                </div>
              </div>
              <div className="alarm-sag">
                <div className="sure mono">{sureMetni(a.yerlesik_sure_sn)}</div>
                <div className="skor mono">öncelik {a.oncelik.toFixed(2)}</div>
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="aciklama-kutu" style={{ marginTop: 10 }}>
        Öncelik = <b>şiddet</b> (%50) + <b>süre</b> (%30) + <b>model güveni</b> (%20). Süre katkısı
        2 dakikada doygunlaşır. Yalnızca histerezis sonrası <b>yerleşik</b> arızalar listelenir.
      </div>
    </div>
  );
}
