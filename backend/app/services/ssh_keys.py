"""SSH keypair generation + host-key fingerprinting for Linux onboarding.

NetFleet generates the keypair itself rather than asking the operator to
paste one in. The private half never leaves the database (Fernet-encrypted
like every other credential); the public half is embedded in the
onboarding script that gets run on the target host. That way onboarding a
server is the same copy-paste flow as onboarding a RouterOS device, and no
human ever handles the private key.

Ed25519 rather than RSA: shorter keys, no size decision to get wrong, and
supported by every sshd shipped since OpenSSH 6.5 (2014).
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# A key comment is appended verbatim to the public key, and that line is
# written into a remote authorized_keys. A comment containing a newline
# would therefore append a *second*, attacker-chosen key — so the charset
# is restricted here rather than trusted to callers.
_SAFE_COMMENT = re.compile(r"^[A-Za-z0-9@._-]{1,128}$")


class UnsafeKeyComment(ValueError):
    pass


def _check_comment(comment: str) -> str:
    if not _SAFE_COMMENT.match(comment):
        raise UnsafeKeyComment(
            "SSH key comment must be 1-128 characters from [A-Za-z0-9@._-]"
        )
    return comment


@dataclass(slots=True)
class SshKeyPair:
    private_pem: str      # OpenSSH-format private key, unencrypted
    public_openssh: str   # "ssh-ed25519 AAAA... comment"


def generate_ed25519_keypair(comment: str = "netfleet") -> SshKeyPair:
    """Generate a fresh unencrypted Ed25519 keypair.

    The private key is left without a passphrase on purpose: it is stored
    encrypted at rest under the deployment's Fernet KEK, and a passphrase
    NetFleet would also have to store adds a second copy of the same
    secret rather than a second factor.
    """
    _check_comment(comment)
    key = ed25519.Ed25519PrivateKey.generate()

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_body = key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()

    return SshKeyPair(
        private_pem=private_pem,
        public_openssh=f"{public_body} {comment}",
    )


def public_key_from_private_pem(private_pem: str, comment: str = "netfleet") -> str:
    """Re-derive the public half from a stored private key.

    Only the private key is persisted; the onboarding script needs the
    public one, and deriving it on demand beats storing the same fact twice.
    """
    _check_comment(comment)
    key = serialization.load_ssh_private_key(private_pem.encode(), password=None)
    body = key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()
    return f"{body} {comment}"


def fingerprint_from_key_bytes(key_bytes: bytes) -> str:
    """Render an SSH key's fingerprint the way OpenSSH does:
    ``SHA256:<base64 of the sha256 digest, padding stripped>``.

    Takes the raw wire-format key blob — for host keys that is
    ``paramiko.PKey.asbytes()`` — so the value we pin matches what an
    operator sees from ``ssh-keyscan | ssh-keygen -lf -``.
    """
    digest = hashlib.sha256(key_bytes).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")
