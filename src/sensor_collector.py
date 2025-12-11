"""
Sensor Data Collection Module
Collects data from Raspberry Pi sensors including CPU, memory, temperature, and network stats.
"""

import psutil
import time
import json
from datetime import datetime
from typing import Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SensorCollector:
    """Collects various system metrics from the Raspberry Pi."""
    
    def __init__(self):
        """Initialize the sensor collector."""
        self.start_time = datetime.now()
        logger.info("SensorCollector initialized")
    
    def get_cpu_temperature(self) -> float:
        """
        Get CPU temperature in Celsius.
        
        Returns:
            float: CPU temperature in Celsius, or None if unavailable
        """
        try:
            # Try reading from thermal zone (Raspberry Pi)
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                return round(temp, 2)
        except Exception as e:
            logger.warning(f"Could not read CPU temperature: {e}")
            return None
    
    def get_cpu_usage(self) -> Dict[str, float]:
        """
        Get CPU usage statistics.
        
        Returns:
            dict: CPU usage percentages
        """
        cpu_percent = psutil.cpu_percent(interval=1, percpu=False)
        cpu_freq = psutil.cpu_freq()
        
        return {
            'usage_percent': round(cpu_percent, 2),
            'frequency_mhz': round(cpu_freq.current, 2) if cpu_freq else None,
            'core_count': psutil.cpu_count()
        }
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get memory usage statistics.
        
        Returns:
            dict: Memory usage information
        """
        memory = psutil.virtual_memory()
        
        return {
            'total_mb': round(memory.total / (1024 * 1024), 2),
            'available_mb': round(memory.available / (1024 * 1024), 2),
            'used_mb': round(memory.used / (1024 * 1024), 2),
            'percent': round(memory.percent, 2)
        }
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """
        Get disk usage statistics.
        
        Returns:
            dict: Disk usage information
        """
        disk = psutil.disk_usage('/')
        
        return {
            'total_gb': round(disk.total / (1024 ** 3), 2),
            'used_gb': round(disk.used / (1024 ** 3), 2),
            'free_gb': round(disk.free / (1024 ** 3), 2),
            'percent': round(disk.percent, 2)
        }
    
    def get_network_stats(self) -> Dict[str, Any]:
        """
        Get network statistics.
        
        Returns:
            dict: Network statistics
        """
        net_io = psutil.net_io_counters()
        
        return {
            'bytes_sent_mb': round(net_io.bytes_sent / (1024 * 1024), 2),
            'bytes_recv_mb': round(net_io.bytes_recv / (1024 * 1024), 2),
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'errors_in': net_io.errin,
            'errors_out': net_io.errout
        }
    
    def collect_all_data(self) -> Dict[str, Any]:
        """
        Collect all sensor data.
        
        Returns:
            dict: Complete sensor data reading
        """
        timestamp = datetime.now().isoformat()
        
        data = {
            'timestamp': timestamp,
            'device_id': 'rapsberry-pi-monitor',
            'cpu': {
                'temperature': self.get_cpu_temperature(),
                **self.get_cpu_usage()
            },
            'memory': self.get_memory_usage(),
            'disk': self.get_disk_usage(),
            'network': self.get_network_stats()
        }
        
        logger.info(f"Collected sensor data at {timestamp}")
        return data
    
    def collect_data_json(self) -> str:
        """
        Collect all sensor data and return as JSON string.
        
        Returns:
            str: JSON string of sensor data
        """
        data = self.collect_all_data()
        return json.dumps(data, indent=2)


def main():
    """Main function to test sensor collection."""
    collector = SensorCollector()
    
    print("=== Raspberry Pi Network Monitor ===")
    print("Collecting sensor data...\n")
    
    # Collect data once
    data = collector.collect_all_data()
    print(json.dumps(data, indent=2))
    
    print("\n=== Continuous monitoring (Ctrl+C to stop) ===")
    try:
        while True:
            data = collector.collect_all_data()
            print(f"\n[{data['timestamp']}]")
            print(f"CPU: {data['cpu']['usage_percent']}% | Temp: {data['cpu']['temperature']}°C")
            print(f"Memory: {data['memory']['percent']}% ({data['memory']['used_mb']}/{data['memory']['total_mb']} MB)")
            print(f"Disk: {data['disk']['percent']}% ({data['disk']['used_gb']}/{data['disk']['total_gb']} GB)")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


if __name__ == "__main__":
    main()
