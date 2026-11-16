"""Wire format and public-key verification for the two Studio017 initial stages."""
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

from studio017_guard import doc, enc, hexid, need, put, read, sha


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
    return dict(protocol="studio017-supervisor-spend/1", slot=slot(stage),
                issuer=FINGERPRINT, principal=PRINCIPAL, namespace=NAMESPACE)


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
    need(result.returncode == 0, "invalid independent supervisor signature")


def verify_supervisor(message, signature):
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


def spend_statement(challenge):
    """Canonical bytes the external custodian signs only after committing the slot."""
    return enc(dict(schema="studio017-consumed/1", disposition="spent-before-launch",
                    slot=challenge["slot"], challenge_sha256=sha(enc(challenge))))



def original_spend(directory, grant, pointer, claim):
    """Audit the retained signed consumption without requesting another attempt."""
    challenge = doc(directory / "remote-spend-challenge.json")
    operation = hexid(claim["operation"], 32)
    expected = dict(schema="studio017-live-consume/1", **grant_identity(grant, pointer),
                    operation=operation, nonce=hexid(challenge["nonce"], 64))
    need(challenge == expected and claim["grant"] == pointer, "original spend identity differs")
    signature = read(directory / "supervisor-spend.sshsig", SIGNATURE_LIMIT)
    verify_supervisor(spend_statement(expected), signature)
    receipt = dict(operation=operation, challenge_sha256=sha(enc(expected)),
                   signature_sha256=sha(signature), slot=expected["slot"])
    need(receipt == claim["remote_spend"] == doc(directory / "remote-spend-verified.json"),
         "original signed consumption receipt differs")


def consume_before_launch(directory, grant, pointer, operation, timeout=180):
    # Only the in-memory challenge can authorize this invocation. Never restore it on restart.
    challenge = live_challenge(grant, pointer, operation)
    response = directory / "supervisor-spend.sshsig"
    need(not os.path.lexists(response), "unexpected pre-existing spend response")
    put(directory / "remote-spend-challenge.json", challenge)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if os.path.lexists(response):
            signature = read(response, SIGNATURE_LIMIT)
            verify_supervisor(spend_statement(challenge), signature)
            need(time.monotonic() < end, "expired supervisor spend response")
            receipt = dict(operation=operation, challenge_sha256=sha(enc(challenge)),
                           signature_sha256=sha(signature), slot=challenge["slot"])
            put(directory / "remote-spend-verified.json", receipt)
            return receipt
        time.sleep(min(0.25, max(0, end - time.monotonic())))
    raise TimeoutError("unconfirmed remote spend: reconcile supervisor ledger and original challenge")
