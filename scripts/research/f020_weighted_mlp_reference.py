"""Independent dyadic integer binary32 model for the controlled host fixture."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/weighted-expert-mlp"
INPUT = "3c563f14ae18c17c9365324c2fd265ee96251a3448d5ae43e0fee1474cd5233c"
WEIGHTS = (0, 0x3e800000, 0x3f000000, 0x3f400000, 0x3f800000)
SIGN = 1 << 31


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def bounded(path, limit=1 << 20):
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("input size")
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input grew")
    return data


def decode(word):
    if type(word) is not int or not 0 <= word < 1 << 32:
        raise ValueError("word")
    e, m = (word >> 23) & 255, word & 0x7fffff
    if e == 255:
        raise ValueError("nonfinite word")
    return word & SIGN, (1 << 23 | m) if e else m, e - 150 if e else -149


def rounded(sign, magnitude, exponent):
    if not magnitude:
        return sign
    top = magnitude.bit_length() - 1 + exponent
    unit = max(-149, top - 23)
    shift = unit - exponent
    if shift > 0:
        q, rem = divmod(magnitude, 1 << shift)
        half = 1 << (shift - 1)
        q += rem > half or (rem == half and q & 1)
    else:
        q = magnitude << -shift
    if q < 1 << 23:
        return sign | q
    if q == 1 << 24:
        q >>= 1
        unit += 1
    field = unit + 150
    if field >= 255:
        raise OverflowError("binary32 overflow")
    return sign | (field << 23) | (q - (1 << 23))


def multiply(a, b):
    sa, ma, ea = decode(a)
    sb, mb, eb = decode(b)
    return rounded(sa ^ sb, ma * mb, ea + eb)


def add(a, b):
    sa, ma, ea = decode(a)
    sb, mb, eb = decode(b)
    e = min(ea, eb)
    total = ((-ma if sa else ma) << (ea-e)) + ((-mb if sb else mb) << (eb-e))
    sign = SIGN if total < 0 or (total == 0 and sa and sb) else 0
    return rounded(sign, abs(total), e)


def words(values):
    return b"".join(struct.pack("<I", x) for x in values)


def field(blob):
    return words([len(blob)]) + blob


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def report(config=None):
    if config is None:
        config = json.loads(bounded(FIXTURE / "routes.json"), object_pairs_hook=unique)
    if (type(config) is not dict or set(config) != {"routes", "patterns", "lanes"}
            or type(config["lanes"]) is not int or type(config["routes"]) is not list
            or type(config["patterns"]) is not dict or set(config["patterns"]) != {"mixed", "default"}):
        raise ValueError("fixture layout")
    routes = config["routes"]
    if config["lanes"] != 128 or not 1 <= len(routes) <= 5:
        raise ValueError("book limits")
    plans = []
    count = 0
    for plan in routes:
        if type(plan) is not list or not 1 <= len(plan) <= 3:
            raise ValueError("plan length")
        count += len(plan)
        if count > 12:
            raise ValueError("occurrence limit")
        units = 0
        for pair in plan:
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("term layout")
            expert, weight = pair
            if type(expert) is not int or not 0 <= expert < 3 or type(weight) is not int:
                raise ValueError("occurrence")
            units += WEIGHTS.index(weight)
        if units != 4:
            raise ValueError("quarters")
        plans.append(b"weighted-plan-v1\0" + words([len(plan)]) +
                     words(v for pair in plan for v in pair))
    manifest = bounded(ROOT / "fixtures/resident-expert-mlp/manifest.json")
    profiles = {}
    for profile, bits in (("default", [4,4,4]), ("mixed", [8,4,8])):
        row = json.loads(manifest, object_pairs_hook=unique)["recipes"][profile]
        header = (b"weighted-book-v1\0" + field(profile.encode()) +
                  field(b"binary32-rne-mul-then-add-v1") + bytes.fromhex(sha(manifest)) +
                  bytes.fromhex(row["content"]) + bytes.fromhex(INPUT) +
                  words([1,128,64,3,64,0] + bits + [len(plans)]))
        patterns = config["patterns"][profile]
        if type(patterns) is not list or len(patterns) != 3:
            raise ValueError("expert count")
        for pattern in patterns:
            if type(pattern) is not list or not 1 <= len(pattern) <= 128 or 128 % len(pattern):
                raise ValueError("lane pattern")
            for value in pattern:
                decode(value)
        outputs = []
        for route in routes:
            lanes = [0]*128
            for expert, weight in route:
                pattern = patterns[expert]
                lanes = [add(previous, multiply(weight, pattern[i % len(pattern)]))
                         for i, previous in enumerate(lanes)]
            outputs.append(dict(bits=lanes, sha256=sha(words(lanes))))
        profiles[profile] = dict(book=sha(header + b"".join(map(field, plans))), outputs=outputs)
    return dict(plan_sha256=list(map(sha, plans)), profiles=profiles)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = (json.dumps(report(), indent=2) + "\n").encode()
    if len(result) > 8 << 20:
        raise ValueError("report limit")
    if args.check:
        if bounded(FIXTURE / "expected.json", 8 << 20) != result:
            raise ValueError("golden mismatch")
    else:
        import sys
        sys.stdout.buffer.write(result)
