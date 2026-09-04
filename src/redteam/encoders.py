"""Mutation/encoding arsenal — techniques cataloged from P4RS3LT0NGV3 & L1B3RT4S.

Reference: elder-plinius/P4RS3LT0NGV3 (222 transforms), L1B3RT4S
(MOTHERLOAD unicode-tag smuggling, TOKENADE variation-selector stego).
"""
from __future__ import annotations

import base64
import codecs

# ------------------------------------------------------------------ ciphers

def rot13(text: str) -> str:
    return codecs.encode(text, "rot13")


_LEET_LIGHT = str.maketrans("aeiost", "431057")
_LEET_HEAVY = str.maketrans("aeiostbgz", "43|057692")


def leet_light(text: str) -> str:
    return text.translate(_LEET_LIGHT)


def leet_heavy(text: str) -> str:
    return text.translate(_LEET_HEAVY)


def atbash(text: str) -> str:
    out = []
    for c in text:
        if c.isalpha() and c.islower():
            out.append(chr(219 - ord(c)))
        elif c.isalpha() and c.isupper():
            out.append(chr(155 - ord(c)))
        else:
            out.append(c)
    return "".join(out)


def caesar(text: str, shift: int = 3) -> str:
    out = []
    for c in text:
        if c.islower():
            out.append(chr((ord(c) - 97 + shift) % 26 + 97))
        elif c.isupper():
            out.append(chr((ord(c) - 65 + shift) % 26 + 65))
        else:
            out.append(c)
    return "".join(out)


# ------------------------------------------------------------ classic encodings

def hex_encode(text: str) -> str:
    return " ".join(f"{b:02x}" for b in text.encode())


def binary_encode(text: str) -> str:
    return " ".join(f"{b:08b}" for b in text.encode())


def base64_encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


_NATO = {
    "a": "Alfa", "b": "Bravo", "c": "Charlie", "d": "Delta", "e": "Echo",
    "f": "Foxtrot", "g": "Golf", "h": "Hotel", "i": "India", "j": "Juliett",
    "k": "Kilo", "l": "Lima", "m": "Mike", "n": "November", "o": "Oscar",
    "p": "Papa", "q": "Quebec", "r": "Romeo", "s": "Sierra", "t": "Tango",
    "u": "Uniform", "v": "Victor", "w": "Whiskey", "x": "X-ray", "y": "Yankee",
    "z": "Zulu",
}


def nato_encode(text: str) -> str:
    return " ".join(_NATO[c] for c in text.lower() if c.isalpha())


_MORSE = {
    "a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".", "f": "..-.",
    "g": "--.", "h": "....", "i": "..", "j": ".---", "k": "-.-", "l": ".-..",
    "m": "--", "n": "-.", "o": "---", "p": ".--.", "q": "--.-", "r": ".-.",
    "s": "...", "t": "-", "u": "..-", "v": "...-", "w": ".--", "x": "-..-",
    "y": "-.--", "z": "--..", "0": "-----", "1": ".----", "2": "..---",
    "3": "...--", "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
}


def morse_encode(text: str) -> str:
    return " ".join(_MORSE[c] for c in text.lower() if c in _MORSE)


def a1z26_encode(text: str) -> str:
    return " ".join(str(ord(c) - 96) for c in text.lower() if c.isalpha())


def reverse_words(text: str) -> str:
    return " ".join(w[::-1] for w in text.split())


# ------------------------------------------------------- invisible smuggling

# Unicode Tags block (U+E0000..U+E007F): renders as nothing in most UIs,
# but tokenizes. Technique from L1B3RT4S #MOTHERLOAD.txt.
def _to_unicode_tags(text: str) -> str:
    out = []
    for c in text.encode("ascii", errors="ignore"):
        out.append(chr(0xE0000 + c))
    return "".join(out)


def unicode_tag_wrap(text: str) -> str:
    return _to_unicode_tags(text)


def decode_unicode_tags(text: str) -> str:
    return "".join(
        chr(ord(c) - 0xE0000) for c in text if 0xE0000 <= ord(c) <= 0xE007F
    )


# Emoji variation-selector stego (L1B3RT4S TOKENADE.mkd): visible emoji frame
# with the payload encoded in VS16-style invisible selectors.
_VS_BASE = 0xFE00


def emoji_stego_wrap(text: str) -> str:
    frame = "💀🔥🎯🚀"
    payload = "".join(
        chr(_VS_BASE + (b & 0x0F)) + chr(_VS_BASE + ((b >> 4) & 0x0F))
        for b in text.encode("utf-8")
    )
    return frame[0] + payload + frame[-1] + " 🎯 " + unicode_tag_wrap(text)


def zero_width_encode(text: str) -> str:
    # ZWSP/ZWNJ/ZWJ/word-joiner quaternary encoding (P4RS3LT0NGV3 category)
    zws = ["\u200b", "\u200c", "\u200d", "\u2060"]
    out = []
    for b in text.encode("utf-8"):
        out.append(zws[(b >> 6) & 3] + zws[b & 3])
    return "".join(out)


