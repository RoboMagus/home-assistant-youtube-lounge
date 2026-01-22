#!/usr/bin/env bash
set -e

apk update && apk add --no-cache git wget

pip install -r requirements.txt

hass -c ha-config --script ensure_config

# Symlink custom integration into HA Config directory
mkdir -p ha-config/custom_components
ln -sf custom_components/yt_lounge ha-config/custom_components/yt_lounge

