import psutil
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SensorCollector:
        def scan_network(self, subnet: str = "192.168.1.0/24") -> list:
            """
            Scan the local network for reachable devices using ping.
            Args:
                subnet: The subnet to scan (CIDR notation, e.g., '192.168.1.0/24')
            Returns:
                List of dicts: [{"ip": ..., "mac": ...}, ...]
            """
            import ipaddress
            import platform
            import subprocess
            import re
            devices = []
            import socket
            try:
                net = ipaddress.ip_network(subnet, strict=False)
                for ip in net.hosts():
                    ip_str = str(ip)
                    # Ping the IP
                    if platform.system().lower() == "windows":
                        ping_cmd = ["ping", "-n", "1", "-w", "500", ip_str]
                    else:
                        ping_cmd = ["ping", "-c", "1", "-W", "1", ip_str]
                    result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if result.returncode == 0:
                        # Try to get MAC address (arp)
                        if platform.system().lower() == "windows":
                            arp_cmd = ["arp", "-a", ip_str]
                            arp_out = subprocess.run(arp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            match = re.search(r"([0-9a-fA-F]{2}(-[0-9a-fA-F]{2}){5})", arp_out.stdout.decode())
                            mac = match.group(1) if match else None
                        else:
                            arp_cmd = ["arp", "-n", ip_str]
                            arp_out = subprocess.run(arp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            match = re.search(r"([0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5})", arp_out.stdout.decode())
                            mac = match.group(1) if match else None
                        # Try to get hostname
                        try:
                            name = socket.gethostbyaddr(ip_str)[0]
                        except Exception:
                            name = None
                        devices.append({"ip": ip_str, "mac": mac, "name": name})
            except Exception as e:
                logger.error(f"Network scan failed: {e}")
            return devices
        
def __init__(self, enabled_sensors: Optional[Dict[str, bool]] = None):
    """
    Initialize the sensor collector.
    
    Args:
        enabled_sensors: Dictionary of sensor names and their enabled status.
                        Example: {'temperature': True, 'cpu': True, 'memory': False}
                        If None, all sensors are enabled by default.
    """
    self.start_time = datetime.now()
    self.enabled_sensors = enabled_sensors or {
        'temperature': True,
        'cpu': True,
        'memory': True,
        'disk': True,
        'network': True
    }
    logger.info(f"SensorCollector initialized with enabled sensors: {self.enabled_sensors}")

def update_enabled_sensors(self, enabled_sensors: Dict[str, bool]):
    """
    Update which sensors are enabled.
    
    Args:
        enabled_sensors: Dictionary of sensor names and their enabled status
    """
    self.enabled_sensors.update(enabled_sensors)
    logger.info(f"Updated enabled sensors: {self.enabled_sensors}")

def get_cpu_temperature(self) -> Optional[float]:
    """
    Get CPU temperature from thermal zone.
    
    Returns:
        float: Temperature in Celsius, or None if unavailable
    """
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = float(f.read().strip()) / 1000.0
            return round(temp, 2)
    except FileNotFoundError:
        logger.warning("Temperature sensor not found")
        return None
    except Exception as e:
        logger.error(f"Error reading temperature: {e}")
        return None

def get_cpu_usage(self) -> Dict[str, Any]:
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
    Collect enabled sensor data only.
    
    Returns:
        dict: Sensor data for enabled sensors only
    """
    timestamp = datetime.now().isoformat()
    
    data = {
        'timestamp': timestamp,
        'device_id': 'rapsberry-pi-monitor'
    }
    
    # Collect CPU data (temperature + usage together)
    if self.enabled_sensors.get('temperature', True) or self.enabled_sensors.get('cpu', True):
        cpu_data = {}
        
        if self.enabled_sensors.get('temperature', True):
            cpu_data['temperature'] = self.get_cpu_temperature()
        
        if self.enabled_sensors.get('cpu', True):
            cpu_data.update(self.get_cpu_usage())
        
        if cpu_data:  # Only add cpu key if we collected something
            data['cpu'] = cpu_data
    
    # Collect memory data
    if self.enabled_sensors.get('memory', True):
        data['memory'] = self.get_memory_usage()
    
    # Collect disk data
    if self.enabled_sensors.get('disk', True):
        data['disk'] = self.get_disk_usage()
    
    # Collect network data
    if self.enabled_sensors.get('network', True):
        data['network'] = self.get_network_stats()
    
    enabled_list = [k for k, v in self.enabled_sensors.items() if v]
    logger.info(f"Collected data for enabled sensors: {enabled_list} at {timestamp}")
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
            if 'cpu' in data:
                temp_str = f"Temp: {data['cpu'].get('temperature', 'N/A')}°C" if 'temperature' in data['cpu'] else ''
                usage_str = f"CPU: {data['cpu'].get('usage_percent', 'N/A')}%" if 'usage_percent' in data['cpu'] else ''
                if temp_str or usage_str:
                    print(f"{usage_str} | {temp_str}".strip(' |'))
            if 'memory' in data:
                print(f"Memory: {data['memory']['percent']}% ({data['memory']['used_mb']}/{data['memory']['total_mb']} MB)")
            if 'disk' in data:
                print(f"Disk: {data['disk']['percent']}% ({data['disk']['used_gb']}/{data['disk']['total_gb']} GB)")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


if __name__ == "__main__":
    main()