#!/usr/bin/env bash
# Birim testlerini çalıştırır ve sonucu results/test_ozeti.json'a yazar
# (dashboard'daki "Testler" paneli bu dosyayı okur).
set -uo pipefail
KOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$KOK/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"
cd "$KOK"
"$PY" -m pytest "$@"
KOD=$?
echo
echo "Test özeti: results/test_ozeti.json"
exit $KOD
