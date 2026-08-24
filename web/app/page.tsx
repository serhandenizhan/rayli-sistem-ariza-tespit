"use client";

import { useEffect, useMemo, useState } from "react";
import Kontroller from "@/components/Kontroller";
import KenarCubugu, { type Sekme } from "@/components/KenarCubugu";
import KpiKartlari from "@/components/KpiKartlari";
import MetroHarita from "@/components/MetroHarita";
import DingilIzgara from "@/components/DingilIzgara";
import SensorGrafik from "@/components/SensorGrafik";
import OlasilikCubuk from "@/components/OlasilikCubuk";
import OlayGunlugu from "@/components/OlayGunlugu";
import DogrulamaPaneli from "@/components/DogrulamaPaneli";
import EgitimPaneli from "@/components/EgitimPaneli";
import AktifAlarmlar from "@/components/AktifAlarmlar";
import AnomaliPaneli from "@/components/AnomaliPaneli";
import GecmisPaneli from "@/components/GecmisPaneli";
import NlpBildirimPaneli from "@/components/NlpBildirimPaneli";
import { SINIF_ETIKET, SINIF_RENK } from "@/lib/tipler";
import { useAkis } from "@/lib/useAkis";
import { useNlp } from "@/lib/useNlp";

export default function Sayfa() {
  const { meta, ag, tick, olaylar, bagli, hata, kontrol, gecmisAl,
          oynatiliyor, korMod, hiz, histerezis, belirsizlikEsigi,
          gecmis, gecmisiYenile } = useAkis();
  const nlp = useNlp();
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
    <div className="uygulama">
      <KenarCubugu sekme={sekme} onSekme={setSekme} alarmSayisi={aktifAlarm} />
      <main className="ana-icerik">
      <Kontroller meta={meta} tick={tick} bagli={bagli} kontrol={kontrol}
                  oynatiliyor={oynatiliyor} korMod={korMod} hiz={hiz} histerezis={histerezis}
                  belirsizlikEsigi={belirsizlikEsigi} />

      {hata && <div className="uyari">{hata}</div>}

      {/* KPI şeridi her sekmede görünür — özet bilgi her zaman elde olsun */}
      <KpiKartlari tick={tick} meta={meta} />

      {sekme === "izleme" && (
        <div className="sekme-icerik">
          {/* Harita tam genişlikte (yatayda mümkün olduğunca büyük); alarm günlüğü ve renk
              anahtarı haritanın ALTINDA yan yana. */}
          <MetroHarita ag={ag} axles={tick?.axles ?? []} secili={secili} onSec={dingilSec} olaylar={olaylar} />
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

      {sekme === "bildirimler" && (
        <NlpBildirimPaneli
          ornekler={nlp.ornekler} kategoriler={nlp.kategoriler} dagilim={nlp.dagilim}
          sonKayitlar={nlp.sonKayitlar} sonuc={nlp.sonuc} yukleniyor={nlp.yukleniyor}
          hata={nlp.hata} tahminEt={nlp.tahminEt} dogrula={nlp.dogrula}
        />
      )}

      {sekme === "gecmis" && (
        <div className="sekme-icerik">
          <GecmisPaneli gecmis={gecmis} yenile={gecmisiYenile} />
        </div>
      )}
      </main>
    </div>
  );
}
