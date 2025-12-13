"""
AI Models Module - Unified & Simplified
Features:
- Train IsolationForest (real QuestDB → synthetic fallback)
- ONNX export preferred
- PKL fallback if ONNX fails
- Local inference (ONNX preferred)
- Cloud AI (Azure ML) integration
"""

import os
import json
import pickle
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

import onnxruntime as ort
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------- Load config ---------------------------

CONFIG_PATH = Path(__file__).parent.parent / "config/config.json"

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"config.json not found at {CONFIG_PATH}")

with CONFIG_PATH.open("r") as f:
    CONFIG = json.load(f)

MODEL_DIR = CONFIG.get("ai_models", {}).get("local", {}).get("model_path", "./models/model.onnx")
CLOUD_CONF = CONFIG.get("ai_models", {}).get("cloud", {})

# --------------------------- TRAINING HELPERS ---------------------------

def load_real_data(min_samples=100):
    """Load last samples from QuestDB or fallback."""
    try:
        from questdb_storage import QuestDBStorage
        db = QuestDBStorage()
        query = """
            SELECT cpu_temperature, cpu_usage_percent, memory_percent, 
                   disk_percent, network_sent_mb, network_recv_mb
            FROM sensor_data
            ORDER BY timestamp DESC LIMIT 100
        """
        result = db.query(query)
        data = result.get("dataset", []) if result else []
        if len(data) < min_samples:
            logger.warning(f"Not enough QuestDB data ({len(data)}/{min_samples})")
            return None
        return np.array(data, dtype=float)
    except Exception as e:
        logger.error(f"QuestDB load failed: {e}")
        return None


def generate_synthetic_data(n=100):
    """Fallback synthetic dataset with 10% anomalies."""
    np.random.seed(42)
    X = np.column_stack([
        np.random.normal(45, 5, n),   # cpu_temp
        np.random.normal(30, 10, n),  # cpu_usage
        np.random.normal(50, 10, n),  # memory_percent
        np.random.normal(60, 5, n),   # disk_percent
        np.random.normal(100, 20, n), # network_sent
        np.random.normal(200, 30, n)  # network_recv
    ])
    # inject anomalies
    idx = np.random.choice(n, max(1, n // 10), replace=False)
    X[idx] += np.random.normal(30, 10, (len(idx), 6))
    logger.info(f"Synthetic dataset generated ({n} samples)")
    return X


# --------------------------- TRAIN + SAVE ---------------------------

def train_and_save_models(model_dir="./models"):
    """Train IsolationForest + Scaler → ONNX preferred, fallback PKL."""
    os.makedirs(model_dir, exist_ok=True)
    X = load_real_data() or generate_synthetic_data()
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)
    model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42).fit(X_scaled)

    # ONNX export
    try:
        logger.info("Exporting ONNX models...")
        n_features = X.shape[1]
        init_type = [('float_input', FloatTensorType([None, n_features]))]
        
        # Specify target opset to avoid version mismatch
        target_opset = {'': 15, 'ai.onnx.ml': 3}

        # Scaler ONNX
        scaler_onnx = convert_sklearn(scaler, initial_types=init_type, target_opset=target_opset)
        with open(os.path.join(model_dir, "scaler.onnx"), "wb") as f:
            f.write(scaler_onnx.SerializeToString())

        # Model ONNX
        model_onnx = convert_sklearn(model, initial_types=init_type, target_opset=target_opset)
        with open(os.path.join(model_dir, "model.onnx"), "wb") as f:
            f.write(model_onnx.SerializeToString())

        logger.info("ONNX export successful → skipping PKL save")
        return

    except Exception as e:
        logger.error(f"ONNX export failed → fallback to PKL: {e}")

    # PKL fallback
    with open(os.path.join(model_dir, "model.pkl"), "wb") as f:
        pickle.dump(model, f)
    with open(os.path.join(model_dir, "scaler.pkl"), "wb") as f:
        pickle.dump(scaler, f)
    logger.info("PKL models saved")


