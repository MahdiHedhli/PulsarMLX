"""One-use transaction run by the independent Studio017 custodian.

The service opens an existing database. Its operator enrolls the exact approved grant
digest for each slot separately. Only the custodian service may access the signer and
write to this database. Neither that deployment nor its restore policy is established
by these SQLite constraints. The Studio controller never imports this module.
"""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import time

import studio017_authority as auth
from studio017_guard import enc, hexid, need, parse


def ledger_schema():
    """DDL for provisioning an empty custodian store. Never run as part of consumption."""
    schema = """
        CREATE TABLE enrollments(slot TEXT PRIMARY KEY NOT NULL, grant_sha256 TEXT NOT NULL)
            WITHOUT ROWID;
        CREATE TABLE spends(sequence INTEGER PRIMARY KEY, slot TEXT UNIQUE NOT NULL
            REFERENCES enrollments(slot), challenge BLOB NOT NULL, committed_ns INTEGER NOT NULL);
        CREATE TABLE replies(slot TEXT PRIMARY KEY NOT NULL REFERENCES spends(slot),
            receipt BLOB NOT NULL) WITHOUT ROWID;
    """
    for table in ("enrollments", "spends", "replies"):
        for action in ("UPDATE", "DELETE"):
            schema += f"""CREATE TRIGGER {table}_{action} BEFORE {action} ON {table}
                          BEGIN SELECT RAISE(ABORT,'immutable ledger entry'); END;"""
        schema += f"""CREATE TRIGGER {table}_replace BEFORE INSERT ON {table}
                     WHEN EXISTS(SELECT 1 FROM {table} WHERE slot=NEW.slot)
                     BEGIN SELECT RAISE(ABORT,'duplicate ledger slot'); END;"""
    # SQLite REPLACE can also conflict on the sequence alias of rowid.
    schema += """CREATE TRIGGER spends_sequence BEFORE INSERT ON spends
                 WHEN EXISTS(SELECT 1 FROM spends WHERE sequence=NEW.sequence)
                 BEGIN SELECT RAISE(ABORT,'duplicate ledger sequence'); END;"""
    return schema


@contextmanager
def _connection(database, mode):
    uri = Path(database).resolve(strict=True).as_uri()
    with closing(sqlite3.connect(uri+"?mode="+mode, uri=True, timeout=3)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        if mode == "rw":
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            need(journal in ("delete","truncate","persist","wal"), "non-durable issuer journal")
            conn.execute("PRAGMA synchronous=EXTRA")
            conn.execute("PRAGMA fullfsync=ON")
        yield conn


def _validate(approved_grant, approved_pointer, challenge):
    identity = auth.grant_identity(approved_grant, approved_pointer)
    expected = dict(schema="studio017-live-consume/1", **identity,
                    operation=hexid(challenge["operation"], 32), nonce=hexid(challenge["nonce"], 64))
    need(challenge == expected, "challenge differs from custodian grant")
    return identity


def _original(database, challenge):
    with _connection(database, "ro") as conn:
        row = conn.execute("""SELECT sequence, challenge, committed_ns, receipt FROM spends
                              LEFT JOIN replies USING(slot) WHERE spends.slot=?""",
                           (challenge["slot"],)).fetchone()
    need(row is not None, "slot has no committed spend")
    sequence, original, committed_ns, receipt = row
    need(original == enc(challenge), "slot consumed by a different live challenge")
    return auth.spend_statement(challenge, sequence, committed_ns), receipt


def recover_reply(database, challenge):
    """Read only. Returns the stored signed reply for the exact original challenge."""
    _, receipt = _original(database, challenge)
    need(receipt is not None, "spent without a released signature; reconcile original")
    return parse(receipt)


def _consume_and_sign(database, approved_grant, approved_pointer, challenge, sign, verify):
    identity = _validate(approved_grant, approved_pointer, challenge)
    slot = identity["slot"]
    with _connection(database, "rw") as conn:
        conn.execute("BEGIN IMMEDIATE")
        enrollment = conn.execute("SELECT grant_sha256 FROM enrollments WHERE slot=?", (slot,)).fetchone()
        need(enrollment is not None, "unenrolled slot")
        need(enrollment[0] == identity["grant_sha256"], "grant differs from enrolled digest")
        previous = conn.execute("SELECT challenge FROM spends WHERE slot=?", (slot,)).fetchone()
        if previous:
            need(previous[0] == enc(challenge), "slot already spent by a different challenge")
            conn.rollback()
            retained = recover_reply(database, challenge)
            auth.check_receipt(challenge, retained, verify)
            return retained
        conn.execute("INSERT INTO spends(slot,challenge,committed_ns) VALUES (?,?,?)",
                     (slot, enc(challenge), time.time_ns()))
        conn.commit()
    # Reopen after durable commit. No signature exists along the successful path until here.
    statement, _ = _original(database, challenge)
    receipt = auth.signed_receipt(statement, sign(enc(statement)))
    auth.check_receipt(challenge, receipt, verify)
    with _connection(database, "rw") as conn:
        conn.execute("INSERT INTO replies(slot,receipt) VALUES (?,?)", (slot, enc(receipt)))
        conn.commit()
    original = recover_reply(database, challenge)
    need(original == receipt, "stored signed reply differs")
    return original


def consume_and_sign(database, approved_grant, approved_pointer, challenge, sign):
    """sign is the custodian-only signing facility. No signing facility is present on Studio."""
    return _consume_and_sign(database, approved_grant, approved_pointer, challenge, sign,
                             auth.verify_supervisor)
