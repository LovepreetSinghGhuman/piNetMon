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

# Create logs directory if it doesn't exist
mkdir -p logs

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
if docker ps | grep -q questdb; then
    print_status "QuestDB is already running"
else
    if docker ps -a | grep -q questdb; then
        print_warning "QuestDB container exists but stopped, starting..."
        docker start questdb
    else
        print_warning "QuestDB container not found, creating..."
        docker run -d \
            --name questdb \
            -p 9000:9000 \
            -p 9009:9009 \
            -p 8812:8812 \
            -p 9003:9003 \
            --restart unless-stopped \
            -v ~/piNetMon/data/questdb:/var/lib/questdb \
            questdb/questdb
    fi
    sleep 5
    print_status "QuestDB started"
fi

# Test QuestDB connection (suppress errors, wait a bit longer)
echo "   Testing QuestDB connection..."
sleep 3
python3 -c "import requests; r = requests.get('http://localhost:9000/exec', params={'query': 'SELECT 1'}, timeout=15); exit(0 if r.status_code == 200 else 1)" 2>/dev/null && print_status "QuestDB is accessible" || print_warning "QuestDB may not be ready yet (will retry on first use)"

# 3. Start Streamlit Dashboard (in background)
echo ""
echo "3. Starting Streamlit Dashboard..."
if pgrep -f "streamlit run.*dashboard.py" > /dev/null; then
    print_status "Streamlit is already running"
else
    source pivenv/bin/activate
    nohup streamlit run dashboard/dashboard.py --server.address 0.0.0.0 --server.port 8501 > logs/dashboard.log 2>&1 &
    STREAMLIT_PID=$!
    sleep 3
    if ps -p $STREAMLIT_PID > /dev/null; then
        print_status "Streamlit started (PID: $STREAMLIT_PID)"
        echo "   Dashboard: http://$(hostname -I | awk '{print $1}'):8501"
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
    nohup python3 src/main.py > logs/main.log 2>&1 &
    MAIN_PID=$!
    sleep 3
    if ps -p $MAIN_PID > /dev/null; then
        print_status "Main application started (PID: $MAIN_PID)"
    else
        print_error "Failed to start main application"
        print_warning "Check logs/main.log for errors"
    fi
    deactivate
fi

# Summary
echo ""
echo "=================================="
echo "Deployment Summary"
echo "=================================="
docker ps --filter "name=questdb" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Running Processes:"
pgrep -af "streamlit|src/main.py" || echo "No monitoring processes found"
echo ""
echo "Logs:"
echo "  - Dashboard: logs/dashboard.log"
echo "  - Main App:  logs/main.log"
echo ""
echo "Access Points:"
echo "  - Dashboard:  http://$(hostname -I | awk '{print $1}'):8501"
echo "  - QuestDB UI: http://$(hostname -I | awk '{print $1}'):9000"
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