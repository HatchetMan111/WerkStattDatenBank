#!/usr/bin/env bash
# Abnahmetest auf dem Proxmox-HOST: Installation → Neustart des Containers → Oberfläche wieder erreichbar.
#   bash test/verify.sh [CTID]        (ohne CTID: Container namens werkstattdatenbank)
# Schreibt ein Protokoll nach /var/log/werkstattdatenbank-verify-<zeit>.log und endet mit Exit-Code 0 (alles ok) oder 1.
set -uo pipefail

APP=werkstattdatenbank
LOG="${WDB_VERIFY_LOG:-/var/log/${APP}-verify-$(date +%Y%m%d-%H%M%S).log}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || LOG="/tmp/$(basename "$LOG")"
exec > >(tee -a "$LOG") 2>&1

FAIL=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAIL=1; }
check() { # check "Beschreibung" befehl…
  local d=$1 out rc=0; shift
  out=$("$@" 2>&1) || rc=$?
  if ((rc == 0)); then pass "$d"; else fail "$d (Exit-Code $rc)"; echo "      Ausgabe: $out"; fi
}

CTID="${1:-}"
if [[ -z "$CTID" ]]; then
  CTID=$(pct list | awk -v n="$APP" 'NR>1 && $NF==n {print $1; exit}')
fi
[[ -n "$CTID" ]] || { echo "FAIL  Kein Container '$APP' gefunden."; exit 1; }
echo "== Abnahmetest CT $CTID – $(date -Is) =="

ct() { pct exec "$CTID" -- "$@"; }
ip_of() { ct ip -4 -o addr show dev eth0 | awk '{print $4}' | cut -d/ -f1 | head -n1; }
port_of() { ct sh -c "grep -E '^WDB_PORT=' /etc/${APP}.env | cut -d= -f2" | tr -d '\r\n'; }

wait_http() { # wartet bis zu 90 s auf die API
  for _ in $(seq 1 45); do
    ct curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/stats" 2>/dev/null && return 0
    sleep 2
  done
  return 1
}

check_state() { # $1 = Phase
  check "[$1] Dienst ist active"  test "$(ct systemctl is-active $APP.service)" = active
  check "[$1] Dienst ist enabled" test "$(ct systemctl is-enabled $APP.service)" = enabled
  check "[$1] API antwortet auf localhost:$PORT" ct curl -fsS "http://127.0.0.1:$PORT/api/stats"
  check "[$1] Oberfläche wird ausgeliefert" bash -c "pct exec $CTID -- curl -fsS http://127.0.0.1:$PORT/ | grep -qi '<div id=\"root\">'"
  check "[$1] Antwort ist von außen (Host → Container-IP) erreichbar" curl -fsS -m 10 -o /dev/null "http://$(ip_of):$PORT/api/stats"
}

check "Container läuft" test "$(pct status "$CTID" | awk '{print $2}')" = running
check "onboot=1 gesetzt" bash -c "pct config $CTID | grep -qx 'onboot: 1'"
PORT=$(port_of); PORT=${PORT:-8080}
echo "Container-IP: $(ip_of)   Port: $PORT"
check_state "vor Neustart"

echo "-- Neustart des Containers --"
check "pct reboot" pct reboot "$CTID"
sleep 5
for _ in $(seq 1 30); do [[ "$(pct status "$CTID" | awk '{print $2}')" == running ]] && break; sleep 2; done
if wait_http; then pass "API nach Neustart wieder erreichbar"; else fail "API nach 90 s nicht erreichbar"; fi
check_state "nach Neustart"

if ((FAIL)); then
  echo "== ERGEBNIS: FEHLGESCHLAGEN – Protokoll: $LOG =="
  echo "-- journalctl (letzte 40 Zeilen) --"
  ct journalctl -u "$APP.service" -n 40 --no-pager 2>&1 || true
  exit 1
fi
echo "== ERGEBNIS: ALLES OK – Protokoll: $LOG =="
