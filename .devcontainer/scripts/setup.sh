#!/usr/bin/env bash
set -e

apk update && apk add --no-cache git wget

hass -c ha-config --script ensure_config
