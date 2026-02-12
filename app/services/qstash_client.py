"""
QStash Client for Background Tasks
Location: app/services/qstash_client.py
"""
from qstash import QStash # type: ignore
from app.core.config import settings

qstash = QStash(token=settings.QSTASH_TOKEN)