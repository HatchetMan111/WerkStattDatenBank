#!/usr/bin/env python3
"""Legt die Datenbank an. Mit --demo zusätzlich erkennbar erfundene Beispieldaten."""
import sys

import wdb_db as db


def demo(con):
    """Erfundene Daten: Hersteller 'Musterwagen', Artikel 'DEMO-...'. Keine echten Fahrzeuge oder Teile."""
    hid = db.get_or_create_hersteller(con, "Musterwagen (Demo)")
    mid = db.get_or_create_modell(con, hid, "Muster 1")
    fz = []
    for kraftstoff, ccm, kw in [("Benzin", 1197, 81), ("Diesel", 1598, 85), ("Benzin", 1395, 110)]:
        cur = con.execute(
            """INSERT OR IGNORE INTO fahrzeug(modell_id, kraftstoff, hubraum_ccm, leistung_kw,
               baujahr_von, baujahr_bis, quelle) VALUES (?,?,?,?,2015,2020,'demo')""",
            (mid, kraftstoff, ccm, kw),
        )
        fz.append(cur.lastrowid or con.execute(
            "SELECT id FROM fahrzeug WHERE modell_id=? AND kraftstoff=? AND hubraum_ccm=? AND leistung_kw=? AND quelle='demo'",
            (mid, kraftstoff, ccm, kw)).fetchone()[0])

    artikel = [
        ("Demo-Teile", "DEMO-BB-1000", "Bremsbelagsatz Vorderachse (Demo)", "Bremsbeläge", [("Musterwagen", "OE-DEMO-1")], [0, 1, 2], 24.90),
        ("Demo-Teile", "DEMO-BS-2000", "Bremsscheibe belüftet, Satz (Demo)", "Bremsscheiben", [("Musterwagen", "OE-DEMO-2")], [1, 2], 58.00),
        ("Demo-Teile", "DEMO-OF-3000", "Ölfilter (Demo)", "Ölfilter", [("Musterwagen", "OE-DEMO-3")], [0, 1], 6.50),
        ("Demo-Teile", "DEMO-ZK-4000", "Zündkerze (Demo)", "Zündkerzen", [("Musterwagen", "OE-DEMO-4")], [0, 2], 7.20),
    ]
    for lief, nr, bez, gruppe, oes, idx, ek in artikel:
        cur = con.execute(
            "INSERT OR IGNORE INTO artikel(lieferant, artikelnr, artikelnr_norm, bezeichnung, produktgruppe_id, quelle) VALUES (?,?,?,?,?,'demo')",
            (lief, nr, db.norm(nr), bez, db.gruppe_id_by_name(con, gruppe)),
        )
        aid = cur.lastrowid or con.execute(
            "SELECT id FROM artikel WHERE lieferant=? AND artikelnr_norm=?", (lief, db.norm(nr))).fetchone()[0]
        for h, n in oes:
            con.execute("INSERT OR IGNORE INTO oe_nummer VALUES (?,?,?,?)", (aid, h, n, db.norm(n)))
        for i in idx:
            con.execute("INSERT OR IGNORE INTO artikel_fahrzeug(artikel_id, fahrzeug_id, quelle) VALUES (?,?, 'demo')", (aid, fz[i]))
        con.execute(
            "INSERT OR REPLACE INTO preis(artikel_id, haendler, ek_netto) VALUES (?, 'Demo-Großhandel', ?)", (aid, ek)
        )
        db.reindex_artikel(con, aid)
    db.register_quelle(con, "demo", "Demo-Daten (erfunden)", None, "Nur zum Ausprobieren, keine echten Teile oder Fahrzeuge", len(artikel))


def main():
    con = db.connect()
    db.init_schema(con)
    if "--demo" in sys.argv:
        demo(con)
        print("Demo-Daten angelegt.")
    con.commit()
    print(f"Datenbank bereit: {db.DB_PATH}")


if __name__ == "__main__":
    main()
