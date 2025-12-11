"""
Scoring script for Azure ML endpoint
"""

import json
import numpy as np
import pickle
import os


def init():
    """Initialize the model."""
    global model, scaler
    
    try:
        # Load model and scaler from models directory
        model_dir = os.getenv('AZUREML_MODEL_DIR', '.')
        print(f"Model directory: {model_dir}")
        
        # List all files recursively to debug path structure
        for root, dirs, files in os.walk(model_dir):
            print(f"Directory: {root}")
            for file in files:
                print(f"  File: {file}")
        
        # Try multiple possible paths
        possible_paths = [
            (os.path.join(model_dir, 'pi-anomaly-detector', 'model.pkl'),
             os.path.join(model_dir, 'pi-anomaly-detector', 'scaler.pkl')),
            (os.path.join(model_dir, 'pi-anomaly-detector', 'models', 'model.pkl'),
             os.path.join(model_dir, 'pi-anomaly-detector', 'models', 'scaler.pkl')),
            (os.path.join(model_dir, 'model.pkl'),
             os.path.join(model_dir, 'scaler.pkl'))
        ]
        
        model_path = None
        scaler_path = None
        
        for m_path, s_path in possible_paths:
            if os.path.exists(m_path) and os.path.exists(s_path):
                model_path = m_path
                scaler_path = s_path
                print(f"Found model at: {model_path}")
                break
        
        if not model_path:
            raise FileNotFoundError(f"Could not find model files in {model_dir}")
        
        print(f"Loading model from: {model_path}")
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        
        print(f"Loading scaler from: {scaler_path}")
        with open(scaler_path, 'rb') as f:
            scaler = pickle.load(f)
        
        print("Model and scaler loaded successfully")
    except Exception as e:
        print(f"Error in init(): {e}")
        import traceback
        traceback.print_exc()
        raise


def run(raw_data):
    """
    Make predictions on input data.
    
    Expected input format:
    {
        "data": {
            "cpu_temperature": 45.0,
            "cpu_usage": 30.0,
            "memory_percent": 50.0,
            "disk_percent": 60.0,
            "network_sent": 100.0,
            "network_recv": 200.0
        }
    }
    """
    try:
        # Parse input
        data = json.loads(raw_data)
        input_data = data.get('data', data)
        
        # Extract features
        features = [
            input_data.get('cpu_temperature', 0) or 0,
            input_data.get('cpu_usage', 0),
            input_data.get('memory_percent', 0),
            input_data.get('disk_percent', 0),
            input_data.get('network_sent', 0),
            input_data.get('network_recv', 0)
        ]
        
        # Reshape and scale
        X = np.array(features).reshape(1, -1)
        X_scaled = scaler.transform(X)
        
        # Predict
        prediction = model.predict(X_scaled)[0]
        anomaly_score = -model.score_samples(X_scaled)[0]
        
        # Prepare response
        result = {
            'prediction': 'anomaly' if prediction == -1 else 'normal',
            'anomaly_score': float(anomaly_score),
            'confidence': float(min(1.0, max(0.0, 1.0 - anomaly_score / 5.0))),
            'is_anomaly': bool(prediction == -1)
        }
        
        return json.dumps(result)
        
    except Exception as e:
        error_msg = {
            'error': str(e),
            'prediction': 'error'
        }
        return json.dumps(error_msg)
