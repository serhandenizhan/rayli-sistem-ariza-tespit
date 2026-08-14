"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Meta, Olay, TickPaketi } from "./tipler";

const OLAY_LIMIT = 120;
const GECMIS_LIMIT = 90;   // sensör grafiği için tutulan tick sayısı

/**
 * Canlı akış API'sine SSE ile bağlanır; her tick'te gelen paketi state'e yazar,
 * seçili dingil için sensör geçmişini biriktirir ve kontrol (play/pause/hız) fonksiyonlarını
 * döndürür.
 */
export function useAkis() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [tick, setTick] = useState<TickPaketi | null>(null);
  const [olaylar, setOlaylar] = useState<Olay[]>([]);
  const [bagli, setBagli] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  // Play/pause durumu, sunucudan SSE ile gelen SON tick'in "oynatiliyor" alanına dayanırsa
  // duraklatınca yeni tick gelmediği için buton donmuş gibi görünür — bu yüzden ayrı bir state
  // tutup her kontrol çağrısının kendi (anlık) sunucu yanıtından güncelliyoruz.
  const [oynatiliyor, setOynatiliyor] = useState(true);
  const gecmisRef = useRef<Map<string, { t: number; s: Record<string, number>; pred?: string }[]>>(new Map());
  const [gecmisVersiyon, setGecmisVersiyon] = useState(0);

  useEffect(() => {
    let iptal = false;
    fetch("/api/meta")
      .then((r) => r.json())
      .then((m) => !iptal && setMeta(m))
      .catch(() => setHata("API'ye ulaşılamadı — canlı akış sunucusu çalışıyor mu? (python rayli_canli_akis_sunucu.py)"));

    fetch("/api/olaylar")
      .then((r) => r.json())
      .then((d) => !iptal && setOlaylar(d.olaylar ?? []))
      .catch(() => {});

    const es = new EventSource("/api/akis");
    es.onopen = () => { setBagli(true); setHata(null); };
    es.onerror = () => setBagli(false);
    es.onmessage = (e) => {
      const p: TickPaketi = JSON.parse(e.data);
      setTick(p);
      setOynatiliyor(p.oynatiliyor);
      if (p.yeni_olaylar?.length) {
        setOlaylar((prev) => [...p.yeni_olaylar].reverse().concat(prev).slice(0, OLAY_LIMIT));
      }
      // Reset sonrası (tick 0) geçmişi temizle
      if (p.tick === 0) gecmisRef.current.clear();
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

  const kontrol = useCallback(async (action: string, value?: number) => {
    try {
      const res = await fetch("/api/kontrol", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, value }),
      });
      // Sunucu her kontrol isteğine güncel {oynatiliyor, hiz, tick} döner — bir sonraki SSE
      // paketini beklemeden butonun anında doğru durumu yansıtması için bunu hemen uyguluyoruz.
      const data = await res.json();
      if (typeof data.oynatiliyor === "boolean") setOynatiliyor(data.oynatiliyor);
      if (action === "reset") { gecmisRef.current.clear(); setOlaylar([]); }
    } catch { /* sunucu kapalıysa sessiz geç */ }
  }, []);

  const gecmisAl = useCallback(
    (axle: string) => gecmisRef.current.get(axle) ?? [],
    [gecmisVersiyon] // eslint-disable-line react-hooks/exhaustive-deps
  );

  return { meta, tick, olaylar, bagli, hata, kontrol, gecmisAl, oynatiliyor };
}
