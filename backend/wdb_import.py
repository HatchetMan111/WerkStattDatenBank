"""WerkstattDatenBank: Import-Logik (gemeinsam für Kommandozeile und Oberfläche).

* EEA-Fahrzeugdaten (CSV, auch als .zip oder .gz)
* Eigene/Händler-Artikellisten (CSV)
* Download aus dem Internet mit Schutz gegen Zugriffe auf interne Adressen
* ein Hintergrund-Job (immer nur einer gleichzeitig) mit abfragbarem Status
"""
import csv
import gzip
import ipaddress
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import wdb_db as db

MAX_ENTPACKT = int(os.environ.get("WDB_MAX_IMPORT_MB", "4096")) * 1024 * 1024
ERLAUBE_PRIVAT = os.environ.get("WDB_ALLOW_PRIVATE_URLS", "") == "1"  # nur für Tests
USER_AGENT = "WerkstattDatenBank/1.0 (+https://github.com/HatchetMan111/WerkStattDatenBank)"

EEA_NAME = "Europäische Umweltagentur (EEA): CO2-Überwachung neuer Pkw"
EEA_URL = "https://www.eea.europa.eu/en/datahub/datahubitem-view/fa8b1229-3db6-495d-b18e-9c9b3267c02b"
EEA_LIZENZ = "CC BY 4.0 (EEA / Europäische Kommission, GD CLIMA) – Quellenangabe erforderlich"


class ImportFehler(Exception):
    """Fehler, dessen Text direkt für den Benutzer bestimmt ist."""


def arbeitsordner():
    return db.DB_PATH.parent / "import-tmp"


# ------------------------------------------------------------------------------------------------
# EEA-Fahrzeugdaten
# ------------------------------------------------------------------------------------------------
ALIASE = {
    "make": ["mk", "make"],
    "name": ["cn", "commercial name", "commercial_name", "commercialname"],
    "fuel": ["ft", "fuel type", "fuel_type"],
    "ccm": ["ec (cm3)", "ec", "engine capacity", "engine capacity (cm3)"],
    "kw": ["ep (kw)", "ep", "engine power", "engine power (kw)"],
    "co2": ["ewltp (g/km)", "ewltp", "specific co2 emissions (g/km)"],
    "year": ["year", "registration year", "reporting year"],
    "regs": ["r", "registrations", "total new registrations"],
}

KRAFTSTOFF = {
    "petrol": "Benzin", "diesel": "Diesel", "lpg": "Autogas (LPG)", "ng": "Erdgas (CNG)", "e85": "E85",
    "electric": "Elektro", "hydrogen": "Wasserstoff", "petrol/electric": "Benzin/Elektro (Hybrid)",
    "diesel/electric": "Diesel/Elektro (Hybrid)", "ng-biomethane": "Erdgas/Biomethan",
    "ng_biomethane": "Erdgas/Biomethan",
}


def kapital(token):
    if any(c.isdigit() for c in token) or len(token) <= 3 or (token and all(c in "IVX" for c in token)) or not token.isupper():
        return token
    return token.capitalize()


def schoen(text):
    """VOLKSWAGEN -> Volkswagen, GOLF VII -> Golf VII, ID.3 bleibt, BMW bleibt."""
    teile = " ".join(text.split())
    return " ".join("-".join(kapital(p) for p in tok.split("-")) for tok in teile.split(" "))


def zahl_int(text):
    try:
        return int(float(str(text).replace(",", ".").strip()))
    except ValueError:
        return 0


def zahl_float(text):
    try:
        return float(str(text).replace(",", ".").strip())
    except ValueError:
        return None


def finde_spalten(header, overrides=None):
    overrides = overrides or {}
    low = {h.strip().lower(): h for h in header}
    out = {}
    for feld, namen in ALIASE.items():
        if feld in overrides:
            out[feld] = overrides[feld]
            continue
        for n in namen:
            if n in low:
                out[feld] = low[n]
                break
    return out


def oeffne(pfad, trenner_kandidaten=(";", ",", "\t", "|")):
    f = open(pfad, newline="", encoding="utf-8-sig", errors="replace")
    probe = f.readline()
    f.seek(0)
    trenner = max(trenner_kandidaten, key=probe.count)
    return f, csv.DictReader(f, delimiter=trenner)


