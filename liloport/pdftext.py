"""Textauszug aus PDF-Dateien nur mit der Standardbibliothek.

Liest Objekte (auch aus Objektströmen), entpackt FlateDecode-Streams, wertet pro Seite die
Schriften (ToUnicode-CMaps für Identity-H, sonst WinAnsi/Latin) aus und interpretiert die
Textoperatoren Tj, TJ, ', \" sowie die Zeilenwechsel. Gescannte PDFs ohne Textebene liefern nichts.
"""
import base64
import re
import time
import zlib

MAX_TEXT = 2_000_000   # ganze Bücher; ein 300-seitiges PDF hat rund 600 000 Zeichen und braucht etwa 0,3 s
_OBJ_RE = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b(.*?)endobj", re.S)
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
_REF_RE = re.compile(rb"(\d+)\s+\d+\s+R")
MAX_STROM = 64 * 1024 * 1024   # entpackte Grösse eines einzelnen Streams (Schutz vor «Zip-Bomben»)
FRIST = 60                      # Sekunden pro PDF; danach Abbruch (die Suche kennt dann nur den Dateinamen)
# Streams, die nie Text enthalten: gar nicht erst entpacken (Bilder machen bei Scans fast die ganze Datei aus)
_OHNE_TEXT = (b"/Image", b"/FontFile", b"/Metadata", b"/EmbeddedFile", b"/ICCBased", b"/XRef")


class PdfZuAufwendig(Exception):
    """Das PDF braucht zu lange; der Text wird nicht ausgelesen."""


def _frist_pruefen(frist):
    if frist is not None and time.monotonic() > frist:
        raise PdfZuAufwendig("Zeitlimit beim Auslesen des PDFs überschritten")

# WinAnsi (cp1252) ist bei einfachen Schriften mit Abstand am häufigsten.
def _einfach(bytes_: bytes) -> str:
    try:
        return bytes_.decode("cp1252")
    except UnicodeDecodeError:
        return bytes_.decode("latin-1", "replace")


def _flate(roh: bytes) -> bytes:
    """Entpackt höchstens MAX_STROM Bytes (auch abgeschnittene Streams liefern, was lesbar ist)."""
    for versuch in (roh, roh.strip()):
        try:
            return zlib.decompressobj().decompress(versuch, MAX_STROM)
        except zlib.error:
            continue
    return b""


def _entpacken(dikt: bytes, roh: bytes) -> bytes:
    """Wendet die Filterkette an (ASCII85, ASCIIHex, Flate); unbekannte Filter lassen den Stream leer."""
    fm = re.search(rb"/Filter\s*(\[[^\]]*\]|/[A-Za-z0-9]+)", dikt)
    if not fm:
        return roh
    filter_namen = re.findall(rb"/([A-Za-z0-9]+)", fm.group(1))
    daten = roh
    for name in filter_namen:
        if name == b"FlateDecode":
            daten = _flate(daten)
        elif name == b"ASCII85Decode":
            try:
                daten = base64.a85decode(re.sub(rb"\s", b"", daten).replace(b"<~", b""), adobe=False) \
                    if b"~>" not in daten else base64.a85decode(re.sub(rb"\s", b"", daten), adobe=True)
            except ValueError:
                return b""
        elif name == b"ASCIIHexDecode":
            hx = re.sub(rb"[^0-9A-Fa-f]", b"", daten.split(b">")[0])
            daten = bytes.fromhex(hx.decode() if len(hx) % 2 == 0 else hx.decode() + "0")
        else:
            return b""  # Bildfilter u. ä.: kein Text
    return daten


