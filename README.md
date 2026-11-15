# WerkstattDatenBank

Selbst gehostete Fahrzeug- und Teiledatenbank für freie Werkstätten – aufgebaut aus **öffentlichen Daten und eigenen Einträgen**.
Läuft als LXC-Container auf Proxmox VE, Oberfläche mit React + Vite, Backend in reinem Python (SQLite, keine Fremdpakete).

> **Wichtig:** Die Datenbank enthält nur, was du selbst importierst oder einträgst. Öffentliche Quellen (z. B. EEA-Zulassungsdaten) liefern Fahrzeuge,
> aber **keine Teile-Zuordnungen, keine HSN/TSN und keine Preise**. Bestell-Passgenauigkeit immer über Fahrgestellnummer und Teilenummer prüfen.

## Installation (Einzeiler)

Auf dem **Proxmox-Host** als root ausführen (Shell des Hosts, nicht in einem Container):

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/WerkStattDatenBank/main/install/werkstattdatenbank.sh)"
```

(Das Repository muss öffentlich sein, sonst kann `raw.githubusercontent.com` die Datei nicht ausliefern.)

Das Skript

1. wählt die **nächste freie Container-ID** (`pvesh get /cluster/nextid`, oder `var_ctid=…`),
2. legt einen unprivilegierten Debian-12-LXC namens **`werkstattdatenbank`** an (1 Kern, 1 GB RAM, 8 GB Platte, `onboot: 1`, DHCP),
3. installiert Python 3, lädt die App aus diesem Repo, richtet Benutzer, Datenbank, Konfiguration und den systemd-Dienst ein,
4. prüft sich selbst (Dienst `active`/`enabled`, HTTP-Check auf `localhost:8080`) und zeigt am Ende die URL.

### Erwartete Ausgabe (gekürzt)

```
» Neue Container-ID: 120
✔ Vorlage: debian-12-standard_12.x-x_amd64.tar.zst
✔ Container 120 gestartet (onboot=1)
✔ Netzwerk bereit: 192.168.178.57
  Selbsttest ok: Dienst aktiv, API und Oberfläche antworten auf Port 8080.
✔ Dienst aktiv: active / enabled
✔ HTTP-Check localhost:8080 erfolgreich

 WerkstattDatenBank ist bereit
 Oberfläche:    http://192.168.178.57:8080
 Änderungen:    Zugangs-Token (nur zum Schreiben nötig): <zufällig erzeugt>
```

### Einstellungen (alle optional, als Umgebungsvariable vor dem Einzeiler)

| Variable | Bedeutung | Standard |
|---|---|---|
| `var_ctid` | Container-ID | nächste freie |
| `var_hostname` | Containername | `werkstattdatenbank` |
| `var_cpu` / `var_ram` / `var_disk` | Kerne / MB RAM / GB Platte | `1` / `1024` / `8` |
| `var_bridge` | Netzwerk-Bridge | `vmbr0` |
| `var_ip` / `var_gw` | feste IP, z. B. `192.168.178.60/24` und Gateway | DHCP |
| `var_storage` / `var_template_storage` | Speicher für Platte / Vorlage | automatisch (`local-lvm` / `local`) |
| `var_port` | Port der Oberfläche | `8080` |
| `var_new=1` | immer neuen Container anlegen (statt Update) | – |
| `WDB_REPO`, `WDB_BRANCH` | anderes Repo / Branch (Fork) | dieses Repo, `main` |
| `WDB_DEBUG=1` oder `--debug` | `bash -x`-Ablaufprotokoll ins Log | aus |
| `WDB_KEEP_ON_ERROR=1` | fehlgeschlagenen neuen Container behalten | wird gelöscht |

Beispiel: `var_ctid=150 var_ram=2048 var_ip=192.168.178.60/24 var_gw=192.168.178.1 bash -c "$(wget -qLO - …)"`

## Bedienung

* Oberfläche: `http://<Container-IP>:8080` – Fahrzeug wählen (Hersteller → Modell → Variante), Produktgruppe wählen oder suchen
  (Teilenummer, OE-Nummer, EAN, Bezeichnung; auch Teilwörter wie „scheibe“).
* **Lesen** ist frei im Netzwerk. **Schreiben** (neue Artikel, Zuordnungen, „verbaut“) braucht das Zugangs-Token; die Oberfläche fragt einmal danach.
  Das Token steht in `/etc/werkstattdatenbank.env` im Container (`pct exec <CTID> -- grep WDB_TOKEN /etc/werkstattdatenbank.env`).
* Ohne Token-Konfiguration ist die Datenbank außerhalb von localhost schreibgeschützt.
* Der Dienst ist **nicht für das offene Internet** gedacht. Nur im Werkstattnetz betreiben oder hinter einen Reverse-Proxy mit Anmeldung stellen.
* „Verbaut“-Buchungen speichern keine Kundendaten und keine Kennzeichen (DSGVO) – nur Datum, Auftragsnummer, km, Notiz.

## Daten laden

Importe laufen im Container mit dem Hilfsprogramm `wdb-run` (führt Python als Dienstbenutzer mit der richtigen Datenbank aus):

