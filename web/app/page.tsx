"use client";

import { useEffect, useMemo, useState } from "react";
import Kontroller, { type Sekme } from "@/components/Kontroller";
import KpiKartlari from "@/components/KpiKartlari";
import MetroHarita from "@/components/MetroHarita";
import DingilIzgara from "@/components/DingilIzgara";
import SensorGrafik from "@/components/SensorGrafik";
import OlasilikCubuk from "@/components/OlasilikCubuk";
import OlayGunlugu from "@/components/OlayGunlugu";
import DogrulamaPaneli from "@/components/DogrulamaPaneli";
import EgitimPaneli from "@/components/EgitimPaneli";
import TestPaneli from "@/components/TestPaneli";
import AktifAlarmlar from "@/components/AktifAlarmlar";
import AnomaliPaneli from "@/components/AnomaliPaneli";
import GecmisPaneli from "@/components/GecmisPaneli";
import { SINIF_ETIKET, SINIF_RENK } from "@/lib/tipler";
import { useAkis } from "@/lib/useAkis";

export default function Sayfa() {
  const { meta, ag, tick, olaylar, testler, bagli, hata, kontrol, gecmisAl,
          oynatiliyor, korMod, histerezis, belirsizlikEsigi,
          testleriCalistir, gecmis, gecmisiYenile } = useAkis();
  const [secili, setSecili] = useState<string | null>(null);
  const [sekme, setSekme] = useState<Sekme>("izleme");

  // İlk pakette bir dingil seçili gelsin (varsa arızalı olan, yoksa ilki)
  useEffect(() => {
    if (secili || !tick?.axles.length) return;
    const arizali = tick.axles.find((a) => a.pred && a.pred !== "normal");
    setSecili((arizali ?? tick.axles[0]).axle);
  }, [tick, secili]);

  const seciliAxle = useMemo(
    () => tick?.axles.find((a) => a.axle === secili) ?? null,
    [tick, secili]
  );

  // Haritadan/ızgaradan dingil seçilince ilgili sekmeye geç (bağlam kaybolmasın)
  const dingilSec = (axle: string) => {
    setSecili(axle);
    if (sekme === "izleme") setSekme("dingiller");
  };

  const aktifAlarm = (tick?.axles ?? []).filter((a) => a.yerlesik && a.yerlesik !== "normal").length;

  return (
    <main className="sayfa">
      <Kontroller meta={meta} tick={tick} bagli={bagli} kontrol={kontrol}
                  oynatiliyor={oynatiliyor} korMod={korMod} histerezis={histerezis}
                  sekme={sekme} onSekme={setSekme} alarmSayisi={aktifAlarm}
                  belirsizlikEsigi={belirsizlikEsigi} />

      {hata && <div className="uyari">{hata}</div>}

      {/* KPI şeridi her sekmede görünür — özet bilgi her zaman elde olsun */}
      <KpiKartlari tick={tick} meta={meta} />

      {sekme === "izleme" && (
        <div className="sekme-icerik">
          {/* Harita tam genişlikte (yatayda mümkün olduğunca büyük); alarm günlüğü ve renk
              anahtarı haritanın ALTINDA yan yana. */}
          <MetroHarita ag={ag} axles={tick?.axles ?? []} secili={secili} onSec={dingilSec} />
          <div className="izgara">
            <div className="sutun">
              <AktifAlarmlar alarmlar={tick?.aktif_alarmlar ?? []} onSec={dingilSec} />
              <OlayGunlugu olaylar={olaylar} histerezis={histerezis} />
            </div>
            <div className="sutun">
              <div className="panel">
                <header><h2>Sınıf Renk Anahtarı</h2></header>
                <div className="efsane">
                  {(meta?.classes ?? []).map((c) => (
                    <span key={c}>
                      <i style={{ background: SINIF_RENK[c] }} /> {SINIF_ETIKET[c]}
                      <span className="mono" style={{ color: "var(--muted)" }}>
                        {" "}({tick?.sayaclar?.[c] ?? 0} dingil)
                      </span>
                    </span>
                  ))}
                </div>
                <div className="aciklama-kutu" style={{ marginTop: 10 }}>
                  Sayılar modelin o anki <b>ham</b> tahminine göredir; haritadaki ikon rengi
                  histerezis sonrası <b>yerleşik</b> durumu gösterir.
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {sekme === "dingiller" && (
        <div className="sekme-icerik">
          {/* Dingil ızgarası dikeyde uzun olduğu için sola alındı; boş kalan sağ yarıya
              sensör akışı ve model çıktısı alt alta yerleştirildi. */}
          <div className="izgara-dingil">
            <DingilIzgara axles={tick?.axles ?? []} secili={secili} onSec={setSecili} korMod={korMod} />
            <div className="sutun">
              <SensorGrafik axle={secili} gecmis={secili ? gecmisAl(secili) : []} />
              <OlasilikCubuk axle={seciliAxle} meta={meta} />
            </div>
          </div>
        </div>
      )}

      {sekme === "dogrulama" && (
        <div className="sekme-icerik">
          <div className="izgara">
            <div className="sutun">
              <DogrulamaPaneli metrikler={tick?.metrikler} meta={meta} />
              <AnomaliPaneli axles={tick?.axles ?? []} meta={meta}
                             bilinmeyenler={tick?.bilinmeyen_anomali_dingiller ?? []} />
            </div>
            <div className="sutun">
              <EgitimPaneli egitim={meta?.egitim ?? null} />
            </div>
          </div>
        </div>
      )}

      {sekme === "gecmis" && (
        <div className="sekme-icerik">
          <GecmisPaneli gecmis={gecmis} yenile={gecmisiYenile} />
        </div>
      )}

      {sekme === "testler" && (
        <div className="sekme-icerik">
          <TestPaneli testler={testler} calistir={testleriCalistir} />
        </div>
      )}
    </main>
  );
}
