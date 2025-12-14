# Raspberry Pi Network Monitoring Platform – Documentatie

**Auteur:** Lovepreet Singh  
**Versie:** 3.1  
**Datum:** 14 december 2025  
**Project:** HOWEST TIC – CFAI Eindopdracht

---

## 📘 1. Inleiding

Dit project ontwikkelt een **real-time netwerk- en systeemmonitoringplatform** met een **Raspberry Pi** als IoT-device en een moderne **cloud-gebaseerde analytics pipeline** op **Azure**.

Het systeem verzamelt systeemstatistieken, detecteert anomalieën met **Edge AI + Cloud AI**, slaat data op in **QuestDB** en **MongoDB Atlas**, en visualiseert alles in een **Streamlit dashboard**.

Het platform is ontworpen voor:

- Real-time monitoring  
- Anomaly detection  
- Historische analyse  
- Cloud-integratie  
- Schaalbaarheid & betrouwbaarheid (Azure serverless + Azure ML)

---

## 📡 2. Architectuur – High-Level Overzicht

  ┌──────────────────┐
  │ Raspberry Pi      │
  │ (IoT Device)      │
  └───────┬──────────┘
          │ Telemetry (JSON)
          ▼
  ┌──────────────────┐
  │ Azure IoT Hub     │
  └───────┬──────────┘
          │ Trigger
          ▼
  ┌──────────────────┐
  │ Azure Functions   │
  └───────┬──────────┘
          │ Process → Score → Store
          ▼
  ┌─────────────────────────────────────────┐
  │ QuestDB Cloud  │ MongoDB Atlas │ Blob    │
  └─────────────────────────────────────────┘

  ┌──────────────────────┐
  │ Azure ML Endpoint    │
  └──────────────────────┘

  ┌──────────────────────┐
  │ Streamlit Dashboard  │
  └──────────────────────┘

---

## ⚙️ 3. Componentenoverzicht

### 3.1 Raspberry Pi (Edge Device)

| Component                 | Beschrijving |
|--------------------------|--------------|
| **Sensor Collector**     | Leest CPU, RAM, disk, network en CPU-temperatuur uit. |
| **QuestDB (lokaal)**     | Lokaal time-series opslag, draait in Docker container met auto-restart. |
| **Unified AI Model**     | `ai_models.py` bevat training, local AI en cloud AI functionaliteit. |
| **Threshold-fallback**   | Simpele grenswaardedetectie bij model failure. |
| **Azure IoT Client**     | Verzenden van telemetrie + cloud configuratie. |
| **Runtime configuratie** | Updatebaar via IoT Hub Device Twin. |
| **Deployment scripts**   | `deploy_pi.sh` en `stop_pi.sh` voor service management. |

---

#### 3.2 Cloud Componenten

##### Azure IoT Hub

- Device-to-Cloud telemetrie
- Cloud-to-Device commands
- Direct Methods
- Device Twin configuratiebeheer

##### Azure Functions

- Trigger: IoT Hub events
- Taken:
  - Telemetry parsing
  - Health score berekenen
  - Anomaly detection
  - Opslaan in QuestDB / Blob / MongoDB

##### Azure ML (Cloud AI)

- Managed endpoint voor anomaly inferencing
- Isolation Forest model (scikit-learn 1.8.0)
- Key-based authentication

##### Datastores

| Service | Functie |
|---------|---------|
| **QuestDB Cloud** | High-performance time-series opslag |
| **MongoDB Atlas** | JSON backups & redundancy |
| **Azure Blob Storage** | Archival & cold storage |

---

## 🤖 4. AI Architectuur

Het systeem gebruikt een **Unified AI Module** (`ai_models.py`) met **ONNX-optimalisatie** voor snellere inferencing.

### 4.1 Model Training & Export

**Functie:** `train_and_save_models()`

**Proces:**

1. Laadt real sensor data uit QuestDB (374+ samples)
2. Fallback naar synthetische data bij < 100 samples
3. Traint Isolation Forest model (scikit-learn 1.8.0)
4. Exporteert naar **dubbel formaat**:
   - `model.pkl` + `scaler.pkl` (pickle - backward compatibility)
   - `model.onnx` + `scaler.onnx` (ONNX - optimized runtime)

