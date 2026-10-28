"""Tests für Phase 3: Export, Metadaten-Entfernung, Passwortschutz, Verlauf, Papierkorb, Backup."""
import io
import json
import struct
import sys
import tempfile
import unittest
import time
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liloport import aes  # noqa: E402
from liloport.assets import Assets  # noqa: E402
from liloport.backup import Backup  # noqa: E402
from liloport.export import Exporter, jpeg_bereinigen, png_bereinigen, webp_bereinigen  # noqa: E402
from liloport.history import History, vergleichen  # noqa: E402
from liloport.render import Renderer  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402


def png_mit_text() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"tEXt", b"Author\x00Geheim") + chunk(b"eXIf", b"\x00" * 8)
            + chunk(b"IDAT", zlib.compress(b"\x00\x01\x02\x03")) + chunk(b"IEND", b""))


def jpeg_mit_exif() -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    app1 = b"\xff\xe1" + struct.pack(">H", 24) + b"Exif\x00\x00GEHEIM-GPS-DATEN"
    com = b"\xff\xfe" + struct.pack(">H", 8) + b"Kommen"
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x00" * 6 + b"BILDDATEN\xff\xd9"
    return b"\xff\xd8" + app0 + app1 + com + sos


class MetadatenTests(unittest.TestCase):
    def test_png(self):
        out = png_bereinigen(png_mit_text())
        self.assertNotIn(b"Geheim", out)
        self.assertNotIn(b"eXIf", out)
        self.assertIn(b"IDAT", out)

    def test_jpeg(self):
        out = jpeg_bereinigen(jpeg_mit_exif())
        self.assertNotIn(b"GEHEIM", out)
        self.assertNotIn(b"Kommen", out)
        self.assertIn(b"JFIF", out)
        self.assertTrue(out.endswith(b"BILDDATEN\xff\xd9"))

    def test_webp(self):
        vp8 = b"VP8 " + struct.pack("<I", 4) + b"abcd"
        exif = b"EXIF" + struct.pack("<I", 6) + b"GEHEIM"
        daten = b"RIFF" + struct.pack("<I", 4 + len(vp8) + len(exif)) + b"WEBP" + vp8 + exif
        out = webp_bereinigen(daten)
        self.assertNotIn(b"GEHEIM", out)
        self.assertIn(b"VP8 ", out)
        self.assertEqual(struct.unpack("<I", out[4:8])[0], len(out) - 8)


