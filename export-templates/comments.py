#!/usr/bin/env python3
"""Liloport – Kommentare als Python-CGI-Skript (Alternative zu comments.php).

Für Webserver ohne PHP, aber mit Python und CGI (z. B. Apache mit ExecCGI, viele Uni-Server).
Speichert Kommentare in comments.json im selben Ordner. Gespeichert werden nur Name, Text,
Zeit und eine zufällige ID. Schutz: Längenlimit, Honeypot-Feld, 10 Sekunden Pause pro Herkunft.
"""
import hashlib
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from urllib.parse import parse_qs

MAX_HTML = 20000
ERLAUBT = {
    "p": (), "br": (), "h2": (), "h3": (), "h4": (), "strong": (), "em": (), "u": (), "s": (), "sub": (), "sup": (),
    "ul": (), "ol": (), "li": (), "blockquote": (), "code": (), "pre": (), "hr": (), "span": ("style",), "div": ("style",),
    "a": ("href", "title"), "img": ("src", "alt", "width", "height"),
    "table": (), "thead": (), "tbody": (), "tr": (), "th": (), "td": (),
}
UMBENENNEN = {"b": "strong", "i": "em", "strike": "s"}
LEER = {"br", "hr", "img"}


class _Filter(HTMLParser):
    """Baut HTML neu auf und lässt nur erlaubte Tags/Attribute stehen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.teile, self.offen = [], []

    @staticmethod
    def _attr_ok(tag, name, wert):
        w = (wert or "").strip()
        if name == "href":
            return w.lower().startswith(("http://", "https://", "mailto:", "#", "/", "./", "../")) or ":" not in w
        if name == "src":
            return w.lower().startswith(("http://", "https://", "./", "../", "assets/"))
        if name == "style":
            return all(d.split(":", 1)[0].strip().lower() in ("color", "background-color", "text-align")
                       and "url" not in d.lower() for d in w.split(";") if d.strip())
        return True

    def handle_starttag(self, tag, attrs):
        tag = UMBENENNEN.get(tag, tag)
        if tag not in ERLAUBT:
            return
        a = "".join(f' {n}="{escape(v, quote=True)}"' for n, v in attrs if n in ERLAUBT[tag] and v is not None and self._attr_ok(tag, n, v))
        if tag == "a":
            a += ' rel="noopener nofollow" target="_blank"'
        if tag in LEER:
            self.teile.append(f"<{tag}{a}>")
            return
        self.teile.append(f"<{tag}{a}>")
        self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = UMBENENNEN.get(tag, tag)
        if tag in self.offen:
            while self.offen:
                t = self.offen.pop()
                self.teile.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, daten):
        self.teile.append(escape(daten, quote=False))

    def ergebnis(self):
        while self.offen:
            self.teile.append(f"</{self.offen.pop()}>")
        return "".join(self.teile).strip()


def html_filtern(roh):
    f = _Filter()
    f.feed(roh or "")
    f.close()
    return f.ergebnis()


def nur_text(html):
    import re
    return re.sub(r"<[^>]+>", "", html).strip()

HIER = os.path.dirname(os.path.abspath(__file__))
DATEI = os.path.join(HIER, "comments.json")
SPERRE = os.path.join(HIER, "comments.lock")


def antwort(daten, status=200):
    body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Status: {status}\r\nContent-Type: application/json; charset=utf-8\r\n"
                            f"Cache-Control: no-store\r\nX-Robots-Tag: noindex\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def formular_lesen():
    """Liest POST-Daten (application/x-www-form-urlencoded oder multipart/form-data) ohne das cgi-Modul."""
    laenge = int(os.environ.get("CONTENT_LENGTH") or 0)
    if laenge <= 0 or laenge > 1_000_000:
        return {}
    roh = sys.stdin.buffer.read(laenge)
    typ = os.environ.get("CONTENT_TYPE", "")
    felder = {}
    if typ.startswith("multipart/form-data"):
        grenze = typ.split("boundary=", 1)[-1].strip().strip('"').encode()
        for teil in roh.split(b"--" + grenze)[1:]:
            if teil.strip() in (b"", b"--"):
                continue
            kopf, _, wert = teil.partition(b"\r\n\r\n")
            kopf = kopf.decode("utf-8", "replace")
            if 'name="' not in kopf:
                continue
            name = kopf.split('name="', 1)[1].split('"', 1)[0]
            felder[name] = wert.rstrip(b"\r\n").decode("utf-8", "replace")
    else:
        for k, v in parse_qs(roh.decode("utf-8", "replace"), keep_blank_values=True).items():
            felder[k] = v[0]
    return felder


def laden():
    try:
        with open(DATEI, encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, list) else []
    except (OSError, ValueError):
        return []


MODERATION = os.path.join(HIER, "moderation.json")


def _hash(schluessel: str) -> str:
    return hashlib.sha256((schluessel or "").encode("utf-8")).hexdigest()


def _moderation_hash() -> str:
    try:
        with open(MODERATION, encoding="utf-8") as f:
            return str(json.load(f).get("hash") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _darf(eintrag: dict, schluessel: str) -> bool:
    """Bearbeiten/Löschen: wer den Kommentar geschrieben hat (eigener Schlüssel) oder wer moderiert."""
    if not schluessel or len(schluessel) < 16:
        return False
    h = _hash(schluessel)
    return h == eintrag.get("sh") or (bool(_moderation_hash()) and h == _moderation_hash())


def _speichern(liste) -> bool:
    try:
        with open(DATEI, "w", encoding="utf-8") as f:
            json.dump(liste[-2000:], f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _oeffentlich(liste, seite=""):
    """Liste für Besucher: optional nur eine Seite (bei Portfolio-Exporten), Einträge ohne Seite gelten überall."""
    return [k for k in liste if not seite or not k.get("seite") or k.get("seite") == seite]


def beurteilung_lesen(form):
    """Felder einer Kompetenz-Beurteilung: Skala 1..10, Wert 0..Skala, Block, Knoten, Knotentitel."""
    try:
        skala, wert = int(form.get("skala", "")), int(form.get("wert", ""))
    except ValueError:
        return None
    if not (1 <= skala <= 10 and 0 <= wert <= skala):
        return None
    return {"art": "beurteilung", "skala": skala, "wert": wert, "block": form.get("block", "")[:40],
            "knoten": form.get("knoten", "")[:12], "knotenTitel": form.get("knotenTitel", "")[:300]}


def verarbeiten(methode: str, query: dict, form: dict, herkunft_roh: str, backend: str = "python"):
    """Logik für CGI (comments.py); als Funktion auch für Tests und lokale Server nutzbar. Gibt (status, daten) zurück."""
    if methode == "GET":
        if "ping" in query:
            return 200, {"ok": True, "backend": backend, "bearbeiten": True}
        return 200, _oeffentlich(laden(), query.get("seite", ""))
    if methode != "POST":
        return 405, {"fehler": "Nur GET und POST."}

    aktion = form.get("aktion", "")
    if aktion in ("bearbeiten", "loeschen", "pruefen"):
        liste = laden()
        kid, schluessel = form.get("id", ""), form.get("schluessel", "")
        if aktion == "pruefen":  # Moderationsschlüssel gültig?
            return 200, {"ok": bool(_moderation_hash()) and _hash(schluessel) == _moderation_hash()}
        treffer = next((k for k in liste if k.get("id") == kid), None)
        if not treffer:
            return 404, {"fehler": "Kommentar nicht gefunden."}
        if not _darf(treffer, schluessel):
            return 403, {"fehler": "Keine Berechtigung für diesen Kommentar."}
        if aktion == "loeschen":
            liste = [k for k in liste if k.get("id") != kid]
            return (200, {"ok": True}) if _speichern(liste) else (500, {"fehler": "Speichern nicht möglich."})
        text = form.get("text", "").strip()
        if len(text) > MAX_HTML:
            return 400, {"fehler": "Der Kommentar ist zu lang."}
        text = html_filtern(text)
        if treffer.get("art") == "beurteilung":
            b = beurteilung_lesen(form)
            if not b:
                return 400, {"fehler": "Ungültige Skala oder ungültiger Wert."}
            treffer.update(b)
        elif not nur_text(text) and "<img" not in text:
            return 400, {"fehler": "Bitte einen Kommentar eingeben."}
        treffer["text"] = text
        treffer["bearbeitet"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        return (200, {"ok": True, "kommentar": treffer}) if _speichern(liste) else (500, {"fehler": "Speichern nicht möglich."})

    name = form.get("name", "").strip()
    text = form.get("text", "").strip()
    if form.get("website", ""):
        return 200, {"ok": True}  # Bot: still ignorieren
    if len(text) > MAX_HTML or len(name) > 80:
        return 400, {"fehler": "Der Kommentar ist zu lang."}
    text = html_filtern(text)
    beurteilung = None
    if form.get("art") == "beurteilung":
        beurteilung = beurteilung_lesen(form)
        if not beurteilung:
            return 400, {"fehler": "Ungültige Skala oder ungültiger Wert."}
    elif not nur_text(text) and "<img" not in text:
        return 400, {"fehler": "Bitte einen Kommentar eingeben."}

    # Frequenzbremse über die Sperrdatei (Tages-Hash der Herkunft, nie in comments.json)
    herkunft = hashlib.sha256((herkunft_roh + datetime.now().strftime("%Y-%m-%d")).encode()).hexdigest()
    jetzt = int(time.time())
    try:
        with open(SPERRE, encoding="utf-8") as f:
            zeiten = json.load(f)
        if not isinstance(zeiten, dict):
            zeiten = {}
    except (OSError, ValueError):
        zeiten = {}
    if jetzt - int(zeiten.get(herkunft, 0)) < 10:
        return 429, {"fehler": "Bitte einen Moment warten."}
    zeiten = {k: v for k, v in zeiten.items() if jetzt - int(v) < 3600}
    zeiten[herkunft] = jetzt

    schluessel = secrets.token_urlsafe(18)  # bekommt nur die kommentierende Person (für Bearbeiten/Löschen)
    eintrag = {"id": secrets.token_hex(6), "zeit": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "name": name, "text": text, "sh": _hash(schluessel)}
    if beurteilung:
        eintrag.update(beurteilung)
    seite = form.get("seite", "")
    if seite.isalnum() and len(seite) <= 40:
        eintrag["seite"] = seite
    liste = laden()
    liste.append(eintrag)
    if not _speichern(liste):
        return 500, {"fehler": "Speichern zurzeit nicht möglich (Schreibrechte im Ordner prüfen)."}
    try:
        with open(SPERRE, "w", encoding="utf-8") as f:
            json.dump(zeiten, f)
    except OSError:
        pass
    return 200, {"ok": True, "kommentar": eintrag, "schluessel": schluessel}


def main():
    methode = os.environ.get("REQUEST_METHOD", "GET").upper()
    query = {k: v[0] for k, v in parse_qs(os.environ.get("QUERY_STRING", ""), keep_blank_values=True).items()}
    form = formular_lesen() if methode == "POST" else {}
    status, daten = verarbeiten(methode, query, form, os.environ.get("REMOTE_ADDR", ""))
    antwort(daten, status)


if __name__ == "__main__":
    main()
