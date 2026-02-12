"""
Secrets Management Module
Location: app/core/secrets.py

OPTIONAL: For production AWS Secrets Manager integration
For now, you can skip this file and use environment variables
"""

import os
import json
from typing import Dict, Any, Optional
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class SecretsManager:
    """
    Manage secrets from AWS Secrets Manager or environment variables
    
    USAGE:
        from app.core.secrets import secrets_manager
        
        # Get a secret
        api_key = secrets_manager.get_secret("GROQ_API_KEY")
        
        # Get a JSON secret
        db_config = secrets_manager.get_secret_dict("database-config")
    """
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.use_aws = self.environment == "production" and os.getenv("USE_AWS_SECRETS", "false").lower() == "true"
        
        if self.use_aws:
            try:
                import boto3  # type: ignore
                self.client = boto3.client('secretsmanager')
                logger.info("AWS Secrets Manager enabled")
            except ImportError:
                logger.warning("boto3 not installed. Install with: pip install boto3")
                self.client = None
                self.use_aws = False
        else:
            self.client = None
            logger.info("Using environment variables for secrets")
    
    @lru_cache(maxsize=10)
    def get_secret(self, secret_name: str) -> Optional[str]:
        """
        Get secret from AWS Secrets Manager (production) or env vars (dev)
        
        Args:
            secret_name: Name of secret
            
        Returns:
            Secret value or None
        """
        if self.use_aws and self.client:
            try:
                response = self.client.get_secret_value(SecretId=secret_name)
                
                if 'SecretString' in response:
                    return response['SecretString']
                else:
                    # Binary secret
                    return response['SecretBinary'].decode('utf-8')
                    
            except Exception as e:
                logger.error(f"Failed to get secret {secret_name} from AWS: {e}")
                # Fallback to environment variable
                return os.getenv(secret_name)
        else:
            # Development: use environment variables
            return os.getenv(secret_name)
    
    def get_secret_dict(self, secret_name: str) -> Dict[str, Any]:
        """
        Get secret as JSON dictionary
        
        Args:
            secret_name: Name of secret
            
        Returns:
            Dictionary with secret data
        """
        secret_string = self.get_secret(secret_name)
        
        if secret_string:
            try:
                return json.loads(secret_string)
            except json.JSONDecodeError:
                logger.error(f"Secret {secret_name} is not valid JSON")
                return {}
        
        return {}


# Global instance
secrets_manager = SecretsManager()


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Example 1: Get simple secret (API key)
---------------------------------------
from app.core.secrets import secrets_manager

groq_key = secrets_manager.get_secret("GROQ_API_KEY")


Example 2: Get JSON secret (database config)
---------------------------------------------
from app.core.secrets import secrets_manager

db_config = secrets_manager.get_secret_dict("tax-platform/database")
# Returns: {"host": "...", "port": 5432, "database": "..."}


Example 3: Use in config.py
----------------------------
from app.core.secrets import secrets_manager

class Settings(BaseSettings):
    @property
    def SECRET_KEY(self) -> str:
        if self.ENVIRONMENT == "production":
            return secrets_manager.get_secret("tax-platform/secret-key") or "fallback"
        else:
            return os.getenv("SECRET_KEY", "dev-secret-key")


Example 4: AWS Setup (Production)
----------------------------------
1. Install boto3:
   pip install boto3

2. Set environment variable:
   USE_AWS_SECRETS=true
   
3. Configure AWS credentials:
   AWS_ACCESS_KEY_ID=xxx
   AWS_SECRET_ACCESS_KEY=xxx
   AWS_DEFAULT_REGION=us-east-1

4. Create secrets in AWS Secrets Manager:
   aws secretsmanager create-secret --name "tax-platform/secret-key" --secret-string "your-secret-key"
   aws secretsmanager create-secret --name "tax-platform/groq-api-key" --secret-string "your-groq-key"


FOR NOW: Just use environment variables, this file is for future production use!
"""