class AesTests(unittest.TestCase):
    def test_nist_vektor(self):
        out = aes.gcm_verschluesseln(b"\0" * 32, b"\0" * 12, b"\0" * 16)
        self.assertEqual(out.hex(), "cea7403d4d606b6e074ec5d3baf39d18d0d1c8a799996bf0265b98b5d48ab919")

    def test_passwort_ableitung_deterministisch(self):
        self.assertEqual(aes.schluessel_aus_passwort("x", b"s" * 16, 1000), aes.schluessel_aus_passwort("x", b"s" * 16, 1000))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.assets = Assets(self.store)
        v = self.store.verzeichnis_anlegen("A")
        self.pfad, _ = self.store.seite_anlegen("Meine Seite", v["id"])
        self.p2, _ = self.store.seite_anlegen("Andere", v["id"])
        self.bild = self.assets.hochladen(self.pfad, "foto.png", png_mit_text())
        self.fremd = self.assets.hochladen(self.p2, "fremd.png", png_mit_text())
        seite = self.store.seite_aktualisieren(self.pfad, css=".x { color: red }", bloecke=[
            {"id": "b1", "typ": "text", "html": "<p>Hallo</p>"},
            {"id": "b2", "typ": "bild", "asset": self.bild["id"], "bildtext": "Foto", "breite": "voll"}])
        self.assets.referenzen_setzen(self.pfad, seite)
        self.exporter = Exporter(self.store, self.assets)

    def tearDown(self):
        self.tmp.cleanup()

    def _zip(self, optionen=None):
        name, daten, zufall = self.exporter.exportieren(self.pfad, optionen)
        return name, zipfile.ZipFile(io.BytesIO(daten)), zufall

    def test_zip_inhalt(self):
        name, z, zufall = self._zip()
        namen = z.namelist()
        ordner = namen[0].split("/")[0]
        self.assertTrue(name.endswith(".zip") and ordner.startswith("export-meine-seite-"))
        self.assertEqual(len(zufall), 32)
        self.assertIn(f"{ordner}/inhalt/{zufall}.html", namen)
        self.assertIn(f"{ordner}/inhalt/robots.txt", namen)
        self.assertIn(f"{ordner}/inhalt/style.css", namen)
        self.assertIn(f"{ordner}/inhalt/LIESMICH.txt", namen)
        self.assertIn(f"{ordner}/Seite öffnen.html", namen)
        self.assertEqual(len([n for n in namen if n.count("/") == 1]), 1, "oben nur die Startdatei")
        self.assertIn(f"{ordner}/inhalt/dateien.html", namen)
        self.assertFalse([n for n in namen if n.lower().endswith(".js")], "keine .js-Dateien (Windows blockiert sie beim Entpacken)")
        self.assertNotIn("LILOPORT-SEITE-OEFFNEN", " ".join(namen))
        assets = [n for n in namen if "/assets/" in n]
        self.assertEqual(len(assets), 1, "nur das referenzierte Bild, nicht das fremde")
        self.assertNotIn("foto", assets[0], "Dateiname ist zufällig")
        self.assertNotIn(b"Geheim", z.read(assets[0]), "EXIF/Text entfernt")
        html = z.read(f"{ordner}/inhalt/{zufall}.html").decode()
        self.assertIn('name="robots" content="noindex', html)
        self.assertNotIn("menu.js", html)
        self.assertNotIn("reader.js", html)
        self.assertNotIn("class=\"kopf\"", html)
        self.assertNotIn("<time", html)
        self.assertIn(".seite-meine-seite .x", html)
        self.assertIn('src="' + assets[0].split("/inhalt/", 1)[1], html)
        self.assertEqual(z.getinfo(f"{ordner}/inhalt/robots.txt").date_time, (1980, 1, 1, 0, 0, 0))

    def test_datum_und_autor_nur_auf_wunsch(self):
        site = self.store.site_laden()
        site["export"]["autor"] = "Anna Muster"
        self.store.site_speichern(site)
        _, z, zufall = self._zip({"autorAnzeigen": True, "datumAnzeigen": True})
        html = [z.read(n).decode() for n in z.namelist() if n.endswith(".html") and "/inhalt/" in n and not n.endswith("dateien.html")][0]
        self.assertIn("Anna Muster", html)
        self.assertIn("<time datetime=", html)
        _, z2, _ = self._zip({})
        html2 = [z2.read(n).decode() for n in z2.namelist() if n.endswith(".html") and "/inhalt/" in n and not n.endswith("dateien.html")][0]
        self.assertNotIn("Anna Muster", html2)

    def test_passwort_verschluesselt(self):
        _, z, _ = self._zip({"passwort": "geheim123"})
        html = [z.read(n).decode() for n in z.namelist() if n.endswith(".html") and "/inhalt/" in n and not n.endswith("dateien.html")][0]
        self.assertNotIn("Hallo", html)
        self.assertNotIn("Meine Seite</title>", html)
        self.assertIn("PBKDF2", html)
        self.assertIn('"iterationen": 310000', html)
        self.assertIn("crypto.subtle.decrypt", html)


class VerlaufTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.history = History(self.store)
        self.v = self.store.verzeichnis_anlegen("A")
        self.pfad, _ = self.store.seite_anlegen("S", self.v["id"], "voll", [{"id": "b1", "typ": "text", "html": "<p>v1</p>"}])

    def tearDown(self):
        self.tmp.cleanup()

    def _aendern(self, html):
        self.history.sichern(self.pfad, self.store.seite_laden(self.pfad))
        return self.store.seite_aktualisieren(self.pfad, bloecke=[{"id": "b1", "typ": "text", "html": html}, {"id": "b2", "typ": "trenner"}])

    def test_versionen_und_wiederherstellen(self):
        self._aendern("<p>v2</p>")
        self.history.sichern(self.pfad, self.store.seite_laden(self.pfad))
        self.history.sichern(self.pfad, self.store.seite_laden(self.pfad))  # identisch -> keine neue Version
        versionen = self.history.versionen(self.pfad)
        self.assertEqual(len(versionen), 2)
        self.assertEqual(versionen[0]["geaendert"], 0)  # neueste = aktuelle Fassung
        self.assertEqual(versionen[1]["diff"]["geaendert"], ["b1"])
        self.assertEqual(versionen[1]["diff"]["entfernt"], [])
        self.assertEqual(versionen[1]["geaendert"], 2)  # b1 geändert + b2 neu
        self.history.wiederherstellen(self.pfad, versionen[1]["id"])
        aktuell = self.store.seite_laden(self.pfad)
        self.assertEqual(aktuell["bloecke"][0]["html"], "<p>v1</p>")
        self.assertEqual(len(self.history.versionen(self.pfad)), 2, "v2 war schon gesichert, nichts doppelt")

    def test_vergleichen(self):
        d = vergleichen({"bloecke": [{"id": "a", "typ": "text", "html": "x"}], "titel": "T"},
                        {"bloecke": [{"id": "a", "typ": "text", "html": "y"}, {"id": "b", "typ": "trenner"}], "titel": "T2"})
        self.assertEqual((d["geaendert"], d["neu"], d["entfernt"], d["titel"]), (["a"], ["b"], [], True))

    def test_papierkorb(self):
        self._aendern("<p>v2</p>")
        self.history.in_papierkorb(self.pfad, self.v["id"])
        self.store.seite_loeschen(self.pfad)
        korb = self.history.papierkorb()
        self.assertEqual(korb[0]["titel"], "S")
        neu = self.history.aus_papierkorb(korb[0]["id"])
        self.assertEqual(neu, "a/s")
        self.assertEqual(self.store.seite_laden(neu)["bloecke"][0]["html"], "<p>v2</p>")
        self.assertEqual(len(self.history.versionen(neu)), 1, "Versionen kamen mit zurück")
        self.assertEqual(self.history.papierkorb(), [])

    def test_papierkorb_ohne_verzeichnis(self):
        self.history.in_papierkorb(self.pfad, self.v["id"])
        self.store.seite_loeschen(self.pfad)
        self.store.verzeichnis_loeschen(self.v["id"])
        w = self.store.verzeichnis_anlegen("W")
        neu = self.history.aus_papierkorb(self.history.papierkorb()[0]["id"])
        self.assertEqual(neu, "w/s")
        self.assertEqual(w["id"], "d1")

    def test_papierkorb_nimmt_anhaenge_mit(self):
        from liloport.assets import Assets
        assets = Assets(self.store)
        pdf = assets.hochladen(self.pfad, "skript.pdf", b"%PDF-1.4\n%%EOF\n")
        seite = self.store.seite_aktualisieren(self.pfad, bloecke=[{"id": "b1", "typ": "pdf", "asset": pdf["id"]}])
        assets.referenzen_setzen(self.pfad, seite)
        self.history.in_papierkorb(self.pfad, self.v["id"], assets)
        assets.seite_loeschen(self.pfad)
        self.assertNotIn(pdf["id"], assets.laden())
        self.assertFalse((self.store.root / "assets/s/skript.pdf").exists())
        korb = self.history.papierkorb()
        self.assertEqual(korb[0]["anhaenge"], 1)
        neu = self.history.aus_papierkorb(korb[0]["id"], assets)
        reg = assets.laden()
        self.assertIn(pdf["id"], reg)
        self.assertEqual(reg[pdf["id"]]["datei"], "assets/s/skript.pdf")
        self.assertEqual(reg[pdf["id"]]["referenzen"], [neu])
        self.assertTrue((self.store.root / "assets/s/skript.pdf").exists())
        self.assertFalse(any(self.history.papierkorb_ordner.glob("*.anhaenge")), "Ablage aufgeräumt")

    def test_endgueltig(self):
        self.history.in_papierkorb(self.pfad, self.v["id"])
        self.history.endgueltig(self.history.papierkorb()[0]["id"])
        self.assertEqual(self.history.papierkorb(), [])


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "inhalte")
        self.store.anlegen()
        self.backup = Backup(self.store)
        # Schwelle zwischen den Programmdateien in _wiki (bis ~100 KB) und den Test-«Videos» (600 KB)
        import liloport.backup as b
        self._gross = b.GROSS
        b.GROSS = 500_000
        v = self.store.verzeichnis_anlegen("A")
        self.store.seite_anlegen("S", v["id"])
        Renderer(self.store).alles_schreiben()

    def tearDown(self):
        import liloport.backup as b
        b.GROSS = self._gross
        self.tmp.cleanup()

    def test_erstellen_und_status(self):
        self.assertTrue(self.backup.status()["warnung"])
        e = self.backup.erstellen()
        with zipfile.ZipFile(self.store.root / "_wiki/backups" / e["name"]) as z:
            self.assertIn("a/s.json", z.namelist())
            self.assertIn("site.json", z.namelist())
            self.assertFalse(any("_wiki/backups" in n for n in z.namelist()))
        status = self.backup.status()
        self.assertFalse(status["warnung"])
        self.assertEqual(status["anzahl"], 1)
        self.assertFalse(self.backup.taeglich()["erstellt"], "heute schon eines")

    def test_wiederherstellen_nur_in_leeren_ordner(self):
        e = self.backup.erstellen()
        ziel = Path(self.tmp.name) / "neu"
        self.backup.wiederherstellen(e["name"], str(ziel))
        self.assertTrue((ziel / "a/s.json").exists())
        with self.assertRaises(StoreFehler):
            self.backup.wiederherstellen(e["name"], str(ziel))
        with self.assertRaises(StoreFehler):
            self.backup.wiederherstellen(e["name"], str(self.store.root))

    def _grosse_datei(self, name="film.mp4", groesse=600_000, inhalt=b"x"):
        datei = self.store.root / "assets" / name
        datei.parent.mkdir(exist_ok=True)
        datei.write_bytes((inhalt * groesse)[:groesse])
        return datei

    def test_grosse_dateien_nur_einmal_gespeichert(self):
        import liloport.backup as b
        film = self._grosse_datei()
        e1 = self.backup.erstellen()
        speicher = list((self.store.root / "_wiki/backups/dateien").glob("*/*.dat"))
        self.assertEqual(len(speicher), 1, "grosse Datei im gemeinsamen Speicher")
        with zipfile.ZipFile(self.store.root / "_wiki/backups" / e1["name"]) as z:
            self.assertNotIn("assets/film.mp4", z.namelist(), "nicht im ZIP selbst")
            self.assertIn(b.MANIFEST, z.namelist())
        mtime = film.stat().st_mtime_ns
        e2 = self.backup.erstellen()
        self.assertEqual(len(list((self.store.root / "_wiki/backups/dateien").glob("*/*.dat"))), 1, "nicht doppelt")
        self.assertEqual(film.stat().st_mtime_ns, mtime)
        # Wiederherstellen setzt die grosse Datei wieder zusammen
        ziel = Path(self.tmp.name) / "zurueck"
        self.backup.wiederherstellen(e2["name"], str(ziel))
        self.assertEqual((ziel / "assets/film.mp4").read_bytes(), film.read_bytes())
        self.assertTrue((ziel / "a/s.json").exists())
        self.assertEqual(self.backup.status()["backups"][0]["groesse"], e2["groesse"])

    def test_aufraeumen_loescht_nicht_mehr_gebrauchte_dateien(self):
        import liloport.backup as b
        alt = b.MAX_BACKUPS
        b.MAX_BACKUPS = 2
        try:
            film = self._grosse_datei(inhalt=b"a")
            self.backup.erstellen()
            film.unlink()
            self._grosse_datei("neu.mp4", inhalt=b"b")
            self.backup.erstellen()
            self.assertEqual(len(list((self.store.root / "_wiki/backups/dateien").glob("*/*.dat"))), 2)
            self.backup.erstellen()   # das erste Backup fällt weg, damit auch film.mp4
            self.assertEqual(len(list((self.store.root / "_wiki/backups/dateien").glob("*/*.dat"))), 1)
            self.assertEqual(len(self.backup.liste()), 2)
        finally:
            b.MAX_BACKUPS = alt

    def test_zu_wenig_platz(self):
        import liloport.backup as b
        alt = b.RESERVE_MIN
        b.RESERVE_MIN = 10 ** 18   # mehr als jedes Laufwerk
        try:
            with self.assertRaises(StoreFehler) as f:
                self.backup.erstellen()
            self.assertIn("Zu wenig Speicherplatz", str(f.exception))
            self.assertEqual(self.backup.liste(), [])
            status = self.backup.status()
            self.assertTrue(status["warnung"])
            self.assertIn("Zu wenig Speicherplatz", status["meldung"])
        finally:
            b.RESERVE_MIN = alt
        self.backup.erstellen()
        self.assertIsNone(self.backup.status()["meldung"], "Meldung verschwindet nach gelungenem Backup")

    def test_eigener_backup_ordner(self):
        extern = Path(self.tmp.name) / "festplatte" / "Liloport-Backups"
        with self.assertRaises(StoreFehler):
            self.backup.ort_setzen(str(self.store.root / "unter"))
        with self.assertRaises(StoreFehler):
            self.backup.ort_setzen("relativ/pfad")
        extern = Path(self.backup.ort_setzen(str(extern))["ordner"])
        self.assertIn("Liloport-Backups", str(extern))
        self._grosse_datei()
        e = self.backup.erstellen()
        self.assertTrue((extern / e["name"]).exists())
        self.assertFalse((self.store.root / "_wiki/backups" / e["name"]).exists())
        self.assertEqual(len(list((extern / "dateien").glob("*/*.dat"))), 1)
        self.assertFalse(self.backup.status()["standard"])
        # Festplatte abgezogen: klare Meldung statt stillem Fehler
        import shutil as sh
        sh.rmtree(extern)
        self.assertFalse(self.backup.status()["erreichbar"])
        with self.assertRaises(StoreFehler):
            self.backup.erstellen()
        self.backup.ort_setzen("")
        self.assertTrue(self.backup.status()["standard"])
        # Ordner mit fremden Dateien: Liloport legt einen eigenen Unterordner an
        laufwerk = Path(self.tmp.name) / "laufwerk"
        laufwerk.mkdir()
        (laufwerk / "steuern.pdf").write_bytes(b"x")
        status = self.backup.ort_setzen(str(laufwerk))
        eigener = Path(status["ordner"])
        self.assertEqual(eigener.parent, (laufwerk / "Liloport-Backups").resolve())
        self.backup.erstellen()
        self.assertEqual(sorted(p.name for p in laufwerk.iterdir()), ["Liloport-Backups", "steuern.pdf"])
        status = self.backup.ort_setzen(str(eigener))   # schon der eigene Backup-Ordner: bleibt
        self.assertEqual(Path(status["ordner"]), eigener)
        # Zweites Portfolio am selben Ort: bekommt einen eigenen Unterordner, sieht die fremden Backups nicht
        store2 = Store(Path(self.tmp.name) / "zweites")
        store2.anlegen()
        b2 = Backup(store2)
        ordner2 = Path(b2.ort_setzen(str(laufwerk))["ordner"])
        self.assertNotEqual(ordner2, eigener)
        self.assertEqual(b2.liste(), [])
        self.assertTrue(b2.taeglich()["erstellt"])
        self.assertEqual(len(self.backup.liste()), 1, "Backups des ersten bleiben unberührt")
        # Ordner eines anderen Portfolios direkt gewählt: kein Backup, klare Meldung
        (Path(self.tmp.name) / "zweites/_wiki/backup-ort.json").write_text(
            json.dumps({"ordner": str(eigener)}), encoding="utf-8")
        with self.assertRaises(StoreFehler) as f:
            b2.erstellen()
        self.assertIn("anderen", str(f.exception))

    def test_kopie_bekommt_eigene_kennung_und_keinen_fremden_ort(self):
        extern = Path(self.tmp.name) / "platte"
        self.backup.ort_setzen(str(extern))
        e = self.backup.erstellen()
        ziel = Path(self.tmp.name) / "kopie"
        self.backup.wiederherstellen(e["name"], str(ziel))
        self.assertFalse((ziel / "_wiki/backup-ort.json").exists())
        self.assertFalse((ziel / "_wiki/portfolio-id.json").exists())
        with self.assertRaises(StoreFehler):
            self.backup.wiederherstellen(e["name"], "relativ")

    def test_kleine_datei_mit_lesefehler_fehlt_ganz(self):
        from unittest import mock
        (self.store.root / "a" / "notiz.json").write_text("{}")
        echt = Path.read_bytes

        def lesen(pfad):
            if pfad.name == "notiz.json":
                raise PermissionError(13, "gesperrt")
            return echt(pfad)
        with mock.patch.object(Path, "read_bytes", lesen):
            e = self.backup.erstellen()
        self.assertTrue(any("notiz.json" in u for u in e["uebersprungen"]))
        with zipfile.ZipFile(self.store.root / "_wiki/backups" / e["name"]) as z:
            self.assertNotIn("a/notiz.json", z.namelist())

    def test_beschaedigte_datei_im_speicher_wird_erkannt_und_ersetzt(self):
        film = self._grosse_datei(inhalt=b"q")
        e = self.backup.erstellen()
        dat = next((self.store.root / "_wiki/backups/dateien").glob("*/*.dat"))
        dat.write_bytes(b"kaputt")   # z. B. Stick abgezogen
        ziel = Path(self.tmp.name) / "w1"
        self.backup.wiederherstellen(e["name"], str(ziel))
        self.assertFalse((ziel / "assets/film.mp4").exists(), "nicht stillschweigend falsch")
        self.assertTrue(any("beschädigt" in f for f in self.backup.status()["zuletzt"]["fehlend"]))
        self.backup.erstellen()   # nächstes Backup ersetzt die beschädigte Kopie
        self.assertEqual(dat.read_bytes(), film.read_bytes())

    def test_sperre_eines_anderen_liloport(self):
        ordner = self.store.root / "_wiki/backups"
        ordner.mkdir(parents=True)
        (ordner / ".sperre").write_text("{}")
        with self.assertRaises(StoreFehler) as f:
            self.backup.erstellen()
        self.assertIn("anderes Liloport", str(f.exception))
        import os as _os
        alt = time.time() - 3600
        _os.utime(ordner / ".sperre", (alt, alt))   # abgestürzt: alte Sperre wird übernommen
        self.backup.erstellen()
        self.assertFalse((ordner / ".sperre").exists())

    def test_im_hintergrund(self):
        self._grosse_datei()
        self.backup.erstellen_hintergrund()
        self.assertTrue(self.backup.warten(30))
        status = self.backup.status()
        self.assertEqual(status["anzahl"], 1)
        self.assertIsNone(status["laeuft"])
        self.assertTrue(status["zuletzt"]["ok"])
        self.assertFalse(self.backup.taeglich_hintergrund(), "heute schon eines")

    def test_altes_vollstaendiges_backup_wiederherstellen(self):
        ordner = self.store.root / "_wiki/backups"
        ordner.mkdir(parents=True)
        with zipfile.ZipFile(ordner / "2026-01-02_030405.zip", "w") as z:
            z.writestr("site.json", "{}")
            z.writestr("assets/film.mp4", b"x" * 1000)
        self.assertEqual(self.backup.liste()[0]["art"], "vollständig")
        ziel = Path(self.tmp.name) / "alt"
        self.backup.wiederherstellen("2026-01-02_030405.zip", str(ziel))
        self.assertEqual((ziel / "assets/film.mp4").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
