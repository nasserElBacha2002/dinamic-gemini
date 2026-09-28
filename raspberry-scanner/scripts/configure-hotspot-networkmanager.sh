#!/usr/bin/env bash
set -euo pipefail

# This script changes NetworkManager configuration. Run it explicitly as root on
# Raspberry Pi OS systems that use NetworkManager; it never runs from app.py.
if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
command -v nmcli >/dev/null || { echo "NetworkManager/nmcli is required." >&2; exit 1; }

WIFI_INTERFACE=${WIFI_INTERFACE:-wlan0}
HOTSPOT_NAME=${HOTSPOT_NAME:-Dinamic-Scanner}
HOTSPOT_PASSWORD=${HOTSPOT_PASSWORD:-}

if [[ ${#HOTSPOT_PASSWORD} -lt 8 ]]; then
  echo "Set HOTSPOT_PASSWORD to at least 8 characters before running this script." >&2
  exit 1
fi

nmcli connection delete dinamic-scanner-hotspot 2>/dev/null || true
nmcli device wifi hotspot ifname "$WIFI_INTERFACE" con-name dinamic-scanner-hotspot ssid "$HOTSPOT_NAME" password "$HOTSPOT_PASSWORD"
nmcli connection modify dinamic-scanner-hotspot connection.autoconnect yes ipv4.method shared ipv6.method disabled
nmcli connection up dinamic-scanner-hotspot
nmcli -g IP4.ADDRESS device show "$WIFI_INTERFACE"
