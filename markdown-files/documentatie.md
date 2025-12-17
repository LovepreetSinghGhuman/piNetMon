# Documentatie – IoT Eindopdracht (Howest MTS5 - TI - Cloud Computing for AI)

## Inleiding

Dit project is een IoT-oplossing ontwikkeld voor de Raspberry Pi 4 Model B (1GB RAM) als onderdeel van de eindopdracht voor het vak Cloud Computing for AI aan Howest. Het systeem monitort sensordata, verwerkt deze lokaal en in de cloud, en visualiseert alles via een Streamlit-dashboard.

## Architectuur

Hieronder vind je een overzicht van de architectuur van het systeem:

```text
// Architectuurdiagram
+----------------+      +---------------+      +-----------------+
|  Raspberry Pi  | ---> |  Azure IoT Hub| ---> |  Azure Function |
+----------------+      +---------------+      +-----------------+
      | Telemetry (JSON)     | Trigger           | Process/Store
      v                      v                    v
+---------------------------------------------------------------+
| QuestDB | MongoDB Atlas | Azure Blob | Azure ML Endpoint      |
+---------------------------------------------------------------+
      |
      v
+----------------------+
| Streamlit Dashboard  |
+----------------------+
```  

## Hoofdcomponenten en Werking

### 1a. Offline werking & automatische synchronisatie

Indien de Raspberry Pi tijdelijk geen wifi- of internetverbinding heeft, blijft het systeem gewoon lokaal data verzamelen en opslaan in QuestDB (en MongoDB indien geconfigureerd). De cloudconnectie (Azure IoT Hub) wordt automatisch hervat zodra de verbinding terug is:

- **Lokale opslag:** Sensor- en netwerkscandata worden altijd lokaal opgeslagen, ongeacht de internetverbinding.
- **Cloud synchronisatie:** Tijdens een onderbreking worden berichten aan Azure IoT Hub tijdelijk in een wachtrij geplaatst (tot een limiet). Zodra de verbinding hersteld is, worden deze berichten automatisch doorgestuurd naar de cloud.
- **Databehoud:** Zo gaat er geen lokale data verloren bij tijdelijke netwerkproblemen. Enkel als de wachtrij volloopt, kunnen berichten verloren gaan.

### 1. Raspberry Pi & Sensoren & Netwerkscan

De Raspberry Pi 4 B draait het hoofdprogramma (`src/main.py`) en verzamelt periodiek data van verschillende sensoren:

- **CPU-temperatuur, -gebruik, -frequentie**
- **Geheugen- en schijfgebruik**
- **Netwerkverkeer**
- **Netwerkscan: detectie van alle actieve apparaten op het lokale netwerk**

De `SensorCollector` module leest deze waarden uit het systeem en structureert ze als JSON. Voor de netwerkscan wordt het lokale subnet gepingd en worden alle actieve apparaten opgespoord. Per gevonden apparaat worden het IP-adres, MAC-adres en (indien mogelijk) de hostnaam opgeslagen.

### 2. Lokale Opslag (QuestDB)

De sensordata én de resultaten van de netwerkscan worden lokaal opgeslagen in QuestDB, een snelle time-series database. De module `questdb_storage.py` zorgt voor het aanmaken van de juiste tabellen en het wegschrijven van data via HTTP API. Netwerkscan-data wordt als JSON-blok opgeslagen per scanmoment. Hierdoor kan de data lokaal geanalyseerd en bewaard worden, zelfs zonder internetverbinding.

### 3. Lokale AI-modellen

Met de module `ai_models.py` wordt een IsolationForest-model getraind op de sensordata. Dit model wordt geëxporteerd naar ONNX-formaat voor snelle inferentie met ONNX Runtime. De Pi detecteert zo lokaal anomalieën (bv. abnormale temperatuurstijgingen). De drempelwaarde en modelinstellingen zijn configureerbaar in `config/config.json`.

### 4. Cloud Integratie (Azure IoT Hub)

De `cloud_integration.py` module stuurt de sensordata (en AI-resultaten) als JSON-berichten naar Azure IoT Hub. Dit gebeurt veilig en betrouwbaar, met ondersteuning voor device twin updates (remote configuratie).

### 5. Azure Function & Cloud Opslag

Een Azure Function (zie `azure-functions/IoTHubTrigger/`) wordt getriggerd door nieuwe berichten in IoT Hub. Deze functie:

