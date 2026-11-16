"""Independent binary64 goldens for five full-width packed QMM control calls.
Takes no inputs; all values are synthetic. Emit before any GPU observation.
The scalar oracle works from logical integer codes, not packed decoder/native code.
"""
import hashlib
import json
import math
import struct

CASES = ((4, 2048), (4, 4096), (8, 4096), (8, 12288), (8, 16384))
ROWS = 64


def bfword(value):
    # All operands, final exact results, and former-quartet partials fit in F32 exactly.
    raw = struct.pack("<f", value)
    assert struct.unpack("<f", raw)[0] == value
    f, = struct.unpack("<I", raw)
    return (f + 0x7fff + ((f >> 16) & 1)) >> 16


def frombf(word):
    return struct.unpack("<f", struct.pack("<I", word << 16))[0]


def u16le(words):
    return b"".join(struct.pack("<H", w) for w in words)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def case(bits, cols):
    # Each consecutive quartet contains one 1 and three 2^-8 (or all negated).
    # Rotate the large term across all four lanes. The exact quartet sum is
    # ±259/256, not BF16; signs repeat +++-, preventing cancellation of a bad
    # quartet-bias implementation merely by using symmetric signs.
    x = [(256 if j % 4 == (j // 4) % 4 else 1)
         * (-1 if (j // 4) % 4 == 3 else 1) for j in range(cols)]
    inp = [math.ldexp(float(v), -8) for v in x]
    assert all(frombf(bfword(f)) == f for f in inp)
    assert all(frombf(bfword(math.fsum(inp[j:j+4]))) != math.fsum(inp[j:j+4])
               for j in range(0, cols, 4))
    # Before BF16 rounding, every relevant F32 sum of decoded products is exact:
    # integer units 2^-16, |decoded weight * 256| <= 9 and every quartet of x
    # has 259 absolute input units. This also bounds arbitrary addition order.
    assert 9 * 259 * (cols // 4) < 2**24
    packed, scales, biases = bytearray(), [], []
    sums, golden = [], []
    changed = dict(reverse_in_word=0, missing_bias=0, wrong_group=0, bf_quartet=0)
    for r in range(ROWS):
        qrow = []
        scale, bias = [], []
        old_bias_errors = []
        for g in range(cols // 64):
            t = (r + 3*g + g//3) % 5
            center = (5 + t) if bits == 4 else (120 + 4*t)
            su = (1, 2, -3, 3)[(g + 3*r + g//5) % 4]
            if r == 1 and g == cols//64 - 1:
                su = 1
            sc, bi = math.ldexp(su, -8), math.ldexp(-center*su, -8)
            assert all(frombf(bfword(v)) == v for v in [sc, bi])
            scale.append(sc); bias.append(bi)
            for lane in range(64):
                j = g*64+lane
                if r == 0:
                    delta = 0                     # each decoded coefficient exactly zero
                elif r in (1, 2):
                    delta = 2 if lane < 32 else -2  # two dense cancelling signed half-groups
                    if r == 1 and j == cols-2:
                        delta += 1                 # tail lane: exactly -1/65536 overall
                else:
                    delta = ((13*r + 5*g + 3*lane + (lane//4)*(1+r%5) + r*(j%11) + g//3) % 7)-3
                qrow.append(center+delta)
            # Explicit negative control for the historical four-BF16-term bias sum.
            # No alternate native call. Operates on the independently defined dense input.
            if r == 0:
                for j in range(g*64, (g+1)*64, 4):
                    a,b,c,d = inp[j:j+4]
                    bad = frombf(bfword(frombf(bfword(frombf(bfword(a+b))+c))+d))
                    old_bias_errors.append(bi * (bad - math.fsum([a,b,c,d])))
        if bits == 4:
            packed.extend(qrow[j] | (qrow[j+1] << 4) for j in range(0, cols, 2))
        else:
            packed.extend(qrow)
        scales.extend(map(bfword, scale)); biases.extend(map(bfword, bias))
        # Oracle is a dense binary64 dot with compensated summation. A second,
        # integer-lattice contraction proves its exactness including cancellations.
        exact = math.fsum(v*(q*scale[j//64]+bias[j//64]) for j,(v,q) in enumerate(zip(inp,qrow)))
        units = sum(v*(q*int(scale[j//64]*256)+int(bias[j//64]*256)) for j,(v,q) in enumerate(zip(x,qrow)))
        assert exact == math.ldexp(units, -16)
        target = bfword(exact)
        sums.append(units); golden.append(target)
        stride = 32//bits
        wrong = math.fsum(v*(qrow[j//stride*stride+stride-1-j%stride]*scale[j//64]+bias[j//64]) for j,v in enumerate(inp))
        changed['reverse_in_word'] += (bfword(wrong) != target)
        wrong = math.fsum(v*qrow[j]*scale[j//64] for j,v in enumerate(inp))
        # This mutant can lie outside the proof for correct outputs. It is
        # sufficient to demonstrate a gross change without rounding the mutant.
        changed['missing_bias'] += (abs(wrong-exact) > max(0.01, abs(exact)/64))
        wrong = math.fsum(v*(qrow[j]*scale[(j//64+1)%len(scale)]+bias[(j//64+1)%len(bias)]) for j,v in enumerate(inp))
        changed['wrong_group'] += (abs(wrong-exact) > max(0.01, abs(exact)/64))
        if r == 0:
            changed['bf_quartet'] = int(bfword(math.fsum(old_bias_errors)) != target)
    assert sums[:3] == [0, -1, 0] and all(changed.values())
    return dict(bits=bits,cols=cols,rows=ROWS,sums_in_units_of_2m16=sums,
                expected_bf16=golden,sha256=[digest(u16le(map(bfword,inp))),digest(packed),
                digest(u16le(scales)),digest(u16le(biases))],mutant_rows_rejected=changed)


if __name__ == '__main__':
    print(json.dumps([case(*args) for args in CASES], sort_keys=True, separators=(',',':')))
