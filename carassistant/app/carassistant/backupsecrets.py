"""Secrets in a backup: tokens, passwords, access keys and codes travel in ONE block, encrypted with a passphrase of the person's choice.

Why a block of its own: a backup file is meant to be carried around (to another system, a cloud folder, a mail to oneself) and the file of a car may even
be shared. Without a passphrase a backup holds no secret at all. With one, the secrets lie in ``secrets.enc``: authenticated encryption (Fernet: AES-128-CBC
and HMAC-SHA256) with a key that scrypt derives from the passphrase and a fresh random salt every time. A wrong passphrase or a changed block is
recognised - it never "decrypts to rubbish". The passphrase is not stored, not logged and never part of an address.

A copy that stays on THIS system (the safety copy made before a restore) holds its secrets in ``secrets.sys`` instead: sealed with the key of this system
(vault.py), so no passphrase is needed to undo a restore here and the block is useless anywhere else.
"""

from __future__ import annotations

import base64
import json
import os
import unicodedata

NAME = "secrets.enc"  # encrypted with a passphrase: made for a file that travels
LOCAL_NAME = "secrets.sys"  # sealed with the key of this system: only for the copies that stay here
MIN_LENGTH = 8
SCRYPT_N = 2**15  # a test may lower it
BOUNDS = {"n": (2**10, 2**20), "r": (1, 16), "p": (1, 4)}  # what a file may ask for: it cannot make this system run out of memory


class WrongPassphrase(ValueError):
    """The passphrase does not open the block (or the block was changed)."""


class PassphraseTooShort(ValueError):
    """A new passphrase must have at least ``MIN_LENGTH`` characters."""


def clean(passphrase: str | None) -> str:
    """The passphrase as it is used: the same text on every keyboard (Unicode normal form), nothing trimmed - a space may be part of it."""
    return unicodedata.normalize("NFKC", passphrase or "")


def _key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    raw = Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(clean(passphrase).encode())
    return base64.urlsafe_b64encode(raw)


def seal(payload: dict, passphrase: str) -> bytes:
    """The block for a backup file."""
    from cryptography.fernet import Fernet

    if len(clean(passphrase)) < MIN_LENGTH:
        raise PassphraseTooShort(passphrase)
    salt = os.urandom(16)
    n, r, p = SCRYPT_N, 8, 1
    token = Fernet(_key(passphrase, salt, n, r, p)).encrypt(json.dumps(payload, ensure_ascii=False).encode())
    head = {
        "app": "carassistant",
        "kind": "secrets",
        "v": 1,
        "kdf": "scrypt",
        "n": n,
        "r": r,
        "p": p,
        "salt": base64.b64encode(salt).decode(),
    }
    return json.dumps({**head, "data": token.decode()}).encode()


def unseal(block: bytes, passphrase: str) -> dict:
    """What a block holds. Raises ``WrongPassphrase`` for a wrong passphrase and for a block that is not one of ours or was changed."""
    from cryptography.fernet import Fernet, InvalidToken

    try:
        head = json.loads(block)
        if head.get("app") != "carassistant" or head.get("kind") != "secrets" or head.get("v") != 1 or head.get("kdf") != "scrypt":
            raise ValueError("not a secrets block")
        n, r, p = (int(head[k]) for k in ("n", "r", "p"))
        if any(not BOUNDS[k][0] <= v <= BOUNDS[k][1] for k, v in (("n", n), ("r", r), ("p", p))) or n & (n - 1):
            raise ValueError("odd parameters")
        key = _key(passphrase, base64.b64decode(head["salt"]), n, r, p)
        payload = json.loads(Fernet(key).decrypt(head["data"].encode()))
    except (InvalidToken, ValueError, KeyError, TypeError, AttributeError):
        raise WrongPassphrase from None
    if not isinstance(payload, dict):
        raise WrongPassphrase
    return payload


def seal_local(payload: dict) -> bytes:
    """The block for a copy that stays on this system."""
    from . import vault

    return (vault.encrypt(json.dumps(payload, ensure_ascii=False)) or "").encode()


def unseal_local(block: bytes) -> dict | None:
    """What a local block holds, or None when it was sealed by another system (its key is not ours)."""
    from . import vault

    try:
        payload = json.loads(vault.decrypt(block.decode()) or "null")
    except (ValueError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
