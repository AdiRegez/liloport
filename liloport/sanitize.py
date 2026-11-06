"""HTML-Filter für Textblöcke: nur erlaubte Tags und Attribute bleiben stehen."""
import html
import re
from html.parser import HTMLParser

ERLAUBT_AMATEUR = {
    "h1": {"style"}, "h2": {"style"}, "h3": {"style"}, "p": {"style"}, "strong": set(), "em": set(), "u": set(),
    "a": {"href"}, "ul": set(), "ol": set(), "li": {"style"}, "blockquote": {"style"},
    "code": set(), "br": set(), "div": {"style"},
    "span": {"class"},  # nur class="fussnote" (siehe _KLASSEN_OK)
}
ERLAUBT_PROFI = dict(ERLAUBT_AMATEUR)
ERLAUBT_PROFI.update({
    "h2": {"style"}, "h3": {"style"}, "h4": {"style"}, "p": {"style"},
    "table": {"class"}, "thead": set(), "tbody": set(), "tr": set(), "caption": set(),
    "th": {"style", "colspan", "rowspan"}, "td": {"style", "colspan", "rowspan"}, "pre": set(), "span": {"style", "class"}, "div": {"style"},
    "li": {"style"}, "blockquote": {"style"}, "sub": set(), "sup": set(), "s": set(),
})
_UMBENENNEN = {"b": "strong", "i": "em", "strike": "s", "del": "s", "ins": "u"}
_LEER = {"br"}
_HREF_OK = ("http://", "https://", "mailto:", "#", "/", "./", "../")
_STIL_OK = {"color", "background-color", "text-align", "vertical-align", "width"}
_STIL_NUR = {"vertical-align": {"th", "td"}, "width": {"th", "td"}}   # nur in Tabellenzellen
_KLASSEN_OK = {"fussnote"}
# Tabellen (Profi): ein Design und Zusätze, gesetzt von der Tabellen-Leiste im Editor
TABELLEN_DESIGNS = ("tab-schlicht", "tab-gestreift", "tab-teal", "tab-lavendel", "tab-pastell", "tab-luftig")
TABELLEN_ZUSAETZE = ("tab-breit", "tab-erste-spalte", "tab-kompakt", "tab-zentriert", "tab-summe")
_KLASSEN_TAG = {"table": set(TABELLEN_DESIGNS) | set(TABELLEN_ZUSAETZE)}
_STIL_WERT = re.compile(r"^[#a-zA-Z0-9 ,.()%-]+$")
_FARBE_ATTR = re.compile(r"^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$|^[a-zA-Z]{3,20}$")


def _auszeichnung_aus_stil(wert: str) -> list:
    """Fett, kursiv, unterstrichen und durchgestrichen aus einem style-Attribut als Tags.

    Browser schreiben diese Formate je nach Einstellung als <span style="font-weight: bold"> statt <b>.
    Der Filter lässt font-weight & Co. nicht als CSS durch, übernimmt sie aber als <strong>, <em>, <u>, <s>,
    damit beim Speichern keine Formatierung verloren geht."""
    tags = []
    for deklaration in (wert or "").split(";"):
        if ":" not in deklaration:
            continue
        name, w = deklaration.split(":", 1)
        name, w = name.strip().lower(), w.strip().lower()
        if name == "font-weight" and (w in ("bold", "bolder") or (w.isdigit() and int(w) >= 600)):
            tags.append("strong")
        elif name == "font-style" and w in ("italic", "oblique"):
            tags.append("em")
        elif name in ("text-decoration", "text-decoration-line"):
            if "underline" in w:
                tags.append("u")
            if "line-through" in w:
                tags.append("s")
    return tags


def _stil_filtern(wert: str, tag: str = "") -> str:
    """Lässt nur color, background-color, text-align (in Zellen auch vertical-align, width) mit harmlosen Werten durch."""
    teile = []
    for deklaration in (wert or "").split(";"):
        if ":" not in deklaration:
            continue
        name, w = deklaration.split(":", 1)
        name, w = name.strip().lower(), w.strip()
        if name in _STIL_NUR and tag not in _STIL_NUR[name]:
            continue
        if name == "width" and not re.match(r"^\d{1,3}(\.\d+)?%$|^\d{1,4}px$", w):
            continue
        if name in _STIL_OK and _STIL_WERT.match(w) and "url" not in w.lower():
            teile.append(f"{name}: {w}")
    return "; ".join(teile)


