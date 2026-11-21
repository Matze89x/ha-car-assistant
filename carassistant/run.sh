#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

export CARASSISTANT_DATA="/data"
export CARASSISTANT_LOG_LEVEL="$(bashio::config 'log_level')"

if bashio::services.available "mqtt"; then
    export MQTT_HOST="$(bashio::services mqtt 'host')"
    export MQTT_PORT="$(bashio::services mqtt 'port')"
    export MQTT_USER="$(bashio::services mqtt 'username')"
    export MQTT_PASSWORD="$(bashio::services mqtt 'password')"
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
