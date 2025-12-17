#!/bin/bash
# WiFi Selector Script for Raspberry Pi/Linux
# Lists available WiFi networks, lets user select, and connects using nmcli

set -e

if ! command -v nmcli &> /dev/null; then
    echo "nmcli (NetworkManager) is required. Please install it first."
    exit 1
fi

echo "Scanning for WiFi networks..."
nmcli device wifi rescan > /dev/null

# List networks and let user select
mapfile -t networks < <(nmcli -t -f SSID,SECURITY device wifi list | awk -F: '{if($1!="") print $1" ["$2"]"}')

if [ ${#networks[@]} -eq 0 ]; then
    echo "No WiFi networks found."
    exit 1
fi

echo "Available WiFi networks:"
select net in "${networks[@]}"; do
    if [ -n "$net" ]; then
        ssid=$(echo "$net" | awk -F' [' '{print $1}')
        break
    fi
done

read -sp "Enter WiFi password for '$ssid': " wifi_pass

echo

# Try to connect
if nmcli device wifi connect "$ssid" password "$wifi_pass"; then
    echo "Successfully connected to $ssid!"
    ip_addr=$(hostname -I | awk '{print $1}')
    echo "Your IP address: $ip_addr"
else
    echo "Failed to connect to $ssid."
    exit 1
fi
