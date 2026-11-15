"""Datenbank-Schema und Hilfsfunktionen der WerkstattDatenBank."""
import os
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("WDB_DB", BASE / "data" / "wdb.sqlite"))

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS hersteller (
  id   INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS modell (
  id            INTEGER PRIMARY KEY,
  hersteller_id INTEGER NOT NULL REFERENCES hersteller(id),
  name          TEXT NOT NULL,
  UNIQUE (hersteller_id, name)
);

-- Eine Zeile = eine Fahrzeugvariante (Modell + Kraftstoff + Hubraum + Leistung).
CREATE TABLE IF NOT EXISTS fahrzeug (
  id          INTEGER PRIMARY KEY,
  modell_id   INTEGER NOT NULL REFERENCES modell(id),
  kraftstoff  TEXT NOT NULL DEFAULT '',
  hubraum_ccm INTEGER NOT NULL DEFAULT 0,
  leistung_kw INTEGER NOT NULL DEFAULT 0,
  baujahr_von INTEGER,
  baujahr_bis INTEGER,
  co2_wltp    INTEGER,
  zulassungen INTEGER NOT NULL DEFAULT 0,
  hsn         TEXT,
  tsn         TEXT,
  quelle      TEXT NOT NULL DEFAULT 'manuell',
  UNIQUE (modell_id, kraftstoff, hubraum_ccm, leistung_kw, quelle)
);
CREATE INDEX IF NOT EXISTS idx_fahrzeug_modell ON fahrzeug(modell_id);

-- Eigene, generische Systematik der Produktgruppen (Baum).
CREATE TABLE IF NOT EXISTS produktgruppe (
  id        INTEGER PRIMARY KEY,
  parent_id INTEGER REFERENCES produktgruppe(id),
  name      TEXT NOT NULL,
  sort      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS artikel (
  id               INTEGER PRIMARY KEY,
  lieferant        TEXT NOT NULL COLLATE NOCASE,
  artikelnr        TEXT NOT NULL,
  artikelnr_norm   TEXT NOT NULL,
  bezeichnung      TEXT NOT NULL,
  produktgruppe_id INTEGER REFERENCES produktgruppe(id),
  ean              TEXT,
  quelle           TEXT NOT NULL DEFAULT 'manuell',
  UNIQUE (lieferant, artikelnr_norm)
);
CREATE INDEX IF NOT EXISTS idx_artikel_norm   ON artikel(artikelnr_norm);
CREATE INDEX IF NOT EXISTS idx_artikel_gruppe ON artikel(produktgruppe_id);
CREATE INDEX IF NOT EXISTS idx_artikel_ean    ON artikel(ean);

CREATE TABLE IF NOT EXISTS oe_nummer (
  artikel_id  INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
  hersteller  TEXT NOT NULL DEFAULT '',
  nummer      TEXT NOT NULL,
  nummer_norm TEXT NOT NULL,
  PRIMARY KEY (artikel_id, hersteller, nummer_norm)
);
CREATE INDEX IF NOT EXISTS idx_oe_norm ON oe_nummer(nummer_norm);

-- Verwendungsnachweis: Artikel passt zu Fahrzeugvariante.
CREATE TABLE IF NOT EXISTS artikel_fahrzeug (
  artikel_id INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
  fahrzeug_id INTEGER NOT NULL REFERENCES fahrzeug(id) ON DELETE CASCADE,
  bemerkung  TEXT,
  quelle     TEXT NOT NULL DEFAULT 'manuell',
  PRIMARY KEY (artikel_id, fahrzeug_id)
);
CREATE INDEX IF NOT EXISTS idx_af_fahrzeug ON artikel_fahrzeug(fahrzeug_id);

CREATE TABLE IF NOT EXISTS preis (
  id         INTEGER PRIMARY KEY,
  artikel_id INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
  haendler   TEXT NOT NULL DEFAULT '',
  ek_netto   REAL NOT NULL,
  waehrung   TEXT NOT NULL DEFAULT 'EUR',
  stand      TEXT NOT NULL DEFAULT (date('now')),
  UNIQUE (artikel_id, haendler)
);

-- Was wurde wann verbaut. Bewusst ohne Kundendaten und Kennzeichen (DSGVO).
CREATE TABLE IF NOT EXISTS verbaut (
  id          INTEGER PRIMARY KEY,
  artikel_id  INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
  fahrzeug_id INTEGER REFERENCES fahrzeug(id) ON DELETE SET NULL,
  auftrag     TEXT,
  km          INTEGER,
  notiz       TEXT,
  datum       TEXT NOT NULL DEFAULT (date('now'))
);

-- Herkunft und Lizenz jeder Datenquelle (Quellenangabe in der Oberfläche).
CREATE TABLE IF NOT EXISTS datenquelle (
  key       TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  url       TEXT,
  lizenz    TEXT,
  stand     TEXT,
  eintraege INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS artikel_fts
  USING fts5(text, tokenize='trigram');  -- Teilstring-Suche, wichtig für deutsche Wortzusammensetzungen
"""

# Eigene, generische Systematik (keine Übernahme fremder Kataloge).
GRUPPEN = {
    "Bremsanlage": ["Bremsbeläge", "Bremsscheiben", "Bremssättel", "Bremsschläuche", "Bremsflüssigkeit"],
    "Filter": ["Ölfilter", "Luftfilter", "Innenraumfilter", "Kraftstofffilter"],
    "Motor": ["Zündkerzen", "Zahnriemen und Kettensätze", "Wasserpumpen", "Dichtungen", "Keilrippenriemen"],
    "Fahrwerk und Lenkung": ["Stoßdämpfer", "Federn", "Querlenker", "Spurstangen", "Radlager"],
    "Elektrik": ["Batterien", "Glühkerzen", "Zündspulen", "Lichtmaschinen", "Anlasser", "Glühlampen"],
    "Abgasanlage": ["Katalysatoren", "Partikelfilter", "Schalldämpfer", "Lambdasonden"],
    "Kühlung und Heizung": ["Kühler", "Thermostate", "Kühlmittel"],
    "Kupplung und Getriebe": ["Kupplungssätze", "Schwungräder", "Getriebeöl"],
    "Karosserie und Beleuchtung": ["Scheibenwischer", "Scheinwerfer", "Spiegel"],
    "Betriebsstoffe": ["Motoröl", "Frostschutz", "Reiniger"],
}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_schema(con):
    con.executescript(SCHEMA)
    seed_gruppen(con)
    con.commit()


def seed_gruppen(con):
    if con.execute("SELECT 1 FROM produktgruppe LIMIT 1").fetchone():
        return
    for i, (haupt, unter) in enumerate(GRUPPEN.items()):
        pid = con.execute(
            "INSERT INTO produktgruppe(parent_id, name, sort) VALUES (NULL, ?, ?)", (haupt, i)
        ).lastrowid
        for j, name in enumerate(unter):
            con.execute(
                "INSERT INTO produktgruppe(parent_id, name, sort) VALUES (?, ?, ?)", (pid, name, j)
            )


def norm(s):
    """Vergleichsform für Nummern: nur Ziffern und Buchstaben, Großschreibung."""
    return re.sub(r"[^0-9A-Z]", "", (s or "").upper())


def reindex_artikel(con, artikel_id):
    a = con.execute(
        """SELECT a.lieferant, a.artikelnr, a.bezeichnung, a.ean, g.name AS gruppe
           FROM artikel a LEFT JOIN produktgruppe g ON g.id = a.produktgruppe_id
           WHERE a.id = ?""",
        (artikel_id,),
    ).fetchone()
    con.execute("DELETE FROM artikel_fts WHERE rowid = ?", (artikel_id,))
    if not a:
        return
    oes = [r[0] for r in con.execute("SELECT nummer FROM oe_nummer WHERE artikel_id = ?", (artikel_id,))]
    text = " ".join(x for x in [a["lieferant"], a["artikelnr"], a["bezeichnung"], a["ean"], a["gruppe"], *oes] if x)
    con.execute("INSERT INTO artikel_fts(rowid, text) VALUES (?, ?)", (artikel_id, text))


def gruppe_id_by_name(con, name):
    if not name:
        return None
    r = con.execute(
        "SELECT id FROM produktgruppe WHERE name = ? COLLATE NOCASE ORDER BY parent_id IS NULL LIMIT 1",
        (name.strip(),),
    ).fetchone()
    return r[0] if r else None


def get_or_create_hersteller(con, name):
    r = con.execute("SELECT id FROM hersteller WHERE name = ?", (name,)).fetchone()
    return r[0] if r else con.execute("INSERT INTO hersteller(name) VALUES (?)", (name,)).lastrowid


def get_or_create_modell(con, hersteller_id, name):
    r = con.execute(
        "SELECT id FROM modell WHERE hersteller_id = ? AND name = ?", (hersteller_id, name)
    ).fetchone()
    if r:
        return r[0]
    return con.execute(
        "INSERT INTO modell(hersteller_id, name) VALUES (?, ?)", (hersteller_id, name)
    ).lastrowid


def register_quelle(con, key, name, url, lizenz, eintraege):
    con.execute(
        """INSERT INTO datenquelle(key, name, url, lizenz, stand, eintraege)
           VALUES (?, ?, ?, ?, date('now'), ?)
           ON CONFLICT(key) DO UPDATE SET name=excluded.name, url=excluded.url,
             lizenz=excluded.lizenz, stand=excluded.stand, eintraege=excluded.eintraege""",
        (key, name, url, lizenz, eintraege),
    )
