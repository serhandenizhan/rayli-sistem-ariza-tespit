// Canlı akış API'sinden (src/rayli_canli_akis_sunucu.py) gelen paketlerin tip tanımları.

export type SinifAdi =
  | "normal" | "wheel_flat" | "bearing_fault" | "brake_fault" | "motor_fault" | "rail_crack";

export interface AxleDurum {
  axle: string;
  train_id: string;
  wagon_id: string;
  axle_id: string;
  hazir: boolean;          // kayan pencere doldu mu (10 örnek)
  doluluk: number;
  sensors: Record<string, number>;
  pred?: SinifAdi;
  conf?: number;
  probs?: number[];
  // Aşağıdakiler yalnızca kör mod KAPALI iken gelir (cevap anahtarı = doğrulama katmanı)
  gercek?: SinifAdi;
  severity?: string;
  dogru_mu?: boolean;
}

export interface Olay {
  ts: string;
  axle: string;
  onceki: string | null;
  yeni: SinifAdi;
  conf: number;
  tip: "alarm" | "temizlendi";
  gercek?: SinifAdi;
}

export interface Metrikler {
  kor_mod: boolean;
  degerlendirilen: number;
  dogru?: number;
  accuracy?: number;
  macro_f1?: number;
  confusion?: number[][];
  per_class?: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  trend?: { tick: number; acc: number | null }[];
}

export interface TickPaketi {
  tick: number;
  toplam_tick: number;
  timestamp: string;
  hiz: number;
  oynatiliyor: boolean;
  bitti: boolean;
  axles: AxleDurum[];
  yeni_olaylar: Olay[];
  sayaclar: Record<string, number>;
  metrikler: Metrikler;
}

export interface EgitimOzeti {
  classes: string[];
  epochs: number;
  batch_size: number;
  seed: number;
  n_features: number;
  window: number;
  n_fit_seq: number;
  n_val_seq: number;
  n_test_seq: number;
  history: { epoch: number; train_loss: number; train_acc: number; val_loss: number; val_acc: number }[];
  macro_f1: number;
  accuracy: number;
  confusion_matrix: number[][];
}

export interface Meta {
  classes: SinifAdi[];
  axles: string[];
  feature_cols: string[];
  window: number;
  tick_seconds: number;
  toplam_tick: number;
  kor_mod: boolean;
  baslangic: string;
  bitis: string;
  egitim: EgitimOzeti | null;
}

export const SINIF_ETIKET: Record<string, string> = {
  normal: "Normal",
  wheel_flat: "Teker Düzlüğü",
  bearing_fault: "Rulman Arızası",
  brake_fault: "Fren Arızası",
  motor_fault: "Motor Arızası",
  rail_crack: "Ray Çatlağı",
};

export const SINIF_RENK: Record<string, string> = {
  normal: "var(--ok)",
  wheel_flat: "var(--c-wheel)",
  bearing_fault: "var(--c-bearing)",
  brake_fault: "var(--c-brake)",
  motor_fault: "var(--c-motor)",
  rail_crack: "var(--c-rail)",
};
