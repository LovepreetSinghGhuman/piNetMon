"""
Streamlit Dashboard for Raspberry Pi Network Monitor
Provides real-time visualization and device twin control.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import sys
import os
import json
import requests
import hmac
import hashlib
import base64
from urllib.parse import quote_plus

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from questdb_storage import QuestDBStorage

# Page configuration
st.set_page_config(
    page_title="Pi Network Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .anomaly-alert {
        background-color: #ff4b4b;
        color: white;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
        text-align: center;
        font-weight: bold;
    }
    .normal-status {
        background-color: #00cc00;
        color: white;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
        text-align: center;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# STORAGE
# ============================================================================

@st.cache_resource
def get_storage():
    """Initialize QuestDBStorage with caching (Option 1)."""
    # Configuration still loaded if needed elsewhere
    _ = load_config()
    return QuestDBStorage()


def load_config():
    """Load configuration."""
    dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(dashboard_dir, '..', 'config', 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        return {}


def load_recent_data(hours):
    """Load recent data from QuestDB."""
    storage = get_storage()
    result = storage.get_recent_data(hours=hours)

    if result and 'dataset' in result:
        columns = [col['name'] for col in result.get('columns', [])]
        data = result.get('dataset', [])
        if data:
            df = pd.DataFrame(data, columns=columns)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df.sort_values('timestamp')
    return pd.DataFrame()


def load_statistics():
    """Load storage statistics."""
    storage = get_storage()
    result = storage.get_statistics()

    if result and 'dataset' in result and result['dataset']:
        columns = [col['name'] for col in result.get('columns', [])]
        data = result['dataset'][0]
        return dict(zip(columns, data))
    return {}


# ============================================================================
# DEVICE TWIN MANAGEMENT
# ============================================================================

def generate_sas_token(uri, key, policy_name, expiry=3600):
    """Generate SAS token for Azure IoT Hub authentication."""
    ttl = int(datetime.now().timestamp()) + expiry
    uri_lower = uri.lower()
    sign_key = f"{uri_lower}\n{ttl}"
    signature = base64.b64encode(
        hmac.new(base64.b64decode(key), sign_key.encode('utf-8'), hashlib.sha256).digest()
    ).decode('utf-8')
    return f"SharedAccessSignature sr={quote_plus(uri_lower)}&sig={quote_plus(signature)}&se={ttl}&skn={policy_name}"


def parse_connection_string(conn_str):
    """Parse IoT Hub connection string."""
    parts = {}
    for item in conn_str.split(';'):
        if '=' in item:
            key, value = item.split('=', 1)
            parts[key] = value
    return parts


def get_device_twin_rest(device_id, conn_str):
    """Get device twin using REST API."""
    try:
        parts = parse_connection_string(conn_str)
        hostname = parts.get('HostName', '')
        key = parts.get('SharedAccessKey', '')
        policy = parts.get('SharedAccessKeyName', 'iothubowner')

        sas_token = generate_sas_token(hostname, key, policy)
        url = f"https://{hostname}/twins/{device_id}?api-version=2021-04-12"
        headers = {'Authorization': sas_token, 'Content-Type': 'application/json'}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"Error {response.status_code}: {response.text}"
    except Exception as e:
        return False, f"Exception: {str(e)}"


def update_device_twin_rest(device_id, conn_str, desired_properties):
    """Update device twin desired properties using REST API."""
    success, twin = get_device_twin_rest(device_id, conn_str)
    if not success:
        return False, twin

    etag = twin.get('etag', '*')
    parts = parse_connection_string(conn_str)
    hostname = parts.get('HostName', '')
    key = parts.get('SharedAccessKey', '')
    policy = parts.get('SharedAccessKeyName', 'iothubowner')

    sas_token = generate_sas_token(hostname, key, policy)
    patch = {"properties": {"desired": desired_properties}}
    url = f"https://{hostname}/twins/{device_id}?api-version=2021-04-12"
    headers = {'Authorization': sas_token, 'Content-Type': 'application/json', 'If-Match': etag}

    response = requests.patch(url, headers=headers, json=patch, timeout=10)
    if response.status_code == 200:
        return True, "Device twin updated successfully!"
    else:
        return False, f"Error {response.status_code}: {response.text}"


def get_iot_hub_info():
    """Get IoT Hub connection info from config."""
    config = load_config()
    azure_config = config.get('azure', {})
    iot_hub = azure_config.get('iot_hub', {})
    conn_str = iot_hub.get('service_connection_string') or iot_hub.get('connection_string')
    device_id = iot_hub.get('device_id')
    return conn_str, device_id


def compare_sensor_configs(desired, reported):
    """Compare sensor configurations, ignoring extra fields in reported."""
    if not desired or not reported:
        return False
    
    for sensor_name, desired_config in desired.items():
        if sensor_name not in reported:
            return False
        
        reported_config = reported[sensor_name]
        
        # Check enabled status
        if desired_config.get('enabled') != reported_config.get('enabled'):
            return False
        
        # Check interval if specified in desired
        if 'interval_seconds' in desired_config:
            if desired_config.get('interval_seconds') != reported_config.get('interval_seconds'):
                return False
    
    return True


# ============================================================================
# VISUALIZATION HELPERS
# ============================================================================

def create_time_series_chart(df, column, title, color):
    """Create a time series chart."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['timestamp'], y=df[column], mode='lines+markers',
                             name=title, line=dict(color=color, width=2), marker=dict(size=4)))
    fig.update_layout(title=title, xaxis_title="Time", yaxis_title="Value",
                      hovermode='x unified', template='plotly_white', height=300)
    return fig


