"use client";

import { useState } from "react";
import type { NlpKategoriInfo, NlpKategoriSayim, NlpOrnek, NlpPredictYanit, NlpSonKayit } from "@/lib/tipler";

const ALAN_ETIKET: Record<string, string> = {
  line: "Hat", station: "İstasyon", location: "Konum", equipment: "Ekipman",
  symptom: "Belirti", root_cause: "Kök sebep",
};

function tarihMetni(iso: string) {
  try { return new Date(iso + "Z").toLocaleString("tr-TR", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" }); }
  catch { return iso; }
}

/** Tahmin sonucu: kategori/intent/öncelik rozetleri, yapısal alanlar, kanıt, uyarılar. */
function SonucKarti({ sonuc, onDogrula, kategoriler }: {
  sonuc: NlpPredictYanit;
  onDogrula: (dogru: boolean, duzeltilmisKategori?: string) => Promise<void>;
  kategoriler: NlpKategoriInfo[];
}) {
  const [duzeltmeAcik, setDuzeltmeAcik] = useState(false);
  // null | "dogru" | "yanlis" — onaylandıktan sonra buton yerine teşekkür mesajı gösterilir.
  const [onayDurumu, setOnayDurumu] = useState<"dogru" | "yanlis" | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  const gonder = async (dogru: boolean, duzeltilmisKategori?: string) => {
    setGonderiliyor(true);
    try {
      await onDogrula(dogru, duzeltilmisKategori);
      setOnayDurumu(dogru ? "dogru" : "yanlis");
    } finally {
      setGonderiliyor(false);
    }
  };

  const yapisalAlanlar = ["line", "station", "location", "equipment", "symptom", "root_cause"] as const;
  const doluAlanlar = yapisalAlanlar.filter((a) => sonuc[a]);

  return (
    <div className="panel" style={{ borderColor: sonuc.color, borderWidth: 1, borderStyle: "solid" }}>
      <header>
        <h2>Tahmin Sonucu</h2>
        <span className="ipucu mono">{sonuc.response_time_ms.toFixed(1)} ms</span>
      </header>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <span className="rozet" style={{ borderColor: sonuc.color, color: sonuc.color }}>
          {sonuc.label} · %{(sonuc.confidence * 100).toFixed(1)}
        </span>
        <span className="rozet mono">{sonuc.intent_label}</span>
        <span className="rozet" style={{ borderColor: sonuc.priority_color, color: sonuc.priority_color }}>
          {sonuc.priority_label}
          {sonuc.priority_rule && (
            <span title={`Kural: ${sonuc.priority_rule}`} style={{ marginLeft: 5, opacity: 0.8 }}>· KURAL</span>
          )}
        </span>
        {sonuc.secondary_category && (
          <span className="rozet" style={{ borderStyle: "dashed" }}>
            + {sonuc.secondary_label} (%{((sonuc.secondary_confidence ?? 0) * 100).toFixed(1)})
          </span>
        )}
      </div>

      {doluAlanlar.length > 0 && (
        <div className="alt-baslik" style={{ marginTop: 4 }}>Yapısal Bilgiler</div>
      )}
      {doluAlanlar.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8, marginBottom: 10 }}>
          {doluAlanlar.map((a) => (
            <div key={a} style={{ fontSize: 12 }}>
              <span style={{ color: "var(--muted)" }}>{ALAN_ETIKET[a]}: </span>
              <b>{sonuc[a]}</b>
            </div>
          ))}
        </div>
      )}

      {sonuc.evidence.length > 0 && (
        <>
          <div className="alt-baslik">Kanıt (modelin en çok dikkate aldığı kelimeler)</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
            {sonuc.evidence.map((k, i) => (
              <span key={i} className="mono" style={{
                fontSize: 11, padding: "2px 7px", borderRadius: 999,
                background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)",
              }}>{k}</span>
            ))}
          </div>
        </>
      )}

      {sonuc.missing_information.length > 0 && (
        <div className="aciklama-kutu" style={{ marginBottom: 10 }}>
          Eksik bilgi: {sonuc.missing_information.map((a) => ALAN_ETIKET[a] ?? a).join(", ")}
        </div>
      )}

      {sonuc.possible_duplicate && (
        <div className="uyari" style={{ marginBottom: 10 }}>
          Bu aynı arıza son 15 dakikada zaten bildirilmiş olabilir.
        </div>
      )}

      {sonuc.manual_review && (
        <div className="uyari" style={{ marginBottom: 10 }}>{sonuc.manual_review_message ?? "Bu bildirim manuel incelemeye alınmalı."}</div>
      )}

      {onayDurumu === "dogru" && <span className="ipucu">✓ Teşekkürler, kaydedildi.</span>}
      {onayDurumu === "yanlis" && <span className="ipucu">✓ Düzeltme kaydedildi.</span>}

      {sonuc.log_id >= 0 && onayDurumu === null && !duzeltmeAcik && (
        <div style={{ display: "flex", gap: 8 }}>
          <button className="ikon" disabled={gonderiliyor} onClick={() => gonder(true)}>✓ Doğru</button>
          <button className="ikon" disabled={gonderiliyor} onClick={() => setDuzeltmeAcik(true)}>✕ Yanlış</button>
        </div>
      )}
      {onayDurumu === null && duzeltmeAcik && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {kategoriler.map((k) => (
            <button key={k.category} className="ikon" style={{ fontSize: 11 }} disabled={gonderiliyor}
                    onClick={() => gonder(false, k.category)}>
              {k.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Kategori bazında toplam (geçmiş havuz + canlı) bildirim sayısı — yatay bar grafiği. */
function KategoriGrafik({ dagilim }: { dagilim: NlpKategoriSayim[] }) {
  const enCok = Math.max(1, ...dagilim.map((d) => d.count));
  return (
    <div className="panel">
      <header><h2>Kategori Dağılımı</h2></header>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {dagilim.map((d) => (
          <div key={d.category} style={{ display: "grid", gridTemplateColumns: "160px 1fr 60px", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 12 }}>{d.label}</span>
            <div className="mini-bar" style={{ height: 9 }}>
              <div style={{ width: `${(d.count / enCok) * 100}%`, background: d.color, opacity: 0.55 }} />
              {d.live_count > 0 && (
                <div style={{ width: `${(d.live_count / enCok) * 100}%`, background: d.color, opacity: 1, marginTop: -9 }} />
              )}
            </div>
            <span className="mono" style={{ fontSize: 11, textAlign: "right" }}>{d.count}</span>
          </div>
        ))}
      </div>
      <div className="aciklama-kutu" style={{ marginTop: 10 }}>
        Soluk = geçmiş havuz, parlak = canlı eklenen bildirimler.
      </div>
    </div>
  );
}

/** Birleşik olay akışı: bu servisin metin bildirimleri, zaman damgasına göre en yeniden eskiye. */
function SonKayitlar({ kayitlar }: { kayitlar: NlpSonKayit[] }) {
  return (
    <div className="panel">
      <header>
        <h2>Son Metin Bildirimleri</h2>
        <span className="ipucu">{kayitlar.length} kayıt</span>
      </header>
      {kayitlar.length === 0 ? (
        <div className="aciklama-kutu">Henüz bir bildirim yok.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead><tr><th>Zaman</th><th>Metin</th><th>Kategori</th><th>Öncelik</th><th>Kaynak</th></tr></thead>
            <tbody>
              {kayitlar.map((k) => (
                <tr key={k.id}>
                  <td className="mono" style={{ fontSize: 11 }}>{tarihMetni(k.timestamp)}</td>
                  <td style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{k.text}</td>
                  <td><span className="rozet" style={{ borderColor: k.color, color: k.color, fontSize: 11 }}>{k.label}</span></td>
                  <td className="mono" style={{ fontSize: 11 }}>{k.priority ?? "—"}</td>
                  <td className="ipucu" style={{ fontSize: 11 }}>{k.source === "canli" ? "personel bildirimi" : "geçmiş havuz"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/**
 * Metin Bildirimleri sekmesi: serbest metin arıza bildirimi girip anlık BERTurk+LoRA
 * sınıflandırması (intent + 11 kategori + öncelik + yapısal çıkarım) görmek için.
 *
 * Sensör tarafı zaman serisinden OTOMATİK tespit yapar; bu panel personelin/yolcunun
 * YAZDIĞI bildirimleri işler — iki ayrı arıza tespit yolu, ortak dashboard'da yan yana.
 */
export default function NlpBildirimPaneli({
  ornekler, kategoriler, dagilim, sonKayitlar, sonuc, yukleniyor, hata, tahminEt, dogrula,
}: {
  ornekler: NlpOrnek[]; kategoriler: NlpKategoriInfo[]; dagilim: NlpKategoriSayim[];
  sonKayitlar: NlpSonKayit[]; sonuc: NlpPredictYanit | null; yukleniyor: boolean; hata: string | null;
  tahminEt: (text: string) => void;
  dogrula: (logId: number, dogru: boolean, duzeltilmisKategori?: string) => Promise<void>;
}) {
  const [metin, setMetin] = useState("");
  const MAKS_KARAKTER = 300;

  const gonder = () => {
    const t = metin.trim();
    if (!t || yukleniyor) return;
    tahminEt(t);
  };

  return (
    <div className="sekme-icerik">
      <div className="izgara">
        <div className="sutun">
          <div className="panel">
            <header><h2>Arıza Bildirimi Yaz</h2></header>
            <textarea
              value={metin}
              onChange={(e) => setMetin(e.target.value.slice(0, MAKS_KARAKTER))}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); gonder(); } }}
              placeholder="Örn. M4 Kadıköy 2 numaralı girişteki yürüyen merdiven çalışmıyor"
              rows={3}
              style={{ width: "100%", resize: "vertical", fontFamily: "inherit", fontSize: 13,
                       background: "rgba(255,255,255,0.04)", color: "var(--text)",
                       border: "1px solid rgba(255,255,255,0.12)", borderRadius: 8, padding: 10 }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
              <span className="ipucu mono" style={{ color: metin.length >= MAKS_KARAKTER ? "var(--bad)" : undefined }}>
                {metin.length}/{MAKS_KARAKTER}
              </span>
              <button className="ikon vurgu" onClick={gonder} disabled={!metin.trim() || yukleniyor}>
                {yukleniyor ? "Gönderiliyor…" : "Gönder"}
              </button>
            </div>
            {ornekler.length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div className="alt-baslik">Örnekler (tek tıkla doldur)</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {ornekler.map((o, i) => (
                    <button key={i} className="ikon" style={{ fontSize: 11 }} onClick={() => setMetin(o.text)}>
                      {o.text.length > 40 ? o.text.slice(0, 40) + "…" : o.text}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {hata && <div className="uyari">{hata}</div>}
          {sonuc && (
            <SonucKarti key={sonuc.log_id + sonuc.response_time_ms} sonuc={sonuc} kategoriler={kategoriler}
                        onDogrula={(dogru, duzeltilmisKategori) => dogrula(sonuc.log_id, dogru, duzeltilmisKategori)} />
          )}
        </div>

        <div className="sutun">
          <KategoriGrafik dagilim={dagilim} />
          <SonKayitlar kayitlar={sonKayitlar} />
        </div>
      </div>
    </div>
  );
}
