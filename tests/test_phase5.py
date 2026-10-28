"""Phase 5: Datum und Tags, interne Links und Rückverweise, Fussnoten, Export von Verzeichnissen und
Portfolio, Abgabestempel, Kommentare bearbeiten/löschen/moderieren, Konflikte, zweites Gerät, Beispiel."""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liloport import beispiel, links  # noqa: E402
from liloport.assets import Assets  # noqa: E402
from liloport.export import Exporter  # noqa: E402
from liloport.importer import Importer  # noqa: E402
from liloport.kommentare import Kommentare  # noqa: E402
from liloport.render import Renderer  # noqa: E402
from liloport.store import Store, StoreFehler, datum_pruefen, tags_pruefen  # noqa: E402
from liloport.suche import Suche  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def umgebung(ordner):
    store = Store(ordner)
    store.anlegen()
    assets = Assets(store)
    kommentare = Kommentare(store)
    renderer = Renderer(store, assets, kommentare, Suche(store, assets))
    return store, assets, kommentare, renderer


class DatumTagsTests(unittest.TestCase):
    def test_tags_bereinigt(self):
        self.assertEqual(tags_pruefen(["#Reflexion", " reflexion ", "Woche  3", "", "a,b"]), ["Reflexion", "Woche 3", "a b"])
        self.assertEqual(tags_pruefen("x, y"), ["x", "y"])
        self.assertEqual(len(tags_pruefen([str(i) for i in range(30)])), 20)

    def test_datum(self):
        self.assertEqual(datum_pruefen("2026-10-26"), "2026-10-26")
        self.assertEqual(datum_pruefen(""), "")
        with self.assertRaises(StoreFehler):
            datum_pruefen("26.10.2026")

    def test_tags_im_suchindex_und_auf_der_seite(self):
        with tempfile.TemporaryDirectory() as t:
            store, assets, k, r = umgebung(t)
            v = store.verzeichnis_anlegen("A")
            p, _ = store.seite_anlegen("Seite", v["id"])
            store.seite_aktualisieren(p, tags=["Projekt X"], datum="2026-01-05")
            r.alles_schreiben()
            index = (Path(t) / "_wiki" / "suchindex.js").read_text(encoding="utf-8")
            self.assertIn('"tags": ["Projekt X"]', index)
            html = (Path(t) / (p + ".html")).read_text(encoding="utf-8")
            self.assertIn("05.01.2026", html)
            self.assertIn("index.html?suche=%23Projekt%20X", html)


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.assets, self.k, self.r = umgebung(self.tmp.name)
        self.v = self.store.verzeichnis_anlegen("Semester 1")
        self.u = self.store.verzeichnis_anlegen("Projekte", self.v["id"])
        self.a, _ = self.store.seite_anlegen("Start", self.v["id"])
        self.b, _ = self.store.seite_anlegen("Projekt", self.u["id"])
        self.store.seite_aktualisieren(self.a, bloecke=[
            {"id": "b1", "typ": "text", "html": f'<p>Siehe <a href="lp:{self.b}">Projekt</a> und <a href="lp:weg/da">weg</a>'
                                                '<span class="fussnote">Quelle 1</span> sowie<span class="fussnote">Quelle 2</span>.</p>'},
            {"id": "b2", "typ": "button", "text": "Los", "ziel": f"lp:{self.b}"}])

    def tearDown(self):
        self.tmp.cleanup()

    def html(self, pfad):
        return (Path(self.tmp.name) / (pfad + ".html")).read_text(encoding="utf-8")

    def test_aufloesen_rueckverweis_fussnoten(self):
        self.r.alles_schreiben()
        a = self.html(self.a)
        self.assertIn('href="../semester-1/projekte/projekt.html"', a)
        self.assertIn('class="link-fehlt"', a)
        self.assertIn('<li id="fn-2">Quelle 2', a)
        self.assertIn('href="#fn-1"', a)
        self.assertEqual(a.count('class="seiten-button'), 1)
        b = self.html(self.b)
        self.assertIn("Verlinkt von", b)
        self.assertIn('href="../../semester-1/start.html">Start</a>', b)

    def test_verlinkt_von_ausblendbar(self):
        self.store.seite_aktualisieren(self.b, verweise=False)
        self.r.alles_schreiben()
        self.assertNotIn("Verlinkt von", self.html(self.b))
        self.assertIs(self.store.seite_laden(self.b)["verweise"], False)
        self.store.seite_aktualisieren(self.b, verweise=True)
        self.r.alles_schreiben()
        self.assertIn("Verlinkt von", self.html(self.b))
        self.assertNotIn("verweise", self.store.seite_laden(self.b), "Standard wird nicht gespeichert")

    def test_pdf_startseite(self):
        from liloport.render import BlockRenderer
        reg = {"aaaaaaaa": {"id": "aaaaaaaa", "datei": "assets/x/buch.pdf", "name": "buch.pdf", "typ": "pdf"}}
        br = BlockRenderer(reg, "../")
        self.assertIn('src="../assets/x/buch.pdf#page=12"', br.block({"id": "p", "typ": "pdf", "asset": "aaaaaaaa", "seite": 12}))
        self.assertIn('src="../assets/x/buch.pdf"', br.block({"id": "p", "typ": "pdf", "asset": "aaaaaaaa"}))

    def test_umbenennen_zieht_links_mit(self):
        self.store.letzte_umbenennung = None
        self.store.verzeichnis_aendern(self.u["id"], "Arbeiten")
        links.pfade_umbenennen(self.store, *self.store.letzte_umbenennung)
        seite = self.store.seite_laden(self.a)
        self.assertIn('lp:semester-1/arbeiten/projekt', seite["bloecke"][0]["html"])
        self.assertEqual(seite["bloecke"][1]["ziel"], "lp:semester-1/arbeiten/projekt")


class PortfolioExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store, self.assets, self.k, self.r = umgebung(self.tmp.name)
        self.v = self.store.verzeichnis_anlegen("Semester 1")
        self.u = self.store.verzeichnis_anlegen("Projekte", self.v["id"])
        self.andere = self.store.verzeichnis_anlegen("Privat")
        self.a, _ = self.store.seite_anlegen("Start", self.v["id"])
        self.b, _ = self.store.seite_anlegen("Projekt", self.u["id"])
        self.c, _ = self.store.seite_anlegen("Geheim", self.andere["id"])
        bild = self.assets.hochladen(self.b, "bild.png", PNG)
        self.store.seite_aktualisieren(self.a, tags=["Reflexion"], bloecke=[
            {"id": "b1", "typ": "text", "html": f'<p><a href="lp:{self.b}">Projekt</a> <a href="lp:{self.c}">Geheim</a></p>'}])
        s = self.store.seite_aktualisieren(self.b, bloecke=[{"id": "b1", "typ": "bild", "asset": bild["id"], "bildtext": "B", "breite": "voll"}])
        self.assets.referenzen_setzen(self.b, s)
        self.ex = Exporter(self.store, self.assets, self.k)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verzeichnis_export(self):
        name, daten, start = self.ex.exportieren_mehrere(self.v["id"], {"kommentare": True, "abgabe": True})
        z = zipfile.ZipFile(io.BytesIO(daten))
        wurzel = z.namelist()[0].split("/")[0] + "/inhalt/"
        info = json.loads(z.read(wurzel + "liloport.json"))
        self.assertEqual(info["liloport"], 2)
        self.assertEqual([s["titel"] for s in info["seiten"]], ["Start", "Projekt"], "Geheim gehört nicht dazu")
        startseite = z.read(wurzel + start + ".html").decode()
        self.assertIn("Semester 1 › Projekte", startseite)
        datei_a = info["seiten"][0]["datei"]
        seite_a = z.read(wurzel + datei_a).decode()
        self.assertIn(f'href="{info["seiten"][1]["datei"]}"', seite_a, "interner Link zeigt auf den Zufallsnamen")
        self.assertIn('class="link-fehlt"', seite_a, "Link auf nicht exportierte Seite wird Text")
        self.assertIn("abgabe-stempel", seite_a)
        self.assertIn(wurzel + "ABGABE.txt", z.namelist())
        # Abgabe: kein Moderations-Link, das steht beim Stempel, in ABGABE.txt und für export.js in den Metadaten
        self.assertEqual(self.ex.moderation, "")
        mod = json.loads(z.read(wurzel + "moderation.json"))
        self.assertEqual((mod["hash"], mod["ausgeschaltet"]), ("", "abgabe"))
        self.assertIn("Moderations-Link ausgeschaltet", seite_a)
        self.assertIn('"moderation": false', seite_a)
        self.assertIn("Moderation: ausgeschaltet", z.read(wurzel + "ABGABE.txt").decode())

        # Import in einen anderen Inhalte-Ordner: Unterverzeichnis nachgebildet, Link umgeschrieben, Stempel gültig
        with tempfile.TemporaryDirectory() as t2:
            store2, assets2, k2, r2 = umgebung(t2)
            ziel = store2.verzeichnis_anlegen("Import")
            imp = Importer(store2, assets2, k2)
            vorschau = imp.vorschau(daten, name)
            self.assertEqual(vorschau["seiten"], 2)
            self.assertTrue(vorschau["abgabe"]["gueltig"])
            erste = imp.importieren(vorschau["token"], ziel["id"])
            site = store2.site_laden()
            self.assertEqual(sorted(v["name"] for v in site["verzeichnisse"]), ["Import", "Projekte"])
            s = store2.seite_laden(erste)
            self.assertEqual(s["tags"], ["Reflexion"])
            self.assertIn('href="lp:import/projekte/projekt"', s["bloecke"][0]["html"])
            self.assertNotIn("lp:privat", s["bloecke"][0]["html"])
            self.assertIn("Geheim", s["bloecke"][0]["html"], "Linktext bleibt erhalten")

    def test_moderation_ohne_abgabe(self):
        # Normaler Export: Moderations-Link wie bisher; abwählbar
        _, daten, _ = self.ex.exportieren(self.a, {"kommentare": True})
        z = zipfile.ZipFile(io.BytesIO(daten))
        mod = json.loads(z.read([n for n in z.namelist() if n.endswith("moderation.json")][0]))
        self.assertTrue(self.ex.moderation)
        self.assertEqual(mod["hash"], hashlib.sha256(self.ex.moderation.encode()).hexdigest())
        self.assertNotIn(self.ex.moderation, daten.decode("latin-1"), "Schlüssel selbst nie in der ZIP")
        _, daten, _ = self.ex.exportieren(self.a, {"kommentare": True, "moderation": False})
        z = zipfile.ZipFile(io.BytesIO(daten))
        mod = json.loads(z.read([n for n in z.namelist() if n.endswith("moderation.json")][0]))
        self.assertEqual((self.ex.moderation, mod["hash"], mod["ausgeschaltet"]), ("", "", "export"))
        # Abgabe gewinnt, auch wenn die Oberfläche «moderation: true» schicken würde
        self.ex.exportieren(self.a, {"kommentare": True, "abgabe": True, "moderation": True})
        self.assertEqual(self.ex.moderation, "")

    def test_veraenderter_export_faellt_auf(self):
        name, daten, _ = self.ex.exportieren(self.a, {"abgabe": True})
        z = zipfile.ZipFile(io.BytesIO(daten))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z2:
            for n in z.namelist():
                inhalt = z.read(n)
                if n.endswith("liloport.json"):
                    info = json.loads(inhalt)
                    info["titel"] = "Nachträglich geändert"
                    inhalt = json.dumps(info).encode()
                z2.writestr(n, inhalt)
        with tempfile.TemporaryDirectory() as t2:
            store2, assets2, k2, _ = umgebung(t2)
            vorschau = Importer(store2, assets2, k2).vorschau(out.getvalue(), name)
            self.assertFalse(vorschau["abgabe"]["gueltig"])

    def test_ganzes_portfolio(self):
        _, daten, _ = self.ex.exportieren_mehrere("", {})
        z = zipfile.ZipFile(io.BytesIO(daten))
        info = json.loads(z.read([n for n in z.namelist() if n.endswith("liloport.json")][0]))
        self.assertEqual(len(info["seiten"]), 3)


