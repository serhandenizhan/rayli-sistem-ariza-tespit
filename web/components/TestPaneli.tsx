"use client";

import { useState } from "react";
import type { TestOzeti } from "@/lib/tipler";

const DOSYA_ETIKET: Record<string, string> = {
  "testler/test_veri_semasi.py": "Veri şeması & sızıntı korumaları",
  "testler/test_metro_agi.py": "İstanbul metro ağı doğruluğu",
  "testler/test_model.py": "Model mimarisi & checkpoint",
  "testler/test_canli_akis.py": "Canlı akış motoru",
};

const SONUC_SIMGE: Record<string, string> = { passed: "✓", failed: "✕", skipped: "–" };
const SONUC_RENK: Record<string, string> = {
  passed: "var(--ok)", failed: "var(--bad)", skipped: "var(--muted)",
};

/** pytest sonuçlarını (results/test_ozeti.json) okunabilir biçimde gösterir. */
export default function TestPaneli({ testler, yenile }: { testler: TestOzeti | null; yenile: () => void }) {
  const [acik, setAcik] = useState<string | null>(null);

  if (!testler?.var) {
    return (
      <div className="panel">
        <header><h2>Birim Testleri</h2></header>
        <div className="aciklama-kutu">
          {testler?.mesaj ?? "Test sonucu yok."}<br />
          Çalıştırmak için: <span className="mono">./testleri_calistir.sh</span>
        </div>
      </div>
    );
  }

  const gruplar = new Map<string, typeof testler.testler>();
  for (const t of testler.testler ?? []) {
    const g = gruplar.get(t.dosya) ?? [];
    g.push(t);
    gruplar.set(t.dosya, g);
  }

  const hepsiGecti = (testler.kaldi ?? 0) === 0;

  return (
    <div className="panel">
      <header>
        <h2>Birim Testleri</h2>
        <button style={{ fontSize: 11, padding: "4px 9px" }} onClick={yenile}>⟳ Yenile</button>
      </header>

      <div className="test-ozet" style={{ borderColor: hepsiGecti ? "var(--ok)" : "var(--bad)" }}>
        <div>
          <div className="deger" style={{ color: hepsiGecti ? "var(--ok)" : "var(--bad)" }}>
            {hepsiGecti ? "✓ Tümü geçti" : `✕ ${testler.kaldi} test başarısız`}
          </div>
          <div className="alt mono">
            {testler.gecti}/{testler.toplam} geçti
            {(testler.atlandi ?? 0) > 0 ? ` · ${testler.atlandi} atlandı` : ""} ·
            {" "}{testler.toplam_sure}s
          </div>
        </div>
        <div className="alt mono" style={{ textAlign: "right" }}>
          son çalıştırma<br />
          {testler.calistirma_zamani?.replace("T", " ")}
        </div>
      </div>

      {[...gruplar.entries()].map(([dosya, liste]) => {
        const kalan = liste!.filter((t) => t.sonuc === "failed").length;
        const acikMi = acik === dosya;
        return (
          <div key={dosya} className="test-grup">
            <button className="test-grup-baslik" onClick={() => setAcik(acikMi ? null : dosya)}>
              <span style={{ color: kalan ? "var(--bad)" : "var(--ok)" }}>{kalan ? "✕" : "✓"}</span>
              <span className="ad">{DOSYA_ETIKET[dosya] ?? dosya}</span>
              <span className="mono sag">{liste!.length} test</span>
              <span className="ok">{acikMi ? "▾" : "▸"}</span>
            </button>
            {acikMi && (
              <div className="test-liste">
                {liste!.map((t) => (
                  <div key={t.nodeid} className="test-satir">
                    <span style={{ color: SONUC_RENK[t.sonuc] }}>{SONUC_SIMGE[t.sonuc]}</span>
                    <div>
                      <div className="mono" style={{ fontSize: 11 }}>{t.ad}</div>
                      {t.aciklama && <div className="test-aciklama">{t.aciklama}</div>}
                      {t.hata && <pre className="test-hata">{t.hata}</pre>}
                    </div>
                    <span className="mono sure">{(t.sure * 1000).toFixed(0)}ms</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <div className="aciklama-kutu" style={{ marginTop: 10 }}>
        Testler veri şemasını ve <b>sızıntı korumalarını</b> (akış dosyasında etiket olmaması,
        kör modda cevap anahtarının paketlere sızmaması), gerçek metro ağının doğruluğunu
        (istasyon sırası, koordinatlar), model checkpoint'ini ve canlı akış motorunu
        (histerezis, doğruluk eşiği) doğrular.
      </div>
    </div>
  );
}
