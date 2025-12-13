"""
Unified AI Models Module - Simplified
Includes:
- Training (real QuestDB → synthetic fallback)
- ONNX export (preferred)
- PKL fallback only if ONNX fails
- Local inference (ONNX preferred)
- Azure ML cloud AI client
"""

import os
import json
import pickle
import logging
import requests
import numpy as np

from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

import onnxruntime as ort
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
#                           TRAINING HELPERS
# ============================================================================

def load_real_data_for_training(min_samples=100):
    """Load last ~1000 samples from QuestDB."""
    try:
        from questdb_storage import QuestDBStorage
        db = QuestDBStorage()
        query = """
            SELECT cpu_temperature, cpu_usage, memory_percent, 
                   disk_percent, network_sent_mb, network_recv_mb 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 1000
        """

        result = db.query(query)
        data = result.get("dataset", []) if result else []

        if len(data) < min_samples:
            logger.warning(f"QuestDB data too small ({len(data)}/{min_samples})")
            return None

        return np.array(data, dtype=float)

    except Exception as e:
        logger.error(f"QuestDB load error: {e}")
        return None


def generate_synthetic_data(n=100):
    """Fallback synthetic training dataset."""
    np.random.seed(42)
    X = np.column_stack([
        np.random.normal(45, 5, n),
        np.random.normal(30, 10, n),
        np.random.normal(50, 10, n),
        np.random.normal(60, 5, n),
        np.random.normal(100, 20, n),
        np.random.normal(200, 30, n)
    ])

    # Inject anomalies (10%)
    idx = np.random.choice(n, max(1, n // 10), replace=False)
    X[idx] += np.random.normal(30, 10, (len(idx), 6))

    logger.info(f"Generated synthetic dataset ({n} samples)")
    return X


# ============================================================================
#                           TRAIN + SAVE
# ============================================================================

def train_and_save_models(models_dir="../models"):
    """Train IsolationForest + Scaler and export ONNX (preferred)."""

    print("\n========== Training AI Models ==========\n")

    # Load real → synthetic fallback
    X = load_real_data_for_training() or generate_synthetic_data()

    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.10,
        random_state=42
    ).fit(X_scaled)

    # Prepare paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(script_dir, models_dir)
    os.makedirs(models_path, exist_ok=True)

    # --- ONNX preferred ---
    try:
        logger.info("Exporting ONNX...")

        n_features = X.shape[1]
        input_type = [('float_input', FloatTensorType([None, n_features]))]
        target_op = {'': 12, 'ai.onnx.ml': 3}

        # Export scaler
        scaler_onnx = convert_sklearn(scaler, initial_types=input_type, target_opset=target_op)
        scaler_onnx_path = os.path.join(models_path, "scaler.onnx")
        with open(scaler_onnx_path, "wb") as f:
            f.write(scaler_onnx.SerializeToString())

        # Export model
        model_onnx = convert_sklearn(model, initial_types=input_type, target_opset=target_op)
        model_onnx_path = os.path.join(models_path, "model.onnx")
        with open(model_onnx_path, "wb") as f:
            f.write(model_onnx.SerializeToString())

        logger.info("ONNX export successful → skipping PKL save")

        print(f"\n==== Training finished using ONNX ({len(X)} samples) ====\n")
        return  # <-- EXIT HERE (your special request)

    except Exception as e:
        logger.error(f"ONNX export failed → falling back to PKL: {e}")

    # --- Fallback: PKL only if ONNX fails ---
    model_path = os.path.join(models_path, "model.pkl")
    scaler_path = os.path.join(models_path, "scaler.pkl")

    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)

    logger.info("Fallback PKL models saved")

    print(f"\n==== Training finished using PKL ({len(X)} samples) ====\n")


# ============================================================================
#                        LOCAL INFERENCE MODEL
# ============================================================================

