"""MIT. PulsarMLX authored literal test oracle; no adapter/candidate helpers."""
import math
from scripts.research.glm53_flash.native_preparation_model_state_v1 import oracle as chronological

DESCRIPTOR = ('toy-checkpoint', 'graph-v1', 'recipe-v1')
INITIAL = (((1., -2., 3.), (.5, 1.5, -.25)), ((0.,)*7, (0.,)*7))
K = ((0.,)*7, (.25, -.5), .75)
NZ = ((.125, -.25, .375, -.5, .625, -.75, .875), (.25, -.5), .75)
S = ((.25, -.5), (.75, -1.), (.5, .25), 1., (.25, .5, -.75), (1., -.5, .25), (1., -2., 3.))
WORDS = {
    0.: '0000000000000000', .125: '000000000000c03f',
    .25: '000000000000d03f', -.25: '000000000000d0bf',
    .375: '000000000000d83f', .5: '000000000000e03f', -.5: '000000000000e0bf',
    .625: '000000000000e43f', .75: '000000000000e83f', -.75: '000000000000e8bf',
    .875: '000000000000ec3f', 1.: '000000000000f03f', -1.: '000000000000f0bf',
    -2.: '00000000000000c0', 3.: '0000000000000840',
}
TRUNK = b'0123456789abcdef'
IDLE = (16384, 0, 0, 0)
ACTIVE = (65536, 32768, 8192, 8192)
SUCCESS = (16384, 32768, 0, 0)
ZERO = (0,)*6
TERMINAL = (16, 0, 0, 0, 0, 0)
SUCCESS_EVENTS = (
    ('reserve:0', (0,80,0,8,80,0), 1),
    ('reserve:1', (0,208,0,16,208,0), 2),
    ('reserve:2', (16,208,0,24,224,0), 3),
    ('admit:0', (16,208,0,24,144,0), 3),
    ('admit:1', (16,208,0,24,16,0), 3),
    ('admit:2', (16,208,0,24,0,0), 3),
    ('ack:0:completed', (16,208,0,16,0,0), 3),
    ('ack:1:completed', (16,208,0,8,0,0), 3),
    ('ack:2:completed', (16,208,0,0,0,0), 3),
    ('evict:0', (16,128,0,0,0,0), 2),
    ('evict:1', TERMINAL, 1),
    ('release:2', TERMINAL, 1),
)


def payload(token, count=1):
    values = tuple(x for part in token for x in (part if isinstance(part, tuple) else (part,)))
    return bytes.fromhex(''.join(WORDS[x] for x in values))*count


def decode_word(word):
    """Independent integer IEEE754 expansion; no struct or adapter decoder."""
    bits = int.from_bytes(word, 'little')
    sign = -1 if bits >> 63 else 1
    exponent = (bits >> 52) & 2047
    fraction = bits & ((1 << 52)-1)
    if exponent == 2047:
        return math.nan if fraction else sign*math.inf
    if exponent == 0:
        return math.copysign(math.ldexp(float(fraction), -1074), sign)
    return sign*math.ldexp(float((1 << 52)+fraction), exponent-1075)


def kda_expected(token=K, count=1):
    taps = tuple(((c+1)/32, -(c+2)/64, (c+3)/32) for c in range(7))
    return chronological.kda((token,)*count, taps, INITIAL)
