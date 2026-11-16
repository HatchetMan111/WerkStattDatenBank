#!/usr/bin/env python3
"""Tests für den Import (Upload, Download, gemerkte Quellen, Schutzmechanismen).

Start:  python3 test/test_import.py          (nur Python-Standardbibliothek, startet eigene Server)
"""
import http.server
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
TOKEN = "test-token-123"

EEA_CSV = (
    "Mk;Cn;Ft;ec (cm3);ep (KW);Ewltp (g/km);r;year\n"
    "VOLKSWAGEN;GOLF VII;petrol;1395;110;130;100;2023\n"
    "VOLKSWAGEN;GOLF VII;petrol;1395;110;134;50;2024\n"
    "VOLKSWAGEN;ID.3;electric;0;150;0;200;2024\n"
    "BMW;320D;diesel;1995;140;125;80;2024\n"
    "BMW;;diesel;1995;140;125;80;2024\n"  # ohne Modellname -> wird übersprungen
)
ARTIKEL_CSV = (
    "lieferant;artikelnr;bezeichnung;gruppe;ean;oe;ek_netto;haendler\n"
    "Testteile;T-100;Bremsscheibe vorne;Bremsscheiben;;Muster:OE-1|Muster:OE-2;12,5;Großhandel\n"
    "Testteile;T-200;Ölfilter;Ölfilter;;;4,10;Großhandel\n"
)


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, privat_erlaubt):
        self.dir = tempfile.mkdtemp(prefix="wdb-test-")
        self.port = freier_port()
        env = dict(os.environ, WDB_HOST="127.0.0.1", WDB_PORT=str(self.port), WDB_TOKEN=TOKEN,
                   WDB_DB=os.path.join(self.dir, "t.sqlite"), WDB_STATIC=os.path.join(self.dir, "keine-ui"),
                   WDB_MAX_UPLOAD_MB="1", PYTHONDONTWRITEBYTECODE="1")
        if privat_erlaubt:
            env["WDB_ALLOW_PRIVATE_URLS"] = "1"
        self.proc = subprocess.Popen([sys.executable, str(BACKEND / "app.py")], env=env, cwd=BACKEND,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(100):
            try:
                self.call("GET", "/api/stats")
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("Server startet nicht")

    def call(self, method, path, body=None, headers=None, raw=None, token=True):
        h = dict(headers or {})
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if token:
            h["X-WDB-Token"] = TOKEN
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def upload(self, daten, typ="auto", name="x.csv", quelle="", header=True, token=True):
        h = {"Content-Type": "application/octet-stream"}
        if header:
            h["X-WDB-Upload"] = "1"
        from urllib.parse import urlencode
        q = urlencode({"typ": typ, "name": name, "quelle": quelle})
        return self.call("POST", f"/api/import/upload?{q}", raw=daten, headers=h, token=token)

    def warte(self, timeout=20):
        ende = time.time() + timeout
        while time.time() < ende:
            _, st = self.call("GET", "/api/import/status")
            if st["state"] in ("fertig", "fehler"):
                return st
            time.sleep(0.1)
        raise TimeoutError("Import wird nicht fertig")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


class Dateiserver:
    """Kleiner HTTP-Server, der die Testdateien ausliefert (Ziel für den URL-Import)."""

    def __init__(self, dateien):
        self.dateien = dateien
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/weiter":
                    self.send_response(302)
                    self.send_header("Location", "/eea.csv")
                    self.end_headers()
                    return
                body = outer.dateien.get(self.path.lstrip("/"))
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, name):
        return f"http://127.0.0.1:{self.port}/{name}"

    def stop(self):
        self.httpd.shutdown()


