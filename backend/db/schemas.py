from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

# --------------------------
# USER SCHEMAS
# --------------------------
class UserBase(BaseModel):
    user_id: str
    full_name: str
    role: str
    clearance_level: str
    status: str

class UserCreate(UserBase):
    password: str  # The raw password from the frontend before hashing

class UserResponse(UserBase):
    id: UUID
    
    model_config = ConfigDict(from_attributes=True)

# --------------------------
# CAMERA SCHEMAS
# --------------------------
class CameraResponse(BaseModel):
    id: str
    name: str
    coordinates: Optional[str] = None
    stream_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --------------------------
# INCIDENT SCHEMAS
# --------------------------
class IncidentCreate(BaseModel):
    camera_id: str
    entity_type: str
    identifier: Optional[str] = None
    confidence: float
    image_path: Optional[str] = None

class IncidentResponse(BaseModel):
    id: UUID
    camera_id: str
    timestamp: datetime
    entity_type: str
    identifier: Optional[str]
    confidence: float
    image_path: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)

# --------------------------
# AUDIT LOG SCHEMAS
# --------------------------
class AuditLogCreate(BaseModel):
    user_id: Optional[UUID] = None
    action_category: str
    event_details: str
    target_system: str

class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    timestamp: datetime
    action_category: str
    event_details: str
    target_system: str

    model_config = ConfigDict(from_attributes=True)