**ONNX Voordelen:**

- 🚀 2-3x snellere inferencing op CPU
- 📦 20-40% kleinere bestanden
- 🔄 Cross-platform compatibiliteit
- ⚡ Optimaal voor edge devices (Raspberry Pi)

**Training uitvoeren:**

```bash
python3 src/ai_models.py
```

**Output:**

```plaintext
Exporting to ONNX format...
✅ ONNX export complete (saved 35.2%)
Pickle:  ../models/model.pkl, ../models/scaler.pkl
ONNX:    ../models/model.onnx, ../models/scaler.onnx
Samples: 374
```

---

### 4.2 Edge AI – Local Anomaly Detection

**Class:** `AnomalyDetector`

**Runtime Modes:**

- **ONNX Runtime** (primair) - Gebruikt `onnxruntime` voor snelle inferencing
- **Scikit-learn** (fallback) - Pickle-based wanneer ONNX niet beschikbaar

**Auto-selection:**

```python
detector = AnomalyDetector(use_onnx=True)  # Default
# Probeert ONNX eerst → Fallback naar pickle bij failure
```

**Features (6):**

- CPU temperature  
- CPU usage (%)  
- Memory percent  
- Disk percent  
- Network sent MB  
- Network recv MB  

**Model specificaties:**

- Algorithm: Isolation Forest
- Contamination: 0.1 (10% anomaly rate)
- N-estimators: 100
- Random state: 42

**Inference Performance:**

- ONNX: ~1-2ms per prediction
- Pickle: ~3-5ms per prediction

---

### 4.3 Threshold Fallback Detector

**Class:** `SimpleThresholdDetector`

Wordt gebruikt wanneer:

- ML model corrupt of ontbreekt
- Te weinig historische data beschikbaar is
- ONNX en pickle beide falen

**Grenswaarden:**

- CPU temp > **85°C**
- CPU usage > **95%**
- RAM > **90%**
- Disk > **95%**

---

### 4.4 Cloud AI – Azure ML Endpoint

**Class:** `CloudAIService` met `AzureMLClient`

Geavanceerde anomaly analysis via REST API.

**Endpoint:** `pi-anomaly-endpoint`  
**Runtime:** Python 3.11 (conda environment)  
**SKU:** Standard_DS2_v2

**Deployment workflow:**

1. `python3 src/ai_models.py` → Train model lokaal (exports ONNX + pickle)
2. `python3 azure-ml/deploy_to_azure.py` → Upload & deploy  
3. `score.py` → Inference script in Azure (loads pickle)
4. ~10-20 min deployment tijd

**Request voorbeeld:**

```json
{
  "data": {
    "cpu_temperature": 65.0,
    "cpu_usage": 45.0,
    "memory_percent": 60.0,
    "disk_percent": 70.0,
    "network_sent": 150.0,
    "network_recv": 250.0
  }
}
```

**Response:**

```json
{
  "prediction": "normal",
  "anomaly_score": 0.13033342361450195,
  "confidence": 0.9739333152770996,
  "is_anomaly": false,
  "model_type": "onnx"
}
```

**Belangrijk:** Azure ML endpoint retourneert JSON als string - dit wordt automatisch geparsed door `AzureMLClient.predict()`.

**InfluxDB Line Protocol Fix:**
Voor QuestDB opslag worden string velden correct ge-escaped:
```python
# Cloud prediction wordt opgeslagen met dubbele quotes
fields["cloud_prediction"] = f'"{escaped_prediction}"'
```

