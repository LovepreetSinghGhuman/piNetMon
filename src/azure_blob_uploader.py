"""
Azure Blob Storage Integration
"""

import os
from azure.storage.blob import BlobServiceClient
from datetime import datetime
import logging

logger = logging.getLogger("AzureBlobUploader")

class AzureBlobUploader:
    def __init__(self, connection_string: str, container_name: str):
        self.connection_string = connection_string
        self.container_name = container_name
        self.service_client = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.service_client.get_container_client(container_name)
        try:
            self.container_client.create_container()
        except Exception:
            pass  # Container may already exist

    def upload_text(self, blob_name: str, text: str) -> bool:
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            blob_client.upload_blob(text, overwrite=True)
            logger.info(f"Uploaded blob: {blob_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload blob: {e}")
            return False

    def upload_file(self, blob_name: str, file_path: str) -> bool:
        try:
            blob_client = self.container_client.get_blob_client(blob_name)
            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            logger.info(f"Uploaded file as blob: {blob_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            return False
