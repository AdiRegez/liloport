"""Kommentare: auf dem Webserver erfasst, mit der heruntergeladenen Seite zurück nach Liloport.

Jeder Export bekommt eine Kennung (der Zufallsname der Seite); _wiki/exporte.json ordnet sie der
lokalen Seite zu. Importierte Kommentare liegen unter _wiki/kommentare/<pfad>.json und werden in der
lokalen Seite angezeigt sowie beim nächsten Export wieder mitgegeben.
"""
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from .store import INTERN, Store, StoreFehler, jetzt

META_RE = re.compile(r'<script[^>]+id="liloport-meta"[^>]*>(.*?)</script>', re.S)
KOMMENTARE_RE = re.compile(r'<script[^>]+id="liloport-kommentare"[^>]*>(.*?)</script>', re.S)
MAX_TEXT = 20000


def kommentar_bereinigen(k: dict) -> dict:
    """Übernimmt nur bekannte Felder mit begrenzter Länge (sh = Hash des Bearbeitungsschlüssels)."""
    neu = {"id": str(k.get("id") or "")[:40], "zeit": str(k.get("zeit") or "")[:25],
           "name": str(k.get("name") or "")[:80], "text": str(k.get("text") or "")[:MAX_TEXT]}
    if k.get("bearbeitet"):
        neu["bearbeitet"] = str(k["bearbeitet"])[:25]
    if isinstance(k.get("sh"), str) and len(k["sh"]) == 64:
        neu["sh"] = k["sh"]
    if k.get("art") == "beurteilung":
        try:
            skala, wert = int(k.get("skala")), int(k.get("wert"))
        except (TypeError, ValueError):
            skala, wert = 0, 0
        if 1 <= skala <= 10 and 0 <= wert <= skala:
            neu.update({"art": "beurteilung", "skala": skala, "wert": wert, "block": str(k.get("block") or "")[:40],
                        "knoten": str(k.get("knoten") or "")[:12], "knotenTitel": str(k.get("knotenTitel") or "")[:300]})
    return neu