# --------------------------------------------------- v2 expansion (WallBreaker parity)

def base32_encode(text: str) -> str:
    import base64 as _b64
    return _b64.b32encode(text.encode()).decode()


def base85_encode(text: str) -> str:
    import base64 as _b64
    return _b64.a85encode(text.encode()).decode()


def base36_encode(text: str) -> str:
    """Whole text \u2192 one big base-36 integer (dense, model-decodable)."""
    n = int.from_bytes(text.encode("utf-8"), "big")
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def uu_encode(text: str) -> str:
    # b2a_uu encodes at most 45 bytes per call, which is the uuencode line
    # length; anything longer must be split into lines the same way.
    import binascii
    raw = text.encode()
    return "\n".join(
        binascii.b2a_uu(raw[i:i + 45]).decode().rstrip("\n")
        for i in range(0, len(raw), 45)
    ) or binascii.b2a_uu(b"").decode().rstrip("\n")


def quoted_printable_encode(text: str) -> str:
    import quopri
    return quopri.encodestring(text.encode()).decode()


def url_encode(text: str) -> str:
    import urllib.parse
    return urllib.parse.quote(text)


def hex_dense_encode(text: str) -> str:
    return "".join(f"{b:02x}" for b in text.encode())


def binary_dense_encode(text: str) -> str:
    return "".join(f"{b:08b}" for b in text.encode())


def double_base64_encode(text: str) -> str:
    return base64_encode(base64_encode(text))


def rot47(text: str) -> str:
    out = []
    for c in text:
        o = ord(c)
        if 33 <= o <= 126:
            out.append(chr(33 + ((o - 33 + 47) % 94)))
        else:
            out.append(c)
    return "".join(out)


def rot5(text: str) -> str:
    out = []
    for c in text:
        if c.isdigit():
            out.append(str((int(c) + 5) % 10))
        else:
            out.append(c)
    return "".join(out)


def rot18(text: str) -> str:
    """ROT13 for letters + ROT5 for digits (classic ROT18 combo)."""
    return rot13(rot5(text))


def alternating_case(text: str) -> str:
    out = []
    upper = False
    for c in text:
        if c.isalpha():
            out.append(c.upper() if upper else c.lower())
            upper = not upper
        else:
            out.append(c)
    return "".join(out)


def vowel_shuffle(text: str) -> str:
    """Rotate vowels a\u2192e\u2192i\u2192o\u2192u\u2192y\u2192a \u2014 mostly readable, off-regex."""
    m = str.maketrans("aeiouy", "eiouya")
    return text.translate(m)


_UPSIDE = (
    "\u0250q\u0254p\u01dd\u025f\u0183\u0265\u0131\u027e\u029el\u026fuodb\u0279s\u0287n\u028c\u028dx\u028ez"  # a-z flipped
    "\u2200\ud801\udc12\u0186p\u018e\u2132\u2141HI\u017f\u029e\u02e5WNO\u0500Q\u0279S\u22a5\u2229\u039bMX\u2144Z"  # A-Z flipped
    "0\u0406\u1105\u3123\u03db9\u312586"  # 0-9 flipped
)
_UPSIDE_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    ".?!,'\"()[]{}<>&_",
    _UPSIDE + "\u02d9\u00bf\u00a1',\u201e)(][}{><\u214b\u203e",
)


def upside_down(text: str) -> str:
    """Upside-down flip (180\u00b0 rotation) \u2014 readable after mental rotation."""
    return "".join(reversed(text.translate(_UPSIDE_MAP)))


def zalgo(text: str) -> str:
    """Combining-diacritics storm: visually noisy, tokenizer-hostile."""
    import random
    combining = [chr(c) for c in range(0x0300, 0x036F)]
    rng = random.Random(len(text))
    out = []
    for c in text:
        out.append(c + "".join(rng.sample(combining, rng.randint(1, 3))))
    return "".join(out)


def rtl_override(text: str) -> str:
    """U+202E RIGHT-TO-LEFT OVERRIDE wrap \u2014 renders reversed in most UIs."""
    return "\u202e" + text + "\u202c"


_BRAILLE_BASE = 0x2800  # \u2800 (blank cell); +pattern \u2192 braille cell


def braille_encode(text: str) -> str:
    """Letters \u2192 braille cells via dot-pattern encoding (visual, decodable)."""
    out = []
    for c in text.lower():
        if c.isalpha():
            v = ord(c) - 96  # a=1 ... z=26 \u2192 5-bit pattern
            pattern = (v & 0b00011) | ((v & 0b11100) << 2)
            out.append(chr(_BRAILLE_BASE | pattern))
        else:
            out.append(c)
    return "".join(out)


def polybius_encode(text: str) -> str:
    """5x5 Polybius square (I/J merged): letter \u2192 row+col digits."""
    out = []
    for c in text.upper():
        if c.isalpha():
            ch = "I" if c == "J" else c
            n = ord(ch) - 65  # A=0 ... I=8, K=9 (J merged into I)
            out.append(f"{n // 5 + 1}{n % 5 + 1}")
        else:
            out.append(c)
    return " ".join(out)


