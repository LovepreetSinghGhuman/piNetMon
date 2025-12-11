"""
Train and deploy an anomaly detection model to Azure ML
"""

import numpy as np
import pickle
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import json
import os

# Generate training data (simulating normal Raspberry Pi behavior)
np.random.seed(42)
n_samples = 1000

# Normal operating ranges
cpu_temp = np.random.normal(45, 5, n_samples)
cpu_usage = np.random.normal(30, 10, n_samples)
memory_usage = np.random.normal(50, 10, n_samples)
disk_usage = np.random.normal(60, 5, n_samples)
network_sent = np.random.normal(100, 20, n_samples)
network_recv = np.random.normal(200, 30, n_samples)

# Combine into training data
X_train = np.column_stack([
    cpu_temp,
    cpu_usage,
    memory_usage,
    disk_usage,
    network_sent,
    network_recv
])

# Add some anomalies (10%)
n_anomalies = 100
anomaly_indices = np.random.choice(n_samples, n_anomalies, replace=False)
X_train[anomaly_indices] += np.random.normal(30, 10, (n_anomalies, 6))

# Scale the data
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)

# Train Isolation Forest model
model = IsolationForest(
    contamination=0.1,
    random_state=42,
    n_estimators=100
)
model.fit(X_train_scaled)

# Save model and scaler in root models/ directory
script_dir = os.path.dirname(os.path.abspath(__file__))
models_dir = os.path.join(os.path.dirname(script_dir), 'models')
os.makedirs(models_dir, exist_ok=True)
model_path = os.path.join(models_dir, 'model.pkl')
scaler_path = os.path.join(models_dir, 'scaler.pkl')

with open(model_path, 'wb') as f:
    pickle.dump(model, f)

with open(scaler_path, 'wb') as f:
    pickle.dump(scaler, f)

print("Model trained and saved successfully!")
print(f"Model saved to: {model_path}")
print(f"Scaler saved to: {scaler_path}")
print(f"Training samples: {n_samples}")
print(f"Features: 6 (cpu_temp, cpu_usage, memory_usage, disk_usage, network_sent, network_recv)")
