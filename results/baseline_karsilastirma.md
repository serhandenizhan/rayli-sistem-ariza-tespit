# Baseline Model Karşılaştırması

Mevcut çok görevli CNN+LSTM mimarisinin gerekçesini deneysel olarak gösterir. Baseline'lar (LogReg/RF/tek başına CNN/tek başına LSTM) yalnızca arıza TİPİ görevi üzerinde, aynı train/test bölmesiyle eğitilmiştir; final model kayıtlı checkpoint'ten yüklenip yeniden eğitilmeden değerlendirilmiştir.

| Model | Accuracy | Macro F1 | Toplam Inference (sn) | Örnek Başı (ms) | Test Örneği |
|---|---|---|---|---|---|
| Logistic Regression | 0.9681 | 0.8281 | 0.004 | 0.0003 | 16352 |
| Random Forest | 0.9739 | 0.8910 | 0.040 | 0.0025 | 16352 |
| 1D-CNN (tek başına) | 0.9722 | 0.9107 | 0.245 | 0.0150 | 16352 |
| LSTM (tek başına) | 0.9710 | 0.9228 | 0.061 | 0.0037 | 16352 |
| Final CNN+LSTM (çok görevli, kayıtlı checkpoint) | 0.9700 | 0.9236 | 0.227 | 0.0139 | 16352 |
