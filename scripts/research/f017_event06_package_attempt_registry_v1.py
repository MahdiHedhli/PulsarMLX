#!/usr/bin/env python3
"""Historical Event 06 registry API tombstones.

The former shared writer accepted a caller-selected qualification root before
enforcing production scope.  All writer implementations were removed from the
live closure.  These exact symbols remain only so historical imports fail
closed before any authority, filesystem, package, checkpoint, or accounting
operation.
"""
from __future__ import annotations


class ValidatedPackageAttemptReservation:
    def __new__(cls, *args, **kwargs):
        del cls, args, kwargs
        raise RuntimeError("superseded Event 06 reservation type")


class ValidatedPackageTerminalSink:
    def __new__(cls, *args, **kwargs):
        del cls, args, kwargs
        raise RuntimeError("superseded Event 06 terminal sink type")


def reserve_package_attempt(*args, **kwargs):
    del args, kwargs
    raise RuntimeError("superseded Event 06 shared package reservation writer")


def claim_terminal_sinks(*args, **kwargs):
    del args, kwargs
    raise RuntimeError("superseded Event 06 live terminal-claim writer")


def claim_qualification_terminal_sinks(*args, **kwargs):
    del args, kwargs
    raise RuntimeError("superseded Event 06 qualification terminal-claim writer")


def bank_terminal(*args, **kwargs):
    del args, kwargs
    raise RuntimeError("superseded Event 06 generic terminal writer")


__all__ = [
    "ValidatedPackageAttemptReservation",
    "ValidatedPackageTerminalSink",
    "bank_terminal",
    "claim_qualification_terminal_sinks",
    "claim_terminal_sinks",
    "reserve_package_attempt",
]
