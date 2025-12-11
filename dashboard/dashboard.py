"""
Streamlit Dashboard for Raspberry Pi Network Monitor
Provides real-time visualization and control interface.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
import os
import json

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
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .anomaly-alert {
        background-color: #ff4b4b;
        color: white;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .normal-status {
        background-color: #00cc00;
        color: white;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
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


@st.cache_data(ttl=5)
def load_recent_data(hours):
    """Load recent data with caching."""
    storage = get_storage()
    result = storage.get_recent_data(hours=hours)
    
    # Convert QuestDB result to DataFrame format
    if result and 'dataset' in result:
        columns = [col['name'] for col in result.get('columns', [])]
        data = result.get('dataset', [])
        df = pd.DataFrame(data, columns=columns)
        return df.to_dict('records') if not df.empty else []
    return []


@st.cache_data(ttl=30)
def load_statistics():
    """Load storage statistics."""
    storage = get_storage()
    result = storage.get_statistics()
    
    # Convert QuestDB result to dict format
    if result and 'dataset' in result and len(result['dataset']) > 0:
        columns = [col['name'] for col in result.get('columns', [])]
        data = result['dataset'][0]
        return dict(zip(columns, data))
    return {}


def load_config():
    """Load configuration."""
    # Use absolute path relative to dashboard script location
    dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(dashboard_dir, '..', 'config', 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        return {}


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
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Time range selector
        time_range = st.selectbox(
            "Time Range",
            options=[1, 6, 12, 24, 48, 168],
            format_func=lambda x: f"Last {x} hours" if x < 24 else f"Last {x//24} days",
            index=3
        )
        
        # Refresh interval
        refresh_interval = st.number_input(
            "Auto-refresh (seconds)",
            min_value=5,
            max_value=300,
            value=30,
            step=5
        )
        
        # Manual refresh button
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        
        # Show configuration
        st.subheader("📋 Configuration")
        config = load_config()
        if config:
            st.json(config['sensors'])
    
    # Load data
    try:
        data = load_recent_data(time_range)
        stats = load_statistics()
        
        if not data:
            st.warning("No data available. Make sure the monitoring application is running.")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # Get latest reading
        latest = df.iloc[-1]
        
        # Status Overview
        st.header("📊 Current Status")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Readings",
                value=stats.get('total_records', 0),
                delta=None
            )
        
        with col2:
            anomaly_rate = (stats.get('anomaly_count', 0) / max(stats.get('total_records', 1), 1)) * 100
            st.metric(
                label="Anomalies Detected",
                value=stats.get('anomaly_count', 0),
                delta=f"{anomaly_rate:.1f}%"
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
            temp = latest.get('cpu_temperature')
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
        st.header("📉 Historical Data")
        
        tab1, tab2, tab3, tab4 = st.tabs(["CPU", "Memory", "Disk", "Network"])
        
        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                if 'cpu_temperature' in df.columns and df['cpu_temperature'].notna().any():
                    st.plotly_chart(
                        create_time_series_chart(df, 'cpu_temperature', 'CPU Temperature (°C)', 'red'),
                        use_container_width=True
                    )
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
            st.write(f"Found {len(anomalies)} anomalies in the selected time range")
            
            # Show anomaly distribution over time
            fig = px.scatter(
                df,
                x='timestamp',
                y='anomaly_score',
                color='is_anomaly',
                title='Anomaly Score Over Time',
                color_discrete_map={0: 'green', 1: 'red'},
                labels={'is_anomaly': 'Is Anomaly', 'anomaly_score': 'Anomaly Score'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Recent anomalies table
            st.subheader("Recent Anomalies")
            anomaly_table = anomalies[['timestamp', 'cpu_temperature', 'cpu_usage', 
                                       'memory_percent', 'disk_percent', 'anomaly_score']].tail(10)
            st.dataframe(anomaly_table, use_container_width=True)
        else:
            st.success("No anomalies detected in the selected time range! 🎉")
        
        # Raw Data Table
        with st.expander("📋 View Raw Data"):
            st.dataframe(df.tail(50), use_container_width=True)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv,
                file_name=f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.exception(e)
    
    # Auto-refresh
    if refresh_interval > 0:
        import time
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