def comments_modul(ordner):
    quelle = Path(__file__).resolve().parent.parent / "export-templates" / "comments.py"
    ziel = Path(ordner) / "comments.py"
    ziel.write_bytes(quelle.read_bytes())
    spec = importlib.util.spec_from_file_location("comments_test", ziel)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class KommentarBearbeitenTests(unittest.TestCase):
    def test_eigene_und_moderation(self):
        with tempfile.TemporaryDirectory() as t:
            c = comments_modul(t)
            mod = "m" * 24
            (Path(t) / "moderation.json").write_text(json.dumps({"hash": hashlib.sha256(mod.encode()).hexdigest()}))
            st, j = c.verarbeiten("POST", {}, {"name": "Lea", "text": "<p>Hallo</p>", "seite": "a" * 32}, "1.2.3.4")
            self.assertEqual(st, 200)
            kid, schluessel = j["kommentar"]["id"], j["schluessel"]
            self.assertNotIn(schluessel, (Path(t) / "comments.json").read_text())
            st, _ = c.verarbeiten("POST", {}, {"aktion": "bearbeiten", "id": kid, "text": "<p>neu</p>", "schluessel": "x" * 24}, "")
            self.assertEqual(st, 403)
            st, j = c.verarbeiten("POST", {}, {"aktion": "bearbeiten", "id": kid, "text": "<p>Neu<script>x</script></p>", "schluessel": schluessel}, "")
            self.assertEqual((st, j["kommentar"]["text"]), (200, "<p>Neux</p>"))
            self.assertIn("bearbeitet", j["kommentar"])
            st, j = c.verarbeiten("GET", {"liste": "1", "seite": "b" * 32}, {}, "")
            self.assertEqual(j, [], "Kommentar gehört zu einer anderen Seite")
            st, j = c.verarbeiten("POST", {}, {"aktion": "pruefen", "schluessel": mod}, "")
            self.assertTrue(j["ok"])
            st, _ = c.verarbeiten("POST", {}, {"aktion": "loeschen", "id": kid, "schluessel": mod}, "")
            self.assertEqual(st, 200)
            self.assertEqual(json.loads((Path(t) / "comments.json").read_text()), [])


