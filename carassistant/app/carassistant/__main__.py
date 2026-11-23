from __future__ import annotations

import logging

import uvicorn

from . import __version__, config, db, events, pluginsvc, worker
from .mqtt_ha import publisher


def main() -> None:
    logging.basicConfig(level=config.log_level(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("carassistant")
    log.info("Car Assistant %s starting (data: %s)", __version__, config.data_dir())
    db.migrate()
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
            log_level=config.log_level().lower(),
            proxy_headers=False,
            access_log=False,
        )
    finally:
        pluginsvc.stop_all()
        events.stop.set()
        publisher.stop()


if __name__ == "__main__":
    main()
