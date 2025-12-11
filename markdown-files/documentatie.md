# Raspberry Pi Network Monitoring Platform – Documentatie

**Auteur:** Lovepreet Singh  
**Versie:** 2.0  
**Datum:** 11 december 2025  
**Project:** HOWEST TIC – CFAI Eindopdracht

---

# 📘 1. Inleiding

Dit project ontwikkelt een **real-time netwerk- en systeemmonitoringplatform** met een **Raspberry Pi** als IoT-device en een moderne **cloud-gebaseerde analytics pipeline** op **Azure**.

Het systeem verzamelt systeemstatistieken, detecteert anomalieën met **Edge AI + Cloud AI**, slaat data op in **QuestDB** en **MongoDB Atlas**, en visualiseert alles in een **Streamlit dashboard**.

Het platform is ontworpen voor:

- Real-time monitoring  
- Anomaly detection  
- Historische analyse  
- Cloud-integratie  
- Schaalbaarheid & betrouwbaarheid (Azure serverless + Azure ML)

---

# 📡 2. Architectuur – High-Level Overzicht


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

# ⚙️ 3. Componentenoverzicht

## 3.1 Raspberry Pi (Edge Device)

| Component                 | Beschrijving |
|--------------------------|--------------|
| **Sensor Collector**     | Leest CPU, RAM, disk, network en CPU-temperatuur uit. |
| **QuestDB (lokaal)**     | Lokaal time-series opslag, draait in Docker container. |
| **Local AI Model**       | Isolation Forest voor lokale anomaliedetectie. |
| **Threshold-fallback**   | Simpele grenswaardedetectie bij model failure. |
| **Azure IoT Client**     | Verzenden van telemetrie + cloud configuratie. |
| **Runtime configuratie** | Updatebaar via IoT Hub Device Twin. |

---

## 3.2 Cloud Componenten

### Azure IoT Hub

- Device-to-Cloud telemetrie
- Cloud-to-Device commands
- Direct Methods
- Device Twin configuratiebeheer

### Azure Functions

- Trigger: IoT Hub events
- Taken:
  - Telemetry parsing
  - Health score berekenen
  - Anomaly detection
  - Opslaan in QuestDB / Blob / MongoDB

### Azure ML (Cloud AI)

- Managed endpoint voor anomaly inferencing
- Isolation Forest model (scikit-learn 1.8.0)
- Key-based authentication

### Datastores

| Service | Functie |
|---------|---------|
| **QuestDB Cloud** | High-performance time-series opslag |
| **MongoDB Atlas** | JSON backups & redundancy |
| **Azure Blob Storage** | Archival & cold storage |

---

# 🤖 4. AI Architectuur

Het systeem gebruikt een **Dual-Model AI Strategie**.

## 4.1 Edge AI – Local Isolation Forest

**Voordelen:**

- Offline beschikbaar
- Geen latency
- Snellere anomaly detection

**Features (6):**

- CPU temperature  
- CPU usage (%)  
- Memory percent  
- Disk percent  
- Network sent MB  
- Network recv MB  

**Model file:** `models/local-model.pkl`  
**Contamination:** `0.1`  

---

## 4.2 Threshold Fallback Detector

Wordt gebruikt wanneer:

- Het local model corrupt of ontbreekt
- Te weinig historische data beschikbaar is

**Grenswaarden:**
- CPU temp > **85°C**
- CPU usage > **95%**
- RAM > **90%**
- Disk > **95%**

---

## 4.3 Cloud AI – Azure ML Endpoint

Geavanceerde anomaly analysis via REST API.

**Endpoint:**  
`pi-anomaly-endpoint`

**Deployment workflow:**
1. `train_model.py` → Train Isolation Forest  
2. `deploy_to_azure.py` → Upload & deploy  
3. `score.py` → Inference script  

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

# 🗄️ 5. Datastromen

Pi → IoT Hub → Azure Function → QuestDB / Blob / MongoDB
Pi → Azure ML (AI inferencing)
Pi → Streamlit Dashboard

---

# 🌐 6. Azure Integratie

## 6.1 IoT Hub

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

## 6.2 Azure Functions

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

## 6.3 QuestDB

**Voordelen:**

- Miljoenen rows/sec ingestie
- Time-series optimalisaties
- SQL compatibel

**Tabelstructuur:**

```sql
CREATE TABLE telemetry (
  device_id SYMBOL,
  cpu_temperature DOUBLE,
  cpu_usage DOUBLE,
  memory_usage DOUBLE,
  disk_usage DOUBLE,
  network_sent_mb DOUBLE,
  network_recv_mb DOUBLE,
  health_score INT,
  is_anomaly BOOLEAN,
  anomaly_score DOUBLE,
  timestamp TIMESTAMP
) timestamp(timestamp) PARTITION BY DAY;
```

---

## 6.3 MongoDB Atlas

Gebruikt voor:

- JSON opslag
- backups
- Multi-cloud redundantie

---

# 📊 7. Streamlit Dashboard

**Functies:**

- Realtime metrics
- Gauge visualisaties
- Historische trendgrafieken (1u tot 7d)
- Auto-refresh
- CSV export
- Raw data viewer
- Anomaly overlays

---

# 🛠️ 8. Projectstructuur

```pgsql
piNetMon/
├── config/
│   └── config.json
├── data/
│   ├── questdb/
│   ├── sensor_data.db
│   └── json/
├── models/
│   ├── local-model.pkl
│   ├── model.pkl
│   └── scaler.pkl
├── src/
│   ├── main.py
│   ├── sensor_collector.py
│   ├── questdb_storage.py
│   ├── local_storage.py
│   ├── mongodb_storage.py
│   ├── local_ai_model.py
│   ├── cloud_ai_model.py
│   └── cloud_integration.py
├── dashboard/
│   └── dashboard.py
├── azure-functions/
│   └── IoTHubTrigger/
│       ├── __init__.py
│       └── function.json
├── azure-ml/
│   ├── train_model.py
│   ├── deploy_to_azure.py
│   └── score.py
├── requirements.txt
└── README.md
```

---

# 📄 9. Documentatieversie

- Connection strings niet committen
- Gebruik .env of Azure Key Vault
- IoT Hub gebruikt SAS Tokens
- Azure ML endpoint gebruikt API Keys

---

# 🎯 10. Checklist Eindopdracht

**Minimumvereisten**

- ✔ Raspberry Pi monitort systeemdata
- ✔ Lokale opslag (QuestDB + SQLite fallback)
- ✔ Cloud opslag (IoT Hub + MongoDB)
- ✔ Edge AI (Isolation Forest + Threshold)
- ✔ Cloud AI (Azure ML)
- ✔ Dashboard
- ✔ Remote configuratie
- ✔ Documentatie

**Bonus Features**

- ✔ Azure Functions
- ✔ QuestDB (Docker + Cloud)
- ✔ MongoDB Atlas
- ✔ Direct Methods
- ✔ Device Twin
- ✔ Async I/O
- ✔ Dockerized QuestDB
- ✔ Dual AI strategie

---

# 🧾 11. Conclusie

Dit platform combineert edge computing, cloud scalability, real-time analytics, en machine learning in één geïntegreerd IoT-systeem.

Met:

- Lokale anomaly detection
- Cloud-based AI
- QuestDB time-series opslag
- Streamlit dashboard
- Azure serverless verwerking

---

### Health score berekening:

```python
score = 100
score -= cpu_usage * 0.3
score -= memory_usage * 0.25
score -= disk_usage * 0.25
score -= (cpu_temperature / 100) * 20
score = max(0, min(100, score))
```

---
