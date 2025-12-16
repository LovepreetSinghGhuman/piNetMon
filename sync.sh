#!/bin/bash
# Sync piNetMon project to/from remote Raspberry Pi
# Usage: ./sync.sh [up|down] [optional:custom-destination]
#   up:   local → Pi (default)
#   down: Pi → local

SRC_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$SRC_DIR/config/config.json"
PI_IP=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('pi_ip'))" 2>/dev/null)
PI_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('pi_user', 'admin'))" 2>/dev/null)
PI_PROJECT_PATH=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('pi_project_path', '/home/admin/piNetMon/'))" 2>/dev/null)
SYNC_EXCLUDES=$(python3 -c "import json; print(' '.join([f'--exclude=\"{x}\"' for x in json.load(open('$CONFIG_FILE')).get('sync_excludes', [])]))" 2>/dev/null)
REMOTE="${PI_USER}@${PI_IP}:${PI_PROJECT_PATH}"

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



# Only run the requested direction and exit immediately after
if [[ "$DIRECTION" == "down" ]]; then
    eval rsync -avz --progress $SYNC_EXCLUDES "$REMOTE" "$SRC_DIR/"
    STATUS=$?
    if [ $STATUS -eq 0 ]; then
        echo "✓ Sync complete: $REMOTE → $SRC_DIR"
    else
        echo "✗ Sync failed"
        exit 1
    fi
    exit 0
else
    eval rsync -avz --progress $SYNC_EXCLUDES "$SRC_DIR/" "$REMOTE"
    STATUS=$?
    if [ $STATUS -eq 0 ]; then
        echo "✓ Sync complete: $SRC_DIR → $REMOTE"
    else
        echo "✗ Sync failed"
        exit 1
    fi
    exit 0
fi