class KonfliktUndGeraetTests(unittest.TestCase):
    def test_konflikt_beim_speichern(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        os.environ.setdefault("LILOPORT_EINSTELLUNGEN", tempfile.mkdtemp())
        import server
        with tempfile.TemporaryDirectory() as t:
            store = server.einrichten(t)
            v = store.verzeichnis_anlegen("A")
            pfad, seite = store.seite_anlegen("S", v["id"])
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                def put(daten):
                    c = http.client.HTTPConnection("127.0.0.1", port)
                    c.request("PUT", "/api/seiten/" + pfad, json.dumps(daten), {"Host": f"127.0.0.1:{port}"})
                    r = c.getresponse()
                    ergebnis = r.status, json.loads(r.read())
                    c.close()
                    return ergebnis
                st, j = put({"titel": "S", "basis": "2000-01-01T00:00:00"})
                self.assertEqual((st, j.get("konflikt")), (409, True))
                st, j = put({"titel": "S2", "basis": "2000-01-01T00:00:00", "erzwingen": True, "tags": ["x"]})
                self.assertEqual((st, j["seite"]["tags"]), (200, ["x"]))
                st, j = put({"titel": "S3", "basis": j["seite"]["geaendert"]})
                self.assertEqual(st, 200)
                # Zwei Speicherungen desselben Editors überholen sich (Autosave + «Fertig»): kein Konflikt
                import time as _t
                basis = j["seite"]["geaendert"]
                st, j = put({"titel": "S4", "basis": basis, "editor": "ed1"})
                self.assertEqual(st, 200)
                _t.sleep(1.1)
                st, j = put({"titel": "S5", "basis": basis, "editor": "ed1"})
                self.assertEqual(st, 200, "eigene frühere Speicherung ist kein Konflikt")
                # ... aber ein anderer Editor mit veraltetem Stand schon
                _t.sleep(1.1)
                st, j = put({"titel": "S6", "basis": basis, "editor": "ed2"})
                self.assertEqual((st, j.get("konflikt")), (409, True))
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_zweites_geraet(self):
        from liloport.sitzung import Sitzung
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as e:
            os.environ["LILOPORT_EINSTELLUNGEN"] = e
            (Path(t) / "_wiki").mkdir()
            ich = Sitzung(t)
            (Path(t) / "_wiki" / "sitzung.json").write_text(json.dumps({"geraet": "0" * 16, "name": "Laptop", "zeit": time.time()}))
            self.assertEqual(ich.status()["fremd"]["name"], "Laptop")
            ich.schreiben()
            self.assertIsNotNone(ich.status()["fremd"], "Warnung bleibt, auch wenn wir selbst geschrieben haben")
            (Path(t) / "_wiki" / "sitzung.json").write_text(json.dumps({"geraet": "0" * 16, "name": "Laptop", "zeit": time.time() - 3600}))
            ich.fremd = None
            self.assertIsNone(ich.status()["fremd"])


class BeispielTests(unittest.TestCase):
    def test_beispiel_anlegen(self):
        with tempfile.TemporaryDirectory() as t:
            store, assets, k, r = umgebung(t)
            start = beispiel.anlegen(store, assets)
            r.alles_schreiben()
            self.assertTrue((Path(t) / (start + ".html")).exists())
            self.assertGreaterEqual(len(store.alle_seiten()), 4)


if __name__ == "__main__":
    unittest.main()


class VerschiebenTests(unittest.TestCase):
    def test_seite_verschieben_zieht_alles_mit(self):
        import server
        with tempfile.TemporaryDirectory() as t:
            store = server.einrichten(t)
            a = store.verzeichnis_anlegen("A"); b = store.verzeichnis_anlegen("B")
            p, _ = store.seite_anlegen("Seite", a["id"])
            q, _ = store.seite_anlegen("Andere", a["id"])
            bild = server.Handler.assets.hochladen(p, "x.png", PNG)
            s = store.seite_aktualisieren(p, bloecke=[{"id": "b1", "typ": "bild", "asset": bild["id"], "breite": "voll"}])
            server.Handler.assets.referenzen_setzen(p, s)
            store.seite_aktualisieren(q, bloecke=[{"id": "b1", "typ": "text", "html": f'<p><a href="lp:{p}">Link</a></p>'},
                                                  {"id": "b2", "typ": "button", "text": "x", "ziel": f"lp:{p}#oben"}])
            server.Handler.history.sichern(p, store.seite_laden(p))
            server.Handler.kommentare.zusammenfuehren(p, [{"id": "k1", "zeit": "2026-01-01T00:00:00", "name": "L", "text": "hi"}])
            neu = store.seite_verschieben(p, b["id"])
            links.pfade_umbenennen(store, p, neu); server.Handler.assets.pfade_umbenennen(p, neu)
            server.Handler.history.verschieben(p, neu); server.Handler.kommentare.pfade_umbenennen(p, neu)
            server.Handler.renderer.alles_schreiben()
            self.assertEqual(neu, "b/seite")
            self.assertTrue((Path(t) / "b/seite.json").exists()); self.assertFalse((Path(t) / "a/seite.json").exists())
            self.assertEqual(server.Handler.assets.laden()[bild["id"]]["heimat"], neu)
            andere = store.seite_laden(q)
            self.assertIn('lp:b/seite"', andere["bloecke"][0]["html"]); self.assertEqual(andere["bloecke"][1]["ziel"], "lp:b/seite#oben")
            self.assertEqual(len(server.Handler.kommentare.laden(neu)), 1)
            self.assertTrue(server.Handler.history.versionen(neu))
            site = store.site_laden()
            self.assertEqual([v["seiten"] for v in site["verzeichnisse"]], [["andere"], ["seite"]])
            html = (Path(t) / "a/andere.html").read_text(encoding="utf-8")
            self.assertIn('href="../b/seite.html"', html)
