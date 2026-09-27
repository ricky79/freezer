#!/usr/bin/env bash
# Installa o aggiorna Freezer su Linux Mint / Ubuntu. Si può rilanciare quante volte si vuole.
#   sudo ./deploy/install.sh [--host NOME.local] [--https-port 443] [--http-port 80] [--notify-time 08:30]
set -euo pipefail

APP_DIR=/opt/freezer
ENV_FILE=/etc/freezer/freezer.env
DATA_DIR=/var/lib/freezer
CADDY_ROOT_CRT=/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt

HOST="$(hostname).local"
HTTPS_PORT=443
HTTP_PORT=80
NOTIFY_TIME="08:30"

die() { echo "ERRORE: $*" >&2; exit 1; }
info() { echo "==> $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:?manca il valore di --host}"; shift 2 ;;
    --https-port) HTTPS_PORT="${2:?manca il valore di --https-port}"; shift 2 ;;
    --http-port) HTTP_PORT="${2:?manca il valore di --http-port}"; shift 2 ;;
    --notify-time) NOTIFY_TIME="${2:?manca il valore di --notify-time}"; shift 2 ;;
    *) die "opzione sconosciuta: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "lancia lo script con sudo"
[[ "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" == "$APP_DIR" ]] || die "il repository deve stare in $APP_DIR"
[[ $HTTPS_PORT =~ ^[0-9]+$ && $HTTP_PORT =~ ^[0-9]+$ ]] || die "le porte devono essere numeri"
[[ $NOTIFY_TIME =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "orario non valido: $NOTIFY_TIME (formato HH:MM)"
cd "$APP_DIR"

# ---- Controlli prima di toccare qualcosa -----------------------------------

if [[ $HOST == *.local ]]; then
  systemctl is-active --quiet avahi-daemon || die "avahi-daemon non è attivo: senza, gli iPhone non trovano $HOST"
fi

CONFIG_SOURCE="$ENV_FILE"
[[ -f $CONFIG_SOURCE ]] || CONFIG_SOURCE=deploy/freezer.env.example
APP_PORT="$(sed -n 's/^FREEZER_PORT=\([0-9][0-9]*\).*/\1/p' "$CONFIG_SOURCE" | tail -n1)"
APP_PORT="${APP_PORT:-8765}"

port_owner() {
  ss -Htlnp "sport = :$1" | grep -o 'users:(("[^"]*"' | head -n1 | cut -d'"' -f2 || true
}

check_port() {
  local port=$1 owner allowed
  shift
  owner="$(port_owner "$port")"
  [[ -z $owner ]] && return 0
  for allowed in "$@"; do
    [[ $owner == "$allowed" ]] && return 0
  done
  die "la porta $port è già usata da '$owner'. Vedi nel README come usare porte diverse."
}

check_port "$APP_PORT" uvicorn python3
check_port "$HTTPS_PORT" caddy
check_port "$HTTP_PORT" caddy

# ---- Pacchetti ---------------------------------------------------------------

info "Pacchetti"
apt-get update
if ! command -v caddy >/dev/null; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi
dpkg -s python3-venv >/dev/null 2>&1 || apt-get install -y python3-venv

# ---- Utente, cartelle, configurazione ---------------------------------------

info "Utente e cartelle"
id -u freezer >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin freezer
install -d -o freezer -g freezer -m 750 "$DATA_DIR" "$DATA_DIR/backups"
install -d -m 755 /etc/freezer
if [[ ! -f $ENV_FILE ]]; then
  install -m 640 -o root -g freezer deploy/freezer.env.example "$ENV_FILE"
  info "Creato $ENV_FILE: qui si configura Telegram"
fi

# ---- App Python ---------------------------------------------------------------

info "Ambiente Python"
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

info "Servizi systemd"
install -m 644 deploy/systemd/freezer.service deploy/systemd/freezer-notify.service \
  deploy/systemd/freezer-backup.service deploy/systemd/freezer-backup.timer /etc/systemd/system/
sed "s|__NOTIFY_TIME__|$NOTIFY_TIME|g" deploy/systemd/freezer-notify.timer > /etc/systemd/system/freezer-notify.timer
chmod 644 /etc/systemd/system/freezer-notify.timer
systemctl daemon-reload
systemctl enable --quiet freezer.service freezer-notify.timer freezer-backup.timer
systemctl restart freezer.service
systemctl restart freezer-notify.timer freezer-backup.timer

for _ in $(seq 1 20); do
  curl -fsS "http://127.0.0.1:$APP_PORT/api/inventory" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$APP_PORT/api/inventory" >/dev/null \
  || die "l'app non risponde: guarda 'journalctl -u freezer -n 50'"

# ---- Caddy (HTTPS) --------------------------------------------------------------

info "Caddy"
if [[ $HTTPS_PORT == 443 ]]; then HTTPS_SUFFIX=""; else HTTPS_SUFFIX=":$HTTPS_PORT"; fi
if [[ $HTTP_PORT == 80 ]]; then HTTP_SUFFIX=""; else HTTP_SUFFIX=":$HTTP_PORT"; fi
APP_URL="https://$HOST$HTTPS_SUFFIX"
CERT_URL="http://$HOST$HTTP_SUFFIX/cert"

if [[ -f /etc/caddy/Caddyfile && ! -f /etc/caddy/Caddyfile.orig ]] && ! grep -q '^# freezer' /etc/caddy/Caddyfile; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
fi
sed -e "s|__HOST__|$HOST|g" \
    -e "s|__HTTPS_PORT__|$HTTPS_PORT|g" \
    -e "s|__HTTP_PORT__|$HTTP_PORT|g" \
    -e "s|__APP_PORT__|$APP_PORT|g" \
    -e "s|__HTTPS_SUFFIX__|$HTTPS_SUFFIX|g" \
    deploy/Caddyfile.template > /etc/caddy/Caddyfile
sed "s|__APP_URL__|$APP_URL|g" deploy/cert.html > /etc/caddy/freezer-cert.html
chmod 644 /etc/caddy/Caddyfile /etc/caddy/freezer-cert.html
caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null || die "Caddyfile non valido"
systemctl enable --quiet caddy
systemctl reload-or-restart caddy

ok=""
for _ in $(seq 1 30); do
  if [[ -f $CADDY_ROOT_CRT ]] && curl -fsS --cacert "$CADDY_ROOT_CRT" \
      --resolve "$HOST:$HTTPS_PORT:127.0.0.1" "$APP_URL/api/inventory" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
[[ -n $ok ]] || die "HTTPS non risponde su $APP_URL: guarda 'journalctl -u caddy -n 50'"

cat <<EOF

Fatto! Freezer è attivo.

Su ogni iPhone (collegato al Wi-Fi di casa), in Safari:
  1. apri  $CERT_URL  e segui i passaggi per il certificato
  2. apri  $APP_URL  →  Condividi  →  "Aggiungi alla schermata Home"

Telegram: inserisci TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID in $ENV_FILE, poi prova con
  sudo -u freezer bash -c 'set -a; . $ENV_FILE; cd $APP_DIR && .venv/bin/python -m freezer.notify --prova'
Avviso giornaliero alle $NOTIFY_TIME (controlla con: systemctl list-timers 'freezer-*').
EOF
