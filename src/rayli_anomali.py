"""
Denetimsiz (unsupervised) anomali tespiti — mevcut 6 sınıflık denetimli sınıflandırıcıyı
TAMAMLAYAN, onun yerine geçmeyen ikinci bir katman.

Neden ayrı bir katman?
-----------------------
Ana model (rayli_model.CNNLSTM) yalnızca önceden tanımlanmış 6 sınıftan birini seçebilir —
hiç görmediği bir örüntüyle karşılaştığında bile bunlardan birine (genelde yanlış bir güvenle)
karar verir. Belirsizlik (entropi) eşiği bu sorunu kısmen çözer ama onu da atlatabilir: bir
sinir ağı, dağılım dışı (out-of-distribution) bir girdide bile YÜKSEK güvenle YANLIŞ sınıf
söyleyebilir — bu, literatürde bilinen bir problemdir.

Autoencoder farklı bir soru soruyor: "Bu pencereyi normal örüntülerden öğrendiğim şekilde
yeniden üretebiliyor muyum?" SADECE `normal` pencerelerle eğitilir; yeniden yapılandırma hatası
yüksekse (normale benzemiyorsa) bu, "her ne olduğunu bilmesem de bu normal değil" sinyali verir
— tıpkı kullanıcının tarif ettiği "bilinmeyen anomali" senaryosu gibi.

Dürüstlük notu: bu sentetik veri setinde yalnızca 6 belgelenmiş arıza tipi var; gerçekten
"bilinmeyen" bir arıza örneği yok. Bu yüzden aşağıdaki `degerlendir()` fonksiyonu autoencoder'ın
BİLİNEN 6 sınıfı da normalden ayırabildiğini (yani mekanizmanın çalıştığını) doğrulamak için
kullanılır — gerçek dünyada asıl değeri, veri setinde hiç bulunmayan GERÇEKTEN yeni bir arıza
tipiyle karşılaşıldığında ortaya çıkar.
"""

import numpy as np
import torch
import torch.nn as nn


class SekansAutoencoder(nn.Module):
    """Küçük, tam bağlı (dense) bir encoder-decoder. Girdi (batch, WINDOW, n_features)
    düzleştirilip sıkıştırılır, sonra aynı şekle geri yeniden yapılandırılır."""

    def __init__(self, n_features, window, gizli=16):
        super().__init__()
        self.window = window
        self.n_features = n_features
        girdi = n_features * window
        self.encoder = nn.Sequential(
            nn.Linear(girdi, 64), nn.ReLU(),
            nn.Linear(64, gizli), nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(gizli, 64), nn.ReLU(),
            nn.Linear(64, girdi),
        )

    def forward(self, x):
        b = x.shape[0]
        z = self.encoder(x.reshape(b, -1))
        cikti = self.decoder(z)
        return cikti.reshape(b, self.window, self.n_features)


def yeniden_yapilandirma_hatasi(model, X):
    """Her pencere için ortalama kare hata (MSE) döndürür — (N,) boyutunda numpy dizisi.
    Yüksek değer = model bu pencereyi 'normal örüntü' olarak tanıyamadı."""
    model.eval()
    with torch.no_grad():
        cikti = model(torch.from_numpy(X))
        hata = ((cikti - torch.from_numpy(X)) ** 2).mean(dim=(1, 2))
    return hata.numpy()


def load_anomali_checkpoint(path, map_location="cpu"):
    """Kaydedilmiş anomali modelini yükler: (model, checkpoint_dict). checkpoint_dict eşik,
    scaler parametreleri ve değerlendirme özetini içerir."""
    checkpoint = torch.load(path, map_location=map_location, weights_only=False)
    model = SekansAutoencoder(
        n_features=len(checkpoint["feature_cols"]), window=checkpoint["window"],
        gizli=checkpoint.get("gizli_boyut", 16),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, checkpoint


def anomali_skoru_normalize(hata, esik):
    """Ham MSE'yi 0-1'e sıkıştırır (eşiğe göre): 1.0 = eşiğin tam üstü, üstünde doygunlaşır.
    Arayüzde ilerleme çubuğu / renk için kullanılır."""
    return float(np.clip(hata / (2 * esik), 0.0, 1.0)) if esik > 0 else 0.0
