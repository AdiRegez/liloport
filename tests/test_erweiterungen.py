"""Tests für die Erweiterungen 0.10: Audio, Galerie, Trenner-Stile, Verzeichnis verschieben,
Import auf oberster Ebene, Fusszeile mit target=_blank."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liloport.assets import Assets, typ_erkennen  # noqa: E402
from liloport.render import BlockRenderer, Renderer, produktfuss_html, trenner_stil  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402
from server import bloecke_pruefen  # noqa: E402

MP3_ID3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 32
MP3_ROH = b"\xff\xfb\x90\x00" + b"\x00" * 32
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
OGG = b"OggS" + b"\x00" * 32
FLAC = b"fLaC" + b"\x00" * 32
M4A = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


class AudioTypTests(unittest.TestCase):
    def test_audio_formate(self):
        self.assertEqual(typ_erkennen(MP3_ID3), ("audio", "mp3"))
        self.assertEqual(typ_erkennen(MP3_ROH), ("audio", "mp3"))
        self.assertEqual(typ_erkennen(WAV), ("audio", "wav"))
        self.assertEqual(typ_erkennen(OGG), ("audio", "ogg"))
        self.assertEqual(typ_erkennen(FLAC), ("audio", "flac"))
        self.assertEqual(typ_erkennen(M4A), ("audio", "m4a"))

    def test_mp4_bleibt_video(self):
        self.assertEqual(typ_erkennen(MP4), ("video", "mp4"))


class BloeckePruefenTests(unittest.TestCase):
    def test_audio_block(self):
        bloecke = bloecke_pruefen([{"id": "b1", "typ": "audio", "asset": "0a1b2c3d"}])
        self.assertEqual(bloecke[0], {"id": "b1", "typ": "audio", "asset": "0a1b2c3d"})

    def test_galerie_block(self):
        bloecke = bloecke_pruefen([{"id": "b1", "typ": "galerie", "spalten": 4,
                                    "bilder": [{"asset": "0a1b2c3d", "bildtext": "x" * 400}, "quatsch"]}])
        self.assertEqual(bloecke[0]["spalten"], 4)
        self.assertEqual(len(bloecke[0]["bilder"]), 1)
        self.assertEqual(len(bloecke[0]["bilder"][0]["bildtext"]), 300)

    def test_galerie_ungueltige_asset_id(self):
        with self.assertRaises(StoreFehler):
            bloecke_pruefen([{"id": "b1", "typ": "galerie", "bilder": [{"asset": "../../x"}]}])

    def test_trenner_eigenschaften(self):
        b = bloecke_pruefen([{"id": "b1", "typ": "trenner", "farbe": "#AB12cd", "dicke": 4,
                              "stil": "gestrichelt", "abstandOben": 0, "abstandUnten": 80}])[0]
        self.assertEqual(b, {"id": "b1", "typ": "trenner", "farbe": "#ab12cd", "dicke": 4,
                             "stil": "gestrichelt", "abstandOben": 0, "abstandUnten": 80})

    def test_trenner_ungueltiges_wird_verworfen(self):
        b = bloecke_pruefen([{"id": "b1", "typ": "trenner", "farbe": "red\" onload=\"x",
                              "dicke": 999, "stil": "zackig", "abstandOben": -5, "abstandUnten": "zehn"}])[0]
        self.assertEqual(b, {"id": "b1", "typ": "trenner"})


class RenderTests(unittest.TestCase):
    def test_trenner_stil(self):
        self.assertEqual(trenner_stil({}), "")
        self.assertIn("border-top:4px dashed #ab12cd", trenner_stil({"farbe": "#ab12cd", "dicke": 4, "stil": "gestrichelt"}))
        self.assertIn("margin-top:0px", trenner_stil({"abstandOben": 0}))
        self.assertIn("margin-bottom:80px", trenner_stil({"abstandUnten": 80}))
        # Doppellinie braucht mindestens 3 Pixel
        self.assertIn("border-top:3px double", trenner_stil({"stil": "doppelt"}))
        # Ungültige Werte erzeugen keinen Stil (defensiv, z. B. bei Importen)
        self.assertEqual(trenner_stil({"farbe": "x\" onload=\"", "dicke": "viel", "abstandOben": 9999}), "")

    def test_audio_und_galerie_html(self):
        registry = {"0a1b2c3d": {"datei": "assets/s/ton.mp3", "name": "Ton.mp3", "typ": "audio"},
                    "0a1b2c3e": {"datei": "assets/s/bild.png", "name": "Bild.png", "typ": "bild"}}
        br = BlockRenderer(registry, "")
        audio = br.block({"id": "a1", "typ": "audio", "asset": "0a1b2c3d"})
        self.assertIn("<audio controls", audio)
        self.assertIn("assets/s/ton.mp3", audio)
        galerie = br.block({"id": "g1", "typ": "galerie", "spalten": 2,
                            "bilder": [{"asset": "0a1b2c3e", "bildtext": "Eins"}, {"asset": "fehlt000"}]})
        self.assertIn("galerie-2", galerie)
        self.assertIn("assets/s/bild.png", galerie)
        self.assertIn("<figcaption>Eins</figcaption>", galerie)

    def test_fusszeile_links_neuer_tab(self):
        fuss = produktfuss_html("")
        self.assertIn('target="_blank"', fuss)
        # jeder Link der Fusszeile öffnet in einem neuen Tab
        self.assertEqual(fuss.count("<a "), fuss.count('target="_blank"'))


class AssetsReferenzTests(unittest.TestCase):
    def test_ids_in_bloecken_mit_audio_und_galerie(self):
        ids = Assets.ids_in_bloecken([
            {"typ": "audio", "asset": "aaaaaaaa"},
            {"typ": "galerie", "bilder": [{"asset": "bbbbbbbb"}, {"asset": ""}]},
            {"typ": "spalten", "spalten": [[{"typ": "galerie", "bilder": [{"asset": "cccccccc"}]}], []]},
        ])
        self.assertEqual(ids, {"aaaaaaaa", "bbbbbbbb", "cccccccc"})


class VerzeichnisVerschiebenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.renderer = Renderer(self.store)
        self.a = self.store.verzeichnis_anlegen("Alpha")
        self.b = self.store.verzeichnis_anlegen("Beta")
        self.unter = self.store.verzeichnis_anlegen("Unter", self.a["id"])
        self.pfad, _ = self.store.seite_anlegen("Seite", self.unter["id"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_unterverzeichnis_auf_oberste_ebene(self):
        v = self.store.verzeichnis_verschieben(self.unter["id"], None)
        self.assertIsNone(v["eltern"])
        self.assertEqual(v["ordner"], "unter")
        self.assertTrue((Path(self.tmp.name) / "unter" / "seite.json").exists())
        self.assertFalse((Path(self.tmp.name) / "alpha" / "unter").exists())
        self.assertEqual(self.store.letzte_umbenennung, ("alpha/unter", "unter"))
        self.assertEqual(self.store.seite_laden("unter/seite")["titel"], "Seite")

    def test_in_anderes_verzeichnis(self):
        v = self.store.verzeichnis_verschieben(self.unter["id"], self.b["id"])
        self.assertEqual(v["eltern"], self.b["id"])
        self.assertEqual(v["ordner"], "beta/unter")
        self.assertTrue((Path(self.tmp.name) / "beta" / "unter" / "seite.json").exists())

    def test_mit_unterverzeichnissen(self):
        tief = self.store.verzeichnis_anlegen("Tief", self.unter["id"])
        self.store.seite_anlegen("Tiefe Seite", tief["id"])
        self.store.verzeichnis_verschieben(self.a["id"], self.b["id"])
        site = self.store.site_laden()
        ordner = {v["id"]: v["ordner"] for v in site["verzeichnisse"]}
        self.assertEqual(ordner[self.a["id"]], "beta/alpha")
        self.assertEqual(ordner[self.unter["id"]], "beta/alpha/unter")
        self.assertEqual(ordner[tief["id"]], "beta/alpha/unter/tief")
        self.assertTrue((Path(self.tmp.name) / "beta" / "alpha" / "unter" / "tief" / "tiefe-seite.json").exists())

    def test_nicht_in_sich_selbst_oder_nachkommen(self):
        with self.assertRaises(StoreFehler):
            self.store.verzeichnis_verschieben(self.a["id"], self.a["id"])
        with self.assertRaises(StoreFehler):
            self.store.verzeichnis_verschieben(self.a["id"], self.unter["id"])

    def test_bereits_dort(self):
        with self.assertRaises(StoreFehler):
            self.store.verzeichnis_verschieben(self.b["id"], None)
        with self.assertRaises(StoreFehler):
            self.store.verzeichnis_verschieben(self.unter["id"], self.a["id"])

    def test_namenskonflikt_bekommt_neuen_slug(self):
        self.store.verzeichnis_anlegen("Unter", self.b["id"])   # gleicher Slug am Ziel
        v = self.store.verzeichnis_verschieben(self.unter["id"], self.b["id"])
        self.assertEqual(v["ordner"], "beta/unter-2")


class ImportObersteEbeneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.assets = Assets(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _export_zip(self):
        """Exportiert ein kleines Verzeichnis mit Unterverzeichnis als ZIP (in Bytes)."""
        import io
        from liloport.export import Exporter
        from liloport.kommentare import Kommentare
        v = self.store.verzeichnis_anlegen("Semester")
        unter = self.store.verzeichnis_anlegen("Projekte", v["id"])
        self.store.seite_anlegen("Journal", v["id"], bloecke=[{"id": "b1", "typ": "text", "html": "<p>Hallo</p>"}])
        self.store.seite_anlegen("Projekt A", unter["id"], bloecke=[{"id": "b1", "typ": "trenner", "farbe": "#112233"}])
        exporter = Exporter(self.store, self.assets, Kommentare(self.store))
        _name, daten, _start = exporter.exportieren_mehrere(v["id"], {"kommentare": False})
        return io.BytesIO(daten).getvalue() if not isinstance(daten, (bytes, bytearray)) else daten

    def test_verzeichnis_export_auf_oberster_ebene_importieren(self):
        from liloport.importer import Importer
        from liloport.kommentare import Kommentare
        zip_daten = self._export_zip()
        importer = Importer(self.store, self.assets, Kommentare(self.store))
        vorschau = importer.vorschau(zip_daten, "export-semester.zip")
        self.assertEqual(vorschau["seiten"], 2)
        pfad = importer.importieren(vorschau["token"], "", None)
        site = self.store.site_laden()
        namen = {v["name"]: v for v in site["verzeichnisse"]}
        self.assertIn("Semester", namen)           # neues Verzeichnis auf oberster Ebene
        self.assertIsNone(namen["Semester"].get("eltern"))
        self.assertIn("Projekte", namen)           # Unterverzeichnis nachgebildet
        self.assertEqual(namen["Projekte"]["eltern"], namen["Semester"]["id"])
        seite = self.store.seite_laden(pfad)
        self.assertEqual(seite["titel"], "Journal")
        # Trenner-Eigenschaften überleben den Export und Import
        projekt = self.store.seite_laden(namen["Projekte"]["ordner"] + "/projekt-a")
        self.assertEqual(projekt["bloecke"][0].get("farbe"), "#112233")


class AbgleichTests(unittest.TestCase):
    """Von Hand (im Dateimanager) gemachte Änderungen am Inhalte-Ordner erkennen und übernehmen."""

    def setUp(self):
        import shutil
        self.shutil = shutil
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.store.anlegen()
        self.assets = Assets(self.store)
        self.a = self.store.verzeichnis_anlegen("Alpha")
        self.unter = self.store.verzeichnis_anlegen("Unter", self.a["id"])
        self.b = self.store.verzeichnis_anlegen("Beta")
        self.store.seite_anlegen("Eins", self.a["id"])
        self.store.seite_anlegen("Zwei", self.unter["id"])
        self.store.seite_anlegen("Drei", self.b["id"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_bericht_ohne_unterschiede(self):
        from liloport import abgleich
        self.assertEqual(abgleich.bericht(self.store)["anzahl"], 0)

    def test_geloeschter_ordner_wird_erkannt_und_entfernt(self):
        from liloport import abgleich
        self.shutil.rmtree(Path(self.tmp.name) / "alpha")   # von Hand gelöscht (samt Unterordner)
        bericht = abgleich.bericht(self.store)
        self.assertEqual({e["ordner"] for e in bericht["verzeichnisseFehlen"]}, {"alpha", "alpha/unter"})
        ergebnis = abgleich.anwenden(self.store, self.assets)
        self.assertEqual(ergebnis["entfernteVerzeichnisse"], 2)
        site = self.store.site_laden()
        self.assertEqual({v["name"] for v in site["verzeichnisse"]}, {"Beta"})
        self.assertEqual(abgleich.bericht(self.store)["anzahl"], 0)

    def test_geloeschte_seite_wird_ausgetragen(self):
        from liloport import abgleich
        (Path(self.tmp.name) / "beta" / "drei.json").unlink()
        bericht = abgleich.bericht(self.store)
        self.assertEqual(bericht["seitenFehlen"], [{"verzeichnis": "Beta", "ordner": "beta", "slug": "drei"}])
        abgleich.anwenden(self.store, self.assets)
        self.assertEqual(self.store.verzeichnis(self.store.site_laden(), self.b["id"])["seiten"], [])

    def test_von_hand_verschobene_seite(self):
        from liloport import abgleich
        # Seite im Dateimanager von Beta nach Alpha verschoben
        (Path(self.tmp.name) / "beta" / "drei.json").rename(Path(self.tmp.name) / "alpha" / "drei.json")
        bericht = abgleich.bericht(self.store)
        self.assertEqual(len(bericht["seitenFehlen"]), 1)
        self.assertEqual(bericht["seitenNeu"], [{"verzeichnis": "Alpha", "ordner": "alpha", "slug": "drei", "titel": "Drei"}])
        abgleich.anwenden(self.store, self.assets)
        site = self.store.site_laden()
        self.assertIn("drei", self.store.verzeichnis(site, self.a["id"])["seiten"])
        self.assertNotIn("drei", self.store.verzeichnis(site, self.b["id"])["seiten"])
        self.assertEqual(self.store.seite_laden("alpha/drei")["titel"], "Drei")

    def test_neuer_ordner_mit_seiten_wird_aufgenommen(self):
        import json as jsonlib
        from liloport import abgleich
        neu = Path(self.tmp.name) / "neuer-ordner" / "tiefer"
        neu.mkdir(parents=True)
        (neu.parent / "seite-x.json").write_text(jsonlib.dumps({"titel": "Seite X", "bloecke": []}), encoding="utf-8")
        (neu / "seite-y.json").write_text(jsonlib.dumps({"titel": "Seite Y", "bloecke": []}), encoding="utf-8")
        bericht = abgleich.bericht(self.store)
        self.assertEqual(bericht["ordnerNeu"], [{"ordner": "neuer-ordner", "seiten": 2}])
        ergebnis = abgleich.anwenden(self.store, self.assets)
        self.assertEqual(ergebnis["neueVerzeichnisse"], 2)
        self.assertEqual(ergebnis["neueSeiten"], 2)
        site = self.store.site_laden()
        namen = {v["name"]: v for v in site["verzeichnisse"]}
        self.assertIn("neuer-ordner", namen)
        self.assertEqual(namen["tiefer"]["eltern"], namen["neuer-ordner"]["id"])
        self.assertEqual(self.store.seite_laden("neuer-ordner/seite-x")["slug"], "seite-x")

    def test_redirect_auf_geloeschte_seite_wird_entfernt(self):
        from liloport import abgleich
        self.store.redirect_hinzufuegen(self.b["id"], "alpha/eins")
        self.shutil.rmtree(Path(self.tmp.name) / "alpha")
        abgleich.anwenden(self.store, self.assets)
        self.assertEqual(self.store.verzeichnis(self.store.site_laden(), self.b["id"])["seiten"], ["drei"])

    def test_anhang_referenzen_werden_bereinigt(self):
        from liloport import abgleich
        PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        eintrag = self.assets.hochladen("beta/drei", "bild.png", PNG)
        seite = self.store.seite_aktualisieren("beta/drei", bloecke=[{"id": "b1", "typ": "bild", "asset": eintrag["id"],
                                                                     "bildtext": "", "breite": "voll", "ausrichtung": "links"}])
        self.assets.referenzen_setzen("beta/drei", seite)
        (Path(self.tmp.name) / "beta" / "drei.json").unlink()
        abgleich.anwenden(self.store, self.assets)
        self.assertEqual(self.assets.laden()[eintrag["id"]]["referenzen"], [])
        self.assertEqual([e["id"] for e in self.assets.verwaist()], [eintrag["id"]])

    def test_export_reste_werden_nicht_als_seite_aufgenommen(self):
        import json as jsonlib
        from liloport import abgleich
        # jemand entpackt eine Export-ZIP in den Inhalte-Ordner: liloport.json ist keine Seite
        (Path(self.tmp.name) / "beta" / "liloport.json").write_text(
            jsonlib.dumps({"titel": "Export", "bloecke": []}), encoding="utf-8")
        self.assertEqual(abgleich.bericht(self.store)["seitenNeu"], [])

    def test_verzeichnis_loeschen_mit_fehlenden_dateien(self):
        # Seiten-Dateien von Hand gelöscht: Das Verzeichnis lässt sich trotzdem in Liloport löschen
        (Path(self.tmp.name) / "beta" / "drei.json").unlink()
        self.store.verzeichnis_loeschen(self.b["id"])
        self.assertEqual({v["name"] for v in self.store.site_laden()["verzeichnisse"]}, {"Alpha", "Unter"})


if __name__ == "__main__":
    unittest.main()
