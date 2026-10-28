"""Tests für Phase 4: Suchindex, PDF-Text, Kommentare (Export, Download-Datei, Import)."""
import io
import json
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liloport.assets import Assets  # noqa: E402
from liloport.export import Exporter  # noqa: E402
from liloport.kommentare import Kommentare  # noqa: E402
from liloport.render import Renderer  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402
from liloport.suche import Suche, html_zu_text, pdf_text  # noqa: E402


def mini_pdf(text_ops: bytes) -> bytes:
    """Ein winziges PDF mit einem FlateDecode-Inhaltsstrom."""
    stream = zlib.compress(b"BT /F1 12 Tf 72 700 Td " + text_ops + b" ET")
    return (b"%PDF-1.4\n1 0 obj<</Length " + str(len(stream)).encode() + b" /Filter /FlateDecode>>stream\n"
            + stream + b"\nendstream\nendobj\ntrailer<<>>\n%%EOF\n")


class SucheTests(unittest.TestCase):
    def test_html_zu_text(self):
        self.assertEqual(html_zu_text("<h2>A</h2><p>b &amp; <strong>c</strong></p><script>x</script>"), "A b & c")

    def test_pdf_text_tj_und_tj_array(self):
        pdf = mini_pdf(b"(Lernjournal Woche) Tj [(Zwei) -250 (Wochen)] TJ")
        self.assertIn("Lernjournal Woche", pdf_text(pdf))
        self.assertIn("Zwei Wochen", pdf_text(pdf))

    def test_pdf_ohne_text(self):
        self.assertEqual(pdf_text(b"%PDF-1.4\n%%EOF"), "")

    def test_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp); store.anlegen()
            assets = Assets(store)
            v = store.verzeichnis_anlegen("A")
            pfad, _ = store.seite_anlegen("Reflexion", v["id"])
            pdf = assets.hochladen(pfad, "skript.pdf", mini_pdf(b"(Thermodynamik Grundlagen) Tj"))
            seite = store.seite_aktualisieren(pfad, bloecke=[
                {"id": "b1", "typ": "text", "html": "<p>Wärmelehre <em>heute</em></p>"},
                {"id": "b2", "typ": "pdf", "asset": pdf["id"]}])
            assets.referenzen_setzen(pfad, seite)
            suche = Suche(store, assets)
            self.assertEqual(suche.schreiben(), 1)
            js = (store.root / "_wiki/suchindex.js").read_text(encoding="utf-8")
            daten = json.loads(js[len("window.LILOPORT_INDEX = "):].rstrip().rstrip(";"))
            self.assertEqual(daten[0]["titel"], "Reflexion")
            self.assertIn("Wärmelehre heute", daten[0]["text"])
            self.assertIn("Thermodynamik", daten[0]["text"])
            self.assertEqual(daten[0]["anhaenge"], ["skript.pdf"])
            self.assertTrue((store.root / "_wiki/pdftext.json").exists(), "PDF-Text wird zwischengespeichert")

    def test_index_im_hintergrund(self):
        # Laufendes Liloport: Index sofort ohne neuen PDF-Text, kurz danach mit
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp); store.anlegen()
            assets = Assets(store)
            v = store.verzeichnis_anlegen("A")
            pfad, _ = store.seite_anlegen("Reflexion", v["id"])
            pdf = assets.hochladen(pfad, "skript.pdf", mini_pdf(b"(Thermodynamik Grundlagen) Tj"))
            seite = store.seite_aktualisieren(pfad, bloecke=[{"id": "b2", "typ": "pdf", "asset": pdf["id"]}])
            assets.referenzen_setzen(pfad, seite)
            suche = Suche(store, assets, hintergrund=True)
            suche.schreiben()
            self.assertTrue(suche.warten(10))
            js = (store.root / "_wiki/suchindex.js").read_text(encoding="utf-8")
            self.assertIn("Thermodynamik", js)
            # Defektes PDF: wird als leer gemerkt und nicht bei jedem Start neu versucht
            kaputt = assets.hochladen(pfad, "kaputt.pdf", b"%PDF-1.4\n1 0 obj <</Font 2 0 R>> stream\nxx\nendstream endobj")
            seite = store.seite_aktualisieren(pfad, bloecke=seite["bloecke"] + [{"id": "b3", "typ": "pdf", "asset": kaputt["id"]}])
            assets.referenzen_setzen(pfad, seite)
            suche.schreiben(); self.assertTrue(suche.warten(10))
            cache = json.loads((store.root / "_wiki/pdftext.json").read_text(encoding="utf-8"))
            self.assertIn(kaputt["id"], cache)
            self.assertEqual(suche._fehlende(cache), [])

    def test_zeitlimit(self):
        from liloport.pdftext import PdfZuAufwendig
        with self.assertRaises(PdfZuAufwendig):
            pdf_text(mini_pdf(b"(x) Tj"), sekunden=-1)


class KommentareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name); self.store.anlegen()
        self.assets = Assets(self.store)
        self.kommentare = Kommentare(self.store)
        v = self.store.verzeichnis_anlegen("A")
        self.pfad, _ = self.store.seite_anlegen("Blog", v["id"], "voll", [{"id": "b1", "typ": "text", "html": "<p>Hi</p>"}])
        self.store.seite_aktualisieren(self.pfad, kommentare=True)
        self.exporter = Exporter(self.store, self.assets, self.kommentare)
        self.renderer = Renderer(self.store, self.assets, self.kommentare)

    def tearDown(self):
        self.tmp.cleanup()

    def _export(self, optionen=None):
        name, daten, zufall = self.exporter.exportieren(self.pfad, optionen)
        return zipfile.ZipFile(io.BytesIO(daten)), zufall

    def test_export_mit_kommentarfunktion(self):
        z, zufall = self._export()
        namen = z.namelist()
        ordner = namen[0].split("/")[0]
        self.assertIn(f"{ordner}/inhalt/comments.php", namen)
        self.assertIn(f"{ordner}/inhalt/comments.json", namen)
        self.assertNotIn(f"{ordner}/inhalt/export.js", namen)
        html = z.read(f"{ordner}/inhalt/{zufall}.html").decode()
        self.assertIn("/* export.js */", html, "Skripte stehen direkt in der Seite")
        self.assertIn("/* comment-editor.js */", html)
        self.assertIn('id="kommentare"', html)
        self.assertIn('id="kommentar-form"', html)
        self.assertIn(f'"export": "{zufall}"', html)
        self.assertEqual(self.kommentare.exporte()[zufall]["pfad"], self.pfad)

    def test_export_ohne_kommentarfunktion(self):
        self.store.seite_aktualisieren(self.pfad, kommentare=False)
        z, zufall = self._export()
        self.assertFalse(any(n.endswith("comments.php") for n in z.namelist()))
        html = [z.read(n).decode() for n in z.namelist() if n.endswith(".html") and "/inhalt/" in n and not n.endswith("dateien.html")][0]
        self.assertNotIn('id="kommentare"', html)
        self.assertIn('id="liloport-meta"', html, "Kennung für Download/Import ist trotzdem da")

    def test_import_aus_heruntergeladener_seite(self):
        z, zufall = self._export()
        html = [z.read(n).decode() for n in z.namelist() if n.endswith(".html") and "/inhalt/" in n and not n.endswith("dateien.html")][0]
        # So baut export.js die heruntergeladene Datei: eingebettete Kommentare am Ende
        liste = [{"id": "k1", "zeit": "2026-10-24T10:00:00+02:00", "name": "Lea", "text": "Spannend!"},
                 {"id": "k2", "zeit": "2026-10-24T11:00:00+02:00", "name": "", "text": "<b>Frage</b>"}]
        runter = html.replace('id="liloport-kommentare">[]</script>', "") \
            + f'<script type="application/json" id="liloport-kommentare">{json.dumps(liste)}</script>'
        ergebnis = self.kommentare.importieren_aus_datei(f"{zufall}.html", runter.encode())
        self.assertEqual((ergebnis["pfad"], ergebnis["neu"], ergebnis["gesamt"]), (self.pfad, 2, 2))
        # nochmals importieren: nichts Neues
        self.assertEqual(self.kommentare.importieren_aus_datei(f"{zufall}.html", runter.encode())["neu"], 0)
        # lokale Seite zeigt die Kommentare, HTML wird escaped
        self.renderer.alles_schreiben()
        seite = (self.store.root / self.pfad).with_suffix(".html").read_text(encoding="utf-8")
        self.assertIn("Kommentare vom Webserver", seite)
        self.assertIn("Spannend!", seite)
        self.assertIn("<strong>Frage</strong>", seite, "HTML in Kommentaren wird gefiltert, nicht escaped")
        self.assertIn("Anonym", seite)
        # nächster Export nimmt die Kommentare mit
        z2, _ = self._export()
        cj = [z2.read(n) for n in z2.namelist() if n.endswith("comments.json")][0]
        self.assertEqual(len(json.loads(cj)), 2)

    def test_import_json_mit_kennung_im_namen(self):
        _, zufall = self._export()
        liste = json.dumps([{"id": "x", "zeit": "2026-01-01T00:00:00", "name": "A", "text": "ok"}]).encode()
        with self.assertRaises(StoreFehler):
            self.kommentare.importieren_aus_datei("comments.json", liste)
        self.assertEqual(self.kommentare.importieren_aus_datei(f"comments-{zufall}.json", liste)["neu"], 1)

    def test_unbekannte_kennung(self):
        with self.assertRaises(StoreFehler):
            self.kommentare.importieren_aus_datei("x.html", b'<script type="application/json" id="liloport-meta">{"export":"a"*32}</script>')

    def test_loeschen_und_umbenennen(self):
        _, zufall = self._export()
        self.kommentare.importieren(zufall, [{"id": "k1", "zeit": "2026", "name": "", "text": "a"}, {"id": "k2", "zeit": "2026", "name": "", "text": "b"}])
        self.kommentare.loeschen(self.pfad, "k1")
        self.assertEqual([k["id"] for k in self.kommentare.laden(self.pfad)], ["k2"])
        self.store.verzeichnis_aendern("d1", name="Neu")
        self.kommentare.pfade_umbenennen(*self.store.letzte_umbenennung)
        self.assertEqual(self.kommentare.exporte()[zufall]["pfad"], "neu/blog")
        self.assertEqual(len(self.kommentare.laden("neu/blog")), 1)


