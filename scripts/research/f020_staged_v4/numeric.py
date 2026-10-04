"""Bounded exact original-reference mathematics; no candidate/oracle imports."""
from dataclasses import dataclass
from fractions import Fraction as F

PRECISION = 256
LATTICE = 1 << PRECISION
D0 = (1 << 94)*((1 << 24)-273)
DEN_E = D0**3*LATTICE
FLOOR = F(1, 1 << 32)
E_ACT = F(1, 128)
TAU = F(1, 1 << 126)


class Refusal(ValueError):
    pass


def require(ok, why):
    if not ok:
        raise Refusal(why)


def bounded(v, bits=4096):
    require(type(v) in (int, F), 'exact rational type')
    v = F(v)
    require(abs(v.numerator).bit_length() <= bits and v.denominator.bit_length() <= bits,
            'arithmetic bitlength')
    return v


def integer(v, bits=768):
    require(type(v) is int and abs(v).bit_length() <= bits, 'accumulator bitlength')
    return v


def add(a, b):
    return bounded(bounded(a)+bounded(b))


def times(a, b):
    return bounded(bounded(a)*bounded(b))


def divide(a, b):
    require(b != 0, 'zero denominator')
    return bounded(bounded(a)/bounded(b))


def outward(lo, hi, precision=PRECISION):
    require(type(precision) is int and precision == PRECISION, 'fixed precision')
    lo, hi = bounded(lo), bounded(hi)
    require(lo <= hi, 'interval order')
    return F((lo*LATTICE).__floor__(), LATTICE), F((hi*LATTICE).__ceil__(), LATTICE)


def interval(value, width=False):
    require(type(value) is tuple and len(value) == 2, 'immutable interval')
    lo, hi = map(bounded, value)
    require(lo <= hi, 'interval order')
    require((lo*LATTICE).denominator == (hi*LATTICE).denominator == 1, 'interval lattice')
    if width:
        require(hi-lo <= F(1, 1 << 160), 'interval width')
    return lo, hi


def mul_interval(a, b):
    products = [times(x, y) for x in interval(a) for y in interval(b)]
    return outward(min(products), max(products))


def exp_interval(z):
    """N80 outward Taylor, geometric tail, five squares. Fixed scratch size.

    Every operation has <=4096-bit stored operands and <=8192-bit temporary
    numerator/denominator before refusal; never an unbounded Fraction series.
    Term intervals use positive multiplication, so accumulated rounding widens.
    """
    z = bounded(z)
    require(abs(z) <= 16, 'exp domain')
    a = divide(abs(z), 32)
    term = (F(1), F(1))
    lo = hi = F(1)
    for n in range(1, 81):
        term = outward(divide(times(term[0], a), n), divide(times(term[1], a), n))
        lo, hi = outward(add(lo, term[0]), add(hi, term[1]))
    tail = divide(divide(times(term[1], a), 81), 1-divide(a, 82))
    lo, hi = outward(lo, add(hi, tail))
    for _ in range(5):
        lo, hi = outward(times(lo, lo), times(hi, hi))
    if z < 0:
        lo, hi = outward(divide(1, hi), divide(1, lo))
    return lo, hi


def activation(g, u):
    g, u = bounded(g), bounded(u)
    require(abs(g) <= 16 and abs(u) <= 16, 'activation domain')
    g, u = min(g, F(10)), min(max(u, F(-10)), F(10))
    if not g or not u:
        return F(0), F(0)
    el, eh = exp_interval(-g)
    sig = outward(divide(1, 1+eh), divide(1, 1+el))
    h = mul_interval(mul_interval(outward(g, g), sig), outward(u, u))
    return interval(h, width=True)


def endpoint_error(v, ref):
    lo, hi = interval(ref)
    v = bounded(v)
    return max(abs(v-lo), abs(v-hi))


def scale_e(e):
    value = times(e, DEN_E)
    require(value.denominator == 1, 'E common lattice')
    require(0 <= e <= 401 and value.numerator.bit_length() < 620, 'E integer envelope')
    return value.numerator


@dataclass(frozen=True)
class Lane:
    g: F
    u: F
    bg: F
    bu: F
    h: tuple
    a: F
    e: F
    old: F
    lg: F
    lu: F
    magnitude: F
    zero: bool