def create_gauge_chart(value, title, max_value, threshold):
    """Create a gauge chart."""
    color = 'red' if value > threshold else 'green'
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={'text': title},
        gauge={
            'axis': {'range': [None, max_value]},
            'bar': {'color': color},
            'steps': [{'range': [0, threshold], 'color': 'lightgray'},
                      {'range': [threshold, max_value], 'color': 'lightpink'}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': threshold}
        }
    ))
    fig.update_layout(height=250)
    return fig


# ============================================================================
# MAIN DASHBOARD
# ============================================================================

def main():
    st.title("🔍 Raspberry Pi Network Monitor Dashboard")

    # IoT Hub info
    conn_str, device_id = get_iot_hub_info()
    twin_available = bool(conn_str and device_id)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")

        # Time range selector
        time_options = {"Last 1 hour": 1, "Last 6 hours": 6, "Last 12 hours": 12,
                        "Last 24 hours": 24, "Last 2 days": 48, "Last week": 168}
        time_label = st.selectbox("Time Range", options=list(time_options.keys()), index=3)
        time_range = time_options[time_label]

        # Manual refresh
        if st.button("🔄 Refresh Now"):
            st.rerun()

        st.markdown("---")

        # Device Twin
        st.subheader("🔧 Device Twin Control")
        if not twin_available:
            st.warning("⚠️ IoT Hub not configured. Add 'service_connection_string' to config.json")
            current_twin = {}
        else:
            success, twin_data = get_device_twin_rest(device_id, conn_str)
            current_twin = twin_data.get('properties', {}).get('desired', {}) if success else {}

        # Device Twin Control inputs
        if twin_available and current_twin:
            st.write("**Sensor Configuration**")
            
            # Get current sensor settings from twin or defaults
            sensors = current_twin.get('sensors', {})
            
            cpu_enabled = st.checkbox("CPU Monitoring", 
                                     value=sensors.get('cpu', {}).get('enabled', True))
            memory_enabled = st.checkbox("Memory Monitoring", 
                                        value=sensors.get('memory', {}).get('enabled', True))
            disk_enabled = st.checkbox("Disk Monitoring", 
                                      value=sensors.get('disk', {}).get('enabled', True))
            network_enabled = st.checkbox("Network Monitoring", 
                                         value=sensors.get('network', {}).get('enabled', True))
            temp_enabled = st.checkbox("Temperature Monitoring", 
                                      value=sensors.get('temperature', {}).get('enabled', True))
            
            st.write("**Collection Intervals (seconds)**")
            cpu_interval = st.number_input("CPU Interval", min_value=10, max_value=300, 
                                          value=sensors.get('cpu', {}).get('interval_seconds', 30))
            memory_interval = st.number_input("Memory Interval", min_value=10, max_value=300, 
                                             value=sensors.get('memory', {}).get('interval_seconds', 30))
            
            st.write("**AI Configuration**")
            ai_models = current_twin.get('ai_models', {})
            local_ai = ai_models.get('local', {})
            anomaly_det = local_ai.get('anomaly_detection', {})
            
            local_ai_enabled = st.checkbox("Local AI Anomaly Detection", 
                                          value=anomaly_det.get('enabled', True))
            cloud_ai_enabled = st.checkbox("Cloud AI", 
                                          value=ai_models.get('cloud', {}).get('enabled', False))
            
            st.write("**Anomaly Thresholds**")
            thresholds = anomaly_det.get('thresholds', {})
            cpu_temp_thresh = st.slider("CPU Temperature (°C)", 60, 100, 
                                        value=int(thresholds.get('cpu_temperature', 80)))
            cpu_usage_thresh = st.slider("CPU Usage (%)", 50, 100, 
                                         value=int(thresholds.get('cpu_usage', 90)))
            memory_thresh = st.slider("Memory Usage (%)", 50, 100, 
                                     value=int(thresholds.get('memory_percent', 85)))
            disk_thresh = st.slider("Disk Usage (%)", 50, 100, 
                                   value=int(thresholds.get('disk_percent', 90)))
            
            # Update button
            if st.button("📤 Update Device Twin", type="primary"):
                desired_properties = {
                    "sensors": {
                        "cpu": {"enabled": cpu_enabled, "interval_seconds": cpu_interval},
                        "memory": {"enabled": memory_enabled, "interval_seconds": memory_interval},
                        "disk": {"enabled": disk_enabled},
                        "network": {"enabled": network_enabled},
                        "temperature": {"enabled": temp_enabled}
                    },
                    "ai_models": {
                        "local": {
                            "anomaly_detection": {
                                "enabled": local_ai_enabled,
                                "thresholds": {
                                    "cpu_temperature": float(cpu_temp_thresh),
                                    "cpu_usage": float(cpu_usage_thresh),
                                    "memory_percent": float(memory_thresh),
                                    "disk_percent": float(disk_thresh)
                                }
                            }
                        },
                        "cloud": {"enabled": cloud_ai_enabled}
                    }
                }
                
                success, message = update_device_twin_rest(device_id, conn_str, desired_properties)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(f"Failed to update: {message}")
        elif twin_available:
            st.info("Loading device twin configuration...")

        # Configuration Status Monitor
        if twin_available:
            st.markdown("---")
            st.subheader("📋 Configuration Status")
            
            success, twin_data = get_device_twin_rest(device_id, conn_str)
            if success:
                desired = twin_data.get('properties', {}).get('desired', {})
                reported = twin_data.get('properties', {}).get('reported', {})
                
                # Last modified time for desired properties
                desired_metadata = twin_data.get('properties', {}).get('desired', {}).get('$metadata', {})
                if '$lastUpdated' in desired_metadata:
                    last_updated = desired_metadata['$lastUpdated']
                    st.caption(f"🕐 Last updated: {last_updated}")
                
                # Check sync status
                reported_config = reported.get('configuration', {})
                if reported_config:
                    # Compare sensors using the new comparison function
                    desired_sensors = desired.get('sensors', {})
                    reported_sensors = reported_config.get('sensors', {})
                    
                    if compare_sensor_configs(desired_sensors, reported_sensors):
                        st.success("✅ Configuration is in sync")
                    else:
                        st.warning("⚠️ Configuration update pending")
                        st.caption("Device hasn't reported back the new configuration yet")
                else:
                    st.info("ℹ️ Waiting for device to report configuration...")
                
                # View full twin data
                with st.expander("🔍 View Full Device Twin"):
                    tab1, tab2 = st.tabs(["Desired Properties", "Reported Properties"])
                    with tab1:
                        st.json(desired)
                    with tab2:
                        st.json(reported)

    # Load data
    df = load_recent_data(time_range)
    stats = load_statistics()

    if df.empty:
        st.warning("⚠️ No data available. Make sure the monitoring application is running.")
        return

    latest = df.iloc[-1]

    # Overview metrics
    st.header("📊 System Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Readings", f"{stats.get('total_records', 0):,}")
    total = max(stats.get('total_records', 1), 1)
    anomaly_count = stats.get('anomaly_count', 0)
    anomaly_rate = (anomaly_count / total) * 100
    col2.metric("Anomalies", anomaly_count, f"{anomaly_rate:.1f}%", delta_color="inverse")
    col3.metric("Avg CPU Temp", f"{stats.get('avg_cpu_temp', 0):.1f}°C")
    col4.metric("Avg Memory", f"{stats.get('avg_memory_usage', 0):.1f}%")

    # Anomaly alert
    if latest.get('is_anomaly'):
        st.markdown('<div class="anomaly-alert">⚠️ ANOMALY DETECTED IN LATEST READING!</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="normal-status">✓ System Operating Normally</div>', unsafe_allow_html=True)

    # Download raw data section
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.subheader("📥 Download Raw Data")
    with col2:
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📄 Download CSV",
            data=csv_data,
            file_name=f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
    with col3:
        json_data = df.to_json(orient='records', date_format='iso').encode('utf-8')
        st.download_button(
            label="📋 Download JSON",
            data=json_data,
            file_name=f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

    # Current metrics charts
    st.header("📈 Current Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    # Try both column names for CPU usage (cpu_usage_percent or cpu_usage)
    cpu_usage_value = latest.get('cpu_usage_percent', latest.get('cpu_usage', 0))
    
    col1.plotly_chart(create_gauge_chart(latest.get('cpu_temperature', 0), "CPU Temp (°C)", 100, 75), use_container_width=True)
    col2.plotly_chart(create_gauge_chart(cpu_usage_value, "CPU Usage (%)", 100, 80), use_container_width=True)
    col3.plotly_chart(create_gauge_chart(latest.get('memory_percent', 0), "Memory (%)", 100, 80), use_container_width=True)
    col4.plotly_chart(create_gauge_chart(latest.get('disk_percent', 0), "Disk (%)", 100, 85), use_container_width=True)

    # Historical trends & anomalies
    st.header("📉 Historical Trends")
    tab1, tab2, tab3, tab4 = st.tabs(["CPU", "Memory", "Disk", "Network"])
    
    # Determine which CPU usage column exists
    cpu_usage_col = 'cpu_usage_percent' if 'cpu_usage_percent' in df.columns else 'cpu_usage'
    
    with tab1:
        st.plotly_chart(create_time_series_chart(df, 'cpu_temperature', 'CPU Temperature (°C)', '#FF6B6B'), use_container_width=True)
        if cpu_usage_col in df.columns:
            st.plotly_chart(create_time_series_chart(df, cpu_usage_col, 'CPU Usage (%)', '#4ECDC4'), use_container_width=True)
        
    with tab2:
        st.plotly_chart(create_time_series_chart(df, 'memory_percent', 'Memory Usage (%)', '#95E1D3'), use_container_width=True)
        st.plotly_chart(create_time_series_chart(df, 'memory_used_mb', 'Memory Used (MB)', '#F38181'), use_container_width=True)
        
    with tab3:
        st.plotly_chart(create_time_series_chart(df, 'disk_percent', 'Disk Usage (%)', '#AA96DA'), use_container_width=True)
        st.plotly_chart(create_time_series_chart(df, 'disk_used_gb', 'Disk Used (GB)', '#FCBAD3'), use_container_width=True)
        
    with tab4:
        st.plotly_chart(create_time_series_chart(df, 'network_sent_mb', 'Network Sent (MB)', '#A8E6CF'), use_container_width=True)
        st.plotly_chart(create_time_series_chart(df, 'network_recv_mb', 'Network Received (MB)', '#FFD3B6'), use_container_width=True)
    
    # Anomalies section
    st.header("⚠️ Anomalies")
    anomalies = df[df['is_anomaly'] == True] if 'is_anomaly' in df.columns else pd.DataFrame()
    if not anomalies.empty:
        st.write(f"Found {len(anomalies)} anomalous readings in the selected time range:")
        # Use the correct CPU usage column in the anomalies table
        display_cols = ['timestamp', 'cpu_temperature', cpu_usage_col, 'memory_percent', 'disk_percent', 'anomaly_score']
        display_cols = [col for col in display_cols if col in anomalies.columns]
        st.dataframe(anomalies[display_cols], use_container_width=True)
    else:
        st.success("No anomalies detected in this time range!")

    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()