```

---

## 🗄️ 5. Datastromen

Pi → IoT Hub → Azure Function → QuestDB / Blob / MongoDB
Pi → Azure ML (AI inferencing)
Pi → Streamlit Dashboard

---

## 🌐 6. Azure Integratie

### 6.1 IoT Hub

**Hub:**
HowestTICFAILovepreetHub
**Device ID:**
rapsberry-pi-monitor

**Direct Methods:**

- get_status
- get_statistics
- restart_monitoring
- update_config

**Cloud-to-Device Messages:**

- config_update
- retrain_model
- collect_now

---

### 6.2 Azure Functions

**Function App:**
pi-monitor-functions
**Runtime:**
Python 3.13
**Plan:**
Flex Consumption

**Taken:**

1. IoT Hub trigger verwerken
2. JSON normalisatie
3. Health Score berekenen
4. Anomaly detection
5. Opslag naar QuestDB, Blob, MongoDB

**Vereiste Environment Variables:**

```nginx
IOT_HUB_CONNECTION_STRING
AZURE_STORAGE_CONNECTION_STRING
QUESTDB_HOST
QUESTDB_PORT
```

---

### 6.3 QuestDB

**Docker container met auto-restart:**

```bash
docker run -d \
  --name questdb \
  -p 9000:9000 \
  -p 9009:9009 \
  --restart unless-stopped \
  -v ~/piNetMon/data/questdb:/var/lib/questdb \
  questdb/questdb
```

**Voordelen:**

- Miljoenen rows/sec ingestie
- Time-series optimalisaties
- SQL compatibel
- Web UI op poort 9000

**Connectie optimalisatie:**

- Gebruikt `/exec` endpoint (niet root `/`)
- 15-20 seconden timeout voor Raspberry Pi
- Query direct, geen health check op root endpoint

**Tabelstructuur:**

```sql
CREATE TABLE sensor_data (
  device_id SYMBOL,
  cpu_temperature DOUBLE,
  cpu_usage DOUBLE,
  memory_percent DOUBLE,
  disk_percent DOUBLE,
  network_sent_mb DOUBLE,
  network_recv_mb DOUBLE,
  anomaly_score DOUBLE,
  is_anomaly BOOLEAN,
  cloud_anomaly_score DOUBLE,
  cloud_is_anomaly BOOLEAN,
  cloud_prediction STRING,
  timestamp TIMESTAMP
) timestamp(timestamp) PARTITION BY DAY;
```

**Cloud AI Kolommen (Nieuw!):**
- `cloud_anomaly_score`: Anomaly score van Azure ML endpoint (0.0 - 1.0)
- `cloud_is_anomaly`: Boolean flag van cloud AI detectie
- `cloud_prediction`: Prediction type ('normal' of 'anomaly')

---

### 6.4 MongoDB Atlas

Gebruikt voor:

- JSON opslag
- backups
- Multi-cloud redundantie

---

## 📊 7. Streamlit Dashboard

**Versie:** 1.29.0+  
**Poort:** 8501  
**Access:** http://raspberrypi-lovepreet:8501

### 7.1 Kernfuncties

**Visualisatie:**

- Real-time metrics met auto-refresh (5-300s instelbaar)
- Gauge charts voor CPU, Memory, Disk, Temperature
- Historische trendgrafieken (1u, 6u, 12u, 24u, 2d, 7d)
- Anomaly score scatter plots (Local AI + Cloud AI)
- **Cloud AI Status Display** - Toont cloud anomaly score en prediction
- CSV/JSON export functionaliteit
- Raw data viewer met filtering

**Device Twin Control (Nieuw!):**

Het dashboard bevat nu **3 configuratiepanels** voor remote device management:

#### 1. Collection Interval

Pas sensor data collectie frequentie aan (5-300 seconden):

```json
{
  "collection_interval_seconds": 30,
  "updated_at": "2025-12-12T15:30:00Z"
}
```

#### 2. AI Model Settings

Enable/disable AI modellen en pas anomaly threshold aan:

```json
{
  "ai_models":
      "anomaly_detection": {
        "enabled": true,
        "thresholds": {
          "cpu_temperature": 90.0,
          "cpu_usage": 90.0,
          "memory_percent": 85.0,
          "disk_percent": 90.0
        }
      }
    },
    "cloud": {"enabled": true}
  }
}
```

**Belangrijke opmerking:** Local AI en Cloud AI kunnen **niet tegelijk actief zijn**. Het dashboard biedt een radio button selector voor AI modus:
- **Local AI** - ONNX/Pickle model op Raspberry Pi
- **Cloud AI** - Azure ML endpoint (werkt alleen met internet connectie)
```

#### 3. Sensor Toggle

Schakel individuele sensors in/uit:

```json
{
  "sensors": {
    "temperature": {"enabled": true},
    "cpu": {"enabled": true},
    "memory": {"enabled": true},
    "disk": {"enabled": true},
    "network": {"enabled": true}
  }
}
```

