"""Tests für Phase 1: Slug-Regel, HTML-Filter, Store, Renderer, Menü, relative Pfade."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liloport import sanitize, slugs  # noqa: E402
from liloport.render import Renderer, menue_daten, relativ_zur_wurzel  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402


class SlugTests(unittest.TestCase):
    def test_umlaute_und_zeichen(self):
        self.assertEqual(slugs.slugify("Übung 1: Grüsse & Küsse!"), "uebung-1-gruesse-kuesse")

    def test_akzente(self):
        self.assertEqual(slugs.slugify("Café Résumé"), "cafe-resume")

    def test_leer_und_laenge(self):
        self.assertEqual(slugs.slugify("   "), "seite")
        self.assertLessEqual(len(slugs.slugify("x" * 200)), 60)

    def test_eindeutig(self):
        self.assertEqual(slugs.eindeutig("a", {"a", "a-2"}), "a-3")
        self.assertEqual(slugs.eindeutig("b", {"a"}), "b")


class SanitizeTests(unittest.TestCase):
    def test_erlaubte_tags_bleiben(self):
        roh = '<h2>T</h2><p><strong>f</strong> <em>k</em> <u>u</u></p><ul><li>x</li></ul>'
        self.assertEqual(sanitize.filtern(roh), roh)

    def test_script_und_attribute_fliegen_raus(self):
        roh = '<p onclick="x()">a</p><script>alert(1)</script><img src=x>'
        self.assertEqual(sanitize.filtern(roh), '<p>a</p>alert(1)')

    def test_b_i_werden_umbenannt(self):
        self.assertEqual(sanitize.filtern("<b>a</b><i>b</i>"), "<strong>a</strong><em>b</em>")

    def test_javascript_link_entfernt(self):
        self.assertEqual(sanitize.filtern('<a href="javascript:x()">l</a>'), "<a>l</a>")
        self.assertEqual(sanitize.filtern('<a href="https://x.ch">l</a>'), '<a href="https://x.ch">l</a>')

    def test_offene_tags_werden_geschlossen(self):
        self.assertEqual(sanitize.filtern("<p>a<strong>b"), "<p>a<strong>b</strong></p>")


class StoreUndRendererTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.renderer = Renderer(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_anlegen_erzeugt_site_json(self):
        site = self.store.site_laden()
        self.assertEqual(site["niveau"], "amateur")
        self.assertTrue((self.store.root / "_wiki").is_dir())

    def test_verzeichnis_ist_echter_ordner(self):
        v = self.store.verzeichnis_anlegen("Semester 1")
        self.assertEqual(v["ordner"], "semester-1")
        self.assertTrue((self.store.root / "semester-1").is_dir())
        u = self.store.verzeichnis_anlegen("Projekte", eltern=v["id"])
        self.assertEqual(u["ordner"], "semester-1/projekte")
        self.assertTrue((self.store.root / "semester-1/projekte").is_dir())

    def test_verzeichnis_umbenennen_verschiebt_ordner(self):
        v = self.store.verzeichnis_anlegen("Alt")
        u = self.store.verzeichnis_anlegen("Unten", eltern=v["id"])
        pfad, _ = self.store.seite_anlegen("Seite", u["id"])
        self.store.verzeichnis_aendern(v["id"], name="Neu")
        site = self.store.site_laden()
        self.assertEqual(self.store.verzeichnis(site, v["id"])["ordner"], "neu")
        self.assertEqual(self.store.verzeichnis(site, u["id"])["ordner"], "neu/unten")
        self.assertTrue((self.store.root / "neu/unten/seite.json").exists())
        self.assertFalse((self.store.root / "alt").exists())

    def test_verzeichnis_loeschen_nur_wenn_leer(self):
        v = self.store.verzeichnis_anlegen("A")
        self.store.seite_anlegen("S", v["id"])
        with self.assertRaises(StoreFehler):
            self.store.verzeichnis_loeschen(v["id"])
        self.store.seite_loeschen("a/s")
        self.store.verzeichnis_loeschen(v["id"])
        self.assertFalse((self.store.root / "a").exists())

    def test_seite_anlegen_und_slug_kollision(self):
        v = self.store.verzeichnis_anlegen("A")
        p1, _ = self.store.seite_anlegen("Mein Text", v["id"])
        p2, _ = self.store.seite_anlegen("Mein Text", v["id"])
        self.assertEqual((p1, p2), ("a/mein-text", "a/mein-text-2"))
        self.assertTrue((self.store.root / "a/mein-text-2.json").exists())

    def test_pfad_ausserhalb_wird_abgewiesen(self):
        with self.assertRaises(StoreFehler):
            self.store.sicherer_pfad("../../etc/passwd")

    def test_relative_pfade_nach_tiefe(self):
        self.assertEqual(relativ_zur_wurzel("a/s"), "../")
        self.assertEqual(relativ_zur_wurzel("a/b/c/s"), "../../../")

    def test_rendern_erzeugt_html_mit_relativen_links(self):
        v = self.store.verzeichnis_anlegen("Semester 1")
        u = self.store.verzeichnis_anlegen("Projekte", eltern=v["id"])
        pfad, _ = self.store.seite_anlegen("Projekt A", u["id"], "seitenmenue",
                                          [{"id": "b1", "typ": "text", "html": "<p>Hallo <b>Welt</b></p>"},
                                           {"id": "b2", "typ": "trenner"}])
        self.renderer.alles_schreiben()
        html = (self.store.root / "semester-1/projekte/projekt-a.html").read_text(encoding="utf-8")
        self.assertIn('href="../../_wiki/style.css"', html)
        self.assertIn('src="../../_wiki/menu.js"', html)
        self.assertIn('data-menue="seitenmenue"', html)
        self.assertIn("<p>Hallo <strong>Welt</strong></p>", html)
        self.assertIn('class="block block-trenner"', html)
        self.assertTrue((self.store.root / "index.html").exists())
        self.assertTrue((self.store.root / "_wiki/reader.js").exists())
        self.assertTrue((self.store.root / "_wiki/logo.svg").exists())

    def test_menu_js_enthaelt_struktur(self):
        v = self.store.verzeichnis_anlegen("Semester 1", in_menue=False)
        self.store.seite_anlegen("Lernjournal", v["id"])
        daten = self.renderer.menue_schreiben()
        text = (self.store.root / "_wiki/menu.js").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("window.LILOPORT = "))
        geparst = json.loads(text[len("window.LILOPORT = "):].rstrip().rstrip(";"))
        self.assertEqual(geparst["verzeichnisse"][0]["seiten"][0]["pfad"], "semester-1/lernjournal")
        self.assertFalse(daten["verzeichnisse"][0]["inMenue"])

    def test_seite_aktualisieren_rendert_neu(self):
        v = self.store.verzeichnis_anlegen("A")
        pfad, _ = self.store.seite_anlegen("S", v["id"])
        self.renderer.alles_schreiben()
        self.store.seite_aktualisieren(pfad, titel="Neuer Titel", menue="keine")
        self.renderer.seite_schreiben(pfad)
        html = (self.store.root / "a/s.html").read_text(encoding="utf-8")
        self.assertIn("<title>Neuer Titel – Liloport</title>", html)
        self.assertIn('data-menue="keine"', html)


if __name__ == "__main__":
    unittest.main()
