# Raspberry Pi Network Monitoring Platform – Documentatie

**Auteur:** Lovepreet Singh  
**Versie:** 3.1  
**Datum:** 14 december 2025  

## 🛡️ Troubleshooting & Best Practices

### Veelvoorkomende issues

- **Cloud AI 'Waiting...':** Check Device Twin config, Azure ML endpoint bereikbaarheid, logs/monitor.log. Oplossing: stabiele internetverbinding, retry logic, string escaping gefixt in v3.1.
- **QuestDB write errors:** Foutieve string escaping. Oplossing: dubbele quotes voor stringvelden (v3.1).
- **Code updates niet actief:** Gebruik altijd `deploy_pi.sh` voor een volledige herstart.

### Security

- Commit nooit secrets of connection strings
- Gebruik .env of Azure Key Vault
- Roteer SAS tokens/API keys regelmatig
- Tailscale VPN voor veilige remote toegang

---

## ✅ Eindopdracht Checklist

**Minimum:**

- Raspberry Pi monitort systeemdata
- Lokale opslag (QuestDB)
- Cloud opslag (IoT Hub, MongoDB)
- Edge AI (Isolation Forest + Threshold)
- Cloud AI (Azure ML)
- Dashboard
- Remote configuratie
- Documentatie

**Bonus:**

- Azure Functions, QuestDB Cloud, MongoDB Atlas
- Direct Methods, Device Twin, Async I/O
- Dockerized QuestDB, ONNX Runtime, Tailscale VPN
- Deployment automation, real data training, dual AI score tracking

---

## 🧾 Conclusie

Dit platform combineert edge computing, cloud scalability, real-time analytics en machine learning in één geïntegreerd IoT-systeem. Alle onderdelen zijn modulair, schaalbaar en veilig opgezet, met moderne optimalisaties voor performance en beheer.

---

### Tailscale VPN

- 3 devices: Pi, laptop, desktop
- MagicDNS, hostname-based toegang, systemd auto-start
- Toegang: ssh, dashboard, QuestDB via Tailscale hostname

### Projectstructuur

Zie codeblok voor overzicht van alle directories, scripts en modellen.

---

## 📡 Architectuur

```
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ Raspberry Pi  │──→──▶ Azure IoT Hub │──→──▶ Azure Function │
└──────┬────────┘      └──────┬────────┘      └──────┬────────┘
       │ Telemetry (JSON)     │ Trigger             │ Process/Store
       ▼                      ▼                     ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ QuestDB │ MongoDB Atlas │ Azure Blob │ Azure ML Endpoint    │
   └──────────────────────────────────────────────────────────────┘
       │
       ▼
   ┌──────────────────────┐
   │ Streamlit Dashboard  │
   └──────────────────────┘
```

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
