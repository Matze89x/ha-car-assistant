"""Tiny signal used to wake the background worker after data changes."""

from __future__ import annotations

import threading

dirty = threading.Event()
stop = threading.Event()


def changed() -> None:
    dirty.set()
