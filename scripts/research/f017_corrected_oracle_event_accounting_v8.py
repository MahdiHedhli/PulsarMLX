#!/usr/bin/env python3
"""Typed V8 event-accounting constants."""

AUTHORIZATION_MINT_DELTA = 0
PACKAGE_DURABLE_START_DELTA = 1
PRIMARY_DURABLE_START_DELTA = 1
SECONDARY_DURABLE_START_DELTA = 1
HISTORICAL_REAL_PAYLOAD_LEDGER = 175


def deltas(*, package_started: bool, primary_started: bool, secondary_started: bool) -> dict:
    return {
        "authorization": AUTHORIZATION_MINT_DELTA,
        "package": int(package_started),
        "primary": int(primary_started),
        "secondary": int(secondary_started),
        "historical_before": HISTORICAL_REAL_PAYLOAD_LEDGER,
        "historical_after": HISTORICAL_REAL_PAYLOAD_LEDGER,
    }
