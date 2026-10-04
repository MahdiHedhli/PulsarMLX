"""MIT. Independently authored deterministic synthetic inputs; no model bytes.

Seven tokens, unequal key/value=2/3, raw convolution width=7, kernel=3.
All values are tiny dyadics except explicit mathematical constants.
"""


def kda_tokens(count=7, salt=0):
    return tuple((tuple((((t+1)*(c+3)+salt) % 17-8)/32 for c in range(7)),
                  ((t-3)/16, (2-t)/32), (t-2)/16) for t in range(count))


def sparse_tokens(count=7, salt=0):
    # Index Q/K width 2 and attention Q/K width 3 are independent boundaries.
    return tuple((((t+1+salt)/16, ((t*3+salt) % 7-3)/8),
                  ((t-2)/8, (3-t)/16),
                  ((4-t)/16, (t+2)/8), .75,
                  ((t+3)/16, (salt-t)/8, (t % 3-1)/4),
                  ((2-t)/8, (t+salt+1)/16, (3*t % 5-2)/8),
                  ((t+1)/8, (2-t)/16, ((t*2+salt) % 5-2)/4)) for t in range(count))


def initial_kda():
    return (((.125, -.25, .375), (-.5, .0625, .25)),
            (tuple((c-3)/32 for c in range(7)), tuple((4-c)/16 for c in range(7))))


def kernels():
    return tuple(((c+1)/32, -(c+2)/64, (c+3)/32) for c in range(7))


def mhc_case():
    return {
        'streams': tuple(tuple((i*3+d-4)/8 for d in range(3)) for i in range(4)),
        'fn': tuple(tuple(((r*5+c*3) % 19-9)/64 for c in range(12)) for r in range(24)),
        'scale': (.5, -.25, .75),
        'base': tuple((r % 7-3)/8 for r in range(24)),
        'branch': (.375, -.25, .625),
    }


def mlp_weights(salt=0):
    return {
        'gate': tuple(tuple(((r*3+c+salt) % 11-5)/8 for c in range(3)) for r in range(4)),
        'up': tuple(tuple(((r+c*2+salt) % 13-6)/8 for c in range(3)) for r in range(4)),
        'down': tuple(tuple(((r*2+c*3+salt) % 9-4)/8 for c in range(4)) for r in range(3)),
    }


def boundary_case():
    return {'embedding': tuple(tuple((i*3+d-6)/8 for d in range(3)) for i in range(5)),
            'head': tuple(tuple((i-d*2+1)/16 for d in range(3)) for i in range(5)),
            'norm': (.5, 1.25, .75), 'ids': (3, 0, 4)}