def lane(g, u, bg, bu):
    g, u, bg, bu = map(bounded, (g, u, bg, bu))
    require(bg >= 0 and bu >= 0, 'nonnegative budgets')
    require(-16 <= g-bg <= g+bg <= 16 and -16 <= u-bu <= u+bu <= 16,
            'original activation rectangle')
    aa, ab = min(g-bg, 10), min(g+bg, 10)
    va, vb = min(max(u-bu, -10), 10), min(max(u+bu, -10), 10)
    m = 0 if aa <= 0 <= ab else min(abs(aa), abs(ab))
    maximum, cmax = max(abs(aa), abs(ab)), max(abs(va), abs(vb))
    el, _ = exp_interval(-ab)
    q = min(F(1), outward(divide(1, 1+el), divide(1, 1+el))[1])
    p = min(F(1, 4), exp_interval(-m)[1])
    t = min(F(10), times(maximum, q))
    lg = F(0) if aa == ab else times(cmax, min(F(3, 2), add(q, times(maximum, p))))
    lu = F(0) if va == vb else t
    # A zero-width rectangle permits zero propagation along that axis.
    a = F(1, 1 << 20) + times(F(1, 1 << 23), times(cmax, t)) + TAU
    zero = (g == 0 and bg == 0) or (u == 0 and bu == 0)
    e = F(0) if zero else add(add(times(lg, bg), times(lu, bu)), a)
    old = F(0) if zero else 20*bg+10*bu+E_ACT
    require(0 <= a < F(1, 1 << 16) and e <= old, 'checked profile ceiling')
    h = (F(0), F(0)) if zero else activation(g, u)
    scale_e(e)
    if not zero:
        require(h[0]-e >= FLOOR or h[1]+e <= -FLOOR, 'prospective down nonzero floor')
    magnitude = max(abs(h[0]-e), abs(h[1]+e))
    require(magnitude <= 1 << 32, 'prospective magnitude')
    for value in (g, u, bg, bu, *h, a, e, old, lg, lu, magnitude):
        bounded(value, 768)
    return Lane(g, u, bg, bu, h, a, e, old, lg, lu, magnitude, zero)


def f32(word):
    require(type(word) is int and 0 <= word < 1 << 32, 'F32 word')
    e, m = (word >> 23) & 255, word & 0x7fffff
    require(e != 255, 'nonfinite F32')
    power = e-150 if e else -149
    if e:
        m |= 1 << 23
    value = F(m)*F(2)**power
    return -value if word >> 31 else value


def domain(values):
    require(all(v == 0 or FLOOR <= abs(v) <= 1 << 32 for v in values), 'actual input floor/magnitude')
    require(sum(map(abs, values)) <= 1 << 40, 'actual input row sum')
    require(all((v*(1 << 55)).denominator == 1 for v in values), 'actual input lattice')


def check_gu(g, u, lanes):
    require(len(g) == len(u) == len(lanes) == 2048, 'GU lane count')
    for gv, uv, ref in zip(g, u, lanes, strict=True):
        require(abs(gv) <= 16 and abs(uv) <= 16, 'candidate activation domain')
        require(abs(gv-ref.g) <= ref.bg and abs(uv-ref.u) <= ref.bu, 'GU exact bound')


def check_hidden(h, local, lanes):
    require(len(h) == len(local) == len(lanes) == 2048, 'hidden lane count')
    for v, loc, ref in zip(h, local, lanes, strict=True):
        interval(loc, width=True)
        interval(ref.h, width=True)
        require(endpoint_error(v, loc) <= ref.a and endpoint_error(v, loc) <= E_ACT, 'local activation bound')
        require(endpoint_error(v, ref.h) <= ref.e and endpoint_error(v, ref.h) <= ref.old, 'ideal hidden bound')
        require(not ref.zero or v == 0, 'exact-zero hidden')


def check_down(y, z, rounding, ideal, propagation):
    require(len(y) == len(z) == len(rounding) == len(ideal) == len(propagation) == 4096,
            'down row count')
    for v, local, r, target, d in zip(y, z, rounding, ideal, propagation, strict=True):
        require(r >= 0 and d >= 0, 'down nonnegative budget')
        require(abs(v-local) <= r, 'down local bound')
        require(endpoint_error(v, target) <= r+d, 'down ideal bound')
