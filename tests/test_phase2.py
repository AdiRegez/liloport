"""Tests für Phase 2: Anhänge, Referenzzählung, Löschlogik, Redirects, CSS-Scoping, Blockprüfung."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
from liloport import sanitize  # noqa: E402
from liloport.assets import Assets, typ_erkennen  # noqa: E402
from liloport.render import Renderer, css_scopen  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


class TypTests(unittest.TestCase):
    def test_erkennung(self):
        self.assertEqual(typ_erkennen(PNG), ("bild", "png"))
        self.assertEqual(typ_erkennen(PDF), ("pdf", "pdf"))
        self.assertEqual(typ_erkennen(MP4), ("video", "mp4"))
        self.assertEqual(typ_erkennen(b"<svg xmlns='x'></svg>"), ("bild", "svg"))
        with self.assertRaises(StoreFehler):
            typ_erkennen(b"MZ\x90\x00 exe")


class CssTests(unittest.TestCase):
    def test_selektoren_werden_gescoped(self):
        css = "h2, p { color: red } @media (max-width: 600px) { .x { margin: 0 } }"
        out = css_scopen(css, "intro")
        self.assertIn(".seite-intro h2, .seite-intro p {", out)
        self.assertIn("@media (max-width: 600px) {", out)
        self.assertIn(".seite-intro .x {", out)

    def test_stil_attribut_gefiltert(self):
        self.assertEqual(sanitize.filtern('<p style="color:red; position:fixed">a</p>', "profi"),
                         '<p style="color: red">a</p>')
        self.assertEqual(sanitize.filtern('<span style="background:url(x)">a</span>', "profi"), "<span>a</span>")


class BlockPruefungTests(unittest.TestCase):
    def test_medien_und_spalten(self):
        bl = server.bloecke_pruefen([
            {"id": "b1", "typ": "bild", "asset": "0123abcd", "breite": "33%", "bildtext": "x"},
            {"id": "b2", "typ": "pdf", "asset": "", "hoehe": "9999"},
            {"id": "b3", "typ": "spalten", "spalten": [[{"typ": "text", "html": "<b>a</b>"}], [{"typ": "trenner"}]]},
            {"id": "b4", "typ": "html", "html": "<div class=\"x\">roh</div>"},
        ])
        self.assertEqual(bl[0]["breite"], "33%")
        self.assertEqual(bl[1]["hoehe"], 2000)
        self.assertEqual(bl[2]["spalten"][0][0]["html"], "<strong>a</strong>")
        self.assertEqual(bl[3]["html"], '<div class="x">roh</div>')
        with self.assertRaises(StoreFehler):
            server.bloecke_pruefen([{"typ": "bild", "asset": "../x"}])
        with self.assertRaises(StoreFehler):
            server.bloecke_pruefen([{"typ": "spalten", "spalten": [[{"typ": "spalten", "spalten": [[], []]}], []]}])


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.assets = Assets(self.store)
        self.renderer = Renderer(self.store, self.assets)
        self.v = self.store.verzeichnis_anlegen("A")
        self.p1, _ = self.store.seite_anlegen("Eins", self.v["id"])
        self.p2, _ = self.store.seite_anlegen("Zwei", self.v["id"])

    def tearDown(self):
        self.tmp.cleanup()

    def _einbetten(self, pfad, aid, typ="bild"):
        seite = self.store.seite_aktualisieren(pfad, bloecke=[{"id": "b1", "typ": typ, "asset": aid, "breite": "voll"}])
        self.assets.referenzen_setzen(pfad, seite)
        return seite

    def test_upload_landet_unter_assets_slug(self):
        e = self.assets.hochladen(self.p1, "Mein Bild.PNG", PNG)
        self.assertEqual(e["datei"], "assets/eins/mein-bild.png")
        self.assertEqual(e["typ"], "bild")
        self.assertTrue((self.store.root / e["datei"]).exists())
        e2 = self.assets.hochladen(self.p1, "Mein Bild.PNG", PNG)
        self.assertEqual(e2["datei"], "assets/eins/mein-bild-2.png")

    def test_falscher_typ_abgewiesen(self):
        with self.assertRaises(StoreFehler):
            self.assets.hochladen(self.p1, "x.png", b"kein bild")

    def test_referenzen_und_rendering(self):
        e = self.assets.hochladen(self.p1, "b.png", PNG)
        self._einbetten(self.p1, e["id"])
        self._einbetten(self.p2, e["id"])
        reg = self.assets.laden()
        self.assertEqual(sorted(reg[e["id"]]["referenzen"]), ["a/eins", "a/zwei"])
        self.renderer.alles_schreiben()
        html = (self.store.root / "a/zwei.html").read_text(encoding="utf-8")
        self.assertIn('<img src="../assets/eins/b.png"', html)
        # Referenz entfernen
        seite = self.store.seite_aktualisieren(self.p2, bloecke=[])
        self.assets.referenzen_setzen(self.p2, seite)
        self.assertEqual(self.assets.laden()[e["id"]]["referenzen"], ["a/eins"])

    def test_html_block_referenz_wird_erkannt(self):
        e = self.assets.hochladen(self.p1, "b.png", PNG)
        seite = self.store.seite_aktualisieren(self.p2, bloecke=[{"id": "b1", "typ": "html", "html": '<img src="../assets/eins/b.png">'}])
        self.assets.referenzen_setzen(self.p2, seite)
        self.assertIn("a/zwei", self.assets.laden()[e["id"]]["referenzen"])

    def test_loeschen_mit_drei_listen(self):
        nur_eins = self.assets.hochladen(self.p1, "nur.png", PNG)
        geteilt = self.assets.hochladen(self.p1, "geteilt.pdf", PDF)
        self.store.seite_aktualisieren(self.p1, bloecke=[
            {"id": "b1", "typ": "bild", "asset": nur_eins["id"]}, {"id": "b2", "typ": "pdf", "asset": geteilt["id"]}])
        self.assets.referenzen_setzen(self.p1, self.store.seite_laden(self.p1))
        self._einbetten(self.p2, geteilt["id"], "pdf")
        v2 = self.store.verzeichnis_anlegen("B")
        self.store.redirect_hinzufuegen(v2["id"], self.p1)
        self.renderer.alles_schreiben()
        self.assertTrue((self.store.root / "b/eins.html").exists())

        vorschau = self.assets.loesch_vorschau(self.p1)
        self.assertEqual([e["id"] for e in vorschau["geloescht"]], [nur_eins["id"]])
        self.assertEqual(vorschau["bleibt"][0]["seiten"], ["a/zwei"])
        self.assertEqual(vorschau["redirects"][0]["ordner"], "b")

        self.assets.seite_loeschen(self.p1)
        self.renderer.alles_schreiben()
        reg = self.assets.laden()
        self.assertNotIn(nur_eins["id"], reg)
        self.assertEqual(reg[geteilt["id"]]["heimat"], "a/zwei")
        self.assertEqual(reg[geteilt["id"]]["datei"], "assets/zwei/geteilt.pdf")
        self.assertTrue((self.store.root / "assets/zwei/geteilt.pdf").exists())
        self.assertFalse((self.store.root / "assets/eins").exists())
        self.assertFalse((self.store.root / "a/eins.json").exists())
        self.assertFalse((self.store.root / "b/eins.html").exists())
        self.assertNotIn("->a/eins", self.store.verzeichnis(self.store.site_laden(), v2["id"])["seiten"])
        html = (self.store.root / "a/zwei.html").read_text(encoding="utf-8")
        self.assertIn("assets/zwei/geteilt.pdf", html)

    def test_verwaist_und_loeschen(self):
        e = self.assets.hochladen(self.p1, "x.png", PNG)
        self.assertEqual([x["id"] for x in self.assets.verwaist()], [e["id"]])
        self._einbetten(self.p1, e["id"])
        with self.assertRaises(StoreFehler):
            self.assets.loeschen(e["id"])
        seite = self.store.seite_aktualisieren(self.p1, bloecke=[])
        self.assets.referenzen_setzen(self.p1, seite)
        self.assets.loeschen(e["id"])
        self.assertFalse((self.store.root / "assets/eins").exists())

    def test_umbenennen_passt_registry_und_redirects_an(self):
        e = self.assets.hochladen(self.p1, "x.png", PNG)
        self._einbetten(self.p1, e["id"])
        v2 = self.store.verzeichnis_anlegen("B")
        self.store.redirect_hinzufuegen(v2["id"], self.p1)
        self.store.verzeichnis_aendern(self.v["id"], name="Neu")
        self.assets.pfade_umbenennen(*self.store.letzte_umbenennung)
        reg = self.assets.laden()[e["id"]]
        self.assertEqual(reg["heimat"], "neu/eins")
        self.assertEqual(reg["referenzen"], ["neu/eins"])
        self.assertIn("->neu/eins", self.store.verzeichnis(self.store.site_laden(), v2["id"])["seiten"])

    def test_redirect_seite_rendert(self):
        v2 = self.store.verzeichnis_anlegen("B")
        u = self.store.verzeichnis_anlegen("Tief", eltern=v2["id"])
        self.store.redirect_hinzufuegen(u["id"], self.p1)
        with self.assertRaises(StoreFehler):
            self.store.redirect_hinzufuegen(u["id"], self.p1)
        self.renderer.alles_schreiben()
        html = (self.store.root / "b/tief/eins.html").read_text(encoding="utf-8")
        self.assertIn('url=../../a/eins.html', html)
        daten = self.renderer.menue_schreiben()
        tief = [v for v in daten["verzeichnisse"] if v["id"] == u["id"]][0]
        self.assertTrue(tief["seiten"][0]["redirect"])
        self.store.redirect_entfernen(u["id"], self.p1)
        self.assertFalse((self.store.root / "b/tief/eins.html").exists())


if __name__ == "__main__":
    unittest.main()
