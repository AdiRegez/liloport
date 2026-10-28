"""Suchindex für das Dashboard: Titel, Textblöcke, HTML-Blöcke und PDF-Text, als _wiki/suchindex.js.

Der Index wird beim Rendern geschrieben und im Browser durchsucht; so funktioniert die Suche
auch im Lesemodus (file://). PDF-Text liefert pdftext.py; gescannte PDFs bleiben beim Dateinamen.

Mit `hintergrund=True` (laufendes Liloport) liest ein eigener Thread neue PDFs: Der Index wird sofort
mit allem geschrieben, was schon bekannt ist, und ein zweites Mal, sobald der PDF-Text da ist. So hält
ein grosses PDF weder das Speichern noch den Start auf. Jedes PDF wird nur einmal gelesen (Cache nach
Grösse und Änderungszeit, nach jedem PDF gespeichert); was zu lange dauert, merkt sich der Cache als leer.
"""
import json
import os
import re
import threading
import time
from pathlib import Path

from .pdftext import FRIST, PdfZuAufwendig, _pdf_datei_lesen, pdf_text, pdf_text_isoliert  # noqa: F401
from .store import INTERN, Store

PDF_CACHE = "pdftext.json"
MAX_TEXT = 2_000_000   # pro Seite (Text, HTML und PDFs zusammen)