def pig_latin(text: str) -> str:
    out = []
    for word in text.split():
        if not word.isalpha():
            out.append(word)
        elif word[0].lower() in "aeiou":
            out.append(word + "way")
        else:
            out.append(word[1:] + word[0].lower() + "ay")
    return " ".join(out)


_CYRILLIC = str.maketrans(
    "acekopxyABCEHKMOPTX",
    "\u0430\u0441\u0435\u043a\u043e\u0440\u0445\u0443\u0410\u0412\u0421\u0415\u041d\u041a\u041c\u041e\u0420\u0422\u0425",
)


def cyrillic_homoglyph(text: str) -> str:
    """Latin \u2192 Cyrillic lookalikes (acekopxy...): visually identical, distinct codepoints."""
    return text.translate(_CYRILLIC)


_GREEK = str.maketrans(
    "abdegiklnopstuvxy",
    "\u03b1\u03b2\u03b4\u03b5\u03b3\u03b9\u03ba\u03bb\u03bd\u03bf\u03c1\u03c3\u03c4\u03c5\u03bd\u03c7\u03c8",
)


def greeklish(text: str) -> str:
    """Latin \u2192 Greek letter lookalikes."""
    return text.translate(_GREEK)


_VIGENERE_KEY = "REDTEAM"


def vigenere_encode(text: str, key: str = _VIGENERE_KEY) -> str:
    out = []
    ki = 0
    for c in text:
        if c.isalpha():
            k = ord(key[ki % len(key)].lower()) - 97
            if c.islower():
                out.append(chr((ord(c) - 97 + k) % 26 + 97))
            else:
                out.append(chr((ord(c) - 65 + k) % 26 + 65))
            ki += 1
        else:
            out.append(c)
    return "".join(out)


def keyboard_shift(text: str) -> str:
    """Shift each letter to the key to its right on QWERTY (typo-mimicry)."""
    rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    right = {}
    for row in rows:
        for i, c in enumerate(row):
            right[c] = row[(i + 1) % len(row)]
    out = []
    for c in text:
        low = c.lower()
        if low in right:
            rep = right[low]
            out.append(rep.upper() if c.isupper() else rep)
        else:
            out.append(c)
    return "".join(out)


def morse_dense_encode(text: str) -> str:
    """Morse without letter separators (harder variant)."""
    return morse_encode(text).replace(" / ", "  ")


def expand_numbers(text: str) -> str:
    """Digits \u2192 English words (bypass numeric-content filters)."""
    words = ["zero", "one", "two", "three", "four", "five", "six",
             "seven", "eight", "nine"]
    return "".join(words[int(c)] if c.isdigit() else c for c in text)


def sup_codepoints(text: str) -> str:
    """Map digits/letters to Unicode superscript codepoints where they exist."""
    sup_digits = str.maketrans("0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")
    sup_letters = str.maketrans("abdegilmnoprstuv", "\u1d43\u1d47\u1d48\u1d49\u1d4d\u2071\u02e1\u1d50\u207f\u1d52\u1d56\u02b3\u02e2\u1d57\u1d58\u1d5b")
    return text.translate(sup_digits).translate(sup_letters)


ENCODERS: dict[str, object] = {
    "rot13": rot13,
    "leetspeak": leet_light,
    "leetspeak_heavy": leet_heavy,
    "atbash": atbash,
    "hex": hex_encode,
    "binary": binary_encode,
    "nato": nato_encode,
    "morse": morse_encode,
    "a1z26": a1z26_encode,
    "reverse": reverse_words,
    "caesar3": lambda t: caesar(t, 3),
    "base64": base64_encode,
    "unicode_tags": unicode_tag_wrap,
    "emoji_stego": emoji_stego_wrap,
    "zero_width": zero_width_encode,
    # ---- v2 expansion (WallBreaker / P4RS3LT0NGV3 parity) ----
    "base32": base32_encode,
    "base85": base85_encode,
    "base36": base36_encode,
    "uuencode": uu_encode,
    "quoted_printable": quoted_printable_encode,
    "url": url_encode,
    "hex_dense": hex_dense_encode,
    "binary_dense": binary_dense_encode,
    "double_base64": double_base64_encode,
    "rot47": rot47,
    "rot5": rot5,
    "rot18": rot18,
    "alternating_case": alternating_case,
    "vowel_shuffle": vowel_shuffle,
    "upside_down": upside_down,
    "zalgo": zalgo,
    "rtl_override": rtl_override,
    "braille": braille_encode,
    "polybius": polybius_encode,
    "pig_latin": pig_latin,
    "cyrillic": cyrillic_homoglyph,
    "greeklish": greeklish,
    "vigenere": vigenere_encode,
    "keyboard_shift": keyboard_shift,
    "morse_dense": morse_dense_encode,
    "expand_numbers": expand_numbers,
    "sup_codepoints": sup_codepoints,
}
