"""Wire format and public-key verification for the two Studio017 initial stages."""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from studio017_guard import doc, enc, hexid, need, parse, put, read, sha


PRINCIPAL = "pulsarmlx-studio017-supervisor"
NAMESPACE = "studio017-launch@pulsarmlx"
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINyi9FZMH73UFifrCsljGriinsAdbW37zK6Suhnf+YoU"
FINGERPRINT = "SHA256:x2ED53SSpJOI/EGQ4YB3Sv0Ty71QrXbtCvJur4WOtWQ"
FAMILY = "PulsarMLX/Studio017/full-flash-golden-token"
SIGNATURE_LIMIT = 2048
GRANT_SCHEMA = "studio017-stage-grant/2"


def slot(stage):
    need(stage in ("reference", "native"), "unknown Studio017 stage")
    return f"{FAMILY}/{stage}/initial"


def authority_binding(stage):
    return dict(protocol="studio017-supervisor-spend/2", slot=slot(stage),
                issuer=FINGERPRINT, principal=PRINCIPAL, namespace=NAMESPACE)


def fingerprint(public_key):
    algorithm, body = public_key.split()
    need(algorithm == "ssh-ed25519", "unexpected issuer algorithm")
    wire = base64.b64decode(body, validate=True)
    return "SHA256:" + base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip("=")


def _verify_ssh(message, signature, public_key):
    """OpenSSH reads two ordinary files. Never consult agent, user keyring or Git config."""
    need(isinstance(signature, bytes) and 0 < len(signature) <= SIGNATURE_LIMIT,
         "missing or oversized supervisor signature")
    with tempfile.TemporaryDirectory(prefix="studio017-verify-") as directory:
        allowed = Path(directory) / "allowed_signers"
        sigfile = Path(directory) / "signature"
        allowed.write_text(f'{PRINCIPAL} namespaces="{NAMESPACE}" {public_key}\n', encoding="ascii")
        sigfile.write_bytes(signature)
        result = subprocess.run(
            ["/usr/bin/ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", PRINCIPAL,
             "-n", NAMESPACE, "-s", str(sigfile)], input=message, capture_output=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=10)
    expected = f'Good "{NAMESPACE}" signature for {PRINCIPAL} with ED25519 key {fingerprint(public_key)}'
    need(result.returncode == 0 and result.stdout.decode("ascii").strip() == expected,
         "invalid independent supervisor signature")


def verify_supervisor(message, signature):
    need(fingerprint(PUBLIC_KEY) == FINGERPRINT, "mismatched issuer key or fingerprint")
    _verify_ssh(message, signature, PUBLIC_KEY)


def grant_identity(grant, pointer):
    stage = grant["stage"]
    need(grant["schema"] == GRANT_SCHEMA and grant["attempt"] == "initial"
         and grant["authority"] == authority_binding(stage), "unexpected grant scope")
    need(set(pointer) == {"commit", "path", "sha256"} and pointer["sha256"] == sha(enc(grant)),
         "signed grant digest mismatch")
    # The caller also checks the exact role/run-dependent private repository path.
    return dict(slot=slot(stage), grant_sha256=pointer["sha256"],
                grant_commit=hexid(pointer["commit"], 40), run=hexid(grant["run"], 64),
                source=hexid(grant["source"]["head"], 40), tree=hexid(grant["source"]["tree"], 40))


def live_challenge(grant, pointer, operation):
    return dict(schema="studio017-live-consume/1", **grant_identity(grant, pointer),
                operation=hexid(operation, 32), nonce=secrets.token_hex(32))


def spend_statement(challenge, sequence, committed_ns):
    for value in (sequence, committed_ns):
        need(type(value) is int and 0 < value < 2**63, "invalid issuer sequence or time")
    return dict(schema="studio017-consumed/2", disposition="spent-before-launch",
                slot=challenge["slot"], challenge_sha256=sha(enc(challenge)),
                sequence=sequence, committed_ns=committed_ns)


def signed_receipt(statement, signature):
    need(isinstance(signature, bytes) and 0 < len(signature) <= SIGNATURE_LIMIT,
         "invalid issuer signature size")
    return dict(statement=statement, signature=base64.b64encode(signature).decode("ascii"))


def check_receipt(challenge, receipt, verify):
    need(set(receipt) == {"statement", "signature"}, "invalid spend receipt fields")
    statement = receipt["statement"]
    expected = spend_statement(challenge, statement["sequence"], statement["committed_ns"])
    need(statement == expected, "signed spend differs from live challenge")
    signature = base64.b64decode(receipt["signature"], validate=True)
    verify(enc(expected), signature)
    return dict(operation=challenge["operation"], slot=expected["slot"],
                challenge_sha256=expected["challenge_sha256"], receipt_sha256=sha(enc(receipt)),
                sequence=expected["sequence"], committed_ns=expected["committed_ns"])


def _publish(directory, name, message):
    directory = Path(directory).resolve(strict=True)
    pending = directory / (".spend-message-" + secrets.token_hex(16))
    put(pending, message)
    try:
        os.link(pending, directory / name)
    finally:
        pending.unlink()
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def deliver_reply(directory, receipt):
    """Atomically deliver an already recorded signed reply received from the custodian."""
    _publish(directory, "supervisor-spend.json", receipt)


def _read_reply(path):
    raw = read(path,8192)
    receipt = parse(raw)
    need(raw == enc(receipt), "noncanonical signed spend receipt")
    return receipt


def _original_spend(directory, grant, pointer, claim, verify):
    challenge = doc(directory / "remote-spend-challenge.json")
    expected = dict(schema="studio017-live-consume/1", **grant_identity(grant, pointer),
                    operation=hexid(claim["operation"],32), nonce=hexid(challenge["nonce"],64))
    need(challenge == expected and claim["grant"] == pointer, "original spend identity differs")
    receipt = _read_reply(directory / "supervisor-spend.json")
    fact = check_receipt(expected, receipt, verify)
    need(fact == claim["remote_spend"] == doc(directory / "remote-spend-verified.json"),
         "original signed consumption receipt differs")


def original_spend(directory, grant, pointer, claim):
    _original_spend(directory, grant, pointer, claim, verify_supervisor)


def _await_spend(directory, challenge, verify, timeout):
    response = directory / "supervisor-spend.json"
    need(not os.path.lexists(response), "unexpected pre-existing spend response")
    _publish(directory, "remote-spend-challenge.json", challenge)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.path.lexists(response):
            fact = check_receipt(challenge, _read_reply(response), verify)
            need(time.monotonic() < end, "expired supervisor spend response")
            put(directory / "remote-spend-verified.json", fact)
            return fact
        time.sleep(min(0.25, max(0, end - time.monotonic())))
    raise TimeoutError("unconfirmed remote spend: reconcile supervisor ledger and original challenge")


def consume_before_launch(directory, grant, pointer, operation, timeout=180):
    # This process never loads an old challenge to authorize a new invocation.
    challenge = live_challenge(grant, pointer, operation)
    return _await_spend(directory, challenge, verify_supervisor, timeout)