**Updates worden direct naar IoT Hub Device Twin gestuurd en door de Pi opgepikt.**

### 7.2 Vereiste Dependencies

```python
streamlit>=1.29.0
plotly>=5.18.0
pandas>=2.1.4
azure-iot-hub>=2.6.1  # Voor Device Twin updates
```

**Starten:**

```bash
streamlit run dashboard/dashboard.py --server.address 0.0.0.0 --server.port 8501
```

**Auto-start via deploy script:**

```bash
./deploy_pi.sh  # Start automatisch in background
```

---

## 🛠️ 8. Projectstructuur & Deployment

### 8.1 Deployment Scripts

**Start alle services:**

```bash
./deploy_pi.sh
```

Functionaliteit:

- ✓ Start Docker service
- ✓ Start QuestDB container (met auto-restart)
- ✓ Start Streamlit dashboard (achtergrond)
- ✓ Start main.py monitoring (achtergrond)
- ✓ Test connecties
- ✓ Detecteert Tailscale hostname automatisch
- ✓ Toont lokale én Tailscale URLs
- ✓ Toon URLs, PIDs en toegangspunten

**Stop alle services:**

```bash
./stop_pi.sh
```

Functionaliteit:

- ✓ Stop main.py gracefully
- ✓ Stop Streamlit dashboard
- ✓ Stop QuestDB container
- ✓ Verificatie van shutdown

**Logs:**

- Dashboard: `logs/dashboard.log`
- Main App: `logs/main.log`

---

### 8.1.1 Tailscale VPN Netwerk

**Geïnstalleerd op 3 devices:**

1. **Raspberry Pi 4** - IoT monitoring device (raspberrypi-lovepreet)
2. **Laptop** - Development & testing
3. **Desktop Workstation** - Primary development machine

**Voordelen:**

- ✓ Alle 3 devices zijn pingable en toegankelijk
- ✓ Veilige verbinding zonder port forwarding
- ✓ Remote toegang tot Pi dashboard en QuestDB
- ✓ MagicDNS voor hostname-based toegang
- ✓ Automatisch start bij boot via systemd (enabled)
- ✓ Tailnet domain: tail815165.ts.net

**Toegang via Tailscale:**

```bash
# Ping Raspberry Pi via Tailscale
ping raspberrypi-lovepreet

# SSH via Tailscale (short name)
ssh admin@raspberrypi-lovepreet

# SSH via Tailscale (full domain)
ssh admin@raspberrypi-lovepreet.tail815165.ts.net

# Dashboard toegang (short name)
http://raspberrypi-lovepreet:8501

# Dashboard toegang (full domain)
http://raspberrypi-lovepreet.tail815165.ts.net:8501

# QuestDB UI
http://raspberrypi-lovepreet:9000
http://raspberrypi-lovepreet.tail815165.ts.net:9000
```

**Systemd Service:**

Tailscale draait als systemd service en start automatisch bij boot:

```bash
# Status controleren
sudo systemctl status tailscaled

# Output toont:
# Loaded: enabled; preset: enabled
# Active: active (running)
# Status: "Connected; LovepreetSinghGhuman@github; 100.95.69.78"
```

**Belangrijke opmerking:** `tailscale up` is alleen nodig voor initiële authenticatie. De service en verbinding blijven bestaan na reboot.

---

### 8.2 Projectstructuur

```plaintext
piNetMon/
├── config/
│   ├── config.json              # Runtime configuratie
│   └── config.json.example      # Template
├── data/
│   └── questdb/                 # QuestDB Docker volume
├── logs/                        # Application logs
│   ├── main.log
│   └── dashboard.log
├── models/
│   ├── model.pkl                # Scikit-learn model (pickle)
│   ├── scaler.pkl               # StandardScaler (pickle)
│   ├── model.onnx               # ONNX optimized model
│   └── scaler.onnx              # ONNX optimized scaler
├── src/
│   ├── main.py                  # Main orchestrator
│   ├── sensor_collector.py      # System metrics collection
│   ├── questdb_storage.py       # QuestDB time-series storage
│   ├── mongodb_storage.py       # MongoDB Atlas integration
│   ├── ai_models.py             # Unified AI (ONNX + pickle + cloud)
│   └── cloud_integration.py     # Azure IoT Hub client
├── dashboard/
│   └── dashboard.py             # Streamlit dashboard + Device Twin control
├── azure-functions/
│   └── IoTHubTrigger/
│       ├── __init__.py
│       └── function.json
├── azure-ml/
│   ├── conda_env.yml            # Python 3.11 environment
│   ├── deploy_to_azure.py       # Model deployment script
│   └── score.py                 # Azure ML inference endpoint
├── deploy_pi.sh                 # Start services (Tailscale aware)
├── stop_pi.sh                   # Stop services gracefully
└── requirements.txt             # Python dependencies + ONNX
```

