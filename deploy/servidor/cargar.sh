#!/usr/bin/env bash
# Carga en Ámbar boletines consolidados de la BVRD descargados a mano en el navegador.
# Uso:  sudo bash /opt/ambar/deploy/servidor/cargar.sh ARCHIVO1.xlsx [ARCHIVO2.xlsx ...]
# La fecha se toma del nombre del archivo (DD-MM-YYYY). Hace lo mismo que el robot: procesa,
# prepara los datos de la terminal y los sube a Supabase. No se conecta a la BVRD.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }
[ $# -ge 1 ] || { echo "Uso: sudo bash $0 ARCHIVO.xlsx [ARCHIVO2.xlsx ...]"; exit 1; }

# rutas absolutas y orden por fecha (más antiguo primero)
declare -a LISTA=()
for f in "$@"; do
  f=$(readlink -f "$f")
  [ -f "$f" ] || { echo "No existe: $f"; exit 1; }
  n=$(basename "$f")
  if [[ $n =~ ([0-9]{2})-([0-9]{2})-([0-9]{4}) ]]; then
    d="${BASH_REMATCH[3]}-${BASH_REMATCH[2]}-${BASH_REMATCH[1]}"
  else
    echo "No encuentro la fecha DD-MM-YYYY en el nombre: $n"; exit 1
  fi
  [ "$(head -c2 "$f")" = "PK" ] || { echo "$n no es un Excel válido (¿se descargó una página en vez del archivo?)"; exit 1; }
  LISTA+=("$d|$(stat -c %Y "$f")|$f")   # fecha del boletín y hora de modificación del archivo
done
# por fecha y, dentro del mismo día, del archivo más viejo al más nuevo: la última descarga es la que queda
IFS=$'\n' LISTA=($(printf '%s\n' "${LISTA[@]}" | sort)); unset IFS

RAIZ=/opt/ambar; PY="$RAIZ/venv/bin/python"
exec 9>/var/lock/ambar-boletin.lock; flock 9          # espera si el robot está corriendo
set -a; . /etc/ambar.env; set +a
cd "$RAIZ"
git pull --ff-only -q || echo "(aviso) no se pudo actualizar el código; se usa la copia local"

"$PY" scripts/supa.py bajar-estado
for x in "${LISTA[@]}"; do
  d="${x%%|*}"; f="${x#*|}"; f="${f#*|}"
  echo "== $d  ($(basename "$f"))"
  "$PY" scripts/boletin.py --archivo "$f" "$d"
done
"$PY" scripts/build_data.py
"$PY" scripts/supa.py subir
"$PY" scripts/publicar.py || echo "(aviso) publicar.py falló"
echo "Listo: recarga Ámbar para ver los boletines."
