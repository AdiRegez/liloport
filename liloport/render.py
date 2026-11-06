"""Erzeugt aus JSON die HTML-Seiten, Redirect-Seiten, das Dashboard und menu.js."""
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote as urlquote

from . import kompetenzen, links, sanitize
from .store import INTERN, Store

# Als PyInstaller-Programm liegen templates/ und static/ im entpackten Bündel (sys._MEIPASS)
PROGRAMM = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
TEMPLATES = PROGRAMM / "templates"
STATIC = PROGRAMM / "static"
BREITEN = ("voll", "halb", "klein")
AUSRICHTUNGEN = ("links", "mitte", "rechts")
TRENNER_ARTEN = {"gestrichelt": "dashed", "gepunktet": "dotted", "doppelt": "double"}
GLIEDERUNGEN = ("linien", "flaechen", "nummern")   # Profi: Hierarchie der Überschriften sichtbar machen
_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")
_LEERE_TAGS = {"br", "hr", "img", "input", "wbr"}
_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _ganzzahl(wert, kleinste, groesste):
    """Ganzzahl im Bereich oder None (defensiv: auch importierte Blöcke rendern sicher)."""
    try:
        zahl = int(wert)
    except (TypeError, ValueError):
        return None
    return zahl if kleinste <= zahl <= groesste else None


def trenner_stil(b: dict) -> str:
    """Inline-Stil eines Trenners (Farbe, Dicke, Linienart, Abstand oben/unten); leer bei Standardwerten."""
    teile = []
    farbe = str(b.get("farbe") or "")
    if not _FARBE.match(farbe):
        farbe = ""
    art = TRENNER_ARTEN.get(b.get("stil"))
    dicke = _ganzzahl(b.get("dicke"), 1, 20)
    if farbe or art or dicke:
        breite = dicke or 1
        if art == "double":
            breite = max(breite, 3)   # eine Doppellinie braucht mindestens 3 Pixel
        teile.append(f"border-top:{breite}px {art or 'solid'} {farbe or 'var(--pg-rand)'}")
    oben = _ganzzahl(b.get("abstandOben"), 0, 200)
    if oben is not None:
        teile.append(f"margin-top:{oben}px")
    unten = _ganzzahl(b.get("abstandUnten"), 0, 200)
    if unten is not None:
        teile.append(f"margin-bottom:{unten}px")
    return f' style="{";".join(teile)}"' if teile else ""


def _vorlage(name: str) -> str:
    """Liest eine Vorlage aus templates/."""
    return (TEMPLATES / name).read_text(encoding="utf-8")


def relativ_zur_wurzel(pfad: str) -> str:
    """Gibt für einen Seitenpfad (ordner/slug) das Präfix bis zur Wurzel zurück, z. B. ../../."""
    return "../" * pfad.count("/")


def css_scopen(css: str, slug: str) -> str:
    """Stellt jedem Selektor .seite-<slug> voran; @media-Blöcke werden rekursiv behandelt."""
    praefix = f".seite-{slug} "
    css = re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)
    css = re.sub(r"(?i)<(/?)(style|script)", r"\\3C \1\2", css)  # kein Ausbruch aus <style>
    ergebnis, i = [], 0
    while i < len(css):
        m = re.search(r"([^{}]*)\{", css[i:])
        if not m:
            ergebnis.append(css[i:])
            break
        kopf = m.group(1).strip()
        start = i + m.end()
        tiefe, j = 1, start
        while j < len(css) and tiefe:
            tiefe += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        koerper = css[start:j - 1]
        if kopf.startswith("@media") or kopf.startswith("@supports"):
            ergebnis.append(f"{kopf} {{{css_scopen(koerper, slug)}}}")
        elif kopf.startswith("@"):
            ergebnis.append(f"{kopf} {{{koerper}}}")
        else:
            selektoren = [praefix + s.strip() for s in kopf.split(",") if s.strip()]
            ergebnis.append(f"{', '.join(selektoren)} {{{koerper}}}")
        i = j
    return "\n".join(ergebnis)


