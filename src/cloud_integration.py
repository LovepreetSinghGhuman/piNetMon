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


# ===================================================================
#                           Azure IoT Client
# ===================================================================

class AzureIoTClient:
    """Manages Azure IoT Hub connection and communication."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.client: Optional[IoTHubDeviceClient] = None
        self.is_connected = False

        # Optional callbacks
        self.message_callback: Optional[Callable] = None
        self.method_callback: Optional[Callable] = None
        self.twin_patch_callback: Optional[Callable] = None

        logger.info("AzureIoTClient initialized")

    # ------------------------------- Connection -------------------------------

    async def connect(self):
        """Connect to Azure IoT Hub and register handlers."""
        try:
            self.client = IoTHubDeviceClient.create_from_connection_string(self.connection_string)
            await self.client.connect()

            self.client.on_message_received = self._handle_message
            self.client.on_method_request_received = self._handle_method_request
            self.client.on_twin_desired_properties_patch_received = self._handle_twin_patch

            self.is_connected = True
            logger.info("Connected to Azure IoT Hub")

        except Exception as e:
            logger.error(f"Failed to connect to Azure IoT Hub: {e}")
            self.is_connected = False
            raise

    async def disconnect(self):
        """Disconnect the device client."""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("Disconnected from Azure IoT Hub")

    # ---------------------------- Telemetry / Twin ----------------------------

    async def send_telemetry(self, data: Dict[str, Any]) -> bool:
        """Send JSON telemetry to IoT Hub."""
        if not self.is_connected:
            logger.warning("Telemetry drop: IoT Hub not connected")
            return False

        try:
            msg = Message(json.dumps(data))
            msg.content_type = "application/json"
            msg.content_encoding = "utf-8"

            # Useful metadata
            msg.custom_properties["deviceId"] = data.get("device_id", "unknown")
            msg.custom_properties["timestamp"] = data.get("timestamp", datetime.utcnow().isoformat())

            await self.client.send_message(msg)
            logger.info(f"Telemetry sent ({msg.custom_properties['timestamp']})")
            return True

        except Exception as e:
            logger.error(f"Failed to send telemetry: {e}")
            return False

    async def send_property_update(self, properties: Dict[str, Any]):
        """Update reported twin properties."""
        if not self.is_connected:
            logger.warning("Twin update ignored: IoT Hub not connected")
            return

        try:
            await self.client.patch_twin_reported_properties(properties)
            logger.info(f"Twin updated: {properties}")
        except Exception as e:
            logger.error(f"Failed to update twin properties: {e}")

    async def get_twin(self) -> Optional[Dict[str, Any]]:
        """Fetch device twin."""
        if not self.is_connected:
            logger.warning("Twin fetch ignored: IoT Hub not connected")
            return None

        try:
            return await self.client.get_twin()
        except Exception as e:
            logger.error(f"Failed to get twin: {e}")
            return None

    # ------------------------------ C2D Handlers ------------------------------

    async def _handle_message(self, message):
        """Handle cloud-to-device message."""
        try:
            data = json.loads(message.data.decode("utf-8"))
            logger.info(f"C2D message: {data}")

            if self.message_callback:
                await self.message_callback(data)

        except Exception as e:
            logger.error(f"Error handling C2D message: {e}")

    async def _handle_method_request(self, method_request):
        """Handle direct method calls from cloud."""
        try:
            name = method_request.name
            payload = method_request.payload
            logger.info(f"Method request: {name} | Payload: {payload}")

            if self.method_callback:
                result = await self.method_callback(name, payload)
                status, response_payload = 200, result
            else:
                status, response_payload = 404, {"error": "No handler registered"}

            response = MethodResponse.create_from_method_request(
                method_request, status, response_payload
            )
            await self.client.send_method_response(response)

        except Exception as e:
            logger.error(f"Error handling method request: {e}")
            response = MethodResponse.create_from_method_request(
                method_request, 500, {"error": str(e)}
            )
            await self.client.send_method_response(response)

    async def _handle_twin_patch(self, patch):
        """Handle desired properties updates."""
        try:
            logger.info(f"Twin patch received: {patch}")
            if self.twin_patch_callback:
                await self.twin_patch_callback(patch)
        except Exception as e:
            logger.error(f"Error handling twin patch: {e}")

    # ------------------------------ Registration ------------------------------

    def set_message_handler(self, callback: Callable):
        self.message_callback = callback
        logger.info("Registered C2D message handler")

    def set_method_handler(self, callback: Callable):
        self.method_callback = callback
        logger.info("Registered direct method handler")

    def set_twin_patch_handler(self, callback: Callable):
        self.twin_patch_callback = callback
        logger.info("Registered twin patch handler")


# ===================================================================
#                       Cloud Data Manager
# ===================================================================

class CloudDataManager:
    """Queues and uploads telemetry to Azure IoT Hub."""

    def __init__(self, iot_client: AzureIoTClient):
        self.iot = iot_client
        self.upload_queue = []
        self.max_queue_size = 100
        logger.info("CloudDataManager initialized")

    async def upload_sensor_data(self, data: Dict[str, Any]) -> bool:
        """Upload telemetry or queue it if offline."""
        if not self.iot.is_connected:
            if len(self.upload_queue) < self.max_queue_size:
                self.upload_queue.append(data)
                logger.warning(f"Queued telemetry ({len(self.upload_queue)})")
                return False

            logger.error("Upload queue full — telemetry dropped")
            return False

        success = await self.iot.send_telemetry(data)

        if success and self.upload_queue:
            await self._flush_queue()

        return success

    async def _flush_queue(self):
        """Send all queued messages once connected."""
        logger.info(f"Flushing {len(self.upload_queue)} queued messages")

        while self.upload_queue and self.iot.is_connected:
            data = self.upload_queue.pop(0)
            await self.iot.send_telemetry(data)
            await asyncio.sleep(0.1)

        logger.info("Queue flush complete")

    async def update_device_status(self, status: Dict[str, Any]):
        await self.iot.send_property_update(status)


# ===================================================================
#                           Test main()
# ===================================================================

async def main():
    """Run a simple standalone test of Azure IoT Hub communication."""
    config_path = "../config/config.json"

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        conn_str = config["azure"]["iot_hub"]["connection_string"]
    except Exception as e:
        logger.error(f"Config load failed: {e}")
        return

    client = AzureIoTClient(conn_str)

    try:
        await client.connect()
        cloud = CloudDataManager(client)

        test_data = {
            "timestamp": datetime.now().isoformat(),
            "device_id": "raspberry-pi",
            "cpu": {"temperature": 45.3, "usage_percent": 25.5},
            "memory": {"percent": 50.0},
        }

        await cloud.upload_sensor_data(test_data)
        await asyncio.sleep(2)

        await cloud.update_device_status({
            "status": "online",
            "version": "1.0.0",
            "last_update": datetime.now().isoformat(),
        })

        print("IoT Hub test completed.")

    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
