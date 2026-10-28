"""AES-256-GCM in reinem Python (nur Verschlüsseln), kompatibel mit der Web Crypto API im Browser.

Wird nur beim Export mit Passwortschutz gebraucht; die Entschlüsselung macht der Browser.
Nicht für grosse Datenmengen gedacht (eine Seite ist einige Kilobyte, das dauert Sekundenbruchteile).
"""
import hashlib
import secrets

# ---------- AES-Grundlagen ----------

_SBOX = [0] * 256


def _sbox_bauen():
    """Berechnet die S-Box aus dem Galoisfeld, statt sie als Tabelle zu tippen."""
    p = q = 1
    while True:
        p = p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xff
        if q & 0x80:
            q ^= 0x09
        def rot(v, n):
            return ((v << n) | (v >> (8 - n))) & 0xff
        x = q ^ rot(q, 1) ^ rot(q, 2) ^ rot(q, 3) ^ rot(q, 4)
        _SBOX[p] = (x ^ 0x63) & 0xff
        if p == 1:
            break
    _SBOX[0] = 0x63


_sbox_bauen()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36, 0x6c, 0xd8]


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else a << 1


def _mul(a, b):
    """Multiplikation in GF(2^8)."""
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _schluessel_erweitern(key: bytes) -> list:
    """Erzeugt die 15 Rundenschlüssel für AES-256."""
    nk, runden = 8, 14
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (runden + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        elif i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return [sum(w[4 * r:4 * r + 4], []) for r in range(runden + 1)]


def _block_verschluesseln(rk: list, block: bytes) -> bytes:
    """Verschlüsselt einen 16-Byte-Block."""
    s = [block[i] ^ rk[0][i] for i in range(16)]
    for runde in range(1, 15):
        s = [_SBOX[b] for b in s]
        s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows (spaltenweise Anordnung)
        if runde != 14:
            neu = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                neu += [_mul(a[0], 2) ^ _mul(a[1], 3) ^ a[2] ^ a[3],
                        a[0] ^ _mul(a[1], 2) ^ _mul(a[2], 3) ^ a[3],
                        a[0] ^ a[1] ^ _mul(a[2], 2) ^ _mul(a[3], 3),
                        _mul(a[0], 3) ^ a[1] ^ a[2] ^ _mul(a[3], 2)]
            s = neu
        s = [s[i] ^ rk[runde][i] for i in range(16)]
    return bytes(s)


# ---------- GCM ----------

def _ghash_mul(x: int, y: int) -> int:
    """Multiplikation in GF(2^128) für GHASH."""
    r = 0xe1 << 120
    z, v = 0, x
    for i in range(127, -1, -1):
        if (y >> i) & 1:
            z ^= v
        v = (v >> 1) ^ r if v & 1 else v >> 1
    return z


def _ghash(h: int, aad: bytes, ct: bytes) -> bytes:
    def pad(b):
        return b + b"\x00" * (-len(b) % 16)
    daten = pad(aad) + pad(ct) + (len(aad) * 8).to_bytes(8, "big") + (len(ct) * 8).to_bytes(8, "big")
    y = 0
    for i in range(0, len(daten), 16):
        y = _ghash_mul(y ^ int.from_bytes(daten[i:i + 16], "big"), h)
    return y.to_bytes(16, "big")


def gcm_verschluesseln(key: bytes, iv: bytes, klartext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM: liefert Geheimtext + 16 Byte Tag (wie Web Crypto `encrypt`)."""
    assert len(key) == 32 and len(iv) == 12
    rk = _schluessel_erweitern(key)
    h = int.from_bytes(_block_verschluesseln(rk, b"\x00" * 16), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    ct = bytearray()
    zaehler = int.from_bytes(j0, "big")
    for i in range(0, len(klartext), 16):
        zaehler += 1
        ks = _block_verschluesseln(rk, zaehler.to_bytes(16, "big"))
        stueck = klartext[i:i + 16]
        ct += bytes(a ^ b for a, b in zip(stueck, ks))
    s = _ghash(h, aad, bytes(ct))
    tag = bytes(a ^ b for a, b in zip(_block_verschluesseln(rk, j0), s))
    return bytes(ct) + tag


def schluessel_aus_passwort(passwort: str, salt: bytes, iterationen: int = 310000) -> bytes:
    """PBKDF2-HMAC-SHA256, 32 Byte, wie `deriveKey` im Browser."""
    return hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), salt, iterationen, dklen=32)


def text_verschluesseln(passwort: str, text: str, iterationen: int = 310000) -> dict:
    """Verschlüsselt einen Text mit Passwort; gibt salt, iv, daten (alle Bytes) zurück."""
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = schluessel_aus_passwort(passwort, salt, iterationen)
    return {"salt": salt, "iv": iv, "daten": gcm_verschluesseln(key, iv, text.encode("utf-8")),
            "iterationen": iterationen}