class BlockRenderer:
    """Rendert Blöcke; braucht die Asset-Registry für Dateipfade."""

    def __init__(self, registry: dict, rel: str, export: bool = False, ziel_fuer=None, rahmen: dict = None, pfad: str = "",
                 beurteilung: bool = False):
        self.registry = registry
        self.rel = rel
        self.export = export  # auf dem Webserver: Dateien verlinken statt Ordner öffnen
        self.rahmen = rahmen or {}   # Kompetenzrahmen {id: kr} für KR-Blöcke
        self.pfad = pfad
        self.beurteilung = beurteilung   # Export «als Abgabe»: Kompetenzen zur Bewertung freigeben
        # interne Links lp:pfad → Adresse; Standard: relativ zur Seite
        self.ziel_fuer = ziel_fuer or (lambda pfad: f"{rel}{pfad}.html")

    def _asset(self, block):
        e = self.registry.get(block.get("asset") or "")
        if not e:
            return None
        return e

    def _fehlt(self, bid, typ, text):
        return (f'<section class="block block-{typ} block-fehlt" data-id="{bid}" data-typ="{typ}">'
                f'<p class="hinweis">{html.escape(text)}</p></section>')

    def block(self, b: dict) -> str:
        """Rendert einen Block, bei Bedarf als auf der Seite einklappbaren Bereich."""
        inner = self._block(b)
        if b.get("klapp") in ("offen", "zu"):
            titel = html.escape(b.get("klappTitel") or _klapp_titel(b))
            offen = " open" if b["klapp"] == "offen" else ""
            return (f'<details class="klapp" data-id="{html.escape(str(b.get("id", "")), quote=True)}"{offen}>'
                    f'<summary>{titel}</summary><div class="klapp-inhalt">{inner}</div></details>')
        return inner

    def bloecke(self, liste: list, gliederung: str = "") -> str:
        """Rendert die Blöcke einer Seite, verschachtelt nach Überschriften (siehe gliedern)."""
        liste = [b for b in (liste or []) if isinstance(b, dict)]
        # Standard (auch Amateur): Kapitel links bündig, Überschriften in der Farbe ihrer Ebene
        return gliedern(liste, self, gliederung if gliederung in GLIEDERUNGEN else "standard")

    def _text_inhalt(self, b: dict) -> str:
        inhalt = links.aufloesen(sanitize.filtern(b.get("html", ""), "profi"), self.ziel_fuer)
        # Breite Tabellen scrollen in ihrem Rahmen, statt über das Seitenlayout hinauszuragen
        return inhalt.replace("<table", '<div class="tabelle-rahmen"><table').replace("</table>", "</table></div>")

    def _block(self, b: dict) -> str:
        """Rendert einen Block; unbekannte Typen ergeben einen Hinweis."""
        bid = html.escape(str(b.get("id", "")), quote=True)
        typ = b.get("typ", "text")
        if typ == "text":
            inhalt = self._text_inhalt(b)
            return f'<section class="block block-text" data-id="{bid}" data-typ="text">{inhalt}</section>'
        if typ == "trenner":
            return f'<hr class="block block-trenner" data-id="{bid}" data-typ="trenner"{trenner_stil(b)}>'
        if typ == "galerie":
            bilder = [x for x in (b.get("bilder") or []) if isinstance(x, dict)]
            n = _ganzzahl(b.get("spalten"), 2, 4) or 3
            teile = []
            for x in bilder:
                e = self.registry.get(str(x.get("asset") or ""))
                if not e:
                    continue
                text = html.escape(x.get("bildtext", "") or "")
                cap = f"<figcaption>{text}</figcaption>" if text else ""
                teile.append(f'<figure class="galerie-bild"><img src="{self.rel}{html.escape(e["datei"], quote=True)}" '
                             f'alt="{text}" loading="lazy">{cap}</figure>')
            if not teile:
                return self._fehlt(bid, "galerie", "Noch keine Bilder in der Galerie gewählt.")
            return f'<div class="block block-galerie galerie-{n}" data-id="{bid}" data-typ="galerie">{"".join(teile)}</div>'
        if typ == "bild":
            e = self._asset(b)
            if not e:
                return self._fehlt(bid, "bild", "Bild noch nicht gewählt.")
            breite = b.get("breite", "voll")
            ausrichtung = b.get("ausrichtung", "links")
            klasse = (f"breite-{breite}" if breite in BREITEN else "breite-frei") + f" ausr-{ausrichtung if ausrichtung in AUSRICHTUNGEN else 'links'}"
            stil = "" if breite in BREITEN else f' style="width:{html.escape(str(breite), quote=True)}"'
            text = html.escape(b.get("bildtext", ""))
            cap = f"<figcaption>{text}</figcaption>" if text else ""
            return (f'<figure class="block block-bild {klasse}" data-id="{bid}" data-typ="bild"{stil}>'
                    f'<img src="{self.rel}{html.escape(e["datei"], quote=True)}" alt="{text}">{cap}</figure>')
        if typ == "video":
            e = self._asset(b)
            if not e:
                return self._fehlt(bid, "video", "Video noch nicht gewählt.")
            return (f'<figure class="block block-video" data-id="{bid}" data-typ="video">'
                    f'<video controls preload="metadata" src="{self.rel}{html.escape(e["datei"], quote=True)}"></video>'
                    f'{druck_hinweis("Video", "In der digitalen Version ist hier ein Video eingebunden", e["name"])}</figure>')
        if typ == "audio":
            e = self._asset(b)
            if not e:
                return self._fehlt(bid, "audio", "Audio-Datei noch nicht gewählt.")
            return (f'<figure class="block block-audio" data-id="{bid}" data-typ="audio">'
                    f'<audio controls preload="metadata" src="{self.rel}{html.escape(e["datei"], quote=True)}"></audio>'
                    f'<figcaption>{html.escape(e["name"])}</figcaption>'
                    f'{druck_hinweis("Audio", "In der digitalen Version kann hier eine Audioaufnahme abgespielt werden", e["name"])}</figure>')
        if typ == "pdf":
            e = self._asset(b)
            if not e:
                return self._fehlt(bid, "pdf", "PDF noch nicht gewählt.")
            hoehe = int(b.get("hoehe") or 600)
            try:
                startseite = int(b.get("seite") or 1)
            except (TypeError, ValueError):
                startseite = 1
            anker = f"#page={startseite}" if startseite > 1 else ""   # vom PDF-Betrachter des Browsers ausgewertet
            src = f'{self.rel}{html.escape(e["datei"], quote=True)}{anker}'
            ordner = html.escape(e["datei"].rsplit("/", 1)[0], quote=True)
            link = (f'<a href="{src}" target="_blank" rel="noopener">PDF öffnen</a>' if self.export
                    else f'<a href="{self.rel}{ordner}/" class="ordner-link" data-ordner="{ordner}">Im Ordner öffnen</a>')
            return (f'<figure class="block block-pdf" data-id="{bid}" data-typ="pdf">'
                    f'<iframe src="{src}" style="height:{hoehe}px" title="{html.escape(e["name"])}"></iframe>'
                    f'<figcaption>{html.escape(e["name"])} · {link}</figcaption>'
                    f'{druck_hinweis("PDF", "In der digitalen Version ist hier ein PDF-Dokument eingebettet, das sich durchblättern lässt" + (f" (ab Seite {startseite})" if startseite > 1 else ""), e["name"])}</figure>')
        if typ == "datei":
            e = self._asset(b)
            if not e:
                return self._fehlt(bid, "datei", "Datei noch nicht gewählt.")
            ordner = html.escape(e["datei"].rsplit("/", 1)[0], quote=True)
            groesse = e.get("groesse", 0)
            einheit = f"{groesse / 1048576:.1f} MB" if groesse > 1048576 else f"{max(1, groesse // 1024)} KB"
            if self.export:
                href, klasse, info = f'{self.rel}{html.escape(e["datei"], quote=True)}', 'datei-karte', f'{einheit} · ZIP-Archiv · herunterladen'
                extra = ' download'
            else:
                href, klasse, info = f'{self.rel}{ordner}/', 'datei-karte ordner-link', f'{einheit} · ZIP-Archiv · im Ordner öffnen'
                extra = f' data-ordner="{ordner}" title="Öffnet den Ordner, in dem die Datei liegt"'
            return (f'<div class="block block-datei" data-id="{bid}" data-typ="datei">'
                    f'<a href="{href}" class="{klasse}"{extra}>'
                    f'<span class="datei-symbol">🗜</span><span class="datei-name">{html.escape(e["name"])}</span>'
                    f'<span class="datei-info">{info}</span></a>'
                    f'{druck_hinweis("ZIP-Archiv", f"In der digitalen Version kann hier eine Datei ({einheit}) heruntergeladen werden", e["name"])}</div>')
        if typ == "button":
            text = html.escape(b.get("text") or "Link")
            ziel = html.escape(links.ziel_aufloesen(b.get("ziel") or "", self.ziel_fuer) or "#", quote=True)
            neu = ' target="_blank" rel="noopener"' if ziel.startswith(("http://", "https://")) else ""
            stil = b.get("stil") if b.get("stil") in ("voll", "umrandet") else "voll"
            ausrichtung = b.get("ausrichtung") if b.get("ausrichtung") in AUSRICHTUNGEN else "links"
            extern = ziel.startswith(("http://", "https://"))
            ziel_text = (f'Schaltfläche · führt in der digitalen Version zu <span class="druck-url">{ziel}</span>' if extern
                         else "Schaltfläche · führt in der digitalen Version zu einer verlinkten Seite")
            return (f'<div class="block block-button ausr-{ausrichtung}" data-id="{bid}" data-typ="button">'
                    f'<a class="seiten-button stil-{stil}" href="{ziel}"{neu}>{text}</a>'
                    f'<span class="druck-nur druck-button-info">{ziel_text}</span></div>')
        if typ == "spalten":
            spalten = b.get("spalten") or [[], []]
            n = max(2, min(4, len(spalten)))
            inner = "".join(f'<div class="spalte">{"".join(self.block(x) for x in sp)}</div>' for sp in spalten[:n])
            return f'<div class="block block-spalten spalten-{n}" data-id="{bid}" data-typ="spalten">{inner}</div>'
        if typ == "html":
            roh = b.get("html", "") or ""
            interaktiv = re.search(r"<(iframe|video|audio|embed|object|canvas|script)\b", roh, re.I)
            hinweis = druck_hinweis("Eingebetteter Inhalt", "In der digitalen Version ist hier ein interaktiver oder eingebetteter Inhalt zu sehen") if interaktiv else ""
            return f'<div class="block block-html" data-id="{bid}" data-typ="html">{links.aufloesen(roh, self.ziel_fuer)}{hinweis}</div>'
        if typ == "kr":
            # lokal: Schalter (reader.js aktiviert sie nur mit laufendem Liloport); Export: nur der Stand
            return kompetenzen.block_html(b, self.rahmen, self.rel, bid, bearbeitbar=None if self.export else True, pfad=self.pfad,
                                          beurteilung=self.beurteilung)
        return self._fehlt(bid, html.escape(typ), f"Blocktyp «{typ}» ist nicht verfügbar.")


