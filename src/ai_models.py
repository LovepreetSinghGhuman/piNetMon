"""
Unified AI Models Module
Contains training, local inference, and cloud AI functionality.
"""

import numpy as np
import pickle
import os
import sys
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
    """
    Load real sensor data from QuestDB for training.
    
    Args:
        min_samples: Minimum number of samples required
        
    Returns:
        numpy array of features or None if insufficient data
    """
    try:
        from questdb_storage import QuestDBStorage
        
        db = QuestDBStorage()
        query = "SELECT cpu_temperature, cpu_usage, memory_percent, disk_percent, network_sent_mb, network_recv_mb FROM sensor_data ORDER BY timestamp DESC LIMIT 1000"
        
        result = db.query(query)
        
        if result is None:
            print(f"⚠️  Query returned None - QuestDB may not be accessible")
            return None
        
        # Extract dataset from QuestDB response
        data = result.get('dataset', [])
        # Extract dataset from QuestDB response
        data = result.get('dataset', [])
        
        if not data or len(data) < min_samples:
            print(f"⚠️  Insufficient data in QuestDB: {len(data) if data else 0} samples (need {min_samples})")
            return None
        
        # Convert to numpy array
        # QuestDB returns data as array of arrays
        X = np.array(data, dtype=float)
        
        print(f"✅ Loaded {len(X)} real samples from QuestDB")
        return X
        
    except Exception as e:
        print(f"Error loading real data: {e}")
        return None


def generate_synthetic_data(n_samples=100):
    """
    Generate synthetic training data simulating normal Raspberry Pi behavior.
    
    Args:
        n_samples: Number of samples to generate
        
    Returns:
        numpy array of features
    """
    np.random.seed(42)
    
    # Normal operating ranges for Raspberry Pi
    cpu_temp = np.random.normal(45, 5, n_samples)
    cpu_usage = np.random.normal(30, 10, n_samples)
    memory_usage = np.random.normal(50, 10, n_samples)
    disk_usage = np.random.normal(60, 5, n_samples)
    network_sent = np.random.normal(100, 20, n_samples)
    network_recv = np.random.normal(200, 30, n_samples)
    
    X_train = np.column_stack([
        cpu_temp, cpu_usage, memory_usage,
        disk_usage, network_sent, network_recv
    ])
    
    # Add anomalies (10%)
    n_anomalies = max(1, int(n_samples * 0.1))
    anomaly_indices = np.random.choice(n_samples, n_anomalies, replace=False)
    X_train[anomaly_indices] += np.random.normal(30, 10, (n_anomalies, 6))
    
    print(f"✅ Generated {n_samples} synthetic samples")
    return X_train


def train_and_save_models(models_dir='../models'):
    """
    Train Isolation Forest model and save to disk.
    
    Args:
        models_dir: Directory to save model files
    """
    print("\n" + "="*60)
    print("Pi Network Monitor - Model Training")
    print("="*60 + "\n")
    
    # Try real data first
    X_train = load_real_data_for_training(min_samples=100)
    
    # Fallback to synthetic
    if X_train is None:
        print("⚠️  Using synthetic data for training")
        X_train = generate_synthetic_data(n_samples=100)
    
    # Scale the data
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    # Train model
    print("Training Isolation Forest model...")
    model = IsolationForest(
        contamination=0.1,
        random_state=42,
        n_estimators=100
    )
    model.fit(X_train_scaled)
    
    # Save
    script_dir = os.path.dirname(os.path.abspath(__file__))
    models_path = os.path.join(script_dir, models_dir)
    os.makedirs(models_path, exist_ok=True)
    
    model_file = os.path.join(models_path, 'model.pkl')
    scaler_file = os.path.join(models_path, 'scaler.pkl')
    model_onnx_file = os.path.join(models_path, 'model.onnx')
    scaler_onnx_file = os.path.join(models_path, 'scaler.onnx')
    
    # Save pickle versions (backward compatibility)
    with open(model_file, 'wb') as f:
        pickle.dump(model, f)
    
    with open(scaler_file, 'wb') as f:
        pickle.dump(scaler, f)
    
    # Export to ONNX format for optimized inference
    print("Exporting to ONNX format...")
    try:
        n_features = X_train.shape[1]
        
        # Convert scaler to ONNX
        initial_type_scaler = [('float_input', FloatTensorType([None, n_features]))]
        scaler_onnx = convert_sklearn(
            scaler,
            initial_types=initial_type_scaler,
            target_opset=12
        )
        with open(scaler_onnx_file, 'wb') as f:
            f.write(scaler_onnx.SerializeToString())
        
        # Convert model to ONNX
        initial_type_model = [('float_input', FloatTensorType([None, n_features]))]
        model_onnx = convert_sklearn(
            model,
            initial_types=initial_type_model,
            target_opset=12
        )
        with open(model_onnx_file, 'wb') as f:
            f.write(model_onnx.SerializeToString())
        
        # Get file sizes
        pkl_size = os.path.getsize(model_file) + os.path.getsize(scaler_file)
        onnx_size = os.path.getsize(model_onnx_file) + os.path.getsize(scaler_onnx_file)
        
        print(f"✅ ONNX export complete (saved {(1 - onnx_size/pkl_size)*100:.1f}%)")
    except Exception as e:
        print(f"⚠️  ONNX export failed: {e}")
        print("   Falling back to pickle-only mode")
    
    print(f"\n{'='*60}")
    print(f"✅ Model training complete!")
    print(f"{'='*60}")
    print(f"Pickle:  {model_file}, {scaler_file}")
    if os.path.exists(model_onnx_file):
        print(f"ONNX:    {model_onnx_file}, {scaler_onnx_file}")
    print(f"Samples: {len(X_train)}")
    print(f"{'='*60}\n")


