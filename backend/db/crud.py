from sqlalchemy.orm import Session
from . import models, schemas
from passlib.context import CryptContext

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ==========================================
# USER OPERATIONS
# ==========================================
def get_user_by_user_id(db: Session, user_id: str):
    """Fetch user for authentication."""
    return db.query(models.User).filter(models.User.user_id == user_id).first()

def get_all_users(db: Session):
    """Fetch all users for the Admin Dashboard."""
    return db.query(models.User).all()

def create_user(db: Session, user: schemas.UserCreate):
    """Provision a new operator from Admin Dashboard."""
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        user_id=user.user_id,
        password_hash=hashed_password,
        full_name=user.full_name,
        role=user.role,
        clearance_level=user.clearance_level,
        status="offline"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_status(db: Session, user_id: str, new_status: str):
    """Update online/offline status (e.g., when forced logged out)."""
    user = get_user_by_user_id(db, user_id)
    if user:
        user.status = new_status
        db.commit()
        db.refresh(user)
    return user

def delete_user(db: Session, user_id: str):
    """Delete an operator from Admin Dashboard."""
    user = get_user_by_user_id(db, user_id)
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

# ==========================================
# CAMERA OPERATIONS
# ==========================================
def get_cameras(db: Session):
    """Fetch grid for the dashboard."""
    return db.query(models.Camera).all()

# ==========================================
# INCIDENT (ALERT) OPERATIONS
# ==========================================
def create_incident(db: Session, incident: schemas.IncidentCreate):
    """Log an AI threat detection into the database."""
    db_incident = models.Incident(
        camera_id=incident.camera_id,
        entity_type=incident.entity_type,
        identifier=incident.identifier,
        confidence=incident.confidence,
        image_path=incident.image_path,
        status="UNRESOLVED"
    )
    db.add(db_incident)
    db.commit()
    db.refresh(db_incident)
    return db_incident

def get_unresolved_incidents(db: Session):
    """Fetch active alerts for the right sidebar."""
    return db.query(models.Incident).filter(models.Incident.status == "UNRESOLVED").order_by(models.Incident.timestamp.desc()).all()

def dismiss_incident(db: Session, incident_id: str):
    """Mark an incident as dismissed."""
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if incident:
        incident.status = "DISMISSED"
        db.commit()
        db.refresh(incident)
    return incident

# ==========================================
# AUDIT LOG OPERATIONS
# ==========================================
def create_audit_log(db: Session, log: schemas.AuditLogCreate):
    """Record an action in the system."""
    db_log = models.AuditLog(
        user_id=log.user_id,
        action_category=log.action_category,
        event_details=log.event_details,
        target_system=log.target_system
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log

def get_audit_logs(db: Session, limit: int = 50):
    """Fetch logs for the Admin Dashboard."""
    return db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(limit).all()