# Raspberry Pi Network Monitor - Deployment Guide

**Versie**: 2.0  
**Laatst bijgewerkt**: 11 december 2025  
**Author**: Lovepreet Singh  
**Project**: HOWEST TIC CFAI - IoT Monitoring Opdracht

---

## 🚀 Quick Start

### Prerequisites

- Raspberry Pi (3 of hoger) met Raspbian OS
- Python 3.11+
- Docker (voor QuestDB)
- Azure account met IoT Hub

### 1. Environment Setup

```bash
# Clone en navigeer naar project
git clone <repository-url> piNetMon && cd piNetMon

# Create virtual environment en installeer dependencies
python3 -m venv pivenv
source pivenv/bin/activate
pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Start QuestDB container
docker run -d --name questdb \
  -p 9000:9000 -p 9009:9009 -p 8812:8812 \
  -v ~/piNetMon/data/questdb:/var/lib/questdb \
  questdb/questdb

# Verify: http://localhost:9000
```

### 3. Configuration

Edit `config/config.json`:

```json
{
  "azure": {
    "iot_hub": {
      "connection_string": "HostName=<hub>.azure-devices.net;DeviceId=<device>;SharedAccessKey=<key>"
    }
  },
  "mongodb": {
    "enabled": true,
    "connection_string": "mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/"
  }
}
```

### 4. Model Training & Application Start

```bash
# Train local AI model
python3 azure-ml/train_model.py

# Start monitoring
python3 src/main.py

# Start dashboard (nieuwe terminal)
streamlit run dashboard/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

**Dashboard toegankelijk op**: `http://<pi-ip>:8501`

## 🔧 Remote Configuration

### Via Device Twin (Azure Portal)

**Azure Portal** → **IoT Hub** → **Devices** → **rapsberry-pi-monitor** → **Device twin**

Bewerk `desired` properties en save - Pi past automatisch aan:

```json
{
  "desired": {
    "collection_interval": 30,
    "sensors": {
      "cpu": {"enabled": true, "interval_seconds": 30},
      "temperature": {"enabled": true, "interval_seconds": 60}
    }
  }
}
```

### Via Direct Methods

| Method | Payload | Beschrijving |
|--------|---------|-------------|
| `getConfig` | `{}` | Huidige configuratie |
| `updateConfig` | `{"collection_interval": 45}` | Update parameters |

## 🔄 Development Sync

```bash
# Sync naar Raspberry Pi
rsync -avz --progress --exclude='__pycache__/' --exclude='data/' --exclude='pivenv/' --exclude='*.pyc' \
  /home/lovep/piNetMon/ admin@<pi-ip>:/home/admin/piNetMon/
```

## ☁️ Azure ML Deployment (Optional)

```bash
az login && az account set --subscription <subscription-id>
cd azure-ml && python3 deploy_to_azure.py
```

Update `config/config.json` met endpoint URL en API key uit deployment output.

## ✅ Deployment Checklist

**Local (Pi)**

- [ ] QuestDB container running
- [ ] Virtual environment active
- [ ] `config.json` configured
- [ ] Model trained (`models/local-model.pkl`)
- [ ] Main app running (`python3 src/main.py`)
- [ ] Dashboard accessible (port 8501)

**Azure**

- [ ] IoT Hub device registered
- [ ] Azure Function deployed ✅ 
- [ ] MongoDB Atlas active

**Verify:**

```bash
docker ps | grep questdb
ps aux | grep main.py
curl "http://localhost:9000/exec?query=SELECT%20count(*)%20FROM%20sensor_data"
```

## 🐛 Troubleshooting

| Probleem | Oplossing |
|----------|----------|
| **QuestDB connection failed** | `docker restart questdb` en verify met `curl localhost:9000` |
| **Azure IoT Hub timeout** | Check connection string in config.json, test: `ping <hub>.azure-devices.net` |
| **Dashboard no data** | Verify main.py running: `ps aux \| grep main.py` en check QuestDB data |
| **Model training fails** | Wacht tot 10+ samples in QuestDB (gebruikt threshold detector als fallback) |

## 📊 Assignment Status

**Vereisten: 11/11 ✅**

✅ Sensor data (CPU, memory, disk, network) | ✅ Local storage (QuestDB) | ✅ Cloud telemetry (IoT Hub)  
✅ Cloud storage (Blob + MongoDB) | ✅ Local AI (Isolation Forest) | ✅ Cloud AI (Azure ML ready)  
✅ User interaction (Dashboard + Direct Methods) | ✅ Remote config (Device Twin) | ✅ Documentation

**Bonus:**
Azure Functions (188+ invocations) • QuestDB time-series • MongoDB Atlas • Docker • Dual AI

## 📞 Quick Reference

**Common Commands:**

```bash
# Status
docker ps && ps aux | grep python

# Restart
docker restart questdb
pkill -f main.py && python3 src/main.py &

# Logs  
docker logs -f questdb
tail -f logs/main.log
```

**URLs:**

- Dashboard: `http://<pi-ip>:8501`
- QuestDB Console: `http://localhost:9000`
- [Azure Portal](https://portal.azure.com)

---