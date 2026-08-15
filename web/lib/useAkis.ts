"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MetroAgi, Meta, Olay, TestOzeti, TickPaketi } from "./tipler";

const OLAY_LIMIT = 120;
const GECMIS_LIMIT = 90;   // sensör grafiği için tutulan tick sayısı

/**
 * Canlı akış API'sine SSE ile bağlanır; her tick'te gelen paketi state'e yazar,
 * seçili dingil için sensör geçmişini biriktirir ve kontrol (play/pause/hız/kör mod/
 * histerezis) fonksiyonlarını döndürür.
 */
export function useAkis() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [ag, setAg] = useState<MetroAgi | null>(null);
  const [tick, setTick] = useState<TickPaketi | null>(null);
  const [olaylar, setOlaylar] = useState<Olay[]>([]);
  const [testler, setTestler] = useState<TestOzeti | null>(null);
  const [bagli, setBagli] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  // Kontrol durumları SSE paketine bağlı kalırsa duraklatınca buton donmuş görünür —
  // bu yüzden ayrı state tutup her kontrol çağrısının anlık sunucu yanıtından güncelliyoruz.
  const [oynatiliyor, setOynatiliyor] = useState(true);
  const [korMod, setKorMod] = useState(false);
  const [histerezis, setHisterezis] = useState(3);

  const gecmisRef = useRef<Map<string, { t: number; s: Record<string, number>; pred?: string }[]>>(new Map());
  const [, setGecmisVersiyon] = useState(0);

  useEffect(() => {
    let iptal = false;

    fetch("/api/meta")
      .then((r) => r.json())
      .then((m: Meta) => {
        if (iptal) return;
        setMeta(m);
        setKorMod(m.kor_mod);
        setHisterezis(m.histerezis);
      })
      .catch(() => setHata("API'ye ulaşılamadı — canlı akış sunucusu çalışıyor mu? (python rayli_canli_akis_sunucu.py)"));

    fetch("/api/ag").then((r) => r.json()).then((a) => !iptal && setAg(a)).catch(() => {});
    fetch("/api/olaylar").then((r) => r.json()).then((d) => !iptal && setOlaylar(d.olaylar ?? [])).catch(() => {});
    fetch("/api/testler").then((r) => r.json()).then((t) => !iptal && setTestler(t)).catch(() => {});

    const es = new EventSource("/api/akis");
    es.onopen = () => { setBagli(true); setHata(null); };
    es.onerror = () => setBagli(false);
    es.onmessage = (e) => {
      const p: TickPaketi = JSON.parse(e.data);
      setTick(p);
      setOynatiliyor(p.oynatiliyor);
      setKorMod(p.kor_mod);
      setHisterezis(p.histerezis);
      if (p.yeni_olaylar?.length) {
        setOlaylar((prev) => [...p.yeni_olaylar].reverse().concat(prev).slice(0, OLAY_LIMIT));
      }
      if (p.tick === 0) gecmisRef.current.clear();   // reset sonrası geçmişi temizle
      for (const a of p.axles) {
        const arr = gecmisRef.current.get(a.axle) ?? [];
        arr.push({ t: p.tick, s: a.sensors, pred: a.pred });
        if (arr.length > GECMIS_LIMIT) arr.shift();
        gecmisRef.current.set(a.axle, arr);
      }
      setGecmisVersiyon((v) => v + 1);
    };
    return () => { iptal = true; es.close(); };
  }, []);

  const kontrol = useCallback(async (action: string, value?: number | boolean) => {
    try {
      const res = await fetch("/api/kontrol", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, value }),
      });
      const data = await res.json();
      if (typeof data.oynatiliyor === "boolean") setOynatiliyor(data.oynatiliyor);
      if (typeof data.kor_mod === "boolean") setKorMod(data.kor_mod);
      if (typeof data.histerezis === "number") setHisterezis(data.histerezis);
      if (action === "reset") { gecmisRef.current.clear(); setOlaylar([]); }
    } catch { /* sunucu kapalıysa sessiz geç */ }
  }, []);

  const testleriYenile = useCallback(async () => {
    try {
      const t = await (await fetch("/api/testler")).json();
      setTestler(t);
      return t as TestOzeti;
    } catch { return null; }
  }, []);

  /** Testleri sunucuda yeniden çalıştırır ve bitene kadar durumu yoklar.
   *  pytest ~15 sn sürdüğü için arayüz bu sürede geçen süreyi canlı gösterir. */
  const testleriCalistir = useCallback(async () => {
    try {
      await fetch("/api/testler/calistir", { method: "POST" });
      const yokla = async () => {
        const t = await testleriYenile();
        if (t?.calisiyor) setTimeout(yokla, 400);
      };
      setTimeout(yokla, 300);
    } catch { /* sunucu kapalıysa sessiz geç */ }
  }, [testleriYenile]);

  const gecmisAl = useCallback((axle: string) => gecmisRef.current.get(axle) ?? [], []);

  return { meta, ag, tick, olaylar, testler, bagli, hata, kontrol, gecmisAl,
           oynatiliyor, korMod, histerezis, testleriYenile, testleriCalistir };
}
