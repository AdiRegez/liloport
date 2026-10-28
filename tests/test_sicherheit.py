"""Sicherheit und Grösse: Host-/Origin-Prüfung, Import fremder HTML-Blöcke, CSS-Ausbruch, grosse Uploads."""
import http.client
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402
from liloport.render import css_scopen  # noqa: E402


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = server.einrichten(cls.tmp.name)
        v = cls.store.verzeichnis_anlegen("A")
        cls.vid = v["id"]
        cls.pfad, _ = cls.store.seite_anlegen("Seite", v["id"], "voll", [])
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def anfrage(self, methode, pfad, body=None, kopf=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        k = {"Host": f"127.0.0.1:{self.port}"}
        k.update(kopf or {})
        c.request(methode, pfad, body=body, headers=k)
        r = c.getresponse()
        daten = r.read()
        c.close()
        return r, daten

    def test_eigener_zugriff_geht(self):
        r, d = self.anfrage("GET", "/api/site")
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")

    def test_dns_rebinding_fremder_host_abgelehnt(self):
        r, _ = self.anfrage("GET", "/api/site", kopf={"Host": f"boese.example:{self.port}"})
        self.assertEqual(r.status, 403)

    def test_fremde_website_darf_nicht_schreiben(self):
        body = json.dumps({"niveau": "profi"})
        r, _ = self.anfrage("POST", "/api/niveau", body, {"Origin": "https://boese.example", "Content-Type": "text/plain"})
        self.assertEqual(r.status, 403)
        r, _ = self.anfrage("POST", "/api/niveau", body, {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status, 403)
        r, _ = self.anfrage("POST", "/api/niveau", json.dumps({"niveau": "amateur"}),
                            {"Origin": f"http://127.0.0.1:{self.port}", "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(r.status, 200)

    def test_grosser_upload_ohne_limit_gestreamt(self):
        groesse = 210 * 1024 * 1024  # über dem früheren Limit von 200 MB
        kopf = b"%PDF-1.4\n"

        class Quelle(io.RawIOBase):
            """Liefert die Datei stückweise, ohne sie im Speicher zu halten."""
            def __init__(self):
                self.rest = groesse
                self.erstes = True

            def readable(self):
                return True

            def readinto(self, b):
                if self.rest <= 0:
                    return 0
                n = min(len(b), self.rest)
                if self.erstes:
                    b[:len(kopf)] = kopf
                    b[len(kopf):n] = b"\x00" * (n - len(kopf))
                    self.erstes = False
                else:
                    b[:n] = b"\x00" * n
                self.rest -= n
                return n

        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        c.putrequest("POST", "/api/upload/" + self.pfad, skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.port}")
        c.putheader("Content-Length", str(groesse))
        c.putheader("X-Dateiname", "gross.pdf")
        c.endheaders()
        q = Quelle()
        while True:
            stueck = q.read(1024 * 1024)
            if not stueck:
                break
            c.send(stueck)
        r = c.getresponse()
        antwort = json.loads(r.read())
        c.close()
        self.assertEqual(r.status, 200, antwort)
        datei = Path(self.tmp.name) / antwort["asset"]["datei"]
        self.assertEqual(datei.stat().st_size, groesse)
        self.assertFalse(list(datei.parent.glob("*.teil")))
        datei.unlink()

    def test_svg_wird_mit_sandbox_ausgeliefert(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        r, d = self.anfrage("POST", "/api/upload/" + self.pfad, svg, {"X-Dateiname": "x.svg"})
        datei = json.loads(d)["asset"]["datei"]
        r, _ = self.anfrage("GET", "/" + datei)
        self.assertIn("sandbox", r.getheader("Content-Security-Policy"))


class ImportFiltertSkriptTests(unittest.TestCase):
    def test_fremder_html_block_wird_entschaerft(self):
        tmp = tempfile.TemporaryDirectory()
        store = server.einrichten(tmp.name)
        v = store.verzeichnis_anlegen("Ziel")
        zip_daten = io.BytesIO()
        info = {"titel": "Fremd", "menue": "voll", "css": "p{}</style><script>alert(1)</script>", "anhaenge": {},
                "bloecke": [{"id": "b1", "typ": "html", "html": '<p>Hallo</p><script>fetch("/api/seiten")</script><img src=x onerror=alert(1)>'},
                            {"id": "b2", "typ": "text", "html": '<p onclick="alert(1)">Text</p>'},
                            {"id": "b3", "typ": "button", "text": "x", "ziel": "javascript:alert(1)"},
                            {"id": "b4", "typ": "boese"}]}
        with zipfile.ZipFile(zip_daten, "w") as z:
            z.writestr("abc/liloport.json", json.dumps(info))
        vorschau = server.Handler.importer.vorschau(zip_daten.getvalue(), "fremd.zip")
        self.assertEqual(vorschau["html"], 1)
        pfad = server.Handler.importer.importieren(vorschau["token"], v["id"])
        seite = store.seite_laden(pfad)
        roh = json.dumps(seite)
        self.assertNotIn("<script", roh)
        self.assertNotIn("onclick", roh)
        self.assertNotIn("onerror", roh)
        self.assertNotIn("javascript:", roh)
        self.assertEqual(len(seite["bloecke"]), 3)
        server.Handler.renderer.alles_schreiben()
        html = (Path(tmp.name) / (pfad + ".html")).read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html)
        tmp.cleanup()

    def test_css_kann_style_nicht_verlassen(self):
        self.assertNotIn("</style", css_scopen("p{}</style><script>x</script>", "s").lower())


if __name__ == "__main__":
    unittest.main()
