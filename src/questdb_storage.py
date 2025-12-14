"""
QuestDB Storage Module
Uses config.json for host and port settings.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import requests
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
CONFIG_PATH = Path(__file__).parent.parent / "config/config.json"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    CONFIG = json.load(f)

QUESTDB_CONF = CONFIG.get("questdb", {})
QUESTDB_HOST = QUESTDB_CONF.get("host", "localhost")
QUESTDB_PORT = QUESTDB_CONF.get("port", 9000)


class QuestDBStorage:
    """QuestDB storage using config.json settings."""

    TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS sensor_data (
            device_id SYMBOL,
            cpu_temperature DOUBLE,
            cpu_usage_percent DOUBLE,
            cpu_frequency_mhz DOUBLE,
            cpu_core_count DOUBLE,
            memory_total_mb DOUBLE,
            memory_available_mb DOUBLE,
            memory_percent DOUBLE,
            disk_total_gb DOUBLE,
            disk_used_gb DOUBLE,
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
    """

    def __init__(self):
        self.write_url = f"http://{QUESTDB_HOST}:{QUESTDB_PORT}/write"
        self.query_url = f"http://{QUESTDB_HOST}:{QUESTDB_PORT}/exec"
        self._ensure_table_exists()
        logger.info(f"QuestDBStorage initialized: {QUESTDB_HOST}:{QUESTDB_PORT}")

    def _request(self, sql: str, method: str = "get", timeout: int = 10) -> Optional[requests.Response]:
        try:
            if method.lower() == "post":
                logger.debug(f"POST to {self.write_url}: {sql[:200]}")
                response = requests.post(self.write_url, data=sql, timeout=timeout)
                logger.debug(f"POST response: {response.status_code}")
                return response
            response = requests.get(self.query_url, params={"query": sql}, timeout=timeout)
            return response
        except requests.exceptions.Timeout as e:
            logger.error(f"QuestDB request timeout after {timeout}s: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"QuestDB connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"QuestDB request failed: {e}")
            return None

    def _ensure_table_exists(self):
        response = self._request("SELECT 1")
        if not response or response.status_code != 200:
            logger.info("Creating table 'sensor_data'")
            self._request(self.TABLE_SQL)

    def save_sensor_data(self, data: Dict[str, Any], anomaly_score: Optional[float] = None,
                         is_anomaly: bool = False, cloud_anomaly_score: Optional[float] = None,
                         cloud_is_anomaly: bool = False, cloud_prediction: Optional[str] = None) -> bool:
        try:
            device_id = data.get("device_id", "unknown")
            fields = {}

            # Map CPU fields
            cpu = data.get("cpu", {})
            if cpu.get("temperature") is not None:
                fields["cpu_temperature"] = cpu["temperature"]
            if cpu.get("usage_percent") is not None:
                fields["cpu_usage_percent"] = cpu["usage_percent"]
            if cpu.get("frequency_mhz") is not None:
                fields["cpu_frequency_mhz"] = cpu["frequency_mhz"]
            if cpu.get("core_count") is not None:
                fields["cpu_core_count"] = cpu["core_count"]

            # Map Memory fields
            memory = data.get("memory", {})
            if memory.get("total_mb") is not None:
                fields["memory_total_mb"] = memory["total_mb"]
            if memory.get("available_mb") is not None:
                fields["memory_available_mb"] = memory["available_mb"]
            if memory.get("percent") is not None:
                fields["memory_percent"] = memory["percent"]

            # Map Disk fields
            disk = data.get("disk", {})
            if disk.get("total_gb") is not None:
                fields["disk_total_gb"] = disk["total_gb"]
            if disk.get("used_gb") is not None:
                fields["disk_used_gb"] = disk["used_gb"]
            if disk.get("percent") is not None:
                fields["disk_percent"] = disk["percent"]

            # Map Network fields
            network = data.get("network", {})
            if network.get("bytes_sent_mb") is not None:
                fields["network_sent_mb"] = network["bytes_sent_mb"]
            if network.get("bytes_recv_mb") is not None:
                fields["network_recv_mb"] = network["bytes_recv_mb"]

            # Add anomaly fields
            if anomaly_score is not None:
                fields["anomaly_score"] = anomaly_score
            fields["is_anomaly"] = str(is_anomaly).lower()
            
            # Add cloud AI fields
            if cloud_anomaly_score is not None:
                fields["cloud_anomaly_score"] = cloud_anomaly_score
            fields["cloud_is_anomaly"] = str(cloud_is_anomaly).lower()
            if cloud_prediction:
                # Escape quotes in the prediction string and wrap in double quotes for InfluxDB line protocol
                escaped_prediction = str(cloud_prediction).replace('"', '\\"').replace("'", "\\'")
                fields["cloud_prediction"] = f'"{escaped_prediction}"'

            line = f"sensor_data,device_id={device_id} " + ",".join(f"{k}={v}" for k, v in fields.items())
            resp = self._request(line, method="post", timeout=5)
            if resp is not None and resp.status_code in [200, 204]:
                logger.debug(f"Data saved to QuestDB successfully")
                return True
            else:
                status = resp.status_code if resp else "No response"
                text = resp.text[:200] if resp else "Connection failed"
                logger.error(f"QuestDB save failed: {status} - {text}")
                logger.debug(f"Failed line: {line[:200]}")
                return False
        except Exception as e:
            logger.error(f"Failed to save data: {e}")
            return False

    def query(self, sql: str) -> Optional[Dict[str, Any]]:
        resp = self._request(sql)
        if resp and resp.status_code == 200:
            return resp.json()
        if resp:
            logger.error(f"Query failed: {resp.status_code} - {resp.text}")
        return None

    def get_recent_data(self, hours: int = 24) -> Dict[str, Any]:
        sql = f"SELECT * FROM sensor_data WHERE timestamp > dateadd('h', -{hours}, now()) ORDER BY timestamp DESC"
        return self.query(sql) or {"dataset": [], "count": 0}

    def get_anomalies(self, hours: int = 24) -> Optional[Dict[str, Any]]:
        sql = f"SELECT * FROM sensor_data WHERE timestamp > dateadd('h', -{hours}, now()) AND is_anomaly = true ORDER BY timestamp DESC"
        return self.query(sql)

    def get_statistics(self) -> Dict[str, Any]:
        sql = """
            SELECT 
                count(*) as total_records,
                sum(CASE WHEN is_anomaly = true THEN 1 ELSE 0 END) as anomaly_count,
                min(timestamp) as oldest_record,
                max(timestamp) as newest_record,
                avg(cpu_temperature) as avg_cpu_temp,
                avg(cpu_usage_percent) as avg_cpu_usage,
                avg(memory_percent) as avg_memory_usage
            FROM sensor_data
        """
        return self.query(sql) or {
            "dataset": [],
            "count": 0,
            "columns": [
                "total_records",
                "anomaly_count",
                "oldest_record",
                "newest_record",
                "avg_cpu_temp",
                "avg_cpu_usage",
                "avg_memory_usage"
            ]
        }


if __name__ == "__main__":
    storage = QuestDBStorage()
    test_data = {
        "timestamp": datetime.now().isoformat(),
        "device_id": "raspberry-pi-monitor",
        "cpu": {"temperature": 45.3, "usage_percent": 25.5, "frequency_mhz": 1500.0},
        "memory": {"total_mb": 1024, "used_mb": 512, "percent": 50.0},
        "disk": {"total_gb": 128, "used_gb": 64, "percent": 50.0},
        "network": {"bytes_sent_mb": 100.5, "bytes_recv_mb": 250.3}
    }
    success = storage.save_sensor_data(test_data, anomaly_score=0.15)
    print(f"Data save {'successful' if success else 'failed'}")
    print(storage.get_statistics())