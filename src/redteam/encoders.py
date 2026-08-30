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
}