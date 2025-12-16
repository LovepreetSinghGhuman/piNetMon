#!/bin/bash
# Sync piNetMon project to remote Raspberry Pi
# Usage: ./sync_to_pi.sh [user@host:/remote/path]


SRC_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$SRC_DIR/config/config.json"
PI_IP=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('pi_ip', '192.168.0.100'))" 2>/dev/null)
DEST="admin@${PI_IP}:/home/admin/piNetMon/"

if [ -n "$1" ]; then
    DEST="$1"
fi

rsync -avz --progress \
  --exclude='__pycache__/' \
  --exclude='data/' \
  --exclude='.vscode/' \
  --exclude='pivenv/' \
  --exclude='*.pyc' \
  "$SRC_DIR/" "$DEST"

if [ $? -eq 0 ]; then
    echo "✓ Sync complete: $SRC_DIR → $DEST"
else
    echo "✗ Sync failed"
    exit 1
fi