def erkenne_typ(pfad):
    """'artikel' (Spalten lieferant/artikelnr/bezeichnung), 'eea' (Marke + Modellname) oder Fehler."""
    f, reader = oeffne(pfad)
    try:
        header = reader.fieldnames or []
    finally:
        f.close()
    low = {h.strip().lower() for h in header}
    if {"lieferant", "artikelnr", "bezeichnung"} <= low:
        return "artikel"
    sp = finde_spalten(header)
    if "make" in sp and "name" in sp:
        return "eea"
    raise ImportFehler(
        "Dateityp nicht erkannt. Erwartet: Artikelliste (Spalten lieferant;artikelnr;bezeichnung) oder "
        f"EEA-Fahrzeugdaten (Spalten Mk und Cn). Gefundene Kopfzeile: {header[:15]}")


def import_eea(con, pfade, overrides=None, jahr=None, min_zulassungen=1, progress=None, zeigen=False):
    """Liest EEA-CSV-Dateien und legt Hersteller, Modelle und Fahrzeugvarianten an/aktualisiert sie.

    Alle gewünschten Jahre in EINEM Lauf übergeben: Zulassungen werden je Lauf neu berechnet.
    """
    progress = progress or (lambda phase, n: None)
    agg = defaultdict(lambda: [0, 0, 0, 9999, 0])  # regs, co2*regs, regs mit co2, jahr_min, jahr_max
    zeilen = 0
    zuordnung = {}
    for pfad in pfade:
        f, reader = oeffne(pfad)
        try:
            sp = finde_spalten(reader.fieldnames or [], overrides)
            zuordnung[str(pfad)] = sp
            fehlt = [k for k in ("make", "name") if k not in sp]
            if fehlt:
                raise ImportFehler(f"Pflichtspalten nicht gefunden: {fehlt}. Kopfzeile: {reader.fieldnames}")
            if zeigen:
                continue
            for row in reader:
                marke, modell = schoen(row.get(sp["make"], "")), schoen(row.get(sp["name"], ""))
                if not marke or not modell:
                    continue
                ft = (row.get(sp.get("fuel", ""), "") or "").strip()
                kraft = KRAFTSTOFF.get(ft.lower(), ft.title())
                ccm, kw = zahl_int(row.get(sp.get("ccm", ""), 0)), zahl_int(row.get(sp.get("kw", ""), 0))
                regs = zahl_int(row.get(sp.get("regs", ""), 1)) or 1
                roh_co2 = (row.get(sp.get("co2", ""), "") or "").strip()
                hat_co2 = roh_co2 != ""  # 0 g/km (Elektro) ist ein gültiger Wert
                co2 = zahl_int(roh_co2)
                j = zahl_int(row.get(sp.get("year", ""), 0)) or jahr or 0
                e = agg[(marke, modell, kraft, ccm, kw)]
                e[0] += regs
                if hat_co2:
                    e[1] += co2 * regs
                    e[2] += regs
                if j:
                    e[3], e[4] = min(e[3], j), max(e[4], j)
                zeilen += 1
                if zeilen % 50000 == 0:
                    progress("Zeilen lesen", zeilen)
        finally:
            f.close()
    if zeigen:
        return {"zuordnung": zuordnung}

    progress("In Datenbank schreiben", zeilen)
    db.init_schema(con)
    hid_cache, mid_cache = {}, {}
    for (marke, modell, kraft, ccm, kw), (regs, co2sum, co2n, jmin, jmax) in agg.items():
        if regs < min_zulassungen:
            continue
        hid = hid_cache.get(marke) or hid_cache.setdefault(marke, db.get_or_create_hersteller(con, marke))
        mid = mid_cache.get((hid, modell)) or mid_cache.setdefault((hid, modell), db.get_or_create_modell(con, hid, modell))
        von, bis = (jmin if jmin != 9999 else None), (jmax or None)
        co2 = round(co2sum / co2n) if co2n else None
        con.execute(
            """INSERT INTO fahrzeug(modell_id, kraftstoff, hubraum_ccm, leistung_kw, baujahr_von, baujahr_bis,
                                    co2_wltp, zulassungen, quelle) VALUES (?,?,?,?,?,?,?,?, 'eea')
               ON CONFLICT(modell_id, kraftstoff, hubraum_ccm, leistung_kw, quelle) DO UPDATE SET
                 baujahr_von = MIN(COALESCE(baujahr_von, excluded.baujahr_von), COALESCE(excluded.baujahr_von, baujahr_von)),
                 baujahr_bis = MAX(COALESCE(baujahr_bis, excluded.baujahr_bis), COALESCE(excluded.baujahr_bis, baujahr_bis)),
                 co2_wltp = excluded.co2_wltp, zulassungen = excluded.zulassungen""",
            (mid, kraft, ccm, kw, von, bis, co2, regs))
    anzahl = con.execute("SELECT COUNT(*) FROM fahrzeug WHERE quelle = 'eea'").fetchone()[0]
    db.register_quelle(con, "eea", EEA_NAME, EEA_URL, EEA_LIZENZ, anzahl)
    con.commit()
    return {"typ": "eea", "zeilen": zeilen, "varianten_aggregiert": len(agg), "in_datenbank": anzahl}


