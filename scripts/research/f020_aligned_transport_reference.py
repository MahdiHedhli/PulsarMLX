"""Independent integer model for the two buffered transfer modes. No file payload reader."""
import hashlib
import itertools
import json
from pathlib import Path

U64 = (1 << 64) - 1
MAX_SELECTED = 32 << 20
MAX_BACKING = MAX_SELECTED + 3 * (16384 - 1)
CONTROL = 65536
FROZEN = Path(__file__).resolve().parents[2] / "docs/research/f020/m4c-aligned-transport/corpus.json"


def sizes(a):
    return sorted({0, 1, a - 1, a, a + 1, 2 * a + 1})


def corpus():
    for a in (1, 2, 4, 8, 16):
        for length in range(2 * a + 2):
            yield from ((a, length, offset, n) for offset, n in
                        itertools.product(range(length + 2), sizes(a)))
    for a in (4096, 16384):
        lengths = (a-1, a, a+1, 2*a-1, 2*a, 2*a+1, 3*a+17)
        offsets = (0, 1, a-1, a, a+1, 2*a-1, 2*a, 2*a+1)
        yield from itertools.product([a], lengths, offsets, sizes(a))


def geometry(a, length, offset, n, native=U64, public=False):
    if public and a not in (4096, 16384):
        return ["alignment"]
    if n == 0:
        return ["empty"]
    end = offset + n
    if end > U64:
        return ["end-overflow"]
    if end > length:
        return ["out-of-file"]
    start = (offset // a) * a
    quotient, remainder = divmod(end, a)
    upper = (quotient + bool(remainder)) * a
    if upper > U64:
        return ["round-overflow"]
    if upper > length:
        kind, start, size, delta = "buffered-edge-exact", offset, n, 0
    else:
        kind, size, delta = "buffered-aligned-window", upper - start, offset - start
    if max(n, size, delta) > native:
        return ["native-size"]
    return [kind, start, size, delta]


def backing(a, largest, selected, native=U64):
    if a not in (4096, 16384):
        return ["alignment"]
    if not 0 < selected <= MAX_SELECTED:
        return ["selected-limit"]
    required = largest + a - 1
    if required > U64:
        return ["backing-overflow"]
    if required > MAX_BACKING:
        return ["backing-limit"]
    if required > native:
        return ["native-size"]
    return ["backing", required]


def reservation(back, control, budget):
    if control > CONTROL:
        return ["control-limit"]
    if back > MAX_BACKING:
        return ["backing-limit"]
    total = back + CONTROL
    return ["reservation", total] if total <= budget else ["budget"]


NAMED = [
    ("endpoint-overflow", "geometry", [4096,U64,U64-2,3,U64,True]),
    ("rounded-overflow", "geometry", [16384,U64,U64-3,3,U64,True]),
    ("aligned-near-maximum", "geometry", [4096,U64,U64-8191,4096,U64,True]),
    ("high-offset-small-native", "geometry", [4096,U64,1<<45,32,65535,True]),
    ("window-native-conversion", "geometry", [16384,65536,1,65535,65535,True]),
    ("edge-native-conversion", "geometry", [4096,65537,0,65537,65535,True]),
    ("no-empty", "geometry", [4096,0,0,0,U64,True]),
    ("small-public", "geometry", [16,1024,0,1,U64,True]),
    ("zero-alignment", "geometry", [0,2,0,1,U64,True]),
    ("unsupported-nonpower", "geometry", [12288,16384,1,1,U64,True]),
    ("maximum-backing", "backing", [16384,MAX_SELECTED+32766,MAX_SELECTED,U64]),
    ("backing-one-over", "backing", [16384,MAX_SELECTED+32767,MAX_SELECTED,U64]),
    ("backing-add-overflow", "backing", [4096,U64,1,U64]),
    ("backing-native-limit", "backing", [4096,65536,4096,65535]),
    ("selected-one-over", "backing", [16384,16384,MAX_SELECTED+1,U64]),
    ("control-at-cap", "reservation", [MAX_BACKING,CONTROL,MAX_BACKING+CONTROL]),
    ("control-one-over", "reservation", [4096,CONTROL+1,U64]),
    ("retained-over-cap", "reservation", [MAX_BACKING+1,1,U64]),
    ("one-byte-short", "reservation", [MAX_BACKING,CONTROL,MAX_BACKING+CONTROL-1]),
]


def named_records():
    operations = {"geometry": geometry, "backing": backing, "reservation": reservation}
    return [[name, operation, args, operations[operation](*args)] for name, operation, args in NAMED]


def encoded(row):
    return (json.dumps(row, ensure_ascii=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def freeze():
    digest = hashlib.sha256()
    census = {}
    for args in corpus():
        outcome = geometry(*args)
        digest.update(encoded([*args, outcome]))
        census[outcome[0]] = census.get(outcome[0], 0) + 1
    named = named_records()
    return dict(schema="buffered-window-corpus/1", order="ascending A,L,o,n; duplicate n removed; one compact JSON array and LF per record",
                small=5489, public=672, total=sum(census.values()), census=census,
                ordered_sha256=digest.hexdigest(), named=named,
                named_sha256=hashlib.sha256(b"".join(map(encoded,named))).hexdigest())


def verify_capture(directory):
    """Compare observed rows with the independent integer model and immutable recipe data."""
    directory = Path(directory)
    expected = b"".join(encoded([*args, geometry(*args)]) for args in corpus())
    if (directory / "integer.jsonl").read_bytes() != expected:
        raise ValueError("ordered geometry population differs")
    if (directory / "named.jsonl").read_bytes() != b"".join(map(encoded, named_records())):
        raise ValueError("named boundary population differs")

    fixtures = FROZEN.parents[4] / "fixtures" / "resident-expert-mlp"
    recipes = json.loads((fixtures / "manifest.json").read_bytes())["recipes"]
    seen = set()
    totals = {}
    roles = ("gate", "up", "down")
    for line in (directory / "real.jsonl").read_bytes().splitlines():
        profile, expert, old, r = json.loads(line)
        role, mode, a = r["role"], r["mode"], r["alignment"]
        key = profile, expert, role, a, mode
        if key in seen:
            raise ValueError("duplicate fixture observation")
        seen.add(key)
        recipe = recipes[profile]
        plane = recipe["planes"][expert][roles.index(role)]
        assert old["actual_sha256"] == plane["sha256"]
        assert old["plane"]["ranges"] == plane["ranges"]
        assert old["metadata_snapshot_sha256"] == recipe["metadata"]
        logical = candidate = requested = copied = copies = edges = largest = 0
        for i, bounds in enumerate(plane["ranges"]):
            o, n = bounds["begin"], bounds["len"]
            length = (fixtures / recipe["name"] / bounds["shard"]).stat().st_size
            assert length == r["descriptor_lengths"][i]
            window = geometry(a, length, o, n)
            def fields(w):
                return [w["kind"], w["begin"], w["bytes"], w["delta"]]
            assert fields(r["windows"][i]) == window
            transfer = ["buffered-exact", o, n, 0] if mode == "BufferedExact" else window
            assert fields(r["transfers"][i]) == transfer
            bounce = transfer[0] == "buffered-aligned-window"
            assert r["effects"][i] == dict(attempted=True, returned_bytes=transfer[2], copied=n if bounce else 0)
            logical += n
            candidate += window[2]
            requested += transfer[2]
            copied += n if bounce else 0
            copies += int(bounce)
            edges += int(transfer[0] == "buffered-edge-exact")
            largest = max(largest, window[2])
        ledger = r["ledger"]
        assert logical == r["logical_requested"] == r["logical_delivered"] == ledger["logical_bytes"] == old["requested_bytes"]
        assert requested == r["requested"] == r["completed"]
        assert requested - logical == r["attempted_overread"] == r["completed_overread"]
        assert candidate == ledger["candidate_bytes"] and candidate - logical == r["candidate_overread"]
        assert r["copies"] == copies and r["copied"] == copied and r["edge_attempts"] == edges
        assert r["logical_attempts"] == r["attempted"] == old["range_attempts"] == 3
        assert r["published"] and r["coalescing_overread"] == 0
        assert all(r[k] is None for k in ("physical_bytes", "syscalls", "cache_observed"))
        back = largest + a - 1
        assert ledger["minimum_backing"] == ledger["backing_bytes"] == back
        assert ledger["largest_request"] == largest and ledger["head_slack"] < a
        assert ledger["head_slack"] + ledger["usable_bytes"] == back
        assert ledger["tail_slack"] + largest == ledger["usable_bytes"]
        assert 0 < ledger["control_required"] <= ledger["control_reserved"] == CONTROL
        assert ledger["additional_reservation"] == back + CONTROL
        totals_key = (profile, a, mode)
        row = totals.setdefault(totals_key, dict(roles=0, logical=0, requested=0, overread=0, copies=0, copied=0, edges=0))
        for k, v in zip(row, (1, logical, requested, requested-logical, copies, copied, edges)):
            row[k] += v
    arms = ["BufferedExact","BufferedAlignedWindow"]
    assert seen == set(itertools.product(recipes, range(3), roles, (4096,16384), arms))
    return [[*group, row] for group, row in sorted(totals.items())]
