"""Kompetenzrahmen: Validierung, Statuslogik (Vererbung nach oben), Abbildung, Import, Block."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liloport import kompetenzen as K  # noqa: E402
from liloport.store import Store, StoreFehler  # noqa: E402

RAHMEN = {"titel": "Test", "bereiche": [
    {"id": "b00001", "titel": "B1", "kompetenzen": [
        {"id": "k00001", "titel": "K1", "stufen": [
            {"id": "s00001", "titel": "S1", "punkte": [{"id": "p00001", "titel": "P1"}, {"id": "p00002", "titel": "P2"}]},
            {"id": "s00002", "titel": "S2", "punkte": []}]}]},
    {"id": "b00002", "titel": "B2", "kompetenzen": []}]}


def seite(bloecke):
    return {"titel": "S", "bloecke": bloecke}


class StatusTests(unittest.TestCase):
    def status(self, knoten_liste):
        seiten = [(f"a/s{i}", f"S{i}", seite([{"id": "b1", "typ": "kr", "rahmen": "t", "knoten": kn}])) for i, kn in enumerate(knoten_liste)]
        kr = dict(RAHMEN, id="t")
        return {nid: e["status"] for nid, e in K.status_berechnen(kr, seiten).items()}

    def test_alles_offen_ohne_seiten(self):
        self.assertEqual(set(self.status([]).values()), {"offen"})

    def test_oranger_punkt_faerbt_alles_darueber(self):
        st = self.status([{"p00001": "orange"}])
        self.assertEqual((st["p00001"], st["s00001"], st["k00001"], st["b00001"], st["b00002"]), ("orange", "orange", "orange", "orange", "offen"))

    def test_stufe_gruen_wenn_alle_punkte_gruen(self):
        st = self.status([{"p00001": "gruen"}, {"p00002": "gruen"}])
        self.assertEqual(st["s00001"], "gruen")
        self.assertEqual(st["k00001"], "orange", "S2 noch offen → Kompetenz in Bearbeitung")
        st = self.status([{"p00001": "gruen", "p00002": "gruen", "s00002": "gruen"}])
        self.assertEqual((st["k00001"], st["b00001"]), ("gruen", "gruen"))

    def test_hoechster_status_ueber_seiten(self):
        st = self.status([{"p00001": "gruen"}, {"p00001": "weiss"}])
        self.assertEqual(st["p00001"], "gruen")

    def test_direkt_gesetzt_schlaegt_ableitung(self):
        st = self.status([{"s00001": "gruen"}])
        self.assertEqual((st["s00001"], st["p00001"]), ("gruen", "offen"))

    def test_noch_nicht_bearbeitet_und_offen_getrennt(self):
        # Eine Seite führt drei Stufen: erarbeitet, in Bearbeitung, noch nicht bearbeitet; S2 von B1 fehlt
        rahmen = {"titel": "T", "bereiche": [{"id": "b00001", "titel": "B", "kompetenzen": [{"id": "k00001", "titel": "K", "stufen": [
            {"id": "s0000a", "titel": "a", "punkte": [{"id": "p0000a", "titel": "pa"}]},
            {"id": "s0000b", "titel": "b", "punkte": [{"id": "p0000b", "titel": "pb"}]},
            {"id": "s0000c", "titel": "c", "punkte": [{"id": "p0000c", "titel": "pc"}]},
            {"id": "s0000d", "titel": "d"}]}]}], "id": "t"}
        seiten = [("a/s", "S", seite([{"id": "b1", "typ": "kr", "rahmen": "t", "knoten": {"s0000a": "gruen", "s0000b": "orange", "s0000c": "weiss"}}]))]
        st = {n: e["status"] for n, e in K.status_berechnen(rahmen, seiten).items()}
        self.assertEqual((st["s0000a"], st["s0000b"], st["s0000c"], st["s0000d"]), ("gruen", "orange", "weiss", "offen"))
        self.assertEqual((st["p0000c"], st["k00001"]), ("offen", "orange"), "Punkte ohne Seite bleiben offen")
        z = K.zusammenfassung(rahmen, K.status_berechnen(rahmen, seiten))["stufe"]
        self.assertEqual((z["gruen"], z["orange"], z["weiss"], z["offen"], z["gesamt"]), (1, 1, 1, 1, 4))

    def test_zugeordnet_vererbt_sich_als_noch_nicht_bearbeitet(self):
        st = self.status([{"p00002": "weiss"}])
        self.assertEqual((st["p00002"], st["s00001"], st["k00001"], st["b00001"], st["s00002"], st["b00002"]),
                         ("weiss", "weiss", "weiss", "weiss", "offen", "offen"))
        st = self.status([{"p00002": "weiss"}, {"s00002": "gruen"}])
        self.assertEqual(st["k00001"], "orange", "ein erarbeitetes Kind: in Bearbeitung")


class RahmenTests(unittest.TestCase):
    def test_pruefen_vergibt_ids_und_kuerzt(self):
        kr = K.rahmen_pruefen({"titel": " X ", "bereiche": [{"titel": "B", "kompetenzen": [{"titel": "K" * 300, "stufen": [{"titel": "S", "punkte": [{"text": "P"}]}]}]}]}, "x")
        self.assertEqual(kr["titel"], "X")
        self.assertEqual(len(kr["bereiche"][0]["kompetenzen"][0]["titel"]), 200)
        p = kr["bereiche"][0]["kompetenzen"][0]["stufen"][0]["punkte"][0]
        self.assertEqual(p["titel"], "P"); self.assertRegex(p["id"], r"[a-z0-9]{6}")
        with self.assertRaises(StoreFehler):
            K.rahmen_pruefen({"bereiche": "nein"})

    def test_ablage_import_abbildung_und_block(self):
        with tempfile.TemporaryDirectory() as t:
            store = Store(t); store.anlegen()
            komp = K.Kompetenzen(store)
            kr = komp.anlegen(dict(RAHMEN))
            self.assertEqual(kr["id"], "test")
            self.assertEqual([e["knoten"] for e in komp.liste()], [7])
            kopie = komp.importieren(json.dumps(RAHMEN).encode("utf-8"), "rahmen.json")
            self.assertEqual(kopie["id"], "test-2")
            v = store.verzeichnis_anlegen("A")
            p, _ = store.seite_anlegen("Seite", v["id"])
            store.seite_aktualisieren(p, bloecke=[K.block_pruefen({"rahmen": "test", "knoten": {"p00001": "gruen", "x": "gruen", "p00002": "lila"}}, "b1")])
            st = komp.status("test")
            self.assertEqual(st["p00001"]["status"], "gruen"); self.assertEqual(st["p00001"]["seiten"][0]["titel"], "Seite")
            vorlage = "{{TITEL}}|{{KRID}}|{{REL}}|{{META}}|{{GESAMT}}|{{TABELLE}}|{{INHALT}}|{{PRODUKTFUSS}}|{{EXPORT}}"
            html = K.abbildung_html(kr, st, "../", vorlage, "")
            self.assertIn('href="../a/seite.html"', html)
            self.assertIn("ka-anzahl", html)
            block = K.block_html({"rahmen": "test", "knoten": {"p00001": "gruen"}}, {"test": kr}, "../", "b1", True, p)
            self.assertIn("kr-schalter", block); self.assertIn("B1 › K1 › S1", block)
            export = K.block_html({"rahmen": "test", "knoten": {"p00001": "gruen"}}, {"test": kr}, "", "b1", None)
            self.assertNotIn("kr-schalter", export); self.assertNotIn("Abbildung", export)
            komp.loeschen("test")
            self.assertEqual(len(komp.liste()), 1)


class BeurteilungTests(unittest.TestCase):
    def test_bereinigen_behaelt_beurteilung(self):
        from liloport.kommentare import kommentar_bereinigen
        k = kommentar_bereinigen({"id": "x1", "zeit": "2026", "name": "L", "text": "ok", "art": "beurteilung", "skala": "6", "wert": 5, "block": "b4", "knoten": "p1a2c3", "knotenTitel": "T"})
        self.assertEqual((k["art"], k["skala"], k["wert"], k["knotenTitel"]), ("beurteilung", 6, 5, "T"))
        self.assertNotIn("art", kommentar_bereinigen({"id": "x", "text": "t", "art": "beurteilung", "skala": 11, "wert": 3}))

    def test_block_mit_beurteilung_nur_im_abgabe_export(self):
        kr = dict(RAHMEN, id="t")
        b = {"rahmen": "t", "knoten": {"p00001": "gruen"}}
        self.assertIn("kr-beurteilung", K.block_html(b, {"t": kr}, "", "b1", None, beurteilung=True))
        self.assertNotIn("kr-beurteilung", K.block_html(b, {"t": kr}, "", "b1", None))


class BeschreibungTests(unittest.TestCase):
    def test_links_und_zeilen(self):
        from liloport.kompetenzen import _beschreibung
        h = _beschreibung('Text <b>\nMehr: https://be.lehrplan.ch/101abc. Ende "x" javascript:alert(1)')
        self.assertIn('<a href="https://be.lehrplan.ch/101abc" target="_blank" rel="noopener">', h)
        self.assertIn("&lt;b&gt;\nMehr", h)
        self.assertNotIn('href="javascript', h)


if __name__ == "__main__":
    unittest.main()
