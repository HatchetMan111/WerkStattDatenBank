#!/usr/bin/env bash
# WerkstattDatenBank – Proxmox-VE-Installer (läuft auf dem Proxmox-HOST, legt einen LXC an)
#
#   bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/WerkStattDatenBank/main/install/werkstattdatenbank.sh)"
#
# Ist schon ein Container namens "werkstattdatenbank" vorhanden, wird er aktualisiert
# (Daten und Token bleiben erhalten). Neuinstallation erzwingen: var_new=1.
#
# Einstellungen per Umgebungsvariable (alle optional):
#   var_ctid=120            Container-ID (Standard: nächste freie ID)
#   var_hostname=…          Name (Standard: werkstattdatenbank)
#   var_cpu=1  var_ram=1024  var_disk=8     Kerne / MB RAM / GB Platte
#   var_bridge=vmbr0        Netzwerk-Bridge
#   var_ip=192.168.1.50/24 var_gw=192.168.1.1   feste IP (Standard: DHCP)
#   var_storage=…           Speicher für die Container-Platte (Standard: automatisch)
#   var_template_storage=…  Speicher für Vorlagen (Standard: automatisch)
#   var_port=8080           Port der Weboberfläche
#   var_new=1               immer neuen Container anlegen
#   WDB_REPO / WDB_BRANCH   anderes Repo bzw. anderer Branch
#   WDB_DEBUG=1  oder  --debug     ausführliches bash -x Protokoll
#   WDB_KEEP_ON_ERROR=1     fehlgeschlagenen neuen Container NICHT löschen
set -Eeuo pipefail

APP=werkstattdatenbank
WDB_REPO="${WDB_REPO:-HatchetMan111/WerkStattDatenBank}"
WDB_BRANCH="${WDB_BRANCH:-main}"
WDB_PROVISION_SRC="${WDB_PROVISION_SRC:-https://raw.githubusercontent.com/${WDB_REPO}/${WDB_BRANCH}/install/provision.sh}"
WDB_SRC_URL="${WDB_SRC_URL:-}"

for a in "$@"; do
  case "$a" in
    --debug) WDB_DEBUG=1 ;;
    -h | --help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unbekannte Option: $a (erlaubt: --debug, --help)" >&2; exit 2 ;;
  esac
done

TS=$(date +%Y%m%d-%H%M%S)
LOG="${WDB_LOG:-/var/log/${APP}-install-${TS}.log}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || LOG="/tmp/${APP}-install-${TS}.log"
: >"$LOG"; chmod 600 "$LOG" 2>/dev/null || true

if [[ "${WDB_DEBUG:-0}" == "1" ]]; then
  exec 9>>"$LOG"
  export BASH_XTRACEFD=9
  PS4='+ ${BASH_SOURCE##*/}:${LINENO}: '
  set -x
fi

if [[ -t 1 ]]; then C_OK=$'\e[32m'; C_ERR=$'\e[31m'; C_DIM=$'\e[2m'; C_OFF=$'\e[0m'; else C_OK=; C_ERR=; C_DIM=; C_OFF=; fi
info() { printf '%s\n' "${C_DIM}»${C_OFF} $*" | tee -a "$LOG"; }
ok() { printf '%s\n' "${C_OK}✔${C_OFF} $*" | tee -a "$LOG"; }

CTID=""
CT_CREATED=0

