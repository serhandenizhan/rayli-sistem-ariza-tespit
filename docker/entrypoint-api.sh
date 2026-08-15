#!/usr/bin/env bash
# API konteyneri başlangıç betiği: gerekli türetilmiş dosyalar eksikse üretir, sonra sunucuyu
# başlatır. Model/veri git'e gömülü olduğu için normalde hiçbir şey üretmesi gerekmez —
# bu sadece "temiz bir clone + docker compose up" senaryosunda güvence sağlar.
set -euo pipefail

cd /app/src

if [[ ! -f ../model/rayli_cnn_lstm_model.pt ]]; then
  echo "HATA: eğitilmiş model yok (model/rayli_cnn_lstm_model.pt)." >&2
  echo "Depoya gömülü olmalıydı; yoksa: python rayli_dl_egitim.py" >&2
  exit 1
fi

[[ -f ../data/rayli_sistem_test_akis.csv ]] || python rayli_etiketsiz_uret.py
[[ -f ../model/rayli_anomali_model.pt ]] || python rayli_anomali_egitim.py

ARGLAR=(--host 0.0.0.0 --port 8000 --hiz "${HIZ:-5}")
[[ -n "${KOR_MOD:-}" ]] && ARGLAR+=(--kor-mod)
[[ -n "${HISTEREZIS:-}" ]] && ARGLAR+=(--histerezis "$HISTEREZIS")

exec python rayli_canli_akis_sunucu.py "${ARGLAR[@]}"
