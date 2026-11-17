"""Read only the sealed Studio017 CPU reference and audit its routing decision.

Usage: python3 -I -B -S studio018_routing.py /absolute/path/to/campaign-reference
The JSON report is written to stdout. No checkpoint, backend, or campaign launcher is used.
"""
import argparse
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys

LAYERS = range(3, 45)
EXPERTS, TOP_K, VOCAB = 288, 8, 154880
SEAL = "d0f1bd25bc0ed210bcf0a56e3bdcf0d32006ddf7b992e9f7c857370ecbd34988"
ELIGIBILITY = "6aa114a4d3236afadaf25031af91023bd7f152bdc33d94cb4b19a67d13a1048f"
LOGITS = "6e79c894992ab92e8d912384d3da4529591fe3cf27fc8c7d223ca67ba5b61631"
OPERATION = "84bca402c0066d03b211cf24f6259ef3"
FILE_BYTES = 8 << 20
TOTAL_BYTES = 256 << 20


def require(condition, why):
    if not condition:
        raise ValueError(why)


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def from_bits(bits):
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def bits_of(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def exact_f32(x):
    require(type(x) in (int, float) and math.isfinite(x) and f32(x) == x,
            "expected a finite binary32 value")
    return Fraction(x)


def epsilon(center):
    return Fraction(1, 25000) + abs(center) / 250000


def interval_gap(selected_centers, excluded_centers, epsilon):
    require(selected_centers and excluded_centers, "both groups are required")
    low = [c - epsilon(c) for c in selected_centers]
    high = [c + epsilon(c) for c in excluded_centers]
    i = min(range(len(low)), key=low.__getitem__)
    j = max(range(len(high)), key=high.__getitem__)
    return i, j, low[i] - high[j]


def route(scores, k):
    require(type(k) is int and 0 < k < len(scores), "invalid top-k")
    centers = [exact_f32(x) for x in scores]
    ranked = sorted(range(len(centers)), key=lambda i: (-centers[i], i))
    inside, outside = ranked[:k], ranked[k:]
    i, j, gap = interval_gap([centers[n] for n in inside],
                             [centers[n] for n in outside], epsilon)
    return dict(ranked_ids=ranked, selected_ids=inside, selected_boundary=inside[i],
                unselected_boundary=outside[j], observed_gap=centers[inside[-1]]-centers[outside[0]],
                conservative_gap=gap, eligible=gap > 0)


def compare_membership(ids, expected, population):
    require(all(type(i) is int and 0 <= i < population for i in ids)
            and len(ids) == len(expected) == len(set(ids)) and set(ids) == set(expected),
            "reported expert membership disagrees with reconstructed set")


def neighbors(x, step):
    bits = bits_of(x)
    require(bits % step == 0, "value is not exactly in the declared format")
    if x == 0:
        pair = (0x80000000 | step, step)
    elif x < 0:
        pair = (bits + step, bits - step)
    else:
        pair = (bits - step, bits + step)
    result = tuple(from_bits(b) for b in pair)
    require(all(math.isfinite(y) for y in result), "outer finite neighbor unavailable")
    return result


def bf_margin(scores):
    require(len(scores) >= 2, "incomplete logits")
    lower, upper = [], []
    for x in scores:
        require(math.isfinite(x) and f32(x) == x, "nonfinite or unrepresented logit")
        lo, hi = neighbors(x, 1 << 16)
        lower.append(lo)
        upper.append(hi)
    winner = max(range(len(scores)), key=scores.__getitem__)
    rivals = [i for i in range(len(scores)) if i != winner]
    runner = max(rivals, key=scores.__getitem__)
    adverse = max(rivals, key=upper.__getitem__)
    gap = Fraction(lower[winner]) - Fraction(upper[adverse])
    return dict(winner=winner, runner_up=runner, winner_logit=scores[winner],
                runner_up_logit=scores[runner], worst_rival_id=adverse,
                lower_winner=lower[winner], upper_worst_rival=upper[adverse],
                margin=Fraction(scores[winner])-Fraction(scores[runner]),
                conservative_gap=gap, eligible=gap > 0)


def rounding_cell(x):
    lo, hi = neighbors(x, 1)
    center = exact_f32(x)
    return (Fraction(lo) + center) / 2, (Fraction(hi) + center) / 2


def selected_proportion_bounds(weight):
    """Enclose p_i / D, D = the shared rounded sum, before division rounding.

    Invert the final binary32 multiplication by 2.5, restrict to representable
    normalized fractions, then undo division rounding. Closed endpoints may
    include midpoint ties that round the other way.
    """
    lo, hi = rounding_cell(weight)
    lo, hi = lo * Fraction(2, 5), hi * Fraction(2, 5)
    # Positive binary32 encodings increase with value. Search over [0, 1].
    def lower_bound(target, strict):
        left, right = 0, 0x3f800001
        while left < right:
            mid = (left + right) // 2
            value = Fraction(from_bits(mid))
            if value < target or (strict and value == target):
                left = mid + 1
            else:
                right = mid
        return left
    first, last = lower_bound(lo, False), lower_bound(hi, True) - 1
    require(first <= last, "weight cannot be obtained from rounded normalization")
    return max(Fraction(0), rounding_cell(from_bits(first))[0]), min(Fraction(1), rounding_cell(from_bits(last))[1])


def unpack_json(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, "duplicate JSON key")
            obj[k] = v
        return obj
    def nonfinite(value):
        raise ValueError("nonfinite JSON " + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def stamp(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


@contextmanager
def directory(name, parent=None):
    fd = os.open(name, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def read_bound(fd, name, limit, expected_sha, sealed_stamp=None):
    require(name == Path(name).name and name not in (".", ".."), "invalid flat name")
    f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(f, "rb") as stream:
        st = os.fstat(f)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and 0 < st.st_size <= limit,
                "invalid type, link count or size: " + name)
        if sealed_stamp is not None:
            require(stamp(st) == sealed_stamp and stat.S_IMODE(st.st_mode) == 0o400,
                    "sealed file identity: " + name)
        data = stream.read(st.st_size)
        require(len(data) == st.st_size and hashlib.sha256(data).hexdigest() == expected_sha,
                "digest mismatch: " + name)
        require(stamp(st) == stamp(os.fstat(f)) == stamp(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                "file changed while reading: " + name)
        return data


def bind(stage):
    require(stage.is_absolute() and stage.resolve(strict=True) == stage, "canonical stage path required")
    wanted = {"logits.f32", "report.json"} | {f"{i:02}.moe.corrected.f32" for i in LAYERS}
    with directory(stage) as sd, directory("output", sd) as od:
        seal = unpack_json(read_bound(sd, "sealed.json", FILE_BYTES, SEAL))
        original = unpack_json(read_bound(sd, "eligibility.json", FILE_BYTES, ELIGIBILITY))
        require(seal["operation"] == original["operation"] == OPERATION and
                original["seal_sha256"] == SEAL, "original stage/grade bindings")
        files = seal["files"]
        require(len(files) == 558 and wanted <= files.keys() and set(files) == set(os.listdir(od))
                and stat.S_IMODE(os.fstat(od).st_mode) == 0o500, "sealed population")
        require(sum(z["stamp"][2] for z in files.values()) <= TOTAL_BYTES, "sealed byte limit")
        retained = {}
        for name, row in files.items():
            require(name in ("report.json", "logits.f32") or
                    re.fullmatch(r"[0-4][0-9]\.[a-z_]+(?:\.[a-z_]+)*\.f32", name),
                    "unexpected sealed name")
            data = read_bound(od, name, FILE_BYTES, row["sha256"], row["stamp"])
            if name in wanted:
                retained[name] = data
        require(files["logits.f32"]["sha256"] == LOGITS, "wrong full logits")
        report = unpack_json(retained.pop("report.json"))
        require(report["schema"] == "studio017-reference/1" and report["input_id"] == 154820
                and report["position"] == 0 and report["generated_token_count"] == 1
                and report["layer_count"] == 45, "reported input or geometry")
        expected = {n: {"sha256": r["sha256"], "bytes": r["stamp"][2]}
                    for n, r in files.items() if n != "report.json"}
        require(report["files"] == expected and [r["layer"] for r in report["routes"]] == list(LAYERS),
                "reference report and sealed files disagree")
        require(set(original["result"]["route_gates"]) == {str(i) for i in LAYERS},
                "original eligibility population")
        return retained, files, report, original


def number(v):
    return {"fraction": str(v), "decimal": float(v)}


def audit_route(row, raw, archived):
    require(len(raw) == EXPERTS*4, "corrected vector byte count")
    scores = struct.unpack("<288f", raw)
    calc = route(scores, TOP_K)
    ids, weights = row["ids"], row["weights"]
    compare_membership(ids, calc["selected_ids"], EXPERTS)
    require(len(weights) == TOP_K and all(0 <= exact_f32(w) <= Fraction(5, 2) for w in weights)
            and abs(math.fsum(weights) - 2.5) <= 4e-5, "invalid original normalized weights")
    a, b = calc["selected_boundary"], calc["unselected_boundary"]
    center_a, center_b = map(Fraction, (scores[a], scores[b]))
    observed, adverse = calc["observed_gap"], calc["conservative_gap"]
    # Deliberately separate exact decimal-coefficient arithmetic and the original binary64 evaluation.
    lo64 = min(scores[i] - (4e-5 + 4e-6 * abs(scores[i])) for i in calc["selected_ids"])
    hi64 = max(scores[i] + (4e-5 + 4e-6 * abs(scores[i])) for i in calc["ranked_ids"][TOP_K:])
    strongest = max(range(TOP_K), key=weights.__getitem__)
    bounds = [selected_proportion_bounds(w) for w in weights]
    dlo, dhi = bounds[strongest]
    require(dlo > 0, "no positive normalization anchor")
    proportions = [{"id": i, "weight": w, "weight_ratio": number(Fraction(w)/Fraction(weights[strongest])),
                    "sigmoid_ratio_enclosure": [str(lo/dhi), str(hi/dlo)] if j != strongest else ["1", "1"]}
                   for j, (i, w, (lo, hi)) in enumerate(zip(ids, weights, bounds))]
    return dict(layer=row["layer"], sha256=hashlib.sha256(raw).hexdigest(), count=len(scores),
                corrected_scores=scores, selected_ids=calc["selected_ids"],
                unselected_ids=calc["ranked_ids"][TOP_K:], reported_ids=ids,
                reported_order_matches=ids == calc["selected_ids"], selection_matches=True,
                selected_boundary=a, unselected_boundary=b, selected_score=scores[a], unselected_score=scores[b],
                selected_radius=number(epsilon(center_a)), unselected_radius=number(epsilon(center_b)),
                observed_gap=number(observed), reported_cutoff=row["cutoff_gap"],
                reported_cutoff_minus_exact=number(Fraction(row["cutoff_gap"])-observed),
                conservative_gap=number(adverse), binary64_gap=lo64-hi64,
                original_gap=archived["robust_lower_gap"],
                original_minus_exact=number(Fraction(archived["robust_lower_gap"])-adverse),
                binary64_matches_original=(lo64-hi64)==archived["robust_lower_gap"],
                eligible=calc["eligible"], original_eligible=archived["eligible"],
                strongest_selected_weight_id=ids[strongest], selected_proportions=proportions)


def reconstruct(stage):
    originals, files, report, original = bind(stage)
    logits = originals["logits.f32"]
    require(len(logits) == VOCAB*4, "vocabulary byte count")
    token = bf_margin(struct.unpack("<154880f", logits))
    previous_token = original["result"]["token"]
    matches = (token["winner"] == previous_token["winner"] == report["token_id"]
               and token["runner_up"] == previous_token["runner_up"] == report["runner_up"]
               and token["margin"] == Fraction(previous_token["margin"]) == Fraction(report["margin"])
               and token["conservative_gap"] == Fraction(previous_token["robust_lower_gap"])
               and token["eligible"] == previous_token["eligible"])
    token.update(margin=number(token["margin"]), conservative_gap=number(token["conservative_gap"]),
                 vocabulary=VOCAB, sha256=LOGITS, original_matches=matches)
    rows = [audit_route(row, originals[f"{row['layer']:02}.moe.corrected.f32"],
                        original["result"]["route_gates"][str(row["layer"])]) for row in report["routes"]]
    failed = [r["layer"] for r in rows if not r["eligible"]]
    return dict(schema="studio018-diagnostic/1", stage_operation=OPERATION, seal=SEAL, eligibility=ELIGIBILITY,
                bound_files=len(files), bound_bytes=sum(z["stamp"][2] for z in files.values()),
                input_id=154820, logits=token, layers=rows, failed_layers=failed,
                eligible=bool(token["eligible"] and not failed), original_eligible=original["eligible"],
                real_model_executions=0,
                unretained={"pre_sigmoid_logits": None,"absolute_sigmoid_scores": None,"bias_values": None,
                            "router_input_differences":None,"native_scores":None},
                summaries=dict(eligibility_label_differences=sum(r["eligible"]!=r["original_eligible"] for r in rows),
                               reported_order_differences=sum(not r["reported_order_matches"] for r in rows),
                               binary64_differences=sum(not r["binary64_matches_original"] for r in rows),
                               exact_arithmetic_deltas=sum(r["original_minus_exact"]["fraction"]!="0" for r in rows),
                               max_abs_exact_delta=max(abs(r["original_minus_exact"]["decimal"]) for r in rows)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_reference_stage", type=Path)
    args = parser.parse_args()
    json.dump(reconstruct(args.original_reference_stage), sys.stdout, allow_nan=False, sort_keys=True,
              separators=(",", ":"))
    print()
