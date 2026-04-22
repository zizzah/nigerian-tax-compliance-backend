"""
QStash Client for Background Tasks - COMPLETE FIX
Location: app/services/qstash_client.py

This adds the 'publish' method to the qstash object so documents.py works
"""
from app.core.config import settings
import requests
import logging

logger = logging.getLogger(__name__)


class QStashClient:
    """QStash client that works with the documents.py code"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://qstash.upstash.io/v2"
    
    def publish(self, url: str, body: dict, delay: int = 0, retries: int = 3):
        """
        Publish a message to QStash (using HTTP API)
        
        Args:
            url: Callback URL to call
            body: JSON body to send
            delay: Delay in seconds (default: 0 - immediate)
            retries: Number of retries (default: 3)
        
        Returns:
            dict: Response from QStash with messageId
        """
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Upstash-Retries": str(retries),
        }
        
        # Add delay header if specified
        if delay > 0:
            headers["Upstash-Delay"] = f"{delay}s"
        
        # QStash publish endpoint
        publish_url = f"{self.base_url}/publish/{url}"
        
        try:
            response = requests.post(
                publish_url,
                headers=headers,
                json=body,
                timeout=10
            )
            
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"QStash task published: {result.get('messageId')}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"QStash publish failed: {e}")
            raise Exception(f"Failed to publish to QStash: {str(e)}")


# Initialize global qstash client
qstash = QStashClient(token=settings.QSTASH_TOKEN)


# Keep the publish_task function for backwards compatibility
def publish_task(url: str, body: dict, delay: int = 0, retries: int = 3):
    """Wrapper function that calls qstash.publish()"""
    return qstash.publish(url=url, body=body, delay=delay, retries=retries)