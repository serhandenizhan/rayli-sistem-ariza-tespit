# Raylı Sistem Arıza Tespiti — Veri Şeması

## Pencere (window) mantığı
Her satır, yaklaşık **2 saniyelik** bir zaman penceresine karşılık gelir (yüksek frekanslı
titreşim/akustik sinyalden çıkarılmış özellik vektörü). Sıcaklık, akım gibi yavaş değişen
büyüklükler de aynı 2 saniyelik pencereye örneklenip aynı satıra eklenmiştir — böylece tüm
sensörler tek bir "wide" tabloda hizalanır ve hem model eğitimi hem de canlı akış simülasyonu
(satır satır, 2 sn aralıklarla yayınlama) için doğrudan kullanılabilir.

## Kolonlar

| Kolon | Açıklama | Birim |
|---|---|---|
| timestamp | Kayıt zaman damgası (ISO 8601) | - |
| train_id | Tren kimliği | - |
| wagon_id | Vagon/araç numarası | - |
| axle_id | Dingil (axle) numarası | - |
| track_km | Hat üzerindeki konum | km |
| speed_kmh | Anlık hız | km/sa |
| load_ton | Dingil/vagon yükü | ton |
| vib_x_rms_g, vib_y_rms_g, vib_z_rms_g | 3 eksende titreşim RMS değeri | g |
| vib_peak_g | Pencere içi tepe titreşim değeri | g |
| vib_kurtosis | Titreşim sinyali basıklık (kurtosis) katsayısı | - |
| vib_crest_factor | Tepe/RMS oranı (darbesel arızaların göstergesi) | - |
| vib_dom_freq_hz | Baskın titreşim frekansı | Hz |
| acoustic_rms | Akustik emisyon RMS seviyesi | - |
| acoustic_peak_freq_hz | Akustik sinyalde baskın frekans | Hz |
| axle_box_temp_c | Dingil yatağı sıcaklığı | °C |
| brake_temp_c | Fren sıcaklığı | °C |
| motor_temp_c | Çekiş motoru sıcaklığı | °C |
| ambient_temp_c | Ortam sıcaklığı | °C |
| motor_current_a | Motor akımı | A |
| motor_voltage_v | Motor gerilimi | V |
| humidity_pct | Bağıl nem | % |
| fault_type | Etiket: normal, wheel_flat, bearing_fault, rail_crack, brake_fault, motor_fault | - |
| fault_severity | none / mild / moderate / severe | - |

## Sınıf mantığı (özellik-arıza ilişkisi)
- **normal**: tüm değerler referans aralıkta, düşük kurtosis/crest factor.
- **wheel_flat** (teker düzlüğü): hız ile orantılı periyodik darbe frekansında vib_dom_freq,
  yüksek crest_factor.
- **bearing_fault** (rulman arızası): yüksek vib_kurtosis, karakteristik yüksek frekans bandında
  enerji, axle_box_temp_c yükselmesi.
- **rail_crack** (ray çatlağı): ani/yüksek acoustic_rms darbeleri, vib_peak_g artışı, konuma
  (track_km) bağlı tekrarlayan örüntü.
- **brake_fault** (fren arızası): brake_temp_c belirgin yüksek, motor_current_a'da anomali.
- **motor_fault** (motor arızası): motor_current_a / motor_voltage_v anormal, motor_temp_c
  yüksek.

## Train/test ayrımı
Rastgele karıştırma yerine **zaman bazlı** bölünür: verinin ilk %80'i (kronolojik olarak daha
eski) eğitim, son %20'si (daha yeni) test setidir. Bu hem veri sızıntısını (data leakage) önler
hem de canlı akış simülasyonunu gerçekçi kılar — model yalnızca "geçmiş" veriyle eğitilmiş
haldeyken "gelecekten" akan test verisini sınıflandırıyormuş gibi çalışır.
