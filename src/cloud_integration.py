"""
Azure IoT Hub Integration Module
Handles sending sensor data to Azure IoT Hub and receiving cloud-to-device messages.
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import logging
from azure.iot.device.aio import IoTHubDeviceClient
from azure.iot.device import Message, MethodResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AzureIoTClient:
    """Manages Azure IoT Hub connection and communication."""
    
    def __init__(self, connection_string: str):
        """
        Initialize Azure IoT Hub client.
        
        Args:
            connection_string: Device connection string for Azure IoT Hub
        """
        self.connection_string = connection_string
        self.client: Optional[IoTHubDeviceClient] = None
        self.is_connected = False
        self.message_callback: Optional[Callable] = None
        self.method_callback: Optional[Callable] = None
        self.twin_patch_callback: Optional[Callable] = None
        logger.info("AzureIoTClient initialized")
    
    async def connect(self):
        """Establish connection to Azure IoT Hub."""
        try:
            self.client = IoTHubDeviceClient.create_from_connection_string(
                self.connection_string
            )
            await self.client.connect()
            self.is_connected = True
            logger.info("Connected to Azure IoT Hub")
            
            # Set up message and method handlers
            self.client.on_message_received = self._handle_message
            self.client.on_method_request_received = self._handle_method_request
            self.client.on_twin_desired_properties_patch_received = self._handle_twin_patch
            
        except Exception as e:
            logger.error(f"Failed to connect to Azure IoT Hub: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """Disconnect from Azure IoT Hub."""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("Disconnected from Azure IoT Hub")
    
    async def send_telemetry(self, data: Dict[str, Any]) -> bool:
        """
        Send telemetry data to Azure IoT Hub.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected:
            logger.warning("Not connected to Azure IoT Hub")
            return False
        
        try:
            # Create message
            message = Message(json.dumps(data))
            message.content_type = "application/json"
            message.content_encoding = "utf-8"
            
            # Add custom properties
            message.custom_properties["deviceId"] = data.get('device_id', 'unknown')
            message.custom_properties["timestamp"] = data.get('timestamp', datetime.now().isoformat())
            
            # Send message
            await self.client.send_message(message)
            logger.info(f"Telemetry sent: {data.get('timestamp')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send telemetry: {e}")
            return False
    
    async def send_property_update(self, properties: Dict[str, Any]):
        """
        Update device twin reported properties.
        
        Args:
            properties: Properties to update
        """
        if not self.is_connected:
            logger.warning("Not connected to Azure IoT Hub")
            return
        
        try:
            await self.client.patch_twin_reported_properties(properties)
            logger.info(f"Updated twin properties: {properties}")
        except Exception as e:
            logger.error(f"Failed to update twin properties: {e}")
    
    async def _handle_message(self, message):
        """
        Handle cloud-to-device messages.
        
        Args:
            message: Received message from cloud
        """
        try:
            data = json.loads(message.data.decode('utf-8'))
            logger.info(f"Received message from cloud: {data}")
            
            if self.message_callback:
                await self.message_callback(data)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_method_request(self, method_request):
        """
        Handle direct method requests from cloud.
        
        Args:
            method_request: Method request from cloud
        """
        try:
            method_name = method_request.name
            payload = method_request.payload
            
            logger.info(f"Received method request: {method_name} with payload: {payload}")
            
            # Execute method if callback is set
            if self.method_callback:
                result = await self.method_callback(method_name, payload)
                status = 200
                response_payload = result
            else:
                status = 404
                response_payload = {"error": "No method handler registered"}
            
            # Send method response
            method_response = MethodResponse.create_from_method_request(
                method_request, status, response_payload
            )
            await self.client.send_method_response(method_response)
            
        except Exception as e:
            logger.error(f"Error handling method request: {e}")
            method_response = MethodResponse.create_from_method_request(
                method_request, 500, {"error": str(e)}
            )
            await self.client.send_method_response(method_response)
    
    def set_message_handler(self, callback: Callable):
        """
        Set callback for cloud-to-device messages.
        
        Args:
            callback: Async function to handle messages
        """
        self.message_callback = callback
        logger.info("Message handler registered")
    
    def set_method_handler(self, callback: Callable):
        """
        Set callback for direct method requests.
        
        Args:
            callback: Async function to handle method requests
        """
        self.method_callback = callback
        logger.info("Method handler registered")
    
    def set_twin_patch_handler(self, callback: Callable):
        """
        Set callback for device twin desired properties updates.
        
        Args:
            callback: Async function to handle twin patches
        """
        self.twin_patch_callback = callback
        logger.info("Twin patch handler registered")
    
    async def _handle_twin_patch(self, patch):
        """
        Handle device twin desired properties patch.
        
        Args:
            patch: Desired properties patch from cloud
        """
        try:
            logger.info(f"Received twin patch: {patch}")
            
            if self.twin_patch_callback:
                await self.twin_patch_callback(patch)
        except Exception as e:
            logger.error(f"Error handling twin patch: {e}")
    
    async def get_twin(self) -> Optional[Dict[str, Any]]:
        """
        Get the current device twin.
        
        Returns:
            dict: Device twin data or None
        """
        if not self.is_connected:
            logger.warning("Not connected to Azure IoT Hub")
            return None
        
        try:
            twin = await self.client.get_twin()
            return twin
        except Exception as e:
            logger.error(f"Failed to get twin: {e}")
            return None