- Verrijkt en verwerkt de data
- Voert optioneel cloudgebaseerde AI-analyse uit via een Azure ML Endpoint (`azure-ml/score.py`)
- Slaat de data op in Azure Blob Storage en/of MongoDB Atlas voor centrale opslag en analyse
- Uploadt ook de resultaten van de netwerkscan (lijst van gevonden apparaten met IP, MAC en naam) als JSON-bestand naar Azure Blob Storage

### 6. Cloud AI-model (Azure ML)

Het cloudmodel wordt getraind en gedeployed via scripts in `azure-ml/`. Zowel ONNX als PKL-modellen worden ondersteund. De Azure ML Endpoint voert inferentie uit op binnenkomende data voor extra anomaliedetectie.

### 7. Streamlit Dashboard

Het dashboard (`dashboard/dashboard.py`) biedt:

- Realtime visualisatie van alle sensordata en AI-resultaten
- Overzicht van anomalieën
- Mogelijkheid tot het aanpassen van instellingen (device twin)
- Toegang tot historische data via QuestDB

### 8. Configuratie

Alle instellingen (sensoren, AI, cloud, opslag, netwerkscan) zijn centraal beheerd in `config/config.json`. Je kan het te scannen subnet en Azure Blob Storage credentials instellen. Dit maakt het systeem flexibel en makkelijk aanpasbaar, zowel lokaal als op afstand via het dashboard of IoT Hub.

### 9. Bestandsstructuur (Belangrijkste onderdelen)

- `src/` – Hoofdcode: sensoren, AI, cloud, opslag
- `dashboard/` – Streamlit dashboard
- `azure-functions/` – Azure Function code voor cloudverwerking
- `azure-ml/` – Scripts voor training en deployment van cloud AI-modellen
- `config/` – Configuratiebestanden
- `requirements.txt` – Alle benodigde Python-pakketten

## Checklist & Eisen (op basis van opdracht.md)

- ✅ Minstens één sensor die data vastlegt (CPU, temperatuur, geheugen, netwerk, ...)
- ✅ Data wordt lokaal opgeslagen (QuestDB)
- ✅ Data wordt doorgestuurd naar de cloud (Azure IoT Hub)
- ✅ Data wordt in de cloud opgeslagen (Azure Blob, MongoDB Atlas)
- ✅ Netwerkscan: actieve apparaten op het lokale netwerk worden periodiek opgespoord en opgeslagen (IP, MAC, naam)
- ✅ Resultaten van netwerkscan worden als JSON geüpload naar Azure Blob Storage
- ✅ Minstens één lokaal AI-model (IsolationForest, ONNX Runtime)
- ✅ Minstens één AI-model in de cloud (Azure ML Endpoint)
- ✅ Gebruiker kan interageren met het IoT-device (Streamlit dashboard, device twin)
- ✅ Configuratie van het toestel kan vanop afstand bekeken en aangepast worden (IoT Hub device twin, dashboard)
- ✅ Dashboard aanwezig (Streamlit)
- ✅ Rapport "documentatie.md" (dit bestand)
- ✅ requirements.txt aanwezig met alle nodige Python-pakketten
- ✅ Raspberry Pi aanwezig in de flow

## Dataflow en Interactie

1. Sensoren verzamelen data én netwerkscan detecteert actieve apparaten → lokaal verwerkt en opgeslagen (QuestDB)
2. Lokale AI detecteert anomalieën → resultaten toegevoegd aan data
3. Data + AI-resultaten + netwerkscan worden via Azure IoT Hub naar de cloud gestuurd
4. Azure Function verwerkt, verrijkt en slaat data en netwerkscan-resultaten op in Azure/MongoDB/Blob
5. Cloud AI-model voert extra analyse uit (optioneel)
6. Streamlit-dashboard toont alles realtime en laat device management toe
7. Configuratie kan zowel lokaal als via de cloud aangepast worden

## Tech Stack & Gebruikte Technologieën

| Component            | Technologie / Service        | Rol / Functie                                               |
|----------------------|------------------------------|-------------------------------------------------------------|
| Sensoren & Netwerkscan| psutil, Python, subprocess, socket | Uitlezen van CPU, geheugen, disk, netwerk, temperatuur, én detectie van actieve apparaten (IP, MAC, naam) |
| Raspberry Pi         | Raspbian OS, Python 3.11+    | Edge device, draait alle lokale code                        |
| Lokale opslag        | QuestDB                      | Time-series database voor sensordata                        |
| Lokale AI            | scikit-learn, ONNX Runtime   | Anomaliedetectie, modeltraining & inferentie                |
| Cloud connectie      | Azure IoT Hub, azure-iot-device | Veilige dataoverdracht naar de cloud                     |
| Cloud verwerking     | Azure Functions (Python)     | Verwerking, verrijking en opslag van data                   |
| Cloud opslag         | Azure Blob Storage, MongoDB Atlas | Centrale opslag van ruwe en verwerkte data             |
| Cloud AI             | Azure ML, ONNX, PKL          | Cloud inferentie, model deployment                          |
| Dashboard            | Streamlit, Plotly, Pandas    | Realtime visualisatie, device management                    |
| Remote Access        | Tailscale                    | Veilige, eenvoudige toegang tot de Pi op afstand            |
| Configuratiebeheer   | JSON, Device Twin (IoT Hub)  | Instellingen lokaal en op afstand beheren                   |
| Overige              | requests, pymongo, skl2onnx  | API-calls, MongoDB integratie, modelconversie               |

