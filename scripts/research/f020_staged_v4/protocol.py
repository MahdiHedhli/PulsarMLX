"""Immutable data-only CPU/mock backend protocol; no numerical dependencies."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    buffers: tuple
    input_digests: tuple
    family: tuple
    clamp_gate: tuple = ()
    clamp_up: tuple = ()
    resources: tuple = (0, 0, 0)
