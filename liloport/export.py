"""Export einer Seite als ZIP für einen Webserver: Zufallsname, nur genutzte Anhänge, ohne Metadaten."""
import base64
import hashlib
import html
import io
import json
import re
import secrets
import string
import struct
import zipfile
from datetime import date, datetime
from pathlib import Path

from . import aes, links
from .abgabe import pruefsumme, text as abgabe_text
from .assets import Assets
from .render import (TEMPLATES, STATIC, BlockRenderer, css_scopen, datum_lesbar, produktfuss_html,
                     rueckverweise_html, seiten_meta_html)
from .store import Store, StoreFehler

from .render import PROGRAMM  # noqa: E402

EXPORT_VORLAGEN = PROGRAMM / "export-templates"

_ZEICHEN = string.ascii_lowercase + string.digits


def zufallsname(laenge: int = 32) -> str:
    """Zufälliger Name aus a-z 0-9, nicht erratbar."""
    return "".join(secrets.choice(_ZEICHEN) for _ in range(laenge))


# ---------- Metadaten aus Bildern entfernen ----------

def jpeg_bereinigen(daten: bytes) -> bytes:
    """Entfernt EXIF, XMP, IPTC und Kommentare aus einem JPEG; Bilddaten bleiben unverändert."""
    if not daten.startswith(b"\xff\xd8"):
        return daten
    out, i = bytearray(b"\xff\xd8"), 2
    while i + 4 <= len(daten):
        if daten[i] != 0xff:
            break
        marker = daten[i + 1]
        if marker == 0xda:  # Start of Scan: Rest unverändert anhängen
            out += daten[i:]
            return bytes(out)
        laenge = struct.unpack(">H", daten[i + 2:i + 4])[0]
        segment = daten[i:i + 2 + laenge]
        # APP1 (EXIF/XMP), APP2…APP12 ausser APP0/APP14, APP13 (IPTC), COM entfernen
        if not (marker in (0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea, 0xeb, 0xec, 0xed, 0xfe)):
            out += segment
        i += 2 + laenge
    return bytes(out) + daten[i:]


