"""
Scoring script for Azure ML endpoint
"""

import json
import numpy as np
import pickle
import os


def init():
    """Initialize the model."""
    global model, scaler, use_onnx
    
    try:
        # Get model directory
        model_dir = os.getenv('AZUREML_MODEL_DIR', '.')
        print(f"AZUREML_MODEL_DIR: {model_dir}")
        
        # List all files recursively to find models
        print(f"Searching for models in {model_dir}:")
        model_files = []
        for root, dirs, files in os.walk(model_dir):
            for file in files:
                if file.endswith(('.onnx', '.pkl')):
                    full_path = os.path.join(root, file)
                    model_files.append(full_path)
                    print(f"  Found: {full_path}")
        
        # Find ONNX models
        onnx_model_path = next((f for f in model_files if f.endswith('model.onnx')), None)
        onnx_scaler_path = next((f for f in model_files if f.endswith('scaler.onnx')), None)
        
        # Find PKL models
        pkl_model_path = next((f for f in model_files if f.endswith('model.pkl')), None)
        pkl_scaler_path = next((f for f in model_files if f.endswith('scaler.pkl')), None)
        
        if onnx_model_path and onnx_scaler_path:
            # Use ONNX
            print("Loading ONNX models...")
            import onnxruntime as ort
            
            model = ort.InferenceSession(onnx_model_path)
            scaler = ort.InferenceSession(onnx_scaler_path)
            use_onnx = True
            
            print(f"✓ ONNX Model loaded from {onnx_model_path}")
            print(f"✓ ONNX Scaler loaded from {onnx_scaler_path}")
            
        elif pkl_model_path and pkl_scaler_path:
            # Use PKL
            print("Loading PKL models...")
            
            with open(pkl_model_path, 'rb') as f:
                model = pickle.load(f)
            with open(pkl_scaler_path, 'rb') as f:
                scaler = pickle.load(f)
            use_onnx = False
            
            print(f"✓ PKL Model loaded: {type(model)}")
            print(f"✓ PKL Scaler loaded: {type(scaler)}")
        else:
            raise FileNotFoundError(
                f"No models found in {model_dir}. Found files: {model_files}"
            )
        
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
            input_data.get('cpu_usage', 0) or 0,
            input_data.get('memory_percent', 0) or 0,
            input_data.get('disk_percent', 0) or 0,
            input_data.get('network_sent', 0) or 0,
            input_data.get('network_recv', 0) or 0
        ]
        
        # Reshape
        X = np.array(features, dtype=np.float32).reshape(1, -1)
        
        if use_onnx:
            # ONNX inference
            scaler_input_name = scaler.get_inputs()[0].name
            X_scaled = scaler.run(None, {scaler_input_name: X})[0]
            
            model_input_name = model.get_inputs()[0].name
            outputs = model.run(None, {model_input_name: X_scaled})
            
            prediction = outputs[0][0]
            anomaly_score = -outputs[1][0][0]
        else:
            # PKL inference
            X_scaled = scaler.transform(X)
            prediction = model.predict(X_scaled)[0]
            anomaly_score = -model.score_samples(X_scaled)[0]
        
        # Prepare response
        result = {
            'prediction': 'anomaly' if prediction == -1 else 'normal',
            'anomaly_score': float(anomaly_score),
            'confidence': float(min(1.0, max(0.0, 1.0 - anomaly_score / 5.0))),
            'is_anomaly': bool(prediction == -1),
            'model_type': 'onnx' if use_onnx else 'pkl'
        }
        
        return json.dumps(result)
        
    except Exception as e:
        import traceback
        error_msg = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'prediction': 'error'
        }
        return json.dumps(error_msg)
