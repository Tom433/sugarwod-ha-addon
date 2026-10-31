#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
set -e

bashio::log.info "Starte SugarWOD Coach ..."

WATCH_FOLDER="$(bashio::config 'watch_folder')"
if [ -n "${WATCH_FOLDER}" ]; then
    mkdir -p "${WATCH_FOLDER}" || bashio::log.warning "Ordner ${WATCH_FOLDER} konnte nicht angelegt werden"
fi

export DATA_DIR=/data
export OPTIONS_FILE=/data/options.json
export PORT=8099

cd /app
exec python3 -m server
