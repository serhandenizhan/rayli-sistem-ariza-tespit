"use client";

import { useEffect, useMemo, useState } from "react";
import Kontroller from "@/components/Kontroller";
import KpiKartlari from "@/components/KpiKartlari";
import MetroHarita from "@/components/MetroHarita";
import DingilIzgara from "@/components/DingilIzgara";
import SensorGrafik from "@/components/SensorGrafik";
import OlasilikCubuk from "@/components/OlasilikCubuk";
import OlayGunlugu from "@/components/OlayGunlugu";
import DogrulamaPaneli from "@/components/DogrulamaPaneli";
import EgitimPaneli from "@/components/EgitimPaneli";
import TestPaneli from "@/components/TestPaneli";
import { SINIF_ETIKET, SINIF_RENK } from "@/lib/tipler";
import { useAkis } from "@/lib/useAkis";

export default function Sayfa() {
  const { meta, ag, tick, olaylar, testler, bagli, hata, kontrol, gecmisAl,
          oynatiliyor, korMod, histerezis, testleriYenile } = useAkis();
  const [secili, setSecili] = useState<string | null>(null);

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

  return (
    <main className="sayfa">
      <Kontroller meta={meta} tick={tick} bagli={bagli} kontrol={kontrol}
                  oynatiliyor={oynatiliyor} korMod={korMod} histerezis={histerezis} />

      {hata && <div className="uyari">{hata}</div>}

      <KpiKartlari tick={tick} meta={meta} />

      <MetroHarita ag={ag} axles={tick?.axles ?? []} secili={secili} onSec={setSecili} />

      <div className="izgara" style={{ marginTop: 16 }}>
        <div className="sutun">
          <DingilIzgara axles={tick?.axles ?? []} secili={secili} onSec={setSecili} korMod={korMod} />
          <SensorGrafik axle={secili} gecmis={secili ? gecmisAl(secili) : []} />
          <OlasilikCubuk axle={seciliAxle} meta={meta} />

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
          </div>
        </div>

        <div className="sutun">
          <OlayGunlugu olaylar={olaylar} histerezis={histerezis} />
          <DogrulamaPaneli metrikler={tick?.metrikler} meta={meta} />
          <TestPaneli testler={testler} yenile={testleriYenile} />
          <EgitimPaneli egitim={meta?.egitim ?? null} />
        </div>
      </div>
    </main>
  );
}
