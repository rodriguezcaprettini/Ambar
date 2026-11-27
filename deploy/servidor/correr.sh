#!/usr/bin/env bash
# Robot del boletín BVRD para el servidor con IP fija. Lo lanza cron (ver instalar.sh).
# Hace lo mismo que el workflow "Actualización diaria" de GitHub, sin las noticias.
# Se identifica siempre como AmbarBot/1.0 y hace una petición por archivo; no usa navegadores ni proxies.
set -u
RAIZ=/opt/ambar
LOG=/var/log/ambar/boletin.log
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

# una sola ejecución a la vez
exec 9>/var/lock/ambar-boletin.lock
flock -n 9 || { echo "Ya hay otra ejecución en curso."; exit 0; }

set -a; . /etc/ambar.env; set +a
cd "$RAIZ" || exit 1
git pull --ff-only -q || echo "(aviso) no se pudo actualizar el código; se usa la copia local"

PY="$RAIZ/venv/bin/python"
"$PY" scripts/supa.py bajar-estado || exit 1
"$PY" scripts/boletin.py            || exit 1      # si la BVRD bloquea (403), se detiene aquí y no reintenta
"$PY" scripts/calendario.py         || echo "(aviso) calendario no disponible"
"$PY" scripts/build_data.py         || exit 1
"$PY" scripts/supa.py subir         || exit 1
"$PY" scripts/publicar.py           || echo "(aviso) publicar.py falló"
echo "OK"
