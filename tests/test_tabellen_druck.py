"""Tabellen (Profi), lange Links und Druckhinweise für Inhalte, die es nur digital gibt."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from liloport.render import BlockRenderer  # noqa: E402
from liloport.sanitize import filtern  # noqa: E402

REG = {
    "v": {"datei": "assets/a/film.mp4", "name": "film.mp4"},
    "a": {"datei": "assets/a/ton.mp3", "name": "ton.mp3"},
    "p": {"datei": "assets/a/bericht.pdf", "name": "bericht.pdf"},
    "z": {"datei": "assets/a/daten.zip", "name": "daten.zip", "groesse": 2_500_000},
}


class TabellenFilter(unittest.TestCase):
    def test_design_und_zusaetze_bleiben(self):
        aus = filtern('<table class="tab-teal tab-breit tab-summe boese"><caption>C</caption><tbody><tr><td>x</td></tr></tbody></table>', "profi")
        self.assertIn('<table class="tab-teal tab-breit tab-summe"><caption>C</caption>', aus)

    def test_zellstil(self):
        aus = filtern('<table><tr><td style="background-color: #fdf0a6; color: #2a2a28; text-align: center; vertical-align: middle; width: 25%; position: absolute">x</td></tr></table>', "profi")
        self.assertIn('style="background-color: #fdf0a6; color: #2a2a28; text-align: center; vertical-align: middle; width: 25%"', aus)

    def test_breite_nur_in_zellen_und_harmlos(self):
        self.assertEqual(filtern('<p style="width: 50%">x</p>', "profi"), "<p>x</p>")
        self.assertNotIn("width", filtern('<table><tr><td style="width: calc(1px)">x</td></tr></table>', "profi"))

    def test_colspan(self):
        aus = filtern('<table><tr><td colspan="2" rowspan="abc">x</td><td colspan="999">y</td></tr></table>', "profi")
        self.assertIn('<td colspan="2">x</td><td>y</td>', aus)

    def test_amateur_ohne_tabelle(self):
        self.assertNotIn("<table", filtern('<table class="tab-teal"><tr><td>x</td></tr></table>', "amateur"))

    def test_tabelle_im_rahmen(self):
        aus = BlockRenderer({}, "").block({"id": "t", "typ": "text", "html": "<table><tr><td>a</td></tr></table>"})
        self.assertIn('<div class="tabelle-rahmen"><table>', aus)
        self.assertIn("</table></div>", aus)


class Druckhinweise(unittest.TestCase):
    def setUp(self):
        self.br = BlockRenderer(REG, "")

    def test_video(self):
        aus = self.br.block({"id": "1", "typ": "video", "asset": "v"})
        self.assertIn('class="druck-nur druck-hinweis"', aus)
        self.assertIn("ein Video eingebunden", aus)
        self.assertIn("«film.mp4»", aus)

    def test_audio(self):
        self.assertIn("Audioaufnahme", self.br.block({"id": "1", "typ": "audio", "asset": "a"}))

    def test_pdf_mit_startseite(self):
        aus = self.br.block({"id": "1", "typ": "pdf", "asset": "p", "seite": 3})
        self.assertIn("PDF-Dokument eingebettet", aus)
        self.assertIn("(ab Seite 3)", aus)
        self.assertIn("«bericht.pdf»", aus)

    def test_zip(self):
        aus = self.br.block({"id": "1", "typ": "datei", "asset": "z"})
        self.assertIn("ZIP-Archiv", aus)
        self.assertIn("heruntergeladen werden", aus)
        self.assertIn("2.4 MB", aus)

    def test_button(self):
        aus = self.br.block({"id": "1", "typ": "button", "text": "Web", "ziel": "https://example.org/x"})
        self.assertIn('class="druck-nur druck-button-info"', aus)
        self.assertIn("https://example.org/x", aus)
        intern = self.br.block({"id": "1", "typ": "button", "text": "Seite", "ziel": "lp:a/b"})
        self.assertIn("verlinkten Seite", intern)

    def test_html_nur_wenn_interaktiv(self):
        self.assertIn("druck-hinweis", self.br.block({"id": "1", "typ": "html", "html": '<iframe src="https://x"></iframe>'}))
        self.assertNotIn("druck-hinweis", self.br.block({"id": "1", "typ": "html", "html": "<p>nur Text</p>"}))


if __name__ == "__main__":
    unittest.main()
