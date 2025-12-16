#!/bin/bash
# Pi Network Monitor Deployment Script (Cleaned)

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load configuration from config.json
CONFIG_FILE="$SCRIPT_DIR/config/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "✗ Error: config.json not found at $CONFIG_FILE"
    exit 1
fi

get_config() {
    python3 -c "import json; config=json.load(open('$CONFIG_FILE')); print($1)" 2>/dev/null || echo "$2"
}

QDB_CONTAINER=$(get_config "config['questdb']['docker']['container_name']" "questdb")
QDB_PORT_HTTP=$(get_config "config['questdb']['docker']['ports']['http']" "9000")

QDB_VOLUME=$(get_config "config['questdb']['docker']['volume_path']" "~/piNetMon/data/questdb")
QDB_RESTART=$(get_config "config['questdb']['docker']['restart_policy']" "unless-stopped")
DASH_HOST=$(get_config "config['dashboard']['host']" "0.0.0.0")
DASH_PORT=$(get_config "config['dashboard']['port']" "8501")
LOG_DIR=$(get_config "config['logging']['log_dir']" "./logs")


MAIN_APP_SCRIPT=$(get_config "config['services']['main_app']['script']" "src/main.py")
MAIN_APP_PATTERN=$(get_config "config['services']['main_app']['process_pattern']" "python.*src/main.py")
MAIN_APP_LOG=$(get_config "config['services']['main_app']['log']" "logs/monitor.log")
DASHBOARD_SCRIPT=$(get_config "config['services']['dashboard']['script']" "dashboard/dashboard.py")
DASHBOARD_PATTERN=$(get_config "config['services']['dashboard']['process_pattern']" "streamlit run.*dashboard.py")
DASHBOARD_LOG=$(get_config "config['services']['dashboard']['log']" "logs/dashboard.log")
MONGO_DB=$(get_config "config['mongodb']['database']" "piNetMon")
MONGO_COLLECTION=$(get_config "config['mongodb']['collection']" "sensor_data")

mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}✓${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

TAILSCALE_HOSTNAME=""
if command -v tailscale &> /dev/null; then
    TAILSCALE_HOSTNAME=$(tailscale status --json 2>/dev/null | grep -o '"HostName":"[^"]*"' | cut -d'"' -f4 || echo "")
    [ -z "$TAILSCALE_HOSTNAME" ] && TAILSCALE_HOSTNAME=$(hostname)
fi

# 1. Check Docker service
if systemctl is-active --quiet docker; then
    print_status "Docker service is running"
else
    sudo systemctl start docker && sleep 2
    systemctl is-active --quiet docker && print_status "Docker service started" || print_error "Docker failed to start"
fi

# 2. Start QuestDB container
if docker ps | grep -q "$QDB_CONTAINER"; then
    print_status "QuestDB is running"
else
    if docker ps -a | grep -q "$QDB_CONTAINER"; then
        docker start "$QDB_CONTAINER"
    else
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
    docker ps | grep -q "$QDB_CONTAINER" && print_status "QuestDB started" || print_error "QuestDB failed to start"
fi

# Test QuestDB connection
sleep 3
python3 -c "import requests; r = requests.get('http://localhost:$QDB_PORT_HTTP/exec', params={'query': 'SELECT 1'}, timeout=15); exit(0 if r.status_code == 200 else 1)" 2>/dev/null && print_status "QuestDB accessible" || print_warning "QuestDB may not be ready yet"

# 3. Test MongoDB Atlas connection
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from mongodb_storage import MongoDBStorage
    mongo = MongoDBStorage()
    if mongo.is_connected:
        stats = mongo.get_statistics()
        print('✓ MongoDB connected: {}.{} ({} docs)'.format(stats.get('database'), stats.get('collection'), stats.get('total_documents', 0)))
        mongo.disconnect()
        exit(0)
    else:
        print('⚠️ MongoDB not connected')
        exit(1)
except Exception as e:
    print(f'✗ MongoDB error: {e}')
    exit(1)
" && print_status "MongoDB backup ready" || print_warning "MongoDB backup unavailable"


# Helper to start a service if not running
start_service() {
    local pattern="$1"
    local start_cmd="$2"
    local log_file="$3"
    local name="$4"
    if pgrep -f "$pattern" > /dev/null; then
        print_status "$name running"
    else
        source pivenv/bin/activate
        nohup $start_cmd > "$log_file" 2>&1 &
        local pid=$!
        sleep 3
        ps -p $pid > /dev/null && print_status "$name started (PID: $pid)" || print_error "$name failed (see $log_file)"
        deactivate
    fi
}

# Start Dashboard
start_service "$DASHBOARD_PATTERN" "streamlit run $DASHBOARD_SCRIPT --server.address $DASH_HOST --server.port $DASH_PORT" "$DASHBOARD_LOG" "Streamlit Dashboard"
# Start Main App
start_service "$MAIN_APP_PATTERN" "python3 $MAIN_APP_SCRIPT" "$MAIN_APP_LOG" "Main Monitoring App"

# 6. Show which AI model will be used (ONNX or PKL)
source pivenv/bin/activate
python3 -c "import sys; sys.path.insert(0, 'src'); from ai_models import AnomalyDetector; det = AnomalyDetector(); print(f'AI model: {'ONNX' if det.onnx_model else 'PKL'}')" || echo "AI model preference unknown."
deactivate

# Summary
echo
echo "========== Deployment Summary =========="
echo

# Storage Services
echo "Storage Services:"
docker ps --filter "name=$QDB_CONTAINER" --format "  - QuestDB: {{.Status}}" | grep . || echo "  - QuestDB: Not running"
echo "  - MongoDB Atlas: $MONGO_DB.$MONGO_COLLECTION"


# Running Processes
echo
echo "Running Processes:"
for svc in "dashboard" "main_app"; do
    pattern=$(get_config "config['services'][\"$svc\"]['process_pattern']" "")
    name=$(echo $svc | sed 's/_/ /g' | sed 's/\b./\u&/g')
    pid=$(pgrep -f "$pattern" | head -n1)
    if [ -n "$pid" ]; then
        echo "  - $name (PID: $pid)"
    else
        echo "  - $name: Not running"
    fi
done

# Logs
echo
echo "Logs:"
echo "  - Dashboard: $LOG_DASHBOARD"
echo "  - Main App:  $LOG_MAIN"

# Access Points
echo
echo "Access Points:"
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "  - Dashboard:  http://$IP_ADDR:$DASH_PORT"
echo "  - QuestDB UI: http://$IP_ADDR:$QDB_PORT_HTTP"
if [ -n "$TAILSCALE_HOSTNAME" ]; then
    echo "  - Dashboard (Tailscale):  http://$TAILSCALE_HOSTNAME:$DASH_PORT"
    echo "  - QuestDB UI (Tailscale): http://$TAILSCALE_HOSTNAME:$QDB_PORT_HTTP"
fi

echo
print_status "Deployment complete!"