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
    "table": set(), "thead": set(), "tbody": set(), "tr": set(),
    "th": {"style"}, "td": {"style"}, "pre": set(), "span": {"style", "class"}, "div": {"style"},
    "li": {"style"}, "blockquote": {"style"}, "sub": set(), "sup": set(), "s": set(),
})
_UMBENENNEN = {"b": "strong", "i": "em", "strike": "s"}
_LEER = {"br"}
_HREF_OK = ("http://", "https://", "mailto:", "#", "/", "./", "../")
_STIL_OK = {"color", "background-color", "text-align"}
_KLASSEN_OK = {"fussnote"}
_STIL_WERT = re.compile(r"^[#a-zA-Z0-9 ,.()%-]+$")


def _stil_filtern(wert: str) -> str:
    """Lässt nur color, background-color und text-align mit harmlosen Werten durch."""
    teile = []
    for deklaration in (wert or "").split(";"):
        if ":" not in deklaration:
            continue
        name, w = deklaration.split(":", 1)
        name, w = name.strip().lower(), w.strip()
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

    def handle_starttag(self, tag, attrs):
        tag = _UMBENENNEN.get(tag, tag)
        if tag not in self.erlaubt:
            return
        attribute = ""
        for name, wert in attrs:
            if name in self.erlaubt[tag] and wert is not None:
                if name == "href" and not _href_sicher(wert):
                    continue
                if name == "class":
                    wert = " ".join(k for k in wert.split() if k in _KLASSEN_OK)
                    if not wert:
                        continue
                if name == "style":
                    wert = _stil_filtern(wert)
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

    def handle_endtag(self, tag):
        tag = _UMBENENNEN.get(tag, tag)
        if tag not in self.erlaubt or tag in _LEER:
            return
        if tag in self.offen:
            while self.offen:
                letztes = self.offen.pop()
                self.teile.append(f"</{letztes}>")
                if letztes == tag:
                    break

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
