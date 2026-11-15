#!/usr/bin/env python3
"""WerkstattDatenBank: Server (nur Python-Standardbibliothek).

Start:  python3 app.py
Umgebungsvariablen:
  WDB_HOST   Bind-Adresse (Standard 127.0.0.1)
  WDB_PORT   Port (Standard 8080)
  WDB_TOKEN  Zugangs-Token für Änderungen. Pflicht, sobald der Server nicht nur lokal läuft.
  WDB_DB     Pfad zur SQLite-Datei
  WDB_STATIC Ordner mit der gebauten Oberfläche (Standard: ../frontend/dist)
"""
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import sys
import traceback
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import wdb_db as db

STATIC = Path(os.environ.get("WDB_STATIC") or db.BASE.parent / "frontend" / "dist").resolve()
HOST = os.environ.get("WDB_HOST", "127.0.0.1")
PORT = int(os.environ.get("WDB_PORT", "8080"))
TOKEN = os.environ.get("WDB_TOKEN", "")
LOOPBACK = HOST in ("127.0.0.1", "localhost", "::1")
MAX_BODY = 1_000_000
PS_PRO_KW = 1.35962


class ApiError(Exception):
    def __init__(self, status, msg, code="fehler"):
        super().__init__(msg)
        self.status, self.msg, self.code = status, msg, code


def s(value, maxlen=200):
    return (str(value).strip()[:maxlen]) if value is not None else ""


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fahrzeug_label(r):
    teile = []
    if r["kraftstoff"]:
        teile.append(r["kraftstoff"])
    if r["hubraum_ccm"]:
        teile.append(f'{r["hubraum_ccm"]} ccm')
    if r["leistung_kw"]:
        teile.append(f'{r["leistung_kw"]} kW ({round(r["leistung_kw"] * PS_PRO_KW)} PS)')
    von, bis = r["baujahr_von"], r["baujahr_bis"]
    if von and bis and von != bis:
        teile.append(f"{von}–{bis}")
    elif von or bis:
        teile.append(str(von or bis))
    return " · ".join(teile) or "Variante"