### Korte toelichting per technologie

- **psutil**: Leest systeemstatistieken uit op de Pi.
- **subprocess, socket**: Worden gebruikt voor het uitvoeren van de netwerkscan (ping, ARP, reverse DNS/hostname lookup).
- **Azure Blob Storage**: Slaat ruwe sensordata en netwerkscan-resultaten als JSON-bestanden op in de cloud.
- **QuestDB**: Snelle opslag en query van tijdsreeksen, lokaal op de Pi.
- **scikit-learn**: Training van AI-modellen (IsolationForest).
- **ONNX Runtime**: Snelle inferentie van AI-modellen op edge en cloud.
- **azure-iot-device**: Python SDK voor communicatie met Azure IoT Hub.
- **Azure IoT Hub**: Device management, veilige data-ingest.
- **Azure Functions**: Serverless verwerking van binnenkomende berichten.
- **Azure ML**: Training, deployment en inferentie van cloudmodellen.
- **MongoDB Atlas**: Multi-cloud opslag, schaalbaar en flexibel.
- **Streamlit**: Webdashboard voor visualisatie en interactie.
- **Tailscale**: VPN-oplossing voor eenvoudige, veilige remote toegang tot de Raspberry Pi, zonder poort-forwarding.
- **Device Twin**: Synchronisatie van configuratie tussen cloud en device.
- **skl2onnx**: Conversie van scikit-learn modellen naar ONNX-formaat.
- **requests/pymongo**: HTTP- en databasecommunicatie.

## Security & Privacy

Beveiliging en privacy zijn belangrijke aspecten van dit IoT-project. Hieronder een overzicht van de genomen maatregelen:

- **Authenticatie & Autorisatie**
      - Azure IoT Hub vereist device keys voor elke Pi; alleen geregistreerde apparaten kunnen data sturen.
      - Azure Functions en ML Endpoints zijn beveiligd met Azure Active Directory en toegangsrechten.

- **Encryptie**
      - Alle communicatie tussen de Pi en Azure IoT Hub verloopt via TLS/SSL (end-to-end encryptie).
      - Data in Azure Blob Storage en MongoDB Atlas wordt standaard versleuteld opgeslagen.

- **Remote Access (Tailscale)**
      - Tailscale gebruikt WireGuard VPN-technologie voor veilige, end-to-end versleutelde verbindingen.
      - Alleen geautoriseerde gebruikers in het Tailscale-netwerk kunnen de Pi bereiken.

- **Privacy**
      - Er worden enkel technische sensordata en systeemstatistieken verzameld, geen persoonsgegevens.
      - Configuratiebestanden kunnen worden aangepast om dataminimalisatie toe te passen.

Deze maatregelen zorgen ervoor dat data veilig wordt verzonden, opgeslagen en enkel toegankelijk is voor bevoegde gebruikers.

### Integratie-overzicht

- **Edge ↔ Cloud**: Data en AI-resultaten worden via IoT Hub naar de cloud gestuurd. Device Twin zorgt voor tweerichtingsconfiguratie.
- **Cloud ↔ Dashboard**: Dashboard haalt data op uit QuestDB (lokaal) en toont cloudstatussen. Instellingen kunnen via het dashboard worden aangepast en gesynchroniseerd.
- **Remote Access**: Via Tailscale kan de beheerder of docent de Raspberry Pi veilig op afstand bereiken voor beheer, troubleshooting of demonstraties, zonder complexe netwerkinstellingen.

Zie requirements.txt voor een volledig overzicht van alle gebruikte Python-pakketten.

## Opmerkingen

- Het project is ontworpen voor eenvoudige uitrol op een Raspberry Pi 4 B (1GB RAM).
- De code is modulair opgebouwd en makkelijk uitbreidbaar met extra sensoren of AI-modellen.
- Voor meer details, zie de broncode en config-bestanden.

---
