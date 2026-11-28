#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

export CARASSISTANT_DATA="/data"
export CARASSISTANT_LOG_LEVEL="$(bashio::config 'log_level')"

# The MQTT service of the Supervisor (a broker app, when one is installed). Asked quietly with curl: bashio::services.available writes an ERROR line
# ("Service not enabled") into the log at every start of an installation that has no broker, though that is no error at all.
mqtt_json="$(curl -sf -m 5 -H "Authorization: Bearer ${SUPERVISOR_TOKEN:-}" http://supervisor/services/mqtt 2>/dev/null || true)"
if [ -n "${mqtt_json:-}" ]; then
    export MQTT_HOST="$(bashio::jq "${mqtt_json:-}" '.data.host // empty')"
    export MQTT_PORT="$(bashio::jq "${mqtt_json:-}" '.data.port // empty')"
    export MQTT_USER="$(bashio::jq "${mqtt_json:-}" '.data.username // empty')"
    export MQTT_PASSWORD="$(bashio::jq "${mqtt_json:-}" '.data.password // empty')"
fi

# Add-on configuration (Settings -> Apps -> Car Assistant -> Configuration): the sensors in Home Assistant via MQTT, optionally an own broker
if bashio::config.has_value 'mqtt_host'; then
    export MQTT_HOST="$(bashio::config 'mqtt_host')"
    export MQTT_PORT="$(bashio::config 'mqtt_port')"
    export MQTT_USER="$(bashio::config 'mqtt_user')"
    export MQTT_PASSWORD="$(bashio::config 'mqtt_password')"
fi
if [ "$(bashio::config 'mqtt_sensors')" = "true" ]; then
    export MQTT_SENSORS="1"
fi

case "$CARASSISTANT_LOG_LEVEL" in debug|info) bashio::log.info "Starting Car Assistant" ;; esac
cd /app
exec /opt/venv/bin/python -m carassistant
