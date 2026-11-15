#!/usr/bin/env python3
"""Importiert die offenen EEA-Daten zur CO2-Überwachung neuer Pkw (Hersteller, Modell, Kraftstoff,
Hubraum, Leistung, CO2, Zulassungen).

Quelle: Europäische Umweltagentur (EEA), "Monitoring of CO2 emissions from passenger cars".
Die Datei (CSV) lädt man selbst von der EEA-Datenseite herunter. Die Weiterverwendung ist laut EEA
(sofern nicht anders angegeben) auch kommerziell kostenfrei erlaubt, wenn die Quelle genannt wird.

Beispiel:
  python3 import_eea.py co2_2023.csv co2_2024.csv
  python3 import_eea.py datei.csv --zeigen          # nur Spaltenzuordnung anzeigen
  python3 import_eea.py datei.csv --map ccm="ec (cm3)" --map kw="ep (KW)"

Alle gewünschten Jahre in EINEM Lauf angeben: Zulassungen werden je Lauf neu berechnet.
Die EEA-Daten enthalten keine HSN/TSN und keine Teile-Zuordnungen.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict

import wdb_db as db

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

ROEMISCH = re.compile(r"^[IVX]+$")


def kapital(token):
    if any(c.isdigit() for c in token) or len(token) <= 3 or ROEMISCH.match(token) or not token.isupper():
        return token
    return token.capitalize()


def schoen(text):
    """VOLKSWAGEN -> Volkswagen, GOLF VII -> Golf VII, ID.3 bleibt, BMW bleibt."""
    teile = " ".join(text.split())
    return " ".join("-".join(kapital(p) for p in tok.split("-")) for tok in teile.split(" "))


def zahl(text):
    try:
        return int(float(str(text).replace(",", ".").strip()))
    except ValueError:
        return 0


def finde_spalten(header, overrides):
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


def oeffne(pfad):
    f = open(pfad, newline="", encoding="utf-8-sig", errors="replace")
    probe = f.readline()
    f.seek(0)
    trenner = max([";", ",", "\t", "|"], key=probe.count)
    return f, csv.DictReader(f, delimiter=trenner)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dateien", nargs="+")
    ap.add_argument("--map", action="append", default=[], metavar="FELD=SPALTE",
                    help="Spaltenzuordnung überschreiben (Felder: " + ", ".join(ALIASE) + ")")
    ap.add_argument("--jahr", type=int, help="Berichtsjahr, falls die Datei keine Jahres-Spalte hat")
    ap.add_argument("--min-zulassungen", type=int, default=1)
    ap.add_argument("--zeigen", action="store_true", help="nur Spaltenzuordnung zeigen, nichts importieren")
    a = ap.parse_args()
    overrides = dict(m.split("=", 1) for m in a.map if "=" in m)

    agg = defaultdict(lambda: [0, 0, 0, 9999, 0])  # regs, co2*regs, regs mit co2, jahr_min, jahr_max
    zeilen = 0
    for pfad in a.dateien:
        f, reader = oeffne(pfad)
        sp = finde_spalten(reader.fieldnames or [], overrides)
        print(f"{pfad}: Spaltenzuordnung {sp}")
        fehlt = [k for k in ("make", "name") if k not in sp]
        if fehlt:
            sys.exit(f"Pflichtspalten nicht gefunden: {fehlt}. Mit --map zuordnen. Kopfzeile: {reader.fieldnames}")
        if a.zeigen:
            f.close()
            continue
        for row in reader:
            marke, modell = schoen(row.get(sp["make"], "")), schoen(row.get(sp["name"], ""))
            if not marke or not modell:
                continue
            ft = (row.get(sp.get("fuel", ""), "") or "").strip()
            kraft = KRAFTSTOFF.get(ft.lower(), ft.title())
            ccm, kw = zahl(row.get(sp.get("ccm", ""), 0)), zahl(row.get(sp.get("kw", ""), 0))
            regs = zahl(row.get(sp.get("regs", ""), 1)) or 1
            roh_co2 = (row.get(sp.get("co2", ""), "") or "").strip()
            hat_co2 = roh_co2 != ""  # 0 g/km (Elektro) ist ein gültiger Wert
            co2 = zahl(roh_co2)
            jahr = zahl(row.get(sp.get("year", ""), 0)) or a.jahr or 0
            e = agg[(marke, modell, kraft, ccm, kw)]
            e[0] += regs
            if hat_co2:
                e[1] += co2 * regs
                e[2] += regs
            if jahr:
                e[3], e[4] = min(e[3], jahr), max(e[4], jahr)
            zeilen += 1
        f.close()
    if a.zeigen:
        return

    con = db.connect()
    db.init_schema(con)
    hid_cache, mid_cache = {}, {}
    neu = 0
    for (marke, modell, kraft, ccm, kw), (regs, co2sum, co2n, jmin, jmax) in agg.items():
        if regs < a.min_zulassungen:
            continue
        hid = hid_cache.get(marke) or hid_cache.setdefault(marke, db.get_or_create_hersteller(con, marke))
        mid = mid_cache.get((hid, modell)) or mid_cache.setdefault((hid, modell), db.get_or_create_modell(con, hid, modell))
        von, bis = (jmin if jmin != 9999 else None), (jmax or None)
        co2 = round(co2sum / co2n) if co2n else None
        cur = con.execute(
            """INSERT INTO fahrzeug(modell_id, kraftstoff, hubraum_ccm, leistung_kw, baujahr_von, baujahr_bis,
                                    co2_wltp, zulassungen, quelle) VALUES (?,?,?,?,?,?,?,?, 'eea')
               ON CONFLICT(modell_id, kraftstoff, hubraum_ccm, leistung_kw, quelle) DO UPDATE SET
                 baujahr_von = MIN(COALESCE(baujahr_von, excluded.baujahr_von), COALESCE(excluded.baujahr_von, baujahr_von)),
                 baujahr_bis = MAX(COALESCE(baujahr_bis, excluded.baujahr_bis), COALESCE(excluded.baujahr_bis, baujahr_bis)),
                 co2_wltp = excluded.co2_wltp, zulassungen = excluded.zulassungen""",
            (mid, kraft, ccm, kw, von, bis, co2, regs))
        neu += cur.rowcount
    anzahl = con.execute("SELECT COUNT(*) FROM fahrzeug WHERE quelle = 'eea'").fetchone()[0]
    db.register_quelle(
        con, "eea", "Europäische Umweltagentur (EEA): CO2-Überwachung neuer Pkw",
        "https://sdi.eea.europa.eu/catalogue/srv/api/records/b4044b06-2e6b-4f8e-a6e6-66e0e98bb0dd",
        "EEA-Weiterverwendung: auch kommerziell erlaubt, Quellenangabe erforderlich (sofern nicht anders angegeben)",
        anzahl)
    con.commit()
    print(f"{zeilen} Zeilen gelesen, {len(agg)} Varianten aggregiert, {anzahl} EEA-Varianten in der Datenbank.")


if __name__ == "__main__":
    main()
