"""PDF-Text: Inhaltsströme werden in linearer Zeit gelesen; ein ungewöhnliches PDF kann Liloport nie anhalten."""
import os
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liloport import pdftext  # noqa: E402
from liloport.pdftext import PdfZuAufwendig, _inhalt_lesen, pdf_text, pdf_text_isoliert  # noqa: E402


class _Latin:
    def dekodieren(self, b):
        return b.decode("latin-1")


def _pdf(inhalt: bytes) -> bytes:
    strom = zlib.compress(inhalt)
    objekte = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(strom) + strom + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    teile = [b"%PDF-1.4\n"]
    for i, o in enumerate(objekte, 1):
        teile.append(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    return b"".join(teile) + b"trailer << /Root 1 0 R >>\n%%EOF\n"


class PdfTextTests(unittest.TestCase):
    def test_text_operatoren(self):
        s = (b"BT /F1 12 Tf (Hallo \\(Welt\\)) Tj T* [(Zeit) -50 (schrift) -300 (Bildung)] TJ "
             b"(Ende\\101) ' <4C696C6F> Tj ET")
        self.assertEqual(_inhalt_lesen(s, {}, _Latin()), "Hallo (Welt)\nZeitschrift Bildung\nEndeALilo\n")

    def test_oktal_nur_0_bis_7(self):   # «\9» ist kein Oktal-Escape; früher brach das ganze PDF ab
        self.assertIn("9", _inhalt_lesen(b"(Seite \\9) Tj", {}, _Latin()))

    def test_ungewoehnliche_stroeme_in_linearer_zeit(self):
        faelle = {
            "Array ohne TJ": b"[" + b"(a) <41> 12 " * 20000,
            "viele (": b"[" + b"(" * 50000,
            "viele <": b"[" + b"<" * 50000,
            "Escapes ohne Ende": b"(" + b"\\a" * 50000,
            "gemischt": (b"[(x)(" + b"\\)" * 10 + b"]") * 5000,
            "viele [": b"[" * 200000,
            "Bilddaten": b"BI /W 10 ID " + bytes(range(256)) * 4000 + b" EI (Hallo) Tj",
        }
        for name, strom in faelle.items():
            t = time.monotonic()
            ergebnis = _inhalt_lesen(strom, {}, _Latin())
            self.assertLess(time.monotonic() - t, 2, name)
        self.assertEqual(ergebnis, "Hallo", "eingebettetes Bild übersprungen, Text danach gelesen")

    def test_ganzes_pdf(self):
        self.assertIn("Lebenslanges Lernen", pdf_text(_pdf(b"BT /F1 12 Tf (Lebenslanges Lernen) Tj ET")))

    def test_eigener_prozess(self):
        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "a.pdf"
            datei.write_bytes(_pdf(b"BT /F1 12 Tf (Aus dem Arbeitsprozess) Tj ET"))
            self.assertIn("Aus dem Arbeitsprozess", pdf_text_isoliert(datei))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "braucht eine Named Pipe (Linux/macOS)")
    def test_haengender_prozess_wird_beendet(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = Path(tmp) / "haengt.pdf"
            os.mkfifo(fifo)   # Öffnen blockiert für immer: simuliert ein PDF, das den Prozess anhält
            t = time.monotonic()
            with mock.patch.object(pdftext, "ANLAUF", 3):
                with self.assertRaises(PdfZuAufwendig):
                    pdf_text_isoliert(fifo, sekunden=1)
            self.assertLess(time.monotonic() - t, 15)


if __name__ == "__main__":
    unittest.main()
