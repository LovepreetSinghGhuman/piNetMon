"""
Azure Function - IoT Hub Trigger
Processes telemetry data from Raspberry Pi and stores in Azure Storage/QuestDB
"""

import logging
import json
import azure.functions as func
from datetime import datetime


def main(event: func.EventHubEvent):
    """
    Process IoT Hub telemetry messages.
    
    Args:
        event: Event from IoT Hub (Event Hub compatible endpoint)
    """
    logging.info('IoT Hub trigger function processing message')
    
    try:
        # Get message body
        message_body = event.get_body().decode('utf-8')
        telemetry_data = json.loads(message_body)
        
        logging.info(f'Received telemetry from device: {telemetry_data.get("device_id")}')
        
        # Process the telemetry data
        processed_data = process_telemetry(telemetry_data)
        
        # Check for anomalies
        if processed_data.get('is_anomaly'):
            logging.warning(f'ANOMALY DETECTED: {processed_data}')
            # Could send alert here (email, SMS, etc.)
        
        # Store in Azure Storage Blob (required for cloud storage)
        store_to_blob(processed_data)
        
        # Store in QuestDB for time-series analytics
        store_to_questdb(processed_data)
        
        logging.info('Telemetry processed successfully')
        
    except Exception as e:
        logging.error(f'Error processing telemetry: {str(e)}')
        raise


def process_telemetry(telemetry_data: dict) -> dict:
    """
    Process and enrich telemetry data.
    
    Args:
        telemetry_data: Raw telemetry from IoT device
        
    Returns:
        Processed telemetry data
    """
    # Extract data
    timestamp = telemetry_data.get('timestamp', datetime.utcnow().isoformat())
    device_id = telemetry_data.get('device_id', 'unknown')
    
    # Get sensor readings
    cpu = telemetry_data.get('cpu', {})
    memory = telemetry_data.get('memory', {})
    disk = telemetry_data.get('disk', {})
    network = telemetry_data.get('network', {})
    
    # Get analysis results
    local_analysis = telemetry_data.get('local_analysis', {})
    cloud_analysis = telemetry_data.get('cloud_analysis', {})
    
    # Create processed data structure
    processed = {
        'id': f"{device_id}_{timestamp.replace(':', '-')}",
        'timestamp': timestamp,
        'device_id': device_id,
        'metrics': {
            'cpu_temperature': cpu.get('temperature'),
            'cpu_usage': cpu.get('usage_percent'),
            'cpu_frequency': cpu.get('frequency_mhz'),
            'memory_usage': memory.get('percent'),
            'memory_used_mb': memory.get('used_mb'),
            'disk_usage': disk.get('percent'),
            'disk_used_gb': disk.get('used_gb'),
            'network_sent_mb': network.get('bytes_sent_mb'),
            'network_recv_mb': network.get('bytes_recv_mb')
        },
        'is_anomaly': local_analysis.get('is_anomaly', False),
        'anomaly_score': local_analysis.get('ml_score', 0.0),
        'threshold_violations': local_analysis.get('threshold_violations', []),
        'cloud_available': cloud_analysis.get('available', False),
        'processed_at': datetime.utcnow().isoformat(),
        'partition_key': device_id,
        'row_key': timestamp
    }
    
    # Calculate health score (0-100)
    health_score = calculate_health_score(processed['metrics'])
    processed['health_score'] = health_score
    
    return processed


def calculate_health_score(metrics: dict) -> float:
    """
    Calculate overall system health score (0-100).
    
    Args:
        metrics: System metrics
        
    Returns:
        Health score between 0 and 100
    """
    score = 100.0
    
    # Deduct points for high resource usage
    cpu_usage = metrics.get('cpu_usage', 0)
    if cpu_usage > 80:
        score -= (cpu_usage - 80) * 0.5
    
    memory_usage = metrics.get('memory_usage', 0)
    if memory_usage > 80:
        score -= (memory_usage - 80) * 0.5
    
    disk_usage = metrics.get('disk_usage', 0)
    if disk_usage > 85:
        score -= (disk_usage - 85)
    
    # Deduct points for high temperature
    cpu_temp = metrics.get('cpu_temperature')
    if cpu_temp and cpu_temp > 70:
        score -= (cpu_temp - 70) * 0.3
    
    return max(0.0, min(100.0, score))


def store_to_blob(data: dict):
    """
    Store processed data to Azure Blob Storage.
    
    Args:
        data: Processed telemetry data
    """
    # This requires AZURE_STORAGE_CONNECTION_STRING in app settings
    try:
        from azure.storage.blob import BlobServiceClient
        import os
        
        connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        if not connection_string:
            logging.warning('Azure Storage connection string not configured')
            return
        
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_name = 'iot-telemetry'
        
        # Create container if it doesn't exist
        try:
            blob_service_client.create_container(container_name)
        except Exception:
            pass  # Container already exists
        
        # Create blob name with timestamp
        timestamp = data['timestamp'].replace(':', '-')
        device_id = data['device_id']
        blob_name = f"{device_id}/{timestamp}.json"
        
        # Upload data
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name
        )
        blob_client.upload_blob(json.dumps(data), overwrite=True)
        
        logging.info(f'Data stored to blob: {blob_name}')
        
    except Exception as e:
        logging.error(f'Failed to store to blob: {str(e)}')


def store_to_questdb(data: dict):
    """
    Store processed data to QuestDB for time-series analytics.
    
    Args:
        data: Processed telemetry data
    """
    # This requires QUESTDB_HOST and QUESTDB_PORT in app settings
    try:
        import requests
        import os
        
        questdb_host = os.environ.get('QUESTDB_HOST', 'localhost')
        questdb_port = os.environ.get('QUESTDB_PORT', '9000')
        
        # QuestDB uses InfluxDB Line Protocol for high-speed ingestion
        timestamp = data['timestamp']
        device_id = data['device_id']
        metrics = data['metrics']
        
        # Build InfluxDB line protocol message
        # Format: measurement,tag1=value1 field1=value1,field2=value2 timestamp
        fields = []
        for key, value in metrics.items():
            if value is not None:
                fields.append(f"{key}={value}")
        
        # Add additional fields
        fields.append(f"health_score={data['health_score']}")
        fields.append(f"is_anomaly={str(data['is_anomaly']).lower()}")
        fields.append(f"anomaly_score={data['anomaly_score']}")
        
        line = f"telemetry,device_id={device_id} {','.join(fields)}"
        
        # Send to QuestDB via HTTP
        url = f"http://{questdb_host}:{questdb_port}/write"
        response = requests.post(url, data=line)
        
        if response.status_code == 200:
            logging.info(f'Data stored to QuestDB for device: {device_id}')
        else:
            logging.error(f'QuestDB write failed: {response.status_code} - {response.text}')
        
    except Exception as e:
        logging.error(f'Failed to store to QuestDB: {str(e)}')
