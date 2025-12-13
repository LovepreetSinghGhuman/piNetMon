"""
Deploy model to Azure ML
Run this script after creating the ML workspace
"""
import os
from azure.ai.ml import MLClient
from azure.ai.ml.entities import (
    ManagedOnlineEndpoint,
    ManagedOnlineDeployment,
    Model,
    Environment,
    CodeConfiguration
)
from azure.identity import DefaultAzureCredential
import json

# Get paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
models_dir = os.path.join(project_root, "models")
config_path = os.path.join(project_root, "config", "config.json")

# Load configuration from config.json
with open(config_path, 'r') as f:
    config = json.load(f)

azure_config = config.get('azure', {})
subscription_id = azure_config.get('subscription_id')
ml_config = azure_config.get('ml', {})
resource_group = ml_config.get('resource_group')
workspace_name = ml_config.get('workspace_name')

if not all([subscription_id, resource_group, workspace_name]):
    raise ValueError("Missing required Azure ML configuration in config.json")

# Connect to workspace
credential = DefaultAzureCredential()
ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)

print("Connected to Azure ML workspace")

# Register the model - no flattening, just use models directory directly
print("Registering model...")

# Check which models exist
onnx_model = os.path.join(models_dir, "model.onnx")
onnx_scaler = os.path.join(models_dir, "scaler.onnx")
pkl_model = os.path.join(models_dir, "model.pkl")
pkl_scaler = os.path.join(models_dir, "scaler.pkl")

if os.path.exists(onnx_model) and os.path.exists(onnx_scaler):
    model_type = "onnx"
    print("Using ONNX models...")
elif os.path.exists(pkl_model) and os.path.exists(pkl_scaler):
    model_type = "pkl"
    print("Using PKL models...")
else:
    raise FileNotFoundError("No trained models found. Run 'python3 src/ai_models.py' first.")

# Register model using the models directory directly
model = Model(
    path=models_dir,
    type="custom_model",
    name="pi-anomaly-detector",
    description=f"Anomaly detection model ({model_type}) for Raspberry Pi monitoring"
)
registered_model = ml_client.models.create_or_update(model)
print(f"Model registered: {registered_model.name} version {registered_model.version}")

# Create endpoint
print("Creating endpoint...")
endpoint_name = "pi-anomaly-endpoint"
endpoint = ManagedOnlineEndpoint(
    name=endpoint_name,
    description="Endpoint for Raspberry Pi anomaly detection",
    auth_mode="key"
)

try:
    ml_client.online_endpoints.begin_create_or_update(endpoint).result()
    print(f"Endpoint created: {endpoint_name}")
except Exception as e:
    print(f"Endpoint might already exist: {e}")

# Create deployment
print("Creating deployment...")
deployment = ManagedOnlineDeployment(
    name="blue",
    endpoint_name=endpoint_name,
    model=registered_model.id,
    code_configuration=CodeConfiguration(
        code=script_dir,
        scoring_script="score.py"
    ),
    environment=Environment(
        conda_file=os.path.join(script_dir, "conda_env.yml"),
        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest"
    ),
    instance_type="Standard_DS2_v2",
    instance_count=1
)

ml_client.online_deployments.begin_create_or_update(deployment).result()
print("Deployment created successfully!")

# Set traffic to 100% for this deployment
endpoint.traffic = {"blue": 100}
ml_client.online_endpoints.begin_create_or_update(endpoint).result()

# Get endpoint details
endpoint_details = ml_client.online_endpoints.get(endpoint_name)
primary_key = ml_client.online_endpoints.get_keys(endpoint_name).primary_key

print(f"\n✅ Deployment complete!")
print(f"\nEndpoint URL: {endpoint_details.scoring_uri}")
print(f"Primary Key: {primary_key}")

print("\n📝 Update your config/config.json with:")
print(f'''
{{
  "ai_models": {{
    "cloud": {{
      "enabled": true,
      "endpoint": "{endpoint_details.scoring_uri}",
      "api_key": "{primary_key}"
    }}
  }}
}}
''')

print("\n💡 The cloud AI is accessed via the CloudAIService in src/ai_models.py")
print("   Enable/disable cloud AI from the dashboard or by updating device twin.")