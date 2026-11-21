"""Secrets at rest: passwords of a plugin's settings and the access key of a source are stored encrypted in the database.

The key lies in ``secret.key`` in the data folder (readable by the app only). Someone who gets only a copy of the database (a stray file, a backup
of the database alone) cannot read them. The key is not part of a backup file: after a restore on another system the secrets are empty and are
entered again. A value without the ``enc:v1:`` mark is an old plain value and is still read (and encrypted the next time it is saved).
"""

from __future__ import annotations

import os

from . import config

PREFIX = "enc:v1:"
_fernet = None
_path = None


def _cipher():
    from cryptography.fernet import Fernet  # only needed when a secret is really stored (tools/check_plugin.py runs without it)

    global _fernet, _path
    path = config.data_dir() / "secret.key"
    if _fernet is None or _path != path:  # a test (or a restore) may point to another folder
        if path.is_file():
            key = path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as fh:
                fh.write(key)
        _fernet, _path = Fernet(key), path
    return _fernet


def encrypt(text: str | None) -> str | None:
    """The stored form of a secret. Empty stays empty; an already encrypted value is not encrypted twice."""
    if not text or text.startswith(PREFIX):
        return text
    return PREFIX + _cipher().encrypt(text.encode()).decode()


def decrypt(text: str | None) -> str:
    """The secret itself. An old plain value is returned as it is; one that cannot be read (another key) is empty."""
    if not text:
        return ""
    if not text.startswith(PREFIX):
        return text
    from cryptography.fernet import InvalidToken

    try:
        return _cipher().decrypt(text[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        return ""
