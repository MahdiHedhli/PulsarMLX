"""Independent scalar oracle for bounded GLM53-Flash synthetic fixtures.

This module intentionally uses only the Python standard library.  It does not
import the separately implemented candidate and keeps all arithmetic helpers
private so candidate and oracle do not share disputed numerical code.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import math
from typing import Any, Optional, Sequence, Tuple, Union


MAX_SEQUENCE = 16
MAX_DIMENSION = 32
MAX_EXPERTS = 8
MAX_HEADS = 4
MAX_NUMBERS = 65_536


class OracleContractError(ValueError):
    """Raised when an input, shape, limit, or intermediate is unsupported."""


Vector = Tuple[float, ...]
Matrix = Tuple[Vector, ...]


@dataclass(frozen=True)
class RouteResult:
    ids: Tuple[int, ...]
    raw_scores: Vector
    corrected_scores: Vector
    weights: Vector


@dataclass(frozen=True)
class SparseResult:
    indices: Tuple[int, ...]
    bypassed: bool
    requested: int
    returned: int


@dataclass(frozen=True)
class ConvResult:
    outputs: Matrix
    suffix: Matrix


@dataclass(frozen=True)
class KdaResult:
    outputs: Matrix
    state: Matrix
    position: int
    decays: Matrix
    betas: Vector


@dataclass(frozen=True)
class MhcResult:
    collapsed: Vector
    pre: Vector
    post: Vector
    comb: Matrix
    mixes: Vector


@dataclass(frozen=True)
class MlpWeights:
    gate: Matrix
    up: Matrix
    down: Matrix


@dataclass(frozen=True)
class MlpTrace:
    gate: Vector
    up: Vector
    activated: Vector
    output: Vector


@dataclass(frozen=True)
class CompositionResult:
    output: Vector
    route: RouteResult
    selected_traces: Tuple[Tuple[int, MlpTrace], ...]
    shared_trace: MlpTrace
    routed: Vector
    shared: Vector
    branch: Vector


def _count_numbers(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return 1
    if is_dataclass(value):
        return sum(_count_numbers(getattr(value, f.name)) for f in fields(value))
    if isinstance(value, (list, tuple)):
        return sum(_count_numbers(item) for item in value)
    return 0


def _budget(*values: Any) -> None:
    if sum(_count_numbers(value) for value in values) > MAX_NUMBERS:
        raise OracleContractError("numeric element ceiling exceeded")


def _finite(value: Union[int, float], label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OracleContractError(f"{label} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise OracleContractError(f"{label} must be finite")
    return result


def _positive_int(value: int, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OracleContractError(f"{label} must be an integer")
    if value < 1 or value > maximum:
        raise OracleContractError(f"{label} must be in [1,{maximum}]")
    return value


def _vector(values: Sequence[float], label: str, *, maximum: int = MAX_DIMENSION) -> Vector:
    if not isinstance(values, (list, tuple)):
        raise OracleContractError(f"{label} must be a list or tuple")
    if len(values) < 1 or len(values) > maximum:
        raise OracleContractError(f"{label} length must be in [1,{maximum}]")
    return tuple(_finite(value, f"{label}[{i}]") for i, value in enumerate(values))


def _matrix(
    values: Sequence[Sequence[float]],
    label: str,
    *,
    max_rows: int = MAX_DIMENSION,
    max_cols: int = MAX_DIMENSION,
) -> Matrix:
    if not isinstance(values, (list, tuple)):
        raise OracleContractError(f"{label} must be a list or tuple")
    if len(values) < 1 or len(values) > max_rows:
        raise OracleContractError(f"{label} row count must be in [1,{max_rows}]")
    rows = tuple(_vector(row, f"{label}[{i}]", maximum=max_cols) for i, row in enumerate(values))
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise OracleContractError(f"{label} must be rectangular")
    return rows


def _checked_add(left: float, right: float, label: str) -> float:
    return _finite(left + right, label)


def _checked_sub(left: float, right: float, label: str) -> float:
    return _finite(left - right, label)


def _checked_mul(left: float, right: float, label: str) -> float:
    return _finite(left * right, label)


def _checked_div(numerator: float, denominator: float, label: str) -> float:
    denominator = _finite(denominator, f"{label} denominator")
    if denominator == 0.0:
        raise OracleContractError(f"{label} denominator must be nonzero")
    return _finite(numerator / denominator, label)


def _checked_exp(value: float, label: str) -> float:
    value = _finite(value, f"{label} input")
    try:
        result = math.exp(value)
    except OverflowError as exc:
        raise OracleContractError(f"{label} overflowed") from exc
    return _finite(result, label)


def _checked_sqrt(value: float, label: str) -> float:
    value = _finite(value, f"{label} input")
    if value < 0.0:
        raise OracleContractError(f"{label} input must be nonnegative")
    return _finite(math.sqrt(value), label)


def _sigmoid(value: float, label: str) -> float:
    value = _finite(value, f"{label} input")
    if value >= 0.0:
        z = _checked_exp(-value, f"{label} exp")
        return _checked_div(1.0, _checked_add(1.0, z, f"{label} denominator"), label)
    z = _checked_exp(value, f"{label} exp")
    return _checked_div(z, _checked_add(1.0, z, f"{label} denominator"), label)


def _silu(value: float, label: str) -> float:
    return _checked_mul(value, _sigmoid(value, f"{label} sigmoid"), label)


def _dot(left: Sequence[float], right: Sequence[float], label: str) -> float:
    if len(left) != len(right):
        raise OracleContractError(f"{label} operands have different widths")
    total = 0.0
    for i, (a, b) in enumerate(zip(left, right)):
        product = _checked_mul(a, b, f"{label} product {i}")
        total = _checked_add(total, product, f"{label} sum {i}")
    return total


def _softmax(values: Sequence[float], label: str) -> Vector:
    if not values:
        raise OracleContractError(f"{label} must not be empty")
    maximum = max(_finite(value, f"{label} value") for value in values)
    exps = tuple(
        _checked_exp(_checked_sub(value, maximum, f"{label} shift"), f"{label} exp")
        for value in values
    )
    denominator = 0.0
    for i, value in enumerate(exps):
        denominator = _checked_add(denominator, value, f"{label} sum {i}")
    return tuple(_checked_div(value, denominator, f"{label} probability") for value in exps)


def route_scores(
    scores: Sequence[float],
    correction_bias: Sequence[float],
    top_k: int,
    scaling_factor: float,
    *,
    normalize: bool = True,
) -> RouteResult:
    """Select experts using corrected scores and weight original scores."""

    _budget(scores, correction_bias, top_k, scaling_factor)
    raw = _vector(scores, "scores", maximum=MAX_EXPERTS)
    bias = _vector(correction_bias, "correction_bias", maximum=MAX_EXPERTS)
    if len(raw) != len(bias):
        raise OracleContractError("scores and correction_bias must have equal length")
    top_k = _positive_int(top_k, "top_k", len(raw))
    scale = _finite(scaling_factor, "scaling_factor")
    if scale <= 0.0:
        raise OracleContractError("scaling_factor must be positive")
    for i, score in enumerate(raw):
        if score < 0.0 or score > 1.0:
            raise OracleContractError(f"scores[{i}] must be in [0,1]")
    corrected = tuple(
        _checked_add(score, bias[i], f"corrected_scores[{i}]")
        for i, score in enumerate(raw)
    )
    ids = tuple(sorted(range(len(raw)), key=lambda i: (-corrected[i], i))[:top_k])
    selected = tuple(raw[i] for i in ids)
    if normalize:
        denominator = 0.0
        for i, value in enumerate(selected):
            denominator = _checked_add(denominator, value, f"weight denominator {i}")
        if denominator <= 0.0:
            raise OracleContractError("selected score denominator must be positive")
        weights = tuple(
            _checked_mul(
                scale,
                _checked_div(value, denominator, f"weight[{j}] normalized"),
                f"weight[{j}] scaled",
            )
            for j, value in enumerate(selected)
        )
    else:
        weights = tuple(
            _checked_mul(scale, value, f"weight[{j}]") for j, value in enumerate(selected)
        )
    return RouteResult(ids, raw, corrected, weights)


def route_tokens(
    logits: Sequence[float],
    correction_bias: Sequence[float],
    top_k: int,
    scaling_factor: float,
    *,
    normalize: bool = True,
) -> RouteResult:
    """Apply sigmoid to router logits, then perform corrected top-k selection."""

    raw_logits = _vector(logits, "logits", maximum=MAX_EXPERTS)
    scores = tuple(_sigmoid(value, f"logits[{i}] sigmoid") for i, value in enumerate(raw_logits))
    return route_scores(scores, correction_bias, top_k, scaling_factor, normalize=normalize)


def sparse_select(
    keys: Sequence[Sequence[float]],
    gates: Sequence[Sequence[float]],
    ape: Sequence[Sequence[float]],
    queries: Sequence[Sequence[float]],
    head_weights: Sequence[float],
    valid: Sequence[bool],
    query_position: int,
    top_k: int,
    pool_size: int,
    *,
    always_tail: bool = True,
    current_query_valid: bool = True,
    bypass_short: bool = True,
) -> SparseResult:
    """Compress complete pools and select causally visible source indices."""

    _budget(keys, gates, ape, queries, head_weights, query_position, top_k, pool_size)
    key_rows = _matrix(keys, "keys", max_rows=MAX_SEQUENCE)
    gate_rows = _matrix(gates, "gates", max_rows=MAX_SEQUENCE)
    if len(key_rows) != len(gate_rows) or len(key_rows[0]) != len(gate_rows[0]):
        raise OracleContractError("keys and gates must have equal shape")
    token_count, width = len(key_rows), len(key_rows[0])
    # index_topk is a configured selection budget, so it may exceed the
    # current cached length.  That is exactly the source's short-context
    # bypass condition (T <= index_topk).
    top_k = _positive_int(top_k, "top_k", MAX_SEQUENCE)
    pool_size = _positive_int(pool_size, "pool_size", MAX_SEQUENCE)
    if top_k % pool_size != 0:
        raise OracleContractError("top_k must be divisible by pool_size")
    ape_rows = _matrix(ape, "ape", max_rows=pool_size, max_cols=width)
    if len(ape_rows) != pool_size or len(ape_rows[0]) != width:
        raise OracleContractError("ape shape must be [pool_size,width]")
    query_rows = _matrix(queries, "queries", max_rows=MAX_HEADS, max_cols=width)
    if len(query_rows[0]) != width:
        raise OracleContractError("query width must match key width")
    weights = _vector(head_weights, "head_weights", maximum=MAX_HEADS)
    if len(weights) != len(query_rows):
        raise OracleContractError("head_weights length must equal query head count")
    if not isinstance(valid, (list, tuple)) or len(valid) != token_count:
        raise OracleContractError("valid must have one Boolean per token")
    if any(not isinstance(item, bool) for item in valid):
        raise OracleContractError("valid entries must be Boolean")
    if isinstance(query_position, bool) or not isinstance(query_position, int):
        raise OracleContractError("query_position must be an integer")
    if query_position < 0 or query_position >= token_count:
        raise OracleContractError("query_position must address the supplied cache")
    if not isinstance(always_tail, bool) or not isinstance(current_query_valid, bool):
        raise OracleContractError("selection flags must be Boolean")
    if not isinstance(bypass_short, bool):
        raise OracleContractError("bypass_short must be Boolean")
    if bypass_short and token_count <= top_k:
        return SparseResult((), True, top_k, 0)
    if not any(valid):
        raise OracleContractError("at least one token must be valid")

    first = next(i for i, item in enumerate(valid) if item)
    if any(not valid[i] for i in range(first, token_count)):
        raise OracleContractError("interior validity holes unsupported")
    pool_count = (token_count + pool_size - 1) // pool_size
    pools = []
    width_scale = _checked_sqrt(float(width), "sparse width scale")
    head_scale = _checked_sqrt(float(len(query_rows)), "sparse head scale")
    for pool_id in range(pool_count):
        positions = tuple(first + pool_id * pool_size + j for j in range(pool_size))
        complete = all(pos < token_count and valid[pos] for pos in positions)
        if not complete or positions[-1] > query_position:
            continue
        pooled = []
        for d in range(width):
            logits = tuple(
                _checked_add(gate_rows[pos][d], ape_rows[j][d], f"pool {pool_id} logit")
                for j, pos in enumerate(positions)
            )
            probs = _softmax(logits, f"pool {pool_id} feature {d} softmax")
            value = 0.0
            for j, pos in enumerate(positions):
                product = _checked_mul(probs[j], key_rows[pos][d], f"pool {pool_id} feature {d}")
                value = _checked_add(value, product, f"pool {pool_id} feature {d} sum")
            pooled.append(value)
        pool_score = 0.0
        for h, query in enumerate(query_rows):
            score = _checked_div(_dot(query, pooled, f"pool {pool_id} head {h}"), width_scale, "head score")
            rectified = max(score, 0.0)
            contribution = _checked_mul(
                _checked_div(weights[h], head_scale, f"head weight {h}"),
                rectified,
                f"pool {pool_id} head {h} contribution",
            )
            pool_score = _checked_add(pool_score, contribution, f"pool {pool_id} score")
        # The source masks invalid pools with -1e30 before ordering.  An
        # otherwise eligible score at or below that sentinel would collide
        # with the mask ordering contract, so this bounded oracle rejects it.
        if pool_score <= -1e30:
            raise OracleContractError("eligible pool score collides with invalid sentinel")
        pools.append((pool_id, pool_score, positions))

    selected_count = top_k // pool_size
    selected = sorted(pools, key=lambda item: (-item[1], item[0]))[:selected_count]
    pool_slots = [pos for _, _, positions in selected for pos in positions]
    pool_slots.extend([-1] * (top_k - len(pool_slots)))
    tail_slots = []
    if always_tail and pool_size > 1:
        visible_count = sum(1 for i, item in enumerate(valid) if item and i <= query_position)
        tail_count = visible_count % pool_size
        tail_start = first + visible_count - tail_count
        for offset in range(pool_size - 1):
            pos = tail_start + offset
            tail_slots.append(
                pos if offset < tail_count and pos < token_count and valid[pos] and pos <= query_position else -1
            )
    indices = tuple(pool_slots + tail_slots)
    # In the source, valid_cur masks the current query after selection.  The
    # explicit flag supports a separately supplied query mask; valid at the
    # addressed cached position covers the one-sequence fixture convention.
    if not current_query_valid or not valid[query_position]:
        indices = tuple(-1 for _ in indices)
    return SparseResult(indices, False, top_k, sum(1 for index in indices if index >= 0))


def causal_conv_silu(
    inputs: Sequence[Sequence[float]],
    kernels: Sequence[Sequence[float]],
    suffix: Optional[Sequence[Sequence[float]]] = None,
) -> ConvResult:
    """Apply a valid depthwise convolution over a raw causal suffix and SiLU."""

    _budget(inputs, kernels, suffix)
    input_rows = _matrix(inputs, "inputs", max_rows=MAX_SEQUENCE)
    channel_count = len(input_rows[0])
    kernel_rows = _matrix(kernels, "kernels", max_rows=channel_count, max_cols=MAX_SEQUENCE)
    if len(kernel_rows) != channel_count:
        raise OracleContractError("kernels must have one row per input channel")
    width = len(kernel_rows[0])
    if suffix is None:
        suffix_rows = tuple(tuple(0.0 for _ in range(channel_count)) for _ in range(width - 1))
    elif width == 1 and isinstance(suffix, (list, tuple)) and len(suffix) == 0:
        suffix_rows = ()
    else:
        suffix_rows = _matrix(suffix, "suffix", max_rows=MAX_SEQUENCE)
        if len(suffix_rows) != width - 1 or len(suffix_rows[0]) != channel_count:
            raise OracleContractError("suffix shape must be [kernel_width-1,channels]")
    window = suffix_rows + input_rows
    outputs = []
    for t in range(len(input_rows)):
        row = []
        for channel in range(channel_count):
            total = 0.0
            for tap in range(width):
                product = _checked_mul(
                    window[t + tap][channel], kernel_rows[channel][tap], f"conv[{t},{channel}] tap {tap}"
                )
                total = _checked_add(total, product, f"conv[{t},{channel}] sum {tap}")
            row.append(_silu(total, f"conv[{t},{channel}] silu"))
        outputs.append(tuple(row))
    new_suffix = window[-(width - 1) :] if width > 1 else ()
    return ConvResult(tuple(outputs), tuple(new_suffix))


def _normalize(row: Vector, eps: float, label: str, *, query: bool) -> Vector:
    norm_sq = 0.0
    for i, value in enumerate(row):
        square = _checked_mul(value, value, f"{label} square {i}")
        norm_sq = _checked_add(norm_sq, square, f"{label} square sum {i}")
    denominator = _checked_sqrt(_checked_add(norm_sq, eps, f"{label} eps"), f"{label} norm")
    if query:
        denominator = _checked_mul(denominator, _checked_sqrt(float(len(row)), f"{label} width"), f"{label} scaled norm")
    return tuple(_checked_div(value, denominator, f"{label}[{i}]") for i, value in enumerate(row))


def kda_sequence(
    q: Sequence[Sequence[float]],
    k: Sequence[Sequence[float]],
    v: Sequence[Sequence[float]],
    a: Sequence[Sequence[float]],
    b: Sequence[float],
    A_log: Union[float, Sequence[float]],
    dt_bias: Sequence[float],
    *,
    lower_bound: float = -5.0,
    state: Optional[Sequence[Sequence[float]]] = None,
    position: int = 0,
    l2_eps: float = 1e-6,
) -> KdaResult:
    """Evaluate one-head KDA with public state axes [Dk,Dv]."""

    _budget(q, k, v, a, b, A_log, dt_bias, state)
    q_rows = _matrix(q, "q", max_rows=MAX_SEQUENCE)
    k_rows = _matrix(k, "k", max_rows=MAX_SEQUENCE)
    v_rows = _matrix(v, "v", max_rows=MAX_SEQUENCE)
    a_rows = _matrix(a, "a", max_rows=MAX_SEQUENCE)
    time_count, key_dim, value_dim = len(q_rows), len(q_rows[0]), len(v_rows[0])
    if len(k_rows) != time_count or len(a_rows) != time_count or len(v_rows) != time_count:
        raise OracleContractError("q, k, v, and a must have equal time axes")
    if len(k_rows[0]) != key_dim or len(a_rows[0]) != key_dim:
        raise OracleContractError("q, k, and a must have equal key widths")
    b_values = _vector(b, "b", maximum=MAX_SEQUENCE)
    if len(b_values) != time_count:
        raise OracleContractError("b must have one value per time step")
    dt_values = _vector(dt_bias, "dt_bias", maximum=key_dim)
    if len(dt_values) != key_dim:
        raise OracleContractError("dt_bias width must equal Dk")
    if isinstance(A_log, (int, float)) and not isinstance(A_log, bool):
        a_log_values = tuple(_finite(A_log, "A_log") for _ in range(key_dim))
    else:
        a_log_values = _vector(A_log, "A_log", maximum=key_dim)  # type: ignore[arg-type]
        if len(a_log_values) != key_dim:
            raise OracleContractError("A_log must be scalar or width Dk")
    lower = _finite(lower_bound, "lower_bound")
    if lower >= 0.0:
        raise OracleContractError("lower_bound must be negative")
    eps = _finite(l2_eps, "l2_eps")
    if eps <= 0.0:
        raise OracleContractError("l2_eps must be positive")
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise OracleContractError("position must be a nonnegative integer")
    if position + time_count > MAX_SEQUENCE:
        raise OracleContractError("state position exceeds tiny sequence ceiling")
    if state is None:
        current = [[0.0 for _ in range(value_dim)] for _ in range(key_dim)]
    else:
        state_rows = _matrix(state, "state", max_rows=key_dim, max_cols=value_dim)
        if len(state_rows) != key_dim or len(state_rows[0]) != value_dim:
            raise OracleContractError("state shape must be [Dk,Dv]")
        current = [list(row) for row in state_rows]

    q_normalized = tuple(_normalize(row, eps, f"q[{t}]", query=True) for t, row in enumerate(q_rows))
    k_normalized = tuple(_normalize(row, eps, f"k[{t}]", query=False) for t, row in enumerate(k_rows))
    outputs = []
    all_decays = []
    betas = []
    for t in range(time_count):
        beta = _sigmoid(b_values[t], f"beta[{t}]")
        betas.append(beta)
        decays = []
        for d in range(key_dim):
            rate = _checked_exp(a_log_values[d], f"exp_A_log[{d}]")
            gate_input = _checked_add(a_rows[t][d], dt_values[d], f"gate_input[{t},{d}]")
            scaled_gate = _checked_mul(rate, gate_input, f"scaled_gate[{t},{d}]")
            log_decay = _checked_mul(lower, _sigmoid(scaled_gate, f"safe_gate[{t},{d}]"), f"log_decay[{t},{d}]")
            decays.append(_checked_exp(log_decay, f"decay[{t},{d}]"))
        all_decays.append(tuple(decays))
        for d in range(key_dim):
            for value_index in range(value_dim):
                current[d][value_index] = _checked_mul(
                    current[d][value_index], decays[d], f"decayed_state[{t},{d},{value_index}]"
                )
        memory = []
        for value_index in range(value_dim):
            total = 0.0
            for d in range(key_dim):
                product = _checked_mul(current[d][value_index], k_normalized[t][d], f"memory[{t},{value_index},{d}]")
                total = _checked_add(total, product, f"memory[{t},{value_index}] sum")
            memory.append(total)
        deltas = tuple(
            _checked_mul(_checked_sub(v_rows[t][j], memory[j], f"delta[{t},{j}] residual"), beta, f"delta[{t},{j}]")
            for j in range(value_dim)
        )
        for d in range(key_dim):
            for value_index in range(value_dim):
                update = _checked_mul(k_normalized[t][d], deltas[value_index], f"state_update[{t},{d},{value_index}]")
                current[d][value_index] = _checked_add(
                    current[d][value_index], update, f"new_state[{t},{d},{value_index}]"
                )
        output = []
        for value_index in range(value_dim):
            total = 0.0
            for d in range(key_dim):
                product = _checked_mul(current[d][value_index], q_normalized[t][d], f"output[{t},{value_index},{d}]")
                total = _checked_add(total, product, f"output[{t},{value_index}] sum")
            output.append(total)
        outputs.append(tuple(output))
    return KdaResult(tuple(outputs), tuple(tuple(row) for row in current), position + time_count, tuple(all_decays), tuple(betas))


def mhc_collapse(
    streams: Sequence[Sequence[float]],
    fn: Sequence[Sequence[float]],
    scale: Sequence[float],
    base: Sequence[float],
    *,
    sinkhorn_iters: int = 20,
    norm_eps: float = 1e-5,
    hc_eps: float = 1e-6,
) -> MhcResult:
    """Apply RMS transform, pre/post weights, Sinkhorn, and stream collapse."""

    _budget(streams, fn, scale, base, sinkhorn_iters)
    stream_rows = _matrix(streams, "streams", max_rows=MAX_HEADS)
    stream_count, width = len(stream_rows), len(stream_rows[0])
    mix_count = (2 + stream_count) * stream_count
    fn_rows = _matrix(fn, "fn", max_rows=mix_count, max_cols=stream_count * width)
    if len(fn_rows) != mix_count or len(fn_rows[0]) != stream_count * width:
        raise OracleContractError("fn shape must be [(2+R)R,RD]")
    scales = _vector(scale, "scale", maximum=3)
    if len(scales) != 3:
        raise OracleContractError("scale must have three values")
    bases = _vector(base, "base", maximum=mix_count)
    if len(bases) != mix_count:
        raise OracleContractError("base length must be (2+R)R")
    sinkhorn_iters = _positive_int(sinkhorn_iters, "sinkhorn_iters", 64)
    norm_eps = _finite(norm_eps, "norm_eps")
    hc_eps = _finite(hc_eps, "hc_eps")
    if norm_eps <= 0.0 or hc_eps <= 0.0:
        raise OracleContractError("mHC epsilons must be positive")
    flat = tuple(value for row in stream_rows for value in row)
    square_sum = 0.0
    for i, value in enumerate(flat):
        square_sum = _checked_add(square_sum, _checked_mul(value, value, f"rms square {i}"), f"rms sum {i}")
    mean_square = _checked_div(square_sum, float(len(flat)), "rms mean")
    denominator = _checked_sqrt(_checked_add(mean_square, norm_eps, "rms epsilon"), "rms denominator")
    normalized = tuple(_checked_div(value, denominator, f"normalized[{i}]") for i, value in enumerate(flat))
    mixes = tuple(_dot(normalized, row, f"mixes[{i}]") for i, row in enumerate(fn_rows))
    pre = tuple(
        _checked_add(
            _sigmoid(_checked_add(_checked_mul(mixes[r], scales[0], f"pre[{r}] scale"), bases[r], f"pre[{r}] bias"), f"pre[{r}] sigmoid"),
            hc_eps,
            f"pre[{r}] epsilon",
        )
        for r in range(stream_count)
    )
    post = tuple(
        _checked_mul(
            2.0,
            _sigmoid(
                _checked_add(
                    _checked_mul(mixes[stream_count + r], scales[1], f"post[{r}] scale"),
                    bases[stream_count + r],
                    f"post[{r}] bias",
                ),
                f"post[{r}] sigmoid",
            ),
            f"post[{r}]",
        )
        for r in range(stream_count)
    )
    logits = []
    comb_offset = 2 * stream_count
    for row in range(stream_count):
        logits.append(
            tuple(
                _checked_add(
                    _checked_mul(mixes[comb_offset + row * stream_count + col], scales[2], f"comb[{row},{col}] scale"),
                    bases[comb_offset + row * stream_count + col],
                    f"comb[{row},{col}] bias",
                )
                for col in range(stream_count)
            )
        )
    comb = [
        [_checked_add(value, hc_eps, f"comb[{row}] softmax epsilon") for value in _softmax(logits[row], f"comb row {row}")]
        for row in range(stream_count)
    ]

    def normalize_columns(values: list[list[float]], phase: str) -> None:
        for col in range(stream_count):
            denominator_value = hc_eps
            for row in range(stream_count):
                denominator_value = _checked_add(denominator_value, values[row][col], f"{phase} col {col} sum")
            for row in range(stream_count):
                values[row][col] = _checked_div(values[row][col], denominator_value, f"{phase} col {col} row {row}")

    def normalize_rows(values: list[list[float]], phase: str) -> None:
        for row in range(stream_count):
            denominator_value = hc_eps
            for col in range(stream_count):
                denominator_value = _checked_add(denominator_value, values[row][col], f"{phase} row {row} sum")
            for col in range(stream_count):
                values[row][col] = _checked_div(values[row][col], denominator_value, f"{phase} row {row} col {col}")

    normalize_columns(comb, "sinkhorn initial")
    for iteration in range(1, sinkhorn_iters):
        normalize_rows(comb, f"sinkhorn {iteration}")
        normalize_columns(comb, f"sinkhorn {iteration}")
    collapsed = []
    for d in range(width):
        total = 0.0
        for r in range(stream_count):
            total = _checked_add(total, _checked_mul(pre[r], stream_rows[r][d], f"collapse[{d},{r}]"), f"collapse[{d}] sum")
        collapsed.append(total)
    return MhcResult(tuple(collapsed), pre, post, tuple(tuple(row) for row in comb), mixes)


def mhc_expand(
    branch: Sequence[float],
    streams: Sequence[Sequence[float]],
    post: Sequence[float],
    comb: Sequence[Sequence[float]],
) -> Matrix:
    """Expand a branch into destination streams and mix original residuals."""

    _budget(branch, streams, post, comb)
    stream_rows = _matrix(streams, "streams", max_rows=MAX_HEADS)
    stream_count, width = len(stream_rows), len(stream_rows[0])
    branch_values = _vector(branch, "branch", maximum=width)
    if len(branch_values) != width:
        raise OracleContractError("branch width must equal stream width")
    post_values = _vector(post, "post", maximum=stream_count)
    if len(post_values) != stream_count:
        raise OracleContractError("post length must equal stream count")
    comb_rows = _matrix(comb, "comb", max_rows=stream_count, max_cols=stream_count)
    if len(comb_rows) != stream_count or len(comb_rows[0]) != stream_count:
        raise OracleContractError("comb shape must be [R,R]")
    expanded = []
    for destination in range(stream_count):
        row = []
        for d in range(width):
            total = _checked_mul(post_values[destination], branch_values[d], f"expand[{destination},{d}] branch")
            for source in range(stream_count):
                contribution = _checked_mul(comb_rows[source][destination], stream_rows[source][d], f"expand[{destination},{d}] source {source}")
                total = _checked_add(total, contribution, f"expand[{destination},{d}] sum {source}")
            row.append(total)
        expanded.append(tuple(row))
    return tuple(expanded)


def clamped_swiglu(
    gate: Sequence[float], up: Sequence[float], limit: float = 10.0
) -> Vector:
    """Apply upper-only gate clamp, symmetric up clamp, and SiLU product."""

    _budget(gate, up, limit)
    gate_values = _vector(gate, "gate")
    up_values = _vector(up, "up")
    if len(gate_values) != len(up_values):
        raise OracleContractError("gate and up must have equal length")
    limit = _finite(limit, "limit")
    if limit <= 0.0:
        raise OracleContractError("limit must be positive")
    result = []
    for i, (gate_value, up_value) in enumerate(zip(gate_values, up_values)):
        gate_clamped = min(gate_value, limit)
        up_clamped = min(max(up_value, -limit), limit)
        result.append(
            _checked_mul(_silu(gate_clamped, f"gate[{i}] silu"), up_clamped, f"swiglu[{i}]")
        )
    return tuple(result)


def clamped_mlp(
    x: Sequence[float],
    gate_weight: Sequence[Sequence[float]],
    up_weight: Sequence[Sequence[float]],
    down_weight: Sequence[Sequence[float]],
    limit: float = 10.0,
) -> MlpTrace:
    """Evaluate separately visible gate, up, activation, and down boundaries."""

    _budget(x, gate_weight, up_weight, down_weight, limit)
    x_values = _vector(x, "x")
    gate_rows = _matrix(gate_weight, "gate_weight")
    up_rows = _matrix(up_weight, "up_weight")
    if len(gate_rows) != len(up_rows) or len(gate_rows[0]) != len(x_values) or len(up_rows[0]) != len(x_values):
        raise OracleContractError("gate/up weights must share shape [I,D]")
    intermediate = len(gate_rows)
    down_rows = _matrix(down_weight, "down_weight", max_cols=intermediate)
    if len(down_rows) != len(x_values) or len(down_rows[0]) != intermediate:
        raise OracleContractError("down_weight shape must be [D,I]")
    gate = tuple(_dot(row, x_values, f"gate projection {i}") for i, row in enumerate(gate_rows))
    up = tuple(_dot(row, x_values, f"up projection {i}") for i, row in enumerate(up_rows))
    activated = clamped_swiglu(gate, up, limit)
    output = tuple(_dot(row, activated, f"down projection {i}") for i, row in enumerate(down_rows))
    return MlpTrace(gate, up, activated, output)


def _coerce_weights(value: MlpWeights, label: str) -> MlpWeights:
    if not isinstance(value, MlpWeights):
        raise OracleContractError(f"{label} must be MlpWeights")
    return value


def compose_moe_residual(
    x: Sequence[float],
    residual: Sequence[float],
    logits: Sequence[float],
    correction_bias: Sequence[float],
    experts: Sequence[MlpWeights],
    shared_expert: MlpWeights,
    top_k: int,
    scaling_factor: float,
    *,
    limit: float = 10.0,
) -> CompositionResult:
    """Compose routing, routed/shared clamped MLPs, and a vector residual."""

    _budget(x, residual, logits, correction_bias, experts, shared_expert)
    x_values = _vector(x, "x")
    residual_values = _vector(residual, "residual", maximum=len(x_values))
    if len(residual_values) != len(x_values):
        raise OracleContractError("residual width must equal x width")
    if not isinstance(experts, (list, tuple)) or len(experts) < 1 or len(experts) > MAX_EXPERTS:
        raise OracleContractError("experts must contain between one and eight MlpWeights")
    expert_values = tuple(_coerce_weights(expert, f"experts[{i}]") for i, expert in enumerate(experts))
    shared = _coerce_weights(shared_expert, "shared_expert")
    if len(logits) != len(expert_values) or len(correction_bias) != len(expert_values):
        raise OracleContractError("router axes must equal expert count")
    route = route_tokens(logits, correction_bias, top_k, scaling_factor)
    selected_traces = tuple(
        (
            expert_id,
            clamped_mlp(
                x_values,
                expert_values[expert_id].gate,
                expert_values[expert_id].up,
                expert_values[expert_id].down,
                limit,
            ),
        )
        for expert_id in route.ids
    )
    routed_values = []
    for d in range(len(x_values)):
        total = 0.0
        for j, (_, trace) in enumerate(selected_traces):
            contribution = _checked_mul(route.weights[j], trace.output[d], f"routed[{d}] expert {j}")
            total = _checked_add(total, contribution, f"routed[{d}] sum {j}")
        routed_values.append(total)
    shared_trace = clamped_mlp(x_values, shared.gate, shared.up, shared.down, limit)
    shared_values = shared_trace.output
    branch = tuple(
        _checked_add(routed_values[d], shared_values[d], f"branch[{d}]") for d in range(len(x_values))
    )
    output = tuple(
        _checked_add(residual_values[d], branch[d], f"output[{d}]") for d in range(len(x_values))
    )
    return CompositionResult(
        output,
        route,
        selected_traces,
        shared_trace,
        tuple(routed_values),
        shared_values,
        branch,
    )


__all__ = [
    "OracleContractError",
    "RouteResult",
    "SparseResult",
    "ConvResult",
    "KdaResult",
    "MhcResult",
    "MlpWeights",
    "MlpTrace",
    "CompositionResult",
    "route_tokens",
    "route_scores",
    "sparse_select",
    "causal_conv_silu",
    "kda_sequence",
    "mhc_collapse",
    "mhc_expand",
    "clamped_swiglu",
    "clamped_mlp",
    "compose_moe_residual",
]
