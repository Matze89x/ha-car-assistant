# syntax=docker/dockerfile:1
# Car Assistant Developer: the same app, built from the newest state of the `dev` branch of this repository.
# Home Assistant builds an add-on from its own folder only, so the source is fetched here at build time. BUILD_VERSION changes with every
# dev version, which is what makes the download run again (an unchanged version reuses the cached layer).
ARG BUILD_FROM=ghcr.io/home-assistant/base:3.23
FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH
ARG SOURCE_BRANCH=dev

RUN apk add --no-cache python3 py3-pip tzdata curl \
 && python3 -m venv /opt/venv

RUN echo "dev build ${BUILD_VERSION}" \
 && mkdir -p /tmp/src \
 && curl -fsSL "https://github.com/Matze89x/ha-car-assistant/archive/refs/heads/${SOURCE_BRANCH}.tar.gz" | tar -xz -C /tmp/src --strip-components=1 \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/src/carassistant/requirements.txt \
 && cp -r /tmp/src/carassistant/app /app \
 && cp /tmp/src/carassistant/run.sh /run.sh \
 && chmod a+x /run.sh \
 && rm -rf /tmp/src

WORKDIR /app
CMD ["/run.sh"]

LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.title="Car Assistant Developer" \
      org.opencontainers.image.description="Car Assistant - the newest development state" \
      org.opencontainers.image.source="https://github.com/Matze89x/ha-car-assistant"
