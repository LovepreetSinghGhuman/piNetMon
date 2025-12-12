#!/bin/bash
# Pi Network Monitor Deployment Script
# Run this after Pi reboot to start all services

set -e  # Exit on error

echo "=================================="
echo "Pi Network Monitor - Deployment"
echo "=================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load configuration from config.json
CONFIG_FILE="$SCRIPT_DIR/config/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.json not found at $CONFIG_FILE"
    exit 1
fi

# Extract config values using Python
get_config() {
    python3 -c "import json; config=json.load(open('$CONFIG_FILE')); print($1)" 2>/dev/null || echo "$2"
}

# Load QuestDB Docker configuration
QDB_CONTAINER=$(get_config "config['questdb']['docker']['container_name']" "questdb")
QDB_PORT_HTTP=$(get_config "config['questdb']['docker']['ports']['http']" "9000")
QDB_PORT_INFLUX=$(get_config "config['questdb']['docker']['ports']['influxdb']" "9009")
QDB_PORT_PG=$(get_config "config['questdb']['docker']['ports']['postgres']" "8812")
QDB_PORT_MIN=$(get_config "config['questdb']['docker']['ports']['min_http']" "9003")
QDB_VOLUME=$(get_config "config['questdb']['docker']['volume_path']" "~/piNetMon/data/questdb")
QDB_RESTART=$(get_config "config['questdb']['docker']['restart_policy']" "unless-stopped")

# Load Dashboard configuration
DASH_HOST=$(get_config "config['dashboard']['host']" "0.0.0.0")
DASH_PORT=$(get_config "config['dashboard']['port']" "8501")

# Load Logging configuration
LOG_DIR=$(get_config "config['logging']['log_dir']" "./logs")
LOG_DASHBOARD=$(get_config "config['logging']['files']['dashboard']" "logs/dashboard.log")
LOG_MAIN=$(get_config "config['logging']['files']['main']" "logs/monitor.log")

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Get Tailscale hostname if available
TAILSCALE_HOSTNAME=""
if command -v tailscale &> /dev/null; then
    TAILSCALE_HOSTNAME=$(tailscale status --json 2>/dev/null | grep -o '"HostName":"[^"]*"' | cut -d'"' -f4 || echo "")
    if [ -z "$TAILSCALE_HOSTNAME" ]; then
        TAILSCALE_HOSTNAME=$(hostname)
    fi
fi

# 1. Check Docker service
echo "1. Checking Docker..."
if systemctl is-active --quiet docker; then
    print_status "Docker service is running"
else
    print_warning "Docker service not running, starting..."
    sudo systemctl start docker
    sleep 2
    print_status "Docker service started"
fi

# 2. Start QuestDB container
echo ""
echo "2. Starting QuestDB..."
if docker ps | grep -q "$QDB_CONTAINER"; then
    print_status "QuestDB is already running"
else
    if docker ps -a | grep -q "$QDB_CONTAINER"; then
        print_warning "QuestDB container exists but stopped, starting..."
        docker start "$QDB_CONTAINER"
    else
        print_warning "QuestDB container not found, creating..."
        docker run -d \
            --name "$QDB_CONTAINER" \
            -p "$QDB_PORT_HTTP:9000" \
            -p "$QDB_PORT_INFLUX:9009" \
            -p "$QDB_PORT_PG:8812" \
            -p "$QDB_PORT_MIN:9003" \
            --restart "$QDB_RESTART" \
            -v "$QDB_VOLUME:/var/lib/questdb" \
            questdb/questdb
    fi
    sleep 5
    print_status "QuestDB started"
fi

# Test QuestDB connection (suppress errors, wait a bit longer)
echo "   Testing QuestDB connection..."
sleep 3
python3 -c "import requests; r = requests.get('http://localhost:$QDB_PORT_HTTP/exec', params={'query': 'SELECT 1'}, timeout=15); exit(0 if r.status_code == 200 else 1)" 2>/dev/null && print_status "QuestDB is accessible" || print_warning "QuestDB may not be ready yet (will retry on first use)"

# 3. Start Streamlit Dashboard (in background)
echo ""
echo "3. Starting Streamlit Dashboard..."
if pgrep -f "streamlit run.*dashboard.py" > /dev/null; then
    print_status "Streamlit is already running"
else
    source pivenv/bin/activate
    nohup streamlit run dashboard/dashboard.py --server.address "$DASH_HOST" --server.port "$DASH_PORT" > "$LOG_DASHBOARD" 2>&1 &
    STREAMLIT_PID=$!
    sleep 3
    if ps -p $STREAMLIT_PID > /dev/null; then
        print_status "Streamlit started (PID: $STREAMLIT_PID)"
        echo "   Local: http://$(hostname -I | awk '{print $1}'):$DASH_PORT"
        [ -n "$TAILSCALE_HOSTNAME" ] && echo "   Tailscale: http://$TAILSCALE_HOSTNAME:$DASH_PORT"
    else
        print_error "Failed to start Streamlit"
    fi
    deactivate
fi

# 4. Start Main Monitoring Application (in background)
echo ""
echo "4. Starting Main Monitoring Application..."
if pgrep -f "python.*src/main.py" > /dev/null; then
    print_status "Main application is already running"
else
    source pivenv/bin/activate
    nohup python3 src/main.py > "$LOG_MAIN" 2>&1 &
    MAIN_PID=$!
    sleep 3
    if ps -p $MAIN_PID > /dev/null; then
        print_status "Main application started (PID: $MAIN_PID)"
    else
        print_error "Failed to start main application"
        print_warning "Check $LOG_MAIN for errors"
    fi
    deactivate
fi

# Summary
echo ""
echo "=================================="
echo "Deployment Summary"
echo "=================================="
docker ps --filter "name=$QDB_CONTAINER" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Running Processes:"
pgrep -af "streamlit|src/main.py" || echo "No monitoring processes found"
echo ""
echo "Logs:"
echo "  - Dashboard: $LOG_DASHBOARD"
echo "  - Main App:  $LOG_MAIN"
echo ""
echo "Access Points:"
echo "  Local Network:"
echo "    - Dashboard:  http://$(hostname -I | awk '{print $1}'):$DASH_PORT"
echo "    - QuestDB UI: http://$(hostname -I | awk '{print $1}'):$QDB_PORT_HTTP"
if [ -n "$TAILSCALE_HOSTNAME" ]; then
    echo ""
    echo "  Tailscale (Remote Access):"
    echo "    - Dashboard:  http://$TAILSCALE_HOSTNAME:$DASH_PORT"
    echo "    - QuestDB UI: http://$TAILSCALE_HOSTNAME:$QDB_PORT_HTTP"
fi
echo ""
print_status "Deployment complete!"

# Optional: Sync updated files to remote Pi
# rsync -avz --progress \
#   --exclude='__pycache__/' \
#   --exclude='data/' \
#   --exclude='.vscode/' \
#   --exclude='pivenv/' \
#   --exclude='*.pyc' \
#   /home/lovep/piNetMon/ admin@<PI-IP>:/home/admin/piNetMon/