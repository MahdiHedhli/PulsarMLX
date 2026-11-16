"""Transaction for an independently administered Studio017 issuer ledger.

The custodian supplies an existing, pre-enrolled database and the exact independently
approved grant. No network listener, signing material, database bootstrap or slot reset
is available here. Studio's stage controller never imports this module. The signed
reply may be released only after this transaction returns on the custodian's machine.
"""
from contextlib import closing
from pathlib import Path
import sqlite3

from studio017_authority import grant_identity, spend_statement
from studio017_guard import enc, hexid, need, sha


# Provision exactly one row per authorized family/stage/attempt on the custodian.
# grant_sha256 is enrolled by the custodian after grant review, never from a worker request.
TABLE = """CREATE TABLE attempts (
    slot TEXT PRIMARY KEY NOT NULL,
    grant_sha256 TEXT NOT NULL CHECK(length(grant_sha256) = 64),
    spent_challenge_sha256 TEXT CHECK(length(spent_challenge_sha256) = 64)
) WITHOUT ROWID"""


def commit_spend(database, approved_grant, approved_pointer, challenge):
    """Atomically consume a pre-enrolled slot, returning the exact unsigned reply."""
    expected = grant_identity(approved_grant, approved_pointer)
    operation = hexid(challenge["operation"], 32)
    nonce = hexid(challenge["nonce"], 64)
    need(challenge == dict(schema="studio017-live-consume/1", **expected,
                           operation=operation, nonce=nonce), "challenge differs from custodian grant")
    database = Path(database).resolve(strict=True)
    uri = database.as_uri()
    digest = sha(enc(challenge))
    params = (digest, expected["slot"], expected["grant_sha256"])
    with closing(sqlite3.connect(uri + "?mode=rw", uri=True, timeout=3)) as conn:
        # Survive process interruption. Existing grants/spends are never recreated or cleared.
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        need(mode in ("delete", "truncate", "persist", "wal"), "non-durable issuer journal")
        conn.execute("PRAGMA synchronous=EXTRA")
        conn.execute("PRAGMA fullfsync=ON")
        conn.execute("BEGIN IMMEDIATE")
        updated = conn.execute("""UPDATE attempts SET spent_challenge_sha256=?
                                  WHERE slot=? AND grant_sha256=?
                                  AND spent_challenge_sha256 IS NULL""", params)
        need(updated.rowcount == 1, "attempt unavailable, already spent, or grant differs")
        conn.commit()
    with closing(sqlite3.connect(uri + "?mode=ro", uri=True, timeout=3)) as conn:
        stored = conn.execute("SELECT grant_sha256, spent_challenge_sha256 FROM attempts WHERE slot=?",
                              (expected["slot"],)).fetchone()
        need(stored == (expected["grant_sha256"], digest), "no independent spend readback")
    return spend_statement(challenge)
