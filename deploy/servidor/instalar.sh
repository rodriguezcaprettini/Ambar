#!/usr/bin/env bash
# Instala el robot del boletín BVRD en un servidor Linux con IP fija (Ubuntu u Oracle Linux).
# Uso (como administrador):   sudo bash instalar.sh
# Pide dos datos de Supabase (la clave no se muestra al escribirla) y los guarda solo en /etc/ambar.env (permiso 600).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo."; exit 1; }

REPO=https://github.com/rodriguezcaprettini/Ambar.git
RAIZ=/opt/ambar

echo "1/5 Instalando paquetes…"
if command -v apt-get >/dev/null; then
  apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip git cron util-linux curl
  systemctl enable --now cron >/dev/null 2>&1 || true
else
  dnf install -y -q python3 python3-pip git cronie util-linux curl
  systemctl enable --now crond >/dev/null 2>&1 || true
fi

echo "2/5 Descargando el código…"
if [ -d "$RAIZ/.git" ]; then git -C "$RAIZ" pull --ff-only -q; else git clone -q "$REPO" "$RAIZ"; fi
python3 -m venv "$RAIZ/venv"
"$RAIZ/venv/bin/pip" install -q requests pandas openpyxl beautifulsoup4

echo "3/5 Credenciales de Supabase (quedan solo en este servidor)"
if [ ! -f /etc/ambar.env ]; then
  read -r  -p "SUPABASE_URL (https://xxxx.supabase.co): " SURL
  read -rs -p "SUPABASE_SERVICE_KEY (no se verá al escribir): " SKEY; echo
  umask 077
  printf 'SUPABASE_URL=%s\nSUPABASE_SERVICE_KEY=%s\nTZ=America/Santo_Domingo\n' "$SURL" "$SKEY" > /etc/ambar.env
fi
chmod 600 /etc/ambar.env

echo "4/5 Horario (hora de República Dominicana, lunes a viernes)"
chmod +x "$RAIZ/deploy/servidor/correr.sh"
cat > /etc/cron.d/ambar-boletin <<'CRON'
CRON_TZ=America/Santo_Domingo
# 8:15 AM · cada 15 min de 1:03 a 8:48 PM · 9:05 PM (definitivo)
15 8 * * 1-5 root /opt/ambar/deploy/servidor/correr.sh
3,18,33,48 13-20 * * 1-5 root /opt/ambar/deploy/servidor/correr.sh
5 21 * * 1-5 root /opt/ambar/deploy/servidor/correr.sh
CRON
chmod 644 /etc/cron.d/ambar-boletin

echo "5/5 Listo. IP pública de SALIDA de este servidor (la que debe habilitar la BVRD):"
curl -s https://api.ipify.org || true; echo
echo "Identificación del robot: AmbarBot/1.0 (+https://github.com/rodriguezcaprettini/Ambar)"
echo "Registro de ejecuciones: /var/log/ambar/boletin.log"
