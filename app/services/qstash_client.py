"""
QStash Client for Background Tasks
Location: app/services/qstash_client.py
"""
from upstash_qstash import QStash
from app.core.config import settings

qstash = QStash(token=settings.QSTASH_TOKEN)