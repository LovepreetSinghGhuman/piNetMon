"""
Unified AI Models Module - Simplified
Contains training, local inference, and cloud AI functionality.
"""

import numpy as np
import pickle
import os
import json
import requests
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import Dict, Any, Tuple, List, Optional
import logging
import onnxruntime as ort
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# TRAINING FUNCTIONS
# ============================================================================

def load_real_data_for_training(min_samples=100):
    """Load real data from QuestDB for training."""
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
        
        if not result:
            logger.warning("Query returned None - QuestDB may not be accessible")
            return None
        
        data = result.get('dataset', [])
        
        if not data or len(data) < min_samples:
            logger.warning(f"Insufficient data: {len(data) if data else 0}/{min_samples}")
            return None
        
        X = np.array(data, dtype=float)
        logger.info(f"Loaded {len(X)} real samples from QuestDB")
        return X
        
    except Exception as e:
        logger.error(f"Error loading real data: {e}")
        return None


def generate_synthetic_data(n_samples=100):
    """Generate synthetic training data."""
    np.random.seed(42)
    
    # Normal operating ranges for Raspberry Pi
    X_train = np.column_stack([
        np.random.normal(45, 5, n_samples),    # cpu_temp
        np.random.normal(30, 10, n_samples),   # cpu_usage
        np.random.normal(50, 10, n_samples),   # memory_usage
        np.random.normal(60, 5, n_samples),    # disk_usage
        np.random.normal(100, 20, n_samples),  # network_sent
        np.random.normal(200, 30, n_samples)   # network_recv
    ])
    
    # Add anomalies (10%)
    n_anomalies = max(1, int(n_samples * 0.1))
    anomaly_indices = np.random.choice(n_samples, n_anomalies, replace=False)
    X_train[anomaly_indices] += np.random.normal(30, 10, (n_anomalies, 6))
    
    logger.info(f"Generated {n_samples} synthetic samples")
    return X_train


def train_and_save_models(models_dir='../models'):
    """Train Isolation Forest model and save to disk."""
    print("\n" + "="*60)
    print("Pi Network Monitor - Model Training")
    print("="*60 + "\n")
    
    # Try real data first, fallback to synthetic
    X_train = load_real_data_for_training(min_samples=100)
    if X_train is None:
        logger.warning("Using synthetic data for training")
        X_train = generate_synthetic_data(n_samples=100)
    
    # Scale and train
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    logger.info("Training Isolation Forest model...")
    model = IsolationForest(
        contamination=0.1,
        random_state=42,
        n_estimators=100
    )
    model.fit(X_train_scaled)
    
    # Prepare paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(script_dir, models_dir)
    os.makedirs(models_path, exist_ok=True)
    
    # Save pickle versions
    model_file = os.path.join(models_path, 'model.pkl')
    scaler_file = os.path.join(models_path, 'scaler.pkl')
    
    with open(model_file, 'wb') as f:
        pickle.dump(model, f)
    with open(scaler_file, 'wb') as f:
        pickle.dump(scaler, f)
    
    # Export to ONNX
    logger.info("Exporting to ONNX format...")
    try:
        n_features = X_train.shape[1]
        initial_type = [('float_input', FloatTensorType([None, n_features]))]
        
        # Convert scaler
        scaler_onnx = convert_sklearn(scaler, initial_types=initial_type, target_opset=12)
        scaler_onnx_file = os.path.join(models_path, 'scaler.onnx')
        with open(scaler_onnx_file, 'wb') as f:
            f.write(scaler_onnx.SerializeToString())
        
        # Convert model
        model_onnx = convert_sklearn(model, initial_types=initial_type, target_opset=12)
        model_onnx_file = os.path.join(models_path, 'model.onnx')
        with open(model_onnx_file, 'wb') as f:
            f.write(model_onnx.SerializeToString())
        
        # Report sizes
        pkl_size = os.path.getsize(model_file) + os.path.getsize(scaler_file)
        onnx_size = os.path.getsize(model_onnx_file) + os.path.getsize(scaler_onnx_file)
        
        logger.info(f"ONNX export complete (saved {(1 - onnx_size/pkl_size)*100:.1f}%)")
    except Exception as e:
        logger.warning(f"ONNX export failed: {e} - continuing with pickle only")
    
    print(f"\n{'='*60}")
    print(f"✅ Training complete! Samples: {len(X_train)}")
    print(f"{'='*60}\n")


# ============================================================================
# LOCAL AI - ANOMALY DETECTION
# ============================================================================

