"""
QuestDB Storage Module
Handles local time-series storage of sensor data using QuestDB.
"""

import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuestDBStorage:
    """Manages local time-series storage using QuestDB."""
    
    def __init__(self, host: str = "localhost", port: int = 9000):
        """
        Initialize QuestDB storage.
        
        Args:
            host: QuestDB host address
            port: QuestDB HTTP port (default 9000)
        """
        self.host = host
        self.port = port
        self.write_url = f"http://{host}:{port}/write"
        self.query_url = f"http://{host}:{port}/exec"
        
        # Test connection
        self._test_connection()
        logger.info(f"QuestDBStorage initialized: {host}:{port}")
    
    def _test_connection(self):
        """Test connection to QuestDB and ensure table exists."""
        try:
            # Skip the root endpoint test, go directly to exec endpoint
            # This avoids timeout issues while still verifying QuestDB is accessible
            test_query = "SELECT 1"
            response = requests.get(self.query_url, params={'query': test_query}, timeout=15)
            if response.status_code == 200:
                logger.info("Successfully connected to QuestDB")
                # Ensure table exists
                self._ensure_table_exists()
            else:
                logger.warning(f"QuestDB responded with status {response.status_code}")
        except Exception as e:
            logger.warning(f"QuestDB connection test failed: {e}")
            logger.info("Will attempt to create table on first write")
    
    def _ensure_table_exists(self):
        """Ensure sensor_data table exists in QuestDB."""
        try:
            # Check if table exists by querying it
            check_sql = "SELECT count(*) FROM sensor_data LIMIT 1"
            response = requests.get(self.query_url, params={'query': check_sql}, timeout=5)
            
            if response.status_code == 200:
                logger.info("Table 'sensor_data' already exists")
                return
            
            # Table doesn't exist, create it
            create_sql = """
                CREATE TABLE IF NOT EXISTS sensor_data (
                    device_id SYMBOL,
                    cpu_temperature DOUBLE,
                    cpu_usage DOUBLE,
                    cpu_frequency DOUBLE,
                    memory_total_mb DOUBLE,
                    memory_used_mb DOUBLE,
                    memory_percent DOUBLE,
                    disk_total_gb DOUBLE,
                    disk_used_gb DOUBLE,
                    disk_percent DOUBLE,
                    network_sent_mb DOUBLE,
                    network_recv_mb DOUBLE,
                    anomaly_score DOUBLE,
                    is_anomaly BOOLEAN,
                    timestamp TIMESTAMP
                ) timestamp(timestamp) PARTITION BY DAY;
            """
            
            response = requests.get(self.query_url, params={'query': create_sql}, timeout=10)
            if response.status_code == 200:
                logger.info("Created table 'sensor_data'")
            else:
                logger.warning(f"Could not create table: {response.text}")
                
        except Exception as e:
            logger.debug(f"Table check/creation skipped: {e}")
    
    def save_sensor_data(self, data: Dict[str, Any], anomaly_score: Optional[float] = None, 
                        is_anomaly: bool = False) -> bool:
        """
        Save sensor data to QuestDB using InfluxDB Line Protocol.
        
        Args:
            data: Sensor data dictionary
            anomaly_score: Optional anomaly detection score
            is_anomaly: Whether data point is anomalous
            
        Returns:
            bool: Success status
        """
        try:
            device_id = data.get('device_id', 'unknown')
            
            # Extract metrics
            cpu = data.get('cpu', {})
            memory = data.get('memory', {})
            disk = data.get('disk', {})
            network = data.get('network', {})
            
            # Build InfluxDB line protocol message
            # Format: measurement,tag1=value1 field1=value1,field2=value2 timestamp
            fields = []
            
            # CPU metrics
            if cpu.get('temperature') is not None:
                fields.append(f"cpu_temperature={cpu['temperature']}")
            if cpu.get('usage_percent') is not None:
                fields.append(f"cpu_usage={cpu['usage_percent']}")
            if cpu.get('frequency_mhz') is not None:
                fields.append(f"cpu_frequency={cpu['frequency_mhz']}")
            
            # Memory metrics
            if memory.get('total_mb') is not None:
                fields.append(f"memory_total_mb={memory['total_mb']}")
            if memory.get('used_mb') is not None:
                fields.append(f"memory_used_mb={memory['used_mb']}")
            if memory.get('percent') is not None:
                fields.append(f"memory_percent={memory['percent']}")
            
            # Disk metrics
            if disk.get('total_gb') is not None:
                fields.append(f"disk_total_gb={disk['total_gb']}")
            if disk.get('used_gb') is not None:
                fields.append(f"disk_used_gb={disk['used_gb']}")
            if disk.get('percent') is not None:
                fields.append(f"disk_percent={disk['percent']}")
            
            # Network metrics
            if network.get('bytes_sent_mb') is not None:
                fields.append(f"network_sent_mb={network['bytes_sent_mb']}")
            if network.get('bytes_recv_mb') is not None:
                fields.append(f"network_recv_mb={network['bytes_recv_mb']}")
            
            # Anomaly information
            if anomaly_score is not None:
                fields.append(f"anomaly_score={anomaly_score}")
            fields.append(f"is_anomaly={str(is_anomaly).lower()}")
            
            # Create line protocol message
            line = f"sensor_data,device_id={device_id} {','.join(fields)}"
            
            # Send to QuestDB
            response = requests.post(self.write_url, data=line, timeout=5)
            
            # InfluxDB Line Protocol returns 204 No Content on success
            if response.status_code in [200, 204]:
                logger.debug(f"Data saved to QuestDB for device: {device_id}")
                return True
            else:
                logger.error(f"QuestDB write failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to save to QuestDB: {e}")
            return False
    
    def query(self, sql: str) -> Optional[Dict[str, Any]]:
        """
        Execute SQL query against QuestDB.
        
        Args:
            sql: SQL query string
            
        Returns:
            dict: Query results or None on error
        """
        try:
            params = {'query': sql}
            response = requests.get(self.query_url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Query failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Query error: {e}")
            return None
    
    def get_recent_data(self, hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        Retrieve recent sensor data.
        
        Args:
            hours: Number of hours of data to retrieve
            
        Returns:
            dict: Query results or empty result if table doesn't exist
        """
        sql = f"""
            SELECT * FROM sensor_data 
            WHERE timestamp > dateadd('h', -{hours}, now())
            ORDER BY timestamp DESC
        """
        result = self.query(sql)
        
        # Return empty dataset if table doesn't exist yet
        if result is None:
            return {'dataset': [], 'count': 0}
        
        return result
    
    def get_anomalies(self, hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        Retrieve anomalous data points.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            dict: Query results
        """
        sql = f"""
            SELECT * FROM sensor_data 
            WHERE timestamp > dateadd('h', -{hours}, now())
            AND is_anomaly = true
            ORDER BY timestamp DESC
        """
        return self.query(sql)
    
    def get_statistics(self) -> Optional[Dict[str, Any]]:
        """
        Get storage statistics.
        
        Returns:
            dict: Storage statistics
        """
        sql = """
            SELECT 
                count(*) as total_records,
                sum(CASE WHEN is_anomaly = true THEN 1 ELSE 0 END) as anomaly_count,
                min(timestamp) as oldest_record,
                max(timestamp) as newest_record,
                avg(cpu_temperature) as avg_cpu_temp,
                avg(cpu_usage) as avg_cpu_usage,
                avg(memory_percent) as avg_memory_usage
            FROM sensor_data
        """
        result = self.query(sql)
        
        # Return empty stats if table doesn't exist yet
        if result is None:
            return {
                'dataset': [],
                'count': 0,
                'columns': ['total_records', 'anomaly_count', 'oldest_record', 'newest_record', 
                           'avg_cpu_temp', 'avg_cpu_usage', 'avg_memory_usage']
            }
        
        return result


def main():
    """Test QuestDB storage functionality."""
    storage = QuestDBStorage()
    
    # Test data
    test_data = {
        'timestamp': datetime.now().isoformat(),
        'device_id': 'raspberry-pi-monitor',
        'cpu': {
            'temperature': 45.3,
            'usage_percent': 25.5,
            'frequency_mhz': 1500.0
        },
        'memory': {
            'total_mb': 1024.0,
            'used_mb': 512.0,
            'percent': 50.0
        },
        'disk': {
            'total_gb': 128.0,
            'used_gb': 64.0,
            'percent': 50.0
        },
        'network': {
            'bytes_sent_mb': 100.5,
            'bytes_recv_mb': 250.3
        }
    }
    
    # Save test data
    success = storage.save_sensor_data(test_data, anomaly_score=0.15, is_anomaly=False)
    print(f"\nData save {'successful' if success else 'failed'}")
    
    # Get statistics
    stats = storage.get_statistics()
    print("\n=== Storage Statistics ===")
    if stats:
        print(stats)
    else:
        print("Failed to retrieve statistics")


if __name__ == "__main__":
    main()
