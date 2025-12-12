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


@st.cache_resource
def get_storage():
    """Initialize storage with caching."""
    config = load_config()
    questdb_config = config.get('questdb', {})
    return QuestDBStorage(
        host=questdb_config.get('host', 'localhost'),
        port=questdb_config.get('port', 9000)
    )


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
            return df
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
# DEVICE TWIN MANAGEMENT - Using REST API (no azure-iot-hub package needed)
# ============================================================================

def generate_sas_token(uri, key, policy_name, expiry=3600):
    """Generate SAS token for Azure IoT Hub authentication."""
    ttl = int(datetime.now().timestamp()) + expiry
    sign_key = f"{uri}\n{ttl}"
    signature = base64.b64encode(
        hmac.new(
            base64.b64decode(key),
            sign_key.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')  # Decode bytes to string before URL encoding
    
    return f"SharedAccessSignature sr={quote_plus(uri)}&sig={quote_plus(signature)}&se={ttl}&skn={policy_name}"


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
        
        # Generate SAS token
        resource_uri = hostname
        sas_token = generate_sas_token(resource_uri, key, policy)
        
        # Make REST API call
        url = f"https://{hostname}/twins/{device_id}?api-version=2021-04-12"
        headers = {
            'Authorization': sas_token,
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return True, response.json()
        else:
            return False, f"Error {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, f"Exception: {str(e)}"


def update_device_twin_rest(device_id, conn_str, desired_properties):
    """Update device twin desired properties using REST API."""
    try:
        parts = parse_connection_string(conn_str)
        hostname = parts.get('HostName', '')
        key = parts.get('SharedAccessKey', '')
        policy = parts.get('SharedAccessKeyName', 'iothubowner')
        
        # Get current twin first (need etag)
        success, twin = get_device_twin_rest(device_id, conn_str)
        if not success:
            return False, twin
        
        etag = twin.get('etag', '*')
        
        # Generate SAS token
        resource_uri = hostname
        sas_token = generate_sas_token(resource_uri, key, policy)
        
        # Prepare patch
        patch = {
            "properties": {
                "desired": desired_properties
            }
        }
        
        # Make REST API call
        url = f"https://{hostname}/twins/{device_id}?api-version=2021-04-12"
        headers = {
            'Authorization': sas_token,
            'Content-Type': 'application/json',
            'If-Match': etag
        }
        
        response = requests.patch(url, headers=headers, json=patch, timeout=10)
        
        if response.status_code == 200:
            return True, "Device twin updated successfully!"
        else:
            return False, f"Error {response.status_code}: {response.text}"
            
    except Exception as e:
        return False, f"Exception: {str(e)}"


def get_iot_hub_info():
    """Get IoT Hub connection info from config."""
    config = load_config()
    azure_config = config.get('azure', {})
    iot_hub = azure_config.get('iot_hub', {})
    
    # For service operations, we need a connection string with service/registry permissions
    # This should be in your config as 'service_connection_string'
    conn_str = iot_hub.get('service_connection_string') or iot_hub.get('connection_string')
    device_id = iot_hub.get('device_id')
    
    return conn_str, device_id


# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def create_time_series_chart(df, column, title, color):
    """Create a time series chart."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df[column],
        mode='lines+markers',
        name=title,
        line=dict(color=color, width=2),
        marker=dict(size=4)
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Value",
        hovermode='x unified',
        template='plotly_white',
        height=300
    )
    
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
            'steps': [
                {'range': [0, threshold], 'color': 'lightgray'},
                {'range': [threshold, max_value], 'color': 'lightpink'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': threshold
            }
        }
    ))
    
    fig.update_layout(height=250)
    return fig


def main():
    """Main dashboard function."""
    st.title("🔍 Raspberry Pi Network Monitor Dashboard")
    
    # Get IoT Hub connection info
    conn_str, device_id = get_iot_hub_info()
    twin_available = bool(conn_str and device_id)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Time range selector
        time_options = {
            "Last 1 hour": 1,
            "Last 6 hours": 6,
            "Last 12 hours": 12,
            "Last 24 hours": 24,
            "Last 2 days": 48,
            "Last week": 168
        }
        
        time_label = st.selectbox(
            "Time Range",
            options=list(time_options.keys()),
            index=3
        )
        time_range = time_options[time_label]
        
        # Manual refresh button
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.markdown("---")
        
        # Device Twin Configuration
        st.subheader("🔧 Device Twin Control")
        
        if not twin_available:
            st.warning("⚠️ IoT Hub not configured. Add 'service_connection_string' to config.json")
        else:
            # View current twin
            with st.expander("📖 View Current Twin", expanded=False):
                if st.button("Fetch Twin", key="fetch_twin"):
                    with st.spinner("Fetching device twin..."):
                        success, result = get_device_twin_rest(device_id, conn_str)
                        if success:
                            st.success("✅ Twin fetched successfully!")
                            st.json(result.get('properties', {}).get('desired', {}))
                        else:
                            st.error(f"❌ {result}")
            
            # Update collection interval
            with st.expander("⏱️ Collection Interval", expanded=False):
                new_interval = st.number_input(
                    "Interval (seconds)",
                    min_value=5,
                    max_value=300,
                    value=30,
                    step=5,
                    help="How often to collect sensor readings"
                )
                
                if st.button("Apply Interval", key="apply_interval"):
                    with st.spinner("Updating device twin..."):
                        desired = {
                            "collection_interval_seconds": new_interval,
                            "updated_at": datetime.now().isoformat()
                        }
                        success, message = update_device_twin_rest(device_id, conn_str, desired)
                        if success:
                            st.success(f"✅ {message}")
                        else:
                            st.error(f"❌ {message}")
            
            # Update AI settings
            with st.expander("🤖 AI Model Settings", expanded=False):
                enable_local = st.checkbox("Enable Local AI", value=True, key="local_ai")
                enable_cloud = st.checkbox("Enable Cloud AI", value=False, key="cloud_ai")
                
                threshold = st.slider(
                    "Anomaly Threshold",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.5,
                    step=0.05
                )
                
                if st.button("Apply AI Settings", key="apply_ai"):
                    with st.spinner("Updating device twin..."):
                        desired = {
                            "ai_models": {
                                "local": {"enabled": enable_local},
                                "cloud": {"enabled": enable_cloud},
                                "anomaly_threshold": threshold
                            },
                            "updated_at": datetime.now().isoformat()
                        }
                        success, message = update_device_twin_rest(device_id, conn_str, desired)
                        if success:
                            st.success(f"✅ {message}")
                        else:
                            st.error(f"❌ {message}")
            
            # Toggle sensors
            with st.expander("📡 Sensor Control", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    temp_en = st.checkbox("CPU Temp", value=True, key="temp")
                    cpu_en = st.checkbox("CPU Usage", value=True, key="cpu")
                    mem_en = st.checkbox("Memory", value=True, key="mem")
                with col2:
                    disk_en = st.checkbox("Disk", value=True, key="disk")
                    net_en = st.checkbox("Network", value=True, key="net")
                
                if st.button("Apply Sensors", key="apply_sensors"):
                    with st.spinner("Updating device twin..."):
                        desired = {
                            "sensors": {
                                "temperature": {"enabled": temp_en},
                                "cpu": {"enabled": cpu_en},
                                "memory": {"enabled": mem_en},
                                "disk": {"enabled": disk_en},
                                "network": {"enabled": net_en}
                            },
                            "updated_at": datetime.now().isoformat()
                        }
                        success, message = update_device_twin_rest(device_id, conn_str, desired)
                        if success:
                            st.success(f"✅ {message}")
                        else:
                            st.error(f"❌ {message}")
        
        st.markdown("---")
        st.caption("💡 Changes take effect on next device sync")
    
    # Load data
    try:
        df = load_recent_data(time_range)
        stats = load_statistics()
        
        if df.empty:
            st.warning("⚠️ No data available. Make sure the monitoring application is running.")
            return
        
        # Process data
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        latest = df.iloc[-1]
        
        # Status Overview
        st.header("📊 System Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Readings",
                value=f"{stats.get('total_records', 0):,}"
            )
        
        with col2:
            total = max(stats.get('total_records', 1), 1)
            anomaly_count = stats.get('anomaly_count', 0)
            anomaly_rate = (anomaly_count / total) * 100
            st.metric(
                label="Anomalies",
                value=anomaly_count,
                delta=f"{anomaly_rate:.1f}%",
                delta_color="inverse"
            )
        
        with col3:
            st.metric(
                label="Avg CPU Temp",
                value=f"{stats.get('avg_cpu_temp', 0):.1f}°C"
            )
        
        with col4:
            st.metric(
                label="Avg Memory",
                value=f"{stats.get('avg_memory_usage', 0):.1f}%"
            )
        
        # Anomaly Alert
        if latest.get('is_anomaly'):
            st.markdown(
                '<div class="anomaly-alert">⚠️ ANOMALY DETECTED IN LATEST READING!</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="normal-status">✓ System Operating Normally</div>',
                unsafe_allow_html=True
            )
        
        # Current Metrics
        st.header("📈 Current Metrics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            temp = latest.get('cpu_temperature', 0)
            st.plotly_chart(
                create_gauge_chart(temp if temp else 0, "CPU Temp (°C)", 100, 75),
                use_container_width=True
            )
        
        with col2:
            st.plotly_chart(
                create_gauge_chart(latest.get('cpu_usage', 0), "CPU Usage (%)", 100, 80),
                use_container_width=True
            )
        
        with col3:
            st.plotly_chart(
                create_gauge_chart(latest.get('memory_percent', 0), "Memory (%)", 100, 80),
                use_container_width=True
            )
        
        with col4:
            st.plotly_chart(
                create_gauge_chart(latest.get('disk_percent', 0), "Disk (%)", 100, 85),
                use_container_width=True
            )
        
        # Time Series Charts
        st.header("📉 Historical Trends")
        
        tab1, tab2, tab3, tab4 = st.tabs(["CPU", "Memory", "Disk", "Network"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                if 'cpu_temperature' in df.columns and df['cpu_temperature'].notna().any():
                    st.plotly_chart(
                        create_time_series_chart(df, 'cpu_temperature', 'CPU Temperature (°C)', 'red'),
                        use_container_width=True
                    )
                else:
                    st.info("CPU temperature data not available")
            with col2:
                st.plotly_chart(
                    create_time_series_chart(df, 'cpu_usage', 'CPU Usage (%)', 'orange'),
                    use_container_width=True
                )
        
        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    create_time_series_chart(df, 'memory_percent', 'Memory Usage (%)', 'blue'),
                    use_container_width=True
                )
            with col2:
                st.plotly_chart(
                    create_time_series_chart(df, 'memory_used_mb', 'Memory Used (MB)', 'cyan'),
                    use_container_width=True
                )
        
        with tab3:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    create_time_series_chart(df, 'disk_percent', 'Disk Usage (%)', 'green'),
                    use_container_width=True
                )
            with col2:
                st.plotly_chart(
                    create_time_series_chart(df, 'disk_used_gb', 'Disk Used (GB)', 'lightgreen'),
                    use_container_width=True
                )
        
        with tab4:
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(
                    create_time_series_chart(df, 'network_sent_mb', 'Network Sent (MB)', 'purple'),
                    use_container_width=True
                )
            with col2:
                st.plotly_chart(
                    create_time_series_chart(df, 'network_recv_mb', 'Network Received (MB)', 'magenta'),
                    use_container_width=True
                )
        
        # Anomaly Analysis
        st.header("🚨 Anomaly Analysis")
        
        anomalies = df[df['is_anomaly'] == True]
        
        if not anomalies.empty:
            st.warning(f"Found {len(anomalies)} anomalies in the selected time range")
            
            # Anomaly score over time
            fig = px.scatter(
                df,
                x='timestamp',
                y='anomaly_score',
                color='is_anomaly',
                title='Anomaly Score Over Time',
                color_discrete_map={False: 'green', True: 'red'},
                labels={'is_anomaly': 'Anomaly', 'anomaly_score': 'Score'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Recent anomalies table
            st.subheader("Recent Anomalies")
            display_cols = ['timestamp', 'cpu_temperature', 'cpu_usage', 
                          'memory_percent', 'disk_percent', 'anomaly_score']
            available_cols = [col for col in display_cols if col in anomalies.columns]
            anomaly_table = anomalies[available_cols].tail(10)
            st.dataframe(anomaly_table, use_container_width=True)
        else:
            st.success("✅ No anomalies detected in the selected time range!")
        
        # Raw Data
        with st.expander("📋 Raw Data"):
            st.dataframe(df.tail(100), use_container_width=True)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        # Footer
        st.markdown("---")
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        with st.expander("Error Details"):
            st.exception(e)


if __name__ == "__main__":
    main()