class AnomalyDetector:
    """Local AI model for detecting anomalies in sensor data."""
    
    FEATURE_NAMES = [
        'cpu_temperature', 'cpu_usage_percent', 'memory_percent',
        'disk_percent', 'network_bytes_sent_mb', 'network_bytes_recv_mb'
    ]
    
    def __init__(self, model_path: str = "./models/model.pkl", use_onnx: bool = True):
        """Initialize anomaly detector."""
        self.model_path = model_path
        self.use_onnx = use_onnx
        self.model = None
        self.scaler = None
        self.onnx_model = None
        self.onnx_scaler = None
        
        # Try loading ONNX first
        if use_onnx and self._load_onnx():
            logger.info("✅ Using ONNX models for fast inference")
        # Fallback to pickle
        elif os.path.exists(model_path):
            self._load_pickle()
        else:
            logger.warning("No model found - initialize with train() first")
    
    def _load_onnx(self) -> bool:
        """Try to load ONNX models."""
        try:
            onnx_model_path = self.model_path.replace('.pkl', '.onnx')
            onnx_scaler_path = self.model_path.replace('model.pkl', 'scaler.onnx')
            
            if os.path.exists(onnx_model_path) and os.path.exists(onnx_scaler_path):
                self.onnx_model = ort.InferenceSession(onnx_model_path)
                self.onnx_scaler = ort.InferenceSession(onnx_scaler_path)
                return True
        except Exception as e:
            logger.warning(f"Failed to load ONNX: {e}")
        return False
    
    def _load_pickle(self):
        """Load pickle models."""
        try:
            with open(self.model_path, 'rb') as f:
                self.model = pickle.load(f)
            
            scaler_path = self.model_path.replace('model.pkl', 'scaler.pkl')
            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            
            logger.info(f"Loaded pickle model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load pickle model: {e}")
    
    def extract_features(self, data: Dict[str, Any]) -> np.ndarray:
        """Extract numerical features from sensor data."""
        features = [
            data['cpu'].get('temperature', 0.0) or 0.0,
            data['cpu'].get('usage_percent', 0.0),
            data['memory'].get('percent', 0.0),
            data['disk'].get('percent', 0.0),
            data['network'].get('bytes_sent_mb', 0.0),
            data['network'].get('bytes_recv_mb', 0.0)
        ]
        return np.array(features, dtype=np.float32).reshape(1, -1)
    
    def predict(self, data: Dict[str, Any]) -> Tuple[bool, float]:
        """Predict if data point is anomalous."""
        features = self.extract_features(data)
        
        # Try ONNX inference first
        if self.onnx_model and self.onnx_scaler:
            try:
                # Scale features
                scaler_input = {self.onnx_scaler.get_inputs()[0].name: features}
                features_scaled = self.onnx_scaler.run(None, scaler_input)[0]
                
                # Predict
                model_input = {self.onnx_model.get_inputs()[0].name: features_scaled}
                outputs = self.onnx_model.run(None, model_input)
                
                prediction = outputs[0][0]
                anomaly_score = -outputs[1][0][0]
                is_anomaly = (prediction == -1 or prediction == 1)
                
                if is_anomaly:
                    logger.warning(f"⚠️  Anomaly detected! Score: {anomaly_score:.3f}")
                
                return bool(is_anomaly), float(anomaly_score)
                
            except Exception as e:
                logger.error(f"ONNX inference failed: {e}, falling back to sklearn")
                self.use_onnx = False
        
        # Fallback to sklearn
        if not self.model or not self.scaler:
            logger.warning("Model not loaded")
            return False, 0.0
        
        features_scaled = self.scaler.transform(features)
        prediction = self.model.predict(features_scaled)[0]
        anomaly_score = -self.model.score_samples(features_scaled)[0]
        is_anomaly = (prediction == -1)
        
        if is_anomaly:
            logger.warning(f"⚠️  Anomaly detected! Score: {anomaly_score:.3f}")
        
        return is_anomaly, float(anomaly_score)


# ============================================================================
# CLOUD AI - AZURE ML CLIENT (Optional)
# ============================================================================

class AzureMLClient:
    """Client for Azure Machine Learning REST API."""
    
    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize Azure ML client."""
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.is_configured = bool(endpoint_url and api_key)
        
        if self.is_configured:
            logger.info("Azure ML client initialized")
        else:
            logger.info("Azure ML client not configured (optional)")
    
    def predict(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send data to Azure ML endpoint for prediction."""
        if not self.is_configured:
            return None
        
        try:
            response = requests.post(
                self.endpoint_url,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                },
                json={'data': data},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Cloud prediction failed: {e}")
            return None


# ============================================================================
# MAIN - FOR TRAINING
# ============================================================================

if __name__ == "__main__":
    train_and_save_models()