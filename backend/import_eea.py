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
import sys

import wdb_db as db
import wdb_import as imp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dateien", nargs="+")
    ap.add_argument("--map", action="append", default=[], metavar="FELD=SPALTE",
                    help="Spaltenzuordnung überschreiben (Felder: " + ", ".join(imp.ALIASE) + ")")
    ap.add_argument("--jahr", type=int, help="Berichtsjahr, falls die Datei keine Jahres-Spalte hat")
    ap.add_argument("--min-zulassungen", type=int, default=1)
    ap.add_argument("--zeigen", action="store_true", help="nur Spaltenzuordnung zeigen, nichts importieren")
    a = ap.parse_args()
    overrides = dict(m.split("=", 1) for m in a.map if "=" in m)
    con = db.connect()
    try:
        erg = imp.import_eea(con, a.dateien, overrides, a.jahr, a.min_zulassungen,
                             progress=lambda phase, n: print(f"  {phase}: {n}", file=sys.stderr), zeigen=a.zeigen)
    except imp.ImportFehler as e:
        sys.exit(str(e))
    if a.zeigen:
        for pfad, sp in erg["zuordnung"].items():
            print(f"{pfad}: Spaltenzuordnung {sp}")
        return
    print(f"{erg['zeilen']} Zeilen gelesen, {erg['varianten_aggregiert']} Varianten aggregiert, "
          f"{erg['in_datenbank']} EEA-Varianten in der Datenbank.")


if __name__ == "__main__":
    main()
