"""Reduced rational serialization and binary32 nearest-even rounding, version 1."""
import re
from fractions import Fraction

LIMIT = 8192
DIGITS = 2467  # ceil(8192 * log10(2))
TOKEN = re.compile(r"(0|-?[1-9][0-9]*)/([1-9][0-9]*)\Z")


def bounded(x):
    if type(x) not in (int, Fraction):
        raise ValueError("exact integer or rational required")
    if max(x.numerator.bit_length(), x.denominator.bit_length()) > LIMIT:
        raise ValueError("rational bit limit")
    return x


def encode(x):
    bounded(x)
    return f"{x.numerator}/{x.denominator}"


def parse(s):
    if type(s) is not str or len(s) > 2 * DIGITS + 2:
        raise ValueError("rational token length")
    m = TOKEN.fullmatch(s)
    if not m or any(len(v.lstrip("-")) > DIGITS for v in m.groups()):
        raise ValueError("rational token")
    value = Fraction(int(m[1]), int(m[2]))
    if encode(value) != s:
        raise ValueError("noncanonical rational")
    return value


def rn32(x):
    bounded(x)
    if not x:
        return 0
    n, d = abs(x.numerator), x.denominator
    top = n.bit_length() - d.bit_length()
    if n << max(-top, 0) < d << max(top, 0):
        top -= 1
    spacing = max(-149, top - 23)
    n <<= max(-spacing, 0)
    d <<= max(spacing, 0)
    q, rem = divmod(n, d)
    if 2 * rem > d or (2 * rem == d and q & 1):
        q += 1
    sign = (1 << 31) if x < 0 else 0
    if q < 1 << 23:
        return sign | q
    if q == 1 << 24:
        q >>= 1
        spacing += 1
    field = spacing + 150
    if field >= 255:
        raise OverflowError("nonfinite prospective endpoint")
    return sign | field << 23 | (q - (1 << 23))