# ============================================================================
# LOCAL AI - ANOMALY DETECTION
# ============================================================================

class AnomalyDetector:
    """Local AI model for detecting anomalies in sensor data."""
    
    def __init__(self, model_path: str = "./models/model.pkl",
                 contamination: float = 0.1,
                 use_onnx: bool = True):
        """Initialize anomaly detector."""
        self.model_path = model_path
        self.contamination = contamination
        self.use_onnx = use_onnx
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.onnx_model = None
        self.onnx_scaler = None
        self.feature_names = [
            'cpu_temperature', 'cpu_usage_percent', 'memory_percent',
            'disk_percent', 'network_bytes_sent_mb', 'network_bytes_recv_mb'
        ]
        
        # Try ONNX first if enabled
        if use_onnx:
            onnx_model_path = model_path.replace('.pkl', '.onnx')
            onnx_scaler_path = model_path.replace('model.pkl', 'scaler.onnx')
            if os.path.exists(onnx_model_path) and os.path.exists(onnx_scaler_path):
                try:
                    self.onnx_model = ort.InferenceSession(onnx_model_path)
                    self.onnx_scaler = ort.InferenceSession(onnx_scaler_path)
                    logger.info("✅ Loaded ONNX models for fast inference")
                except Exception as e:
                    logger.warning(f"Failed to load ONNX: {e}, falling back to pickle")
                    self.use_onnx = False
        
        # Fallback to pickle
        if not self.use_onnx or self.onnx_model is None:
            if os.path.exists(model_path):
                self.load_model()
            else:
                self._initialize_model()
        
        logger.info(f"AnomalyDetector initialized (ONNX: {self.use_onnx and self.onnx_model is not None})")
    
    def _initialize_model(self):
        """Initialize a new model and scaler."""
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
        logger.info("New model initialized")
    
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
        return np.array(features).reshape(1, -1)
    
    def train(self, training_data: List[Dict[str, Any]]):
        """
        Train the model with provided sensor data.
        
        Args:
            training_data: List of sensor data dictionaries
        """
        if not training_data:
            logger.warning("No training data provided")
            return
        
        # Extract features from all training samples
        features_list = [self.extract_features(sample).flatten() for sample in training_data]
        X_train = np.array(features_list)
        
        logger.info(f"Training with {len(X_train)} samples...")
        
        # Fit scaler
        self.scaler.fit(X_train)
        X_train_scaled = self.scaler.transform(X_train)
        
        # Train model
        self.model.fit(X_train_scaled)
        
        logger.info("Model training complete")
        
        # Save the trained model
        try:
            self.save_model()
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
    
    def predict(self, data: Dict[str, Any]) -> Tuple[bool, float]:
        """Predict if data point is anomalous."""
        features = self.extract_features(data)
        
        # Use ONNX runtime for faster inference
        if self.use_onnx and self.onnx_model is not None and self.onnx_scaler is not None:
            try:
                # Scale features
                features_float = features.astype(np.float32)
                scaler_input = {self.onnx_scaler.get_inputs()[0].name: features_float}
                features_scaled = self.onnx_scaler.run(None, scaler_input)[0]
                
                # Predict
                model_input = {self.onnx_model.get_inputs()[0].name: features_scaled.astype(np.float32)}
                outputs = self.onnx_model.run(None, model_input)
                
                prediction = outputs[0][0]  # label
                anomaly_score = -outputs[1][0][0]  # score (negated)
                
                is_anomaly = (prediction == -1 or prediction == 1)  # ONNX may use 1 for anomaly
                
                if is_anomaly:
                    logger.warning(f"Anomaly detected! Score: {anomaly_score:.3f} (ONNX)")
                
                return bool(is_anomaly), float(anomaly_score)
                
            except Exception as e:
                logger.error(f"ONNX inference failed: {e}, falling back to sklearn")
                self.use_onnx = False
        
        # Fallback to sklearn
        if self.model is None or self.scaler is None:
            logger.warning("Model not trained yet")
            return False, 0.0
        
        features_scaled = self.scaler.transform(features)
        prediction = self.model.predict(features_scaled)[0]
        anomaly_score = -self.model.score_samples(features_scaled)[0]
        
        is_anomaly = (prediction == -1)
        
        if is_anomaly:
            logger.warning(f"Anomaly detected! Score: {anomaly_score:.3f}")
        
        return is_anomaly, float(anomaly_score)
        
        # Use ONNX runtime for faster inference
        if self.use_onnx and self.onnx_model is not None and self.onnx_scaler is not None:
            try:
                # Scale features
                features_float = features.astype(np.float32)
                scaler_input = {self.onnx_scaler.get_inputs()[0].name: features_float}
                features_scaled = self.onnx_scaler.run(None, scaler_input)[0]
                
                # Predict
                model_input = {self.onnx_model.get_inputs()[0].name: features_scaled.astype(np.float32)}
                outputs = self.onnx_model.run(None, model_input)
                
                prediction = outputs[0][0]  # label
                anomaly_score = -outputs[1][0][0]  # score (negated)
                
                is_anomaly = (prediction == -1 or prediction == 1)  # ONNX may use 1 for anomaly
                
                if is_anomaly:
                    logger.warning(f"Anomaly detected! Score: {anomaly_score:.3f} (ONNX)")
                
                return bool(is_anomaly), float(anomaly_score)
                
            except Exception as e:
                logger.error(f"ONNX inference failed: {e}, falling back to sklearn")
                self.use_onnx = False
        
        # Fallback to sklearn
        if self.model is None or self.scaler is None:
            logger.warning("Model not trained yet")
            return False, 0.0
        
        features_scaled = self.scaler.transform(features)
        prediction = self.model.predict(features_scaled)[0]
        anomaly_score = -self.model.score_samples(features_scaled)[0]
        
        is_anomaly = (prediction == -1)
        
        if is_anomaly:
            logger.warning(f"Anomaly detected! Score: {anomaly_score:.3f}")
        
        return is_anomaly, float(anomaly_score)
    
    def save_model(self):
        """Save model and scaler to disk."""
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'contamination': self.contamination
        }
        
        with open(self.model_path, 'wb') as f:
            pickle.dump(model_data, f)
        
        logger.info(f"Model saved to {self.model_path}")
    
    def load_model(self):
        """Load model and scaler from disk."""
        try:
            with open(self.model_path, 'rb') as f:
                model_data = pickle.load(f)
            
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            self.contamination = model_data['contamination']
            
            logger.info(f"Model loaded from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self._initialize_model()


class SimpleThresholdDetector:
    """Simple threshold-based anomaly detector."""
    
    def __init__(self):
        """Initialize threshold detector."""
        self.thresholds = {
            'cpu_temperature': {'min': 0, 'max': 85},
            'cpu_usage_percent': {'min': 0, 'max': 95},
            'memory_percent': {'min': 0, 'max': 90},
            'disk_percent': {'min': 0, 'max': 95}
        }
        logger.info("SimpleThresholdDetector initialized")
    
    def detect(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Detect anomalies using simple thresholds."""
        violations = []
        
        # Check CPU temperature
        cpu_temp = data['cpu'].get('temperature', 0)
        if cpu_temp > self.thresholds['cpu_temperature']['max']:
            violations.append(f"CPU temperature: {cpu_temp}°C")
        
        # Check CPU usage
        cpu_usage = data['cpu'].get('usage_percent', 0)
        if cpu_usage > self.thresholds['cpu_usage_percent']['max']:
            violations.append(f"CPU usage: {cpu_usage}%")
        
        # Check memory
        memory_pct = data['memory'].get('percent', 0)
        if memory_pct > self.thresholds['memory_percent']['max']:
            violations.append(f"Memory: {memory_pct}%")
        
        # Check disk
        disk_pct = data['disk'].get('percent', 0)
        if disk_pct > self.thresholds['disk_percent']['max']:
            violations.append(f"Disk: {disk_pct}%")
        
        return len(violations) > 0, violations


# ============================================================================
# CLOUD AI - AZURE ML CLIENT
# ============================================================================

class AzureMLClient:
    """Client for Azure Machine Learning REST API."""
    
    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize Azure ML client."""
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.is_configured = bool(endpoint_url and api_key)
        
        if not self.is_configured:
            logger.warning("Azure ML client not fully configured")
        else:
            logger.info("Azure ML client initialized")
    
    def predict(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send data to Azure ML endpoint for prediction."""
        if not self.is_configured:
            logger.warning("Azure ML client not configured")
            return None
        
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            payload = json.dumps({'data': data})
            
            response = requests.post(
                self.endpoint_url,
                headers=headers,
                data=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            logger.info("Cloud prediction successful")
            return result
            
        except Exception as e:
            logger.error(f"Cloud prediction failed: {e}")
            return None
    
    def health_check(self) -> bool:
        """Check if Azure ML endpoint is accessible."""
        if not self.is_configured:
            return False
        
        try:
            response = requests.get(self.endpoint_url, timeout=10)
            return response.status_code in [200, 405]
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class MockAzureMLClient:
    """Mock Azure ML client for testing without cloud connection."""
    
    def __init__(self):
        """Initialize mock client."""
        self.is_configured = False
        logger.info("MockAzureMLClient initialized (no cloud connection)")
    
    def predict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Return mock prediction."""
        return {
            'prediction': 'normal',
            'anomaly_score': 0.3,
            'confidence': 0.85,
            'is_anomaly': False
        }
    
    def health_check(self) -> bool:
        """Mock health check always returns True."""
        return True


class CloudAIService:
    """Service for cloud-based AI operations."""
    
    def __init__(self, ml_client: Optional[AzureMLClient] = None):
        """Initialize cloud AI service."""
        self.ml_client = ml_client or MockAzureMLClient()
        logger.info("CloudAIService initialized")
    
    @classmethod
    def from_config(cls, config: dict):
        """Create CloudAIService from configuration."""
        ml_config = config.get('ai_models', {}).get('cloud', {})
        endpoint = ml_config.get('endpoint')
        api_key = ml_config.get('api_key')
        
        if endpoint and api_key:
            ml_client = AzureMLClient(endpoint, api_key)
        else:
            ml_client = MockAzureMLClient()
        
        return cls(ml_client)
    
    def analyze_sensor_data(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sensor data using cloud AI."""
        result = {
            'timestamp': sensor_data.get('timestamp'),
            'device_id': sensor_data.get('device_id'),
            'cloud_analysis': {
                'available': False,
                'prediction': None,
                'confidence': None
            }
        }
        
        # Call cloud service
        prediction = self.ml_client.predict(sensor_data)
        
        if prediction:
            result['cloud_analysis'].update({
                'available': True,
                'prediction': prediction.get('prediction'),
                'confidence': prediction.get('confidence'),
                'anomaly_score': prediction.get('anomaly_score'),
                'is_anomaly': prediction.get('is_anomaly', False)
            })
        
        return result


# ============================================================================
# MAIN - FOR TRAINING
# ============================================================================

if __name__ == "__main__":
    train_and_save_models()
