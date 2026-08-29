import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(50), unique=True, index=True, nullable=False) # e.g., "ID-8842"
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), default="user") # "admin" or "user"
    clearance_level = Column(String(50), default="STANDARD OPERATOR")
    status = Column(String(20), default="offline") # "online" or "offline"

    # Relationships
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(50), primary_key=True, index=True) # e.g., "CAM-01"
    name = Column(String(100), nullable=False)
    coordinates = Column(String(100))
    stream_url = Column(String(255))

    # Relationships
    incidents = relationship("Incident", back_populates="camera")

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id = Column(String(50), ForeignKey("cameras.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    entity_type = Column(String(50)) # Person, Vehicle, Animal
    identifier = Column(String(100), nullable=True) # Face ID or ANPR Plate
    confidence = Column(Float)
    image_path = Column(String(255), nullable=True)
    status = Column(String(20), default="UNRESOLVED") # UNRESOLVED, DISMISSED

    # Relationships
    camera = relationship("Camera", back_populates="incidents")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) # Nullable for system events
    timestamp = Column(DateTime, default=datetime.utcnow)
    action_category = Column(String(50)) # SESSION, AI_CONTROL, SECURITY, PROVISION
    event_details = Column(String(255))
    target_system = Column(String(100))

    # Relationships
    user = relationship("User", back_populates="audit_logs")