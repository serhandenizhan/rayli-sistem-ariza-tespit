# Baseline Model Karşılaştırması

Mevcut çok görevli CNN+LSTM mimarisinin gerekçesini deneysel olarak gösterir. Baseline'lar (LogReg/RF/tek başına CNN/tek başına LSTM) yalnızca arıza TİPİ görevi üzerinde, aynı train/test bölmesiyle eğitilmiştir; final model kayıtlı checkpoint'ten yüklenip yeniden eğitilmeden değerlendirilmiştir.

| Model | Accuracy | Macro F1 | Toplam Inference (sn) | Örnek Başı (ms) | Test Örneği |
|---|---|---|---|---|---|
| Logistic Regression | 0.9806 | 0.8775 | 0.005 | 0.0003 | 16352 |
| Random Forest | 0.9825 | 0.8972 | 0.040 | 0.0024 | 16352 |
| 1D-CNN (tek başına) | 0.9905 | 0.9772 | 0.259 | 0.0158 | 16352 |
| LSTM (tek başına) | 0.9914 | 0.9799 | 0.059 | 0.0036 | 16352 |
| Final CNN+LSTM (çok görevli, kayıtlı checkpoint) | 0.9922 | 0.9820 | 0.263 | 0.0161 | 16352 |