class _Objekte:
    """Sammelt alle Objekte einer PDF: Nummer -> Wörterbuchtext; Streams werden erst bei Bedarf entpackt."""

    def __init__(self, daten: bytes, frist=None):
        self.objekte = {}     # num -> (dikt, roher Stream oder None)
        self._entpackt = {}   # num -> entpackter Stream
        self.frist = frist
        for i, m in enumerate(_OBJ_RE.finditer(daten)):
            if i % 200 == 0:
                _frist_pruefen(frist)
            num, inhalt = int(m.group(1)), m.group(3)
            sm = _STREAM_RE.search(inhalt)
            if sm:
                self.objekte[num] = (inhalt[:sm.start()], sm.group(1))
            else:
                self.objekte[num] = (inhalt, None)
        # Objektströme (PDF 1.5+): enthalten weitere Objekte ohne eigenes "obj"
        for num, (dikt, roh) in list(self.objekte.items()):
            if roh is not None and b"/ObjStm" in dikt:
                _frist_pruefen(frist)
                self._objstm(dikt, self.stream(num))

    def _objstm(self, dikt: bytes, stream: bytes):
        n = re.search(rb"/N\s+(\d+)", dikt)
        first = re.search(rb"/First\s+(\d+)", dikt)
        if not n or not first or not stream:
            return
        kopf = stream[:int(first.group(1))].split()
        try:
            paare = [(int(kopf[i]), int(kopf[i + 1])) for i in range(0, min(len(kopf), 2 * int(n.group(1))) - 1, 2)]
        except ValueError:
            return
        for i, (onum, offset) in enumerate(paare):
            ende = paare[i + 1][1] if i + 1 < len(paare) else len(stream) - int(first.group(1))
            text = stream[int(first.group(1)) + offset:int(first.group(1)) + ende]
            if onum not in self.objekte:
                self.objekte[onum] = (text, None)

    def dikt(self, num: int) -> bytes:
        return self.objekte.get(num, (b"", None))[0]

    def hat_strom(self, num: int) -> bool:
        dikt, roh = self.objekte.get(num, (b"", None))
        return roh is not None and not any(k in dikt for k in _OHNE_TEXT)

    def stream(self, num: int) -> bytes:
        if num in self._entpackt:
            return self._entpackt[num]
        if not self.hat_strom(num):
            return b""
        _frist_pruefen(self.frist)
        dikt, roh = self.objekte[num]
        daten = _entpacken(dikt, roh) or b""
        self._entpackt[num] = daten
        return daten


def _cmap_parsen(cmap: bytes) -> tuple:
    """Liest bfchar/bfrange aus einem ToUnicode-CMap; gibt (Zuordnung, Codelänge in Bytes) zurück."""
    zuordnung = {}
    laenge = 2
    cs = re.search(rb"begincodespacerange(.*?)endcodespacerange", cmap, re.S)
    if cs:
        hexe = re.findall(rb"<([0-9A-Fa-f]+)>", cs.group(1))
        if hexe:
            laenge = max(1, len(hexe[0]) // 2)

    def uni(hx: bytes) -> str:
        try:
            b = bytes.fromhex(hx.decode())
            return b.decode("utf-16-be", "ignore") if len(b) >= 2 else chr(b[0])
        except ValueError:
            return ""

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            zuordnung[int(src, 16)] = uni(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
        for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            lo_i, hi_i = int(lo, 16), int(hi, 16)
            start = uni(dst)
            if not start:
                continue
            basis = ord(start[-1])
            for code in range(lo_i, min(hi_i, lo_i + 65535) + 1):
                zuordnung[code] = start[:-1] + chr(basis + code - lo_i)
        for lo, hi, liste in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.S):
            for i, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", liste)):
                zuordnung[int(lo, 16) + i] = uni(dst)
    return zuordnung, laenge


class _Schrift:
    """Dekodiert Bytes eines Textstrings anhand von CMap oder einfacher Kodierung."""

    def __init__(self, objekte: _Objekte, num: int):
        dikt = objekte.dikt(num)
        self.cmap, self.laenge = None, 1
        self.type0 = b"/Type0" in dikt
        tu = re.search(rb"/ToUnicode\s+(\d+)\s+\d+\s+R", dikt)
        if tu:
            cmap = objekte.stream(int(tu.group(1)))
            if cmap:
                self.cmap, self.laenge = _cmap_parsen(cmap)
        if self.type0 and not self.cmap:
            self.laenge = 2  # Identity-H ohne ToUnicode: nicht lesbar

    def dekodieren(self, roh: bytes) -> str:
        if self.cmap:
            n = self.laenge
            return "".join(self.cmap.get(int.from_bytes(roh[i:i + n], "big"), "") for i in range(0, len(roh) - n + 1, n))
        if self.type0:
            return ""
        return _einfach(roh)


def _literal(s: bytes) -> bytes:
    """Löst Escapes in einem (…)-String auf."""
    s = re.sub(rb"\\\r?\n", b"", s)
    s = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xff]), s)
    return re.sub(rb"\\(.)", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(m.group(1), m.group(1)), s)


