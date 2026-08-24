#!/usr/bin/env bash
# NLP servisi konteyner başlangıç betiği: model/adaptör git'e gömülü olduğu için normalde
# hiçbir şey üretmesi gerekmez (bkz. docker/entrypoint-api.sh'deki aynı desen).
set -euo pipefail

if [[ ! -f model/govde/adapter_model.safetensors ]]; then
  echo "HATA: eğitilmiş LoRA adaptörü yok (model/govde/adapter_model.safetensors)." >&2
  echo "Depoya gömülü olmalıydı; yoksa: python -m src.train" >&2
  exit 1
fi

exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001
