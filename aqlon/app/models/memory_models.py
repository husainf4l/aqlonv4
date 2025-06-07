"""
Database models for memory subsystem
"""
import uuid
from sqlalchemy import Column, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.sql import func

# Import Base from database
from app.models.database import Base

class MemoryEvent(Base):
    """
    Model for storing memory events in the database
    """
    __tablename__ = "memory_events"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    goal_id = Column(PG_UUID(as_uuid=True), nullable=True)
    step_id = Column(PG_UUID(as_uuid=True), nullable=True)
    agent_action = Column(Text, nullable=False)
    vision_state = Column(Text, nullable=True)
    terminal_output = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)
