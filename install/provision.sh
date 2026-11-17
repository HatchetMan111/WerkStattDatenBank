#!/usr/bin/env bash
# WerkstattDatenBank – Einrichtung INNERHALB des Containers.
# Wird vom Host-Skript (werkstattdatenbank.sh) per `pct exec` gestartet, kann aber auch
# direkt im Container laufen:   MODE=install|update bash provision.sh
#
# Umgebungsvariablen:
#   MODE          install (Standard) | update
#   WDB_SRC_URL   Quell-Tarball (Standard: GitHub-Archiv des Branches). file:// ist erlaubt.
#   WDB_REPO      Standard: HatchetMan111/WerkStattDatenBank
#   WDB_BRANCH    Standard: main
#   WDB_PORT      Standard: 8080
#   WDB_DEBUG     1 = bash -x Ablaufprotokoll
#   WDB_DEMO      1 (Standard) = bei Neuinstallation erfundene Beispieldaten laden, 0 = leere Datenbank
#   WDB_IMPORT_URL  optional: direkter Download-Link (CSV/ZIP/GZ), wird nach der Installation importiert
set -Eeuo pipefail

MODE="${MODE:-install}"
WDB_REPO="${WDB_REPO:-HatchetMan111/WerkStattDatenBank}"
WDB_BRANCH="${WDB_BRANCH:-main}"
WDB_PORT="${WDB_PORT:-8080}"
WDB_SRC_URL="${WDB_SRC_URL:-https://github.com/${WDB_REPO}/archive/refs/heads/${WDB_BRANCH}.tar.gz}"

APP=werkstattdatenbank
APP_DIR=/opt/$APP
DATA_DIR=/var/lib/$APP
ENV_FILE=/etc/$APP.env
UNIT=/etc/systemd/system/$APP.service
LOG="${WDB_PROVISION_LOG:-/var/log/${APP}-provision.log}"
export DEBIAN_FRONTEND=noninteractive

mkdir -p "$(dirname "$LOG")"
: >>"$LOG"

if [[ "${WDB_DEBUG:-0}" == "1" ]]; then
  exec 9>>"$LOG.xtrace"
  export BASH_XTRACEFD=9
  PS4='+ ${BASH_SOURCE##*/}:${LINENO}: '
  set -x
fi

say() { printf '  %s\n' "$*" | tee -a "$LOG"; }