# --- Fehlerkette: Exit-Code, Zeile, Befehl, Aufrufstapel, Hinweise ----------------------------
error_handler() {
  local rc=$1 line=$2 cmd=$3 i
  {
    echo
    echo "${C_ERR}✘ FEHLER${C_OFF} im Installer: Exit-Code $rc, Zeile $line"
    echo "  Befehl: $cmd"
    echo "  Aufrufstapel:"
    for ((i = 1; i < ${#FUNCNAME[@]}; i++)); do
      echo "    ${FUNCNAME[$i]}() in ${BASH_SOURCE[$i]##*/}:${BASH_LINENO[$((i - 1))]}"
    done
    echo "  Protokoll: $LOG"
    echo "  Ausführliches Ablaufprotokoll:  WDB_DEBUG=1 bash -c \"\$(wget -qLO - https://raw.githubusercontent.com/${WDB_REPO}/${WDB_BRANCH}/install/${APP}.sh)\""
  } | tee -a "$LOG" >&2
}
trap 'rc=$?; error_handler "$rc" "$LINENO" "$BASH_COMMAND"' ERR

cleanup() {
  local rc=$?
  if ((rc != 0 && CT_CREATED == 1)) && [[ -n "$CTID" ]]; then
    if [[ "${WDB_KEEP_ON_ERROR:-0}" == "1" ]]; then
      echo "Hinweis: Container $CTID bleibt zur Fehlersuche bestehen (WDB_KEEP_ON_ERROR=1). Konsole: pct enter $CTID" | tee -a "$LOG" >&2
    else
      echo "Räume auf: neuer Container $CTID wird wieder entfernt (zum Behalten: WDB_KEEP_ON_ERROR=1)." | tee -a "$LOG" >&2
      pct stop "$CTID" >/dev/null 2>&1 || true
      pct destroy "$CTID" --purge >/dev/null 2>&1 || true
    fi
  fi
  ((rc == 0)) || echo "Installation fehlgeschlagen (Exit-Code $rc). Protokoll: $LOG" >&2
}
trap cleanup EXIT

die() { echo "${C_ERR}✘${C_OFF} $*" | tee -a "$LOG" >&2; exit 1; }

# Befehl ausführen; bei Fehler vollständige Ausgabe zeigen.
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

# --- Voraussetzungen ------------------------------------------------------------------------
preflight() {
  [[ $EUID -eq 0 ]] || die "Bitte als root auf dem Proxmox-Host ausführen."
  local c
  for c in pct pvesh pveam pvesm pveversion; do
    command -v "$c" >/dev/null 2>&1 || die "'$c' nicht gefunden – dieses Skript gehört auf einen Proxmox-VE-Host (nicht in einen Container)."
  done
  info "Proxmox: $(pveversion 2>/dev/null | head -n1)"
}

# --- Container-Suche ----------------------------------------------------------------------
find_existing() {
  local id name
  while read -r id name; do
    [[ -n "$id" ]] || continue
    if [[ "$name" == "$HOSTNAME_CT" ]]; then echo "$id"; return 0; fi
  done < <(pct list 2>/dev/null | awk 'NR>1 {print $1, $NF}')
  return 0
}

pick_ctid() {
  if [[ -n "${var_ctid:-}" ]]; then
    [[ "$var_ctid" =~ ^[0-9]+$ ]] || die "var_ctid muss eine Zahl sein (ist: $var_ctid)."
    if pct status "$var_ctid" >/dev/null 2>&1 || qm status "$var_ctid" >/dev/null 2>&1; then
      die "Die ID $var_ctid ist bereits belegt."
    fi
    CTID=$var_ctid
  else
    CTID=$(pvesh get /cluster/nextid)
    [[ "$CTID" =~ ^[0-9]+$ ]] || die "Konnte die nächste freie ID nicht ermitteln (Antwort: '$CTID')."
  fi
}

# --- Speicher & Vorlage -----------------------------------------------------------------------
first_storage() { # $1 = content-Typ, $2 = bevorzugt
  local list
  list=$(pvesm status --content "$1" 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}')
  [[ -n "$list" ]] || return 1
  if [[ -n "${2:-}" ]] && grep -qx "$2" <<<"$list"; then echo "$2"; else head -n1 <<<"$list"; fi
}

prepare_template() {
  TPL_STORAGE="${var_template_storage:-$(first_storage vztmpl local || true)}"
  [[ -n "$TPL_STORAGE" ]] || die "Kein Speicher für Container-Vorlagen gefunden (Inhaltstyp 'vztmpl'). Mit var_template_storage=… angeben."
  CT_STORAGE="${var_storage:-$(first_storage rootdir local-lvm || true)}"
  [[ -n "$CT_STORAGE" ]] || die "Kein Speicher für Container-Platten gefunden (Inhaltstyp 'rootdir'). Mit var_storage=… angeben."
  info "Speicher: Platte=$CT_STORAGE, Vorlagen=$TPL_STORAGE"

  info "Vorlagenliste aktualisieren…"
  run pveam update
  TPL=$(pveam available --section system 2>/dev/null | awk '{print $2}' | grep -E '^debian-12-standard_.*_amd64\.tar\.(zst|gz)$' | sort -V | tail -n1 || true)
  [[ -n "$TPL" ]] || die "Keine Debian-12-Vorlage in 'pveam available' gefunden."
  if ! pveam list "$TPL_STORAGE" 2>/dev/null | grep -q "$TPL"; then
    info "Lade Vorlage $TPL …"
    run pveam download "$TPL_STORAGE" "$TPL"
  fi
  ok "Vorlage: $TPL"
}

create_container() {
  local net="name=eth0,bridge=${var_bridge:-vmbr0}"
  if [[ -n "${var_ip:-}" ]]; then
    net+=",ip=${var_ip}"
    [[ -n "${var_gw:-}" ]] && net+=",gw=${var_gw}"
  else
    net+=",ip=dhcp"
  fi
  info "Lege Container $CTID ($HOSTNAME_CT) an: ${CPU} Kern(e), ${RAM} MB RAM, ${DISK} GB Platte…"
  CT_CREATED=1
  run pct create "$CTID" "$TPL_STORAGE:vztmpl/$TPL" \
    --hostname "$HOSTNAME_CT" \
    --cores "$CPU" --memory "$RAM" --swap 512 \
    --rootfs "$CT_STORAGE:$DISK" \
    --net0 "$net" \
    --unprivileged 1 --features nesting=1 \
    --onboot 1 --ostype debian \
    --tags "$APP" \
    --description "WerkstattDatenBank – https://github.com/${WDB_REPO}"
  run pct start "$CTID"
  ok "Container $CTID gestartet (onboot=1)"
}

ct_ip() { pct exec "$CTID" -- ip -4 -o addr show dev eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1; }

wait_for_network() {
  local i ip=""
  info "Warte auf Netzwerk im Container…"
  for i in $(seq 1 60); do
    ip=$(ct_ip || true)
    if [[ -n "$ip" ]] && pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1; then
      CT_IP=$ip
      ok "Netzwerk bereit: $CT_IP"
      return 0
    fi
    sleep 2
  done
  {
    echo "Container hat nach 120 s keine Verbindung (IP='${ip:-keine}')."
    echo "Prüfen: Bridge '${var_bridge:-vmbr0}', DHCP im Netz, DNS/Gateway."
    pct exec "$CTID" -- ip -4 addr 2>&1 || true
    pct exec "$CTID" -- ip route 2>&1 || true
  } | tee -a "$LOG" >&2
  return 1
}

# --- Provisionierung im Container -------------------------------------------------------------
provision() { # $1 = install|update
  local mode=$1 tmp
  tmp=$(mktemp)
  case "$WDB_PROVISION_SRC" in
    http://* | https://*)
      info "Lade provision.sh: $WDB_PROVISION_SRC"
      run wget -q -O "$tmp" "$WDB_PROVISION_SRC" ;;
    *)
      [[ -f "$WDB_PROVISION_SRC" ]] || die "WDB_PROVISION_SRC nicht lesbar: $WDB_PROVISION_SRC"
      cp "$WDB_PROVISION_SRC" "$tmp" ;;
  esac
  bash -n "$tmp" || die "provision.sh hat einen Syntaxfehler (heruntergeladene Datei: $tmp)."
  run pct push "$CTID" "$tmp" /root/wdb-provision.sh --perms 0700
  rm -f "$tmp"

  local envs=(MODE="$mode" WDB_PORT="$PORT" WDB_REPO="$WDB_REPO" WDB_BRANCH="$WDB_BRANCH" WDB_DEBUG="${WDB_DEBUG:-0}")
  [[ -n "$WDB_SRC_URL" ]] && envs+=(WDB_SRC_URL="$WDB_SRC_URL")

  info "Richte die Anwendung im Container ein ($mode)… (das dauert etwa eine Minute)"
  local rc=0
  pct exec "$CTID" -- env "${envs[@]}" bash /root/wdb-provision.sh 2>&1 | tee -a "$LOG" || rc=${PIPESTATUS[0]}
  if ((rc != 0)); then
    {
      echo "Einrichtung im Container fehlgeschlagen (Exit-Code $rc)."
      echo "Protokoll im Container: pct exec $CTID -- cat /var/log/${APP}-provision.log"
      echo "--- letzte Zeilen ---"
      pct exec "$CTID" -- tail -n 40 "/var/log/${APP}-provision.log" 2>&1 || true
    } | tee -a "$LOG" >&2
    return "$rc"
  fi
}

verify_from_host() {
  local port i
  port=$(pct exec "$CTID" -- sh -c "grep -E '^WDB_PORT=' /etc/${APP}.env | cut -d= -f2" | tr -d '\r\n')
  PORT=${port:-$PORT}
  CT_IP=${CT_IP:-$(ct_ip)}
  for i in 1 2 3 4 5; do
    if pct exec "$CTID" -- curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/stats"; then
      ok "Dienst aktiv: $(pct exec "$CTID" -- systemctl is-active "$APP.service") / $(pct exec "$CTID" -- systemctl is-enabled "$APP.service")"
      ok "HTTP-Check localhost:$PORT erfolgreich"
      return 0
    fi
    sleep 2
  done
  die "HTTP-Check auf localhost:$PORT im Container fehlgeschlagen (journalctl -u $APP -n 50 im Container ansehen)."
}

summary() {
  local token
  token=$(pct exec "$CTID" -- sh -c "grep -E '^WDB_TOKEN=' /etc/${APP}.env | cut -d= -f2" | tr -d '\r\n')
  cat <<EOF | tee -a "$LOG"

════════════════════════════════════════════════════════════
 WerkstattDatenBank ist bereit
────────────────────────────────────────────────────────────
 Oberfläche:    http://${CT_IP}:${PORT}
 Container:     CT ${CTID} (${HOSTNAME_CT}), startet automatisch mit dem Host
 Änderungen:    Zugangs-Token (nur zum Schreiben nötig):
                ${token}
 Konsole:       pct enter ${CTID}
 Daten laden:   siehe README – Importe mit  wdb-run import_eea.py <datei>
 Aktualisieren: Einzeiler einfach erneut ausführen
 Protokoll:     ${LOG}
════════════════════════════════════════════════════════════
EOF
}

main() {
  HOSTNAME_CT="${var_hostname:-$APP}"
  CPU="${var_cpu:-1}"
  RAM="${var_ram:-1024}"
  DISK="${var_disk:-8}"
  PORT="${var_port:-8080}"
  [[ "$CPU" =~ ^[0-9]+$ && "$RAM" =~ ^[0-9]+$ && "$DISK" =~ ^[0-9]+$ && "$PORT" =~ ^[0-9]+$ ]] \
    || die "var_cpu, var_ram, var_disk und var_port müssen Zahlen sein."

  info "WerkstattDatenBank-Installer (Protokoll: $LOG)"
  preflight

  local existing=""
  if [[ "${var_new:-0}" != "1" && -z "${var_ctid:-}" ]]; then existing=$(find_existing); fi

  if [[ -n "$existing" ]]; then
    CTID=$existing
    info "Container '$HOSTNAME_CT' existiert bereits (CT $CTID) → Aktualisierung"
    if [[ "$(pct status "$CTID" | awk '{print $2}')" != running ]]; then
      run pct start "$CTID"
    fi
    wait_for_network
    provision update
  else
    pick_ctid
    info "Neue Container-ID: $CTID"
    prepare_template
    create_container
    wait_for_network
    provision install
  fi

  verify_from_host
  summary
}

main "$@"