**Key Dependencies:**

```txt
# Core
psutil>=5.9.6
numpy>=1.26.0
scikit-learn>=1.3.2

# ONNX Runtime
onnxruntime>=1.16.0
skl2onnx>=1.16.0

# Azure
azure-iot-device>=2.13.0
azure-iot-hub>=2.6.1

# Dashboard
streamlit>=1.29.0
plotly>=5.18.0
pandas>=2.1.4

# Storage
pymongo[srv]>=4.6.1
requests>=2.31.0
```

---

## � 9. Troubleshooting & Known Issues

### 9.1 Cloud AI Integration

**Issue:** Dashboard toont "Waiting..." voor cloud AI scores

**Diagnose stappen:**
1. Controleer of cloud AI enabled is in Device Twin
2. Verifieer Azure ML endpoint bereikbaar is (kan DNS issues hebben op Pi)
3. Check `logs/monitor.log` voor Cloud AI errors

**Veelvoorkomende errors:**

```bash
# DNS resolution failure (tijdelijke network issues)
ERROR:ai_models:Cloud AI error: Failed to resolve 'pi-anomaly-endpoint.westeurope.inference.ml.azure.com'

# QuestDB save failures door verkeerde string formatting
ERROR:questdb_storage:QuestDB save failed: 400 - failed to parse line protocol
```

**Oplossing:**
- Cloud AI vereist stabiele internet connectie
- Bij DNS failures: wacht enkele seconden, Azure ML retry gebeurt automatisch
- String escaping is gefixt in versie 3.1 (`cloud_prediction` wordt correct ge-escaped)

### 9.2 QuestDB Write Issues

**Symptoom:** Data wordt niet opgeslagen, maar QuestDB draait wel

**Root cause:** InfluxDB line protocol vereist correcte string escaping

**Fix (geïmplementeerd in v3.1):**
```python
# String velden moeten dubbele quotes hebben, niet enkele
fields["cloud_prediction"] = f'"{escaped_prediction}"'  # Correct
# fields["cloud_prediction"] = f"'{cloud_prediction}'"  # FOUT - veroorzaakt 400 error
```

### 9.3 Module Reloading

**Issue:** Code updates worden niet direct actief na rsync

**Oplossing:** Gebruik `deploy_pi.sh` voor volledige herstart:
```bash
./deploy_pi.sh  # Herstart alle services en herlaadt modules
```

**Waarom:** Python cached geïmporteerde modules. Een simpele process kill is niet voldoende - gebruik deployment script voor clean restart.

---

## 🔒 10. Security & Best Practices

- Connection strings niet committen
- Gebruik .env of Azure Key Vault
- IoT Hub gebruikt SAS Tokens (roteer regelmatig)
- Azure ML endpoint gebruikt API Keys (vernieuw maandelijks)
- MongoDB connection strings bevatten credentials
- Tailscale VPN voor veilige remote toegang (geen port forwarding nodig)

---

## 🎯 11. Checklist Eindopdracht

**Minimumvereisten:**

- ✔ Raspberry Pi monitort systeemdata
- ✔ Lokale opslag (QuestDB + SQLite fallback)
- ✔ Cloud opslag (IoT Hub + MongoDB)
- ✔ Edge AI (Isolation Forest + Threshold)
- ✔ Cloud AI (Azure ML)
- ✔ Dashboard
- ✔ Remote configuratie
- ✔ Documentatie

**Bonus Features:**

