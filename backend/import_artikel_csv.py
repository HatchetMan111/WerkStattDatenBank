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
import csv
import sys

import wdb_db as db


def zahl(text):
    try:
        return float(str(text).replace(",", ".").strip())
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datei")
    ap.add_argument("--quelle", default="CSV-Import", help="Herkunft für die Quellenliste")
    a = ap.parse_args()

    con = db.connect()
    db.init_schema(con)
    n = 0
    with open(a.datei, newline="", encoding="utf-8-sig", errors="replace") as f:
        probe = f.readline()
        f.seek(0)
        trenner = max([";", ",", "\t"], key=probe.count)
        reader = csv.DictReader(f, delimiter=trenner)
        fehlt = [c for c in ("lieferant", "artikelnr", "bezeichnung") if c not in (reader.fieldnames or [])]
        if fehlt:
            sys.exit(f"Pflichtspalten fehlen: {fehlt}")
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
            ek = zahl(z.get("ek_netto") or "")
            if ek is not None:
                con.execute("INSERT OR REPLACE INTO preis(artikel_id, haendler, ek_netto) VALUES (?,?,?)",
                            (aid, (z.get("haendler") or "").strip(), ek))
            db.reindex_artikel(con, aid)
            n += 1
    anzahl = con.execute("SELECT COUNT(*) FROM artikel WHERE quelle = 'csv'").fetchone()[0]
    db.register_quelle(con, "csv", a.quelle, None, "Eigene bzw. lizenzierte Listen des Betriebs", anzahl)
    con.commit()
    print(f"{n} Artikel verarbeitet.")


if __name__ == "__main__":
    main()