class CloudDataManager:
    """Manages cloud data storage and synchronization."""
    
    def __init__(self, iot_client: AzureIoTClient):
        """
        Initialize cloud data manager.
        
        Args:
            iot_client: Azure IoT Hub client instance
        """
        self.iot_client = iot_client
        self.upload_queue = []
        self.max_queue_size = 100
        logger.info("CloudDataManager initialized")
    
    async def upload_sensor_data(self, data: Dict[str, Any]) -> bool:
        """
        Upload sensor data to cloud.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            bool: True if successful
        """
        # Add to queue if not connected
        if not self.iot_client.is_connected:
            if len(self.upload_queue) < self.max_queue_size:
                self.upload_queue.append(data)
                logger.warning(f"Added to queue (size: {len(self.upload_queue)})")
                return False
            else:
                logger.error("Upload queue full")
                return False
        
        # Send immediately if connected
        success = await self.iot_client.send_telemetry(data)
        
        # Try to flush queue if connected
        if success and self.upload_queue:
            await self._flush_queue()
        
        return success
    
    async def _flush_queue(self):
        """Upload queued data to cloud."""
        logger.info(f"Flushing queue with {len(self.upload_queue)} items")
        
        while self.upload_queue and self.iot_client.is_connected:
            data = self.upload_queue.pop(0)
            await self.iot_client.send_telemetry(data)
            await asyncio.sleep(0.1)  # Avoid overwhelming the service
        
        logger.info("Queue flushed successfully")
    
    async def update_device_status(self, status: Dict[str, Any]):
        """
        Update device status in cloud.
        
        Args:
            status: Device status information
        """
        await self.iot_client.send_property_update(status)


async def main():
    """Test Azure IoT Hub integration."""
    # Load configuration
    config_path = "../config/config.json"
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    connection_string = config['azure']['iot_hub']['connection_string']
    
    # Create client
    client = AzureIoTClient(connection_string)
    
    try:
        # Connect
        await client.connect()
        
        # Create cloud data manager
        cloud_manager = CloudDataManager(client)
        
        # Test data
        test_data = {
            'timestamp': datetime.now().isoformat(),
            'device_id': 'rapsberry-pi-monitor',
            'cpu': {
                'temperature': 45.3,
                'usage_percent': 25.5
            },
            'memory': {
                'percent': 50.0
            }
        }
        
        # Send test telemetry
        await cloud_manager.upload_sensor_data(test_data)
        
        # Wait a bit
        await asyncio.sleep(5)
        
        # Update device status
        await cloud_manager.update_device_status({
            'status': 'online',
            'version': '1.0.0',
            'last_update': datetime.now().isoformat()
        })
        
        print("Test completed successfully!")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
