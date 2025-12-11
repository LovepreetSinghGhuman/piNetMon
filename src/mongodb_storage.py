"""
MongoDB Atlas Integration Module
Handles cloud storage of sensor data in MongoDB Atlas (free tier).
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    logging.warning("pymongo not installed. MongoDB integration disabled.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDBStorage:
    """Manages MongoDB Atlas cloud storage for sensor data."""
    
    def __init__(self, connection_string: Optional[str] = None, 
                 database_name: str = "piNetMon",
                 collection_name: str = "sensor_data"):
        """
        Initialize MongoDB Atlas connection.
        
        Args:
            connection_string: MongoDB Atlas connection string
            database_name: Name of the database
            collection_name: Name of the collection
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.collection_name = collection_name
        self.client: Optional[MongoClient] = None
        self.db = None
        self.collection = None
        self.is_connected = False
        
        if not MONGODB_AVAILABLE:
            logger.error("pymongo not installed. Install with: pip install pymongo")
            return
        
        if connection_string:
            self.connect()
        else:
            logger.warning("MongoDB connection string not provided")
    
    def connect(self):
        """Connect to MongoDB Atlas."""
        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            self.is_connected = True
            
            # Create indexes for better query performance
            self.collection.create_index("timestamp")
            self.collection.create_index("device_id")
            self.collection.create_index([("timestamp", -1)])
            
            logger.info(f"Connected to MongoDB Atlas: {self.database_name}.{self.collection_name}")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB Atlas: {e}")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            self.is_connected = False
    
    def disconnect(self):
        """Disconnect from MongoDB Atlas."""
        if self.client:
            self.client.close()
            self.is_connected = False
            logger.info("Disconnected from MongoDB Atlas")
    
    def store_sensor_data(self, data: Dict[str, Any]) -> bool:
        """
        Store sensor data in MongoDB Atlas.
        
        Args:
            data: Sensor data dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected:
            logger.warning("Not connected to MongoDB Atlas")
            return False
        
        try:
            # Add metadata
            document = {
                **data,
                'stored_at': datetime.utcnow(),
                'source': 'raspberry-pi',
                'cloud_provider': 'mongodb_atlas'
            }
            
            # Insert document
            result = self.collection.insert_one(document)
            logger.info(f"Data stored in MongoDB: {result.inserted_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store data in MongoDB: {e}")
            return False
    
    def get_recent_data(self, hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieve recent sensor data from MongoDB.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of documents to return
            
        Returns:
            list: List of sensor data documents
        """
        if not self.is_connected:
            logger.warning("Not connected to MongoDB Atlas")
            return []
        
        try:
            cutoff_time = datetime.utcnow()
            cutoff_time = cutoff_time.replace(
                hour=cutoff_time.hour - hours
            )
            
            cursor = self.collection.find(
                {'stored_at': {'$gte': cutoff_time}},
                {'_id': 0}  # Exclude MongoDB _id field
            ).sort('timestamp', -1).limit(limit)
            
            data = list(cursor)
            logger.info(f"Retrieved {len(data)} documents from MongoDB")
            return data
            
        except Exception as e:
            logger.error(f"Failed to retrieve data from MongoDB: {e}")
            return []
    
    def get_anomalies(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve anomalous data points from MongoDB.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of documents to return
            
        Returns:
            list: List of anomalous data documents
        """
        if not self.is_connected:
            logger.warning("Not connected to MongoDB Atlas")
            return []
        
        try:
            cutoff_time = datetime.utcnow()
            cutoff_time = cutoff_time.replace(
                hour=cutoff_time.hour - hours
            )
            
            cursor = self.collection.find(
                {
                    'stored_at': {'$gte': cutoff_time},
                    'local_analysis.is_anomaly': True
                },
                {'_id': 0}
            ).sort('timestamp', -1).limit(limit)
            
            data = list(cursor)
            logger.info(f"Retrieved {len(data)} anomalies from MongoDB")
            return data
            
        except Exception as e:
            logger.error(f"Failed to retrieve anomalies from MongoDB: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get collection statistics.
        
        Returns:
            dict: Collection statistics
        """
        if not self.is_connected:
            return {}
        
        try:
            total_count = self.collection.count_documents({})
            anomaly_count = self.collection.count_documents(
                {'local_analysis.is_anomaly': True}
            )
            
            # Get oldest and newest documents
            oldest = self.collection.find_one(
                sort=[('timestamp', 1)]
            )
            newest = self.collection.find_one(
                sort=[('timestamp', -1)]
            )
            
            return {
                'total_documents': total_count,
                'anomaly_count': anomaly_count,
                'oldest_record': oldest.get('timestamp') if oldest else None,
                'newest_record': newest.get('timestamp') if newest else None,
                'database': self.database_name,
                'collection': self.collection_name,
                'connected': self.is_connected
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics from MongoDB: {e}")
            return {}
    
    def cleanup_old_data(self, days: int = 30):
        """
        Remove data older than specified days.
        
        Args:
            days: Number of days to retain data
        """
        if not self.is_connected:
            logger.warning("Not connected to MongoDB Atlas")
            return
        
        try:
            cutoff_time = datetime.utcnow()
            cutoff_time = cutoff_time.replace(
                day=cutoff_time.day - days
            )
            
            result = self.collection.delete_many(
                {'stored_at': {'$lt': cutoff_time}}
            )
            
            logger.info(f"Deleted {result.deleted_count} old documents from MongoDB")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data in MongoDB: {e}")


def main():
    """Test MongoDB Atlas integration."""
    # This requires a MongoDB Atlas connection string
    # Get one for free at: https://www.mongodb.com/cloud/atlas/register
    
    connection_string = "mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/"
    
    print("=== MongoDB Atlas Integration Test ===")
    print("To use this, you need to:")
    print("1. Sign up for free at https://www.mongodb.com/cloud/atlas/register")
    print("2. Create a free cluster (M0)")
    print("3. Get your connection string")
    print("4. Update config/config.json with your connection string")
    
    # Test with dummy connection string (will fail, but shows usage)
    storage = MongoDBStorage(connection_string)
    
    if storage.is_connected:
        # Test data
        test_data = {
            'timestamp': datetime.now().isoformat(),
            'device_id': 'rapsberry-pi-monitor',
            'cpu': {
                'temperature': 45.3,
                'usage_percent': 30.0
            },
            'memory': {
                'percent': 50.0
            }
        }
        
        # Store data
        storage.store_sensor_data(test_data)
        
        # Get statistics
        stats = storage.get_statistics()
        print(f"\nStatistics: {json.dumps(stats, indent=2)}")
        
        # Disconnect
        storage.disconnect()
    else:
        print("\nNot connected. Configure your MongoDB Atlas connection string first.")


if __name__ == "__main__":
    main()