```bash
# Beispieldaten (erkennbar erfunden)
pct exec 120 -- wdb-run init_db.py --demo

# EEA-Fahrzeugdaten: CSV selbst von der EEA-Datenseite laden (Quellenangabe nötig), dann:
pct push 120 co2_2024.csv /root/co2_2024.csv
pct exec 120 -- wdb-run import_eea.py /root/co2_2024.csv

# Eigene/Großhändler-Artikelliste (Format: backend/beispiel_artikel.csv)
pct push 120 meine_artikel.csv /root/meine_artikel.csv
pct exec 120 -- wdb-run import_artikel_csv.py /root/meine_artikel.csv --quelle "Großhandel Müller"
```

Nutze nur Daten, die du verwenden darfst (eigene Listen, Händlerlisten im Rahmen der Händlerbedingungen, offene Daten mit Quellenangabe).
Es werden keine Daten fremder Kataloge kopiert.

## Aktualisieren

Den Einzeiler **einfach erneut ausführen**. Ist ein Container namens `werkstattdatenbank` vorhanden, wird er aktualisiert:
neuer Code, **Datenbank und Token bleiben erhalten**; die vorige Version bleibt als `/opt/werkstattdatenbank.old-<Zeit>` im Container
(die zwei neuesten Sicherungen). Schlägt das Update fehl, wird automatisch zurückgerollt.

## Deinstallieren

```bash
pct stop <CTID>
pct destroy <CTID> --purge     # löscht den Container samt Datenbank!
```

Vorher ggf. sichern: `pct exec <CTID> -- cat /var/lib/werkstattdatenbank/wdb.sqlite > wdb-backup.sqlite`
(oder `vzdump <CTID>` für eine komplette Sicherung).

## Fehlersuche

* Installer-Protokoll auf dem Host: `/var/log/werkstattdatenbank-install-<Zeit>.log` (enthält jeweils die komplette Ausgabe fehlgeschlagener Befehle,
  Exit-Codes und den Aufrufstapel). Mit `WDB_DEBUG=1` zusätzlich ein `bash -x`-Ablaufprotokoll.
* Protokoll im Container: `/var/log/werkstattdatenbank-provision.log`
* Dienst: `pct exec <CTID> -- systemctl status werkstattdatenbank` und `pct exec <CTID> -- journalctl -u werkstattdatenbank -n 100 --no-pager`
* Container zum Untersuchen behalten: `WDB_KEEP_ON_ERROR=1`, dann `pct enter <CTID>`.
* Konfiguration: `/etc/werkstattdatenbank.env` (Port, Token, Pfade). Nach Änderung: `systemctl restart werkstattdatenbank`.

## Abnahmetest auf dem Proxmox-Host

```bash
bash test/verify.sh [CTID]
```

Prüft Dienststatus, `onboot`, API, Oberfläche und Erreichbarkeit über die Container-IP, **startet den Container neu** und prüft alles erneut.
Das Protokoll liegt unter `/var/log/werkstattdatenbank-verify-<Zeit>.log`; Ergebnis: `PASS`/`FAIL` je Prüfpunkt, Exit-Code 0 = alles in Ordnung.

## Entwicklung

```bash
cd backend && python3 init_db.py --demo && python3 app.py        # API + Oberfläche auf http://127.0.0.1:8080
cd frontend && npm install && npm run dev                        # Vite-Entwicklungsserver, /api wird an 127.0.0.1:8080 weitergeleitet
cd frontend && npm test                                          # Oberflächentest (Testdaten)
cd frontend && WDB_E2E_BASE=http://127.0.0.1:8080 npm test       # derselbe Test gegen das echte Backend
cd frontend && npm run build                                     # erzeugt frontend/dist
```

**`frontend/dist` ist absichtlich eingecheckt**, damit im Container kein Node.js nötig ist. Nach Änderungen am Frontend: `npm run build` und `frontend/dist` committen.

Aufbau: `backend/` (Python, SQLite/FTS5), `frontend/` (React + Vite + TypeScript), `install/` (Host-Installer, Container-Einrichtung, systemd-Unit), `test/` (Abnahmetest).

## Sicherheit in Kürze

Schreibzugriffe nur mit Token; ohne Token außerhalb von localhost schreibgeschützt · POST nur mit `Content-Type: application/json` ·
Host-Prüfung gegen DNS-Rebinding bei localhost-Betrieb · CSP `default-src 'self'` · kein `innerHTML` · Schutz gegen Pfad-Traversal ·
Dienst läuft als unprivilegierter Benutzer `wdb` im unprivilegierten Container.

## Was getestet ist – und was nicht

Getestet (in einer Entwicklungsumgebung): Backend-API und Importer, React-Oberfläche (Vitest, mit Testdaten **und** gegen das echte Backend),
`bash -n` und `shellcheck` aller Skripte, eine **Simulation** des Installers mit nachgebauten `pct`/`pvesh`/`pveam`/`pvesm`/`systemctl`-Befehlen
(Neuinstallation, Update mit Datenerhalt, Neustart-Test, Fehlerfälle, Aufräumen).

**Nicht** getestet: ein echter Lauf auf einem Proxmox-Host (echte Container-Erstellung, apt im Container, echtes systemd, echter Neustart).
Bitte nach der ersten Installation `bash test/verify.sh` auf dem Host ausführen und bei Abweichungen das Installer-Protokoll prüfen.

## Datenquellen und Lizenz

Eigene Einträge, Importe aus eigenen/Händlerlisten und offene EEA-Daten (Weiterverwendung mit Quellenangabe). Die App zeigt die verwendeten Quellen im Seitenfuß an.
Quellcode: Lizenz nach Wahl des Repository-Inhabers (bitte `LICENSE` ergänzen).