def zip_bytes(name, inhalt):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, inhalt)
    return b.getvalue()


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server(privat_erlaubt=True)
        cls.streng = Server(privat_erlaubt=False)
        cls.files = Dateiserver({"eea.csv": EEA_CSV.encode(), "eea.zip": zip_bytes("daten.csv", EEA_CSV),
                                 "artikel.csv": ARTIKEL_CSV.encode(), "kaputt.csv": b"a;b\n1;2\n", "leer.csv": b""})

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()
        cls.streng.stop()
        cls.files.stop()

    # ---- Schutz ----
    def test_01_ohne_token_401(self):
        self.assertEqual(self.srv.call("GET", "/api/import/status", token=False)[0], 401)
        self.assertEqual(self.srv.upload(b"x", token=False)[0], 401)

    def test_02_upload_ohne_header_abgelehnt(self):
        code, r = self.srv.upload(EEA_CSV.encode(), header=False)
        self.assertEqual(code, 400, r)

    def test_03_upload_zu_gross(self):
        code, r = self.srv.upload(b"x" * (1024 * 1024 + 1))
        self.assertEqual(code, 413, r)

    def test_04_ssrf_und_schemas(self):
        for url in ("http://127.0.0.1/x.csv", "file:///etc/passwd", "ftp://example.org/x", "https://user:pw@example.org/x"):
            code, r = self.streng.call("POST", "/api/import/url", {"url": url})
            self.assertEqual(code, 400, (url, r))
        code, r = self.streng.call("POST", "/api/import/url", {"url": "https://localhost/x.csv"})
        self.assertEqual(code, 400, r)
        self.assertIn("intern", r["fehler"])

    # ---- Upload ----
    def test_10_upload_eea_automatisch(self):
        code, r = self.srv.upload(EEA_CSV.encode(), name="eea.csv")
        self.assertEqual(code, 200, r)
        st = self.srv.warte()
        self.assertEqual(st["state"], "fertig", st)
        self.assertEqual(st["ergebnis"]["typ"], "eea")
        self.assertEqual(st["ergebnis"]["in_datenbank"], 3)  # Golf, ID.3, 320d
        _, hs = self.srv.call("GET", "/api/hersteller")
        self.assertEqual([h["name"] for h in hs], ["BMW", "Volkswagen"])
        _, ms = self.srv.call("GET", f"/api/modelle?hersteller_id={hs[1]['id']}")
        self.assertEqual(sorted(m["name"] for m in ms), ["Golf VII", "ID.3"])
        _, fz = self.srv.call("GET", f"/api/fahrzeuge?modell_id={[m for m in ms if m['name'] == 'Golf VII'][0]['id']}")
        self.assertEqual(len(fz), 1)
        self.assertIn("110 kW", fz[0]["label"])
        _, stats = self.srv.call("GET", "/api/stats")
        self.assertIn("eea", [q["key"] for q in stats["quellen"]])
        self.assertTrue(any("CC BY" in (q["lizenz"] or "") for q in stats["quellen"]))

    def test_11_erneuter_import_ist_idempotent(self):
        self.srv.upload(EEA_CSV.encode())
        st = self.srv.warte()
        self.assertEqual(st["ergebnis"]["in_datenbank"], 3)

    def test_12_zip_upload(self):
        self.srv.upload(zip_bytes("irgendwas.csv", EEA_CSV), name="eea.zip")
        st = self.srv.warte()
        self.assertEqual(st["state"], "fertig", st)

    def test_13_artikel_upload_und_suche(self):
        self.srv.upload(ARTIKEL_CSV.encode(), name="liste.csv", quelle="Großhandel Test")
        st = self.srv.warte()
        self.assertEqual(st["ergebnis"]["typ"], "artikel", st)
        self.assertEqual(st["ergebnis"]["verarbeitet"], 2)
        _, rows = self.srv.call("GET", "/api/artikel?q=scheibe")
        self.assertEqual([r["artikelnr"] for r in rows], ["T-100"])
        _, rows = self.srv.call("GET", "/api/artikel?q=OE-2")
        self.assertEqual([r["artikelnr"] for r in rows], ["T-100"])
        _, stats = self.srv.call("GET", "/api/stats")
        self.assertIn("Großhandel Test", [q["name"] for q in stats["quellen"]])

    def test_14_unbekanntes_format_gibt_klaren_fehler(self):
        self.srv.upload(b"a;b\n1;2\n")
        st = self.srv.warte()
        self.assertEqual(st["state"], "fehler")
        self.assertIn("nicht erkannt", st["fehler"])
        self.assertIn("['a', 'b']", st["fehler"])

    # ---- URL-Import ----
    def test_20_url_import_mit_weiterleitung_und_merken(self):
        code, r = self.srv.call("POST", "/api/import/url", {"url": self.files.url("weiter"), "typ": "eea",
                                                           "name": "EEA-Test", "merken": True})
        self.assertEqual(code, 200, r)
        st = self.srv.warte()
        self.assertEqual(st["state"], "fertig", st)
        _, q = self.srv.call("GET", "/api/import/quellen")
        self.assertEqual(len(q["gespeichert"]), 1)
        self.assertTrue(q["gespeichert"][0]["ergebnis"].startswith("OK"))
        self.assertEqual(q["katalog"][0]["key"], "eea")
        self.assertTrue(q["katalog"][0]["seite"].startswith("https://www.eea.europa.eu/"))

    def test_21_gemerkte_quelle_aktualisieren_und_entfernen(self):
        _, q = self.srv.call("GET", "/api/import/quellen")
        qid = q["gespeichert"][0]["id"]
        code, r = self.srv.call("POST", f"/api/import/quellen/{qid}/aktualisieren", {})
        self.assertEqual(code, 200, r)
        self.assertEqual(self.srv.warte()["state"], "fertig")
        self.assertEqual(self.srv.call("DELETE", f"/api/import/quellen/{qid}")[0], 200)
        self.assertEqual(self.srv.call("GET", "/api/import/quellen")[1]["gespeichert"], [])
        self.assertEqual(self.srv.call("POST", "/api/import/quellen/9999/aktualisieren", {})[0], 404)

    def test_22_zip_per_url(self):
        self.srv.call("POST", "/api/import/url", {"url": self.files.url("eea.zip")})
        self.assertEqual(self.srv.warte()["state"], "fertig")

    def test_23_download_fehler_werden_gemeldet(self):
        self.srv.call("POST", "/api/import/url", {"url": self.files.url("gibt-es-nicht.csv")})
        st = self.srv.warte()
        self.assertEqual(st["state"], "fehler")
        self.assertIn("404", st["fehler"])
        self.srv.call("POST", "/api/import/url", {"url": self.files.url("leer.csv")})
        self.assertIn("leer", self.srv.warte()["fehler"])

    def test_24_nur_ein_import_gleichzeitig(self):
        gross = ("lieferant;artikelnr;bezeichnung\n" + "".join(f"L;N{i};Teil {i}\n" for i in range(20000))).encode()
        self.assertEqual(self.srv.upload(gross, typ="artikel")[0], 200)
        code, r = self.srv.upload(ARTIKEL_CSV.encode())
        # Entweder lief der erste noch (409) oder war schon fertig (200) – in keinem Fall zwei gleichzeitig
        self.assertIn(code, (200, 409), r)
        if code == 409:
            self.assertEqual(r["code"], "belegt")
        self.srv.warte(60)

    def test_25_aufraeumen(self):
        self.srv.warte()
        tmp = Path(self.srv.dir) / "import-tmp"
        self.assertEqual(list(tmp.iterdir()) if tmp.exists() else [], [])


class EinheitenTests(unittest.TestCase):
    def test_pruefe_url_ohne_ausnahme(self):
        sys.path.insert(0, str(BACKEND))
        os.environ.pop("WDB_ALLOW_PRIVATE_URLS", None)
        import importlib
        import wdb_import as imp
        importlib.reload(imp)
        for url in ("https://127.0.0.1/", "https://[::1]/", "https://10.1.2.3/", "https://192.168.0.5/", "https://169.254.169.254/latest/meta-data/"):
            with self.assertRaises(imp.ImportFehler, msg=url):
                imp.pruefe_url(url)

    def test_zip_bombe_wird_begrenzt(self):
        sys.path.insert(0, str(BACKEND))
        import wdb_import as imp
        d = Path(tempfile.mkdtemp())
        try:
            z = d / "b.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("x.csv", "a" * 3_000_000)
            alt = imp.MAX_ENTPACKT
            imp.MAX_ENTPACKT = 1_000_000
            try:
                with self.assertRaises(imp.ImportFehler):
                    imp.aufbereiten(z, d)
            finally:
                imp.MAX_ENTPACKT = alt
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
