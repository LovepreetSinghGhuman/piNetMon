# QuestDB Setup Guide

## Overview

This project uses QuestDB for local time-series storage of IoT sensor data. QuestDB is optimized for high-performance time-series analytics.

## Installation Options

### Option 1: Docker (Recommended)

**Prerequisites:** Docker installed

```bash
# Run QuestDB container
docker run -d \
  --name questdb \
  -p 9000:9000 \
  -p 9009:9009 \
  -p 8812:8812 \
  -v $(pwd)/questdb-data:/var/lib/questdb \
  questdb/questdb

# Verify it's running
docker ps | grep questdb

# View logs
docker logs questdb
```

**Ports:**
- `9000` - HTTP/Web Console
- `9009` - InfluxDB Line Protocol (high-performance ingestion)
- `8812` - PostgreSQL wire protocol

### Option 2: Binary Installation

**Linux/macOS:**
```bash
# Download latest release
wget https://github.com/questdb/questdb/releases/download/7.3.10/questdb-7.3.10-rt-linux-amd64.tar.gz

# Extract
tar -xzf questdb-7.3.10-rt-linux-amd64.tar.gz

# Run
cd questdb-7.3.10-rt-linux-amd64
./questdb.sh start
```

**Raspberry Pi (ARM):**
```bash
# Download ARM release
wget https://github.com/questdb/questdb/releases/download/7.3.10/questdb-7.3.10-rt-linux-arm64.tar.gz

# Extract and run
tar -xzf questdb-7.3.10-rt-linux-arm64.tar.gz
cd questdb-7.3.10-rt-linux-arm64
./questdb.sh start
```

## Configuration

Update `config/config.json`:

```json
{
  "questdb": {
    "host": "localhost",
    "port": 9000
  }
}
```

For remote QuestDB (e.g., Azure Container Instance):
```json
{
  "questdb": {
    "host": "questdb-instance.azurecontainer.io",
    "port": 9000
  }
}
```

## Web Console

Access the QuestDB web console at: **http://localhost:9000**

Features:
- SQL query interface
- Real-time data visualization
- Schema browser
- Query performance monitoring

## Table Schema

The application automatically creates data with this structure:

```sql
-- Measurement: sensor_data
-- Tags: device_id
-- Fields: 
--   cpu_temperature, cpu_usage, cpu_frequency
--   memory_total_mb, memory_used_mb, memory_percent
--   disk_total_gb, disk_used_gb, disk_percent
--   network_sent_mb, network_recv_mb
--   anomaly_score, is_anomaly
-- Timestamp: automatic
```

## Sample Queries

**View recent data:**
```sql
SELECT * FROM sensor_data 
WHERE timestamp > dateadd('h', -1, now())
ORDER BY timestamp DESC 
LIMIT 100;
```

**Get anomalies:**
```sql
SELECT * FROM sensor_data 
WHERE is_anomaly = true
AND timestamp > dateadd('h', -24, now())
ORDER BY timestamp DESC;
```

**Average metrics per hour:**
```sql
SELECT 
  timestamp,
  avg(cpu_temperature) as avg_cpu_temp,
  avg(cpu_usage) as avg_cpu_usage,
  avg(memory_percent) as avg_memory
FROM sensor_data
WHERE timestamp > dateadd('d', -7, now())
SAMPLE BY 1h
ORDER BY timestamp DESC;
```

**CPU temperature trends:**
```sql
SELECT 
  timestamp,
  cpu_temperature,
  avg(cpu_temperature) OVER (ORDER BY timestamp ROWS BETWEEN 10 PRECEDING AND CURRENT ROW) as moving_avg
FROM sensor_data
WHERE timestamp > dateadd('h', -24, now())
ORDER BY timestamp;
```

## Data Retention

QuestDB uses partitioning for efficient data management:

```sql
-- Create partitioned table (if needed manually)
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

**Drop old partitions:**
```sql
-- Drop partitions older than 30 days
ALTER TABLE sensor_data DROP PARTITION 
WHERE timestamp < dateadd('d', -30, now());
```

## Performance Tips

1. **Use InfluxDB Line Protocol** for ingestion (port 9009) - fastest method
2. **Sample queries** for large datasets: `SAMPLE BY 1h` for hourly aggregates
3. **Partition by day/month** for large data volumes
4. **Create indexes** on frequently queried columns (device_id is already indexed as SYMBOL)

## Monitoring

**Check table size:**
```sql
SELECT count(*) as total_records FROM sensor_data;
```

**Check data rate:**
```sql
SELECT 
  date_trunc('minute', timestamp) as minute,
  count(*) as records_per_minute
FROM sensor_data
WHERE timestamp > dateadd('h', -1, now())
SAMPLE BY 1m;
```

## Backup

**Export data:**
```sql
COPY sensor_data TO '/tmp/sensor_backup.csv';
```

**Docker backup:**
```bash
# Stop container
docker stop questdb

# Backup volume
tar -czf questdb-backup-$(date +%Y%m%d).tar.gz questdb-data/

# Restart
docker start questdb
```

## Deploying to Azure

**Azure Container Instances:**
```bash
az container create \
  --resource-group CFAI \
  --name questdb \
  --image questdb/questdb \
  --ports 9000 9009 8812 \
  --dns-name-label pinetmon-questdb \
  --cpu 1 \
  --memory 2
```

Access at: `pinetmon-questdb.<region>.azurecontainer.io:9000`

## Troubleshooting

**Connection refused:**
- Check if QuestDB is running: `docker ps` or `netstat -tuln | grep 9000`
- Verify firewall rules allow port 9000
- Check logs: `docker logs questdb`

**Performance issues:**
- Monitor query execution time in web console
- Use SAMPLE BY for large datasets
- Check disk I/O with `iostat`

**Data not appearing:**
- Check application logs for write errors
- Verify connection string in config.json
- Test with curl: `curl -G http://localhost:9000/exec --data-urlencode "query=SELECT * FROM sensor_data LIMIT 10"`

## Resources

- [QuestDB Documentation](https://questdb.io/docs/)
- [SQL Reference](https://questdb.io/docs/reference/sql/)
- [Time-Series Functions](https://questdb.io/docs/reference/function/time-series/)
- [Performance Guide](https://questdb.io/docs/guides/performance/)