- ✔ Azure Functions
- ✔ QuestDB (Docker + Cloud)
- ✔ MongoDB Atlas
- ✔ Direct Methods
- ✔ Device Twin met dashboard control
- ✔ Async I/O
- ✔ Dockerized QuestDB met auto-restart
- ✔ Unified AI module (ONNX + pickle dual export)
- ✔ ONNX Runtime voor 2-3x snellere inferencing
- ✔ Deployment automation met Tailscale support
- ✔ Real data training (374+ samples)
- ✔ QuestDB connection optimalisatie
- ✔ Tailscale VPN met MagicDNS (3 devices, auto-start via systemd)
- ✔ Device Twin remote configuratie via dashboard
- ✔ Cloud AI volledige integratie met QuestDB opslag (v3.1)
- ✔ Dashboard toggle tussen Local/Cloud AI (v3.1)
- ✔ InfluxDB line protocol correcte string escaping (v3.1)
- ✔ Azure ML JSON response parsing (v3.1)

---

## 🧾 12. Conclusie

Dit platform combineert edge computing, cloud scalability, real-time analytics, en machine learning in één geïntegreerd IoT-systeem met moderne optimalisaties.

### Kerncomponenten

**AI & ML:**

- Unified AI module (`ai_models.py`) met **ONNX-optimalisatie**
- Dual-format model export (ONNX + pickle)
- 2-3x snellere edge inference
- Cloud AI via Azure ML (Python 3.11 runtime)

**Data & Storage:**

- QuestDB time-series opslag (Docker met auto-restart)
- MongoDB Atlas voor redundantie
- 374+ real sensor samples voor training

**Dashboard & Control:**

- Streamlit dashboard met real-time visualisatie
- **Device Twin configuratie** vanuit dashboard
- Remote sensor enable/disable
- **AI model runtime toggle** - Local vs Cloud AI (exclusief)
- Cloud AI status display met anomaly score & prediction
- Threshold aanpassing voor local AI

**Infrastructuur:**

- Azure serverless verwerking (IoT Hub + Functions)
- Deployment automation met `deploy_pi.sh` en `stop_pi.sh`
- Tailscale VPN voor veilige remote toegang
- Systemd auto-start voor alle services

### Technische Prestaties

**Inferencing:**

- ONNX: ~1-2ms per prediction
- Pickle fallback: ~3-5ms per prediction
- Model size: 35% reductie met ONNX

**Data Processing:**

- QuestDB: 15-20s timeout optimalisati
- **Cloud AI data opslag** met correct string escaping
- Dual AI score tracking (local + cloud in dezelfde tabel)e
- Time-series partitioning per dag
- Miljoenen rows/sec ingestie capacity

**Deployment:**

- Graceful shutdown & startup scripts
- Background process management
- Comprehensive logging (main + dashboard)
- Tailscale hostname auto-detection

**Remote Management:**

- Device Twin updates via dashboard
- **AI model runtime switching** (Local ↔ Cloud)
- Real-time AI mode status indicator
- Cloud AI prediction tracking in QuestDBuratie
- Sensor enable/disable toggle
- AI model runtime switching

---

### Tech Stack Overzicht

| Component | Technologie |
|-----------|-------------|
| **Edge Device** | Raspberry Pi 4 |
| **OS** | Raspberry Pi OS (Debian) |
| **Runtime** | Python 3.13 (local), Python 3.11 (Azure ML) |
| **AI Framework** | scikit-learn 1.8.0 |
| **Inference** | ONNX Runtime 1.16.0+ |
| **Time-Series DB** | QuestDB (Docker) |
| **Cloud DB** | MongoDB Atlas |
| **Dashboard** | Streamlit 1.29.0 |
| **Cloud Platform** | Microsoft Azure |
| **IoT Protocol** | Azure IoT Hub (MQTT/AMQP) |
| **ML Deployment** | Azure ML Managed Endpoints |
| **Networking** | Tailscale VPN (MagicDNS) |
| **Containerization** | Docker |
| **Orchestration** | Bash scripts + systemd |

---

### Health Score Berekening

```python
score = 100
score -= cpu_usage * 0.3
score -= memory_usage * 0.25
score -= disk_usage * 0.25
score -= (cpu_temperature / 100) * 20
score = max(0, min(100, score))
```

---
