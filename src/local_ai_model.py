"""
Local AI Model for Anomaly Detection
Uses Isolation Forest algorithm for detecting anomalies in sensor data.
"""

import numpy as np
import pickle
import os
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import Dict, Any, Tuple, List, Optional
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Local AI model for detecting anomalies in sensor data."""
    
    def __init__(self, model_path: str = "./models/local-model.pkl",
                 contamination: float = 0.1):
        """
        Initialize anomaly detector.
        
        Args:
            model_path: Path to save/load model
            contamination: Expected proportion of outliers in the dataset
        """
        self.model_path = model_path
        self.contamination = contamination
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names = [
            'cpu_temperature',
            'cpu_usage_percent',
            'memory_percent',
            'disk_percent',
            'network_bytes_sent_mb',
            'network_bytes_recv_mb'
        ]
        
        # Try to load existing model
        if os.path.exists(model_path):
            self.load_model()
        else:
            self._initialize_model()
        
        logger.info("AnomalyDetector initialized")
    
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
        """
        Extract numerical features from sensor data.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            numpy array of features
        """
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
        Train the anomaly detection model.
        
        Args:
            training_data: List of sensor data dictionaries
        """
        if len(training_data) < 10:
            logger.warning("Not enough training data (minimum 10 samples required)")
            return
        
        # Extract features from all training samples
        features_list = []
        for data in training_data:
            features = self.extract_features(data)
            features_list.append(features.flatten())
        
        X = np.array(features_list)
        
        # Fit scaler and transform data
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model.fit(X_scaled)
        
        logger.info(f"Model trained on {len(training_data)} samples")
        
        # Save model
        self.save_model()
    
    def predict(self, data: Dict[str, Any]) -> Tuple[bool, float]:
        """
        Predict if data point is anomalous.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            tuple: (is_anomaly, anomaly_score)
                - is_anomaly: True if anomaly detected
                - anomaly_score: Anomaly score (higher = more anomalous)
        """
        if self.model is None or self.scaler is None:
            logger.warning("Model not trained yet")
            return False, 0.0
        
        # Extract and scale features
        features = self.extract_features(data)
        features_scaled = self.scaler.transform(features)
        
        # Predict
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
    """Simple threshold-based anomaly detector for immediate use."""
    
    def __init__(self):
        """Initialize threshold detector with default thresholds."""
        self.thresholds = {
            'cpu_temperature': {'min': 0, 'max': 85},
            'cpu_usage_percent': {'min': 0, 'max': 95},
            'memory_percent': {'min': 0, 'max': 90},
            'disk_percent': {'min': 0, 'max': 95}
        }
        logger.info("SimpleThresholdDetector initialized")
    
    def detect(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Detect anomalies using simple thresholds.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            tuple: (is_anomaly, list of violated thresholds)
        """
        violations = []
        
        # Check CPU temperature
        cpu_temp = data['cpu'].get('temperature')
        if cpu_temp is not None:
            if cpu_temp < self.thresholds['cpu_temperature']['min'] or \
               cpu_temp > self.thresholds['cpu_temperature']['max']:
                violations.append(f"CPU temperature: {cpu_temp}°C")
        
        # Check CPU usage
        cpu_usage = data['cpu'].get('usage_percent', 0)
        if cpu_usage > self.thresholds['cpu_usage_percent']['max']:
            violations.append(f"CPU usage: {cpu_usage}%")
        
        # Check memory usage
        memory_usage = data['memory'].get('percent', 0)
        if memory_usage > self.thresholds['memory_percent']['max']:
            violations.append(f"Memory usage: {memory_usage}%")
        
        # Check disk usage
        disk_usage = data['disk'].get('percent', 0)
        if disk_usage > self.thresholds['disk_percent']['max']:
            violations.append(f"Disk usage: {disk_usage}%")
        
        is_anomaly = len(violations) > 0
        
        if is_anomaly:
            logger.warning(f"Threshold violations: {', '.join(violations)}")
        
        return is_anomaly, violations
    
    def update_thresholds(self, new_thresholds: Dict[str, Dict[str, float]]):
        """
        Update detection thresholds.
        
        Args:
            new_thresholds: New threshold values
        """
        self.thresholds.update(new_thresholds)
        logger.info(f"Thresholds updated: {new_thresholds}")


def main():
    """Test anomaly detection."""
    # Test data - normal
    normal_data = {
        'timestamp': '2024-01-01T12:00:00',
        'device_id': 'rapsberry-pi-monitor',
        'cpu': {
            'temperature': 45.0,
            'usage_percent': 30.0
        },
        'memory': {
            'percent': 50.0
        },
        'disk': {
            'percent': 60.0
        },
        'network': {
            'bytes_sent_mb': 100.0,
            'bytes_recv_mb': 200.0
        }
    }
    
    # Test data - anomaly
    anomaly_data = {
        'timestamp': '2024-01-01T12:05:00',
        'device_id': 'rapsberry-pi-monitor',
        'cpu': {
            'temperature': 90.0,  # High!
            'usage_percent': 98.0  # High!
        },
        'memory': {
            'percent': 95.0  # High!
        },
        'disk': {
            'percent': 60.0
        },
        'network': {
            'bytes_sent_mb': 100.0,
            'bytes_recv_mb': 200.0
        }
    }
    
    print("=== Testing Threshold Detector ===")
    threshold_detector = SimpleThresholdDetector()
    
    is_anomaly, violations = threshold_detector.detect(normal_data)
    print(f"Normal data: Anomaly={is_anomaly}, Violations={violations}")
    
    is_anomaly, violations = threshold_detector.detect(anomaly_data)
    print(f"Anomaly data: Anomaly={is_anomaly}, Violations={violations}")
    
    print("\n=== Testing ML Detector ===")
    ml_detector = AnomalyDetector()
    
    # Generate some training data
    training_data = []
    for i in range(50):
        data = {
            'timestamp': f'2024-01-01T{i:02d}:00:00',
            'device_id': 'rapsberry-pi-monitor',
            'cpu': {
                'temperature': 40.0 + np.random.randn() * 5,
                'usage_percent': 30.0 + np.random.randn() * 10
            },
            'memory': {
                'percent': 50.0 + np.random.randn() * 10
            },
            'disk': {
                'percent': 60.0 + np.random.randn() * 5
            },
            'network': {
                'bytes_sent_mb': 100.0 + np.random.randn() * 20,
                'bytes_recv_mb': 200.0 + np.random.randn() * 30
            }
        }
        training_data.append(data)
    
    # Train model
    ml_detector.train(training_data)
    
    # Test prediction
    is_anomaly, score = ml_detector.predict(normal_data)
    print(f"Normal data: Anomaly={is_anomaly}, Score={score:.3f}")
    
    is_anomaly, score = ml_detector.predict(anomaly_data)
    print(f"Anomaly data: Anomaly={is_anomaly}, Score={score:.3f}")


if __name__ == "__main__":
    main()
