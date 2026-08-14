"use client";

import type { EgitimOzeti } from "@/lib/tipler";

/** Eğitim (offline) özeti: loss/accuracy eğrileri + test seti referans skorları.
 *  Kaynak: results/egitim_ozeti.json (rayli_dl_egitim.py tarafından yazılır). */
export default function EgitimPaneli({ egitim }: { egitim: EgitimOzeti | null }) {
  if (!egitim) {
    return (
      <div className="panel">
        <header><h2>Eğitim Özeti</h2></header>
        <div className="aciklama-kutu">
          <span className="mono">results/egitim_ozeti.json</span> bulunamadı. Modeli
          <span className="mono"> python rayli_dl_egitim.py</span> ile yeniden eğitince oluşur.
        </div>
      </div>
    );
  }

  const h = egitim.history;
  const W = 320, H = 90, P = 6;
  const maxLoss = Math.max(...h.flatMap((e) => [e.train_loss, e.val_loss]));
  const cizgi = (getir: (e: typeof h[0]) => number, olcek: number) =>
    h.map((e, i) => {
      const x = P + (i * (W - 2 * P)) / Math.max(h.length - 1, 1);
      const y = H - P - (getir(e) / olcek) * (H - 2 * P);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

  return (
    <div className="panel">
      <header>
        <h2>Eğitim Özeti (offline)</h2>
        <span className="ipucu">{egitim.epochs} epoch · seed {egitim.seed}</span>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>Loss (mavi: train, turuncu: val)</div>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
            <path d={cizgi((e) => e.train_loss, maxLoss)} fill="none" stroke="var(--accent)" strokeWidth={1.8} />
            <path d={cizgi((e) => e.val_loss, maxLoss)} fill="none" stroke="var(--warn)" strokeWidth={1.8} />
          </svg>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "var(--muted)" }}>Accuracy (mavi: train, yeşil: val)</div>
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}>
            <path d={cizgi((e) => e.train_acc, 1)} fill="none" stroke="var(--accent)" strokeWidth={1.8} />
            <path d={cizgi((e) => e.val_acc, 1)} fill="none" stroke="var(--ok)" strokeWidth={1.8} />
          </svg>
        </div>
      </div>

      <table style={{ marginTop: 10 }}>
        <tbody>
          <tr><td>Test accuracy (offline)</td><td className="mono">%{(egitim.accuracy * 100).toFixed(2)}</td></tr>
          <tr><td>Test macro F1 (offline)</td><td className="mono">{egitim.macro_f1.toFixed(4)}</td></tr>
          <tr><td>Sekans sayısı (fit / val / test)</td>
              <td className="mono">{egitim.n_fit_seq} / {egitim.n_val_seq} / {egitim.n_test_seq}</td></tr>
          <tr><td>Girdi şekli</td><td className="mono">{egitim.window} × {egitim.n_features}</td></tr>
        </tbody>
      </table>

      <div className="aciklama-kutu" style={{ marginTop: 10 }}>
        Train/test bölmesi <b>kronolojiktir</b> (ilk %80 eğitim, son %20 test). Canlı akış, modelin
        hiç görmediği bu son zaman dilimini gerçek zamanlı olarak yeniden oynatır — dolayısıyla
        soldaki canlı skorların offline test skorlarına yakınsaması beklenir.
      </div>
    </div>
  );
}
