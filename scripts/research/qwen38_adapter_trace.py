"""Bounded synthetic operation tape and catalog/operation-aware replay.

This is a fixture protocol, not the production prefetch-trace schema or proof
of real routing, GPU completion, numerical parity, memory or physical SSD I/O.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import struct
from dataclasses import asdict, dataclass
from types import MappingProxyType

from qwen38_page_catalog import PageCatalog, PageKey

SCHEMA = "pulsarmlx.qwen38.adapter-fixture/1"


class TraceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise TraceError(message)


def key_name(key):
    return f"L{key.layer}:E{key.index}" if key.kind == "expert" else f"L{key.layer}:P{key.index}:{key.block}"


def parse_key(name):
    if type(name) is not str:
        raise TraceError("invalid page address")
    e = re.fullmatch(r"L(\d+):E(\d+)", name)
    p = re.fullmatch(r"L(\d+):P(\d+):(\d+)", name)
    if not e and not p:
        raise TraceError("invalid page address")
    key = PageKey("expert", int(e[1]), int(e[2])) if e else PageKey("ple", int(p[1]), int(p[2]), int(p[3]))
    require(key_name(key) == name, "noncanonical address")
    return key


def spans(spec):
    return [asdict(span) for span in spec.spans]


def catalog_identity(catalog):
    data = [(name, asdict(ref)) for name, ref in sorted(catalog.tensors.items())]
    geometry = [catalog.layers, catalog.experts, catalog.ple_layer, catalog.ple_shards,
                catalog.ple_rows_per_page, sorted(catalog.ple_rows.items())]
    return hashlib.sha256(json.dumps([geometry, data], sort_keys=True).encode()).hexdigest()


def file_identity(files):
    rows = [(name, f.size, f.algorithm, f.expected_digest, f.identity)
            for name, f in sorted(files.files.items())]
    return hashlib.sha256(json.dumps([files.root_identity, rows]).encode()).hexdigest()


@dataclass(frozen=True)
class FrozenCatalog:
    _catalog: PageCatalog
    signature: str
    file_signature: str

    @classmethod
    def capture(cls, catalog, files):
        require(type(catalog) is PageCatalog, "exact admitted catalog required")
        clone = PageCatalog(dict(catalog.tensors), layers=catalog.layers, experts=catalog.experts,
                            ple_layer=catalog.ple_layer, ple_shards=catalog.ple_shards,
                            ple_rows_per_page=catalog.ple_rows_per_page)
        clone.tensors = MappingProxyType(clone.tensors)
        clone.ple_rows = MappingProxyType(clone.ple_rows)
        return cls(clone, catalog_identity(clone), file_identity(files))

    def page(self, key):
        return self._catalog.page(key)

    def ple_key_for_global_row(self, row):
        return self._catalog.ple_key_for_global_row(row)

    @property
    def tensors(self):
        return self._catalog.tensors


@dataclass(frozen=True, init=False)
class SyntheticOperations:
    """Immutable deterministic fixture router/lookup table; never runs a model."""
    routes: object
    ple_rows: object

    def __init__(self, *, routes, ple_rows):
        checked = {}
        require(type(routes) is dict and type(ple_rows) is dict and len(routes) <= 64 and len(ple_rows) <= 64,
                "bounded synthetic operation tables required")
        for address, value in routes.items():
            require(type(address) is tuple and len(address) == 2 and
                    all(type(n) is int and n >= 0 for n in address), "invalid route address")
            require(type(value) is tuple and len(value) == 2, "invalid synthetic route result")
            selected, weights = value
            require(type(selected) is tuple and type(weights) is tuple and bool(selected) and
                    len(selected) == len(set(selected)) == len(weights) and len(selected) <= 512 and
                    all(type(n) is int and n >= 0 for n in selected) and
                    all(type(w) is float and math.isfinite(w) and w >= 0 for w in weights) and
                    abs(sum(weights) - 1) <= 1e-9, "invalid synthetic routing")
            checked[address] = (selected, weights)
        for address, row in ple_rows.items():
            require(type(address) is tuple and len(address) == 2 and
                    all(type(n) is int and n >= 0 for n in address) and
                    type(row) is int and row >= 0, "invalid PLE operation")
        object.__setattr__(self, "routes", MappingProxyType(checked))
        object.__setattr__(self, "ple_rows", MappingProxyType(dict(ple_rows)))

    def route(self, step, layer):
        return self.routes[(step, layer)]

    def ple(self, step, lookup):
        return self.ple_rows[(step, lookup)]


def weight_digest(weights):
    return hashlib.sha256(b"".join(struct.pack("<d", w) for w in weights)).hexdigest()


class Tape:
    """Metadata is bounded; reserve a separate cleanup margin on overflow."""
    def __init__(self, clock):
        self.clock = clock
        self.events = []
        self.serialized_bytes = 0

    def emit(self, kind, *, cleanup=False, **fields):
        event = {"type": kind, "t_ns": self.clock(), **fields}
        encoded = json.dumps(event, sort_keys=True).encode()
        cap = 1536 if cleanup else 1024
        byte_cap = 192 * 1024 if cleanup else 128 * 1024
        require(len(self.events) < cap and self.serialized_bytes + len(encoded) <= byte_cap, "trace metadata cap")
        require(type(event["t_ns"]) is int and event["t_ns"] >= 0 and
                (not self.events or event["t_ns"] >= self.events[-1]["t_ns"]), "invalid trace clock")
        self.events.append(event)
        self.serialized_bytes += len(encoded)
        return event["t_ns"]

    def report(self, catalog, retained_bytes):
        counters = dict(admitted=0, useful=0, late=0, wasted=0)
        for event in self.events:
            if event["type"] == "read_start" and event["purpose"] == "hint": counters["admitted"] += event["bytes"]
            if event["type"] == "hint_terminal": counters[event["classification"]] += event["bytes"]
        return {"schema": SCHEMA, "scope": "synthetic operations and owning payloads only",
                "catalog_signature": catalog.signature, "events": copy.deepcopy(self.events),
                "file_signature": catalog.file_signature,
                "hint_bytes": counters, "retained_owner_bytes": retained_bytes,
                "physical_ssd_measurement": "unavailable", "physical_ssd_read_bytes": None}


def validate(report, catalog, operations):
    """Replay against independently supplied fixture operation table/catalog."""
    require(type(catalog) is FrozenCatalog and type(operations) is SyntheticOperations, "fixture authorities required")
    require(report.get("schema") == SCHEMA and report.get("catalog_signature") == catalog.signature and
            report.get("file_signature") == catalog.file_signature,
            "wrong trace/catalog identity")
    require(report.get("physical_ssd_measurement") == "unavailable" and report.get("physical_ssd_read_bytes") is None,
            "synthetic trace cannot attribute SSD traffic")
    events = report.get("events")
    require(type(events) is list and len(events) <= 1536 and len(json.dumps(events).encode()) <= 256 * 1024,
            "trace metadata cap")
    require(type(report.get("retained_owner_bytes")) is int and report["retained_owner_bytes"] >= 0,
            "invalid retained owner count")
    summary = report.get("hint_bytes")
    require(type(summary) is dict and set(summary) == {"admitted", "useful", "late", "wasted"} and
            all(type(n) is int and n >= 0 for n in summary.values()), "invalid hint byte summary")
    op_keys, demands, reads, ready, leases = {}, {}, {}, {}, {}
    demanded_operations = set()
    hints = set(); operations_seen = set(); cancelled = False; previous = -1
    counters = dict(admitted=0, useful=0, late=0, wasted=0)
    for e in events:
        require(type(e) is dict and type(e.get("t_ns")) is int and e["t_ns"] >= previous and e["t_ns"] >= 0,
                "invalid event/time")
        previous = e["t_ns"]; kind = e.get("type")
        for field in ("id", "step", "layer", "lookup", "global_row", "operation", "demand", "read", "lease", "completion"):
            if field in e:
                require(type(e[field]) is int and e[field] >= 0, "invalid event identity/address")
        if kind == "route":
            address = (e["step"], e["layer"])
            require(not cancelled and ("route", address) not in operations_seen and e["id"] not in op_keys,
                    "duplicate/cancelled route")
            try: selected, weights = operations.route(*address)
            except KeyError as exc: raise TraceError("unknown route operation") from exc
            require(type(e["selected"]) is list and type(e["executed"]) is list and type(e["weights"]) is list and
                    all(type(n) is int for n in e["selected"] + e["executed"]) and
                    all(type(w) is float for w in e["weights"]) and
                    e["selected"] == e["executed"] == list(selected) and e["weights"] == list(weights) and
                    e["weights_digest"] == weight_digest(weights) == weight_digest(e["weights"]),
                    "route differs from executed operation")
            keys = {key_name(PageKey("expert", e["layer"], n)) for n in selected}
            for key in keys: catalog.page(parse_key(key))
            operations_seen.add(("route", address)); op_keys[e["id"]] = keys
        elif kind == "ple":
            address = (e["step"], e["lookup"])
            require(not cancelled and ("ple", address) not in operations_seen and e["id"] not in op_keys,
                    "duplicate/cancelled PLE operation")
            try: row = operations.ple(*address)
            except KeyError as exc: raise TraceError("unknown PLE operation") from exc
            key = key_name(catalog.ple_key_for_global_row(row))
            require(e["global_row"] == row and e["key"] == key, "PLE differs from lookup/catalog")
            operations_seen.add(("ple", address)); op_keys[e["id"]] = {key}
        elif kind == "demand":
            pair = (e["operation"], e["key"])
            require(not cancelled and e["id"] not in demands and e["key"] in op_keys.get(e["operation"], set()) and
                    pair not in demanded_operations,
                    "demand lacks actual operation")
            demanded_operations.add(pair)
            demands[e["id"]] = dict(key=e["key"], at=e["t_ns"], used=False)
        elif kind == "hint":
            require(not cancelled and e["key"] not in hints and e["key"] not in ready and
                    not any(d["key"] == e["key"] and not d["used"] for d in demands.values()), "invalid hint")
            catalog.page(parse_key(e["key"])); hints.add(e["key"])
        elif kind == "read_start":
            require(not cancelled and e["id"] not in reads and e["key"] not in ready and
                    not any(r["key"] == e["key"] and r["status"] == "pending" for r in reads.values()), "duplicate read")
            spec = catalog.page(parse_key(e["key"]))
            require(type(e["bytes"]) is int and e["bytes"] == spec.size_bytes and
                    json.dumps(e["spans"], sort_keys=True) == json.dumps(spans(spec), sort_keys=True),
                    "read bytes/spans differ from catalog")
            waiting = [d for d in demands.values() if not d["used"] and d["key"] not in ready]
            require(e["purpose"] in ("hint", "demand"), "invalid read purpose")
            if e["purpose"] == "hint":
                require(e["key"] in hints and not waiting, "hint overtook actual demand")
                counters["admitted"] += e["bytes"]
            else: require(any(d["key"] == e["key"] for d in waiting), "read lacks demand")
            hints.discard(e["key"])
            reads[e["id"]] = dict(key=e["key"], size=e["bytes"], purpose=e["purpose"], status="pending",
                                  used=False, classification=None, terminal=False, retired=False)
        elif kind in ("read_done", "read_failed", "read_cancelled"):
            r = reads.get(e["id"]); require(r is not None and r["status"] == "pending", "unmatched read completion")
            r["status"] = kind; r["done_at"] = e["t_ns"]
            if kind == "read_done":
                require(not cancelled and type(e.get("payload_sha256")) is str and
                        re.fullmatch(r"[0-9a-f]{64}", e["payload_sha256"]) is not None,
                        "read adopted after cancellation or missing payload identity")
                r["digest"] = e["payload_sha256"]; ready[r["key"]] = e["id"]
        elif kind == "borrow":
            d = demands.get(e["demand"]); r = reads.get(e["read"])
            require(not cancelled and e["lease"] not in leases and d is not None and not d["used"] and
                    r is not None and ready.get(d["key"]) == e["read"] and type(e["device_bytes"]) is int and
                    e["device_bytes"] == r["size"] and e["completion"] == e["lease"] and
                    e.get("payload_sha256") == r["digest"],
                    "borrow lacks actual read/demand or duplicate bytes")
            d["used"] = True; leases[e["lease"]] = dict(read=e["read"], completion=e["completion"], done=False, released=False)
            if r["purpose"] == "hint" and not r["used"]:
                r["classification"] = "useful" if r["done_at"] <= d["at"] else "late"
            r["used"] = True
        elif kind == "completion":
            lease = leases.get(e["lease"])
            require(lease is not None and not lease["done"] and e["completion"] == lease["completion"], "forged completion")
            lease["done"] = True
        elif kind == "release":
            lease = leases.get(e["lease"])
            require(lease is not None and lease["done"] and not lease["released"], "release before completion")
            lease["released"] = True
        elif kind == "retire":
            r = reads.get(e["id"])
            require(r is not None and r["status"] != "pending" and not r["retired"] and
                    not any(l["read"] == e["id"] and not l["released"] for l in leases.values()), "retire before drain")
            r["retired"] = True; ready.pop(r["key"], None)
        elif kind == "hint_terminal":
            r = reads.get(e["id"])
            require(r is not None and r["purpose"] == "hint" and r["retired"] and not r["terminal"] and
                    type(e["bytes"]) is int and e["bytes"] == r["size"] and
                    e["classification"] == (r["classification"] if r["used"] else "wasted"),
                    "hint terminal accounting mismatch")
            r["terminal"] = True; counters[e["classification"]] += r["size"]
        elif kind == "cancel":
            require(not cancelled, "duplicate cancellation"); cancelled = True
        else:
            raise TraceError("unknown fixture event")
    require(all(r["retired"] and (r["purpose"] != "hint" or r["terminal"]) for r in reads.values()) and
            all(l["released"] for l in leases.values()) and
            (cancelled or all(d["used"] for d in demands.values())) and report.get("retained_owner_bytes") == 0,
            "trace ended before operations/owners drained")
    require(report.get("hint_bytes") == counters and counters["admitted"] == counters["useful"] + counters["late"] + counters["wasted"],
            "admitted hint bytes not reconciled")
