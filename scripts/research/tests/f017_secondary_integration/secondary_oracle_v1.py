"""Independent data-only transcript reducer; imports no candidate producer."""

COUNTERS = ("attempts", "requested_bytes", "successful_returns", "error_returns",
            "short_returns", "zero_returns", "returned_bytes")


def derive(transcript):
    rows = []
    for shard in (2, 3, 4, 5, 6):
        for purpose in ("FORMAT_PROBE", "NUMERICAL_PAYLOAD"):
            matching = [event for event in transcript if event["shard_ordinal"] == shard
                        and event["purpose"] == purpose]
            successful = [event for event in matching if event["outcome"] == "RETURN"]
            rows.append({"shard_ordinal": shard, "purpose": purpose,
                "attempts": len(matching),
                "requested_bytes": sum(event["requested_bytes"] for event in matching),
                "successful_returns": len(successful),
                "error_returns": len(matching) - len(successful),
                "short_returns": sum(len(bytes.fromhex(event["returned_hex"])) < event["requested_bytes"] for event in successful),
                "zero_returns": sum(event["returned_hex"] == "" for event in successful),
                "returned_bytes": sum(len(bytes.fromhex(event["returned_hex"])) for event in successful)})
    return rows


def require_complete(attachment, transcript):
    if attachment["completeness"] != "COMPLETE" or attachment["unknown_suffix"] is not False:
        raise AssertionError("EXPECTED_COMPLETE_BOUND_PREFIX")
    if attachment["totals"] != derive(transcript):
        raise AssertionError("INDEPENDENT_TRANSCRIPT_COUNTER_MISMATCH")


def require_incomplete(attachment):
    if (attachment["completeness"] != "INCOMPLETE" or attachment["totals"] is not None
            or attachment["unknown_suffix"] is not True):
        raise AssertionError("UNKNOWN_MUST_NOT_BECOME_COMPLETE_ZERO")


def validate_requests(transcript):
    for event in transcript:
        if event["shard_ordinal"] not in (2, 3, 4, 5, 6):
            raise AssertionError("INDEPENDENT_SHARD")
        expected_purpose = "FORMAT_PROBE" if event["offset"] >= 128 else "NUMERICAL_PAYLOAD"
        if event["purpose"] != expected_purpose or event["requested_bytes"] < 0:
            raise AssertionError("INDEPENDENT_PURPOSE_OR_SIZE")