class AnomalyDetector:
    """Local anomaly inference using ONNX (fast) → PKL fallback."""

    FEATURES = [
        "cpu_temperature", "cpu_usage_percent", "memory_percent",
        "disk_percent", "network_bytes_sent_mb", "network_bytes_recv_mb"
    ]

    def __init__(self, model_path="./models/model.pkl", prefer_onnx=True):
        self.model_path = model_path
        self.prefer_onnx = prefer_onnx

        self.onnx_model = None
        self.onnx_scaler = None
        self.model = None
        self.scaler = None

        # Try ONNX first
        if prefer_onnx and self._load_onnx():
            logger.info("Using ONNX inference")
        else:
            logger.info("Falling back to PKL models")
            self._load_pkl()

    # ------------------------ Loaders ------------------------

    def _load_onnx(self) -> bool:
        try:
            m = self.model_path.replace(".pkl", ".onnx")
            s = self.model_path.replace("model.pkl", "scaler.onnx")

            if os.path.exists(m) and os.path.exists(s):
                self.onnx_model = ort.InferenceSession(m)
                self.onnx_scaler = ort.InferenceSession(s)
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

    # ------------------------ Feature Extraction ------------------------

    def extract(self, d: Dict[str, Any]):
        return np.array([
            d["cpu"].get("temperature", 0),
            d["cpu"].get("usage_percent", 0),
            d["memory"].get("percent", 0),
            d["disk"].get("percent", 0),
            d["network"].get("bytes_sent_mb", 0),
            d["network"].get("bytes_recv_mb", 0),
        ], dtype=np.float32).reshape(1, -1)

    # ------------------------ Prediction ------------------------

    def predict(self, data: Dict[str, Any]) -> Tuple[bool, float]:
        x = self.extract(data)

        # ---------- ONNX INFERENCE ----------
        if self.onnx_model:
            try:
                xs = self.onnx_scaler.run(None, {self.onnx_scaler.get_inputs()[0].name: x})[0]
                out = self.onnx_model.run(None, {self.onnx_model.get_inputs()[0].name: xs})

                pred = out[0][0]     # -1 or 1
                score = -out[1][0][0]

                anomaly = bool(pred == -1 or pred == 1)

                if anomaly:
                    logger.warning(f"⚠️ Anomaly from ONNX (score={score:.3f})")

                return anomaly, float(score)

            except Exception as e:
                logger.error(f"ONNX inference error: {e}")

        # ---------- FALLBACK: SKLEARN ----------
        xs = self.scaler.transform(x)
        pred = self.model.predict(xs)[0]
        score = -self.model.score_samples(xs)[0]
        anomaly = (pred == -1)

        if anomaly:
            logger.warning(f"⚠️ Anomaly from PKL (score={score:.3f})")

        return anomaly, float(score)


# ============================================================================
#                           CLOUD AI
# ============================================================================

class AzureMLClient:
    """Azure ML REST endpoint client (optional)."""

    def __init__(self, endpoint: Optional[str], api_key: Optional[str]):
        self.endpoint = endpoint
        self.api_key = api_key
        self.enabled = bool(endpoint and api_key)

    def predict(self, data: Dict[str, Any]):
        if not self.enabled:
            return None

        try:
            r = requests.post(
                self.endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={"data": data},
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Cloud AI error: {e}")
            return None


class CloudAIService:
    def __init__(self, endpoint=None, api_key=None):
        self.client = AzureMLClient(endpoint, api_key)

    @classmethod
    def from_config(cls, cfg):
        c = cfg.get("ai_models", {}).get("cloud", {})
        return cls(c.get("endpoint"), c.get("api_key"))

    def analyze_sensor_data(self, data):
        r = self.client.predict(data)
        return {
            "cloud_analysis": r,
            "timestamp": datetime.now().isoformat(),
            "error": None if r else "Cloud AI unavailable",
        }


# ============================================================================
#                           MAIN → TRAINING
# ============================================================================

if __name__ == "__main__":
    train_and_save_models()