def html_zu_text(html: str) -> str:
    """Entfernt Tags und normalisiert Leerraum."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


class Suche:
    """Baut den Suchindex aus Seiten und Anhängen."""

    def __init__(self, store: Store, assets, hintergrund: bool = False):
        self.store = store
        self.assets = assets
        self.cache_datei = store.root / INTERN / PDF_CACHE
        self.hintergrund = hintergrund
        self._sperre = threading.Lock()       # Cache und Index nur von einem Thread gleichzeitig schreiben
        self._arbeiter = None                 # Hintergrund-Thread, der neue PDFs liest
        self._nochmal = threading.Event()     # während des Lesens kam etwas Neues dazu

    def _pdf_cache(self) -> dict:
        if self.cache_datei.exists():
            try:
                return json.loads(self.cache_datei.read_text(encoding="utf-8"))
            except ValueError:
                return {}
        return {}

    def _kennung(self, e) -> tuple:
        datei = self.store.sicherer_pfad(e["datei"])
        if not datei.exists():
            return datei, None
        st = datei.stat()
        return datei, f"{st.st_size}-{int(st.st_mtime)}"

    def _cache_schreiben(self, cache: dict):
        self.cache_datei.parent.mkdir(exist_ok=True)
        tmp = self.cache_datei.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.cache_datei)

    _isolieren = True   # im laufenden Liloport: jedes PDF in einem eigenen Prozess lesen (siehe pdftext)

    def _pdf_lesen(self, aid, datei, kennung, cache) -> None:
        try:
            if self.hintergrund and Suche._isolieren:
                try:
                    text = pdf_text_isoliert(datei)
                except OSError as e:   # Prozess liess sich nicht starten: ab jetzt im eigenen Prozess lesen
                    print(f"PDF-Text: eigener Prozess nicht möglich ({e}), lese direkt.")
                    Suche._isolieren = False
                    text = _pdf_datei_lesen(str(datei), FRIST)
            else:
                # Grosse PDFs ohne Schrift-Verweis sind Scans ohne Textebene: gar nicht erst zerlegen
                text = _pdf_datei_lesen(str(datei), FRIST)
            cache[aid] = {"kennung": kennung, "text": text}
        except PdfZuAufwendig:
            cache[aid] = {"kennung": kennung, "text": "", "hinweis": "zu aufwendig"}
        except Exception:  # noqa: BLE001 – ein defektes PDF darf die Suche nie verhindern
            cache[aid] = {"kennung": kennung, "text": "", "hinweis": "nicht lesbar"}

    def _fehlende(self, cache: dict) -> list:
        """PDFs aus der Registry, deren Text noch nicht (oder nicht mehr gültig) im Cache steht."""
        registry = self.assets.laden() if self.assets else {}
        fehlend = []
        for aid, e in registry.items():
            if e.get("typ") != "pdf":
                continue
            datei, kennung = self._kennung(e)
            if kennung and (cache.get(aid) or {}).get("kennung") != kennung:
                fehlend.append((aid, datei, kennung))
        return fehlend

    def _pdf_texte(self, lesen: bool = True) -> dict:
        """Text aller bekannten PDFs. lesen=False: nur aus dem Cache (neue PDFs liest der Hintergrund)."""
        cache = self._pdf_cache()
        if lesen:
            fehlend = self._fehlende(cache)
            for aid, datei, kennung in fehlend:
                self._pdf_lesen(aid, datei, kennung, cache)
                self._cache_schreiben(cache)   # nach jedem PDF: Abbruch verliert keinen Fortschritt
        registry = self.assets.laden() if self.assets else {}
        return {aid: v.get("text", "") for aid, v in cache.items() if aid in registry}

    def eintraege(self, site=None, alle=None) -> list:
        """Ein Eintrag pro Seite: Titel, Text aller Blöcke, Anhangnamen und PDF-Text."""
        site = site or self.store.site_laden()
        registry = self.assets.laden() if self.assets else {}
        pdfs = self._pdf_texte(lesen=not self.hintergrund)
        ergebnis = []
        for v, pfad, seite in (alle if alle is not None else self.store.alle_seiten(site)):
            texte, anhaenge = [], []

            def rek(bl):
                for b in bl or []:
                    if b.get("typ") in ("text", "html"):
                        texte.append(html_zu_text(b.get("html", "")))  # Fussnoten sind <span>: ihr Text ist dabei
                    if b.get("typ") == "bild" and b.get("bildtext"):
                        texte.append(b["bildtext"])
                    if b.get("typ") == "button" and b.get("text"):
                        texte.append(b["text"])
                    if b.get("typ") in ("bild", "video", "pdf", "datei") and b.get("asset") in registry:
                        e = registry[b["asset"]]
                        anhaenge.append(e["name"])
                        if b["typ"] == "pdf" and pdfs.get(b["asset"]):
                            texte.append(pdfs[b["asset"]])
                    if b.get("typ") == "spalten":
                        for sp in b.get("spalten", []):
                            rek(sp)
            rek(seite.get("bloecke"))
            ergebnis.append({"pfad": pfad, "titel": seite.get("titel", ""), "verzeichnis": v["name"],
                             "text": " ".join(t for t in texte if t)[:MAX_TEXT], "anhaenge": anhaenge,
                             "tags": seite.get("tags") or [], "datum": seite.get("datum", ""),
                             "geaendert": seite.get("geaendert", "")})
        return ergebnis

    def _index_schreiben(self, eintraege: list):
        ziel = self.store.root / INTERN / "suchindex.js"
        tmp = ziel.with_suffix(".tmp")
        tmp.write_text("window.LILOPORT_INDEX = " + json.dumps(eintraege, ensure_ascii=False) + ";\n", encoding="utf-8")
        os.replace(tmp, ziel)

    def schreiben(self, site=None, alle=None) -> int:
        """Schreibt _wiki/suchindex.js und gibt die Anzahl Einträge zurück.

        Im Hintergrund-Modus sofort mit dem bekannten Text; neue PDFs liest danach ein eigener Thread."""
        with self._sperre:
            eintraege = self.eintraege(site, alle)
            self._index_schreiben(eintraege)
        if self.hintergrund and self._fehlende(self._pdf_cache()):
            self._hintergrund_starten()
        return len(eintraege)

    def _hintergrund_starten(self):
        self._nochmal.set()
        if self._arbeiter and self._arbeiter.is_alive():
            return
        self._arbeiter = threading.Thread(target=self._hintergrund, name="pdf-text", daemon=True)
        self._arbeiter.start()

    def _hintergrund(self):
        while self._nochmal.is_set():
            self._nochmal.clear()
            cache = self._pdf_cache()
            neu, zuletzt = {}, time.monotonic()
            for aid, datei, kennung in self._fehlende(cache):
                self._pdf_lesen(aid, datei, kennung, cache)
                neu[aid] = cache[aid]
                # Zwischenstand höchstens alle 15 Sekunden sichern: Bei Hunderten PDFs wäre es sonst
                # quadratisch viel Schreibarbeit (der Cache wächst mit jedem PDF).
                if time.monotonic() - zuletzt > 15:
                    self._cache_ergaenzen(neu)
                    neu, zuletzt = {}, time.monotonic()
            if neu:
                self._cache_ergaenzen(neu)
            with self._sperre:
                try:
                    self._index_schreiben(self.eintraege())
                except Exception:  # noqa: BLE001 – z. B. Inhalte-Ordner gerade nicht erreichbar
                    pass

    def _cache_ergaenzen(self, neu: dict):
        with self._sperre:
            aktuell = self._pdf_cache()
            aktuell.update(neu)
            self._cache_schreiben(aktuell)

    def warten(self, sekunden: float = 30) -> bool:
        """Für Tests: wartet, bis der Hintergrund fertig ist."""
        if self._arbeiter:
            self._arbeiter.join(sekunden)
            return not self._arbeiter.is_alive()
        return True
