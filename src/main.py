"""
Main Application - Raspberry Pi Network Monitor
Orchestrates all components: sensors, storage, AI models, and cloud integration.
"""

import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from typing import Dict, Any
import logging

# Add src directory to path
sys.path.insert(0, os.path.dirname(__file__))

from sensor_collector import SensorCollector
from questdb_storage import QuestDBStorage
from ai_models import AnomalyDetector, SimpleThresholdDetector, CloudAIService
from cloud_integration import AzureIoTClient, CloudDataManager
from mongodb_storage import MongoDBStorage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PiNetworkMonitor:
    """Main application class for Raspberry Pi Network Monitor."""
    
    def __init__(self, config_path: str = None):
        """
        Initialize the monitoring application.
        
        Args:
            config_path: Path to configuration file (if None, auto-detects)
        """
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, '..', 'config', 'config.json')
        
        self.config_path = config_path
        self.config = self._load_config()
        self.running = False
        
        # Initialize components
        self.sensor_collector = SensorCollector()
        
        # Initialize QuestDB for local time-series storage
        questdb_config = self.config.get('questdb', {})
        self.local_storage = QuestDBStorage(
            host=questdb_config.get('host', 'localhost'),
            port=questdb_config.get('port', 9000)
        )
        self.threshold_detector = SimpleThresholdDetector()
        self.ml_detector = AnomalyDetector()
        
        # AI control flags from config
        ai_config = self.config.get('ai_models', {})
        self.local_ai_enabled = ai_config.get('local', {}).get('anomaly_detection', {}).get('enabled', True)
        self.cloud_ai_enabled = ai_config.get('cloud', {}).get('enabled', False)
        self.anomaly_threshold = ai_config.get('local', {}).get('anomaly_detection', {}).get('threshold', 0.8)
        
        # Initialize cloud components
        self.iot_client: AzureIoTClient = None
        self.cloud_manager: CloudDataManager = None
        self.cloud_ai_service: CloudAIService = None
        self.mongodb_storage: MongoDBStorage = None
        
        # Statistics
        self.stats = {
            'total_readings': 0,
            'anomalies_detected': 0,
            'cloud_uploads': 0,
            'failed_uploads': 0,
            'start_time': datetime.now().isoformat()
        }
        
        logger.info("PiNetworkMonitor initialized")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    async def initialize_cloud(self):
        """Initialize cloud services."""
        try:
            connection_string = self.config['azure']['iot_hub']['connection_string']
            self.iot_client = AzureIoTClient(connection_string)
            await self.iot_client.connect()
            
            self.cloud_manager = CloudDataManager(self.iot_client)
            self.cloud_ai_service = CloudAIService.from_config(self.config)
            
            # Set up message and method handlers
            self.iot_client.set_message_handler(self._handle_cloud_message)
            self.iot_client.set_method_handler(self._handle_cloud_method)
            self.iot_client.set_twin_patch_handler(self._handle_twin_patch)
            
            # Report initial configuration to device twin
            await self._report_configuration()
            
            # Initialize MongoDB Atlas if enabled
            mongodb_config = self.config.get('mongodb', {})
            if mongodb_config.get('enabled', False):
                self.mongodb_storage = MongoDBStorage(
                    connection_string=mongodb_config.get('connection_string'),
                    database_name=mongodb_config.get('database', 'piNetMon'),
                    collection_name=mongodb_config.get('collection', 'sensor_data')
                )
            
            logger.info("Cloud services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize cloud services: {e}")
            logger.warning("Running in local-only mode")
    
    async def _handle_cloud_message(self, message: Dict[str, Any]):
        """
        Handle messages from cloud.
        
        Args:
            message: Message data from cloud
        """
        logger.info(f"Received cloud message: {message}")
        
        # Handle configuration updates
        if 'config_update' in message:
            self._update_configuration(message['config_update'])
        
        # Handle commands
        if 'command' in message:
            await self._execute_command(message['command'])
    
    async def _handle_cloud_method(self, method_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle direct method calls from cloud.
        
        Args:
            method_name: Name of the method
            payload: Method parameters
            
        Returns:
            dict: Method result
        """
        logger.info(f"Received method call: {method_name}")
        
        if method_name == "getConfig":
            # Return current configuration
            return {
                "status": "success",
                "config": self.config
            }
        
        elif method_name == "updateConfig":
            # Update configuration
            try:
                self._apply_config_update(payload)
                await self._report_configuration()
                return {
                    "status": "success",
                    "message": "Configuration updated",
                    "config": self.config
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": str(e)
                }
        
        elif method_name == "get_status":
            return self.get_status()
        
        elif method_name == "get_statistics":
            return self.stats
        
        elif method_name == "update_config":
            self._update_configuration(payload)
            return {"status": "success", "message": "Configuration updated"}
        
        elif method_name == "restart_monitoring":
            # Would restart the monitoring loop
            return {"status": "success", "message": "Restart requested"}
        
        else:
            return {"status": "error", "message": f"Unknown method: {method_name}"}
    
    def _update_configuration(self, updates: Dict[str, Any]):
        """
        Update configuration dynamically.
        
        Args:
            updates: Configuration updates
        """
        # Update thresholds if provided
        if 'thresholds' in updates:
            self.threshold_detector.update_thresholds(updates['thresholds'])
        
        # Update sensor intervals if provided
        if 'sensors' in updates:
            self.config['sensors'].update(updates['sensors'])
        
        logger.info(f"Configuration updated: {updates}")
    
    async def _handle_twin_patch(self, patch: Dict[str, Any]):
        """
        Handle device twin desired properties patch.
        
        Args:
            patch: Desired properties from Azure IoT Hub
        """
        logger.info(f"Received twin desired properties update: {patch}")
        
        try:
            # Apply configuration updates from twin
            self._apply_config_update(patch)
            
            # Report back the updated configuration
            await self._report_configuration()
            
            logger.info("Configuration updated from device twin")
        except Exception as e:
            logger.error(f"Failed to apply twin patch: {e}")
    
    def _apply_config_update(self, updates: Dict[str, Any]):
        """
        Apply configuration updates from device twin or direct method.
        
        Args:
            updates: Configuration updates
        """
        # Update sensors configuration
        if 'sensors' in updates:
            for sensor_name, sensor_config in updates['sensors'].items():
                if sensor_name in self.config['sensors']:
                    self.config['sensors'][sensor_name].update(sensor_config)
        
        # Update collection interval
        if 'collection_interval' in updates:
            self.config['collection_interval'] = updates['collection_interval']
        
        # Update AI model settings
        if 'ai_models' in updates:
            # Update local AI settings
            if 'local' in updates['ai_models']:
                local_config = updates['ai_models']['local']
                if 'enabled' in local_config:
                    self.local_ai_enabled = local_config['enabled']
                    logger.info(f"Local AI {'enabled' if self.local_ai_enabled else 'disabled'}")
                if 'anomaly_detection' in local_config:
                    anomaly_config = local_config['anomaly_detection']
                    if 'thresholds' in anomaly_config:
                        self.threshold_detector.update_thresholds(anomaly_config['thresholds'])
            
            # Update cloud AI settings
            if 'cloud' in updates['ai_models']:
                cloud_config = updates['ai_models']['cloud']
                if 'enabled' in cloud_config:
                    self.cloud_ai_enabled = cloud_config['enabled']
                    logger.info(f"Cloud AI {'enabled' if self.cloud_ai_enabled else 'disabled'}")
            
            # Update anomaly threshold
            if 'anomaly_threshold' in updates['ai_models']:
                self.anomaly_threshold = updates['ai_models']['anomaly_threshold']
                logger.info(f"Anomaly threshold updated to {self.anomaly_threshold}")
        
        # Save updated config to file
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
    
    async def _report_configuration(self):
        """Report current configuration to device twin reported properties."""
        if not self.iot_client or not self.iot_client.is_connected:
            return
        
        try:
            reported_props = {
                "configuration": {
                    "sensors": self.config.get('sensors', {}),
                    "collection_interval": self.config.get('collection_interval', 30),
                    "ai_models": {
                        "local": {
                            "anomaly_detection": {
                                "enabled": self.config.get('ai_models', {}).get('local', {}).get('anomaly_detection', {}).get('enabled', True),
                                "thresholds": self.threshold_detector.thresholds if hasattr(self, 'threshold_detector') else {}
                            }
                        }
                    }
                },
                "system_info": {
                    "python_version": sys.version,
                    "os": sys.platform,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            await self.iot_client.send_property_update(reported_props)
            logger.info("Configuration reported to device twin")
        except Exception as e:
            logger.error(f"Failed to report configuration: {e}")
    
    async def _execute_command(self, command: str):
        """
        Execute a command from cloud.
        
        Args:
            command: Command to execute
        """
        logger.info(f"Executing command: {command}")
        
        if command == "collect_now":
            await self.collect_and_process()
        
        elif command == "cleanup_old_data":
            logger.info("Cleanup command received - QuestDB handles retention automatically")
        
        elif command == "retrain_model":
            # Get recent data and retrain
            recent_data = self.local_storage.get_recent_data(hours=168)  # 7 days
            if recent_data and recent_data.get('dataset') and len(recent_data['dataset']) >= 10:
                training_data = self._convert_db_to_sensor_format(recent_data)
                try:
                    self.ml_detector.train(training_data)
                    logger.info(f"Model retrained with {len(training_data)} samples")
                except Exception as e:
                    logger.error(f"Model retraining failed: {e}")
    
    def _convert_db_to_sensor_format(self, db_result: dict) -> list:
        """Convert QuestDB query results to sensor data format."""
        if not db_result or 'dataset' not in db_result:
            return []
        
        columns = db_result.get('columns', [])
        dataset = db_result.get('dataset', [])
        
        # Create column index map with safe defaults
        col_map = {col['name']: i for i, col in enumerate(columns)}
        
        sensor_data_list = []
        for row in dataset:
            try:
                data = {
                    'timestamp': row[col_map.get('timestamp', 0)],
                    'device_id': row[col_map.get('device_id', 1)],
                    'cpu': {
                        'temperature': row[col_map.get('cpu_temperature', 2)],
                        'usage_percent': row[col_map.get('cpu_usage', 3)]
                    },
                    'memory': {
                        'percent': row[col_map.get('memory_percent', 4)]
                    },
                    'disk': {
                        'percent': row[col_map.get('disk_percent', 5)]
                    },
                    'network': {
                        'bytes_sent_mb': row[col_map.get('network_sent_mb', 6)],
                        'bytes_recv_mb': row[col_map.get('network_recv_mb', 7)]
                    }
                }
                sensor_data_list.append(data)
            except (IndexError, KeyError) as e:
                logger.warning(f"Skipping malformed row: {e}")
                continue
        
        return sensor_data_list
    
    async def collect_and_process(self):
        """Collect sensor data and process it through all stages."""
        try:
            # Collect sensor data
            sensor_data = self.sensor_collector.collect_all_data()
            self.stats['total_readings'] += 1
            
            # Threshold-based detection
            is_threshold_anomaly, violations = self.threshold_detector.detect(sensor_data)
            
            # ML-based detection (only if local AI is enabled)
            is_ml_anomaly, ml_score = False, 0.0
            if self.local_ai_enabled:
                try:
                    is_ml_anomaly, ml_score = self.ml_detector.predict(sensor_data)
                except Exception as ml_error:
                    # Model not trained yet - train it with initial data
                    logger.info(f"ML model not ready ({ml_error}). Training with initial data...")
                    recent_data = self.local_storage.get_recent_data(hours=24)
                    
                    if recent_data and recent_data.get('dataset') and len(recent_data['dataset']) >= 10:
                        training_data = self._convert_db_to_sensor_format(recent_data)
                        try:
                            self.ml_detector.train(training_data)
                            is_ml_anomaly, ml_score = self.ml_detector.predict(sensor_data)
                        except Exception as train_error:
                            logger.warning(f"ML training failed: {train_error}. Using threshold only.")
            else:
                logger.debug("Local AI disabled, skipping ML detection")
            
            is_anomaly = bool(is_threshold_anomaly or is_ml_anomaly)
            
            if is_anomaly:
                self.stats['anomalies_detected'] += 1
                logger.warning(f"Anomaly detected - Threshold: {is_threshold_anomaly}, ML: {is_ml_anomaly}")
            
            # Store locally in QuestDB
            self.local_storage.save_sensor_data(
                sensor_data,
                anomaly_score=float(ml_score),
                is_anomaly=is_anomaly
            )
            
            # Cloud AI analysis (only if cloud AI is enabled)
            cloud_analysis = None
            if self.cloud_ai_enabled and self.cloud_ai_service:
                cloud_analysis = self.cloud_ai_service.analyze_sensor_data(sensor_data)
            elif not self.cloud_ai_enabled:
                logger.debug("Cloud AI disabled, skipping cloud analysis")
            
            # Upload to cloud
            if self.cloud_manager:
                upload_data = {
                    **sensor_data,
                    'local_analysis': {
                        'is_anomaly': is_anomaly,
                        'ml_score': float(ml_score),
                        'threshold_violations': violations
                    }
                }
                if cloud_analysis:
                    upload_data['cloud_analysis'] = cloud_analysis['cloud_analysis']
                
                success = await self.cloud_manager.upload_sensor_data(upload_data)
                if success:
                    self.stats['cloud_uploads'] += 1
                else:
                    self.stats['failed_uploads'] += 1
            
            # Store in MongoDB Atlas if enabled
            if self.mongodb_storage and self.mongodb_storage.is_connected:
                mongodb_data = {
                    **sensor_data,
                    'local_analysis': {
                        'is_anomaly': is_anomaly,
                        'ml_score': float(ml_score),
                        'threshold_violations': violations
                    }
                }
                if cloud_analysis:
                    mongodb_data['cloud_analysis'] = cloud_analysis['cloud_analysis']
                
                self.mongodb_storage.store_sensor_data(mongodb_data)
            
        except Exception as e:
            logger.error(f"Error in collect_and_process: {e}")
    
    async def monitoring_loop(self, interval: int = 60):
        """
        Main monitoring loop.
        
        Args:
            interval: Seconds between collections
        """
        logger.info(f"Starting monitoring loop (interval: {interval}s)")
        self.running = True
        
        while self.running:
            try:
                await self.collect_and_process()
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Monitoring interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current application status."""
        storage_stats = self.local_storage.get_statistics()
        uptime = (datetime.now() - datetime.fromisoformat(self.stats['start_time'])).total_seconds()
        
        return {
            'running': self.running,
            'statistics': self.stats,
            'storage': storage_stats,
            'cloud_connected': self.iot_client.is_connected if self.iot_client else False,
            'uptime_seconds': uptime
        }
    
    async def shutdown(self):
        """Gracefully shutdown the application."""
        logger.info("Shutting down...")
        self.running = False
        
        if self.iot_client:
            await self.iot_client.disconnect()
        
        if self.mongodb_storage:
            self.mongodb_storage.disconnect()
        
        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    print("=" * 50)
    print("Raspberry Pi Network Monitor")
    print("=" * 50)
    
    # Initialize application
    monitor = PiNetworkMonitor()
    
    # Initialize cloud services
    await monitor.initialize_cloud()
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Signal received, shutting down...")
        asyncio.create_task(monitor.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Display initial status
    status = monitor.get_status()
    print(f"\nStatus: {json.dumps(status, indent=2)}")
    
    print("\nStarting monitoring...")
    print("Press Ctrl+C to stop\n")
    
    # Start monitoring loop
    interval = monitor.config['sensors']['cpu']['interval_seconds']
    await monitor.monitoring_loop(interval=interval)
    
    # Cleanup
    await monitor.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication stopped by user")