def png_bereinigen(daten: bytes) -> bytes:
    """Entfernt Text-, Zeit- und EXIF-Chunks aus einem PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    if not daten.startswith(sig):
        return daten
    out, i = bytearray(sig), 8
    weg = {b"tEXt", b"iTXt", b"zTXt", b"tIME", b"eXIf"}
    while i + 8 <= len(daten):
        laenge = struct.unpack(">I", daten[i:i + 4])[0]
        typ = daten[i + 4:i + 8]
        ende = i + 12 + laenge
        if typ not in weg:
            out += daten[i:ende]
        i = ende
    return bytes(out)


def webp_bereinigen(daten: bytes) -> bytes:
    """Entfernt EXIF- und XMP-Chunks aus einem WebP (RIFF)."""
    if daten[:4] != b"RIFF" or daten[8:12] != b"WEBP":
        return daten
    out, i = bytearray(), 12
    while i + 8 <= len(daten):
        typ = daten[i:i + 4]
        laenge = struct.unpack("<I", daten[i + 4:i + 8])[0]
        ende = i + 8 + laenge + (laenge & 1)
        if typ not in (b"EXIF", b"XMP "):
            out += daten[i:ende]
        i = ende
    return b"RIFF" + struct.pack("<I", len(out) + 4) + b"WEBP" + bytes(out)


def bereinigen(daten: bytes, endung: str) -> bytes:
    """Wählt den passenden Reiniger nach Dateiendung."""
    return {"jpg": jpeg_bereinigen, "jpeg": jpeg_bereinigen, "png": png_bereinigen,
            "webp": webp_bereinigen}.get(endung.lower(), lambda d: d)(daten)


REINIGBAR = {"jpg", "jpeg", "png", "webp"}
BEREITS_KOMPRIMIERT = {"jpg", "jpeg", "png", "gif", "webp", "mp4", "webm", "pdf", "zip", "woff2"}
STUECK = 1024 * 1024


class Quelle:
    """Anhang aus dem Inhalte-Ordner, der erst beim Schreiben der ZIP gelesen wird.

    So liegt ein Export mit grossen Videos nie ganz im Arbeitsspeicher: Bilder werden einzeln bereinigt,
    alles andere stückweise kopiert."""

    def __init__(self, pfad: Path, endung: str):
        self.pfad, self.endung = pfad, endung.lower()

    def groesse(self) -> int:
        return self.pfad.stat().st_size

    def lesen(self) -> bytes:
        daten = self.pfad.read_bytes()
        return bereinigen(daten, self.endung) if self.endung in REINIGBAR else daten

    def stuecke(self):
        if self.endung in REINIGBAR:
            yield self.lesen()
            return
        with open(self.pfad, "rb") as f:
            while True:
                stueck = f.read(STUECK)
                if not stueck:
                    return
                yield stueck


def _groesse(daten) -> int:
    return len(daten) if isinstance(daten, (bytes, bytearray)) else daten.groesse()


def _bytes(daten) -> bytes:
    return daten if isinstance(daten, (bytes, bytearray)) else daten.lesen()


# ---------- Export ----------

class Exporter:
    """Baut die ZIP-Datei für eine Seite, ein Verzeichnis oder das ganze Portfolio."""

    def __init__(self, store: Store, assets: Assets, kommentare=None):
        self.store = store
        self.assets = assets
        self.kommentare = kommentare
        self.kompetenzen = None   # wird vom Server gesetzt; liefert die Rahmen für KR-Blöcke
        self.moderation = ""   # Schlüssel des letzten Exports (nur für die Antwort an die Oberfläche)

    # ---------- Einstieg ----------

    def exportieren(self, pfad: str, optionen: dict = None, ziel=None) -> tuple:
        """Eine Seite. Gibt (dateiname, zip_bytes, zufallsname) zurück; Schlüssel in self.moderation.
        Mit ziel (offene Datei) wird die ZIP dorthin geschrieben und statt der Bytes die Datei zurückgegeben."""
        seite = self.store.seite_laden(pfad)
        return self._paket([(pfad, seite, [])], seite["titel"], seite["slug"], optionen or {}, portfolio=False, ziel=ziel)

    def exportieren_mehrere(self, verzeichnis_id: str = "", optionen: dict = None, ziel=None) -> tuple:
        """Ein Verzeichnis samt Unterverzeichnissen ('' = alles) mit Inhaltsverzeichnis als Startseite."""
        site = self.store.site_laden()
        nach_id = {v["id"]: v for v in site["verzeichnisse"]}

        def ort(v):
            namen = []
            while v:
                namen.insert(0, v["name"])
                v = nach_id.get(v.get("eltern"))
            return namen

        def unter(vid):
            if not vid:
                return True
            v = nach_id.get(vid)
            return v is not None
        if verzeichnis_id and verzeichnis_id not in nach_id:
            raise StoreFehler("Verzeichnis nicht gefunden.")

        def gehoert_dazu(v):
            while v:
                if v["id"] == verzeichnis_id:
                    return True
                v = nach_id.get(v.get("eltern"))
            return not verzeichnis_id

        # Reihenfolge wie im Menü: Baum in Tiefe zuerst
        seiten = []

        def rek(eltern):
            kinder = sorted((v for v in site["verzeichnisse"] if v.get("eltern") == eltern),
                            key=lambda v: (v.get("reihenfolge", 0), v["name"].lower()))
            for v in kinder:
                if gehoert_dazu(v):
                    for slug in v["seiten"]:
                        if slug.startswith("->"):
                            continue
                        pfad = self.store.seiten_pfad(v, slug)
                        try:
                            seiten.append((pfad, self.store.seite_laden(pfad), ort(v)))
                        except StoreFehler:
                            pass
                rek(v["id"])
        rek(None)
        if not seiten:
            raise StoreFehler("In diesem Verzeichnis gibt es keine Seiten.")
        titel = nach_id[verzeichnis_id]["name"] if verzeichnis_id else site.get("titel") or "Portfolio"
        from . import slugs
        return self._paket(seiten, titel, slugs.slugify(titel), optionen or {}, portfolio=True, ziel=ziel)

    # ---------- Kern ----------

    def _paket(self, seiten: list, titel: str, slug: str, optionen: dict, portfolio: bool, ziel=None) -> tuple:
        site = self.store.site_laden()
        registry = self.assets.laden()
        ordner = f"export-{slug}-{date.today().isoformat()}"
        passwort = (optionen.get("passwort") or "").strip()
        mit_kommentaren = bool(optionen.get("kommentare", any(s.get("kommentare") for _p, s, _o in seiten)))
        abgabe = bool(optionen.get("abgabe"))
        # Moderations-Link: bei einer Abgabe immer aus – sonst könnte die abgebende Person Kommentare und
        # Beurteilungen der Lehrperson ändern oder löschen
        moderation_an = mit_kommentaren and not abgabe and optionen.get("moderation", True) is not False
        self.moderation = secrets.token_urlsafe(18) if moderation_an else ""
        self._moderation_aus = mit_kommentaren and not moderation_an

        namen = {pfad: zufallsname() for pfad, _s, _o in seiten}
        start = zufallsname() if portfolio else namen[seiten[0][0]]

        def ziel_fuer(pfad):
            return f"{namen[pfad]}.html" if pfad in namen else None

        # Anhänge aller Seiten, mit zufälligen Namen und ohne Metadaten
        export_registry, ersetzungen, dateien = {}, {}, {}
        for pfad, seite, _o in seiten:
            ids = Assets.ids_in_bloecken(seite.get("bloecke"))
            pfade_html = Assets.pfade_in_html(seite.get("bloecke"), seite.get("css"))
            for aid, e in registry.items():
                if aid in export_registry or not (aid in ids or e["datei"] in pfade_html):
                    continue
                quelle = self.store.sicherer_pfad(e["datei"])
                if not quelle.exists():
                    continue
                endung = quelle.suffix.lstrip(".")
                neu = f"assets/{zufallsname(16)}.{endung}"
                export_registry[aid] = dict(e, datei=neu)
                ersetzungen[e["datei"]] = neu
                dateien[neu] = Quelle(quelle, endung)

        # Seiten vorbereiten: Pfade in HTML/CSS ersetzen
        vorbereitet = []
        for pfad, seite, ort in seiten:
            bloecke = json.loads(json.dumps(seite.get("bloecke", [])))
            css = seite.get("css", "") or ""
            for alt, neu in ersetzungen.items():
                css = css.replace("../" + alt, neu).replace(alt, neu)
            for b in _alle(bloecke):
                if b.get("typ") == "html":
                    for alt, neu in ersetzungen.items():
                        b["html"] = b["html"].replace("../" + alt, neu).replace(alt, neu)
            vorbereitet.append({"pfad": pfad, "ort": ort, "titel": seite["titel"], "datum": seite.get("datum", ""),
                                "tags": seite.get("tags") or [], "menue": seite.get("menue", "voll"),
                                "css": css, "bloecke": bloecke, "slug": seite["slug"], "geaendert": seite.get("geaendert", ""),
                                "verweise": seite.get("verweise") is not False})

        # Abgabestempel über Inhalt und Dateien (ohne Kommentare)
        stempel = None
        if abgabe:
            stempel = {"zeit": datetime.now().astimezone().isoformat(timespec="minutes"),
                       "pruefsumme": pruefsumme(vorbereitet, dateien)}
            if mit_kommentaren:
                stempel["moderation"] = "aus"

        verweise = links.rueckverweise(self.store) if portfolio else {}
        rahmen_alle = self.kompetenzen.alle() if self.kompetenzen else {}
        reihenfolge = [v["pfad"] for v in vorbereitet]
        seiten_html, kommentare_alle = {}, []
        for i, v in enumerate(vorbereitet):
            name = namen[v["pfad"]]
            br = BlockRenderer(export_registry, "", export=True, ziel_fuer=ziel_fuer, rahmen=rahmen_alle,
                               beurteilung=abgabe and mit_kommentaren)
            inhalt = ""
            if portfolio:
                vor = reihenfolge[i - 1] if i > 0 else None
                nach = reihenfolge[i + 1] if i + 1 < len(reihenfolge) else None
                inhalt += _portfolio_nav(start, vor and (namen[vor], vorbereitet[i - 1]["titel"]),
                                         nach and (namen[nach], vorbereitet[i + 1]["titel"]))
            inhalt += f"<h1 class=\"seitentitel\">{html.escape(v['titel'])}</h1>\n"
            inhalt += _stempel_html(stempel)
            inhalt += _metazeile(v, site, optionen)
            inhalt += links.fussnoten("\n".join(br.block(b) for b in v["bloecke"]))
            if portfolio and v.get("verweise", True):
                inhalt += rueckverweise_html(verweise.get(v["pfad"], []), ziel_fuer)
            bisherige = []
            if mit_kommentaren and self.kommentare:
                bisherige = [dict(k, seite=name) for k in self.kommentare.laden(v["pfad"])]
                kommentare_alle += bisherige
            seiten_html[f"{name}.html"] = self._seite(name, v["titel"], v["slug"], v["css"], inhalt,
                                                      _kommentar_abschnitt(bisherige) if mit_kommentaren else "",
                                                      passwort, start)
        if portfolio:
            inhalt = (f"<h1 class=\"seitentitel\">{html.escape(titel)}</h1>\n" + _stempel_html(stempel)
                      + _inhaltsverzeichnis(vorbereitet, namen))
            seiten_html[f"{start}.html"] = self._seite(start, titel, "inhalt", "", inhalt, "", passwort, start)

        # Quelle für den Import zurück nach Liloport (nicht bei Passwortschutz)
        quelle = None
        if not passwort:
            felder = lambda v: {"titel": v["titel"], "datum": v["datum"], "tags": v["tags"], "menue": v["menue"],  # noqa: E731
                                "css": v["css"], "bloecke": v["bloecke"]}
            anhaenge = {aid: {"datei": e["datei"], "name": e["name"], "typ": e["typ"]} for aid, e in export_registry.items()}
            if portfolio:
                quelle = {"liloport": 2, "titel": titel, "anhaenge": anhaenge,
                          "seiten": [dict(felder(v), pfad=v["pfad"], ort=v["ort"], datei=f"{namen[v['pfad']]}.html") for v in vorbereitet]}
            else:
                quelle = dict(felder(vorbereitet[0]), liloport=1, pfad=vorbereitet[0]["pfad"], anhaenge=anhaenge,
                              datei=f"{start}.html")
            if stempel:
                quelle["abgabe"] = stempel

        # Alles, was in den Unterordner «inhalt/» kommt (das ist auch der Ordner für den Webserver)
        inhalt = {}
        for name, text in seiten_html.items():
            inhalt[name] = text.encode("utf-8")
        if quelle:
            inhalt["liloport.json"] = json.dumps(quelle, ensure_ascii=False, indent=2).encode("utf-8")
        if stempel:
            inhalt["ABGABE.txt"] = (abgabe_text(stempel["zeit"], stempel["pruefsumme"], titel)
                                    + (MODERATION_AUS_TEXT + "\n" if stempel.get("moderation") == "aus" else "")).encode("utf-8")
        inhalt["style.css"] = (STATIC / "style.css").read_bytes()
        for schrift in sorted(STATIC.glob("*.woff2")) + sorted(STATIC.glob("OFL-*.txt")):
            inhalt[schrift.name] = schrift.read_bytes()
        inhalt["robots.txt"] = b"User-agent: *\nDisallow: /\n"
        inhalt["LIESMICH.txt"] = _liesmich(start, bool(passwort), mit_kommentaren, portfolio, len(vorbereitet)).encode("utf-8")
        # Keine .js-Dateien in der ZIP: Windows blockiert sie beim Entpacken einer heruntergeladenen ZIP
        # («Windows-Sicherheitswarnung»), und manche Mailprogramme lehnen ZIPs mit .js ab. Die Skripte
        # stehen darum direkt in jeder Seite (siehe skripte_html), die Dateiliste in dateien.html.
        if mit_kommentaren:
            inhalt["comments.php"] = (EXPORT_VORLAGEN / "comments.php").read_bytes()
            inhalt["comments.py"] = (EXPORT_VORLAGEN / "comments.py").read_bytes()
            inhalt["comments.json"] = json.dumps(kommentare_alle, ensure_ascii=False, indent=2).encode("utf-8")
            # Nur der Hash des Moderationsschlüssels liegt auf dem Server; der Schlüssel selbst bleibt in Liloport
            inhalt["moderation.json"] = json.dumps(
                {"hash": hashlib.sha256(self.moderation.encode()).hexdigest()} if self.moderation
                else {"hash": "", "ausgeschaltet": "abgabe" if abgabe else "export"}).encode("utf-8")
        inhalt.update(dateien)
        dateiliste = sorted(inhalt) + [DATEIEN_HTML, "manifest.json"]
        inhalt["manifest.json"] = json.dumps({"dateien": dateiliste, "start": f"{start}.html"}, ensure_ascii=False).encode("utf-8")
        inhalt[DATEIEN_HTML] = dateien_html(inhalt)

        # In eine Datei (ziel) statt in den Arbeitsspeicher: Ein Portfolio kann viele Gigabyte gross sein.
        zipdaten = ziel if ziel is not None else io.BytesIO()
        fest = (1980, 1, 1, 0, 0, 0)  # keine echten Zeitstempel in der ZIP
        with zipfile.ZipFile(zipdaten, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            def schreiben(name, daten, ausfuehrbar=False):
                info = zipfile.ZipInfo(f"{ordner}/{name}", fest)
                # Bilder, Videos, PDFs sind schon komprimiert: nur speichern (viel schneller, kaum grösser)
                info.compress_type = (zipfile.ZIP_STORED if name.rsplit(".", 1)[-1].lower() in BEREITS_KOMPRIMIERT
                                      else zipfile.ZIP_DEFLATED)
                if ausfuehrbar:
                    info.external_attr = 0o755 << 16
                if isinstance(daten, (bytes, bytearray)):
                    z.writestr(info, daten)
                    return
                with z.open(info, "w", force_zip64=daten.groesse() > 1_000_000_000) as f:
                    for stueck in daten.stuecke():
                        f.write(stueck)
            # Auf oberster Ebene nur eine Datei zum Doppelklicken und der Ordner «inhalt»
            schreiben(STARTDATEI, startdatei_html(start).encode("utf-8"))
            for name in sorted(inhalt):
                schreiben("inhalt/" + name, inhalt[name], ausfuehrbar=(name == "comments.py"))
        if self.kommentare:
            for v in vorbereitet:
                self.kommentare.export_merken(namen[v["pfad"]], v["pfad"], moderation=self.moderation,
                                              start=start, portfolio=portfolio, titel=titel)
        return f"{ordner}.zip", (zipdaten if ziel is not None else zipdaten.getvalue()), start

    def _seite(self, name, titel, slug, css, inhalt, kommentar_html, passwort, start) -> str:
        """Eine exportierte HTML-Seite (bei Passwort verschlüsselt)."""
        stil = f"<style>\n{css_scopen(css, slug)}\n</style>" if (css or "").strip() else ""
        daten = {"liloport": 1, "export": name, "start": start}
        if getattr(self, "_moderation_aus", False):
            daten["moderation"] = False   # export.js nimmt dann keinen Moderationsschlüssel an
        meta = json.dumps(daten).replace("</", "<\\/")
        if passwort:
            geheim = aes.text_verschluesseln(passwort, stil + "\n" + inhalt + "\n" + kommentar_html + '\n<footer class="export-leiste"></footer>')
            nutzlast = {"salt": base64.b64encode(geheim["salt"]).decode(), "iv": base64.b64encode(geheim["iv"]).decode(),
                        "daten": base64.b64encode(geheim["daten"]).decode(), "iterationen": geheim["iterationen"],
                        "titel": titel, "slug": slug}
            return ((TEMPLATES / "export_passwort.html").read_text(encoding="utf-8")
                    .replace("{{SKRIPTE}}", skripte_html())
                    .replace("{{GEHEIM}}", json.dumps(nutzlast, ensure_ascii=False).replace("</", "<\\/"))
                    .replace("{{META}}", meta).replace("{{PRODUKTFUSS}}", produktfuss_html("", export=True)))
        text = (TEMPLATES / "export.html").read_text(encoding="utf-8")
        for k, v in {"{{SKRIPTE}}": skripte_html(), "{{TITEL}}": html.escape(titel), "{{SLUG}}": html.escape(slug), "{{STIL}}": stil, "{{INHALT}}": inhalt,
                     "{{KOMMENTARE}}": kommentar_html, "{{META}}": meta,
                     "{{PRODUKTFUSS}}": produktfuss_html("", export=True)}.items():
            text = text.replace(k, v)
        return text


STARTDATEI = "Seite öffnen.html"
EINBETTEN_MAX = 60 * 1024 * 1024   # so viel passt in dateien.html (für «Herunterladen» aus einer lokalen Kopie)


STARTHINWEIS = ("Öffnet sich die Seite nicht oder ohne Gestaltung, wurde die ZIP-Datei vermutlich nicht entpackt. "
                "Windows: Rechtsklick auf die ZIP-Datei › «Alle extrahieren…»; Mac: Doppelklick. "
                "Danach im entpackten Ordner «Seite öffnen» doppelklicken.")


def startdatei_html(start: str) -> str:
    """Die eine Datei auf oberster Ebene: öffnet per Doppelklick die (Start-)Seite im Ordner «inhalt»."""
    ziel = f"inhalt/{start}.html"
    return (f'<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8"><title>Seite öffnen</title>'
            f'<meta http-equiv="refresh" content="0; url={ziel}"></head>'
            f'<body style="font-family:system-ui,sans-serif;margin:3em;max-width:40em"><p><a href="{ziel}">Seite öffnen</a></p>'
            f'<p>{STARTHINWEIS}</p></body></html>\n')


DATEIEN_HTML = "dateien.html"


def skripte_html() -> str:
    """comment-editor.js und export.js als Inline-Skripte für jede exportierte Seite."""
    teile = []
    for name in ("comment-editor.js", "export.js"):
        js = (EXPORT_VORLAGEN / name).read_text(encoding="utf-8")
        js = re.sub(r"</(script)", r"<\\/\1", js, flags=re.I).replace("<!--", "<\\!--")
        teile.append(f"<script>/* {name} */\n{js}</script>")
    return "\n".join(teile)


def dateien_html(inhalt: dict) -> bytes:
    """Alle Dateien (base64) in einer kleinen HTML-Datei. Ein Browser darf aus einer lokalen Datei die
    Nachbardateien nicht lesen, sie aber in einem unsichtbaren Rahmen öffnen; die Datei schickt ihren Inhalt
    dann per postMessage an die Seite. So liefert «Herunterladen» auch aus einer per Doppelklick geöffneten
    Kopie die vollständige ZIP. Sehr grosse Dateien bleiben draussen und werden als «fehlend» vermerkt."""
    dateien, fehlend, gesamt = {}, [], 0
    for name, daten in sorted(inhalt.items(), key=lambda x: _groesse(x[1])):
        if name in (DATEIEN_HTML, "dateien.js"):
            continue
        if gesamt + _groesse(daten) <= EINBETTEN_MAX:
            roh = _bytes(daten)
            dateien[name] = base64.b64encode(roh).decode("ascii")
            gesamt += len(roh)
        else:
            fehlend.append(name)
    nutzlast = json.dumps({"dateien": dateien, "fehlend": fehlend}).replace("</", "<\\/")
    return dateien_rahmen(nutzlast).encode("utf-8")


def dateien_rahmen(nutzlast: str) -> str:
    # Gleicher Text wie dateienHtml() in export.js
    return ('<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
            '<title>Liloport – Hilfsdatei</title></head><body style="font-family:system-ui,sans-serif;margin:3em">'
            '<p>Hilfsdatei von Liloport für «Herunterladen». Bitte nicht löschen; zum Ansehen «Seite öffnen» verwenden.</p>'
            '<script>(function(){var d=' + nutzlast + ';if(window.parent===window)return;'
            'var ziel=location.protocol==="file:"?"*":location.origin;'
            'window.parent.postMessage({liloportDateien:d},ziel);})();</script></body></html>\n')


def _alle(bloecke):
    for b in bloecke:
        yield b
        if b.get("typ") == "spalten":
            for sp in b.get("spalten", []):
                yield from _alle(sp)


def _metazeile(seite: dict, site: dict, optionen: dict) -> str:
    """Tags immer; Autor und Datum nur, wenn ausdrücklich eingeschaltet."""
    teile = []
    einstellungen = site.get("export", {})
    if optionen.get("autorAnzeigen") and einstellungen.get("autor"):
        teile.append(f'<span class="autor">{html.escape(einstellungen["autor"])}</span>')
    if optionen.get("idAnzeigen") and einstellungen.get("id"):
        teile.append(f'<span class="autor-id" title="Identifikationsnummer">{html.escape(einstellungen["id"])}</span>')
    meta = seiten_meta_html(seite, None, datum=bool(optionen.get("datumAnzeigen")))
    if teile:
        inhalt = meta[len('<p class="seiten-meta">'):-len("</p>")] if meta else ""
        return f'<p class="seiten-meta">{" · ".join(teile)}{" · " if inhalt else ""}{inhalt}</p>\n'
    return meta + "\n" if meta else ""


MODERATION_AUS_KURZ = ("Moderations-Link ausgeschaltet: Kommentare und Beurteilungen kann nur ändern oder löschen, "
                       "wer sie geschrieben hat.")
MODERATION_AUS_TEXT = ("Moderation: ausgeschaltet. Die abgebende Person hat keinen Moderations-Link; Kommentare und\n"
                       "Beurteilungen kann nur ändern oder löschen, wer sie geschrieben hat.")


def _stempel_html(stempel) -> str:
    if not stempel:
        return ""
    z = stempel["zeit"]
    lesbar = f"{z[8:10]}.{z[5:7]}.{z[0:4]}, {z[11:16]} Uhr"
    mod = (f'<br><span class="abgabe-moderation">{html.escape(MODERATION_AUS_KURZ)}</span>'
           if stempel.get("moderation") == "aus" else "")
    return (f'<div class="abgabe-stempel"><strong>Abgabe</strong> · exportiert am {lesbar}<br>'
            f'Prüfsumme (SHA-256): <code>{stempel["pruefsumme"]}</code>{mod}</div>\n')


def _portfolio_nav(start, vor, nach) -> str:
    teile = [f'<a href="{start}.html">☰ Inhaltsverzeichnis</a>']
    rechts = []
    if vor:
        rechts.append(f'<a href="{vor[0]}.html">‹ {html.escape(vor[1])}</a>')
    if nach:
        rechts.append(f'<a href="{nach[0]}.html">{html.escape(nach[1])} ›</a>')
    return f'<nav class="portfolio-nav">{teile[0]}<span>{" · ".join(rechts)}</span></nav>\n'


def _inhaltsverzeichnis(vorbereitet, namen) -> str:
    """Startseite eines Portfolio-Exports: Seiten nach Verzeichnissen gruppiert."""
    teile, zuletzt = ['<nav class="portfolio-inhalt"><ul>'], None
    for v in vorbereitet:
        ort = " › ".join(v["ort"])
        if ort != zuletzt:
            if zuletzt is not None:
                teile.append("</ul></li>")
            teile.append(f'<li><span class="verz-name">{html.escape(ort)}</span><ul>')
            zuletzt = ort
        datum = f' <span class="klein-text">{datum_lesbar(v["datum"])}</span>' if v.get("datum") else ""
        teile.append(f'<li><a href="{namen[v["pfad"]]}.html">{html.escape(v["titel"])}</a>{datum}</li>')
    if zuletzt is not None:
        teile.append("</ul></li>")
    teile.append("</ul></nav>")
    return "".join(teile)


def _kommentar_abschnitt(bisherige: list) -> str:
    """Kommentarbereich der exportierten Seite: Liste (von export.js gefüllt) und Formular."""
    eingebettet = json.dumps(bisherige, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<section class="kommentare" id="kommentare">'
        '<h2>Kommentare</h2>'
        '<div id="kommentar-liste"></div>'
        '<form id="kommentar-form" class="kommentar-form" autocomplete="off">'
        '<label>Name (freiwillig)<input type="text" name="name" maxlength="80"></label>'
        '<label>Kommentar<textarea name="text" rows="4" maxlength="20000" required></textarea></label>'
        '<input type="text" name="website" class="honig" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<div class="feld-zeile"><button type="submit" class="knopf primaer">Kommentar senden</button>'
        '<span class="kommentar-status klein-text"></span></div>'
        '<p class="klein-text">Formatierung und HTML sind erlaubt (ohne Skripte). Gespeichert werden nur Name, Text und Zeit. '
        'Eigene Kommentare kannst du in diesem Browser später bearbeiten oder löschen.</p>'
        '</form>'
        f'<script type="application/json" id="liloport-kommentare">{eingebettet}</script>'
        '</section>'
    )


def _liesmich(name: str, passwort: bool, kommentare: bool = False, portfolio: bool = False, anzahl: int = 1) -> str:
    return (
        "Liloport-Export" + (f" (Portfolio mit {anzahl} Seiten)" if portfolio else "") + "\n\n"
        "ZUERST ENTPACKEN\n"
        "  Die ZIP-Datei vor dem Öffnen entpacken – nicht im ZIP-Fenster doppelklicken. Windows öffnet dort\n"
        "  nur die eine Datei; die Seite erscheint dann ohne Gestaltung.\n"
        "  Windows: Rechtsklick auf die ZIP-Datei › «Alle extrahieren…». Mac: Doppelklick. Linux: «Hier entpacken».\n\n"
        "ANSEHEN UND KOMMENTIEREN\n"
        "  Eine Ebene höher «Seite öffnen» doppelklicken. Die Seite öffnet sich im Browser, ohne Internet\n"
        "  und ohne Zusatzprogramm. Kommentare werden in diesem Browser gespeichert; «Herunterladen» unten\n"
        "  auf der Seite liefert wieder die vollständige ZIP – samt Kommentaren –, zum Weitergeben per E-Mail\n"
        "  oder für den Import in Liloport (Dashboard → Neu → Seite aus ZIP importieren).\n\n"
        "AUF EINEN WEBSERVER STELLEN (z. B. den Webspace, den die Hochschule bereitstellt)\n"
        "1. Diesen Ordner «inhalt» auf den Webserver kopieren (per SFTP oder Hosting-Oberfläche);\n"
        "   er darf dabei umbenannt werden.\n"
        f"2. Die {'Startseite' if portfolio else 'Seite'} ist dann erreichbar unter: https://<server>/<ordner>/{name}.html\n"
        "   Der Name ist absichtlich lang und zufällig: Nur wer die Adresse kennt, findet die Seite.\n"
        "   Den Link zum Beispiel per E-Mail weitergeben.\n"
        "3. Suchmaschinen werden per robots.txt und noindex ferngehalten.\n"
        + ("4. Die Seite ist passwortgeschützt. Der Inhalt ist verschlüsselt und wird erst im Browser nach\n"
           "   Eingabe des Passworts entschlüsselt. Das funktioniert über https:// (oder lokal per Doppelklick),\n"
           "   nicht über unverschlüsseltes http://. Ein vergessenes Passwort kann nicht wiederhergestellt werden.\n"
           "   Kommentare in comments.json sind nicht verschlüsselt.\n"
           if passwort else "")
        + ("5. Kommentare: Kann der Server PHP (comments.php) oder Python-CGI (comments.py; Datei ausführbar,\n"
           "   Ordner beschreibbar), werden Kommentare in comments.json auf dem Server gespeichert und sind für\n"
           "   alle sichtbar. Sonst bleiben sie im Browser der kommentierenden Person und kommen über\n"
           "   «Herunterladen» zurück. Eigene Kommentare lassen sich im selben Browser bearbeiten und löschen;\n"
           "   die Autorin oder der Autor moderiert mit dem Moderations-Link aus dem Export-Dialog\n"
           "   (bei einer Abgabe ist der Moderations-Link ausgeschaltet).\n"
           if kommentare else "")
        + "\nPersönliche Daten: Autor, Zeitstempel und Bild-Metadaten (EXIF) wurden entfernt,\n"
        "sofern sie im Export-Dialog nicht ausdrücklich eingeschaltet wurden.\n"
    )
