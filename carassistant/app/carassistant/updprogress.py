"""How far the update of a package has come - what the bar of the update window shows (docs/sources.md, "The update window").

The update runs in the request that the button *Update now* started (addons_web.addons_update); the window asks every moment how far it is, and what it hears
is what the update says about ITSELF: the stage it is in and, while the files of the package arrive, how many of their bytes have come. A bar that only moves
on a timer is not built: it would say things that are not so. The share of every stage is fixed here (what takes long is the arrival of the files); the
percentage never goes back, and it reaches 100 only when the update is done.

Every update is one ``Run``: what it says goes to ITS bar only, and a newer update of the same install takes the place of an older one (the older one goes on
with its work but is not heard any more). A window marks its update with a ``token`` and asks for that one only - never for the finished one of a minute ago.

Nothing in here decides anything, reads a file of a source or touches the database: it keeps a few numbers per installed package for a short time."""

from __future__ import annotations

import contextlib
import contextvars
import itertools
import re
import threading
import time

WEIGHTS = {"read": 10, "download": 55, "check": 15, "save": 10, "restart": 10}  # the share of every stage in the whole bar
KEEP_SECONDS = 120  # a finished update is remembered this long (the page asks once more after it is done)
STALE_SECONDS = 900  # an update that has said nothing for this long is forgotten
MAX_RUNS = 50
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,40}")

_lock = threading.Lock()
_runs: dict[int, dict] = {}
_serial = itertools.count(1)
_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("update_progress_run", default=None)


def _now() -> float:
    return time.monotonic()


def token_of(raw: str | None) -> str:
    """The mark a window puts on its update (a random word it made up): what is not such a word is no mark."""
    return raw if raw and TOKEN.fullmatch(raw) else ""


def plan_for(needs_package: bool, service: bool) -> tuple[str, ...]:
    """The stages of an update of a package: a plain description is read and saved; a package with files or a service is also loaded and checked, and a
    service starts again. The two answers come from its manifest (``addons.needs_package``, ``pluginsvc.service_of``)."""
    stages = ["read"]
    if needs_package:
        stages += ["download", "check"]
    stages.append("save")
    if service:
        stages.append("restart")
    return tuple(stages)


def _percent(run: dict) -> float:
    plan = run["plan"]
    total = sum(WEIGHTS[s] for s in plan)
    before = sum(WEIGHTS[s] for s in plan[: plan.index(run["stage"])]) if run["stage"] in plan else 0
    now = (before + run["fraction"] * WEIGHTS.get(run["stage"], 0)) / total * 100
    return min(99.0, now)  # 100 is for "done"


def _purge(now: float) -> None:
    for pk in [k for k, r in _runs.items() if now - r["at"] > (KEEP_SECONDS if r["done"] else STALE_SECONDS)]:
        del _runs[pk]
    while len(_runs) >= MAX_RUNS:  # (a few people pressing at once: never a lot; there is room for the one that starts now)
        del _runs[min(_runs, key=lambda k: _runs[k]["at"])]


class Run:
    """One update of one install: what it says about itself. Created by ``begin``."""

    def __init__(self, pk: int, serial: int):
        self.pk, self.serial = pk, serial

    def _mine(self) -> dict | None:
        run = _runs.get(self.pk)
        return run if run is not None and run["serial"] == self.serial and not run["done"] else None

    def stage(self, name: str, fraction: float = 0.0, got: int | None = None, total: int | None = None) -> None:
        """The update is in the stage ``name`` and ``fraction`` (0 to 1) of it is done; ``got`` / ``total`` are the bytes that have come while a file arrives.
        A stage this update does not have is ignored."""
        with _lock:
            run = self._mine()
            if run is None or name not in run["plan"]:
                return
            run.update(stage=name, fraction=min(1.0, max(0.0, fraction)), at=_now(), got=got, total=total)
            run["pct"] = max(run["pct"], _percent(run))

    def replan(self, plan: tuple[str, ...]) -> None:
        """The new version needs other stages than the installed one did (it brings files, or no longer a service)."""
        with _lock:
            run = self._mine()
            if run is not None:
                run["plan"] = plan  # (what is shown stays: the next report counts again, and the bar does not go back)
                if run["stage"] not in plan:
                    run["stage"] = plan[0]

    def finish(self, ok: bool) -> None:
        with _lock:
            run = self._mine()
            if run is None:
                return
            run.update(done=True, ok=ok, at=_now(), got=None, total=None)
            if ok:
                run["pct"] = 100.0


def begin(pk: int, plan: tuple[str, ...], token: str = "") -> Run:
    """An update of the install ``pk`` starts (an earlier one of the same install is forgotten). ``token`` is the mark of the window that pressed the button:
    it asks only for ITS update, never for the finished one of a minute ago, nor for the one somebody else started."""
    now = _now()
    with _lock:
        _purge(now)
        serial = next(_serial)
        _runs[pk] = {
            "serial": serial,
            "plan": plan,
            "stage": plan[0],
            "fraction": 0.0,
            "pct": 0.0,
            "done": False,
            "ok": None,
            "at": now,
            "got": None,
            "total": None,
            "token": token,
        }
    return Run(pk, serial)


def read(pk: int, token: str | None = None) -> dict | None:
    """What the update of ``pk`` has said so far: ``{"stage", "pct", "done", "ok", "got", "total"}``, or None when there is none (or it is long ago). With a
    ``token`` only the update that carries it answers."""
    with _lock:
        run = _runs.get(pk)
        if run is None or (token is not None and run["token"] != token):
            return None
        return {k: run[k] for k in ("stage", "pct", "done", "ok", "got", "total")}


@contextlib.contextmanager
def tracking(run: Run):
    """While this runs, ``report`` (called from deeper down: the reading of a file of a source, the unpacking of a package) tells this update."""
    token = _current.set(run)
    try:
        yield
    finally:
        _current.reset(token)


def report(name: str, fraction: float = 0.0, got: int | None = None, total: int | None = None) -> None:
    """Said by the code that does the work, without knowing who asked: nothing happens when no update is being tracked in this thread."""
    run = _current.get()
    if run is not None:
        run.stage(name, fraction, got, total)


def describe(run: dict | None, t, fnum) -> dict:
    """The answer for the page: ``{"pct", "label", "detail", "done", "ok"}`` in the language of the person (``t`` the translator, ``fnum`` the number format).
    No update known: ``{"state": "none"}`` - the page then shows that it is starting."""
    if run is None:
        return {"state": "none"}
    label = t("updprog.done") if run["done"] and run["ok"] else t("updprog.failed") if run["done"] else t(f"updprog.{run['stage']}")
    detail = ""
    if not run["done"] and run["got"] is not None:
        mb = run["got"] / 1_000_000
        detail = (
            t("updprog.bytes", got=fnum(mb, 1), total=fnum(run["total"] / 1_000_000, 1))
            if run["total"]
            else t("updprog.bytes_open", got=fnum(mb, 1))
        )
    return {"pct": round(run["pct"]), "label": label, "detail": detail, "done": run["done"], "ok": run["ok"]}
