"""Model-free validator for the proposed Qwen paging trace contract.

No model, MLX, Strata code, or I/O is imported or executed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


SCHEMA = "pulsarmlx.qwen38.prefetch-trace/0.3"
EXPERT_KEY = re.compile(r"L(\d+):E(\d+)\Z")
PLE_KEY = re.compile(r"L(\d+):P(\d+):(\d+)\Z")
METRICS = (
    "logical_expert_read_bytes",
    "prefetch_useful_bytes_before_demand",
    "prefetch_late_bytes",
    "prefetch_wasted_bytes",
    "peak_footprint_bytes",
    "swap_delta_bytes",
    "ttft_ns",
    "request_end_ns",
    "decode_p50_ns",
    "decode_p95_ns",
    "decode_p99_ns",
    "max_intertoken_stall_ns",
)


class ContractError(ValueError):
    """The event sequence cannot support the proposed safety claim."""


@dataclass
class Buffer:
    size: int
    io_done_at: int | None = None
    gpu_used: bool = False
    gpu_done: bool = False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def validate(trace: dict) -> None:
    _require(trace.get("schema") == SCHEMA, "wrong schema")
    for field in ("base_commit", "model_revision", "tokenizer_revision", "runtime_revision",
                  "prompt_digest", "decode_settings_digest", "logits_digest"):
        _require(isinstance(trace.get(field), str) and bool(trace[field]), f"missing {field}")
    output_ids = trace.get("output_token_ids")
    _require(isinstance(output_ids, list) and bool(output_ids) and
             all(type(token) is int and token >= 0 for token in output_ids), "invalid output token IDs")
    _require(trace.get("arm") in ("baseline", "prefetch"), "invalid arm")
    _require(trace.get("warmth") in ("cold-start", "logical-empty-os-warm", "logical-warm-os-warm"), "invalid warmth")
    request_cap = trace.get("max_prefetch_requests")
    byte_cap = trace.get("max_prefetch_bytes")
    _require(type(request_cap) is int and request_cap > 0, "invalid request cap")
    _require(type(byte_cap) is int and byte_cap > 0, "invalid byte cap")
    events = trace.get("events")
    _require(isinstance(events, list), "missing events")

    hints: set[str] = set()
    invalid: set[str] = set()
    pending_demands: set[str] = set()
    started_demands: dict[str, int] = {}
    buffers: dict[str, Buffer] = {}
    used_bytes = 0
    admitted_bytes = 0
    useful_bytes = 0
    late_bytes = 0
    wasted_bytes = 0
    previous_time = -1
    routes = 0
    routed: dict[tuple[int, int], set[int]] = {}
    ple_lookups: set[tuple[int, str]] = set()
    demand_io_started: set[str] = set()
    demand_io_done: set[str] = set()
    served_demands: set[str] = set()
    peak_used_bytes = 0
    cancelled = False
    for event in events:
        _require(isinstance(event, dict), "event is not an object")
        kind, key, now = event.get("type"), event.get("key"), event.get("t_ns")
        _require(type(now) is int and now >= 0 and now >= previous_time, "event time is not monotonic")
        previous_time = now
        if kind == "route":
            _require(not cancelled, "route after cancellation")
            layer, step = event.get("layer"), event.get("step")
            _require(type(layer) is int and layer >= 0 and type(step) is int and step >= 0,
                     "invalid route address")
            _require((step, layer) not in routed, "duplicate route address")
            selected, executed = event.get("selected"), event.get("executed")
            _require(isinstance(selected, list) and selected == executed, "prefetch changed route")
            _require(all(type(expert) is int and expert >= 0 for expert in selected), "invalid route ID")
            _require(isinstance(event.get("weights_digest"), str) and bool(event["weights_digest"]), "missing weight digest")
            routed[(step, layer)] = set(selected)
            routes += 1
            continue
        if kind == "ple_lookup":
            _require(not cancelled and type(event.get("step")) is int and event["step"] >= 0 and
                     type(event.get("global_row")) is int and event["global_row"] >= 0 and
                     isinstance(key, str) and PLE_KEY.fullmatch(key) is not None,
                     "invalid PLE lookup")
            ple_lookups.add((event["step"], key))
            continue
        if kind == "cancel":
            _require(not cancelled, "duplicate cancellation")
            cancelled = True
            invalid.update(hints)
            hints.clear()
            pending_demands.clear()
            started_demands.clear()
            demand_io_started.clear()
            demand_io_done.clear()
            served_demands.clear()
            continue
        _require(isinstance(key, str) and bool(key), "missing key")
        if kind == "demand_queued":
            _require(not cancelled and key not in pending_demands and key not in started_demands,
                     "duplicate or cancelled demand")
            step = event.get("step")
            _require(type(step) is int and step >= 0, "invalid demand step")
            expert = EXPERT_KEY.fullmatch(key)
            ple = PLE_KEY.fullmatch(key)
            _require((expert is not None and
                      int(expert[2]) in routed.get((step, int(expert[1])), set())) or
                     (ple is not None and (step, key) in ple_lookups),
                     "demand lacks matching route or PLE lookup")
            pending_demands.add(key)
        elif kind == "demand_start":
            _require(not cancelled and key in pending_demands, "demand was not queued")
            pending_demands.remove(key)
            started_demands[key] = now
        elif kind == "demand_finish":
            _require(key in started_demands and key in served_demands,
                     "demand finished before page use")
            del started_demands[key]
            served_demands.remove(key)
            demand_io_started.discard(key)
            demand_io_done.discard(key)
        elif kind == "hint":
            _require(not cancelled, "hint after cancellation")
            _require(key not in hints and key not in buffers and
                     key not in pending_demands and key not in started_demands,
                     "duplicate or already demanded hint")
            hints.add(key)
            invalid.discard(key)
        elif kind == "hint_invalidate":
            _require(key in hints, "unknown hint")
            hints.remove(key)
            invalid.add(key)
        elif kind == "prefetch_start":
            size = event.get("bytes")
            _require(trace["arm"] == "prefetch", "baseline admitted prefetch")
            _require(not cancelled, "prefetch after cancellation")
            _require(key in hints and key not in buffers, "stale or duplicate prefetch")
            _require(not pending_demands, "prefetch overtook queued demand")
            _require(not any((waiting_key not in demand_io_done and
                              (waiting_key not in buffers or buffers[waiting_key].io_done_at is None))
                             for waiting_key in started_demands),
                     "prefetch overtook waiting demand")
            _require(type(size) is int and size > 0, "invalid prefetch size")
            _require(len(buffers) < request_cap and used_bytes + size <= byte_cap, "prefetch cap exceeded")
            buffers[key] = Buffer(size=size)
            used_bytes += size
            peak_used_bytes = max(peak_used_bytes, used_bytes)
            admitted_bytes += size
        elif kind == "demand_io_start":
            _require(key in started_demands and key not in demand_io_started and
                     key not in buffers, "invalid demand I/O start")
            demand_io_started.add(key)
        elif kind == "demand_io_done":
            _require(key in demand_io_started and key not in demand_io_done,
                     "unmatched demand I/O completion")
            demand_io_done.add(key)
            served_demands.add(key)
        elif kind == "prefetch_io_done":
            _require(key in buffers and buffers[key].io_done_at is None, "unmatched I/O completion")
            buffers[key].io_done_at = now
        elif kind == "prefetch_use":
            _require(key in buffers and buffers[key].io_done_at is not None, "use before I/O completion")
            _require(key in hints and key not in invalid, "invalidated hint used")
            _require(key in started_demands, "prefetch used without actual demand")
            _require(not buffers[key].gpu_used, "duplicate GPU use")
            buffers[key].gpu_used = True
            served_demands.add(key)
            if buffers[key].io_done_at <= started_demands[key]:
                useful_bytes += buffers[key].size
            else:
                late_bytes += buffers[key].size
        elif kind == "prefetch_gpu_done":
            _require(key in buffers and buffers[key].gpu_used and not buffers[key].gpu_done, "unmatched GPU completion")
            buffers[key].gpu_done = True
        elif kind == "buffer_release":
            _require(key in buffers, "unknown buffer")
            buffer = buffers[key]
            _require(buffer.io_done_at is not None and (not buffer.gpu_used or buffer.gpu_done),
                     "buffer released before completion")
            if not buffer.gpu_used:
                wasted_bytes += buffer.size
            used_bytes -= buffer.size
            del buffers[key]
        else:
            raise ContractError(f"unknown event {kind!r}")

    _require(routes > 0, "no actual routing event")
    _require(not pending_demands and not started_demands and not buffers,
             "request ended with pending work")
    metrics = trace.get("metrics")
    _require(isinstance(metrics, dict), "missing metrics")
    for field in METRICS:
        value = metrics.get(field)
        _require(type(value) is int and value >= 0, f"invalid {field}")
    _require(metrics["prefetch_useful_bytes_before_demand"] == useful_bytes,
             "useful bytes disagree with events")
    _require(metrics["prefetch_late_bytes"] == late_bytes, "late bytes disagree with events")
    _require(metrics["prefetch_wasted_bytes"] == wasted_bytes, "wasted bytes disagree with events")
    _require(metrics["peak_footprint_bytes"] >= peak_used_bytes,
             "peak footprint below admitted buffers")
    _require(metrics["swap_delta_bytes"] == 0, "successful trace reports swap growth")
    _require(useful_bytes + late_bytes + wasted_bytes == admitted_bytes,
             "prefetch byte accounting is incomplete")
    state = metrics.get("physical_ssd_measurement")
    physical = metrics.get("physical_ssd_read_bytes")
    _require(state in ("measured", "unavailable"), "physical I/O state missing")
    _require((type(physical) is int and physical >= 0) if state == "measured" else physical is None,
             "physical I/O value contradicts state")
    _require(metrics["request_end_ns"] >= metrics["ttft_ns"], "request ends before first token")
    _require(metrics["request_end_ns"] >= previous_time, "request ends before final event")
    _require(metrics["decode_p50_ns"] <= metrics["decode_p95_ns"] <= metrics["decode_p99_ns"] <= metrics["max_intertoken_stall_ns"],
             "decode latency percentiles inconsistent")


def compare_pair(baseline: dict, candidate: dict) -> None:
    """Check the identity fields and exact outputs expected from an I/O-only change."""
    validate(baseline)
    validate(candidate)
    _require(baseline["arm"] == "baseline" and candidate["arm"] == "prefetch", "invalid A/B arms")
    for field in ("base_commit", "model_revision", "tokenizer_revision", "runtime_revision",
                  "prompt_digest", "decode_settings_digest", "warmth", "output_token_ids", "logits_digest"):
        _require(baseline[field] == candidate[field], f"A/B mismatch: {field}")
    def routes(trace: dict) -> list[tuple[int, int, tuple[int, ...], str]]:
        return [(event["step"], event["layer"], tuple(event["selected"]),
                 event["weights_digest"])
                for event in trace["events"] if event["type"] == "route"]
    _require(routes(baseline) == routes(candidate), "A/B routing or weights differ")
