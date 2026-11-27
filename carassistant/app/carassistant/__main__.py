from __future__ import annotations

import logging

import uvicorn

from . import __version__, config, db, events, logsetup, pluginsvc, sources, worker
from .mqtt_ha import publisher


def main() -> None:
    logsetup.setup(config.log_level())
    log = logging.getLogger("carassistant")
    log.info("Car Assistant %s starting (log level %s, data: %s)", __version__, logsetup.level_name(config.log_level()), config.data_dir())
    db.migrate()
    try:
        with db.tx() as conn:
            sources.seed_bundled(conn)  # the standard source as it came with this version: its list needs no connection
    except Exception:
        log.exception("The packages that came with this version could not be listed")
    try:
        publisher.start()
    except Exception:
        log.exception("MQTT could not be started")
    worker.start()
    pluginsvc.start_supervisor()
    try:
        uvicorn.run(
            "carassistant.asgi:app",
            host="0.0.0.0",  # noqa: S104 - reachable only through the Supervisor ingress gateway (checked in web.py)
            port=config.port(),
            log_level=logsetup.uvicorn_level(config.log_level()),
            log_config=None,  # its lines go through our handler too: one format, and the filter against repeats
            proxy_headers=False,
            access_log=False,
        )
    finally:
        pluginsvc.stop_all()
        events.stop.set()
        publisher.stop()


if __name__ == "__main__":
    main()
