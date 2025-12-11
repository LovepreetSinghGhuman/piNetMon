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
        # Get model directory from Azure ML environment variable
        model_dir = os.getenv('AZUREML_MODEL_DIR', '.')
        print(f"AZUREML_MODEL_DIR: {model_dir}")
        
        # Azure ML puts model files directly in AZUREML_MODEL_DIR
        # Structure: /var/azureml-app/azureml-models/<model-name>/<version>/
        # Our files should be directly there (flattened during upload)
        model_path = os.path.join(model_dir, 'model.pkl')
        scaler_path = os.path.join(model_dir, 'scaler.pkl')
        
        print(f"Looking for model at: {model_path}")
        print(f"Looking for scaler at: {scaler_path}")
        
        # Debug: List directory contents
        print(f"Contents of {model_dir}:")
        for root, dirs, files in os.walk(model_dir):
            level = root.replace(model_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            sub_indent = ' ' * 2 * (level + 1)
            for file in files:
                print(f"{sub_indent}{file}")
        
        # Check if files exist
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at: {model_path}")
        if not os.path.exists(scaler_path):
            raise FileNotFoundError(f"Scaler file not found at: {scaler_path}")
        
        print(f"✓ Found model.pkl ({os.path.getsize(model_path)} bytes)")
        print(f"✓ Found scaler.pkl ({os.path.getsize(scaler_path)} bytes)")
        
        # Load model
        print("Loading model...")
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        print(f"✓ Model loaded: {type(model)}")
        
        # Load scaler
        print("Loading scaler...")
        with open(scaler_path, 'rb') as f:
            scaler = pickle.load(f)
        print(f"✓ Scaler loaded: {type(scaler)}")
        
        print("✅ Initialization complete!")
        
    except Exception as e:
        print(f"❌ Error in init(): {e}")
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