class Kommentare:
    """Verwaltet Export-Kennungen und importierte Kommentare."""

    def __init__(self, store: Store):
        self.store = store
        self.exporte_datei = store.root / INTERN / "exporte.json"
        self.ordner = store.root / INTERN / "kommentare"

    # ---------- Export-Kennungen ----------

    def exporte(self) -> dict:
        if not self.exporte_datei.exists():
            return {}
        return json.loads(self.exporte_datei.read_text(encoding="utf-8"))

    def export_merken(self, kennung: str, pfad: str, **extra):
        """Merkt sich, zu welcher lokalen Seite ein Export gehört (dazu Moderationsschlüssel, Startseite)."""
        e = self.exporte()
        e[kennung] = {"pfad": pfad, "zeit": jetzt(), **extra}
        self.exporte_datei.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")

    def pfade_umbenennen(self, alt: str, neu: str):
        """Nach Ordnerumbenennung: Export-Zuordnungen und Kommentardateien mitziehen."""
        e = self.exporte()
        for v in e.values():
            p = v["pfad"]
            if p == alt or p.startswith(alt + "/"):
                v["pfad"] = neu + p[len(alt):]
        self.exporte_datei.write_text(json.dumps(e, ensure_ascii=False, indent=2), encoding="utf-8")
        for quelle, ziel in ((self.ordner / alt, self.ordner / neu), (self._datei(alt), self._datei(neu))):
            if quelle.exists():  # Ordner (Verzeichnis umbenannt) oder Datei (Seite verschoben)
                ziel.parent.mkdir(parents=True, exist_ok=True)
                quelle.rename(ziel)

    # ---------- Kommentare ----------

    def _datei(self, pfad: str) -> Path:
        return self.ordner / (pfad + ".json")

    def laden(self, pfad: str) -> list:
        """Importierte Kommentare einer Seite, älteste zuerst."""
        datei = self._datei(pfad)
        if not datei.exists():
            return []
        try:
            return json.loads(datei.read_text(encoding="utf-8"))
        except ValueError:
            return []

    def speichern(self, pfad: str, kommentare: list):
        datei = self._datei(pfad)
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(json.dumps(kommentare, ensure_ascii=False, indent=2), encoding="utf-8")

    def loeschen(self, pfad: str, kid: str = None):
        """Entfernt einen Kommentar oder alle Kommentare einer Seite."""
        if kid is None:
            datei = self._datei(pfad)
            if datei.exists():
                datei.unlink()
            return
        self.speichern(pfad, [k for k in self.laden(pfad) if k.get("id") != kid])

    def zusammenfuehren(self, pfad: str, neue: list) -> int:
        """Fügt Kommentare hinzu, die (nach ID) noch fehlen; gibt die Anzahl neuer zurück."""
        vorhanden = self.laden(pfad)
        ids = {k.get("id") for k in vorhanden}
        anzahl = 0
        for k in neue:
            k = kommentar_bereinigen(k)
            if not k["text"].strip() or k["id"] in ids:
                continue
            vorhanden.append(k)
            ids.add(k["id"])
            anzahl += 1
        vorhanden.sort(key=lambda k: k.get("zeit", ""))
        self.speichern(pfad, vorhanden)
        return anzahl

    # ---------- Import ----------

    def aus_html(self, html: str) -> tuple:
        """Liest Export-Kennung und eingebettete Kommentare aus einer heruntergeladenen Seite."""
        m = META_RE.search(html)
        if not m:
            raise StoreFehler("Das ist keine von Liloport exportierte Seite (keine Kennung gefunden).")
        try:
            meta = json.loads(m.group(1))
        except ValueError:
            raise StoreFehler("Kennung der Seite ist unlesbar.")
        kommentare = []
        k = KOMMENTARE_RE.search(html)
        if k:
            try:
                kommentare = json.loads(k.group(1))
            except ValueError:
                kommentare = []
        return str(meta.get("export") or ""), kommentare if isinstance(kommentare, list) else []

    def importieren(self, kennung: str, kommentare: list) -> dict:
        """Ordnet die Kennung einer Seite zu und führt die Kommentare zusammen."""
        eintrag = self.exporte().get(kennung)
        if not eintrag:
            raise StoreFehler("Zu dieser Export-Kennung ist hier keine Seite bekannt. Wurde die Seite auf diesem Rechner exportiert?")
        pfad = eintrag["pfad"]
        self.store.seite_laden(pfad)
        neu = self.zusammenfuehren(pfad, kommentare)
        return {"pfad": pfad, "neu": neu, "gesamt": len(self.laden(pfad))}

    def importieren_aus_datei(self, name: str, daten: bytes) -> dict:
        """Import aus einer heruntergeladenen HTML-Seite oder einer comments.json (+ Kennung im Namen)."""
        text = daten.decode("utf-8", "replace")
        if name.lower().endswith(".json") or text.lstrip().startswith(("[", "{")):
            try:
                roh = json.loads(text)
            except ValueError:
                raise StoreFehler("Die JSON-Datei ist unlesbar.")
            if isinstance(roh, dict):
                kennung, liste = str(roh.get("export") or ""), roh.get("kommentare") or []
            else:
                kennung, liste = "", roh
            if not kennung:
                m = re.search(r"[a-z0-9]{32}", name)
                if not m:
                    raise StoreFehler("Die Datei nennt keine Export-Kennung. Bitte die heruntergeladene HTML-Seite importieren.")
                kennung = m.group(0)
            return self.importieren(kennung, liste)
        kennung, liste = self.aus_html(text)
        return self.importieren(kennung, liste)

    def importieren_von_url(self, url: str) -> dict:
        """Holt die Seite und comments.json vom Webserver und importiert die Kommentare."""
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise StoreFehler("Bitte eine vollständige Adresse mit https:// angeben.")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                html = r.read(5_000_000).decode("utf-8", "replace")
        except Exception as e:
            raise StoreFehler(f"Seite nicht erreichbar: {e}")
        kennung, eingebettet = self.aus_html(html)
        liste = list(eingebettet)
        try:
            with urllib.request.urlopen(urljoin(url, "comments.json"), timeout=15) as r:
                extern = json.loads(r.read(2_000_000).decode("utf-8", "replace"))
                if isinstance(extern, list):
                    liste += extern
        except Exception:
            pass  # kein comments.json: Seite ohne Kommentarfunktion
        return self.importieren(kennung, liste)
