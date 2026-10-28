"""Import einer heruntergeladenen Export-ZIP als neue Seite(n) (Blöcke, Anhänge, Kommentare).

Grundlage ist liloport.json in der ZIP: Titel, Datum, Tags, Menü-Option, CSS, Blöcke mit Anhang-Zuordnung;
bei Verzeichnis- und Portfolio-Exporten (liloport: 2) eine Liste solcher Seiten samt Verzeichnisnamen.
Passwortgeschützte Exporte enthalten kein liloport.json und können nicht importiert werden.
"""
import io
import json
import re
import secrets
import zipfile
from pathlib import Path

from . import sanitize
from .abgabe import pruefsumme
from .store import INTERN, Store, StoreFehler, datum_pruefen, tags_pruefen



class Importer:
    """Zwei Schritte: vorschau() legt die ZIP ab und beschreibt sie, importieren() legt die Seite(n) an."""

    def __init__(self, store: Store, assets, kommentare):
        self.store = store
        self.assets = assets
        self.kommentare = kommentare
        self.ordner = store.root / INTERN / "import"

    def _lesen(self, daten) -> tuple:
        """Öffnet die ZIP (Bytes oder Pfad), findet liloport.json und gibt (zip, wurzelpfad, info) zurück."""
        try:
            z = zipfile.ZipFile(io.BytesIO(daten) if isinstance(daten, (bytes, bytearray)) else daten)
        except zipfile.BadZipFile:
            raise StoreFehler("Das ist keine gültige ZIP-Datei.")
        try:
            return self._pruefen(z)
        except Exception:
            z.close()   # Windows: eine offene ZIP liesse sich nicht löschen
            raise

    @staticmethod
    def _pruefen(z) -> tuple:
        namen = z.namelist()
        treffer = sorted((n for n in namen if n.endswith("liloport.json") and not n.startswith("__MACOSX")), key=len)
        if not treffer:
            if any(n.endswith("manifest.json") for n in namen):
                raise StoreFehler("Diese ZIP enthält kein liloport.json – sie stammt aus einer älteren Liloport-Version oder ist ein passwortgeschützter Export. Bitte neu exportieren (ohne Passwort).")
            raise StoreFehler("Diese ZIP ist kein Liloport-Export (liloport.json fehlt).")
        wurzel = treffer[0][: -len("liloport.json")]
        try:
            info = json.loads(z.read(treffer[0]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise StoreFehler("liloport.json ist unlesbar.")
        if not isinstance(info, dict) or not (isinstance(info.get("bloecke"), list) or isinstance(info.get("seiten"), list)):
            raise StoreFehler("liloport.json hat ein unbekanntes Format.")
        return z, wurzel, info

    @staticmethod
    def _seiten(info: dict) -> list:
        """Einheitlich: Liste der Seiten (Export einer Seite = Liste mit einem Eintrag)."""
        if isinstance(info.get("seiten"), list):
            return [s for s in info["seiten"] if isinstance(s, dict) and isinstance(s.get("bloecke"), list)]
        return [info]

    def _abgabe_pruefen(self, z, wurzel, info) -> dict:
        """Stimmt die Prüfsumme des Abgabestempels noch? (Inhalt und Dateien unverändert seit dem Export)"""
        stempel = info.get("abgabe")
        if not isinstance(stempel, dict):
            return None
        dateien = {}
        for a in (info.get("anhaenge") or {}).values():
            name = wurzel + str(a.get("datei", ""))
            if name in z.namelist():
                dateien[a["datei"]] = _ZipEintrag(z, name)
        summe = pruefsumme(self._seiten(info), dateien)
        return {"zeit": str(stempel.get("zeit", "")), "pruefsumme": str(stempel.get("pruefsumme", "")),
                "gueltig": summe == stempel.get("pruefsumme")}

    def vorschau(self, daten: bytes, dateiname: str) -> dict:
        """Legt die ZIP unter _wiki/import/<token>.zip ab und beschreibt den Inhalt."""
        return self.vorschau_strom(io.BytesIO(daten), len(daten), dateiname)

    def vorschau_strom(self, quelle, laenge: int, dateiname: str) -> dict:
        """Schreibt die hochgeladene ZIP stückweise nach _wiki/import/<token>.zip (ohne Grössenlimit)."""
        self.ordner.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(8)
        ziel = self.ordner / f"{token}.zip"
        rest = laenge
        with open(ziel, "wb") as f:
            while rest > 0:
                stueck = quelle.read(min(1024 * 1024, rest))
                if not stueck:
                    break
                f.write(stueck)
                rest -= len(stueck)
        try:
            z, wurzel, info = self._lesen(ziel)
        except Exception:
            ziel.unlink(missing_ok=True)
            raise
        try:
            seiten = self._seiten(info)
            kommentare = sum(len(self._kommentare_lesen(z, wurzel, s, i == 0, len(seiten) > 1)) for i, s in enumerate(seiten))
            abgabe = self._abgabe_pruefen(z, wurzel, info)
            namen = z.namelist()
        except Exception:
            z.close()
            ziel.unlink(missing_ok=True)
            raise
        z.close()
        self._aufraeumen(behalten=token)
        anhaenge = info.get("anhaenge") or {}
        fehlend = [a["name"] for a in anhaenge.values() if wurzel + a["datei"] not in namen]
        return {"token": token, "titel": info.get("titel") or Path(dateiname).stem, "menue": seiten[0].get("menue", "voll"),
                "seiten": len(seiten), "bloecke": sum(_anzahl(s["bloecke"]) for s in seiten), "anhaenge": len(anhaenge),
                "fehlend": fehlend, "kommentare": kommentare, "css": any((s.get("css") or "").strip() for s in seiten),
                "html": sum(_anzahl(s["bloecke"], "html") for s in seiten), "abgabe": abgabe,
                "verzeichnisse": sorted({" › ".join(s.get("ort") or []) for s in seiten} - {""}) if len(seiten) > 1 else []}

    def _unterverzeichnis(self, eltern_id: str, name: str) -> str:
        """Findet oder erstellt ein Unterverzeichnis mit diesem Namen."""
        site = self.store.site_laden()
        for v in site["verzeichnisse"]:
            if v.get("eltern") == eltern_id and v["name"] == name:
                return v["id"]
        return self.store.verzeichnis_anlegen(name, eltern_id)["id"]

    def importieren(self, token: str, verzeichnis_id: str, titel: str = None) -> str:
        """Legt die Seite(n) an, lädt Anhänge hoch, führt Kommentare zusammen; gibt den Pfad der ersten Seite zurück."""
        if not token or not all(c in "0123456789abcdef" for c in token):
            raise StoreFehler("Ungültiger Import.")
        datei = self.ordner / f"{token}.zip"
        if not datei.exists():
            raise StoreFehler("Der Import ist abgelaufen; bitte die ZIP erneut wählen.")
        self.store.verzeichnis(self.store.site_laden(), verzeichnis_id)  # Ziel muss existieren
        z, wurzel, info = self._lesen(datei)
        try:
            erste = self._anlegen(z, wurzel, info, verzeichnis_id, titel)
        finally:
            z.close()   # Windows: erst nach dem Schliessen lässt sich die abgelegte ZIP löschen
        datei.unlink()
        return erste

    def _anlegen(self, z, wurzel, info, verzeichnis_id, titel) -> str:
        seiten = self._seiten(info)
        mehrere = len(seiten) > 1

        # 1. Seiten anlegen (leer), Verzeichnisstruktur unterhalb des Ziels nachbilden
        orte = [list(s.get("ort") or []) for s in seiten]
        gemeinsam = 0
        while mehrere and all(len(o) > gemeinsam for o in orte) and len({o[gemeinsam] for o in orte}) == 1:
            gemeinsam += 1
        neue_pfade, pfad_map = [], {}
        for s, ort in zip(seiten, orte):
            ziel_id = verzeichnis_id
            for name in (ort[gemeinsam:] if mehrere else []):
                ziel_id = self._unterverzeichnis(ziel_id, str(name)[:120])
            t = (titel if (titel and not mehrere) else s.get("titel")) or "Importierte Seite"
            menue = s.get("menue") if s.get("menue") in ("voll", "seitenmenue", "keine") else "voll"
            pfad, _ = self.store.seite_anlegen(str(t).strip()[:120], ziel_id, menue, [])
            neue_pfade.append(pfad)
            if s.get("pfad"):
                pfad_map[str(s["pfad"])] = pfad

        # 2. Anhänge: Heimat ist die erste Seite, die sie verwendet
        anhaenge = info.get("anhaenge") or {}
        zuordnung = {}
        for alt_id, a in anhaenge.items():
            name = wurzel + str(a.get("datei", ""))
            if name not in z.namelist():
                continue
            heimat = next((neue_pfade[i] for i, s in enumerate(seiten)
                           if alt_id in _asset_ids(s["bloecke"]) or a["datei"] in json.dumps(s["bloecke"]) or a["datei"] in (s.get("css") or "")),
                          neue_pfade[0])
            try:
                with z.open(name) as quelle:
                    neu = self.assets.hochladen_strom(heimat, a.get("name") or Path(a["datei"]).name, quelle, z.getinfo(name).file_size)
            except StoreFehler:
                continue
            zuordnung[alt_id] = (neu["id"], neu["datei"])

        # 3. Inhalte: Anhänge und interne Links umschreiben, filtern, Datum/Tags, Kommentare
        for i, (s, pfad) in enumerate(zip(seiten, neue_pfade)):
            bloecke = _links_umschreiben(_bloecke_umschreiben(s["bloecke"], zuordnung, anhaenge), pfad_map)
            bloecke = _entschaerfen(bloecke)
            css = str(s.get("css") or "").replace("<", "")  # CSS braucht kein «<»; verhindert Ausbruch aus <style>
            for alt_id, (neu_id, neu_datei) in zuordnung.items():
                alt = (anhaenge.get(alt_id) or {}).get("datei", "")
                if alt:
                    css = css.replace(alt, neu_datei)
            try:
                datum = datum_pruefen(s.get("datum"))
            except StoreFehler:
                datum = ""
            try:
                tags = tags_pruefen(s.get("tags") or [])
            except StoreFehler:
                tags = []
            seite = self.store.seite_aktualisieren(pfad, bloecke=bloecke, css=css, datum=datum, tags=tags)
            self.assets.referenzen_setzen(pfad, seite)
            kommentare = self._kommentare_lesen(z, wurzel, s, i == 0, mehrere)
            if kommentare and self.kommentare:
                self.kommentare.zusammenfuehren(pfad, kommentare)
        return neue_pfade[0]

    def _kommentare_lesen(self, z, wurzel, seite: dict = None, erste: bool = True, mehrere: bool = False) -> list:
        """Kommentare einer Seite aus comments.json und aus ihrem eingebetteten Block, zusammengeführt nach ID."""
        from .kommentare import KOMMENTARE_RE
        gesammelt, ids = [], set()
        datei = str((seite or {}).get("datei") or "")
        kennung = datei[:-5] if datei.endswith(".html") else ""

        def passt(k):
            if not mehrere:
                return True
            return k.get("seite") == kennung or (not k.get("seite") and erste)

        def aufnehmen(liste):
            for k in liste or []:
                if isinstance(k, dict) and k.get("id") and k["id"] not in ids and passt(k):
                    ids.add(k["id"])
                    gesammelt.append(k)

        name = wurzel + "comments.json"
        if name in z.namelist():
            try:
                aufnehmen(json.loads(z.read(name).decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                pass
        if datei and wurzel + datei in z.namelist():
            html_dateien = [wurzel + datei]
        elif mehrere:
            html_dateien = []
        else:
            html_dateien = [n for n in z.namelist() if n.startswith(wurzel) and n.endswith(".html") and not n.endswith("/dateien.html") and n.count("/") == wurzel.count("/")]
        for n in html_dateien:
            m = KOMMENTARE_RE.search(z.read(n).decode("utf-8", "replace"))
            if m:
                try:
                    aufnehmen(json.loads(m.group(1)))
                except ValueError:
                    pass
        gesammelt.sort(key=lambda k: str(k.get("zeit", "")))
        return gesammelt

    def _aufraeumen(self, behalten: str):
        import time
        for alt in self.ordner.glob("*.zip"):
            if alt.stem != behalten and time.time() - alt.stat().st_mtime > 3600:
                alt.unlink()


def _asset_ids(bloecke) -> set:
    ids = set()
    for b in bloecke or []:
        if isinstance(b, dict):
            if b.get("asset"):
                ids.add(b["asset"])
            if b.get("typ") == "spalten":
                for sp in b.get("spalten") or []:
                    ids |= _asset_ids(sp)
    return ids


def _links_umschreiben(bloecke, pfad_map: dict) -> list:
    """lp:alter-pfad → lp:neuer-pfad; Links auf Seiten, die nicht mitkamen, werden zu Text."""
    def html_ersetzen(text):
        def ersetzen(m):
            neu = pfad_map.get(m.group(2))
            return f'<a{m.group(1)}href="lp:{neu}{m.group(3) or ""}"' if neu else "<a data-weg=\"1\""
        text = re.sub(r'<a([^>]*?)href="lp:([^"#]*)(#[^"]*)?"', ersetzen, text or "")
        return re.sub(r'<a data-weg="1"[^>]*>(.*?)</a>', r"\1", text, flags=re.S)

    ergebnis = []
    for b in bloecke or []:
        if not isinstance(b, dict):
            continue
        b = dict(b)
        if b.get("typ") in ("text", "html"):
            b["html"] = html_ersetzen(b.get("html"))
        if b.get("typ") == "button" and str(b.get("ziel") or "").startswith("lp:"):
            alt, _, anker = b["ziel"][3:].partition("#")
            b["ziel"] = ("lp:" + pfad_map[alt] + ("#" + anker if anker else "")) if alt in pfad_map else ""
        if b.get("typ") == "spalten":
            b["spalten"] = [_links_umschreiben(sp, pfad_map) for sp in b.get("spalten") or []]
        ergebnis.append(b)
    return ergebnis


def _anzahl(bloecke, typ=None) -> int:
    n = 0
    for b in bloecke or []:
        if not isinstance(b, dict):
            continue
        n += 1 if typ is None or b.get("typ") == typ else 0
        if b.get("typ") == "spalten":
            for sp in b.get("spalten", []):
                n += _anzahl(sp, typ)
    return n


_TYPEN = {"text", "trenner", "bild", "video", "pdf", "datei", "spalten", "html", "button", "kr"}


def _entschaerfen(bloecke) -> list:
    """Fremde Seiten dürfen kein Skript mitbringen: HTML wird gefiltert, unbekannte Blöcke fallen weg.

    Ohne diesen Schritt könnte eine präparierte ZIP über einen HTML-Block JavaScript einschleusen, das im
    Editiermodus (gleiche Adresse wie die Liloport-API) Seiten lesen, ändern oder löschen könnte.
    """
    ergebnis = []
    for b in bloecke or []:
        if not isinstance(b, dict) or b.get("typ") not in _TYPEN:
            continue
        b = dict(b)
        if b["typ"] in ("text", "html"):
            b["html"] = sanitize.filtern(str(b.get("html") or ""), "profi")
        if b["typ"] == "kr":
            from .kompetenzen import block_pruefen
            b = dict(block_pruefen(b, str(b.get("id") or "b")), **{k: b[k] for k in ("klapp", "klappTitel") if k in b})
        if b["typ"] == "button" and str(b.get("ziel") or "").strip().lower().startswith(("javascript:", "data:", "vbscript:")):
            b["ziel"] = ""
        if b["typ"] == "spalten":
            b["spalten"] = [_entschaerfen(sp) for sp in (b.get("spalten") or []) if isinstance(sp, list)]
        ergebnis.append(b)
    return ergebnis


def _bloecke_umschreiben(bloecke, zuordnung, info_anhaenge=None) -> list:
    info_anhaenge = info_anhaenge or {}
    """Ersetzt alte Asset-IDs durch neue (fehlende Anhänge bleiben leer) und Pfade in HTML-Blöcken."""
    ergebnis = []
    for b in bloecke or []:
        b = dict(b)
        if b.get("typ") in ("bild", "video", "pdf", "datei"):
            b["asset"] = zuordnung.get(b.get("asset"), ("", ""))[0]
        if b.get("typ") == "html":
            for alt_id, (neu_id, neu_datei) in zuordnung.items():
                alt_datei = (info_anhaenge.get(alt_id) or {}).get("datei", "")
                if alt_datei:
                    b["html"] = b.get("html", "").replace(alt_datei, neu_datei)
        if b.get("typ") == "spalten":
            b["spalten"] = [_bloecke_umschreiben(sp, zuordnung, info_anhaenge) for sp in b.get("spalten", [])]
        ergebnis.append(b)
    return ergebnis


class _ZipEintrag:
    """Datei in der ZIP, für die Prüfsumme stückweise gelesen (grosse Videos nie ganz im Speicher)."""

    def __init__(self, z, name):
        self.z, self.name = z, name

    def stuecke(self):
        with self.z.open(self.name) as f:
            while True:
                stueck = f.read(1024 * 1024)
                if not stueck:
                    return
                yield stueck