def such_ids(con, text, limit=500):
    """Artikelnummer, OE-Nummer, EAN (Präfix, ohne Sonderzeichen) plus Volltext."""
    ids = set()
    qn = db.norm(text)
    if len(qn) >= 3:
        lo, hi = qn, qn + "~"
        ids.update(r[0] for r in con.execute(
            "SELECT id FROM artikel WHERE artikelnr_norm BETWEEN ? AND ? LIMIT ?", (lo, hi, limit)))
        ids.update(r[0] for r in con.execute(
            "SELECT artikel_id FROM oe_nummer WHERE nummer_norm BETWEEN ? AND ? LIMIT ?", (lo, hi, limit)))
        ids.update(r[0] for r in con.execute("SELECT id FROM artikel WHERE ean = ?", (text.strip(),)))
    if ids:  # Nummern-Treffer sind exakt: keine unscharfen Textergebnisse dazumischen
        return list(ids)[:limit]
    # Textsuche über den Trigram-Index: Teilstrings ab 3 Zeichen (z. B. "scheibe" findet "Bremsscheibe").
    # Kürzere Wörter müssen als Teilstring vorkommen. Alle Wörter müssen passen (UND).
    toks = re.findall(r"\w+", text)
    lang = [t for t in toks if len(t) >= 3]
    conds, args = [], []
    if lang:
        conds.append("artikel_fts MATCH ?")
        args.append(" ".join(f'"{t}"' for t in lang))
    for t in toks:
        if len(t) < 3:
            conds.append("text LIKE ? ESCAPE '\\'")
            args.append("%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if not conds:
        return []
    try:
        return [r[0] for r in con.execute(
            f"SELECT rowid FROM artikel_fts WHERE {' AND '.join(conds)} LIMIT ?", args + [limit])]
    except sqlite3.OperationalError:
        return []


def list_artikel(con, q):
    fid = int_or_none(q.get("fahrzeug_id"))
    gid = int_or_none(q.get("gruppe_id"))
    text = s(q.get("q"), 100)
    strikt = q.get("strikt", "1") != "0"
    limit = min(max(int_or_none(q.get("limit")) or 200, 1), 500)

    join, jargs, passt, where, wargs = "", [], "0 AS passt", [], []
    if fid:
        join = "LEFT JOIN artikel_fahrzeug af ON af.artikel_id = a.id AND af.fahrzeug_id = ?"
        jargs = [fid]
        passt = "(af.fahrzeug_id IS NOT NULL) AS passt"
        if strikt:
            where.append("af.fahrzeug_id IS NOT NULL")
    if gid:
        where.append(
            "a.produktgruppe_id IN (WITH RECURSIVE t(id) AS (SELECT ? UNION ALL "
            "SELECT g.id FROM produktgruppe g JOIN t ON g.parent_id = t.id) SELECT id FROM t)")
        wargs.append(gid)
    if text:
        ids = such_ids(con, text)
        if not ids:
            return []
        where.append(f"a.id IN ({','.join('?' * len(ids))})")
        wargs.extend(ids)

    sql = f"""SELECT a.id, a.lieferant, a.artikelnr, a.bezeichnung, a.quelle, g.name AS gruppe,
                     {passt}, (SELECT MIN(ek_netto) FROM preis p WHERE p.artikel_id = a.id) AS ek_min
              FROM artikel a
              LEFT JOIN produktgruppe g ON g.id = a.produktgruppe_id
              {join}
              {'WHERE ' + ' AND '.join(where) if where else ''}
              ORDER BY passt DESC, g.name, a.lieferant, a.artikelnr
              LIMIT ?"""
    return [dict(r) for r in con.execute(sql, jargs + wargs + [limit])]


def artikel_detail(con, aid):
    a = con.execute(
        """SELECT a.*, g.name AS gruppe FROM artikel a
           LEFT JOIN produktgruppe g ON g.id = a.produktgruppe_id WHERE a.id = ?""", (aid,)).fetchone()
    if not a:
        raise ApiError(404, "Artikel nicht gefunden")
    fz = con.execute(
        """SELECT f.*, m.name AS modell, h.name AS hersteller, af.bemerkung
           FROM artikel_fahrzeug af JOIN fahrzeug f ON f.id = af.fahrzeug_id
           JOIN modell m ON m.id = f.modell_id JOIN hersteller h ON h.id = m.hersteller_id
           WHERE af.artikel_id = ? ORDER BY h.name, m.name, f.kraftstoff, f.hubraum_ccm LIMIT 300""", (aid,)).fetchall()
    anzahl = con.execute("SELECT COUNT(*) FROM artikel_fahrzeug WHERE artikel_id = ?", (aid,)).fetchone()[0]
    return {
        "artikel": dict(a),
        "oe": [dict(r) for r in con.execute(
            "SELECT hersteller, nummer FROM oe_nummer WHERE artikel_id = ? ORDER BY hersteller, nummer", (aid,))],
        "preise": [dict(r) for r in con.execute(
            "SELECT haendler, ek_netto, waehrung, stand FROM preis WHERE artikel_id = ? ORDER BY ek_netto", (aid,))],
        "fahrzeuge": [{"id": r["id"], "hersteller": r["hersteller"], "modell": r["modell"],
                       "label": fahrzeug_label(r), "bemerkung": r["bemerkung"]} for r in fz],
        "fahrzeuge_gesamt": anzahl,
        "verbaut": [dict(r) for r in con.execute(
            "SELECT datum, auftrag, km, notiz FROM verbaut WHERE artikel_id = ? ORDER BY id DESC LIMIT 10", (aid,))],
    }


def gruppen_baum(con):
    rows = con.execute(
        """SELECT g.id, g.parent_id, g.name, (SELECT COUNT(*) FROM artikel a WHERE a.produktgruppe_id = g.id) AS n
           FROM produktgruppe g ORDER BY g.sort, g.name""").fetchall()
    nodes = {r["id"]: {"id": r["id"], "name": r["name"], "anzahl": r["n"], "children": []} for r in rows}
    roots = []
    for r in rows:
        (nodes[r["parent_id"]]["children"] if r["parent_id"] in nodes else roots).append(nodes[r["id"]])

    def summe(n):
        n["anzahl"] += sum(summe(c) for c in n["children"])
        return n["anzahl"]
    for n in roots:
        summe(n)
    return roots


def create_artikel(con, b):
    lief, nr, bez = s(b.get("lieferant"), 80), s(b.get("artikelnr"), 60), s(b.get("bezeichnung"), 200)
    if not (lief and nr and bez):
        raise ApiError(400, "Lieferant, Artikelnummer und Bezeichnung sind Pflicht")
    if not db.norm(nr):
        raise ApiError(400, "Artikelnummer enthält keine Ziffern oder Buchstaben")
    gid = int_or_none(b.get("produktgruppe_id"))
    cur = con.execute(
        "INSERT INTO artikel(lieferant, artikelnr, artikelnr_norm, bezeichnung, produktgruppe_id, ean) VALUES (?,?,?,?,?,?)",
        (lief, nr, db.norm(nr), bez, gid, s(b.get("ean"), 20) or None))
    aid = cur.lastrowid
    for o in (b.get("oe") or [])[:50]:
        num = s(o.get("nummer"), 60)
        if db.norm(num):
            con.execute("INSERT OR IGNORE INTO oe_nummer VALUES (?,?,?,?)",
                        (aid, s(o.get("hersteller"), 60), num, db.norm(num)))
    for fid in (b.get("fahrzeug_ids") or [])[:200]:
        con.execute("INSERT OR IGNORE INTO artikel_fahrzeug(artikel_id, fahrzeug_id) VALUES (?,?)", (aid, int(fid)))
    ek = b.get("ek_netto")
    if ek not in (None, ""):
        try:
            ek = float(str(ek).replace(",", "."))
        except (TypeError, ValueError):
            raise ApiError(400, "EK-Preis ist keine Zahl")
        con.execute("INSERT OR REPLACE INTO preis(artikel_id, haendler, ek_netto) VALUES (?,?,?)",
                    (aid, s(b.get("haendler"), 80), ek))
    db.reindex_artikel(con, aid)
    con.commit()
    return {"id": aid}


class Handler(BaseHTTPRequestHandler):
    server_version = "WerkstattDatenBank"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ---- Antworten ----
    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self._json(404, {"fehler": "Nicht gefunden"})
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    # ---- Schutz ----
    def _check_host(self):
        """Gegen DNS-Rebinding: lokal nur localhost-Hostnamen akzeptieren."""
        if LOOPBACK:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if host not in ("localhost", "127.0.0.1", "::1"):
                raise ApiError(403, "Unzulässiger Host-Header")

    def _require_write(self):
        if TOKEN:
            got = (self.headers.get("X-WDB-Token") or "").encode()
            if not hmac.compare_digest(got, TOKEN.encode()):
                raise ApiError(401, "Token fehlt oder ist falsch", "token")
        elif not LOOPBACK:
            raise ApiError(403, "Änderungen sind aus: WDB_TOKEN setzen, wenn der Server nicht nur lokal läuft", "readonly")

    def _body(self):
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ApiError(415, "Content-Type application/json erforderlich")
        n = int_or_none(self.headers.get("Content-Length")) or 0
        if n < 0 or n > MAX_BODY:
            raise ApiError(413, "Anfrage zu groß")
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ApiError(400, "Ungültiges JSON")
        if not isinstance(data, dict):
            raise ApiError(400, "JSON-Objekt erwartet")
        return data

    # ---- Routing ----
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            self._check_host()
            if u.path.startswith("/api/"):
                con = db.connect()
                try:
                    self._json(200, self._api(con, method, u.path, q))
                finally:
                    con.close()
            elif method == "GET":
                self._static(u.path)
            else:
                raise ApiError(405, "Methode nicht erlaubt")
        except ApiError as e:
            self._json(e.status, {"fehler": e.msg, "code": e.code})
        except sqlite3.IntegrityError as e:
            msg = "Eintrag existiert bereits" if "UNIQUE" in str(e) else "Ungültige Referenz (unbekannte ID)"
            self._json(409, {"fehler": msg, "code": "konflikt"})
        except Exception:
            traceback.print_exc()
            self._json(500, {"fehler": "Interner Fehler"})

    def _api(self, con, method, path, q):
        if method == "GET":
            if path == "/api/stats":
                z = {k: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for k, t in
                     [("hersteller", "hersteller"), ("modelle", "modell"), ("fahrzeuge", "fahrzeug"),
                      ("artikel", "artikel"), ("zuordnungen", "artikel_fahrzeug")]}
                return {"zahlen": z, "quellen": [dict(r) for r in con.execute("SELECT * FROM datenquelle ORDER BY name")],
                        "schreiben": bool(TOKEN) or LOOPBACK, "token_noetig": bool(TOKEN)}
            if path == "/api/hersteller":
                return [dict(r) for r in con.execute(
                    """SELECT h.id, h.name FROM hersteller h
                       WHERE EXISTS (SELECT 1 FROM modell m WHERE m.hersteller_id = h.id)
                       ORDER BY h.name COLLATE NOCASE""")]
            if path == "/api/modelle":
                return [dict(r) for r in con.execute(
                    """SELECT m.id, m.name, (SELECT COUNT(*) FROM fahrzeug f WHERE f.modell_id = m.id) AS varianten
                       FROM modell m WHERE m.hersteller_id = ? ORDER BY m.name COLLATE NOCASE""",
                    (int_or_none(q.get("hersteller_id")),))]
            if path == "/api/fahrzeuge":
                rows = con.execute(
                    """SELECT * FROM fahrzeug WHERE modell_id = ?
                       ORDER BY kraftstoff, hubraum_ccm, leistung_kw""", (int_or_none(q.get("modell_id")),))
                return [{"id": r["id"], "label": fahrzeug_label(r), "quelle": r["quelle"],
                         "kraftstoff": r["kraftstoff"], "hubraum_ccm": r["hubraum_ccm"],
                         "leistung_kw": r["leistung_kw"]} for r in rows]
            if path == "/api/gruppen":
                return gruppen_baum(con)
            if path == "/api/artikel":
                return list_artikel(con, q)
            m = re.fullmatch(r"/api/artikel/(\d+)", path)
            if m:
                return artikel_detail(con, int(m.group(1)))
            raise ApiError(404, "Unbekannter Endpunkt")

        self._require_write()
        if method == "POST" and path == "/api/artikel":
            return create_artikel(con, self._body())
        if method == "POST" and path == "/api/fitment":
            b = self._body()
            aid = int_or_none(b.get("artikel_id"))
            ids = [int(i) for i in (b.get("fahrzeug_ids") or [b.get("fahrzeug_id")]) if i is not None][:500]
            for fid in ids:
                con.execute("INSERT OR IGNORE INTO artikel_fahrzeug(artikel_id, fahrzeug_id, bemerkung) VALUES (?,?,?)",
                            (aid, fid, s(b.get("bemerkung"), 200) or None))
            con.commit()
            return {"ok": True, "anzahl": len(ids)}
        if method == "DELETE" and path == "/api/fitment":
            con.execute("DELETE FROM artikel_fahrzeug WHERE artikel_id = ? AND fahrzeug_id = ?",
                        (int_or_none(q.get("artikel_id")), int_or_none(q.get("fahrzeug_id"))))
            con.commit()
            return {"ok": True}
        if method == "POST" and path == "/api/verbaut":
            b = self._body()
            con.execute("INSERT INTO verbaut(artikel_id, fahrzeug_id, auftrag, km, notiz) VALUES (?,?,?,?,?)",
                        (int_or_none(b.get("artikel_id")), int_or_none(b.get("fahrzeug_id")),
                         s(b.get("auftrag"), 60) or None, int_or_none(b.get("km")), s(b.get("notiz"), 300) or None))
            con.commit()
            return {"ok": True}
        raise ApiError(404, "Unbekannter Endpunkt")


def main():
    con = db.connect()
    db.init_schema(con)
    con.close()
    if not (STATIC / "index.html").is_file():
        print(f"Hinweis: Oberfläche fehlt ({STATIC}). Die API läuft trotzdem.", file=sys.stderr)
    if not LOOPBACK and not TOKEN:
        print("Hinweis: Server ist im Netz erreichbar, aber WDB_TOKEN fehlt. Die Datenbank ist nur lesbar.", file=sys.stderr)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"WerkstattDatenBank läuft auf http://{HOST}:{PORT}  (Datenbank: {db.DB_PATH})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")


if __name__ == "__main__":
    main()
