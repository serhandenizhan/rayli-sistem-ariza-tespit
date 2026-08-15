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
  entropi?: number;             // 0-1 normalize softmax entropisi (belirsizlik ölçüsü)
  belirsiz?: boolean;           // eşiğin üstünde mi — alarm üretemez
  yerlesik_sure_sn?: number;    // mevcut yerleşik durum ne kadardır sürüyor
  oncelik?: number;             // 0-1 alarm öncelik skoru (şiddet + süre + güven)
  oncelik_seviye?: "kritik" | "yuksek" | "orta" | "dusuk";
  // Denetimsiz katman (autoencoder) — modeli eğitilmediyse bu alanlar hiç gelmez
  anomali?: boolean;             // yeniden yapılandırma hatası eşiği aştı mı
  anomali_skor?: number;         // 0-1 normalize skor (arayüzde çubuk için)
  bilinmeyen_anomali?: boolean;  // pred=normal AMA anomali=true — "ne olduğunu bilmiyorum"
  // Aşağıdakiler yalnızca kör mod KAPALI iken gelir (cevap anahtarı = doğrulama katmanı)
  gercek?: SinifAdi;
  gercek_severity?: SiddetAdi;
  dogru_mu?: boolean;
}

export interface Olay {
  ts: string;
  tick?: number;
  axle: string;
  sure_sn?: number;       // önceki durum ne kadar sürdü
  oncelik?: number | null;
  line_id?: string | null;
  onceki: string | null;
  yeni: SinifAdi;
  conf: number;
  severity?: SiddetAdi;
  istasyon?: string | null;
  tip: "alarm" | "temizlendi";
  gercek?: SinifAdi;
  kusur_id?: string;      // ray çatlağı ise: sabit kusur noktası kimliği
  kusur_arasi?: string;   // kusurun hangi istasyonlar arasında olduğu
  tekrar_no?: number;     // aynı kusurun kaçıncı tespiti
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

export interface AktifAlarm {
  axle: string;
  line_id?: string | null;
  yerlesik: SinifAdi;
  severity?: SiddetAdi;
  conf?: number;
  oncelik: number;
  oncelik_seviye: "kritik" | "yuksek" | "orta" | "dusuk";
  yerlesik_sure_sn: number;
  istasyon?: string | null;
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
  belirsizlik_esigi: number;
  aktif_alarmlar: AktifAlarm[];
  belirsiz_sayisi: number;
  anomali_modeli_var: boolean;
  bilinmeyen_anomali_dingiller: string[];
  ray_kusuru_tespitleri: { kusur_id: string; tespit: number; arasi: string | null }[];
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
  oynatiliyor: boolean;   // sunucunun anlık akış durumu (duraklatılmış başlar)
  tick: number;
  histerezis: number;
  belirsizlik_esigi: number;
  anomali_modeli_var: boolean;
  anomali_esik: number | null;
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

/** Harita zemini: ilçe poligonları. poligonlar[parça][halka][nokta] = [lon, lat];
 *  her parçanın ilk halkası dış sınır, sonrakiler deliktir. */
export interface Ilce {
  ad: string;
  poligonlar: number[][][][];
}

export interface Cografya {
  kaynak: string;
  ilce_sayisi: number;
  ilceler: Ilce[];
}

export interface MetroAgi {
  hatlar: Record<string, Hat>;
  simulasyon_hatlari: string[];
  ray_kusurlari: RayKusuru[];
  cografya: Cografya | null;
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
  calisiyor?: boolean;      // pytest şu anda çalışıyor mu
  gecen_sn?: number | null; // çalışıyorsa geçen süre
  hata?: string | null;
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

// ------------------------------------------------------------- geçmiş (SQLite)
export interface GecmisDingil {
  axle: string; line_id: string | null; alarm_sayisi: number;
  agir_sayisi: number; ort_sure_sn: number | null; son_alarm: string;
}
export interface GecmisAlarm {
  kayit_zamani: string; sim_zamani: string | null; axle: string; line_id: string | null;
  onceki: string | null; yeni: string; severity: string | null; conf: number | null;
  istasyon: string | null; sure_sn: number | null; oncelik: number | null; gercek: string | null;
}
export interface GecmisOzet {
  var: boolean;
  mesaj?: string;
  toplam_alarm?: number;
  calistirma_sayisi?: number;
  dingiller?: GecmisDingil[];
  hatlar?: { line_id: string; alarm_sayisi: number; dingil_sayisi: number }[];
  siniflar?: { sinif: string; adet: number; ort_sure_sn: number | null }[];
  ray_kusurlari?: { kusur_id: string; tespit_sayisi: number; dingil_sayisi: number;
                    ilk_tespit: string; son_tespit: string }[];
  calistirmalar?: { id: number; baslangic: string; histerezis: number; dingil_sayisi: number;
                    hat_sayisi: number; alarm_sayisi: number }[];
  son_alarmlar?: GecmisAlarm[];
}

export const ONCELIK_ETIKET: Record<string, string> = {
  kritik: "Kritik", yuksek: "Yüksek", orta: "Orta", dusuk: "Düşük",
};
export const ONCELIK_RENK: Record<string, string> = {
  kritik: "var(--bad)", yuksek: "var(--c-bearing)", orta: "var(--warn)", dusuk: "var(--muted)",
};
