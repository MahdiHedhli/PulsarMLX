"""Independent policy-route expectations from the frozen synthetic manifest."""
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/resident-expert-mlp"
MATRIX = ROOT / "docs/research/f020/m4c-fixed-policy/matrix.json"
POLICIES = ("BufferedRequested", "NoCacheRequested")


def routes(ranges, lengths, page, policy):
    if page not in (4096, 16384) or policy not in POLICIES:
        raise ValueError("unsupported policy geometry")
    result = []
    for entry in ranges:
        o, n = entry["begin"], entry["len"]
        end = o+n
        lo, hi = o//page*page, ((end+page-1)//page)*page
        if not n or not 0 <= o < end <= lengths[entry["shard"]]:
            raise ValueError("invalid bounds")
        if hi > lengths[entry["shard"]]:
            route, start, length = "buffered-edge-exact", o, n
        else:
            route = ("buffered-requested" if policy == POLICIES[0] else "nocache-requested") + "-aligned-window"
            start, length = lo, hi-lo
        result.append(dict(route=route, begin=start, bytes=length, delta=o-start, logical_begin=o, logical_bytes=n))
    return result


def population(page):
    manifest = json.loads((FIXTURES / "manifest.json").read_bytes())
    rows = []
    for recipe, expert, role, policy in itertools.product(("default","mixed"), range(3), range(3), POLICIES):
        record = manifest["recipes"][recipe]
        plane = record["planes"][expert][role]
        names = list(dict.fromkeys(r["shard"] for r in plane["ranges"]))
        lengths = {n:(FIXTURES / record["name"] / n).stat().st_size for n in names}
        rows.append(dict(recipe=recipe, expert=expert, role=plane["module"].split(".")[-1], policy=policy, hashes=plane["sha256"],
                         slots=len(names), mapping=[names.index(r["shard"]) for r in plane["ranges"]],
                         components=routes(plane["ranges"],lengths,page,policy)))
    return rows


CONTROLS = {
    "catalog": ["fresh-original identity", "one setter per fresh open for 0 and 1", "all seven stamp fields", "wrong witness", "missing", "replaced", "regular/no-follow", "symlink", "inadmissible name", "setter interruption", "mutation during setter"],
    "setup": ["unsupported platform", "page mismatch", "unsupported page", "short preparation budget", "full identity and deduplication", "three distinct shards", "setter failures at positions 0/1/2", "source already stale", "preparation survives root rename"],
    "read": ["36 real roles and 108 attempts", "exact hashes and every logical byte", "original EOF edge", "page-aligned pointer/offset/length", "prefix/header, sibling and exactly aligned window", "short read budget", "empty/short/long destination", "malformed digest", "insufficient/oversized scratch", "excessive metadata", "long multibyte checkpoint", "A/B/A scratch", "error after partial bytes at positions 0/1/2", "completed read followed by bad digest", "mapping refusal before raw read", "source stamp drift", "owned descriptor retirement"],
    "legacy": ["6161 arithmetic rows", "19 named boundaries", "72 buffered roles", "old exact and catalog controls"]
}


def verify(directory):
    directory = Path(directory)
    rows = [json.loads(line) for line in (directory/"policy-real.jsonl").read_bytes().splitlines()]
    if len(rows) != 36:
        raise ValueError("incomplete role population")
    page = rows[0][3]["setup"]["page_size"]
    expected = population(page)
    aggregate = {p:dict(cases=0, logical=0, requested=0, completed=0, copies=0, copied=0, edges=0, setters=0, attempts=0) for p in POLICIES}
    pairs = {}
    for (recipe,expert,old,r,record_size,retired), oracle in zip(rows,expected):
        setup = r["setup"]
        policy = setup["policy"]
        assert (recipe,expert,old["role"],policy)==tuple(oracle[k] for k in ("recipe","expert","role","policy"))
        assert old["actual_sha256"] == oracle["hashes"]
        assert r["components"] == oracle["components"]
        assert setup["page_size"] == setup["alignment"] == page
        assert setup["map"] == oracle["mapping"] and setup["live"] == oracle["slots"] == retired["released"]
        assert retired["live"] == setup["released"] == 0 and retired["kernel_close_observed"] is None
        assert record_size == len(json.dumps(r,separators=(",",":")).encode()) <= 32768
        assert all(r[k] is None for k in ("physical_bytes","cache_bypass_observed","syscalls","physical_memory","performance"))
        assert r["coalescing_overread"] == 0 and r["published"]
        for i,j in enumerate(setup["map"]):
            s = setup["slots"][j]
            assert s["open_attempted"] and s["fresh_owned"] and s["configured"] and s["matched"]
            assert s["original_stamp"] == s["fresh_stamp"] == setup["original_stamps"][i]
            assert len(s["fresh_stamp"]) == 32
            call = s["setter"]
            assert call["command"] == "F_NOCACHE" and call["argument"] == POLICIES.index(policy) and call["returned"] == 0 and call["errno"] is None
        lengths = [w["logical_bytes"] for w in oracle["components"]]
        requested = [w["bytes"] for w in oracle["components"]]
        edges = [w["route"]=="buffered-edge-exact" for w in oracle["components"]]
        copied = [0 if e else n for n,e in zip(lengths,edges)]
        assert r["logical_requested"] == r["logical_delivered"] == sum(lengths) == old["requested_bytes"]
        assert r["requested"] == r["completed"] == sum(requested)
        assert r["candidate_overread"] == r["attempted_overread"] == r["completed_overread"] == sum(requested)-sum(lengths)
        assert r["logical_attempts"] == r["attempted"] == 3
        assert r["edge_attempts"] == sum(edges) and r["copies"] == 3-sum(edges) and r["copied"] == sum(copied)
        assert r["effects"] == [dict(attempted=True,returned_bytes=n,copied=c) for n,c in zip(requested,copied)]
        ledger = r["ledger"]
        assert ledger["largest_request"] == max(requested) and ledger["backing_bytes"] == max(requested)+page-1
        assert ledger["backing_bytes"] == ledger["head_slack"]+ledger["usable_bytes"]
        assert ledger["usable_bytes"] == ledger["largest_request"]+ledger["tail_slack"]
        assert r["combined_reservation"] == setup["minimum_reservation"] == ledger["additional_reservation"]+65536 <= 33734653
        assert 0 < r["policy_control_required"] <= setup["policy_control"] == 65536
        key = recipe,expert,old["role"]
        comparison = (ledger,r["combined_reservation"],r["policy_control_required"],setup["binding"],setup["original_stamps"],setup["map"])
        if key in pairs:
            assert comparison == pairs[key]
        pairs[key] = comparison
        tot = aggregate[policy]
        for k,n in dict(cases=1,logical=sum(lengths),requested=sum(requested),completed=sum(requested),copies=3-sum(edges),copied=sum(copied),edges=sum(edges),setters=setup["live"],attempts=3).items():
            tot[k] += n
    assert len(pairs) == 18
    return aggregate