# Inhaltsströme werden mit einem Zerleger gelesen, der jedes Byte nur einmal anschaut (linear). Ein früherer
# Ansatz mit einem einzigen grossen regulären Ausdruck konnte bei ungewöhnlichen Strömen (viele «(» oder «[»
# ohne Gegenstück, z. B. in eingebetteten Bilddaten) exponentiell bzw. quadratisch lange laufen und hielt
# dabei die ganze Python-Ausführung an: Liloport fror ein. tests/test_pdftext.py prüft solche Fälle.
_TRENN = rb" \t\r\n\f\x00()<>\[\]{}/%"
_TOKEN = re.compile(
    rb"(?P<ws>[ \t\r\n\f\x00]+)"
    rb"|(?P<kommentar>%[^\r\n]*)"
    rb"|(?P<name>/[^ \t\r\n\f\x00()<>\[\]{}/%]*)"
    rb"|(?P<zahl>[+-]?(?:\d+\.?\d*|\.\d+))(?![^ \t\r\n\f\x00()<>\[\]{}/%])"
    rb"|(?P<hex><[0-9A-Fa-f \t\r\n\f\x00]*>)"
    rb"|(?P<klammer><<|>>|[\[\]{}])"
    rb"|(?P<op>[^ \t\r\n\f\x00()<>\[\]{}/%]+)")
_STRING_ZEICHEN = re.compile(rb"[()\\]")
_BILD_ENDE = re.compile(rb"[ \t\r\n\f\x00]EI(?=[ \t\r\n\f\x00]|$)")
_NEUE_ZEILE = {b"T*", b"TD", b"Td", b"ET"}


def _string_ende(daten: bytes, i: int) -> int:
    """daten[i] ist «(»: Position nach der passenden «)» (Klammern dürfen verschachtelt sein)."""
    tiefe, j = 0, i
    while True:
        m = _STRING_ZEICHEN.search(daten, j)
        if not m:
            return len(daten)
        c = m.group(0)
        if c == b"\\":
            j = m.end() + 1
            continue
        tiefe += 1 if c == b"(" else -1
        j = m.end()
        if tiefe == 0:
            return j


def _zerlegen(daten: bytes):
    """Liefert Tokens: ('s', rohe Bytes) für (…), ('h', hex) für <…>, ('n', Zahl), ('/', Name), ('[',), (']',),
    ('op', Operator). Läuft in linearer Zeit; eingebettete Bilder (BI … ID … EI) werden übersprungen."""
    i, n = 0, len(daten)
    while i < n:
        if daten[i] == 0x28:   # «(»
            ende = _string_ende(daten, i)
            yield ("s", daten[i + 1:ende - 1])
            i = ende
            continue
        m = _TOKEN.match(daten, i)
        if not m:
            i += 1   # einzelnes «)» oder «<» ohne Gegenstück: überspringen
            continue
        i = m.end()
        art = m.lastgroup
        if art in ("ws", "kommentar"):
            continue
        wert = m.group(0)
        if art == "zahl":
            try:
                yield ("n", float(wert))
            except ValueError:
                pass
        elif art == "name":
            yield ("/", wert[1:])
        elif art == "hex":
            yield ("h", wert[1:-1])
        elif art == "klammer":
            if wert in (b"[", b"]"):
                yield (wert.decode(),)
        else:
            if wert == b"ID":   # Daten eines eingebetteten Bilds: bis «EI» überspringen
                e = _BILD_ENDE.search(daten, i)
                i = e.end() if e else n
                continue
            yield ("op", wert)


