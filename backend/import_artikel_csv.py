#!/usr/bin/env python3
"""Importiert Artikel aus einer CSV-Datei, z. B. aus einer Preisliste des Großhändlers oder eigener Pflege.

Spalten (Kopfzeile Pflicht, Reihenfolge egal):
  lieferant;artikelnr;bezeichnung;gruppe;ean;oe;ek_netto;haendler

  gruppe    Name einer Produktgruppe (z. B. Bremsbeläge), leer = ohne Gruppe
  oe        Hersteller:Nummer, mehrere mit | getrennt  (z. B. Musterwagen:OE-DEMO-1|Musterwagen:OE-DEMO-9)
  ek_netto  Dezimalkomma oder -punkt

Beispiel:  python3 import_artikel_csv.py beispiel_artikel.csv --quelle "Großhandel Müller"
Nutze nur Daten, die du verwenden darfst (eigene Listen, Händlerlisten im Rahmen der Händlerbedingungen).
"""
import argparse
import sys

import wdb_db as db
import wdb_import as imp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei")
    ap.add_argument("--quelle", default="CSV-Import", help="Herkunft für die Quellenliste")
    a = ap.parse_args()
    con = db.connect()
    try:
        erg = imp.import_artikel(con, a.datei, a.quelle)
    except imp.ImportFehler as e:
        sys.exit(str(e))
    print(f"{erg['verarbeitet']} Artikel verarbeitet.")


if __name__ == "__main__":
    main()