# --------------------------- LOCAL INFERENCE ---------------------------
class SimpleThresholdDetector:
    """Simple threshold-based anomaly detection."""
    
    def __init__(self):
        self.thresholds = {
            "cpu_temperature": 80.0,
            "cpu_usage": 90.0,
            "memory_percent": 85.0,
            "disk_percent": 90.0
        }
        logger.info(f"SimpleThresholdDetector initialized with thresholds: {self.thresholds}")
    
    def update_thresholds(self, new_thresholds: dict):
        """Update threshold values from device twin."""
        if new_thresholds:
            self.thresholds.update(new_thresholds)
            logger.info(f"Thresholds updated: {self.thresholds}")
    
    def detect(self, data: dict) -> Tuple[bool, dict]:
        """
        Detect anomalies based on thresholds.
        Returns (is_anomaly, violations_dict)
        """
        violations = {}
        is_anomaly = False
        
        # Check CPU temperature
        cpu = data.get("cpu", {})
        temp = cpu.get("temperature", 0)
        if temp > self.thresholds.get("cpu_temperature", 80):
            violations["cpu_temperature"] = temp
            is_anomaly = True
        
        # Check CPU usage
        usage = cpu.get("usage_percent", 0)
        if usage > self.thresholds.get("cpu_usage", 90):
            violations["cpu_usage"] = usage
            is_anomaly = True
        
        # Check Memory
        memory = data.get("memory", {})
        mem_pct = memory.get("percent", 0)
        if mem_pct > self.thresholds.get("memory_percent", 85):
            violations["memory_percent"] = mem_pct
            is_anomaly = True
        
        # Check Disk
        disk = data.get("disk", {})
        disk_pct = disk.get("percent", 0)
        if disk_pct > self.thresholds.get("disk_percent", 90):
            violations["disk_percent"] = disk_pct
            is_anomaly = True
        
        return is_anomaly, violations

class AnomalyDetector:
    """Local anomaly detection: ONNX preferred, PKL fallback."""

    FEATURES = ["cpu_temperature", "cpu_usage_percent", "memory_percent", "disk_percent", "network_sent_mb", "network_recv_mb"]

    def __init__(self, model_path=MODEL_DIR, prefer_onnx=True):
        self.model_path = model_path
        self.prefer_onnx = prefer_onnx
        self.onnx_model, self.onnx_scaler = None, None
        self.model, self.scaler = None, None
        if prefer_onnx and self._load_onnx():
            logger.info("Using ONNX inference")
        else:
            self._load_pkl()
            logger.info("Using PKL inference")

    def _load_onnx(self):
        try:
            m_path = self.model_path.replace(".pkl", ".onnx")
            s_path = self.model_path.replace("model.pkl", "scaler.onnx")
            if os.path.exists(m_path) and os.path.exists(s_path):
                self.onnx_model = ort.InferenceSession(m_path)
                self.onnx_scaler = ort.InferenceSession(s_path)
                return True
        except Exception as e:
            logger.error(f"ONNX load failed: {e}")
        return False

    def _load_pkl(self):
        try:
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)
            scaler_path = self.model_path.replace("model.pkl", "scaler.pkl")
            with open(scaler_path, "rb") as f:
                self.scaler = pickle.load(f)
        except Exception as e:
            logger.error(f"PKL load failed: {e}")

    def extract_features(self, d: Dict[str, Any]):
        return np.array([
            d["cpu"].get("temperature", 0),
            d["cpu"].get("usage_percent", 0),
            d["memory"].get("percent", 0),
            d["disk"].get("percent", 0),
            d["network"].get("bytes_sent_mb", 0),
            d["network"].get("bytes_recv_mb", 0)
        ], dtype=np.float32).reshape(1, -1)

    def predict(self, data: Dict[str, Any]) -> Tuple[bool, float]:
        x = self.extract_features(data)

        if self.onnx_model:
            try:
                xs = self.onnx_scaler.run(None, {self.onnx_scaler.get_inputs()[0].name: x})[0]
                out = self.onnx_model.run(None, {self.onnx_model.get_inputs()[0].name: xs})
                pred, score = out[0][0], -out[1][0][0]
                return bool(pred == -1 or pred == 1), float(score)
            except Exception as e:
                logger.error(f"ONNX inference failed: {e}")

        xs = self.scaler.transform(x)
        pred = self.model.predict(xs)[0]
        score = -self.model.score_samples(xs)[0]
        return (pred == -1), float(score)


# --------------------------- CLOUD AI ---------------------------

class AzureMLClient:
    """Azure ML REST endpoint client."""

    def __init__(self, endpoint=None, api_key=None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.enabled = bool(endpoint and api_key)

    def predict(self, data):
        if not self.enabled:
            return None
        try:
            r = requests.post(
                self.endpoint,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                json={"data": data}, timeout=20
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Cloud AI error: {e}")
            return None


class CloudAIService:
    """Wrapper for cloud inference."""

    def __init__(self, endpoint=None, api_key=None):
        self.client = AzureMLClient(endpoint, api_key)

    @classmethod
    def from_config(cls, cfg=CONFIG):
        c = cfg.get("ai_models", {}).get("cloud", {})
        return cls(c.get("endpoint"), c.get("api_key"))

    def analyze_sensor_data(self, data):
        r = self.client.predict(data)
        return {"cloud_analysis": r, "timestamp": datetime.now().isoformat(), "error": None if r else "Cloud AI unavailable"}


# --------------------------- MAIN ---------------------------

if __name__ == "__main__":
    train_and_save_models()
