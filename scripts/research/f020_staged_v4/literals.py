"""Independent public oracle. Does not import checker, source or owner modules.

Decimal is an independent mock-output oracle, not the certified reference.
No files, model paths, MLX imports or execution capabilities.
"""
from decimal import Decimal, localcontext
from fractions import Fraction
import struct

ASYMMETRIC = ((-2, 3, Fraction(-716, 1000), Fraction(-715, 1000)),
              (3, -2, Fraction(-5716, 1000), Fraction(-5715, 1000)))
COUNTS = {"pre": (0, 0, 0, 1), "gu": (1, 0, 0, 1),
          "hidden": (1, 1, 0, 1), "down": (1, 1, 1, 1),
          "success": (1, 1, 1, 1)}
PERTURBED = {0: (0x3f800040, 0x40000040),
             1023: (0x40000040, 0xc13fffc0),
             2047: (0x40000040, 0xc13fffc0)}


def word_value(word):
    # Independently decoded IEEE32 via exact binary64 widening.
    return Fraction(struct.unpack('<f', struct.pack('<I', word))[0])


def rtne_word(value):
    """Exact rational to binary32; never convert via binary64."""
    value = Fraction(value)
    sign = 0x80000000 if value < 0 else 0
    v = abs(value)
    if not v:
        return sign
    e = v.numerator.bit_length() - v.denominator.bit_length()
    if v < Fraction(2) ** e:
        e -= 1
    if e > 127:
        raise ValueError('oracle overflow')
    shift = 149 if e < -126 else 23-e
    t = v * Fraction(2) ** shift
    q, r = divmod(t.numerator, t.denominator)
    if 2*r > t.denominator or (2*r == t.denominator and q & 1):
        q += 1
    if e < -126:
        return sign | q
    if q == 1 << 24:
        q >>= 1
        e += 1
    if e > 127:
        raise ValueError('oracle overflow')
    return sign | ((e+127) << 23) | (q-(1 << 23))


def activation_word(g, u):
    g, u = min(Fraction(g), 10), min(max(Fraction(u), -10), 10)
    with localcontext() as ctx:
        ctx.prec = 120
        gd = Decimal(g.numerator)/Decimal(g.denominator)
        ud = Decimal(u.numerator)/Decimal(u.denominator)
        result = gd/(1+(-gd).exp())*ud
        return rtne_word(Fraction(result))


def affine_row(packed, scales, biases, x):
    """Scalar original-byte public oracle, independent U32 decoder and Phi."""
    total = Fraction(0)
    phi = Fraction(0)
    for group in range(len(scales)//2):
        s = word_value(struct.unpack_from('<H', scales, group*2)[0] << 16)
        b = word_value(struct.unpack_from('<H', biases, group*2)[0] << 16)
        for j in range(64):
            col = group*64+j
            w = struct.unpack_from('<I', packed, col//8*4)[0]
            code = (w >> (4*(col%8))) & 15
            total += x[col]*(s*code+b)
            phi += abs(x[col])*(abs(s)*code+abs(b))
    return total, phi
