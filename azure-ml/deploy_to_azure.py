"""
Deploy model to Azure ML
Run this script after creating the ML workspace
"""

from azure.ai.ml import MLClient
from azure.ai.ml.entities import (
    ManagedOnlineEndpoint,
    ManagedOnlineDeployment,
    Model,
    Environment,
    CodeConfiguration
)
from azure.identity import DefaultAzureCredential

# Configuration
subscription_id = "921ad5d6-1557-439f-9b4a-b79c931b64d0"
resource_group = "CFAI"
workspace_name = "piAIModelCloud"

# Connect to workspace
credential = DefaultAzureCredential()
ml_client = MLClient(credential, subscription_id, resource_group, workspace_name)

print("Connected to Azure ML workspace")

# Register the model
print("Registering model...")
# Upload models directory and azure-ml code
model = Model(
    path="models",
    type="custom_model",
    name="pi-anomaly-detector",
    description="Anomaly detection model for Raspberry Pi monitoring"
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
        code="azure-ml",
        scoring_script="score.py"
    ),
    environment=Environment(
        conda_file="azure-ml/conda_env.yml",
        image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest"
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
print(f"\nEndpoint URL: {endpoint_details.scoring_uri}")
print(f"Primary Key: {ml_client.online_endpoints.get_keys(endpoint_name).primary_key}")

print("\n✅ Deployment complete!")
print("\nUpdate your cloud_ai_model.py with:")
print(f"  endpoint_url = '{endpoint_details.scoring_uri}'")
print(f"  api_key = '[YOUR_PRIMARY_KEY]'")
