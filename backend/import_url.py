#!/usr/bin/env python3
"""Lädt eine frei zugängliche Datei (CSV, ZIP oder GZ) aus dem Internet und importiert sie.

Beispiel:
  python3 import_url.py https://example.org/daten.zip
  python3 import_url.py https://example.org/liste.csv --typ artikel --quelle "Großhandel Müller"

Dasselbe kann man in der Oberfläche unter „Daten importieren“ tun.
"""
import argparse
import shutil
import sys

import wdb_db as db
import wdb_import as imp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--typ", choices=["auto", "eea", "artikel"], default="auto")
    ap.add_argument("--quelle", default="Download", help="Herkunft für die Quellenliste (nur Artikellisten)")
    a = ap.parse_args()
    ordner = imp.neuer_ordner()
    con = None
    try:
        ziel = ordner / "download.bin"
        n = imp.lade_url(a.url, ziel, progress=lambda phase, n: print(f"\r  {phase}: {n // 1048576} MB", end="", file=sys.stderr))
        print(f"\n{n // 1024} KB geladen.", file=sys.stderr)
        dateien = imp.aufbereiten(ziel, ordner)
        art = a.typ if a.typ != "auto" else imp.erkenne_typ(dateien[0])
        con = db.connect()
        if art == "eea":
            erg = imp.import_eea(con, dateien, progress=lambda phase, n: print(f"  {phase}: {n}", file=sys.stderr))
        else:
            erg = imp.import_artikel(con, dateien[0], a.quelle)
        print("Fertig:", ", ".join(f"{k}={v}" for k, v in erg.items()))
    except imp.ImportFehler as e:
        sys.exit(f"Import fehlgeschlagen: {e}")
    finally:
        if con is not None:
            con.close()
        shutil.rmtree(ordner, ignore_errors=True)


if __name__ == "__main__":
    main()
