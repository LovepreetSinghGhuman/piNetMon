#!/bin/bash
# Sync piNetMon project to/from remote Raspberry Pi
# Usage: ./sync.sh [up|down] [optional:custom-destination]
#   up:   local → Pi (default)
#   down: Pi → local

SRC_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$SRC_DIR/config/config.json"
PI_IP=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('pi_ip', '192.168.0.100'))" 2>/dev/null)
REMOTE="admin@${PI_IP}:/home/admin/piNetMon/"

DIRECTION="up"
if [[ "$1" == "down" ]]; then
    DIRECTION="down"
    shift
elif [[ "$1" == "up" ]]; then
    shift
fi

if [ -n "$1" ]; then
    REMOTE="$1"
fi

EXCLUDES=(--exclude='__pycache__/' --exclude='data/' --exclude='.vscode/' --exclude='pivenv/' --exclude='*.pyc')

if [[ "$DIRECTION" == "down" ]]; then
    rsync -avz --progress "${EXCLUDES[@]}" "$REMOTE" "$SRC_DIR/"
    STATUS=$?
    if [ $STATUS -eq 0 ]; then
        echo "✓ Sync complete: $REMOTE → $SRC_DIR"
    else
        echo "✗ Sync failed"
        exit 1
    fi
else
    rsync -avz --progress "${EXCLUDES[@]}" "$SRC_DIR/" "$REMOTE"
    STATUS=$?
    if [ $STATUS -eq 0 ]; then
        echo "✓ Sync complete: $SRC_DIR → $REMOTE"
    else
        echo "✗ Sync failed"
        exit 1
    fi
fi