# --- Fehlerkette: Exit-Code, Zeile, Befehl, Aufrufstapel ---------------------------------
error_handler() {
  local rc=$1 line=$2 cmd=$3 i
  {
    echo
    echo "FEHLER in provision.sh: Exit-Code $rc, Zeile $line"
    echo "  Befehl: $cmd"
    echo "  Aufrufstapel:"
    for ((i = 1; i < ${#FUNCNAME[@]}; i++)); do
      echo "    ${FUNCNAME[$i]}() in ${BASH_SOURCE[$i]##*/}:${BASH_LINENO[$((i - 1))]}"
    done
    echo "  Protokoll: $LOG"
  } | tee -a "$LOG" >&2
}
trap 'rc=$?; error_handler "$rc" "$LINENO" "$BASH_COMMAND"' ERR

die() { echo "FEHLER: $*" | tee -a "$LOG" >&2; exit 1; }

# Befehl ausführen; bei Fehler kompletten stdout/stderr ausgeben (nicht nur den Exit-Code).
run() {
  local out rc=0
  out=$("$@" 2>&1) || rc=$?
  printf '$ %s\n%s\n' "$*" "$out" >>"$LOG"
  if ((rc != 0)); then
    {
      echo "Befehl fehlgeschlagen (Exit-Code $rc): $*"
      echo "----- Ausgabe -----"
      echo "$out"
      echo "-------------------"
    } | tee -a "$LOG" >&2
    return "$rc"
  fi
}

[[ $EUID -eq 0 ]] || die "Muss als root laufen."
[[ "$MODE" == install || "$MODE" == update ]] || die "MODE muss install oder update sein (ist: $MODE)."

# --- Pakete --------------------------------------------------------------------------------
install_packages() {
  say "Pakete installieren (python3, ca-certificates, curl, tar)…"
  run apt-get update -qq
  run apt-get install -y -qq --no-install-recommends python3 ca-certificates curl tar
  python3 -c 'import sqlite3; c = sqlite3.connect(":memory:"); c.execute("create virtual table t using fts5(x, tokenize=\"trigram\")")' \
    || die "SQLite im Container hat keinen FTS5-Trigram-Tokenizer (SQLite >= 3.34 nötig)."
}

# --- Anwendung holen -----------------------------------------------------------------------
fetch_source() {
  SRC_TMP=$(mktemp -d)
  say "Quellcode laden: $WDB_SRC_URL"
  run curl -fsSL --retry 3 --retry-delay 2 -o "$SRC_TMP/src.tar.gz" "$WDB_SRC_URL"
  run tar -xzf "$SRC_TMP/src.tar.gz" -C "$SRC_TMP" --strip-components=1
  [[ -f "$SRC_TMP/backend/app.py" ]] || die "backend/app.py fehlt im Archiv ($WDB_SRC_URL)."
  [[ -f "$SRC_TMP/frontend/dist/index.html" ]] || die "frontend/dist/index.html fehlt im Archiv – im Repo 'npm run build' ausführen und frontend/dist committen."
  [[ -f "$SRC_TMP/install/$APP.service" ]] || die "install/$APP.service fehlt im Archiv."
}

deploy_files() {
  local ts; ts=$(date +%Y%m%d-%H%M%S)
  if [[ -d "$APP_DIR" ]]; then
    OLD_DIR="$APP_DIR.old-$ts"
    run mv "$APP_DIR" "$OLD_DIR"
  fi
  mkdir -p "$APP_DIR/frontend"
  cp -a "$SRC_TMP/backend" "$APP_DIR/backend"
  cp -a "$SRC_TMP/frontend/dist" "$APP_DIR/frontend/dist"
  rm -rf "$APP_DIR/backend/data" "$APP_DIR/backend/__pycache__"
  chown -R root:root "$APP_DIR"
  install -m 0644 "$SRC_TMP/install/$APP.service" "$UNIT"
}

rollback() {
  [[ -n "${OLD_DIR:-}" && -d "${OLD_DIR:-}" ]] || return 0
  say "Rollback auf die vorherige Version ($OLD_DIR)…"
  rm -rf "$APP_DIR"
  mv "$OLD_DIR" "$APP_DIR"
  systemctl daemon-reload || true
  systemctl restart "$APP.service" || true
}

# --- Benutzer, Daten, Konfiguration ------------------------------------------------------------
setup_user_and_data() {
  id wdb >/dev/null 2>&1 || run useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin wdb
  install -d -o wdb -g wdb -m 0750 "$DATA_DIR"
}

gen_token() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }

write_env() {
  if [[ -f "$ENV_FILE" ]]; then
    say "Konfiguration bleibt erhalten: $ENV_FILE"
    # Nur den Port nachziehen, falls ausdrücklich geändert.
    return
  fi
  local token; token=$(gen_token)
  umask 077
  cat >"$ENV_FILE" <<EOF
WDB_HOST=0.0.0.0
WDB_PORT=$WDB_PORT
WDB_DB=$DATA_DIR/wdb.sqlite
WDB_STATIC=$APP_DIR/frontend/dist
WDB_TOKEN=$token
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
EOF
  chmod 600 "$ENV_FILE"
  umask 022
}

# Hilfsprogramm für Importe: lädt die Konfiguration und startet ein Skript als Benutzer wdb.
write_helper() {
  cat >/usr/local/bin/wdb-run <<'EOF'
#!/usr/bin/env bash
# Aufruf: wdb-run import_eea.py datei.csv   |   wdb-run init_db.py --demo
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte als root ausführen." >&2; exit 1; }
set -a; . /etc/werkstattdatenbank.env; set +a
cd /opt/werkstattdatenbank/backend
exec runuser -u wdb -- env WDB_DB="$WDB_DB" PYTHONDONTWRITEBYTECODE=1 python3 "$@"
EOF
  chmod 755 /usr/local/bin/wdb-run
}

init_database() {
  run /usr/local/bin/wdb-run init_db.py
}

open_firewall() {
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    local port; port=$(grep -E '^WDB_PORT=' "$ENV_FILE" | cut -d= -f2)
    say "ufw ist aktiv → Port $port/tcp freigeben"
    run ufw allow "${port}/tcp"
  fi
}

start_service() {
  run systemctl daemon-reload
  run systemctl enable "$APP.service"
  if ! systemctl restart "$APP.service" >>"$LOG" 2>&1; then
    {
      echo "Dienst konnte nicht gestartet werden. Status und Journal:"
      systemctl status "$APP.service" --no-pager -l 2>&1 || true
      journalctl -u "$APP.service" -n 60 --no-pager 2>&1 || true
    } | tee -a "$LOG" >&2
    return 1
  fi
}

verify() {
  local port ok=0 i; port=$(grep -E '^WDB_PORT=' "$ENV_FILE" | cut -d= -f2)
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$port/api/stats" 2>>"$LOG"; then ok=1; break; fi
    sleep 1
  done
  if ((ok == 0)); then
    {
      echo "Selbsttest fehlgeschlagen: http://127.0.0.1:$port/api/stats antwortet nicht."
      echo "systemctl is-active: $(systemctl is-active "$APP.service" 2>&1 || true)"
      journalctl -u "$APP.service" -n 60 --no-pager 2>&1 || true
    } | tee -a "$LOG" >&2
    return 1
  fi
  [[ "$(systemctl is-active "$APP.service")" == active ]] || die "Dienst ist nicht 'active'."
  [[ "$(systemctl is-enabled "$APP.service")" == enabled ]] || die "Dienst ist nicht 'enabled'."
  curl -fsS "http://127.0.0.1:$port/" | grep -qi '<div id="root">' || die "Startseite enthält die Oberfläche nicht."
  say "Selbsttest ok: Dienst aktiv, API und Oberfläche antworten auf Port $port."
}

# Beispieldaten zum sofortigen Ausprobieren (nur bei Neuinstallation; Fehler brechen nichts ab).
lade_demo() {
  [[ "$MODE" == install && "${WDB_DEMO:-1}" == "1" ]] || return 0
  say "Beispieldaten laden (erfunden; in der Oberfläche unter Daten importieren wieder entfernbar)…"
  run /usr/local/bin/wdb-run init_db.py --demo || say "WARNUNG: Beispieldaten konnten nicht geladen werden (nicht kritisch)."
}

# Optionaler Erstimport. Ein Fehler hier bricht die Installation NICHT ab (der Import lässt sich in der Oberfläche wiederholen).
first_import() {
  [[ -n "${WDB_IMPORT_URL:-}" ]] || return 0
  say "Erstimport aus $WDB_IMPORT_URL …"
  if ! run /usr/local/bin/wdb-run import_url.py "$WDB_IMPORT_URL"; then
    say "WARNUNG: Der Erstimport ist fehlgeschlagen (Details oben). Die Installation ist trotzdem fertig – Import später in der Oberfläche wiederholen."
  else
    say "Erstimport abgeschlossen."
  fi
}

main() {
  say "WerkstattDatenBank – Modus: $MODE"
  install_packages
  fetch_source
  if [[ "$MODE" == update && ! -d "$APP_DIR" ]]; then die "Update gewünscht, aber $APP_DIR existiert nicht (erst installieren)."; fi
  deploy_files
  setup_user_and_data
  write_env
  write_helper
  # Ab hier kann ein Fehler zurückgerollt werden.
  if ! { init_database && open_firewall && start_service && verify; }; then
    rollback
    die "Einrichtung fehlgeschlagen (siehe oben). Vorherige Version wiederhergestellt, falls vorhanden."
  fi
  lade_demo
  first_import
  rm -rf "$SRC_TMP"
  # Nur die zwei neuesten Sicherungen behalten.
  find "$(dirname "$APP_DIR")" -maxdepth 1 -name "$APP.old-*" 2>/dev/null | sort -r | tail -n +3 | xargs -r rm -rf || true
  say "Fertig."
}

main "$@"