def druck_hinweis(art: str, text: str, name: str = "") -> str:
    """Kasten, der nur im Druck erscheint: Was in der digitalen Version an dieser Stelle mehr zu sehen ist."""
    datei = f' <span class="druck-hinweis-name">«{html.escape(name)}»</span>' if name else ""
    return (f'<p class="druck-nur druck-hinweis"><span class="druck-hinweis-art">{html.escape(art)}</span>'
            f'<span class="druck-hinweis-text">{html.escape(text)}{":" if name else "."}{datei}</span></p>')


def _ueberschriften_teilen(inhalt: str) -> list:
    """Teilt das HTML eines Textblocks an Überschriften der obersten Ebene.

    Liefert [(ebene, html), …]; ebene 0 für Text vor der ersten Überschrift, sonst 1–4 (h1–h4).
    Das HTML kommt aus dem Filter und ist darum sauber verschachtelt."""
    teile, start, ebene, tiefe = [], 0, 0, 0
    for m in _TAG.finditer(inhalt):
        zu, name, selbst = m.group(1), m.group(2).lower(), m.group(3)
        if name in _LEERE_TAGS or selbst:
            continue
        if zu:
            tiefe = max(0, tiefe - 1)
            continue
        if tiefe == 0 and name in ("h1", "h2", "h3", "h4"):
            if inhalt[start:m.start()].strip():
                teile.append((ebene, inhalt[start:m.start()].strip()))
            start, ebene = m.start(), int(name[1])
        tiefe += 1
    if inhalt[start:].strip():
        teile.append((ebene, inhalt[start:].strip()))
    return teile


