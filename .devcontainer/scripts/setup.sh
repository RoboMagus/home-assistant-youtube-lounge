#!/usr/bin/env bash
set -e

apk update && apk add --no-cache git wget

pip install -r requirements.txt

hass -c ha-config --script ensure_config

# Symlink custom integration into HA Config directory
mkdir -p ha-config/custom_components
ln -sf ../../custom_components/yt_lounge ha-config/custom_components/yt_lounge

# Install HACS
if [ ! -d "ha-config/custom_components/hacs" ]; then
    mkdir -p ha-config/custom_components/hacs
    echo "Downloading HACS"
    wget "https://github.com/hacs/integration/releases/latest/download/hacs.zip" -O hacs.zip
    unzip hacs.zip -d ha-config/custom_components/hacs >/dev/null 2>&1
    rm hacs.zip
fi