def _hex_bytes(hx: bytes) -> bytes:
    hx = re.sub(rb"[^0-9A-Fa-f]", b"", hx)
    return bytes.fromhex((hx + b"0" if len(hx) % 2 else hx).decode())


def _inhalt_lesen(inhalt: bytes, schriften: dict, standard) -> str:
    """Interpretiert einen Inhaltsstrom und liefert den Text."""
    teile, aktuell = [], standard
    operanden, arrays = [], []

    def text(token):
        roh = _literal(token[1]) if token[0] == "s" else _hex_bytes(token[1])
        return aktuell.dekodieren(roh) if aktuell is not None else ""

    for tok in _zerlegen(inhalt):
        art = tok[0]
        if art == "[":
            arrays.append(operanden)
            operanden = []
            continue
        if art == "]":
            inhalt_array = operanden
            operanden = arrays.pop() if arrays else []
            operanden.append(("a", inhalt_array))
            continue
        if art != "op":
            operanden.append(tok)
            continue
        op = tok[1]
        if op == b"Tf":
            namen = [o for o in operanden if o[0] == "/"]
            if namen:
                aktuell = schriften.get(namen[-1][1].decode("latin-1"), standard)
        elif op in _NEUE_ZEILE:
            teile.append("\n")
        elif op == b"Tm":
            teile.append(" ")
        elif op in (b"Tj", b"'", b'"'):
            s = next((o for o in reversed(operanden) if o[0] in ("s", "h")), None)
            if s is not None:
                if op != b"Tj":
                    teile.append("\n")
                teile.append(text(s))
        elif op == b"TJ":
            arr = next((o for o in reversed(operanden) if o[0] == "a"), None)
            for o in (arr[1] if arr else []):
                if o[0] == "n":
                    if abs(o[1]) > 180:
                        teile.append(" ")
                elif o[0] in ("s", "h"):
                    teile.append(text(o))
        operanden, arrays = [], []
    return "".join(teile)


def _schriftenkarte(objekte: _Objekte, dikt: bytes, cache: dict) -> dict:
    """Name -> _Schrift für ein /Resources-Wörterbuch (inline oder als Referenz)."""
    karte = {}
    res = dikt
    rm = re.search(rb"/Resources\s+(\d+)\s+\d+\s+R", dikt)
    if rm:
        res = objekte.dikt(int(rm.group(1)))
    fm = re.search(rb"/Font\s*<<(.*?)>>", res, re.S)
    fonttext = fm.group(1) if fm else b""
    if not fm:
        fr = re.search(rb"/Font\s+(\d+)\s+\d+\s+R", res)
        if fr:
            fonttext = objekte.dikt(int(fr.group(1)))
    for name, num in re.findall(rb"/([^\s/\[\]<>(){}]+)\s+(\d+)\s+\d+\s+R", fonttext):
        num = int(num)
        if num not in cache:
            cache[num] = _Schrift(objekte, num)
        karte[name.decode("latin-1")] = cache[num]
    return karte


