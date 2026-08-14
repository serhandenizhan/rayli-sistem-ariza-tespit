// Canlı akış API'sinden (src/rayli_canli_akis_sunucu.py) gelen paketlerin tip tanımları.

export type SinifAdi =
  | "normal" | "wheel_flat" | "bearing_fault" | "brake_fault" | "motor_fault" | "rail_crack";

export type SiddetAdi = "none" | "mild" | "moderate" | "severe";

export interface Konum {
  lat: number | null;
  lon: number | null;
  km: number;
  istasyon: string | null;
  durakta: boolean;
}

export interface AxleDurum {
  axle: string;
  line_id: string | null;
  train_id: string;
  wagon_id: string;
  axle_id: string;
  hazir: boolean;          // kayan pencere doldu mu (10 örnek)
  doluluk: number;
  sensors: Record<string, number>;
  konum: Konum;
  pred?: SinifAdi;
  conf?: number;
  probs?: number[];
  severity?: SiddetAdi;
  sev_conf?: number;
  sev_probs?: number[];
  yerlesik?: SinifAdi | null;   // histerezis sonrası kararlı sınıf
  kararli?: boolean;
  // Aşağıdakiler yalnızca kör mod KAPALI iken gelir (cevap anahtarı = doğrulama katmanı)
  gercek?: SinifAdi;
  gercek_severity?: SiddetAdi;
  dogru_mu?: boolean;
}

export interface Olay {
  ts: string;
  axle: string;
  line_id?: string | null;
  onceki: string | null;
  yeni: SinifAdi;
  conf: number;
  severity?: SiddetAdi;
  istasyon?: string | null;
  tip: "alarm" | "temizlendi";
  gercek?: SinifAdi;
}

export interface Metrikler {
  kor_mod: boolean;
  degerlendirilen: number;
  dogru?: number;
  accuracy?: number;
  severity_accuracy?: number;
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
  kor_mod: boolean;
  histerezis: number;
  bitti: boolean;
  axles: AxleDurum[];
  yeni_olaylar: Olay[];
  sayaclar: Record<string, number>;
  metrikler: Metrikler;
}

export interface EgitimOzeti {
  classes: string[];
  severity_classes?: string[];
  epochs: number;
  batch_size: number;
  seed: number;
  n_features: number;
  window: number;
  n_fit_seq: number;
  n_val_seq: number;
  n_test_seq: number;
  history: {
    epoch: number; train_loss: number; train_acc: number; val_loss: number; val_acc: number;
    train_sev_acc?: number; val_sev_acc?: number;
  }[];
  macro_f1: number;
  accuracy: number;
  confusion_matrix: number[][];
  severity?: { accuracy: number; macro_f1: number };
}

export interface Meta {
  classes: SinifAdi[];
  severity_classes: SiddetAdi[];
  axles: string[];
  axle_hat: Record<string, string>;
  feature_cols: string[];
  window: number;
  tick_seconds: number;
  toplam_tick: number;
  kor_mod: boolean;
  histerezis: number;
  kaynak: string;
  baslangic: string;
  bitis: string;
  egitim: EgitimOzeti | null;
}

// ---------------------------------------------------------------- metro ağı (harita)
export interface Istasyon {
  ad: string;
  lat: number;
  lon: number;
  km: number;
}

export interface Hat {
  kod: string;
  ad: string;
  kisa_ad: string;
  tur: string;
  renk: string;
  uzunluk_km: number;
  istasyon_sayisi: number;
  istasyonlar: Istasyon[];
  cizim: number[][][];      // [parça][nokta][lon, lat]
}

export interface RayKusuru {
  hat: string;
  km: number;
  genislik_km: number;
  siddet: string;
  arasi: string;
  lat: number;
  lon: number;
}

export interface MetroAgi {
  hatlar: Record<string, Hat>;
  simulasyon_hatlari: string[];
  ray_kusurlari: RayKusuru[];
  kaynak: string | null;
}

// ------------------------------------------------------------------ test sonuçları
export interface TestKaydi {
  nodeid: string;
  dosya: string;
  ad: string;
  aciklama?: string;
  sonuc: "passed" | "failed" | "skipped";
  sure: number;
  hata?: string;
}

export interface TestOzeti {
  var: boolean;
  mesaj?: string;
  calistirma_zamani?: string;
  toplam?: number;
  gecti?: number;
  kaldi?: number;
  atlandi?: number;
  toplam_sure?: number;
  testler?: TestKaydi[];
}

// ------------------------------------------------------------------------- etiketler
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

export const SIDDET_ETIKET: Record<string, string> = {
  none: "Yok",
  mild: "Hafif",
  moderate: "Orta",
  severe: "Ağır",
};

export const SIDDET_RENK: Record<string, string> = {
  none: "var(--muted)",
  mild: "var(--warn)",
  moderate: "var(--c-bearing)",
  severe: "var(--bad)",
};
