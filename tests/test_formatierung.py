"""Formatierung im Textblock (Fett/Kursiv/Unterstrichen, Farbe, Textmarker) und «zuletzt bearbeitet»."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from liloport.render import seiten_meta_html, zeit_lesbar  # noqa: E402
from liloport.sanitize import filtern  # noqa: E402


class FormatierungFilter(unittest.TestCase):
    def test_span_stile_werden_zu_auszeichnung(self):
        roh = ('<p><span style="font-weight: bold;">a</span> <span style="font-style: italic;">b</span> '
               '<span style="text-decoration-line: underline;">c</span> <span style="text-decoration: line-through;">d</span></p>')
        aus = filtern(roh, "profi")
        self.assertIn("<strong><span>a</span></strong>", aus)
        self.assertIn("<em><span>b</span></em>", aus)
        self.assertIn("<u><span>c</span></u>", aus)
        self.assertIn("<s><span>d</span></s>", aus)
        self.assertNotIn("font-weight", aus)

    def test_fett_und_farbe_zusammen(self):
        aus = filtern('<p><span style="font-weight: 700; color: rgb(42, 127, 120);">x</span></p>', "profi")
        self.assertEqual(aus, '<p><strong><span style="color: rgb(42, 127, 120)">x</span></strong></p>')

    def test_amateur_behaelt_fett_aber_keine_farbe(self):
        aus = filtern('<p><span style="font-weight: bold; color: red;">x</span></p>', "amateur")
        self.assertEqual(aus, "<p><strong><span>x</span></strong></p>")

    def test_b_i_u_bleiben(self):
        self.assertEqual(filtern("<p><b>a</b><i>b</i><u>c</u></p>", "profi"), "<p><strong>a</strong><em>b</em><u>c</u></p>")

    def test_font_color_wird_span(self):
        self.assertEqual(filtern('<p><font color="#ff0000">rot</font></p>', "profi"), '<p><span style="color: #ff0000">rot</span></p>')
        self.assertEqual(filtern('<p><font color="javascript:x">x</font></p>', "profi"), "<p><span>x</span></p>")

    def test_textmarker_bleibt(self):
        roh = '<p><span style="background-color: rgb(58, 46, 74); color: rgb(255, 255, 255);">m</span></p>'
        self.assertEqual(filtern(roh, "profi"), '<p><span style="background-color: rgb(58, 46, 74); color: rgb(255, 255, 255)">m</span></p>')

    def test_verschachtelt_und_fussnote(self):
        aus = filtern('<p><span style="font-weight:bold">a <span class="fussnote">f</span> b</span> c</p>', "profi")
        self.assertEqual(aus, '<p><strong><span>a <span class="fussnote">f</span> b</span></strong> c</p>')


class ZuletztBearbeitet(unittest.TestCase):
    def test_zeit_lesbar(self):
        self.assertEqual(zeit_lesbar("2026-11-06T09:15:42"), "06.11.2026, 09:15")
        self.assertEqual(zeit_lesbar(""), "")
        self.assertEqual(zeit_lesbar("kaputt"), "")

    def test_meta_mit_zuletzt_bearbeitet(self):
        html = seiten_meta_html({"datum": "2026-11-05", "geaendert": "2026-11-06T09:15:42", "tags": []}, "./")
        self.assertIn("05.11.2026", html)
        self.assertIn('zuletzt bearbeitet <time datetime="2026-11-06T09:15:42">06.11.2026, 09:15</time>', html)

    def test_export_ohne_datum_ohne_zuletzt(self):
        html = seiten_meta_html({"datum": "2026-11-05", "geaendert": "2026-11-06T09:15:42", "tags": []}, None, datum=False)
        self.assertEqual(html, "")


class Gliederung(unittest.TestCase):
    BLOECKE = [
        {"id": "b1", "typ": "text", "html": "<p>Intro</p><h1>A</h1><p>a</p><h2>A1</h2><p>x</p>"},
        {"id": "b2", "typ": "trenner"},
        {"id": "b3", "typ": "text", "html": "<h3>A1a</h3><p>y</p><h2>A2</h2><h1>B</h1><p>b</p>"},
        {"id": "b4", "typ": "text", "klapp": "zu", "html": "<h1>im Klappblock</h1>"},
    ]

    def _render(self, art):
        from liloport.render import BlockRenderer
        return BlockRenderer({}, "").bloecke(self.BLOECKE, art)

    def test_standard_ohne_wahl(self):
        aus = self._render("")
        self.assertTrue(aus.startswith('<div class="gliederung gl-standard">'))
        self.assertIn('data-gliederung="1.1"', aus)
        self.assertIn('data-id="b1"', aus)
        self.assertNotIn('<span class="gl-nr">', aus)

    def test_verschachtelung(self):
        import re
        aus = self._render("linien")
        self.assertTrue(aus.startswith('<div class="gliederung gl-linien">'))
        # Reihenfolge der Abschnitte und Tiefe
        self.assertEqual(re.findall(r'data-gliederung="([\d.]+)"', aus), ["1", "1.1", "1.1.1", "1.2", "2"])
        self.assertEqual(aus.count("<section"), aus.count("</section>"))
        # Trenner gehört zu A1 (vor A1a), Klappblock zu B (ganz, ohne eigenen Abschnitt)
        a1 = aus.index('data-gliederung="1.1"'); a1a = aus.index('data-gliederung="1.1.1"')
        self.assertTrue(a1 < aus.index('data-id="b2"') < a1a)
        self.assertGreater(aus.index("im Klappblock"), aus.index('data-gliederung="2"'))
        self.assertNotIn('<span class="gl-nr">', aus)

    def test_nummern(self):
        aus = self._render("nummern")
        self.assertIn('<h3><span class="gl-nr">1.1.1</span> A1a</h3>', aus)
        self.assertIn('<h1><span class="gl-nr">2</span> B</h1>', aus)

    def test_unbekanntes_design_ist_standard(self):
        self.assertTrue(self._render("<script>").startswith('<div class="gliederung gl-standard">'))


if __name__ == "__main__":
    unittest.main()
