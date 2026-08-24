"use client";

import { useCallback, useEffect, useState } from "react";
import type {
  NlpKategoriInfo, NlpKategoriSayim, NlpOrnek, NlpPredictYanit, NlpSonKayit,
} from "./tipler";

/**
 * Metin sınıflandırma servisine (nlp/backend/main.py, /api/nlp/* proxy'si) bağlanır.
 *
 * Sensör tarafının useAkis.ts'i SSE ile canlı akış dinler; burada öyle bir akış yok —
 * kullanıcı bir metin gönderdiğinde tek seferlik istek/yanıt yeterli. Kategori listesi ve
 * örnekler sayfa açılışında bir kez çekilir.
 */
export function useNlp() {
  const [kategoriler, setKategoriler] = useState<NlpKategoriInfo[]>([]);
  const [ornekler, setOrnekler] = useState<NlpOrnek[]>([]);
  const [dagilim, setDagilim] = useState<NlpKategoriSayim[]>([]);
  const [sonKayitlar, setSonKayitlar] = useState<NlpSonKayit[]>([]);
  const [sonuc, setSonuc] = useState<NlpPredictYanit | null>(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    let iptal = false;
    fetch("/api/nlp/categories").then((r) => r.json()).then((d) => !iptal && setKategoriler(d)).catch(() => {});
    fetch("/api/nlp/examples?count=8").then((r) => r.json()).then((d) => !iptal && setOrnekler(d)).catch(() => {});
    fetch("/api/nlp/stats/categories").then((r) => r.json()).then((d) => !iptal && setDagilim(d)).catch(() => {});
    fetch("/api/nlp/logs/recent?limit=30").then((r) => r.json()).then((d) => !iptal && setSonKayitlar(d)).catch(() => {});
    return () => { iptal = true; };
  }, []);

  const dagilimiYenile = useCallback(async () => {
    try { setDagilim(await (await fetch("/api/nlp/stats/categories")).json()); } catch { /* yok say */ }
    try { setSonKayitlar(await (await fetch("/api/nlp/logs/recent?limit=30")).json()); } catch { /* yok say */ }
  }, []);

  const tahminEt = useCallback(async (text: string) => {
    setYukleniyor(true);
    setHata(null);
    try {
      const res = await fetch("/api/nlp/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) {
        const gövde = await res.json().catch(() => null);
        throw new Error(gövde?.detail ?? `Sunucu hatası (${res.status})`);
      }
      const data: NlpPredictYanit = await res.json();
      setSonuc(data);
      dagilimiYenile();
      return data;
    } catch (e) {
      setHata(e instanceof Error ? e.message
        : "NLP servisine ulaşılamadı — çalışıyor mu? (uvicorn backend.main:app --port 8001, nlp/ dizininde)");
      return null;
    } finally {
      setYukleniyor(false);
    }
  }, [dagilimiYenile]);

  const dogrula = useCallback(async (logId: number, dogru: boolean, duzeltilmisKategori?: string) => {
    if (logId < 0) return;
    try {
      await fetch("/api/nlp/logs/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ log_id: logId, correct: dogru, corrected_category: duzeltilmisKategori ?? null }),
      });
      dagilimiYenile();
    } catch { /* yok say */ }
  }, [dagilimiYenile]);

  return { kategoriler, ornekler, dagilim, sonKayitlar, sonuc, yukleniyor, hata, tahminEt, dogrula, dagilimiYenile };
}