# ------------------------------------------------------------------------------------------------
# Artikellisten
# ------------------------------------------------------------------------------------------------
def import_artikel(con, pfad, quelle="CSV-Import", progress=None):
    """Spalten: lieferant;artikelnr;bezeichnung;gruppe;ean;oe;ek_netto;haendler (Pflicht: die ersten drei)."""
    progress = progress or (lambda phase, n: None)
    db.init_schema(con)
    n = 0
    f, reader = oeffne(pfad, (";", ",", "\t"))
    try:
        fehlt = [c for c in ("lieferant", "artikelnr", "bezeichnung") if c not in (reader.fieldnames or [])]
        if fehlt:
            raise ImportFehler(f"Pflichtspalten fehlen: {fehlt}. Kopfzeile: {reader.fieldnames}")
        for z in reader:
            lief, nr, bez = (z.get("lieferant") or "").strip(), (z.get("artikelnr") or "").strip(), (z.get("bezeichnung") or "").strip()
            if not (lief and db.norm(nr) and bez):
                continue
            gid = db.gruppe_id_by_name(con, z.get("gruppe") or "")
            con.execute(
                """INSERT INTO artikel(lieferant, artikelnr, artikelnr_norm, bezeichnung, produktgruppe_id, ean, quelle)
                   VALUES (?,?,?,?,?,?,'csv')
                   ON CONFLICT(lieferant, artikelnr_norm) DO UPDATE SET bezeichnung=excluded.bezeichnung,
                     produktgruppe_id=COALESCE(excluded.produktgruppe_id, produktgruppe_id),
                     ean=COALESCE(excluded.ean, ean)""",
                (lief, nr, db.norm(nr), bez, gid, (z.get("ean") or "").strip() or None))
            aid = con.execute("SELECT id FROM artikel WHERE lieferant=? AND artikelnr_norm=?", (lief, db.norm(nr))).fetchone()[0]
            for teil in (z.get("oe") or "").split("|"):
                teil = teil.strip()
                if not teil:
                    continue
                h, _, num = teil.partition(":") if ":" in teil else ("", "", teil)
                if db.norm(num):
                    con.execute("INSERT OR IGNORE INTO oe_nummer VALUES (?,?,?,?)", (aid, h.strip(), num.strip(), db.norm(num)))
            ek = zahl_float(z.get("ek_netto") or "")
            if ek is not None:
                con.execute("INSERT OR REPLACE INTO preis(artikel_id, haendler, ek_netto) VALUES (?,?,?)",
                            (aid, (z.get("haendler") or "").strip(), ek))
            db.reindex_artikel(con, aid)
            n += 1
            if n % 2000 == 0:
                con.commit()
                progress("Artikel verarbeiten", n)
    finally:
        f.close()
    anzahl = con.execute("SELECT COUNT(*) FROM artikel WHERE quelle = 'csv'").fetchone()[0]
    db.register_quelle(con, "csv", (quelle or "CSV-Import")[:120], None, "Eigene bzw. lizenzierte Listen des Betriebs", anzahl)
    con.commit()
    return {"typ": "artikel", "verarbeitet": n, "in_datenbank": anzahl}


