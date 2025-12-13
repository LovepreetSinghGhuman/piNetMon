"""
MongoDB Atlas Storage Module
Uses config.json for connection details.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging
from pathlib import Path

try:
    from pymongo import MongoClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    logging.warning("pymongo not installed. MongoDB integration disabled.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
CONFIG_PATH = Path(__file__).parent.parent / "config/config.json"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    CONFIG = json.load(f)

MONGO_CONF = CONFIG.get("mongodb", {})
CONNECTION_STRING = MONGO_CONF.get("connection_string")
DB_NAME = MONGO_CONF.get("database", "piNetMon")
COLLECTION_NAME = MONGO_CONF.get("collection", "sensor_data")


class MongoDBStorage:
    """MongoDB cloud storage using config.json settings."""

    def __init__(self):
        self.client: MongoClient | None = None
        self.collection = None
        self.is_connected = False
        if not MONGODB_AVAILABLE:
            logger.error("pymongo not installed. Install with `pip install pymongo`")
        elif CONNECTION_STRING:
            self.connect()
        else:
            logger.warning("MongoDB connection string not found in config.json")

    def connect(self):
        try:
            self.client = MongoClient(CONNECTION_STRING, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")
            self.collection = self.client[DB_NAME][COLLECTION_NAME]
            self.is_connected = True

            # Indexes
            self.collection.create_index("timestamp")
            self.collection.create_index("device_id")
            logger.info(f"Connected to MongoDB: {DB_NAME}.{COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")

    def disconnect(self):
        if self.client:
            self.client.close()
            self.is_connected = False
            logger.info("Disconnected from MongoDB")

    def _check_connection(self) -> bool:
        if not self.is_connected:
            logger.warning("Not connected to MongoDB")
            return False
        return True

    def store_sensor_data(self, data: Dict[str, Any]) -> bool:
        if not self._check_connection():
            return False
        try:
            document = {
                **data,
                "stored_at": datetime.utcnow(),
                "source": "raspberry-pi",
                "cloud_provider": "mongodb_atlas"
            }
            result = self.collection.insert_one(document)
            logger.info(f"Data stored in MongoDB: {result.inserted_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store data: {e}")
            return False

    def get_recent_data(self, hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        if not self._check_connection():
            return []
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cursor = self.collection.find(
            {"stored_at": {"$gte": cutoff}}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        return list(cursor)

    def get_anomalies(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._check_connection():
            return []
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cursor = self.collection.find(
            {"stored_at": {"$gte": cutoff}, "local_analysis.is_anomaly": True},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        return list(cursor)

    def get_statistics(self) -> Dict[str, Any]:
        if not self._check_connection():
            return {}
        total = self.collection.count_documents({})
        anomalies = self.collection.count_documents({"local_analysis.is_anomaly": True})
        oldest = self.collection.find_one(sort=[("timestamp", 1)])
        newest = self.collection.find_one(sort=[("timestamp", -1)])
        return {
            "total_documents": total,
            "anomaly_count": anomalies,
            "oldest_record": oldest.get("timestamp") if oldest else None,
            "newest_record": newest.get("timestamp") if newest else None,
            "database": DB_NAME,
            "collection": COLLECTION_NAME,
            "connected": self.is_connected
        }

    def cleanup_old_data(self, days: int = 30):
        if not self._check_connection():
            return
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = self.collection.delete_many({"stored_at": {"$lt": cutoff}})
        logger.info(f"Deleted {result.deleted_count} old documents from MongoDB")


if __name__ == "__main__":
    storage = MongoDBStorage()
    if storage.is_connected:
        test_data = {
            "timestamp": datetime.now().isoformat(),
            "device_id": "raspberry-pi-monitor",
            "cpu": {"temperature": 45.3, "usage_percent": 30.0},
            "memory": {"percent": 50.0}
        }
        storage.store_sensor_data(test_data)
        print(storage.get_statistics())
        storage.disconnect()
    else:
        print("MongoDB not connected. Check config.json.")
