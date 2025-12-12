#!/bin/bash
# Pi Network Monitor Shutdown Script
# Stops all running services

set -e  # Exit on error

echo "=================================="
echo "Pi Network Monitor - Shutdown"
echo "=================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Load configuration from config.json
CONFIG_FILE="$SCRIPT_DIR/config/config.json"
if [ -f "$CONFIG_FILE" ]; then
    QDB_CONTAINER=$(python3 -c "import json; config=json.load(open('$CONFIG_FILE')); print(config['questdb']['docker']['container_name'])" 2>/dev/null || echo "questdb")
else
    QDB_CONTAINER="questdb"
fi

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

# 1. Stop Main Monitoring Application
echo "1. Stopping Main Monitoring Application..."
if pgrep -f "python.*src/main.py" > /dev/null; then
    pkill -f "python.*src/main.py"
    sleep 2
    if pgrep -f "python.*src/main.py" > /dev/null; then
        print_warning "Process still running, force killing..."
        pkill -9 -f "python.*src/main.py"
    fi
    print_status "Main application stopped"
else
    print_warning "Main application was not running"
fi

# 2. Stop Streamlit Dashboard
echo ""
echo "2. Stopping Streamlit Dashboard..."
if pgrep -f "streamlit run.*dashboard.py" > /dev/null; then
    pkill -f "streamlit run.*dashboard.py"
    sleep 2
    if pgrep -f "streamlit run.*dashboard.py" > /dev/null; then
        print_warning "Process still running, force killing..."
        pkill -9 -f "streamlit run.*dashboard.py"
    fi
    print_status "Streamlit dashboard stopped"
else
    print_warning "Streamlit dashboard was not running"
fi

# 3. Stop QuestDB container
echo ""
echo "3. Stopping QuestDB..."
if docker ps | grep -q "$QDB_CONTAINER"; then
    docker stop "$QDB_CONTAINER"
    print_status "QuestDB stopped"
else
    print_warning "QuestDB was not running"
fi

# Summary
echo ""
echo "=================================="
echo "Shutdown Summary"
echo "=================================="
echo "Running processes:"
pgrep -af "streamlit|src/main.py" || print_status "No monitoring processes running"
echo ""
echo "Docker containers:"
docker ps --filter "name=$QDB_CONTAINER" --format "table {{.Names}}\t{{.Status}}" 2>/dev/null || print_status "No QuestDB container running"
echo ""
print_status "All services stopped!"
