#!/usr/bin/env bash
#
# Uçtan uca çalıştırma: ortam kurulumu -> veri -> MODEL EĞİTİMİ -> etiketsiz akış seti
# -> canlı akış API'si -> Next.js dashboard.
#
# Kullanım:
#   ./calistir.sh                 # her şeyi yap (modeli sıfırdan eğitir)
#   ./calistir.sh --egitmeden     # mevcut model/rayli_cnn_lstm_model.pt ile devam et
#   ./calistir.sh --veri-uret     # sentetik veriyi de yeniden üret
#   ./calistir.sh --hiz 10        # simülasyon hız çarpanı (varsayılan 5x)
#   ./calistir.sh --kor-mod       # cevap anahtarını arayüze hiç gönderme
#
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$KOK/.venv"
PY="$VENV/bin/python"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

EGIT=1; VERI_URET=0; HIZ=5; KOR_MOD=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --egitmeden) EGIT=0; shift ;;
    --veri-uret) VERI_URET=1; shift ;;
    --hiz) HIZ="$2"; shift 2 ;;
    --kor-mod) KOR_MOD="--kor-mod"; shift ;;
    *) echo "Bilinmeyen seçenek: $1"; exit 1 ;;
  esac
done

baslik() { printf "\n\033[1;36m== %s\033[0m\n" "$1"; }

# ------------------------------------------------------------------ 1) ortam
baslik "1/6  Python ortamı"
if [[ ! -x "$PY" ]]; then
  echo "Sanal ortam kuruluyor (.venv)…"
  python3 -m venv "$VENV"
fi
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r "$KOK/requirements.txt"
echo "Hazır: $($PY -c 'import torch; print("torch", torch.__version__)')"

# -------------------------------------------------------------------- 2) veri
baslik "2/6  Veri seti"
cd "$KOK/src"
if [[ $VERI_URET -eq 1 || ! -f "$KOK/data/rayli_sistem_test.csv" ]]; then
  "$PY" rayli_veri_uret.py
else
  echo "Mevcut veri kullanılıyor (yeniden üretmek için: --veri-uret)"
fi

# ------------------------------------------------------------------ 3) eğitim
baslik "3/6  Model eğitimi"
if [[ $EGIT -eq 1 ]]; then
  "$PY" rayli_dl_egitim.py
else
  echo "Eğitim atlandı (--egitmeden). Mevcut checkpoint kullanılacak."
  [[ -f "$KOK/model/rayli_cnn_lstm_model.pt" ]] || { echo "HATA: eğitilmiş model yok."; exit 1; }
fi

# ------------------------------------------- 4) etiketsiz akış seti + doğrulama
baslik "4/6  Etiketsiz akış seti + cevap anahtarı"
"$PY" rayli_etiketsiz_uret.py

# -------------------------------------------------------------- 5) akış API'si
baslik "5/6  Canlı akış API'si (:$API_PORT)"
"$PY" rayli_canli_akis_sunucu.py --port "$API_PORT" --hiz "$HIZ" $KOR_MOD &
API_PID=$!
temizle() {
  echo -e "\nKapatılıyor…"
  kill "$API_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap temizle EXIT INT TERM

for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$API_PORT/api/meta" >/dev/null; then echo "API hazır."; break; fi
  sleep 0.5
done

# ------------------------------------------------------------- 6) web arayüzü
baslik "6/6  Next.js dashboard (:$WEB_PORT)"
cd "$KOK/web"
[[ -d node_modules ]] || npm install
AKIS_API_URL="http://127.0.0.1:$API_PORT" npx next dev -p "$WEB_PORT" &
WEB_PID=$!

echo -e "\n\033[1;32mDashboard: http://localhost:$WEB_PORT\033[0m   (durdurmak için Ctrl+C)"
wait "$WEB_PID"
