"""Start und Beenden des installierten Programms: Einzelinstanz, Beenden über die Leiste, Startfehler."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


class StartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.umg = mock.patch.dict(os.environ, {"LILOPORT_EINSTELLUNGEN": str(Path(self.tmp.name) / "einst")})
        self.umg.start()
        # Ein echtes Liloport auf dem Standardport des Rechners soll die Tests nicht stören
        self.port_patch = mock.patch.object(server, "STANDARD_PORT", 9)
        self.port_patch.start()

    def tearDown(self):
        server.Handler.beenden = None
        server.Handler.sitzung = None
        self.port_patch.stop()
        self.umg.stop()
        self.tmp.cleanup()

    def anfrage(self, port, methode, pfad, body=None, kopf=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        k = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
        k.update(kopf or {})
        c.request(methode, pfad, body=body, headers=k)
        r = c.getresponse()
        d = r.read()
        c.close()
        return r.status, d

    def test_dienst_starten_finden_beenden(self):
        dienst = server.Dienst(None, 8790)
        with mock.patch.object(server, "inhalte_ordner", return_value=Path(self.tmp.name) / "inhalte"):
            adresse, ordner = dienst.starten()
        dienst.im_hintergrund()
        port = dienst.server.server_address[1]
        try:
            lauf = json.loads(server.lauf_datei().read_text(encoding="utf-8"))
            self.assertEqual((lauf["port"], lauf["pid"]), (port, os.getpid()))
            self.assertEqual(server.laufende_adresse(), f"http://127.0.0.1:{port}/", "zweiter Start findet den ersten")
            # Fremde Website darf Liloport nicht beenden
            status, _ = self.anfrage(port, "POST", "/api/beenden", "{}", {"Origin": "https://boese.example"})
            self.assertEqual(status, 403)
            self.assertFalse(dienst.beendet.is_set())
            # Knopf ⏻ in der Leiste
            status, d = self.anfrage(port, "POST", "/api/beenden", "{}", {"Origin": f"http://127.0.0.1:{port}"})
            self.assertEqual((status, json.loads(d)), (200, {"ok": True}))
            self.assertTrue(dienst.beendet.wait(5))
        finally:
            dienst.aufraeumen()
        self.assertFalse(server.lauf_datei().exists(), "laufend.json wird beim Beenden entfernt")
        self.assertIsNone(server.laufende_adresse())

    def test_startfehler_verstaendlich(self):
        datei = Path(self.tmp.name) / "datei"
        datei.write_text("x")
        dienst = server.Dienst(str(datei / "unmoeglich"), 8790)   # Ordner unter einer Datei: geht nicht
        with self.assertRaises(server.StartFehler) as f:
            dienst.starten()
        self.assertIn("Inhalte-Ordner nicht öffnen oder anlegen", str(f.exception))
        dienst.aufraeumen()

    def test_beenden_ohne_dienst_abgelehnt(self):
        tmp = Path(self.tmp.name) / "i2"
        server.einrichten(tmp)
        server.Handler.beenden = None
        from http.server import ThreadingHTTPServer
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            status, d = self.anfrage(httpd.server_address[1], "POST", "/api/beenden", "{}")
            self.assertNotEqual(status, 200)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_videos_in_teilen_und_export_ohne_arbeitsspeicher(self):
        tmp = Path(self.tmp.name) / "i3"
        store = server.einrichten(tmp)
        (tmp / "film.mp4").write_bytes(bytes(range(256)) * 40)   # 10 240 Bytes
        from http.server import ThreadingHTTPServer
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            status, d = self.anfrage(port, "GET", "/film.mp4", kopf={"Range": "bytes=256-511"})
            self.assertEqual((status, d), (206, bytes(range(256))))
            status, d = self.anfrage(port, "GET", "/film.mp4", kopf={"Range": "bytes=-10"})
            self.assertEqual((status, d), (206, bytes(range(246, 256))))
            status, d = self.anfrage(port, "GET", "/film.mp4", kopf={"Range": "bytes=10240-"})
            self.assertEqual(status, 416)
            status, d = self.anfrage(port, "GET", "/film.mp4")
            self.assertEqual((status, len(d)), (200, 10240))
            # Export ganzes Portfolio: kommt als vollständige ZIP an (aus temporärer Datei gestreamt)
            v = store.verzeichnis_anlegen("A")
            store.seite_anlegen("S", v["id"])
            status, d = self.anfrage(port, "POST", "/api/export-mehrere", json.dumps({"verzeichnis": ""}),
                                     {"Origin": f"http://127.0.0.1:{port}"})
            self.assertEqual(status, 200, d[:200])
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(d)) as z:
                self.assertTrue(any(n.endswith("liloport.json") for n in z.namelist()))
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()


class VersionTests(unittest.TestCase):
    def test_beta_anzeige(self):
        from liloport.render import version_anzeige
        self.assertEqual(version_anzeige("0.9.0"), "0.9.0 Beta")
        self.assertEqual(version_anzeige("1.0.0"), "1.0.0")
        self.assertEqual(version_anzeige(""), "")
