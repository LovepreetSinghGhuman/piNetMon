# Raspberry Pi Network Monitoring Platform – Documentatie

**Auteur:** Lovepreet Singh  
**Versie:** 2.0  
**Datum:** 11 december 2025  
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

Het systeem gebruikt een **Unified AI Module** (`ai_models.py`) met drie componenten.

### 4.1 Model Training

**Functie:** `train_and_save_models()`

- Laadt real sensor data uit QuestDB (373+ samples)
- Fallback naar synthetische data bij < 100 samples
- Traint Isolation Forest model
- Slaat `model.pkl` en `scaler.pkl` op

**Training uitvoeren:**

```bash
python3 src/ai_models.py
```

---

### 4.2 Edge AI – Local Isolation Forest

**Class:** `AnomalyDetector`

**Voordelen:**

- Offline beschikbaar
- Geen latency
- Snellere anomaly detection
- Trainbaar met nieuwe data via `train()` method

**Features (6):**

- CPU temperature  
- CPU usage (%)  
- Memory percent  
- Disk percent  
- Network sent MB  
- Network recv MB  

**Model file:** `models/model.pkl`  
**Contamination:** `0.1`  

---

### 4.2 Threshold Fallback Detector

**Class:** `SimpleThresholdDetector`

Wordt gebruikt wanneer:

- Het local model corrupt of ontbreekt
- Te weinig historische data beschikbaar is

**Grenswaarden:**

- CPU temp > **85°C**
- CPU usage > **95%**
- RAM > **90%**
- Disk > **95%**

---

### 4.3 Cloud AI – Azure ML Endpoint

**Class:** `CloudAIService` met `AzureMLClient`

Geavanceerde anomaly analysis via REST API.

**Endpoint:**

`pi-anomaly-endpoint`

**Deployment workflow:**

1. `python3 src/ai_models.py` → Train model lokaal  
2. `python3 azure-ml/deploy_to_azure.py` → Upload & deploy  
3. `score.py` → Inference script in Azure  

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
  timestamp TIMESTAMP
) timestamp(timestamp) PARTITION BY DAY;
```

---

### 6.4 MongoDB Atlas

Gebruikt voor:

- JSON opslag
- backups
- Multi-cloud redundantie

---

## 📊 7. Streamlit Dashboard

**Functies:**

- Realtime metrics
- Gauge visualisaties
- Historische trendgrafieken (1u tot 7d)
- Auto-refresh
- CSV export
- Raw data viewer
- Anomaly overlays

**Starten:**

```bash
streamlit run dashboard/dashboard.py --server.address 0.0.0.0
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
- ✓ Toon URLs en PIDs

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

1. **Raspberry Pi 4** - IoT monitoring device
2. **Laptop** - Development & testing
3. **Desktop Workstation** - Primary development machine

**Voordelen:**

- ✓ Alle 3 devices zijn pingable en toegankelijk
- ✓ Veilige verbinding zonder port forwarding
- ✓ Remote toegang tot Pi dashboard en QuestDB
- ✓ Geïntegreerde DNS voor gemakkelijke device discovery

**Toegang via Tailscale:**

```bash
## Ping Raspberry Pi via Tailscale
ping raspberry-pi-tailscale-name

## SSH via Tailscale
ssh admin@raspberry-pi-tailscale-name

## Dashboard toegang
http://raspberry-pi-tailscale-name:8501
```

---

### 8.2 Projectstructuur

```pgsql
piNetMon/
├── config/
│   ├── config.json
│   └── config.json.example
├── data/
│   └── questdb/              ## QuestDB Docker volume
├── logs/                      ## Application logs
│   ├── main.log
│   └── dashboard.log
├── models/
│   ├── model.pkl             ## Trained Isolation Forest
│   └── scaler.pkl            ## StandardScaler for features
├── src/
│   ├── main.py               ## Main orchestrator
│   ├── sensor_collector.py   ## System metrics collection
│   ├── questdb_storage.py    ## QuestDB time-series storage
│   ├── mongodb_storage.py    # MongoDB Atlas integration
│   ├── ai_models.py          ## Unified AI module (training + local + cloud)
│   └── cloud_integration.py  ## Azure IoT Hub client
├── dashboard/
│   └── dashboard.py          ## Streamlit visualization
├── azure-functions/
│   └── IoTHubTrigger/
│       ├── __init__.py
│       └── function.json
├── azure-ml/
│   ├── deploy_to_azure.py    ## Deploy model to Azure ML
│   └── score.py              ## Azure ML inference script
├── deploy_pi.sh              ## Start all services after reboot
├── stop_pi.sh                ## Stop all services
├── requirements.txt
└── README.md
```

---

## 📄 9. Documentatieversie

- Connection strings niet committen
- Gebruik .env of Azure Key Vault
- IoT Hub gebruikt SAS Tokens
- Azure ML endpoint gebruikt API Keys

---

## 🎯 10. Checklist Eindopdracht

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
- ✔ Device Twin
- ✔ Async I/O
- ✔ Dockerized QuestDB met auto-restart
- ✔ Unified AI module (consolidated codebase)
- ✔ Deployment automation scripts
- ✔ Real data training (373+ samples)
- ✔ QuestDB connection optimalisatie
- ✔ Tailscale VPN voor veilige remote toegang (3 devices)

---

## 🧾 11. Conclusie

Dit platform combineert edge computing, cloud scalability, real-time analytics, en machine learning in één geïntegreerd IoT-systeem.

**Kerncomponenten:**

- Unified AI module (`ai_models.py`) met training, local en cloud inferencing
- QuestDB time-series opslag (Docker met auto-restart)
- Streamlit dashboard voor visualisatie
- Azure serverless verwerking (IoT Hub + Functions)
- MongoDB Atlas voor redundantie
- Deployment automation met `deploy_pi.sh` en `stop_pi.sh`

**Prestaties:**

- 373+ real sensor samples voor model training
- 15-20s QuestDB timeout optimalisatie
- Graceful shutdown & startup scripts
- Background process management
- Comprehensive logging

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
