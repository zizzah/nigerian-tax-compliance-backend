"""
AI Insights Model
Location: app/models/ai_insight.py
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id   = Column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_type  = Column(String(50), nullable=False)   # cash_flow | overdue_risk | customer_behavior | revenue_trend | anomaly | positive
    severity      = Column(String(20), nullable=False)   # info | warning | critical | positive
    title         = Column(String(255), nullable=False)
    body          = Column(Text, nullable=False)
    action_label  = Column(String(100), nullable=True)
    action_url    = Column(String(500), nullable=True)
    data_snapshot = Column(JSONB, nullable=True)
    is_dismissed  = Column(Boolean, default=False, nullable=False)
    dismissed_at  = Column(DateTime(timezone=True), nullable=True)
    expires_at    = Column(DateTime(timezone=True), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    business = relationship("Business")