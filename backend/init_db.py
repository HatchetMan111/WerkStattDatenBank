#!/usr/bin/env python3
"""Legt die Datenbank an. Mit --demo zusätzlich erkennbar erfundene Beispieldaten (zum Ausprobieren)."""
import sys

import wdb_db as db
import wdb_import as imp


def main():
    con = db.connect()
    db.init_schema(con)
    if "--demo" in sys.argv:
        erg = imp.demo_laden(con)
        print(f"Demo-Daten angelegt: {erg['artikel']} Artikel, {erg['fahrzeuge']} Fahrzeugvarianten.")
    con.commit()
    print(f"Datenbank bereit: {db.DB_PATH}")


if __name__ == "__main__":
    main()