def pdf_text(daten: bytes, sekunden: float = FRIST) -> str:
    """Zieht den sichtbaren Text eines PDFs heraus (Seite für Seite, dann Formular-XObjects).

    Bricht nach `sekunden` mit PdfZuAufwendig ab, damit ein ungewöhnliches PDF nie alles aufhält."""
    if not daten.startswith(b"%PDF"):
        return ""
    frist = time.monotonic() + sekunden if sekunden else None
    objekte = _Objekte(daten, frist)
    cache, texte = {}, []
    einfach = _Schrift.__new__(_Schrift)
    einfach.cmap, einfach.laenge, einfach.type0 = None, 1, False

    # Alle Schriften global sammeln (Fallback, wenn eine Seite ihre Ressourcen erbt)
    global_karte = {}
    for num, (dikt, _s) in list(objekte.objekte.items()):
        if b"/Font" in dikt and b"<<" in dikt:
            global_karte.update(_schriftenkarte(objekte, dikt, cache))

    gelesen = set()
    for num, (dikt, _s) in list(objekte.objekte.items()):
        if b"/Type" not in dikt or b"/Page" not in dikt or b"/Pages" in dikt:
            continue
        _frist_pruefen(frist)
        karte = dict(global_karte)
        karte.update(_schriftenkarte(objekte, dikt, cache))
        cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", dikt)
        if not cm:
            continue
        for ref in _REF_RE.findall(cm.group(1)):
            gelesen.add(int(ref))
            texte.append(_inhalt_lesen(objekte.stream(int(ref)), karte, einfach))
        texte.append("\n")
    for num, (dikt, _s) in list(objekte.objekte.items()):
        if num in gelesen or b"/Form" not in dikt or not objekte.hat_strom(num):
            continue
        _frist_pruefen(frist)
        stream = objekte.stream(num)
        if b"Tj" in stream or b"TJ" in stream:
            karte = dict(global_karte)
            karte.update(_schriftenkarte(objekte, dikt, cache))
            texte.append(_inhalt_lesen(stream, karte, einfach))
    if not gelesen:  # keine Seitenobjekte gefunden: alle Inhaltsströme mit globaler Schriftkarte
        for num, (dikt, _s) in list(objekte.objekte.items()):
            if b"/ObjStm" in dikt or not objekte.hat_strom(num):
                continue
            _frist_pruefen(frist)
            stream = objekte.stream(num)
            if b"Tj" in stream or b"TJ" in stream:
                texte.append(_inhalt_lesen(stream, global_karte, einfach))
    text = "".join(texte)
    text = re.sub(r"[ \t\f\r]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:MAX_TEXT]


# ---------- in eigenem Prozess (für das laufende Liloport) ----------

GROSS_OHNE_SCHRIFT = 20_000_000
ANLAUF = 30   # Sekunden zusätzlich zur Frist: Start des Prozesses (installiertes Programm unter Windows: langsam)   # grössere PDFs ohne Schrift-Verweis sind Scans: gar nicht erst zerlegen


def _pdf_datei_lesen(pfad: str, sekunden: float) -> str:
    with open(pfad, "rb") as f:
        daten = f.read()
    if len(daten) > GROSS_OHNE_SCHRIFT and b"/Font" not in daten:
        return ""
    return pdf_text(daten, sekunden)


def _arbeiter(pfad: str, sekunden: float, senden):
    try:
        senden.send(("ok", _pdf_datei_lesen(pfad, sekunden)))
    except PdfZuAufwendig:
        senden.send(("zu aufwendig", ""))
    except Exception as e:  # noqa: BLE001
        senden.send(("fehler", f"{type(e).__name__}: {e}"))
    finally:
        senden.close()


def pdf_text_isoliert(pfad, sekunden: float = FRIST) -> str:
    """Wie pdf_text, aber in einem eigenen Prozess, der nach Ablauf der Frist hart beendet wird.

    Grund: Läuft Python in einer einzelnen langen C-Operation (etwa einem regulären Ausdruck), hält es
    alle Threads an – ein Thread allein schützt das laufende Liloport also nicht vor einem PDF, das sich
    ungewöhnlich verhält. Ein eigener Prozess schon. Wirft PdfZuAufwendig bei Zeitüberschreitung und
    OSError, wenn sich kein Prozess starten lässt (dann liest der Aufrufer im eigenen Prozess)."""
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    empfang, senden = ctx.Pipe(duplex=False)
    prozess = ctx.Process(target=_arbeiter, args=(str(pfad), sekunden, senden), daemon=True,
                          name="liloport-pdftext")
    prozess.start()
    senden.close()
    try:
        # Start eines Prozesses (v. a. beim installierten Programm unter Windows) dauert etwas: grosszügig
        art, wert = empfang.recv() if empfang.poll(sekunden + ANLAUF) else ("zeit", "")
    except (EOFError, OSError):
        art, wert = "fehler", "Prozess beendet sich ohne Ergebnis"
    finally:
        if prozess.is_alive():
            prozess.kill()
        prozess.join(5)
        empfang.close()
    if art == "ok":
        return wert
    if art in ("zeit", "zu aufwendig"):
        raise PdfZuAufwendig("Zeitlimit beim Auslesen des PDFs überschritten")
    raise RuntimeError(wert)