# ------------------------------------------------------------------------------------------------
# Dateien vorbereiten (.zip / .gz entpacken) und aus dem Internet laden
# ------------------------------------------------------------------------------------------------
def aufbereiten(pfad, ordner):
    """Gibt die zu lesenden CSV-Dateien zurück. Entpackt .zip und .gz mit Größenbegrenzung."""
    pfad = Path(pfad)
    ordner = Path(ordner)
    if zipfile.is_zipfile(pfad):
        out, gesamt = [], 0
        with zipfile.ZipFile(pfad) as z:
            for i, info in enumerate(z.infolist()):
                if info.is_dir() or not info.filename.lower().endswith((".csv", ".txt", ".tsv")):
                    continue
                gesamt += info.file_size
                if gesamt > MAX_ENTPACKT:
                    raise ImportFehler(f"Archiv entpackt größer als {MAX_ENTPACKT // 1048576} MB (WDB_MAX_IMPORT_MB).")
                ziel = ordner / f"entpackt-{i}.csv"
                with z.open(info) as src, open(ziel, "wb") as dst:
                    _kopiere_begrenzt(src, dst, MAX_ENTPACKT)
                out.append(ziel)
        if not out:
            raise ImportFehler("Das ZIP-Archiv enthält keine CSV-/TXT-Datei.")
        return out
    with open(pfad, "rb") as f:
        magic = f.read(2)
    if magic == b"\x1f\x8b":
        ziel = ordner / "entpackt-gz.csv"
        with gzip.open(pfad, "rb") as src, open(ziel, "wb") as dst:
            _kopiere_begrenzt(src, dst, MAX_ENTPACKT)
        return [ziel]
    return [pfad]


def _kopiere_begrenzt(src, dst, limit):
    n = 0
    while True:
        block = src.read(1 << 20)
        if not block:
            return
        n += len(block)
        if n > limit:
            raise ImportFehler(f"Datei entpackt größer als {limit // 1048576} MB (WDB_MAX_IMPORT_MB).")
        dst.write(block)


def pruefe_url(url):
    """Nur https; keine Zugangsdaten in der URL; Ziel darf keine interne Adresse sein (Schutz vor SSRF)."""
    u = urllib.parse.urlparse(url.strip())
    erlaubt = ("https", "http") if ERLAUBE_PRIVAT else ("https",)
    if u.scheme not in erlaubt:
        raise ImportFehler("Nur https://-Adressen sind erlaubt.")
    if not u.hostname or u.username or u.password:
        raise ImportFehler("Ungültige Adresse (Host fehlt oder Zugangsdaten in der URL).")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ImportFehler(f"Adresse '{u.hostname}' nicht auflösbar: {e}")
    if not ERLAUBE_PRIVAT:
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if not ip.is_global:
                raise ImportFehler(f"Adresse zeigt auf eine interne Adresse ({ip}) – nicht erlaubt.")
    return u.geturl()


class _KeinRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def lade_url(url, ziel, max_bytes=None, progress=None):
    """Lädt eine Datei (max. 5 Weiterleitungen, jede wird erneut geprüft)."""
    max_bytes = max_bytes or MAX_ENTPACKT
    progress = progress or (lambda phase, n: None)
    opener = urllib.request.build_opener(_KeinRedirect)
    aktuell = pruefe_url(url)
    for _ in range(6):
        req = urllib.request.Request(aktuell, headers={"User-Agent": USER_AGENT})
        try:
            resp = opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                aktuell = pruefe_url(urllib.parse.urljoin(aktuell, e.headers["Location"]))
                continue
            raise ImportFehler(f"Download fehlgeschlagen: HTTP {e.code} {e.reason} ({aktuell})")
        except (urllib.error.URLError, OSError) as e:
            raise ImportFehler(f"Download fehlgeschlagen: {e} ({aktuell})")
        break
    else:
        raise ImportFehler("Zu viele Weiterleitungen.")
    n = 0
    with resp, open(ziel, "wb") as out:
        laenge = int_or_none(resp.headers.get("Content-Length"))
        if laenge and laenge > max_bytes:
            raise ImportFehler(f"Datei ist {laenge // 1048576} MB groß – Grenze {max_bytes // 1048576} MB (WDB_MAX_IMPORT_MB).")
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            n += len(block)
            if n > max_bytes:
                raise ImportFehler(f"Download größer als {max_bytes // 1048576} MB – abgebrochen.")
            out.write(block)
            progress("Herunterladen", n)
    if n == 0:
        raise ImportFehler("Der Download war leer.")
    return n


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------
# Hintergrund-Job (immer nur einer)
# ------------------------------------------------------------------------------------------------
_lock = threading.Lock()
_status = {"id": 0, "state": "leer", "phase": "", "fortschritt": 0, "name": "", "ergebnis": None,
           "fehler": None, "details": None, "start": None, "ende": None}


