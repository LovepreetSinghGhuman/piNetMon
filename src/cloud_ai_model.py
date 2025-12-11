"""
Cloud AI Model Integration
Connects to Azure Machine Learning endpoints for cloud-based predictions.
"""

import json
import requests
from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AzureMLClient:
    """Client for Azure Machine Learning REST API."""
    
    def __init__(self, endpoint_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Azure ML client.
        
        Args:
            endpoint_url: Azure ML endpoint URL
            api_key: API key for authentication
        """
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.is_configured = bool(endpoint_url and api_key)
        
        if not self.is_configured:
            logger.warning("Azure ML client not fully configured")
        else:
            logger.info("Azure ML client initialized")
    
    def predict(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Send data to Azure ML endpoint for prediction.
        
        Args:
            data: Input data for prediction
            
        Returns:
            dict: Prediction result or None if failed
        """
        if not self.is_configured:
            logger.warning("Azure ML client not configured")
            return None
        
        try:
            # Prepare request
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            }
            
            payload = json.dumps({'data': data})
            
            # Send request
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
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud prediction failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in cloud prediction: {e}")
            return None
    
    def health_check(self) -> bool:
        """
        Check if Azure ML endpoint is accessible.
        
        Returns:
            bool: True if endpoint is healthy
        """
        if not self.is_configured:
            return False
        
        try:
            # Simple GET request to check availability
            response = requests.get(self.endpoint_url, timeout=10)
            return response.status_code in [200, 405]  # 405 if GET not allowed but service is up
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class CloudAIService:
    """Service for cloud-based AI operations."""
    
    def __init__(self, ml_client: Optional[AzureMLClient] = None):
        """
        Initialize cloud AI service.
        
        Args:
            ml_client: Azure ML client instance
        """
        self.ml_client = ml_client
        self.prediction_cache = {}
        self.cache_enabled = True
        logger.info("CloudAIService initialized")
    
    @classmethod
    def from_config(cls, config: dict):
        """
        Create CloudAIService from configuration.
        
        Args:
            config: Configuration dictionary with Azure ML settings
        """
        ml_config = config.get('ai_models', {}).get('cloud', {})
        endpoint = ml_config.get('endpoint')
        api_key = ml_config.get('api_key')
        
        if endpoint and api_key:
            ml_client = AzureMLClient(endpoint, api_key)
            return cls(ml_client)
        else:
            # Use mock client if not configured
            ml_client = MockAzureMLClient()
            return cls(ml_client)
    
    def analyze_sensor_data(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze sensor data using cloud AI.
        
        Args:
            sensor_data: Sensor data dictionary
            
        Returns:
            dict: Analysis results with predictions
        """
        result = {
            'timestamp': sensor_data.get('timestamp'),
            'device_id': sensor_data.get('device_id'),
            'cloud_analysis': {
                'available': False,
                'prediction': None,
                'confidence': None,
                'recommendations': []
            }
        }
        
        # Check if cloud ML is available
        if not self.ml_client or not self.ml_client.is_configured:
            result['cloud_analysis']['available'] = False
            result['cloud_analysis']['recommendations'].append(
                "Cloud AI not configured - using local models only"
            )
            return result
        
        # Prepare data for cloud prediction
        features = {
            'cpu_temperature': sensor_data['cpu'].get('temperature'),
            'cpu_usage': sensor_data['cpu'].get('usage_percent'),
            'memory_percent': sensor_data['memory'].get('percent'),
            'disk_percent': sensor_data['disk'].get('percent'),
            'network_sent': sensor_data['network'].get('bytes_sent_mb'),
            'network_recv': sensor_data['network'].get('bytes_recv_mb')
        }
        
        # Get cloud prediction
        prediction_result = self.ml_client.predict(features)
        
        if prediction_result:
            result['cloud_analysis']['available'] = True
            result['cloud_analysis']['prediction'] = prediction_result.get('prediction')
            result['cloud_analysis']['confidence'] = prediction_result.get('confidence')
            
            # Generate recommendations based on prediction
            recommendations = self._generate_recommendations(sensor_data, prediction_result)
            result['cloud_analysis']['recommendations'] = recommendations
        
        return result
    
    def _generate_recommendations(self, sensor_data: Dict[str, Any], 
                                 prediction: Dict[str, Any]) -> list:
        """
        Generate actionable recommendations based on cloud predictions.
        
        Args:
            sensor_data: Current sensor data
            prediction: Cloud prediction results
            
        Returns:
            list: List of recommendation strings
        """
        recommendations = []
        
        # Check CPU
        cpu_temp = sensor_data['cpu'].get('temperature', 0)
        cpu_usage = sensor_data['cpu'].get('usage_percent', 0)
        
        if cpu_temp and cpu_temp > 70:
            recommendations.append("High CPU temperature detected - check cooling system")
        
        if cpu_usage > 80:
            recommendations.append("High CPU usage - consider optimizing processes")
        
        # Check memory
        memory_percent = sensor_data['memory'].get('percent', 0)
        if memory_percent > 80:
            recommendations.append("High memory usage - consider closing unused applications")
        
        # Check disk
        disk_percent = sensor_data['disk'].get('percent', 0)
        if disk_percent > 85:
            recommendations.append("Low disk space - clean up old files")
        
        # Add cloud-specific recommendations
        if prediction.get('prediction') == 'anomaly':
            recommendations.append("Cloud AI detected unusual pattern - investigate system behavior")
        
        return recommendations
    
    def batch_analyze(self, data_list: list) -> list:
        """
        Analyze multiple data points in batch.
        
        Args:
            data_list: List of sensor data dictionaries
            
        Returns:
            list: List of analysis results
        """
        results = []
        for data in data_list:
            result = self.analyze_sensor_data(data)
            results.append(result)
        
        logger.info(f"Batch analysis completed for {len(data_list)} samples")
        return results


class MockAzureMLClient:
    """Mock client for testing without actual Azure ML endpoint."""
    
    def __init__(self):
        """Initialize mock client."""
        self.is_configured = True
        logger.info("MockAzureMLClient initialized (for testing)")
    
    def predict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return mock prediction.
        
        Args:
            data: Input data
            
        Returns:
            dict: Mock prediction result
        """
        # Simple rule-based mock prediction
        cpu_temp = data.get('cpu_temperature', 0) or 0
        cpu_usage = data.get('cpu_usage', 0)
        memory_percent = data.get('memory_percent', 0)
        
        is_anomaly = (cpu_temp > 75) or (cpu_usage > 85) or (memory_percent > 85)
        
        return {
            'prediction': 'anomaly' if is_anomaly else 'normal',
            'confidence': 0.85 if is_anomaly else 0.92,
            'model_version': 'mock-v1.0'
        }
    
    def health_check(self) -> bool:
        """Mock health check - always returns True."""
        return True


def main():
    """Test cloud AI integration."""
    # Use mock client for testing
    mock_client = MockAzureMLClient()
    cloud_service = CloudAIService(mock_client)
    
    # Test data
    test_data = {
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
    
    print("=== Testing Cloud AI Service ===")
    result = cloud_service.analyze_sensor_data(test_data)
    print(json.dumps(result, indent=2))
    
    # Test with high values (anomaly)
    test_data['cpu']['temperature'] = 80.0
    test_data['cpu']['usage_percent'] = 95.0
    
    print("\n=== Testing with Anomaly Data ===")
    result = cloud_service.analyze_sensor_data(test_data)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
