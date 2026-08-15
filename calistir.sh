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
#   ./calistir.sh --testsiz       # birim testlerini atla
#   API_PORT=8001 WEB_PORT=3001 ./calistir.sh   # portlar meşgulse alternatif port
#
set -euo pipefail

KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$KOK/.venv"
PY="$VENV/bin/python"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

EGIT=1; VERI_URET=0; HIZ=5; KOR_MOD=""; TEST=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --egitmeden) EGIT=0; shift ;;
    --veri-uret) VERI_URET=1; shift ;;
    --testsiz) TEST=0; shift ;;
    --hiz) HIZ="$2"; shift 2 ;;
    --kor-mod) KOR_MOD="--kor-mod"; shift ;;
    *) echo "Bilinmeyen seçenek: $1"; exit 1 ;;
  esac
done

baslik() { printf "\n\033[1;36m== %s\033[0m\n" "$1"; }
hata()   { printf "\n\033[1;31mHATA: %s\033[0m\n" "$1" >&2; }

# Port zaten dinleniyorsa anlaşılır bir hata ver ve çık.
# Neden gerekli? Aksi hâlde uvicorn/next "address already in use" ile sessizce ölüyor; üstelik
# sağlık kontrolü ESKİ sunucuya cevap verdiği için script "API hazır" deyip devam ediyor ve
# kullanıcı yeni kodu çalıştırdığını sanarken bayat bir sunucuyla konuşuyor.
port_dolu_mu() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

port_kontrol() {
  local port="$1" ad="$2" degisken="$3"
  if port_dolu_mu "$port"; then
    hata "$port portu ($ad) zaten kullanımda — muhtemelen önceki bir çalıştırma sürüyor."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR>1 {print "   süreç: PID " $2 " (" $1 ")"}' >&2
    {
      echo "   Çözüm 1 — eski süreci kapat:"
      echo "       kill \$(lsof -t -iTCP:$port -sTCP:LISTEN)"
      echo "   Çözüm 2 — başka port kullan:"
      echo "       $degisken=$((port + 1)) ./calistir.sh"
      echo "   Çözüm 3 — bu projeye ait tüm süreçleri kapat:"
      echo "       pkill -f rayli_canli_akis_sunucu; pkill -f 'next dev'"
    } >&2
    exit 1
  fi
}

# Portlar en başta kontrol edilir: 40 saniyelik eğitimden sonra port hatasıyla karşılaşmak
# yerine hemen bilgilendirilmek daha iyi.
port_kontrol "$API_PORT" "canlı akış API'si" "API_PORT"
port_kontrol "$WEB_PORT" "Next.js dashboard" "WEB_PORT"

# ------------------------------------------------------------------ 1) ortam
baslik "1/8  Python ortamı"
if [[ ! -x "$PY" ]]; then
  echo "Sanal ortam kuruluyor (.venv)…"
  python3 -m venv "$VENV"
fi
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r "$KOK/requirements.txt"
echo "Hazır: $($PY -c 'import torch; print("torch", torch.__version__)')"

# -------------------------------------------------------------------- 2) veri
baslik "2/8  Metro ağı + veri seti"
cd "$KOK/src"
# Gerçek İstanbul metro ağı modeli (İBB açık verisi) — yoksa önbellekten kurulur
[[ -f "$KOK/data/istanbul_metro_agi.json" ]] || "$PY" istanbul_metro_agi.py
if [[ $VERI_URET -eq 1 || ! -f "$KOK/data/rayli_sistem_test.csv" ]]; then
  "$PY" rayli_veri_uret.py
else
  echo "Mevcut veri kullanılıyor (yeniden üretmek için: --veri-uret)"
fi

# ------------------------------------------------------------------ 3) eğitim
baslik "3/8  Model eğitimi (denetimli)"
if [[ $EGIT -eq 1 ]]; then
  "$PY" rayli_dl_egitim.py
else
  echo "Eğitim atlandı (--egitmeden). Mevcut checkpoint kullanılacak."
  [[ -f "$KOK/model/rayli_cnn_lstm_model.pt" ]] || { echo "HATA: eğitilmiş model yok."; exit 1; }
fi

# ------------------------------------------------------------- 3.5) anomali modeli
baslik "3.5/8  Anomali tespiti modeli (denetimsiz, tamamlayıcı)"
if [[ $EGIT -eq 1 || ! -f "$KOK/model/rayli_anomali_model.pt" ]]; then
  "$PY" rayli_anomali_egitim.py
else
  echo "Mevcut anomali modeli kullanılıyor (yeniden eğitmek için: --egitmeden kullanmayın)"
fi

# ------------------------------------------- 4) etiketsiz akış seti + doğrulama
baslik "4/8  Etiketsiz akış seti + cevap anahtarı"
"$PY" rayli_etiketsiz_uret.py

# ------------------------------------------------------------------ 5) testler
baslik "5/8  Birim testleri"
if [[ $TEST -eq 1 ]]; then
  # Sonuçlar results/test_ozeti.json'a yazılır ve dashboard'daki test panelinde görünür.
  # Test başarısız olsa bile demo ayağa kalksın diye çıkış kodu yutuluyor (panelde kırmızı görünür).
  (cd "$KOK" && "$PY" -m pytest -q) || echo "UYARI: bazı testler başarısız — ayrıntı dashboard'daki Testler panelinde"
else
  echo "Testler atlandı (--testsiz)"
fi

# -------------------------------------------------------------- 6) akış API'si
baslik "6/8  Canlı akış API'si (:$API_PORT)"
"$PY" rayli_canli_akis_sunucu.py --port "$API_PORT" --hiz "$HIZ" $KOR_MOD &
API_PID=$!
temizle() {
  echo -e "\nKapatılıyor…"
  kill "$API_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap temizle EXIT INT TERM

API_HAZIR=0
for i in $(seq 1 60); do
  # Başlattığımız süreç öldüyse porta bakmanın anlamı yok (başka bir sunucu cevap veriyor olabilir)
  if ! kill -0 "$API_PID" 2>/dev/null; then
    hata "Canlı akış API'si başlatılamadı (süreç sonlandı). Yukarıdaki çıktıya bakın."
    exit 1
  fi
  if curl -sf "http://127.0.0.1:$API_PORT/api/meta" >/dev/null; then API_HAZIR=1; echo "API hazır."; break; fi
  sleep 0.5
done
if [[ $API_HAZIR -eq 0 ]]; then
  hata "API $API_PORT portunda 30 saniyede yanıt vermedi."
  exit 1
fi

# ------------------------------------------------------------- 6) web arayüzü
baslik "8/8  Next.js dashboard (:$WEB_PORT)"
cd "$KOK/web"
[[ -d node_modules ]] || npm install
AKIS_API_URL="http://127.0.0.1:$API_PORT" npx next dev -p "$WEB_PORT" &
WEB_PID=$!

for i in $(seq 1 60); do
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    hata "Next.js dashboard başlatılamadı. Yukarıdaki çıktıya bakın."
    exit 1
  fi
  curl -sf "http://127.0.0.1:$WEB_PORT" >/dev/null && break
  sleep 0.5
done

echo -e "\n\033[1;32mDashboard: http://localhost:$WEB_PORT\033[0m   (durdurmak için Ctrl+C)"
echo -e "API      : http://127.0.0.1:$API_PORT/api/meta"
wait "$WEB_PID"
