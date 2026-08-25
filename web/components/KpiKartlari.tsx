"use client";

import { SINIF_ETIKET, type Meta, type TickPaketi } from "@/lib/tipler";

function Kpi({ baslik, deger, alt, renk }: { baslik: string; deger: string; alt?: string; renk?: string }) {
  return (
    <div className="kpi">
      <div className="baslik">{baslik}</div>
      <div className="deger" style={renk ? { color: renk } : undefined}>{deger}</div>
      {alt && <div className="alt">{alt}</div>}
    </div>
  );
}

export default function KpiKartlari({ tick, meta }: { tick: TickPaketi | null; meta: Meta | null }) {
  const m = tick?.metrikler;
  const sayaclar = tick?.sayaclar ?? {};
  // Alarm sayısı histerezis sonrası YERLEŞİK duruma göre — anlık sıçramalar sayılmaz
  const arizali = (tick?.axles ?? []).filter((a) => a.yerlesik && a.yerlesik !== "normal").length;
  const toplamDingil = meta?.axles.length ?? 0;

  const enSik = Object.entries(sayaclar)
    .filter(([k, v]) => k !== "normal" && v > 0)
    .sort((a, b) => b[1] - a[1])[0];

  const acc = m?.accuracy;
  const accRenk = acc == null ? undefined : acc >= 0.95 ? "var(--ok)" : acc >= 0.85 ? "var(--warn)" : "var(--bad)";

  return (
    <div className="kpi-satir">
      <Kpi
        baslik="Aktif Alarm"
        deger={`${arizali}`}
        alt={`${toplamDingil} dingilin ${arizali} tanesi arızalı sınıflandı`}
        renk={arizali > 0 ? "var(--bad)" : "var(--ok)"}
      />
      <Kpi
        baslik="Baskın Arıza"
        deger={enSik ? SINIF_ETIKET[enSik[0]] : "—"}
        alt={enSik ? `${enSik[1]} dingilde` : "tüm dingiller normal"}
      />
      <Kpi
        baslik="Tip Doğruluğu"
        deger={acc != null ? `%${(acc * 100).toFixed(1)}` : "—"}
        alt={m?.kor_mod ? "kör mod: cevap anahtarı kapalı" : `${m?.dogru ?? 0}/${m?.degerlendirilen ?? 0} tahmin doğru`}
        renk={accRenk}
      />
      <Kpi
        baslik="Şiddet Doğruluğu"
        deger={m?.severity_accuracy != null ? `%${(m.severity_accuracy * 100).toFixed(1)}` : "—"}
        alt={`macro F1 (tip): ${m?.macro_f1 != null ? m.macro_f1.toFixed(3) : "—"} · offline: ${
          meta?.egitim ? meta.egitim.macro_f1.toFixed(3) : "—"}`}
      />
      <Kpi
        baslik="Belirsiz"
        deger={`${tick?.belirsiz_sayisi ?? 0}`}
        alt={`entropi > ${tick?.belirsizlik_esigi?.toFixed(2) ?? "—"} · alarm üretmez`}
        renk={(tick?.belirsiz_sayisi ?? 0) > 0 ? "var(--warn)" : undefined}
      />
      <Kpi
        baslik="İşlenen Sekans"
        deger={`${(m?.toplam_degerlendirilen ?? m?.degerlendirilen)?.toLocaleString("tr-TR") ?? 0}`}
        alt="oturum başından beri toplam (Sıfırla'dan etkilenmez)"
      />
    </div>
  );
}