def gliedern(liste: list, br: "BlockRenderer", gliederung: str) -> str:
    """Macht die Hierarchie der Überschriften sichtbar: Jede Überschrift (h1–h4 in Textblöcken der obersten
    Ebene) eröffnet einen Abschnitt <section class="gl-abschnitt gl-hN">, der alles bis zur nächsten
    Überschrift gleicher oder höherer Ordnung umschliesst – auch Bilder, Spalten und andere Blöcke dazwischen.
    Textblöcke mit mehreren Überschriften werden dafür an den Überschriften aufgeteilt. Einklappbare Blöcke
    und Spalten bleiben ganz (ihre Überschriften zählen nicht). Funktioniert ohne JavaScript, auch im Export."""
    aus, offen, zaehler = [], [], []   # offen: Ebenen der offenen Abschnitte; zaehler: Nummern je Tiefe

    def schliessen(bis_ebene):
        while offen and offen[-1] >= bis_ebene:
            offen.pop()
            aus.append("</section>")

    for b in liste:
        if b.get("typ") != "text" or b.get("klapp") in ("offen", "zu"):
            aus.append(br.block(b))
            continue
        bid = html.escape(str(b.get("id", "")), quote=True)
        for i, (ebene, teil) in enumerate(_ueberschriften_teilen(br._text_inhalt(b)) or [(0, "")]):
            if ebene:
                schliessen(ebene)
                tiefe = len(offen)
                del zaehler[tiefe + 1:]
                if len(zaehler) <= tiefe:
                    zaehler.append(0)
                zaehler[tiefe] += 1
                nummer = ".".join(str(n) for n in zaehler[:tiefe + 1])
                if gliederung == "nummern":
                    teil = re.sub(r"^(<h[1-4][^>]*>)", lambda m: f'{m.group(1)}<span class="gl-nr">{nummer}</span> ', teil, count=1)
                aus.append(f'<section class="gl-abschnitt gl-h{ebene} gl-tiefe-{tiefe + 1}" data-gliederung="{nummer}">')
                offen.append(ebene)
            kennung = f' data-id="{bid}"' if i == 0 else ""
            aus.append(f'<section class="block block-text{"" if i == 0 else " block-text-teil"}"{kennung} data-typ="text">{teil}</section>')
    schliessen(0)
    return f'<div class="gliederung gl-{gliederung}">\n' + "\n".join(aus) + "\n</div>"


def _klapp_titel(b: dict) -> str:
    """Ersatztitel für einklappbare Blöcke ohne eigenen Titel: erste Überschrift, sonst Blocktyp."""
    if b.get("typ") in ("text", "html"):
        m = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", b.get("html", ""), re.S | re.I)
        if m:
            return re.sub(r"<[^>]+>", "", m.group(1)).strip()[:120] or "Abschnitt"
        text = re.sub(r"<[^>]+>", " ", b.get("html", "")).strip()
        return (text[:60] + "…") if len(text) > 60 else (text or "Abschnitt")
    if b.get("typ") == "bild":
        return b.get("bildtext") or "Bild"
    if b.get("typ") == "button":
        return b.get("text") or "Button"
    return {"video": "Video", "audio": "Audio", "pdf": "PDF", "datei": "Datei", "spalten": "Spalten",
            "galerie": "Galerie", "trenner": "Abschnitt"}.get(b.get("typ"), "Abschnitt")