def status():
    with _lock:
        return dict(_status)


def _setze(**kw):
    with _lock:
        _status.update(kw)


def laeuft():
    return status()["state"] == "laeuft"


def aufraeumen_start():
    """Reste abgebrochener Importe beim Serverstart entfernen."""
    shutil.rmtree(arbeitsordner(), ignore_errors=True)


def neuer_ordner():
    arbeitsordner().mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=arbeitsordner()))


def starte(name, ordner, typ="auto", quelle=None, url=None, datei=None, quelle_id=None):
    """Startet den Import im Hintergrund. `datei` liegt bereits in `ordner`, bei `url` wird sie geladen."""
    with _lock:
        if _status["state"] == "laeuft":
            shutil.rmtree(ordner, ignore_errors=True)
            raise ImportFehler("Es läuft bereits ein Import. Bitte warten, bis er fertig ist.")
        job_id = _status["id"] + 1
        _status.update(id=job_id, state="laeuft", phase="Start", fortschritt=0, name=name, ergebnis=None,
                       fehler=None, details=None, start=time.time(), ende=None)
    t = threading.Thread(target=_lauf, args=(job_id, ordner, typ, quelle, url, datei, quelle_id), daemon=True, name=f"import-{job_id}")
    t.start()
    return job_id


def _lauf(job_id, ordner, typ, quelle, url, datei, quelle_id):
    def fortschritt(phase, n):
        _setze(phase=phase, fortschritt=n)

    con = None
    try:
        if url:
            datei = ordner / "download.bin"
            lade_url(url, datei, progress=fortschritt)
        fortschritt("Datei prüfen", 0)
        dateien = aufbereiten(datei, ordner)
        art = typ if typ in ("eea", "artikel") else erkenne_typ(dateien[0])
        con = db.connect()
        if art == "eea":
            erg = import_eea(con, dateien, progress=fortschritt)
        else:
            erg = import_artikel(con, dateien[0], quelle or "CSV-Import", progress=fortschritt)
        if quelle_id:
            con.execute("UPDATE import_quelle SET letzter_lauf = datetime('now'), ergebnis = ? WHERE id = ?",
                        ("OK: " + ", ".join(f"{k}={v}" for k, v in erg.items() if k != "typ"), quelle_id))
            con.commit()
        _setze(state="fertig", phase="Fertig", ergebnis=erg, ende=time.time())
    except ImportFehler as e:
        _fehler(con, quelle_id, str(e), None)
    except Exception as e:  # unerwartet: vollständige Fehlerkette in Status (nur für Berechtigte) und Journal
        tb = traceback.format_exc()
        print(f"Import {job_id} fehlgeschlagen:\n{tb}", file=sys.stderr, flush=True)
        _fehler(con, quelle_id, f"Unerwarteter Fehler: {type(e).__name__}: {e}", tb)
    finally:
        if con is not None:
            con.close()
        shutil.rmtree(ordner, ignore_errors=True)


def _fehler(con, quelle_id, text, details):
    if con is not None and quelle_id:
        try:
            con.execute("UPDATE import_quelle SET letzter_lauf = datetime('now'), ergebnis = ? WHERE id = ?",
                        ("Fehler: " + text[:300], quelle_id))
            con.commit()
        except Exception:
            pass
    _setze(state="fehler", phase="Fehlgeschlagen", fehler=text, details=details, ende=time.time())