if __name__ == "__main__":
    unittest.main()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name); self.store.anlegen()
        self.assets = Assets(self.store)
        self.kommentare = Kommentare(self.store)
        v = self.store.verzeichnis_anlegen("A")
        self.ziel = self.store.verzeichnis_anlegen("B")
        self.pfad, _ = self.store.seite_anlegen("Quelle", v["id"], "seitenmenue", [])
        self.bild = self.assets.hochladen(self.pfad, "bild.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        seite = self.store.seite_aktualisieren(self.pfad, css=".x { color: red }", bloecke=[
            {"id": "b1", "typ": "text", "html": "<h1>Hallo</h1>"},
            {"id": "b2", "typ": "spalten", "spalten": [[{"id": "b3", "typ": "bild", "asset": self.bild["id"], "bildtext": "B", "breite": "voll"}], [{"id": "b4", "typ": "button", "text": "Los", "ziel": "https://x.ch"}]]}])
        self.assets.referenzen_setzen(self.pfad, seite)
        self.exporter = Exporter(self.store, self.assets, self.kommentare)
        from liloport.importer import Importer
        self.importer = Importer(self.store, self.assets, self.kommentare)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_enthaelt_liloport_json_ohne_zeitstempel(self):
        _, daten, _ = self.exporter.exportieren(self.pfad)
        z = zipfile.ZipFile(io.BytesIO(daten))
        name = [n for n in z.namelist() if n.endswith("liloport.json")][0]
        info = json.loads(z.read(name))
        self.assertEqual(info["titel"], "Quelle")
        self.assertNotIn("erstellt", info); self.assertNotIn("geaendert", info)
        self.assertEqual(len(info["anhaenge"]), 1)
        self.assertIn(name.replace("liloport.json", "") + list(info["anhaenge"].values())[0]["datei"], z.namelist())
        self.assertNotIn("bild.png", json.dumps(info["anhaenge"])[:0] + str([a["datei"] for a in info["anhaenge"].values()]), "zufälliger Dateiname")

    def test_passwort_export_ohne_liloport_json(self):
        _, daten, _ = self.exporter.exportieren(self.pfad, {"passwort": "geheim"})
        self.assertFalse(any(n.endswith("liloport.json") for n in zipfile.ZipFile(io.BytesIO(daten)).namelist()))
        with self.assertRaises(StoreFehler):
            self.importer.vorschau(daten, "x.zip")

    def test_import_rundreise(self):
        _, daten, _ = self.exporter.exportieren(self.pfad)
        # Kommentare so, wie «Herunterladen» sie beilegt
        z_in = zipfile.ZipFile(io.BytesIO(daten)); out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z_out:
            for n in z_in.namelist():
                z_out.writestr(n, z_in.read(n))
            wurzel = z_in.namelist()[0].split("/")[0]
            z_out.writestr(f"{wurzel}/inhalt/comments.json", json.dumps([{"id": "k1", "zeit": "2026-10-25T10:00:00+01:00", "name": "Lea", "text": "<p>Gut!</p>"}]))
        vorschau = self.importer.vorschau(out.getvalue(), "export.zip")
        self.assertEqual((vorschau["titel"], vorschau["bloecke"], vorschau["anhaenge"], vorschau["kommentare"], vorschau["css"]), ("Quelle", 4, 1, 1, True))
        neu = self.importer.importieren(vorschau["token"], self.ziel["id"], "Kopie")
        self.assertEqual(neu, "b/kopie")
        seite = self.store.seite_laden(neu)
        self.assertEqual(seite["menue"], "seitenmenue")
        self.assertEqual(seite["css"], ".x { color: red }")
        self.assertEqual(seite["bloecke"][0]["html"], "<h1>Hallo</h1>")
        neu_asset = seite["bloecke"][1]["spalten"][0][0]["asset"]
        self.assertNotEqual(neu_asset, self.bild["id"])
        reg = self.assets.laden()[neu_asset]
        self.assertEqual((reg["heimat"], reg["referenzen"], reg["name"]), (neu, [neu], "bild.png"))
        self.assertTrue((self.store.root / reg["datei"]).exists())
        self.assertEqual(self.kommentare.laden(neu)[0]["text"], "<p>Gut!</p>")
        self.assertFalse(any(self.importer.ordner.glob("*.zip")), "ZIP nach Import gelöscht")