def produkt_laden() -> dict:
    """Liest produkt.json aus dem Programm-Ordner (Name, Version, GitHub, DOI, Lizenz, Impressum)."""
    datei = PROGRAMM / "produkt.json"
    standard = {"name": "Liloport", "untertitel": "Lifelong-Learning-Portfolio", "version": "", "github": "", "doi": "",
                "lizenz": "MIT", "lizenzUrl": "https://opensource.org/licenses/MIT", "impressum": {}}
    try:
        standard.update(json.loads(datei.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return standard


def version_anzeige(version) -> str:
    """«0.9.0» -> «0.9.0 Beta»: Versionen vor 1.0 sind Beta (es können noch Fehler vorkommen)."""
    v = str(version or "")
    return f"{v} Beta" if v.startswith("0.") else v


def produktfuss_html(rel: str, export: bool = False) -> str:
    """Produkt-Fusszeile von Liloport: Name, Version, GitHub, DOI, Lizenz, Impressum, Datenschutz."""
    pr = produkt_laden()
    teile = [f'<span class="pf-name"><img src="{rel}_wiki/logo.svg" alt="">{html.escape(pr["name"])}'
             + (f' <span class="pf-version">v{html.escape(version_anzeige(pr["version"]))}</span>' if pr.get("version") else "") + "</span>"]
    if export:
        teile[0] = f'<span class="pf-name">Erstellt mit {html.escape(pr["name"])}' + (f' v{html.escape(version_anzeige(pr["version"]))}' if pr.get("version") else "") + "</span>"
    # Alle Links der Fusszeile öffnen in einem neuen Tab, damit die aktuelle Seite (z. B. im Editor) offen bleibt
    if pr.get("github"):
        url = pr["github"] if pr["github"].startswith("http") else "https://github.com/" + pr["github"]
        teile.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">GitHub</a>')
    else:
        teile.append('<span class="pf-platzhalter" title="GitHub-Projekt folgt">GitHub</span>')
    if pr.get("doi"):
        url = pr["doi"] if pr["doi"].startswith("http") else "https://doi.org/" + pr["doi"]
        teile.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">DOI</a>')
    else:
        teile.append('<span class="pf-platzhalter" title="DOI folgt">DOI</span>')
    teile.append(f'<a href="{html.escape(pr.get("lizenzUrl") or "#", quote=True)}" target="_blank" rel="license noopener">{html.escape(pr.get("lizenz") or "Lizenz")}</a>')
    if not export:
        teile.append(f'<a href="{rel}_wiki/impressum.html" target="_blank" rel="noopener">Impressum</a>')
        teile.append(f'<a href="{rel}_wiki/datenschutz.html" target="_blank" rel="noopener">Datenschutz</a>')
    return '<footer class="produktfuss">' + '<span class="pf-trenner">·</span>'.join(teile) + '</footer>'


def rechtstext_html(name: str) -> str:
    """Rendert templates/impressum.html bzw. datenschutz.html mit den Angaben aus produkt.json."""
    pr = produkt_laden()
    imp = pr.get("impressum") or {}
    text = _vorlage(name)
    github = pr.get("github") or ""
    doi = pr.get("doi") or ""
    ersetzungen = {
        "{{NAME}}": html.escape(pr["name"]), "{{UNTERTITEL}}": html.escape(pr.get("untertitel") or ""),
        "{{VERSION}}": html.escape(str(pr.get("version") or "")),
        "{{VERANTWORTLICH}}": html.escape(imp.get("verantwortlich") or ""), "{{ADRESSE}}": html.escape(imp.get("adresse") or ""),
        "{{KONTAKT}}": html.escape(imp.get("kontakt") or ""), "{{INSTITUTION}}": (html.escape(imp["institution"]) + "<br>") if imp.get("institution") else "",
        "{{LIZENZ}}": html.escape(pr.get("lizenz") or ""), "{{LIZENZ_URL}}": html.escape(pr.get("lizenzUrl") or "#", quote=True),
        "{{GITHUB_ZEILE}}": (f'Quellcode: <a href="{html.escape(github if github.startswith("http") else "https://github.com/" + github, quote=True)}" target="_blank" rel="noopener">{html.escape(github)}</a><br>' if github else "Quellcode: Veröffentlichung auf GitHub folgt.<br>"),
        "{{DOI_ZEILE}}": (f'DOI: <a href="{html.escape(doi if doi.startswith("http") else "https://doi.org/" + doi, quote=True)}" target="_blank" rel="noopener">{html.escape(doi)}</a>' if doi else "DOI: folgt."),
        "{{PRODUKTFUSS}}": produktfuss_html("../"),
    }
    for k, v in ersetzungen.items():
        text = text.replace(k, v)
    return text


def kommentare_html(kommentare: list) -> str:
    """Abschnitt mit vom Webserver importierten Kommentaren (nur lokal, nur lesen)."""
    if not kommentare:
        return ""
    beurteilungen = [k for k in kommentare if k.get("art") == "beurteilung"]
    normale = [k for k in kommentare if k.get("art") != "beurteilung"]
    titel = "Kommentare und Beurteilungen vom Webserver" if beurteilungen else "Kommentare vom Webserver"
    teile = [f'<section class="kommentare importiert" id="kommentare"><h2>{titel}</h2>']

    def text_html(k):
        return (sanitize.filtern(k.get("text", ""), "profi") if re.search(r"<[a-z]", k.get("text", ""), re.I)
                else html.escape(k.get("text", "")).replace("\n", "<br>"))
    for k in beurteilungen:
        teile.append('<article class="kommentar beurteilung" data-id="%s"><header><span class="kr-b-marke">Beurteilung</span><strong>%s</strong><time datetime="%s"> · %s</time></header>'
                     '<p class="kr-b-ergebnis"><span class="kr-b-knoten">%s</span><span class="kr-b-wert">%s von %s</span></p><p>%s</p></article>' % (
            html.escape(str(k.get("id", "")), quote=True), html.escape(k.get("name") or "Anonym"),
            html.escape(str(k.get("zeit", "")), quote=True), html.escape(str(k.get("zeit", ""))[:16].replace("T", " ")),
            html.escape(k.get("knotenTitel") or k.get("knoten") or ""), html.escape(str(k.get("wert", ""))), html.escape(str(k.get("skala", ""))), text_html(k)))
    for k in normale:
        teile.append('<article class="kommentar" data-id="%s"><header><strong>%s</strong><time datetime="%s"> · %s</time></header><p>%s</p></article>' % (
            html.escape(str(k.get("id", "")), quote=True), html.escape(k.get("name") or "Anonym"),
            html.escape(str(k.get("zeit", "")), quote=True), html.escape(str(k.get("zeit", ""))[:16].replace("T", " ")), text_html(k)))
    teile.append("</section>")
    return "\n".join(teile)


def datum_lesbar(iso: str) -> str:
    """2026-10-26 → 26.10.2026"""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


def zeit_lesbar(iso: str) -> str:
    """2026-11-06T09:15:42 → 06.11.2026, 09:15"""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}, {m.group(4)}:{m.group(5)}" if m else ""


def seiten_meta_html(seite: dict, rel: str = None, datum: bool = True) -> str:
    """Datum, «zuletzt bearbeitet» und Tags unter dem Titel; rel=None: Tags ohne Link (Export)."""
    teile = []
    if datum and datum_lesbar(seite.get("datum", "")):
        teile.append(f'<time datetime="{html.escape(seite["datum"], quote=True)}">{datum_lesbar(seite["datum"])}</time>')
    if datum and zeit_lesbar(seite.get("geaendert", "")):
        geaendert = seite["geaendert"]
        teile.append(f'<span class="zuletzt-bearbeitet" title="Zeitpunkt der letzten Speicherung">zuletzt bearbeitet '
                     f'<time datetime="{html.escape(geaendert, quote=True)}">{zeit_lesbar(geaendert)}</time></span>')
    tags = [t for t in seite.get("tags") or [] if t]
    if tags:
        if rel is None:
            chips = "".join(f'<span class="tag">#{html.escape(t)}</span>' for t in tags)
        else:
            chips = "".join(f'<a class="tag" href="{rel}index.html?suche=%23{html.escape(urlquote(t), quote=True)}" title="Alle Seiten mit diesem Tag">#{html.escape(t)}</a>' for t in tags)
        teile.append(f'<span class="tags">{chips}</span>')
    return f'<p class="seiten-meta">{"".join(teile)}</p>' if teile else ""


def rueckverweise_html(eintraege: list, ziel_fuer) -> str:
    """«Verlinkt von»-Liste unter einer Seite."""
    punkte = []
    for pfad, titel in eintraege or []:
        ziel = ziel_fuer(pfad)
        if ziel is not None:
            punkte.append(f'<li><a href="{html.escape(ziel, quote=True)}">{html.escape(titel)}</a></li>')
    if not punkte:
        return ""
    return f'<aside class="rueckverweise"><h2>Verlinkt von</h2><ul>{"".join(punkte)}</ul></aside>'


def seite_html(pfad: str, seite: dict, registry: dict = None, kommentare: list = None, verweise: list = None,
               pfade: set = None, rahmen: dict = None) -> str:
    """Setzt die Seitenvorlage mit Titel, Blöcken, gescoptem CSS, Kommentaren und relativen Pfaden zusammen."""
    rel = relativ_zur_wurzel(pfad)
    br = BlockRenderer(registry or {}, rel, ziel_fuer=lambda p: f"{rel}{p}.html" if pfade is None or p in pfade else None,
                       rahmen=rahmen, pfad=pfad)
    bloecke = links.fussnoten(br.bloecke(seite.get("bloecke", []), seite.get("gliederung", "")))
    if seite.get("verweise") is False:   # Profi: «Verlinkt von» auf dieser Seite ausgeblendet
        verweise = None
    bloecke = seiten_meta_html(seite, rel) + "\n" + bloecke + rueckverweise_html(verweise, br.ziel_fuer)
    slug = seite.get("slug", "")
    css = seite.get("css", "").strip()
    stil = f"<style>\n{css_scopen(css, slug)}\n</style>" if css else ""
    ersetzungen = {
        "{{TITEL}}": html.escape(seite.get("titel", ""), quote=True),
        "{{SLUG}}": html.escape(slug, quote=True),
        "{{PFAD}}": html.escape(pfad, quote=True),
        "{{REL}}": rel,
        "{{MENUE}}": html.escape(seite.get("menue", "voll"), quote=True),
        "{{BLOECKE}}": bloecke,
        "{{STIL}}": stil,
        "{{KOMMENTARE}}": kommentare_html(kommentare or []),
        "{{WERKZEUGE}}": '<div class="seiten-werkzeuge" id="seiten-werkzeuge"></div>',
        "{{PRODUKTFUSS}}": produktfuss_html(rel),
    }
    text = _vorlage("page.html")
    for schluessel, wert in ersetzungen.items():
        text = text.replace(schluessel, wert)
    return text


def redirect_html(von_ordner: str, ziel_pfad: str, titel: str) -> str:
    """Kleine Weiterleitungsseite von einem Ordner zur echten Seite."""
    rel = "../" * (von_ordner.count("/") + 1)
    ziel = f"{rel}{ziel_pfad}.html"
    return (f'<!DOCTYPE html>\n<html lang="de"><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0; url={html.escape(ziel, quote=True)}">'
            f'<title>{html.escape(titel)} – Weiterleitung</title></head>'
            f'<body><p>Weiter zu <a href="{html.escape(ziel, quote=True)}">{html.escape(titel)}</a> …</p></body></html>\n')


def menue_daten(store: Store, site: dict, seiten: dict = None) -> dict:
    """Baut die Datenstruktur für menu.js: Verzeichnisse mit Seitentiteln (Redirects markiert).
    seiten: schon geladene Seiten {pfad: seite} (spart bei vielen Seiten das erneute Lesen)."""
    titel_cache = dict(seiten or {})

    def titel_von(pfad):
        if pfad not in titel_cache:
            try:
                titel_cache[pfad] = store.seite_laden(pfad)
            except Exception:
                titel_cache[pfad] = None
        return titel_cache[pfad]

    verzeichnisse = []
    for v in sorted(site["verzeichnisse"], key=lambda x: (x.get("reihenfolge", 0), x["name"].lower())):
        seiten = []
        for slug in v["seiten"]:
            if slug.startswith("->"):
                ziel = slug[2:]
                s = titel_von(ziel)
                if s:
                    seiten.append({"slug": ziel.rsplit("/", 1)[-1], "titel": s.get("titel", ziel),
                                   "pfad": f"{v['ordner']}/{ziel.rsplit('/', 1)[-1]}", "ziel": ziel,
                                   "redirect": True, "menue": s.get("menue", "voll"), "geaendert": s.get("geaendert", "")})
                continue
            pfad = store.seiten_pfad(v, slug)
            s = titel_von(pfad)
            if not s:
                continue
            seiten.append({"slug": slug, "titel": s.get("titel", slug), "pfad": pfad, "redirect": False,
                           "menue": s.get("menue", "voll"), "geaendert": s.get("geaendert", ""),
                           "datum": s.get("datum", ""), "tags": s.get("tags") or []})
        verzeichnisse.append({"id": v["id"], "name": v["name"], "ordner": v["ordner"],
                              "inMenue": v.get("inMenue", True), "eltern": v.get("eltern"),
                              "reihenfolge": v.get("reihenfolge", 0), "seiten": seiten})
    return {"titel": site.get("titel", "Liloport"), "niveau": site.get("niveau", "amateur"),
            "verzeichnisse": verzeichnisse}


def schreiben_wenn_neu(ziel: Path, inhalt) -> bool:
    """Schreibt nur, wenn sich der Inhalt geändert hat. Bei vielen Seiten spart das viel Arbeit für Festplatte,
    Virenscanner und Cloud-Synchronisierung (unveränderte Dateien bleiben unberührt)."""
    daten = inhalt.encode("utf-8") if isinstance(inhalt, str) else inhalt
    try:
        if ziel.stat().st_size == len(daten) and ziel.read_bytes() == daten:
            return False
    except OSError:
        pass
    ziel.write_bytes(daten)
    return True


def menue_js(daten: dict) -> str:
    """Serialisiert die Menüdaten als JavaScript-Datei (funktioniert auch unter file://)."""
    return "window.LILOPORT = " + json.dumps(daten, ensure_ascii=False, indent=2) + ";\n"


class Renderer:
    """Schreibt HTML, menu.js und die statischen Dateien in den Inhalte-Ordner."""

    def __init__(self, store: Store, assets=None, kommentare=None, suche=None, kompetenzen=None):
        self.store = store
        self.assets = assets
        self.kommentare = kommentare
        self.suche = suche
        self.kompetenzen = kompetenzen
        self._rahmen_cache = None

    def rahmen(self) -> dict:
        """Alle Kompetenzrahmen {id: kr}; innerhalb von alles_schreiben() nur einmal gelesen."""
        if self._rahmen_cache is None:
            self._rahmen_cache = self.kompetenzen.alle() if self.kompetenzen else {}
        return self._rahmen_cache

    def _registry(self) -> dict:
        return self.assets.laden() if self.assets else {}

    def statik_kopieren(self):
        """Kopiert style.css, reader.js, editor.js, app.js, logo.svg nach _wiki/ (nur was sich geändert hat)."""
        ziel = self.store.root / INTERN
        ziel.mkdir(exist_ok=True)
        for datei in STATIC.iterdir():
            if datei.is_file():
                schreiben_wenn_neu(ziel / datei.name, datei.read_bytes())

    def menue_schreiben(self, site=None, seiten=None) -> dict:
        """Schreibt _wiki/menu.js und gibt die Daten zurück."""
        site = site or self.store.site_laden()
        daten = menue_daten(self.store, site, seiten)
        schreiben_wenn_neu(self.store.root / INTERN / "menu.js", menue_js(daten))
        return daten

    def seite_schreiben(self, pfad: str, seite=None, registry=None, verweise=None, pfade=None) -> Path:
        """Rendert eine Seite nach <pfad>.html (mit Rückverweisen anderer Seiten)."""
        seite = seite or self.store.seite_laden(pfad)
        ziel = self.store.sicherer_pfad(pfad + ".html")
        kommentare = self.kommentare.laden(pfad) if self.kommentare else []
        if verweise is None:
            verweise = links.rueckverweise(self.store)
        if pfade is None:
            pfade = {p for _v, p, _s in self.store.alle_seiten()}
        if registry is None:   # einzelne Seite: Kompetenzrahmen frisch laden (bei alles_schreiben einmal für alle)
            self._rahmen_cache = None
        schreiben_wenn_neu(ziel, seite_html(pfad, seite, registry if registry is not None else self._registry(), kommentare,
                                            verweise.get(pfad, []), pfade, self.rahmen()))
        return ziel

    def kompetenzen_schreiben(self):
        """Schreibt für jeden Kompetenzrahmen die Rahmen-Seite und die Abbildung nach _kompetenzen/."""
        if not self.kompetenzen:
            return
        self._rahmen_cache = None
        ordner = self.store.root / kompetenzen.ORDNER
        seiten = [(pfad, seite.get("titel", pfad), seite) for _v, pfad, seite in self.store.alle_seiten()]
        vorhanden = set()
        for kid, kr in self.rahmen().items():
            status = kompetenzen.status_berechnen(kr, seiten)
            ordner.mkdir(exist_ok=True)
            (ordner / f"{kid}.html").write_text(kompetenzen.rahmen_seite_html(kr, status, _vorlage("kompetenzrahmen.html"), produktfuss_html("../")), encoding="utf-8")
            (ordner / f"{kid}-abbildung.html").write_text(kompetenzen.abbildung_html(kr, status, "../", _vorlage("abbildung.html"), produktfuss_html("../")), encoding="utf-8")
            vorhanden |= {f"{kid}.html", f"{kid}-abbildung.html", f"{kid}.json"}
        if ordner.exists():
            for alt in ordner.glob("*.html"):
                if alt.name not in vorhanden:
                    alt.unlink()

    def redirects_schreiben(self, site=None):
        """Schreibt für jeden ->Eintrag eine Weiterleitungsseite."""
        site = site or self.store.site_laden()
        for v in site["verzeichnisse"]:
            for s in v["seiten"]:
                if not s.startswith("->"):
                    continue
                ziel = s[2:]
                try:
                    titel = self.store.seite_laden(ziel).get("titel", ziel)
                except Exception:
                    continue
                datei = self.store.sicherer_pfad(f"{v['ordner']}/{ziel.rsplit('/', 1)[-1]}.html")
                datei.parent.mkdir(parents=True, exist_ok=True)
                datei.write_text(redirect_html(v["ordner"], ziel, titel), encoding="utf-8")

    def dashboard_schreiben(self, site=None):
        """Rendert index.html im Inhalte-Ordner."""
        site = site or self.store.site_laden()
        text = _vorlage("dashboard.html").replace("{{TITEL}}", html.escape(site.get("titel", "Liloport")))
        text = text.replace("{{PRODUKTFUSS}}", produktfuss_html(""))
        (self.store.root / "index.html").write_text(text, encoding="utf-8")
        for name in ("impressum.html", "datenschutz.html"):
            (self.store.root / INTERN / name).write_text(rechtstext_html(name), encoding="utf-8")

    def alles_schreiben(self):
        """Rendert menu.js, Dashboard, Redirects und jede Seite neu."""
        self.statik_kopieren()
        self._rahmen_cache = None
        site = self.store.site_laden()
        registry = self._registry()
        # Alle Seiten nur einmal lesen (Menü, Rückverweise, Seiten und Suche brauchen sie)
        alle = self.store.alle_seiten(site)
        self.menue_schreiben(site, {p: s for _v, p, s in alle})
        self.dashboard_schreiben(site)
        verweise = links.rueckverweise(self.store, site, alle)
        pfade = {p for _v, p, _s in alle}
        for _v, pfad, seite in alle:
            self.seite_schreiben(pfad, seite, registry, verweise, pfade)
        self.redirects_schreiben(site)
        self.kompetenzen_schreiben()
        if self.suche:
            self.suche.schreiben(site, alle)
