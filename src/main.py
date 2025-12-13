"""
Main Application – Raspberry Pi Network Monitor
"""

import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from typing import Dict, Any
import logging

# Add src/ to path
sys.path.insert(0, os.path.dirname(__file__))

# Local modules
from sensor_collector import SensorCollector
from questdb_storage import QuestDBStorage
from ai_models import AnomalyDetector, SimpleThresholdDetector, CloudAIService
from cloud_integration import AzureIoTClient, CloudDataManager
from mongodb_storage import MongoDBStorage

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PiNetworkMonitor")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def safe_get(d: dict, *path, default=None):
    """Safe nested dict get."""
    for p in path:
        if d is None or p not in d:
            return default
        d = d[p]
    return d


# -------------------------------------------------------------------
# Main Application Class
# -------------------------------------------------------------------

class PiNetworkMonitor:
    def __init__(self, config_path: str = None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path or os.path.join(script_dir, "..", "config", "config.json")
        self.config = self._load_config()
        self.running = False

        # --- Sensors ---
        sensor_cfg = self.config.get("sensors", {})
        enabled = {k: safe_get(sensor_cfg, k, "enabled", default=True) for k in sensor_cfg}
        self.sensor_collector = SensorCollector(enabled)

        # --- Storage ---
        qcfg = self.config.get("questdb", {})
        self.local_storage = QuestDBStorage(
            host=qcfg.get("host", "localhost"), port=qcfg.get("port", 9000)
        )

        # --- AI ---
        self.threshold_detector = SimpleThresholdDetector()
        self.ml_detector = AnomalyDetector()

        self.local_ai_enabled = safe_get(self.config, "ai_models", "local", "anomaly_detection",
                                         "enabled", default=True)
        self.cloud_ai_enabled = safe_get(self.config, "ai_models", "cloud", "enabled", default=False)
        self.anomaly_threshold = safe_get(self.config, "ai_models", "local",
                                          "anomaly_detection", "threshold", default=0.8)

        # --- Cloud ---
        self.iot_client = None
        self.cloud_manager = None
        self.cloud_ai_service = None
        self.mongodb_storage = None

        # --- Stats ---
        self.stats = {
            "total_readings": 0,
            "anomalies_detected": 0,
            "cloud_uploads": 0,
            "failed_uploads": 0,
            "start_time": datetime.now().isoformat()
        }

        logger.info("PiNetworkMonitor initialized.")

    # ---------------------------------------------------------------
    # Config
    # ---------------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path) as f:
                cfg = json.load(f)
            logger.info(f"Loaded config: {self.config_path}")
            return cfg
        except Exception as e:
            logger.error(f"Config load failed: {e}")
            raise

    def _save_config(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving config: {e}")

    # ---------------------------------------------------------------
    # CLOUD INITIALIZATION
    # ---------------------------------------------------------------

    async def initialize_cloud(self):
        try:
            conn_str = safe_get(self.config, "azure", "iot_hub", "connection_string")
            self.iot_client = AzureIoTClient(conn_str)
            await self.iot_client.connect()

            self.cloud_manager = CloudDataManager(self.iot_client)
            self.cloud_ai_service = CloudAIService.from_config(self.config)

            # Handlers
            self.iot_client.set_message_handler(self._handle_cloud_message)
            self.iot_client.set_method_handler(self._handle_cloud_method)
            self.iot_client.set_twin_patch_handler(self._handle_twin_patch)

            await self._report_configuration()

            # MongoDB optional
            mcfg = self.config.get("mongodb", {})
            if mcfg.get("enabled", False):
                self.mongodb_storage = MongoDBStorage(
                    mcfg["connection_string"],
                    mcfg.get("database", "piNetMon"),
                    mcfg.get("collection", "sensor_data")
                )

            logger.info("Cloud initialized.")
        except Exception as e:
            logger.error(f"Cloud init failed: {e}")
            logger.warning("Running in local-only mode.")

    # ---------------------------------------------------------------
    # CLOUD HANDLERS
    # ---------------------------------------------------------------

    async def _handle_cloud_message(self, message: Dict[str, Any]):
        logger.info(f"Cloud message: {message}")
        if "config_update" in message:
            self._apply_config_update(message["config_update"])
        if "command" in message:
            await self._execute_command(message["command"])

    async def _handle_cloud_method(self, name: str, payload: Dict[str, Any]):
        logger.info(f"Method: {name}")

        if name == "getConfig":
            return {"status": "success", "config": self.config}

        if name == "updateConfig":
            try:
                self._apply_config_update(payload)
                await self._report_configuration()
                return {"status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        if name == "get_status":
            return self.get_status()

        if name == "get_statistics":
            return self.stats

        if name == "restart_monitoring":
            return {"status": "success", "message": "Restart requested"}

        return {"status": "error", "message": f"Unknown method {name}"}

    async def _handle_twin_patch(self, patch: Dict[str, Any]):
        logger.info(f"Twin patch: {patch}")
        self._apply_config_update(patch)
        await self._report_configuration()

    # ---------------------------------------------------------------
    # CONFIG UPDATE
    # ---------------------------------------------------------------

    def _apply_config_update(self, updates: Dict[str, Any]):
        # Sensors
        if "sensors" in updates:
            for s, v in updates["sensors"].items():
                if s in self.config["sensors"]:
                    self.config["sensors"][s].update(v)

            enabled = {k: v.get("enabled", True)
                       for k, v in self.config["sensors"].items()}
            self.sensor_collector.update_enabled_sensors(enabled)

        # Collection interval
        if "collection_interval" in updates:
            self.config["collection_interval"] = updates["collection_interval"]

        # AI
        if "ai_models" in updates:
            ai = updates["ai_models"]

            # Local
            local = ai.get("local", {})
            local_anom = local.get("anomaly_detection", {})
            if "enabled" in local:
                self.local_ai_enabled = local["enabled"]
            if "thresholds" in local_anom:
                self.threshold_detector.update_thresholds(local_anom["thresholds"])

            # Cloud
            cloud_cfg = ai.get("cloud", {})
            if "enabled" in cloud_cfg:
                self.cloud_ai_enabled = cloud_cfg["enabled"]

            if "anomaly_threshold" in ai:
                self.anomaly_threshold = ai["anomaly_threshold"]

        self._save_config()

    # ---------------------------------------------------------------
    # DEVICE TWIN REPORT
    # ---------------------------------------------------------------

    async def _report_configuration(self):
        if not (self.iot_client and self.iot_client.is_connected):
            return

        props = {
            "configuration": {
                "sensors": self.config.get("sensors", {}),
                "collection_interval": self.config.get("collection_interval", 30),
                "ai_models": {
                    "local": {
                        "anomaly_detection": {
                            "enabled": self.local_ai_enabled,
                            "thresholds": getattr(self.threshold_detector, "thresholds", {})
                        }
                    },
                    "cloud": {"enabled": self.cloud_ai_enabled}
                }
            },
            "system_info": {
                "python_version": sys.version,
                "os": sys.platform,
                "timestamp": datetime.now().isoformat()
            }
        }

        await self.iot_client.send_property_update(props)

    # ---------------------------------------------------------------
    # COMMAND EXECUTION
    # ---------------------------------------------------------------

    async def _execute_command(self, cmd: str):
        if cmd == "collect_now":
            await self.collect_and_process()
            return

        if cmd == "retrain_model":
            data = self.local_storage.get_recent_data(hours=168)
            if data and data.get("dataset") and len(data["dataset"]) >= 10:
                training = self._convert_db_to_sensor_format(data)
                try:
                    self.ml_detector.train(training)
                except Exception as e:
                    logger.error(f"Retrain failed: {e}")
        # cleanup_old_data handled by QuestDB automatically

    # ---------------------------------------------------------------
    # DB → SENSOR FORMAT CONVERSION
    # ---------------------------------------------------------------

    def _convert_db_to_sensor_format(self, db: dict) -> list:
        if not db or "dataset" not in db:
            return []

        cols = {c["name"]: i for i, c in enumerate(db["columns"])}
        out = []

        for row in db["dataset"]:
            try:
                out.append({
                    "timestamp": row[cols.get("timestamp", 0)],
                    "device_id": row[cols.get("device_id", 1)],
                    "cpu": {
                        "temperature": row[cols.get("cpu_temperature", 2)],
                        "usage_percent": row[cols.get("cpu_usage", 3)]
                    },
                    "memory": {"percent": row[cols.get("memory_percent", 4)]},
                    "disk": {"percent": row[cols.get("disk_percent", 5)]},
                    "network": {
                        "bytes_sent_mb": row[cols.get("network_sent_mb", 6)],
                        "bytes_recv_mb": row[cols.get("network_recv_mb", 7)]
                    }
                })
            except Exception:
                continue
        return out

    # ---------------------------------------------------------------
    # DATA COLLECTION & PROCESSING
    # ---------------------------------------------------------------

    async def collect_and_process(self):
        try:
            data = self.sensor_collector.collect_all_data()
            self.stats["total_readings"] += 1

            # Threshold
            thr_anom, thr_viol = self.threshold_detector.detect(data)

            # ML
            ml_anom, ml_score = False, 0.0
            if self.local_ai_enabled:
                try:
                    ml_anom, ml_score = self.ml_detector.predict(data)
                except Exception:
                    recent = self.local_storage.get_recent_data(hours=24)
                    if recent and recent.get("dataset") and len(recent["dataset"]) >= 10:
                        training = self._convert_db_to_sensor_format(recent)
                        try:
                            self.ml_detector.train(training)
                            ml_anom, ml_score = self.ml_detector.predict(data)
                        except Exception:
                            pass

            is_anom = thr_anom or ml_anom
            if is_anom:
                self.stats["anomalies_detected"] += 1

            # Store local
            self.local_storage.save_sensor_data(
                data, anomaly_score=float(ml_score), is_anomaly=is_anom
            )

            # Cloud AI
            cloud_analysis = None
            if self.cloud_ai_enabled and self.cloud_ai_service:
                cloud_analysis = self.cloud_ai_service.analyze_sensor_data(data)

            upload = {
                **data,
                "local_analysis": {
                    "is_anomaly": is_anom,
                    "ml_score": float(ml_score),
                    "threshold_violations": thr_viol
                }
            }
            if cloud_analysis:
                upload["cloud_analysis"] = cloud_analysis["cloud_analysis"]

            # Upload to IoT Hub
            if self.cloud_manager:
                if await self.cloud_manager.upload_sensor_data(upload):
                    self.stats["cloud_uploads"] += 1
                else:
                    self.stats["failed_uploads"] += 1

            # MongoDB
            if self.mongodb_storage and self.mongodb_storage.is_connected:
                self.mongodb_storage.store_sensor_data(upload)

        except Exception as e:
            logger.error(f"collect_and_process error: {e}")

    # ---------------------------------------------------------------
    # MONITOR LOOP
    # ---------------------------------------------------------------

    async def monitoring_loop(self, interval: int):
        self.running = True
        logger.info(f"Loop started (interval {interval}s)")

        while self.running:
            await self.collect_and_process()
            await asyncio.sleep(interval)

    # ---------------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------------

    def get_status(self):
        uptime = datetime.now() - datetime.fromisoformat(self.stats["start_time"])
        return {
            "running": self.running,
            "statistics": self.stats,
            "storage": self.local_storage.get_statistics(),
            "cloud_connected": self.iot_client.is_connected if self.iot_client else False,
            "uptime_seconds": uptime.total_seconds()
        }

    # ---------------------------------------------------------------
    # SHUTDOWN
    # ---------------------------------------------------------------

    async def shutdown(self):
        self.running = False
        if self.iot_client:
            await self.iot_client.disconnect()
        if self.mongodb_storage:
            self.mongodb_storage.disconnect()
        logger.info("Shutdown complete.")


# -------------------------------------------------------------------
# Main entry point
# -------------------------------------------------------------------

async def main():
    print("=" * 50)
    print("Raspberry Pi Network Monitor")
    print("=" * 50)

    app = PiNetworkMonitor()
    await app.initialize_cloud()

    def handler(sig, frame):
        asyncio.create_task(app.shutdown())

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    interval = safe_get(app.config, "sensors", "cpu", "interval_seconds", default=30)
    await app.monitoring_loop(interval)

    await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