def _href_sicher(wert: str) -> bool:
    """Lässt nur harmlose Link-Ziele durch (keine javascript:-Links)."""
    wert = (wert or "").strip().lower()
    return wert.startswith(_HREF_OK) or ("://" not in wert and not wert.startswith("javascript"))


class _Filter(HTMLParser):
    """Baut das HTML Tag für Tag neu auf und lässt alles Unerlaubte weg."""

    def __init__(self, erlaubt):
        super().__init__(convert_charrefs=True)
        self.erlaubt = erlaubt
        self.teile = []
        self.offen = []
        self.zusatz = []   # je offenes span/font: die daraus erzeugten Auszeichnungs-Tags (oder None)

    def handle_starttag(self, tag, attrs):
        tag = _UMBENENNEN.get(tag, tag)
        if tag == "font":
            # <font color="…"> (ältere Browser-Ausgabe) → <span style="color: …">
            farbe = next((w for n, w in attrs if n == "color" and w and _FARBE_ATTR.match(w.strip())), None)
            attrs = [("style", f"color: {farbe.strip()}")] if farbe else []
            tag = "span"
        if tag == "span":
            stil = next((w for n, w in attrs if n == "style" and w), "")
            extra = [t for t in _auszeichnung_aus_stil(stil) if t in self.erlaubt]
            for t in extra:
                self.teile.append(f"<{t}>")
                self.offen.append(t)
            self.zusatz.append(extra)
            if "span" not in self.erlaubt:
                return
        if tag not in self.erlaubt:
            return
        attribute = ""
        for name, wert in attrs:
            if name in self.erlaubt[tag] and wert is not None:
                if name == "href" and not _href_sicher(wert):
                    continue
                if name == "class":
                    wert = " ".join(k for k in wert.split() if k in _KLASSEN_TAG.get(tag, _KLASSEN_OK))
                    if not wert:
                        continue
                if name in ("colspan", "rowspan"):
                    if not wert.strip().isdigit() or not 1 < int(wert) <= 50:
                        continue
                    wert = str(int(wert))
                if name == "style":
                    wert = _stil_filtern(wert, tag)
                    if not wert:
                        continue
                attribute += f' {name}="{html.escape(wert, quote=True)}"'
        if tag in _LEER:
            self.teile.append(f"<{tag}>")
            return
        self.teile.append(f"<{tag}{attribute}>")
        self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def _schliessen(self, tag):
        if tag in self.offen:
            while self.offen:
                letztes = self.offen.pop()
                self.teile.append(f"</{letztes}>")
                if letztes == tag:
                    break

    def handle_endtag(self, tag):
        tag = _UMBENENNEN.get(tag, tag)
        if tag == "font":
            tag = "span"
        if tag == "span":
            if "span" in self.erlaubt:
                self._schliessen("span")
            extra = self.zusatz.pop() if self.zusatz else []
            for t in reversed(extra):
                self._schliessen(t)
            return
        if tag not in self.erlaubt or tag in _LEER:
            return
        self._schliessen(tag)

    def handle_data(self, daten):
        self.teile.append(html.escape(daten, quote=False))

    def ergebnis(self) -> str:
        """Schliesst offene Tags und liefert das gefilterte HTML."""
        while self.offen:
            self.teile.append(f"</{self.offen.pop()}>")
        return "".join(self.teile).strip()


def filtern(roh: str, niveau: str = "amateur") -> str:
    """Filtert HTML gegen die Whitelist des Niveaus (amateur oder profi)."""
    erlaubt = ERLAUBT_PROFI if niveau == "profi" else ERLAUBT_AMATEUR
    parser = _Filter(erlaubt)
    parser.feed(roh or "")
    parser.close()
    return parser.ergebnis()
